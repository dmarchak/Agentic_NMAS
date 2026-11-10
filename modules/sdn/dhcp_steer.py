"""DHCP steering (Lab 9 Objective 4; C2904; docs/LAB9_SDN_GAP.md A4; board lab9-sdn B, the DHCP
steering card): a client's DHCP broadcast entering the fabric at an edge port is sent as
unicast to the network's DHCP server, never flooded, and a server reply arriving on any port
but the server's is dropped (the trusted-port rule). Deterministic; no AI.

**Compiled from the committed NSOT export only** (`compile`; `modules/nsot/export.py`), never
from a controller's learning:
- **the server:** the one device carrying a NetBox Service named ``dhcp`` (`SERVICE`) on UDP
  67; its IPv4 address (the Service's own, else the device's primary IPv4); the interface that
  address sits on and that interface's MAC (the export's interface ``mac``); the switch port
  the interface is cabled to (the switch's ``openflow_datapath_id``, the port's
  ``openflow_port``). A value the export does not record is refused by name, never guessed;
- **the edge ports:** each end host's switch port (`export.host_ports`); a host whose port
  cannot be resolved refuses the whole compile, naming it (a host left out would look steered);
- **the paths:** the export's cables between switches that both record a datapath id and an
  ``openflow_port``, walked breadth first from the server's switch (ties by switch name), so
  each switch has one port toward the server and the paths form a tree (no loop).

**The flows, per switch** (`ROLES`), each in table 0:
- ``request``, one per edge port: in_port, IPv4, eth_dst ``ff:ff:ff:ff:ff:ff``, ipv4_dst
  ``255.255.255.255``, UDP, udp_dst 67; actions SET_FIELD eth_dst to the server's MAC, then
  OUTPUT toward the server (the server's own port on its switch, else the next hop's);
- ``transit``, one per switch on a path after the edge (the server's switch among them):
  IPv4, eth_dst the server's MAC, ipv4_dst ``255.255.255.255``, UDP, udp_dst 67; OUTPUT toward
  the server;
- ``reply_drop``, two per edge port: in_port, IPv4, UDP, udp_src 67, udp_dst 68, and ipv4_dst
  ``255.255.255.255`` (a broadcast OFFER or ACK) or the server's own prefix (one unicast to a
  client's offered address; the router serves the subnet of the interface it hears the request
  on); no action, a drop.

**ipv4_dst is matched and never rewritten** (the decision this module takes): a client with no
address sends to ``255.255.255.255`` (RFC 2131 section 4.1), and a server accepts that limited
broadcast delivered to its own MAC, so rewriting eth_dst alone makes the request unicast on the
wire without changing what the server reads (its reply follows the request's giaddr, ciaddr
and broadcast bit, never its IP destination). Matching ipv4_dst ``255.255.255.255`` keeps every
flow apart from the management class (`modules/protected.py`: traffic between two management
addresses, which a flow leaving IPv4 addresses unset would meet and be refused for) and from a
client's unicast renewal, which already reaches the server by the fabric's own forwarding.

**Priorities** (`flow_ops.response_priority`, the codebase's one scheme): each flow
`flow_ops.RESPONSE_PRIORITY_STEP` above the highest flow on its switch that is not Mercury's
recorded flow and could match the same packets (the fabric's forwarding entries), at least
`flow_ops.RESPONSE_PRIORITY_FLOOR`; a flow disjoint from it (the controller's LLDP flow, the
control channel's TCP) is not counted, and a priority that would reach 65535 is refused.

**Cookies:** Mercury's (`flow_intent.new_cookie`), drawn at the preview and carried by the
confirm (keyed by switch and flow, `flow_key`); every flow recorded as intent with
``response.owner`` = `OWNER`, the owner the NSOT's protected classes ``dhcp`` and
``dhcp-reply`` name (docs/LAB9_NETBOX_STEPS.md section 9), so only this feature may write them.

**Writes** go through the one flow path, `flow_ops.plan` and `flow_ops.apply` with
``writer=OWNER``, one plan per switch, the server's switch first and the edges last (so no
rewrite lands before its path); the preview shows every flow and its REST body. A confirm
rebuilds the whole preview from the export, the tables and the carried cookies, and refuses a
hash that moved, naming both. A switch whose apply fails is rolled back by `flow_ops`; the
switches this confirm already changed are then put back by the inverse of what was applied
there (`STEPS`: ``rollback``). **Remove steering** (`remove_preview`) removes exactly the flows
this feature recorded, each by delete-strict on its table, priority, match and cookie, never a
wildcard; a recorded flow no longer on its switch is named and its record closed.

**IPv6 is not covered** (`IPV6_WORDS`): DHCPv6 (UDP 546 and 547) is not steered and floods as
before; a server with no IPv4 address is refused, naming it.

**The card's counts** (`card`) come from the SDN reader's stored flows (each flow's packet
counter), never a controller call per view.
"""

import hashlib
import ipaddress
import json
import logging
import time

log = logging.getLogger(__name__)

OWNER = "feature:dhcp-unicast"
SERVICE = "dhcp"
SERVER_PORT = 67
CLIENT_PORT = 68
BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"
LIMITED_BROADCAST = "255.255.255.255"
ETH_IPV4 = 0x0800
UDP = 17
ROLES = ("request", "transit", "reply_drop")
#: The operation's steps, as the confirm reports the one reached and the manual names them
#: (docs/manual/how-it-works/dhcp-steering.md).
STEPS = ("compile", "plan", "hash", "hold", "send", "verify", "rollback", "record")
#: What the card and a refusal say of IPv6 (the board's words; CLAUDE.md, IPv6 parity).
IPV6_WORDS = "DHCPv6 (UDP 546 and 547) is not steered: it floods as before"
TOP_PRIORITY = 0xFFFF


class Refused(ValueError):
    """Steering refused before anything is sent, in words."""


# ───────────────────────────────────────────────────────────────────────────── the export

def _host(text) -> str:
    try:
        return str(ipaddress.ip_interface(str(text or "").strip()).ip) if text else ""
    except ValueError:
        return ""


def _switch(export: dict, name: str, memo: dict) -> tuple:
    """``(dpid or None, {interface: OpenFlow port number})`` for the device *name*, read as
    every OpenFlow reader reads a switch (`openflow_values.from_export`: the device's
    ``openflow_datapath_id``; each interface tagged ``openflow`` and not protected, with its
    ``openflow_port``), so a path never crosses a management port. *memo* keeps each answer
    for one compile."""
    from modules.sdn import openflow_values
    from modules.sdn.drivers.base import SpecError, parse_dpid

    if name in memo:
        return memo[name]
    if X_device(export, name) is None:
        memo[name] = (None, {})
        return memo[name]
    got = openflow_values.from_export(export, name)
    values = (got.get("values") or {}) if isinstance(got, dict) else {}
    raw = values.get("openflow.datapath_id")
    try:
        dpid = parse_dpid(raw) if raw not in (None, "") else None
    except SpecError:
        dpid = None
    ports = {k: int(v) for k, v in (values.get("port.openflow_port") or {}).items()
             if str(v).isdigit()}
    memo[name] = (dpid, ports)
    return memo[name]


def X_device(export: dict, name: str):                     # noqa: N802 (export.device, named)
    from modules.nsot import export as X

    return X.device(export, name)


def _single_ends(export: dict) -> list:
    """``[((device, iface), (device, iface))]``: each cable with one termination on each side."""
    out = []
    for c in (export.get("body") or {}).get("cables") or []:
        a, b = c.get("a") or [], c.get("b") or []
        if len(a) == 1 and len(b) == 1:
            out.append((tuple(a[0]), tuple(b[0])))
    return out


def _peer(export: dict, device: str, iface: str):
    for a, b in _single_ends(export):
        if a == (device, iface):
            return b
        if b == (device, iface):
            return a
    return None


def server_of(export: dict, memo: dict = None) -> dict:
    """The DHCP server the export names: ``{"device", "address", "prefix", "interface", "mac",
    "switch", "switch_interface", "dpid", "port_no", "service", "addresses_v6"}``. Raises
    Refused naming the value missing."""
    from modules.nsot import export as X

    memo = {} if memo is None else memo
    sha = str(export.get("sha256") or "")[:12]
    services = [s for s in X.services_named(export, SERVICE)]
    if not services:
        raise Refused(f"the committed NSOT export {sha} holds no NetBox Service named "
                      f"{SERVICE!r}: the DHCP server is the device carrying one (UDP "
                      f"{SERVER_PORT}), so nothing can be steered")
    if len(services) > 1:
        raise Refused(f"the committed NSOT export {sha} holds {len(services)} Services named "
                      f"{SERVICE!r} ({', '.join(s.get('parent') or '?' for s in services)}): "
                      "steering sends every request to one server")
    svc = services[0]
    parent = svc.get("parent") or ""
    if str(svc.get("protocol") or "").lower() != "udp" or SERVER_PORT not in (svc.get("ports")
                                                                             or []):
        raise Refused(f"the Service {SERVICE!r} on {parent} is {svc.get('protocol') or 'no '
                      'protocol'} {', '.join(map(str, svc.get('ports') or [])) or 'no port'}, "
                      f"and a DHCP server listens on UDP {SERVER_PORT}")
    device = X.device(export, parent)
    if device is None:
        raise Refused(f"the Service {SERVICE!r} names {parent!r}, and the export holds no "
                      "device of that name (is it in the network's NetBox filter?)")
    own = [_host(a) for a in svc.get("ipaddresses") or [] if _host(a)]
    v4 = [a for a in own if ipaddress.ip_address(a).version == 4]
    v6 = [a for a in own if ipaddress.ip_address(a).version == 6]
    source = "the Service's address"
    if not own:
        primary = _host(device.get("primary_ip4"))
        v4 = [primary] if primary else []
        v6 = [_host(device.get("primary_ip6"))] if _host(device.get("primary_ip6")) else []
        source = f"{parent}'s primary IPv4"
    if not v4:
        raise Refused(f"the DHCP server {parent} has no IPv4 address in the export (the Service "
                      f"names {', '.join(own) or 'none'}; its primary IPv4 is "
                      f"{device.get('primary_ip4') or 'unset'}): steering serves DHCPv4, and "
                      "IPv6 is not covered: " + IPV6_WORDS)
    address = v4[0]
    holding, prefix = None, ""
    for i in X.interfaces_of(export, parent):
        for text in i.get("ip_addresses") or []:
            if _host(text) == address:
                holding = i
                prefix = str(ipaddress.ip_interface(text).network)
    if holding is None:
        raise Refused(f"no interface of {parent} holds {address} ({source}) in the export, so "
                      "the server's MAC and switch port cannot be read")
    mac = str(holding.get("mac") or "")
    if not mac:
        raise Refused(f"the export records no MAC for {parent} {holding['name']} (the interface "
                      f"holding {address}): set its primary MAC address in NetBox and export "
                      "again (an export from before interface MACs were kept carries none)")
    att = _peer(export, parent, holding["name"])
    if att is None:
        raise Refused(f"{parent} {holding['name']} has no cable recorded in the export, so the "
                      "server's switch port is not known")
    dpid, ports = _switch(export, att[0], memo)
    port = ports.get(att[1])
    missing = []
    if dpid is None:
        missing.append(f"{att[0]} records no openflow_datapath_id")
    if port is None:
        missing.append(f"{att[0]} {att[1]} records no openflow_port (an interface tagged "
                       "openflow, not protected)")
    if missing:
        raise Refused(f"the DHCP server {parent} {holding['name']} is cabled to {att[0]} "
                      f"{att[1]}, and " + "; ".join(missing))
    return {"device": parent, "address": address, "prefix": prefix, "source": source,
            "interface": holding["name"], "mac": mac, "switch": att[0],
            "switch_interface": att[1], "dpid": dpid, "port_no": port,
            "addresses_v6": v6, "service": f"{SERVICE} UDP {SERVER_PORT}"}


def _graph(export: dict, memo: dict) -> tuple:
    """``(nodes, edges, unnumbered)``: *nodes* ``{switch: dpid}`` for every device recording a
    datapath id; *edges* ``{switch: [(port_no, peer, peer_port_no)]}`` from each cable between
    two of them whose both ports are OpenFlow ports with a number; *unnumbered* the cabled
    devices with an OpenFlow port but no datapath id (named when a path is missing)."""
    body = export.get("body") or {}
    nodes = {}
    for d in body.get("devices") or []:
        dpid, _ports = _switch(export, d["name"], memo)
        if dpid:
            nodes[d["name"]] = dpid
    edges, unnumbered = {}, set()
    for a, b in _single_ends(export):
        pa, pb = _switch(export, a[0], memo)[1].get(a[1]), _switch(export, b[0], memo)[1].get(b[1])
        if a[0] in nodes and b[0] in nodes and pa is not None and pb is not None:
            edges.setdefault(a[0], []).append((pa, b[0], pb))
            edges.setdefault(b[0], []).append((pb, a[0], pa))
        else:
            for end, p in ((a, pa), (b, pb)):
                if end[0] not in nodes and p is not None:
                    unnumbered.add(end[0])
    for k in edges:
        edges[k].sort(key=lambda e: (e[1], e[0]))
    return nodes, edges, sorted(unnumbered)


def _toward(server: dict, edges: dict) -> dict:
    """``{switch: (port toward the server, next switch or "", hops)}``, breadth first from the
    server's switch; the server's own switch outputs on the server's port."""
    out = {server["switch"]: (server["port_no"], "", 0)}
    queue = [server["switch"]]
    while queue:
        here = queue.pop(0)
        for my_port, peer, peer_port in edges.get(here, []):
            if peer not in out:
                out[peer] = (peer_port, here, out[here][2] + 1)
                queue.append(peer)
    return out


def flow_key(dpid: int, flow: dict) -> str:
    """A flow's key within the operation (its switch, its role and what distinguishes it), the
    name a confirm carries its cookie by."""
    m = flow.get("match") or {}
    tail = {"request": f"in_port={m.get('in_port')}", "transit": "any",
            "reply_drop": f"in_port={m.get('in_port')},to={m.get('ipv4_dst')}"}[flow["role"]]
    return f"{dpid}:{flow['role']}:{tail}"


def compile(export: dict, *, edge_switches=None) -> dict:      # noqa: A001 (the module's verb)
    """The steering *export* asks for, written nothing and read nothing but *export*: ``{"ok",
    "error", "export_sha256", "server", "hosts", "edge_switches", "chosen", "switches": {dpid:
    {"name", "flows": [{"role", "table_id", "match", "actions", "words"}]}}, "order", "ipv6"}``.
    *edge_switches*: the edge switches to steer on, by name (None: every one); a name that is
    no edge switch is refused. Each flow has no priority or cookie yet (`preview` gives them)."""
    from modules.nsot import export as X

    out = {"ok": False, "error": "", "export_sha256": str(export.get("sha256") or ""),
           "server": None, "hosts": [], "edge_switches": [], "chosen": [], "switches": {},
           "order": [], "ipv6": IPV6_WORDS}
    memo: dict = {}
    try:
        server = server_of(export, memo)
        out["server"] = server
        if X.hosts_of(export) is None:
            raise Refused(f"the committed NSOT export {out['export_sha256'][:12]} predates end "
                          "hosts (it has no hosts kind): export again, so each host's switch "
                          "port is read")
        rows = X.host_ports(export)
        if not rows:
            raise Refused("the export names no end host (a NetBox device tagged "
                          f"{X.HOST_TAG}), so no edge port is known")
        bad = [r["error"] for r in rows if r["error"] or r["dpid"] is None or
               r["port_no"] is None]
        if bad:
            raise Refused("an end host's switch port is not known, so it cannot be steered: "
                          + "; ".join(bad))
        clash = [f"{r['host']} {r['interface']}" for r in rows
                 if (r["switch"], r["switch_interface"]) == (server["switch"],
                                                              server["switch_interface"])]
        if clash:
            raise Refused(f"{', '.join(clash)} is recorded on the server's own port "
                          f"{server['switch']} {server['switch_interface']}: the server's port "
                          "is the trusted one, never an edge port")
        out["hosts"] = rows
        nodes, edges, unnumbered = _graph(export, memo)
        toward = _toward(server, edges)
        out["edge_switches"] = sorted({r["switch"] for r in rows})
        chosen = out["edge_switches"] if edge_switches is None else sorted(set(edge_switches))
        unknown = [s for s in chosen if s not in out["edge_switches"]]
        if unknown:
            raise Refused(f"{', '.join(unknown)} is no edge switch of this network (the edge "
                          f"switches: {', '.join(out['edge_switches'])})")
        if not chosen:
            raise Refused("no edge switch is chosen: choose one, or every one")
        out["chosen"] = chosen
        lost = [s for s in chosen if s not in toward]
        if lost:
            raise Refused(f"no path from {', '.join(lost)} to the server's switch "
                          f"{server['switch']} through the export's cables between switches "
                          "that record a datapath id and openflow_port"
                          + (f" ({', '.join(unnumbered)} records no openflow_datapath_id)"
                             if unnumbered else ""))
        flows: dict = {}

        def put(switch, flow):
            flows.setdefault(switch, [])
            if flow not in flows[switch]:
                flows[switch].append(flow)

        mac, here_port = server["mac"], None
        transit = set()
        for r in sorted(rows, key=lambda r: (r["switch"], r["port_no"])):
            if r["switch"] not in chosen:
                continue
            here_port = toward[r["switch"]][0]
            put(r["switch"], {"role": "request", "table_id": 0, "match": {
                "in_port": r["port_no"], "eth_type": ETH_IPV4, "eth_dst": BROADCAST_MAC,
                "ip_proto": UDP, "ipv4_dst": LIMITED_BROADCAST, "udp_dst": SERVER_PORT},
                "actions": [{"type": "SET_FIELD", "field": "eth_dst", "value": mac},
                            {"type": "OUTPUT", "port": here_port}],
                "words": (f"{r['host']}'s DHCP broadcasts on port {r['port_no']}: eth_dst "
                          f"rewritten to {mac}, out port {here_port} toward {server['device']}")})
            for dst in (LIMITED_BROADCAST, server["prefix"]):
                put(r["switch"], {"role": "reply_drop", "table_id": 0, "match": {
                    "in_port": r["port_no"], "eth_type": ETH_IPV4, "ip_proto": UDP,
                    "ipv4_dst": dst, "udp_src": SERVER_PORT, "udp_dst": CLIENT_PORT},
                    "actions": [], "words": (f"a DHCP server reply to {dst} arriving on "
                                             f"{r['host']}'s port {r['port_no']}: dropped")})
            hop = toward[r["switch"]][1]
            while hop:
                transit.add(hop)
                hop = toward[hop][1]
        for sw in sorted(transit):
            port = toward[sw][0]
            put(sw, {"role": "transit", "table_id": 0, "match": {
                "eth_type": ETH_IPV4, "eth_dst": mac, "ip_proto": UDP,
                "ipv4_dst": LIMITED_BROADCAST, "udp_dst": SERVER_PORT},
                "actions": [{"type": "OUTPUT", "port": port}],
                "words": (f"a steered request (eth_dst {mac}): out port {port} toward "
                          f"{server['device']}")})
        order = sorted(flows, key=lambda s: (toward[s][2], s))
        out["switches"] = {nodes[s]: {"name": s, "flows": flows[s]} for s in order}
        out["order"] = [nodes[s] for s in order]
        out["ok"] = True
    except Refused as exc:
        out["error"] = str(exc)
    return out


# ───────────────────────────────────────────────────────────────────────────── the preview

def _driver(network: str, connection: str, driver=None) -> dict:
    if driver is not None:
        return driver(network, connection)
    from modules.sdn import connections

    return connections.driver_for(network, connection)


def _ours(intent_flows: list) -> list:
    return [r for r in intent_flows or [] if (r.get("response") or {}).get("owner") == OWNER]


def role_of(flow: dict) -> str:
    """A recorded or installed steering flow's role, from its match."""
    m = flow.get("match") or {}
    if str(m.get("udp_src")) == str(SERVER_PORT):
        return "reply_drop"
    if str(m.get("eth_dst") or "").lower() == BROADCAST_MAC:
        return "request"
    return "transit"


ROLE_WORDS = {"request": "client request, unicast to the server",
              "transit": "steered request, toward the server",
              "reply_drop": "server reply on an edge port, dropped"}


def rows(plans: list) -> list:
    """Every request of *plans*, as the card's preview draws it: ``[{"dpid", "switch", "do",
    "role", "role_words", "priority", "words", "method", "path", "body"}]``, in send order."""
    out = []
    for p in plans:
        for s in p["steps"]:
            body = json.loads(s["request"]["body"])
            role = role_of(body)
            out.append({"dpid": p["dpid"], "switch": p["name"] or f"switch {p['dpid']}",
                        "do": "remove" if s["role"] == "remove_flow" else "add", "role": role,
                        "role_words": ROLE_WORDS[role], "priority": body.get("priority"),
                        "words": s["words"], "method": s["request"]["method"],
                        "path": s["request"]["path"], "body": s["request"]["body"]})
    return out


def _overall(network: str, connection: str, kind: str, export_sha: str, plans: list,
             closing: list) -> str:
    bound = {"network": network, "connection": connection, "kind": kind, "export": export_sha,
             "plans": [[p["dpid"], p["hash"]] for p in plans],
             "closing": sorted(r.get("cookie") for r in closing)}
    return hashlib.sha256(json.dumps(bound, sort_keys=True).encode("utf-8")).hexdigest()


def _base(network: str, kind: str) -> dict:
    return {"ok": False, "error": "", "network": network, "kind": kind, "connection": "",
            "export_sha256": "", "server": None, "hosts": [], "edge_switches": [],
            "chosen": [], "switches": [], "plans": [], "closing": [], "warnings": [],
            "hash": "", "cookies": {}, "ipv6": IPV6_WORDS, "flows": 0, "unchanged": 0,
            "rows": []}


def _export(network: str, export=None) -> dict:
    if export is not None:
        return export
    from modules.nsot import export as X

    got = X.read(network)
    if not got["ok"]:
        raise Refused(f"{network}'s committed NSOT export cannot be read: {got['error']}")
    return got["export"]


def _connection(network: str, connection=None) -> str:
    if connection:
        return connection
    from modules.sdn import connections

    name, why = connections.choose(network, "", purpose="the one DHCP steering writes to")
    if not name:
        raise Refused(why)
    return name


def _owner_note(network: str) -> str:
    """A warning when no protected class names `OWNER` (nothing then refuses another writer's
    flow on UDP 67)."""
    from modules import protected

    pset = protected.for_network(network)
    if pset.get("state") != "ok":
        return ""
    if any(OWNER in (c.get("owners") or []) for c in pset.get("classes") or []):
        return ""
    return (f"no protected class in {network}'s NSOT names {OWNER} as its owner, so another "
            f"writer's flow on UDP {SERVER_PORT} is not refused: declare the dhcp classes "
            "(docs/LAB9_NETBOX_STEPS.md section 9)")


def preview(network: str, *, edge_switches=None, cookies=None, driver=None, connection=None,
            export=None) -> dict:
    """Preview steering on *network*: the compile, each switch's table read now, the changes
    that make its steering flows the compiled ones (each kept flow left alone), and one
    `flow_ops.plan` per switch with changes. Writes nothing. *cookies*: ``{flow_key: cookie}``
    a confirm carries back (a key not carried draws a fresh cookie). ``{"ok", "error", "plans":
    [{"dpid", "name", "ask", "hash", "steps", "words", "kept"}], "hash", "cookies", ...}``."""
    from modules.sdn import flow_intent, flow_ops

    out = _base(network, "steer")
    cookies = dict(cookies or {})
    try:
        doc = _export(network, export)
        c = compile(doc, edge_switches=edge_switches)
        out.update(export_sha256=c["export_sha256"], server=c["server"], hosts=c["hosts"],
                   edge_switches=c["edge_switches"], chosen=c["chosen"])
        if not c["ok"]:
            raise Refused(c["error"])
        conn = _connection(network, connection)
        out["connection"] = conn
        made = _driver(network, conn, driver)
        if not made.get("ok"):
            raise Refused(made.get("error") or f"no driver for {conn!r}")
        drv = made["driver"]
        intent = flow_intent.intent(network, conn)
        if intent["state"] != "ok":
            raise Refused(f"{network}'s flow intent could not be read ({intent['error']})")
        recorded = {r.get("cookie") for r in intent["flows"]}
        ours = _ours(intent["flows"])
        dpids = list(c["order"]) + sorted({r["dpid"] for r in ours} - set(c["order"]))
        for dpid in dpids:
            want = (c["switches"].get(dpid) or {}).get("flows") or []
            name = (c["switches"].get(dpid) or {}).get("name") or ""
            got = drv.flows(dpid)
            if not got.get("ok"):
                raise Refused(f"the flow table of switch {dpid} ({name or 'not in the export'}) "
                              f"could not be read: {got.get('error')}")
            table = got.get("flows") or []
            mine = [r for r in ours if r.get("dpid") == dpid]
            installed = {f.get("cookie"): f for f in table}
            changes, kept, sw_flows = [], [], []
            matched = set()
            for w in want:
                key = flow_key(dpid, w)
                same = next((r for r in mine if r.get("cookie") in installed
                             and r.get("cookie") not in matched
                             and flow_intent.normal_match(r.get("match"))
                             == flow_intent.normal_match(w["match"])
                             and flow_intent.normal_actions(r.get("actions"))
                             == flow_intent.normal_actions(w["actions"])), None)
                if same is not None:
                    matched.add(same.get("cookie"))
                    kept.append(dict(w, key=key, cookie=same.get("cookie"),
                                     priority=same.get("priority")))
                    sw_flows.append(kept[-1])
                    continue
                prio = flow_ops.response_priority(table, intent_cookies=recorded,
                                                  match=w["match"])
                if prio >= TOP_PRIORITY:
                    raise Refused(f"switch {dpid} ({name}) holds a flow at priority 65535 that "
                                  f"meets {flow_ops.match_words(w['match'])}, so no steering "
                                  "flow can sit above it and below the control channel")
                cookie = cookies.get(key)
                if not flow_intent.is_mercury(cookie):
                    cookie = flow_intent.new_cookie()
                out["cookies"][key] = cookie
                flow = {"table_id": w["table_id"], "priority": prio, "cookie": cookie,
                        "match": dict(w["match"]), "actions": [dict(a) for a in w["actions"]],
                        "idle_timeout": 0, "hard_timeout": 0}
                changes.append({"do": "add_flow", "flow": flow})
                sw_flows.append(dict(w, key=key, cookie=cookie, priority=prio))
            removes, stale = [], []
            for r in mine:
                if r.get("cookie") in matched:
                    continue
                if r.get("cookie") in installed:
                    removes.append({"do": "remove_flow", "target": {
                        "table_id": r.get("table_id", 0), "priority": r.get("priority"),
                        "match": dict(r.get("match") or {}), "cookie": r.get("cookie")}})
                else:
                    stale.append(dict(r))
            changes = removes + changes
            # A recorded flow no longer on its switch is closed with that switch's plan; on a
            # switch steering leaves as it is, Remove steering… closes it.
            if changes:
                out["closing"] += stale
            entry = {"dpid": dpid, "name": name, "flows": sw_flows, "kept": len(kept),
                     "removed": len(removes)}
            out["switches"].append(entry)
            out["unchanged"] += len(kept)
            if not changes:
                continue
            ask = {"connection": conn, "dpid": dpid, "changes": changes}
            p = flow_ops.plan(network, ask, driver=driver, writer=OWNER)
            if not p["ok"]:
                raise Refused(f"switch {dpid} ({name or 'not in the export'}): {p['error']}")
            out["warnings"] += [w for w in p["warnings"] if w not in out["warnings"]]
            out["plans"].append({"dpid": dpid, "name": name, "ask": ask, "hash": p["hash"],
                                 "steps": p["steps"], "words": p["words"],
                                 "dpid_hex": p.get("dpid_hex", "")})
            out["flows"] += sum(1 for ch in changes if ch["do"] == "add_flow")
        note = _owner_note(network)
        if note:
            out["warnings"].append(note)
        out["rows"] = rows(out["plans"])
        out["hash"] = _overall(network, conn, "steer", out["export_sha256"], out["plans"],
                               out["closing"])
        out["ok"] = True
    except Refused as exc:
        out["error"] = str(exc)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("dhcp_steer: the preview for %s failed (%s)", network, type(exc).__name__)
        out["error"] = f"the preview could not be made: {type(exc).__name__}: {exc}"
    return out


def remove_preview(network: str, *, driver=None, connection=None) -> dict:
    """Preview Remove steering: every flow this feature recorded (``response.owner`` =
    `OWNER`), each removed by delete-strict on its table, priority, match and cookie; a recorded
    flow not on its switch is named and its record closed at the confirm. Writes nothing."""
    from modules.sdn import flow_intent, flow_ops

    out = _base(network, "remove")
    try:
        conn = _connection(network, connection)
        out["connection"] = conn
        made = _driver(network, conn, driver)
        if not made.get("ok"):
            raise Refused(made.get("error") or f"no driver for {conn!r}")
        drv = made["driver"]
        intent = flow_intent.intent(network, conn)
        if intent["state"] != "ok":
            raise Refused(f"{network}'s flow intent could not be read ({intent['error']})")
        ours = _ours(intent["flows"])
        if not ours:
            raise Refused(f"{network} has no DHCP steering flow recorded on {conn}: nothing to "
                          "remove")
        by_dpid: dict = {}
        for r in ours:
            by_dpid.setdefault(r.get("dpid"), []).append(r)
        # The edges first: their rewrite stops before the paths it used go.
        for dpid in sorted(by_dpid, key=lambda d: (-sum(1 for r in by_dpid[d]
                                                       if role_of(r) == "request"), d)):
            got = drv.flows(dpid)
            if not got.get("ok"):
                raise Refused(f"the flow table of switch {dpid} could not be read: "
                              f"{got.get('error')}")
            installed = {f.get("cookie") for f in got.get("flows") or []}
            changes = []
            for r in sorted(by_dpid[dpid], key=lambda r: (ROLES.index(role_of(r)),
                                                          r.get("cookie"))):
                if r.get("cookie") not in installed:
                    out["closing"].append(dict(r))
                    continue
                changes.append({"do": "remove_flow", "target": {
                    "table_id": r.get("table_id", 0), "priority": r.get("priority"),
                    "match": dict(r.get("match") or {}), "cookie": r.get("cookie")}})
            out["switches"].append({"dpid": dpid, "name": "", "removed": len(changes),
                                    "flows": [dict(r, role=role_of(r)) for r in by_dpid[dpid]]})
            if not changes:
                continue
            ask = {"connection": conn, "dpid": dpid, "changes": changes}
            p = flow_ops.plan(network, ask, driver=driver, writer=OWNER)
            if not p["ok"]:
                raise Refused(f"switch {dpid}: {p['error']}")
            out["plans"].append({"dpid": dpid, "name": "", "ask": ask, "hash": p["hash"],
                                 "steps": p["steps"], "words": p["words"],
                                 "dpid_hex": p.get("dpid_hex", "")})
            out["flows"] += len(changes)
        out["rows"] = rows(out["plans"])
        out["hash"] = _overall(network, conn, "remove", "", out["plans"], out["closing"])
        out["ok"] = True
    except Refused as exc:
        out["error"] = str(exc)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("dhcp_steer: the removal's preview for %s failed (%s)", network,
                  type(exc).__name__)
        out["error"] = f"the preview could not be made: {type(exc).__name__}: {exc}"
    return out


# ───────────────────────────────────────────────────────────────────────────── the confirm

def _inverse(plan: dict, applied: dict) -> dict:
    """The ask that puts a switch back as it was before *applied* (`flow_ops.apply`'s verified
    answer for *plan*): each flow it added removed by its cookie, each flow it removed added
    back as it was, with a fresh cookie (a cookie names one flow, once)."""
    from modules.sdn import flow_intent

    changes = []
    for ch in plan["ask"]["changes"]:
        if ch["do"] == "add_flow":
            f = ch["flow"]
            changes.append({"do": "remove_flow", "target": {
                "table_id": f["table_id"], "priority": f["priority"], "match": f["match"],
                "cookie": f["cookie"]}})
    for snap in (applied.get("plan") or {}).get("before") or []:
        # The snapshot's actions are `flow_intent.normal_actions`' two groups (instructions,
        # then the apply-actions in order), each action as its JSON text.
        actions = [json.loads(text) for group in snap.get("actions") or [] for text in group]
        changes.append({"do": "add_flow", "flow": {
            "table_id": snap.get("table_id", 0), "priority": snap.get("priority"),
            "cookie": flow_intent.new_cookie(), "match": snap.get("match") or {},
            "actions": actions, "idle_timeout": snap.get("idle_timeout", 0),
            "hard_timeout": snap.get("hard_timeout", 0)}})
    return {"connection": plan["ask"]["connection"], "dpid": plan["dpid"], "changes": changes}


def confirm(network: str, kind: str, confirmed_hash: str, *, actor: str, actor_verified: str = "",
            edge_switches=None, cookies=None, driver=None, connection=None, export=None,
            sleep=time.sleep, now=time.time) -> dict:
    """Apply the previewed steering (*kind* ``steer``) or its removal (``remove``) as *actor*,
    bound to *confirmed_hash*: the preview made again from the same inputs, its hash compared
    (a move refused, naming both, nothing sent), then each switch's plan through
    `flow_ops.apply` (``writer=OWNER``), which holds the switch, sends, verifies, rolls back
    and records. A switch that does not verify stops the run, and the switches it already
    changed are put back. ``{"ok", "error", "at", "outcome", "run", "switches": [...],
    "closed", "preview"}``; *outcome* ``refused``, ``verified``, ``rolled_back`` or
    ``rollback_failed``."""
    from modules.sdn import flow_intent, flow_ops

    run = f"dhcpsteer-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(now()))}"
    out = {"ok": False, "error": "", "at": "compile", "outcome": "refused", "run": run,
           "kind": kind, "network": network, "switches": [], "closed": [], "preview": None,
           "rollback": [], "actor": actor}
    if kind not in ("steer", "remove"):
        out["error"] = f"the operation is steer or remove, not {kind!r}"
        return out
    if not actor:
        out["error"] = "steering is applied by someone, and no actor was given"
        return out
    p = (preview(network, edge_switches=edge_switches, cookies=cookies, driver=driver,
                 connection=connection, export=export) if kind == "steer"
         else remove_preview(network, driver=driver, connection=connection))
    out["preview"] = p
    out["at"] = "plan"
    if not p["ok"]:
        out["error"] = p["error"]
        return out
    out["at"] = "hash"
    if p["hash"] != (confirmed_hash or ""):
        out["error"] = (f"the preview's hash was {str(confirmed_hash or '')[:12] or 'none'}, "
                        f"and the steering made now is {p['hash'][:12]}: the export, a switch's "
                        "table or the requests moved since the preview, so nothing was sent; "
                        "preview again")
        return out
    response = {"kind": "dhcp-steering", "owner": OWNER, "run": run, "operation_kind": kind}
    done = []
    out["at"] = "send"
    for plan in p["plans"]:
        got = flow_ops.apply(network, plan["ask"], plan["hash"], actor=actor,
                             actor_verified=actor_verified, driver=driver, sleep=sleep, now=now,
                             counter_interval=0, writer=OWNER, response=response)
        out["switches"].append({"dpid": plan["dpid"], "name": plan["name"],
                                "outcome": got["outcome"], "at": got["at"], "id": got["id"],
                                "error": got["error"],
                                "checks": (got.get("verify") or {}).get("checks") or []})
        if got["outcome"] != "verified":
            out["error"] = (f"switch {plan['dpid']} ({plan['name'] or 'by its record'}) "
                            f"{got['outcome'].replace('_', ' ')}: {got['error']}")
            out["at"] = "rollback"
            ok = got["outcome"] == "rolled_back"
            for prior, applied in reversed(done):
                back = _inverse(prior, applied)
                if not back["changes"]:
                    continue
                bp = flow_ops.plan(network, back, driver=driver, writer=OWNER)
                undone = (flow_ops.apply(network, back, bp["hash"], actor=actor,
                                         actor_verified=actor_verified, driver=driver,
                                         sleep=sleep, now=now, counter_interval=0, writer=OWNER,
                                         response=dict(response, rollback_of=applied["id"]))
                          if bp["ok"] else {"outcome": "refused", "error": bp["error"]})
                out["rollback"].append({"dpid": prior["dpid"], "name": prior["name"],
                                        "outcome": undone["outcome"],
                                        "error": undone.get("error", "")})
                ok = ok and undone["outcome"] == "verified"
            out["outcome"] = "rolled_back" if ok else "rollback_failed"
            return out
        done.append((plan, got))
    out["at"] = "record"
    for r in p["closing"]:
        try:
            flow_intent.record_withdrawn(network, r.get("cookie"), connection=p["connection"],
                                         actor=actor, actor_verified=actor_verified,
                                         why=f"not on switch {r.get('dpid')} at {kind} {run}")
            out["closed"].append(r.get("cookie"))
        except flow_intent.IntentRefused as exc:
            out["error"] = ((out["error"] + "; ") if out["error"] else "") + str(exc)
    out["outcome"], out["ok"] = "verified", not out["error"]
    return out


# ───────────────────────────────────────────────────────────────────────────── the card

def counts(network: str, connection: str = "", cached=None) -> dict:
    """The steering flows' packet counters from the SDN reader's stored value (never a
    controller call): ``{"state": "read"|"none"|"unread", "requests", "replies_dropped",
    "transit", "read_at", "switches", "flows", "why"}``. The counters are the switch's own,
    since each flow was installed."""
    from modules import reader_job
    from modules.readers import sdn_controllers as R
    from modules.sdn import flow_intent

    out = {"state": "unread", "requests": 0, "replies_dropped": 0, "transit": 0, "read_at": "",
           "switches": 0, "flows": 0, "recorded": 0, "unread_flows": 0, "why": ""}
    intent = flow_intent.intent(network, connection or None)
    if intent["state"] != "ok":
        out["why"] = f"the flow intent could not be read ({intent['error']})"
        return out
    ours = _ours(intent["flows"])
    out["recorded"] = len(ours)
    out["switches"] = len({r.get("dpid") for r in ours})
    if not ours:
        out["state"] = "none"
        return out
    got = cached if cached is not None else reader_job.read_cached_for(R.READER_NAME, network)
    value = (((got or {}).get("doc") or {}).get("last_good") or {}).get("value") or {}
    seen = {}
    for c in value.get("controllers") or []:
        if connection and c.get("name") != connection:
            continue
        out["read_at"] = c.get("last_good_at") or c.get("read_at") or out["read_at"]
        for s in c.get("switches") or []:
            for f in s.get("flows") or []:
                seen[f.get("cookie")] = f
    if not seen:
        out["why"] = "the SDN reader holds no read of these switches' flows yet"
        return out
    for r in ours:
        f = seen.get(r.get("cookie"))
        if f is None or f.get("packet_count") is None:
            out["unread_flows"] += 1
            continue
        out["flows"] += 1
        key = {"request": "requests", "reply_drop": "replies_dropped",
               "transit": "transit"}[role_of(r)]
        out[key] += int(f.get("packet_count") or 0)
    out["state"] = "read"
    return out


def _pick(d, keys) -> dict:
    return {k: d.get(k) for k in keys} if isinstance(d, dict) else d


def view(s: dict) -> dict:
    """What `templates/v2/_sdn_dhcp.html` draws of a card, a preview or a result, and nothing
    else (every carried field is drawn; the operation's own answer keeps the rest)."""
    hosts = s.get("hosts")
    out = {k: s.get(k) for k in ("network", "state_card", "error", "edge_switches",
                                 "steered_switches", "ipv6", "protected", "kind", "hash",
                                 "cookies", "flows", "unchanged", "warnings", "export_sha256",
                                 "connection", "chosen", "scope", "outcome") if k in s}
    out["hosts"] = len(hosts) if isinstance(hosts, list) else (hosts or 0)
    if "server" in s:
        out["server"] = _pick(s["server"], ("device", "address", "mac", "switch", "port_no",
                                            "switch_interface"))
    if "counts" in s:
        out["counts"] = _pick(s["counts"], ("state", "requests", "replies_dropped", "read_at",
                                            "unread_flows", "why"))
    if "plans" in s:
        out["switch_count"] = len(s["plans"])
    if "closing" in s:
        out["closing"] = [_pick(r, ("cookie", "cookie_hex", "dpid")) for r in s["closing"]]
    if "rows" in s:
        out["rows"] = [_pick(r, ("switch", "do", "role_words", "priority", "words", "method",
                                 "path", "body")) for r in s["rows"]]
    if s.get("state_card") == "result":
        out["switches"] = [dict(_pick(w, ("dpid", "name", "outcome", "error", "id")),
                                checks=[_pick(c, ("state", "words")) for c in
                                        w.get("checks") or []])
                           for w in s.get("switches") or []]
        out["rollback"] = [_pick(r, ("dpid", "name", "outcome", "error"))
                           for r in s.get("rollback") or []]
        out["closed"] = list(s.get("closed") or [])
    return out


def card(network: str, *, cached=None, export=None) -> dict:
    """The DHCP steering card at rest (board lab9-sdn B): the server, the edge switches, what
    is steered by Mercury's record and the stored counters. A read: no controller, no NetBox."""
    from modules.sdn import connections

    out = {"network": network, "state_card": "rest", "server": None, "error": "",
           "edge_switches": [], "hosts": 0, "steered_switches": 0, "counts": None,
           "ipv6": IPV6_WORDS, "connection": "", "protected": "", "export_sha256": ""}
    try:
        doc = _export(network, export)
    except Refused as exc:
        out["error"] = str(exc)
        doc = None
    if doc is not None:
        c = compile(doc)
        out.update(server=c["server"], edge_switches=c["edge_switches"], hosts=len(c["hosts"]),
                   export_sha256=c["export_sha256"])
        if not c["ok"]:
            out["error"] = c["error"]
    name, _why = connections.choose(network, "", purpose="the one DHCP steering writes to")
    out["connection"] = name
    out["counts"] = counts(network, name, cached=cached)
    out["steered_switches"] = out["counts"]["switches"]
    note = _owner_note(network) if out["server"] else ""
    out["protected"] = "" if not out["server"] else (
        f"NOT protected: {note}" if note else f"protected: the NSOT's dhcp classes name {OWNER}")
    return out
