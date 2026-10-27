"""`classify_threat` (PHASE8_PLAN 17.1 S7; modules/sdn/closed_loop.py): an SDN detection
classified by AI through the gateway, its answer checked in code, proposed and never confirmed.
No provider is called: every answer is planted through a fake `send`, the gateway otherwise
real (its trigger, allowance, background switch, caps, mask and record), with a real settings
file, a real record of AI calls and real evidence packs in the test's own folder. The evidence
is the Lab 8 run's (tests/fixtures/ai_cases/sdn_classify/recorded.json: the scan on s1 by IPv4,
the flood on s1, the unauthorised redirect on s2; held_out.json's IPv6 scan).

- **The request**: the prompt and the catalogue as the cached prefix; the detection, its
  evidence, the names a device may be given and the network's limits as data; the pin's model;
  the call recorded under its trigger. The pack's hash checked first; the topology class off
  sends nothing.
- **The check**, each refusal its own: an action outside the catalogue for the rule, a source
  the detection did not see, a flow it does not name, a timeout over the ceiling, an answer
  citing nothing, an id not sent, a device the evidence does not name, no threat with an
  action. An IPv6 source in another spelling is the same address.
- **The loop**: its classify is a BACKGROUND call; off (the default) the gateway records the
  refusal and sends nothing, and the catalogue's default is proposed; on, the AI's action is
  proposed with its classification; an answer of no action is never AUTO's; AUTO applies the
  AI's action recorded as the AI's choice.
- **The estimate's frequency**: from the network's SDN detections in its alert history;
  unknown with none.
"""
import json
import os
import types

import pytest

from modules import evidence_pack as EP
from modules.ai import anthropic_adapter as A
from modules.ai import calls, gateway, triggers
from modules.sdn import closed_loop as CL
from modules.sdn import detect as D
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.ai_person import PERSON, pressed_by
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "tests", "fixtures", "ai_cases", "sdn_classify")
KEY = "sk-planted-sdn-classify-key-0123456789"
NET = "Default"


def case(name: str, key: str) -> dict:
    with open(os.path.join(CASES, f"{name}.json"), encoding="utf-8") as fh:
        found = [c for c in json.load(fh)["cases"] if c["key"] == key]
    (c,) = found
    return c


def detection_of(c: dict) -> dict:
    """The case's detection as the loop holds it, on the test's network (the one edit)."""
    return dict(c["detection"], network=NET)


def keep_pack(c: dict) -> dict:
    """The detection's evidence pack built and kept as `detect.observe` keeps it."""
    d = detection_of(c)
    at = D._epoch(d["at"])
    inst = D.instance(d, at, at)
    pack = EP.build_detection(inst, network=NET, sdn=c["section"], now=at,
                              trigger=f"planted: {d['words']}",
                              switch_words=f"switch {d['dpid_hex']} on {d['connection']}")
    assert EP.record(pack)["ok"]
    return pack


def answer(**over) -> dict:
    """A planted answer to the scan on s1 (recorded case 1) that passes the check."""
    a = {"reasoning": "192.0.2.1 reached 257 destination ports in 60 s, each probe one packet.",
         "threat_detected": True, "threat_type": "port_scan", "severity": "high",
         "affected_devices": ["192.0.2.1", "192.0.2.3", "0000000000000001"],
         "recommended_action": "Drop the source's traffic on s1 for ten minutes.",
         "action_id": "drop_source",
         "parameters": {"source": "192.0.2.1", "flow": "", "hard_timeout": 0, "rate": 0,
                        "unit": "kbps", "burst": 0},
         "evidence_refs": [SCAN["expect"]["cites_any"][0]]}
    a.update(over)
    return a


SCAN = case("recorded", "scan-1-s1")
FLOOD = case("recorded", "flood-s1")
REDIRECT = case("recorded", "unauthorised-s2")
SCAN6 = case("held_out", "scan-v6-s1")


@pytest.fixture
def world(networks, monkeypatch):  # noqa: F811 - the fixture, used
    """Hosted AI allowed with a $1.50 day cap in a real settings file, a key, the record of AI
    calls and the packs in the test's folder, and a fake provider answering `w.answer`."""
    from modules.settings_schema import write_settings

    assert write_settings({"ai_hosted": {"by": PERSON, "at": "2026-10-27T00:00:00Z",
                                         "reason": "the lab's proof of concept"},
                           "ai_cap_usd_per_day": 1.50})["ok"]
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    monkeypatch.setattr(calls, "_path", lambda: str(networks / "ai_calls.jsonl"))
    w = types.SimpleNamespace(sent=[], answer=answer(), dir=networks)

    def send(body, key):
        w.sent.append(body)
        return A.Reply(status=200, body={
            "content": [{"type": "text", "text": json.dumps(w.answer)}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 3000, "output_tokens": 300}},
            attempts=1, latency_s=0.1)
    w.send = send
    return w


def classify_as_person(w, c=SCAN, **kw):
    with pressed_by(PERSON):
        return CL.classify_threat(NET, detection_of(c), actor=PERSON,
                                  trigger=triggers.person(PERSON), send=w.send, **kw)


def rows():
    """The record's calls, newest first."""
    return calls.read()["rows"]


def uses():
    """What became of each call's answer, every call's uses in order."""
    return [u for us in calls.uses().values() for u in us]


# ── the request ───────────────────────────────────────────────────────────────────────────────

def test_the_request_holds_the_detection_its_evidence_and_the_catalogue(world):
    keep_pack(SCAN)
    got = classify_as_person(world)
    assert got["ok"], got
    (body,) = world.sent
    from modules.ai import profiles, prompts
    assert body["model"] == profiles.TASKS["sdn_classify"]["model"] == "claude-haiku-5-5"
    # The adopted prompt's text, whole (C1988: v3 since 2026-10-27).
    assert body["system"][0]["text"] == prompts.load(*CL.CLASSIFY_PROMPT)["text"]
    assert 'name="catalogue"' in body["system"][1]["text"]
    assert body["system"][-1]["cache_control"] == {"type": "ephemeral"}
    data = body["messages"][0]["content"]
    blocks = [line.split('"')[1] for line in data.splitlines() if line.startswith("<data name=")]
    assert blocks == ["detection", "evidence", "limits", "names"]
    assert "tools" not in body
    sent_ids = set(CL.sent_evidence(SCAN["section"])["ids"])
    assert SCAN["expect"]["cites_any"][0] in sent_ids and SCAN["expect"]["cites_any"][0] in data
    (row,) = rows()
    assert row["verdict"] == "ok" and row["trigger"]["kind"] == "person"
    assert row["subject"] == {"kind": "sdn_detection", "id": SCAN["detection"]["key"],
                              "rule": "scan", "devices": []}
    assert [u["use"] for u in uses()] == ["proposed: drop_source"]


def test_history_names_the_detection_a_call_was_about(world):
    from modules import history_sources as HS
    keep_pack(SCAN)
    classify_as_person(world)
    (event,) = HS.ai_calls({"device": None, "limit": 10})["events"]
    assert event["what"].startswith(
        f"AI call, sdn_classify on the SDN detection scan {SCAN['detection']['key']}: ")


def test_a_passing_answer_proposes_its_catalogue_action_with_checked_parameters(world):
    keep_pack(SCAN)
    got = classify_as_person(world)
    assert (got["action"], got["params"]) == ("drop_source", {"source": "192.0.2.1"})
    c = got["classification"]
    assert c["threat_type"] == "port_scan" and c["call_id"] == got["call_id"]
    assert c["model"] == "claude-haiku-5-5" and c["trigger"] == "person"


def test_a_pack_changed_since_it_was_kept_is_refused_and_nothing_is_sent(world):
    pack = keep_pack(SCAN)
    changed = json.loads(json.dumps(pack))
    changed["sections"][-1]["pieces"][0]["words"] = "edited after it was kept"
    with pressed_by(PERSON):
        got = CL.classify_pack(NET, detection_of(SCAN), changed, actor=PERSON,
                               trigger=triggers.person(PERSON), send=world.send)
    assert got["error"] == "changed" and world.sent == []


def test_no_pack_kept_is_refused_and_nothing_is_sent(world):
    got = classify_as_person(world)
    assert got["error"] == "no_pack" and "no evidence pack was kept" in got["detail"]
    assert world.sent == []


def test_the_topology_class_off_sends_nothing(world, monkeypatch):
    keep_pack(SCAN)
    monkeypatch.setattr("modules.ai.egress_classes.topology_allowed",
                        lambda net: {"allowed": False, "why": "planted: an admin turned it off"})
    got = classify_as_person(world)
    assert got["error"] == "withheld" and "topology class" in got["detail"]
    assert world.sent == []


def test_a_network_carrying_a_classification_marking_sends_nothing(world, monkeypatch):
    # The tier hand check's survivor (S7): the marking forces AI off before the topology gate,
    # said as the marking, whatever the topology class says.
    keep_pack(SCAN)
    monkeypatch.setattr("modules.ai.egress_classes.classification_marking",
                        lambda net: "planted-restricted")
    monkeypatch.setattr("modules.ai.egress_classes.topology_allowed",
                        lambda net: {"allowed": True, "why": ""})
    got = classify_as_person(world)
    assert got["error"] == "classified" and "'planted-restricted'" in got["detail"]
    assert "nothing was sent" in got["detail"] and world.sent == []


# ── the check ─────────────────────────────────────────────────────────────────────────────────

PARAMS = answer()["parameters"]
REFUSED = {
    "an action that does not answer the rule": (
        {"action_id": "remove_flow"}, "remove_flow answers unauthorised_flow, not"),
    "a source the detection did not see": (
        {"parameters": dict(PARAMS, source="192.0.2.2")}, "is not one the detection saw"),
    "a source the detection did not see, by IPv6": (
        {"parameters": dict(PARAMS, source="2001:db8:8::1")}, "is not one the detection saw"),
    "a hard timeout over the network's ceiling": (
        {"parameters": dict(PARAMS, hard_timeout=3601)}, "outside 1 to 3600 s"),
    "an answer citing nothing": ({"evidence_refs": []}, "cites no evidence id"),
    "an id the evidence did not send": (
        {"evidence_refs": ["flow:lab:0000000000000001:t0:p2:0000000000"]},
        "which the evidence sent does not hold"),
    "a device the evidence does not name": (
        {"affected_devices": ["198.51.100.7"]}, "which the evidence does not name"),
    "no threat, and an action": (
        {"threat_detected": False, "threat_type": "none"}, "finds no threat and proposes"),
}


@pytest.mark.parametrize("how", sorted(REFUSED))
def test_an_answer_the_check_refuses_is_said_and_nothing_of_it_is_used(world, how):
    keep_pack(SCAN)
    over, words = REFUSED[how]
    world.answer = answer(**over)
    got = classify_as_person(world)
    assert got["ok"] is False and got["error"] == "couldnt_classify", got
    assert words in got["detail"] and got["classification"] is None
    assert [u["use"] for u in uses()] == ["refused by validation"]


def test_an_ipv6_source_in_another_spelling_is_the_detection_s_own(world):
    keep_pack(SCAN6)
    world.answer = answer(
        affected_devices=["2001:0db8:0008::0001"],
        parameters=dict(PARAMS, source="2001:0db8:8:0:0:0:0:1"),
        evidence_refs=[SCAN6["expect"]["cites_any"][0]])
    got = classify_as_person(world, c=SCAN6)
    assert got["ok"], got
    assert got["params"] == {"source": "2001:db8:8::1"}


def test_remove_flow_names_the_flow_the_detection_names(world):
    keep_pack(REDIRECT)
    flow = REDIRECT["detection"]["subject"]["value"]
    world.answer = answer(threat_type="unauthorised_flow", action_id="remove_flow",
                          affected_devices=["192.0.2.3"],
                          parameters=dict(PARAMS, source="", flow=flow), evidence_refs=[flow])
    assert classify_as_person(world, c=REDIRECT)["action"] == "remove_flow"
    world.answer["parameters"]["flow"] = "flow:lab:0000000000000002:t0:p1:0000000000"
    got = classify_as_person(world, c=REDIRECT)
    assert got["error"] == "couldnt_classify" and "is not the one the detection names" in \
        got["detail"]


def test_a_rate_limit_s_rate_and_unit_are_kept(world):
    keep_pack(FLOOD)
    port = FLOOD["expect"]["cites_any"][0]
    world.answer = answer(threat_type="flood", action_id="rate_limit_source",
                          affected_devices=["192.0.2.2", "192.0.2.4"],
                          parameters=dict(PARAMS, source="192.0.2.2", hard_timeout=120,
                                          rate=500, unit="pktps", burst=50),
                          evidence_refs=[port])
    got = classify_as_person(world, c=FLOOD)
    assert got["params"] == {"source": "192.0.2.2", "hard_timeout": 120, "rate": 500,
                             "unit": "pktps", "burst": 50}


# ── the loop: a background call ─────────────────────────────────────────────────────────────

def _observed(c):
    d = detection_of(c)
    return lambda network, collected: {"ok": True, "fired": [d["key"]], "resolved": [],
                                       "detections": [d]}


def _pass(world, c=SCAN):
    return LP.run_pass(NET, collect=lambda: {"network": NET, "summary": {}, "state": "ok"},
                       observe=_observed(c), job="sdn-loop-default-test", send=world.send,
                       driver=lambda n, conn: {"ok": False, "error": "unused"})


def _feature_on():
    """Turned on now: an approval lasts 14 days from its time (background.APPROVAL_DAYS), so a
    fixed date would turn this off by itself once the 14 days passed."""
    import time
    from modules.settings_schema import write_settings
    assert write_settings({"ai_background": {"default": {"sdn_classify": {
        "on": True, "by": "admin@example.com", "verified": "access",
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "day_cap_usd": 0.5,
        "month_cap_usd": 5.0}}}})["ok"]


def test_the_loop_s_classify_is_a_background_call_refused_while_the_feature_is_off(world):
    keep_pack(SCAN)
    out = _pass(world)
    assert out["ok"] and world.sent == [], "nothing is sent while the feature is off"
    (row,) = rows()
    assert row["verdict"] == "feature_off" and row["actor"] == "job:sdn-loop-default-test"
    assert row["trigger"] == {"kind": "background", "feature": "sdn_classify",
                              "job": "sdn-loop-default-test", "network": "default",
                              "finding": {"kind": "detection", "id": SCAN["detection"]["key"]}}
    (resp,) = LP.awaiting(NET)["rows"]
    assert resp["action"] == "drop_source" and resp["classification"] is None
    assert "feature_off" in resp["classified"] and CL.DEFAULT_WORDS in resp["classified"]
    line = next(x for x in out["lines"] if x["step"] == "classify")
    assert "no AI classification (feature_off" in line["words"]


def test_with_the_feature_on_the_loop_proposes_the_ai_s_action(world):
    keep_pack(FLOOD)
    _feature_on()
    port = FLOOD["expect"]["cites_any"][0]
    world.answer = answer(threat_type="flood", action_id="drop_source",
                          affected_devices=["192.0.2.2"],
                          parameters=dict(PARAMS, source="192.0.2.2"), evidence_refs=[port])
    out = _pass(world, FLOOD)
    assert out["ok"] and len(world.sent) == 1
    (resp,) = LP.awaiting(NET)["rows"]
    assert (resp["action"], resp["params"]) == ("drop_source", {"source": "192.0.2.2"})
    assert resp["classification"]["trigger"] == "background"
    assert rows()[0]["trigger"]["kind"] == "background"


def test_an_answer_of_no_action_is_kept_for_a_person_even_in_auto(world, monkeypatch):
    keep_pack(SCAN)
    _feature_on()
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=__import__("time").time() + 600, allowed_risk="low")
    applied = []
    monkeypatch.setattr(CL, "respond_to_threat", lambda *a, **k: applied.append(a) or {})
    world.answer = answer(threat_detected=False, threat_type="none", severity="none",
                          affected_devices=[], action_id="none",
                          parameters=dict(PARAMS, source=""))
    out = _pass(world)
    assert applied == [] and out["proposed"]
    (resp,) = LP.awaiting(NET)["rows"]
    assert resp["why"] == "the AI proposed no catalogue action, so a person decides"
    assert resp["action"] == "drop_source" and resp["classification"]["action_id"] == "none"


def test_auto_applies_the_ai_s_action_recorded_as_the_ai_s_choice(world, monkeypatch):
    keep_pack(SCAN)
    _feature_on()
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=__import__("time").time() + 600, allowed_risk="low")
    seen = []

    def respond(network, d, action, params=None, *, confirm=None, **kw):
        seen.append((action, params, kw.get("classified_by")))
        if confirm is None:
            return {"ok": True, "ask": {"a": 1}, "plan": {"hash": "h"}}
        return {"id": "sdnop-1", "outcome": "verified"}
    monkeypatch.setattr(CL, "respond_to_threat", respond)
    out = _pass(world)
    assert out["applied"] == [{"id": "sdnop-1", "outcome": "verified"}]
    ((action, params, _none), (applied, _p, by)) = seen
    assert (action, params, applied) == ("drop_source", {"source": "192.0.2.1"}, "drop_source")
    assert by.startswith("proposed by AI call ") and by.endswith("checked in code")


# ── the estimate's frequency ─────────────────────────────────────────────────────────────────

def test_the_frequency_is_unknown_with_no_detection_and_measured_from_the_history(world):
    from modules import alert_history
    from modules.ai import background

    got = CL.detection_frequency("default", now=1_793_000_000.0)
    assert got["per_day"] is None and got["basis"].startswith("unknown: no SDN detection")
    est = background.estimate(NET, "sdn_classify")
    assert est["calls_per_day"] is None and est["frequency"]["basis"].startswith("unknown")
    d = detection_of(SCAN)
    at = 1_793_000_000.0 - 2 * 86400
    inst = dict(D.instance(d, at, at), active_at=D._iso(at))
    assert alert_history.record(alert_history.from_detections(D.STORE, [NET], [inst], [],
                                                              now=at))["ok"]
    got = CL.detection_frequency("default", now=1_793_000_000.0)
    assert got["per_day"] == 0.5 and got["basis"].startswith("measured: 1 detection(s)")
    assert CL.detection_frequency("branch", now=1_793_000_000.0)["per_day"] is None


def _clock(monkeypatch, at: float):
    """Every reader of the time sees *at*, then the time passing from it; returns a function
    moving the clock on by a number of seconds."""
    import time
    real, start, skew = time.time, time.time(), [0.0]
    monkeypatch.setattr(time, "time", lambda: at + (real() - start) + skew[0])
    return lambda seconds: skew.__setitem__(0, skew[0] + seconds)


def _detected(at: float):
    from modules import alert_history

    d = detection_of(SCAN)
    inst = dict(D.instance(d, at, at), active_at=D._iso(at))
    assert alert_history.record(alert_history.from_detections(D.STORE, [NET], [inst], [],
                                                              now=at))["ok"]


def _turn_on(shown: str):
    from modules.ai import background

    return background.turn_on(NET, "sdn_classify", day_cap_usd=0.5, month_cap_usd=10.0,
                              shown=shown, actor="admin@example.com", verified="access")


@pytest.mark.parametrize("ago,per_day", [(2 * 86400, 0.5), (30 * 86400 - 300, 0.033)],
                         ids=["two-days-before", "at-the-windows-edge"])
def test_an_estimate_confirmed_ten_minutes_after_it_was_shown_is_accepted(world, monkeypatch,
                                                                          ago, per_day):
    # C1954: the measured frequency's figures are whole UTC days, so time alone (07:26 UTC to
    # 07:36) does not move the estimate's digest: not the span (a detection two days before),
    # and not the window (one 30 days less 5 minutes before, which a window of 30 times
    # 86400 s back from now would drop within the 10 minutes).
    from modules.ai import background

    later = _clock(monkeypatch, 1_793_000_000.0)
    _detected(1_793_000_000.0 - ago)
    shown = background.estimate(NET, "sdn_classify")
    assert shown["calls_per_day"] == per_day
    later(600)
    got = _turn_on(shown["digest"])
    assert got["ok"] is True and got["entry"]["estimate"]["digest"] == shown["digest"]


def test_an_estimate_whose_detections_changed_since_it_was_shown_is_refused(world, monkeypatch):
    # C1954's other half: the digest still moves when the measurement does (a detection
    # recorded between showing and confirming), and nothing is turned on.
    from modules.ai import background

    later = _clock(monkeypatch, 1_793_000_000.0)
    _detected(1_793_000_000.0 - 2 * 86400)
    shown = background.estimate(NET, "sdn_classify")["digest"]
    later(60)
    _detected(1_793_000_000.0 + 30)
    with pytest.raises(background.Refused, match="the estimate moved since it was shown"):
        _turn_on(shown)
    assert background.switches() == {}


# ── a person's Classify, through the real routes ─────────────────────────────────────────────

@pytest.fixture
def screen(world):
    """The real app, one scan awaiting a person on SDN › Responses, its pack kept."""
    import app as APP

    keep_pack(SCAN)
    row = LP.propose(NET, detection_of(SCAN), "drop_source", "low", why="HITL",
                     classified="no AI classification (planted)")
    return types.SimpleNamespace(world=world, client=APP.app.test_client(), row=row)


def _html(r):
    from html import unescape
    return unescape(r.get_data(as_text=True))


def test_classify_draws_the_ai_s_classification_and_proposes_its_action(screen, monkeypatch):
    from tests.conftest import TEST_PERSON
    monkeypatch.setattr(gateway, "anthropic_adapter",
                        types.SimpleNamespace(**{**vars(gateway.anthropic_adapter),
                                                 "send": screen.world.send}))
    screen.world.answer = answer(action_id="rate_limit_source",
                                 parameters=dict(PARAMS, hard_timeout=300, rate=200,
                                                 unit="pktps", burst=20))
    r = screen.client.post(f"/v2/sdn/response/{screen.row['id']}/classify",
                           data={"list": NET}, headers={"HX-Request": "true"})
    html = _html(r)
    assert r.status_code == 200, html
    assert "A threat: port scan" in html and "It recommends:" in html
    assert 'catalogue action <span class="mono">rate_limit_source</span>, its parameters' in html
    assert "Classify again" in html
    assert 'name="hard_timeout" min="1" max="3600" value="300"' in html
    assert '<option value="pktps" selected>' in html
    (resp,) = LP.awaiting(NET)["rows"]
    assert resp["action"] == "rate_limit_source" and resp["classified_by"] == TEST_PERSON
    (row,) = rows()
    assert row["trigger"]["kind"] == "person" and row["actor"] == TEST_PERSON
    assert len(screen.world.sent) == 1


def test_a_refused_classification_is_said_on_its_card_and_the_proposal_stays(screen,
                                                                              monkeypatch):
    monkeypatch.setattr(gateway, "anthropic_adapter",
                        types.SimpleNamespace(**{**vars(gateway.anthropic_adapter),
                                                 "send": screen.world.send}))
    screen.world.answer = answer(evidence_refs=[])
    r = screen.client.post(f"/v2/sdn/response/{screen.row['id']}/classify",
                           data={"list": NET}, headers={"HX-Request": "true"})
    html = _html(r)
    assert "Couldn't classify: couldn't classify: it cites no evidence id" in html
    assert "The proposal above is unchanged." in html
    (resp,) = LP.awaiting(NET)["rows"]
    assert resp["action"] == "drop_source" and resp["classification"] is None


def test_classify_is_an_ai_control_and_preview_and_dismiss_stay_usable(screen, monkeypatch):
    """PHASE8_PLAN 15.13 through the page's real route: Classify carries the AI mark with its
    task, model and cap; while hosted AI cannot answer it is disabled with the reason in place,
    and the response's Preview and Dismiss are drawn usable beside it."""
    from tests import ai_controls_check as AIC

    def get():
        return screen.client.get(f"/v2/sdn/responses?list={NET}").get_data(as_text=True)

    def parity(html):
        # Drawn, and (check_screen's own comparison) not disabled by AI's state: a viewer who
        # may not confirm sees them as the gate draws them.
        assert "Preview the drop traffic from the source…" in _html_text(html)
        assert "Dismiss with this reason" in html
    AIC.check_screen(monkeypatch, get, "sdn_classify", parity)


def test_a_confirmed_response_records_who_chose_its_action(screen, monkeypatch):
    from tests.sdn_fakes import FakeRyu
    from tests.test_sdn_flow_ops import captured_table
    from modules.sdn import connections as C
    from modules.sdn import drivers
    from modules.sdn import flow_intent as F

    fake = FakeRyu("http://192.0.2.10:8080", flows={1: captured_table()})
    real = drivers.make
    monkeypatch.setattr(drivers, "make", lambda kind, conn, **kw: real(
        kind, conn, **dict(kw, session=fake, sleep=lambda s: None)))
    monkeypatch.setattr("modules.sdn.flow_ops.COUNTER_INTERVAL", 0)
    C.save_connection(NET, {"name": "lab", "kind": "ryu", "url": "http://192.0.2.10:8080"},
                      actor="op@example.com")
    with pressed_by(PERSON):
        got = CL.classify_threat(NET, detection_of(SCAN), actor=PERSON,
                                 trigger=triggers.person(PERSON), send=screen.world.send)
    LP.classified(NET, screen.row["id"], got, actor=PERSON)
    c = screen.client
    html = c.post(f"/v2/sdn/response/{screen.row['id']}/preview",
                  data={"list": NET}).get_data(as_text=True)
    from tests.test_sdn_ops_v2 import form_fields
    fields = form_fields(html)
    assert "proposed by AI call" in _html_text(html)
    r = c.post("/v2/sdn/response/confirm", data=fields)
    assert "Done, verified" in r.get_data(as_text=True)
    (op,) = F.operations(NET)["rows"]
    assert op["response"]["classified_by"] == (f"proposed by AI call {got['call_id']} "
                                               "(claude-haiku-5-5), checked in code")


def _html_text(html):
    from html import unescape
    return unescape(html)
