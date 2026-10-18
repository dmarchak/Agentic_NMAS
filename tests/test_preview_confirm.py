"""Stage 7.1: the preview-then-confirm contract. One builder, one renderer.

NSOT_STAGE7_PLAN.md section 2, pattern 1. Every preview had its own renderer,
and each dropped something: D4 (the deploy wizard drew the diff in place of
the program), C27 (the restore preview never drew the lines to add). So the
server builds six parts with one helper (`modules/preview_confirm.py`) and
one renderer draws them: today's `static/js/nmas_preview_confirm.js` until it left with
today's index at 7.8 (2026-10-17, P7-27); on v2 the shared parts
(`templates/v2/_preview_parts.html`) and the cards drawn from the same parts (the device page's
Deploy…, the batch's card).

**The six parts are a FLOOR, not a template** (the operator, 2026-09-27): a
part with nothing to say states it, because an empty section and a missing
one read the same to a person. The builder refuses a silent part.

Renders are v2's templates through the app's own Jinja (`tests/payload_render.py`), and the
screen-level ones use a REAL plan (`payload_providers.deploy_plan`).
"""

import os
import re

import pytest

from modules import preview_confirm as pc
from tests import payload_providers as P
from tests.payload_render import (render_deploy_card_v2, render_operation_result_v2,
                                  render_preview_v2)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
    """v2's shared parts (`templates/v2/_preview_parts.html`, the drawing of a component-built
    preview on NetBox and onboarding). Today's renderer drew six marked parts in order, said
    "nothing is left out" in an empty what-not part and refused a preview whose parts
    disagreed; it left with today's index at 7.8 (2026-10-17, P7-27). v2's parts draw no
    what-not section when it is empty (the register row named in the P7-27 commit)."""

    def test_every_part_is_drawn(self):
        p = _preview(what_not=[{"target": "r1", "kind": "residue", "text": "Left: x."}])
        html = render_preview_v2(p)
        assert "Do a thing to r1." in html                        # what
        assert "interface Loopback9" in html                      # program
        assert "<dt>capture hash</dt><dd>abc</dd>" in html         # operands
        assert "template approved" in html                        # gates
        assert "Left: x." in html                                 # what_not

    def test_the_parts_repeat_per_target(self):
        html = render_preview_v2(_preview(targets=[_target(), _target(name="r2")]))
        assert html.count("Checked now, and at your confirm") == 2
        assert html.count("<dt>capture hash</dt>") == 2

    def test_an_empty_program_draws_its_sentence(self):
        html = render_preview_v2(_preview(
            targets=[_target(program={"lines": [], "none": "Nothing will be sent: X."})]))
        assert "Nothing will be sent: X." in html

    def test_every_gate_state_is_drawn_in_words(self):
        gates = [pc.gate(s, s) for s in pc.GATE_STATES]
        html = render_preview_v2(_preview(targets=[_target(gates=gates)]))
        drawn = re.findall(r'<span class="badge [^"]*">([^<]+)</span> <span>([a-z_]+)</span>',
                           html)
        assert {state: words for words, state in drawn} == {
            "pass": "passed", "fail": "FAILS", "not_applicable": "not applicable",
            "at_apply": "at confirm", "not_reached": "not established"}



class TestTheDeployScreen:
    """The real plan (`/deploy/plan` until 7.8), drawn by v2's Deploy… card."""

    def test_what_not_states_nothing_when_there_is_no_residue(self, monkeypatch):
        """The fixture's intent is a superset of its capture: no residue, and
        its one device is not blocked. The part is still drawn, and says so."""
        plan = P.deploy_plan(monkeypatch)
        assert plan["preview"]["what_not"]["items"] == []
        host = plan["devices"][0]["device"]
        html = render_deploy_card_v2(plan, host)
        assert f"Nothing: {host} holds no line its committed intent lacks." in html
        assert "No line is removed that you did not tick." in html


    def test_the_apply_time_checks_are_never_drawn_as_passed(self, monkeypatch):
        plan = P.deploy_plan(monkeypatch)
        gates = {g["name"]: g["state"] for g in plan["preview"]["targets"][0]["gates"]}
        assert gates["device and capture unchanged since this preview"] == "at_apply"
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
    and the apply re-read the STORED capture, never the device. Both
    previews and the deploy wizard's summary said so. The sentence then named
    what was compared and what was not; since C78 was built (2026-10-07) the
    device is compared too (tests/test_device_compared_at_apply.py)."""

    def test_the_gate_names_the_stored_capture_and_the_device(self, monkeypatch):
        plan = P.deploy_plan(monkeypatch)
        gate = {g["name"]: g for g in plan["preview"]["targets"][0]["gates"]}[
            "device and capture unchanged since this preview"]
        assert "stored capture is re-read" in gate["detail"]
        assert "skipped as drifted, with nothing sent" in gate["detail"]

    def test_no_screen_claims_the_device_is_re_read(self):
        # Today's re-apply dialog (partials__golden_repo.3.js) and deploy wizard
        # (partials__deploy_wizard.1.js) left at 7.8 (2026-10-17); v2's templates are held.
        from tests.source_index import tracked

        v2 = tracked("templates/v2", suffix=".html", recursive=False)
        assert len(v2) > 50
        for f in v2:
            assert "Each device is re-read" not in open(f, encoding="utf-8").read(), f
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
        """With nobody verified the part refuses in words, and v2's Deploy… card fails its
        verified-person check and offers no confirm (today's renderer drew the refusal on its
        button until P7-27)."""
        from modules import identity

        plan = P.deploy_plan(monkeypatch)
        monkeypatch.setattr(identity, "identify", lambda _r: identity.Identity())
        part = pc.confirm_part(None)
        assert part["may"] is False and part["statement"].startswith("You may not confirm")
        html = render_deploy_card_v2(plan, plan["devices"][0]["device"])
        assert "<strong>You are a verified person</strong>: You may not confirm" in html
        assert "op-confirm" not in html

    def test_the_button_control(self, monkeypatch):
        """Control for the one above: a person passes the check, by name."""
        plan = P.deploy_plan(monkeypatch)
        html = render_deploy_card_v2(plan, plan["devices"][0]["device"])
        assert "<strong>You are a verified person</strong>" not in html
        assert "You are a verified person: " in html



# RETROFITTED, RETROFIT_PENDING and the checks over them (each of today's screens calling the
# component and drawing no preview part itself) left with today's last screens at 7.8
# (2026-10-17, P7-27): no script of today's is left to retrofit. v2 draws a component-built
# preview with its shared parts (`templates/v2/_preview_parts.html`) or a card of its own, and
# its confirms are one pattern (tests/test_v2_one_confirm.py).


class TestNoSecondImplementation:
    def test_the_old_renderers_are_gone_everywhere(self):
        """The deploy wizard's own renderers and onboarding's review, which the component
        replaced (7.1), were held gone in their two scripts until both scripts left at 7.8
        (2026-10-17, P7-25); held now across every script still shipped."""
        from tests.source_index import tracked

        scripts = tracked("static/js", suffix=".js", recursive=False)
        assert len(scripts) > 10
        for path in scripts:
            src = open(path, encoding="utf-8").read()
            for gone in ("function _programHtml", "function _attributionHtml",
                         "function _deviceCard", "function onboardReviewHtml"):
                assert gone not in src, (path, gone)



class TestAProgramSentNowhereDoesNotSaySent:
    """C127: the program part said "Exactly these N line(s) will be sent" for
    every preview, and two of them send nothing: a capture READS a device
    (the lines are what will be recorded) and onboarding writes a startup
    config to no device. The program's title says where the lines go; with none, the
    deploy's sentence stands (the control). Drawn by v2's shared parts (today's renderer, which
    drew a caption, until P7-27)."""

    def test_onboarding_says_where_the_lines_go(self):
        from modules.preview_confirm import onboard_preview
        plan = {"hostname": "r9", "list_name": "default", "platform": "cisco_ios",
                "mgmt_ip": "192.0.2.9", "blocking_reasons": [], "advisories": []}
        p = onboard_preview(plan, "hostname r9\n!\nend\n",
                            {"may": True, "actor": "a@example.com", "kind": "person",
                             "statement": "You are confirming as a@example.com."})
        out = render_preview_v2(p)
        assert "will be sent" not in out
        assert "What will be created (on no device)" in out

    def test_capture_says_it_reads(self, monkeypatch, tmp_path):
        """From the real capture preview (r2 with the host's exact break, so the program part
        has lines); the device page's Capture card draws it (tests/test_device_capture_v2.py,
        `test_it_draws_every_part_the_mockup_drew`)."""
        d = P.capture_preview(monkeypatch, tmp_path)
        assert any(t["program"]["lines"] for t in d["preview"]["targets"]), "floor"
        assert d["preview"]["titles"]["program"] == "What will change in its golden"
        assert all(t["program"].get("caption") for t in d["preview"]["targets"])

    def test_without_a_caption_the_deploy_sentence_stands(self):
        out = render_preview_v2(_preview())
        assert "What will be sent" in out



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
        """THE plan's residue on v2's Deploy… card (today's renderer until P7-27): each line
        with its section, under merge-only."""
        import html as _html

        plan = P.deploy_plan_with_residue(monkeypatch)
        host = plan["devices"][0]["device"]
        html = _html.unescape(render_deploy_card_v2(plan, host))
        part = html[html.index('id="removal"'):html.index("What will not happen")]
        assert "interface GigabitEthernet0/3 > " in part and "retired uplink" in part
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
        """v2's batch card (`templates/v2/_apply_job.html`; today's renderer until P7-27):
        the level as its badge, what happened, what was sent with the match, what verify
        checked, the record and what is not watched."""
        html = render_operation_result_v2(self._result([self._row()]))
        assert '<span class="badge badge-ok">Done</span>' in html
        assert "1 of 1 device(s) deployed" in html
        assert "interface Gi0/2\n shutdown\nexit" in html
        assert "matches the program you confirmed" in html
        assert "Verify passed, checking ospf." in html
        assert "Receipt: 1 device row(s) recorded" in html

    def test_a_partial_result_is_never_drawn_green(self):
        html = render_operation_result_v2(self._result([self._row(matches_confirmed=False)]))
        assert "badge-ok" not in html.split("</h2>", 1)[0]
        assert '<span class="badge badge-warn">Partly done</span>' in html
        assert "DOES NOT MATCH the program you confirmed" in html

    def test_device_text_is_escaped(self):
        """C88's class: markup in a device name or a reason is drawn as text."""
        evil = '<img src=x onerror="alert(1)">'
        rows = [self._row(device=evil, outcome="failed", sent=False, reason=evil)]
        html = render_operation_result_v2(self._result(rows))
        assert evil not in html and "&lt;img src=x onerror=" in html

    # Today's renderer refused a result whose parts disagreed with its own (`data-pr-mismatch`)
    # and turned the level into a toast's; both left with it at 7.8 (P7-27). v2's cards draw a
    # result by its keys and raise no toast (tests/test_v2_pages.py).

    def test_the_builder_refuses_a_silent_part(self):
        with pytest.raises(pc.ResultIncomplete, match="part 4"):
            pc.build_result(action="deploy", level="success", summary="x",
                            targets=[{"name": "s4", "sent": {"none": "nothing"},
                                      "checks": {"ran": False}}],
                            did_not=[], nothing_left_out="none", record={"statement": "s"},
                            not_watched="w")



# TestATintedBlockSetsItsOwnTextColour (today's renderer's `bg-body-tertiary` blocks each paired
# with `text-body`, the NetBox sync card's unreadable code blocks, 2026-09-28) left with today's
# renderer and Bootstrap at 7.8 (2026-10-17, P7-27). v2 colours by tokens with dark values
# (tests/test_v2_theme.py).
