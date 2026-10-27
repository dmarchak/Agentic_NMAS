"""The SDN closed loop's named functions (PHASE8_PLAN 17.1 S13): what the loop reads, judges and
does, in one module, so a report can show their code. `collect_threat_data` (S4) is here;
`classify_threat` (S7) and `respond_to_threat` (S8) are later items.

**`collect_threat_data(network)`** is deterministic and asks no AI. For every controller
connection of *network* (`connections.connections`) it reads:
- each switch's flow table (`flows`): every flow, the active flow count, and the drop flows (a
  flow with an empty action list);
- each switch's port counters twice, a stated interval apart (`port_stats`), so each port's
  packet and byte rates are counter deltas over the measured time between the two reads;
- the flow granularity found per switch (``coverage``): ``L4`` when a flow matches `tcp_dst` or
  `udp_dst`, ``L3`` when flows match IP fields and no transport port, ``L2`` when they match
  only Ethernet fields and `in_port`, ``none`` with no flow but the match-all. Only L4 flows
  can show a scan as distinct destination ports; L3 and L2 flows cannot, and the answer says
  so (a detection then rests on packet rates, at lower confidence).

**The answer is a plain dict, JSON-serialisable**, so a report can show it, an evidence pack can
carry it and the classifier can be sent it. **Every flow and port row carries its evidence id**
(``id``), what a detection (`detect`) and the classifier cite:
- a flow's, ``flow:<connection>:<dpid hex>:t<table>:p<priority>:<match digest>``: OpenFlow's
  own identity of a flow (no two flows in one table share a priority and a match), so a flow
  keeps its id from one collection to the next;
- a port's, ``port:<connection>:<dpid hex>:<port number>``. A controller that fails is said, per controller
(``unreadable``, with why) and per switch (``partial`` or ``unreadable``, naming each read that
failed), never dropped. No connection is ``none``; a store that cannot be read is
``unreadable``: absent and unreadable are different states.

**Bounds.** Every read is bounded by its driver (the connection's timeout). The wait between the
two samples is *sleep*, and the times are *clock*'s, both injectable: a test passes a fake
clock and never sleeps. The interval is from `MIN_INTERVAL` to `MAX_INTERVAL` seconds.

**Fleet scale.** A job calls this, never a request handler (CLAUDE.md, "Enterprise scale").
For a connection with N switches it makes 1 + 3N controller calls: the switch list, then per
switch one flow read and two port reads. The reads across switches (and connections) run at
once (`fanout.read_each`), and the wait is one, for the whole network, between the two rounds.
"""

import hashlib
import json
import logging
import threading
import time

log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 5.0
MIN_INTERVAL = 1.0
MAX_INTERVAL = 60.0
#: Match fields that make a flow L4 (a scan shows as distinct destination ports).
L4_FIELDS = frozenset({"tcp_dst", "udp_dst"})
#: Match fields of Ethernet and the switch port alone: a flow matching nothing else is L2.
L2_FIELDS = frozenset({"in_port", "in_phy_port", "eth_src", "eth_dst", "eth_type", "vlan_vid",
                       "vlan_pcp", "metadata", "tunnel_id", "pbb_isid"})
GRANULARITIES = ("L4", "L3", "L2", "none")
COVERAGE_WORDS = {
    "L4": ("flows match transport ports, so a scan shows as distinct destination ports per "
           "source"),
    "L3": ("flows match IP addresses and no transport port: they cannot show a per-port scan; "
           "a scan shows only as packet rates, at lower confidence"),
    "L2": ("flows match only Ethernet fields and the switch port: they cannot show a per-port "
           "scan; a scan shows only as packet rates, at lower confidence"),
    "none": ("no flow but the match-all, so nothing shows what traffic crosses this switch "
             "beyond its port counters"),
}
_COUNTERS = ("rx_packets", "tx_packets", "rx_bytes", "tx_bytes", "rx_dropped", "tx_dropped")


def granularity(match: dict) -> str:
    """One flow's granularity from its match (OpenFlow 1.3 OXM names): ``L4``, ``L3``, ``L2``,
    or ``none`` for an empty match (the match-all)."""
    keys = set(match or {})
    if not keys:
        return "none"
    if keys & L4_FIELDS:
        return "L4"
    if keys - L2_FIELDS:
        return "L3"
    return "L2"


def coverage(flows: list) -> dict:
    """What *flows* can show: ``{"granularity", "by_granularity", "scan_by_ports", "words"}``,
    the finest granularity found among them."""
    counts = {g: 0 for g in GRANULARITIES}
    for f in flows:
        counts[granularity(f.get("match"))] += 1
    found = next((g for g in GRANULARITIES if counts[g]), "none")
    return {"granularity": found, "by_granularity": counts, "scan_by_ports": found == "L4",
            "words": COVERAGE_WORDS[found]}


def flow_ref(connection: str, dpid: int, flow: dict) -> str:
    """A flow's evidence id: its connection, switch, table, priority and a digest of its match
    in one canonical form (`flow_intent.normal_match`), so a switch's spelling of a match does
    not move it."""
    from modules.sdn.drivers.base import dpid_hex
    from modules.sdn.flow_intent import normal_match

    digest = hashlib.sha256(json.dumps(normal_match(flow.get("match")), sort_keys=True,
                                       default=str).encode()).hexdigest()[:10]
    return (f"flow:{connection}:{dpid_hex(dpid)}:t{flow.get('table_id', 0)}:"
            f"p{flow.get('priority', 0)}:{digest}")


def port_ref(connection: str, dpid: int, port_no) -> str:
    """A port's evidence id: its connection, switch and port number (or reserved name)."""
    from modules.sdn.drivers.base import dpid_hex

    return f"port:{connection}:{dpid_hex(dpid)}:{port_no}"


def _rates(first: dict, second: dict, elapsed: float) -> list:
    """Each port's counter deltas and rates between two reads *elapsed* seconds apart. A port
    in one read only, or a counter that fell (a reset), is said, never given a rate."""
    one = {p.get("port_no"): p for p in first.get("ports") or []}
    two = {p.get("port_no"): p for p in second.get("ports") or []}
    out = []
    for port in sorted(set(one) | set(two), key=lambda p: (isinstance(p, str), str(p))):
        a, b = one.get(port), two.get(port)
        row = {"port_no": port}
        if a is None or b is None:
            row["note"] = ("in the second read only" if a is None else "in the first read only")
            out.append(row)
            continue
        fell = [k for k in _COUNTERS if (b.get(k) or 0) < (a.get(k) or 0)]
        if fell:
            row["note"] = f"counters fell between the reads ({', '.join(fell)}): a reset"
            out.append(row)
            continue
        for k in _COUNTERS:
            row[f"{k}_delta"] = (b.get(k) or 0) - (a.get(k) or 0)
        if elapsed > 0:
            for k in ("rx_packets", "tx_packets", "rx_bytes", "tx_bytes"):
                row[f"{k[:2]}_{'pps' if k.endswith('packets') else 'bytes_per_s'}"] = round(
                    row[f"{k}_delta"] / elapsed, 3)
        out.append(row)
    return out


def _connections(network: str) -> dict:
    from modules.sdn import connections

    return connections.connections(network)


def _driver(network: str, name: str) -> dict:
    from modules.sdn import connections

    return connections.driver_for(network, name)


def collect_threat_data(network: str, interval: float = DEFAULT_INTERVAL, *,
                        sleep=time.sleep, clock=time.monotonic, now=time.time,
                        driver=None) -> dict:
    """Every controller connection of *network*: its switches' flows, port rates over two
    samples *interval* seconds apart, active flows, drop flows and coverage; each failure said
    where it happened. *sleep*, *clock* and *now* (the wall clock the answer is stamped with)
    are injectable; *driver* is ``driver(network, name) -> driver_for's answer`` (a test's
    fakes). See the module's docstring for the shape and the call count."""
    from modules import fanout

    calls = {"n": 0}
    out = {"network": network, "collected_at": _iso(now()), "interval_s": interval,
           "state": "unreadable", "error": "", "controllers": [], "summary": {}, "calls": 0}
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) \
            or not MIN_INTERVAL <= interval <= MAX_INTERVAL:
        out["error"] = (f"the interval between the two samples is from {MIN_INTERVAL:g} to "
                        f"{MAX_INTERVAL:g} seconds, not {interval!r}")
        return out
    listed = _connections(network)
    if listed["state"] in ("unreadable",):
        out["error"] = f"{network}'s controller connections could not be read: {listed['error']}"
        return out
    if listed["state"] in ("none", "not_applicable"):
        out.update(state="none", error="", summary=_summary([]),
                   words=(f"{network} has no SDN controller connection" if
                          listed["state"] == "none" else
                          f"SDN controllers are declared not applicable on {network}"))
        return out
    make = driver or _driver
    counter = threading.Lock()

    def counted(fn, *args):
        with counter:
            calls["n"] += 1
        return fn(*args)

    # 1. Each connection's driver and switch list, at once.
    def open_one(conn):
        got = make(network, conn["name"])
        entry = _entry(conn)
        if not got.get("ok"):
            entry["error"] = got.get("error") or "no driver"
            return entry, None, []
        drv = got["driver"]
        listed_switches = counted(drv.switches)
        if not listed_switches.get("ok"):
            entry["error"] = f"the switch list could not be read: {listed_switches.get('error')}"
            return entry, drv, []
        return entry, drv, [s["dpid"] for s in listed_switches.get("switches") or []]

    opened = _each(fanout, open_one, listed["connections"], "sdn-open",
                   lambda conn, words: (dict(_entry(conn), error=words), None, []))
    pairs = [(entry, drv, dpid) for entry, drv, dpids in opened for dpid in dpids]

    # 2. The first round: each switch's flows and its first port read, at once.
    def first(pair):
        _entry, drv, dpid = pair
        flows = counted(drv.flows, dpid)
        ports = counted(drv.port_stats, dpid)
        return flows, ports, clock()

    round_one = _each(fanout, first, pairs, "sdn-sample-1",
                      lambda _pair, words: ({"ok": False, "error": words},
                                            {"ok": False, "error": words}, None))
    # 3. One wait for the whole network, then the second port read.
    if pairs:
        sleep(interval)

    def second(pair):
        _entry, drv, dpid = pair
        ports = counted(drv.port_stats, dpid)
        return ports, clock()

    round_two = _each(fanout, second, pairs, "sdn-sample-2",
                      lambda _pair, words: ({"ok": False, "error": words}, None))
    for (entry, _drv, dpid), one, two in zip(pairs, round_one, round_two):
        entry["switches"].append(_switch(dpid, one, two, interval,
                                         connection=entry["connection"]))
    for entry, drv, dpids in opened:
        if drv is not None and not entry["error"]:
            bad = [s for s in entry["switches"] if s["state"] != "ok"]
            unread = [s for s in bad if s["state"] == "unreadable"]
            entry["state"] = ("ok" if not bad else
                              "unreadable" if len(unread) == len(entry["switches"]) else
                              "partial")
            if bad:
                entry["error"] = (f"{len(bad)} of {len(entry['switches'])} switch(es) not read "
                                  "whole: " + "; ".join(f"{s['dpid_hex']}: {s['error']}"
                                                        for s in bad))
    controllers = [entry for entry, _drv, _dpids in opened]
    states = {c["state"] for c in controllers}
    out.update(controllers=controllers, summary=_summary(controllers), calls=calls["n"],
               state="ok" if states == {"ok"} else
               "unreadable" if states == {"unreadable"} else "partial")
    if out["state"] != "ok":
        out["error"] = "; ".join(f"{c['connection']}: {c['error']}" for c in controllers
                                 if c["state"] != "ok")
    return out


def _each(fanout, fn, items, name, fallback):
    """`fanout.read_each`; a read that raised is that item's ``fallback(item, words)``, its
    failure in words, never dropped."""
    got = fanout.read_each(fn, items, name=name)
    return [fallback(item, f"the read raised {g}") if isinstance(g, fanout.Failed) else g
            for item, g in zip(items, got)]


def _entry(conn: dict) -> dict:
    return {"connection": conn.get("name"), "kind": conn.get("kind"), "url": conn.get("url"),
            "own_cookies": conn.get("own_cookies"), "state": "unreadable", "error": "", "switches": []}


def _switch(dpid: int, one: tuple, two: tuple, interval: float, connection: str = "") -> dict:
    from modules.sdn.drivers.base import dpid_hex

    flows_got, first_ports, t1 = one
    second_ports, t2 = two
    row = {"dpid": dpid, "dpid_hex": dpid_hex(dpid), "state": "ok", "error": "",
           "flows": [], "active_flows": None, "drop_flows": [], "coverage": None,
           "ports": [], "sample": {"interval_s": interval, "elapsed_s": None}}
    errors = []
    flows_ok = bool(flows_got.get("ok"))
    if flows_ok:
        flows = [dict(f, id=flow_ref(connection, dpid, f)) for f in flows_got.get("flows") or []]
        row.update(flows=flows, active_flows=len(flows),
                   drop_flows=[f for f in flows if not f.get("actions")],
                   coverage=coverage(flows))
    else:
        errors.append(f"flows: {flows_got.get('error')}")
    ports_ok = bool(first_ports.get("ok") and second_ports.get("ok")
                    and t1 is not None and t2 is not None)
    if ports_ok:
        elapsed = round(t2 - t1, 3)
        row["sample"]["elapsed_s"] = elapsed
        row["ports"] = [dict(p, id=port_ref(connection, dpid, p["port_no"]))
                        for p in _rates(first_ports, second_ports, elapsed)]
    else:
        for which, got in (("first port read", first_ports), ("second port read", second_ports)):
            if not got.get("ok"):
                errors.append(f"{which}: {got.get('error')}")
    if errors:
        row["error"] = "; ".join(errors)
        row["state"] = "partial" if flows_ok or ports_ok else "unreadable"
    return row


def _summary(controllers: list) -> dict:
    switches = [s for c in controllers for s in c["switches"]]
    return {"controllers": len(controllers),
            "unreadable": sum(c["state"] == "unreadable" for c in controllers),
            "partial": sum(c["state"] == "partial" for c in controllers),
            "switches": len(switches),
            "flows": sum(s["active_flows"] or 0 for s in switches),
            "drop_flows": sum(len(s["drop_flows"]) for s in switches),
            "scan_by_ports": sum(bool(s["coverage"] and s["coverage"]["scan_by_ports"])
                                 for s in switches)}


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))
