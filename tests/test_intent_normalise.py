"""C1693 (the operator's order, 2026-10-27; board H-N): Normalise the formatting, on the host's
REAL documents.

A device's committed intent that does not round-trip through `hostvars.to_yaml` cannot be
patched (feature 7 and bulk intent refuse it). The Intent tab offers "Normalise the
formatting…" for such a document only; it loads Mercury's own serialisation into the intent
editor and writes nothing. The editor's check, for an edit that changes formatting only, draws
the five lines of the proof: the parsed document equal; the render byte-identical to the
committed render; the device diff empty; the masked lines compared by keyed hash, N of N
identical; the new text round-trips. Any failure stops the commit, at the server, and lists
every differing line, masked; a keyed-hash mismatch is named by its line and masked text,
never its value. And every intent write path saves in the canonical format.

THE FIXTURES ARE THE HOST'S COMMITTED FILES (tests/fixtures/committed/README.md): r2's intent
and golden; `r2_hand_formatted.yml` is r2's intent with its `interfaces` list indented under
its key and one comment above it, as an editor writes YAML (the shape r6's took: board H-N
draws `  - name: GigabitEthernet1`), the same document. The credential store answers each
secret reference with a made-up value, so the true renders carry values in the masked
positions for the keyed hash to compare.
"""

import inspect
from types import SimpleNamespace
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "committed")
DEVICE = {"hostname": "r2", "ip": "192.0.2.12", "device_type": "cisco_xe",
          "platform": "cisco_iosxe", "role": "router"}
#: Made-up values for each secret reference r2's intent names, never a real one.
SECRETS = {"snmp_community_ro": "c1693RoTest", "user_admin_secret": "9 $9$c1693NotARealHash"}
#: The planted credential change: the value the keyed hash must see differ.
CHANGED = "9 $9$c1693AnotherHashX"


def _text(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


HAND = "r2_hand_formatted.yml"


@pytest.fixture
def lab(monkeypatch, tmp_path):
    """A list 'Lab' holding r2 as the host holds it, its committed intent hand-formatted: the
    real golden, the shipped templates approved, a planted switch for the keyed hash."""
    import app as A
    from modules.nsot import approval, templates_repo
    from modules.nsot import repo as R
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars

    list_dir = tmp_path / "lab"
    repo = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
    settings = {"nsot_git_author_name": "NMAS", "nsot_git_author_email": "nmas@localhost"}
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(approval, "is_approved", lambda repo, t: True)
    templates_repo.seed_templates(repo)
    assert R.save_templates("Lab", ["_common.j2", "cisco_ios/base.j2", "cisco_iosxe/base.j2"],
                            actor="t", message="the shipped templates")["ok"]
    save_golden("Lab", [GoldenItem("r2", _text("r2.cfg"), DEVICE["ip"],
                                   platform=DEVICE["platform"])],
                source="onboarding", actor="t", allow_new=True, baseline=False)
    with open(os.path.join(repo, "host_vars", "r2.yml"), "w", encoding="utf-8") as fh:
        fh.write(_text(HAND))
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    plant = {"on": False, "calls": 0}

    def hydrate(hv, h, ln=""):
        values = dict(SECRETS)
        # The planted change: the NEW document's true render, in the keyed-hash comparison
        # (`_masked_compared` hydrates the committed document, then the new one).
        if plant["on"] and inspect.stack()[1].function == "_masked_compared":
            plant["calls"] += 1
            if plant["calls"] % 2 == 0:
                values["user_admin_secret"] = CHANGED
        return {**hv, "secrets": values}
    monkeypatch.setattr("modules.nsot.hostvars.hydrate_secrets", hydrate)
    monkeypatch.setattr("modules.device.load_saved_devices", lambda *a, **k: [dict(DEVICE)])
    monkeypatch.setattr("routes.templates._row_for", lambda h, ln="": dict(DEVICE)
                        if h == "r2" else None)
    # The device page finds r2 in 'Lab', as its inventory row would (test_intent_editor_v2's).
    found = ((SimpleNamespace(name="Lab", repo_dir=repo), dict(DEVICE)), None)
    monkeypatch.setattr("routes.intent_v2._device_or_404", lambda name: found)
    monkeypatch.setattr("routes.device_v2._device_or_404", lambda name: found)
    # No value the store holds is known to the masking here but the made-up ones.
    monkeypatch.setattr("modules.redact.known_secret_values", lambda: {})
    return {"client": A.app.test_client(), "app": A.app, "repo": repo, "plant": plant}


def _committed(lab):
    from modules.nsot import hostvars
    return hostvars.committed_at_head(lab["repo"], "r2")[0]


def _proof(lab, text=None):
    from modules.nsot import hostvars, intent_normalise
    committed = _committed(lab)
    return intent_normalise.proof("Lab", "r2", text or hostvars.canonical(committed),
                                  committed)


class TestTheFixture:
    def test_the_hand_formatted_document_is_r2s_and_does_not_round_trip(self):
        from modules.nsot import hostvars
        hand, real = _text(HAND), _text("r2.yml")
        assert hostvars.from_yaml(hand) == hostvars.from_yaml(real)
        assert not hostvars.round_trips(hand) and hostvars.round_trips(real)
        assert hostvars.canonical(hand) == real


class TestTheProof:
    def test_formatting_only_passes_all_five_lines(self, lab):
        p = _proof(lab)
        assert [l["key"] for l in p["lines"]] == ["document", "render", "device", "masked",
                                                 "round_trip"]
        assert [l["passed"] for l in p["lines"]] == [True] * 5, p["lines"]
        assert p["ok"] and p["differs"] == []

    def test_the_masked_lines_are_compared_n_of_n(self, lab):
        p = _proof(lab)
        m = p["masked"]
        assert m["compared"] >= 2 and m["identical"] == m["compared"], m
        words = p["lines"][3]["words"]
        assert f"{m['identical']} of {m['compared']} identical" in words
        assert "No value is shown or kept" in words

    def test_no_value_reaches_the_proof(self, lab):
        lab["plant"]["on"] = True
        p = _proof(lab)
        flat = repr(p)
        for value in list(SECRETS.values()) + [CHANGED]:
            assert value.split()[-1] not in flat

    def test_a_credential_that_differs_stops_it_naming_the_line_never_the_value(self, lab):
        lab["plant"]["on"] = True
        p = _proof(lab)
        assert not p["ok"]
        masked = p["lines"][3]
        assert masked["key"] == "masked" and not masked["passed"]
        assert "Its value is not shown" in masked["words"]
        named = [d for d in p["differs"] if d["from"] == "masked"]
        assert len(named) == 1 and named[0]["number"] > 0
        assert "username" in named[0]["line"] and "<redacted:user_password>" in named[0]["line"]
        assert f"line {named[0]['number']}" in masked["words"]
        # The other four still pass: only the credential moved.
        assert [l["passed"] for l in p["lines"]] == [True, True, True, False, True]

    def test_a_render_that_differs_stops_it_listing_each_line(self, lab):
        from modules.nsot import hostvars, intent_normalise
        committed = _committed(lab)
        doc = hostvars.from_yaml(committed)
        doc["interfaces"][0]["description"] = "a different description"
        p = intent_normalise.proof("Lab", "r2", hostvars.to_yaml(doc), committed)
        assert not p["ok"]
        passed = {l["key"]: l["passed"] for l in p["lines"]}
        assert passed == {"document": False, "render": False, "device": False,
                          "masked": True, "round_trip": True}
        render = [d["line"] for d in p["differs"] if d["from"] == "render"]
        assert any(l.startswith("+") and "a different description" in l for l in render)
        assert any(l.startswith("-") and "description" in l for l in render)

    @staticmethod
    def _masked_in_render(lab):
        """How many lines of r2's masked render (the editor's own) hide a value."""
        from modules.nsot import hostvars, intent_edit
        from modules.nsot.render_artifact import MASK
        from routes.templates import artifact_for
        ctx = intent_edit.render_context("Lab", "r2")
        doc = hostvars.from_yaml(_committed(lab))
        art = artifact_for("r2", ctx["capture"], ctx["repo"], ctx["platform"], ctx["template"],
                           host_vars=hostvars.hydrate_secrets(ctx["eff"](doc), "r2", "Lab"))
        return sum(1 for l in art.rendered_masked.splitlines() if MASK in l)

    def test_every_line_the_render_masks_is_compared(self, lab):
        p = _proof(lab)
        assert p["masked"]["compared"] == self._masked_in_render(lab) >= 2

    def test_the_network_s_own_template_is_the_one_compared(self, lab):
        """The true renders go through the network's library, as the masked one does: a
        library that renders one more secret line has it compared too."""
        from modules.nsot import repo as R
        before = _proof(lab)["masked"]["compared"]
        path = os.path.join(lab["repo"], "templates", "_common.j2")
        text = open(path, encoding="utf-8").read()
        line = "snmp-server community {{ secret(c.ref) }} {{ c.access }}"
        assert text.count(line) == 1
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(line, line + "\nsnmp-server community {{ secret(c.ref) }} "
                                               "view all-view {{ c.access }}"))
        assert R.save_templates("Lab", ["_common.j2"], actor="t", message="one more")["ok"]
        p = _proof(lab)
        assert p["masked"]["compared"] == self._masked_in_render(lab)
        assert p["masked"]["compared"] > before, (before, p["masked"])

    def test_what_the_profile_adds_is_compared_too(self, lab):
        """The network's monitoring profile (the host's real one) gives a device without its
        own SNMP block the profile's community and trap host: the true renders take them, as
        the masked render does."""
        from modules.nsot import hostvars, repo as R
        doc = hostvars.from_yaml(_committed(lab))
        assert doc["snmp"]["communities"] and doc["snmp"]["hosts"]
        doc["snmp"] = {}
        hostvars.write_committed_text(lab["repo"], "r2", hostvars.to_yaml(doc))
        got = R.save_host_vars("Lab", ["r2"], actor="t", source="extraction")
        assert got["ok"], got
        before = _proof(lab)["masked"]["compared"]
        os.makedirs(os.path.join(lab["repo"], "profiles"), exist_ok=True)
        with open(os.path.join(lab["repo"], "profiles", "monitoring.yml"), "w",
                  encoding="utf-8") as fh:
            fh.write(_text("profile.yml"))
        assert R._commit_paths("Lab", ["profiles/monitoring.yml"], "profile: the host's",
                               ["Actor: t"], "profile")["ok"]
        p = _proof(lab)
        assert p["masked"]["compared"] == self._masked_in_render(lab) > before

    def test_the_template_bound_to_the_device_is_the_one_compared(self, lab):
        """r2 bound to its own template, which renders one more secret line."""
        from modules.nsot import repo as R, templates_repo
        before = _proof(lab)["masked"]["compared"]
        tdir = os.path.join(lab["repo"], "templates", "cisco_iosxe")
        base = open(os.path.join(tdir, "base.j2"), encoding="utf-8").read()
        with open(os.path.join(tdir, "edge.j2"), "w", encoding="utf-8") as fh:
            fh.write(base + "\nsnmp-server community {{ secret('snmp_community_ro') }} RW\n")
        bindings = templates_repo.load_bindings(lab["repo"])
        bindings["overrides"] = {"r2": "cisco_iosxe/edge.j2"}
        templates_repo.save_bindings(lab["repo"], bindings)
        assert R.save_templates("Lab", ["cisco_iosxe/edge.j2", "bindings.yml"], actor="t",
                                message="r2's own")["ok"]
        p = _proof(lab)
        assert p["masked"]["compared"] == self._masked_in_render(lab) > before

    def test_the_document_s_own_platform_is_rendered(self, lab, monkeypatch):
        """The masked render renders the platform the document names (`build_artifact`); the
        true renders do the same, whatever the inventory row says: here the row says IOS,
        whose library template renders one more secret line, and r2's document IOS-XE."""
        from modules.nsot import repo as R
        path = os.path.join(lab["repo"], "templates", "cisco_ios", "base.j2")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\nsnmp-server community {{ secret('snmp_community_ro') }} RW\n")
        assert R.save_templates("Lab", ["cisco_ios/base.j2"], actor="t", message="ios")["ok"]
        monkeypatch.setattr("routes.templates._row_for", lambda h, ln="": dict(
            DEVICE, platform="cisco_ios", device_type="cisco_ios") if h == "r2" else None)
        p = _proof(lab)
        assert p["masked"]["compared"] == self._masked_in_render(lab) >= 2, p["lines"]

    def test_each_document_is_rendered_with_its_own_values(self, lab, monkeypatch):
        """`_masked_compared` hydrates and renders the committed document and the new one,
        each its own: a value the new one alone holds differs."""
        from modules.nsot import hostvars, intent_edit, intent_normalise
        monkeypatch.setattr(
            "modules.nsot.hostvars.hydrate_secrets",
            lambda hv, h, ln="": {**hv, "secrets": {r: hv.get("c1693_value", "c1693Value1")
                                                    for r in hv.get("secret_refs") or []}})
        ctx = intent_edit.render_context("Lab", "r2")
        old = hostvars.from_yaml(_committed(lab))
        same = intent_normalise._masked_compared(ctx, "r2", "Lab", old, dict(old))
        assert same["compared"] >= 2 and same["identical"] == same["compared"]
        for new, was in ((dict(old, c1693_value="c1693Value2"), old),
                         (old, dict(old, c1693_value="c1693Value2"))):
            got = intent_normalise._masked_compared(ctx, "r2", "Lab", was, new)
            assert got["compared"] == same["compared"] and got["identical"] == 0, got

    def test_a_pending_device_diff_stops_it(self, lab, monkeypatch):
        """The operator's order: the device diff empty. A golden that lacks a line the
        render holds is a diff, so the commit stops even though the render did not move."""
        from modules.nsot import hostvars, intent_normalise, intent_edit
        real = intent_edit.render_context

        def less(list_name, hostname):
            ctx = real(list_name, hostname)
            ctx["capture"] = ctx["capture"].replace(" description mgmt identity\n", "")
            return ctx
        monkeypatch.setattr(intent_edit, "render_context", less)
        committed = _committed(lab)
        p = intent_normalise.proof("Lab", "r2", hostvars.canonical(committed), committed)
        passed = {l["key"]: l["passed"] for l in p["lines"]}
        assert passed["render"] and not passed["device"] and not p["ok"]
        assert any(d["from"] == "device" and "mgmt identity" in d["line"]
                   for d in p["differs"])


class TestTheEditorCheck:
    def test_formatting_only_carries_the_proof(self, lab):
        from modules.nsot import hostvars, intent_edit
        p = intent_edit.preview("Lab", "r2", hostvars.canonical(_committed(lab)))
        assert p["ok"] and p["proof"]["ok"] and p["canonical"]

    def test_a_data_edit_carries_no_proof(self, lab):
        from modules.nsot import hostvars, intent_edit
        doc = hostvars.from_yaml(_committed(lab))
        doc["interfaces"][0]["description"] = "changed"
        p = intent_edit.preview("Lab", "r2", hostvars.to_yaml(doc))
        assert p["ok"] and "proof" not in p

    @staticmethod
    def _commit_button(html):
        m = re.search(r'<span class="op-act ie-commit" id="ie-commit" hx-swap-oob="true">'
                      r'.*?(<button\b[^>]*>)(.*?)</button>', html, re.S)
        assert m, "the check draws the editor's Commit again, out of band"
        return m.group(1), m.group(2)

    def test_the_check_draws_the_proof_and_the_commit_it_allows(self, lab):
        from modules.nsot import hostvars
        html = lab["client"].post("/v2/device/r2/intent/check", data={
            "yaml": hostvars.canonical(_committed(lab))}).get_data(as_text=True)
        assert 'data-proof="proved"' in html
        assert html.count('<li data-line="') == 5
        tag, label = self._commit_button(html)
        assert not re.search(r"\sdisabled[\s>]", tag) and "Commit the formatting only" in label

    def test_a_planted_mismatch_disables_the_commit(self, lab):
        from modules.nsot import hostvars
        lab["plant"]["on"] = True
        html = lab["client"].post("/v2/device/r2/intent/check", data={
            "yaml": hostvars.canonical(_committed(lab))}).get_data(as_text=True)
        assert 'data-proof="stopped"' in html and "A masked line differs by keyed hash" in html
        tag, label = self._commit_button(html)
        assert re.search(r"\sdisabled[\s>]", tag) and "Commit the formatting only" in label
        for value in [CHANGED] + list(SECRETS.values()):
            assert value.split()[-1] not in html

    def test_a_data_edit_draws_the_commit_as_before(self, lab):
        from modules.nsot import hostvars
        doc = hostvars.from_yaml(_committed(lab))
        doc["interfaces"][0]["description"] = "changed"
        html = lab["client"].post("/v2/device/r2/intent/check", data={
            "yaml": hostvars.to_yaml(doc)}).get_data(as_text=True)
        tag, label = self._commit_button(html)
        assert not re.search(r"\sdisabled[\s>]", tag) and "Commit to r2's intent" in label


class TestTheCommit:
    def _commit(self, lab, text, summary="C1693: Mercury's own formatting"):
        from modules.nsot import intent_edit
        base = intent_edit.open_doc("Lab", "r2")["base"]
        return intent_edit.commit("Lab", "r2", text, summary, base, "op@example.com")

    def test_a_proved_normalisation_commits_the_canonical_text(self, lab):
        from modules.nsot import hostvars
        committed = _committed(lab)
        got = self._commit(lab, hostvars.canonical(committed))
        assert got["ok"] and got["changed"] and got["formatting_only"], got
        assert _committed(lab) == _text("r2.yml")
        from modules.nsot.repo import git
        body = git(lab["repo"], "log", "-1", "--format=%B")[1]
        assert "Formatting-Only: proved" in body and "identical by keyed hash" in body

    def test_the_server_refuses_a_failing_proof_whatever_the_button(self, lab):
        from modules.nsot import hostvars
        lab["plant"]["on"] = True
        before = _committed(lab)
        got = self._commit(lab, hostvars.canonical(before))
        assert not got["ok"] and got["status"] == 409 and got["stage"] == "proof"
        assert "Not committed: this is not formatting only" in got["error"]
        assert "Nothing was written" in got["error"]
        assert _committed(lab) == before

    def test_a_comment_typed_into_a_canonical_document_commits_nothing(self, lab):
        from modules.nsot import hostvars
        assert self._commit(lab, hostvars.canonical(_committed(lab)))["changed"]
        got = self._commit(lab, "# a note\n" + _committed(lab))
        assert got["ok"] and not got["changed"]
        assert "Mercury's own formatting" in got["message"]


class TestEveryWritePathCommitsCanonical:
    """C1693 (a), through each path's own commit on r2's real intent: a hand-formatted input is
    committed in Mercury's own formatting, with the change it carries and nothing else."""

    def test_the_editor_s_commit_of_a_data_edit_typed_by_hand(self, lab):
        from modules.nsot import hostvars, intent_edit
        hand = _committed(lab)
        assert not hostvars.round_trips(hand)
        typed = hand.replace("description: mgmt identity", "description: mgmt identity two")
        assert typed != hand
        base = intent_edit.open_doc("Lab", "r2")["base"]
        got = intent_edit.commit("Lab", "r2", typed, "retitle", base, "op@example.com")
        assert got["ok"] and got["changed"] and got["reformatted"] and \
            not got["formatting_only"], got
        committed = _committed(lab)
        assert committed == hostvars.canonical(typed) and hostvars.round_trips(committed)
        want = hostvars.from_yaml(hand)
        next(i for i in want["interfaces"] if i.get("description") == "mgmt identity")[
            "description"] = "mgmt identity two"
        assert hostvars.from_yaml(committed) == want, "the edit, and nothing else"

    def test_feature_7_s_commit_the_patch_path(self, lab):
        """`intent_words.commit_draft` commits through `intent_patch.commit`, which hands the
        editor's commit the patched document serialised by `to_yaml`."""
        from modules.nsot import hostvars, intent_edit, intent_patch
        base = intent_edit.open_doc("Lab", "r2")["base"]
        assert intent_edit.commit("Lab", "r2", hostvars.canonical(_committed(lab)), "normalise",
                                  base, "op@example.com")["ok"]
        before = hostvars.from_yaml(_committed(lab))
        iface = before["interfaces"][0]["name"]
        patch = {"hostname": "r2", "operations": [
            {"op": "set_description", "interface": iface, "description": "patched"}]}
        base = intent_edit.open_doc("Lab", "r2")["base"]
        got = intent_patch.commit("Lab", "r2", patch, "describe it", base, "op@example.com")
        assert got["ok"] and got["changed"], got
        committed = _committed(lab)
        assert hostvars.round_trips(committed)
        before["interfaces"][0]["description"] = "patched"
        assert hostvars.from_yaml(committed) == before


class TestTheOffer:
    def test_the_whole_page_draws_the_offer(self, lab):
        r = lab["client"].get("/v2/device/r2?tab=intent")
        html = r.get_data(as_text=True)
        assert r.status_code == 200, html[:600]
        assert "data-normalise" in html and "Normalise the formatting" in html

    def test_offered_for_a_hand_formatted_document_only(self):
        from modules.nsot import intent_normalise
        assert intent_normalise.offered(_text(HAND))
        assert not intent_normalise.offered(_text("r2.yml"))
        assert not intent_normalise.offered("")
        assert not intent_normalise.offered("- a list\n")

    def test_the_tab_offers_it_and_the_route_loads_the_canonical_text(self, lab):
        html = lab["client"].get("/v2/device/r2/intent").get_data(as_text=True)
        assert "Normalise the formatting" in html
        r = lab["client"].get("/v2/device/r2/intent/normalise")
        page = r.get_data(as_text=True)
        assert r.status_code == 200
        import html as _h
        text = _h.unescape(re.search(r'<textarea id="ie-text"[^>]*>(.*?)</textarea>', page,
                                     re.S).group(1))
        assert text == _text("r2.yml")
        assert "Mercury's formatting loaded; nothing written" in page
        assert _committed(lab) == _text(HAND), "Normalise writes nothing"

    def test_a_canonical_document_is_not_offered(self, lab):
        from modules.nsot import hostvars
        TestTheCommit()._commit(lab, hostvars.canonical(_committed(lab)))
        html = lab["client"].get("/v2/device/r2/intent").get_data(as_text=True)
        assert "Normalise the formatting" not in html


def test_a_real_browser_normalises_and_a_planted_mismatch_disables_the_commit(lab):
    """The path a person takes, in a real browser, on r2's real intent laid out by hand: the
    Intent tab offers Normalise; it opens the editor on Mercury's formatting and the check
    draws the five lines, proved, with Commit the formatting only pressable; the credential
    store then answers the new document's true render with another value (planted), the next
    check stops naming the masked line and the commit is disabled; the plant lifted, it is
    proved again, committed in place, and the tab, read again, no longer offers it."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from tests.test_device_seed_v2 import SETTLED
    CHECK = "document.querySelector('#ie-check')"
    COMMIT = "document.querySelector('#intent-form #ie-commit button')"

    def proof(state):
        return (f"var p = {CHECK} && {CHECK}.querySelector('.ie-proof');"
                f"return !!p && p.dataset.proof === '{state}' && "
                f"p.querySelectorAll('.ie-proof-lines li').length === 5 && {SETTLED}")

    def retype():
        # The same document again (a trailing newline changes the text, never the data), so
        # the editor's check runs as typed.
        b.js("var t = document.querySelector('#ie-text');"
             "t.value = /\\n\\n$/.test(t.value) ? t.value.slice(0, -1) : t.value + '\\n';"
             "t.dispatchEvent(new Event('input', {bubbles: true})); return 1")

    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/device/r2?tab=intent"))
            b.wait_for("return !!window.Alpine && window.NMAS && " + SETTLED, 15)
            b.js("window.__notReloaded = 1; return 1")
            assert b.js("return !!document.querySelector('[data-normalise] a[data-op]')")
            b.click('[data-normalise] a[data-op="edit-intent"]')
            b.wait_for(proof("proved"), 20)
            assert b.js(f"return {COMMIT}.disabled") is False
            assert "Commit the formatting only" in b.js(f"return {COMMIT}.textContent")
            assert "identical" in b.js(
                f"return {CHECK}.querySelector('[data-line=masked]').textContent")

            lab["plant"]["on"] = True
            retype()
            b.wait_for(proof("stopped"), 20)
            assert b.js(f"return {COMMIT}.disabled") is True
            said = b.js(f"return {CHECK}.querySelector('.ie-masked-differs').textContent")
            assert "Its value is not shown" in said and "<redacted:user_password>" in said
            for value in [CHANGED] + list(SECRETS.values()):
                assert value.split()[-1] not in b.js("return document.body.innerHTML")

            lab["plant"]["on"] = False
            retype()
            b.wait_for(proof("proved"), 20)
            b.js("var s = document.querySelector('#intent-form input[name=summary]');"
                 "s.value = \"C1693: Mercury's own formatting\"; return 1")
            b.click("#intent-form #ie-commit button")
            b.wait_for("return /formatting normalised/.test(document.body.textContent) && "
                       + SETTLED, 20)
            assert b.js("return window.__notReloaded") == 1, "the commit ran in place"
            b.go(srv.url("/v2/device/r2?tab=intent"))
            b.wait_for("return !!window.Alpine && " + SETTLED, 15)
            assert b.js("return !document.querySelector('[data-normalise]')"), \
                "a canonical document is not offered"
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert _committed(lab) == _text("r2.yml")
