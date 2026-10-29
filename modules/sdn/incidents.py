"""SDN incidents (C1999): one attack seen on many switches is one incident, one response proposed
at its ingress switch, one AI classification, one Needs attention row.

**Why.** A source scanning or flooding across a fabric is seen by every switch on its path: the
reactive application installs the source's flows on each, so each switch's rule fires. Before
incidents, 50 switches seeing one scan were 50 detections, 50 classify calls, 50 responses
awaiting a person and 50 cards, and a person confirming one left 49 more for the same attack.

**The grouping key** (`group_key`): the rule and the detection's source in its one spelling
(`loop.canon_source`, C2005's: IPv4 and IPv6 compressed, a MAC address lower-case). Only the
rules whose subject is a source are grouped (`GROUPED_RULES`: scan, flood). An unauthorised
flow is one flow on one switch, removed on its own, so each is its own incident; a detection
naming no single source (a flood or a scan's packet-rate fallback whose port's flows name no
address and whose port the controller's topology cannot resolve to one host, `detect.
port_source`, C2002) has nothing to tie it to another switch's, so it is its own incident too,
keyed by its detection key. One whose source the topology names groups by that source.

**The window** (`window`), derived, never a setting of its own: the rule's own window, the one
it fires within (scan: `sdn_scan_window_seconds`, 60 by default; flood:
`sdn_flood_window_seconds`, 30). Two switches whose rule fired for the same source within that
window are seeing the same burst. A detection joins an incident still awaiting a person when it
is of the same rule and source and its time is within the window of the incident's last
sighting (`joinable`: at most the window, so 60 s later joins and 61 s later is a new
incident); the detections of one pass, one collection's time, are always within it. The
incident keeps the window it was grouped by and the setting it came from, and the card says
both.

**The ingress switch** (`ingress`): the switch where the source's host port is, read from the
controller's topology as the SDN reader stored it (`topology.stored`, the hosts the controller
learned, in `drivers.base.topo_host`'s shape, the same hosts `closed_loop._port_hosts` reads
live): a host listing the source (by an IPv4 or IPv6 address, or its MAC) on a port that is not
an inter-switch link's end. When exactly one such port is listed, on a switch whose rule fired,
that detection is the incident's: its response is proposed there, since a drop or a rate limit
at the port the source enters by holds it off from every switch behind it. Otherwise the
ingress cannot be told (no source named, the topology not read now, no host listing the source,
the source listed on more than one port, or on a switch that has not fired), the card says why,
and the response is proposed at the switch that saw it first (the earliest detection time; on a
tie, the order the rules reported them). Never a controller call: the reader's stored value.

**What the incident records** (`record`): its key, rule, source, window, the ingress (known or
not, its words, its port) and every other switch that saw it, "seen also", each with its
detection's key, switch and words. The response store keeps it on the proposed row
(`loop.propose`), and the detection proposed carries a compact copy (`stamp`), which a confirmed
response's flow intent keeps, so a response at a known ingress holds the source off on every
switch of its connection (`loop.covering`'s ``across``, C2005 at incident level).

**Severity, for the order** (`SEVERITY_ORDER`): the classification's severity, critical first;
an incident not classified (the feature off, a refused or failed call) ranks below high and
above medium: deterministic code fired on it and no assessment says it is minor, and no
assessment says it is severe either.
"""

import logging
import time

log = logging.getLogger(__name__)

#: The rules whose subject is a source, each with the setting its window comes from.
GROUPED_RULES = {"scan": "sdn_scan_window_seconds", "flood": "sdn_flood_window_seconds"}
#: An incident's severity, most urgent first: the classification's, else ``unclassified``.
SEVERITY_ORDER = ("critical", "high", "unclassified", "medium", "low", "none")
#: The incident key of a detection grouped by nothing but itself.
SINGLE = "detection"


def _epoch(text) -> float:
    import calendar

    try:
        return float(calendar.timegm(time.strptime(str(text or ""), "%Y-%m-%dT%H:%M:%SZ")))
    except ValueError:
        return None


def _canon(value) -> str:
    from modules.sdn.loop import canon_source

    return canon_source(value)


def window(rule: str, values: dict) -> dict:
    """The window an incident of *rule* groups detections within: ``{"seconds", "setting",
    "words"}``, the rule's own window from the network's thresholds *values*
    (`detect.thresholds`' ``values``); 0 for a rule that is not grouped."""
    setting = GROUPED_RULES.get(rule)
    if not setting:
        return {"seconds": 0, "setting": "",
                "words": "not grouped: each unauthorised flow is one flow on one switch"}
    seconds = int((values or {}).get(setting) or 0)
    return {"seconds": seconds, "setting": setting,
            "words": f"within {seconds} s, the {rule} rule's own window ({setting})"}


def group_key(d: dict) -> str:
    """The incident *d* belongs to: ``<rule>|<source>`` for a grouped rule with one source,
    else ``detection|<its key>``."""
    src = _canon(d.get("source"))
    if d.get("rule") in GROUPED_RULES and src:
        return f"{d['rule']}|{src}"
    return f"{SINGLE}|{d.get('key')}"


def group(detections: list, values: dict) -> list:
    """*detections* (one pass's, in the rules' order) as incidents, in the order of each one's
    first detection: ``[{"key", "rule", "source", "window", "members": [detection]}]``."""
    out = {}
    for d in detections:
        k = group_key(d)
        inc = out.get(k)
        if inc is None:
            src = _canon(d.get("source")) if not k.startswith(SINGLE + "|") else ""
            out[k] = inc = {"key": k, "rule": d.get("rule"), "source": src,
                            "window": window(d.get("rule"), values), "members": []}
        if all(m.get("key") != d.get("key") for m in inc["members"]):
            inc["members"].append(d)
    return list(out.values())


def first_seen(members: list) -> dict:
    """The member seen first: the earliest detection time, on a tie the first reported."""
    def when(pair):
        at = _epoch(pair[1].get("at"))
        return (at if at is not None else float("inf"), pair[0])
    return min(enumerate(members), key=when)[1]


def _attachments(stored: dict, source: str, connections: set) -> dict:
    """Where the controllers' topology (`topology.stored`) lists *source*'s host, off an
    inter-switch link: ``{"ports": [(connection, dpid, dpid_hex, port_no)], "why", "read_at"}``,
    *why* saying why nothing could be told (the topology not read now)."""
    if stored.get("state") != "read":
        return {"ports": [], "why": f"the controller's topology could not be read "
                                    f"({stored.get('why') or stored.get('state')})",
                "read_at": ""}
    ports, unread, read_at = [], [], ""
    for c in stored.get("controllers") or []:
        if c.get("name") not in connections:
            continue
        if c.get("state") != "read":
            unread.append(f"{c.get('name')}: {c.get('why') or c.get('state')}")
            continue
        read_at = read_at or c.get("read_at") or ""
        link_ends = set()
        for link in c.get("links") or []:
            for end in ("src", "dst"):
                e = link.get(end) or {}
                link_ends.add((int(e.get("dpid") or 0), e.get("port_no")))
        for h in c.get("hosts") or []:
            names = {_canon(a) for a in list(h.get("ipv4") or []) + list(h.get("ipv6") or [])}
            names.add(_canon(h.get("mac")))
            if source not in names or (int(h.get("dpid") or 0), h.get("port_no")) in link_ends:
                continue
            at = (c.get("name"), int(h["dpid"]), h.get("dpid_hex") or "", h.get("port_no"))
            if at not in ports:
                ports.append(at)
    why = ""
    if not ports and unread:
        why = "the controller's topology was not read now (" + "; ".join(unread) + ")"
    return {"ports": ports, "why": why, "read_at": read_at}


def ingress(network: str, inc: dict, stored: dict = None) -> dict:
    """The detection of incident *inc* its response is proposed at: ``{"detection", "known",
    "words", "port"}`` (the module's docstring). *stored* the reader's stored topology
    (`topology.stored`'s answer), read here when None; one that cannot be read is said."""
    from modules.sdn.drivers.base import SpecError, parse_dpid

    members = inc["members"]
    first = first_seen(members)
    source = inc.get("source") or ""

    def unknown(why: str) -> dict:
        n = len(members)
        where = (f"proposed at {first.get('dpid_hex')}, the switch that saw it first" if n > 1
                 else f"proposed at {first.get('dpid_hex')}, the switch that saw it")
        return {"detection": first, "known": False, "port": None,
                "words": f"the ingress switch cannot be told: {why}; {where}"}

    if not source:
        return unknown("the detection names no single source")
    if stored is None:
        try:
            from modules.sdn import topology
            stored = topology.stored(network)
        except Exception as exc:                      # noqa: BLE001 (said as the reason)
            stored = {"state": "could not read", "why": type(exc).__name__}
    got = _attachments(stored, source, {m.get("connection") for m in members})
    if got["why"]:
        return unknown(got["why"])
    if not got["ports"]:
        return unknown(f"the controller's topology lists no host with {source} on a port "
                       "other than a link's")
    if len(got["ports"]) > 1:
        listed = ", ".join(f"{dh} port {p}" for _c, _d, dh, p in got["ports"])
        return unknown(f"the controller's topology lists {source} on {len(got['ports'])} "
                       f"ports ({listed})")
    conn, dpid, dpid_hex, port = got["ports"][0]
    for m in members:
        try:
            same = m.get("connection") == conn and parse_dpid(
                m.get("dpid") if m.get("dpid") is not None else m.get("dpid_hex")) == dpid
        except SpecError:
            same = False
        if same:
            return {"detection": m, "known": True, "port": port, "words": (
                f"the ingress switch is {m.get('dpid_hex') or dpid_hex}: the controller's "
                f"topology (read {got['read_at'] or 'at a time not recorded'}) lists {source}'s "
                f"host on its port {port}")}
    return unknown(f"the controller's topology lists {source} on {dpid_hex or dpid} port "
                   f"{port}, which has not fired")


def brief(d: dict) -> dict:
    """A detection as an incident's "seen also" keeps it."""
    return {k: d.get(k) for k in ("key", "connection", "dpid", "dpid_hex", "at", "words",
                                  "port")}


def record(inc: dict, chosen: dict) -> dict:
    """What the response store keeps of incident *inc*, its response proposed at *chosen*
    (`ingress`' answer)."""
    d = chosen["detection"]
    w = inc["window"]
    return {"key": inc["key"], "rule": inc.get("rule"), "source": inc.get("source") or "",
            "window_s": w["seconds"], "window_setting": w["setting"], "window_words": w["words"],
            "ingress_known": bool(chosen["known"]), "ingress_words": chosen["words"],
            "ingress_port": chosen["port"],
            "seen_also": [brief(m) for m in inc["members"] if m.get("key") != d.get("key")]}


def stamp(d: dict, rec: dict) -> dict:
    """Detection *d* as its incident's response carries it: with a compact ``incident`` (its
    key, whether *d* is the known ingress, how many switches saw it)."""
    return dict(d, incident={"key": rec["key"], "ingress": rec["ingress_known"],
                             "switches": 1 + len(rec["seen_also"])})


def key_of(row: dict) -> str:
    """The incident key of a response awaiting a person (one kept before incidents: its own
    detection's)."""
    inc = row.get("incident") or {}
    return inc.get("key") or group_key(row.get("detection") or {})


def joinable(rows: list, d: dict, now: float) -> dict:
    """The incident awaiting a person (among `loop.awaiting`'s *rows*) detection *d* joins, or
    None: the same grouped rule and source, *d*'s time (else *now*) at most the incident's
    window after its last sighting."""
    k = group_key(d)
    if k.startswith(SINGLE + "|"):
        return None
    at = _epoch(d.get("at"))
    at = now if at is None else at
    for r in rows:
        if key_of(r) != k:
            continue
        inc = r.get("incident") or {}
        last = _epoch(r.get("last_seen") or r.get("at"))
        if last is not None and at - last <= int(inc.get("window_s") or 0):
            return r
    return None


def severity(row: dict) -> str:
    """An incident's severity: its classification's, else ``unclassified``."""
    sev = str(((row.get("classification") or {}).get("severity") or "")).lower()
    return sev if sev in SEVERITY_ORDER else "unclassified"


def order(rows: list) -> list:
    """*rows* by severity (`SEVERITY_ORDER`), then the longest waiting first."""
    return sorted(rows, key=lambda r: (SEVERITY_ORDER.index(severity(r)),
                                       _epoch(r.get("at")) or 0.0))
