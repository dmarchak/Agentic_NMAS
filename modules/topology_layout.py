"""modules/topology_layout.py — where each device sits on the Topology map (P.11; boards
TopoDesktop and TopoPhone, signed off 2026-10-04, redrawn for C661 on 2026-10-11).

**No bands** (the operator, 2026-10-11: "Remove the Access, Edge, Core and Management sections").
Where nobody has placed a device, it sits where a spring layout of the cabling puts it: every
device pushes every other away, every link pulls its two ends together (Fruchterman and
Reingold, the algorithm behind NetworkX's ``spring_layout``), from a fixed seed, so the same
graph lays out the same map and a refresh moves nothing. Written here in plain Python because
NetworkX's own needs NumPy, a package (and licence) this project does not carry.

**People's places override it** (C661): a network's shared layout (`topology_positions`) pins
every device it holds; a device it does not hold (one added since) starts at the middle of its
placed neighbours and settles among them, the placed ones never moving. The reader lays out the
generated map once per read; a page with a saved layout draws its places, and lays out only a
device the layout lacks (at most the 150 a map draws).
"""

import logging
import math
import random

log = logging.getLogger(__name__)

#: The map's coordinate space: 880 wide fits the board's map box at 1440 at about its own size,
#: so a label drawn at 11 is read at about 11. A layout may be wider or taller (pan and zoom).
W, TOP, SIDE, HALF = 880, 64, 60, 17
#: The seed: one fixed number, so a graph always lays out the same way.
SEED = 11
#: The distance a link settles at, in map units: a device's icon, its name and a two-word chip
#: between two devices fit in it (the template: a 34 icon, chips about 90 wide).
SPACING = 170
#: No two devices closer than this, centre to centre: a name (12.5 px mono) under each icon.
MIN_GAP = 110
#: The spring layout's rounds (the cooling schedule): 150 settles the lab's 11 devices and a
#: random 150-device graph alike (measured 2026-10-11: the last 30 rounds move no device more
#: than 2 units).
ROUNDS = 150


def node_class(name: str, n: dict) -> str:
    from modules.readers.topology_graph import MANAGER
    role = (n.get("role") or "").lower()
    if name == MANAGER:
        return "server"
    # A switch a controller programs (S14), keyed by DPID: its own symbol, whether a controller
    # reports it or only a device's LLDP names it; a host a controller learned.
    if n.get("sdn"):
        return "sdn"
    if n.get("host"):
        return "host"
    if n.get("outside"):
        return "external"
    if role in ("router", "edge-router", "core-router"):
        return "router"
    if "switch" in role:
        return "l3switch" if n.get("l3") else "switch"
    # The board's other classes (TopoDesktop's legend), each from its role's own word: a role
    # that does not name one stays "class unknown", never a guess.
    if "firewall" in role:
        return "firewall"
    if "access-point" in role or "access point" in role:
        return "accesspoint"
    if "controller" in role:
        return "controller"
    if "server" in role:
        return "server"
    return "unknown"


def _edges(nodes: dict, phys: list) -> list:
    """The cabling as pairs of drawn devices, each pair once, in a fixed order."""
    return sorted({tuple(sorted((l["a"], l["b"]))) for l in phys
                   if l["a"] in nodes and l["b"] in nodes and l["a"] != l["b"]})


#: Fruchterman and Reingold's grid variant (C670): two devices repel only within this many
#: spacings, found through a grid of cells that size, so a round costs about the devices
#: times their near neighbours, never every pair. Measured 2026-10-11 against every pair: the
#: lab's layout keeps its shape, and 900 devices fall from 32.8 s (see C670's row).
REPEL_WITHIN = 2.0


def _near_pairs(pos: dict, names: list, radius: float):
    """Every pair of *names* closer than *radius*, each once, in a fixed order: a grid of cells
    *radius* wide, each device checked against its own cell and the eight around it."""
    cells = {}
    for n in names:
        x, y = pos[n]
        cells.setdefault((math.floor(x / radius), math.floor(y / radius)), []).append(n)
    order = {n: i for i, n in enumerate(names)}
    r2 = radius * radius
    for (cx, cy), members in sorted(cells.items()):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                others = cells.get((cx + dx, cy + dy))
                if not others:
                    continue
                for a in members:
                    for b in others:
                        if order[a] < order[b]:
                            ex, ey = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
                            if ex * ex + ey * ey < r2:
                                yield a, b


def spring(names: list, edges: list, start: dict, fixed=frozenset(), rounds: int = ROUNDS,
           k: float = SPACING) -> dict:
    """Fruchterman and Reingold's spring layout, their grid variant: each round every pair of
    devices within ``REPEL_WITHIN`` spacings repels by k²/d, each link attracts its ends by
    d²/k, and each free device moves along its sum, no further than the round's temperature,
    which cools linearly to nothing. *fixed* never move. Deterministic for a given *start*."""
    pos = {n: list(start[n]) for n in names}
    free = [n for n in names if n not in fixed]
    if not free:
        return {n: tuple(p) for n, p in pos.items()}
    span = max(k * math.sqrt(len(names)), k)
    for r in range(rounds):
        temp = span * 0.1 * (1 - r / rounds)
        disp = {n: [0.0, 0.0] for n in free}
        for a, b in _near_pairs(pos, names, k * REPEL_WITHIN):
            dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
            d = math.hypot(dx, dy) or 0.01
            f = k * k / d
            if a in disp:
                disp[a][0] += dx / d * f
                disp[a][1] += dy / d * f
            if b in disp:
                disp[b][0] -= dx / d * f
                disp[b][1] -= dy / d * f
        for a, b in edges:
            dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
            d = math.hypot(dx, dy) or 0.01
            f = d * d / k
            if a in disp:
                disp[a][0] -= dx / d * f
                disp[a][1] -= dy / d * f
            if b in disp:
                disp[b][0] += dx / d * f
                disp[b][1] += dy / d * f
        for n in free:
            dx, dy = disp[n]
            d = math.hypot(dx, dy)
            if d:
                step = min(d, temp)
                pos[n][0] += dx / d * step
                pos[n][1] += dy / d * step
    return {n: tuple(p) for n, p in pos.items()}


def _apart(pos: dict, fixed=frozenset(), gap: float = MIN_GAP, passes: int = 30) -> dict:
    """No two devices closer than *gap*: a free one too close is pushed straight away (both
    halves when neither is fixed), a few passes."""
    pos = {n: list(p) for n, p in pos.items()}
    names = sorted(pos)
    for _ in range(passes):
        moved = False
        for a, b in list(_near_pairs(pos, names, gap)):
            dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
            d = math.hypot(dx, dy)
            if d >= gap:
                continue
            if not d:
                dx, dy, d = 1.0, 0.0, 1.0
            push = gap - d
            share = [n for n in (a, b) if n not in fixed]
            if not share:
                continue
            for n in share:
                sign = -1 if n == a else 1
                pos[n][0] += sign * dx / d * push / len(share)
                pos[n][1] += sign * dy / d * push / len(share)
            moved = True
        if not moved:
            break
    return {n: tuple(p) for n, p in pos.items()}


def _components(names: list, edges: list) -> list:
    """The connected parts, each a sorted list, the largest first (ties by first name)."""
    near = {n: set() for n in names}
    for a, b in edges:
        near[a].add(b)
        near[b].add(a)
    seen, out = set(), []
    for n in names:
        if n in seen:
            continue
        part, todo = [], [n]
        seen.add(n)
        while todo:
            x = todo.pop()
            part.append(x)
            for y in sorted(near[x]):
                if y not in seen:
                    seen.add(y)
                    todo.append(y)
        out.append(sorted(part))
    return sorted(out, key=lambda p: (-len(p), p[0]))


def _part(names: list, edges: list, rng) -> tuple:
    """One connected part laid out from (0, 0): ``(positions, width, height)``. A seeded start
    on a circle, the springs, then turned so its long side runs across (screens are wider than
    tall)."""
    mine = [e for e in edges if e[0] in names]
    if len(names) == 1:
        return {names[0]: (0.0, 0.0)}, 0.0, 0.0
    r = SPACING * math.sqrt(len(names)) / 2
    start = {n: (r * math.cos(2 * math.pi * i / len(names)) + rng.uniform(-1, 1),
                 r * math.sin(2 * math.pi * i / len(names)) + rng.uniform(-1, 1))
             for i, n in enumerate(names)}
    pos = _apart(spring(names, mine, start))
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    if max(ys) - min(ys) > max(xs) - min(xs):
        pos = {n: (y, x) for n, (x, y) in pos.items()}
        xs, ys = ys, xs
    return ({n: (x - min(xs), y - min(ys)) for n, (x, y) in pos.items()},
            max(xs) - min(xs), max(ys) - min(ys))


def layout(nodes: dict, phys: list, placed: dict = None) -> dict:
    """``{"positions": {name: (x, y)}, "width", "height", "placed"}``: every device in *nodes*.
    A device *placed* holds keeps its place; the rest by the spring layout (see the module).
    The map's frame is the places' extent plus a margin, at least ``W`` wide."""
    names = sorted(nodes)
    edges = _edges(nodes, phys)
    placed = {n: (float(p[0]), float(p[1])) for n, p in (placed or {}).items() if n in nodes}
    rng = random.Random(SEED)
    if not placed:
        # The generated map: each connected part laid out on its own (springs alone would push
        # an island, which nothing pulls back, off to the edge of the world), then the parts
        # packed in rows, the largest first, so an island sits beside the network.
        pos, x_off, y_off, row_h = {}, SIDE, TOP, 0.0
        parts = [_part(c, edges, rng) for c in _components(names, edges)]
        row_w = max([W - 2 * SIDE] + [w for _, w, _ in parts]) + 2 * SPACING
        for part, w, h in parts:
            if x_off > SIDE and x_off + w > SIDE + row_w:
                x_off, y_off, row_h = SIDE, y_off + row_h + SPACING, 0.0
            pos.update({n: (x + x_off, y + y_off) for n, (x, y) in part.items()})
            x_off += w + SPACING
            row_h = max(row_h, h)
    else:
        # A device the shared layout does not hold starts at the middle of its placed neighbours
        # (else of every placed device), a little out from it, and settles; placed ones stay.
        cx = sum(p[0] for p in placed.values()) / len(placed)
        cy = sum(p[1] for p in placed.values()) / len(placed)
        start = dict(placed)
        near = {}
        for a, b in edges:
            near.setdefault(a, []).append(b)
            near.setdefault(b, []).append(a)
        for i, n in enumerate(x for x in names if x not in placed):
            by = [placed[o] for o in near.get(n, ()) if o in placed]
            mx, my = ((sum(p[0] for p in by) / len(by), sum(p[1] for p in by) / len(by))
                      if by else (cx, cy))
            angle = rng.uniform(0, 2 * math.pi)
            start[n] = (mx + math.cos(angle) * SPACING * 0.6, my + math.sin(angle) * SPACING * 0.6)
        fixed = frozenset(placed)
        pos = _apart(spring(names, edges, start, fixed, rounds=60), fixed)
        # Kept on the frame: a settled device that drifted above or left of it is brought in.
        pos = {n: (p if n in fixed else (max(p[0], SIDE / 2), max(p[1], TOP / 2)))
               for n, p in pos.items()}
    positions = {n: (round(x), round(y)) for n, (x, y) in pos.items()}
    width = max([W] + [x + SIDE + 40 for x, _ in positions.values()])
    height = max([480] + [y + 90 for _, y in positions.values()])
    return {"positions": positions, "width": round(width), "height": round(height),
            "placed": sorted(placed)}
