"""modules/topology_page.py — the Topology page's view, from the topology reader's STORED value
(P.11 step 2; NSOT_TOPOLOGY_BRIEF sections 2 to 7, boards A to C signed off 2026-10-04).

Nothing here reads a device or Prometheus: the reader (`readers/topology_graph.py`) did, and this
draws what it stored, with its time. A path trace is a search over that stored graph, computed
when a person asks for it (two devices, one layer): never per device, never a read.

**The map is drawn on the server, as SVG** (the brief's drawing spike, decided under the Phase 7
mode: no new library, strict CSP, nothing to vendor). Positions are deterministic for this step:
bands by role, top to bottom, outside peers above the fleet, islands in a band of their own with
why; a refresh moves nothing. Saved, shared positions a person moves are step 3.

**Down is never colour alone** (Q7): a down link is dashed with an "x" at its middle; a link one
end reports is dotted; a ghost (an adjacency intent implies and nothing reports) is a faint
dashed line. A node not answering is crossed. The legend is always drawn.
"""

import logging

log = logging.getLogger(__name__)

LAYERS = ("physical", "ospf", "ospfv3", "bgp")
LAYER_WORDS = {"physical": "Physical (LLDP)", "ospf": "OSPF", "ospfv3": "OSPFv3", "bgp": "BGP"}
#: Above this many fleet devices a band collapses to one summary node (the brief, Q12).
COLLAPSE_ABOVE = 150
WIDTH, BAND, MARGIN, R = 960, 120, 70, 16
#: Role bands, top to bottom; any other role sits under them, a device with none last.
ROLE_ORDER = ("router", "firewall", "switch")


def stored() -> dict:
    """The reader's last good value and its state: ``{"state", "value", "value_at", "failed"}``
    with state ``never`` (no read stored), ``unreadable`` or ``ok``."""
    from modules import reader_job

    got = reader_job.read_cached("topology-graph")
    if got.get("state") == "unreadable":
        return {"state": "unreadable", "value": {}, "value_at": "",
                "failed": got.get("why") or "the reader's store could not be read"}
    doc = got.get("doc") or {}
    last = doc.get("last_good") or {}
    attempt = doc.get("last_attempt") or {}
    failed = "" if attempt.get("ok", True) else (attempt.get("error") or "the last read failed")
    if not last:
        return {"state": "never", "value": {}, "value_at": "", "failed": failed}
    return {"state": "ok", "value": last.get("value") or {}, "value_at": last.get("value_at", ""),
            "failed": failed}


def _band(node: dict) -> tuple:
    role = (node.get("role") or "").lower()
    if node.get("outside"):
        return (0, "outside management")
    if role in ROLE_ORDER:
        return (1 + ROLE_ORDER.index(role), role + "s")
    return (1 + len(ROLE_ORDER), role + "s" if role else "no role")


def layout(nodes: dict, islands: set) -> dict:
    """``{"positions": {name: (x, y)}, "bands": [(y, words)], "height"}``: bands by role, the
    islands in their own band at the bottom. Deterministic: sorted names in each band."""
    bands = {}
    for name, n in nodes.items():
        key = (99, "apart from the rest") if name in islands else _band(n)
        bands.setdefault(key, []).append(name)
    positions, labels, y = {}, [], MARGIN
    for key in sorted(bands):
        names = sorted(bands[key])
        step = (WIDTH - 2 * MARGIN) / max(len(names), 1)
        for i, name in enumerate(names):
            positions[name] = (round(MARGIN + step * (i + 0.5)), y)
        labels.append((y, key[1]))
        y += BAND
    return {"positions": positions, "bands": labels, "height": y - BAND + MARGIN + 30}


def _layer_graph(links: list):
    import networkx as nx
    g = nx.MultiGraph()
    for l in links:
        if l.get("state") in ("up", "unknown"):
            g.add_edge(l["a"], l["b"])
    return g


def path_trace(links: list, a: str, b: str) -> dict:
    """Every equal-cost shortest path from *a* to *b* in the layer's graph, by hop count: a claim
    about the GRAPH, never about forwarding (the brief, Q8)."""
    import networkx as nx

    g = _layer_graph(links)
    if a not in g or b not in g:
        missing = [d for d in (a, b) if d not in g]
        return {"ok": False, "why": f"{', '.join(missing)} has no link carrying traffic in this "
                                    "layer, so no path is drawn"}
    try:
        paths = sorted(nx.all_shortest_paths(g, a, b))
    except nx.NetworkXNoPath:
        return {"ok": False, "why": f"no path joins {a} and {b} in this layer: they are in "
                                    "different islands"}
    edges = {tuple(sorted(p[i:i + 2])) for p in paths for i in range(len(p) - 1)}
    return {"ok": True, "paths": paths, "hops": len(paths[0]) - 1, "edges": sorted(edges),
            "nodes": sorted({n for p in paths for n in p})}


def _ports(phys: list, a: str, b: str) -> str:
    for l in phys:
        if {l["a"], l["b"]} == {a, b}:
            ends = {l["a"]: l["port_a"], l["b"]: l["port_b"]}
            return f"{a} {ends[a] or '?'} to {b} {ends[b] or '?'}"
    return f"{a} to {b}"


def view(list_name: str, layer: str = "physical", a: str = "", b: str = "", q: str = "") -> dict:
    """Everything the page draws for one network and layer."""
    layer = layer if layer in LAYERS else "physical"
    st = stored()
    out = {"list": list_name, "layer": layer, "layers": LAYER_WORDS, "state": st["state"],
           "value_at": st["value_at"], "failed": st["failed"], "a": a, "b": b, "q": q}
    if st["state"] != "ok":
        return out
    value = st["value"]
    if not value.get("configured"):
        out["state"] = "not_configured"
        return out
    net = (value.get("networks") or {}).get(list_name)
    if net is None:
        out["state"] = "not_read"
        return out
    nodes, layers, analysis = net["nodes"], net["layers"], net["analysis"]
    an = analysis.get(layer) or {}
    phys = layers.get("physical") or []
    shown = set(nodes) if layer == "physical" else \
        {e for l in layers.get(layer) or [] for e in (l["a"], l["b"])} | {
            n for n, v in nodes.items() if v.get("managed")}
    fleet = sorted(n for n in shown if (nodes.get(n) or {}).get("managed"))
    islands = {d for i in an.get("islands") or [] for d in i}
    out.update(state="ok", errors=value.get("errors") or [])
    out["collapsed"] = len(fleet) > COLLAPSE_ABOVE
    out["summary"] = _summary(nodes, layers, an, layer)
    out["islands"] = [{"device": d, "why": (an.get("island_why") or {}).get(d, ""),
                       **((an.get("island_state") or {}).get(d) or {})}
                      for d in sorted(islands)]
    out["spof"] = an.get("spof") or []
    out["bridges"] = an.get("bridges") or []
    out["critical"] = an.get("critical") or []
    out["list_groups"] = _list_groups(nodes, phys, layers.get(layer) or [], layer, shown)
    if a and b:
        trace = path_trace(layers.get(layer) or [], a, b)
        if trace.get("ok"):
            trace["hop_words"] = [[_ports(phys, p[i], p[i + 1]) for i in range(len(p) - 1)]
                                  for p in trace["paths"]]
        out["trace"] = trace
    out["matches"] = _search(nodes, phys, q) if q else []
    if out["collapsed"]:
        return out
    geo = layout({n: nodes[n] for n in shown}, islands)
    out["svg"] = _svg(geo, nodes, shown, phys, layers.get(layer) or [], layer, an, islands,
                      out.get("trace"), set(out["matches"]))
    return out


def _summary(nodes: dict, layers: dict, an: dict, layer: str) -> dict:
    links = layers.get(layer) or []
    states = {}
    for l in links:
        key = l.get("kind", "") if layer == "physical" and l.get("state") == "up" else \
            l.get("state", "")
        states[key] = states.get(key, 0) + 1
    return {"devices": sum(1 for v in nodes.values() if v.get("managed")),
            "outside": sum(1 for v in nodes.values() if v.get("outside")),
            "links": len(links), "states": states,
            "islands_warned": sum(1 for s in (an.get("island_state") or {}).values()
                                  if s.get("warn")),
            "islands_expected": sum(1 for s in (an.get("island_state") or {}).values()
                                    if s.get("expected")),
            "spof": len(an.get("spof") or []), "bridges": len(an.get("bridges") or [])}


def _list_groups(nodes, phys, links, layer, shown) -> list:
    """The phone's list (the brief, section 7): devices by band, each with its links and their
    states in this layer."""
    groups = {}
    for name in sorted(shown):
        n = nodes.get(name) or {}
        mine = [l for l in (phys if layer == "physical" else links) if name in (l["a"], l["b"])]
        groups.setdefault(_band(n), []).append({
            "name": name, "managed": n.get("managed", False), "outside": n.get("outside", False),
            "links": [{"to": l["b"] if l["a"] == name else l["a"], "state": l.get("state"),
                       "kind": l.get("kind", ""),
                       "port": (l.get("port_a") if l["a"] == name else l.get("port_b")) or ""}
                      for l in mine]})
    return [{"words": key[1], "devices": devs} for key, devs in sorted(groups.items())]


def _search(nodes: dict, phys: list, q: str) -> list:
    """Names whose device name, role, or one of its ports matches *q* (the brief, Q19: search
    zooms to the item, never filters the map away)."""
    q = q.strip().lower()
    hits = set()
    for name, n in nodes.items():
        if q in name.lower() or q in (n.get("role") or "").lower():
            hits.add(name)
    for l in phys:
        if q in (l.get("port_a") or "").lower():
            hits.add(l["a"])
        if q in (l.get("port_b") or "").lower():
            hits.add(l["b"])
    return sorted(hits)


def _svg(geo, nodes, shown, phys, links, layer, an, islands, trace, matches) -> dict:
    """The map's elements, positioned: ``{"width", "height", "bands", "under", "edges",
    "nodes"}``; the template draws them and escapes every name."""
    pos = geo["positions"]
    on_path = {tuple(e) for e in (trace or {}).get("edges") or []} if (trace or {}).get("ok") \
        else set()
    spof = {s["device"] for s in an.get("spof") or []}
    bridges = {(b["a"], b["b"]) for b in an.get("bridges") or []}

    def edge(l, faint=False):
        a, b = l["a"], l["b"]
        if a not in pos or b not in pos:
            return None
        (x1, y1), (x2, y2) = pos[a], pos[b]
        state = l.get("state", "unknown")
        style = ("ghost" if state == "not_seen" else "down" if state == "down" else
                 "one" if l.get("kind") in ("one_silent", "far_not_polled") else "up")
        return {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "mx": (x1 + x2) // 2,
                "my": (y1 + y2) // 2, "style": style, "faint": faint,
                "path": tuple(sorted((a, b))) in on_path,
                "bridge": tuple(sorted((a, b))) in bridges,
                "title": _edge_title(l, layer, faint)}

    under = [e for e in (edge(l, faint=True) for l in phys) if e] if layer != "physical" else []
    edges = [e for e in (edge(l) for l in links) if e]
    drawn = []
    for name in sorted(shown):
        if name not in pos:
            continue
        n = nodes.get(name) or {}
        x, y = pos[name]
        state = (an.get("island_state") or {}).get(name) or {}
        drawn.append({"name": name, "x": x, "y": y, "managed": n.get("managed", False),
                      "outside": n.get("outside", False),
                      "answering": n.get("answering", True) or not n.get("managed"),
                      "spof": name in spof, "match": name in matches,
                      "path": name in set((trace or {}).get("nodes") or []),
                      "island": name in islands, "expected": bool(state.get("expected")),
                      "role": n.get("role") or ""})
    return {"width": WIDTH, "height": geo["height"], "bands": geo["bands"], "under": under,
            "edges": edges, "nodes": drawn, "r": R}


def _edge_title(l: dict, layer: str, faint: bool) -> str:
    if layer == "physical" or faint:
        kind = {"both": "LLDP both ends", "one_silent": f"LLDP from {', '.join(l.get('reported_by') or [])} only (the other end is polled and silent)",
                "far_not_polled": f"LLDP from {', '.join(l.get('reported_by') or [])} only (the far end is not polled)"}.get(l.get("kind"), "")
        speed = f", {l['speed']} Mb/s" if l.get("speed") else ""
        down = f", down at {', '.join(l['down_at'])}" if l.get("down_at") else ""
        return (f"{l['a']} {l.get('port_a') or '?'} to {l['b']} {l.get('port_b') or '?'}: "
                f"{l.get('state', 'unknown')}{down}{speed}; {kind}")
    words = {"up": "up", "down": "down", "not_seen": "intended by committed intent, not "
                                                     "reported"}.get(l.get("state"), l.get("state"))
    addr = f" ({l['address']})" if l.get("address") else ""
    return f"{LAYER_WORDS[layer]} {l['a']} to {l['b']}{addr}: {words} {l.get('words') or ''}"
