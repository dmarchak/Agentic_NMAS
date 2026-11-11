"""The SDN trace (the final SDN lab's A5, C1911): where a packet from one host goes through an
OpenFlow fabric, walked through the flow tables its controller reported, switch by switch, each
hop's datapath id with the port it came in by and the port it left by.

**What it reads, and only that.** The SDN reader's stored value (`readers/sdn_controllers.py`:
per controller its topology, the switches with their ports, the links it discovered and the
hosts it learned, and per switch its whole flow table), read once per trace through
`reader_job.read_cached_for`, the topology shaped by `topology.stored`, which also judges the
read's age. It asks no controller and no switch, writes nothing, and its work is the hops it
walks times each table's flows: no per-device read per request (CLAUDE.md, "Enterprise
scale"). The flows are those of the last read, so a controller that installs flows only when
a packet arrives (a reactive application) shows the packet sent to it: that is what the tables
held, said so, never guessed past.

**The walk is OpenFlow 1.3.5's** (the Open Networking Foundation, OpenFlow Switch
Specification 1.3.5,
https://opennetworking.org/wp-content/uploads/2014/10/openflow-switch-v1.3.5.pdf, read
2026-11-05):
- a packet starts at table 0 and goes only forward (5.1); in each table the highest-priority
  flow that matches it is taken, and two matching at that priority leave which applies
  "explicitly undefined" (5.3), so their effect is said only when their actions agree;
- with no flow matching and no table-miss entry, the packet is dropped "by default" (5.4);
- a flow's instructions run in the order meter, apply-actions (in their list's order), clear,
  write-actions, write-metadata, goto-table (5.9); without a goto the action set runs, its
  output last, and with no output in it the packet is dropped (5.10);
- a packet goes back out the port it came in only by the reserved port IN_PORT (4.5; appendix
  B: "It is now forbidden unless the output port is explicitly set to OFPP_IN_PORT"); ALL is
  every standard port but the ingress port, and FLOOD is the switch's own flooding, "in general"
  the same (4.5), each taken as the ports the controller lists for the switch.

**Ryu's spellings are its driver's** (`drivers/ryu.py`): matches in OXM names, actions and
instructions in one list in the switch's order. One more is answered here: Ryu writes a match
on a tagged VLAN as the bare id (`ryu/lib/ofctl_utils.py` `match_vid_to_str`, which drops the
present bit, and `to_match_vid`, which adds it back to a decimal; read from
https://raw.githubusercontent.com/faucetsdn/ryu/master/ryu/lib/ofctl_utils.py, 2026-11-05),
and the driver reads it as an integer, so an integer `vlan_vid` is a tagged id (OFPVID_PRESENT
set) and a text one (`0x0000`, `0x1000/0x1000`) is read as its bits. The packet is untagged
(OFPVID_NONE).

**Matching is `flow_intent`'s** (one owner of what a match takes: its bits, its masks, its
prerequisites implied): a flow matches the packet when its match covers the packet's exact
values. A flow naming a field the packet's protocol lacks (a TCP port on an ICMP packet) does
not match it; one naming a field the trace does not model, though the packet could carry it
(`tunnel_id`, IPv6's extension headers), makes the table's answer "cannot tell", as does any
action it does not model (a group, NORMAL, a VLAN, MPLS or PBB push or pop, an action the
driver could not read).

**Never let a wrong thing look like a working thing.** Every branch ends in one named outcome
(`OUTCOMES`), with the flow that decided it: delivered to the destination's port; left by
another host's port, or by a port with no link or host listed; sent to the controller; to the
switch's local port; dropped (by a flow, by the table's default, by a port that is not there,
or back out its ingress port); a loop; or cannot tell, naming why. A table that could not be
read, or a read older than its promise, is said, never walked as current.

**IPv4 and IPv6 alike** (CLAUDE.md, IPv6 parity): the hosts are found by either family's
address or by MAC, and the packet is ICMPv4's or ICMPv6's echo request, or TCP or UDP to a
port, in the addresses' own family. ARP and IPv6 neighbour discovery are not traced: a
packet's destination MAC is the controller's host table's, as if already resolved.

**The ends are `known.resolve`'s** (`modules/sdn/known.py`, C3013): a host a controller lists,
by address or MAC; with NetBox's view handed in (*netbox*, the committed NSOT export's), also
by its NetBox NAME or a NetBox address, matched to the controller's host by its interface's
MAC, or, where the controller has learnt none, placed where NetBox cables it, said so.
**A destination that is only an address** (one no controller and no NetBox interface holds)
is traced too: the packet is the source's, to that address, and the walk says how it ends: a
flow drops it, the table-miss takes it (to the controller, or dropped, as the table says), it
leaves by a port with nothing listed behind it, or it reaches a host a controller lists.
Nobody knows that address's MAC, and the answer says what was assumed (`ASSUMED`): the
packet carries `known.UNKNOWN_MAC`, so a flow that names a destination MAC does not take it.
A real host would first ask for the address (ARP, or IPv6 neighbour discovery), and where the
address is beyond a gateway it would send the packet to the gateway's MAC: neither is traced.
"""

import collections
import ipaddress
import json
import logging
import re

log = logging.getLogger(__name__)

#: How a branch ends.
OUTCOMES = ("delivered", "elsewhere", "to_host", "leaves", "to_controller", "local", "dropped",
            "no_match", "loop", "unknown", "not_read")
#: How a branch ends, each a state of its own (`ending`): an outcome, with a drop said by
#: what dropped it and the controller said by whether the table-miss sent it there.
ENDINGS = {"delivered": "Delivered", "elsewhere": "Sent to another host's port",
           "to_host": "Reaches a listed host", "leaves": "Leaves the fabric",
           "table_miss_controller": "Table-miss, sent to the controller",
           "to_controller": "Sent to the controller", "local": "Sent to the switch itself",
           "dropped_by_flow": "Dropped by a flow",
           "table_miss_dropped": "Table-miss, dropped", "dropped": "Dropped",
           "loop": "A loop", "unknown": "Cannot tell", "not_read": "Cannot tell"}
#: What an address-only destination's answer says was assumed ({address}, {mac} and {netbox}
#: filled in: *netbox* says NetBox holds none either, only where its view was read).
ASSUMED = ("no controller lists a host with {address}{netbox}, so its MAC is "
           "not known: the packet is traced with the destination MAC {mac} (the \"not known\" "
           "value an ARP request carries), which a flow naming a destination MAC does not "
           "take. A host would first ask for the address (ARP, or IPv6 neighbour discovery), "
           "and would send a packet for an address beyond its gateway to the gateway's MAC: "
           "neither is traced")
#: The answer's state, leading with what to act on.
STATES = ("delivered", "not_delivered", "cannot_tell")
#: The outcomes that leave the trace unable to say where the packet went.
UNSURE = frozenset({"unknown", "not_read"})
PROTOCOLS = ("icmp", "tcp", "udp")
#: The most branches an answer carries; past it they are counted, never drawn. A unicast path
#: is one branch; a flood is one per port it leaves by, so a large fabric's flood is counted.
MAX_BRANCHES = 256
#: The source port of a TCP or UDP packet: the first of IANA's dynamic ports (RFC 6335 6).
SOURCE_PORT = 49152
OFPVID_PRESENT = 0x1000
OFPVID_NONE = 0x0000
#: Ports a flood or ALL never leaves by (OpenFlow 1.3.5 4.5: standard ports only).
_RESERVED_LISTED = frozenset({"LOCAL"})
#: Actions that change nothing the walk follows: TTLs and queues (a TTL is not modelled; a
#: packet whose TTL runs out is not said dropped), each said on its hop.
_NOTED = {"DEC_NW_TTL": "decrements the IP TTL", "SET_NW_TTL": "sets the IP TTL",
          "COPY_TTL_OUT": "copies the TTL outwards", "COPY_TTL_IN": "copies the TTL inwards",
          "SET_QUEUE": "sets a queue"}
#: Actions the walk does not model: the table's answer is "cannot tell".
_NOT_MODELLED = {"GROUP": "sends it to a group, whose buckets the trace does not read",
                 "PUSH_VLAN": "pushes a VLAN tag", "POP_VLAN": "pops a VLAN tag",
                 "PUSH_MPLS": "pushes an MPLS label", "POP_MPLS": "pops an MPLS label",
                 "PUSH_PBB": "pushes a PBB tag", "POP_PBB": "pops a PBB tag",
                 "DEC_MPLS_TTL": "decrements an MPLS TTL", "SET_MPLS_TTL": "sets an MPLS TTL"}
_MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
#: The fields a switch's pipeline sets on arrival and that never leave it (OpenFlow 1.3.5,
#: section 7.2.3's pipeline fields: in_port, in_phy_port and metadata, not the packet's headers).
_PIPELINE = frozenset({"in_port", "in_phy_port", "metadata"})


class Refused(ValueError):
    """A trace that cannot start, in words naming what it compared. *places* are the hosts an
    end was found at when it was found at more than one (each with its ``mac`` and its
    ``words``, `known.resolve`'s), so a screen can offer each one's MAC; *end* is which end
    they answer (``source`` or ``destination``)."""

    def __init__(self, words, places=(), end=""):
        super().__init__(words)
        self.places, self.end = list(places), end


# ───────────────────────────────────────────────────────────────────────────── the fabric

def fabric(network: str, cached=None, now: float = None) -> dict:
    """The stored fabric of *network*: ``{"state", "why", "controllers"}``, *state* as
    `topology.stored`'s. Each controller ``{"name", "label", "state", "why", "read_at",
    "switches": {dpid: {"name", "ports": {port_no: name} or None, "flows": [...] or None,
    "why"}}, "links": {(dpid, port): (dpid, port)}, "hosts": [edge host]}``; a switch's
    *flows* is None when its table was not read whole, *why* saying so. *cached* is
    `reader_job.read_cached_for`'s answer (a test's), read from the store when None."""
    from modules import reader_job
    from modules.readers import sdn_controllers as R
    from modules.sdn import topology as T

    got = cached if cached is not None else reader_job.read_cached_for(R.READER_NAME, network)
    topo = T.stored(network, now=now, cached=got)
    if topo["state"] != "read":
        return {"state": topo["state"], "why": topo["why"], "controllers": []}
    value = ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
    raw = {c.get("name"): c for c in value.get("controllers") or []}
    out = []
    for c in topo["controllers"]:
        if c["state"] == "not_declared":
            continue
        switches = {}
        for sw in c.get("switches") or []:
            dpid = int(sw["dpid"])
            switches[dpid] = {"name": c["names"].get(dpid, ""),
                              "ports": {p["port_no"]: p.get("name", "")
                                        for p in sw.get("ports") or []},
                              "flows": None,
                              "why": "the controller's flow read does not list this switch"}
        for s in (raw.get(c["name"]) or {}).get("switches") or []:
            dpid = int(s["dpid"])
            entry = switches.setdefault(dpid, {
                "name": "", "ports": None, "flows": None, "why": ""})
            entry["name"] = entry["name"] or s.get("name") or ""
            if s.get("active_flows") is None:
                entry["why"] = ("its flow table could not be read: "
                                f"{s.get('error') or 'no answer'}")
            else:
                entry.update(flows=list(s.get("flows") or []), why="")
        links = {}
        for l in c.get("links") or []:
            links[(int(l["src"]["dpid"]), l["src"]["port_no"])] = \
                (int(l["dst"]["dpid"]), l["dst"]["port_no"])
        hosts = [h for h in T.placed(c)[0]
                 if (int(h["dpid"]), h["port_no"]) not in links]
        out.append({"name": c["name"], "label": c.get("label", ""), "state": c["state"],
                    "why": c.get("why", ""), "read_at": c.get("read_at", ""),
                    "hosts_note": c.get("hosts_note", ""), "switches": switches,
                    "links": links, "hosts": hosts})
    return {"state": "read", "why": "", "controllers": out}


# ───────────────────────────────────────────────────────────────────────────── the ends

def _address(text: str):
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def host_words(h: dict) -> str:
    """A host as a person names it: its first global address, else its MAC, and where."""
    from modules.sdn import topology as T

    named = next((a for a in list(h.get("ipv4") or []) + list(h.get("ipv6") or [])
                  if T.is_global(a)), h.get("mac", ""))
    port = h.get("port_name") or f"port {h['port_no']}"
    return f"{named} ({h.get('mac', '')}) on {T.switch_key(h['dpid'])} {port}"


def _family_address(h: dict, version: int, text: str):
    from modules.sdn import topology as T

    if _address(text) is not None:
        return str(_address(text))
    key = "ipv4" if version == 4 else "ipv6"
    for a in h.get(key) or []:
        if T.is_global(a):
            return str(ipaddress.ip_address(a))
    return None


def packet_of(src: dict, dst: dict, src_text: str, dst_text: str, protocol: str = "icmp",
              port=None) -> dict:
    """The packet traced from host *src* to *dst* (each `known.resolve`'s end; *dst* a host, or
    an address-only destination, whose MAC is `known.UNKNOWN_MAC`), as the exact values of the
    fields a flow may match, untagged. Its family is the one the addresses given name (both
    must agree), else IPv4 where both ends have one, else IPv6. Raises `Refused`."""
    from modules.sdn.known import end_words
    protocol = str(protocol or "icmp").strip().lower()
    if protocol not in PROTOCOLS:
        raise Refused(f"the protocol is one of {', '.join(PROTOCOLS)}, not {protocol!r}")
    if protocol == "icmp" and port not in (None, ""):
        raise Refused(f"an ICMP echo has no port, and {port!r} was given")
    if protocol != "icmp":
        try:
            port = int(str(port).strip())
        except ValueError:
            raise Refused(f"a {protocol.upper()} trace needs its destination port, from 1 to "
                          f"65535, not {port!r}") from None
        if not 1 <= port <= 65535:
            raise Refused(f"a {protocol.upper()} port is from 1 to 65535, not {port}")
    given = [a.version for a in (_address(src_text), _address(dst_text)) if a is not None]
    if len(set(given)) > 1:
        raise Refused(f"the source {src_text} is IPv{given[0]} and the destination {dst_text} "
                      f"is IPv{given[1]}: a packet has one family")
    versions = given[:1] or [v for v in (4, 6)
                             if _family_address(src, v, "") and _family_address(dst, v, "")][:1]
    if not versions:
        raise Refused(f"{end_words(src)} and {end_words(dst)} share no address family the "
                      "controller lists, so no IP packet can be traced between them")
    v = versions[0]
    a, b = _family_address(src, v, src_text), _family_address(dst, v, dst_text)
    for h, got in ((src, a), (dst, b)):
        if got is None:
            who = ("neither the controller nor NetBox lists a" if h.get("netbox_addresses")
                   or h.get("name") else "the controller lists no")
            raise Refused(f"{who} global IPv{v} address for {end_words(h)}")
    pkt = {"eth_src": src["mac"], "eth_dst": dst["mac"], "vlan_vid": OFPVID_NONE,
           "eth_type": 0x0800 if v == 4 else 0x86DD, "ip_dscp": 0, "ip_ecn": 0}
    pkt.update({"ipv4_src": a, "ipv4_dst": b} if v == 4 else
               {"ipv6_src": a, "ipv6_dst": b, "ipv6_flabel": 0})
    if protocol == "icmp":
        pkt.update({"ip_proto": 1, "icmpv4_type": 8, "icmpv4_code": 0} if v == 4 else
                   {"ip_proto": 58, "icmpv6_type": 128, "icmpv6_code": 0})
    else:
        number = 6 if protocol == "tcp" else 17
        pkt.update({"ip_proto": number, f"{protocol}_src": SOURCE_PORT,
                    f"{protocol}_dst": port})
    return pkt


# ───────────────────────────────────────────────────────────────────────────── matching

def judge(match: dict, packet: dict) -> tuple:
    """``("yes" | "no" | "cannot", why)``: whether a flow matching *match* takes *packet*. The
    match's prerequisites are implied (`flow_intent._fields`), so a flow on `ipv4_dst` alone
    does not take an IPv6 packet; an untagged packet has no VLAN priority to match."""
    from modules.sdn import flow_intent as FI

    m = dict(match or {})
    vid = m.get("vlan_vid")
    if isinstance(vid, int) and not isinstance(vid, bool):
        m["vlan_vid"] = vid | OFPVID_PRESENT
    try:
        mine = FI._fields(m)
        theirs = {k: FI._bits(k, v) for k, v in packet.items()}
    except FI._CannotTell as exc:
        return "cannot", str(exc)
    cannot = ""
    for k, x in mine.items():
        if k in theirs:
            if not FI._covers(x, theirs[k]):
                return "no", ""
        elif k == "vlan_pcp" and packet.get("vlan_vid") == OFPVID_NONE:
            return "no", ""
        elif not cannot:
            cannot = f"it matches {k}, which the trace does not model"
    return ("cannot", cannot) if cannot else ("yes", "")


def _ref(f: dict) -> str:
    cookie = f.get("cookie") or 0
    return (f"the flow at priority {f.get('priority', 0)} in table {f.get('table_id', 0)} "
            f"(cookie {cookie:#x})" if isinstance(cookie, int) else
            f"the flow at priority {f.get('priority', 0)} in table {f.get('table_id', 0)}")


def is_miss(f: dict) -> bool:
    """Whether flow *f* is its table's table-miss entry: every match field wildcarded and
    priority 0 (OpenFlow 1.3.5 5.4: "identified by its match and its priority")."""
    return not (f.get("match") or {}) and not (f.get("priority") or 0)


def _named(f: dict) -> str:
    """`_ref`'s words, and the flow's evidence id where the read gives it one (a kept
    snapshot's flows carry one; the SDN reader's stored flows do not)."""
    return f"{_ref(f)}, {f['id']}" if f.get("id") else _ref(f)


def _taken(f: dict) -> dict:
    from modules.sdn.flow_intent import action_words

    return {"id": f.get("id", ""), "table_id": f.get("table_id", 0),
            "priority": f.get("priority", 0), "cookie": f.get("cookie", 0),
            "owner": f.get("owner", ""), "match": dict(f.get("match") or {}),
            "actions": list(f.get("actions") or []), "miss": is_miss(f),
            "words": f"{_ref(f)}: {action_words(f.get('actions') or [])}"}


def select(flows: list, table: int, packet: dict) -> tuple:
    """``(flow, None)``: the flow of *table* that takes *packet* (5.3); ``(None, None)`` for a
    table miss with no entry for it; ``(None, why)`` when the table cannot tell."""
    rows = [f for f in flows if (f.get("table_id") or 0) == table]
    by_priority = collections.defaultdict(list)
    for f in rows:
        by_priority[f.get("priority") or 0].append(f)
    for priority in sorted(by_priority, reverse=True):
        yes, cannot = [], []
        for f in by_priority[priority]:
            verdict, why = judge(f.get("match"), packet)
            if verdict == "yes":
                yes.append(f)
            elif verdict == "cannot":
                cannot.append((f, why))
        if cannot:
            f, why = cannot[0]
            return None, f"{_ref(f)} may take it: {why}"
        if yes:
            acts = {json.dumps(f.get("actions") or [], sort_keys=True) for f in yes}
            if len(acts) > 1:
                return None, (f"{len(yes)} flows at priority {priority} in table {table} take "
                              f"it with different actions ({'; '.join(_ref(f) for f in yes)}); "
                              "OpenFlow 1.3.5 5.3 leaves which applies undefined")
            return yes[0], None
    return None, None


# ───────────────────────────────────────────────────────────────────────────── one switch

def _set_field(packet: dict, a: dict):
    """Apply a SET_FIELD to *packet*; the why when the trace cannot."""
    from modules.sdn.flow_intent import _value

    field = a.get("field")
    if field in ("vlan_vid", "vlan_pcp"):
        return f"sets {field}, and the trace does not model VLAN tags"
    packet[field] = _value(field, a.get("value"))
    return ""


def _outputs(port, in_port, ports) -> tuple:
    """``([(port, back), ...], why)``: where an OUTPUT to *port* sends the packet (numbers, or
    CONTROLLER or LOCAL), *back* true for a number naming the ingress port (which OpenFlow does
    not send back out), or why the trace cannot say."""
    if isinstance(port, int) and not isinstance(port, bool):
        return [(port, port == in_port)], ""
    name = str(port).upper()
    if name == "IN_PORT":
        return [(in_port, False)], ""
    if name in ("CONTROLLER", "LOCAL"):
        return [(name, False)], ""
    if name in ("ALL", "FLOOD"):
        if ports is None:
            return [], (f"sends it out {name}, and the controller lists no ports for this "
                        "switch")
        return [(p, False) for p in sorted(p for p in ports
                                           if isinstance(p, int) and p != in_port)], ""
    if name == "NORMAL":
        return [], ("sends it to NORMAL, the switch's own forwarding outside OpenFlow, which no "
                    "flow table shows")
    return [], f"sends it out the reserved port {name}, which the trace does not follow"


def through_switch(sw: dict, in_port, packet: dict) -> dict:
    """One switch's pipeline for *packet* arriving on *in_port*: ``{"flows": [taken],
    "emits": [(port, packet, flow, back)], "notes", "end": None or (outcome, words)}``. The flows
    are those *sw* lists (its table read whole)."""
    flows = sw["flows"]
    pkt = dict(packet, in_port=in_port, in_phy_port=in_port, metadata=0)
    action_set = {}
    taken, emits, notes = [], [], []
    table = 0

    def emit(port, flow, why_prefix=""):
        got, why = _outputs(port, in_port, sw.get("ports"))
        if why:
            return f"{why_prefix}{_ref(flow)} {why}"
        # The packet leaves without its pipeline fields: the next switch sets its own.
        sent = {k: v for k, v in pkt.items() if k not in _PIPELINE}
        for p, back in got:
            emits.append((p, sent, flow, back))
        return ""

    def done(outcome, words, **flags):
        return {"flows": taken, "emits": emits, "notes": notes, "end": (outcome, words),
                "flags": flags}

    while True:
        flow, why = select(flows, table, pkt)
        if why:
            return done("unknown", why)
        if flow is None:
            return done("no_match", f"no flow in table {table} takes it, and with no table-miss "
                                    "entry OpenFlow 1.3.5 5.4 drops it by default", miss=True)
        taken.append(_taken(flow))
        apply, write, clear, metadata, goto = [], None, False, None, None
        for a in flow.get("actions") or []:
            kind = a.get("type")
            if kind == "METER":
                notes.append(f"{_ref(flow)} sends it through meter {a.get('meter_id')}, "
                             "which may drop it by rate")
            elif kind == "GOTO_TABLE":
                goto = a.get("table_id")
            elif kind == "CLEAR_ACTIONS":
                clear = True
            elif kind == "WRITE_ACTIONS":
                write = list(a.get("actions") or [])
            elif kind == "WRITE_METADATA":
                metadata = (a.get("metadata") or 0, a.get("metadata_mask") or 0)
            else:
                apply.append(a)
        for a in apply:
            kind = a.get("type")
            if kind == "OUTPUT":
                why = emit(a.get("port"), flow)
            elif kind == "SET_FIELD":
                why = _set_field(pkt, a)
                why = f"{_ref(flow)} {why}" if why else ""
            elif kind in _NOTED:
                notes.append(f"{_ref(flow)} {_NOTED[kind]}, which the trace does not model")
                why = ""
            else:
                why = f"{_ref(flow)} {_NOT_MODELLED.get(kind) or _unread(a)}"
            if why:
                return done("unknown", why)
        if clear:
            action_set = {}
        for a in write or []:
            key = f"SET_FIELD:{a.get('field')}" if a.get("type") == "SET_FIELD" else a.get("type")
            action_set[key] = (a, flow)
        if metadata is not None:
            value, mask = metadata
            pkt["metadata"] = (pkt["metadata"] & ~mask) | (value & mask)
        if goto is None:
            break
        if not isinstance(goto, int) or goto <= table:
            return done("unknown", f"{_ref(flow)} goes to table {goto}, not one after {table}, "
                                   "which a switch refuses (OpenFlow 1.3.5 5.1)")
        table = goto
    # The action set, in 5.10's order: what the trace cannot model first, then the set-fields,
    # then the output, last.
    for key, (a, flow) in action_set.items():
        kind = a.get("type")
        if kind in _NOT_MODELLED or kind not in ("SET_FIELD", "OUTPUT", *_NOTED):
            return done("unknown", f"{_ref(flow)} writes an action that "
                                   f"{_NOT_MODELLED.get(kind) or _unread(a)}")
    for key, (a, flow) in action_set.items():
        if a.get("type") == "SET_FIELD":
            why = _set_field(pkt, a)
            if why:
                return done("unknown", f"{_ref(flow)} {why}")
    if "OUTPUT" in action_set:
        a, flow = action_set["OUTPUT"]
        why = emit(a.get("port"), flow)
        if why:
            return done("unknown", why)
    if not emits:
        last = taken[-1]
        return done("dropped", f"{_named(last)} sends it nowhere "
                               "(no output), so the switch drops it"
                    + (": the table-miss entry, no flow above it taking the packet"
                       if is_miss(last) else ""), by_flow=True, miss=is_miss(last))
    return {"flows": taken, "emits": emits, "notes": notes, "end": None, "flags": {}}


def _unread(a: dict) -> str:
    return f"carries an action the trace does not model ({a.get('text') or a.get('type')})"


# ───────────────────────────────────────────────────────────────────────────── the walk

def _key(packet: dict) -> str:
    return json.dumps(packet, sort_keys=True, default=str)


def _port_name(sw, port) -> str:
    return str(((sw or {}).get("ports") or {}).get(port, "")) if isinstance(port, int) else ""


def ending(branch: dict) -> str:
    """A branch's ending, one of `ENDINGS`' keys: its outcome, a drop said by what dropped it
    (a flow, or the table's default) and the controller by whether the table-miss entry sent
    the packet there."""
    outcome = branch["outcome"]
    if outcome == "no_match":
        return "table_miss_dropped"
    if outcome == "to_controller":
        return "table_miss_controller" if branch.get("miss") else "to_controller"
    if outcome == "dropped" and branch.get("by_flow"):
        return "table_miss_dropped" if branch.get("miss") else "dropped_by_flow"
    return outcome


def walk(controller: dict, packet: dict, start: tuple, destination: tuple = None) -> dict:
    """The packet's branches from *start* ``(dpid, port)`` through *controller*'s fabric
    (`fabric`'s), *destination* ``(dpid, port)`` the destination host's port, or None for a
    destination that is only an address (no port is its own: a host's port it leaves by is
    ``to_host``): ``{"branches": [{"outcome", "words", "hops": [hop], "miss", "by_flow"}],
    "more": the branches past MAX_BRANCHES}``; *miss* when the table-miss decided (its entry,
    or the default with none), *by_flow* when a flow with no output dropped it. A hop is
    ``{"dpid", "dpid_hex", "name", "in_port", "in_port_name", "out_port", "out_port_name",
    "flows", "notes"}``; the last hop of a branch that ends inside a switch has no out port.
    A (switch, port, packet) reached twice is a loop."""
    from modules.sdn.drivers.base import dpid_hex

    switches, links = controller["switches"], controller["links"]
    at = collections.defaultdict(list)
    for h in controller["hosts"]:
        at[(int(h["dpid"]), h["port_no"])].append(h)
    branches, more = [], 0
    seen = set()
    queue = collections.deque([(start[0], start[1], packet, [])])

    def end(hops, outcome, words, miss=False, by_flow=False):
        nonlocal more
        if len(branches) >= MAX_BRANCHES:
            more += 1
            return
        branches.append({"outcome": outcome, "words": words, "hops": hops, "miss": bool(miss),
                         "by_flow": bool(by_flow)})

    while queue:
        dpid, in_port, pkt, hops = queue.popleft()
        sw = switches.get(dpid)
        hop = {"dpid": dpid, "dpid_hex": dpid_hex(dpid), "name": (sw or {}).get("name", ""),
               "in_port": in_port, "in_port_name": _port_name(sw, in_port),
               "out_port": None, "out_port_name": "", "flows": [], "notes": []}
        where = f"{dpid_hex(dpid)} port {in_port}"
        key = (dpid, in_port, _key(pkt))
        if key in seen:
            end(hops + [hop], "loop", f"it reaches {where} a second time, unchanged: the flows "
                                      "forward it in a loop")
            continue
        seen.add(key)
        if sw is None or sw["flows"] is None:
            why = (sw or {}).get("why") or "the controller's read does not list this switch"
            end(hops + [hop], "not_read", f"it reaches {where}, and {why}")
            continue
        got = through_switch(sw, in_port, pkt)
        hop.update(flows=got["flows"], notes=got["notes"])
        if got["end"]:
            end(hops + [hop], *got["end"], **got.get("flags") or {})
        for port, out_pkt, flow, back in got["emits"]:
            h = dict(hop, out_port=port, out_port_name=_port_name(sw, port))
            path = hops + [h]
            out = f"{dpid_hex(dpid)} port {port}"
            if port == "CONTROLLER":
                miss = is_miss(flow)
                end(path, "to_controller",
                    (f"no flow of {dpid_hex(dpid)} names this packet: its table-miss entry "
                     f"(priority 0, every field wildcarded, table {flow.get('table_id', 0)}) "
                     "sends it to the controller, which " if miss else
                     f"{dpid_hex(dpid)} sends it to the controller, which ")
                    + "decides what to do with it (and may install a flow for it): the trace "
                      "follows no packet the controller handles", miss=miss)
            elif port == "LOCAL":
                end(path, "local", f"{dpid_hex(dpid)} sends it to its own local port")
            elif back:
                end(path, "dropped", f"{out} is the port it came in by, and OpenFlow sends a "
                                     "packet back out its ingress port only by IN_PORT")
            elif destination is not None and (dpid, port) == tuple(destination):
                end(path, "delivered", f"{out} is the destination's port")
            elif (dpid, port) in links:
                nxt = links[(dpid, port)]
                queue.append((nxt[0], nxt[1], out_pkt, path))
            elif sw.get("ports") is not None and port not in sw["ports"]:
                end(path, "dropped", f"{out} is not a port the controller lists for the switch, "
                                     "and an output to a port that does not exist is dropped "
                                     "(OpenFlow 1.3.5 5.10)")
            elif at.get((dpid, port)) and destination is None:
                end(path, "to_host", f"it leaves by {out}, where the controller lists "
                                     + " and ".join(host_words(x) for x in at[(dpid, port)])
                                     + ": the flows carry it to that host's port, though no "
                                       "controller lists the destination address there")
            elif at.get((dpid, port)):
                end(path, "elsewhere", f"it leaves by {out}, where the controller lists "
                                       + " and ".join(host_words(x) for x in at[(dpid, port)])
                                       + ", not the destination")
            else:
                end(path, "leaves", f"it leaves the fabric by {out}, where the controller lists "
                                    "no link and no host")
    return {"branches": branches, "more": more}


# ───────────────────────────────────────────────────────────────────────────── the answer

def _hops_words(hops: list) -> str:
    return " → ".join(f"{h['dpid_hex']} (in {h['in_port']}"
                      + (f", out {h['out_port']})" if h["out_port"] is not None else ")")
                      for h in hops)


def trace(network: str, source: str, destination: str, *, protocol: str = "icmp", port=None,
          cached=None, now: float = None, netbox: dict = None) -> dict:
    """Where a packet from *source* to *destination* goes through *network*'s OpenFlow fabric,
    from the stored read. Each end is an IPv4 or IPv6 address or a MAC a controller lists as a
    host, or, with NetBox's view handed in (*netbox*, `known.read`'s), a NetBox name or
    address; a destination may also be an address nothing lists (the module's "A destination
    that is only an address"). ``{"ok", "error", "state" (one of `STATES`), "words",
    "controller", "read_at", "current", "read_why", "source", "destination", "packet",
    "branches", "more", "dpids", "ending", "address_only", "assumed", "notes"}``; *dpids* the
    delivered branch's switches in order; *ending* the leading branch's (`ending`); *assumed*
    what an address-only destination's packet assumes, in words; *notes* how a name or a NetBox
    address was resolved. A refusal is ``ok`` False with *error* naming why. Read-only: it asks
    no controller and writes nothing."""
    return over(fabric(network, cached=cached, now=now), network, source, destination,
                protocol=protocol, port=port, netbox=netbox)


def over(fab: dict, network: str, source: str, destination: str, *, protocol: str = "icmp",
         port=None, netbox: dict = None) -> dict:
    """`trace`'s answer over a fabric already in `fabric`'s shape: the stored read's
    (`trace`), or a kept snapshot's (`modules/ai/sdn_analyst_tools.sealed_fabric`, B4's trace
    tool, which never reads anything live). One walk and one answer for both. *netbox* is
    NetBox's view (`known.read`'s shape), else the fabric's own ``netbox`` (a kept snapshot's),
    else none."""
    from modules.sdn import known

    nb = netbox if netbox is not None else fab.get("netbox")
    names = known.labels_of(fab.get("controllers"), nb)
    try:
        if fab["state"] != "read":
            raise Refused(f"the controller's topology is not read: {fab['why']}")
        if not fab["controllers"]:
            raise Refused("no controller connection of this network reads a topology")
        try:
            src = known.resolve(fab["controllers"], source, nb, "source")
        except Refused as exc:
            raise Refused(str(exc), exc.places, "source") from None
        try:
            dst = known.resolve(fab["controllers"], destination, nb, "destination")
        except Refused as exc:
            raise Refused(str(exc), exc.places, "destination") from None
        sc = next(c for c in fab["controllers"] if c["name"] == src["controller"])
        lone = bool(dst.get("address_only"))
        if not lone and src["controller"] != dst["controller"]:
            raise Refused(f"the source is on {src['controller']}'s fabric and the destination "
                          f"on {dst['controller']}'s: a trace stays inside one controller's "
                          "fabric")
        if not lone and (src["mac"], src["dpid"], src["port_no"]) == (
                dst["mac"], dst["dpid"], dst["port_no"]):
            raise Refused("the source and the destination are the same host, "
                          f"{known.end_words(src, names)}")
        pkt = packet_of(src, dst, source, destination, protocol, port)
    except Refused as exc:
        return {"ok": False, "error": str(exc), "state": "", "branches": [],
                "places": [{"mac": p["mac"], "words": p["words"]} for p in exc.places],
                "end": exc.end}
    got = walk(sc, pkt, (int(src["dpid"]), src["port_no"]),
               None if lone else (int(dst["dpid"]), dst["port_no"]))
    branches = got["branches"]
    outcomes = [b["outcome"] for b in branches]
    delivered = [b for b in branches if b["outcome"] == "delivered"]
    lead = None
    if lone:
        # No port is the destination's: the answer leads with how the packet ends, the first
        # branch the trace cannot follow before any it can (never a known ending over a doubt).
        unsure = got["more"] or any(o in UNSURE for o in outcomes)
        state = "cannot_tell" if unsure else "not_delivered"
        lead = next((b for b in branches if b["outcome"] in UNSURE), None) if unsure else None
        lead = lead or (branches[0] if branches else None)
        if lead is None:
            words = f"Cannot tell: {got['more']} branches past the {MAX_BRANCHES} drawn"
        else:
            words = f"{ENDINGS[ending(lead)]}: {lead['words']} ({_hops_words(lead['hops'])})"
            others = len(branches) - 1 + got["more"]
            if others:
                words += f"; and {others} other cop{'y' if others == 1 else 'ies'} of it"
    elif delivered:
        state = "delivered"
        b = delivered[0]
        words = f"Delivered: {_hops_words(b['hops'])}"
        others = len(branches) - 1 + got["more"]
        if others:
            words += f"; and {others} other cop{'y' if others == 1 else 'ies'} of it"
        unsure = sum(1 for o in outcomes if o in UNSURE) + got["more"]
        if unsure:
            words += f", {unsure} of which the trace cannot follow"
    elif got["more"] or any(o in UNSURE for o in outcomes):
        state = "cannot_tell"
        b = next((b for b in branches if b["outcome"] in UNSURE), branches[0] if branches
                 else None)
        words = "Cannot tell: " + (f"{b['words']} ({_hops_words(b['hops'])})" if b else
                                   f"{got['more']} branches past the {MAX_BRANCHES} drawn")
    else:
        state = "not_delivered"
        b = branches[0]
        words = f"Not delivered: {b['words']} ({_hops_words(b['hops'])})"
    if not lone:
        lead = b
    current = sc["state"] == "read"
    if not current:
        words += f" (as last read at {sc['read_at'] or 'an unknown time'}: {sc['why']})"
    assumed = ASSUMED.format(
        address=dst["address"], mac=dst["mac"],
        netbox=(" and NetBox records no interface with it"
                if (nb or {}).get("state") == "read" else "")) if lone else ""
    return {"ok": True, "error": "", "state": state, "words": words, "network": network,
            "controller": sc["name"], "read_at": sc["read_at"], "current": current,
            "read_why": sc["why"], "source": dict(src, words=known.end_words(src, names)),
            "destination": dict(dst, words=known.end_words(dst, names)), "packet": pkt,
            "branches": branches, "more": got["more"],
            "ending": ending(lead) if lead else "unknown", "address_only": lone,
            "assumed": assumed, "notes": [e["note"] for e in (src, dst) if e.get("note")],
            "dpids": [h["dpid_hex"] for h in delivered[0]["hops"]] if delivered else []}
