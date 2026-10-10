"""How the fleet is connected, and where it is weak: P.11 Topology's ONE reader (NSOT_PLAN P.11;
NSOT_TOPOLOGY_BRIEF section 1, signed off with boards A to C on 2026-10-04).

It reads what Prometheus already scrapes (LLDP's neighbour tables, the three routing tables,
`ifOperStatus` and `ifHighSpeed`, and `up`) and each network's committed intent, builds one graph
per layer per network, computes the analyses with NetworkX, and stores the value with its time.
Routes and the page serve the stored value; nothing here runs per request (plan section 0a).

**A physical link is the union of both ends' LLDP reports** (the brief, Q4): a link one end
reports is kept and CLASSIFIED, never dropped and never flagged wholesale: its far end not polled
(normal), or both ends polled and one silent. Ports are LLDP's own (`lldpLocPortDesc` at the near
end, `lldpRemPortId` at the far end), both the devices' short interface names, so each end's state
is its `ifOperStatus` by `ifName`: down at either end is down, naming the end.

**The routing layers are the Neighbours tab's own comparison** (`neighbours.compare`, one
implementation): an adjacency up, down, or intended by committed intent and not reported (a ghost:
the brief's "disagreement is a finding").

**The analyses** run on a MultiGraph, so parallel links never read as a bridge: islands
(connected components; each one outside the largest named with why), single points of failure
(articulation points and bridges, each with what it would cut off), and criticality
(betweenness). What LLDP cannot see is said by the page, never guessed here.
"""

import logging
import time

from modules import reader_job

log = logging.getLogger(__name__)

#: LLDP and the routing tables are scraped every 60 s (the generated targets, 2026-10-01).
#: The analyses at 900 devices and 1,355 links (betweenness is O(VE)) measured 1.1 s per layer on
#: the laptop, 2026-10-10: about 4.5 s for the four layers, inside the 60 s.
INTERVAL_SECONDS = 60
#: The series read, each one instant query for the whole fleet.
METRICS = ("lldpRemEntry", "lldpRemPortId", "ifOperStatus", "ifHighSpeed", "ospfNbrState",
           "ospfv3NbrState", "cbgpPeer2State")
LAYERS = ("physical", "ospf", "ospfv3", "bgp")
LAYER_WORDS = {"physical": "Physical (LLDP)", "ospf": "OSPF", "ospfv3": "OSPFv3", "bgp": "BGP"}
#: How many devices a criticality ranking names.
CRITICAL_TOP = 5
#: The announcement's keepalive: an unchanged graph is announced at least this often (rule 9),
#: ten reads, so a page that missed one hears the next within ten minutes.
KEEPALIVE_SECONDS = 600


def changed(previous, value) -> bool:
    """Announce only when the graph moved (the brief: "announces `topology` only on a change"):
    the value without its read time."""
    strip = lambda v: {k: x for k, x in (v or {}).items() if k != "read_at"}  # noqa: E731
    return strip(previous) != strip(value)


def short(name: str) -> str:
    """A device-announced name to the inventory's form: its first label ("s3.example.com" is
    s3). Escaping is the page's; this only shortens."""
    return (name or "").split(".")[0].strip()


def _value(row) -> float:
    try:
        return float(row["value"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return float("nan")


# ---------------------------------------------------------------------------- the fetch

def prometheus_series(list_name: str = "") -> tuple:
    """``(configured, {device: {metric: rows}}, {device: {job: 0|1}})`` for one Prometheus
    configuration. Raises when it is configured and cannot be read, so a failure is the
    reader's failure (job health), never an empty map."""
    from modules.integrations.prometheus import PrometheusIntegration

    prom = PrometheusIntegration(list_name=list_name) if list_name else PrometheusIntegration()
    if not prom.is_configured():
        return False, {}, {}
    results, up = {}, {}
    for metric in METRICS + ("up",):
        r = prom._get("api/v1/query", query=metric)
        if not r.get("ok"):
            raise RuntimeError(f"Prometheus could not be asked for {metric}: {r.get('error')}")
        for row in (r["response"].json().get("data") or {}).get("result") or []:
            m = row.get("metric") or {}
            dev = m.get("device")
            if not dev:
                continue
            if metric == "up":
                v = _value(row)
                if v == v:                                   # not NaN
                    up.setdefault(dev, {})[m.get("job", "")] = int(v)
            else:
                results.setdefault(dev, {}).setdefault(metric, []).append(row)
    return True, results, up


# ---------------------------------------------------------------------------- the graph

def _if_index(results: dict) -> dict:
    """``{(device, ifName): {"oper": 1|2|…, "speed": Mb/s or None, "descr"}}``."""
    out = {}
    for dev, metrics in results.items():
        for row in metrics.get("ifOperStatus") or []:
            m = row.get("metric") or {}
            for key in {m.get("ifName"), m.get("ifDescr")} - {None, ""}:
                out.setdefault((dev, key), {})["oper"] = int(_value(row)) \
                    if _value(row) == _value(row) else None
        for row in metrics.get("ifHighSpeed") or []:
            m = row.get("metric") or {}
            v = _value(row)
            for key in {m.get("ifName"), m.get("ifDescr")} - {None, ""}:
                out.setdefault((dev, key), {})["speed"] = int(v) if v == v else None
    return out


def _end_state(ifs: dict, dev: str, port: str) -> str:
    """One end's state from `ifOperStatus`: up, down, or unknown (not read)."""
    oper = (ifs.get((dev, port)) or {}).get("oper")
    return {1: "up", 2: "down"}.get(oper, "unknown" if oper is None else f"oper {oper}")


def physical_links(results: dict, managed: set, polled: set) -> list:
    """Every LLDP link, the union of both ends' reports: ``[{a, port_a, b, port_b, reported_by,
    kind, state, down_at, speed}]`` with ``a < b``. ``kind``: ``both`` (both ends report it),
    ``far_not_polled`` (the far end is not polled, normal), ``one_silent`` (both polled, one
    end does not report it)."""
    remport = {}
    for dev, metrics in results.items():
        for row in metrics.get("lldpRemPortId") or []:
            m = row.get("metric") or {}
            remport[(dev, m.get("lldpLocPortNum"), m.get("lldpRemIndex"))] = \
                m.get("lldpRemPortId", "")
    links = {}
    for dev, metrics in results.items():
        for row in metrics.get("lldpRemEntry") or []:
            m = row.get("metric") or {}
            far = short(m.get("lldpRemEntry", ""))
            if not far or far == dev:
                continue
            near_port = m.get("lldpLocPortDesc", "") or ""
            far_port = remport.get((dev, m.get("lldpLocPortNum"), m.get("lldpRemIndex")), "")
            ends = sorted([(dev, near_port), (far, far_port)])
            key = (ends[0][0], ends[0][1], ends[1][0], ends[1][1])
            link = links.setdefault(key, {"a": key[0], "port_a": key[1], "b": key[2],
                                          "port_b": key[3], "reported_by": []})
            if dev not in link["reported_by"]:
                link["reported_by"].append(dev)
    ifs = _if_index(results)
    out = []
    for link in links.values():
        a, b = link["a"], link["b"]
        if len(link["reported_by"]) == 2:
            kind = "both"
        else:
            other = b if link["reported_by"] == [a] else a
            kind = "one_silent" if (other in polled and other in managed) else "far_not_polled"
        states = {a: _end_state(ifs, a, link["port_a"]), b: _end_state(ifs, b, link["port_b"])}
        down = sorted(d for d, s in states.items() if s == "down")
        speeds = [s for s in ((ifs.get((a, link["port_a"])) or {}).get("speed"),
                              (ifs.get((b, link["port_b"])) or {}).get("speed")) if s]
        link.update(kind=kind, reported_by=sorted(link["reported_by"]),
                    state="down" if down else ("up" if "up" in states.values() else "unknown"),
                    down_at=down, speed=min(speeds) if speeds else None, ends=states)
        out.append(link)
    return sorted(out, key=lambda l: (l["a"], l["b"], l["port_a"], l["port_b"]))


def _iface_networks(iface: dict) -> list:
    """The networks an intent interface's addresses sit in, IPv4 and IPv6."""
    import ipaddress

    nets = []
    v4 = (iface.get("ipv4") or "").split()
    if len(v4) == 2:
        try:
            nets.append(ipaddress.ip_interface(f"{v4[0]}/{v4[1]}"))
        except ValueError:
            pass
    for v6 in iface.get("ipv6") or []:
        try:
            nets.append(ipaddress.ip_interface(v6))
        except ValueError:
            pass
    return nets


def _iface_holding(hv: dict, address: str) -> dict:
    """The intent interface of *hv* whose subnet holds *address*, or ``{}``."""
    import ipaddress

    try:
        addr = ipaddress.ip_address(address)
    except ValueError:
        return {}
    for iface in (hv or {}).get("interfaces") or []:
        if any(addr.version == n.version and addr in n.network and n.network.prefixlen <
               n.max_prefixlen for n in _iface_networks(iface)):
            return iface
    return {}


def _iface(hv: dict, name: str) -> dict:
    from modules.nsot.ifnames import same_interface
    return next((i for i in (hv or {}).get("interfaces") or []
                 if same_interface(i.get("name", ""), name)), {})


def _area(hv: dict, proto: str, port: str) -> str:
    """The OSPF area *port* is in by committed intent: OSPF's from the network statement that
    covers its address, OSPFv3's from the interface's own ``ipv6 ospf <p> area <a>``."""
    import re

    from modules.neighbours import _covered, _v4

    iface = _iface(hv, port)
    if proto == "ospfv3":
        for line in iface.get("ospfv3") or []:
            m = re.search(r"\barea (\S+)", line)
            if m:
                return m.group(1)
        return ""
    ip = _v4(iface.get("ipv4", ""))
    if ip is None:
        return ""
    for proc in ((hv or {}).get("routing") or {}).get("ospf") or []:
        for line in proc.get("networks") or []:
            m = re.search(r"\barea (\S+)", line)
            if m and _covered(ip.ip, line):
                return m.group(1)
    return ""


def _local_port(hv: dict, proto: str, row: dict) -> str:
    """The interface *row*'s adjacency leaves this device on: an OSPF row's own (`via`), else
    the interface whose subnet holds the neighbour's address (a BGP peer, an unexpected OSPF
    neighbour); ``""`` when none does (a peering between loopbacks)."""
    if proto in ("ospf", "ospfv3") and row.get("via"):
        return row["via"]
    return _iface_holding(hv, row.get("address") or "").get("name", "")


def _own_as(hv: dict) -> str:
    return str((((hv or {}).get("routing") or {}).get("bgp") or {}).get("asn") or "")


def routing_links(intents: dict, hosts: list, results: dict, up: dict) -> dict:
    """``{layer: [{a, b, state, words, intended, ports, area, asn, network}]}`` for OSPF,
    OSPFv3 and BGP, through the Neighbours tab's comparison: one row per adjacency, ``state`` up,
    down or not_seen (intent implies it, nothing reports it: drawn as a ghost).

    The facts the map labels each neighbourship with (the operator, 2026-10-10): ``ports``, each
    end's interface it leaves on; ``area``, OSPF's and OSPFv3's by committed intent; ``asn``,
    each end's AS (its own from intent, the peer's from the neighbour statement)."""
    from modules.neighbours import compare

    out = {"ospf": {}, "ospfv3": {}, "bgp": {}}
    rank = {"down": 3, "not_seen": 2, "up": 1}
    for host in hosts:
        hv = intents.get(host) or {}
        view = compare(intents, host, results.get(host, {}), up.get(host, {}))
        for p in view["protocols"]:
            proto = p["proto"]
            for r in p["rows"]:
                peer = r.get("peer") or ""
                external = ""
                if not peer:
                    # A peer outside management (an eBGP neighbour, C648): a node named by its
                    # address, never dropped.
                    external = r.get("address") or ""
                    peer = external
                if not peer:
                    continue
                a, b = sorted((host, peer))
                port = _local_port(hv, proto, r)
                network = r.get("network", "")
                if not network:
                    # An unexpected neighbour: keyed by its subnet (or address family), so both
                    # ends' reports of it are one adjacency.
                    held = _iface_holding(hv, r.get("address") or "")
                    nets = _iface_networks(held)
                    network = str(nets[0].network) if nets and proto == "ospf" else \
                        (f"ipv{6 if ':' in (r.get('address') or '') else 4}"
                         if proto == "bgp" else r.get("address", ""))
                key = (a, b, network)
                state = r["state"]
                if state == "unexpected":
                    state = "up" if r.get("up") else "down"
                cur = out[proto].setdefault(key, {
                    "a": a, "b": b, "state": "", "words": "", "intended": False,
                    "external": external, "network": network, "ports": {}, "area": "",
                    "asn": {}, "words_by": {}})
                if rank.get(state, 0) > rank.get(cur["state"], 0):
                    cur.update(state=state, words=r.get("words", ""))
                cur["intended"] = cur["intended"] or r["state"] != "unexpected"
                cur["words_by"][host] = r.get("words", "")
                if port:
                    cur["ports"][host] = port
                    if proto in ("ospf", "ospfv3") and not cur["area"]:
                        cur["area"] = _area(hv, proto, port)
                if proto == "bgp":
                    if _own_as(hv):
                        cur["asn"][host] = _own_as(hv)
                    via = r.get("via") or ""
                    if via.startswith("AS "):
                        cur["asn"].setdefault(peer, via[3:])
    return {layer: sorted(v.values(), key=lambda l: (l["a"], l["b"], l["network"]))
            for layer, v in out.items()}


#: The node Mercury's own host is drawn as: never a device name (a hostname cannot start "@").
MANAGER = "@mercury"


def here() -> list:
    """This host's own interface addresses, ``[(ifname, "address/prefix")]``, loopback and
    link-local left out: IPv4 by `SIOCGIFADDR` and `SIOCGIFNETMASK` (each interface's primary
    address), IPv6 from `/proc/net/if_inet6`. Linux; elsewhere, or unreadable, ``[]``. A local
    read: no packet leaves the host."""
    import fcntl
    import ipaddress
    import socket
    import struct

    out = []
    try:
        names = [n for _i, n in socket.if_nameindex()]
    except OSError:
        names = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for name in names:
            req = struct.pack("256s", name.encode()[:15])
            try:
                addr = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, req)[20:24])
                mask = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x891B, req)[20:24])
            except OSError:
                continue
            out.append((name, str(ipaddress.ip_interface(f"{addr}/{mask}"))))
    finally:
        s.close()
    try:
        with open("/proc/net/if_inet6", encoding="ascii") as fh:
            for line in fh:
                f = line.split()
                if len(f) < 6:
                    continue
                addr = ":".join(f[0][i:i + 4] for i in range(0, 32, 4))
                out.append((f[5], str(ipaddress.ip_interface(f"{addr}/{int(f[2], 16)}"))))
    except OSError:
        pass
    keep = []
    for name, iface in out:
        ip = ipaddress.ip_interface(iface)
        if not (ip.ip.is_loopback or ip.ip.is_link_local):
            keep.append((name, iface))
    return keep


def _vlan_of_svi(name: str) -> str:
    import re
    m = re.match(r"(?i)^vlan\s*(\d+)$", name or "")
    return m.group(1) if m else ""


def _carries(iface: dict, vlan: str) -> bool:
    """Whether a switchport carries *vlan*: its access VLAN, or on a trunk's allowed list."""
    if not vlan or not iface:
        return False
    if iface.get("switchport_mode") == "access" or iface.get("switchport_access_vlan"):
        return str(iface.get("switchport_access_vlan") or "1") == vlan
    if iface.get("switchport_mode") == "trunk":
        allowed = iface.get("switchport_trunk_vlans") or []
        return not allowed or any(_in_range(vlan, v) for v in allowed)
    return False


def _in_range(vlan: str, spec: str) -> bool:
    for part in str(spec).split(","):
        lo, _, hi = part.strip().partition("-")
        try:
            if int(lo) <= int(vlan) <= int(hi or lo):
                return True
        except ValueError:
            continue
    return False


def attach(phys: list, layers: dict, intents: dict) -> None:
    """Each routing adjacency onto the physical links it runs over, in place: a link carries an
    adjacency at an end whose port the adjacency leaves on, or, for a switch's VLAN interface
    (`VlanN`), at a port carrying that VLAN whose LLDP neighbour is the adjacency's peer. Each
    link gains ``adj`` (``[{layer, i, at}]``, *i* the adjacency's index in its layer, *at* the
    ends it was seen leaving from); each adjacency ``on_link`` (whether any link carries it)."""
    from modules.nsot.ifnames import same_interface

    for l in phys:
        l["adj"] = []
    for layer in ("ospf", "ospfv3", "bgp"):
        for i, adj in enumerate(layers.get(layer) or []):
            adj["on_link"] = False
            for l in phys:
                at = []
                for end, port, far in (("a", l["port_a"], l["b"]), ("b", l["port_b"], l["a"])):
                    dev = l[end]
                    mine = (adj.get("ports") or {}).get(dev)
                    if dev not in (adj["a"], adj["b"]) or not mine:
                        continue
                    other = adj["b"] if dev == adj["a"] else adj["a"]
                    vlan = _vlan_of_svi(mine)
                    if same_interface(port, mine) or (
                            vlan and far == other and
                            _carries(_iface(intents.get(dev), port), vlan)):
                        at.append(dev)
                if at:
                    l["adj"].append({"layer": layer, "i": i, "at": at})
                    adj["on_link"] = True


def unread_protocols(phys: list, intents: dict) -> None:
    """Each link end's routing protocol committed intent configures that no reader reads (RIPng:
    `ipv6 rip <name> enable`), in place, as ``unread`` (``{device: ["RIPng"]}``): drawn as not
    read, never as up."""
    for l in phys:
        l["unread"] = {}
        for end, port in (("a", l["port_a"]), ("b", l["port_b"])):
            iface = _iface(intents.get(l[end]), port)
            if any(" enable" in f" {x}" for x in iface.get("ripng") or []):
                l["unread"].setdefault(l[end], []).append("RIPng")


def manager_links(intents: dict, phys: list, ifs: dict, at_here: list) -> list:
    """Where Mercury's own host attaches, MEASURED (the board's manager node, 2026-10-04): a
    managed device's interface whose subnet holds one of this host's own addresses. A routed
    port is the link's far end; a VLAN interface's is the port carrying that VLAN with no LLDP
    neighbour among the devices (the one facing the host), named when exactly one does."""
    import ipaddress

    from modules.nsot.ifnames import abbreviate, same_interface

    mine = []
    for name, iface in at_here or []:
        try:
            mine.append((name, ipaddress.ip_interface(iface)))
        except ValueError:
            continue
    out = []
    for dev in sorted(intents):
        for iface in (intents.get(dev) or {}).get("interfaces") or []:
            nets = _iface_networks(iface)
            hit = next(((n, m) for n, m in mine for d in nets
                        if m.version == d.version and m.ip in d.network and m.ip != d.ip
                        and d.network.prefixlen < d.max_prefixlen), None)
            if not hit:
                continue
            port, vlan = abbreviate(iface.get("name", "")), _vlan_of_svi(iface.get("name", ""))
            if vlan:
                used = {l["port_a"] for l in phys if l["a"] == dev} | \
                       {l["port_b"] for l in phys if l["b"] == dev}
                facing = [abbreviate(i.get("name", ""))
                          for i in (intents.get(dev) or {}).get("interfaces") or []
                          if _carries(i, vlan) and not any(same_interface(u, i.get("name", ""))
                                                           for u in used)]
                port = facing[0] if len(facing) == 1 else ""
            state = _end_state(ifs, dev, port) if port else "unknown"
            out.append({"a": MANAGER, "port_a": hit[0], "b": dev, "port_b": port,
                        "via": abbreviate(iface.get("name", "")), "vlan": vlan,
                        "reported_by": [], "kind": "address", "manager": True,
                        "state": "down" if state == "down" else
                        ("up" if state == "up" else "unknown"),
                        "down_at": [dev] if state == "down" else [], "speed": None,
                        "ends": {dev: state}, "adj": [], "unread": {}})
    return out


def _link_key(layer: str, l: dict) -> str:
    if layer == "physical":
        return f"{l['a']}|{l['port_a']}|{l['b']}|{l['port_b']}"
    return f"{l['a']}|{l['b']}|{l.get('network', '')}"


def carry_since(layers: dict, before: dict, now: str) -> None:
    """Each link's and adjacency's ``since``, in place: carried from the last good read while
    its state holds; *now* when it changed (``since_seen``: the change happened under watch),
    or on the first read, when it is only "at least since"."""
    for layer, links in layers.items():
        was_layer = (before or {}).get(layer) or {}
        for l in links:
            was = was_layer.get(_link_key(layer, l))
            if was and was.get("state") == l.get("state"):
                l["since"], l["since_seen"] = was.get("since") or now, bool(was.get("since_seen"))
            else:
                l["since"], l["since_seen"] = now, was is not None


def analyse(nodes: list, links: list) -> dict:
    """Islands, single points of failure and criticality over a MultiGraph of *links* that
    carry traffic (state up or unknown; a down or ghost link carries nothing)."""
    import networkx as nx

    g = nx.MultiGraph()
    g.add_nodes_from(nodes)
    for l in links:
        if l.get("state") in ("up", "unknown"):
            g.add_edge(l["a"], l["b"])
    comps = sorted((sorted(c) for c in nx.connected_components(g)), key=lambda c: (-len(c), c))
    main = set(comps[0]) if comps else set()
    simple = nx.Graph(g)
    parallel = {tuple(sorted((u, v))) for u, v in g.edges() if g.number_of_edges(u, v) > 1}
    bridges = []
    for u, v in nx.bridges(simple):
        pair = tuple(sorted((u, v)))
        if pair in parallel:
            continue
        cut = simple.copy()
        cut.remove_edge(u, v)
        lost = sorted(min(nx.connected_components(cut), key=len))
        bridges.append({"a": pair[0], "b": pair[1], "cuts_off": lost})
    spof = []
    for node in sorted(nx.articulation_points(simple)):
        # Within its own component (C651): an island it never joined is not cut off by it.
        cut = simple.subgraph(nx.node_connected_component(simple, node)).copy()
        cut.remove_node(node)
        parts = sorted((sorted(c) for c in nx.connected_components(cut)), key=len)
        spof.append({"device": node, "cuts_off": sorted(d for c in parts[:-1] for d in c)})
    between = nx.betweenness_centrality(simple) if simple.number_of_nodes() > 2 else {}
    ranked = sorted(((round(v, 3), n) for n, v in between.items() if v > 0), reverse=True)
    return {"components": len(comps), "main": sorted(main),
            "islands": [c for c in comps[1:]], "spof": spof,
            "bridges": sorted(bridges, key=lambda b: (b["a"], b["b"])),
            "critical": [{"device": n, "betweenness": v} for v, n in ranked[:CRITICAL_TOP]]}


def network_graph(hosts: list, roles: dict, intents: dict, results: dict, up: dict,
                  expected: dict = None, previous: dict = None, now: str = "",
                  at_here: list = None, before_links: dict = None) -> dict:
    """One network's graph, every layer and its analysis. *hosts* is the inventory (the
    population: a managed device the graph lacks is still a node, drawn apart with why).
    *expected* is the network's declared islands (``{device: {reason, by, at}}``); *previous*
    is each layer's islands at the last good read (``{layer: {device: {since}}}``, None on the
    first read), so a device that becomes an island is told apart from one that was.
    *at_here* is this host's own addresses (`here()`), for where Mercury attaches;
    *before_links* each layer's link states at the last good read, for each one's since."""
    managed = set(hosts)
    polled = {h for h in hosts if (up.get(h) or {}).get("lldp") == 1}
    answering = {h for h in hosts if any(v == 1 for v in (up.get(h) or {}).values())}
    phys = physical_links({h: results.get(h, {}) for h in hosts}, managed, polled)
    others = sorted({e for l in phys for e in (l["a"], l["b"])} - managed)
    nodes = {}
    for h in sorted(hosts):
        nodes[h] = {"managed": True, "role": roles.get(h, ""), "polled": h in polled,
                    "answering": h in answering, "lldp_read": "lldp" in (up.get(h) or {})}
    for o in others:
        nodes[o] = {"managed": False, "role": "", "polled": False, "answering": False,
                    "lldp_read": False}
    layers = {"physical": phys}
    layers.update(routing_links(intents, hosts, results, up))
    # An OUTSIDE PEER (the operator, 2026-10-10: r5, decommissioned, still r4's eBGP neighbour)
    # is a device the fleet peers with and does not manage: never a fleet node, never an island.
    # LLDP names it; a routing peer known only by its address is named through the LLDP
    # neighbour on the interface whose subnet holds that address.
    for o in others:
        nodes[o]["outside"] = True
        nodes[o]["seen_by"] = sorted({l["a"] if l["b"] == o else l["b"] for l in phys
                                      if o in (l["a"], l["b"])})
    for layer in ("ospf", "ospfv3", "bgp"):
        for l in layers[layer]:
            if not l.get("external"):
                continue
            mine = l["a"] if l["b"] == l["external"] else l["b"]
            named = _peer_by_lldp(intents.get(mine) or {}, mine, l["external"], phys)
            address = l["external"]
            if named:
                l["a"], l["b"] = sorted((mine, named))
                l["external"], l["address"] = named, address
                if address in (l.get("asn") or {}):
                    l["asn"][named] = l["asn"].pop(address)
            if l["external"] not in nodes:
                nodes[l["external"]] = {"managed": False, "role": "", "polled": False,
                                        "answering": False, "lldp_read": False,
                                        "outside": True, "external": not named,
                                        "seen_by": []}
            if mine not in nodes[l["external"]]["seen_by"]:
                nodes[l["external"]]["seen_by"] = sorted(nodes[l["external"]]["seen_by"] +
                                                         [mine])
    # Mercury's own host, where it attaches by measurement: a node of the physical layer, so a
    # device that is its only way in is a single point of failure (the board's s3).
    mgr = manager_links({h: intents.get(h) for h in hosts if intents.get(h)}, phys,
                        _if_index({h: results.get(h, {}) for h in hosts}), at_here)
    if mgr:
        nodes[MANAGER] = {"managed": False, "role": "", "polled": False, "answering": True,
                          "lldp_read": False, "manager": True}
        phys.extend(mgr)
    attach(phys, layers, intents)
    unread_protocols(phys, intents)
    from modules.nsot.ifnames import abbreviate
    taking_part = {e for layer in ("ospf", "ospfv3", "bgp") for l in layers[layer]
                   for e in (l["a"], l["b"])}
    for h in hosts:
        nodes[h]["l3"] = h in taking_part
        nodes[h]["addresses"] = [[abbreviate(i.get("name", "")), str(n.ip)]
                                 for i in (intents.get(h) or {}).get("interfaces") or []
                                 for n in _iface_networks(i)]
    carry_since(layers, before_links, now)
    expected = expected or {}
    analysis = {}
    for layer, links in layers.items():
        # A routing layer's population is the devices taking part in it (C648): a switch that
        # runs no OSPF is not an island of the OSPF layer.
        # The physical layer's: the inventory and LLDP's own neighbours, never a routing peer
        # known only by its address.
        names = sorted(n for n, v in nodes.items() if not v.get("external")) \
            if layer == "physical" else sorted({e for l in links for e in (l["a"], l["b"])})
        a = analyse(names, links)
        # An island is of the FLEET: an outside peer cut off is not one of ours.
        a["islands"] = [m for m in ([d for d in i if (nodes.get(d) or {}).get("managed")]
                                    for i in a["islands"]) if m]
        before = (previous or {}).get(layer) or {}
        a["island_why"], a["island_state"] = {}, {}
        for island in a["islands"]:
            for d in island:
                a["island_why"][d] = _why_apart(d, nodes.get(d) or {}, layer, len(island) == 1)
                declared = expected.get(d) if layer == "physical" else None
                was = before.get(d) or {}
                a["island_state"][d] = {
                    # Declared apart by a person, with why: drawn as expected, never a warning.
                    "expected": declared or None,
                    # Since when it has been an island, carried from the last good read; a
                    # device that BECOMES one is new this read and warned.
                    "since": was.get("since") or now,
                    "became": not was and previous is not None,
                    "warn": not declared}
        analysis[layer] = a
    # Where each device sits on the map, laid out once here so a page view never does
    # (modules/topology_layout.py).
    from modules import topology_layout
    try:
        laid = topology_layout.layout(nodes, phys)
    except Exception as exc:                         # noqa: BLE001 (the page lays out instead)
        log.warning("topology: the map could not be laid out (%s); the page lays it out", exc)
        laid = None
    return {"nodes": nodes, "layers": layers, "analysis": analysis, "layout": laid}


def _peer_by_lldp(hv: dict, host: str, address: str, phys: list) -> str:
    """The LLDP neighbour on *host*'s interface whose subnet holds *address*, or ``""``."""
    import ipaddress

    from modules.nsot.ifnames import same_interface

    try:
        addr = ipaddress.ip_address(address)
    except ValueError:
        return ""
    for iface in hv.get("interfaces") or []:
        nets = []
        v4 = (iface.get("ipv4") or "").split()
        if len(v4) == 2:
            try:
                nets.append(ipaddress.ip_interface(f"{v4[0]}/{v4[1]}").network)
            except ValueError:
                pass
        for v6 in iface.get("ipv6") or []:
            try:
                nets.append(ipaddress.ip_interface(v6).network)
            except ValueError:
                pass
        if not any(addr.version == n.version and addr in n for n in nets):
            continue
        for l in phys:
            if l["a"] == host and same_interface(l["port_a"], iface.get("name", "")):
                return l["b"]
            if l["b"] == host and same_interface(l["port_b"], iface.get("name", "")):
                return l["a"]
    return ""


def _why_apart(device: str, node: dict, layer: str, alone: bool) -> str:
    if not node.get("managed"):
        return "not managed: seen only in a neighbour's report"
    if layer == "physical":
        if not node.get("lldp_read"):
            return "not polled: no LLDP target scrapes it (its golden configures no SNMP)"
        if not node.get("polled"):
            return "not polled now: its last LLDP scrape failed"
        return ("no LLDP neighbour among the managed devices" if alone else
                "connected only among themselves: no LLDP link reaches the rest")
    return (f"no {LAYER_WORDS[layer]} adjacency up to the rest" if alone else
            f"its {LAYER_WORDS[layer]} adjacencies reach only each other")


# ---------------------------------------------------------------------------- the reader

def read(source=None, population=None, clock=time.time, previous=None, expected=None,
         at_here=None) -> dict:
    from modules import integration_groups as IG
    from modules.neighbours import committed_intents
    from modules.readers.adjacencies import lists

    configured, results, up = (source or (lambda: IG.merged("prometheus",
                                                            prometheus_series)))()
    if not configured:
        return {"configured": False, "networks": {}, "errors": []}
    if previous is None:
        got = reader_job.read_cached(READER_NAME)
        last = (got.get("doc") or {}).get("last_good")
        previous = (last or {}).get("value") if last else None
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock()))
    networks, errors = {}, []
    for list_name, ref, hosts in (population or lists)():
        intents, err = committed_intents(ref.repo_dir)
        if err:
            errors.append(f"{list_name}: {err}")
        roles = {}
        for h in hosts:
            for metric in ("lldpRemEntry", "ifOperStatus"):
                for row in (results.get(h) or {}).get(metric) or []:
                    roles.setdefault(h, (row.get("metric") or {}).get("role", ""))
        declared = (expected or _expected)(list_name)
        if declared.get("state") == "unreadable":
            errors.append(f"{list_name}: {declared['error']}")
        before, before_links = None, None
        if previous is not None:
            was = (previous.get("networks") or {}).get(list_name) or {}
            before = {layer: a.get("island_state") or {}
                      for layer, a in (was.get("analysis") or {}).items()}
            before_links = {layer: {_link_key(layer, l): {k: l.get(k) for k in
                                                          ("state", "since", "since_seen")}
                                    for l in links}
                            for layer, links in (was.get("layers") or {}).items()}
        networks[list_name] = network_graph(hosts, roles, intents, results, up,
                                            expected=declared.get("islands") or {},
                                            previous=before, now=now,
                                            at_here=here() if at_here is None else at_here,
                                            before_links=before_links)
    return {"configured": True, "networks": networks, "errors": errors, "read_at": now}


READER_NAME = "topology-graph"


def _expected(list_name: str) -> dict:
    from modules import topology_expected
    try:
        return topology_expected.read(list_name)
    except Exception as exc:                         # noqa: BLE001 (said as the read's error)
        return {"state": "unreadable", "islands": {}, "error": str(exc)}


READER = reader_job.register(reader_job.Reader(
    name=READER_NAME,
    what="how each network is connected, layer by layer, and where it is weak (P.11)",
    endpoints=("Prometheus: GET /api/v1/query for lldpRemEntry, lldpRemPortId, ifOperStatus, "
               "ifHighSpeed, ospfNbrState, ospfv3NbrState, cbgpPeer2State and up "
               "(the whole fleet, per configuration)",
               "this host: each list's committed host_vars at HEAD"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the LLDP and routing jobs' scrape interval (60 s since 2026-10-01): a "
                    "faster read only re-reads the same sample"),
    read=read,
    invalidates=("topology",),
    remedy="Read the error above: it names what Prometheus or the repository answered",
    window="Prometheus's last sample of each device's LLDP and routing tables",
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
