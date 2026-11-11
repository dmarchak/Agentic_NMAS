"""The diagnosis runbooks' parsers (board H amendment item 1, part H14; docs/HEAL_TO_INTENT.md
19.3): each read a runbook sends, turned into the facts its rules compare.

**Only a read with a real capture is parsed** (CLAUDE.md, "Fixtures are real captures"; 19.3:
"One not captured is captured in H18 before its parser is written"). Each parser here was
written against `tests/fixtures/operational/`'s captures, or H18's (`tests/fixtures/diagnose/`,
2026-11-07: pings, routes, traceroutes, access lists, IPv6 interfaces and neighbours, the MAC
table and spanning tree), and is tested on them. A read with no
capture yet (`NOT_CAPTURED`) is still SENT, so History › Reads holds its masked answer for a
person to read, and its step says it was read and not interpreted, naming C2414; a rule that
needed it says its evidence is incomplete, never a guess.

**One reader per output, never a second copy:** CDP and LLDP are the NetBox sync's own
(`netbox_client._parse_cdp_neighbors`, `_parse_lldp_neighbors`), BGP's summary is
`bgp_summary.parse_bgp_summary`, THE one BGP summary reader, and ARP's lines the platform
pack's pattern (`endpoints.parse`, the endpoint layer's). `show ip cef` is the path trace's
(`path_trace.parse_cef`), read inside the trace.

Every parser takes the masked answer (the reads engine masks before anything is kept) and
answers ``{"state", "facts", "why"}``: ``parsed``, ``unsupported`` (the device printed IOS's
invalid-input marker: it has no such read), ``not_parsed`` (no capture yet) or ``unreadable``
(text this parser cannot read, said, never read as a quiet device).
"""

import ipaddress
import re

#: The reads whose answers are not yet interpreted (C2414). H18 captured the reach runbook's
#: (tests/fixtures/diagnose/, 2026-11-07), and they left this set: the ping to B, the
#: traceroute, a hop's route and an access list's entries, and `show ipv6 interface`. The
#: adjacency runbook's own reads stay: `show ip ospf interface`, `show ipv6 ospf interface` and
#: the link and df-bit pings are captured too (IOS-XE, IOS) but its rules do not compare them yet;
#: `show ip bgp neighbors` and the BGP ping have no capture in the suite.
NOT_CAPTURED = frozenset({"ospf_interface", "ospfv3_interface", "link_ping", "df_ping",
                          "bgp_neighbor", "bgp_ping"})
NOT_CAPTURED_WORDS = ("read, and not yet interpreted: its parser waits for a real capture of "
                      "this read (C2414)")
PARSED, UNSUPPORTED, NOT_PARSED, UNREADABLE = "parsed", "unsupported", "not_parsed", "unreadable"

#: What both platforms print for a command they do not have (measured: `show foobar` on an IOS-XE router
#: and an IOS switch, tests/fixtures/operational/; the switch's `show ospfv3 neighbor`).
INVALID = re.compile(r"^% Invalid input detected", re.MULTILINE)
#: An interface's first line, `show interfaces` and `show ip interface` alike (captures: two devices'
#: Loopback0, one router's whole `show ip interface`).
_HEAD = re.compile(r"^(?P<name>\S+) is (?P<state>administratively down|up|down), line protocol "
                   r"is (?P<proto>up|down)(?: \((?P<reason>[^)]*)\))?\s*$", re.MULTILINE)
_MTU = re.compile(r"^\s*MTU (?P<mtu>\d+) bytes", re.MULTILINE)
_ERRORS = re.compile(r"^\s*(?P<input>\d+) input errors, (?P<crc>\d+) CRC", re.MULTILINE)
_ADDRESS = re.compile(r"^\s*Internet address is (?P<address>\S+)\s*$", re.MULTILINE)
_IP_MTU = re.compile(r"^\s*MTU is (?P<mtu>\d+) bytes", re.MULTILINE)
_ACL_OUT = re.compile(r"^\s*Outgoing access list is (?P<acl>.+?)\s*$", re.MULTILINE)
_ACL_IN = re.compile(r"^\s*Inbound\s+access list is (?P<acl>.+?)\s*$", re.MULTILINE)
_NOT_SET = "not set"
_OSPF_NBR = re.compile(r"^\s*Neighbor (?P<rid>\S+), interface address (?P<address>[^,\s]+)",
                       re.MULTILINE)
_OSPF_VIA = re.compile(r"via interface (?P<interface>\S+)")
_OSPF_STATE = re.compile(r"State is (?P<state>[A-Z0-9-]+)")
_OSPFV3_ROW = re.compile(r"^(?P<rid>\d+\.\d+\.\d+\.\d+)\s+(?P<pri>\d+)\s+(?P<state>\S+)\s+"
                         r"(?P<dead>\S+)\s+(?P<ifid>\S+)\s+(?P<interface>\S+)\s*$", re.MULTILINE)


def _out(state: str, facts=None, why: str = "") -> dict:
    return {"state": state, "facts": facts, "why": why}


def _int(m, group: str):
    return int(m.group(group)) if m else None


def _blocks(text: str) -> list:
    """``[(name, block)]``: an answer split at each interface's first line (a whole table, or
    the one interface a narrowed read asked for)."""
    heads = list(_HEAD.finditer(text or ""))
    return [(h.group("name"), text[h.start():(heads[i + 1].start() if i + 1 < len(heads)
                                              else len(text))])
            for i, h in enumerate(heads)]


def _block_for(text: str, interface: str):
    from modules.nsot.ifnames import same_interface

    blocks = _blocks(text)
    if not interface:
        return blocks[0][1] if len(blocks) == 1 else None
    return next((b for n, b in blocks if same_interface(n, interface)), None)


def _state(head) -> dict:
    return {"name": head.group("name"),
            "state": head.group("state").replace("administratively down", "admin_down"),
            "protocol": head.group("proto"), "reason": head.group("reason") or ""}


def interfaces(text: str, interface: str = "") -> dict:
    """`show interfaces <if>`: its state, line protocol and why (``err-disabled``), MTU, and the
    input error and CRC counters (read twice, 10 s apart, and their difference is the
    evidence; never `clear counters`)."""
    block = _block_for(text, interface)
    head = _HEAD.search(block or "")
    if not head:
        return _out(UNREADABLE, why=f"no `{interface or 'interface'} is ...` line in the answer")
    m, e = _MTU.search(block), _ERRORS.search(block)
    return _out(PARSED, dict(_state(head), mtu=_int(m, "mtu"), input_errors=_int(e, "input"),
                             crc=_int(e, "crc")))


def ip_interface(text: str, interface: str = "") -> dict:
    """`show ip interface <if>`: its state, IPv4 address and prefix, IP MTU, and the access
    lists bound in and out (``""`` when IOS prints "not set")."""
    block = _block_for(text, interface)
    head = _HEAD.search(block or "")
    if not head:
        return _out(UNREADABLE, why=f"no `{interface or 'interface'} is ...` line in the answer")
    a, m = _ADDRESS.search(block), _IP_MTU.search(block)
    address = None
    if a:
        try:
            address = str(ipaddress.ip_interface(a.group("address")))
        except ValueError:
            address = None
    acl = {}
    for key, rx in (("acl_in", _ACL_IN), ("acl_out", _ACL_OUT)):
        g = rx.search(block)
        acl[key] = "" if not g or g.group("acl") == _NOT_SET else g.group("acl")
    return _out(PARSED, dict(_state(head), address=address, ip_mtu=_int(m, "mtu"), **acl))


def cdp(text: str, interface: str = "") -> dict:
    """`show cdp neighbors <if> detail`: who CDP says is cabled there (the sync's own reader)."""
    from modules.netbox_client import _parse_cdp_neighbors
    return _neighbours(_parse_cdp_neighbors(text or ""), interface)


def lldp(text: str, interface: str = "") -> dict:
    """`show lldp neighbors <if> detail`: who LLDP says is cabled there (the sync's own)."""
    from modules.netbox_client import _parse_lldp_neighbors
    return _neighbours(_parse_lldp_neighbors(text or ""), interface)


def _neighbours(rows: list, interface: str) -> dict:
    from modules.nsot.ifnames import same_interface

    kept = [{"host": r["remote_hostname"], "port": r["remote_iface"],
             "local": r["local_iface"]} for r in rows
            if not interface or same_interface(r["local_iface"], interface)]
    return _out(PARSED, kept)


def ospf_neighbor(text: str, interface: str = "") -> dict:
    """`show ip ospf neighbor <if> detail`: each neighbour's router id, its address on the
    link, the interface and its state (FULL, INIT, EXSTART ...)."""
    from modules.nsot.ifnames import same_interface

    heads = list(_OSPF_NBR.finditer(text or ""))
    out = []
    for i, h in enumerate(heads):
        block = text[h.start():(heads[i + 1].start() if i + 1 < len(heads) else len(text))]
        via, st = _OSPF_VIA.search(block), _OSPF_STATE.search(block)
        row = {"router_id": h.group("rid"), "address": h.group("address"),
               "interface": via.group("interface") if via else "",
               "state": st.group("state") if st else ""}
        if not interface or not row["interface"] or same_interface(row["interface"], interface):
            out.append(row)
    return _out(PARSED, out)


def ospfv3_neighbor(text: str, interface: str = "") -> dict:
    """`show ospfv3 neighbor` (IOS-XE) or `show ipv6 ospf neighbor` (IOS): the one table both
    print (two routers' captures), each neighbour's router id, state and interface."""
    from modules.nsot.ifnames import same_interface

    out = []
    for m in _OSPFV3_ROW.finditer(text or ""):
        if interface and not same_interface(m.group("interface"), interface):
            continue
        out.append({"router_id": m.group("rid"), "state": m.group("state").split("/")[0],
                    "interface": m.group("interface")})
    return _out(PARSED, out)


def peers_from_summary(text: str, interface: str = "") -> dict:
    """`show ip bgp summary` or `show bgp ipv6 unicast summary`: each peer's state and remote
    AS, by THE one BGP summary reader."""
    from modules.bgp_summary import parse_bgp_summary
    if not re.search(r"^BGP router identifier ", text or "", re.MULTILINE):
        # Both platforms print it first (two routers' captures): an answer without it is not a
        # summary, so it is never read as "no neighbours".
        return _out(UNREADABLE, why="no `BGP router identifier` line in the answer")
    got = parse_bgp_summary(text or "")
    return _out(PARSED, {"local_as": got["local_as"], "peers": [
        {"address": _canon(p["neighbor"]), "remote_as": p["remote_as"], "state": p["state"],
         "established": bool(p["established"])} for p in got["peers"]]})


#: ARP's header, both platforms (captures: a C8000v router and a vIOS-L2 switch,
#: tests/fixtures/endpoints/).
_ARP_HEAD = re.compile(r"^Protocol\s+Address\s+Age \(min\)\s+Hardware Addr", re.MULTILINE)
#: An entry IOS has asked for and not resolved: the hardware address column says so.
_ARP_INCOMPLETE = re.compile(r"^Internet\s+(?P<address>\d+\.\d+\.\d+\.\d+)\s+\S+\s+Incomplete\b",
                             re.MULTILINE)


def arp(text: str, interface: str, dialect: str) -> dict:
    """`show ip arp <next hop>`: ``{"entries": [{address, mac, interface}], "incomplete":
    [address]}``, each complete line read by the platform pack's own pattern (THE ARP reader,
    `endpoints.parse`). An answer with neither ARP's header nor an entry is unreadable, never
    read as "no entry"."""
    from modules import endpoints
    rows = endpoints.parse(dialect, "arp", text or "")
    pending = [m.group("address") for m in _ARP_INCOMPLETE.finditer(text or "")]
    if not rows and not pending and not _ARP_HEAD.search(text or ""):
        return _out(UNREADABLE, why="no ARP table in the answer")
    return _out(PARSED, {"entries": [{"address": r["address"], "mac": r["mac"],
                                      "interface": r.get("interface") or ""} for r in rows],
                         "incomplete": pending})


def _canon(address: str) -> str:
    try:
        return str(ipaddress.ip_address(address))
    except ValueError:
        return address.lower()


# ── H18's reads (tests/fixtures/diagnose/: two IOS-XE routers, an IOS switch, 2026-11-07) ──

#: `show ipv6 interface <if>`: the link-local and each global address with its subnet (both
#: platforms). Neither capture binds an IPv6 access list, so the bindings are not read.
_LINK_LOCAL = re.compile(r"^\s*IPv6 is enabled, link-local address is (?P<ll>\S+)", re.MULTILINE)
_GLOBAL6 = re.compile(r"^\s+(?P<address>[0-9A-Fa-f:]+), subnet is (?P<subnet>\S+)", re.MULTILINE)


def ipv6_interface(text: str, interface: str = "") -> dict:
    """`show ipv6 interface <if>`: its state, link-local address, each global address with its
    prefix, and the IPv6 MTU. Its access-list bindings are not read (no capture binds one)."""
    block = _block_for(text, interface)
    head = _HEAD.search(block or "")
    if not head:
        return _out(UNREADABLE, why=f"no `{interface or 'interface'} is ...` line in the answer")
    ll, m = _LINK_LOCAL.search(block), _IP_MTU.search(block)
    addresses = []
    for g in _GLOBAL6.finditer(block):
        try:
            net = ipaddress.IPv6Network(g.group("subnet"), strict=False)
            addresses.append(str(ipaddress.IPv6Interface(f"{g.group('address')}/"
                                                         f"{net.prefixlen}")))
        except ValueError:
            continue
    return _out(PARSED, dict(_state(head), link_local=_canon(ll.group("ll")) if ll else "",
                             addresses=addresses, ip_mtu=_int(m, "mtu")))


#: A ping's summary, both platforms and both families (captures: replies, timeouts and error
#: marks; `Success rate is 0 percent (0/5)` prints no round-trip times).
_SUCCESS = re.compile(r"^Success rate is (?P<pct>\d+) percent \((?P<got>\d+)/(?P<sent>\d+)\)",
                      re.MULTILINE)
_MARKS = re.compile(r"^(?P<marks>[!.A-Z?&@]+)\s*$", re.MULTILINE)
_SOURCE = re.compile(r"^Packet sent with a source address of (?P<src>\S+)", re.MULTILINE)


def ping(text: str, interface: str = "") -> dict:
    """A ping's answer: ``{sent, received, percent, marks, source, reached, all}``. Each mark
    is the device's own (`!` a reply and `.` a timeout, both captured; `X`, `H` and others are
    error answers, kept as printed and never named here). No summary line is unreadable, never
    read as "no reply"."""
    m = _SUCCESS.search(text or "")
    if not m:
        return _out(UNREADABLE, why="no `Success rate is` line in the answer")
    marks = _MARKS.search((text or "")[:m.start()])
    src = _SOURCE.search(text or "")
    got, sent = int(m.group("got")), int(m.group("sent"))
    return _out(PARSED, {"sent": sent, "received": got, "percent": int(m.group("pct")),
                         "marks": marks.group("marks") if marks else "",
                         "source": _canon(src.group("src")) if src else "",
                         "reached": got > 0, "all": sent > 0 and got == sent})


#: `show ip route <a>` and `show ipv6 route <a>` (both platforms: OSPF, OSPFv3, RIP, RIPng,
#: static to Null0, connected, the default): its prefix, what it is known via, and its paths.
_ENTRY = re.compile(r"^Routing entry for (?P<prefix>\S+?)(?:,\s*supernet)?\s*$", re.MULTILINE)
_KNOWN = re.compile(r'^\s*Known via "(?P<source>[^"]+)", distance (?P<distance>\d+), '
                    r'metric (?P<metric>\d+)(?:, type (?P<type>[^,(]+?))?(?:,|\s*$|\s*\()',
                    re.MULTILINE)
_NOT_IN_TABLE = re.compile(r"^% (?:Network|Subnet) not in table", re.MULTILINE)
_PATH4 = re.compile(r"^\s*\*?\s*(?P<nh>\d+\.\d+\.\d+\.\d+), from \S+, .*via (?P<if>\S+)\s*$",
                    re.MULTILINE)
_DIRECT4 = re.compile(r"^\s*\*?\s*directly connected, via (?P<if>\S+)", re.MULTILINE)
_PATH6 = re.compile(r"^\s{4}(?P<nh>[0-9A-Fa-f:]+), (?P<if>\S+)\s*$", re.MULTILINE)
_DIRECT6 = re.compile(r"^\s{4}(?:directly connected|receive) via (?P<if>\S+)", re.MULTILINE)


def route(text: str, interface: str = "") -> dict:
    """A route's entry: ``{in_table, prefix, source, protocol, process, distance, metric, type,
    paths: [{next_hop, interface}]}``. `% Network not in table` (IOS-XE) and `% Subnet not in
    table` (IOS) are ``in_table`` False: IPv4's lookup by address never matches the default
    route (measured on both: the read asks `show ip route 0.0.0.0` for it)."""
    text = text or ""
    if _NOT_IN_TABLE.search(text):
        return _out(PARSED, {"in_table": False, "prefix": "", "source": "", "protocol": "",
                             "process": "", "distance": None, "metric": None, "type": "",
                             "paths": []})
    e, k = _ENTRY.search(text), _KNOWN.search(text)
    if not e or not k:
        return _out(UNREADABLE, why="no `Routing entry for` and `Known via` lines in the answer")
    try:
        prefix = str(ipaddress.ip_network(e.group("prefix"), strict=False))
    except ValueError:
        return _out(UNREADABLE, why=f"not a prefix: {e.group('prefix')!r}")
    six = ":" in prefix
    paths = []
    for rx, direct in (((_PATH6, False), (_DIRECT6, True)) if six else
                       ((_PATH4, False), (_DIRECT4, True))):
        for p in rx.finditer(text):
            paths.append({"next_hop": "" if direct else _canon(p.group("nh")),
                          "interface": p.group("if")})
    source = k.group("source")
    words = source.split()
    return _out(PARSED, {"in_table": True, "prefix": prefix, "source": source,
                         "protocol": words[0], "process": " ".join(words[1:]),
                         "distance": int(k.group("distance")), "metric": int(k.group("metric")),
                         "type": (k.group("type") or "").strip(), "paths": paths})


#: A traceroute's answer (IOS-XE both families, IOS's plain form): each hop's number,
#: the address that answered, its error marks (`!X`) and its unanswered probes (`*`).
_TRACING = re.compile(r"^Tracing the route to (?P<dest>\S+)", re.MULTILINE)
_TRACE_HOP = re.compile(r"^\s*(?P<n>\d+)\s+(?P<rest>.+?)\s*$", re.MULTILINE)


def traceroute(text: str, interface: str = "") -> dict:
    """``{dest, hops: [{n, address, marks, timeouts}], last}``: *last* the last address that
    answered. Whether B was reached is not read from it: a device answers from the interface
    the probe arrived on, not B's address (captured: a switch's link address for its
    loopback)."""
    t = _TRACING.search(text or "")
    if not t:
        return _out(UNREADABLE, why="no `Tracing the route to` line in the answer")
    dest = _canon(t.group("dest"))
    hops = []
    for h in _TRACE_HOP.finditer((text or "")[t.end():]):
        tokens = h.group("rest").split()
        address = ""
        for tok in tokens:
            try:
                address = str(ipaddress.ip_address(tok))
                break
            except ValueError:
                continue
        hops.append({"n": int(h.group("n")), "address": address,
                     "marks": [x for x in tokens if x.startswith("!")],
                     "timeouts": tokens.count("*")})
    answered = [x["address"] for x in hops if x["address"]]
    return _out(PARSED, {"dest": dest, "hops": hops, "last": answered[-1] if answered else ""})


#: An access list's header and entries (an empty extended list and a standard one on IOS-XE,
#: extended and IPv6 ones on IOS). No capture printed a match count, so counts are not read.
_ACL_HEAD = re.compile(r"^(?:(?:Standard|Extended|Reflexive) )?IP(?P<six>v6)? access list "
                       r"(?P<name>\S+)", re.MULTILINE)
_ACL_ENTRY4 = re.compile(r"^\s+(?P<seq>\d+) (?P<text>.+?)\s*$", re.MULTILINE)
_ACL_ENTRY6 = re.compile(r"^\s+(?P<text>.+?) sequence (?P<seq>\d+)\s*$", re.MULTILINE)


def access_list(text: str, interface: str = "") -> dict:
    """`show ip access-lists <name>` (`show ipv6 access-list <name>`): ``{name, family,
    entries: [{seq, text}]}``. An answer with no list's header is unreadable (the device names
    a list it holds even when it has no entries)."""
    h = _ACL_HEAD.search(text or "")
    if not h:
        return _out(UNREADABLE, why="no access list's header in the answer")
    rx = _ACL_ENTRY6 if h.group("six") else _ACL_ENTRY4
    return _out(PARSED, {"name": h.group("name"), "family": 6 if h.group("six") else 4,
                         "entries": [{"seq": int(m.group("seq")), "text": m.group("text")}
                                     for m in rx.finditer(text[h.end():])]})


#: `show ipv6 neighbors <a>` (IOS-XE; vIOS-L2 refuses the address form) and `<if>` (both).
_ND_HEAD = re.compile(r"^IPv6 Address\s+Age\s+Link-layer Addr\s+State\s+Interface",
                      re.MULTILINE)
_ND_ROW = re.compile(r"^(?P<address>[0-9A-Fa-f:]+)\s+(?P<age>\S+)\s+(?P<mac>[0-9a-f]{4}\."
                     r"[0-9a-f]{4}\.[0-9a-f]{4}|-)\s+(?P<state>\S+)\s+(?P<if>\S+)\s*$",
                     re.MULTILINE)


def nd(text: str, interface: str = "") -> dict:
    """``{entries: [{address, mac, state, interface}]}``, each address in Python's form."""
    if not _ND_HEAD.search(text or ""):
        return _out(UNREADABLE, why="no IPv6 neighbour table in the answer")
    return _out(PARSED, {"entries": [
        {"address": _canon(m.group("address")), "mac": "" if m.group("mac") == "-" else
         m.group("mac"), "state": m.group("state"), "interface": m.group("if")}
        for m in _ND_ROW.finditer(text)]})


#: `show mac address-table address <mac>` (vIOS-L2).
_MAC_HEAD = re.compile(r"Mac Address Table")
_MAC_ROW = re.compile(r"^\s*(?P<vlan>\d+)\s+(?P<mac>[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+"
                      r"(?P<type>\S+)\s+(?P<port>\S+)\s*$", re.MULTILINE)


def mac_table(text: str, interface: str = "") -> dict:
    """``{entries: [{vlan, mac, type, port}]}``."""
    if not _MAC_HEAD.search(text or ""):
        return _out(UNREADABLE, why="no MAC address table in the answer")
    return _out(PARSED, {"entries": [{"vlan": int(m.group("vlan")), "mac": m.group("mac"),
                                      "type": m.group("type"), "port": m.group("port")}
                                     for m in _MAC_ROW.finditer(text)]})


#: `show spanning-tree interface <if>` (vIOS-L2): one row per VLAN.
_STP_HEAD = re.compile(r"^Vlan\s+Role\s+Sts\s+Cost", re.MULTILINE)
_STP_ROW = re.compile(r"^VLAN(?P<vlan>\d+)\s+(?P<role>\S+)\s+(?P<state>\S+)\s+(?P<cost>\d+)\s",
                      re.MULTILINE)


def stp(text: str, interface: str = "") -> dict:
    """``{vlans: [{vlan, role, state, cost}]}`` (`FWD` the forwarding state, captured)."""
    if not _STP_HEAD.search(text or ""):
        return _out(UNREADABLE, why="no spanning-tree table in the answer")
    return _out(PARSED, {"vlans": [{"vlan": int(m.group("vlan")), "role": m.group("role"),
                                    "state": m.group("state"), "cost": int(m.group("cost"))}
                                   for m in _STP_ROW.finditer(text)]})


#: `show telemetry ietf subscription all` (IOS-XE; captured 2026-10-17, tests/fixtures/diagnose/):
#: the brief's
#: heading, then one row per subscription (its id, type, state and filter type).
_TEL_HEAD = re.compile(r"^\s*ID\s+Type\s+State\s+Filter type\s*$", re.MULTILINE)
_TEL_ROW = re.compile(r"^\s*(?P<id>\d+)\s+(?P<type>\S+)\s+(?P<state>\S+)\s+(?P<filter>\S+)\s*$",
                      re.MULTILINE)


def telemetry_brief(text: str, interface: str = "") -> dict:
    """``{id: {type, state, filter}}`` for each subscription the device holds (C2828). No
    heading is unreadable, never read as a device holding none."""
    head = _TEL_HEAD.search(text or "")
    if not head:
        return _out(UNREADABLE, why="no subscription table in the answer")
    return _out(PARSED, {m.group("id"): {"type": m.group("type"), "state": m.group("state"),
                                         "filter": m.group("filter")}
                         for m in _TEL_ROW.finditer(text, head.end())})


#: `show telemetry ietf subscription <id> receiver` (IOS-XE; captured on two lab routers through
#: the reads engine, 2026-11-10, tests/fixtures/diagnose/, C2890): its heading, then one block per
#: receiver, each a ``Name: value`` line (the device prints ``Profile:`` and ``Explanation:``
#: with nothing after them). Only the Connected form is captured; the State and Explanation
#: are read as the device prints them, never mapped to a word they did not say.
_RCV_HEAD = re.compile(r"^\s*Telemetry subscription receivers detail:\s*$", re.MULTILINE)
_RCV_FIELD = re.compile(r"^\s*(?P<name>Subscription ID|Address|Port|Protocol|Profile|Connection"
                        r"|State|Explanation):[ \t]*(?P<value>.*?)[ \t\r]*$", re.MULTILINE)
_RCV_KEYS = {"Subscription ID": "subscription", "Address": "address", "Port": "port",
             "Protocol": "protocol", "Profile": "profile", "Connection": "connection",
             "State": "state", "Explanation": "explanation"}


def telemetry_receiver(text: str, interface: str = "") -> dict:
    """``{"receivers": [{subscription, address, port, protocol, profile, connection, state,
    explanation, connected}]}``: each receiver the device holds for the subscription, its
    address compressed when it is one IPv4 or IPv6 address (C2890). No heading is unreadable;
    a heading with no receiver block is the device holding none. A block with no ``State``
    line is unreadable, never read as a state."""
    head = _RCV_HEAD.search(text or "")
    if not head:
        return _out(UNREADABLE, why="no receiver detail in the answer (its heading, "
                                    "\"Telemetry subscription receivers detail:\", is absent)")
    rows, cur = [], None
    for m in _RCV_FIELD.finditer(text, head.end()):
        key = _RCV_KEYS[m.group("name")]
        if key == "subscription":
            cur = {k: "" for k in _RCV_KEYS.values()}
            rows.append(cur)
        if cur is None:
            return _out(UNREADABLE, why=f"a {m.group('name')!r} line before any receiver's "
                                        "Subscription ID")
        cur[key] = m.group("value")
    for r in rows:
        if not r["state"]:
            return _out(UNREADABLE, why=f"subscription {r['subscription']}'s receiver block "
                                        "holds no State line")
        try:
            r["address"] = ipaddress.ip_address(r["address"]).compressed
        except ValueError:
            pass
        r["port"] = int(r["port"]) if r["port"].isdigit() else None
        r["connected"] = r["state"] == "Connected"
    return _out(PARSED, {"receivers": rows})


#: Each read kind's parser (`diagnose.READS` names the kinds).
PARSERS = {"interfaces": interfaces, "ip_interface": ip_interface, "cdp": cdp, "lldp": lldp,
           "ospf_neighbor": ospf_neighbor, "ospfv3_neighbor": ospfv3_neighbor,
           "bgp_summary": peers_from_summary, "arp": arp, "ipv6_interface": ipv6_interface,
           "reach_ping": ping, "route": route, "traceroute": traceroute, "acl_counters": access_list,
           "nd": nd, "mac": mac_table, "stp": stp, "telemetry_brief": telemetry_brief,
           "telemetry_receiver": telemetry_receiver}
#: The parsers that read by the device's dialect (the platform pack's entries are per dialect).
BY_DIALECT = frozenset({"arp"})


def parse(kind: str, text: str, interface: str = "", dialect: str = "") -> dict:
    """*kind*'s answer *text* as facts: ``{"state", "facts", "why"}``. A read the platform pack
    keys by dialect (`BY_DIALECT`) is refused without its device's dialect, never read as one
    platform's by default (C452)."""
    if kind in BY_DIALECT and not dialect:
        return _out(UNSUPPORTED, why=f"the device's dialect is not known, so its {kind} answer is "
                                     "refused rather than read as another platform's (C452)")
    if INVALID.search(text or ""):
        return _out(UNSUPPORTED, why="the device has no such read (it printed IOS's invalid "
                                     "input marker)")
    if kind in NOT_CAPTURED:
        return _out(NOT_PARSED, why=NOT_CAPTURED_WORDS)
    fn = PARSERS.get(kind)
    if fn is None:
        return _out(NOT_PARSED, why=f"no parser for the read kind {kind!r}")
    try:
        return fn(text, interface, dialect) if kind in BY_DIALECT else fn(text, interface)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        return _out(UNREADABLE, why=f"the answer could not be read ({type(exc).__name__})")
