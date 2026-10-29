"""The Lab 8 run on Open vSwitch 2.17.12 under Ryu 4.34, replayed (PHASE8_PLAN 17.1 S4 to S8;
tests/fixtures/sdn/lab8/, its README says when and how each was captured, 2026-10-27).

Each answer is Ryu's own, captured from the lab's controller while the threat ran in Mininet:
- **the scan** (h1 SYN-scanning h3): the real `collect_threat_data` and scan rule over the
  capture find it at high confidence on L4 flows; its drop is above every flow that could match
  it, and NOT tied with the controller's LLDP flow at 65535 (the run's first preview drew
  priority 65535 from it, which this holds against);
- **a table with only L2 flows** (the first topology, after pings): coverage L2, so the scan
  rule cannot count ports there, said;
- **the flood** (h2 to h4, 1,782 packets a second): its rate-limit takes meter 1 and the
  controller's own forwarding for the pair (OUTPUT:3) from the captured table (Mercury's applied
  response taken out of it: the one edit), and the switch's captured meter features;
- **the unauthorised flow** (cookie 0xbad0 on s2): detected, and removed by delete-strict with
  the whole cookie masked;
- **modify-strict on OVS** keeps a flow's cookie and timeouts and replaces only its actions
  (measured): what `flow_ops.MODIFY_KEEPS` declares, and what `FakeRyu` does.
"""
import json

import pytest

from modules.sdn import closed_loop as CL
from modules.sdn import connections as C
from modules.sdn import detect as D
from modules.sdn import flow_intent as F
from modules.sdn import flow_ops as O
from modules.sdn.drivers.ryu import flow_from_ryu
from tests.sdn_fakes import Clock, FakeRyu, Replay, lab8
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

BASE = "http://192.0.2.10:8080"
VALUES = dict(D.THRESHOLDS)


@pytest.fixture
def lab(networks):  # noqa: F811 - the fixture, used
    C.save_connection("Default", {"name": "lab", "kind": "ryu", "url": BASE}, actor="op")
    return networks


def collect(entries, at=1_790_000_000.0):
    clock = Clock()
    session = Replay(entries, BASE)
    return CL.collect_threat_data(
        "Default", 2.0, sleep=lambda s: setattr(clock, "now", clock.now + s), clock=clock,
        now=lambda: at, driver=lambda net, name: C.driver_for(net, name, session=session))


def flows_of(entries, dpid, drop_cookie=None):
    body = next(e for e in entries if e["path"] == f"/stats/flow/{dpid}")["body"]
    return [flow_from_ryu(dpid, e).as_dict() for e in json.loads(body)[str(dpid)]
            if e["cookie"] != drop_cookie]


def features_of(entries, dpid):
    body = next(e for e in entries if e["path"] == f"/stats/meterfeatures/{dpid}")["body"]
    return json.loads(body)[str(dpid)][0]


def fake_with(flows, dpid, features=None):
    fake = FakeRyu(BASE, flows={dpid: flows}, features=features, dpids=(dpid,))
    fake.driver = lambda net, name: C.driver_for(net, name, session=fake, sleep=lambda s: None)
    return fake


def captured_topology() -> dict:
    """The lab controller's topology REST, captured with the fabric attached
    (tests/fixtures/sdn/ryu/topology_rest.json): its answers by path."""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "sdn", "ryu",
                        "topology_rest.json")
    with open(path, encoding="utf-8") as fh:
        entries = json.load(fh)
    return {e["path"]: json.loads(e["body"]) for e in entries
            if e["path"].startswith("/v1.0/topology/")}


def l2_only_switch(topology):
    """s1 as the walk found it at its preview (the operator, 2026-10-27): the scan's L4 flows
    expired, only the controller's standing flows left (the Lab 8 run's L2-only capture: LLDP,
    the match-all, the L2 pairs); its controller's topology *topology*, or none (Ryu's 404)."""
    l2 = lab8("l2_only_s1.json")
    fake = FakeRyu(BASE, flows={1: flows_of(l2, 1)}, features=features_of(l2, 1), dpids=(1,),
                   topology=topology)
    fake.driver = lambda net, name: C.driver_for(net, name, session=fake, sleep=lambda s: None)
    return fake, flows_of(l2, 1)


@pytest.mark.usefixtures("lab")
def test_a_scan_s_rate_limit_takes_every_host_s_port_from_the_topology_with_only_l2_flows_left():
    """The walk's step 10a found it (the operator, 2026-10-27, high B): by a person's preview
    the scan's L4 flows have expired and s1 holds only the controller's L2 pair, so no IP flow
    gives a port. The ports come from the controller's topology (the real capture: h1 and h2
    on s1 ports 1 and 2, h3 and h4 on s2, the s1-s2 link on port 3 of each): one meter, and h1's
    traffic to every other host through it, the scan's target first: h3 and h4 out of port 3,
    h2 out of port 2; each above the controller's L2 flows as well as its L4 ones; the two
    hosts the controller lists with no IPv4 address named as not metered, and the gap said."""
    (d,) = D.scan(collect(lab8("scan_s1.json")), VALUES)["detections"]
    fake, table = l2_only_switch(captured_topology())
    assert not [f for f in table if "ipv4_src" in (f.get("match") or {})], "premise: no IP flow"
    preview = CL.respond_to_threat("Default", d, "rate_limit_source", driver=fake.driver)
    assert preview["ok"], preview["error"]
    meter, *metered = preview["plan"]["steps"]
    meter_id = json.loads(meter["request"]["body"])["meter_id"]
    bodies = [json.loads(s["request"]["body"]) for s in metered]
    out = {b["match"]["ipv4_dst"]: [a["port"] for a in b["actions"] if a["type"] == "OUTPUT"]
           for b in bodies}
    assert out == {"192.0.2.3": [3], "192.0.2.2": [2], "192.0.2.4": [3]}
    assert list(out)[0] == d["targets"][0] == "192.0.2.3"
    assert all(b["match"]["ipv4_src"] == "192.0.2.1" and
               b["actions"][0] == {"type": "METER", "meter_id": meter_id} for b in bodies)
    l2_top = max(f["priority"] for f in table if "eth_src" in (f.get("match") or {}))
    assert all(b["priority"] > l2_top for b in bodies), "above the controller's L2 flows"
    assert preview["params"]["ports_from"] == "the controller's topology"
    assert preview["params"]["not_metered"] == ["12:da:aa:70:da:9f (no IPv4 address listed)",
                                                "d2:e6:76:c9:06:24 (no IPv4 address listed)"]
    (gap,) = [w for w in preview["plan"]["will_not"] if "not metered" in w]
    assert "to a host the controller's topology does not list yet is not metered" in gap
    assert "Only 192.0.2.1's IPv4 traffic is metered" in gap
    done = CL.respond_to_threat("Default", None, confirm={"ask": preview["ask"],
                                                          "hash": preview["plan"]["hash"]},
                                actor="op@example.com", actor_verified="access",
                                driver=fake.driver, sleep=lambda s: None, counter_interval=0)
    assert done["outcome"] == "verified", done["error"]


@pytest.mark.usefixtures("lab")
def test_with_no_topology_and_only_l2_flows_the_rate_limit_is_refused_naming_both():
    """Neither source gives a port (no topology application, the L2-only table): refused before
    any request, naming the flows as the source tried and why the topology gave none."""
    (d,) = D.scan(collect(lab8("scan_s1.json")), VALUES)["detections"]
    fake, _table = l2_only_switch(None)
    preview = CL.respond_to_threat("Default", d, "rate_limit_source", driver=fake.driver)
    assert not preview["ok"]
    assert "no forwarding port for 192.0.2.1's traffic is known on switch 1" in preview["error"]
    assert "the switch's flows (the controller's topology: " in preview["error"]
    assert fake.writes == []


def _mac_only_flood(port):
    """The walk's flood on s1 (C2002, 2026-10-27 step 23): its flows matched MAC addresses only,
    so it named no source. The capture's scan detection with one edit: a flood on *port* with no
    source, as the flood rule writes one over MAC-only flows."""
    (d,) = D.scan(collect(lab8("scan_s1.json")), VALUES)["detections"]
    return dict(d, rule="flood", source=None, sources=[], port=port, targets=[],
                subject={"kind": "port", "value": port})


@pytest.mark.usefixtures("lab")
def test_a_flood_naming_no_source_takes_the_host_on_its_port_from_the_topology():
    """C2002: the controller lists h2 (192.0.2.2, 00:00:00:00:00:02) on s1's port 2, so the
    flood that entered there is dropped by that address, and the preview says where it came
    from."""
    fake, _table = l2_only_switch(captured_topology())
    preview = CL.respond_to_threat("Default", _mac_only_flood(2), "drop_source",
                                   driver=fake.driver)
    assert preview["ok"], preview["error"]
    body = json.loads(preview["plan"]["steps"][0]["request"]["body"])
    assert body["match"] == {"eth_type": 0x0800, "ipv4_src": "192.0.2.2"}
    assert preview["params"]["source"] == "192.0.2.2"
    # The words of the one resolver the detection uses too (`detect.port_source`, C2002's
    # second part): the response reads the topology itself only for a detection that did not.
    assert preview["params"]["source_from"] == (
        "from the controller's topology: the one host on port 2, 192.0.2.2 (00:00:00:00:00:02)")
    assert preview["ask"]["detection"]["source_from"] == preview["params"]["source_from"]
    assert fake.writes == []


@pytest.mark.usefixtures("lab")
@pytest.mark.parametrize("port,topology,said", [
    (1, "without h1", "the controller's topology lists 12:da:aa:70:da:9f on port 1, with no "
                      "address to match"),
    (7, "captured", "the controller's topology lists no host on port 7"),
    (2, None, "the controller's topology could not be read (HTTP 404"),
    (3, "captured", "port 3 is a link to switch 0000000000000002, so the source is not "
                    "attached here"),
], ids=["no-ipv4", "no-host", "no-topology", "link"])
def test_a_flood_with_no_source_the_topology_cannot_name_says_why(port, topology, said):
    """With no host to choose, the refusal says why and never offers a choice (the operator,
    2026-10-27: "never 'choose one' with nothing to choose"). Port 1 without h1 holds only a
    host whose one address is link-local (fe80::), which no response can match; port 3 is
    s1's link to s2."""
    topo = captured_topology() if topology else None
    if topology == "without h1":
        # The capture with h1 (00:00:00:00:00:01, port 1's IPv4 host) left out.
        hosts = topo["/v1.0/topology/hosts"]
        topo["/v1.0/topology/hosts"] = [h for h in hosts if h["mac"] != "00:00:00:00:00:01"]
    fake, _table = l2_only_switch(topo)
    got = CL.respond_to_threat("Default", _mac_only_flood(port), "drop_source",
                               driver=fake.driver)
    assert not got["ok"] and said in got["error"], got["error"]
    assert got["error"].startswith("the detection names no source to act on, and there is no "
                                   "host to choose: not named: ")
    assert "choose one" not in got["error"]
    assert fake.writes == []


@pytest.mark.usefixtures("lab")
def test_the_scan_is_found_on_l4_flows_and_its_drop_clears_the_lldp_flow():
    entries = lab8("scan_s1.json")
    got = collect(entries)
    (sw,) = got["controllers"][0]["switches"]
    assert sw["coverage"]["granularity"] == "L4" and sw["active_flows"] > 200
    (d,) = D.scan(got, VALUES)["detections"]
    assert (d["source"], d["targets"], d["confidence"]) == ("192.0.2.1", ["192.0.2.3"], "high")
    assert d["measurement"]["value"] >= 200
    fake = fake_with(flows_of(entries, 1), 1, features_of(entries, 1))
    assert any(f["priority"] == 65535 for f in fake.table[1]), "the LLDP flow is in the capture"
    preview = CL.respond_to_threat("Default", d, "drop_source", {"hard_timeout": 90},
                                   driver=fake.driver)
    assert preview["ok"], preview["error"]
    body = json.loads(preview["plan"]["steps"][0]["request"]["body"])
    assert body["priority"] == 300 and body["hard_timeout"] == 90
    assert body["match"] == {"eth_type": 2048, "ipv4_src": "192.0.2.1"}


@pytest.mark.usefixtures("lab")
def test_a_table_of_l2_flows_cannot_show_a_scan_by_port():
    got = collect(lab8("l2_only_s1.json"))
    (sw,) = got["controllers"][0]["switches"]
    assert sw["coverage"]["granularity"] == "L2" and not sw["coverage"]["scan_by_ports"]
    assert "cannot show a per-port scan" in sw["coverage"]["words"]


@pytest.mark.usefixtures("lab")
def test_the_flood_s_rate_limit_meters_the_controller_s_forwarding():
    entries = lab8("flood_s1.json")
    (d,) = lab8("flood_detection.json")
    assert (d["rule"], d["source"], d["targets"]) == ("flood", "192.0.2.2", ["192.0.2.4"])
    # The run's network was the harness's "lab8"; the test's is Default (the one edit).
    d = dict(d, network="Default")
    mercury = next(f["cookie"] for f in flows_of(entries, 1) if F.is_mercury(f["cookie"]))
    feats = features_of(entries, 1)
    assert (feats["max_bands"], feats["band_types"]) == (1, ["DROP"])
    fake = fake_with(flows_of(entries, 1, drop_cookie=mercury), 1, feats)
    preview = CL.respond_to_threat("Default", d, "rate_limit_source", {"hard_timeout": 120},
                                   driver=fake.driver)
    assert preview["ok"], preview["error"]
    meter, flow = preview["plan"]["steps"]
    assert json.loads(meter["request"]["body"])["meter_id"] == 1
    body = json.loads(flow["request"]["body"])
    assert body["actions"] == [{"meter_id": 1, "type": "METER"}, {"port": 3, "type": "OUTPUT"}]
    assert body["match"] == {"eth_type": 2048, "ipv4_dst": "192.0.2.4", "ipv4_src": "192.0.2.2"}
    out = CL.respond_to_threat("Default", None, "rate_limit_source", confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        driver=fake.driver, sleep=lambda s: None)
    assert out["outcome"] == "verified"


@pytest.mark.usefixtures("lab")
def test_the_unauthorised_redirect_is_found_and_removed_strictly():
    entries = lab8("unauthorised_s2.json")
    got = collect(entries)
    dets = D.unauthorised(got, F.intent("Default"))["detections"]
    (d,) = dets
    assert d["measurement"]["cookie"] == "0x000000000000bad0" and d["dpid"] == 2
    fake = fake_with(flows_of(entries, 2), 2)
    preview = CL.respond_to_threat("Default", d, driver=fake.driver)
    assert preview["ok"], preview["error"]
    (step,) = preview["plan"]["steps"]
    body = json.loads(step["request"]["body"])
    assert step["request"]["path"] == "/stats/flowentry/delete_strict"
    assert (body["cookie"], body["cookie_mask"], body["priority"]) == (0xBAD0, 2 ** 64 - 1, 100)
    out = CL.respond_to_threat("Default", None, "remove_flow", confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        driver=fake.driver, sleep=lambda s: None)
    assert out["outcome"] == "verified"
    assert not any(f["cookie"] == 0xBAD0 for f in fake.table[2])


def test_modify_strict_on_ovs_keeps_the_cookie_and_timeouts():
    m = lab8("modify_strict.json")
    (before,), (after,) = m["after_add"], m["after_modify"]
    sent = json.loads(m["modify_sent"]["request"]["body"])
    assert sent["cookie"] != before["cookie"] and sent["hard_timeout"] != before["hard_timeout"]
    assert {k: after[k] for k in O.MODIFY_KEEPS} == {k: before[k] for k in O.MODIFY_KEEPS}
    assert after["actions"] == [{"port": "CONTROLLER", "type": "OUTPUT"}] != before["actions"]
    assert m["after_cleanup"] == []
