"""Stage 7.1: the preview-then-confirm contract. One builder, one renderer.

NSOT_STAGE7_PLAN.md section 2, pattern 1. Every preview had its own renderer,
and each dropped something: D4 (the deploy wizard drew the diff in place of
the program), C27 (the restore preview never drew the lines to add). So the
server builds six parts with one helper (`modules/preview_confirm.py`) and
one shipped renderer draws them (`static/js/nmas_preview_confirm.js`).

**The six parts are a FLOOR, not a template** (the operator, 2026-09-27): a
part with nothing to say states it, because an empty section and a missing
one read the same to a person. The builder refuses a silent part, and the
renderer draws the sentence.

Renders are the SHIPPED file executed in duktape, and the screen-level ones
use a REAL `/deploy/plan` payload (`payload_providers.deploy_plan`).
"""

import os
import re

import pytest

from modules import preview_confirm as pc
from tests import payload_providers as P
from tests.payload_render import render_preview, render_result, shipped

pytest.importorskip("dukpy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "static", "js", "gen")

CONFIRM = {"may": True, "actor": "a@example.invalid", "kind": "person",
           "statement": "You are confirming as a@example.invalid."}


def _target(**over):
    t = {"name": "r1", "state": "deployable", "selectable": True, "select_data": {},
         "program": {"lines": ["interface Loopback9", " description x", "exit"]},
         "operands": [{"name": "capture hash", "value": "abc"}],
         "gates": [pc.gate("template approved", "pass")]}
    t.update(over)
    return t


def _preview(**over):
    kw = {"action": "test", "summary": "Do a thing to r1.", "targets": [_target()],
          "what_not": [], "nothing_left_out": "Nothing is left out.", "confirm": CONFIRM}
    kw.update(over)
    return pc.build(**kw)


def _parts_in_order(html):
    return re.findall(r'data-pc-part="([a-z_]+)"', html)


class TestTheBuilderRefusesASilentPart:
    """Each floor, one at a time, with the control that a full preview builds."""

    def test_a_complete_preview_builds(self):
        assert _preview()["parts"] == list(pc.PARTS)

    @pytest.mark.parametrize("over,part", [
        ({"summary": ""}, "part 1"),
        ({"targets": []}, "part 1"),
        ({"nothing_left_out": ""}, "part 2"),
        ({"targets": [_target(program={"lines": []})]}, "part 3"),
        ({"targets": [_target(operands=[])]}, "part 4"),
        ({"targets": [_target(gates=[])]}, "part 5"),
        ({"confirm": {"may": True}}, "part 6"),
        ({"explain": {"nowhere": [{"concept": "x", "text": "y"}]}}, "no such part"),
    ])
    def test_each_floor(self, over, part):
        with pytest.raises(pc.PreviewIncomplete, match=part):
            _preview(**over)

    def test_an_empty_program_that_says_so_builds(self):
        """The floor is a sentence, not content: nothing to send is a real
        answer when it is stated."""
        p = _preview(targets=[_target(program={"lines": [], "none": "Nothing to send."})])
        assert p["targets"][0]["program"]["none"] == "Nothing to send."

    def test_an_unknown_gate_state_is_refused(self):
        with pytest.raises(pc.PreviewIncomplete):
            pc.gate("x", "probably")


class TestTheRendererDrawsEveryPart:
    def test_six_parts_in_order(self):
        html = render_preview(_preview())
        assert _parts_in_order(html) == ["what", "what_not", "program", "operands",
                                         "gates", "confirm"]

    def test_the_parts_repeat_per_target_between_what_not_and_confirm(self):
        html = render_preview(_preview(targets=[_target(), _target(name="r2")]))
        assert _parts_in_order(html) == ["what", "what_not"] + [
            "program", "operands", "gates"] * 2 + ["confirm"]

    def test_nothing_left_out_is_drawn_not_omitted(self):
        html = render_preview(_preview())
        assert 'data-pc-part="what_not"' in html
        assert "Nothing is left out." in html

    def test_an_empty_program_draws_its_sentence(self):
        html = render_preview(_preview(
            targets=[_target(program={"lines": [], "none": "Nothing will be sent: X."})]))
        assert "Nothing will be sent: X." in html

    def test_every_gate_state_is_drawn_in_words(self):
        gates = [pc.gate(s, s) for s in pc.GATE_STATES]
        html = render_preview(_preview(targets=[_target(gates=gates)]))
        drawn = re.findall(r'data-pc-gate="([a-z_]+)"><span class="badge [^"]*">([^<]+)<', html)
        assert dict(drawn) == {"pass": "pass", "fail": "FAIL",
                               "not_applicable": "not applicable",
                               "at_apply": "checked at apply", "not_reached": "not reached"}

    def test_a_preview_with_other_parts_is_refused_on_screen(self):
        """A server and a cached page disagreeing about the parts: drawn as a
        refusal, never rendered with a part missing."""
        p = _preview()
        p["parts"] = [x for x in p["parts"] if x != "what_not"]
        html = render_preview(p)
        assert "data-pc-mismatch" in html and "data-pc-part" not in html


class TestTheDeployScreen:
    """The real `/deploy/plan`, drawn."""

    def test_all_six_parts_from_the_real_payload(self, monkeypatch):
        plan = P.deploy_plan(monkeypatch)
        html = render_preview(plan["preview"])
        assert _parts_in_order(html) == ["what", "what_not", "program", "operands",
                                         "gates", "confirm"]

    def test_what_not_states_nothing_when_there_is_no_residue(self, monkeypatch):
        """The fixture's intent is a superset of its capture: no residue, and
        its one device is not blocked. The part is still drawn, and says so."""
        plan = P.deploy_plan(monkeypatch)
        assert plan["preview"]["what_not"]["items"] == []
        html = render_preview(plan["preview"])
        none = re.search(r'data-pc-part="what_not".*?data-pc-none>([^<]+)<', html, re.S)
        assert none and none.group(1).startswith("Nothing"), html

    def test_the_apply_time_checks_are_never_drawn_as_passed(self, monkeypatch):
        plan = P.deploy_plan(monkeypatch)
        gates = {g["name"]: g["state"] for g in plan["preview"]["targets"][0]["gates"]}
        assert gates["capture unchanged since this preview"] == "at_apply"
        assert gates["credential unchanged"] == "at_apply"

    def test_every_blocking_condition_has_a_gate_by_name(self, monkeypatch):
        """The plan's UNDRAWN promise, kept: each condition that blocks a
        deploy is a named gate, not only a sentence."""
        plan = P.deploy_plan(monkeypatch)
        names = {g["name"] for g in plan["preview"]["targets"][0]["gates"]}
        assert {"template approved", "committed intent", "template reproduces the device",
                "every line modelled or acknowledged", "printable ASCII",
                "dangerous lines", "blocked change"} <= names

    def test_a_device_that_could_not_be_built_reached_no_gate(self):
        """A check that did not run is `not_reached`: neither a pass nor
        "not applicable"."""
        p = pc.deploy_preview([{"device": "r9", "deployable": False,
                                "blocking_reasons": ["no golden config"],
                                "to_add": [], "removal_warnings": []}], None)
        gates = p["targets"][0]["gates"]
        assert gates[0] == pc.gate("artifact built", "fail", "no golden config")
        assert {g["state"] for g in gates[1:]} == {"not_reached"}
        assert p["what"]["targets"][0]["selectable"] is False


class TestTheCaptureGateSaysWhatItCompares:
    """C78. The gate read "device unchanged since capture: re-read at apply",
    and the apply re-reads the STORED capture, never the device. Both
    previews and the deploy wizard's summary said so. The sentence now names
    what is compared and what is not."""

    def test_the_gate_names_the_stored_capture_and_the_limit(self, monkeypatch):
        plan = P.deploy_plan(monkeypatch)
        gate = {g["name"]: g for g in plan["preview"]["targets"][0]["gates"]}[
            "capture unchanged since this preview"]
        assert "stored capture is re-read" in gate["detail"]
        assert "not detected" in gate["detail"]

    def test_no_screen_claims_the_device_is_re_read(self):
        for f in ("partials__deploy_wizard.1.js", "partials__golden_repo.3.js"):
            assert "Each device is re-read" not in shipped(f), f
        src = open(os.path.join(ROOT, "modules", "preview_confirm.py"), encoding="utf-8").read()
        assert "a changed device is skipped" not in src

    def test_the_apply_compares_the_stored_capture(self):
        """What the sentence now says, read from the code it describes: the
        apply's "fresh" capture is the stored one the plan used."""
        src = open(os.path.join(ROOT, "routes", "deploy.py"), encoding="utf-8").read()
        assert src.count("fresh_captures[hostname] = captured") == 2


class TestConfirmSaysWho:
    def test_a_person_is_named(self, monkeypatch):
        plan = P.deploy_plan(monkeypatch)
        c = plan["preview"]["confirm"]
        # The person is named in the statement; there is no separate `actor`
        # echo (7.1: read by nothing, since the apply records the verified one).
        assert c["may"] is True and "actor" not in c
        assert c["statement"].startswith("You are confirming as ") and "@" in c["statement"]

    def test_no_identity_is_a_stated_refusal_and_the_button_says_it(self, monkeypatch):
        import dukpy

        from modules import identity

        monkeypatch.setattr(identity, "identify", lambda _r: identity.Identity())
        part = pc.confirm_part(None)
        assert part["may"] is False and part["statement"].startswith("You may not confirm")
        preview = _preview(confirm=part)
        assert "data-pc-refusal" in render_preview(preview)
        import json

        state = dukpy.evaljs("var window = {};\n" + shipped("nmas_preview_confirm.js")
                             + f"\nwindow.previewConfirmButton({json.dumps(preview)}, 1, 'Go')")
        assert state == {"disabled": True, "text": part["statement"]}

    def test_the_button_control(self):
        """Control for the one above: a person with a selection may press."""
        import json

        import dukpy

        state = dukpy.evaljs("var window = {};\n" + shipped("nmas_preview_confirm.js")
                             + f"\nwindow.previewConfirmButton({json.dumps(_preview())}, 1, 'Go')")
        assert state == {"disabled": False, "text": "Go"}


#: Screens moved onto the component, and the ones still to move, in the
#: approved order. RETROFIT_PENDING only shrinks.
RETROFITTED = {"deploy": "partials__deploy_wizard.1.js",
               "restore": "partials__golden_repo.3.js",
               "onboarding": "partials__onboard_wizard.1.js",
               "netbox import/remove": "partials__netbox_safety_modal.1.js"}
RETROFIT_PENDING = {
    # No screen: the routes (/templatize/bulk/preview, /apply) are reached by
    # curl today, measured 2026-09-27. DEFERRED to Fleet (7.4) by the
    # operator: a fleet-shaped operation, and a button now would be the same
    # action in two places once 7.4 builds it. Its CLI is the path in use.
    "bulk intent": None,
}


class TestNoSecondImplementation:
    """A retrofitted screen draws its preview with the component and nothing
    else: a second renderer is how the six parts drift apart again."""

    #: Phrases only a preview renderer produces.
    OWN = ("line(s) will be sent", "data-dangerous-line", "data-pc-part",
           "tick to authorise this exact line")

    def test_a_retrofitted_screen_calls_the_component_and_draws_nothing_itself(self):
        assert RETROFITTED, "floor"
        for screen, file in RETROFITTED.items():
            src = shipped(file)
            assert "previewConfirmHtml(" in src, screen
            own = [p for p in self.OWN if p in src]
            assert own == [], f"{screen} draws preview parts itself: {own}"

    def test_the_component_holds_every_phrase(self):
        """The floor for the check above: the phrases are real."""
        src = shipped("nmas_preview_confirm.js")
        assert all(p in src for p in self.OWN)

    def test_pending_screens_have_not_moved_yet(self):
        """No ghosts: a screen that now calls the component leaves the list."""
        moved = [s for s, f in RETROFIT_PENDING.items()
                 if f and "previewConfirmHtml(" in shipped(f)]
        assert moved == [], f"retrofitted: move to RETROFITTED: {moved}"

    def test_the_pending_list_only_shrinks(self):
        assert len(RETROFIT_PENDING) <= 1
        for screen, f in RETROFIT_PENDING.items():
            assert f is None or os.path.exists(os.path.join(GEN, f)), screen

    def test_the_old_deploy_renderers_are_gone(self):
        src = shipped(RETROFITTED["deploy"])
        for gone in ("function _programHtml", "function _attributionHtml",
                     "function _deviceCard"):
            assert gone not in src, gone

    def test_the_old_onboarding_review_is_gone(self):
        assert "function onboardReviewHtml" not in shipped(RETROFITTED["onboarding"])


class TestAProgramSentNowhereDoesNotSaySent:
    """C127: the program part said "Exactly these N line(s) will be sent" for
    every preview, and two of them send nothing: a capture READS a device
    (the lines are what will be recorded) and onboarding writes a startup
    config to no device. A caption replaces the sentence; with none, the
    deploy's sentence stands (the control)."""

    def _draw(self, preview):
        import json
        import dukpy
        return dukpy.evaljs("var window = {};\n" + shipped("nmas_preview_confirm.js")
                            + f"\nwindow.previewConfirmHtml({json.dumps(preview)}, {{}})")

    def test_onboarding_says_where_the_lines_go(self):
        from modules.preview_confirm import onboard_preview
        plan = {"hostname": "r9", "list_name": "default", "platform": "cisco_ios",
                "mgmt_ip": "192.0.2.9", "blocking_reasons": [], "advisories": []}
        p = onboard_preview(plan, "hostname r9\n!\nend\n",
                            {"may": True, "actor": "a@example.com", "kind": "person",
                             "statement": "You are confirming as a@example.com."})
        out = self._draw(p)
        assert "will be sent" not in out
        assert "data-pc-caption" in out and "sent to no device" in out

    def test_capture_says_it_reads(self, monkeypatch, tmp_path):
        """From the real /golden/capture/preview payload (r2 with the host's
        exact break, so the program part has lines)."""
        d = P.capture_preview(monkeypatch, tmp_path)
        assert any(t["program"]["lines"] for t in d["preview"]["targets"]), "floor"
        out = self._draw(d["preview"])
        assert "will be sent" not in out and "data-pc-caption" in out

    def test_without_a_caption_the_deploy_sentence_stands(self):
        out = self._draw(_preview())
        assert "will be sent" in out and "data-pc-caption" not in out


class TestResidueIsDrawnInItsSection:
    """A residue line alone names nothing ("description retired uplink will
    NOT be removed", on which interface?). Found by the first real residue
    fixture, 2026-09-27: each line now carries its section."""

    R3 = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r3.cfg")

    def test_a_nested_line_gets_every_header(self):
        from modules.nsot.deploy import residue_in_context

        running = open(self.R3, encoding="utf-8").read()
        got = residue_in_context(["  neighbor 198.51.100.1 prefix-list NO-PRIVATE out"],
                                 running)
        assert got == ["router bgp 65001", " address-family ipv4",
                       "  neighbor 198.51.100.1 prefix-list NO-PRIVATE out"]

    def test_two_lines_in_one_section_share_their_headers(self):
        from modules.nsot.deploy import residue_in_context

        running = open(self.R3, encoding="utf-8").read()
        got = residue_in_context(["  neighbor 198.51.100.1 activate",
                                  "  neighbor 198.51.100.1 prefix-list NO-PRIVATE out"], running)
        assert got.count("router bgp 65001") == 1 and len(got) == 4

    def test_a_line_it_cannot_place_is_reported_not_dropped(self):
        from modules.nsot.deploy import residue_in_context

        assert residue_in_context([" no such line"], "hostname x\n") == [" no such line"]

    def test_the_real_plan_draws_the_interface_with_its_line(self, monkeypatch):
        plan = P.deploy_plan_with_residue(monkeypatch)
        html = render_preview(plan["preview"])
        part = re.search(r'data-pc-part="what_not"(.*?)</section>', html, re.S).group(1)
        assert "interface GigabitEthernet0/3" in part and "retired uplink" in part
        assert 'data-concept="merge-only"' in part


class TestTheResultHalf:
    """7.1 step 2: what happened, drawn the way what-will-happen is, built
    from the receipt rows the apply wrote. Colour is the server's `level`
    only, and every field is escaped by the one renderer (C88's class)."""

    def _row(self, **over):
        row = {"device": "s4", "outcome": "deployed", "sent": True,
               "program": ["interface Gi0/2", " shutdown", "exit"],
               "program_hash": "a" * 16, "confirmed_hash": "a" * 16,
               "matches_confirmed": True, "reason": "", "stage": "",
               "checks": {"ran": True, "ok": True, "issues": [], "checked_protocols": ["ospf"],
                          "neighbours": {"ospf": [5, 5]}, "routes": [13, 13],
                          "interfaces_up": [7, 7], "pending_convergence": []},
               "rollback": {"performed": False, "commands": [], "not_undone": []}}
        row.update(over)
        return row

    def _result(self, rows, receipt_ok=True, **report):
        return pc.operation_result(rows, report, {"ok": receipt_ok, "written": len(rows),
                                                  "error": "" if receipt_ok else "disk full"},
                                   "deploy")

    def test_green_only_when_nothing_qualifies_it(self):
        assert self._result([self._row()])["level"] == "success"

    @pytest.mark.parametrize("change,level", [
        ({"matches_confirmed": False}, "partial"),
        ({"matches_confirmed": None}, "partial"),
        ({"checks": {"ran": True, "ok": False, "issues": ["ospf 5 -> 3"],
                     "checked_protocols": ["ospf"]}}, "partial"),
        ({"outcome": "failed"}, "failed"),
    ])
    def test_each_qualification_takes_the_green_away(self, change, level):
        assert self._result([self._row(**change)])["level"] == level

    def test_an_unwritten_receipt_is_not_success(self):
        """The change happened and its record did not."""
        r = self._result([self._row()], receipt_ok=False)
        assert r["level"] == "partial" and "RECEIPT NOT WRITTEN" in r["record"]["statement"]

    def test_one_refused_among_done_is_partial(self):
        rows = [self._row(), self._row(device="s3", outcome="refused", sent=False,
                                       reason="the exact command list changed")]
        r = self._result(rows)
        assert r["level"] == "partial"
        assert [i["target"] for i in r["did_not"]["items"]] == ["s3"]

    def test_the_renderer_draws_six_parts_and_the_level(self):
        html = render_result(self._result([self._row()]))
        parts = re.findall(r'data-pr-part="([a-z_]+)"', html)
        assert parts == ["happened", "did_not", "sent", "checks", "record", "not_watched"]
        assert 'data-pr-level="success"' in html and "alert-success" in html

    def test_a_partial_result_is_never_drawn_green(self):
        html = render_result(self._result([self._row(matches_confirmed=False)]))
        assert "alert-success" not in html and "alert-warning" in html
        assert "DOES NOT MATCH the program you confirmed" in html

    def test_device_text_is_escaped(self):
        """C88's class: markup in a device name or a reason is drawn as text."""
        evil = '<img src=x onerror="alert(1)">'
        rows = [self._row(device=evil, outcome="failed", sent=False, reason=evil)]
        html = render_result(self._result(rows))
        assert evil not in html and "&lt;img src=x onerror=" in html

    def test_a_result_with_other_parts_is_refused_on_screen(self):
        r = self._result([self._row()])
        r["parts"] = r["parts"][:-1]
        html = render_result(r)
        assert "data-pr-mismatch" in html and "data-pr-part" not in html

    def test_the_builder_refuses_a_silent_part(self):
        with pytest.raises(pc.ResultIncomplete, match="part 4"):
            pc.build_result(action="deploy", level="success", summary="x",
                            targets=[{"name": "s4", "sent": {"none": "nothing"},
                                      "checks": {"ran": False}}],
                            did_not=[], nothing_left_out="none", record={"statement": "s"},
                            not_watched="w")

    def test_the_level_is_the_toast_level(self):
        import json

        import dukpy

        src = shipped("nmas_preview_confirm.js")
        for level, toast in (("success", "success"), ("partial", "warning"), ("failed", "danger")):
            got = dukpy.evaljs("var window = {};\n" + src + "\nwindow.previewConfirmResultLevel("
                               + json.dumps({"level": level}) + ")")
            assert got == toast, (level, got)
