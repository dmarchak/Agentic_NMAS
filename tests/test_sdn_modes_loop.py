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
- **The guard (C2009, PHASE8_PLAN 17.7)**: AUTO is turned on only on a network marked lab
  (refused, in exact words naming the stage and the gate, on one not marked, marked pilot or
  production, or whose stage cannot be read); AUTO recorded on runs nothing unattended once the
  stage moves off lab, and again once it is marked lab; the stage is never inherited from
  Default; setting it needs a verified person, a known value and a reason, is refused when it
  moved since drawn, and is recorded with who, when, from, to and why.
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


def mark_lab(network=NET, value="lab"):
    """Mark *network* (C2009: AUTO is turned on only on a network marked lab until the AUTO
    production-readiness gate is complete), as a verified person with a reason."""
    return MD.set_stage(network, value, actor="admin@example.com", actor_verified="access",
                        reason="the course lab's network")


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
    mark_lab(NET)
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
    mark_lab(NET)
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="r",
               until=T0 + 600, now=T0)
    MD.turn_off(NET, actor="admin@example.com", now=T0 + 5)
    assert MD.current(NET, T0 + 6)["mode"] == "hitl"
    with pytest.raises(MD.ModeRefused, match="AUTO is not on"):
        MD.turn_off(NET, actor="admin@example.com", now=T0 + 7)


# ── C2009: AUTO only on a network marked lab (PHASE8_PLAN 17.7's guard) ───────────────────

GATE = ("AUTO is turned on only on a network marked lab until the AUTO production-readiness "
        "gate (PHASE8_PLAN 17.7) is complete; ")


def _on(network=NET, now=T0):
    return MD.turn_on(network, actor="admin@example.com", actor_verified="access",
                      reason="lab 8 run", until=now + 600, allowed_risk="low", now=now)


def _store_file(network):
    from modules import list_settings as L

    path = L.path(network)
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _unreadable(network="Branch"):
    with open(_store_file(network), "w", encoding="utf-8") as fh:
        fh.write("{torn")


def _record_rows(network=NET):
    import json
    import os

    from modules.config import list_data_path
    path = os.path.join(list_data_path(network), "settings_record.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


@pytest.mark.parametrize("prepare,network,words", [
    (lambda: None, NET, "Default is not marked"),
    (lambda: mark_lab(NET, "pilot"), NET, "Default is marked pilot"),
    (lambda: mark_lab(NET, "production"), NET, "Default is marked production"),
], ids=["not-marked", "pilot", "production"])
def test_auto_is_refused_on_a_network_not_marked_lab(networks, prepare, network,  # noqa: F811
                                                     words):
    prepare()
    with pytest.raises(MD.ModeRefused) as got:
        _on(network)
    assert str(got.value) == GATE + words
    assert MD.current(network, T0)["mode"] == "hitl"
    assert MD.history(network)["rows"] == [], "nothing was recorded on"


def test_auto_is_refused_where_the_stage_cannot_be_read(networks):  # noqa: F811
    _unreadable("Branch")
    st = MD.stage("Branch")
    assert st["state"] == "unreadable" and st["stage"] == ""
    with pytest.raises(MD.ModeRefused) as got:
        _on("Branch")
    words = str(got.value)
    assert words.startswith(GATE + "Branch's stage cannot be read (")
    assert words.endswith("), and a stage that cannot be read is never read as lab")
    assert MD.current("Branch", T0)["mode"] == "hitl"
    # A value that is not a stage (a hand edit) is unreadable too, never lab.
    with open(_store_file("Branch"), "w", encoding="utf-8") as fh:
        fh.write('{"values": {"network_stage": "LAB"}}')
    assert MD.stage("Branch")["state"] == "unreadable"
    with pytest.raises(MD.ModeRefused, match="never read as lab"):
        _on("Branch")


def test_auto_is_accepted_on_a_network_marked_lab(networks):  # noqa: F811
    mark_lab(NET)
    assert MD.stage(NET) == {"stage": "lab", "state": "ok", "error": "",
                             "words": "Default is marked lab"}
    _on(NET)
    assert MD.current(NET, T0 + 1)["mode"] == "auto"
    assert MD.decide(NET, "low", T0 + 1)["auto"] is True


@pytest.mark.parametrize("move,words", [
    ("production", "Default is marked production"),
    ("pilot", "Default is marked pilot"),
    ("unreadable", "Default's stage cannot be read (planted)"),
], ids=["production", "pilot", "unreadable"])
def test_decide_fails_closed_when_the_stage_moves_off_lab(networks, monkeypatch,  # noqa: F811
                                                          move, words):
    from modules import list_settings as L

    mark_lab(NET)
    _on(NET)
    assert MD.decide(NET, "low", T0 + 1)["auto"] is True
    if move == "unreadable":
        def broken(*a, **kw):
            raise L.ListSettingsUnreadable("planted")
        monkeypatch.setattr(L, "resolve", broken)
    else:
        mark_lab(NET, move)
    got = MD.decide(NET, "low", T0 + 2)
    assert got["auto"] is False and got["autonomous"] is None
    assert got["words"].startswith("HITL: AUTO is on and suspended, since " + GATE + words)
    assert MD.current(NET, T0 + 2)["mode"] == "auto", "recorded on, and suspended"


def test_marking_lab_again_lifts_the_suspension(networks):  # noqa: F811
    mark_lab(NET)
    _on(NET)
    mark_lab(NET, "production")
    assert MD.decide(NET, "low", T0 + 1)["auto"] is False
    mark_lab(NET, "lab")
    assert MD.decide(NET, "low", T0 + 1)["auto"] is True


def test_the_stage_is_never_inherited_from_default(networks):  # noqa: F811
    from modules import list_settings as L

    mark_lab(NET)
    # Branch inherits from Default (no mode set: INHERIT), and still has no stage of its own.
    assert L.load("Branch")["mode"] == L.INHERIT
    assert MD.stage("Branch") == {"stage": "", "state": "not_marked", "error": "",
                                  "words": "Branch is not marked"}
    with pytest.raises(MD.ModeRefused) as got:
        _on("Branch")
    assert str(got.value) == GATE + "Branch is not marked"
    # Marked lab itself, it may.
    mark_lab("Branch")
    _on("Branch")
    assert MD.current("Branch", T0 + 1)["mode"] == "auto"


@pytest.mark.parametrize("kw,words", [
    ({"reason": " "}, "with a recorded reason, and none was given"),
    ({"value": "staging"}, "a network's stage is lab, pilot, production, not 'staging'"),
    ({"value": ""}, "a network's stage is lab, pilot, production, not ''"),
    ({"actor_verified": "none"}, "set by a verified person"),
    ({"actor_verified": ""}, "set by a verified person"),
    ({"actor": ""}, "set by a verified person"),
    ({"loaded": "production"}, "Default's stage moved since the card drew it (drawn: "
                               "production; now: not marked): nothing was saved"),
], ids=["no-reason", "unknown-value", "empty-value", "unverified", "verification-unknown",
        "no-actor", "moved-since-drawn"])
def test_setting_the_stage_is_refused_without_its_person_reason_and_value(networks, kw,  # noqa: F811
                                                                          words):
    args = dict(value="lab", actor="admin@example.com", actor_verified="access",
                reason="the course lab", loaded="")
    args.update(kw)
    value = args.pop("value")
    with pytest.raises(MD.ModeRefused) as got:
        MD.set_stage(NET, value, **args)
    assert words in str(got.value)
    assert MD.stage(NET)["state"] == "not_marked"
    assert [r for r in _record_rows() if r.get("kind") == "network_stage"] == []


def test_setting_the_stage_records_who_from_to_and_why(networks):  # noqa: F811
    got = MD.set_stage(NET, "pilot", actor="admin@example.com", actor_verified="access",
                       reason="the first pilot", loaded="")
    assert got == {"ok": True, "network": NET, "before": "", "after": "pilot",
                   "unchanged": False, "recorded": True}
    MD.set_stage(NET, "lab", actor="op@example.com", actor_verified="access",
                 reason="back to the lab", loaded="pilot")
    rows = [r for r in _record_rows() if r.get("kind") == "network_stage"]
    assert [(r["before"], r["after"], r["actor"], r["actor_verified"], r["reason"])
            for r in rows] == [("", "pilot", "admin@example.com", "access", "the first pilot"),
                               ("pilot", "lab", "op@example.com", "access", "back to the lab")]
    assert all(r.get("at") for r in rows), "each says when"
    same = MD.set_stage(NET, "lab", actor="op@example.com", actor_verified="access",
                        reason="again", loaded="lab")
    assert same["unchanged"] is True and same["recorded"] is False


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
    mark_lab(NET)
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
