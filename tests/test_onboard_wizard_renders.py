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
    "template": "", "netbox_objects": 0, "writes_csv": True,
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
             cred_source="default profile", netbox_objects=4,
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
        plan = dict(CLEAN, source_kind="netbox", writes_csv=False)
        flat = re.sub(r"\s+", " ", _html(js, plan))
        assert "identity is read-only on a NetBox list" in flat

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
        body = client.post("/onboard/plan",
                           json={"hostname": "r6", "platform": "cisco_iosxe",
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
        r = client.post("/onboard/create", json={})   # no hostname, no platform
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

    ALL_IDS = ("obHostname", "obPlatform", "obMgmtIp", "obMgmtMask",
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
        assert set(payload) == {"hostname", "platform", "mgmt_ip", "mgmt_mask",
                                "manager_interface", "manager_gateway",
                                "mgmt_interface"}
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

    def test_a_field_missing_from_the_dom_is_survived(self, form_js):
        """The wizard must not throw when a field is absent — the review
        would then render nothing at all, which is worse than a stale
        reason."""
        values = {i: "x" for i in self.ALL_IDS if i != "obMgrGw"}
        out = dukpy.evaljs(self._stub_dom(values) + form_js
                           + "\nJSON.stringify(onboardFormPayload());")
        assert json.loads(out)["manager_gateway"] == ""
