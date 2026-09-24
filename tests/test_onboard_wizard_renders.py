"""Stage 4C.4 — every blocking reason ON SCREEN, with Create disabled.

**A refusal the operator cannot see is not a refusal.** 4C.1 made
`blocking_reasons` carry every reason at once; that property is worth nothing
if the wizard shows one of them, or none.

So this file **executes the shipped renderer** — `onboardReviewHtml` and
`onboardCanCreate`, lifted out of the rendered page, not a copy — in duktape,
against a plan with several blockers. Asserting the plan object is right is
what the agent panel's tests did for three rounds while the screen said
nothing.

Both functions are pure by design: a plan in, HTML or a boolean out. That is
the shape a renderer has to have to be testable at all, and the reason the
button's state is computed separately from the HTML — whether Create is
allowed is a decision about the plan, not a detail of how the plan is drawn.
"""

import json
import re

import pytest

dukpy = pytest.importorskip("dukpy")


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


@pytest.fixture(scope="module")
def page():
    import app as nmas

    return nmas.app.test_client().get("/").get_data(as_text=True)


@pytest.fixture(scope="module")
def js(page):
    """The two pure functions, lifted from the rendered page verbatim."""
    out = []
    for name in ("onboardReviewHtml", "onboardCanCreate"):
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


def _html(js, plan, config=""):
    return dukpy.evaljs(
        js + f"\nonboardReviewHtml({json.dumps(plan)}, {json.dumps(config)});")


def _can_create(js, plan):
    return dukpy.evaljs(js + f"\nonboardCanCreate({json.dumps(plan)});")


class TestEveryReasonIsOnScreen:
    """The acceptance that matters."""

    def test_all_four_reasons_render(self, js):
        html = _html(js, BLOCKED)
        for reason in BLOCKED["blocking_reasons"]:
            head = reason.split("—")[0].strip()[:40]
            assert head in html, f"missing from the screen: {reason}"

    def test_the_count_is_stated(self, js):
        flat = re.sub(r"\s+", " ", _html(js, BLOCKED))
        assert "4 reasons this device cannot be onboarded" in flat

    def test_it_says_why_they_are_all_shown(self, js):
        """So the operator knows to fix them in one pass rather than
        expecting a queue of one-at-a-time refusals."""
        flat = re.sub(r"\s+", " ", _html(js, BLOCKED))
        assert "all of them, so they can be fixed in one pass" in flat

    def test_one_reason_reads_singular(self, js):
        plan = dict(BLOCKED, blocking_reasons=["no management address"])
        flat = re.sub(r"\s+", " ", _html(js, plan))
        assert "1 reason this device" in flat

    def test_a_clean_plan_shows_no_blocker_block(self, js):
        """The panel must not become permanent furniture."""
        assert "cannot be onboarded" not in _html(js, CLEAN)


class TestCreateIsDisabledWhenBlocked:

    def test_a_blocked_plan_cannot_create(self, js):
        assert _can_create(js, BLOCKED) is False

    def test_a_clean_plan_can(self, js):
        assert _can_create(js, CLEAN) is True

    def test_a_missing_plan_cannot(self, js):
        assert _can_create(js, None) is False

    def test_onboardable_must_be_exactly_true(self, js):
        """Not truthy. A plan carrying a string, or a stale field, must not
        open the one step that writes."""
        assert _can_create(js, dict(CLEAN, onboardable="yes")) is False

    def test_the_button_is_bound_to_it(self, page):
        assert "btn.disabled = !onboardCanCreate(d.plan)" in page

    def test_the_footer_says_why_it_is_disabled(self, page):
        flat = re.sub(r"\s+", " ", page)
        assert "Create is disabled:" in flat
        assert "blocking reason(s) above" in flat


class TestNothingHasBeenCreatedYet:
    """Review is the only step that creates anything, so Back is always safe
    — and the review step says so, the same promise the deploy plan makes."""

    def test_the_promise_is_on_the_review_step(self, js):
        flat = re.sub(r"\s+", " ", _html(js, CLEAN))
        assert "Nothing has been created yet." in flat
        assert "This is what will be." in flat

    def test_it_says_back_is_safe(self, js):
        flat = re.sub(r"\s+", " ", _html(js, CLEAN))
        assert "you can go Back from here without undoing anything" in flat

    def test_it_is_shown_even_when_blocked(self, js):
        """A blocked plan has created nothing either, and an operator looking
        at four refusals is exactly who needs telling."""
        flat = re.sub(r"\s+", " ", _html(js, BLOCKED))
        assert "Nothing has been created yet." in flat


class TestTheReviewShowsWhatWillBeCreated:

    def test_the_bootstrap_config_is_shown(self, js):
        html = _html(js, CLEAN, "hostname r6\n!\nend\n")
        assert "hostname r6" in html

    def test_the_placeholder_secret_is_explained(self, js):
        """The real credential is minted at create time and never sent to the
        browser — so the config on screen is not the config that boots."""
        flat = re.sub(r"\s+", " ", _html(js, CLEAN))
        assert "placeholder" in flat
        assert "never sent to the browser" in flat

    def test_the_csv_row_is_explained_on_a_netbox_list(self, js):
        """Two quite different flows, and the difference is visible rather
        than smoothed over."""
        plan = dict(CLEAN, source_kind="netbox", writes_csv=False,
                    inventory_note=("identity is read-only on a NetBox list "
                                    "— the device arrives on the next refresh"))
        flat = re.sub(r"\s+", " ", _html(js, plan))
        assert "identity is read-only on a NetBox list" in flat

    def test_a_local_list_says_the_row_comes_after_it_answers(self, js):
        """The row this screen used to promise outright."""
        plan = dict(CLEAN, inventory_note="after it answers — promotion "
                                          "adds the row, not onboarding")
        flat = re.sub(r"\s+", " ", _html(js, plan))
        assert "after it answers" in flat
        assert "Adds to inventory" in flat

    def test_the_credential_source_is_shown(self, js):
        """`_cred_source` exists so the origin is visible."""
        assert "default profile" in _html(js, CLEAN)

    def test_a_reason_is_escaped(self, js):
        plan = dict(BLOCKED, blocking_reasons=["<script>alert(1)</script>"])
        html = _html(js, plan)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestItIsAToolbarActionNotATab:
    """Stage 7 reorganises around device-centric and fleet-level views.
    Onboarding is fleet-level; a thirteenth tab is what that redesign exists
    to undo."""

    def test_no_new_tab_pane_was_added(self, page):
        panes = re.findall(r'data-bs-target="#(\w+Pane)"', page)
        assert "onboardPane" not in panes
        assert len(set(panes)) == 12, sorted(set(panes))

    def test_the_toolbar_button_exists(self, page):
        assert 'onclick="openOnboardWizard()"' in page

    def test_it_is_available_with_an_empty_device_list(self, page):
        """An empty list is exactly when somebody needs to add a device, and
        the button would be absent when it is most useful.

        Asserted against the SOURCE, where the block structure is still
        visible, and matched on the tag at the START OF A LINE. A plain
        substring search found the tag quoted inside the comment that
        explains this very decision — fourth time prose about code has
        matched a grep for code in this project, and the tell each time is a
        pattern that can appear in English.
        """
        import io
        import os
        import re

        src = io.open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "templates", "index.html"),
            encoding="utf-8").read()

        button = re.search(r'^\s*<button[^>]*openOnboardWizard\(\)', src, re.M)
        guard = re.search(r"^\s*\{% if devices %\}", src, re.M)
        assert button and guard
        assert button.start() < guard.start(), (
            "the onboard button is inside the `if devices` block — it would "
            "be absent from an empty list")


class TestTheRoutes:

    @pytest.fixture
    def client(self):
        import app as nmas

        return nmas.app.test_client()

    def test_plan_creates_nothing_and_says_what_would_be(self, client,
                                                         monkeypatch):
        monkeypatch.setattr("modules.integrations.get_integration",
                            lambda name: None)
        # `list_name` is required as of the target-list change: the wizard
        # carries it rather than inheriting whichever list is active.
        body = client.post("/onboard/plan",
                           json={"list_name": "Default", "hostname": "r6",
                                 "platform": "cisco_iosxe",
                                 "mgmt_ip": "203.0.113.6"}).get_json()
        assert body["ok"] is True
        assert "blocking_reasons" in body["plan"]

    def test_a_blocked_platform_is_listed_not_omitted(self, client):
        """An absent option teaches the operator the tool does not support
        their device, which is a different and wrong lesson."""
        body = client.get("/onboard/platforms").get_json()
        blocked = [p for p in body["platforms"] if p["blocked"]]
        assert blocked, "cisco_ios should be listed and disabled"
        assert all(p["reason"] for p in blocked)

    def test_create_requires_a_person(self, client):
        assert client.post("/onboard/create", json={}).status_code == 403

    def test_create_refuses_a_plan_it_has_rebuilt_and_found_blocked(
            self, client, monkeypatch):
        """**Rebuilt at confirm, not carried from the review.** The stores can
        change between the screen and the confirm — the same reason the
        deploy path recomputes its program at apply rather than trusting what
        was shown."""
        from modules import identity as ident_mod

        monkeypatch.setattr(ident_mod, "require",
                            lambda request, action="", operation="": (
                                type("I", (), {"actor": "a@b"})(), None))
        # A list, so the rebuild gets as far as the plan -- but no hostname
        # and no platform, which is what this test is about.
        r = client.post("/onboard/create", json={"list_name": "Default"})
        assert r.status_code == 409
        assert r.get_json()["blocking_reasons"]

    def test_create_runs_the_real_steps(self):
        """Not stand-ins. The whole of 4C.7 is that the real adapters satisfy
        the contract `run_onboarding` enforces."""
        from tests.astcheck import calls_in

        from routes import onboard

        assert calls_in(onboard.create, "run_onboarding") == 1
        assert calls_in(onboard.create, "real_steps") == 1


# ---------------------------------------------------------------------------
# Every field the payload sends must also trigger a re-validation
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def form_js(page):
    """`ONBOARD_FIELDS` and `onboardFormPayload`, lifted from the page."""
    start = page.index("const ONBOARD_FIELDS = {")
    end = page.index("}", page.index("mgmt_interface:", start)) + 2
    fields = page[start:end]

    fstart = page.index("function onboardFormPayload(")
    depth, i, seen = 0, page.index("{", fstart), False
    while i < len(page):
        if page[i] == "{":
            depth += 1
            seen = True
        elif page[i] == "}":
            depth -= 1
            if seen and depth == 0:
                break
        i += 1
    return fields + "\n" + page[fstart:i + 1]


class TestTheFormIsReadAndWatchedFromOneList:
    """4C.8 added three fields to the form and to the payload, and left the
    listener array as the original four ids.

    The values were **sent** correctly, so nothing about the payload was
    wrong — but nothing asked for them to be re-sent. An operator filling in
    the netmask watched *"no network mask"* sit there unchanged and would
    reasonably conclude the wizard was broken. Measured on the live page,
    mid-probe, by the operator.

    Asserted here by executing the shipped source, because a defect in which
    two lists disagree cannot be seen by reading either one.
    """

    ALL_IDS = ("obList", "obHostname", "obPlatform", "obMgmtIp", "obMgmtMask",
               "obMgrIntf", "obMgrGw", "obMgmtIntf")

    def _stub_dom(self, values):
        return ("var __bound = [];\n"
                "var __els = %s;\n"
                "var document = { getElementById: function (id) {\n"
                "  if (!(id in __els)) { return null; }\n"
                "  return { value: __els[id],\n"
                "           addEventListener: function (ev, fn) {\n"
                "             __bound.push(id + ':' + ev); } };\n"
                "} };\n" % json.dumps(values))

    def test_the_payload_reads_every_field_on_the_form(self, form_js):
        values = {i: "v-" + i for i in self.ALL_IDS}
        out = dukpy.evaljs(self._stub_dom(values) + form_js
                           + "\nJSON.stringify(onboardFormPayload());")
        payload = json.loads(out)
        assert set(payload) == {"list_name", "hostname", "platform", "mgmt_ip",
                                "mgmt_mask", "manager_interface",
                                "manager_gateway", "mgmt_interface"}
        # Every value arrives, not just every key. A builder reading the
        # wrong id would return the right shape full of empty strings.
        assert "" not in payload.values(), payload

    def test_every_field_the_payload_reads_is_also_bound(self, form_js):
        """**The defect, as an assertion.**

        The binding loop and the payload builder now walk the same object, so
        this is true by construction — which is the point. It is asserted
        anyway because "by construction" was also true of `_plan_args()` and
        `onboardFormPayload()`, and the third list still drifted.
        """
        values = {i: "x" for i in self.ALL_IDS}
        binder = ("Object.keys(ONBOARD_FIELDS).forEach(function (key) {\n"
                  "  var el = document.getElementById(ONBOARD_FIELDS[key]);\n"
                  "  if (el) { el.addEventListener('input', function () {});\n"
                  "            el.addEventListener('change', function () {}); }\n"
                  "});\n")
        out = dukpy.evaljs(self._stub_dom(values) + form_js + "\n" + binder
                           + "JSON.stringify([__bound, "
                             "Object.keys(ONBOARD_FIELDS).length]);")
        bound, count = json.loads(out)
        bound_ids = {b.split(":")[0] for b in bound}

        assert count == len(self.ALL_IDS), (
            f"ONBOARD_FIELDS has {count} entries and the form has "
            f"{len(self.ALL_IDS)} — a field was added to one and not the other")
        assert bound_ids == set(self.ALL_IDS), (
            "fields read but never watched: "
            f"{sorted(set(self.ALL_IDS) - bound_ids)}. Filling one of these "
            "in would not clear its blocking reason.")

    def test_the_target_list_value_arrives(self, form_js):
        """Named separately from the loop above because it is the field whose
        absence is worst.

        A payload carrying the right KEY and an empty value would send
        `list_name: ""`, and the route refuses that -- but before
        `_target_list()` existed it fell through to the active list, which is
        the whole defect. The value arriving is the property; the key is not.
        """
        values = {i: "x" for i in self.ALL_IDS}
        values["obList"] = "nmas-probe"
        out = dukpy.evaljs(self._stub_dom(values) + form_js
                           + "\nJSON.stringify(onboardFormPayload());")
        assert json.loads(out)["list_name"] == "nmas-probe"

    def test_a_field_missing_from_the_dom_is_survived(self, form_js):
        """The wizard must not throw when a field is absent — the review
        would then render nothing at all, which is worse than a stale
        reason."""
        values = {i: "x" for i in self.ALL_IDS if i != "obMgrGw"}
        out = dukpy.evaljs(self._stub_dom(values) + form_js
                           + "\nJSON.stringify(onboardFormPayload());")
        assert json.loads(out)["manager_gateway"] == ""


class TestTheTargetListIsCarriedNeverDerived:
    """`PipelineContext.list_name`'s rule, applied to the wizard.

    The pipeline asked `get_current_list_name()` after the push and committed
    one network's captures into another's repository. The wizard inherited
    the active list the same way, and the asymmetry is worse: onboarding into
    the wrong list leaves a commit, a NetBox object and a CSV row, and the
    repair is the provenance-based Remove -- the mechanism the Stage 4C probe
    exists to prove and which has therefore never run.
    """

    def _post(self, path, payload):
        import app as nmas

        client = nmas.app.test_client()
        return client.post(path, json=payload)

    def test_plan_refuses_a_request_with_no_list(self):
        r = self._post("/onboard/plan", {"hostname": "r6",
                                         "platform": "cisco-ios-xe"})
        assert r.status_code == 400, r.status_code
        assert "target list" in (r.get_json() or {}).get("error", "").lower()

    def test_create_refuses_before_it_even_looks_at_the_list(self):
        """**403, not 400, and that ordering is correct.**

        `/onboard/create` is the path that writes, so the identity gate runs
        before input validation — an unauthenticated caller is refused
        without the route parsing their payload at all. The first version of
        this test asserted 400 and was wrong about the code rather than the
        other way round.
        """
        r = self._post("/onboard/create", {"hostname": "r6",
                                           "platform": "cisco-ios-xe"})
        assert r.status_code == 403, r.status_code

    def test_the_refusal_itself_is_unit_tested(self):
        """Because the HTTP path above never reaches it."""
        import pytest as _pytest

        from routes.onboard import NoTargetList, _target_list

        for payload in ({}, {"list_name": ""}, {"list_name": "   "}, None):
            with _pytest.raises(NoTargetList):
                _target_list(payload)
        assert _target_list({"list_name": " nmas-probe "}) == "nmas-probe"

    def test_no_route_falls_back_to_the_active_list(self):
        """The negative-space assertion, **parsed rather than grepped**.

        The first version was `"get_current_list_name" not in source` and
        failed — on `_target_list`'s own docstring, which names the function
        to explain why it is not called. A pattern that can appear in English
        needs an anchor, and the best anchor is a parse: a docstring naming a
        function is a mention, not a call.

        That is the fourth instance of this shape in the project and the
        first where the prose and the checker were written in the same edit.
        """
        import ast
        import inspect

        import routes.onboard as mod

        tree = ast.parse(inspect.getsource(mod))
        referenced, defined = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                referenced.update(a.name for a in node.names)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)

        assert "get_current_list_name" not in referenced, (
            "the wizard can derive a list again; it must be carried")

        # Floor: a parse that found nothing would pass the line above just as
        # happily as one that found everything.
        assert "_target_list" in defined, sorted(defined)
        assert len(referenced) > 20, len(referenced)

    def test_the_lists_endpoint_answers(self):
        import app as nmas

        body = nmas.app.test_client().get("/onboard/lists").get_json()
        assert body.get("ok") is True, body
        assert isinstance(body.get("lists"), list)
        assert body["lists"], "no lists returned — the select would be empty"
        row = body["lists"][0]
        for key in ("name", "slug", "device_count", "is_current"):
            assert key in row, (key, row)


ADVISED = dict(CLEAN, advisories=[
    "You cannot deploy to this device until 'cisco_iosxe/base.j2' is "
    "approved for list 'nmas-probe', which needs a captured device to "
    "validate against."])


class TestAnAdvisoryIsShownAndDoesNotBlock:
    """An advisory list that can swallow a refusal is this change's failure
    mode, so both halves are executed in the shipped renderer."""

    def test_the_advisory_reaches_the_screen(self, js):
        # Whitespace-normalised: the heading wraps in the template source, so
        # a raw substring match tests the line breaks rather than the words.
        html = " ".join(_html(js, ADVISED).split())
        assert "cannot deploy to this device" in html
        assert "this does not block onboarding" in html

    def test_create_stays_enabled(self, js):
        assert _can_create(js, ADVISED) is True

    def test_an_advisory_is_not_drawn_as_a_refusal(self, js):
        """Different colour and a different heading, or the operator learns
        to read a yellow box as a red one — and then stops reading both."""
        html = _html(js, ADVISED)
        assert "alert-warning" in html
        assert "cannot be onboarded" not in html

    def test_a_refusal_alongside_an_advisory_is_still_a_refusal(self, js):
        """**The control.** Both lists populated: the refusal must appear,
        Create must be disabled, and the advisory must not displace it."""
        both = dict(ADVISED, onboardable=False,
                    blocking_reasons=["no management address — the device "
                                      "would be created and unreachable"])
        html = _html(js, both)
        assert "alert-danger" in html
        assert "no management address" in html
        assert "cannot deploy to this device" in html
        assert _can_create(js, both) is False
        # The refusal is drawn ABOVE the note, so a long advisory cannot push
        # it off the top of the panel.
        assert html.index("alert-danger") < html.index("alert-warning")

    def test_no_advisories_draws_no_box(self, js):
        """A panel that always carries a note is a panel nobody reads."""
        html = _html(js, CLEAN)
        assert "alert-warning" not in html
