"""fabric_forwarding's logic over plain data, apart from Ryu (v0; the SDN platform design revision
6, section 14, "Forwarding + L3 failover"): what the app wants on every switch, given the
topology, the hosts and its config, and the difference against what a switch holds. Nothing
here sends, reads a switch or keeps time of its own (the caller passes `now`), so all of it is
tested without a controller. Python 3.5 (C2646): no f-strings, no variable annotations, and
nothing that depends on a dict's order (3.5's dicts have none): every answer is sorted.

**The flows, each tagged with the app's cookie** (`COOKIE_PREFIX` under `COOKIE_MASK`, the
manifest's `owns_flows`; the low bits name the kind):
- in each switch's PUNT table: the table miss to the controller (`MISS`, priority 0), and ARP
  to the controller (`ARP`, priority 10);
- when the FORWARD table is another table: its IPv4 and IPv6 miss going on to the punt table
  (`GOTO`, priority 0, matching `eth_type`, since a hardware table may take only a match that
  carries it: the ProCurve's table 100, C2601);
- per known host address, in the forward table, priority 100, matching `eth_type` and the
  destination address only (no MAC field: the ProCurve's hardware table takes none): at the
  host's own switch, out of the host's port (`DELIVER`); at every other switch that reaches it,
  out of the next hop's port on the shortest path (`TRANSIT`).

The tables are the network's, never the app's: the config names each switch's forward and punt
tables (Mercury compiles them from the switch's platform profile, the design's section 12, "the
compile step"); a switch the config names no tables for is NOT SERVED: nothing is installed or
removed there, and the app's `/health` names it.

**Loop safety (the ring).** No flow the app installs floods: a broadcast, a multicast or a
frame for an unknown destination goes to the controller, which relays it out of EDGE ports only
(`edge_ports`: up, on no link either end has reported, and up for the settle time), once per
frame (`Recent`), and only when it arrived on an edge port. So a broadcast never enters a ring
link, whatever the ring's shape, and a port misread as an edge while discovery runs relays a
frame at most once. Unicast follows shortest paths only, and a set of next hops that loops is
refused before it is installed (`forwarding_loop`).

**Reconcile** (`difference`): against a switch's flows as read, only the app's own cookie is
added to or removed; a flow of another owner with the same table, priority and match is a
CONFLICT, named and never overwritten.
"""

import ipaddress

from fabric_paths import shortest_path

#: The app's cookie (the manifest's owns_flows: "0x4646000000000000" under
#: "0xffff000000000000"); the low bits carry the flow's kind.
COOKIE_PREFIX = 0x4646000000000000
COOKIE_MASK = 0xffff000000000000
MISS, ARP, GOTO, DELIVER, TRANSIT = 1, 2, 3, 4, 5
KINDS = {MISS: "miss", ARP: "arp", GOTO: "goto", DELIVER: "deliver", TRANSIT: "transit"}
#: Each kind's priority.
PRIORITY = {MISS: 0, ARP: 10, GOTO: 0, DELIVER: 100, TRANSIT: 100}
ETH_IPV4, ETH_IPV6, ETH_ARP, ETH_LLDP = 0x0800, 0x86dd, 0x0806, 0x88cc
#: An action, as the app compares them: ("OUTPUT", port), ("GOTO", table) or ("CONTROLLER",).
CONTROLLER = ("CONTROLLER",)
#: The config's fields: each switch's tables, by datapath id in decimal.
TABLE_FIELDS = ("forward_table", "punt_table")
MAX_TABLE = 254
DEFAULTS = {"settle_s": 3.0, "dedup_s": 0.5}
LIMITS = {"settle_s": (0.0, 60.0), "dedup_s": (0.0, 10.0)}


def cookie(kind):
    return COOKIE_PREFIX | kind


def is_ours(value):
    return (value & COOKIE_MASK) == COOKIE_PREFIX


def handles_packet_in(cookie_value):
    """Whether a packet-in is this app's to handle: only one its OWN flow sent (its punt
    table's miss or ARP flow), never one another app's flow raised. dns_blacklist's steering
    flows send DNS to the controller under their own cookie, and forwarding those queries too
    would race the blacklist's answer (Lab 9 Objective 3). OpenFlow 1.3 puts the cookie of the
    entry that sent the packet in the packet-in (all ones when no entry did, which is no one's);
    a packet-in with no cookie at all is not handled."""
    if not isinstance(cookie_value, int) or isinstance(cookie_value, bool):
        return False
    return is_ours(cookie_value)


def kind_of(value):
    return value & ~COOKIE_MASK if is_ours(value) else None


# ── the config ──────────────────────────────────────────────────────────────────────────────

def _table_problem(where, value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_TABLE:
        return "%s is a table id, 0 to %d, not %r" % (where, MAX_TABLE, value)
    return ""


def _tables(where, value, problems):
    if not isinstance(value, dict):
        problems.append("%s is a mapping of %s, not %r" % (where, " and ".join(TABLE_FIELDS),
                                                           value))
        return None
    extra = sorted(k for k in value if k not in TABLE_FIELDS)
    if extra:
        problems.append("%s takes %s, not %s" % (where, " and ".join(TABLE_FIELDS),
                                                 ", ".join(repr(k) for k in extra)))
    out = []
    for field in TABLE_FIELDS:
        if field not in value:
            problems.append("%s names no %s" % (where, field))
            return None
        why = _table_problem("%s.%s" % (where, field), value[field])
        if why:
            problems.append(why)
            return None
        out.append(value[field])
    return tuple(out)


def parse_config(data):
    """`(config, problems)`: *data* (the pushed JSON) as the app keeps it, `{"switches": {dpid:
    (forward, punt)}, "default_tables": (forward, punt) or None, "settle_s", "dedup_s"}`, or
    None with one line per field refused, each naming the field, the value and the rule."""
    problems = []
    if not isinstance(data, dict):
        return None, ["the config is a JSON object, not %r" % (data,)]
    known = ("switches", "default_tables") + tuple(sorted(DEFAULTS))
    extra = sorted(k for k in data if k not in known)
    if extra:
        problems.append("the config takes %s, not %s" % (", ".join(known),
                                                         ", ".join(repr(k) for k in extra)))
    switches = {}
    raw = data.get("switches", {})
    if not isinstance(raw, dict):
        problems.append("switches is a mapping of datapath ids to tables, not %r" % (raw,))
        raw = {}
    for key in sorted(raw):
        if not (isinstance(key, str) and key.isdigit()):
            problems.append("switches: %r is not a datapath id in decimal" % (key,))
            continue
        tables = _tables("switches.%s" % key, raw[key], problems)
        if tables is not None:
            switches[int(key)] = tables
    default = None
    if data.get("default_tables") is not None:
        default = _tables("default_tables", data["default_tables"], problems)
    out = {"switches": switches, "default_tables": default}
    for field in sorted(DEFAULTS):
        value = data.get(field, DEFAULTS[field])
        low, high = LIMITS[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not low <= value <= high:
            problems.append("%s is seconds, %g to %g, not %r" % (field, low, high, value))
            continue
        out[field] = float(value)
    if problems:
        return None, problems
    return out, []


#: What the app says when the app SDK is not on its import path (C2729).
NO_SDK = ("the app SDK mercury_app is not importable on this controller, so the start-time "
          "config Mercury staged cannot be read")


def from_start_config(answer):
    """`(config, why)`: the app's config from *answer*, what `mercury_app.start_config` gave at
    load (None when the SDK could not be imported), as `parse_config` keeps it, with why ""; or
    None and why in words: the SDK absent, the file absent or unreadable (the SDK's own words),
    or a config `parse_config` refuses (each field it named). The app's /health names *why*
    until a config is in force, so a missing file is never an ok (C2729)."""
    if answer is None:
        return None, NO_SDK
    if not answer.get("ok"):
        return None, "its start-time config was not read: %s" % (answer.get("error") or
                                                                 "no reason was given")
    config, problems = parse_config(answer.get("config"))
    if config is None:
        return None, "its start-time config %s is refused: %s" % (answer.get("path") or "",
                                                                  "; ".join(problems))
    return config, ""


def tables_for(config, dpid):
    """`(forward, punt)` for *dpid*, or None when the config names none (the switch is not
    served)."""
    if config is None:
        return None
    return config["switches"].get(dpid, config["default_tables"])


# ── addresses ───────────────────────────────────────────────────────────────────────────────

def address_match(text):
    """`(field, eth_type, address)` a host address is matched by (`ipv4_dst` or `ipv6_dst`,
    the address in its compressed form), or None when *text* is not a host's address: not an
    address, unspecified, multicast, loopback or the IPv4 broadcast."""
    try:
        address = ipaddress.ip_address(str(text))
    except ValueError:
        return None
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        return None
    if address.version == 4:
        if address == ipaddress.IPv4Address("255.255.255.255"):
            return None
        return ("ipv4_dst", ETH_IPV4, address.compressed)
    return ("ipv6_dst", ETH_IPV6, address.compressed)


# ── the topology ────────────────────────────────────────────────────────────────────────────

def graph_of(links, up_ports, served):
    """`{dpid: {neighbour: out_port}}` over the *served* switches: a link counts only when
    both ends have reported it (`links` holds `(src_dpid, src_port, dst_dpid, dst_port)` per
    direction) and both ports are up (`up_ports`: `{dpid: set of ports}`); of parallel links,
    the lowest local port is taken."""
    present = set(links)
    graph = dict((dpid, {}) for dpid in served)
    for (a, pa, b, pb) in sorted(present):
        if a == b or a not in graph or b not in graph or (b, pb, a, pa) not in present:
            continue
        if pa not in up_ports.get(a, ()) or pb not in up_ports.get(b, ()):
            continue
        if b not in graph[a] or pa < graph[a][b]:
            graph[a][b] = pa
    return graph


def link_ports(links):
    """`{dpid: set of ports}` on any link, from either end's report."""
    out = {}
    for (a, pa, b, pb) in links:
        out.setdefault(a, set()).add(pa)
        out.setdefault(b, set()).add(pb)
    return out


def edge_ports(up_ports, links, up_since, now, settle_s):
    """`{dpid: [port, ...]}`: the ports a broadcast may be relayed out of. A port is an edge
    when it is up, on no link either end reported, and up for *settle_s* (`up_since`:
    `{(dpid, port): when it came up}`), so a port is never an edge before discovery had the
    time to find a link on it."""
    on_links = link_ports(links)
    out = {}
    for dpid in sorted(up_ports):
        ports = [p for p in sorted(up_ports[dpid])
                 if p not in on_links.get(dpid, ())
                 and now - up_since.get((dpid, p), now) >= settle_s]
        out[dpid] = ports
    return out


def next_hops(graph, dst, path=shortest_path):
    """`(hops, problems)`: `hops` is `{dpid: (neighbour, out_port)}` toward *dst* for every
    switch *path* (the team's `shortest_path`) finds a way from; `problems` names each answer
    that is not a path of *graph* from that switch to *dst*, which is left out."""
    hops, problems = {}, []
    for src in sorted(graph):
        if src == dst:
            continue
        got = path(graph, src, dst)
        if got is None:
            continue
        if not isinstance(got, list) or len(got) < 2 or got[0] != src or got[-1] != dst \
                or len(set(got)) != len(got) \
                or any(got[i + 1] not in graph.get(got[i], {}) for i in range(len(got) - 1)):
            problems.append("shortest_path(%d, %d) answered %r, which is not a simple path of "
                            "the graph between them" % (src, dst, got))
            continue
        hops[src] = (got[1], graph[src][got[1]])
    return hops, problems


def forwarding_loop(hops, dst):
    """The first loop the next hops toward *dst* hold, as the list of switches around it, or
    None when every switch's hops reach *dst* or stop."""
    for start in sorted(hops):
        seen, node = [], start
        while node in hops and node != dst:
            if node in seen:
                return seen[seen.index(node):] + [node]
            seen.append(node)
            node = hops[node][0]
    return None


# ── the flows ───────────────────────────────────────────────────────────────────────────────

def _match(*items):
    return tuple(sorted(items))


def desired_flows(config, graph, hosts):
    """`({dpid: {(table, priority, match): (actions, cookie)}}, problems)` for every switch in
    *graph* (the served ones); *hosts* is `{address: (dpid, port)}` (see the module's
    docstring for the flows)."""
    out, problems = {}, []
    for dpid in sorted(graph):
        forward, punt = tables_for(config, dpid)
        flows = {(punt, PRIORITY[MISS], _match()): ((CONTROLLER,), cookie(MISS)),
                 (punt, PRIORITY[ARP], _match(("eth_type", ETH_ARP))):
                     ((CONTROLLER,), cookie(ARP))}
        if forward != punt:
            for eth in (ETH_IPV4, ETH_IPV6):
                flows[(forward, PRIORITY[GOTO], _match(("eth_type", eth)))] = \
                    ((("GOTO", punt),), cookie(GOTO))
        out[dpid] = flows
    for address in sorted(hosts):
        matched = address_match(address)
        at, port = hosts[address]
        if matched is None or at not in graph:
            continue
        field, eth, text = matched
        hops, why = next_hops(graph, at)
        problems.extend(why)
        loop = forwarding_loop(hops, at)
        if loop is not None:
            problems.append("the next hops toward %s loop (%s): none is installed"
                            % (text, " -> ".join(str(d) for d in loop)))
            continue
        match = _match(("eth_type", eth), (field, text))
        for dpid in sorted(graph):
            forward = tables_for(config, dpid)[0]
            if dpid == at:
                out[dpid][(forward, PRIORITY[DELIVER], match)] = ((("OUTPUT", port),),
                                                                  cookie(DELIVER))
            elif dpid in hops:
                out[dpid][(forward, PRIORITY[TRANSIT], match)] = ((("OUTPUT", hops[dpid][1]),),
                                                                  cookie(TRANSIT))
    return out, problems


def difference(desired, current):
    """What reconcile does on one switch: *desired* is `desired_flows`' entry for it, *current*
    its flows as read, each `(table, priority, match, actions, cookie)`. Answers `{"add":
    [(key, actions, cookie)], "delete": [(key, cookie)], "conflicts": [words], "kept": n}`:
    only the app's own cookie is added or removed, a key another owner holds is a conflict, and
    a flow already as desired is kept (counted, never sent again)."""
    ours, others = {}, {}
    for (table, priority, match, actions, value) in current:
        key = (table, priority, tuple(sorted(match)))
        if is_ours(value):
            ours[key] = (tuple(actions), value)
        else:
            others[key] = value
    add, delete, conflicts, kept = [], [], [], 0
    for key in sorted(desired):
        actions, value = desired[key]
        if key in others:
            conflicts.append("table %d priority %d match %s is held by cookie %#x, another "
                             "owner's: not overwritten" % (key[0], key[1], dict(key[2]),
                                                           others[key]))
            continue
        if ours.get(key) == (actions, value):
            kept += 1
            continue
        add.append((key, actions, value))
    for key in sorted(ours):
        if key not in desired:
            delete.append((key, ours[key][1]))
    return {"add": add, "delete": delete, "conflicts": conflicts, "kept": kept}


def hosts_from_flows(dpid, current):
    """`{address: (dpid, port)}` from the app's own DELIVER flows on *dpid* (read back after a
    controller restart, so the hosts are rebuilt from the switches, never forgotten)."""
    out = {}
    for (_table, _priority, match, actions, value) in current:
        if kind_of(value) != DELIVER:
            continue
        fields = dict(match)
        address = fields.get("ipv4_dst", fields.get("ipv6_dst"))
        outputs = [a[1] for a in actions if a[0] == "OUTPUT"]
        matched = address_match(address) if address is not None else None
        if matched is not None and len(outputs) == 1:
            out[matched[2]] = (dpid, outputs[0])
    return out


class Recent:
    """The frames relayed within *window_s*: `seen(key, now)` is True for a key seen in the
    window (and drops it), else records it."""

    def __init__(self, window_s):
        self.window_s = window_s
        self.when = {}

    def seen(self, key, now):
        for old in [k for k, t in self.when.items() if now - t > self.window_s]:
            del self.when[old]
        if key in self.when:
            return True
        self.when[key] = now
        return False
