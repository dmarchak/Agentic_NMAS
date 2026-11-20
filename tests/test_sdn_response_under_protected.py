"""A closed-loop response's drop under the flows that serve the protected classes it meets (Lab
9 Part B, 2026-11-20; `flow_ops.response_place`, `protected.served_above`).

A response matches one source's address, so it meets every protected class with a field it
leaves unset: DNS's, DHCP's and DHCP's replies. On the lab's hardware those classes' own flows
(the team's DNS punts at 1200, DHCP steering at 1100 and 1101) sit in table 0 above the
forwarding (1000 on an Arista; table 2 on an Open vSwitch server), so a drop placed between
them takes the source's other traffic and none of the classes'. The tables here are the
hardware's shapes as Ryu answered them on 2026-11-20 at 01:03 UTC, with documentation addresses:

- **An Arista's single table:** the drop at 1010, over forwarding's 1000 and under DHCP's 1100,
  previewed with each class said and the serving flows' priorities, then sent and verified.
- **An Open vSwitch server's table 0** (DNS and DHCP there, forwarding in table 2): the drop at
  the floor, 300, in table 0, under DHCP's 1100.
- **The ProCurve's** (DNS and DHCP in table 200, past table 0): refused naming the class, as a
  class served in a later table cannot be shown untouched; nothing sent.
- **A class no flow on the switch serves:** refused naming it, as before.
- **No room:** forwarding at 1095 under DHCP at 1100 puts the drop at 1105, over DHCP's flow,
  and the guard refuses it naming the class (so the refusal is recorded, C2944).
- **Only a response:** a person's flow and a policy's meet a class as before, served or not.
"""
import pytest

from modules import protected as P
from modules.sdn import closed_loop as CL
from modules.sdn import flow_ops as FO
from tests.test_protected import _detection, _pset, planted  # noqa: F401 - the fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_ops_v2 import lab  # noqa: F401 - the fixture

SOURCE = "192.0.2.1"
ROUTER_MAC = "00:00:5e:00:53:fe"

#: The lab's documented classes (docs/LAB9_NETBOX_STEPS.md, the config context), read by the
#: guard's own parser.
CONTEXT = [
    {"name": "dns", "invariant": "must_reach dns", "owners": ["app:dns_blacklist"],
     "reason": "every host's DNS", "match": {"eth_type": "0x0800", "ip_proto": 17,
                                             "udp_dst": 53}},
    {"name": "dhcp", "invariant": "must_reach dhcp", "owners": ["feature:dhcp-unicast"],
     "reason": "every host's lease", "match": {"eth_type": "0x0800", "ip_proto": 17,
                                               "udp_dst": 67}},
    {"name": "dhcp-reply", "invariant": "must_reach dhcp", "owners": ["feature:dhcp-unicast"],
     "reason": "the router's replies", "match": {"eth_type": "0x0800", "ip_proto": 17,
                                                 "udp_src": 67, "udp_dst": 68}}]


def classes():
    return [P._context_entry(e, f"planted[{n}]") for n, e in enumerate(CONTEXT)]


def team(table, priority, match, actions, n):
    return {"table_id": table, "priority": priority, "cookie": 0x9A01000000000000 + n,
            "match": match, "actions": actions}


def served(table):
    """The team's DNS punt and DHCP steering on host port 10, uplink 1, in *table*."""
    return [
        team(table, 1200, {"eth_type": 0x0800, "in_port": 10, "ip_proto": 17, "udp_dst": 53},
             [{"type": "OUTPUT", "port": "CONTROLLER"}], 1),
        team(table, 1100, {"eth_type": 0x0800, "in_port": 10, "eth_dst": "ff:ff:ff:ff:ff:ff",
                           "ip_proto": 17, "udp_src": 68, "udp_dst": 67},
             [{"type": "OUTPUT", "port": 1}], 2),
        team(table, 1101, {"eth_type": 0x0800, "in_port": 1, "ip_proto": 17, "udp_src": 67,
                           "udp_dst": 68}, [{"type": "OUTPUT", "port": 10}], 3)]


def forwarding(table, top=1000):
    return [team(table, top, {"eth_dst": ROUTER_MAC}, [{"type": "OUTPUT", "port": 1}], 4),
            team(table, 900, {"eth_dst": "ff:ff:ff:ff:ff:ff", "in_port": 10},
                 [{"type": "OUTPUT", "port": 1}], 5),
            team(table, 100, {"in_port": 10}, [{"type": "OUTPUT", "port": 1}], 6)]


LLDP = {"table_id": 0, "priority": 65535, "cookie": 0,
        "match": {"eth_type": 0x88CC, "eth_dst": "01:80:c2:00:00:0e"},
        "actions": [{"type": "OUTPUT", "port": "CONTROLLER"}]}

ARISTA = [LLDP] + served(0) + forwarding(0)
OVS = [LLDP] + served(0) + [team(0, 0, {}, [{"type": "GOTO_TABLE", "table_id": 2}], 7)] \
    + forwarding(2)
PROCURVE = [team(0, 0, {}, [{"type": "GOTO_TABLE", "table_id": 100}], 7),
            team(100, 1000, {"eth_type": 0x0800, "in_port": 2}, [{"type": "OUTPUT", "port": 3}],
                 8),
            team(100, 0, {}, [{"type": "GOTO_TABLE", "table_id": 200}], 9)] + served(200)


@pytest.fixture
def lab9(lab, planted):  # noqa: F811
    planted["set"] = _pset(classes())
    return lab


def _with(lab, table):
    lab["fake"].table[1] = [dict(f) for f in table]


def _drop():
    return CL.respond_to_threat("Default", _detection(SOURCE), "drop_source")


def test_on_an_arista_the_drop_sits_over_forwarding_and_under_dhcp(lab9):
    _with(lab9, ARISTA)
    preview = _drop()
    assert preview["ok"], preview["error"]
    assert preview["params"]["priority"] == 1010
    (flow,) = [c["flow"] for c in preview["ask"]["changes"] if c["do"] == "add_flow"]
    assert flow["table_id"] == 0 and flow["match"] == {"eth_type": 0x0800, "ipv4_src": SOURCE}
    said = " ".join(preview["plan"]["warnings"])
    for name in ("dns", "dhcp", "dhcp-reply"):
        assert f"meets the protected class {name} (" in said
    assert "sit above it in table 0 (priority 1200, this flow 1010)" in said
    assert "sit above it in table 0 (priority 1100, this flow 1010)" in said
    done = CL.respond_to_threat("Default", None, "drop_source", confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        actor_verified="access", sleep=lambda s: None)
    assert done["outcome"] == "verified", done["error"]
    (added,) = [f for f in lab9["fake"].table[1] if f["priority"] == 1010]
    assert added["match"]["ipv4_src"] == SOURCE and not added["actions"]


def test_on_an_open_vswitch_server_the_drop_sits_in_table_0_under_dhcp(lab9):
    _with(lab9, OVS)
    preview = _drop()
    assert preview["ok"], preview["error"]
    assert preview["params"]["priority"] == FO.RESPONSE_PRIORITY_FLOOR
    (flow,) = [c["flow"] for c in preview["ask"]["changes"] if c["do"] == "add_flow"]
    assert flow["table_id"] == 0
    assert "sit above it in table 0 (priority 1100, this flow 300)" in " ".join(
        preview["plan"]["warnings"])


def test_on_the_procurve_a_class_served_in_a_later_table_still_refuses(lab9):
    _with(lab9, PROCURVE)
    writes = list(lab9["fake"].writes)
    preview = _drop()
    assert not preview["ok"]
    assert "meets the protected class dns (must_reach dns" in preview["error"]
    assert lab9["fake"].writes == writes


def test_a_class_no_flow_on_the_switch_serves_still_refuses(lab9):
    _with(lab9, [f for f in ARISTA if f["match"].get("udp_dst") != 67])
    preview = _drop()
    assert not preview["ok"]
    assert "meets the protected class dhcp (must_reach dhcp" in preview["error"]


def test_with_no_room_under_the_serving_flows_the_guard_refuses_naming_the_class(lab9):
    _with(lab9, [LLDP] + served(0) + forwarding(0, top=1095))
    writes = list(lab9["fake"].writes)
    preview = _drop()
    assert not preview["ok"]
    # 1105, over forwarding's 1095, would take DHCP's packets from its flow at 1100.
    assert "meets the protected class dhcp (must_reach dhcp" in preview["error"]
    assert lab9["fake"].writes == writes


def test_a_person_s_flow_meets_a_served_class_as_before():
    flow = {"table_id": 0, "priority": 1010, "match": {"eth_type": 0x0800, "ipv4_src": SOURCE},
            "actions": []}
    changes = [{"do": "add_flow", "flow": flow}]
    for writer in ("person", "app:dns_blacklist"):
        got = P.flow_refusal_detail(_pset(classes()), changes, 1, {}, writer=writer,
                                    switch_flows=ARISTA)
        assert "meets the protected class" in got["words"], writer
    got = P.flow_refusal_detail(_pset(classes()), changes, 1, {}, writer="response",
                                switch_flows=ARISTA)
    assert got["words"] == "" and len(got["notes"]) == 3


def test_a_serving_flow_below_it_shows_nothing():
    cls = classes()[0]
    flow = {"table_id": 0, "priority": 1250, "match": {"eth_type": 0x0800, "ipv4_src": SOURCE}}
    assert P.served_above(flow, cls, ARISTA) == ""
    assert P.served_above(dict(flow, priority=1010), cls, ARISTA).startswith(
        "its match meets the protected class dns (must_reach dns; ")
