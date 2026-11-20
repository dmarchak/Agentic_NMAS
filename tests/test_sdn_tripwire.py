"""The scan tripwire (Lab 9 A, the operator's go of 2026-11-20 after the step-4 measurement) and
a scan's rate limit in packets a second (the operator, 2026-11-20: a 1 Mbit/s cap does not slow
a 250 pps SYN scan).

**The data.** `closed_loop.tripwire_ask` runs over tests/test_sdn_policy_intent.py's Lab 9 world
(the NSOT export built by the real `export.build` from the Lab 9 records, Ryu's captured
switches, FakeRyu behind the real Ryu driver), with OVS server 1's table a team pipeline whose
table 0 misses to its forwarding table 2. `detect._tripwire_scans` runs inside the real
`detect.scan` over a collection the real `collect_threat_data` makes from Ryu's captured flows
(tests/test_sdn_collect.py), with tripwire flows added as Ryu would answer them: the captured
IPv4 L4 flow copied per port, its destination the source's subnet, its cookie a tripwire's and
its packet count set.

- a tripwire is 16 flows from the source to the subnet NetBox records it in, one TCP port each,
  going on by the switch's own goto, for 120 s, each cookie a tripwire's (IPv4 and IPv6);
- refused, naming why, where NetBox records no subnet for the source, or the switch's own flow
  does not go on by a goto;
- six or more tripwires hit by one source is a scan of high confidence, basis "tripwire"; five
  is not; tripwires are left out of coverage and the scan rule's sightings;
- a scan's rate limit defaults to 20 pps with a burst of 10, and a kbit/s one is refused for
  it; a flood's keeps its kbit/s default;
- a fresh ordinary Mercury cookie never carries the tripwire's tag.
"""
import copy
import ipaddress
import json

import pytest

from modules.sdn import closed_loop as CL
from modules.sdn import detect as D
from modules.sdn import flow_intent as F
from tests.test_sdn_collect import captured_flows
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_detect import T0, V4_L4, VALUES, collect, save
from tests.test_sdn_policy_intent import CONN, NET, OVS1, lab  # noqa: F401 - the fixture

H1_V4, H1_V6 = "198.51.100.11", "2001:db8:c8::11"
TEAM = 0x9A00000000000001


def _pipeline(lab):  # noqa: F811 - the fixture's value
    """OVS server 1 as the team's pipeline: table 0 misses to table 2, which forwards."""
    lab.fake.table[OVS1] = [
        {"dpid": OVS1, "table_id": 0, "priority": 0, "cookie": TEAM, "match": {},
         "actions": [{"type": "GOTO_TABLE", "table_id": 2}], "idle_timeout": 0,
         "hard_timeout": 0},
        {"dpid": OVS1, "table_id": 2, "priority": 1000, "cookie": TEAM + 1,
         "match": {"eth_dst": "02:00:00:00:00:05"}, "actions": [{"type": "OUTPUT", "port": 7}],
         "idle_timeout": 0, "hard_timeout": 0}]


def _watched(source, dpid=OVS1):
    return {"rule": "high_rate", "source": source, "connection": CONN, "dpid": dpid,
            "dpid_hex": f"{dpid:016x}"}


@pytest.mark.parametrize("source,eth,fam,subnet", [
    (H1_V4, 0x0800, "ipv4", "198.51.100.0/24"),
    (H1_V6, 0x86DD, "ipv6", "2001:db8:c8::/64")], ids=["ipv4", "ipv6"])
def test_a_tripwire_is_one_flow_a_port_to_the_source_s_subnet_going_on_by_the_goto(
        lab, source, eth, fam, subnet):  # noqa: F811 - the fixture
    _pipeline(lab)
    got = CL.tripwire_ask(NET, _watched(source), driver=lab.driver)
    assert got["ok"], got["error"]
    changes = got["ask"]["changes"]
    assert got["ask"]["dpid"] == OVS1 and got["ask"]["connection"] == CONN
    assert [c["flow"]["match"]["tcp_dst"] for c in changes] == list(CL.TRIPWIRE_PORTS)
    for c in changes:
        f = c["flow"]
        assert c["do"] == "add_flow" and f["table_id"] == 0
        assert f["match"] == {"eth_type": eth, f"{fam}_src": source, f"{fam}_dst": subnet,
                              "ip_proto": 6, "tcp_dst": f["match"]["tcp_dst"]}
        assert f["actions"] == [{"type": "GOTO_TABLE", "table_id": 2}]
        assert f["hard_timeout"] == CL.TRIPWIRE_SECONDS == 120 and f["idle_timeout"] == 0
        assert F.is_tripwire(f["cookie"]) and F.is_mercury(f["cookie"])
        # One above the team's own table-0 flow it meets (the priority-0 goto), so every
        # Mercury response (at least RESPONSE_PRIORITY_FLOOR) sits above it (review 1).
        assert f["priority"] == 1
    assert len({c["flow"]["cookie"] for c in changes}) == len(changes), "a cookie each"
    assert subnet in got["words"] and "A scan beyond" in got["words"]
    assert lab.fake.writes == [], "an ask is only built, never sent"


def test_a_source_netbox_records_no_subnet_for_is_refused(lab):  # noqa: F811 - the fixture
    _pipeline(lab)
    got = CL.tripwire_ask(NET, _watched("198.51.100.200"), driver=lab.driver)
    assert not got["ok"] and got["ask"] is None
    assert "NetBox records no subnet for 198.51.100.200" in got["error"], got["error"]


def test_a_switch_whose_own_flow_does_not_go_on_by_a_goto_is_refused(lab):  # noqa: F811
    """The world's table-miss sends to the controller: a tripwire there would change where the
    source's traffic goes, so none is built, naming the port and the switch's own flow."""
    got = CL.tripwire_ask(NET, _watched(H1_V4), driver=lab.driver)
    assert not got["ok"] and got["ask"] is None
    assert "goes on only by the switch's own goto" in got["error"], got["error"]
    assert "TCP 21 from 198.51.100.11" in got["error"]


def test_a_watched_row_with_no_source_is_refused(lab):  # noqa: F811 - the fixture
    got = CL.tripwire_ask(NET, dict(_watched(H1_V4), source=""), driver=lab.driver)
    assert not got["ok"] and "names no one source address" in got["error"]


# ─────────────────────────────────────────────────────────────── the detection the tripwire makes

SUBNET = "192.0.2.0/24"


def _tripwires(hit, ports=None, src=V4_L4):
    """Tripwire flows from *src* as Ryu answers them (one a port of *ports*, default
    `TRIPWIRE_PORTS`), the first *hit* with packets."""
    ports = CL.TRIPWIRE_PORTS if ports is None else ports
    base = next(f for f in captured_flows()
                if f["match"].get("nw_src") == src[0] and f["match"].get("tp_dst") == src[1])
    out = []
    for n, port in enumerate(ports):
        f = copy.deepcopy(base)
        f["match"]["tp_dst"] = port
        f["match"]["nw_dst"] = SUBNET
        f["cookie"] = F.tripwire_cookie()
        f["packet_count"] = 3 if n < hit else 0
        f["byte_count"] = 180 if n < hit else 0
        out.append(f)
    return out


@pytest.fixture
def saved(networks):  # noqa: F811 - the fixture, used
    save()
    return networks


@pytest.mark.usefixtures("saved")
def test_six_tripwires_hit_by_one_source_is_a_scan_of_high_confidence():
    flows = captured_flows() + _tripwires(D.TRIPWIRE_NEED)
    out = D.scan(collect(T0, flows=flows), VALUES)
    (d,) = [x for x in out["detections"] if x.get("basis") == "tripwire"]
    assert d["rule"] == "scan" and d["source"] == V4_L4[0]
    assert d["confidence"] == "high"
    assert d["measurement"]["value"] == D.TRIPWIRE_NEED
    assert d["measurement"]["of"] == len(CL.TRIPWIRE_PORTS)
    # The subnet watched is no one host, so it is said, never a response's target.
    assert d["targets"] == [] and d["measurement"]["watched"] == [SUBNET]
    assert SUBNET in d["words"]


@pytest.mark.usefixtures("saved")
def test_five_tripwires_hit_is_no_scan_and_tripwires_are_never_the_rule_s_sightings():
    """Five hit is under the need; and the sixteen tripwires (sixteen destination ports from one
    source) are never counted as the scan rule's own sightings."""
    flows = captured_flows() + _tripwires(D.TRIPWIRE_NEED - 1)
    # The rule's own need lowered under the sixteen, so counting them would make a scan.
    values = dict(VALUES, sdn_scan_ports=len(CL.TRIPWIRE_PORTS) - 4)
    out = D.scan(collect(T0, flows=flows), values)
    assert [x for x in out["detections"] if x["rule"] == "scan"] == [], out["detections"]


def test_coverage_leaves_tripwires_out():
    from modules.sdn.drivers.ryu import flow_from_ryu
    plain = [flow_from_ryu(1, e).as_dict() for e in captured_flows()]
    wires = [flow_from_ryu(1, e).as_dict() for e in _tripwires(16)]
    assert all(F.is_tripwire(w["cookie"]) for w in wires), "premise: the cookies survive"
    assert CL.coverage(plain + wires) == CL.coverage(plain)


# ─────────────────────────────────────────────────────────────── the cookie's tag

def test_is_tripwire_only_for_a_tripwire_cookie():
    assert F.is_tripwire(F.tripwire_cookie())
    assert not F.is_tripwire(F.mercury_cookie(1))
    assert not F.is_tripwire(TEAM)
    assert not F.is_tripwire(str(F.tripwire_cookie()))
    assert not F.is_tripwire(True)


def test_an_ordinary_cookie_drawn_with_the_tag_is_drawn_again(monkeypatch):
    drawn = iter([(F.TRIPWIRE_TAG << 32) | 7, 0x1234])
    monkeypatch.setattr(F.secrets, "randbits", lambda bits: next(drawn))
    got = F.new_cookie()
    assert got == F.mercury_cookie(0x1234) and not F.is_tripwire(got)


# ─────────────────────────────────────────────────────────────── a scan's rate limit

def test_the_default_rate_limit_is_packets_a_second_for_a_scan_and_kbit_for_a_flood():
    pps = {"unit": "pktps", "rate": 20, "burst": 10}
    assert CL.rate_limit_default("scan") == pps
    assert CL.rate_limit_default("flood") == CL.RATE_LIMIT_DEFAULT
    # A watched High packet rate is answered as the scan rule's, in packets a second; a
    # watched large-packet stream as the flood rule's, in kbit/s (`answered_rule`).
    rate = CL.answered_rule({"rule": "high_rate", "basis": "rate"})
    large = CL.answered_rule({"rule": "high_rate", "basis": "large_packets"})
    assert (CL.rate_limit_default(rate), CL.rate_limit_default(large)) == (
        pps, CL.RATE_LIMIT_DEFAULT)
    assert CL.RATE_LIMIT_DEFAULT["unit"] == "kbps"
    got = CL.rate_limit_default("scan")
    got["rate"] = 1
    assert CL.SCAN_RATE_LIMIT_DEFAULT["rate"] == 20, "a copy, never the table itself"


@pytest.mark.usefixtures("saved")
def test_a_kbit_rate_limit_for_a_scan_is_refused_before_any_request():
    from tests.test_sdn_detect import scan_flows
    from tests.test_sdn_respond import scan_detection, switch_with, without_live_drop
    flows = scan_flows(25)
    d = scan_detection(flows)
    fake = switch_with(without_live_drop(flows))
    got = CL.respond_to_threat("Default", d, "rate_limit_source",
                               params={"unit": "kbps", "rate": 1000, "burst": 100},
                               driver=fake.driver)
    assert not got["ok"], got
    assert "a scan's rate limit is in packets a second (pktps), not kbps" in got["error"]
    assert fake.writes == []
    pps = CL.respond_to_threat("Default", d, "rate_limit_source", driver=fake.driver)
    assert pps["ok"], pps["error"]
    meter = json.loads(pps["plan"]["steps"][0]["request"]["body"])
    assert meter["bands"] == [{"burst_size": 10, "rate": 20, "type": "DROP"}]
    assert "PKTPS" in meter["flags"]


def _sent(lab, got):  # noqa: F811 - the fixture's value
    """The ask's flows as the switch would hold them (the confirm's result, without a run)."""
    for c in got["ask"]["changes"]:
        lab.fake.table[OVS1].append(dict(c["flow"], dpid=OVS1, packet_count=0, byte_count=0))


def test_a_second_set_beside_a_live_one_is_refused(lab):  # noqa: F811 - the fixture
    """The review of 94fa79c8 (2): a second set would count one host's ordinary ports twice."""
    _pipeline(lab)
    first = CL.tripwire_ask(NET, _watched(H1_V4), driver=lab.driver)
    assert first["ok"], first["error"]
    _sent(lab, first)
    again = CL.tripwire_ask(NET, _watched(H1_V4), driver=lab.driver)
    assert not again["ok"] and "already on switch" in again["error"], again
    other = CL.tripwire_ask(NET, _watched(H1_V6), driver=lab.driver)
    assert other["ok"], "another address of the host is its own set: " + other["error"]


def test_a_tripwire_under_mercury_s_own_live_drop_of_the_source_is_refused(lab):  # noqa: F811
    _pipeline(lab)
    lab.fake.table[OVS1].append({
        "dpid": OVS1, "table_id": 0, "priority": 300, "cookie": F.mercury_cookie(0x77),
        "match": {"eth_type": 0x0800, "ipv4_src": H1_V4}, "actions": [], "idle_timeout": 0,
        "hard_timeout": 600})
    got = CL.tripwire_ask(NET, _watched(H1_V4), driver=lab.driver)
    assert not got["ok"] and "already drops or meters TCP 21" in got["error"], got


def test_a_tripwire_sits_under_any_response_to_its_source(lab):  # noqa: F811 - the fixture
    """The review of 94fa79c8 (1): a response is placed at least RESPONSE_PRIORITY_STEP above
    the team's flows it meets, so a tripwire one above them is always under it, and a drop of
    the source takes the tripwire's ports too."""
    from modules.sdn import flow_ops
    _pipeline(lab)
    lab.fake.table[OVS1].append({
        "dpid": OVS1, "table_id": 0, "priority": 1200, "cookie": TEAM + 7,
        "match": {"eth_type": 0x0800, "ip_proto": 6},
        "actions": [{"type": "GOTO_TABLE", "table_id": 2}], "idle_timeout": 0,
        "hard_timeout": 0})
    got = CL.tripwire_ask(NET, _watched(H1_V4), driver=lab.driver)
    assert got["ok"], got["error"]
    wires = {c["flow"]["priority"] for c in got["ask"]["changes"]}
    assert wires == {1201}, "one above the team's TCP flow it meets"
    flows = lab.driver(NET, CONN)["driver"].flows(OVS1)["flows"]
    drop_at = flow_ops.response_priority(flows, match={"eth_type": 0x0800, "ipv4_src": H1_V4})
    assert drop_at > max(wires), (drop_at, wires)


@pytest.mark.usefixtures("saved")
def test_a_response_level_with_a_live_tripwire_of_its_source_is_refused():
    """The review of 94fa79c8 (1): where a response would go at or under a live tripwire of its
    source (one planted there), the tripwire would carry its port past it: refused, naming it."""
    from tests.test_sdn_detect import scan_flows
    from tests.test_sdn_respond import scan_detection, switch_with, without_live_drop
    flows = scan_flows(25)
    d = scan_detection(flows)
    from modules.sdn.drivers.ryu import flow_from_ryu
    (wire,) = _tripwires(0, ports=(80,))
    wire["priority"] = 60000
    # Recorded, as the flow editor's confirm records a tripwire it sent: a response leaves
    # Mercury's recorded flows out of what it must climb above.
    F.record_installed("Default", connection="ctl-1", flow=flow_from_ryu(1, wire).as_dict(),
                       actor="op@example.com", response={"id": "tw-1", "action": "tripwire"})
    fake = switch_with(without_live_drop(flows) + [wire])
    got = CL.respond_to_threat("Default", d, "drop_source", driver=fake.driver)
    assert not got["ok"], got
    assert "Mercury's tripwire for 192.0.2.1" in got["error"] and "60000" in got["error"]
    assert fake.writes == []


@pytest.mark.usefixtures("saved")
def test_the_tripwire_scan_s_rate_limit_is_metered_in_packets_a_second():
    """End to end: the tripwire's own scan detection (no target, a subnet watched) answered by
    a rate limit: the pps meter and the source's flows through it."""
    from tests.test_sdn_respond import switch_with, without_live_drop
    flows = captured_flows() + _tripwires(D.TRIPWIRE_NEED)
    (d,) = [x for x in D.scan(collect(T0, flows=flows), VALUES)["detections"]
            if x.get("basis") == "tripwire"]
    fake = switch_with(without_live_drop(captured_flows()))
    got = CL.respond_to_threat("Default", d, "rate_limit_source", driver=fake.driver)
    assert got["ok"], got["error"]
    meter, *pairs = got["plan"]["steps"]
    assert json.loads(meter["request"]["body"])["bands"] == [
        {"burst_size": 10, "rate": 20, "type": "DROP"}]
    assert pairs, "the source's flows through the meter"


@pytest.mark.usefixtures("saved")
@pytest.mark.parametrize("case", ["unsupported-counter", "one-port-twice"])
def test_hits_are_distinct_ports_with_a_counter(case):
    """The review of 94fa79c8 (2 and 7): a switch's all-ones counter is unknown, never a hit;
    six flows on three ports are three ports touched."""
    if case == "unsupported-counter":
        wires = _tripwires(len(CL.TRIPWIRE_PORTS))
        for w in wires:
            w["packet_count"] = (1 << 64) - 1
    else:
        wires = _tripwires(6, ports=(21, 21, 22, 22, 23, 23))
    out = D.scan(collect(T0, flows=captured_flows() + wires), VALUES)
    assert [x for x in out["detections"] if x.get("basis") == "tripwire"] == []


def test_a_masked_team_flow_the_tripwire_never_meets_does_not_raise_it(lab):  # noqa: F811
    """The review of d1cb5b71 (2): a management-class flow to 203.0.113.0/24 at 2000 never meets a
    tripwire to the source's subnet, so it does not lift the tripwire above where a response
    placed under it would go."""
    _pipeline(lab)
    lab.fake.table[OVS1].append({
        "dpid": OVS1, "table_id": 0, "priority": 2000, "cookie": TEAM + 9,
        "match": {"eth_type": 0x0800, "ipv4_dst": "203.0.113.0/24"},
        "actions": [{"type": "OUTPUT", "port": "CONTROLLER"}], "idle_timeout": 0,
        "hard_timeout": 0})
    got = CL.tripwire_ask(NET, _watched(H1_V4), driver=lab.driver)
    assert got["ok"], got["error"]
    assert {c["flow"]["priority"] for c in got["ask"]["changes"]} == {1}


def test_the_tripwire_goes_on_the_source_s_own_switch(lab):  # noqa: F811 - the fixture
    """The review of d1cb5b71 (3): a watching row's detection is the switch that saw it first,
    maybe a transit; the tripwire goes where the controller's topology lists the source's
    host, the ingress a flood's response is proposed at."""
    from modules.sdn.drivers.ryu import host_from_ryu
    _pipeline(lab)
    h1 = host_from_ryu({"mac": "02:00:00:00:00:01", "ipv4": [H1_V4], "ipv6": [],
                        "port": {"dpid": f"{OVS1:016x}", "port_no": "00000005",
                                 "hw_addr": "02:90:d3:08:55:05", "name": "eno5"}})
    stored = {"state": "read", "controllers": [dict(lab.topo["controllers"][0], hosts=[h1])]}
    got = CL.tripwire_ask(NET, _watched(H1_V4, dpid=4), driver=lab.driver, stored=stored)
    assert got["ok"], got["error"]
    assert got["ask"]["dpid"] == OVS1
    assert "the source's own switch" in got["words"]


def test_a_second_set_is_refused_whatever_the_address_s_spelling(lab):  # noqa: F811
    """The review of d1cb5b71 (5): Ryu may spell an IPv6 source uncompressed."""
    _pipeline(lab)
    first = CL.tripwire_ask(NET, _watched(H1_V6), driver=lab.driver)
    assert first["ok"], first["error"]
    for c in first["ask"]["changes"]:
        c["flow"]["match"]["ipv6_src"] = ipaddress.ip_address(H1_V6).exploded
    _sent(lab, first)
    again = CL.tripwire_ask(NET, _watched(H1_V6), driver=lab.driver)
    assert not again["ok"] and "already on switch" in again["error"], again


def test_the_tripwire_ports_leave_out_dns_and_are_distinct():
    assert 53 not in CL.TRIPWIRE_PORTS
    assert len(set(CL.TRIPWIRE_PORTS)) == len(CL.TRIPWIRE_PORTS) == 16
    assert D.TRIPWIRE_NEED < len(CL.TRIPWIRE_PORTS)
    assert ipaddress.ip_network(SUBNET)
