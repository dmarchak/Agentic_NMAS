"""A closed-loop response's drop under the flows that serve the protected classes it meets (Lab
9 Part B, 2026-11-20; `flow_ops.response_place`, `protected.owned_class_words`, C4122).

A response matches one source's address, so it meets every protected class with a field it
leaves unset: DNS's, DHCP's and DHCP's replies. Whether it may is the classes' owners' alone, as
for every writer: with the lab's documented owners it is refused, as before. Where the network
names ``response`` among a class's owners, the drop is written in table 0 under the class's own
flows (the team's DNS punts at 1200, DHCP steering at 1100 and 1101) and over the forwarding it
must win against (1000 on an Arista; table 2 on an Open vSwitch server), and its preview says
what of each class it takes: never "none", since those flows match by port and MAC and the class
does not. The tables are the hardware's shapes as Ryu answered them on 2026-11-20 at 01:03 UTC,
with documentation addresses:

- **The documented owners:** refused naming dns, nothing sent; the ProCurve's too.
- **An Arista, `response` an owner:** the drop at 1010, each class said with its flows'
  priority, the team's drop of DNS over TCP named as taking what it matches first; sent and
  verified.
- **An Open vSwitch server's table 0:** the drop at the floor, 300, under DHCP's 1100.
- **The ProCurve** (DNS and DHCP in table 200): written at 300 over the goto, its preview saying
  no flow of the class sits above it.
- **No room** (forwarding at 1095 under DHCP's 1100): the drop at 1105, its preview saying
  DHCP's flows are not above it.
- **The writer is the code's, never the ask's:** a person's plan whose ask carries a response's
  fields is the person's, and refused.
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


def classes(*extra_owners):
    """The documented classes, each with *extra_owners* added to its owners."""
    return [P._context_entry(dict(e, owners=e["owners"] + list(extra_owners)), f"planted[{n}]")
            for n, e in enumerate(CONTEXT)]


def team(table, priority, match, actions, n):
    return {"table_id": table, "priority": priority, "cookie": 0x9A01000000000000 + n,
            "match": match, "actions": actions}


def served(table):
    """The team's DNS punt and DHCP steering on host port 10, uplink 1, in *table*, with the
    team's drop of DNS over TCP beside the punt (at 1200 on the hardware), which serves no
    class the lab declares."""
    return [
        team(table, 1200, {"eth_type": 0x0800, "in_port": 10, "ip_proto": 17, "udp_dst": 53},
             [{"type": "OUTPUT", "port": "CONTROLLER"}], 1),
        team(table, 1200, {"eth_type": 0x0800, "in_port": 10, "ip_proto": 6, "tcp_dst": 53},
             [], 10),
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
    """The documented owners: no class names the response."""
    planted["set"] = _pset(classes())
    return lab


@pytest.fixture
def owned(lab, planted):  # noqa: F811
    """The network names the response among each class's owners."""
    planted["set"] = _pset(classes(P.RESPONSE_WRITER))
    return lab


def _with(lab, table):
    lab["fake"].table[1] = [dict(f) for f in table]


def _drop():
    return CL.respond_to_threat("Default", _detection(SOURCE), "drop_source")


def _said(preview):
    return " ".join(preview["plan"]["warnings"])


def test_without_response_among_the_owners_a_response_is_refused_as_before(lab9):
    for table in (ARISTA, OVS, PROCURVE):
        _with(lab9, table)
        writes = list(lab9["fake"].writes)
        preview = _drop()
        assert not preview["ok"]
        assert "meets the protected class dns (must_reach dns" in preview["error"]
        assert lab9["fake"].writes == writes


def test_on_an_arista_the_drop_sits_over_forwarding_and_under_dhcp(owned):
    _with(owned, ARISTA)
    preview = _drop()
    assert preview["ok"], preview["error"]
    assert preview["params"]["priority"] == 1010
    (flow,) = [c["flow"] for c in preview["ask"]["changes"] if c["do"] == "add_flow"]
    assert flow["table_id"] == 0 and flow["match"] == {"eth_type": 0x0800, "ipv4_src": SOURCE}
    said = _said(preview)
    for name in ("dns", "dhcp", "dhcp-reply"):
        assert f"meets the protected class {name} (" in said
        assert f"{name} (" in said and "which names response among its owners" in said
    assert ("the class's flows above it in table 0 (priority 1200, this flow 1010) take the "
            "packets they match first, and it takes the class's packets they do not match") in said
    assert "takes none" not in said
    # The team's drop of DNS over TCP at 1200 serves no declared class and keeps its packets.
    assert ("1 flow serving no protected class sit above it in its table and take what they "
            "match first, so this flow does not act on those packets: table 0, priority 1200, "
            "match eth_type=0x0800, in_port=10, ip_proto=6, tcp_dst=53, actions drop") in said
    done = CL.respond_to_threat("Default", None, "drop_source", confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        actor_verified="access", sleep=lambda s: None)
    assert done["outcome"] == "verified", done["error"]
    (added,) = [f for f in owned["fake"].table[1] if f["priority"] == 1010]
    assert added["match"]["ipv4_src"] == SOURCE and not added["actions"]


def test_on_an_open_vswitch_server_the_drop_sits_in_table_0_under_dhcp(owned):
    _with(owned, OVS)
    preview = _drop()
    assert preview["ok"], preview["error"]
    assert preview["params"]["priority"] == FO.RESPONSE_PRIORITY_FLOOR
    (flow,) = [c["flow"] for c in preview["ask"]["changes"] if c["do"] == "add_flow"]
    assert flow["table_id"] == 0
    assert "(priority 1100, this flow 300) take the packets they match first" in _said(preview)


def test_on_the_procurve_a_class_served_in_a_later_table_is_said_taken(owned):
    _with(owned, PROCURVE)
    preview = _drop()
    assert preview["ok"], preview["error"]
    assert preview["params"]["priority"] == FO.RESPONSE_PRIORITY_FLOOR
    assert ("no flow on this switch serving that class sits above it in table 0, so it takes "
            "the class's packets it matches") in _said(preview)


def test_with_no_room_the_drop_sits_over_dhcp_and_says_so(owned):
    _with(owned, [LLDP] + served(0) + forwarding(0, top=1095))
    preview = _drop()
    assert preview["ok"], preview["error"]
    assert preview["params"]["priority"] == 1105
    said = _said(preview)
    assert "(priority 1200, this flow 1105) take the packets they match first" in said
    assert ("meets the protected class dhcp (must_reach dhcp; NetBox: planted[1]), which names "
            "response among its owners, so it is written; no flow on this switch serving that "
            "class sits above it in table 0") in said


def test_a_person_s_plan_carrying_a_response_s_fields_is_the_person_s(owned):
    _with(owned, ARISTA)
    ask = {"connection": "lab-controller", "dpid": 1, "response": True, "action": "drop_source",
           "changes": [{"do": "add_flow", "flow": {
               "table_id": 0, "priority": 1010, "cookie": 0x4D45000000000077,
               "hard_timeout": 600, "match": {"eth_type": 0x0800, "ipv4_src": SOURCE},
               "actions": []}}]}
    got = FO.plan("Default", ask)
    assert not got["ok"]
    assert "this write is person's: nothing is sent" in got["error"]


def test_a_person_s_flow_meets_a_served_class_as_before():
    flow = {"table_id": 0, "priority": 1010, "match": {"eth_type": 0x0800, "ipv4_src": SOURCE},
            "actions": []}
    changes = [{"do": "add_flow", "flow": flow}]
    for writer in ("person", "app:dns_blacklist", P.RESPONSE_WRITER):
        got = P.flow_refusal_detail(_pset(classes()), changes, 1, {}, writer=writer,
                                    switch_flows=ARISTA)
        assert "meets the protected class" in got["words"], writer
    got = P.flow_refusal_detail(_pset(classes(P.RESPONSE_WRITER)), changes, 1, {},
                                writer=P.RESPONSE_WRITER, switch_flows=ARISTA)
    assert got["words"] == ""
    assert len([n for n in got["notes"] if "which names response among its owners" in n]) == 3
    assert len([n for n in got["notes"] if "take what they match first" in n]) == 1
    got = P.flow_refusal_detail(_pset(classes(P.RESPONSE_WRITER)), changes, 1, {},
                                writer="person", switch_flows=ARISTA)
    assert "this write is person's" in got["words"]
