"""The SDN trace (the final SDN lab's A5, C1911): a packet walked through the flow tables a
controller reported, each hop's DPID with the port it came in and left by (the bonus).

The controller's answers are REAL, Ryu 4.34 over Open vSwitch 2.17.12 on the lab's controller,
2026-10-27 (each fixture's README says when and how it was captured):
- the topology, tests/fixtures/sdn/ryu/topology_rest.json (~09:35 UTC): s1 (DPID 1) with h1
  (192.0.2.1, 2001:db8:8::1) on port 1 and h2 (.2) on port 2; s2 (DPID 2) with h3 (.3) on port
  1 and h4 (.4) on port 2; the link s1 port 3 to s2 port 3; and the two hosts Ryu kept from
  earlier runs on s1 port 1 and s2 port 1;
- s1's table, tests/fixtures/sdn/lab8/l2_only_s1.json (~09:14): the controller's L2 flows for
  h1 and h3, and h2 and h4 (priority 1), the LLDP flow (65535) and the table-miss to the
  controller (0);
- s2's table, tests/fixtures/sdn/lab8/unauthorised_s2.json (~09:31): the L2 flows for h1 and h3,
  the table-miss, and the unauthorised flow (cookie 0xbad0, priority 100) sending IPv4 to
  192.0.2.3 out port 2, h4's.

The three were read at different minutes of one run; the stored value stamps them with one
read time, as the reader's one read would. Each case below that is not the capture is a minimal
edit of it in Ryu's own spelling, made where it is used (`with_flows`), parsed by the real
driver. Every expected DPID, port and port name is read off the captures by hand.

- **The real tables:** IPv4 from h1 to h3 is carried to h4's port by the unauthorised flow,
  named; IPv6 beside it, which that flow does not match, is delivered; without the flow IPv4 is
  delivered too; h3 to h1 both ways; h2 to h4 ends at the controller (s2 holds no flow for the
  pair, so its table-miss sends it there); a host found by MAC; TCP and UDP to a port.
- **OpenFlow 1.3.5's rules:** no table-miss entry drops (5.4); back out the ingress port only
  by IN_PORT (4.5); IN_PORT round a pair of switches is a loop; FLOOD leaves by every other
  port; a goto with metadata and the action set (5.9, 5.10); a set-field rewrite carried to
  the next switch; two flows of one priority with different actions cannot tell (5.3).
- **Cannot tell, said:** a group, NORMAL, a field the trace does not model, a table not read;
  a field whose prerequisite the packet lacks does not match. A stale read is said.
- **Refusals** name what was compared: an unknown host, one listed twice, two families, a
  missing or stray port, the same host, no controller. Each IPv4 case has its IPv6 case.
- **Read-only:** the stored value is unchanged and nothing else is read; a fabric's work grows
  with its hops, and a flood past the bound is counted.
"""
import calendar
import copy
import json
import time

import pytest

from modules.readers import sdn_controllers as R
from modules.sdn import trace as TR
from modules.sdn.drivers.base import Connection
from modules.sdn.drivers.ryu import RyuDriver
from tests.sdn_fakes import Routes, fixture, lab8, ryu_switch, with_flows

BASE = "http://127.0.0.1:8080"
TOPO = fixture("topology_rest.json")
S1 = lab8("l2_only_s1.json")
S2 = lab8("unauthorised_s2.json")
READ_AT = "2026-10-27T09:35:49Z"
NOW = float(calendar.timegm(time.strptime(READ_AT, "%Y-%m-%dT%H:%M:%SZ"))) + 30
H1, H2, H3, H4 = (f"00:00:00:00:00:0{n}" for n in (1, 2, 3, 4))
DPID1, DPID2 = "0000000000000001", "0000000000000002"


class _Drv:
    def __init__(self, answer):
        self.answer = answer

    def topology(self):
        return self.answer


def _topology(edit=None):
    got = RyuDriver(Connection(BASE), session=Routes(TOPO, BASE)).topology()
    assert got["ok"], got
    if edit:
        edit(got)
    return R._topology(_Drv(got), {"capabilities": ["read_topology"]}, {}, READ_AT)


def cached(s1=S1, s2=S2, topo_edit=None, value_at=READ_AT, rows_edit=None):
    rows = [dict(ryu_switch(s1, 1), name="s1"), dict(ryu_switch(s2, 2), name="s2")]
    if rows_edit:
        rows_edit(rows)
    controller = {"name": "lab", "label": "Ryu", "state": "connected", "switches": rows,
                  "topology": _topology(topo_edit)}
    return {"state": "ok", "doc": {"last_good": {"value_at": value_at, "value": {
        "network": "Lab", "state": "ok", "controllers": [controller]}}}}


def run(src, dst, store=None, **kw):
    return TR.trace("Lab", src, dst, cached=store or cached(), now=NOW, **kw)


def path(got, branch=0):
    return [(h["dpid_hex"], h["in_port"], h["in_port_name"], h["out_port"], h["out_port_name"])
            for h in got["branches"][branch]["hops"]]


def without_bad0(flows):
    return [f for f in flows if f["cookie"] != 47824]


def replacing(match, actions, extra=()):
    """An edit replacing the flow whose match is *match* by one with *actions*, and adding
    *extra* (Ryu-shaped flows)."""
    def edit(flows):
        assert sum(f["match"] == match for f in flows) == 1, match
        out = [dict(f, actions=actions) if f["match"] == match else f for f in flows]
        return out + [dict(_RYU_FLOW, **e) for e in extra]
    return edit


_RYU_FLOW = {"priority": 1, "cookie": 0, "idle_timeout": 0, "hard_timeout": 0, "byte_count": 0,
             "duration_sec": 1, "duration_nsec": 0, "packet_count": 0, "length": 96, "flags": 0,
             "actions": [], "match": {}, "table_id": 0}
S1_H1_H3 = {"in_port": 1, "dl_src": H1, "dl_dst": H3}
S2_H1_H3 = {"in_port": 3, "dl_src": H1, "dl_dst": H3}


# ───────────────────────────────────────────────────────────────────────────── the real tables

def test_ipv4_from_h1_to_h3_is_carried_to_h4_s_port_by_the_unauthorised_flow():
    got = run("192.0.2.1", "192.0.2.3")
    assert got["ok"] and got["state"] == "not_delivered" and got["current"]
    (b,) = got["branches"]
    assert b["outcome"] == "elsewhere" and "192.0.2.4" in b["words"]
    assert path(got) == [(DPID1, 1, "s1-eth1", 3, "s1-eth3"), (DPID2, 3, "s2-eth3", 2, "s2-eth2")]
    taken = b["hops"][1]["flows"]
    assert [(f["priority"], f["cookie"]) for f in taken] == [(100, 0xBAD0)]
    assert got["words"].startswith("Not delivered:") and got["dpids"] == []


def test_ipv6_beside_it_is_delivered_since_the_unauthorised_flow_matches_only_ipv4():
    got = run("2001:db8:8::1", "2001:db8:8::3")
    assert got["state"] == "delivered" and got["packet"]["eth_type"] == 0x86DD
    assert path(got) == [(DPID1, 1, "s1-eth1", 3, "s1-eth3"), (DPID2, 3, "s2-eth3", 1, "s2-eth1")]
    assert got["dpids"] == [DPID1, DPID2]
    assert got["branches"][0]["hops"][1]["flows"][0]["priority"] == 1
    assert got["words"].startswith(f"Delivered: {DPID1} (in 1, out 3) → {DPID2} (in 3, out 1)")


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_without_the_unauthorised_flow_both_families_are_delivered(src, dst):
    got = run(src, dst, cached(s2=with_flows(S2, 2, without_bad0)))
    assert got["state"] == "delivered"
    assert path(got) == [(DPID1, 1, "s1-eth1", 3, "s1-eth3"), (DPID2, 3, "s2-eth3", 1, "s2-eth1")]


@pytest.mark.parametrize("src,dst", [("192.0.2.3", "192.0.2.1"),
                                     ("2001:db8:8::3", "2001:db8:8::1")])
def test_h3_to_h1_is_delivered_back_across_the_link(src, dst):
    got = run(src, dst)
    assert got["state"] == "delivered"
    assert path(got) == [(DPID2, 1, "s2-eth1", 3, "s2-eth3"), (DPID1, 3, "s1-eth3", 1, "s1-eth1")]


@pytest.mark.parametrize("src,dst", [("192.0.2.2", "192.0.2.4"),
                                     ("2001:db8:8::2", "2001:db8:8::4")])
def test_h2_to_h4_ends_at_the_controller_by_s2_s_table_miss(src, dst):
    got = run(src, dst)
    assert got["state"] == "not_delivered"
    (b,) = got["branches"]
    assert b["outcome"] == "to_controller" and "controller" in got["words"]
    assert path(got) == [(DPID1, 2, "s1-eth2", 3, "s1-eth3"),
                         (DPID2, 3, "s2-eth3", "CONTROLLER", "")]
    assert [f["priority"] for f in b["hops"][1]["flows"]] == [0]


def test_a_host_is_found_by_mac_and_its_ipv4_address_taken():
    got = run(H1, H3)
    assert got["packet"]["ipv4_dst"] == "192.0.2.3" and got["branches"][0]["outcome"] == \
        "elsewhere"


@pytest.mark.parametrize("src,dst,protocol,port,state", [
    ("192.0.2.1", "192.0.2.3", "tcp", 80, "not_delivered"),
    ("2001:db8:8::1", "2001:db8:8::3", "tcp", 80, "delivered"),
    ("192.0.2.3", "192.0.2.1", "udp", 53, "delivered"),
    ("2001:db8:8::3", "2001:db8:8::1", "udp", "53", "delivered")])
def test_tcp_and_udp_to_a_port(src, dst, protocol, port, state):
    got = run(src, dst, protocol=protocol, port=port)
    assert got["state"] == state
    assert got["packet"][f"{protocol}_dst"] == int(port)
    assert got["packet"][f"{protocol}_src"] == TR.SOURCE_PORT


# ───────────────────────────────────────────────────────────────────────────── OpenFlow's rules

@pytest.mark.parametrize("src,dst", [("192.0.2.2", "192.0.2.4"),
                                     ("2001:db8:8::2", "2001:db8:8::4")])
def test_no_table_miss_entry_drops_it_by_default(src, dst):
    store = cached(s2=with_flows(S2, 2, lambda fs: [f for f in fs if f["priority"] != 0]))
    got = run(src, dst, store)
    (b,) = got["branches"]
    assert b["outcome"] == "no_match" and "5.4" in b["words"]
    assert b["hops"][-1]["out_port"] is None and got["state"] == "not_delivered"


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_out_the_ingress_port_by_number_is_dropped(src, dst):
    s2 = with_flows(S2, 2, lambda fs: replacing(S2_H1_H3, ["OUTPUT:3"])(without_bad0(fs)))
    got = run(src, dst, cached(s2=s2))
    (b,) = got["branches"]
    assert b["outcome"] == "dropped" and "IN_PORT" in b["words"]


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_in_port_back_and_forth_is_a_loop(src, dst):
    s2 = with_flows(S2, 2, lambda fs: replacing(S2_H1_H3, ["OUTPUT:IN_PORT"])(without_bad0(fs)))
    s1 = with_flows(S1, 1, replacing(S1_H1_H3, ["OUTPUT:3"], extra=[
        {"priority": 2, "match": {"in_port": 3, "dl_dst": H3}, "actions": ["OUTPUT:IN_PORT"]}]))
    got = run(src, dst, cached(s1=s1, s2=s2))
    (b,) = got["branches"]
    assert b["outcome"] == "loop" and got["state"] == "not_delivered"
    assert [h["dpid_hex"] for h in b["hops"]] == [DPID1, DPID2, DPID1, DPID2]


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_flood_leaves_by_every_other_port(src, dst):
    s1 = with_flows(S1, 1, replacing(S1_H1_H3, ["OUTPUT:FLOOD"]))
    got = run(src, dst, cached(s1=s1, s2=with_flows(S2, 2, without_bad0)))
    outcomes = sorted((b["outcome"], b["hops"][0]["out_port"]) for b in got["branches"])
    assert outcomes == [("delivered", 3), ("elsewhere", 2)]
    assert got["state"] == "delivered" and "1 other copy" in got["words"]


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_goto_with_metadata_and_the_action_set(src, dst):
    def s1(value):
        return with_flows(S1, 1, replacing(S1_H1_H3, ["WRITE_METADATA:0x1/0xff", "GOTO_TABLE:1"],
                                           extra=[{"table_id": 1, "match": {
                                               "metadata": f"{value}/255", "dl_dst": H3},
                                               "actions": [{"WRITE_ACTIONS": ["OUTPUT:3"]}]}]))
    s2 = with_flows(S2, 2, without_bad0)
    got = run(src, dst, cached(s1=s1(1), s2=s2))
    assert got["state"] == "delivered"
    assert [(f["table_id"], f["priority"]) for f in got["branches"][0]["hops"][0]["flows"]] == \
        [(0, 1), (1, 1)]
    # The table-1 flow wants metadata the table-0 flow did not write: table 1 has no entry for it.
    missed = run(src, dst, cached(s1=s1(2), s2=s2))
    assert missed["branches"][0]["outcome"] == "no_match"
    assert "table 1" in missed["branches"][0]["words"]


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_a_set_field_rewrite_is_carried_to_the_next_switch(src, dst):
    s1 = with_flows(S1, 1, replacing(S1_H1_H3, [f"SET_FIELD: {{eth_dst:{H4}}}", "OUTPUT:3"]))
    got = run(src, dst, cached(s1=s1, s2=with_flows(S2, 2, without_bad0)))
    (b,) = got["branches"]
    # s2 holds no flow from h1 to h4's MAC, so its table-miss sends it to the controller.
    assert b["outcome"] == "to_controller" and [f["priority"] for f in b["hops"][1]["flows"]] \
        == [0]


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_two_flows_at_one_priority_with_different_actions_cannot_tell(src, dst):
    s1 = with_flows(S1, 1, replacing(S1_H1_H3, ["OUTPUT:3"], extra=[
        {"match": {"in_port": 1}, "actions": ["OUTPUT:2"]}]))
    got = run(src, dst, cached(s1=s1))
    assert got["state"] == "cannot_tell" and "5.3" in got["words"]
    same = with_flows(S1, 1, replacing(S1_H1_H3, ["OUTPUT:3"], extra=[
        {"match": {"in_port": 1}, "actions": ["OUTPUT:3"]}]))
    assert run(src, dst, cached(s1=same, s2=with_flows(S2, 2, without_bad0)))["state"] == \
        "delivered"


@pytest.mark.parametrize("vlan,takes", [("0", False), ("10", False), ("0x0000", True),
                                        ("0x1000/0x1000", False)])
@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_a_vlan_match_is_read_as_ryu_writes_it(vlan, takes, src, dst):
    """Ryu writes a tagged id bare ("0" is VLAN 0, tagged) and OFPVID_NONE as 0x0000
    (ofctl_utils.match_vid_to_str); the traced packet is untagged."""
    s1 = with_flows(S1, 1, lambda fs: fs + [dict(_RYU_FLOW, priority=2, match={
        "dl_vlan": vlan}, actions=["OUTPUT:2"])])
    got = run(src, dst, cached(s1=s1, s2=with_flows(S2, 2, without_bad0)))
    assert got["branches"][0]["hops"][0]["out_port"] == (2 if takes else 3)


@pytest.mark.parametrize("field,value", [("nw_dst", "192.0.2.3"), ("ipv6_dst", "2001:db8:8::3")])
@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_a_match_s_prerequisite_is_implied_where_the_read_leaves_it_out(field, value, src, dst):
    """A flow on one family's destination alone takes that family's packet only (OpenFlow
    1.3.5 7.2.3.6: ipv4_dst needs eth_type 0x0800, ipv6_dst 0x86dd)."""
    s1 = with_flows(S1, 1, lambda fs: fs + [dict(_RYU_FLOW, priority=2, match={field: value},
                                                 actions=["OUTPUT:2"])])
    got = run(src, dst, cached(s1=s1, s2=with_flows(S2, 2, without_bad0)))
    same = ("." in src) == (field == "nw_dst")
    assert got["branches"][0]["hops"][0]["out_port"] == (2 if same else 3)
    assert got["branches"][0]["outcome"] == ("elsewhere" if same else "delivered")


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_a_vlan_priority_never_takes_an_untagged_packet(src, dst):
    s1 = with_flows(S1, 1, lambda fs: fs + [dict(_RYU_FLOW, priority=2, match={
        "vlan_pcp": 0}, actions=["OUTPUT:2"])])
    got = run(src, dst, cached(s1=s1, s2=with_flows(S2, 2, without_bad0)))
    assert got["state"] == "delivered" and got["branches"][0]["hops"][0]["out_port"] == 3


# ───────────────────────────────────────────────────────────────────────────── cannot tell

@pytest.mark.parametrize("actions,words", [(["GROUP:1"], "group"),
                                           (["OUTPUT:NORMAL"], "NORMAL"),
                                           (["POP_VLAN", "OUTPUT:3"], "VLAN"),
                                           ([{"WRITE_ACTIONS": ["GROUP:1"]}], "group")])
@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_what_the_trace_does_not_model_cannot_tell(actions, words, src, dst):
    got = run(src, dst, cached(s1=with_flows(S1, 1, replacing(S1_H1_H3, actions))))
    assert got["state"] == "cannot_tell" and words in got["words"]
    assert got["branches"][0]["outcome"] == "unknown"


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_a_field_not_modelled_cannot_tell_and_one_whose_prerequisite_fails_does_not_match(
        src, dst):
    tunnel = with_flows(S1, 1, lambda fs: fs + [dict(_RYU_FLOW, priority=2, match={
        "tunnel_id": 5}, actions=["OUTPUT:2"])])
    got = run(src, dst, cached(s1=tunnel))
    assert got["state"] == "cannot_tell" and "tunnel_id" in got["words"]
    tcp = with_flows(S1, 1, lambda fs: fs + [dict(_RYU_FLOW, priority=2, match={
        "dl_type": 2048 if "." in src else 34525, "nw_proto": 6, "tp_dst": 80},
        actions=["OUTPUT:2"])])
    s2 = with_flows(S2, 2, without_bad0)
    assert run(src, dst, cached(s1=tcp, s2=s2))["state"] == "delivered"   # an ICMP echo
    assert run(src, dst, cached(s1=tcp, s2=s2), protocol="tcp", port=80)["branches"][0][
        "outcome"] == "elsewhere"


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_a_table_not_read_cannot_tell(src, dst):
    def unread(rows):
        rows[1].update(active_flows=None, flows=[], error="flows: HTTP 500 from /stats/flow/2")
    got = run(src, dst, cached(rows_edit=unread))
    (b,) = got["branches"]
    assert b["outcome"] == "not_read" and "HTTP 500" in b["words"]
    assert got["state"] == "cannot_tell"


def test_a_read_older_than_its_promise_is_said():
    got = TR.trace("Lab", "192.0.2.1", "192.0.2.3", cached=cached(), now=NOW + 3600)
    assert got["ok"] and not got["current"] and "as last read at" in got["words"]


# ───────────────────────────────────────────────────────────────────────────── refusals

def _twice(address):
    def edit(topo):
        extra = dict(topo["hosts"][0], mac="02:00:00:00:00:99")
        extra["ipv4" if "." in address else "ipv6"] = [address]
        topo["hosts"].append(extra)
    return edit


@pytest.mark.parametrize("src,dst,kw,words", [
    ("192.0.2.99", "192.0.2.3", {}, "no controller lists a host with 192.0.2.99"),
    ("2001:db8:8::99", "2001:db8:8::3", {}, "no controller lists a host with 2001:db8:8::99"),
    ("192.0.2.1", "2001:db8:8::3", {}, "is IPv4 and the destination"),
    ("2001:db8:8::1", "192.0.2.3", {}, "is IPv6 and the destination"),
    ("192.0.2.1", "192.0.2.3", {"protocol": "tcp"}, "needs its destination port"),
    ("2001:db8:8::1", "2001:db8:8::3", {"protocol": "udp", "port": 70000}, "1 to 65535"),
    ("192.0.2.1", "192.0.2.3", {"port": 80}, "ICMP echo has no port"),
    ("2001:db8:8::1", "2001:db8:8::3", {"protocol": "sctp"}, "not 'sctp'"),
    ("192.0.2.1", H1, {}, "same host"),
    ("2001:db8:8::1", H1, {}, "same host"),
    ("h1", "192.0.2.3", {}, "not an IPv4 or IPv6 address or a MAC"),
])
def test_refusals_name_what_was_compared(src, dst, kw, words):
    got = run(src, dst, **kw)
    assert not got["ok"] and words in got["error"], got["error"]


@pytest.mark.parametrize("address", ["192.0.2.3", "2001:db8:8::3"])
def test_an_address_listed_at_two_places_is_refused_naming_both(address):
    got = run("192.0.2.1" if "." in address else "2001:db8:8::1", address,
              cached(topo_edit=_twice(address)))
    assert not got["ok"] and "2 places" in got["error"]
    assert "02:00:00:00:00:99" in got["error"] and H3 in got["error"]


def test_a_network_with_no_controller_is_refused():
    got = TR.trace("Lab", "192.0.2.1", "192.0.2.3", cached={"state": "not_configured",
                                                            "why": "no connection"}, now=NOW)
    assert not got["ok"] and "not read" in got["error"]


# ───────────────────────────────────────────────────────────────────────────── read-only, scale

def test_the_trace_reads_only_the_value_it_is_given_and_changes_nothing(monkeypatch):
    from modules import reader_job

    def refuse(*_a, **_k):
        raise AssertionError("the trace read the store though handed its value")
    monkeypatch.setattr(reader_job, "read_cached_for", refuse)
    store = cached()
    before = copy.deepcopy(store)
    run("192.0.2.1", "192.0.2.3", store)
    assert store == before


def _chain(n, extra_ports=0):
    """A line of *n* switches, port 1 to the next's port 2, a host on the first's port 3 and on
    the last's port 3, every flow forwarding by destination MAC; *extra_ports* more host ports
    on the last switch, flooded to."""
    switches, links = {}, {}
    for d in range(1, n + 1):
        out = 1 if d < n else ("FLOOD" if extra_ports else 3)
        switches[d] = {"name": "", "ports": {p: f"p{p}" for p in range(1, 4 + extra_ports)},
                       "why": "", "flows": [{"table_id": 0, "priority": 1, "cookie": 0,
                                             "match": {"eth_dst": H3},
                                             "actions": [{"type": "OUTPUT", "port": out}]}]}
        if d < n:
            links[(d, 1)], links[(d + 1, 2)] = (d + 1, 2), (d, 1)
    return {"switches": switches, "links": links, "hosts": []}


def _packet():
    return {"eth_src": H1, "eth_dst": H3, "vlan_vid": 0, "eth_type": 0x0800,
            "ipv4_src": "192.0.2.1", "ipv4_dst": "192.0.2.3", "ip_proto": 1}


@pytest.mark.parametrize("n", [10, 100])
def test_the_work_grows_with_the_hops(n, monkeypatch):
    calls = []
    real = TR.judge
    monkeypatch.setattr(TR, "judge", lambda m, p: calls.append(1) or real(m, p))
    got = TR.walk(_chain(n), _packet(), (1, 3), (n, 3))
    (b,) = got["branches"]
    assert b["outcome"] == "delivered" and len(b["hops"]) == n and len(calls) == n


def test_a_flood_past_the_bound_is_counted_not_drawn():
    got = TR.walk(_chain(2, extra_ports=TR.MAX_BRANCHES + 10), _packet(), (1, 3), (2, 3))
    assert len(got["branches"]) == TR.MAX_BRANCHES and got["more"] > 0
    assert json.dumps(got, default=str)
