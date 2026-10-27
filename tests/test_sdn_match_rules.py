"""OpenFlow 1.3's match prerequisites, enforced before a request exists
(`modules/sdn/match_rules.py`; PHASE8_PLAN 17.1 S8 and S16, C1912).

The expectations are the specification's table (OpenFlow 1.3.5, section 7.2.3.8, table 12),
written here from the specification, not from the module: each field, the field it needs and
the values that field may hold. Every row is held both ways: missing, it is refused naming the
field and the value needed; present with a wrong value, refused naming both values; met, no
problem. IPv4 and IPv6 alike; an address of the other family refused; a set-field held to its
field's prerequisites against the match.
"""
import pytest

from modules.sdn import match_rules as M

#: The specification's table 12, typed from the specification (independent of the module).
SPEC = {
    "in_phy_port": ("in_port", None), "vlan_pcp": ("vlan_vid", None),
    "ip_dscp": ("eth_type", (0x0800, 0x86DD)), "ip_ecn": ("eth_type", (0x0800, 0x86DD)),
    "ip_proto": ("eth_type", (0x0800, 0x86DD)),
    "ipv4_src": ("eth_type", (0x0800,)), "ipv4_dst": ("eth_type", (0x0800,)),
    "tcp_src": ("ip_proto", (6,)), "tcp_dst": ("ip_proto", (6,)),
    "udp_src": ("ip_proto", (17,)), "udp_dst": ("ip_proto", (17,)),
    "sctp_src": ("ip_proto", (132,)), "sctp_dst": ("ip_proto", (132,)),
    "icmpv4_type": ("ip_proto", (1,)), "icmpv4_code": ("ip_proto", (1,)),
    "arp_op": ("eth_type", (0x0806,)), "arp_spa": ("eth_type", (0x0806,)),
    "arp_tpa": ("eth_type", (0x0806,)), "arp_sha": ("eth_type", (0x0806,)),
    "arp_tha": ("eth_type", (0x0806,)),
    "ipv6_src": ("eth_type", (0x86DD,)), "ipv6_dst": ("eth_type", (0x86DD,)),
    "ipv6_flabel": ("eth_type", (0x86DD,)),
    "icmpv6_type": ("ip_proto", (58,)), "icmpv6_code": ("ip_proto", (58,)),
    "ipv6_nd_target": ("icmpv6_type", (135, 136)), "ipv6_nd_sll": ("icmpv6_type", (135,)),
    "ipv6_nd_tll": ("icmpv6_type", (136,)),
    "mpls_label": ("eth_type", (0x8847, 0x8848)), "mpls_tc": ("eth_type", (0x8847, 0x8848)),
    "mpls_bos": ("eth_type", (0x8847, 0x8848)), "pbb_isid": ("eth_type", (0x88E7,)),
    "ipv6_exthdr": ("eth_type", (0x86DD,)),
}
#: A value each field may hold.
VALUE = {"in_port": 1, "vlan_vid": 4097, "eth_type": 0x0800, "ip_proto": 6, "icmpv6_type": 135,
         "ipv4_src": "192.0.2.1", "ipv4_dst": "192.0.2.0/24", "arp_spa": "192.0.2.1",
         "arp_tpa": "192.0.2.2", "arp_sha": "00:00:00:00:00:01", "arp_tha": "00:00:00:00:00:02",
         "ipv6_src": "2001:db8::1", "ipv6_dst": "2001:db8::/64",
         "ipv6_nd_target": "2001:db8::2", "ipv6_nd_sll": "00:00:00:00:00:03",
         "ipv6_nd_tll": "00:00:00:00:00:04"}


def complete(field: str) -> dict:
    """A match holding *field* and, recursively, every field it needs, met."""
    out = {}

    def need(f, value=None):
        if f in SPEC:
            req, allowed = SPEC[f]
            need(req, allowed[0] if allowed else None)
        out[f] = value if value is not None else VALUE.get(f, 3)

    need(field)
    if field in ("icmpv6_type", "icmpv6_code", "ipv6_nd_target", "ipv6_nd_sll", "ipv6_nd_tll"):
        out["eth_type"], out["ip_proto"] = 0x86DD, 58
    if field in ("icmpv4_type", "icmpv4_code"):
        out["eth_type"], out["ip_proto"] = 0x0800, 1
    if field == "ipv6_nd_tll":
        out["icmpv6_type"] = 136
    return out


def test_the_module_s_table_is_the_specification_s():
    assert M.PREREQUISITES == SPEC


@pytest.mark.parametrize("field", sorted(SPEC))
def test_each_field_met_is_sound(field):
    assert M.problems(complete(field)) == []


@pytest.mark.parametrize("field", sorted(SPEC))
def test_each_field_without_what_it_needs_is_refused_naming_it(field):
    match = complete(field)
    needed, allowed = SPEC[field]
    del match[needed]
    said = [p for p in M.problems(match) if p.startswith(f"{field} needs {needed}")]
    assert said, M.problems(match)
    assert f"or remove {field}" in said[0]
    if allowed:
        assert f"add {needed} = " in said[0]


@pytest.mark.parametrize("field", sorted(f for f, (_n, v) in SPEC.items() if v))
def test_each_field_with_a_wrong_value_names_both(field):
    match = complete(field)
    needed, _allowed = SPEC[field]
    match[needed] = 0x9999 if needed == "eth_type" else 250
    said = [p for p in M.problems(match) if p.startswith(f"{field} needs {needed}")]
    assert said and ", not " in said[0], M.problems(match)


def test_the_board_s_example_tcp_dst_without_ip_proto():
    """Board SdnFlowEdit: tcp_dst needs ip_proto 6 (OpenFlow 1.3's match prerequisites)."""
    assert M.problems({"in_port": 1, "eth_type": 0x0800, "ipv4_src": "192.0.2.1",
                       "tcp_dst": 22}) == [
        "tcp_dst needs ip_proto 6 (OpenFlow 1.3's match prerequisites): add ip_proto = 6, or "
        "remove tcp_dst"]


def test_a_chain_is_said_link_by_link():
    said = M.problems({"tcp_dst": 22, "ip_proto": 6})
    assert said == ["ip_proto needs eth_type 0x0800 or 0x86dd (OpenFlow 1.3's match "
                    "prerequisites): add eth_type = 0x0800, or remove ip_proto"]


@pytest.mark.parametrize("match,words", [
    ({"eth_type": 0x86DD, "ip_proto": 1, "icmpv4_type": 8}, "ICMPv4 is IPv4"),
    ({"eth_type": 0x0800, "ip_proto": 58, "icmpv6_type": 128}, "ICMPv6 is IPv6"),
])
def test_icmp_s_fields_are_their_own_family_s(match, words):
    assert any(words in p for p in M.problems(match))


@pytest.mark.parametrize("match,words", [
    ({"eth_type": 0x0800, "ipv4_src": "2001:db8::1"}, "ipv4_src holds an IPv4 address, not "
                                                      "the IPv6 2001:db8::1"),
    ({"eth_type": 0x86DD, "ipv6_dst": "192.0.2.1"}, "ipv6_dst holds an IPv6 address, not the "
                                                    "IPv4 192.0.2.1"),
    ({"eth_type": 0x0800, "ipv4_dst": "host-a"}, "ipv4_dst holds an IPv4 address or prefix"),
    ({"eth_src": "00:00:00:00:01"}, "eth_src holds a MAC address"),
    ({"in_port": "one"}, "in_port is a whole number"),
])
def test_a_value_not_of_its_field_is_refused(match, words):
    assert any(words in p for p in M.problems(match)), M.problems(match)


@pytest.mark.parametrize("match", [
    {"eth_type": "0x0800", "ipv4_src": "192.0.2.0/255.255.255.0"},
    {"eth_type": "34525", "ipv6_src": "2001:db8::1", "ip_proto": "58", "icmpv6_type": "135",
     "ipv6_nd_target": "2001:db8::9"},
])
def test_a_form_s_text_reads_as_numbers_and_masks(match):
    assert M.problems(match) == []
    assert all(isinstance(v, int) for k, v in M.normalise(match).items() if k in M.INT_FIELDS)


def test_a_set_field_needs_its_field_s_prerequisites_in_the_match():
    assert M.set_field_problems({"in_port": 1}, [
        {"type": "SET_FIELD", "field": "ipv4_dst", "value": "192.0.2.9"}]) == [
        "SET_FIELD ipv4_dst: the flow's match must meet its prerequisite: ipv4_dst needs "
        "eth_type 0x0800 (OpenFlow 1.3's match prerequisites): add eth_type = 0x0800, or "
        "remove ipv4_dst"]
    assert M.set_field_problems({"eth_type": 0x86DD}, [{"type": "WRITE_ACTIONS", "actions": [
        {"type": "SET_FIELD", "field": "ipv6_dst", "value": "2001:db8::9"}]}]) == []


def test_the_table_miss_flow_is_priority_0_matching_everything():
    assert M.is_table_miss({"priority": 0, "match": {}})
    assert not M.is_table_miss({"priority": 0, "match": {"in_port": 1}})
    assert not M.is_table_miss({"priority": 1, "match": {}})
