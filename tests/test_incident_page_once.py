"""The incident page says each fact once and draws a hold as what it is (the operator's review of
r7's page after Part A, 2026-11-15; R2, MERCURY_CHARTER "Two standing rules": "A guard or hold
working as designed is a plain line in the details, never a failure"; docs/UI_RULES.md, "Each
fact appears once").

- **C3728, a hold is never a red failure:** an incident whose decision a guard held (guard 4:
  its golden departs from intent) draws What Mercury has done's chip neutral
  (``data-outcome-level="hold"``, ``badge-neutral``), the hold's plain line (`bluf.hold_line`)
  on its hover; a heal that failed (rolled back) keeps its red chip: red only for what failed.
- **C3729, the evidence drawn once:** every planted page has at most one evidence home, under
  the bottom line (``#inc-evidence``), and none below What Mercury has done; an incident with
  members names them there.

Through the real app on the heal's lab (tests/test_incident_page.py's planted incidents and the
real decision held by guard 4, tests/test_heal_decide.py's `Fake` with its golden departing).
No device, no network.
"""
import re
from html import unescape

import pytest

from tests import test_incident_page as T
from tests import test_incident_titles as TT
from tests.test_heal_decide import GOLDEN, ROUTE4, Fake, settle
from tests.test_heal_decide import lab  # noqa: F401  (the fixture `client` builds on)
from tests.test_heal_policy import T0
from tests.test_heal_propose import measured  # noqa: F401  (a fixture)
from tests.test_incident_page import client, no_host_addresses  # noqa: F401  (fixtures)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

NET = T.NET


def held():
    """A decision held by guard 4: edge-b's golden departs from its intent. Since C3909 (the
    operator, 2026-11-17) the decision no longer holds that case (it is a can't-fix), but the
    decisions it held before stay in the records the page draws: the real decision's pass,
    its guard 4 judged by `guards.g4_golden` (the hold as it was, still in the guards module)
    in place of `decide._g4`, so the record is the one that pass wrote then."""
    import pytest

    from modules.heal import decide as DC
    from modules.heal import guards

    def g4_as_recorded_before(network, device, src, dev):
        golden = src.golden(device, dev)
        return guards.g4_golden(golden), golden
    settle(GOLDEN + ROUTE4, triggers=[T.CFG], claim=False)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(DC, "_g4", g4_as_recorded_before)
        (d,) = DC.run(NET, now=T0, sources=Fake(GOLDEN + ROUTE4, state="departs"))["decided"]
    assert d["outcome"] == "held", d
    from modules.heal import decisions
    (kept,) = [x for x in decisions.decisions(NET) if x.get("incident") == d["incident"]]
    assert (kept.get("guard") or {}).get("guard") == 4, kept
    return d["incident"]


def chip(body: str) -> str:
    """What Mercury has done's outcome chip, as drawn in its summary (its entities read)."""
    done = body.split('id="inc-done"', 1)[1].split("</summary>", 1)[0]
    m = re.search(r'<span data-outcome-level="[^"]*">.*?</span></span>', done, re.S)
    return unescape(m.group(0)) if m else ""


def faults(c: str, *, hold: bool) -> list:
    """What is wrong with chip *c*: a hold drawn red, or without its plain line; a failure not
    drawn red."""
    out = []
    if hold and ("badge-danger" in c or 'data-outcome-level="hold"' not in c):
        out.append("a hold drawn as a failure")
    if hold and "won't write" not in c:
        out.append("a hold without its plain line on the hover")
    if not hold and "badge-danger" not in c:
        out.append("a failure not drawn red")
    return out


class TestAHoldIsNeverARedFailure:
    def test_guard_4_s_hold_is_neutral_with_its_plain_line(self, client):  # noqa: F811
        c = chip(T.page(client, held()))
        assert c and "Self-healing (dry run): held" in c, c
        assert "badge-neutral" in c and faults(c, hold=True) == [], c
        assert "Self-healing won't write to edge-b until its saved config matches intent" in c

    def test_a_heal_that_failed_keeps_its_red(self, client):  # noqa: F811
        c = chip(T.page(client, T.rolled_back()))
        assert c and faults(c, hold=False) == [], c

    def test_the_check_finds_a_hold_drawn_red(self):
        """The floor: the chip the review measured on r7's page."""
        red = ('<span data-outcome-level="danger"><span class="badge badge-danger">'
               "Self-healing (dry run): held</span></span>")
        assert faults(red, hold=True) == ["a hold drawn as a failure",
                                          "a hold without its plain line on the hover"]


def evidence_homes(body: str) -> list:
    """Every place the page draws its evidence: each element whose summary or heading is
    Evidence."""
    live = body.split('id="incident-live"', 1)[1]
    return re.findall(r"<(?:summary|h2)[^>]*>\s*Evidence\b", live)


class TestTheEvidenceIsDrawnOnce:
    @pytest.mark.parametrize("name", sorted(TT.PLANTS))
    def test_at_most_one_home_and_it_is_under_the_bottom_line(self, client, measured, name):  # noqa: F811
        body = T.page(client, TT.PLANTS[name]())
        homes = evidence_homes(body)
        assert len(homes) <= 1, (name, homes)
        if homes:
            live = body.split('id="incident-live"', 1)[1]
            assert live.index('id="inc-bluf"') < live.index('id="inc-evidence"') < \
                live.index('id="inc-done"'), name

    def test_members_are_named_in_the_one_home(self, client):  # noqa: F811
        iid, _old, _other = T.busy()
        body = T.page(client, iid)
        assert len(evidence_homes(body)) == 1
        ev = body.split('id="inc-evidence"', 1)[1].split("</details>", 1)[0]
        assert ">core-a</a>" in ev and "is the far end of its link" in ev

    def test_the_scan_finds_a_second_home(self):
        planted = ('<div id="incident-live"><details><summary>Evidence (2)</summary></details>'
                   '<details class="card inc-evidence"><summary>Evidence</summary></details>')
        assert len(evidence_homes(planted)) == 2


# ── R2's leftovers (the operator, 2026-11-15) ────────────────────────────────────────────────
#: "no red "Check guards failed" or red "can't fix" chip for a decision working as designed;
#: drop "heal_analysis not run: feature_off" and "not diagnosed: no adjacency" noise from the
#: default view (details only)." (C3738, C3540)

def done_of(body: str) -> str:
    """What Mercury has done's card, as drawn."""
    return body.split('id="inc-done"', 1)[1].split("</section>", 1)[0]


def red_in(done: str) -> list:
    """What draws a decision red in What Mercury has done: a failed stage or step, a stage
    sentence announced as an alert, a danger chip."""
    return [m for m in ("run-stage-failed", "run-step-failed", 'role="alert"', "badge-danger")
            if m in done]


class TestADecisionWorkingAsDesignedIsNeverRed:
    def test_a_held_decision_s_stage_is_held_never_failed(self, client):  # noqa: F811
        done = done_of(T.page(client, held()))
        assert red_in(done) == [], red_in(done)
        assert "run-stage-held" in done and "run-step-held" in done
        assert "Held at " in done and "held by a guard, as designed" in done
        # Why it held is one level down, on its step's line, never lost.
        assert "intent" in T.text_of(done.split("run-step-held", 1)[1].split("</li>", 1)[0])

    def test_a_cant_fix_s_chip_is_neutral_with_its_decision_on_the_hover(self, client):  # noqa: F811
        body = T.page(client, T.cant_fix())
        c = chip(body)
        assert 'data-outcome-level="decision"' in c and "badge-neutral" in c, c
        assert "badge-danger" not in c and "A decision, not a failure" in c, c
        assert red_in(done_of(body)) == [], red_in(done_of(body))

    def test_the_check_finds_the_red_the_review_measured(self):
        """The floor: s1's What Mercury has done as the host drew it, 2026-11-15."""
        planted = ('<span class="badge badge-danger">Self-healing (dry run): can&#39;t fix</span>'
                   '<li class="run-stage run-stage-failed"><span class="run-stage-said" '
                   'role="alert">Check guards failed</span>')
        assert red_in(planted) == ["run-stage-failed", 'role="alert"', "badge-danger"]

    def test_the_standing_decision_is_drawn_never_an_earlier_one_s_hold(self):
        """An incident decided twice (held by a topology hold, then can't fix): its steps are
        the standing decision's; the earlier hold stays in The record."""
        from modules.heal import run_card

        def dec(did, guards):
            return [dict(s, row="decision", decision=did) for s in (
                {"step": "claim", "result": "ok"}, {"step": "stops", "result": "ok"},
                {"step": "approved", "result": "ok"}, {"step": "guards", "result": guards,
                                                       "words": f"guards {guards}"})]
        entry = {"incident": "hi-000000000001", "state": "decided", "outcome": "cant_fix",
                 "steps": dec("hd-1", "held") + [dict(step="record", result="ok", row="decision",
                                                      decision="hd-1")]
                 + dec("hd-2", "ok") + [dict(step="decide", result="cant_fix", row="decision",
                                             decision="hd-2", words="a person decides"),
                                        dict(step="record", result="ok", row="decision",
                                             decision="hd-2")]}
        card = run_card.steps_card("edge-b", entry)
        states = {s["key"]: s["state"] for s in card["rows"][0]["steps"]}
        assert states["d-guards"] == "done" and states["d-decide"] == "needs", states
        assert [g["state"] for g in card["stages"]] == ["needs"], card["stages"]


class TestNoiseIsOneLevelDown:
    def test_an_analysis_not_run_is_one_closed_line_never_the_ai_s_analysis(self, client):  # noqa: F811
        iid = T.cant_fix()
        words = ("AI analysis: not run: feature_off: the background feature heal_analysis is off "
                 "for the network default; nothing was sent")
        T.SL.record_advisory(NET, iid, device="edge-b", state="off", words=words, steps=[])
        ai = T.page(client, iid).split('id="inc-ai"', 1)[1].split("</section>", 1)[0]
        box = ai.split('id="inc-analysis"', 1)[1].split("</details>", 1)[0]
        summary = T.text_of(box.split("<summary>", 1)[1].split("</summary>", 1)[0])
        assert summary == "The AI's analysis · not run", summary
        assert "AI analysis (advisory" not in box, "a call not made is no analysis"
        line = box.split('data-advisory="not-run"', 1)[1].split("</p>", 1)[0]
        assert "feature_off" not in line.split(">", 1)[1], "the code is on the hover only"
        assert "feature_off" in unescape(line.split(">", 1)[0])
        assert "nothing was sent" in T.text_of(line)

    def test_a_diagnosis_not_made_is_closed_its_why_inside(self, client):  # noqa: F811
        from modules.heal import auto_diagnose
        iid = T.cant_fix()
        why = "not diagnosed: intent holds no adjacency on edge-b whose diagnosis can be planned"
        auto_diagnose._not_diagnosed(NET, {"device": "edge-b"}, iid, why, "refused", T0 + 10)
        done = done_of(T.page(client, iid))
        diag = done.split('id="inc-diag"', 1)[1].split("</div>", 1)[0]
        assert 'data-diagnosis="not"' in done, diag
        assert "warn-text" not in diag, "a diagnosis not made is not drawn as a warning"
        box = re.search(r'<details class="small inc-diag-not"[^>]*>(.*?)</details>', diag, re.S)
        assert box and "open" not in diag.split("inc-diag-not", 1)[1].split(">", 1)[0], diag
        assert "no adjacency" in box.group(1) and "no adjacency" not in diag.replace(
            box.group(0), ""), "its why is inside the closed line, nowhere else"
