"""modules/topology_layout.py — where each device sits on the Topology map (P.11 step 2; boards
TopoDesktop and TopoPhone, signed off 2026-10-04).

Laid out ONCE per read, by the topology reader, and stored with the graph: a page draws stored
positions and never lays out per request (CLAUDE.md, enterprise scale). Deterministic: the same
graph lays out the same map, so a refresh moves nothing. Saved positions a person moves
(Arrange) are step 3.

Bands by class, top to bottom (the board's CORE, EDGE, ACCESS, MANAGEMENT); each band ordered by
where its neighbours sit, then, on a small map, untangled: neighbours in a band swapped (every
order of a small band tried) while it lowers crossings and links drawn through a device they do
not join.
"""

import itertools
import logging
import math

log = logging.getLogger(__name__)

#: The map's coordinate space: 880 wide fits the board's map box at 1440 at about its own size,
#: so a label drawn at 11 is read at about 11.
W, BAND, TOP, SIDE, HALF = 880, 175, 64, 60, 17
#: Bands, top to bottom (the board): routers inside, routers with an outside peer and the peers
#: themselves, switches, a device of no known class, Mercury's own host.
BANDS = ("core", "edge", "access", "no class", "management")


def node_class(name: str, n: dict) -> str:
    from modules.readers.topology_graph import MANAGER
    role = (n.get("role") or "").lower()
    if name == MANAGER:
        return "server"
    if n.get("outside"):
        return "external"
    if role in ("router", "edge-router", "core-router"):
        return "router"
    if "switch" in role:
        return "l3switch" if n.get("l3") else "switch"
    return "unknown"


def _band(name: str, n: dict, edge: set) -> str:
    cls = node_class(name, n)
    if cls == "server":
        return "management"
    if cls == "external" or name in edge:
        return "edge"
    if cls == "router":
        return "core"
    if cls in ("switch", "l3switch"):
        return "access"
    return "no class"


def layout(nodes: dict, phys: list) -> dict:
    """``{"positions": {name: (x, y)}, "bands": [(y, words)], "height"}``: bands by class, top
    to bottom; each band ordered by where its neighbours sit (a barycentre sweep, four passes,
    ties by name), then spaced evenly. Deterministic: the same graph draws the same map."""
    outside = {n for n, v in nodes.items() if v.get("outside")}
    edge = {l["a"] if l["b"] in outside else l["b"] for l in phys
            if (l["a"] in outside) != (l["b"] in outside)}
    rows = {}
    for name, n in nodes.items():
        rows.setdefault(_band(name, n, edge), []).append(name)
    order = [b for b in BANDS if b in rows]
    near = {}
    for l in phys:
        near.setdefault(l["a"], set()).add(l["b"])
        near.setdefault(l["b"], set()).add(l["a"])
    x = {}

    def spread(band):
        names = rows[band]
        step = (W - 2 * SIDE) / max(len(names), 1)
        for i, name in enumerate(names):
            x[name] = SIDE + step * (i + 0.5)

    for band in order:
        rows[band] = sorted(rows[band])
        spread(band)
    for sweep in range(4):
        for band in (order if sweep % 2 == 0 else list(reversed(order))):
            def centre(name, band=band):
                others = [x[o] for o in near.get(name, ()) if o in x and o not in rows[band]]
                return (sum(others) / len(others) if others else x[name], name)
            rows[band] = sorted(rows[band], key=centre)
            spread(band)
    ys = {band: TOP + BAND * i for i, band in enumerate(order)}

    def place():
        # An outside peer sits above its band (the board's r5), so the band's own links do not
        # run through it.
        return {name: (x[name], ys[band] - (BAND * 0.45 if name in outside else 0))
                for band in order for name in rows[band]}

    if len(nodes) <= UNTANGLE_UP_TO:
        # Swap neighbours in a band while it lowers the cost: two links crossing count 1, a
        # link drawn through a device that is not its end counts 10 (it reads as connected).


        best = _tangle(place(), phys)
        moved = True
        while moved:
            moved = False
            for band in order:
                if len(rows[band]) <= PERMUTE_UP_TO:
                    # A small band: every order of it, the rest held (adjacent swaps alone stop
                    # in a local minimum).
                    for perm in itertools.permutations(sorted(rows[band])):
                        was = rows[band]
                        rows[band] = list(perm)
                        spread(band)
                        cost = _tangle(place(), phys)
                        if cost < best:
                            best, moved = cost, True
                        else:
                            rows[band] = was
                            spread(band)
                    continue
                for i in range(len(rows[band]) - 1):
                    rows[band][i], rows[band][i + 1] = rows[band][i + 1], rows[band][i]
                    spread(band)
                    cost = _tangle(place(), phys)
                    if cost < best:
                        best, moved = cost, True
                    else:
                        rows[band][i], rows[band][i + 1] = rows[band][i + 1], rows[band][i]
                        spread(band)
    positions = {name: (round(px), round(py)) for name, (px, py) in place().items()}
    labels = [(ys[band] - HALF - 26 - (BAND * 0.45 if band == "edge" and outside else 0), band)
              for band in order]
    return {"positions": positions, "bands": labels, "height": TOP + BAND * (len(order) - 1) + 80}


#: Above this many devices the layout keeps its barycentre order: the untangling pass grows
#: fast with the links. Measured on the laptop, 2026-10-10, random graphs at 1.5 links a
#: device: 30 ms at 20 devices, 141 ms at 30, 651 ms at 40, 2,480 ms at 60. The reader lays
#: out once a minute, so 40 keeps it under a second.
UNTANGLE_UP_TO = 40
#: A band this small is tried in every order (6! = 720 layouts per pass).
PERMUTE_UP_TO = 6


def _tangle(pos: dict, phys: list) -> int:
    segs = [(pos[l["a"]], pos[l["b"]], l["a"], l["b"]) for l in phys
            if l["a"] in pos and l["b"] in pos]
    cost = 0
    for i, (p1, p2, a1, b1) in enumerate(segs):
        for p3, p4, a2, b2 in segs[i + 1:]:
            if {a1, b1} & {a2, b2}:
                continue
            if _cross(p1, p2, p3, p4):
                cost += 1
        for name, q in pos.items():
            if name not in (a1, b1) and _near(q, p1, p2, 24):
                cost += 10
    return cost


def _cross(p1, p2, p3, p4) -> bool:
    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2 = side(p3, p4, p1), side(p3, p4, p2)
    d3, d4 = side(p1, p2, p3), side(p1, p2, p4)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def _near(q, p1, p2, within) -> bool:
    (x1, y1), (x2, y2) = p1, p2
    dx, dy = x2 - x1, y2 - y1
    length2 = dx * dx + dy * dy
    if not length2:
        return False
    t = ((q[0] - x1) * dx + (q[1] - y1) * dy) / length2
    if t <= 0.05 or t >= 0.95:
        return False
    return math.hypot(x1 + t * dx - q[0], y1 + t * dy - q[1]) < within
