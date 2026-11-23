"""A read at a golden that departs from intent proves nothing (the correctness review's G4-D3
and D6, C3966; `modules/heal/triggers.py` `clean_ended`, `modules/heal/act.py`
`golden_not_proof`, `modules/heal/decide.py`).

Since C3909 a golden departing from its committed intent holds nothing: the decision stands
the incident on a can't-fix ("the golden departs from its committed intent ... the AI
investigates"). A drift run that then reads the device at that golden reads it at a state
that is not its intent, so it ends nothing, as Mercury's confirmation read already judges it
("a read at it proves nothing"); and a decision settled at such a golden never says the
golden matches its intent.

No device, no network, a fake clock; the decision's sources are tests/test_heal_decide.py's
`Fake`, the fold's world tests/test_heal_triggers.py's.
"""
import pytest

from tests.test_heal_decide import DC, DS, GOLDEN, I, settle
from tests.test_heal_decide import Fake, lab  # noqa: F401 (the fixture `fold` builds on)
from tests.test_heal_policy import T0, iso
from tests.test_heal_standing import R8, change, decide, fold, golden_now, the  # noqa: F401
from tests.test_heal_triggers import T
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)


def _clean_read(at):
    return T.after_drift_record("Default", {"triggered_by": "scheduled", "drifted_devices": [],
                                            "clean_devices": [{"hostname": "core-b",
                                                               "read_at": at}]}, now=at + 1)


def test_departing_golden_cant_fix_not_ended_by_clean_read(fold, monkeypatch):  # noqa: F811
    change("core-b", T0)
    d = decide("core-b", R8, T0 + 150, state="departs")
    assert d["outcome"] == "cant_fix", d
    s = the("core-b")["standing"]
    assert (s["on"], s["guard"]) == ("departure", None) and s["departure"]
    golden_now(monkeypatch, "departs")
    got = _clean_read(T0 + 3600)
    assert got.get("ended", []) == [], got
    inc = the("core-b")
    assert inc["state"] == "standing" and inc["standing"]["decision"] == d["decision"]


def test_an_at_golden_decision_says_a_departing_golden_departs(lab):  # noqa: F811
    inc = settle(GOLDEN, how="at_golden")
    d = DC.decide_one("Default", inc, now=T0, sources=Fake(GOLDEN, state="departs"))
    # C3910, the operator's ruling 0 (2026-11-18): a departing golden is a Tier 3 can't-fix,
    # never "nothing to heal" (`test_at_a_departing_golden_with_no_symptom_...` below).
    assert d["outcome"] == "cant_fix", d
    assert "matches its intent" not in d["words"], d["words"]
    assert "departs from its intent" in d["words"], d["words"]


@pytest.mark.parametrize("state", ["departs", "unknown"])
def test_at_a_departing_golden_with_no_symptom_is_a_tier_3_cant_fix_never_closed(
        lab, state):  # noqa: F811
    """C3910 (the operator, 2026-11-17: "a device at a golden that departs from intent is a
    departure ... never 'nothing to heal'"; the operator's ruling 0, 2026-11-18: "Keep the
    interim (c)", a departing golden is a Tier 3 can't-fix and the AI investigates): an
    incident settled at its golden, that golden departing from committed intent (or its
    intent state unknown: no read at it proves the approved state, `act.golden_not_proof`),
    no symptom, is decided a can't-fix of Tier 3 naming the departure, as the departing golden
    with a departure is, and stays open on it: never closed as nothing to heal. Nothing is
    restored (the restore to intent is C4093's build)."""
    settle(GOLDEN, how="at_golden", claim=False)
    (ran,) = DC.run("Default", now=T0, sources=Fake(GOLDEN, state=state))["decided"]
    d = DS.find("Default", ran["decision"])
    assert (d["outcome"], d["tier"], d["guard"], d["program"]) == ("cant_fix", 3, None, []), d
    assert "nothing to heal" not in d["words"], d["words"]
    assert "departs from its intent" in d["words"], d["words"]
    assert "the AI investigates" in d["words"], d["words"]
    (inc,) = [i for i in I.read("Default")["incidents"] if i["id"] == d["incident"]]
    assert inc["state"] == "standing", inc
    assert inc["standing"]["outcome"] == "cant_fix", inc["standing"]


def test_at_a_departing_golden_a_symptom_cleared_by_itself_is_still_a_cant_fix(lab):  # noqa: F811
    """C3910's same branch: every symptom read gone leaves the device at a golden that departs
    from intent, which is a departure, so the decision is the interim's can't-fix, never
    "nothing to heal: every symptom ... has cleared by itself". At a golden AT its intent the
    same read is nothing to heal (tests/test_heal_decide.py's
    `test_a_symptom_that_cleared_by_itself_is_nothing_to_heal`)."""
    trig = [{"kind": "adjacency", "key": "adj:1", "epoch": T0 - 900, "at": iso(T0 - 900),
             "source": "adjacencies", "words": "the adjacency is down"}]
    src = Fake(GOLDEN, state="departs")
    src.symptom_now = lambda device, triggers: "gone"
    inc = settle(GOLDEN, how="at_golden", triggers=trig)
    d = DC.decide_one("Default", inc, now=T0, sources=src)
    assert (d["outcome"], d["tier"]) == ("cant_fix", 3), d
    assert "nothing to heal" not in d["words"], d["words"]
    assert "departs from its intent" in d["words"], d["words"]


@pytest.mark.parametrize("state", ["departs", "unknown"])
@pytest.mark.parametrize("symptom", [True, False], ids=("link down", "no symptom"))
def test_a_departure_that_leaves_no_unit_at_a_departing_golden_is_a_cant_fix(
        lab, state, symptom):  # noqa: F811
    """The correctness review's MEDIUM-C (review-devicewrite-fixes-2.md), as it holds on this
    code: an incident settled on a departure (not at its golden), read at the decision with no
    unit Mercury would restore, its golden departing from intent (or unknown), was "nothing to
    heal: what departed is not from the approved state" and closed, with its link still down.
    It is the interim's can't-fix (ruling 0), as the same golden with a unit is
    (tests/test_heal_decide.py's `test_4_a_golden_that_departs_from_intent_n5`)."""
    trig = ([{"kind": "adjacency", "key": "adj:1", "epoch": T0 - 900, "at": iso(T0 - 900),
              "source": "adjacencies", "interface": "Gi0/1", "words": "Interface down"}]
            if symptom else None)
    src = Fake(GOLDEN, state=state)
    src.symptom_now = lambda device, triggers: "present"
    inc = settle(GOLDEN, how="persisted", triggers=trig)
    d = DC.decide_one("Default", inc, now=T0, sources=src)
    assert (d["outcome"], d["tier"], d["program"]) == ("cant_fix", 3, []), d
    assert "golden departs from its committed intent" in d["words"], d["words"]
    assert "nothing to heal" not in d["words"], d["words"]
