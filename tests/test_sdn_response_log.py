"""The SDN loop's log for a response and for a pass with no new threat (the Lab 8 walk's
objective 3.1, the operator's order of 2026-10-27; `closed_loop.log_response`, `loop.run_pass`).

- **A response's line**, one writer for both paths: AUTO's apply in a pass, and a person's
  confirm through the real route. Each says who applied which action on which switch, the
  operation's id, and the resulting entry AS VERIFY READ IT BACK from the switch (a FakeRyu
  holding the table, so the read-back is the switch's, not the request): its match, actions,
  priority, idle and hard timeouts and cookie (IPv4 and IPv6 sources); a rate limit's meter
  with its band, rate, unit and burst; a removal's flow gone and Mercury's flow put back. A
  response rolled back says so; an entry not read back is said so, never drawn from the
  request; a switch's reported name is beside its DPID.
- **A pass with no new threat**: "network healthy: no threat detected" only when the
  collection read every switch and nothing is active; "no new threat; N still active: …" while
  a detection is active (or stays firing unread); a partial read, or none, is said and never
  called healthy.
"""
import json
import time

import pytest

from modules.sdn import closed_loop as CL
from modules.sdn import flow_intent as F
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_detect import V6_L4, save, scan_flows
from tests.test_sdn_ops_v2 import form_fields, lab  # noqa: F401 - the fixture
from tests.test_sdn_respond import confirm, scan_detection, switch_with

NET = "Default"
NO_DRIVER = lambda n, c: {"ok": False, "error": "unused"}  # noqa: E731


def respond_lines(network=NET) -> list:
    return [r for r in LP.log_lines(network, 200)["rows"] if r["step"] == "respond"]


def _auto_pass(d, fake, monkeypatch, action="drop_source"):
    """One pass in AUTO whose classification passed, proposing *action* for detection *d*,
    applied through the real flow-operation core on *fake*."""
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=time.time() + 600, allowed_risk="low")
    monkeypatch.setattr("modules.sdn.flow_ops.COUNTER_INTERVAL", 0)
    monkeypatch.setattr(LP, "classify", lambda network, det, job, **kw: {
        "action": action, "risk": "low", "params": {"source": det["source"]},
        "classification": {"call_id": "call-planted", "action_id": action, "model": "m"},
        "person": False, "why": "", "refused_call": "", "words": "planted: passed"})
    return LP.run_pass(NET, collect=lambda: {"network": NET, "state": "ok",
                                             "summary": {"switches": 1, "flows": 25}},
                       observe=lambda network, c: {"ok": True, "fired": [d["key"]],
                                                   "resolved": [], "detections": [d]},
                       driver=fake.driver, sleep=lambda s: None)


# ── a response's line ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("src,field,eth", [(None, "ipv4_src", "0x0800"),
                                           (V6_L4, "ipv6_src", "0x86dd")], ids=["ipv4", "ipv6"])
def test_auto_s_line_carries_the_entry_as_read_back(networks, monkeypatch, src, field,  # noqa: F811
                                                     eth):
    save()
    flows = scan_flows(25) if src is None else scan_flows(25, src)
    d = scan_detection(flows)
    fake = switch_with(flows)
    out = _auto_pass(d, fake, monkeypatch)
    assert out["ok"] and out["applied"][0]["outcome"] == "verified", out
    (line,) = respond_lines()
    (op,) = F.operations(NET)["rows"]
    sent = json.loads(op["requests"][0]["body"])
    installed = next(f for f in fake.table[1] if f["cookie"] == sent["cookie"])
    w = line["words"]
    assert w.startswith(f"Mercury (AUTO) applied drop_source on switch 0000000000000001, "
                        f"operation {op['id']}: verified; as read back: flow match ")
    assert f"{field}={d['source']}" in w and f"eth_type={eth}" in w.lower()
    assert "; actions drop; priority 300; idle timeout 0 s; hard timeout 600 s; cookie " \
        f"{F.cookie_hex(installed['cookie'])}" in w
    assert line["operation"] == op["id"] and line["actor"] == "Mercury (AUTO)"
    (rb,) = line["read_back"]
    assert rb["flow"]["cookie"] == installed["cookie"] and rb["read"] is True
    assert out["lines"][-1]["words"] == w


def _switch_keeps(fake, monkeypatch, **held):
    """*fake* applies each flow it is sent with *held*'s fields in place of the sent ones."""
    real = fake._answer

    def answer(method, path, body):
        if path == "/stats/flowentry/add":
            body = json.dumps(dict(json.loads(body), **held))
        return real(method, path, body)
    monkeypatch.setattr(fake, "_answer", answer)


def test_the_line_says_what_the_switch_holds_not_what_was_sent(networks, monkeypatch):  # noqa: F811
    """The switch keeps an idle timeout of 7 s where 0 was sent (Verify does not gate on the
    idle timeout, so the response is verified): the line says 7, the switch's own."""
    save()
    flows = scan_flows(25)
    d = scan_detection(flows)
    fake = switch_with(flows)
    _switch_keeps(fake, monkeypatch, idle_timeout=7)
    out = _auto_pass(d, fake, monkeypatch)
    assert out["applied"][0]["outcome"] == "verified"
    (line,) = respond_lines()
    assert "idle timeout 7 s; hard timeout 600 s" in line["words"]
    assert line["read_back"][0]["flow"]["idle_timeout"] == 7


def test_a_response_rolled_back_says_so_and_nothing_of_it_in_force(networks,  # noqa: F811
                                                                    monkeypatch):
    """The switch keeps a hard timeout of 599 s where 600 was sent: Verify fails on it, the
    response is rolled back, and the line says so with Verify's reason."""
    save()
    flows = scan_flows(25)
    d = scan_detection(flows)
    fake = switch_with(flows)
    _switch_keeps(fake, monkeypatch, hard_timeout=599)
    out = _auto_pass(d, fake, monkeypatch)
    (line,) = respond_lines()
    assert out["applied"][0]["outcome"] == "rolled_back"
    assert ": rolled back (Verify failed: " in line["words"]
    assert "hard timeout 599 s, sent 600 s" in line["words"]
    assert "nothing of it is in force" in line["words"]


def test_a_person_s_confirm_through_the_route_writes_the_same_line(lab):  # noqa: F811
    from tests.conftest import TEST_PERSON
    d = {"key": "k1", "rule": "scan", "title": "SDN scan", "network": NET,
         "connection": "lab-controller", "dpid": 1, "dpid_hex": "0000000000000001",
         "source": "192.0.2.1", "targets": ["192.0.2.2"], "confidence": "high",
         "words": "192.0.2.1 reached 25 distinct destination ports"}
    row = LP.propose(NET, d, "drop_source", "low", why="HITL")
    c = lab["client"]
    fields = form_fields(c.post(f"/v2/sdn/response/{row['id']}/preview",
                                data={"list": NET}).get_data(as_text=True))
    assert "Done, verified" in c.post("/v2/sdn/response/confirm", data=fields)\
        .get_data(as_text=True)
    (line,) = respond_lines()
    (op,) = F.operations(NET)["rows"]
    assert line["words"].startswith(
        f"{TEST_PERSON} applied drop_source on switch 0000000000000001, operation {op['id']}: "
        "verified; as read back: flow match eth_type=0x0800, ipv4_src=192.0.2.1; actions drop; "
        "priority ")
    assert "hard timeout 600 s; cookie 0x" in line["words"]
    assert line["response"] == row["id"] and line["read_back"][0]["flow"]["hard_timeout"] == 600


def test_a_refused_confirm_is_logged_as_refused_with_its_reason(lab):  # noqa: F811
    from tests.conftest import TEST_PERSON
    d = {"key": "k1", "rule": "scan", "title": "SDN scan", "network": NET,
         "connection": "lab-controller", "dpid": 1, "dpid_hex": "0000000000000001",
         "source": "192.0.2.1", "targets": ["192.0.2.2"], "words": "a scan"}
    row = LP.propose(NET, d, "drop_source", "low", why="HITL")
    c = lab["client"]
    fields = form_fields(c.post(f"/v2/sdn/response/{row['id']}/preview",
                                data={"list": NET}).get_data(as_text=True))
    fields["hash"] = "f" * 64
    c.post("/v2/sdn/response/confirm", data=fields)
    (line,) = respond_lines()
    assert line["words"].startswith(f"{TEST_PERSON}'s drop_source on switch 0000000000000001 "
                                    "was refused: nothing was sent (the preview's hash was")
    assert lab["fake"].writes == []


def test_a_rate_limit_s_line_carries_its_meter(networks):  # noqa: F811
    from tests.sdn_fakes import lab8
    from tests.test_sdn_lab8 import BASE, fake_with, features_of, flows_of
    from modules.sdn import connections as C
    C.save_connection(NET, {"name": "lab", "kind": "ryu", "url": BASE}, actor="op")
    entries = lab8("flood_s1.json")
    (d,) = lab8("flood_detection.json")
    d = dict(d, network=NET)
    mercury = next(f["cookie"] for f in flows_of(entries, 1) if F.is_mercury(f["cookie"]))
    fake = fake_with(flows_of(entries, 1, drop_cookie=mercury), 1, features_of(entries, 1))
    preview = CL.respond_to_threat(NET, d, "rate_limit_source", {"hard_timeout": 120},
                                   driver=fake.driver)
    done = CL.respond_to_threat(NET, None, "rate_limit_source", confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        driver=fake.driver, sleep=lambda s: None, counter_interval=0)
    assert done["outcome"] == "verified"
    line = CL.log_response(NET, done, action="rate_limit_source", who="op@example.com",
                           ask=preview["ask"], now=1_790_000_000.0)
    w = line["words"]
    assert "as read back: meter 1: band drop, rate 1000 kbps, burst 100 | flow match " in w
    assert ("eth_type=0x0800, ipv4_dst=192.0.2.4, ipv4_src=192.0.2.2; actions " in w)
    assert "meter:1" in w.lower() and "hard timeout 120 s" in w
    assert line["logged"] is True and respond_lines()[-1]["words"] == w


def test_a_removal_s_line_says_the_flow_is_gone_and_mercury_s_put_back(networks):  # noqa: F811
    from modules.sdn import detect as D
    from tests.test_sdn_detect import T0, collect
    save()
    flows = scan_flows(0)
    dets = D.unauthorised(collect(T0, flows=flows), F.intent(NET))["detections"]
    d = next(x for x in dets if x["measurement"]["cookie"] == "0x4d45524300000001")
    fake = switch_with(flows)
    hit = next(f for f in fake.table[1] if f["cookie"] == 0x4d45524300000001)
    mine = dict({k: hit[k] for k in ("table_id", "priority", "match", "actions")},
                cookie=F.mercury_cookie(77), hard_timeout=0, idle_timeout=0, dpid=1)
    F.record_installed(NET, connection="ctl-1", flow=mine, actor="op@example.com",
                       response={"id": "r-0"})
    preview = CL.respond_to_threat(NET, d, driver=fake.driver)
    done = confirm(fake, preview)
    assert done["outcome"] == "verified"
    w = CL.log_response(NET, done, action="remove_flow", who="op@example.com",
                        ask=preview["ask"])["words"]
    assert ("removed flow match " in w and "cookie 0x4d45524300000001: gone from the table as "
            "read back" in w)
    assert f"reinstalled flow match " in w and F.cookie_hex(F.mercury_cookie(77)) in w


def test_an_entry_verify_did_not_read_back_is_said_never_drawn_from_the_request():
    done = {"outcome": "verified", "id": "sdnop-x", "plan": {"dpid": 1, "connection": "c"},
            "verify": {"read_back": [
                {"role": "add_flow", "read": False, "cookie": 0x4d45524300000009, "flow": None},
                {"role": "add_meter", "read": False, "meter_id": 4, "meter": None}]}}
    w = CL.response_words(done, action="rate_limit_source", who="p", switch="0000000000000001")
    assert ("flow cookie 0x4d45524300000009: Verify did not read it back (the table could not "
            "be read)") in w
    assert "meter 4: Verify did not read it back" in w and "match" not in w


def test_a_table_verify_could_not_read_says_nothing_of_what_it_holds():
    """`flow_ops.read_back` over a last read that failed: a removed flow is never called gone,
    a flow or a meter never found, each marked not read."""
    from modules.sdn import flow_ops
    target = {"table_id": 0, "priority": 100, "match": {"in_port": 1}, "cookie": 0xBAD0}
    steps = [{"role": "remove_flow", "expect": {"absent": target}},
             {"role": "add_flow", "expect": {"present": dict(target, cookie=1, actions=[])}},
             {"role": "add_meter", "expect": {"meter": {"meter_id": 3, "bands": []}}}]
    got = flow_ops.read_back(steps, {"flows": [], "meters": [], "flows_read": False,
                                     "meters_read": False})
    assert [(r["role"], r["read"]) for r in got] == [("remove_flow", False), ("add_flow", False),
                                                     ("add_meter", False)]
    assert got[0]["gone"] is False and got[1]["flow"] is None and got[2]["meter"] is None
    w = CL.response_words({"outcome": "verified", "id": "op", "verify": {"read_back": got}},
                          action="remove_flow", who="p", switch="0000000000000002")
    assert "Verify did not read the table" in w and "gone" not in w
    read = flow_ops.read_back(steps, {"flows": [], "meters": [], "flows_read": True,
                                      "meters_read": True})
    assert read[0]["gone"] is True, "read and absent: gone"


def test_a_switch_s_reported_name_is_beside_its_dpid(networks, monkeypatch):  # noqa: F811
    from modules.sdn import topology
    monkeypatch.setattr(topology, "stored", lambda network, **kw: {"controllers": [
        {"name": "lab-controller", "names": {1: "s1"}}]})
    done = {"outcome": "refused", "error": "planted", "plan": None}
    line = CL.log_response(NET, done, action="drop_source", who="p",
                           ask={"connection": "lab-controller", "dpid": 1})
    assert line["words"] == ("p's drop_source on switch 0000000000000001 (s1) was refused: "
                             "nothing was sent (planted)")


# ── a pass with no new threat ─────────────────────────────────────────────────────────────────

def _quiet(networks, collected, seen):  # noqa: F811
    out = LP.run_pass(NET, collect=lambda: dict({"network": NET}, **collected),
                      observe=lambda network, c: dict({"ok": True, "fired": [],
                                                       "resolved": []}, **seen),
                      now=lambda: 1_790_000_000.0, driver=NO_DRIVER)
    return next(x for x in out["lines"] if x["step"] == "detect")["words"]


OK_READ = {"state": "ok", "summary": {"switches": 4, "flows": 40}}


def test_healthy_only_when_every_switch_was_read_and_nothing_is_active(networks):  # noqa: F811
    assert _quiet(networks, OK_READ, {"detections": []}) == "network healthy: no threat detected"


def test_a_detection_still_active_is_named_never_healthy(networks):  # noqa: F811
    d = {"key": "k1", "rule": "scan", "words": "192.0.2.1 reached 25 ports"}
    w = _quiet(networks, OK_READ, {"detections": [d]})
    assert w == "no new threat; 1 still active: 192.0.2.1 reached 25 ports"


def test_a_detection_whose_subject_was_not_read_stays_named(networks):  # noqa: F811
    w = _quiet(networks, OK_READ, {"detections": [], "unjudged": [
        {"key": "k2", "title": "SDN flood", "words": "its subject was not read in this "
                                                    "collection, so it stays firing"}]})
    assert w.startswith("no new threat; 1 still active: SDN flood (its subject was not read")


@pytest.mark.parametrize("collected,words", [
    ({"state": "partial", "error": "ctl: 1 of 4 switch(es) not read whole",
      "summary": {"switches": 4}},
     "no threat detected on the switches read, but the collection was partial (ctl: 1 of 4 "
     "switch(es) not read whole): not called healthy"),
    ({"state": "ok", "summary": {"switches": 0}},
     "no switch was read (ok): nothing judged healthy"),
], ids=["partial", "no-switch"])
def test_a_read_that_failed_or_covered_no_switch_is_never_healthy(networks, collected,  # noqa: F811
                                                                  words):
    assert _quiet(networks, collected, {"detections": []}) == words
