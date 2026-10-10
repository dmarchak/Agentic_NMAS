"""modules/topology_page.py — the Topology page's view, from the topology reader's STORED value
(P.11 step 2; NSOT_TOPOLOGY_BRIEF sections 2 to 7; boards TopoDesktop and TopoPhone on the
mockups canvas, signed off 2026-10-04 in their fourth pass, NSOT_STAGE7_PLAN 15.8 and 15.9).

Nothing here reads a device or Prometheus: the reader (`readers/topology_graph.py`) did, and this
draws what it stored, with its time. A path trace and a what-if are searches over that stored
graph, computed when a person asks: never per device, never a read.

**What the boards draw, and so what this computes** (docs/fidelity/topology.md compares them
region by region):

- one physical map, every link labelled with the PORT at each end and the routing protocols'
  neighbourships it carries, each a short state chip with its key fact (OSPF's and OSPFv3's
  area, BGP's peer AS: the operator, 2026-10-10), the protocols toggled over it;
- a link's line says how it compares with intent: as intended (green, solid), not as intended
  (orange, dashed), down or an intended neighbour missing (red, thick), not read (grey, dotted);
  never colour alone;
- each device as its class's icon (our own symbols, static/img/topology/), an L3 switch badged,
  in bands (core, edge, access, management), Mercury's own host where it attaches, measured;
- a hover card per link: each end, the link's state and since, each protocol's neighbours with
  their states against intent; a click selects it (the phone's bottom sheet);
- "Needs attention on the map": every link and weak point that needs review, grouped by line
  style, filterable; the counts lead.

**The map is drawn on the server, as SVG** (the brief's drawing spike: no new library, strict
CSP, so every position is an SVG attribute, never a style). Positions are deterministic: bands
by class, each band ordered by its neighbours' places (fewer crossings); a refresh moves nothing.
Saved, shared positions a person moves (Arrange) are step 3.
"""

import logging
import math
import os
from urllib.parse import urlencode

from modules.topology_layout import BANDS, HALF, W, _band, _near, layout, node_class

log = logging.getLogger(__name__)

#: The protocols a link's states can show, in the toolbar's order: the ones Mercury reads. A
#: protocol it does not read (RIPng, configured by intent) adds no label (C654).
PROTOS = ("ospf", "ospfv3", "bgp")
PROTO_WORDS = {"ospf": "OSPF", "ospfv3": "OSPFv3", "bgp": "BGP", "ripng": "RIPng"}
#: Protocols neither read nor modelled: said beside the toggles, never a toggle that changes
#: nothing (docs/STANDING_APPROVAL_LOG.md, 2026-10-10).
NOT_READ = "RIPng, EIGRP, IS-IS"
#: The zoom steps; 100 fits the map to its box (the board's "100%" is labelled Fit).
ZOOMS = (50, 75, 100, 150, 200)
#: Above this many fleet devices the map is not drawn; the attention list still names every
#: link that needs review (the brief, Q12; the board's large-fleet inset).
COLLAPSE_ABOVE = 150
#: The short state on a chip (the board: "OSPF FULL", "BGP Estab", "BGP Idle").
SHORT = {"full": "FULL", "2-way": "2WAY", "init": "INIT", "attempt": "ATTEMPT",
         "exchange start": "EXSTART", "exchange": "EXCHANGE", "loading": "LOADING",
         "down": "DOWN", "established": "Estab", "idle": "Idle", "connect": "Connect",
         "active": "Active", "open sent": "OpenSent", "open confirm": "OpenConfirm",
         "not reported": "missing", "not measured": "?"}
#: A device's class from its role and what it runs, and the words the legend gives it.
CLASSES = {"router": "router", "switch": "L2 switch", "l3switch": "L3 switch",
           "server": "Mercury's host", "external": "outside management",
           "unknown": "class unknown", "segment": "multi-access segment"}
LINE_WORDS = {"ok": "as intended", "warn": "not as intended",
              "bad": "down, or a neighbour missing", "unread": "not read"}
GROUP_WORDS = {"bad": "Down, or an intended neighbour missing",
               "warn": "Up, not as intended", "unread": "Not read",
               "weak": "Weak points", "apart": "Apart on purpose"}


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


# ---------------------------------------------------------------------------- the question

#: Each question's key, its default (left out of a link), and what it is.
ASKS = {"p": None,          # the protocols toggled on, comma-separated; absent: all present
        "ports": "",        # "" (on at the desktop, off at phone width), "on", "off"
        "labels": "auto",   # auto (shown at Fit and closer), on, off
        "z": "100",         # zoom, one of ZOOMS
        "weak": "1",        # weak points tagged on the map
        "sel": "",          # the selected link's id
        "a": "", "b": "",   # a path from a to b
        "out": "",          # a device taken out (what-if)
        "q": "",            # find on the map
        "f": "",            # filter the attention list
        "show": "all",      # the attention list's group: all, bad, warn, unread, weak
        "tab": "att",       # the phone's tab: att, dev, map
        "arrange": ""}      # "1": arranging the map (C655)


def ask(values) -> dict:
    """The question from a request's values, each normalised to what it may be."""
    s = {}
    for k, default in ASKS.items():
        raw = values.get(k)
        s[k] = default if raw is None else raw.strip()
        if default is not None and not s[k]:
            s[k] = default
    # Absent: every protocol present; present and empty: none (every toggle off).
    s["p"] = None if s["p"] is None else [p for p in s["p"].split(",") if p in PROTOS]
    s["ports"] = s["ports"] if s["ports"] in ("on", "off") else ""
    s["labels"] = s["labels"] if s["labels"] in ("auto", "on", "off") else "auto"
    s["z"] = s["z"] if s["z"].isdigit() and int(s["z"]) in ZOOMS else "100"
    s["weak"] = "0" if s["weak"] == "0" else "1"
    s["show"] = s["show"] if s["show"] in ("all", "bad", "warn", "unread", "weak") else "all"
    s["tab"] = s["tab"] if s["tab"] in ("att", "dev", "map") else "att"
    s["arrange"] = "1" if s["arrange"] == "1" else ""
    return s


def qs(list_name: str, s: dict, over: dict = None) -> str:
    """The query string for this question with *over* changed; defaults are left out."""
    merged = dict(s, **(over or {}))
    pairs = [("list", list_name)]
    for k, default in ASKS.items():
        v = merged.get(k)
        if k == "p":
            if v is not None:
                pairs.append(("p", ",".join(v)))
            continue
        if v not in (None, "") and str(v) != str(default):
            pairs.append((k, v))
    return "?" + urlencode(pairs)


# ---------------------------------------------------------------------------- names

def label(name: str) -> str:
    """How a node is named on the page: Mercury's own host by the product's name."""
    from modules import brand
    from modules.readers.topology_graph import MANAGER
    return brand.PRODUCT_SHORT if name == MANAGER else name


# ---------------------------------------------------------------------------- links

def link_id(l: dict) -> str:
    return f"{l['a']}:{l.get('port_a') or ''}~{l['b']}:{l.get('port_b') or ''}"


def _short(words: str) -> str:
    return SHORT.get(words or "", (words or "?").upper())


def _state_short(adj: dict) -> str:
    if adj.get("state") == "not_seen":
        return "missing"
    if adj.get("state") == "unknown":
        return "?"
    return _short(adj.get("words"))


def _ends(adj: dict) -> dict:
    """Each end's own report of the adjacency, ``{device: short state}``."""
    return {d: _short(w) for d, w in sorted((adj.get("words_by") or {}).items())}


def _disagree(adj: dict) -> bool:
    """Both ends report it and say different things (C654: shown, and flagged)."""
    ends = _ends(adj)
    return len(ends) == 2 and len(set(ends.values())) == 2


def _adj_cls(adj: dict) -> str:
    if adj.get("state") in ("down", "not_seen"):
        return "bad"
    if not adj.get("intended") or _disagree(adj):
        return "warn"
    if adj.get("state") == "unknown":
        return "unread"
    return "ok"


RANK = {"bad": 3, "warn": 2, "unread": 1, "ok": 0}


def _worst(classes) -> str:
    return max(classes, key=lambda c: RANK[c], default="ok")


def _fact(layer: str, adjs: list) -> str:
    """The key fact a protocol's chip carries: OSPF's and OSPFv3's area, BGP's peer AS."""
    if layer in ("ospf", "ospfv3"):
        areas = sorted({a.get("area") for a in adjs if a.get("area")})
        return f"area {', '.join(areas)}" if areas else "area not in intent"
    peers = sorted({asn for a in adjs for dev, asn in (a.get("asn") or {}).items()
                    if dev not in (a.get("_mine") or ())})
    return f"AS {', '.join(peers)}" if peers else "AS not in intent"


def _bgp_kind(adj: dict) -> str:
    asn = set((adj.get("asn") or {}).values())
    return "eBGP" if len(asn) > 1 else "iBGP" if len(asn) == 1 else "BGP"


def _word(layer: str, adj: dict) -> str:
    return _bgp_kind(adj) if layer == "bgp" else PROTO_WORDS[layer]


def _state_words(adj: dict) -> str:
    """The adjacency's state, once: both ends' reports merged; both named only when they
    disagree (C654)."""
    if _disagree(adj):
        return " / ".join(f"{label(d)} {s}" for d, s in _ends(adj).items()) + " (ends disagree)"
    return _state_short(adj)


def _family(adj: dict) -> str:
    return {"ipv4": "IPv4", "ipv6": "IPv6"}.get(adj.get("network", ""), "")


def _adj_chips(layer: str, adjs: list) -> list:
    """One chip per adjacency (C654), the same chip once for sessions that differ only by
    address family (BGP's IPv4 and IPv6 to one peer: "eBGP AS 65002: Estab (IPv4, IPv6)")."""
    chips = {}
    for x in adjs:
        text = f"{_word(layer, x)} {_fact(layer, [x])}: {_state_words(x)}"
        c = chips.setdefault(text, {"text": text, "cls": _adj_cls(x), "families": []})
        if _family(x):
            c["families"].append(_family(x))
    out = []
    for c in chips.values():
        if len(c["families"]) > 1:
            c["text"] += f" ({', '.join(sorted(c['families']))})"
        out.append({"text": c["text"], "cls": c["cls"]})
    return out


def _neighbour_words(adj: dict, from_dev: str) -> str:
    other = adj["b"] if adj["a"] == from_dev else adj["a"]
    words = f"{label(other)} {_state_words(adj)}"
    if adj.get("state") == "not_seen":
        words += " (intended, not reported)"
    elif adj.get("state") == "unknown":
        words += " (not measured)"
    elif not adj.get("intended"):
        words += " (not in committed intent)"
    if _family(adj):
        words += f" ({_family(adj)})"
    return words


def _fault_words(layer: str, x: dict, c: str) -> str:
    why = {"bad": f"intended {'Established' if layer == 'bgp' else 'up'}",
           "warn": "the two ends disagree" if _disagree(x) else "not in committed intent",
           "unread": "not measured"}[c]
    return (f"{_word(layer, x)} {_fact(layer, [x])} {label(x['a'])} to {label(x['b'])}: "
            f"{_state_words(x)}, {why}")


def _link(l: dict, layers: dict, on: list, nodes: dict) -> dict:
    """One physical link as drawn: its class, chips (one per adjacency), hover rows and
    attention words. A protocol Mercury does not read adds no chip and no class (C654); the
    hover card says it is configured."""
    a, b = l["a"], l["b"]
    pa, pb = l.get("port_a") or "?", l.get("port_b") or "?"
    by_layer = {}
    for ref in l.get("adj") or []:
        if ref["layer"] not in on:
            continue
        adj = dict((layers.get(ref["layer"]) or [])[ref["i"]])
        adj["_at"] = ref["at"]
        adj["_mine"] = ref["at"]
        by_layer.setdefault(ref["layer"], []).append(adj)
    chips, rows, whats, classes = [], [], [], []
    if l.get("state") == "down":
        chips.append({"text": "down", "cls": "bad"})
        classes.append("bad")
        whats.append(("bad", f"link down at {', '.join(label(d) for d in l.get('down_at') or [])}",
                      l.get("since"), l.get("since_seen")))
    elif l.get("state") == "unknown":
        classes.append("unread")
        whats.append(("unread", "the link's state is not read (no ifOperStatus for its ports)",
                      "", False))
    if l.get("kind") == "one_silent":
        silent = b if l.get("reported_by") == [a] else a
        classes.append("warn")
        whats.append(("warn", f"only {label(l['reported_by'][0])} reports it: {label(silent)} "
                              "is polled and does not", l.get("since"), l.get("since_seen")))
    for layer in [p for p in PROTOS if p in by_layer]:
        adjs = by_layer[layer]
        cls = _worst(_adj_cls(x) for x in adjs)
        classes.append(cls)
        chips.extend(_adj_chips(layer, adjs))
        rows.append({"dt": f"{_word(layer, adjs[0])} {_fact(layer, adjs)}", "cls": cls,
                     "chip": "; ".join(_state_words(x) for x in adjs),
                     "lines": [f"{label(x['a'])} to {_neighbour_words(x, x['a'])}"
                               for x in adjs]})
        for x in adjs:
            c = _adj_cls(x)
            if c != "ok":
                whats.append((c, _fault_words(layer, x, c), x.get("since"), x.get("since_seen")))
    unread = sorted({p for ps in (l.get("unread") or {}).values() for p in ps})
    if unread:
        ends = " and ".join(f"{label(d)} {pa if d == a else pb}"
                            for d in sorted(l.get("unread") or {}))
        rows.append({"dt": ", ".join(unread), "cls": "unread", "chip": "not read",
                     "lines": [f"configured on {ends} by committed intent; Mercury does not "
                               "read it, so the map says nothing of it"]})
    none = [PROTO_WORDS[p] for p in on if p not in by_layer]
    cls = _worst(classes)
    if l.get("manager"):
        how = f"measured: {label(b)} {l.get('via')}'s subnet holds this host's address"
        if l.get("vlan") and l.get("port_b"):
            how += f"; {label(b)} {pb} is the one port carrying VLAN {l['vlan']} with no " \
                   "device beyond it"
    elif l.get("kind") == "both":
        how = "both ends report it"
    elif l.get("kind") == "far_not_polled":
        near = l["reported_by"][0]
        far = b if near == a else a
        how = (f"as {label(near)} sees it; {label(far)} is "
               f"{'outside management' if (nodes.get(far) or {}).get('outside') else 'not polled'}")
    elif l.get("kind") == "one_silent":
        how = f"only {label(l['reported_by'][0])} reports it"
    else:
        how = ""
    speed = f", {l['speed']} Mb/s" if l.get("speed") else ""
    readers = [d for d in (a, b) if (nodes.get(d) or {}).get("managed")]
    return {"id": link_id(l), "a": a, "b": b, "port_a": pa, "port_b": pb,
            "la": label(a), "lb": label(b), "title": f"{label(a)} {pa} ↔ {label(b)} {pb}",
            "cls": cls, "chips": chips, "state": l.get("state", "unknown"),
            "how": how + speed, "since": l.get("since", ""), "since_seen": l.get("since_seen"),
            "rows": rows, "none": none, "readers": readers,
            "whats": sorted(whats, key=lambda w: -RANK[w[0]]),
            "manager": bool(l.get("manager")), "kind": l.get("kind", "")}


def _segment(seg: dict, layers: dict, on: list, nodes: dict) -> tuple:
    """A multi-access segment as ONE node (C654): its OSPF and OSPFv3 summary once, DR and BDR
    shown neutrally, 2WAY between DROthers normal. The DR and BDR are the devices FULL with
    every other on the segment (the states say who they are; no election is guessed). A fault:
    an adjacency down or missing, a 2WAY with the DR or BDR, the two ends disagreeing, or no
    device FULL with every other. Returns ``(the segment's item, its member links)``."""
    sid = seg["id"]
    chips, rows, whats, classes, member_cls, member_lines = [], [], [], [], {}, {}
    for layer in ("ospf", "ospfv3"):
        if layer not in on or not (seg.get("adj") or {}).get(layer):
            continue
        adjs = [dict(layers[layer][i], _mine=()) for i in seg["adj"][layer]]
        devs = sorted({d for x in adjs for d in (x["a"], x["b"])})
        full = {d: {(x["b"] if x["a"] == d else x["a"]) for x in adjs
                    if d in (x["a"], x["b"]) and x.get("state") == "up"
                    and x.get("words") == "full" and not _disagree(x)} for d in devs}
        # The DR and BDR: FULL with more devices than a DROther can be (a DROther is FULL with
        # the DR and BDR alone), so one broken adjacency of the DR does not hide it (measured
        # 2026-10-10: requiring FULL with every device let a 2WAY with the DR pass as normal).
        need = min(max(len(devs) - 2, 3), len(devs) - 1)
        dr = sorted((d for d in devs if len(full[d]) >= need),
                    key=lambda d: (-len(full[d]), d))
        every = len(dr) > 2              # three or fewer devices: each FULL with every other
        dr = [] if every else dr
        word, fact = PROTO_WORDS[layer], _fact(layer, adjs)
        faults = []
        for x in adjs:
            c = _adj_cls(x)
            if c == "ok" and x.get("words") == "2-way" and ({x["a"], x["b"]} & set(dr)):
                c = "warn"
                faults.append((c, f"{word} {fact} {label(x['a'])} to {label(x['b'])}: 2WAY with "
                                  "the DR or BDR, expected FULL", x.get("since"),
                               x.get("since_seen")))
            elif c != "ok":
                faults.append((c, _fault_words(layer, x, c), x.get("since"), x.get("since_seen")))
            for d in (x["a"], x["b"]):
                member_cls[d] = _worst([member_cls.get(d, "ok"), c])
        if not dr and not every and len(devs) > 2:
            faults.append(("warn", f"{word} {fact} on {seg['name']}: no device is FULL with "
                                   "more than a DROther could be, so no DR and BDR stand out",
                           "", False))
        cls = _worst([f[0] for f in faults])
        classes.append(cls)
        if every:
            roles = "each FULL with every other"
        else:
            roles = f"DR/BDR {', '.join(label(d) for d in dr)}" if dr else "no DR/BDR"
        chips.append({"text": f"{word} {fact}: {len(devs)} devices, {roles}"
                      + (f", {len(faults)} not as expected" if faults else ""), "cls": cls})
        others = [d for d in devs if d not in dr] if not every else []
        lines = []
        if dr:
            lines.append(f"DR and BDR: {', '.join(label(d) for d in dr)} (the devices FULL with "
                         "the most others)")
        if others:
            lines.append(f"The others: {', '.join(label(d) for d in others)} (FULL with the DR "
                         "and BDR; 2WAY with each other, as OSPF intends)")
        lines += [f[1] for f in faults]
        rows.append({"dt": f"{word} {fact}", "cls": cls,
                     "chip": "as expected" if not faults else f"{len(faults)} not as expected",
                     "lines": lines})
        whats.extend(faults)
        for d in devs:
            mine = [x for x in adjs if d in (x["a"], x["b"])]
            states = {}
            for x in mine:
                states.setdefault(_state_words(x), []).append(
                    label(x["b"] if x["a"] == d else x["a"]))
            member_lines.setdefault(d, []).append(
                f"{word}: " + "; ".join(f"{s} with {', '.join(p)}" for s, p in states.items()))
    cls = _worst(classes)
    title = seg["name"] + (f" ({', '.join(seg['networks'])})" if seg.get("vlan") else "")
    item = {"id": sid, "a": sid, "b": sid, "segment": True, "title": title, "la": seg["name"],
            "lb": "", "port_a": "", "port_b": "", "cls": cls, "chips": chips,
            "state": "up", "how": f"a multi-access segment: {len(seg['members'])} interfaces on "
                                  f"{', '.join(seg['networks'])}",
            "since": "", "since_seen": False, "rows": rows, "none": [],
            "readers": sorted({d for d, _p in seg["members"]
                               if (nodes.get(d) or {}).get("managed")}),
            "whats": sorted(whats, key=lambda w: -RANK[w[0]]), "manager": False,
            "kind": "segment"}
    members = []
    for d, p in seg["members"]:
        c = member_cls.get(d, "ok")
        members.append({"id": f"{d}:{p}~{sid}:", "a": d, "b": sid, "port_a": p, "port_b": "",
                        "la": label(d), "lb": seg["name"], "member": True,
                        "title": f"{label(d)} {p} on {seg['name']}", "cls": c, "chips": [],
                        "state": "up", "how": f"{label(d)} {p} is on {seg['name']}",
                        "since": "", "since_seen": False,
                        "rows": [{"dt": "Neighbours here", "cls": c, "chip": "",
                                  "lines": member_lines.get(d, ["none on this segment"])}],
                        "none": [], "readers": [d] if (nodes.get(d) or {}).get("managed") else [],
                        "whats": [], "manager": False, "kind": "member"})
    return item, members


def _routing_only(layers: dict, on: list, nodes: dict) -> list:
    """Neighbourships no physical link or segment carries (a peering between loopbacks, an
    adjacency over a link LLDP does not see): drawn straight between the two devices."""
    out = []
    for layer in ("ospf", "ospfv3", "bgp"):
        if layer not in on:
            continue
        for adj in layers.get(layer) or []:
            if adj.get("on_link", True) or adj.get("segment") or adj["a"] not in nodes \
                    or adj["b"] not in nodes:
                continue
            x = dict(adj, _mine=tuple((adj.get("ports") or {}).keys()))
            cls = _adj_cls(x)
            out.append({"id": f"{layer}:{adj['a']}~{adj['b']}:{adj.get('network', '')}",
                        "a": adj["a"], "b": adj["b"], "port_a": "", "port_b": "",
                        "la": label(adj["a"]), "lb": label(adj["b"]),
                        "title": f"{label(adj['a'])} ↔ {label(adj['b'])}, {_word(layer, adj)}",
                        "cls": cls, "routing_only": True, "chips": _adj_chips(layer, [x]),
                        "state": "", "how": "no physical link carries it (between loopbacks, "
                                            "or over a link LLDP does not see)",
                        "since": adj.get("since", ""), "since_seen": adj.get("since_seen"),
                        "rows": [{"dt": f"{_word(layer, adj)} {_fact(layer, [x])}", "cls": cls,
                                  "chip": _state_words(x),
                                  "lines": [f"{label(adj['a'])} to "
                                            f"{_neighbour_words(x, adj['a'])}"]}],
                        "none": [], "readers": [d for d in (adj["a"], adj["b"])
                                                if (nodes.get(d) or {}).get("managed")],
                        "whats": [] if cls == "ok" else [(cls, _fault_words(layer, x, cls),
                                                          adj.get("since"),
                                                          adj.get("since_seen"))],
                        "manager": False, "kind": "routing"})
    return out

# ---------------------------------------------------------------------------- weak points

def _weak(an: dict, phys: list) -> list:
    """Single points of failure, bridges and islands to look at, each in words a person acts on
    (the board's hover: "the only path between the NMAS and the network"). A device that is
    Mercury's only way into part of the network and one whose loss splits the devices are one
    entry, saying both."""
    from modules.readers.topology_graph import MANAGER

    out = []
    m = label(MANAGER)
    ways = {o["device"]: o for o in an.get("only_way_in") or []}
    splits = {s["device"]: s["cuts_off"] for s in an.get("spof") or []}
    for d in sorted(set(ways) | set(splits)):
        parts = []
        if d in ways:
            o = ways[d]
            port = f" {o['port']}" if o.get("port") else ""
            vlan = f", VLAN {o['vlan']}" if o.get("vlan") else ""
            parts.append(f"the only path between {m} and {', '.join(o['reaches'])} ({m} reaches "
                         f"them only through {d}{port}{vlan}). If {d} or that port fails, {m} "
                         f"loses {len(o['reaches'])} device{'s' if len(o['reaches']) != 1 else ''}")
        if d in splits:
            rest = [label(x) for x in splits[d]]
            parts.append(f"if {d} fails, {', '.join(rest)} lose{'s' if len(rest) == 1 else ''} "
                         "the rest")
        out.append({"kind": "spof", "device": d, "title": d,
                    "words": "Single point of failure: " + "; and ".join(parts) + "."})
    for b in an.get("bridges") or []:
        cut = [label(x) for x in b["cuts_off"]]
        out.append({"kind": "bridge", "device": "", "a": b["a"], "b": b["b"],
                    "title": f"{label(b['a'])} ↔ {label(b['b'])}",
                    "words": f"The only link between them: if it fails, {', '.join(cut)} "
                             f"lose{'s' if len(cut) == 1 else ''} the rest."})
    for i in an.get("islands") or []:
        for d in i:
            st = (an.get("island_state") or {}).get(d) or {}
            out.append({"kind": "apart" if st.get("expected") else "island", "device": d,
                        "title": d, "why": (an.get("island_why") or {}).get(d, ""),
                        "expected": st.get("expected"), "since": st.get("since", ""),
                        "became": st.get("became", False)})
    return out


def what_if(phys: list, nodes: dict, out: str) -> dict:
    """Take *out* away from the physical graph (its up links): who loses the rest. With
    Mercury's host drawn, "the rest" is what Mercury reaches: every part joined to a device it
    attaches to (the host forwards nothing between them); without it, the largest part. A
    device already apart is not counted as lost."""
    import networkx as nx

    from modules.readers.topology_graph import MANAGER

    if out not in nodes:
        return {"ok": False, "why": f"{out} is not on this map"}
    attached = {l["b"] for l in phys if l.get("manager") and l.get("state") in ("up", "unknown")}

    def reached(skip):
        g = nx.MultiGraph()
        g.add_nodes_from(n for n, v in nodes.items()
                         if not v.get("external") and not v.get("segment")
                         and n not in (skip, MANAGER))
        for l in phys:
            if not l.get("manager") and l.get("state") in ("up", "unknown") and \
                    skip not in (l["a"], l["b"]):
                g.add_edge(l["a"], l["b"])
        comps = sorted((set(c) for c in nx.connected_components(g)),
                       key=lambda c: (-len(c), sorted(c)))
        if attached:
            return set().union(*[c for c in comps if c & (attached - {skip})])
        return comps[0] if comps else set()

    def managed(n):
        return n != out and (nodes.get(n) or {}).get("managed")
    before, after = reached(None), reached(out)
    lost = sorted(n for n in before - after if managed(n))
    # Mercury reaches no managed device at all without it.
    cut_mgr = bool(attached) and not any(managed(n) for n in after)
    return {"ok": True, "device": out, "lost": lost, "manager_lost": cut_mgr,
            "with_manager": bool(attached)}


# ---------------------------------------------------------------------------- the view

def view(list_name: str, values) -> dict:
    """Everything the page draws for one network and question."""
    from modules.readers.topology_graph import MANAGER

    s = ask(values)
    st = stored()
    out = {"list": list_name, "s": s, "qs": lambda over=None: qs(list_name, s, over),
           "state": st["state"], "value_at": st["value_at"], "failed": st["failed"],
           "proto_words": PROTO_WORDS, "not_read": NOT_READ, "zooms": ZOOMS,
           "line_words": LINE_WORDS, "group_words": GROUP_WORDS, "classes": CLASSES,
           "manager": MANAGER, "label": label, "symbols": symbols(), "icon_of": {}}
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
    nodes, layers = net["nodes"], net["layers"]
    an = (net.get("analysis") or {}).get("physical") or {}
    phys = layers.get("physical") or []
    present = [p for p in PROTOS if layers.get(p)]
    on = present if s["p"] is None else [p for p in s["p"] if p in present]
    links = [_link(l, layers, on, nodes) for l in phys] + _routing_only(layers, on, nodes)
    segs = []
    for seg in net.get("segments") or []:
        item, members = _segment(seg, layers, on, nodes)
        segs.append(item)
        links += members
    weak = _weak(an, phys)
    from modules import topology_positions
    arranged = topology_positions.read(list_name)
    out.update(state="ok", errors=value.get("errors") or [], present=present, on=on,
               layout=net.get("layout"), segments=segs, arranged=arranged,
               nodes=nodes,
               icon_of={name: _ICON[node_class(name, n)] for name, n in nodes.items()})
    fleet = sorted(n for n, v in nodes.items() if v.get("managed"))
    out["collapsed"] = len(fleet) > COLLAPSE_ABOVE
    drawn = [l for l in links if not l.get("member")] + segs
    out["summary"] = {"devices": len(fleet),
                      "links": sum(1 for l in phys),
                      "outside": sum(1 for v in nodes.values() if v.get("outside")),
                      "segments": len(segs),
                      "ok": sum(1 for l in drawn if l["cls"] == "ok")}
    out["attention"] = _attention(drawn, weak, s)
    out["weak"] = weak
    out["critical"] = an.get("critical") or []
    out["list_groups"] = _list_groups(nodes, phys)
    out["fleet"] = fleet
    if s["a"] and s["b"]:
        trace = path_trace(phys, s["a"], s["b"])
        if trace.get("ok"):
            trace["hop_words"] = [[_ports(phys, p[i], p[i + 1]) for i in range(len(p) - 1)]
                                  for p in trace["paths"]]
        out["trace"] = trace
    if s["out"]:
        out["what_if"] = what_if(phys, nodes, s["out"])
    out["matches"] = _search(nodes, phys, s["q"]) if s["q"] else []
    out["selected"] = next((l for l in links + segs if l["id"] == s["sel"]), None)
    if not out["collapsed"]:
        out["svg"] = _svg(nodes, phys, links, weak, s, out, layers.get("bgp") or [], segs)
    return out


def _attention(links: list, weak: list, s: dict) -> dict:
    """The board's "Needs attention on the map": each link that is not as intended, grouped by
    its line style, with what is wrong and since when; then the weak points. Filtered by the
    group asked and the text typed; the counts are always the whole."""
    groups = {"bad": [], "warn": [], "unread": [], "weak": [], "apart": []}
    for l in links:
        if l["cls"] == "ok":
            continue
        top = [w for w in l["whats"] if w[0] == l["cls"]] or l["whats"][:1]
        groups[l["cls"]].append({"link": l, "id": l["id"], "title": l["title"],
                                 "what": "; ".join(w[1] for w in top),
                                 "since": next((w[2] for w in top if w[2]), ""),
                                 "since_seen": next((w[3] for w in top if w[2]), False),
                                 "a": l["a"], "b": l["b"]})
    for w in weak:
        if w["kind"] == "apart":
            groups["apart"].append(w)
        else:
            groups["weak"].append(w)
    counts = {k: len(v) for k, v in groups.items()}
    counts["all"] = counts["bad"] + counts["warn"] + counts["unread"] + counts["weak"]
    needle = s["f"].lower()

    def keep(e):
        text = " ".join(str(e.get(k) or "") for k in ("title", "what", "words", "why", "device"))
        return not needle or needle in text.lower()

    shown = {k: [e for e in v if keep(e)] if s["show"] in ("all", k) or k == "apart" else []
             for k, v in groups.items()}
    return {"groups": shown, "counts": counts,
            "filtered": bool(needle) or s["show"] != "all"}


def _layer_graph(links: list):
    import networkx as nx
    g = nx.MultiGraph()
    for l in links:
        if l.get("state") in ("up", "unknown"):
            g.add_edge(l["a"], l["b"])
    return g


def path_trace(links: list, a: str, b: str) -> dict:
    """Every equal-cost shortest path from *a* to *b* in the physical graph, by hop count: a
    claim about the GRAPH, never about forwarding (the brief, Q8)."""
    import networkx as nx

    g = _layer_graph(links)
    if a not in g or b not in g:
        missing = [d for d in (a, b) if d not in g]
        return {"ok": False, "why": f"{', '.join(missing)} has no link carrying traffic, so no "
                                    "path is drawn"}
    try:
        paths = sorted(nx.all_shortest_paths(g, a, b))
    except nx.NetworkXNoPath:
        return {"ok": False, "why": f"no path joins {a} and {b}: they are in different islands"}
    edges = {tuple(sorted(p[i:i + 2])) for p in paths for i in range(len(p) - 1)}
    return {"ok": True, "paths": paths, "hops": len(paths[0]) - 1, "edges": sorted(edges),
            "nodes": sorted({n for p in paths for n in p})}


def _ports(phys: list, a: str, b: str) -> str:
    for l in phys:
        if {l["a"], l["b"]} == {a, b}:
            ends = {l["a"]: l["port_a"], l["b"]: l["port_b"]}
            return f"{label(a)} {ends[a] or '?'} to {label(b)} {ends[b] or '?'}"
    return f"{label(a)} to {label(b)}"


def _list_groups(nodes: dict, phys: list) -> list:
    """The phone's Devices tab: devices by band, each with its links, ports and states."""
    outside = {n for n, v in nodes.items() if v.get("outside")}
    edge = {l["a"] if l["b"] in outside else l["b"] for l in phys
            if (l["a"] in outside) != (l["b"] in outside)}
    groups = {}
    for name in sorted(n for n, v in nodes.items() if not v.get("segment")):
        n = nodes.get(name) or {}
        mine = [l for l in phys if name in (l["a"], l["b"])]
        groups.setdefault(_band(name, n, edge), []).append({
            "name": name, "label": label(name), "managed": n.get("managed", False),
            "outside": n.get("outside", False), "cls": node_class(name, n),
            "links": [{"to": label(l["b"] if l["a"] == name else l["a"]),
                       "state": l.get("state"), "kind": l.get("kind", ""),
                       "port": (l.get("port_a") if l["a"] == name else l.get("port_b")) or ""}
                      for l in mine]})
    return [{"words": band, "devices": groups[band]} for band in BANDS if band in groups]


def _search(nodes: dict, phys: list, q: str) -> list:
    """Names whose device name, role, an address or one of its ports matches *q* (the board's
    "Find a device, address or interface"; the brief, Q19: it rings, never filters away)."""
    q = q.strip().lower()
    hits = set()
    for name, n in ((k, v) for k, v in nodes.items() if not v.get("segment")):
        if q in name.lower() or q in (n.get("role") or "").lower() or \
                any(q == addr.lower() or q in port.lower()
                    for port, addr in n.get("addresses") or []):
            hits.add(name)
    for l in phys:
        if q in (l.get("port_a") or "").lower():
            hits.add(l["a"])
        if q in (l.get("port_b") or "").lower():
            hits.add(l["b"])
    return sorted(hits)


# ---------------------------------------------------------------------------- the drawing

def _bez(shape: tuple, t: float) -> tuple:
    """The point at *t* along a link's quadratic curve (straight when its control point is the
    middle)."""
    x1, y1, cx, cy, x2, y2, _length = shape
    return ((1 - t) ** 2 * x1 + 2 * (1 - t) * t * cx + t * t * x2,
            (1 - t) ** 2 * y1 + 2 * (1 - t) * t * cy + t * t * y2)


def _overlap(a: tuple, b: tuple) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _chip_w(text: str) -> int:
    return int(len(text) * 6.1 + 14)


def _card_h(l: dict) -> int:
    lines = 2 + sum(1 + sum(math.ceil(len(x) / 46) for x in r["lines"]) for r in l["rows"])
    return 60 + lines * 17 + (17 if l["none"] else 0)


def _svg(nodes, phys, links, weak, s, view_, bgp=(), segs=()) -> dict:
    """The map's elements, positioned in its own coordinates: ``{"width", "height", "bands",
    "links", "nodes", "labels"}``; the template draws them and escapes every name."""
    from modules.readers.topology_graph import MANAGER

    # Laid out by the reader when it read the graph; a value stored by a reader that did not
    # yet lay out is laid out here, until its next read (within a minute).
    geo = view_.get("layout") or layout(nodes, phys)
    geo = dict(geo, positions={k: tuple(v) for k, v in geo["positions"].items()})
    pos, height = geo["positions"], geo["height"]
    # A layout people arranged and saved (C655) places every node it holds; the generated one
    # places the rest.
    saved = ((view_.get("arranged") or {}).get("positions") or {})
    for name, xy in saved.items():
        if name in pos:
            pos[name] = (round(float(xy[0])), round(float(xy[1])))
    width = max([W] + [x + 70 for x, _y in pos.values()])
    height = max([height] + [y + 80 for _x, y in pos.values()])
    trace = view_.get("trace") or {}
    on_path = {tuple(e) for e in trace.get("edges") or []} if trace.get("ok") else set()
    wi = view_.get("what_if") or {}
    gone, lost = wi.get("device"), set(wi.get("lost") or [])
    # Labels Auto (C654): ports and chips on hover or selection, every one zoomed in (150%
    # and closer); On, always; Off, never. They are placed unless Off, for the hover.
    labels = s["labels"] == "on" or (s["labels"] == "auto" and int(s["z"]) >= 150)
    placed = s["labels"] != "off"
    pairs = {}
    for l in links:
        pairs.setdefault(tuple(sorted((l["a"], l["b"]))), []).append(l["id"])
    # What a chip must not cover: each device's icon and name.
    taken = [(x - HALF - 2, y - HALF - 2, x + HALF + 2, y + HALF + 2) for x, y in pos.values()]
    taken += [(x - 34, y + 20, x + 34, y + 36) for x, y in pos.values()]
    shapes = {}
    for l in links:
        if l["a"] not in pos or l["b"] not in pos:
            continue
        (x1, y1), (x2, y2) = pos[l["a"]], pos[l["b"]]
        twins = pairs[tuple(sorted((l["a"], l["b"])))]
        length = math.hypot(x2 - x1, y2 - y1) or 1
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        shift = (twins.index(l["id"]) - (len(twins) - 1) / 2) * 16
        if l.get("routing_only"):
            shift += 22
        x1, y1, x2, y2 = (x1 - uy * shift, y1 + ux * shift, x2 - uy * shift, y2 + ux * shift)
        # A link drawn straight through a device it does not join would read as joining it:
        # bowed instead, away from the band (down for a link along a band, else to the right).
        through = any(_near(q, (x1, y1), (x2, y2), 24) for name, q in pos.items()
                      if name not in (l["a"], l["b"]))
        bow = 52 if through else 0
        nx_, ny_ = (-uy, ux) if -uy >= 0 else (uy, -ux)
        if abs(uy) < 0.3:
            nx_, ny_ = 0, 1
        cx_, cy_ = (x1 + x2) / 2 + nx_ * bow * 2, (y1 + y2) / 2 + ny_ * bow * 2
        shapes[l["id"]] = (x1, y1, cx_, cy_, x2, y2, length)
    # Ports first (they sit by their device), then each link's chips at the first place along it,
    # from the middle outward, that covers nothing placed: the worst links choose first.
    port_at = {}
    for l in links:
        if l["id"] not in shapes or not placed or l.get("routing_only") or l.get("member"):
            continue
        length = shapes[l["id"]][6]
        for end, port in (("a", l["port_a"]), ("b", l["port_b"])):
            w = len(port) * 6.4 + 4
            box = None
            # By its device, stepping out along the link until it covers no other label.
            for reach in (52, 66, 80, 94):
                t = min(reach, length * 0.4) / length
                px, py = _bez(shapes[l["id"]], t if end == "a" else 1 - t)
                box = (px - w / 2, py - 8, px + w / 2, py + 6)
                if not any(_overlap(box, b) for b in taken):
                    break
            taken.append(box)
            port_at[(l["id"], end)] = ((box[0] + box[2]) / 2, box[3] - 2)
    chip_at = {}
    for l in sorted(links, key=lambda l: (-RANK[l["cls"]], (shapes.get(l["id"]) or [0] * 7)[6])):
        if l["id"] not in shapes or not l["chips"]:
            continue
        w = max(_chip_w(c["text"]) for c in l["chips"])
        h = 18 * len(l["chips"])
        best = None
        # Along the link from its middle outward, then a little to either side of it, then
        # further out (drawn with a leader back to the link).
        offsets = [(0, 0), (0, 20), (0, -20), (0, 40), (0, -40), (0, 60), (0, -60)] + \
            [(dx, dy) for dy in (0, 40, -40, 80, -80) for dx in (90, -90, 150, -150)]
        for dx, dy in offsets:
            for t in (0.5, 0.44, 0.56, 0.38, 0.62, 0.32, 0.68, 0.26, 0.74, 0.2, 0.8):
                ax, ay = _bez(shapes[l["id"]], t)
                mx, my = ax + dx, ay + dy
                box = (mx - w / 2, my - h / 2 - 1, mx + w / 2, my + h / 2 + 1)
                if box[0] < 0 or box[2] > width or box[1] < 0 or box[3] > height:
                    continue
                hits = sum(1 for b in taken if _overlap(box, b))
                if best is None or hits < best[0]:
                    best = (hits, mx, my, box, ax, ay)
                if not hits:
                    break
            if best and not best[0]:
                break
        if best is None:
            ax, ay = _bez(shapes[l["id"]], 0.5)
            best = (0, ax, ay, (ax, ay, ax, ay), ax, ay)
        taken.append(best[3])
        chip_at[l["id"]] = (best[1], best[2], best[4], best[5])
    drawn = []
    for l in links:
        if l["id"] not in shapes:
            continue
        x1, y1, cx_, cy_, x2, y2, length = shapes[l["id"]]
        mx, my, lx, ly = chip_at.get(l["id"]) or (_bez(shapes[l["id"]], 0.5) * 2)
        leader = math.hypot(mx - lx, my - ly) > 24
        chips, top = [], my - (len(l["chips"]) - 1) * 9
        for i, c in enumerate(l["chips"]):
            w = _chip_w(c["text"])
            chips.append(dict(c, x=round(mx - w / 2), y=round(top + i * 18 - 8), w=w,
                              tx=round(mx), ty=round(top + i * 18 + 4)))
        t = min(52, length * 0.4) / length
        pax, pay = port_at.get((l["id"], "a")) or _bez(shapes[l["id"]], t)
        pbx, pby = port_at.get((l["id"], "b")) or _bez(shapes[l["id"]], 1 - t)
        (hx1, hy1), (hx2, hy2) = _bez(shapes[l["id"]], 0.2), _bez(shapes[l["id"]], 0.8)
        hcx, hcy = _bez(shapes[l["id"]], 0.5)
        card_h = _card_h(l)
        cx = min(max(mx + 14, 8), width - 328)
        cy = min(max(my + 14, 8), max(height - card_h - 4, 8))
        drawn.append(dict(l, d=f"M{x1:.0f} {y1:.0f}Q{cx_:.0f} {cy_:.0f} {x2:.0f} {y2:.0f}",
                          hit=f"M{hx1:.0f} {hy1:.0f}Q{hcx:.0f} {hcy:.0f} {hx2:.0f} {hy2:.0f}",
                          mx=round(mx), my=round(my), leader=leader, lx=round(lx), ly=round(ly),
                          pa_x=round(pax), pa_y=round(pay),
                          pb_x=round(pbx), pb_y=round(pby),
                          chip_list=chips, card_x=round(cx), card_y=round(cy), card_h=card_h,
                          path=tuple(sorted((l["a"], l["b"]))) in on_path,
                          sel=l["id"] == s["sel"], labels=labels,
                          gone=gone in (l["a"], l["b"])))
    tags = {}
    if s["weak"] == "1":
        for w in weak:
            if w["kind"] == "spof":
                tags.setdefault(w["device"], []).append({"text": "SPOF", "cls": "spof",
                                                         "words": w["words"]})
            elif w["kind"] == "island":
                tags.setdefault(w["device"], []).append({
                    "text": "island", "cls": "isl",
                    "words": f"Island: {w['why']}. {w['device']} cannot be reached through the "
                             "rest until a link joins it."})
            elif w["kind"] == "apart":
                tags.setdefault(w["device"], []).append({
                    "text": "apart", "cls": "apart",
                    "words": f"Apart on purpose: {(w.get('expected') or {}).get('reason', '')}"})
    matches = set(view_.get("matches") or [])
    on_trace = set(trace.get("nodes") or [])
    peer_as = {}
    for adj in bgp:
        for dev, asn in (adj.get("asn") or {}).items():
            if (nodes.get(dev) or {}).get("outside"):
                peer_as.setdefault(dev, asn)
    out_nodes = []
    for name in sorted(pos):
        n = nodes.get(name) or {}
        x, y = pos[name]
        cls = node_class(name, n)
        out_nodes.append({"name": name,
                          "label": label(name) + (f" · AS {peer_as[name]}" if name in peer_as
                                                  else ""),
                          "x": x, "y": y, "cls": cls, "icon": _ICON[cls],
                          "managed": n.get("managed", False), "outside": n.get("outside", False),
                          "answering": n.get("answering", True) or not n.get("managed"),
                          "l3": cls == "l3switch", "tags": tags.get(name, []),
                          "match": name in matches, "path": name in on_trace,
                          "gone": name == gone, "lost": name in lost,
                          "island": any(t["cls"] == "isl" for t in tags.get(name, [])),
                          "spof": any(t["cls"] == "spof" for t in tags.get(name, [])),
                          "role": n.get("role") or "", "manager": name == MANAGER})
    # Each segment: its node, its summary chips under it, its card (C654).
    seg_out = []
    for sg in segs:
        if sg["id"] not in pos:
            continue
        x, y = pos[sg["id"]]
        chips = []
        for i, c in enumerate(sg["chips"]):
            w = _chip_w(c["text"])
            chips.append(dict(c, x=round(x - w / 2), y=round(y + 26 + i * 18), w=w,
                              tx=round(x), ty=round(y + 38 + i * 18)))
        card_h = _card_h(sg)
        seg_out.append(dict(sg, x=round(x), y=round(y), chip_list=chips,
                            w=max(len(sg["la"]) * 8 + 28, 80),
                            card_x=round(min(max(x + 14, 8), width - 328)),
                            card_y=round(min(max(y + 20, 8), max(height - card_h - 4, 8))),
                            card_h=card_h, sel=sg["id"] == s["sel"]))
    return {"width": round(width), "height": round(height), "links": drawn,
            "nodes": [n for n in out_nodes if n["cls"] != "segment"], "segments": seg_out,
            "labels": labels, "placed": placed, "z": s["z"],
            "arranging": s.get("arrange") == "1"}


_ICON = {"router": "router", "switch": "switch", "l3switch": "switch", "server": "server",
         "segment": "unknown",
         "external": "cloud", "unknown": "unknown"}


_SYMBOLS = {}


def symbols() -> str:
    """The device icons as SVG ``<symbol>``s, from static/img/topology/ (one source: the files
    the third-party inventory claims as the project's own), each without its own title: a
    device's title names it. Our own files, so the template marks the string safe."""
    import re

    if "all" not in _SYMBOLS:
        here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "static", "img", "topology")
        out = []
        for name in sorted(_ICON.values()):
            with open(os.path.join(here, f"{name}.svg"), encoding="utf-8") as fh:
                body = fh.read()
            m = re.search(r"<svg\b([^>]*)>(.*)</svg>", body, re.S)
            attrs = " ".join(f'{k}="{v}"' for k, v in re.findall(
                r'\b(viewBox|fill|stroke|stroke-width|stroke-linecap|stroke-linejoin)="([^"]*)"',
                m.group(1)))
            inner = re.sub(r"<title>.*?</title>|<!--.*?-->", "", m.group(2), flags=re.S)
            out.append(f'<symbol id="ti-{name}" {attrs}>{inner}</symbol>')
        _SYMBOLS["all"] = "".join(out)
    return _SYMBOLS["all"]
