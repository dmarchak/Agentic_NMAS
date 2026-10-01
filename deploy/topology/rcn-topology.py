#!/usr/bin/env python3
"""
rcn-topology.py - live network topology from LLDP, rendered as SVG.

Pulls LLDP adjacencies and device reachability from Prometheus, builds a
graph, and serves it as an auto-refreshing SVG page.

    http://<nmas-host>:8088/               auto-refreshing HTML page
    http://<nmas-host>:8088/topology.svg   raw SVG
    http://<nmas-host>:8088/graph.json     node/edge data as JSON

Nodes are coloured by SNMP reachability:  green = up, red = down,
grey = discovered via a neighbour but not itself polled.

ISLANDS (2026-09-30). A polled device with no LLDP link to the rest of the
network is drawn apart, in a band of its own, with the reason in words: "no
LLDP neighbours" only when its LLDP table WAS read and held nothing; "its
LLDP table is not read" when no LLDP scrape answers for it (absent is not
empty); "not answering" when it is down. Every connected component other
than the largest is an island, so any future device in that situation is
drawn the same way.

NAMES come from the `device` label the scrape targets carry (generated from
the inventory, C232), then sysName, so no device list is kept here. The
hand-kept map this file had until 2026-09-30 lacked r6 (C256).

Versioned in the NMAS repository as deploy/topology/rcn-topology.py and
installed by the operator (docs/DEPLOY_LINUX.md); it was an unversioned copy
in /usr/local/bin until then (C256).

Run:  python3 rcn-topology.py
Deps: networkx, flask, requests
Env:  RCN_TOPOLOGY_PROM (http://localhost:9090), RCN_TOPOLOGY_JOBS
      (cisco_8000v|cisco_vios_l2), RCN_TOPOLOGY_LLDP_JOB (lldp),
      RCN_TOPOLOGY_PORT (8088)
"""

import html
import math
import os
import re
import time
from datetime import datetime, timezone

import requests
from flask import Flask, Response, jsonify

PROM = os.environ.get("RCN_TOPOLOGY_PROM", "http://localhost:9090")
DEVICE_JOBS = os.environ.get("RCN_TOPOLOGY_JOBS", "cisco_8000v|cisco_vios_l2")
LLDP_JOB = os.environ.get("RCN_TOPOLOGY_LLDP_JOB", "lldp")
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.environ.get("RCN_TOPOLOGY_PORT", "8088"))
CACHE_SECONDS = 15          # don't hammer Prometheus on every page refresh

W, H = 1100, 720            # SVG canvas
MARGIN = 90
NODE_R = 26
ISLAND_H = 190              # the islands' band, at the bottom

REASON_NO_NEIGHBOURS = ("no LLDP neighbours — not directly connected "
                        "to any other managed device")
REASON_NOT_READ = "its LLDP table is not read (no LLDP scrape answers for it)"
REASON_DOWN = "not answering SNMP, so its LLDP neighbours cannot be read"
REASON_APART = "no LLDP link to the rest of the network"

app = Flask(__name__)
_cache = {"at": 0.0, "svg": "", "data": None}


# --------------------------------------------------------------------------
# Prometheus
# --------------------------------------------------------------------------
def promq(query):
    """Run an instant query and return the result list."""
    r = requests.get(f"{PROM}/api/v1/query", params={"query": query}, timeout=10)
    r.raise_for_status()
    return r.json()["data"]["result"]


def short(name):
    """r1.example.com -> r1,  s3.rcn.lab -> s3."""
    return re.split(r"[.]", (name or "").strip())[0].lower()


def collect(query=None):
    """Return (nodes, edges, meta).

    nodes: {name: {ip, state, polled, lldp_read}}; edges: {(a, b): (port_a,
    port_b)} with a < b. *query* replaces promq (tests)."""
    query = query or promq

    up_by_ip, lldp_read, ip_to_name = {}, set(), {}
    for s in query(f'up{{job=~"{DEVICE_JOBS}|{LLDP_JOB}"}}'):
        m = s["metric"]
        ip = m.get("instance", "")
        if m.get("job") == LLDP_JOB:
            if float(s["value"][1]) == 1.0:
                lldp_read.add(ip)
            continue
        up_by_ip[ip] = float(s["value"][1]) == 1.0
        if m.get("device"):
            ip_to_name[ip] = short(m["device"])

    for s in query("sysName"):
        m = s["metric"]
        if m.get("sysName") and m.get("instance") not in ip_to_name:
            ip_to_name[m["instance"]] = short(m["sysName"])
    for ip in up_by_ip:
        ip_to_name.setdefault(ip, "dev-" + ip.split(".")[-1])

    remport = {}
    for s in query("lldpRemPortId"):
        m = s["metric"]
        key = (m.get("instance"), m.get("lldpLocPortNum"), m.get("lldpRemIndex"))
        remport[key] = m.get("lldpRemPortId", "")

    edges = {}
    for s in query("lldpRemEntry"):
        m = s["metric"]
        ip = m.get("instance")
        local = ip_to_name.get(ip, short(ip))
        remote = short(m.get("lldpRemEntry", ""))
        if not remote or local == remote:
            continue
        lport = m.get("lldpLocPortDesc", "?")
        rport = remport.get((ip, m.get("lldpLocPortNum"), m.get("lldpRemIndex")), "?")
        key = tuple(sorted((local, remote)))
        if key not in edges:
            edges[key] = (lport, rport) if key[0] == local else (rport, lport)

    nodes = {}
    for ip, name in ip_to_name.items():
        if ip not in up_by_ip:
            continue
        nodes[name] = {"ip": ip, "state": "up" if up_by_ip[ip] else "down",
                       "polled": True, "lldp_read": ip in lldp_read}
    for a, b in edges:
        for n in (a, b):
            # discovered through a neighbour but not polled by us
            nodes.setdefault(n, {"ip": "", "state": "unknown", "polled": False,
                                 "lldp_read": False})

    islands = mark_islands(nodes, edges)
    meta = {
        "nodes": len(nodes),
        "edges": len(edges),
        "down": sum(1 for d in nodes.values() if d["state"] == "down"),
        "islands": len(islands),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    return nodes, edges, meta


def components(nodes, edges):
    """Connected components, largest first (ties by their first name)."""
    parent = {n: n for n in nodes}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for a, b in edges:
        parent[find(a)] = find(b)
    groups = {}
    for n in nodes:
        groups.setdefault(find(n), []).append(n)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: (-len(g), g[0]))


def island_reason(name, d, alone):
    if not alone:
        return REASON_APART
    if d["state"] == "down":
        return REASON_DOWN
    if not d["lldp_read"]:
        return REASON_NOT_READ
    return REASON_NO_NEIGHBOURS


def mark_islands(nodes, edges):
    """Every component but the largest is an island; each node in one carries
    `island` and its `island_reason`. Returns the islands."""
    comps = components(nodes, edges)
    for n in nodes:
        nodes[n]["island"] = False
        nodes[n]["island_reason"] = ""
    for comp in comps[1:]:
        for n in comp:
            nodes[n]["island"] = True
            nodes[n]["island_reason"] = island_reason(n, nodes[n], len(comp) == 1)
    return comps[1:]


# --------------------------------------------------------------------------
# Layout and rendering
# --------------------------------------------------------------------------
def _layout_main(names, edges):
    """Kamada-Kawai gives stable, readable layouts for small graphs."""
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(names)
    g.add_edges_from(e for e in edges if e[0] in names and e[1] in names)
    try:
        return nx.kamada_kawai_layout(g)
    except Exception:
        return nx.spring_layout(g, seed=42, k=1.2)


def _fit(pos, x0, y0, x1, y1):
    if not pos:
        return {}
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    spanx = (max(xs) - min(xs)) or 1.0
    spany = (max(ys) - min(ys)) or 1.0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    out = {}
    for n, (x, y) in pos.items():
        sx = cx if len(pos) == 1 else x0 + (x - min(xs)) / spanx * (x1 - x0)
        sy = cy if len(pos) == 1 else y0 + (y - min(ys)) / spany * (y1 - y0)
        out[n] = (sx, sy)
    return out


def layout(nodes, edges):
    """{name: (x, y)}: the largest component above, each island in its own
    slot of the band below."""
    comps = components(nodes, edges)
    if not comps:
        return {}
    islands = comps[1:]
    bottom = H - ISLAND_H if islands else H
    pos = _fit(_layout_main(comps[0], edges), MARGIN, MARGIN, W - MARGIN, bottom - MARGIN / 2)
    if islands:
        slot = (W - 2 * MARGIN) / len(islands)
        for i, comp in enumerate(islands):
            x0 = MARGIN + i * slot
            if len(comp) == 1:
                pos[comp[0]] = (x0 + slot / 2, H - ISLAND_H + 70)
            else:
                ring = {n: (math.cos(2 * math.pi * k / len(comp)),
                            math.sin(2 * math.pi * k / len(comp))) for k, n in enumerate(comp)}
                pos.update(_fit(ring, x0 + 40, H - ISLAND_H + 45, x0 + slot - 40, H - 60))
    return pos


COLOURS = {
    "up":      ("#2d8a4e", "#3fc46b"),
    "down":    ("#a32020", "#f04444"),
    "unknown": ("#4a4a52", "#8a8a94"),
}


def _wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + ([cur] if cur else [])


def render(nodes, edges, meta, pos=None):
    pos = pos if pos is not None else layout(nodes, edges)
    e = html.escape
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" font-family="DejaVu Sans, Verdana, sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#111217"/>',
    ]

    islands = [n for n, d in nodes.items() if d.get("island")]
    if islands:
        top = H - ISLAND_H
        out.append(f'<line x1="{MARGIN / 2}" y1="{top}" x2="{W - MARGIN / 2}" y2="{top}" '
                   f'stroke="#3d4450" stroke-width="1" stroke-dasharray="4 4"/>')
        out.append(f'<text x="{MARGIN / 2}" y="{top + 18}" fill="#8a8f99" font-size="11">'
                   f'Islands: not connected to the rest of the network by LLDP</text>')

    for (a, b), (pa, pb) in edges.items():
        if a not in pos or b not in pos:
            continue
        x1, y1 = pos[a]
        x2, y2 = pos[b]
        down = nodes[a]["state"] == "down" or nodes[b]["state"] == "down"
        colour = "#f04444" if down else "#3d4450"
        dash = ' stroke-dasharray="6 4"' if down else ""
        out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                   f'y2="{y2:.1f}" stroke="{colour}" stroke-width="2"{dash}/>')
        dx, dy = x2 - x1, y2 - y1
        ln = math.hypot(dx, dy) or 1.0
        ux, uy = dx / ln, dy / ln
        for (px, py, txt) in (
            (x1 + ux * (NODE_R + 30), y1 + uy * (NODE_R + 30), pa),
            (x2 - ux * (NODE_R + 30), y2 - uy * (NODE_R + 30), pb),
        ):
            if txt and txt != "?":
                out.append(f'<text x="{px:.1f}" y="{py:.1f}" fill="#6f7681" '
                           f'font-size="9" text-anchor="middle">{e(txt)}</text>')

    for n, d in nodes.items():
        if n not in pos:
            continue
        x, y = pos[n]
        dark, light = COLOURS.get(d["state"], COLOURS["unknown"])
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{NODE_R}" '
                   f'fill="{dark}" stroke="{light}" stroke-width="2.5"/>')
        out.append(f'<text x="{x:.1f}" y="{y + 5:.1f}" fill="#ffffff" '
                   f'font-size="14" font-weight="bold" text-anchor="middle">{e(n)}</text>')
        below = y + NODE_R + 15
        if d.get("ip"):
            out.append(f'<text x="{x:.1f}" y="{below:.1f}" fill="#8a8f99" '
                       f'font-size="9.5" text-anchor="middle">{e(d["ip"])}</text>')
            below += 13
        if d.get("island") and d.get("island_reason") != REASON_APART:
            for line in _wrap(d["island_reason"], 34):
                out.append(f'<text x="{x:.1f}" y="{below:.1f}" fill="#c9a14a" '
                           f'font-size="9.5" text-anchor="middle">{e(line)}</text>')
                below += 12

    lx, ly = 20, 26
    for label, key in (("up", "up"), ("down", "down"), ("not polled", "unknown")):
        dark, lightc = COLOURS[key]
        out.append(f'<circle cx="{lx + 8}" cy="{ly - 4}" r="7" fill="{dark}" '
                   f'stroke="{lightc}" stroke-width="2"/>')
        out.append(f'<text x="{lx + 22}" y="{ly}" fill="#8a8f99" '
                   f'font-size="11">{label}</text>')
        lx += 22 + 9 * len(label) + 18

    island_note = f' &#183; {meta["islands"]} island(s)' if meta.get("islands") else ""
    out.append(f'<text x="{W - 16}" y="{H - 14}" fill="#5c626c" font-size="11" '
               f'text-anchor="end">{meta["nodes"]} nodes, {meta["edges"]} links'
               f'{island_note} &#183; discovered via LLDP &#183; {e(meta["generated"])}</text>')
    out.append("</svg>")
    return "\n".join(out)


def build(force=False):
    now = time.time()
    if not force and _cache["svg"] and now - _cache["at"] < CACHE_SECONDS:
        return _cache["svg"], _cache["data"]
    nodes, edges, meta = collect()
    svg = render(nodes, edges, meta)
    data = {
        "meta": meta,
        "nodes": [{"id": n, **d} for n, d in nodes.items()],
        "edges": [{"source": a, "target": b, "port_a": pa, "port_b": pb}
                  for (a, b), (pa, pb) in edges.items()],
    }
    _cache.update(at=now, svg=svg, data=data)
    return svg, data


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>RCN Lab topology</title>
<meta http-equiv="refresh" content="30">
<style>
  body {{ background:#111217; margin:0; display:flex; align-items:center;
         justify-content:center; height:100vh;
         font-family:DejaVu Sans,Verdana,sans-serif; }}
  img  {{ width:100vw; height:100vh; object-fit:contain; }}
</style></head>
<body><img src="/topology.svg?t={t}" alt="network topology"></body></html>
"""


@app.route("/")
def index():
    return Response(PAGE.format(t=int(time.time())), mimetype="text/html")


@app.route("/topology.svg")
def svg():
    s, _ = build()
    return Response(s, mimetype="image/svg+xml",
                    headers={"Cache-Control": "no-store"})


@app.route("/graph.json")
def graph_json():
    _, d = build()
    return jsonify(d)


@app.route("/healthz")
def healthz():
    try:
        build(force=True)
        return "ok", 200
    except Exception as exc:
        return f"error: {exc}", 500


if __name__ == "__main__":
    app.run(host=LISTEN_HOST, port=LISTEN_PORT, threaded=True)
