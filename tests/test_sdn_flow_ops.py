"""The flow-operation core (`modules/sdn/flow_ops.py`; PHASE8_PLAN 17.1 S8 and S16, C1912):
one path for every flow and meter Mercury adds, edits or removes.

**The data.** The switch starts with Ryu 4.34's captured flow table (tests/fixtures/sdn/ryu/
rest_with_peer.json, `/stats/flow/1`: the table-miss, L2, L4 and Mercury-range flows), read
through the real Ryu driver from `tests.sdn_fakes.FakeRyu`, which answers in Ryu's own shapes
and applies each write as the lab's Open vSwitch did (an add at an existing place replaces it,
modify-strict replaces the actions and keeps the cookie and timeouts, delete-strict by place
and cookie under the mask). Its meter features are the lab OVS's, read 2026-10-27 (max_bands 1,
DROP only; tests/fixtures/sdn/lab8/README.md).

- **The plan** reads, never writes; renders the exact requests and their undos; the hash binds
  the requests and the before-state, and moves when either does;
- **refusals before a request exists**, each naming what it compared: a match prerequisite, a
  cookie not Mercury's or already used, an add over an existing flow, a response with no hard
  timeout or one past the network's ceiling, a meter the switch's features cannot hold, a
  meter still in use, a flow not in the table, an edit of a flow not Mercury's;
- **the apply**: a moved hash sends nothing; a held switch is refused by name; a verified
  change is recorded (installed, amended, withdrawn, meter, operation); a write the switch did
  not apply fails Verify and is rolled back, read back, and nothing is recorded as installed;
  a controller's refusal mid-way rolls back what landed;
- **remove**: delete-strict with the whole cookie masked, never a wildcard; the table-miss
  flow needs its typed words; a controller-owned flow warned;
- **edit**: actions in place by modify-strict (cookie kept); a priority or timeout change is a
  delete-strict and an add in one operation, said;
- **meters**: a response's meter recorded with its expiry, removed by `expire_meters` once no
  flow points at it; the band's drop count read twice and reported.
"""
import json

import pytest

from modules.sdn import flow_intent as F
from modules.sdn import flow_ops as O
from modules.sdn.drivers.base import Connection
from modules.sdn.drivers.ryu import RyuDriver, flow_from_ryu
from tests.sdn_fakes import Clock, FakeRyu, fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

BASE = "http://192.0.2.10:8080"
NET = "Default"
WITH_PEER = fixture("rest_with_peer.json")


def captured_table():
    entry = next(e for e in WITH_PEER if e["path"] == "/stats/flow/1")
    return [flow_from_ryu(1, e).as_dict() for e in json.loads(entry["body"])["1"]]


@pytest.fixture
def ctl(networks):  # noqa: F811 - the fixture
    fake = FakeRyu(BASE, flows={1: captured_table()})

    def driver(_network, name):
        return {"ok": True, "error": "", "connection": {"name": name, "own_cookies": [0]},
                "driver": RyuDriver(Connection(BASE), session=fake, clock=Clock(),
                                    sleep=lambda s: None)}

    fake.driver = driver
    return fake


def ask(*changes, response=False):
    return {"connection": "lab", "dpid": 1, "changes": list(changes), "response": response}


def drop(cookie=None, src="198.51.100.7", hard=120, priority=300):
    return {"do": "add_flow", "flow": {
        "table_id": 0, "priority": priority, "cookie": cookie or F.new_cookie(),
        "hard_timeout": hard, "match": {"eth_type": 0x0800, "ipv4_src": src}, "actions": []}}


def run(ctl, a, **kw):
    p = O.plan(NET, a, driver=ctl.driver)
    assert p["ok"], p["error"]
    return p, O.apply(NET, a, p["hash"], actor="op@example.com", actor_verified="access",
                      driver=ctl.driver, sleep=lambda s: None, **kw)


# ───────────────────────────────────────────────────────────────────────────── the plan

def test_the_plan_reads_and_writes_nothing_and_renders_each_request_and_its_undo(ctl):
    a = ask(drop())
    p = O.plan(NET, a, driver=ctl.driver)
    assert p["ok"] and ctl.writes == []
    (step,) = p["steps"]
    assert step["request"]["path"] == "/stats/flowentry/add"
    assert step["undo"]["path"] == "/stats/flowentry/delete_strict"
    body = json.loads(step["request"]["body"])
    assert body["match"] == {"eth_type": 2048, "ipv4_src": "198.51.100.7"} and body["actions"] == []
    assert json.loads(step["undo"]["body"])["cookie_mask"] == 2 ** 64 - 1
    assert O.plan(NET, a, driver=ctl.driver)["hash"] == p["hash"]


def test_the_hash_moves_when_the_flow_it_touches_moves(ctl):
    target = {"do": "remove_flow", "target": {"table_id": 0, "priority": 2, "cookie": 0,
                                              "match": {"in_port": 1, "eth_type": 2048,
                                                        "ip_proto": 6, "ipv4_src": "192.0.2.1",
                                                        "ipv4_dst": "192.0.2.2",
                                                        "tcp_dst": 22}}}
    before = O.plan(NET, ask(target), driver=ctl.driver)["hash"]
    hit = next(f for f in ctl.table[1] if f["match"].get("tcp_dst") == 22)
    hit["actions"] = [{"type": "OUTPUT", "port": 3}]
    assert O.plan(NET, ask(target), driver=ctl.driver)["hash"] != before


@pytest.mark.parametrize("change,words", [
    ({"do": "add_flow", "flow": {"priority": 10, "cookie": F.mercury_cookie(9), "actions": [],
                                 "match": {"eth_type": 0x0800, "tcp_dst": 22}}},
     "tcp_dst needs ip_proto 6"),
    ({"do": "add_flow", "flow": {"priority": 10, "cookie": 7, "actions": [],
                                 "match": {"in_port": 1}}},
     "carries Mercury's cookie, and 0x0000000000000007 is not one"),
    ({"do": "add_flow", "flow": {"priority": 100, "cookie": F.mercury_cookie(9), "actions": [],
                                 "match": {"eth_type": 2048, "ipv4_src": "192.0.2.0/24"}}},
     "the switch already holds a flow at table 0, priority 100 with this match"),
    ({"do": "add_flow", "flow": {"priority": 10, "cookie": F.mercury_cookie(9),
                                 "match": {"in_port": 1},
                                 "actions": [{"type": "METER", "meter_id": 7}]}},
     "the flow points at meter 7, and switch 1 holds meters"),
    ({"do": "remove_flow", "target": {"priority": 7, "match": {"in_port": 9}, "cookie": 0}},
     "no flow at table 0, priority 7, match in_port=9, cookie 0x0000000000000000"),
    ({"do": "add_meter", "meter": {"meter_id": 2, "flags": ["KBPS"],
                                   "bands": [{"type": "DSCP_REMARK", "rate": 10,
                                              "prec_level": 1}]}},
     "the switch's meter bands are ['DROP'], not DSCP_REMARK"),
    ({"do": "add_meter", "meter": {"meter_id": 2, "flags": ["KBPS"],
                                   "bands": [{"type": "DROP", "rate": 10},
                                             {"type": "DROP", "rate": 20}]}},
     "the meter has 2 bands and the switch allows 1 (max_bands)"),
    ({"do": "remove_meter", "meter_id": 1},
     "switch 1 holds meters none, not 1"),
    # The capture's flow at priority 90 points at METER:1 with no meter 1 on the switch.
    ({"do": "add_meter", "meter": {"meter_id": 1, "flags": ["KBPS"],
                                   "bands": [{"type": "DROP", "rate": 10}]}},
     "a flow already points at meter 1 on switch 1"),
])
def test_a_refusal_comes_before_any_request_naming_what_it_compared(ctl, change, words):
    p = O.plan(NET, ask(change), driver=ctl.driver)
    assert not p["ok"] and words in p["error"], p["error"]
    assert ctl.writes == []


@pytest.mark.parametrize("hard,words", [
    (0, "a response's flow carries a hard timeout from 1 to 3600 s"),
    (3601, "from 1 to 3600 s (the network's sdn_response_max_seconds), not 3601")])
def test_a_response_flow_carries_a_hard_timeout_within_the_network_s_ceiling(ctl, hard, words):
    p = O.plan(NET, ask(drop(hard=hard), response=True), driver=ctl.driver)
    assert not p["ok"] and words in p["error"]


def test_a_meter_in_use_is_not_removed(ctl):
    ctl.meter[1][1] = {"meter_id": 1, "flags": ["KBPS"], "bands": [{"type": "DROP",
                                                                   "rate": 1000}]}
    p = O.plan(NET, ask({"do": "remove_meter", "meter_id": 1}), driver=ctl.driver)
    assert not p["ok"] and "1 flow(s) still point at meter 1" in p["error"]


# ───────────────────────────────────────────────────────────────────────────── the apply

def test_a_moved_hash_sends_nothing_naming_both_hashes(ctl):
    a = ask(drop())
    p = O.plan(NET, a, driver=ctl.driver)
    out = O.apply(NET, a, "0" * 64, actor="op@example.com", driver=ctl.driver)
    assert out["outcome"] == "refused" and out["at"] == "hash"
    assert "000000000000" in out["error"] and p["hash"][:12] in out["error"]
    assert ctl.writes == []


def test_a_verified_add_is_recorded_as_installed_and_as_an_operation(ctl):
    a = ask(drop(hard=120), response=True)
    _p, out = run(ctl, a)
    assert out["outcome"] == "verified" and out["ok"]
    assert [c["state"] for c in out["verify"]["checks"]] == ["pass", "operator"]
    assert "testing traffic from the hosts is the operator's" in out["verify"]["checks"][-1]["words"]
    rows = F.read(NET)["rows"]
    assert [r["kind"] for r in rows] == ["installed", "operation"]
    assert rows[0]["hard_timeout"] == 120 and rows[1]["outcome"] == "verified"
    assert rows[1]["requests"][0]["path"] == "/stats/flowentry/add"
    assert out["counters"][0]["name"] == "drop counters"


def test_a_write_the_switch_did_not_apply_fails_verify_and_is_rolled_back(ctl):
    ctl.ignore = {"/stats/flowentry/add"}
    _p, out = run(ctl, ask(drop()))
    assert out["outcome"] == "rolled_back" and not out["ok"]
    assert "Verify failed: no flow with cookie" in out["error"]
    assert [w[0] for w in ctl.writes] == ["/stats/flowentry/add",
                                         "/stats/flowentry/delete_strict"]
    assert out["rollback"]["ok"] and out["rollback"]["read_back"][0]["state"] == "pass"
    assert [r["kind"] for r in F.read(NET)["rows"]] == ["operation"]


def test_a_refusal_mid_way_rolls_back_what_landed(ctl):
    meter = {"do": "add_meter", "meter": {"meter_id": 2, "flags": ["KBPS", "STATS"],
                                          "bands": [{"type": "DROP", "rate": 1000}]}}
    flow = drop()
    flow["flow"]["actions"] = [{"type": "METER", "meter_id": 2}, {"type": "OUTPUT", "port": 2}]
    ctl.fail = {"/stats/flowentry/add": 400}
    _p, out = run(ctl, ask(meter, flow))
    assert out["outcome"] == "rolled_back"
    assert "the controller refused request 2 of 2 (add_flow)" in out["error"]
    assert [w[0] for w in ctl.writes] == ["/stats/meterentry/add", "/stats/flowentry/add",
                                         "/stats/meterentry/delete"]
    assert ctl.meter[1] == {}


def test_a_held_switch_is_refused_by_name(ctl):
    from modules.nsot import device_ops

    a = ask(drop())
    p = O.plan(NET, a, driver=ctl.driver)
    with device_ops.hold(NET, O.hold_name("lab", 1), "sdn flows", "other@example.com"):
        import threading
        got = {}
        t = threading.Thread(target=lambda: got.update(O.apply(
            NET, a, p["hash"], actor="op@example.com", driver=ctl.driver)))
        t.start()
        t.join(10)
    assert got["at"] == "hold" and "other@example.com" in got["error"]
    assert ctl.writes == []


# ───────────────────────────────────────────────────────────────────────────── remove

def test_remove_is_delete_strict_by_place_and_whole_cookie(ctl):
    target = {"table_id": 0, "priority": 100, "cookie": 5567946962029772801,
              "match": {"eth_type": 2048, "ipv4_src": "192.0.2.0/255.255.255.0"}}
    p, out = run(ctl, ask({"do": "remove_flow", "target": target}))
    body = json.loads(p["steps"][0]["request"]["body"])
    assert body["cookie_mask"] == 2 ** 64 - 1 and body["priority"] == 100
    assert out["outcome"] == "verified"
    assert not any(f["cookie"] == 5567946962029772801 for f in ctl.table[1])
    assert "unauthorised flow" in p["words"][0]


def test_the_table_miss_flow_needs_its_typed_words(ctl):
    target = {"table_id": 0, "priority": 0, "cookie": 0, "match": {}}
    a = ask({"do": "remove_flow", "target": target})
    p = O.plan(NET, a, driver=ctl.driver)
    assert p["needs_typed"] == "remove table-miss"
    assert any("table-miss flow" in w for w in p["warnings"])
    assert any("reactive application may install it again" in w for w in p["warnings"])
    out = O.apply(NET, a, p["hash"], actor="op@example.com", driver=ctl.driver, typed="yes")
    assert out["outcome"] == "refused" and ctl.writes == []
    out = O.apply(NET, a, p["hash"], actor="op@example.com", driver=ctl.driver,
                  typed="remove table-miss", sleep=lambda s: None)
    assert out["outcome"] == "verified"


def test_removing_mercury_s_flow_withdraws_its_record(ctl):
    add = drop()
    run(ctl, ask(add))
    target = {k: add["flow"][k] for k in ("table_id", "priority", "match", "cookie")}
    _p, out = run(ctl, ask({"do": "remove_flow", "target": target}))
    assert out["outcome"] == "verified"
    assert F.intent(NET, "lab")["flows"] == []
    assert [r["kind"] for r in F.read(NET)["rows"]] == ["installed", "operation", "withdrawn",
                                                       "operation"]


# ───────────────────────────────────────────────────────────────────────────── edit

def test_an_edit_of_actions_is_modify_strict_keeping_the_cookie(ctl):
    add = drop()
    run(ctl, ask(add))
    target = {k: add["flow"][k] for k in ("table_id", "priority", "match", "cookie")}
    new = dict(add["flow"], actions=[{"type": "OUTPUT", "port": 2}], cookie=F.new_cookie())
    p, out = run(ctl, ask({"do": "edit_flow", "target": target, "flow": new}))
    assert [s["request"]["path"] for s in p["steps"]] == ["/stats/flowentry/modify_strict"]
    assert json.loads(p["steps"][0]["request"]["body"])["cookie"] == add["flow"]["cookie"]
    assert out["outcome"] == "verified"
    (rec,) = F.intent(NET, "lab")["flows"]
    assert rec["actions"] == [{"type": "OUTPUT", "port": 2}]


@pytest.mark.parametrize("field,value,why", [
    ("priority", 310, "a change of its priority"),
    ("hard_timeout", 60, "a change of its hard_timeout (OpenFlow 1.3 keeps a flow's timeouts "
                         "on a modify)")])
def test_a_place_or_timeout_change_is_a_remove_and_an_add_said(ctl, field, value, why):
    add = drop()
    run(ctl, ask(add))
    target = {k: add["flow"][k] for k in ("table_id", "priority", "match", "cookie")}
    new = dict(add["flow"], cookie=F.new_cookie(), **{field: value})
    p, out = run(ctl, ask({"do": "edit_flow", "target": target, "flow": new}))
    assert [s["request"]["path"] for s in p["steps"]] == ["/stats/flowentry/delete_strict",
                                                         "/stats/flowentry/add"]
    assert any(w.startswith(why[0].upper() + why[1:]) and "remove and an add as one action"
               in w for w in p["words"])
    assert out["outcome"] == "verified"
    (rec,) = F.intent(NET, "lab")["flows"]
    assert rec["cookie"] == new["cookie"] and rec[field] == value


def test_edit_is_for_mercury_s_own_flows(ctl):
    target = {"table_id": 0, "priority": 1, "cookie": 0,
              "match": {"in_port": 1, "eth_dst": "00:00:00:00:00:02",
                        "eth_src": "00:00:00:00:00:01"}}
    p = O.plan(NET, ask({"do": "edit_flow", "target": target,
                         "flow": {"priority": 1, "cookie": F.new_cookie(), "actions": [],
                                  "match": target["match"]}}), driver=ctl.driver)
    assert not p["ok"] and "edit is for Mercury's own recorded flows" in p["error"]


# ───────────────────────────────────────────────────────────────────────────── meters

def test_a_rate_limit_s_meter_counts_and_expires(ctl):
    meter = {"do": "add_meter", "meter": {"meter_id": 2, "flags": ["KBPS", "STATS", "BURST"],
                                          "bands": [{"type": "DROP", "rate": 1000,
                                                     "burst_size": 100}]}}
    flow = drop(hard=60)
    flow["flow"]["actions"] = [{"type": "METER", "meter_id": 2}, {"type": "OUTPUT", "port": 2}]
    reads = {"n": 0}

    def count(fake):
        reads["n"] += 1
        m = fake.meter[1].get(2)
        if m is not None:
            m["packet_in"] = m.get("packet_in", 0) + 400
            m["dropped"] = m.get("dropped", 0) + 150

    ctl.count = count
    _p, out = run(ctl, ask(meter, flow, response=True), now=lambda: 1000.0)
    assert out["outcome"] == "verified"
    (said,) = [c for c in out["counters"] if c["name"] == "meter counters"]
    assert said["dropped"] > 0 and said["words"].startswith("limiting: meter 2 dropped")
    (m,) = F.meters(NET)["meters"]
    assert m["expires_at"] == 1060.0
    # Not yet expired: kept. Past it, while the flow is still installed: kept, said why.
    assert O.expire_meters(NET, driver=ctl.driver, now=lambda: 1001.0)["removed"] == []
    kept = O.expire_meters(NET, driver=ctl.driver, now=lambda: 2000.0)
    assert kept["removed"] == [] and "still point at meter 2" in kept["kept"][0]["why"]
    # The flow expired at its hard timeout (the switch removed it): the meter goes.
    ctl.table[1] = [f for f in ctl.table[1] if f["cookie"] != flow["flow"]["cookie"]]
    gone = O.expire_meters(NET, driver=ctl.driver, now=lambda: 2000.0)
    assert gone["removed"] == [2] and ctl.meter[1] == {}, gone
    assert F.meters(NET)["meters"] == []


def test_an_ipv6_source_drop_renders_eth_type_86dd(ctl):
    a = ask({"do": "add_flow", "flow": {"priority": 300, "cookie": F.new_cookie(),
                                        "hard_timeout": 60, "actions": [],
                                        "match": {"eth_type": "0x86dd",
                                                  "ipv6_src": "2001:db8::7"}}})
    p, out = run(ctl, a)
    assert json.loads(p["steps"][0]["request"]["body"])["match"] == {
        "eth_type": 34525, "ipv6_src": "2001:db8::7"}
    assert out["outcome"] == "verified"
