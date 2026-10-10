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


def routing_links(intents: dict, hosts: list, results: dict, up: dict) -> dict:
    """``{layer: [{a, b, state, words, intended}]}`` for OSPF, OSPFv3 and BGP, through the
    Neighbours tab's comparison: one row per adjacency, ``state`` up, down or not_seen (intent
    implies it, nothing reports it: drawn as a ghost)."""
    from modules.neighbours import compare

    out = {"ospf": {}, "ospfv3": {}, "bgp": {}}
    for host in hosts:
        view = compare(intents, host, results.get(host, {}), up.get(host, {}))
        for p in view["protocols"]:
            for r in p["rows"]:
                peer = r.get("peer") or ""
                external = ""
                if not peer:
                    # A peer outside management (an eBGP neighbour, C648): a node named by its
                    # address, never dropped.
                    external = r.get("address") or ""
                    peer = external
                if not peer or r["state"] == "unknown":
                    continue
                a, b = sorted((host, peer))
                key = (a, b, r.get("network", "") or r.get("address", ""))
                state = r["state"]
                if state == "unexpected":
                    state = "up" if r.get("up") else "down"
                cur = out[p["proto"]].get(key)
                rank = {"down": 3, "not_seen": 2, "up": 1}
                if cur is None or rank.get(state, 0) > rank.get(cur["state"], 0):
                    out[p["proto"]][key] = {"a": a, "b": b, "state": state,
                                            "words": r.get("words", ""),
                                            "intended": r["state"] != "unexpected",
                                            "external": external}
    return {layer: sorted(v.values(), key=lambda l: (l["a"], l["b"]))
            for layer, v in out.items()}


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
        cut = simple.copy()
        cut.remove_node(node)
        parts = sorted((sorted(c) for c in nx.connected_components(cut)), key=len)
        spof.append({"device": node, "cuts_off": sorted(d for c in parts[:-1] for d in c)})
    between = nx.betweenness_centrality(simple) if simple.number_of_nodes() > 2 else {}
    ranked = sorted(((round(v, 3), n) for n, v in between.items() if v > 0), reverse=True)
    return {"components": len(comps), "main": sorted(main),
            "islands": [c for c in comps[1:]], "spof": spof,
            "bridges": sorted(bridges, key=lambda b: (b["a"], b["b"])),
            "critical": [{"device": n, "betweenness": v} for v, n in ranked[:CRITICAL_TOP]]}


def network_graph(hosts: list, roles: dict, intents: dict, results: dict, up: dict) -> dict:
    """One network's graph, every layer and its analysis. *hosts* is the inventory (the
    population: a managed device the graph lacks is still a node, drawn apart with why)."""
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
    for layer in ("ospf", "ospfv3", "bgp"):
        for l in layers[layer]:
            if l.get("external") and l["external"] not in nodes:
                nodes[l["external"]] = {"managed": False, "role": "", "polled": False,
                                        "answering": False, "lldp_read": False,
                                        "external": True}
    analysis = {}
    for layer, links in layers.items():
        # A routing layer's population is the devices taking part in it (C648): a switch that
        # runs no OSPF is not an island of the OSPF layer.
        names = sorted(nodes) if layer == "physical" else \
            sorted({e for l in links for e in (l["a"], l["b"])})
        a = analyse(names, links)
        a["island_why"] = {}
        for island in a["islands"]:
            for d in island:
                a["island_why"][d] = _why_apart(d, nodes.get(d) or {}, layer, len(island) == 1)
        analysis[layer] = a
    return {"nodes": nodes, "layers": layers, "analysis": analysis}


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

def read(source=None, population=None, clock=time.time) -> dict:
    from modules import integration_groups as IG
    from modules.neighbours import committed_intents
    from modules.readers.adjacencies import lists

    configured, results, up = (source or (lambda: IG.merged("prometheus",
                                                            prometheus_series)))()
    if not configured:
        return {"configured": False, "networks": {}, "errors": []}
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
        networks[list_name] = network_graph(hosts, roles, intents, results, up)
    return {"configured": True, "networks": networks, "errors": errors,
            "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock()))}


READER = reader_job.register(reader_job.Reader(
    name="topology-graph",
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
