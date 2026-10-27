"""OpenFlow 1.3's match prerequisites, enforced in Python before anything is previewed
(PHASE8_PLAN 17.1 S8 and S16; C1912). Deterministic; no AI.

A switch refuses a flow whose match names a field without the field it depends on
(`OFPBMC_BAD_PREREQ`), and Ryu's ofctl_rest never reports a switch's refusal (its 200 says
sent, not installed: drivers/ryu.py). So Mercury refuses such a match itself, naming the field
that is missing and the value it needs, before a request exists.

**The table** (`PREREQUISITES`) is the specification's (OpenFlow 1.3.5, the section on match field prerequisites, table
12), one row per field: the field it needs and the values that field may hold (None: present
with any value). Prerequisites chain: `tcp_dst` needs `ip_proto` 6, and `ip_proto` in turn needs
`eth_type` 0x0800 or 0x86dd, each said in its own words. Two rows go one step past the table,
because the table alone admits a match that can never match:
- ICMPv4's fields need `eth_type` 0x0800 (ICMPv4 is IPv4's), and ICMPv6's need 0x86dd;
- an address field's value is of its family (an `ipv4_*` field holds an IPv4 address or
  prefix, an `ipv6_*` field an IPv6 one, a MAC field six octets).

**Set-field actions** carry the same prerequisites, held against the flow's match (section
7.2.5: a set-field's prerequisites are those of its field, satisfied by the match).
"""

import ipaddress
import re

ETH_IPV4 = 0x0800
ETH_IPV6 = 0x86DD
ETH_ARP = 0x0806
ETH_MPLS = 0x8847
ETH_MPLS_MULTICAST = 0x8848
ETH_PBB = 0x88E7
IP = (ETH_IPV4, ETH_IPV6)

#: field -> (the field it needs, the values that field may hold, or None for any value).
PREREQUISITES = {
    "in_phy_port": ("in_port", None),
    "vlan_pcp": ("vlan_vid", None),
    "ip_dscp": ("eth_type", IP), "ip_ecn": ("eth_type", IP), "ip_proto": ("eth_type", IP),
    "ipv4_src": ("eth_type", (ETH_IPV4,)), "ipv4_dst": ("eth_type", (ETH_IPV4,)),
    "tcp_src": ("ip_proto", (6,)), "tcp_dst": ("ip_proto", (6,)),
    "udp_src": ("ip_proto", (17,)), "udp_dst": ("ip_proto", (17,)),
    "sctp_src": ("ip_proto", (132,)), "sctp_dst": ("ip_proto", (132,)),
    "icmpv4_type": ("ip_proto", (1,)), "icmpv4_code": ("ip_proto", (1,)),
    "arp_op": ("eth_type", (ETH_ARP,)), "arp_spa": ("eth_type", (ETH_ARP,)),
    "arp_tpa": ("eth_type", (ETH_ARP,)), "arp_sha": ("eth_type", (ETH_ARP,)),
    "arp_tha": ("eth_type", (ETH_ARP,)),
    "ipv6_src": ("eth_type", (ETH_IPV6,)), "ipv6_dst": ("eth_type", (ETH_IPV6,)),
    "ipv6_flabel": ("eth_type", (ETH_IPV6,)),
    "icmpv6_type": ("ip_proto", (58,)), "icmpv6_code": ("ip_proto", (58,)),
    "ipv6_nd_target": ("icmpv6_type", (135, 136)),
    "ipv6_nd_sll": ("icmpv6_type", (135,)),
    "ipv6_nd_tll": ("icmpv6_type", (136,)),
    "mpls_label": ("eth_type", (ETH_MPLS, ETH_MPLS_MULTICAST)),
    "mpls_tc": ("eth_type", (ETH_MPLS, ETH_MPLS_MULTICAST)),
    "mpls_bos": ("eth_type", (ETH_MPLS, ETH_MPLS_MULTICAST)),
    "pbb_isid": ("eth_type", (ETH_PBB,)),
    "ipv6_exthdr": ("eth_type", (ETH_IPV6,)),
}
#: One step past the table: ICMP's fields are their own family's.
FAMILY = {"icmpv4_type": ETH_IPV4, "icmpv4_code": ETH_IPV4,
          "icmpv6_type": ETH_IPV6, "icmpv6_code": ETH_IPV6}
#: The fields that hold numbers, read from a form's text as numbers (0x-prefixed or decimal).
INT_FIELDS = frozenset({"in_port", "in_phy_port", "eth_type", "vlan_vid", "vlan_pcp", "ip_dscp",
                        "ip_ecn", "ip_proto", "tcp_src", "tcp_dst", "udp_src", "udp_dst",
                        "sctp_src", "sctp_dst", "icmpv4_type", "icmpv4_code", "arp_op",
                        "icmpv6_type", "icmpv6_code", "mpls_label", "mpls_tc", "mpls_bos",
                        "ipv6_flabel", "pbb_isid", "tunnel_id", "metadata", "ipv6_exthdr"})
V4_FIELDS = frozenset({"ipv4_src", "ipv4_dst", "arp_spa", "arp_tpa"})
V6_FIELDS = frozenset({"ipv6_src", "ipv6_dst", "ipv6_nd_target"})
MAC_FIELDS = frozenset({"eth_src", "eth_dst", "arp_sha", "arp_tha", "ipv6_nd_sll",
                        "ipv6_nd_tll"})
_MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
#: How a value is said: an EtherType in hex, the rest as numbers.
_HEX = frozenset({"eth_type"})


def _said(field: str, value) -> str:
    if field in _HEX and isinstance(value, int):
        return f"{value:#06x}"
    return str(value)


def _values_said(field: str, values) -> str:
    return " or ".join(_said(field, v) for v in values)


def number(value):
    """A match field's number from an int or a form's text (`0x0800`, `2048`); None when it
    is not one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip(), 0)
        except ValueError:
            return None
    return None


def normalise(match: dict) -> dict:
    """*match* with each numeric field as a number (a form sends text), and the rest as given:
    the shape a render sends. A numeric field that is not a number is kept, and
    `problems` names it."""
    out = {}
    for key, value in (match or {}).items():
        if key in INT_FIELDS and isinstance(value, str) and number(value) is not None:
            out[key] = number(value)
        else:
            out[key] = value
    return out


def _value_problem(field: str, value) -> str:
    if field in INT_FIELDS:
        return "" if number(value) is not None and number(value) >= 0 else \
            f"{field} is a whole number, not {value!r}"
    if field in V4_FIELDS or field in V6_FIELDS:
        family, words = (4, "IPv4") if field in V4_FIELDS else (6, "IPv6")
        text = str(value).strip()
        address, slash, mask = text.partition("/")
        try:
            got = ipaddress.ip_address(address)
            if slash:
                if mask.isdigit():
                    ipaddress.ip_network(text, strict=False)
                elif ipaddress.ip_address(mask).version != got.version:
                    raise ValueError
        except ValueError:
            return f"{field} holds an {words} address or prefix, not {value!r}"
        if got.version != family:
            return f"{field} holds an {words} address, not the IPv{got.version} {text}"
        return ""
    if field in MAC_FIELDS:
        text = str(value).strip().lower()
        mac, slash, mask = text.partition("/")
        if not _MAC.match(mac) or (slash and not _MAC.match(mask)):
            return f"{field} holds a MAC address (six octets, colon-separated), not {value!r}"
    return ""


def _need(field: str, match: dict) -> str:
    """Why *field*'s prerequisite is not met by *match*, in words, or ""."""
    rule = PREREQUISITES.get(field)
    if rule is None:
        return ""
    needed, values = rule
    if needed not in match:
        want = f"{needed}" if values is None else f"{needed} {_values_said(needed, values)}"
        fix = (f"add {needed}" if values is None else
               f"add {needed} = {_said(needed, values[0])}") + f", or remove {field}"
        return f"{field} needs {want} (OpenFlow 1.3's match prerequisites): {fix}"
    if values is not None and number(match[needed]) not in values:
        return (f"{field} needs {needed} {_values_said(needed, values)}, not "
                f"{_said(needed, match[needed])} (OpenFlow 1.3's match prerequisites)")
    family = FAMILY.get(field)
    if family is not None and "eth_type" in match and number(match["eth_type"]) != family:
        return (f"{field} needs eth_type {_said('eth_type', family)} "
                f"({'ICMPv4 is IPv4' if family == ETH_IPV4 else 'ICMPv6 is IPv6'}'s), not "
                f"{_said('eth_type', match['eth_type'])}")
    return ""


def problems(match: dict) -> list:
    """Every way *match* (OpenFlow 1.3 OXM names) breaks the specification's prerequisites or
    holds a value not of its field, each in words naming the field; empty when it is sound."""
    match = dict(match or {})
    out = []
    for field in sorted(match):
        value_said = _value_problem(field, match[field])
        if value_said:
            out.append(value_said)
        need = _need(field, match)
        if need:
            out.append(need)
    return out


def set_field_problems(match: dict, actions: list) -> list:
    """Each SET_FIELD action (inside WRITE_ACTIONS too) whose field's prerequisites *match*
    does not meet, in words (section 7.2.5)."""
    out = []

    def walk(items):
        for action in items or []:
            if not isinstance(action, dict):
                continue
            if action.get("type") == "WRITE_ACTIONS":
                walk(action.get("actions"))
            elif action.get("type") == "SET_FIELD":
                field = action.get("field")
                said = _value_problem(field, action.get("value"))
                if said:
                    out.append(f"SET_FIELD: {said}")
                need = _need(field, dict(match or {}))
                if need:
                    out.append(f"SET_FIELD {field}: the flow's match must meet its "
                               f"prerequisite: {need}")

    walk(actions)
    return out


def is_table_miss(flow: dict) -> bool:
    """The table-miss flow: priority 0 and an empty match (it catches what nothing else
    does)."""
    return (flow or {}).get("priority") == 0 and not (flow or {}).get("match")
