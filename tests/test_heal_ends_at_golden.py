"""A read at a golden that departs from intent proves nothing (the correctness review's G4-D3
and D6, C3966; `modules/heal/triggers.py` `clean_ended`, `modules/heal/act.py`
`golden_not_proof`, `modules/heal/decide.py`).

Since C3909 a golden departing from its committed intent holds nothing, and since C3910 (the
operator, 2026-11-17: "decide a restore to intent (same render), never 'nothing to heal'")
the decision restores the device to intent, every line judged by its kind (premise corrected
2026-11-18: these tests had pinned the interim can't-fix). A drift run that then reads the
device at that golden reads it at a state that is not its intent, so it ends nothing, as
Mercury's confirmation read already judges it ("a read at it proves nothing"); and a decision
for such a golden never says the golden matches its intent, nor "nothing to heal".

No device, no network, a fake clock; the decision's sources are tests/test_heal_decide.py's
`Fake`, the fold's world tests/test_heal_triggers.py's.
"""
from tests.test_heal_decide import DC, GOLDEN, ROUTE6, settle
from tests.test_heal_decide import Fake, lab  # noqa: F401 (the fixture `fold` builds on)
from tests.test_heal_policy import T0
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
    assert d["outcome"] == "would_heal", d       # a restore to intent, in dry run (C3910)
    s = the("core-b")["standing"]
    assert (s["on"], s["guard"]) == ("departure", None) and s["departure"]
    golden_now(monkeypatch, "departs")
    got = _clean_read(T0 + 3600)
    assert got.get("ended", []) == [], got
    inc = the("core-b")
    assert inc["state"] == "standing" and inc["standing"]["decision"] == d["decision"]


def test_an_at_golden_decision_says_a_departing_golden_departs(lab):  # noqa: F811
    # The golden departs from intent by lacking a line intent holds (the fake's intent once
    # equalled its golden while saying "departs", a state no real golden has).
    inc = settle(GOLDEN, how="at_golden")
    d = DC.decide_one("Default", inc, now=T0, sources=Fake(GOLDEN, intended=GOLDEN + ROUTE6,
                                                            state="departs"))
    assert d["outcome"] == "would_heal", d
    assert "matches its intent" not in d["words"], d["words"]
    assert "nothing to heal" not in d["words"], d["words"]
