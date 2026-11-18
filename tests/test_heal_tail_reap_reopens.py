"""A heal closed at Fixed whose tail a restart cut short is reopened (the correctness review's
G4-D2; the operator, 2026-11-16: "A failed save/golden tail step reopens the incident";
`modules/heal/act.py` `reap_tails`, `reopen_on_tail`).

At Fixed the act closes its incident and runs the save, the full read, the golden and the
read again as its tail. When the process ends during the tail, the next pass's `reap_tails`
flags the tail as not finished. The incident must then stand again on ``tail_failed``, as a
tail that fails in the running job leaves it, so R1 sees it (`fixit.auto.failures` reads open
incidents only): a fix never saved is not shown as Fixed.

No device, no network; the decision's sources are tests/test_heal_decide.py's `Fake`.
"""
import time

from tests.test_heal_decide import DC, GOLDEN, I, ROUTE4, Fake, lab, settle  # noqa: F401
from tests.test_heal_policy import T0, auto
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

NET = "Default"
RUNNING = GOLDEN + ROUTE4


def _healed_at_fixed():
    """edge-b's heal, decided in Auto, taken, applied healed and its incident closed at Fixed
    with its proof, and the first ``act`` row written with the tail ``running`` (as the act's
    `declare` leaves them), its tail begun past its bound."""
    from modules.heal import act, decisions, steplog

    auto(NET, now=T0 - 60, kinds=("added_line",))
    inc = settle(RUNNING, device="edge-b")
    made = DC.decide_one(NET, inc, now=T0, sources=Fake(RUNNING))
    made.pop("steps", None), made.pop("phase", None)
    d = decisions.record(NET, made, T0)
    assert d["outcome"] == "heal", d["words"]
    DC._act(NET, inc, d, T0)
    decisions.take(NET, d["id"], by="the act", now=T0)
    decisions.applied(NET, d["id"], "healed", by="the act", words="verified", now=T0)
    assert act.outcome_on_incident(NET, d, "healed", "verified",
                                   fixed=act.verified_of(d, [])) == "closed"
    tail = dict(act.tail_of("edge-b", "healed", [], [], running=True),
                began=time.time() - act.tail_bound() - 60)
    steplog.record_act(NET, d, {"outcome": "healed", "words": "verified", "steps": [],
                                "sent": True, "records": {"tail": tail}}, by="the act",
                       now=time.time())
    return inc["id"], d


def _of(inc_id):
    return next(i for i in I.read(NET)["incidents"] if i["id"] == inc_id)


def test_reaped_tail_reopens_incident(lab):  # noqa: F811
    from modules.fixit import auto as R1
    from modules.heal import act

    inc_id, d = _healed_at_fixed()
    assert _of(inc_id)["state"] == "closed" and _of(inc_id)["fixed"]["act"] == d["id"]
    assert act.reap_tails(NET) == [d["id"]]
    inc = _of(inc_id)
    assert inc["state"] == "standing", inc.get("closed_why")
    assert inc["standing"]["outcome"] == act.TAIL_FAILED and inc["standing"]["act"] is True
    assert "did not finish" in inc["standing"]["words"], inc["standing"]["words"]
    keys = [f["key"] for f in R1.failures(NET, open_ids={inc_id})["failures"]]
    assert any(k.startswith("tail:") for k in keys), keys
