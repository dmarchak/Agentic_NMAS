"""Phase 2: reach the device, and diagnose when you cannot.

**Reaching the device is what verifies the management interface.** There is
no earlier moment at which that can be established — the name is checked for
spelling and never against the device, because the device did not exist when
the config was generated.

So the three states are not two:

* `answered` is a fact about the device;
* `answered_but_refused_the_credential` rules out the interface and the
  address, because something is there;
* `did_not_answer` **proves nothing about why**, and must not be recorded as
  "wrong interface". Same distinction as `inconclusive` is to `failed`.
"""

import json
import os

import pytest

dukpy = pytest.importorskip("dukpy")

from modules.nsot.onboard import (ANSWERED, DID_NOT_ANSWER,  # noqa: E402
                                  REFUSED_CREDENTIAL)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    from modules.nsot import manifest as _m, repo as _repo
    from modules.nsot.repo import GoldenItem, adopt_identity

    list_dir = tmp_path / "probe"
    repo_dir = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo_dir, "host_vars"), exist_ok=True)
    # LISTS_DIR too: a module holding its own `get_list_data_dir`
    # binding would still resolve into the live data directory.
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda k, d=None: {"nsot_git_author_name": "NMAS",
                                           "nsot_git_author_email": "n@l"}.get(k, d))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda c: None)
    monkeypatch.setattr("modules.secrets_store.KEY_FILE", str(tmp_path / "key.key"))
    _repo.init_repo(repo_dir)
    identity = adopt_identity(repo_dir, GoldenItem("bp1", "", "203.0.113.31"))
    _m.upsert_device(repo_dir, identity, "bp1", mgmt_ip="203.0.113.31",
                     platform="cisco_iosxe", pending=True)
    return repo_dir


def _verify(repo, *, online, reach=None, **kw):
    from modules.nsot.onboard import verify_device

    if reach is None:
        def reach(*a, **k):
            return "bp1#"
    return verify_device(repo, "bp1", "probe", online=online, reach=reach,
                         interface="GigabitEthernet2", **kw)


class TestVerificationIsAFactAboutTheDevice:

    def test_reaching_it_is_the_verification(self, repo):
        out = _verify(repo, online=lambda ip: True)
        assert out["state"] == ANSWERED
        assert out["answered"] is True
        assert out["causes"] == [], "a success must not offer causes"

    def test_silence_is_recorded_as_silence(self, repo):
        """**Not 'wrong interface'.** Failing to reach proves nothing about
        why; recording a cause as the outcome would be the classifier
        reading a connection failure as a device verdict."""
        out = _verify(repo, online=lambda ip: False)
        assert out["state"] == DID_NOT_ANSWER
        assert out["answered"] is False
        assert "did_not_answer" == out["state"]
        assert "interface" not in out["state"]

    def test_something_answering_rules_two_causes_out(self, repo):
        """A device that refuses the credential has proved its interface and
        its address. Offering the interface as a cause there would send the
        operator to the console for a question already answered."""
        def _refuse(*a, **k):
            raise RuntimeError("Authentication to device failed")

        out = _verify(repo, online=lambda ip: True, reach=_refuse)
        assert out["state"] == REFUSED_CREDENTIAL
        assert len(out["causes"]) == 1
        assert "credential" in out["causes"][0]["cause"]

    def test_a_broken_check_is_not_a_verdict(self, repo):
        """If the reachability check itself raises, that is not evidence
        about the device — a check that did not run has not passed."""
        def _boom(ip):
            raise OSError("no raw socket")

        out = _verify(repo, online=_boom)
        assert out["state"] == DID_NOT_ANSWER
        assert "check itself failed" in out["error"]


class TestItDiagnosesRatherThanFails:

    def test_the_interface_is_named_first(self, repo):
        """It is the only cause nothing before this moment could catch."""
        out = _verify(repo, online=lambda ip: False)
        assert "GigabitEthernet2" in out["causes"][0]["cause"]

    def test_every_cause_carries_a_command_that_settles_it(self, repo):
        out = _verify(repo, online=lambda ip: False)
        assert len(out["causes"]) >= 3
        for c in out["causes"]:
            assert c["command"], c
            assert c["why"], c
            assert c["where"], c
        assert any("show ip interface brief" == c["command"]
                   for c in out["causes"])

    def test_the_recovery_command_names_the_real_path(self, repo):
        """An operator reading this is already having a bad day, so the
        command is given with the actual repo path rather than a
        placeholder."""
        from modules.nsot.onboard import stage_bootstrap_credential

        stage_bootstrap_credential(repo, "bp1", "OneTimeValue123456789")
        out = _verify(repo, online=lambda ip: False)
        assert out["recovery"]["available"] is True
        assert repo in out["recovery"]["command"]
        assert "staged_bootstrap_credential" in out["recovery"]["command"]

    def test_no_staged_credential_says_so_rather_than_offering_one(self, repo):
        out = _verify(repo, online=lambda ip: False)
        assert out["recovery"]["available"] is False
        assert out["recovery"]["note"]

    def test_the_recovery_command_does_not_contain_the_secret(self, repo):
        """It prints the value; it must not BE the value. A diagnostic that
        copies the secret it recovers is a second place the secret lives."""
        from modules.nsot.onboard import stage_bootstrap_credential

        stage_bootstrap_credential(repo, "bp1", "OneTimeValue123456789")
        out = _verify(repo, online=lambda ip: False)
        assert "OneTimeValue123456789" not in json.dumps(out)


class TestPromotionOnlyOnAnAnswer:

    def test_a_device_that_answered_is_promoted(self, repo):
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import verify_and_promote

        out = verify_and_promote(repo, "bp1", "probe", actor="t",
                                 online=lambda ip: True,
                                 reach=lambda *a, **k: "bp1#",
                                 username="admin", password="rotated")
        assert out["ok"] is True, out
        assert out["promoted"] is True
        assert _m.pending_devices(repo) == []

    def test_a_device_that_did_not_answer_stays_pending(self, repo):
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import verify_and_promote

        out = verify_and_promote(repo, "bp1", "probe",
                                 online=lambda ip: False,
                                 username="admin", password="rotated")
        assert out["ok"] is False
        assert out["promoted"] is False
        assert len(_m.pending_devices(repo)) == 1, \
            "a device that never answered was promoted"


# ---------------------------------------------------------------------------
# The banner, executed
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def banner_js():
    """`pendingBannerHtml` and `pendingAgeText`, lifted from the page."""
    import re as _re

    import app as nmas

    page = nmas.app.test_client().get("/").get_data(as_text=True)
    out = []
    for name in ("pendingAgeText", "pendingBannerHtml"):
        start = page.index(f"function {name}(")
        depth, i, seen = 0, page.index("{", start), False
        while i < len(page):
            if page[i] == "{":
                depth += 1
                seen = True
            elif page[i] == "}":
                depth -= 1
                if seen and depth == 0:
                    break
            i += 1
        out.append(page[start:i + 1])
    return "\n".join(out)


def _banner(js, data):
    return dukpy.evaljs(js + f"\npendingBannerHtml({json.dumps(data)});")


def _row(name="bp1", state="in_flight", age=60):
    return {"name": name, "mgmt_ip": "203.0.113.31", "state": state,
            "age_seconds": age, "onboarded_at": "2026-09-23T10:00:00Z"}


class TestTheBannerDistinguishesErrorFromEmpty:
    """**The banner's own wrong-and-looks-right state**: rendering "no
    pending devices" because the query failed — a reassuring sentence
    produced by a broken read.

    Same correction as the drift panel's "all 9 device(s) clean" over a
    ten-device inventory, and the agent panel's disabled read returning
    `[]`. A device may be waiting and invisible, which is the one thing this
    banner exists to prevent.
    """

    def test_a_failed_query_says_so(self, banner_js):
        html = _banner(banner_js, {"ok": False, "error": "manifest unreadable"})
        assert "could not be read" in html
        assert "manifest unreadable" in html
        assert "alert-danger" in html

    def test_a_failed_query_says_it_is_not_the_same_as_none(self, banner_js):
        html = " ".join(_banner(banner_js,
                                {"ok": False, "error": "x"}).split())
        assert "not</em> the same as none being pending" in html

    def test_a_missing_payload_is_an_error_not_an_empty_list(self, banner_js):
        """`undefined` must not fall through to the empty branch."""
        for bad in (None, {}, {"pending": []}):
            html = _banner(banner_js, bad)
            assert "could not be read" in html, bad

    def test_genuinely_empty_renders_nothing(self, banner_js):
        """The control. A banner that always drew something would pass every
        test above and be ignored within a week."""
        assert _banner(banner_js, {"ok": True, "pending": []}) == ""


class TestTheBannerIsActionable:

    def test_in_flight_is_listed_quietly(self, banner_js):
        html = _banner(banner_js, {"ok": True, "pending": [_row()]})
        assert "alert-secondary" in html
        assert "overdue" not in html and "stale" not in html

    def test_overdue_is_flagged(self, banner_js):
        html = _banner(banner_js,
                       {"ok": True, "pending": [_row(state="overdue",
                                                     age=90000)]})
        assert "alert-warning" in html
        assert "overdue" in html

    def test_every_row_offers_abandon(self, banner_js):
        """**Changed deliberately from the opposite assertion.**

        It was offered only at `stale`, on the reasoning that a destructive
        action beside a five-minute-old device invites use. That is wrong in
        the direction that matters: the operator who has just onboarded the
        wrong thing is the one who needs abandon, and the window in which
        they are certain it was a mistake is minutes, not a week.

        Gating it at seven days left `curl` or waiting as the only recovery
        for a fresh mistake — the flow's own recovery path unreachable
        exactly when it is most useful. The confirm in `onboardAbandon()` is
        what stops a misclick; an age gate never was.
        """
        for state, age in (("in_flight", 60), ("overdue", 90000),
                           ("stale", 999999)):
            html = _banner(banner_js,
                           {"ok": True, "pending": [_row(state=state,
                                                         age=age)]})
            assert "onboardAbandon" in html, state

    def test_abandon_still_asks_before_it_acts(self):
        """The thing that actually stops a misclick, asserted in the shipped
        source rather than assumed."""
        import re as _re

        import app as nmas

        page = nmas.app.test_client().get("/").get_data(as_text=True)
        body = page[page.index("async function onboardAbandon("):]
        body = body[:body.index("\n}")]
        assert "confirm(" in body
        assert "NetBox" in body, "the confirm must say what it removes"

    def test_every_row_offers_verify(self, banner_js):
        for state in ("in_flight", "overdue", "stale"):
            html = _banner(banner_js,
                           {"ok": True, "pending": [_row(state=state)]})
            assert "onboardVerify" in html, state

    def test_the_age_is_shown_not_just_the_state(self, banner_js):
        html = _banner(banner_js, {"ok": True,
                                   "pending": [_row(age=7200)]})
        assert "2 hours" in html

    def test_the_unverified_interface_is_stated(self, banner_js):
        """The honest version of the guarantee that could not be made at
        plan time."""
        html = " ".join(_banner(banner_js,
                                {"ok": True, "pending": [_row()]}).split())
        assert "unverified" in html
        assert "never against the device" in html

    def test_the_name_is_escaped(self, banner_js):
        html = _banner(banner_js,
                       {"ok": True,
                        "pending": [_row(name="<script>alert(1)</script>")]})
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# NetBox creation belongs to phase 2
# ---------------------------------------------------------------------------

class TestNetBoxIsCreatedInPhaseTwo:
    """It was step 2 of phase 1 and could not work there.

    `sync_list_to_netbox` is an IMPORTER — every object is built from the
    device's golden config by `_scan_device_from_golden` — and a device being
    onboarded has no golden by definition. So the device landed in the sync's
    `failed` list and was skipped, while the region, site and list-level VRF,
    built unconditionally before that loop, were created.

    Measured on the live NetBox: **3 objects tagged `nmas-managed` — a
    region, a site and a VRF, all named after the list — and no device.** The
    run reported *"Device onboarded."*
    """

    def test_no_capture_means_deferred_not_created(self, repo, monkeypatch):
        """It does not call the importer at all without a capture. Calling
        it is what created the scaffolding for a device that never followed.
        """
        from modules.nsot.onboard import create_netbox_record

        called = []
        out = create_netbox_record(repo, "bp1", "probe",
                                   sync=lambda *a, **k: called.append(a))
        assert out["deferred"] is True
        assert out["ok"] is False
        assert called == [], "the importer ran with nothing to import"
        assert "no captured config" in out["reason"]

    def test_a_sync_reporting_ok_with_failures_is_NOT_success(self, repo,
                                                              monkeypatch):
        """**`ok` means "the sync ran", not "the devices landed".**

        `_sync_list_to_netbox_impl` returns `{"ok": True, ..., "failed":
        [...]}` with every device in `failed`, and the previous caller
        checked only `ok`. Third instance of success meaning *no exception
        reached the top*.
        """
        from modules.nsot.onboard import create_netbox_record

        monkeypatch.setattr("modules.ai_assistant._load_golden_config_file",
                            lambda ip: "hostname bp1\n!\nend\n")
        out = create_netbox_record(
            repo, "bp1", "probe",
            sync=lambda *a, **k: {"ok": True, "failed": [
                {"hostname": "bp1", "error": "No golden config saved"}]})
        assert out["ok"] is False
        assert "No golden config saved" in out["reason"]

    def test_a_clean_sync_is_success(self, repo, monkeypatch):
        """The control. A check that read `failed` and refused regardless
        would pass the test above and never create anything."""
        from modules.nsot.onboard import create_netbox_record

        monkeypatch.setattr("modules.ai_assistant._load_golden_config_file",
                            lambda ip: "hostname bp1\n!\nend\n")
        monkeypatch.setattr("modules.netbox_guard.get_created",
                            lambda lst, endpoint="": {
                                "dcim/devices": [{"id": 42, "name": "bp1"}]})
        out = create_netbox_record(repo, "bp1", "probe",
                                   sync=lambda *a, **k: {"ok": True, "failed": []})
        assert out["ok"] is True
        assert out["device_id"] == 42

    def test_the_device_id_reaches_the_manifest(self, repo, monkeypatch):
        """`netbox_id` was declared and never written: `create_netbox_step`
        collected every created id and `commit_step` never received them, so
        nothing could populate it. The `next_ts` shape, in the identity map.
        """
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import verify_and_promote

        monkeypatch.setattr("modules.ai_assistant._load_golden_config_file",
                            lambda ip: "hostname bp1\n!\nend\n")
        monkeypatch.setattr("modules.netbox_client.sync_list_to_netbox",
                            lambda *a, **k: {"ok": True, "failed": []})
        monkeypatch.setattr("modules.netbox_guard.get_created",
                            lambda lst, endpoint="": {
                                "dcim/devices": [{"id": 42, "name": "bp1"}]})
        verify_and_promote(repo, "bp1", "probe", actor="t",
                           online=lambda ip: True, reach=lambda *a, **k: "bp1#",
                           username="admin", password="rotated")
        _identity, entry = _m.find_by_name(repo, "bp1")
        assert entry["netbox_id"] == 42

    def test_a_netbox_failure_does_not_undo_the_promotion(self, repo,
                                                          monkeypatch):
        """The device answered and is in the inventory; those are facts about
        the network and are already recorded. A later NetBox problem is a
        synchronisation issue with an external system."""
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import verify_and_promote

        monkeypatch.setattr("modules.ai_assistant._load_golden_config_file",
                            lambda ip: "hostname bp1\n!\nend\n")
        monkeypatch.setattr("modules.netbox_client.sync_list_to_netbox",
                            lambda *a, **k: {"ok": False, "blocked": True,
                                             "error": "writes are disabled"})
        out = verify_and_promote(repo, "bp1", "probe", actor="t",
                                 online=lambda ip: True,
                                 reach=lambda *a, **k: "bp1#",
                                 username="admin", password="rotated")
        assert out["ok"] is True, "the promotion was undone by a NetBox error"
        assert out["netbox"]["ok"] is False
        assert "disabled" in out["netbox"]["reason"]
        assert _m.pending_devices(repo) == []


class TestPhaseOneReachesNoExternalSystem:

    def test_the_steps_are_three_and_local(self):
        from modules.nsot.onboard import STEPS

        assert STEPS == ("credentials", "commit", "render")

    def test_no_phase_one_step_imports_the_netbox_client(self):
        """Parsed, not grepped — the docstrings above name the module
        repeatedly to explain why it is not used."""
        import ast
        import inspect
        import textwrap

        from modules.nsot import onboard

        for name in ("bind_credentials_step", "commit_step", "render_step"):
            src = textwrap.dedent(inspect.getsource(getattr(onboard, name)))
            names = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.ImportFrom):
                    names.add(node.module or "")
                elif isinstance(node, ast.Import):
                    names.update(a.name for a in node.names)
            assert not any("netbox" in n for n in names), (name, names)


class TestTheBannerHasAnEntryPoint:
    """`loadOnboardPending` had exactly two callers, and both were buttons
    **inside the banner it draws** — so the banner could only appear after
    you had used a control that only exists once it has appeared.

    The div sat in the DOM, empty, while the manifest held a pending device
    and the Template library listed it as bound. That is the state `pending`
    was built to prevent, and the banner's own design test — *"pending for
    ever and nobody notices"* — was defeated before it ever ran.

    Not client-side suppression like the agent panel, and not two readers
    disagreeing: **a renderer with no caller.** `test_onboard_phase2.py`
    could not see it, because it executes `pendingBannerHtml` directly —
    testing the render and not the wiring, the same seam as `/onboard/create`
    sending `body: '{}'`.
    """

    def _page(self):
        import app as nmas

        return nmas.app.test_client().get("/").get_data(as_text=True)

    def test_something_outside_the_banner_calls_it(self):
        """The property: at least one caller that is not one of the banner's
        own buttons, or the banner is unreachable."""
        import re as _re

        page = self._page()
        callers = [m.start() for m in
                   _re.finditer(r"loadOnboardPending\s*\(", page)]
        assert len(callers) >= 3, (
            f"only {len(callers)} reference(s) — the definition plus its own "
            f"buttons means nothing draws it on load")
        assert "DOMContentLoaded" in page

    def test_it_runs_on_page_load(self):
        page = self._page()
        block = page[page.index("id=\"onboardPendingBanner\""):]
        block = block[:block.index("async function loadOnboardPending")]
        assert "DOMContentLoaded" in block
        assert "loadOnboardPending" in block

    def test_it_reruns_when_the_device_list_changes(self):
        """Pending is per list. A banner showing another list's devices is
        worse than none."""
        page = self._page()
        block = page[page.index("id=\"onboardPendingBanner\""):]
        block = block[:block.index("async function loadOnboardPending")]
        assert "deviceListSelect" in block
        assert "devices-tab" in block

    def test_the_endpoint_answers_without_a_list_name(self):
        """The page does not always know the list at load time, and a READ
        may derive the active one — a listing leaves nothing behind. The
        write path still refuses."""
        import app as nmas

        body = nmas.app.test_client().get("/onboard/pending").get_json()
        assert body.get("ok") is True, body
        assert "list" in body, "the response must say which list it answered for"


class TestTheBannerCarriesTheListIntoItsActions:
    """Both buttons read `#obList` — the WIZARD's select, empty until
    `openOnboardWizard()` populates it. From the banner the modal has never
    been opened, so every action it offers sent `list_name: ''` and was
    refused.

    **`carried, never derived`, failing in the direction the rule is for:**
    the value was in hand — `/onboard/pending` echoes the list it answered
    for, and that response drew the row — and was dropped on the way to the
    call. The same shape as `loadOnboardPending` having no caller: the
    feature renders and nothing it offers works.
    """

    def _page(self):
        import app as nmas

        return nmas.app.test_client().get("/").get_data(as_text=True)

    def test_both_buttons_are_given_the_list(self, banner_js):
        html = _banner(banner_js,
                       {"ok": True, "list": "nmas-probe",
                        "pending": [_row(state="stale", age=999999)]})
        assert "onboardVerify('bp1', 'nmas-probe')" in html
        assert "onboardAbandon('bp1', 'nmas-probe')" in html

    def test_neither_action_falls_back_to_the_wizards_select(self):
        """A fallback would make the banner work by accident once the wizard
        had been opened, and fail otherwise — which is how this shipped."""
        page = self._page()
        for fn in ("onboardVerify", "onboardAbandon"):
            sig = page[page.index(f"async function {fn}("):]
            sig = sig[:sig.index(")") + 1]
            assert "listName" in sig, (fn, sig)

    def test_the_list_is_escaped_like_the_name(self, banner_js):
        html = _banner(banner_js,
                       {"ok": True, "list": "<script>x</script>",
                        "pending": [_row()]})
        assert "<script>x</script>" not in html


class TestARefusalNamesTheCallersOperation:
    """`_target_list()` is shared by plan, create, verify and abandon, and
    its refusal explained why ONBOARDING carries its list — to an operator
    who had pressed Abandon.

    A correct refusal describing a different action reads as a bug in the
    tool: it sent the reader looking for a wizard they had not opened. The
    consequence clause differs too — onboarding is about what a wrong list
    leaves behind, abandon about what it would remove.
    """

    def test_each_caller_gets_its_own_action(self):
        from routes.onboard import NoTargetList, _target_list

        expected = {"plan": "plan an onboarding",
                    "create": "onboard a device",
                    "verify": "verify a pending device",
                    "abandon": "abandon a pending device"}
        for what, phrase in expected.items():
            try:
                _target_list({}, what)
            except NoTargetList as exc:
                assert phrase in str(exc), (what, str(exc))
            else:
                raise AssertionError(f"{what} did not refuse")

    def test_abandon_does_not_talk_about_onboarding(self):
        """The exact confusion, as an assertion."""
        from routes.onboard import NoTargetList, _target_list

        try:
            _target_list({}, "abandon")
        except NoTargetList as exc:
            text = str(exc)
        assert "onboarding into the wrong one" not in text, text
        assert "would delete" in text

    def test_every_route_passes_its_own_name(self):
        """Parsed, not grepped. A route left on the default would give the
        onboarding message for something else — the defect itself."""
        import ast
        import inspect

        import routes.onboard as mod

        seen = {}
        for node in ast.walk(ast.parse(inspect.getsource(mod))):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Call)
                        and getattr(inner.func, "id", "") == "_target_list"):
                    assert len(inner.args) == 2, (
                        f"{node.name} calls _target_list without naming its "
                        f"operation, so it would use the onboarding message")
                    seen[node.name] = inner.args[1].value
        assert seen == {"bootstrap": "bootstrap", "verify": "verify",
                        "abandon": "abandon", "plan": "plan",
                        "create": "create"}, seen


class TestTheArtefactSurvivesTheRun:
    """**Phase 1's entire product is a config the operator boots the node
    with, and it was rendered, validated and thrown away.**

    `render(plan)`'s return value was discarded, the create response carried
    no config, and the artefact appeared only on the review screen BEFORE
    Create. Once the toast cleared the only way back was abandon-and-
    re-create — which mints a new credential, so the staged one on disk
    would no longer match what was booted.

    That is the sharp form: **the credential was durable and the config
    carrying it was ephemeral**, leaving the recoverable half the one you
    cannot use. They must share a lifetime, and here they do by construction
    — the config is re-derived from the staged credential rather than
    stored, so it exists exactly while it is usable.
    """

    def _onboard(self, repo, secret="OneTimeBootstrapValue1"):
        from modules.nsot import hostvars
        from modules.nsot.onboard import stage_bootstrap_credential

        stage_bootstrap_credential(repo, "bp1", secret)
        hostvars.write_committed(repo, {
            "hostname": "bp1",
            "bootstrap": {"address": "203.0.113.31", "mask": "255.255.255.0",
                          "interface": "GigabitEthernet2", "gateway": "",
                          "domain": "rcn.lab", "platform": "cisco_iosxe"}})
        return secret

    def test_it_is_re_renderable_after_the_run(self, repo):
        from modules.nsot.onboard import bootstrap_artifact

        secret = self._onboard(repo)
        out = bootstrap_artifact(repo, "bp1")
        assert out["ok"] is True, out
        assert "interface GigabitEthernet2" in out["config"]
        assert "ip address 203.0.113.31 255.255.255.0" in out["config"]
        assert secret in out["config"], (
            "the re-render must carry the credential the node booted with")

    def test_it_is_byte_identical_to_what_was_rendered(self, repo):
        """Re-derived, not approximated. A config that differs by a line
        from the one the node booted is worse than none."""
        from modules.nsot.bootstrap_config import render_bootstrap
        from modules.nsot.onboard import bootstrap_artifact

        secret = self._onboard(repo)
        original = render_bootstrap(
            "cisco_iosxe", hostname="bp1", username="admin", secret=secret,
            domain="rcn.lab", manager_interface="GigabitEthernet2",
            manager_address="203.0.113.31", manager_mask="255.255.255.0")
        assert bootstrap_artifact(repo, "bp1")["config"] == original

    def test_it_is_gone_once_the_credential_is_rotated(self, repo):
        """**The lifetimes are the same by construction.** After rotation
        the device holds a different credential and the old config would not
        log in; producing it then would hand over something that looks
        usable and is not."""
        from modules.nsot.onboard import (bootstrap_artifact,
                                          clear_bootstrap_credential)

        self._onboard(repo)
        clear_bootstrap_credential(repo, "bp1")
        out = bootstrap_artifact(repo, "bp1")
        assert out["ok"] is False
        assert "would no longer log in" in out["reason"]

    def test_a_device_without_committed_parameters_says_so(self, repo):
        """Devices onboarded before the parameters were committed cannot be
        re-derived, and the refusal says what to do rather than failing
        obscurely."""
        from modules.nsot.onboard import (bootstrap_artifact,
                                          stage_bootstrap_credential)

        stage_bootstrap_credential(repo, "bp1", "OneTimeBootstrapValue1")
        out = bootstrap_artifact(repo, "bp1")
        assert out["ok"] is False
        assert "abandon and re-create" in out["reason"]

    def test_the_config_is_never_written_to_intended(self, repo):
        """`intended/` is committed, so writing it there would put the
        bootstrap credential in git in the clear on a repo that may have a
        remote — and masking it would make the file useless for its one
        purpose, since a node cannot boot a masked password. Wrong in both
        directions."""
        import os

        from modules.nsot.onboard import bootstrap_artifact

        self._onboard(repo)
        bootstrap_artifact(repo, "bp1")
        intended = os.path.join(repo, "intended")
        listing = os.listdir(intended) if os.path.isdir(intended) else []
        assert not [f for f in listing if "bp1" in f], listing

    def test_the_route_requires_a_person_and_audits(self):
        """It hands over a credential in the clear, so it is a reveal and is
        gated like one."""
        import ast
        import inspect

        import routes.onboard as mod

        src = inspect.getsource(mod.bootstrap)
        tree = ast.parse(inspect.cleandoc(src).replace("@bp.route", "#"))
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert "require" in names, "not gated"
        assert "record" in names, "a reveal that is not audited"
        assert '"reveal"' in src or "'reveal'" in src
