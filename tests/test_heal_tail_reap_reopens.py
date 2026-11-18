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


def test_a_tail_failure_on_a_device_in_another_open_incident_attaches_to_it(  # noqa: F811
        lab, monkeypatch):
    """Ruling 17 (the operator, 2026-11-18: "A tail failure on a device already in an open
    incident attaches to that incident"; the correctness review's G4-D7): `incidents.reopen`
    refused when the device was in another open incident (one open incident per device), and
    `reopen_on_tail` logged the refusal and returned, so the failure was only a flag: the
    closed incident stayed Fixed and R1 never saw the tail, its incident not open. It is kept
    on the open incident now, once, and R1's one reader lists it there as the tail failure it
    is."""
    from modules.fixit import auto as R1
    from modules.heal import act
    from tests.test_incident_page import CFG

    inc_id, d = _healed_at_fixed()
    other = I.sight(NET, "edge-b", dict(CFG, key="cfg:2", epoch=T0 + 30), now=T0 + 30)
    other_id = other["incident"]
    assert other_id != inc_id and _of(other_id)["state"] in R1.OPEN, _of(other_id)
    assert act.reap_tails(NET) == [d["id"]]
    assert act.reopen_on_tail(NET, d, {"state": "flagged", "flag": "again"}) == \
        f"attached to {other_id}"
    assert _of(inc_id)["state"] == "closed", "one open incident per device"
    tails = _of(other_id)["tails"]
    assert [(t["incident"], t["decision"]) for t in tails] == [(inc_id, d["id"])], tails
    assert "did not finish" in tails[0]["words"], tails
    got = R1.attached_tail_failures(_of(other_id))
    assert [(f["key"], f["kind"], f["incident"], f["outcome"]) for f in got] == [
        (R1.key_of("tail", d["id"]), "tail", other_id, act.TAIL_FAILED)], got
    # R1's one reader (`pending`), its page and troubleshooting reads stood in (this lab's
    # sighted incident has no device identity, so no troubleshooting record).
    from modules.fixit import incident as F
    monkeypatch.setattr("modules.incident_page.resolve", lambda network, iid: {
        "found": "page", "id": iid, "incident": _of(iid)})
    monkeypatch.setattr("modules.fixit.section.incident_of", lambda network, found: {
        "incident": F.Incident(NET, found["id"], "uid:edge-b", "edge-b", T0), "why": ""})
    monkeypatch.setattr(R1, "plan_failures", lambda network, inc: [])
    monkeypatch.setattr(R1, "capability_failures", lambda network, inc: [])
    pend = {i["id"]: i for i in R1.pending(NET)["incidents"]}
    assert [f["key"] for f in pend[other_id]["failures"]] == [R1.key_of("tail", d["id"])], pend


def _attached(monkeypatch):
    """`_healed_at_fixed`'s tail reaped while a second incident stands open on edge-b, so the
    failure is attached to it; its page and troubleshooting record stood in (this lab's
    sighted incident has no device identity). ``(closed id, decision, open id, record)``."""
    from modules.fixit import incident as F
    from modules.heal import act
    from tests.test_incident_page import CFG

    inc_id, d = _healed_at_fixed()
    other_id = I.sight(NET, "edge-b", dict(CFG, key="cfg:2", epoch=T0 + 30),
                       now=T0 + 30)["incident"]
    assert act.reap_tails(NET) == [d["id"]]
    assert _of(inc_id)["tail_attached"]["to"] == other_id, _of(inc_id)
    rec = F.Incident(NET, other_id, "uid:edge-b", "edge-b", T0)
    monkeypatch.setattr("modules.incident_page.resolve", lambda network, iid: {
        "found": "page", "id": iid, "incident": _of(iid)})
    monkeypatch.setattr("modules.fixit.section.incident_of", lambda network, found: {
        "incident": rec, "why": ""})
    return inc_id, d, other_id, rec


def test_r1_asks_the_ai_on_a_tail_failure_attached_to_an_open_incident(  # noqa: F811
        lab, monkeypatch):
    """Ruling 17 end to end (the device-write review of 67a1ce29, 3-A; C4110): R1's start on
    the attached ``tail:<decision>`` key is investigated on the open incident. Confirm-first
    (`act.confirm_before_ai`) resolved the decision's OWN incident, closed and healed, and said
    ``closed_already``: `_investigation` wrote a ``closed`` start line on the OPEN incident
    with the other incident's "healed" words, never asked the AI, spent the key, and so hid
    the open incident's Start. The AI is asked now, and no ``closed`` line is written."""
    from modules import heal_notice
    from modules.fixit import auto as R1
    from modules.fixit import incident as F

    inc_id, d, other_id, rec = _attached(monkeypatch)
    key = R1.key_of("tail", d["id"])
    asked = []

    def ask(found, inc):
        asked.append(found["id"])
        return {"state": "answered"}
    got = heal_notice._investigation(NET, other_id, key, ask, deliver=None, trigger="auto",
                                     scripts=False)
    assert asked == [other_id] and got == {"state": "answered"}, got
    closed = [ln for ln in F.read(rec)["lines"] if ln.get("state") == "closed"]
    assert closed == [], closed
    assert _of(inc_id)["state"] == "closed" and _of(other_id)["state"] in R1.OPEN
