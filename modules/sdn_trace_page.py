"""Topology › Path… on the Flow tables layer (board D, docs/boards/sdn-trace.html; the final SDN
lab's A4 and its ports bonus, C2578 and C1911): the question asked of the SDN trace
(`modules/sdn/trace.py`) and its answer, shaped for `templates/v2/_topology_flowtrace.html`.

**A read, any viewer** (board D4): the trace walks the SDN reader's stored value and asks
nothing of the controller or any switch, so this page asks it on every view of the question
and the answer redraws as each read arrives (`nmas:sdn`). Nothing is held, recorded or
invalidated; the route is Topology's region, a GET.

**The steps** (`STEPS`, named on the manual's page how-it-works/sdn-trace.md):
1. ``name``: an end given by NAME (neither an address nor a MAC) is looked up among NetBox's end
   hosts in the network's committed NSOT export (`nsot.export.host_ports`), and traced by its
   MAC; the answer says which source answered. An address or MAC goes to the controller as
   given.
2. ``read``: the SDN reader's stored value, read ONCE (`reader_job.read_cached_for`), shared by
   the suggestions and the walk.
3. ``find``: each end found among the hosts the controller lists on an edge port
   (`trace.find_host`); one listed at two places is refused, each MAC offered.
4. ``packet``: the packet built (`trace.packet_of`): ICMP echo, or TCP or UDP from 49152 to
   the port given, in the addresses' family.
5. ``walk``: through each switch's flow tables, OpenFlow 1.3.5's matching (`trace.walk`).
6. ``answer``: each branch's ending in its colour, the delivered branch's DPIDs with their in
   and out ports, a stale read said above it and never green.
"""

import ipaddress
import logging
import re

log = logging.getLogger(__name__)

STEPS = ("name", "read", "find", "packet", "walk", "answer")
#: The question's keys in Topology's address (`topology_page.ASKS`): the layer, and the flow
#: trace's From, to, Protocol and destination port.
KEYS = ("layer", "src", "dst", "proto", "dport")
PROTO_WORDS = {"icmp": "ICMP echo", "tcp": "TCP", "udp": "UDP"}
#: The most hosts suggested under From and to (board D, D7): never a list of every host.
SUGGESTED = 20
#: A branch longer than this draws its first two and last two hops, the middle folded (board D,
#: artboard F).
FOLD_ABOVE = 6
#: Each ending: its chip's words, the badge's kind, the map's class (`path_trace.RANK`'s), and
#: the heading's words at the switch it ends at (board D, artboard C).
ENDINGS = {
    "delivered": ("delivered", "ok", "on", "delivered"),
    "dropped": ("dropped", "danger", "drop", "dropped at {at}"),
    "no_match": ("no flow matched", "danger", "drop", "no flow matched at {at}"),
    "elsewhere": ("to another host", "danger", "drop", "sent to another host's port at {at}"),
    "loop": ("a loop", "danger", "drop", "a loop at {at}"),
    "to_controller": ("to the controller", "warn", "drop", "sent to the controller at {at}"),
    "leaves": ("leaves the fabric", "neutral", "out", "leaves the fabric at {at}"),
    "local": ("to the switch itself", "neutral", "out", "sent to {at}'s own local port"),
    "unknown": ("cannot tell", "warn", "drop", "cannot tell, at {at}"),
    "not_read": ("cannot tell", "warn", "drop", "cannot tell, {at}'s table not read"),
}
#: The summary's order (board D, artboard F): delivered, then cannot tell, then the rest.
ORDER = ("delivered", "unknown", "not_read", "elsewhere", "leaves", "dropped", "no_match",
         "to_controller", "local", "loop")
_MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")


def asked(s: dict) -> bool:
    """Whether the question asks a flow trace: the Flow tables layer with From or to given."""
    return s.get("layer") == "of" and bool(s.get("src") or s.get("dst"))


# ───────────────────────────────────────────────────────────────────────────── name

def _is_address_or_mac(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return bool(_MAC.match(text.lower()))


def resolve(network: str, text: str, export_read=None) -> dict:
    """Step ``name``: *text* as the trace takes it. ``{"text", "note", "error", "places"}``: an
    address or MAC as given; a NAME looked up among NetBox's end hosts in *network*'s committed
    NSOT export and given as its interface's MAC, *note* naming the source; *error* when the
    name answers nothing, naming what was looked in. *export_read* is `export.read`'s answer (a
    test's), read when None."""
    text = str(text or "").strip()
    if not text or _is_address_or_mac(text):
        return {"text": text, "note": "", "error": "", "places": []}
    from modules.nsot import export as X

    head = f"{text!r} is not an IPv4 or IPv6 address or a MAC"
    if export_read is None:
        try:
            export_read = X.read(network)
        except Exception as exc:                        # noqa: BLE001 (said, never a raise)
            export_read = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if not export_read.get("ok"):
        return {"text": text, "note": "", "places": [],
                "error": f"{head}, and no end host can be looked up by name: "
                         f"{export_read.get('error')}"}
    doc = export_read["export"]
    sha = str(export_read.get("sha256") or doc.get("sha256") or "")[:12]
    hosts = X.hosts_of(doc)
    if hosts is None:
        return {"text": text, "note": "", "places": [],
                "error": f"{head}, and {network}'s NSOT export ({sha}) was built before end "
                         "hosts were recorded, so it names none: commit the export again"}
    ports = [p for p in X.host_ports(doc) if p["host"].lower() == text.lower()]
    if not ports:
        return {"text": text, "note": "", "places": [],
                "error": f"{head}, and {network}'s NSOT export ({sha}) names no end host "
                         f"{text!r} ({len(hosts)} end host{'s' if len(hosts) != 1 else ''} "
                         "recorded)"}
    named = ports[0]["host"]
    with_mac = [p for p in ports if p["mac"]]
    if not with_mac:
        return {"text": text, "note": "", "places": [],
                "error": f"NetBox's end host {named} (the NSOT export {sha}) records no MAC on "
                         f"{', '.join(p['interface'] for p in ports)}, so the controller's "
                         "hosts cannot be matched to it"}
    if len({p["mac"] for p in with_mac}) > 1:
        return {"text": text, "note": "", "error": (
            f"NetBox's end host {named} (the NSOT export {sha}) has "
            f"{len(with_mac)} interfaces with a MAC: "
            + " and ".join(f"{p['interface']} {p['mac']}" for p in with_mac)
            + ": give the one to trace"),
            "places": [{"mac": p["mac"], "words": f"{named} {p['interface']} ({p['mac']})"}
                       for p in with_mac]}
    p = with_mac[0]
    where = (f", cabled to {p['switch']} {p['switch_interface']}" if p.get("switch") else "")
    return {"text": p["mac"], "places": [], "error": "",
            "note": f"{named} is {p['mac']} ({p['interface']}{where}) by NetBox's end hosts, "
                    f"in the NSOT export {sha}"}


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


def _switch_words(h: dict) -> str:
    return h.get("name") or h["dpid_hex"]


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
        out.append(dict(drawn, n=i + 1, switch=_switch_words(h), flows_drawn=flows,
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
        cls = ENDINGS[b["outcome"]][2]
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
    hops = _hops(b, links, names, dst_words)
    chip, kind, cls, _heading = ENDINGS[b["outcome"]]
    if b["outcome"] == "dropped" and "sends it nowhere" in b["words"]:
        chip = "dropped by a flow"
    last = hops[-1] if hops else {}
    return {"outcome": b["outcome"], "words": b["words"], "chip": chip, "kind": kind,
            "cls": cls, "hops": hops, "fold": _folded(hops),
            "path": " → ".join(h["switch"] for h in hops), "at": last.get("switch", "")}


def answer(got: dict, s: dict, fab: dict) -> dict:
    """The answer card's fields from `trace.trace`'s *got* (``ok`` True)."""
    from modules.sdn import trace as TR

    controller = next((c for c in fab.get("controllers") or [] if c["name"] == got["controller"]),
                      {"links": {}, "switches": {}})
    links = controller["links"]
    names = {d: sw.get("name") or "" for d, sw in controller["switches"].items()}
    src_words, dst_words = s["src"], s["dst"]
    pkt = got["packet"]
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
        summary = heading if lead["outcome"] in ("to_controller", "leaves", "unknown",
                                                 "not_read", "local") \
            else f"not delivered, {heading}"
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
    src, dst = got["source"], got["destination"]
    v4 = "ipv4_src" in pkt

    def end_words(h, address):
        """A host as the board writes it: the address traced, its MAC, its switch by the name
        it reports (else its DPID) and its port by number and name."""
        from modules.sdn import topology as T
        dpid = int(h["dpid"])
        name = names.get(dpid) or T.switch_key(dpid)
        port = f"port {h['port_no']}" + (f" ({h['port_name']})" if h.get("port_name") else "")
        return f"{address} ({h['mac']}) on {name} {port}"

    from_words = end_words(src, pkt["ipv4_src" if v4 else "ipv6_src"])
    to_words = end_words(dst, pkt["ipv4_dst" if v4 else "ipv6_dst"])
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
            "words": got["words"], "lit": lit(got, primary)}


def _suggestions(fab: dict) -> dict:
    """The first `SUGGESTED` hosts the controllers list, by their first global address, for
    From and to's suggestions (board D, D7): ``{"hosts": [{value, words}], "of": total}``."""
    from modules.sdn import topology as T

    hosts = [h for c in fab.get("controllers") or [] for h in c["hosts"]]
    out = []
    for h in hosts[:SUGGESTED]:
        value = T.host_label(h) if not T.host_label(h).startswith("host on ") else h["mac"]
        port = h.get("port_name") or f"port {h['port_no']}"
        out.append({"value": value,
                    "words": f"{T.switch_key(h['dpid'])} {port} · {h['mac']}"})
    return {"hosts": out, "of": len(hosts)}


def view(network: str, s: dict, cached=None, now: float = None, export_read=None) -> dict:
    """Everything the Flow tables layer draws for *network* and the question *s* (Topology's
    `ask`): ``{"state": "form" | "refused" | "failed" | "ok", ...}``. *cached* and *now* are
    the stored value and the clock (a test's); read once from the store when None."""
    from modules import reader_job
    from modules.readers import sdn_controllers as R
    from modules.sdn import trace as TR

    out = {"state": "form", "notes": [], "suggest": {"hosts": [], "of": 0}, "read_at": "",
           "controller": ""}
    try:
        got_store = cached if cached is not None else reader_job.read_cached_for(
            R.READER_NAME, network)
        fab = TR.fabric(network, cached=got_store, now=now)
        out["suggest"] = _suggestions(fab)
        if fab.get("controllers"):
            c = fab["controllers"][0]
            out.update(read_at=c.get("read_at", ""), controller=c.get("name", ""),
                       current=c.get("state") == "read")
        if not asked(s):
            return out
        ends = {}
        for end, key in (("source", "src"), ("destination", "dst")):
            if not s.get(key):
                out.update(state="refused", end=end, places=[],
                           error=f"{'From' if end == 'source' else 'to'} is empty: give the "
                                 f"{end} host's IPv4 or IPv6 address, MAC or name")
                return out
            r = resolve(network, s[key], export_read)
            if r["error"]:
                out.update(state="refused", error=r["error"], end=end,
                           places=r["places"])
                return out
            if r["note"]:
                out["notes"].append(r["note"])
            ends[end] = r["text"]
        port = s.get("dport") if s.get("proto") in ("tcp", "udp") else None
        got = TR.trace(network, ends["source"], ends["destination"],
                       protocol=s.get("proto") or "icmp", port=port, cached=got_store, now=now)
        if not got["ok"]:
            out.update(state="refused", error=got["error"], end=got.get("end", ""),
                       places=[{"mac": p["mac"], "words": p["words"]}
                               for p in got.get("places") or []])
            return out
        out.update(answer(got, s, fab))
        return out
    except Exception as exc:                            # noqa: BLE001 (drawn, never a 500)
        log.exception("the SDN trace of %s failed", network)
        out.update(state="failed", error=f"{type(exc).__name__}: {exc}")
        return out
