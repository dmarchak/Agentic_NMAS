"""The control-plane guard (`modules/sdn/control_plane.py`; C2022): no SDN response, in any
mode, covers the network's control channel.

- **What a flow may not cover:** LLDP (its EtherType, or a match naming no EtherType and no IP
  field); a controller address (the northbound URL's host, the southbound address), IPv4 and
  IPv6, by a host address or a prefix holding it; OpenFlow's port (6653, 6633, the southbound
  address's own), named, or allowed by a TCP match naming no address and no port. A host's
  source match, the responses' own shape, covers none of it.
- **Removals:** refused only for a flow that names control traffic itself; one covering it by
  breadth (a catch-all, a prefix) may be taken off. A re-installed intent flow is never refused.
- **The real path:** a scan whose source is the controller's southbound address is refused at
  the preview, naming what it covers, before any request; an ask carried back to the confirm
  with such a flow is refused there too, nothing sent.
"""
import pytest

from modules.sdn import closed_loop as CL
from modules.sdn import connections as C
from modules.sdn import control_plane as CP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_detect import BASE, save, scan_flows
from tests.test_sdn_respond import confirm, scan_detection, switch_with

CONN = {"url": "http://192.0.2.10:8080", "southbound": "192.0.2.20:6654"}
CONN6 = {"url": "http://[2001:db8::10]:8080", "southbound": ""}


def _words(match, conn=CONN):
    return [w for _named, w in CP.covers(match, CP.control_channel(conn))]


def test_the_channel_is_the_connection_s_addresses_and_openflow_s_ports():
    got = CP.control_channel(CONN)
    assert [str(a) for a in got["addresses"]] == ["192.0.2.10", "192.0.2.20"]
    assert got["ports"] == [6653, 6633, 6654] and got["not_compared"] == []
    named = CP.control_channel({"url": "http://ryu.example:8080"})
    assert named["addresses"] == [] and named["not_compared"] == [
        "the northbound URL's host ryu.example is a name, not an address, so a match is not "
        "compared with it"]


@pytest.mark.parametrize("match,said", [
    ({"eth_type": 0x88CC}, "LLDP (EtherType 0x88cc), the controller's topology discovery"),
    ({}, "LLDP: it names no EtherType and no IP field"),
    ({"in_port": 3}, "LLDP: it names no EtherType and no IP field"),
    ({"eth_type": 0x0800, "ipv4_src": "192.0.2.10"}, "the controller's address 192.0.2.10"),
    ({"eth_type": 0x0800, "ipv4_dst": "192.0.2.0/24"}, "the controller's address 192.0.2.10"),
    ({"eth_type": 0x0800, "ipv4_src": "192.0.2.0/255.255.255.0"},
     "the controller's address 192.0.2.20"),
    ({"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 6653}, "OpenFlow's port (tcp_dst 6653)"),
    ({"eth_type": 0x0800, "ip_proto": 6, "ipv4_src": "198.51.100.7", "tcp_src": 6654},
     "OpenFlow's port (tcp_src 6654)"),
    ({"eth_type": 0x0800}, "OpenFlow: it allows TCP with no address or port"),
    ({"eth_type": 0x0800, "ip_proto": 6}, "OpenFlow: it allows TCP with no address or port"),
], ids=["lldp", "catch-all", "in-port-only", "ctl-src", "ctl-prefix", "ctl-mask",
        "of-port", "southbound-port", "all-ipv4", "all-tcp"])
def test_a_match_covering_the_channel_is_named(match, said):
    assert any(w.startswith(said) for w in _words(match)), _words(match)


def test_an_ipv6_controller_is_compared_as_an_ipv4_one_is():
    assert _words({"eth_type": 0x86DD, "ipv6_dst": "2001:db8::10"}, CONN6) == [
        "the controller's address 2001:db8::10 (ipv6_dst 2001:db8::10)"]
    assert _words({"eth_type": 0x86DD, "ipv6_src": "2001:db8::/64"}, CONN6) == [
        "the controller's address 2001:db8::10 (ipv6_src 2001:db8::/64)"]
    assert _words({"eth_type": 0x86DD, "ipv6_src": "2001:db8:1::5"}, CONN6) == []


@pytest.mark.parametrize("match", [
    {"eth_type": 0x0800, "ipv4_src": "192.0.2.1"},
    {"eth_type": 0x86DD, "ipv6_src": "2001:db8:1::5"},
    {"eth_type": 0x0800, "ipv4_src": "192.0.2.1", "ipv4_dst": "192.0.2.9"},
    {"eth_type": 0x0800, "ip_proto": 17},
    {"eth_type": 0x0806},
], ids=["v4-source", "v6-source", "pair", "all-udp", "arp"])
def test_a_host_s_match_covers_none_of_it(match):
    assert _words(match) == []


def test_a_response_adding_a_covering_flow_is_refused_naming_it():
    changes = [{"do": "add_flow", "flow": {"match": {"eth_type": 0x0800,
                                                     "ipv4_src": "192.0.2.1"}}},
               {"do": "add_flow", "flow": {"match": {"eth_type": 0x0800,
                                                     "ipv4_src": "192.0.2.20"}}}]
    assert CP.refusal(changes, CONN) == (
        "change 2 adds a flow whose match covers the control channel: the controller's "
        "address 192.0.2.20 (ipv4_src 192.0.2.20). No response may cover it, in any mode "
        "(C2022)")
    assert CP.refusal(changes[:1], CONN) == ""


def test_a_removal_is_refused_only_for_a_flow_naming_control_traffic():
    def remove(match):
        return CP.refusal([{"do": "remove_flow", "target": {"match": match}}], CONN)

    assert remove({"eth_type": 0x88CC}) == (
        "change 1 removes a flow that carries the control channel: LLDP (EtherType 0x88cc), "
        "the controller's topology discovery. No response may take it off, in any mode (C2022)")
    assert "the controller's address 192.0.2.10" in remove(
        {"eth_type": 0x0800, "ipv4_dst": "192.0.2.10"})
    assert "OpenFlow's port (tcp_dst 6633)" in remove(
        {"eth_type": 0x0800, "ip_proto": 6, "tcp_dst": 6633})
    # Covering it by breadth only: taking it off restores what the controller's flows do.
    assert remove({}) == "" and remove({"eth_type": 0x0800, "ipv4_src": "192.0.2.0/24"}) == ""


def test_a_flow_put_back_from_intent_is_never_refused():
    assert CP.refusal([{"do": "add_flow", "reinstall": True,
                        "flow": {"match": {"eth_type": 0x88CC}}}], CONN) == ""


@pytest.fixture
def ctl_is_the_source(networks):  # noqa: F811 - the fixture, used
    """The lab's connection with its southbound address the scan's source, 192.0.2.1."""
    save()
    C.save_connection("Default", {"name": "ctl-1", "kind": "ryu", "url": BASE,
                                  "southbound": "192.0.2.1:6653"}, actor="op")
    return networks


@pytest.mark.usefixtures("ctl_is_the_source")
def test_a_scan_from_the_controller_s_address_is_refused_at_the_preview():
    flows = scan_flows(25)
    d = scan_detection(flows)
    fake = switch_with(flows)
    got = CL.respond_to_threat("Default", d, driver=fake.driver)
    assert not got["ok"] and got["plan"] is None
    assert got["error"] == (
        "change 1 adds a flow whose match covers the control channel: the controller's "
        "address 192.0.2.1 (ipv4_src 192.0.2.1). No response may cover it, in any mode "
        "(C2022)")
    assert fake.writes == []


@pytest.mark.usefixtures("lab")
def test_an_ask_carried_back_with_a_covering_flow_is_refused_at_the_confirm(monkeypatch):
    flows = scan_flows(25)
    d = scan_detection(flows)
    fake = switch_with(flows)
    preview = CL.respond_to_threat("Default", d, driver=fake.driver)
    assert preview["ok"], preview["error"]
    # The controller moved to the source's address after the preview.
    C.save_connection("Default", {"name": "ctl-1", "kind": "ryu", "url": BASE,
                                  "southbound": "192.0.2.1"}, actor="op")
    got = confirm(fake, preview)
    assert not got["ok"] and got["outcome"] == "refused"
    assert got["error"].endswith("No response may cover it, in any mode (C2022): nothing was "
                                 "sent") and "the controller's address 192.0.2.1" in got["error"]
    assert fake.writes == []


@pytest.fixture
def lab(networks):  # noqa: F811 - the fixture, used
    save()
    return networks
