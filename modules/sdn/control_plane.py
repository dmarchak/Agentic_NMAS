"""The control-plane guard (C2022; PHASE8_PLAN 17.7's gate, built first as a guard): no SDN
response, in any mode, may cover the network's control channel. Deterministic; no AI.

**What a response's flow may not cover** (its match, as `drivers.base.OXM_FIELDS` names it):
- **LLDP**, the controller's topology discovery: a match whose EtherType is unset or LLDP's
  (0x88cc) and that names no IP, transport or ARP field (any of those implies another
  EtherType);
- **the controller's addresses**: the connection's northbound URL host and its southbound
  address, when each is an address (a host name is said as not compared, never resolved here):
  a match whose IPv4 or IPv6 source or destination contains one;
- **OpenFlow's port**: 6653, 6633 and the southbound address's own port, when a match names
  one as its TCP source or destination, or names no address and no transport port while
  allowing TCP (its EtherType unset or IP, its protocol unset or TCP): such a match covers the
  switches' channel to the controller whatever its path.

**What is checked:** every flow a response adds, and the flow a removal takes off when that
flow names control traffic itself (LLDP's EtherType, OpenFlow's port, or a controller's own
host address): taking it off could cut the channel. A removed flow that covers the channel only
by breadth (a catch-all, or a prefix holding a controller's address) is not refused: the
response restores what the controller's own flows do. A flow re-installed
from the network's recorded intent (``reinstall``) is the network's own, never refused here.

**Not covered:** the switches' own control addresses. Mercury does not read which address
each switch reaches the controller from, so a response whose source is a switch's in-band
control address is refused only by the rules above.
"""

import ipaddress
import logging
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

ETH_LLDP = 0x88CC
#: OpenFlow's IANA port and its older one.
OPENFLOW_PORTS = (6653, 6633)
TCP = 6
_IP_ETH = (0x0800, 0x86DD)
_NOT_LLDP = ("ipv4_src", "ipv4_dst", "ipv6_src", "ipv6_dst", "ip_proto", "ip_dscp", "ip_ecn",
             "tcp_src", "tcp_dst", "udp_src", "udp_dst", "sctp_src", "sctp_dst",
             "icmpv4_type", "icmpv4_code", "icmpv6_type", "icmpv6_code", "arp_op", "arp_spa",
             "arp_tpa", "arp_sha", "arp_tha", "ipv6_flabel", "ipv6_nd_target", "mpls_label")
_ADDRESS = ("ipv4_src", "ipv4_dst", "ipv6_src", "ipv6_dst")
_PORTS = ("tcp_src", "tcp_dst", "udp_src", "udp_dst", "sctp_src", "sctp_dst")


def _int(value):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return None


def _host_port(text: str) -> tuple:
    """(host, port or None) of an address or ``host[:port]`` (IPv6 bracketed with a port)."""
    text = str(text or "").strip()
    if not text:
        return "", None
    try:
        ipaddress.ip_address(text)
        return text, None
    except ValueError:
        pass
    try:
        parts = urlsplit(text if "://" in text else f"tcp://{text}")
        return parts.hostname or "", parts.port
    except ValueError:
        return "", None


def control_channel(connection: dict) -> dict:
    """``{"addresses": [ip], "ports": [int], "not_compared": [words]}``: the controller's
    addresses and OpenFlow's ports for *connection* (its public form: ``url``,
    ``southbound``)."""
    addresses, ports, not_compared = [], list(OPENFLOW_PORTS), []
    for what, text in (("northbound URL", (connection or {}).get("url")),
                       ("southbound address", (connection or {}).get("southbound"))):
        host, port = _host_port(text)
        if not host:
            continue
        try:
            addresses.append(ipaddress.ip_address(host))
        except ValueError:
            not_compared.append(f"the {what}'s host {host} is a name, not an address, so a "
                                "match is not compared with it")
        if what == "southbound address" and port and port not in ports:
            ports.append(port)
    return {"addresses": addresses, "ports": ports, "not_compared": not_compared}


def _contains(value, address) -> bool:
    """Whether a match field's *value* (an address, ``a/len`` or ``a/mask``) covers *address*."""
    try:
        net = ipaddress.ip_network(str(value).strip(), strict=False)
    except ValueError:
        return False
    return net.version == address.version and address in net


def _host(value) -> bool:
    """Whether a match field's *value* is one host's address (a full-length prefix)."""
    try:
        net = ipaddress.ip_network(str(value).strip(), strict=False)
    except ValueError:
        return False
    return net.prefixlen == net.max_prefixlen


def covers(match: dict, channel: dict) -> list:
    """What of the control channel *match* covers: ``[(named, words)]``, *named* True when
    the match names the control traffic itself (LLDP's EtherType, OpenFlow's port, a
    controller address), False when it covers it only by naming nothing narrower; ``[]``
    when it covers none."""
    m = match or {}
    eth = _int(m.get("eth_type")) if "eth_type" in m else None
    proto = _int(m.get("ip_proto")) if "ip_proto" in m else None
    out = []
    if eth == ETH_LLDP:
        out.append((True, "LLDP (EtherType 0x88cc), the controller's topology discovery"))
    elif eth is None and not any(k in m for k in _NOT_LLDP):
        out.append((False, "LLDP: it names no EtherType and no IP field, so it matches the "
                           "controller's topology discovery"))
    for field in _ADDRESS:
        if field in m:
            # Named when the match is the controller's own host address; a wider prefix that
            # holds it covers it by breadth.
            out += [(_host(m[field]), f"the controller's address {a} ({field} {m[field]})")
                    for a in channel["addresses"] if _contains(m[field], a)]
    tcp_ok = eth in (None,) + _IP_ETH and proto in (None, TCP)
    named = [(k, _int(m[k])) for k in ("tcp_src", "tcp_dst") if k in m]
    hit = [f"{k} {p}" for k, p in named if p in channel["ports"]]
    if tcp_ok and hit:
        out.append((True, f"OpenFlow's port ({', '.join(hit)})"))
    elif tcp_ok and not named and not any(k in m for k in _ADDRESS + _PORTS):
        out.append((False, "OpenFlow: it allows TCP with no address or port, so it matches "
                           "the switches' channel to the controller (port "
                           f"{' or '.join(str(p) for p in channel['ports'])})"))
    return out


def refusal(changes: list, connection: dict) -> str:
    """Why a response's *changes* (`flow_ops`' ask) may not run, or ``""``: the first flow
    that covers the control channel, named with what it covers."""
    channel = control_channel(connection)
    for n, change in enumerate(changes or []):
        do = change.get("do")
        if do == "add_flow" and not change.get("reinstall"):
            hit = [w for _named, w in covers((change.get("flow") or {}).get("match"), channel)]
            if hit:
                return (f"change {n + 1} adds a flow whose match covers the control channel: "
                        f"{'; '.join(hit)}. No response may cover it, in any mode (C2022)")
        elif do == "remove_flow":
            hit = [w for named, w in covers((change.get("target") or {}).get("match"), channel)
                   if named]
            if hit:
                return (f"change {n + 1} removes a flow that carries the control channel: "
                        f"{'; '.join(hit)}. No response may take it off, in any mode (C2022)")
    return ""
