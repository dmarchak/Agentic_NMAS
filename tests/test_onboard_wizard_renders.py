"""Stage 4C.4 — every blocking reason ON SCREEN, with Create withheld.

**A refusal the operator cannot see is not a refusal.** 4C.1 made
`blocking_reasons` carry every reason at once; that property is worth nothing
if the review shows one of them, or none.

So this file **draws the review as the page draws it**: the server's adapter
(`preview_confirm.onboard_preview`) through v2's preview parts
(`templates/v2/_preview_parts.html`) inside Add device's card
(`templates/v2/_onboard_add.html`), against a plan with several blockers.
Asserting the plan object is right is what the agent panel's tests did for
three rounds while the screen said nothing.

Today's onboarding wizard, which drew the same preview with today's renderer
(`nmas_preview_confirm.js`) and decided Create with `onboardCanCreate`, left at
7.8 on 2026-10-17 (P7-25), with its routes. Its properties are held here on v2:
Create is offered only for a preview with no refusal, and the core rebuilds and
refuses at Create whatever the page sent (`routes/onboard.create_run`). Removed
with it, each named where it went: the wizard's own form scripts (v2's form is
held by tests/test_onboard_v2.py, `TestTheFormAndThePlanReadTheSameFields`),
today's toolbar button (v2's Add device… with an empty list:
tests/test_controls_do_something.py), today's /onboard/platforms and
/onboard/lists (v2's form draws the platforms and the page's own network).
"""

import json
import re

import pytest


BLOCKED = {
    "hostname": "9bad", "platform": "cisco_ios", "list": "probe",
    "source_kind": "local", "mgmt_ip": "", "cred_source": "",
    "template": "", "writes_csv": True,
    "netbox_note": "nothing — created in phase 2",
    "onboardable": False,
    "blocking_reasons": [
        "'9bad' is not a usable device name — it must start with a letter",
        "platform 'cisco_ios' cannot be onboarded: stage D has not been run",
        "no management address — the device would be created and unreachable",
        "no template is bound for platform 'cisco_ios'",
    ],
}

CLEAN = dict(BLOCKED, hostname="r6", platform="cisco_iosxe",
             mgmt_ip="203.0.113.6", template="cisco-ios-xe/base.j2",
             cred_source="default profile",
             onboardable=True, blocking_reasons=[])

MAY = {"may": True, "actor": "ops@example.com", "kind": "person",
       "statement": "You are confirming as ops@example.com."}


def _card(plan, config=""):
    """Add device's card, drawn by v2 with the review of *plan* (`None`: no review)."""
    from flask import render_template

    import app as nmas
    from modules.preview_confirm import onboard_preview

    f = {"list_name": "probe", "hostname": (plan or {}).get("hostname", "")}
    pv = None if plan is None else {"preview": onboard_preview(plan, config, MAY),
                                    "shown": "{}", "fingerprint": "f" * 64}
    with nmas.app.test_request_context("/v2/onboard/preview", method="POST"):
        return render_template("v2/_onboard_add.html", f=f, pv=pv, platforms=[])


def _html(plan, config="", raw=False):
    """The review as the operator sees it: the VISIBLE text, unless the test is about the
    markup itself (escaping)."""
    import html as _h

    out = _card(plan, config)
    return out if raw else _h.unescape(out)


def _can_create(plan):
    """Whether the card offers Create (the one step that writes)."""
    host = (plan or {}).get("hostname", "")
    return bool(re.search(r'<span class="op-idle">Create ' + re.escape(host) + "</span>",
                          _card(plan)))


class TestEveryReasonIsOnScreen:
    """The acceptance that matters."""

    def test_all_four_reasons_render(self):
        html = _html(BLOCKED)
        for reason in BLOCKED["blocking_reasons"]:
            head = reason.split("—")[0].strip()[:40]
            assert head in html, f"missing from the screen: {reason}"

    def test_the_count_is_stated(self):
        flat = re.sub(r"\s+", " ", _html(BLOCKED))
        assert "4 reasons this device cannot be onboarded" in flat

    def test_it_says_why_they_are_all_shown(self):
        """So the operator knows to fix them in one pass rather than
        expecting a queue of one-at-a-time refusals."""
        flat = re.sub(r"\s+", " ", _html(BLOCKED))
        assert "all of them, so they can be fixed in one pass" in flat

    def test_one_reason_reads_singular(self):
        plan = dict(BLOCKED, blocking_reasons=["no management address"])
        flat = re.sub(r"\s+", " ", _html(plan))
        assert "1 reason this device" in flat

    def test_a_clean_plan_shows_no_blocker_block(self):
        """The panel must not become permanent furniture."""
        assert "cannot be onboarded" not in _html(CLEAN)


class TestCreateIsWithheldWhenBlocked:

    def test_a_blocked_plan_cannot_create(self):
        assert _can_create(BLOCKED) is False

    def test_a_clean_plan_can(self):
        assert _can_create(CLEAN) is True

    def test_a_missing_plan_cannot(self):
        """No review drawn: the card is the form, and offers no Create."""
        assert _can_create(None) is False and 'name="hostname"' in _card(None)

    def test_each_refusal_is_a_failed_gate_beside_the_withheld_create(self):
        """Where today's footer said "Create is disabled: … blocking reason(s) above", v2
        draws each refusal as a failed gate and does not draw Create at all."""
        flat = re.sub(r"\s+", " ", _html(BLOCKED))
        assert flat.count("FAILS") == len(BLOCKED["blocking_reasons"])
        assert "each is a failed gate below" in flat

    def test_create_rebuilds_and_refuses_whatever_the_page_sent(self):
        """Today's `onboardCanCreate` required `onboardable` to be exactly true in the browser;
        the decision that counts is the server's: Create rebuilds the plan and refuses one that
        is not onboardable, whatever was posted (parsed: the refusal precedes the steps)."""
        import ast
        import inspect
        import textwrap

        from routes import onboard

        src = textwrap.dedent(inspect.getsource(onboard.create_run))
        tree = ast.parse(src)
        refuse = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                      and "onboardable" in ast.unparse(n.test))
        run = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                   and getattr(n.func, "id", "") == "run_onboarding")
        assert refuse.lineno < run.lineno
        assert ast.unparse(refuse.test) == "not plan.onboardable"


class TestNothingHasBeenCreatedYet:
    """Review is the only step before Create, so going back is always safe
    — and the review step says so, the same promise the deploy plan makes."""

    def test_the_promise_is_on_the_review_step(self):
        flat = re.sub(r"\s+", " ", _html(CLEAN))
        assert "Nothing has been created yet." in flat
        assert "This is what will be." in flat

    def test_it_says_back_is_safe(self):
        flat = re.sub(r"\s+", " ", _html(CLEAN))
        assert "you can go Back from here without undoing anything" in flat

    def test_it_is_shown_even_when_blocked(self):
        """A blocked plan has created nothing either, and an operator looking
        at four refusals is exactly who needs telling."""
        flat = re.sub(r"\s+", " ", _html(BLOCKED))
        assert "Nothing has been created yet." in flat


class TestTheReviewShowsWhatWillBeCreated:

    def test_the_bootstrap_config_is_shown(self):
        html = _html(CLEAN, "hostname r6\n!\nend\n")
        assert "hostname r6" in html

    def test_the_placeholder_secret_is_explained(self):
        """The real credential is minted at create time and never sent to the
        browser — so the config on screen is not the config that boots."""
        flat = re.sub(r"\s+", " ", _html(CLEAN))
        assert "placeholder" in flat
        assert "never sent to the browser" in flat

    def test_the_csv_row_is_explained_on_a_netbox_list(self):
        """Two quite different flows, and the difference is visible rather
        than smoothed over."""
        plan = dict(CLEAN, source_kind="netbox", writes_csv=False,
                    inventory_note=("identity is read-only on a NetBox list "
                                    "— the device arrives on the next refresh"))
        flat = re.sub(r"\s+", " ", _html(plan))
        assert "identity is read-only on a NetBox list" in flat

    def test_a_local_list_says_the_row_comes_after_it_answers(self):
        """The row this screen used to promise outright."""
        plan = dict(CLEAN, inventory_note="after it answers — promotion "
                                          "adds the row, not onboarding")
        flat = re.sub(r"\s+", " ", _html(plan))
        assert "after it answers" in flat
        assert "Adds to inventory" in flat

    def test_the_credential_source_is_shown(self):
        """`_cred_source` exists so the origin is visible."""
        assert "default profile" in _html(CLEAN)

    def test_a_reason_is_escaped(self):
        plan = dict(BLOCKED, blocking_reasons=["<script>alert(1)</script>"])
        html = _html(plan, raw=True)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestToday_sIndexHasNoOnboardingTab:
    """Stage 7 reorganises around device-centric and fleet-level views.
    Onboarding is fleet-level; a thirteenth tab is what that redesign exists
    to undo. (Today's toolbar button left with the wizard at 7.8, 2026-10-17, P7-25.)"""

    def test_no_new_tab_pane_was_added(self):
        import app as nmas

        page = nmas.app.test_client().get("/").get_data(as_text=True)
        panes = re.findall(r'data-bs-target="#(\w+Pane)"', page)
        assert "onboardPane" not in panes
        # 12 until P.4 removed the Jenkins tab; 11 until 7.8 removed the History tab with
        # /list/change_log (2026-10-12).
        # 7 since 2026-10-12: Configure, Monitoring and Topology left (7.8); 5 since 2026-10-14:
        # the Ansible and Agent tabs left with the AI family (D15), Approvals became Drift; 4
        # since 2026-10-15: the Drift tab left (7.8); 3 the same day: the Logs tab left (7.8);
        # 2 since 2026-10-17: the NetBox tab left (7.8); 1 the same day: the Git tab left (7.8,
        # P7-21), Devices alone.
        assert len(set(panes)) == 1, sorted(set(panes))
        assert "openOnboardWizard" not in page and "onboardPendingBanner" not in page


class TestTheCores:
    """The cores v2's Add device calls (`routes/onboard.py`; today's /onboard/plan,
    /onboard/platforms and /onboard/create, which called them too, left at 7.8)."""

    def test_plan_creates_nothing_and_says_what_would_be(self, monkeypatch):
        from routes.onboard import plan_of

        monkeypatch.setattr("modules.integrations.get_integration",
                            lambda name: None)
        import app as nmas

        # `list_name` is required as of the target-list change: the form
        # carries it rather than inheriting whichever list is active.
        with nmas.app.test_request_context("/v2/onboard/preview", method="POST"):
            body, status = plan_of({"list_name": "Default", "hostname": "r6",
                                    "platform": "cisco_iosxe", "mgmt_ip": "203.0.113.6"})
        assert status == 200 and body["ok"] is True
        assert "blocking_reasons" in body["plan"]

    def test_a_blocked_platform_is_listed_not_omitted(self, monkeypatch):
        """An absent option teaches the operator the tool does not support
        their device, which is a different and wrong lesson. No platform is
        blocked since stage D (C712), so one is planted to show the listing, and
        Add device's form draws it disabled with its reason."""
        from modules.nsot import onboard
        from routes.onboard import platform_choices

        monkeypatch.setitem(onboard.BLOCKED_PENDING_MEASUREMENT, "cisco_ios",
                            "planted: a measurement this test pretends is owed")
        blocked = [p for p in platform_choices() if p["blocked"]]
        assert [p["reason"] for p in blocked] == \
            ["planted: a measurement this test pretends is owed"], blocked
        import app as nmas

        html = nmas.app.test_client().get("/v2/onboard/new?list=Default").get_data(
            as_text=True)
        assert re.search(r'<option value="%s" disabled>[^<]*\(not yet: planted: a measurement'
                         % re.escape(blocked[0]["platform"]), html), html[-2000:]

    def test_no_platform_is_blocked_now(self):
        """C712: a switch (cisco_ios) is offered like any other platform."""
        from routes.onboard import platform_choices

        platforms = platform_choices()
        assert not [p for p in platforms if p["blocked"]]
        assert any(p.get("dialect") == "cisco_ios" for p in platforms), platforms

    @pytest.mark.real_identity
    def test_create_requires_a_person(self):
        import app as nmas

        assert nmas.app.test_client().post("/v2/onboard/create", data={}).status_code == 403

    def test_create_refuses_a_plan_it_has_rebuilt_and_found_blocked(self, monkeypatch):
        """**Rebuilt at confirm, not carried from the review.** The stores can
        change between the screen and the confirm — the same reason the
        deploy path recomputes its program at apply rather than trusting what
        was shown. Bound to its review, and blocked: refused, naming every reason."""
        import types

        from modules.nsot import onboard as O
        from routes.onboard import create_run

        plan = types.SimpleNamespace(**{**BLOCKED, "summary": dict(BLOCKED),
                                        "host_vars": {}, "bootstrap_config": ""})
        monkeypatch.setattr(O, "build_plan", lambda **k: plan)
        monkeypatch.setattr(O, "run_onboarding",
                            lambda *a, **k: pytest.fail("created a blocked plan"))
        shown = O.plan_shown(plan)
        out, status = create_run({"list_name": "Default", "shown": shown,
                                  "fingerprint": O.plan_fingerprint(shown)}, "a@b")
        assert status == 409 and out["blocking_reasons"] == BLOCKED["blocking_reasons"]

    def test_create_runs_the_real_steps(self):
        """Not stand-ins. The whole of 4C.7 is that the real adapters satisfy
        the contract `run_onboarding` enforces."""
        from tests.astcheck import calls_in

        from routes import onboard

        assert calls_in(onboard.create_run, "run_onboarding") == 1   # the core v2 calls
        assert calls_in(onboard.create_run, "real_steps") == 1


class TestTheTargetListIsCarriedNeverDerived:
    """`PipelineContext.list_name`'s rule, applied to onboarding.

    The pipeline asked `get_current_list_name()` after the push and committed
    one network's captures into another's repository. Today's wizard inherited
    the active list the same way, and the asymmetry is worse: onboarding into
    the wrong list leaves a commit, a NetBox object and a CSV row, and the
    repair is the provenance-based Remove -- the mechanism the Stage 4C probe
    exists to prove and which has therefore never run.
    """

    def test_plan_refuses_a_request_with_no_list(self):
        from routes.onboard import plan_of

        body, status = plan_of({"hostname": "r6", "platform": "cisco-ios-xe"})
        assert status == 400, status
        assert "target list" in body.get("error", "").lower()

    @pytest.mark.real_identity
    def test_create_refuses_before_it_even_looks_at_the_list(self):
        """**403, not 400, and that ordering is correct.**

        Create is the path that writes, so the identity gate runs
        before input validation — an unauthenticated caller is refused
        without the route parsing their payload at all."""
        import app as nmas

        r = nmas.app.test_client().post("/v2/onboard/create",
                                        data={"hostname": "r6", "platform": "cisco-ios-xe"})
        assert r.status_code == 403, r.status_code

    def test_the_refusal_itself_is_unit_tested(self):
        """Because the HTTP path above never reaches it."""
        import pytest as _pytest

        from routes.onboard import NoTargetList, _target_list

        for payload in ({}, {"list_name": ""}, {"list_name": "   "}, None):
            with _pytest.raises(NoTargetList):
                _target_list(payload)
        assert _target_list({"list_name": " nmas-probe "}) == "nmas-probe"

    def test_no_core_falls_back_to_the_active_list(self):
        """The negative-space assertion, **parsed rather than grepped**.

        The first version was `"get_current_list_name" not in source` and
        failed — on `_target_list`'s own docstring, which names the function
        to explain why it is not called. A pattern that can appear in English
        needs an anchor, and the best anchor is a parse: a docstring naming a
        function is a mention, not a call.

        The whole module since today's pending read (the one that might derive the list) left
        at 7.8 (2026-10-17, P7-25): every function in it is a write path's or a reveal's."""
        import ast
        import inspect

        import routes.onboard as mod

        WRITE_PATH = ("_plan_args", "_target_list", "plan_of", "create_run", "verify_run",
                      "abandon_run", "bootstrap_reveal")

        referenced, defined = set(), set()
        for node in ast.walk(ast.parse(inspect.getsource(mod))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Name):
                        referenced.add(inner.id)
                    elif isinstance(inner, ast.Attribute):
                        referenced.add(inner.attr)
                    elif isinstance(inner, ast.ImportFrom):
                        referenced.update(a.name for a in inner.names)

        assert "get_current_list_name" not in referenced, (
            "a write path can derive a list again; it must be carried")

        # Floor: a scan that matched none of those functions would pass the
        # line above just as happily as one that matched all of them.
        for name in WRITE_PATH:
            assert name in defined, (name, sorted(defined))
        assert len(referenced) > 20, len(referenced)


ADVISED = dict(CLEAN, advisories=[
    "You cannot deploy to this device until 'cisco_iosxe/base.j2' is "
    "approved for list 'nmas-probe', which needs a captured device to "
    "validate against."])


class TestAnAdvisoryIsShownAndDoesNotBlock:
    """An advisory list that can swallow a refusal is this change's failure
    mode, so both halves are drawn as the page draws them."""

    def test_the_advisory_reaches_the_screen(self):
        html = " ".join(_html(ADVISED).split())
        assert "cannot deploy to this device" in html
        assert "this does not block onboarding" in html

    def test_create_stays_offered(self):
        assert _can_create(ADVISED) is True

    def test_an_advisory_is_not_drawn_as_a_refusal(self):
        """Different words, or the operator learns to read a note as a refusal — and then
        stops reading both."""
        html = " ".join(_html(ADVISED).split())
        assert "Worth knowing (this does not block onboarding)" in html
        assert "Not created:" not in html and "FAILS" not in html
        assert "cannot be onboarded" not in html

    def test_a_refusal_alongside_an_advisory_is_still_a_refusal(self):
        """**The control.** Both lists populated: the refusal must appear,
        Create must be withheld, and the advisory must not displace it."""
        both = dict(ADVISED, onboardable=False,
                    blocking_reasons=["no management address — the device "
                                      "would be created and unreachable"])
        html = " ".join(_html(both).split())
        assert "Not created: no management address" in html and "FAILS" in html
        assert "cannot deploy to this device" in html
        assert _can_create(both) is False
        # The refusal is drawn ABOVE the note, so a long advisory cannot push
        # it off the top of the panel.
        assert html.index("Not created: no management address") < \
            html.index("Worth knowing (this does not block onboarding)")

    def test_no_advisories_draws_no_note(self):
        """A panel that always carries a note is a panel nobody reads."""
        assert "Worth knowing" not in _html(CLEAN)


class TestTheReviewStatesWhatKeaSaid:
    """**Control BG passed without this**: removing the DHCP branch from the
    review left the suite green while the screen showed nothing about the
    reservation. A missing test, not a broken control.

    `address_claim` is computed server-side from Kea's own answer, so the
    review states *"assigned by Kea reservation <mac> → <address>"* — checked a
    moment ago — rather than *"assigned by DHCP"*, which is a promise about
    later that nothing here would notice failing.
    """

    @staticmethod
    def _dhcp_plan(**kw):
        plan = {"hostname": "bp-dhcp-a", "platform": "cisco_iosxe",
                "list": "probe", "source_kind": "local",
                "address_source": "dhcp", "mgmt_mac": "aa:bb:cc:00:02:40",
                "mgmt_ip": "", "mgmt_mask": "",
                "manager_interface": "GigabitEthernet2",
                "address_claim": ("assigned by Kea reservation "
                                  "aa:bb:cc:00:02:40 → 10.255.0.40"),
                "blocking_reasons": [], "advisories": []}
        plan.update(kw)
        return plan

    def test_the_reservation_claim_is_on_screen(self):
        html = _html(self._dhcp_plan())
        assert "Kea reservation aa:bb:cc:00:02:40" in html
        assert "10.255.0.40" in html

    def test_a_refused_reservation_is_shown_as_refused(self):
        html = _html(self._dhcp_plan(
            address_claim=("DHCP, and Kea has NO reservation for "
                           "aa:bb:cc:00:02:40 — a dynamic lease moves and "
                           "this record would not"),
            blocking_reasons=["Kea has no host reservation for aa:bb:cc:00:02:40"]))
        assert "NO reservation" in html
        assert "dynamic lease moves" in html

    def test_static_is_unchanged(self):
        """**The floor.** The DHCP branch must not capture the static case."""
        html = _html(self._dhcp_plan(
            address_source="static", mgmt_ip="203.0.113.32",
            mgmt_mask="255.255.255.0", address_claim="ignored for static"))
        assert "203.0.113.32 255.255.255.0" in html
        assert "ignored for static" not in html


class TestCreateDrawsItsResult:
    """C86 (7.1's onboarding retrofit): Create is PHASE 1. Its toast said
    "Device onboarded." while the device was pending and never reached. v2's
    Create route and the real `run_onboarding`, with the plan and the step
    adapters stubbed, drawn by v2's result parts in Add device's card."""

    @pytest.fixture
    def create(self, monkeypatch, tmp_path):
        import types

        import app as nmas
        from modules import identity as ident_mod
        from modules.nsot import onboard as O

        monkeypatch.setattr(ident_mod, "require",
                            lambda request, action="", operation="": (
                                types.SimpleNamespace(actor="ops@example.com"), None))
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        plan = types.SimpleNamespace(onboardable=True, hostname="r7", address_source="static",
                                     mgmt_ip="203.0.113.7", mgmt_mac="", blocking_reasons=[],
                                     summary={"hostname": "r7"}, host_vars={})
        monkeypatch.setattr(O, "build_plan", lambda **kw: plan)
        monkeypatch.setattr("routes.onboard._plan_args", lambda data, ln, secret="": {})
        shown = O.plan_shown(plan)

        def steps(commit_raises=None):
            def commit(p):
                if commit_raises:
                    raise RuntimeError(commit_raises)
                return "a1b2c3d4e5f60718293a"
            monkeypatch.setattr(O, "real_steps", lambda repo, actor="": {
                "bind_credentials": lambda p: None, "commit": commit, "render": lambda p: ""})
            r = nmas.app.test_client().post("/v2/onboard/create", data={
                "list_name": "Default", "hostname": "r7", "shown": shown,
                "fingerprint": O.plan_fingerprint(shown)})
            import html as _h
            return r.status_code, " ".join(_h.unescape(r.get_data(as_text=True)).split())
        return steps

    def test_a_complete_phase_one_is_pending_never_onboarded(self, create):
        status, html = create()
        assert status == 200
        assert "PENDING" in html and "press Verify" in html
        # The false claim, exactly: never that THIS device is onboarded. (A
        # bare "onboarded." matched the true sentence "only a device the
        # tool has REACHED is onboarded.")
        assert "Device onboarded" not in html and "r7 is onboarded" not in html
        assert "a1b2c3d4e5f6" in html            # the commit, in the record
        # What Create wrote, each on no device (W4 step 9 reads these lines).
        assert "What was created (on no device)" in html and "commit: " in html

    def test_a_failed_create_names_where_and_why(self, create):
        status, html = create(commit_raises="git refused: no identity")
        assert status == 500
        assert "git refused: no identity" in html
        assert "Abandon removes it" in html      # credentials were written first
