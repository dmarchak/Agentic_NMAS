"""Topology's Path… (board D, signed off 2026-10-12; C693, C694): the path packets take from one
device to an address, read hop by hop from each device's own forwarding table.

Each routed hop is asked `show ip cef <destination>` through the reads engine (allowlisted, the
device held while read, masked, recorded on History › Reads); its answer names the next hops,
and the device holding each next hop's address (committed intent, as the topology reader
stores it) is read next. Equal-cost next hops branch. A trace stops, and says why, at the
destination, a device with no route, a hop it cannot read (never guessed past), a loop, a next
hop no device of the network holds (where the network's knowledge ends), or its bounds.

Layer 2 is not read: between two routed hops the map draws the cabling's path through switches,
dashed. The trace is a job; its record is written as each level lands, so any worker draws it
and it reads again later, and it announces `path_trace`.
"""

import ipaddress
import json
import logging
import os
import re
import time
import uuid

log = logging.getLogger(__name__)

#: At most this many branches (equal-cost next hops multiply) and hops in one branch; past
#: either the trace stops and says which bound it reached, never silence.
MAX_BRANCHES = 8
MAX_HOPS = 16

#: The one command a trace sends, the destination its only field (one IPv4 address).
COMMAND = "show ip cef {dest}"

#: Traces kept per network, newest first; older records are removed as a new one is written.
KEEP = 50

ANNOUNCE_KEYS = ("path_trace",)
ANNOUNCER = "path-trace"

#: How a branch ends, as the map draws it: `on` delivered; `out` handed to a device outside
#: the network (C696: the right outcome for an address beyond it, and where Mercury's
#: knowledge ends, so neither delivered nor a failure); `drop` stopped short.
ENDS = {"delivered": "on", "dropped": "drop", "unread": "drop", "loop": "drop",
        "edge": "out", "bounded": "drop"}
RANK = {"on": 2, "out": 1, "drop": 0}
END_WORDS = {"delivered": "delivered", "dropped": "dropped", "unread": "not read",
             "loop": "a loop", "edge": "leaves the network", "bounded": "stopped at a bound"}

#: The trace's steps, in order, as the manual names them (how-it-works/path-trace.md).
STEPS = ("refuse", "read", "follow", "stop", "record")

_NEXTHOP = re.compile(r"^\s*nexthop\s+(\S+)\s+(\S+)")
_NEXT_HOP = re.compile(r"^\s*next hop\s+([^,\s]+),\s*(\S+)")
_VIA = re.compile(r"^\s*via\s+([0-9.]+),\s*([A-Za-z][^,\s]*)")
_ATTACHED = re.compile(r"^\s*(?:attached|connected) to\s+(\S+)")
_PREFIX = re.compile(r"^(\d+\.\d+\.\d+\.\d+/\d+)")


# ---------------------------------------------------------------------------- one answer

def parse_cef(text: str) -> dict:
    """One device's `show ip cef <destination>` answer: ``{state, prefix, hops, iface, why}``.

    *state* is ``next`` (``hops`` each ``{address, iface}``), ``attached`` (the destination is
    on ``iface``'s segment), ``receive`` (the device holds the address), ``no_route``, ``drop``
    (a discard or null route) or ``unknown`` (``why`` says what was not understood)."""
    text = text or ""
    out = {"state": "unknown", "prefix": "", "hops": [], "iface": "", "why": ""}
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    if not lines:
        out["why"] = "the device answered nothing"
        return out
    if lines[0].lstrip().startswith("%"):
        out["why"] = lines[0].strip()
        return out
    m = _PREFIX.match(lines[0].strip())
    out["prefix"] = m.group(1) if m else ""
    for line in lines[1:]:
        low = line.strip().lower()
        for rx in (_NEXTHOP, _NEXT_HOP, _VIA):
            hm = rx.match(line)
            if hm:
                try:
                    addr = str(ipaddress.IPv4Address(hm.group(1)))
                except ValueError:
                    break
                hop = {"address": addr, "iface": hm.group(2)}
                if hop not in out["hops"]:
                    out["hops"].append(hop)
                break
        else:
            am = _ATTACHED.match(line)
            if am and out["state"] == "unknown":
                out.update(state="attached", iface=am.group(1))
            elif low.startswith("receive"):
                out["state"] = "receive"
                out["iface"] = low.split(" for ", 1)[1] if " for " in low else ""
            elif low == "no route":
                out["state"] = "no_route"
            elif low in ("drop", "discard", "null") or low.startswith("attached to null"):
                out["state"] = "drop"
    if out["hops"] and out["state"] == "unknown":
        out["state"] = "next"
    if out["state"] == "unknown":
        out["why"] = f"not an answer the trace reads: {lines[0].strip()[:80]!r}"
    return out


def answer_words(cef: dict) -> str:
    """The hop's answer as the card says it."""
    p = cef.get("prefix") or "?"
    if cef["state"] == "next":
        return f"{p}, next hop " + ", ".join(
            f"{h['address']} out {_short(h['iface'])}" for h in cef["hops"])
    if cef["state"] == "attached":
        return f"{p} attached to {_short(cef['iface'])}"
    if cef["state"] == "receive":
        return f"{p}: its own address" + (f" ({cef['iface']})" if cef["iface"] else "")
    if cef["state"] == "no_route":
        return f"no route ({p})"
    if cef["state"] == "drop":
        return f"{p}: discarded"
    return cef.get("why") or "not understood"


def _short(iface: str) -> str:
    from modules.nsot.ifnames import abbreviate
    return abbreviate(iface) or iface


# ---------------------------------------------------------------------------- the network

def owners(nodes: dict, bgp: list = ()) -> dict:
    """``{IPv4 address: device}`` from the stored topology: each device's intent addresses, and
    an outside peer's peering address from the BGP layer. An address two devices hold (a lab
    tool's shared management address) names neither: a next hop there is not attributed."""
    seen = {}
    for name, n in (nodes or {}).items():
        for _iface, addr in n.get("addresses") or []:
            if ":" in str(addr):
                continue
            seen.setdefault(str(addr), set()).add(name)
    for l in bgp or []:
        ext, addr = l.get("external"), str(l.get("address") or "")
        if ext and addr and ":" not in addr:
            seen.setdefault(addr, set()).add(ext)
    return {a: next(iter(s)) for a, s in seen.items() if len(s) == 1}


def destinations(nodes: dict, bgp: list = ()) -> list:
    """What To offers: each outside peer's peering addresses (``r5 (outside, AS 65002):
    198.51.100.1, r3's peering``), then each routing device's loopback. ``[{value, words,
    device}]``; IPv4 only, as the trace reads `show ip cef`."""
    out, taken = [], set()
    for l in sorted(bgp or [], key=lambda l: (l.get("external") or "", str(l.get("address")))):
        ext, addr = l.get("external"), str(l.get("address") or "")
        if not ext or not addr or ":" in addr or addr in taken:
            continue
        asn = (l.get("asn") or {}).get(ext)
        mine = l["a"] if l.get("b") == ext else l.get("b")
        taken.add(addr)
        out.append({"value": addr, "device": ext,
                    "words": f"{ext} (outside{f', AS {asn}' if asn else ''}): {addr}, "
                             f"{mine}'s peering"})
    for name in sorted(nodes or {}):
        n = nodes[name]
        if not n.get("managed") or not n.get("l3"):
            continue
        lo = next((a for i, a in n.get("addresses") or []
                   if str(i).lower().startswith("lo") and ":" not in str(a)), "")
        if lo and lo not in taken:
            taken.add(lo)
            out.append({"value": lo, "device": name, "words": f"{name} (its loopback {lo})"})
    return out


def sources(nodes: dict) -> list:
    """What From offers: the managed devices that take part in routing."""
    return sorted(n for n, v in (nodes or {}).items() if v.get("managed") and v.get("l3"))


def switches(nodes: dict) -> set:
    """The devices a frame may cross between two routed hops: those the map draws as switches.
    A router never carries the segment between two others."""
    from modules.topology_layout import node_class
    return {n for n, v in (nodes or {}).items()
            if node_class(n, v) in ("switch", "l3switch")}


def l2_path(phys: list, a: str, a_iface: str, b: str, through: set) -> list:
    """The cabling's path from *a* (leaving on *a_iface*) to *b* across *through* (switches):
    ``[(x, y), ...]`` edges, every shortest one, or ``[]`` when none is drawn. Layer 2 is not
    read, so this is the cabling's claim, drawn dashed."""
    import networkx as nx

    g = nx.Graph()
    for l in phys or []:
        if l.get("state") in ("up", "unknown"):
            g.add_edge(l["a"], l["b"])
    if a not in g or b not in g:
        return []
    port = _short(a_iface)
    # The cable the hop leaves on, when its egress is a cabled port; an SVI's is any of them.
    first = {l["b"] if l["a"] == a else l["a"] for l in phys or []
             if a in (l["a"], l["b"]) and
             (l.get("port_a") if l["a"] == a else l.get("port_b")) == port}
    sub = g.subgraph({n for n in g if n in through - {a, b}} | {a, b}).copy()
    if first:
        for n in list(sub.neighbors(a)):
            if n not in first:
                sub.remove_edge(a, n)
    try:
        paths = list(nx.all_shortest_paths(sub, a, b))
    except nx.NetworkXNoPath:
        return []
    return sorted({tuple(sorted(p[i:i + 2])) for p in paths for i in range(len(p) - 1)})


# ---------------------------------------------------------------------------- the trace

def trace(source: str, dest: str, owner_of: dict, read, managed: set) -> dict:
    """Follow *dest* from *source*. *read(devices)* answers ``{device: {"ok", "answer",
    "why"}}`` for one level's devices at once; each device is read once per trace.

    Returns ``{branches, ends, read_order}``: each branch ``{hops, end, words}``, each hop
    ``{device, answer, words, to, to_address, iface}``."""
    dest_owner = owner_of.get(dest, "")
    answers, order = {}, []
    active = [{"hops": [], "at": source, "seen": [source]}]
    done = []
    while active:
        need = sorted({b["at"] for b in active if b["at"] not in answers})
        if need:
            got = read(need) or {}
            order.append(need)
            for d in need:
                r = got.get(d) or {"ok": False, "why": "no answer came back"}
                answers[d] = (parse_cef(r.get("answer", "")) if r.get("ok")
                              else {"state": "unread", "why": r.get("why") or "not read"})
        nxt = []
        for b in active:
            dev, cef = b["at"], answers[b["at"]]
            hop = {"device": dev, "answer": cef, "words": answer_words(cef)
                   if cef["state"] != "unread" else f"not read: {cef['why']}"}
            hops = b["hops"] + [hop]
            if cef["state"] == "unread":
                done.append(_end(hops, "unread", f"the trace stops at {dev}: not read "
                                                 f"({cef['why']}); what follows is not known"))
            elif cef["state"] == "receive" or (dest_owner and dest_owner == dev):
                done.append(_end(hops, "delivered", f"delivered: {dev} holds {dest}"))
            elif cef["state"] == "attached":
                hop.update(to=dest_owner, to_address=dest, iface=cef["iface"])
                if dest_owner:
                    hop["words"] += f": {dest_owner}'s address"
                done.append(_end(hops, "delivered",
                                 f"delivered to {dest_owner}" if dest_owner else
                                 f"delivered onto {_short(cef['iface'])}'s segment at {dev}"))
            elif cef["state"] == "no_route":
                done.append(_end(hops, "dropped", f"dropped at {dev}: no route to {dest}"))
            elif cef["state"] == "drop":
                done.append(_end(hops, "dropped", f"dropped at {dev}: its route discards it"))
            elif cef["state"] != "next":
                done.append(_end(hops, "unread", f"the trace stops at {dev}: {cef['why']}"))
            else:
                for nh in cef["hops"]:
                    h = dict(hop, to=owner_of.get(nh["address"], ""),
                             to_address=nh["address"], iface=nh["iface"])
                    # This branch's own next hop, never its siblings'.
                    h["words"] = (f"{cef['prefix'] or '?'}, next hop {nh['address']}"
                                  + (f" ({h['to']})" if h["to"] else "")
                                  + f" out {_short(nh['iface'])}")
                    branch = b["hops"] + [h]
                    owner = h["to"]
                    if not owner:
                        done.append(_end(branch, "edge", f"leaves the network at {dev} toward "
                                                         f"{nh['address']}, which no device of "
                                                         "the network holds"))
                    elif owner == dest_owner:
                        done.append(_end(branch, "delivered", f"delivered to {owner}"))
                    elif owner in b["seen"]:
                        done.append(_end(branch, "loop", f"{dev} sends it back to {owner}: a "
                                                         "forwarding loop"))
                    elif owner not in managed:
                        done.append(_end(branch, "edge", f"leaves the network at {dev} toward "
                                                         f"{owner}"))
                    elif len(branch) >= MAX_HOPS:
                        done.append(_end(branch, "bounded", f"stopped: more than {MAX_HOPS} "
                                                            "hops"))
                    else:
                        nxt.append({"hops": branch, "at": owner, "seen": b["seen"] + [owner]})
        room = MAX_BRANCHES - len(done)
        if len(nxt) > max(room, 0):
            for b in nxt[max(room, 0):]:
                done.append(_end(b["hops"], "bounded", f"stopped: more than {MAX_BRANCHES} "
                                                       "equal-cost branches"))
            nxt = nxt[:max(room, 0)]
        active = nxt
    done.sort(key=lambda b: (-RANK[b["cls"]], [h["device"] for h in b["hops"]]))
    return {"branches": done, "read_order": order,
            "delivered": sum(1 for b in done if b["end"] == "delivered")}


def _end(hops: list, end: str, words: str) -> dict:
    return {"hops": hops, "end": end, "cls": ENDS[end], "words": words}


def drawn(result: dict, phys: list, nodes: dict) -> dict:
    """What the map lights: ``{"edges": {"a|b": {cls, l2}}, "nodes": {device: cls}}``. Where
    branches share a link or a device, a delivered branch's colour wins, then one leaving the
    network (C696: handed to a device outside it), then one that stops."""
    edges, lit = {}, {}
    through = switches(nodes)

    def put(key, cls, l2):
        cur = edges.get(key)
        if cur is None or RANK[cls] > RANK[cur["cls"]]:
            edges[key] = {"cls": cls, "l2": l2}
        elif cur["cls"] == cls:
            cur["l2"] = cur["l2"] and l2

    def mark(device, cls):
        if device not in lit or RANK[cls] > RANK[lit[device]]:
            lit[device] = cls

    for b in result.get("branches") or []:
        for h in b["hops"]:
            mark(h["device"], b["cls"])
            if not h.get("to"):
                continue
            path = l2_path(phys, h["device"], h.get("iface") or "", h["to"], through)
            for a, z in path:
                put(f"{a}|{z}", b["cls"], len(path) > 1)
            if b["end"] in ("delivered", "edge") and h is b["hops"][-1]:
                mark(h["to"], b["cls"])
    return {"edges": edges, "nodes": lit}


# ---------------------------------------------------------------------------- the record

def _dir(list_name: str) -> str:
    from modules import config
    return os.path.join(config.get_list_data_dir(list_name), "paths")


def _path(list_name: str, trace_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id or ""):
        raise ValueError(f"not a trace id: {trace_id!r}")
    return os.path.join(_dir(list_name), f"{trace_id}.json")


def _write(list_name: str, record: dict) -> None:
    folder = _dir(list_name)
    os.makedirs(folder, exist_ok=True)
    path = _path(list_name, record["id"])
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    os.replace(tmp, path)


def _prune(list_name: str) -> None:
    folder = _dir(list_name)
    try:
        names = [n for n in os.listdir(folder) if n.endswith(".json")]
    except FileNotFoundError:
        return
    names.sort(key=lambda n: os.path.getmtime(os.path.join(folder, n)), reverse=True)
    for n in names[KEEP:]:
        try:
            os.remove(os.path.join(folder, n))
        except OSError:
            log.warning("path trace: could not remove the old record %s", n)


def get(list_name: str, trace_id: str):
    """The trace's record, or None when there is none; ``{"unreadable": why}`` when its file
    cannot be read (absent and unreadable are different states). Raises ValueError for what is
    not a trace id."""
    path = _path(list_name, trace_id)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except ValueError as exc:
        return {"unreadable": str(exc)}
    except OSError as exc:
        return {"unreadable": f"{type(exc).__name__}: {exc}"}


def _announce() -> None:
    try:
        from modules import invalidation
        invalidation.announce(ANNOUNCE_KEYS, by=ANNOUNCER, ok=True)
    except Exception:                                 # noqa: BLE001 (a page's progress only)
        log.debug("path trace: an announcement failed", exc_info=True)


def refusal(source: str, dest: str, sources_: list) -> str:
    """Why this trace cannot start, or ``""``: the comparison and both operands."""
    if source not in sources_:
        return (f"From is {source!r}, which is not one of this network's routing devices "
                f"({', '.join(sources_) or 'none'})")
    try:
        addr = ipaddress.ip_address(dest)
    except ValueError:
        return f"To is {dest!r}, which is not an address"
    if addr.version != 4:
        return f"To is {dest}, an IPv6 address; the trace reads IPv4 forwarding only"
    return ""


def start(list_name: str, source: str, dest: str, dest_words: str, actor: str, *,
          nodes: dict, bgp: list, run_reads=None) -> dict:
    """Refuse now (``{"refused": why}``, nothing asked), or start the trace as a job:
    ``{"trace": id, "job": id}``. *run_reads* (tests) replaces the reads engine."""
    from modules.nsot import capture_job

    why = refusal(source, dest, sources(nodes))
    if why:
        return {"refused": why}
    dest = str(ipaddress.IPv4Address(dest))
    owner_of = owners(nodes, bgp)
    managed = {n for n, v in nodes.items() if v.get("managed")}
    trace_id = uuid.uuid4().hex
    record = {"id": trace_id, "list": list_name, "actor": actor, "source": source,
              "dest": dest, "dest_words": dest_words or dest, "state": "running",
              "started_at": time.time(), "finished_at": None, "reading": [source],
              "read": [], "runs": [], "branches": [], "delivered": 0, "error": ""}
    _write(list_name, record)
    _prune(list_name)
    command = COMMAND.format(dest=dest)

    def read(devices):
        record["reading"] = list(devices)
        _write(list_name, record)
        _announce()
        if run_reads is not None:
            got = run_reads(devices, command)
        else:
            from modules.nsot import reads
            try:
                rec = reads.run(list_name, devices, [command], actor,
                                purpose=f"Path: {source} to {dest}")
            except reads.Refused as exc:
                return {d: {"ok": False, "why": str(exc)} for d in devices}
            record["runs"].append(rec["id"])
            got = {}
            for d in devices:
                r = rec["results"].get(d) or {}
                a = reads.answer_of(rec, d, command) or {}
                got[d] = ({"ok": True, "answer": a.get("answer", "")}
                          if a.get("state") == reads.ANSWERED else
                          {"ok": False, "why": a.get("why") or r.get("why") or r.get("state")
                           or "not read"})
        record["read"] = record["read"] + list(devices)
        return got

    def work(_job_id):
        try:
            got = trace(source, dest, owner_of, read, managed)
            record.update(branches=got["branches"], delivered=got["delivered"],
                          state="done")
        except Exception as exc:                      # noqa: BLE001 (the trace's own failure)
            log.exception("path trace %s failed", trace_id)
            record.update(state="failed", error=f"{type(exc).__name__}: {exc}")
        record.update(finished_at=time.time(), reading=[])
        _write(list_name, record)
        return {"trace": trace_id}

    job = capture_job.start(list_name, f"Path {source} to {dest}", actor, work,
                            kind="path trace", announce_keys=ANNOUNCE_KEYS,
                            announcer=ANNOUNCER)
    return {"trace": trace_id, "job": job}
