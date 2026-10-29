"""Mercury's needs_human on Explain's "no fault found" (the operator's order of 2026-10-29,
C2141): modules/ai/explain.py (`fault_shown`, `needs_human_guard`, `explain_pack`),
modules/ai/cases.py (`guarded`, `confidently_wrong_candidate`, `explain_graded`),
templates/v2/_explain.html.

**Why:** recorded case 19 (s4's heartbeat alert, its cause its slow clock) was answered "no
fault found" with needs_human false in 9 of 10 v4 runs and 8 of 10 v8 runs of the confirmation
round, 3.8% of v8's runs confidently wrong against 15.12's 1%: the alert was firing, and the
answer told no one to look.

**The rule as built:** the pack's alert section was read (state ok), its piece's kind is
``condition`` (Grafana's Alerting or firing, the reader's `_kind`; never no data, error,
pending or normal) and its state no word of `explain.NOT_FIRING` begins, and the pack records
no resolve at or before its own time (``resolved_at`` against ``built_at``). Then a shown
answer of no fault found with needs_human false is kept with needs_human true, Mercury's
change recorded apart (``mercury_needs_human``: its reason), the
model's response untouched in the call's record, and drawn under "set by Mercury".

On tests/test_ai_explain.py's world (r1's pack built by the real builder, firing) and the
captured Walk 2 pack (tests/fixtures/evidence_pack/walk2_r1_pack.json), and over every
recorded run of tests/fixtures/ai_cases/explain/recorded.json.
"""
import copy
import json
import os
import re
from html import unescape

import pytest

from modules.ai import calls, cases, explain, explain_answers
from tests.test_ai_explain import _answer, _explain, world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "tests", "fixtures", "evidence_pack", "walk2_r1_pack.json"),
          encoding="utf-8") as _fh:
    WALK = json.load(_fh)
with open(os.path.join(ROOT, "tests", "fixtures", "ai_cases", "explain", "recorded.json"),
          encoding="utf-8") as _fh:
    RECORDED = json.load(_fh)


def _alert(pack):
    return next(s for s in pack["sections"] if s["name"] == "alert")


def _with(pack, **piece):
    p = copy.deepcopy(pack)
    _alert(p)["pieces"][0].update(piece)
    return p


# ── the rule ──────────────────────────────────────────────────────────────────────────────

def test_a_firing_alert_shows_the_fault_naming_its_source_state_and_time():
    why = explain.fault_shown(WALK)
    assert why == ("the alert's own source (Grafana's alert state, as the grafana-alerts reader "
                   "stored it) holds it firing (Alerting) at the alert's time "
                   "2026-10-22T18:01:50Z")


@pytest.mark.parametrize("change", [
    {"kind": "no_data"}, {"kind": "error"}, {"kind": "pending"}, {"state": "Normal"},
    {"state": "Normal (NoData)"}, {"state": "resolved"}, {"kind": ""}])
def test_an_alert_not_firing_shows_none(change):
    assert explain.fault_shown(_with(WALK, **change)) == ""


def test_a_resolve_at_or_before_the_pack_s_time_shows_none_and_after_it_still_shows():
    """The Walk 2 pack was resolved at 18:05:50, four minutes after its time: still firing
    then. Resolved at or before its time, it was not."""
    assert WALK["resolved_at"] == "2026-10-22T18:05:50Z"
    assert explain.fault_shown(WALK)
    for at in ("2026-10-22T18:01:50Z", "2026-10-22T17:59:00Z"):
        assert explain.fault_shown(dict(WALK, resolved_at=at)) == "", at


def test_an_alert_section_not_read_shows_none():
    p = copy.deepcopy(WALK)
    _alert(p)["state"] = "unreadable"
    assert explain.fault_shown(p) == ""
    p["sections"] = [s for s in p["sections"] if s["name"] != "alert"]
    assert explain.fault_shown(p) == ""


@pytest.mark.parametrize("outcome,needs,applies", [
    ("no_fault_found", False, True), ("no_fault_found", True, False),
    ("answer", False, False), ("refuse", False, False)])
def test_only_no_fault_found_without_a_person_is_guarded(outcome, needs, applies):
    got = explain.needs_human_guard(outcome, needs, WALK)
    assert bool(got) is applies
    if applies:
        assert set(got) == {"reason"}
        assert got["reason"].startswith("The model found no fault and did not ask for a "
                                        "person, but the alert's own source")


# ── through Explain and the card ──────────────────────────────────────────────────────────

def _no_fault(pack, needs_human=False):
    logs = next(s for s in pack["sections"] if s["name"] == "logs")
    return _answer(pack, outcome="no_fault_found", hypotheses=[], needs_human=needs_human,
                   rationale="r1's log lines show nothing wrong.",
                   checked=[p["ref"] for p in logs["pieces"][:2]])


def test_the_guard_sets_needs_human_kept_and_recorded_as_mercury_s(world, monkeypatch):  # noqa: F811
    used = []
    real = calls.record_use

    def record(cid, use, **kw):
        used.append((use, kw))
        return real(cid, use, **kw)
    monkeypatch.setattr(calls, "record_use", record)
    assert explain.fault_shown(world.pack), "the world's alert is firing"
    world.answer = _no_fault(world.pack)
    got = _explain(world)
    assert got["ok"] is True, got
    shown = got["answer"]
    assert shown["outcome"] == "no_fault_found" and shown["needs_human"] is True
    assert shown["mercury_needs_human"] == explain.needs_human_guard(
        "no_fault_found", False, world.pack)
    # The use's record says what Mercury set; the call's record keeps the model's answer.
    assert used[-1][0] == "shown: no fault found"
    assert "needs a person, set by Mercury: The model found no fault" in used[-1][1]["detail"]
    row = next(r for r in calls.read()["rows"] if r.get("id") == got["call_id"])
    assert json.loads(row["response"])["needs_human"] is False


def test_an_answer_that_asked_for_a_person_or_named_a_cause_is_unchanged(world):  # noqa: F811
    world.answer = _no_fault(world.pack, needs_human=True)
    got = _explain(world)
    assert got["answer"]["needs_human"] is True and got["answer"]["mercury_needs_human"] == {}
    world.answer = _answer(world.pack)
    got = _explain(world)
    assert got["answer"]["needs_human"] is False and got["answer"]["mercury_needs_human"] == {}


def test_a_resolved_alert_s_no_fault_found_is_unchanged(world, monkeypatch):  # noqa: F811
    from modules import evidence_pack as EP
    pack = dict(world.pack, resolved_at=world.pack["built_at"])
    pack.pop("hash")
    pack["hash"] = EP.digest(pack)
    world.answer = _no_fault(pack)
    from modules.ai import triggers
    from tests.ai_person import pressed_by
    with pressed_by("operator@example.com"):
        got = explain.explain_pack(pack, actor="operator@example.com",
                                   trigger=triggers.person("operator@example.com"),
                                   send=world.send, today="2026-10-25")
    assert got["ok"] is True, got
    assert got["answer"]["needs_human"] is False and got["answer"]["mercury_needs_human"] == {}


def test_the_card_draws_set_by_mercury_with_its_reason(world):  # noqa: F811
    world.answer = _no_fault(world.pack)
    r = world.lab["client"].post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
                                 headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and "no fault found" in html
    # The answer card's Needs a person (board AlertsExplain revised 2026-10-29).
    mine = re.search(r'<p class="[^"]*\bexplain-mercury-needs-human\b[^"]*".*?</p>', html, re.S)
    assert mine, html
    assert "needs a person" in mine.group(0) and "set by Mercury" in mine.group(0)
    assert "The model found no fault and did not ask for a person" in mine.group(0)
    assert "Mercury set this" in mine.group(0)
    assert "Something in the pack could not be read." not in html
    # Kept with the pack as drawn (C1853): Mercury's change with it.
    kept = explain_answers.kept(world.pack)["answer"]["result"]["answer"]
    assert kept["needs_human"] is True
    assert kept["mercury_needs_human"]["reason"].startswith("The model found no fault")


def test_the_card_says_something_could_not_be_read_when_the_model_asked(world):  # noqa: F811
    world.answer = _no_fault(world.pack, needs_human=True)
    r = world.lab["client"].post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
                                 headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert "Something in the pack could not be read." in html
    assert "explain-mercury-needs-human" not in html


# ── the grader, both ways ─────────────────────────────────────────────────────────────────

CASE_19 = next(c for c in RECORDED["cases"] if c["n"] == 19)


def _recorded_answer(a):
    """A recorded run's answer as `explain_misses` reads it: each hypothesis its references
    (the recording keeps the structured answer, not the prose)."""
    return {"outcome": a["outcome"], "needs_human": a["needs_human"],
            "checked": list(a.get("checked") or []), "rationale": "", "why_not": "",
            "hypotheses": [{"claim": "", "confirm_with": "", "evidence_refs": list(e)}
                           for e in a.get("evidence") or []]}


def test_case_19_s_no_fault_found_is_confidently_wrong_raw_and_not_guarded():
    raw = _recorded_answer(CASE_19["recorded"]["runs"][0]["answer"])
    assert raw["outcome"] == "no_fault_found" and raw["needs_human"] is False
    got = cases.explain_graded(CASE_19["expect"], raw, WALK)
    assert got["raw"]["misses"] == got["guarded"]["misses"] == [
        "outcome no_fault_found, expected one of ['answer']"]
    assert got["raw"]["confidently_wrong_candidate"] is True
    assert got["guarded"]["confidently_wrong_candidate"] is False
    assert got["guarded"]["set_by_mercury"].startswith("The model found no fault")
    assert raw["needs_human"] is False, "the raw answer is never changed"


def test_the_guarded_answer_is_the_raw_one_where_the_guard_does_not_apply():
    raw = {"outcome": "no_fault_found", "needs_human": False, "hypotheses": [], "checked": []}
    assert cases.guarded(raw, _with(WALK, kind="no_data")) is raw
    assert cases.guarded(None, WALK) is None
    assert cases.explain_graded({"outcome": ["answer"]}, None, WALK, "couldnt_analyse")[
        "guarded"] == {"misses": ["no answer: couldnt_analyse"], "pass": False,
                       "confidently_wrong_candidate": False, "set_by_mercury": "",
                       "who_by_mercury": []}


#: The recorded runs the guard changes: every no fault found with needs_human false, each on a
#: firing alert (every case's pack is a replay's synthesized firing alert or Walk 2's, rebuilt
#: firing): the seven healthy baselines' five runs each, and case 19's runs 1, 3, 4 and 5.
CHANGED = {**{(n, r): True for n in (2, 3, 4, 16, 17, 18, 20) for r in range(1, 6)},
           **{(19, r): True for r in (1, 3, 4, 5)}}


def test_the_recorded_answers_the_guard_changes_and_no_verdict_it_moves():
    """Over every recorded run, graded raw and guarded on one firing pack: the guard changes
    exactly `CHANGED`'s 39 runs, and no run's misses differ between the two (no expectation
    those runs reach reads needs_human: the baselines' expect none, and case 19's outcome
    fails first), while case 19's four leave the confidently wrong candidates."""
    changed, moved, left = [], [], []
    for c in RECORDED["cases"]:
        for run in (c.get("recorded") or {}).get("runs") or []:
            raw = _recorded_answer(run["answer"])
            got = cases.explain_graded(c["expect"], raw, WALK)
            if got["guarded"]["set_by_mercury"]:
                changed.append((c["n"], run["round"]))
            if got["raw"]["misses"] != got["guarded"]["misses"]:
                moved.append((c["n"], run["round"]))
            # The recording's own misses (its pack's), which the line above shows the guard
            # leaves as they are: a candidate raw that is none guarded.
            if cases.confidently_wrong_candidate(run["misses"], raw) and not \
                    cases.confidently_wrong_candidate(run["misses"], cases.guarded(raw, WALK)):
                left.append((c["n"], run["round"]))
    assert len(changed) >= 39, "the floor: the recording's 39"
    assert sorted(changed) == sorted(CHANGED)
    assert moved == []
    assert left == [(19, 1), (19, 3), (19, 4), (19, 5)]
