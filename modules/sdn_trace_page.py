"""Topology › Path… on the Flow tables layer (board D, docs/boards/sdn-trace.html; the final SDN
lab's A4 and its ports bonus, C2578 and C1911): the question asked of the SDN trace
(`modules/sdn/trace.py`) and its answer, shaped for `templates/v2/_topology_flowtrace.html`.

**A read, any viewer** (board D4): the trace walks the SDN reader's stored value and asks
nothing of the controller or any switch, so this page asks it on every view of the question
and the answer redraws as each read arrives (`nmas:sdn`). Nothing is held, recorded or
invalidated; the route is Topology's region, a GET.

**The steps** (`STEPS`, named on the manual's page how-it-works/sdn-trace.md):
1. ``name``: NetBox's view of the fabric, read ONCE from the network's committed NSOT export
   (`sdn.known.read`): each switch's name by its datapath id, and every end host's and
   device's interface with its MAC, its addresses and the switch port its cable ends on. It
   names the choices From and to offer, and answers an end given by NAME or by a NetBox
   address; the answer says which source answered.
2. ``read``: the SDN reader's stored value, read ONCE (`reader_job.read_cached_for`), shared by
   the choices and the walk.
3. ``find``: each end found (`sdn.known.resolve`): a host the controller lists on an edge
   port, by address or MAC, or by NetBox's interface with the name or address given and its
   MAC; where the controller has learnt no such host, NetBox's own place for it, said so; one
   listed at two places is refused, each MAC offered. A to that is an address nothing lists
   is an address-only destination.
4. ``packet``: the packet built (`trace.packet_of`): ICMP echo, or TCP or UDP from 49152 to
   the port given, in the addresses' family; to an address-only destination its destination
   MAC is the "not known" value, and the answer says what that assumes.
5. ``walk``: through each switch's flow tables, OpenFlow 1.3.5's matching (`trace.walk`).
6. ``answer``: each branch's ending in its colour (a flow's drop, the table-miss, a port with
   nothing behind it and a listed host's port each a state of its own), the delivered branch's
   DPIDs with their in and out ports, a stale read said above it and never green.

**What Mercury knows is chosen, never typed** (the charter; C3013, C3011): From is a selection
of the hosts Mercury knows (`sdn.known.options`: the NetBox name first, then the MAC, then
the address; a host with no NetBox match by its switch and port); to is a combo box of the
same hosts that also takes an address, a MAC or a name typed in, checked, with its refusal
naming why.
"""

import logging

log = logging.getLogger(__name__)

STEPS = ("name", "read", "find", "packet", "walk", "answer")
#: The question's keys in Topology's address (`topology_page.ASKS`): the layer, and the flow
#: trace's From, to, Protocol and destination port.
KEYS = ("layer", "src", "dst", "proto", "dport")
PROTO_WORDS = {"icmp": "ICMP echo", "tcp": "TCP", "udp": "UDP"}
#: The most hosts to's combo box suggests (board D, D7): its suggestion list is never one of
#: every host; From's choice lists every host Mercury knows (C3013).
SUGGESTED = 20
#: A branch longer than this draws its first two and last two hops, the middle folded (board D,
#: artboard F).
FOLD_ABOVE = 6
#: Each ending (`trace.ending`'s keys): its chip's words, the badge's kind, the map's class
#: (`path_trace.RANK`'s), and the heading's words at the switch it ends at (board D, artboard
#: C). A drop by a flow, the table-miss (to the controller, or dropped), a port with nothing
#: behind it and a listed host's port are each a state of their own (C3013).
ENDINGS = {
    "delivered": ("delivered", "ok", "on", "delivered"),
    "dropped": ("dropped", "danger", "drop", "dropped at {at}"),
    "dropped_by_flow": ("dropped by a flow", "danger", "drop", "dropped by a flow at {at}"),
    "table_miss_dropped": ("table-miss: dropped", "danger", "drop",
                           "no flow matched at {at}: the table-miss drops it"),
    "elsewhere": ("to another host", "danger", "drop", "sent to another host's port at {at}"),
    "loop": ("a loop", "danger", "drop", "a loop at {at}"),
    "table_miss_controller": ("table-miss: to the controller", "warn", "drop",
                              "no flow matched at {at}: the table-miss sends it to the "
                              "controller"),
    "to_controller": ("to the controller", "warn", "drop", "sent to the controller at {at}"),
    "to_host": ("to a listed host", "neutral", "out", "reaches a listed host's port at {at}"),
    "leaves": ("leaves the fabric", "neutral", "out", "leaves the fabric at {at}"),
    "local": ("to the switch itself", "neutral", "out", "sent to {at}'s own local port"),
    "unknown": ("cannot tell", "warn", "drop", "cannot tell, at {at}"),
    "not_read": ("cannot tell", "warn", "drop", "cannot tell, {at}'s table not read"),
}
#: The summary's order (board D, artboard F): delivered, then cannot tell, then the rest.
ORDER = ("delivered", "unknown", "not_read", "elsewhere", "to_host", "leaves", "dropped",
         "dropped_by_flow", "table_miss_dropped", "table_miss_controller", "to_controller",
         "local", "loop")
#: The endings whose heading stands alone: the packet was neither delivered nor lost to a
#: fault of the tables, so "not delivered" is not said before it.
_NEUTRAL = ("to_controller", "table_miss_controller", "leaves", "to_host", "unknown",
            "not_read", "local")


def asked(s: dict) -> bool:
    """Whether the question asks a flow trace: the Flow tables layer with From or to given."""
    return s.get("layer") == "of" and bool(s.get("src") or s.get("dst"))


# ───────────────────────────────────────────────────────────────────────────── the answer

def _hop_flow(f: dict) -> dict:
    from modules import sdn_page
    from modules.sdn import flow_intent

    owner = f.get("owner") or ""
    return {"table": f.get("table_id", 0), "priority": f.get("priority", 0),
            "cookie": sdn_page._cookie_hex(f.get("cookie")),
            "match": sdn_page._match_words(f.get("match")),
            "actions": flow_intent.action_words(f.get("actions") or []),
            "owner": sdn_page.OWNER_WORDS.get(owner, "not classified"),
            "owner_kind": sdn_page.OWNER_KIND.get(owner, "muted")}


def _hops(branch: dict, links: dict, names: dict, dst_words: str) -> list:
    """A branch's hops as the table draws them: each with its deciding flow (the last its
    pipeline took), every flow it ran, and where the packet goes next."""
    out = []
    hops = branch["hops"]
    for i, h in enumerate(hops):
        flows = [_hop_flow(f) for f in h.get("flows") or []]
        then = ""
        if i + 1 < len(hops):
            nxt = links.get((h["dpid"], h["out_port"]))
            if nxt:
                then = f"link to {names.get(nxt[0]) or f'{nxt[0]:016x}'} port {nxt[1]}"
        elif branch["outcome"] == "delivered":
            then = f"{dst_words}'s port"
        # The raw flows and the integer DPID stay here: the table draws `flows_drawn` and
        # `dpid_hex`.
        drawn = {k: v for k, v in h.items() if k not in ("flows", "dpid")}
        out.append(dict(drawn, n=i + 1, flows_drawn=flows,
                        switch=names.get(h["dpid"]) or h.get("name") or h["dpid_hex"],
                        decided=flows[-1] if flows else None, then=then,
                        last=i + 1 == len(hops)))
    return out


def _folded(hops: list) -> dict:
    """A long branch's hops, its middle folded (board D, artboard F)."""
    if len(hops) <= FOLD_ABOVE:
        return {"head": hops, "middle": [], "tail": []}
    return {"head": hops[:2], "middle": hops[2:-2], "tail": hops[-2:]}


def _packet_lines(pkt: dict) -> list:
    def say(keys):
        parts = []
        for k in keys:
            if k in pkt:
                v = pkt[k]
                if k == "eth_type":
                    v = f"{v:#06x}"
                elif k == "vlan_vid" and v == 0:
                    v = "none"
                parts.append(f"{k}={v}")
        return ", ".join(parts)

    lines = [("Ethernet", say(("eth_src", "eth_dst", "eth_type", "vlan_vid")))]
    if "ipv4_src" in pkt:
        lines.append(("IP", say(("ipv4_src", "ipv4_dst", "ip_proto", "ip_dscp", "ip_ecn"))))
    else:
        lines.append(("IPv6", say(("ipv6_src", "ipv6_dst", "ipv6_flabel", "ip_proto", "ip_dscp",
                                   "ip_ecn"))))
    for label, keys in (("TCP", ("tcp_src", "tcp_dst")), ("UDP", ("udp_src", "udp_dst")),
                        ("ICMP", ("icmpv4_type", "icmpv4_code")),
                        ("ICMPv6", ("icmpv6_type", "icmpv6_code"))):
        if keys[0] in pkt:
            lines.append((label, say(keys)))
    return lines


def _proto_words(proto: str, port, pkt: dict) -> str:
    if proto == "icmp":
        return "ICMPv6 echo" if pkt.get("eth_type") == 0x86DD else "ICMP echo"
    return f"{PROTO_WORDS[proto]} {port}"


def _primary(got: dict) -> dict:
    """The branch the answer leads with: the delivered one, else the one the trace's own words
    name (the first it cannot follow, for cannot tell), else the first."""
    from modules.sdn import trace as TR

    branches = got["branches"]
    if not branches:
        return None
    for b in branches:
        if b["outcome"] == "delivered":
            return b
    if got["state"] == "cannot_tell":
        return next((b for b in branches if b["outcome"] in TR.UNSURE), branches[0])
    return branches[0]


def lit(got: dict, primary: dict) -> dict:
    """What the map lights (Topology's own colours, `path_trace.RANK`): the primary branch's
    switches and the links between them, the source host's link and, when delivered, the
    destination's; one branch only when the trace has more (board D, artboard F)."""
    from modules.path_trace import RANK
    from modules.sdn import topology as T
    from modules.sdn import trace as TR

    edges, nodes = {}, {}
    branches = got["branches"] if len(got["branches"]) == 1 else ([primary] if primary else [])

    def put(a, b, cls):
        key = "|".join(sorted((a, b)))
        if key not in edges or RANK[cls] > RANK[edges[key]["cls"]]:
            edges[key] = {"cls": cls, "l2": False}

    def mark(name, cls):
        if name not in nodes or RANK[cls] > RANK[nodes[name]]:
            nodes[name] = cls

    src, dst = got["source"], got["destination"]
    for b in branches:
        cls = ENDINGS[TR.ending(b)][2]
        keys = [T.switch_key(h["dpid"]) for h in b["hops"]]
        if keys:
            put(T.host_key(src), keys[0], cls)
            mark(T.host_key(src), cls)
        for a, z in zip(keys, keys[1:]):
            put(a, z, cls)
        for k in keys:
            mark(k, cls)
        if b["outcome"] == "delivered" and keys:
            put(keys[-1], T.host_key(dst), cls)
            mark(T.host_key(dst), cls)
    return {"edges": edges, "nodes": nodes}


def _branch(b: dict, links: dict, names: dict, dst_words: str) -> dict:
    """A branch as the card draws it: *outcome* is its ending (`trace.ending`'s key, the
    group it is counted in), with that ending's chip, colour and map class."""
    from modules.sdn import trace as TR

    hops = _hops(b, links, names, dst_words)
    chip, kind, cls, _heading = ENDINGS[TR.ending(b)]
    last = hops[-1] if hops else {}
    return {"outcome": TR.ending(b), "words": b["words"], "chip": chip, "kind": kind,
            "cls": cls, "hops": hops, "fold": _folded(hops),
            "path": " → ".join(h["switch"] for h in hops), "at": last.get("switch", "")}


def _asked_words(text: str, end: dict, address: str) -> str:
    """An end as the title names it: what was asked, unless that is a MAC (a choice's value):
    then the host's NetBox name, else the address traced."""
    from modules.sdn import known

    if known._mac(text):                                        # noqa: SLF001 (one MAC shape)
        return end.get("name") or address or text
    return text


def answer(got: dict, s: dict, fab: dict, nb: dict = None) -> dict:
    """The answer card's fields from `trace.trace`'s *got* (``ok`` True); *nb* is NetBox's view
    (`sdn.known.read`'s), whose names the switches are drawn by where it has one."""
    from modules.sdn import known
    from modules.sdn import trace as TR

    controller = next((c for c in fab.get("controllers") or [] if c["name"] == got["controller"]),
                      {"links": {}, "switches": {}})
    links = controller["links"]
    names = known.labels_of([controller], nb)
    pkt = got["packet"]
    v4 = "ipv4_src" in pkt
    src, dst = got["source"], got["destination"]
    lone = bool(got.get("address_only"))
    src_words = _asked_words(s["src"], src, pkt["ipv4_src" if v4 else "ipv6_src"])
    dst_words = _asked_words(s["dst"], dst, pkt["ipv4_dst" if v4 else "ipv6_dst"])
    primary = _primary(got)
    branches = [_branch(b, links, names, dst_words) for b in got["branches"]]
    lead = next((b for b, raw in zip(branches, got["branches"]) if raw is primary), None)
    proto = _proto_words(s["proto"], s["dport"], pkt)
    count = {o: sum(1 for b in branches if b["outcome"] == o) for o in ORDER}
    others = len(branches) - 1 + got["more"]
    unsure = count["unknown"] + count["not_read"] + got["more"]
    if got["state"] == "delivered":
        n = len(lead["hops"])
        summary = f"delivered through {n} switch{'es' if n != 1 else ''}"
        if others:
            summary += f"; and {others} other cop{'y' if others == 1 else 'ies'} of it"
            if unsure:
                summary += f", {unsure} of which the trace cannot follow"
        chip, kind = "delivered", "ok"
    elif lead is None:
        summary = f"cannot tell: {got['more']} branches past the {TR.MAX_BRANCHES} drawn"
        chip, kind = "cannot tell", "warn"
    else:
        heading = ENDINGS[lead["outcome"]][3].format(at=lead["at"])
        # An address-only destination has no port of its own, so nothing is "not delivered":
        # the answer leads with how the packet ends (C3013).
        summary = heading if lone or lead["outcome"] in _NEUTRAL \
            else f"not delivered, {heading}"
        if lone and others:
            summary += f"; and {others} other cop{'y' if others == 1 else 'ies'} of it"
        chip, kind = lead["chip"], lead["kind"]
    if not got["current"]:
        summary += ", as last read"
        chip, kind = f"{chip}, as last read", "neutral"
    groups = []
    for o in ORDER:
        members = [b for b in branches if b["outcome"] == o]
        if members:
            groups.append({"outcome": o, "chip": members[0]["chip"], "kind": members[0]["kind"],
                           "branches": members, "open": o == "delivered"})
    notes = []
    for h in (lead or {}).get("hops") or []:
        for note in h.get("notes") or []:
            said = f"{h['switch']}: {note}"
            if said not in notes:
                notes.append(said)

    def end_words(h, address):
        """A host as the board writes it: its NetBox name where it has one, the address
        traced, its MAC, its switch by NetBox's name (else the name it reports, else its DPID)
        and its port by number and name; a place that is NetBox's, not learnt, said so."""
        name = known.switch_words(int(h["dpid"]), names)
        port = f"port {h['port_no']}" + (f" ({h['port_name']})" if h.get("port_name") else "")
        lead_words = f"{h['name']}, {address}" if h.get("name") else address
        words = f"{lead_words} ({h['mac']}) on {name} {port}"
        return words if h.get("learnt", True) else f"{words}, by NetBox's cable"

    from_words = end_words(src, pkt["ipv4_src" if v4 else "ipv6_src"])
    to_words = (f"{dst['address']}, an address no controller lists" if lone else
                end_words(dst, pkt["ipv4_dst" if v4 else "ipv6_dst"]))
    mac_words = (f"the source's from {got['controller']}'s host table"
                 + ("" if src.get("learnt", True) else " (NetBox's, the controller having "
                                                       "learnt none)")
                 + f"; the destination's is {known.UNKNOWN_MAC}, the \"not known\" value, "
                   "since nothing lists the address" if lone else
                 f"{got['controller']}'s host table"
                 + ("" if src.get("learnt", True) and dst.get("learnt", True) else
                    ", and NetBox's for a host it has not learnt")
                 + ", as if ARP had already resolved them")
    return {"state": "ok", "trace_state": got["state"], "current": got["current"],
            "read_at": got["read_at"], "read_why": got["read_why"],
            "controller": got["controller"], "title": f"{src_words} to {dst_words}, {proto}",
            "summary": summary, "chip": chip, "kind": kind,
            "from_words": from_words, "to_words": to_words,
            "lead": lead, "branches": branches, "groups": groups,
            "more": got["more"], "max": TR.MAX_BRANCHES, "many": len(branches) > 1,
            "way_notes": notes, "packet_lines": _packet_lines(pkt), "proto": proto,
            "family": "IPv6" if pkt.get("eth_type") == 0x86DD else "IPv4",
            "source_port": pkt.get("tcp_src") or pkt.get("udp_src") or "",
            "address_only": lone, "assumed": got.get("assumed") or "",
            "mac_words": mac_words, "notes": list(got.get("notes") or []),
            "packet_from": src_words, "packet_to": dst_words,
            "words": got["words"], "lit": lit(got, primary)}


def _netbox_words(nb: dict, network: str) -> str:
    """What the form says of NetBox's names: read (naming the export), absent or unreadable,
    each its own words."""
    if nb["state"] == "read":
        return f"NetBox's names are from {network}'s committed NSOT export ({nb['sha']})"
    if nb["state"] == "unreadable":
        return f"NetBox's names are not offered: the NSOT export could not be read ({nb['why']})"
    return ("NetBox's names are not offered: " + (nb.get("why") or f"{network} has no "
                                                  "committed NSOT export"))


def _suggestions(fab: dict, nb: dict = None) -> dict:
    """The first `SUGGESTED` hosts Mercury knows (`sdn.known.options`: NetBox-named ones first),
    for to's combo box (board D, D7): ``{"hosts": [{value, words}], "of": total}``. *value* is
    what the box inserts: the host's NetBox name where one host alone carries it, else its
    first global address where one alone holds it, else its MAC; *words* the whole label."""
    return _suggest(_options(fab, nb))


def _suggest(options: list) -> dict:
    return {"hosts": [{"value": o["text"], "words": o["label"]} for o in options[:SUGGESTED]],
            "of": len(options)}


def _options(fab: dict, nb: dict = None) -> list:
    """`sdn.known.options` for the fabric, each with *text*, what to's combo box inserts."""
    from modules.sdn import known

    options = known.options(fab.get("controllers") or [], nb)
    names, addresses = {}, {}
    for o in options:
        names[o["name"].lower()] = names.get(o["name"].lower(), 0) + 1
        addresses[o["address"]] = addresses.get(o["address"], 0) + 1
    for o in options:
        if o["name"] and names[o["name"].lower()] == 1:
            o["text"] = o["name"]
        elif o["address"] and addresses[o["address"]] == 1:
            o["text"] = o["address"]
        else:
            o["text"] = o["value"]
    return options


def _choices(fab: dict, nb: dict, s: dict) -> dict:
    """From's choices (`sdn.known.options`, every host Mercury knows) and to's suggestions:
    ``{"options": [{value, label}], "picked": the option's value From shows chosen, "typed":
    a From given that is no choice (an address in a link, a host since gone), kept as one more
    option so the form sends back what was asked, "suggest": `_suggestions`'s}``."""
    from modules.sdn import known

    options = _options(fab, nb)
    picked, typed = "", ""
    asked_src = str(s.get("src") or "").strip()
    if asked_src:
        try:
            end = known.resolve(fab.get("controllers") or [], asked_src, nb, "source")
            picked = end.get("mac", "")
        except Exception:                               # noqa: BLE001 (the trace says why)
            picked = ""
        if picked not in {o["value"] for o in options}:
            picked, typed = "", asked_src
    return {"options": [{"value": o["value"], "label": o["label"]} for o in options],
            "picked": picked, "typed": typed, "suggest": _suggest(options)}


def view(network: str, s: dict, cached=None, now: float = None, export_read=None) -> dict:
    """Everything the Flow tables layer draws for *network* and the question *s* (Topology's
    `ask`): ``{"state": "form" | "refused" | "failed" | "ok", ...}``. *cached* and *now* are
    the stored value and the clock (a test's); read once from the store when None.
    *export_read* is `export.read`'s answer (a test's); the network's committed export is read
    once (`sdn.known.read`) when None."""
    from modules import reader_job
    from modules.readers import sdn_controllers as R
    from modules.sdn import known
    from modules.sdn import trace as TR

    out = {"state": "form", "notes": [], "read_at": "", "controller": "",
           "choices": {"options": [], "picked": "", "typed": "",
                       "suggest": {"hosts": [], "of": 0}}, "netbox_words": ""}
    try:
        nb = known.shaped(export_read) if export_read is not None else known.read(network)
        out["netbox_words"] = _netbox_words(nb, network)
        got_store = cached if cached is not None else reader_job.read_cached_for(
            R.READER_NAME, network)
        fab = TR.fabric(network, cached=got_store, now=now)
        out["choices"] = _choices(fab, nb, s)
        if fab.get("controllers"):
            c = fab["controllers"][0]
            out.update(read_at=c.get("read_at", ""), controller=c.get("name", ""),
                       current=c.get("state") == "read")
        if not asked(s):
            return out
        for end, key in (("source", "src"), ("destination", "dst")):
            if not s.get(key):
                out.update(state="refused", end=end, places=[],
                           error=("From is empty: choose the source host" if end == "source"
                                  else "to is empty: give the destination host's IPv4 or IPv6 "
                                       "address, MAC or name, or an address to follow the "
                                       "packet to"))
                return out
        port = s.get("dport") if s.get("proto") in ("tcp", "udp") else None
        got = TR.trace(network, s["src"], s["dst"], protocol=s.get("proto") or "icmp",
                       port=port, cached=got_store, now=now, netbox=nb)
        if not got["ok"]:
            out.update(state="refused", error=got["error"], end=got.get("end", ""),
                       places=[{"mac": p["mac"], "words": p["words"]}
                               for p in got.get("places") or []])
            return out
        out.update(answer(got, s, fab, nb))
        return out
    except Exception as exc:                            # noqa: BLE001 (drawn, never a 500)
        log.exception("the SDN trace of %s failed", network)
        out.update(state="failed", error=f"{type(exc).__name__}: {exc}")
        return out
