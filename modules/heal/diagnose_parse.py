"""The diagnosis runbooks' parsers (board H amendment item 1, part H14; docs/HEAL_TO_INTENT.md
19.3): each read a runbook sends, turned into the facts its rules compare.

**Only a read with a real capture is parsed** (CLAUDE.md, "Fixtures are real captures"; 19.3:
"One not captured is captured in H18 before its parser is written"). Each parser here was
written against `tests/fixtures/operational/`'s captures and is tested on them. A read with no
capture yet (`NOT_CAPTURED`) is still SENT, so History › Reads holds its masked answer for a
person to read, and its step says it was read and not interpreted, naming C2414; a rule that
needed it says its evidence is incomplete, never a guess.

**One reader per output, never a second copy:** CDP and LLDP are the NetBox sync's own
(`netbox_client._parse_cdp_neighbors`, `_parse_lldp_neighbors`), BGP's summary is
`bgp_summary.parse_bgp_summary`, THE one BGP summary reader.

Every parser takes the masked answer (the reads engine masks before anything is kept) and
answers ``{"state", "facts", "why"}``: ``parsed``, ``unsupported`` (the device printed IOS's
invalid-input marker: it has no such read), ``not_parsed`` (no capture yet) or ``unreadable``
(text this parser cannot read, said, never read as a quiet device).
"""

import ipaddress
import re

#: The reads whose parser waits for a real capture (C2414; captured on an IOS-XE router and an IOS switch in H18).
NOT_CAPTURED = frozenset({"ospf_interface", "ospfv3_interface", "ipv6_interface", "link_ping",
                          "df_ping", "bgp_neighbor", "bgp_ping"})
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


def _canon(address: str) -> str:
    try:
        return str(ipaddress.ip_address(address))
    except ValueError:
        return address.lower()


#: Each read kind's parser (`diagnose.READS` names the kinds).
PARSERS = {"interfaces": interfaces, "ip_interface": ip_interface, "cdp": cdp, "lldp": lldp,
           "ospf_neighbor": ospf_neighbor, "ospfv3_neighbor": ospfv3_neighbor,
           "bgp_summary": peers_from_summary}


def parse(kind: str, text: str, interface: str = "") -> dict:
    """*kind*'s answer *text* as facts: ``{"state", "facts", "why"}``."""
    if INVALID.search(text or ""):
        return _out(UNSUPPORTED, why="the device has no such read (it printed IOS's invalid "
                                     "input marker)")
    if kind in NOT_CAPTURED:
        return _out(NOT_PARSED, why=NOT_CAPTURED_WORDS)
    fn = PARSERS.get(kind)
    if fn is None:
        return _out(NOT_PARSED, why=f"no parser for the read kind {kind!r}")
    try:
        return fn(text, interface)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        return _out(UNREADABLE, why=f"the answer could not be read ({type(exc).__name__})")
