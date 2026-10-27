"""SDN responses' modes and the closed loop (`modules/sdn/modes.py`, `modules/sdn/loop.py`;
PHASE8_PLAN 17.1 S9 and S10, 17.4), no network, a fake clock.

- **HITL is the default**; an unreadable mode record reads HITL, never AUTO.
- **AUTO** is turned on only by a verified person, with a reason, an expiry no more than a day
  away and a known risk class; it allows only catalogue actions within its class; at its expiry
  the mode is HITL again and the record says so once; off is one action.
- **The loop's pass**: detect; classify is a background AI call the gateway refuses while hosted
  AI or the feature is off (the default), so no provider request is made and the catalogue's
  default is proposed, chosen in code (tests/test_sdn_classify.py: the feature on); in HITL
  each new detection is kept awaiting a person (one per detection), still awaiting when its
  detection resolves, marked no longer active (C1968; tests/test_sdn_loop_live.py holds the
  rest); in AUTO an action of a classification that passed, within the risk class, is applied
  through the flow-operation core as Mercury, recorded autonomous with the setting and its
  reason; one above it stays HITL.
- **The job**: one loop per network; a second start refused naming the first; stop recorded.
"""
import time

import pytest

from modules.sdn import closed_loop as CL
from modules.sdn import flow_intent as F
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

NET = "Default"
T0 = 1_790_000_000.0


def test_hitl_is_the_default_and_an_unreadable_record_is_never_auto(networks):  # noqa: F811
    assert MD.current(NET, T0)["mode"] == "hitl"
    path = MD._path(NET)
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{"kind": "on", "until_epoch": 9e18\n')
    got = MD.current(NET, T0)
    assert got["mode"] == "hitl" and got["state"] == "unreadable"
    assert "no response runs unattended" in got["words"]
    assert MD.decide(NET, "low", T0)["auto"] is False


@pytest.mark.parametrize("kw,words", [
    ({"actor": "", "actor_verified": "access"}, "by a verified person"),
    ({"actor_verified": "none"}, "by a verified person"),
    ({"reason": " "}, "with a recorded reason"),
    ({"until": T0 - 1}, "expiry is in the future"),
    ({"until": T0 + 25 * 3600}, "at most 24 hours"),
    ({"allowed_risk": "high"}, "the allowed risk is low or medium"),
])
def test_auto_is_refused_without_its_person_reason_and_expiry(networks, kw, words):  # noqa: F811
    args = dict(actor="admin@example.com", actor_verified="access", reason="the lab's run",
                until=T0 + 3600, allowed_risk="low", now=T0)
    args.update(kw)
    with pytest.raises(MD.ModeRefused, match=words):
        MD.turn_on(NET, **args)
    assert MD.current(NET, T0)["mode"] == "hitl"


def test_auto_allows_only_its_risk_class_and_expires_to_hitl_once(networks):  # noqa: F811
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=T0 + 600, allowed_risk="low", now=T0)
    on = MD.decide(NET, "low", T0 + 1)
    assert on["auto"] and on["autonomous"]["reason"] == "lab 8 run"
    assert on["autonomous"]["by"] == "admin@example.com"
    assert MD.decide(NET, "medium", T0 + 1)["auto"] is False
    assert "its risk is medium, and AUTO allows low" in MD.decide(NET, "medium", T0 + 1)["words"]
    assert MD.current(NET, T0 + 600)["mode"] == "hitl"
    assert MD.record_expiry(NET, T0 + 601)["recorded"] is True
    kinds = [r["kind"] for r in MD.history(NET)["rows"]]
    assert kinds == ["on", "expired"]
    assert MD.record_expiry(NET, T0 + 700)["recorded"] is False


def test_off_is_one_action_at_once(networks):  # noqa: F811
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="r",
               until=T0 + 600, now=T0)
    MD.turn_off(NET, actor="admin@example.com", now=T0 + 5)
    assert MD.current(NET, T0 + 6)["mode"] == "hitl"
    with pytest.raises(MD.ModeRefused, match="AUTO is not on"):
        MD.turn_off(NET, actor="admin@example.com", now=T0 + 7)


def test_classify_refuses_and_makes_no_call(networks, monkeypatch, tmp_path):  # noqa: F811
    """The loop's classify is a background call (C1843 live): with hosted AI off, the default,
    the gateway refuses it before anything is read or sent, and records the refusal under the
    loop's job; no provider request is made (tests/test_sdn_classify.py holds the rest)."""
    from modules.ai import calls, triggers
    from tests.test_sdn_classify import SCAN, detection_of, keep_pack
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    keep_pack(SCAN)
    d = detection_of(SCAN)
    t = triggers.background("sdn_classify", "sdn-loop-default", "default", "detection", d["key"])
    got = CL.classify_threat(NET, d, actor=triggers.actor_of(t), trigger=t,
                             send=lambda body, key: pytest.fail("a provider request was made"))
    assert (got["ok"], got["error"]) == (False, "ai_off")
    (row,) = calls.read()["rows"]
    assert row["verdict"] == "ai_off" and row["trigger"]["kind"] == "background"
    assert row["actor"] == "job:sdn-loop-default"


# ───────────────────────────────────────────────────────────────────────────── the pass

def detection(key="k1", rule="scan"):
    return {"key": key, "rule": rule, "title": "SDN scan", "network": NET, "connection": "lab",
            "dpid": 1, "dpid_hex": "0000000000000001", "source": "192.0.2.1",
            "targets": ["192.0.2.3"], "words": "192.0.2.1 reached 25 ports", "subject":
            {"kind": "source", "value": "192.0.2.1"}}


def observed(fired=(), resolved=(), detections=None):
    return lambda network, collected: {
        "ok": True, "fired": list(fired), "resolved": list(resolved),
        "detections": detections if detections is not None else [detection()]}


def collected():
    return {"network": NET, "summary": {"switches": 2, "flows": 9}, "state": "ok"}


def test_a_pass_in_hitl_keeps_one_response_awaiting_a_person(networks, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr(CL, "respond_to_threat", lambda *a, **k: calls.append(a) or {})
    out = LP.run_pass(NET, collect=collected, observe=observed(fired=["k1"]),
                      now=lambda: T0, driver=lambda n, c: {"ok": False, "error": "unused"})
    assert out["ok"] and out["proposed"] and calls == []
    (row,) = LP.awaiting(NET)["rows"]
    assert row["action"] == "drop_source" and row["risk"] == "low"
    steps = [line["step"] for line in out["lines"]]
    assert steps == ["read", "detect", "classify", "respond"]
    assert "no AI classification" in out["lines"][2]["words"]
    assert "chosen in code" in out["lines"][2]["words"]
    LP.run_pass(NET, collect=collected, observe=observed(fired=["k1"]), now=lambda: T0 + 10,
                driver=lambda n, c: {"ok": False, "error": "unused"})
    assert len(LP.awaiting(NET)["rows"]) == 1
    LP.run_pass(NET, collect=collected, observe=observed(resolved=["k1"], detections=[]),
                now=lambda: T0 + 20, driver=lambda n, c: {"ok": False, "error": "unused"})
    (row,) = LP.awaiting(NET)["rows"]
    assert row["inactive_since"] == LP._iso(T0 + 20), "it awaits a person, no longer active"


def test_a_pass_in_auto_applies_within_its_risk_as_mercury_autonomous(networks,  # noqa: F811
                                                                      monkeypatch):
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=time.time() + 600, allowed_risk="low")
    seen = []

    def respond(network, d, action, params=None, *, confirm=None, **kw):
        seen.append((action, confirm is not None, kw.get("mode"), kw.get("autonomous"),
                     kw.get("actor")))
        if confirm is None:
            return {"ok": True, "ask": {"a": 1}, "plan": {"hash": "h"}}
        return {"id": "sdnop-1", "outcome": "verified"}

    monkeypatch.setattr(CL, "respond_to_threat", respond)

    def passed(network, d, job, **kw):
        """A classification that passed the check, proposing the rule's catalogue default
        (C1968: AUTO acts only on one that passed; tests/test_sdn_loop_live.py, none)."""
        action = CL.DEFAULT_ACTION[d["rule"]]
        return {"action": action, "risk": CL.CATALOGUE[action]["risk"], "params": {},
                "classification": {"threat_type": "planted"}, "person": False, "why": "",
                "refused_call": "", "words": "planted: passed"}
    monkeypatch.setattr(LP, "classify", passed)
    out = LP.run_pass(NET, collect=collected, observe=observed(fired=["k1", "k2"], detections=[
        detection("k1", "scan"), detection("k2", "unauthorised_flow")]),
        driver=lambda n, c: {"ok": False, "error": "unused"})
    assert out["applied"] == [{"id": "sdnop-1", "outcome": "verified"}]
    (_p, (action, confirmed, mode, auto, actor)) = seen
    assert (action, confirmed, mode, actor) == ("drop_source", True, "auto", "Mercury (AUTO)")
    assert auto["reason"] == "lab 8 run" and auto["by"] == "admin@example.com"
    (row,) = LP.awaiting(NET)["rows"]
    assert row["action"] == "remove_flow" and "its risk is medium" in row["why"]


def test_one_loop_per_network_and_its_stop_recorded(networks, monkeypatch):  # noqa: F811
    import threading
    gate = threading.Event()
    monkeypatch.setattr(LP, "run_pass", lambda network, **kw: gate.wait(5))
    LP.start(NET, actor="op@example.com", interval=5)
    try:
        with pytest.raises(ValueError, match="started by op@example.com"):
            LP.start(NET, actor="other@example.com", interval=5)
        assert LP.status(NET)["running"]
    finally:
        LP.stop(NET, actor="op@example.com")
        gate.set()
        LP._jobs[NET]["thread"].join(10)
    assert not LP.status(NET)["running"]
    assert LP.status(NET)["stopped"]["words"] == "stopped by op@example.com"
    with pytest.raises(ValueError, match="from 5 to 600 s"):
        LP.start(NET, actor="op@example.com", interval=1)


def test_a_dismissal_names_its_reason(networks):  # noqa: F811
    row = LP.propose(NET, detection(), "drop_source", "low", why="HITL", now=T0)
    with pytest.raises(ValueError, match="names its reason"):
        LP.resolve(NET, row["id"], "dismissed", actor="op@example.com", why="")
    LP.resolve(NET, row["id"], "dismissed", actor="op@example.com", why="a known scanner")
    assert LP.awaiting(NET)["rows"] == []
    assert F.read(NET)["state"] == "absent"
