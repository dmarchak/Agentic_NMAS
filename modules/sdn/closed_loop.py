"""The SDN closed loop's named functions (PHASE8_PLAN 17.1 S13): what the loop reads, judges and
does, in one module, so a report can show their code. `collect_threat_data` (S4) and
`respond_to_threat` (S8) are here; `classify_threat` (S7) is the AI's, and until the cost-safety
rules are live (C1843) it is a stub that refuses (below).

**`respond_to_threat(network, detection, ...)`** answers a detection (`detect`) with an action
from the response catalogue (`CATALOGUE`), deterministic, through the flow-operation core
(`flow_ops`): the same preview, confirm by hash, apply, Verify, rollback and record as every
flow Mercury changes. Without a confirm it is the preview, writing nothing; with one it is the
apply. The actions:
- ``drop_source`` (risk low): one flow on the detection's switch matching the source address
  (IPv4 or IPv6) with no actions, above every flow not Mercury's (`flow_ops.
  response_priority`), with the network's hard timeout;
- ``rate_limit_source`` (risk low): one meter with a single drop band (kbps or pktps, with a
  burst), then, for each destination the evidence saw the source reach, a flow matching the
  pair whose actions are the meter and the controller's own forwarding for it read from the
  switch's table; the meter is removed by Mercury once its flows expire (`flow_ops.
  expire_meters`);
- ``remove_flow`` (risk medium): the unauthorised flow the detection names, by delete-strict
  (its table, priority, match and cookie), then Mercury's own recorded flow put back where the
  unauthorised one displaced it, if one should be there.
Each action's parameters are checked against the evidence (the source is the detection's, the
switch is the detection's, the timeout within the network's limit) before a request exists.

**`classify_threat`** is a stub: background AI is not allowed until the cost-safety rules
(C1843) give the gateway a trigger it can refuse, so it refuses, makes no call, and the loop
(`loop.py`) proposes the catalogue's deterministic default for the rule instead
(`DEFAULT_ACTION`), marked as such.

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


# ───────────────────────────────────────────────────────────────────────────── classify (S7)

#: Why the classifier makes no call yet: the gateway names no trigger (C1843).
CLASSIFY_REFUSED = ("background AI is not allowed until cost safety is live (C1843): no AI call "
                    "was made, and the response proposed is the catalogue's default for the "
                    "rule, chosen in code")


def classify_threat(detection: dict, *, trigger: str = "background") -> dict:
    """S7's classifier, not yet built: it refuses and makes no call (see the module's
    docstring). ``{"ok": False, "refused": True, "error", "trigger"}``."""
    return {"ok": False, "refused": True, "error": CLASSIFY_REFUSED, "trigger": trigger,
            "rule": (detection or {}).get("rule")}


# ───────────────────────────────────────────────────────────────────────────── respond (S8)

#: The response catalogue: each action, its risk class, the rules it answers and its words.
CATALOGUE = {
    "drop_source": {"risk": "low", "rules": ("scan", "flood"),
                    "label": "Drop traffic from the source",
                    "words": "one flow dropping every packet from the source on the switch, "
                             "until its hard timeout"},
    "rate_limit_source": {"risk": "low", "rules": ("flood", "scan"),
                          "label": "Rate-limit the source",
                          "words": "one meter with a single drop band, and the source's flows to "
                                   "each destination through it, until their hard timeout"},
    "remove_flow": {"risk": "medium", "rules": ("unauthorised_flow",),
                    "label": "Remove the unauthorised flow",
                    "words": "the flow removed by delete-strict, and Mercury's own flow put back "
                             "where it displaced one"},
}
RISKS = ("low", "medium")
#: The action proposed for each rule when no classifier advises (C1843: none may yet).
DEFAULT_ACTION = {"scan": "drop_source", "flood": "rate_limit_source",
                  "unauthorised_flow": "remove_flow"}
#: The rate-limit's defaults: NOT measured, a starting point the person changes in the preview.
RATE_LIMIT_DEFAULT = {"unit": "kbps", "rate": 1000, "burst": 100}
RATE_UNITS = {"kbps": "KBPS", "pktps": "PKTPS"}


class ResponseRefused(ValueError):
    """A response's action or parameters refused, in words."""


def _source_match(source: str) -> dict:
    import ipaddress

    from modules.sdn.match_rules import ETH_IPV4, ETH_IPV6

    try:
        addr = ipaddress.ip_address(str(source).strip())
    except ValueError:
        raise ResponseRefused(f"the source {source!r} is not one host's address") from None
    if addr.version == 4:
        return {"eth_type": ETH_IPV4, "ipv4_src": addr.compressed}
    return {"eth_type": ETH_IPV6, "ipv6_src": addr.compressed}


def _pair_match(source: str, target: str) -> dict:
    import ipaddress

    match = _source_match(source)
    try:
        dst = ipaddress.ip_address(str(target).strip())
    except ValueError:
        raise ResponseRefused(f"the destination {target!r} is not one host's address") from None
    if ("ipv4_src" in match) != (dst.version == 4):
        raise ResponseRefused(f"the source {source} and destination {target} are not one family")
    match["ipv4_dst" if dst.version == 4 else "ipv6_dst"] = dst.compressed
    return match


def _sources(detection: dict) -> list:
    out = [s for s in [detection.get("source")] + list(detection.get("sources") or []) if s]
    return list(dict.fromkeys(out))


def _forwarding(flows: list, source: str, target: str) -> list:
    """The controller's own forwarding of *source*'s traffic to *target* on the switch: the
    OUTPUT actions of the flows matching that pair, read from the table (one port, or none
    when the flows disagree or none is there)."""
    from modules.sdn.flow_intent import is_mercury

    ports = set()
    for f in flows or []:
        if is_mercury(f.get("cookie")):
            continue
        m = f.get("match") or {}
        src = m.get("ipv4_src", m.get("ipv6_src"))
        dst = m.get("ipv4_dst", m.get("ipv6_dst"))
        if src != source or dst != target:
            continue
        outs = [a.get("port") for a in f.get("actions") or [] if a.get("type") == "OUTPUT"]
        if len(outs) == 1:
            ports.add(outs[0])
    return sorted(ports, key=str)


def _hard_timeout(network: str, params: dict) -> int:
    from modules.sdn import flow_ops

    limits = flow_ops.settings_of(network)
    if not limits["ok"]:
        raise ResponseRefused(limits["error"])
    v = limits["values"]
    wanted = (params or {}).get("hard_timeout", v["sdn_response_hard_timeout_seconds"])
    if isinstance(wanted, str) and wanted.strip().isdigit():
        wanted = int(wanted.strip())
    if isinstance(wanted, bool) or not isinstance(wanted, int) or \
            not 1 <= wanted <= v["sdn_response_max_seconds"]:
        raise ResponseRefused(f"a response lasts from 1 to {v['sdn_response_max_seconds']} s "
                              f"(the network's sdn_response_max_seconds), not {wanted!r}")
    return wanted


def _flow_by_ref(flows: list, connection: str, dpid: int, ref: str):
    for f in flows or []:
        if flow_ref(connection, dpid, f) == ref:
            return f
    return None


def build_response(network: str, detection: dict, action_id: str = None, params: dict = None,
                   *, driver=None) -> dict:
    """The ask for *detection*'s response (`flow_ops`' shape), its catalogue action and its
    parameters checked against the evidence, reading the switch's table (and meters) once:
    ``{"ok", "error", "action", "risk", "ask", "params"}``. Draws the cookies and meter id
    here, so the preview and the apply send the same bodies."""
    from modules.sdn import flow_intent, flow_ops
    from modules.sdn.drivers.base import parse_dpid

    out = {"ok": False, "error": "", "action": action_id, "risk": "", "ask": None,
           "params": dict(params or {})}
    try:
        if not isinstance(detection, dict) or detection.get("rule") not in DEFAULT_ACTION:
            raise ResponseRefused("a response answers one detection of the scan, flood or "
                                  "unauthorised-flow rule")
        if detection.get("network") not in (None, "", network):
            raise ResponseRefused(f"the detection is {detection.get('network')!r}'s, not "
                                  f"{network!r}'s")
        action_id = action_id or DEFAULT_ACTION[detection["rule"]]
        entry = CATALOGUE.get(action_id)
        if entry is None:
            raise ResponseRefused(f"{action_id!r} is not in the response catalogue "
                                  f"({', '.join(CATALOGUE)})")
        if detection["rule"] not in entry["rules"]:
            raise ResponseRefused(f"{action_id} answers {', '.join(entry['rules'])}, not "
                                  f"{detection['rule']}")
        out.update(action=action_id, risk=entry["risk"])
        conn, dpid = detection.get("connection") or "", parse_dpid(detection.get("dpid"))
        made = flow_ops._driver(network, conn, driver)
        if not made.get("ok"):
            raise ResponseRefused(made.get("error") or f"no driver for {conn!r}")
        drv = made["driver"]
        read = flow_ops._read_switch(drv, dpid, action_id == "rate_limit_source")
        if not read["ok"]:
            raise ResponseRefused(read["error"])
        intent = flow_intent.intent(network, conn)
        if intent["state"] != "ok":
            raise ResponseRefused(f"{network}'s flow intent could not be read "
                                  f"({intent['error']})")
        own = (made.get("connection") or {}).get("own_cookies") or [0]
        recorded = [r.get("cookie") for r in intent["flows"]]
        changes = []
        if action_id in ("drop_source", "rate_limit_source"):
            sources = _sources(detection)
            source = out["params"].get("source") or (sources[0] if len(sources) == 1 else None)
            if not source:
                raise ResponseRefused("the detection names no single source to act on "
                                      f"(it names {sources or 'none'}): choose one")
            if source not in sources:
                raise ResponseRefused(f"the source {source} is not one the evidence saw "
                                      f"({', '.join(sources) or 'none'})")
            hard = _hard_timeout(network, out["params"])
            priority = flow_ops.response_priority(read["flows"], own, recorded,
                                                  match=_source_match(source))
            out["params"].update(source=source, hard_timeout=hard, priority=priority)
            if action_id == "drop_source":
                changes.append({"do": "add_flow", "flow": {
                    "table_id": 0, "priority": priority, "cookie": flow_intent.new_cookie(),
                    "idle_timeout": 0, "hard_timeout": hard, "match": _source_match(source),
                    "actions": []}})
            else:
                unit = str(out["params"].get("unit") or RATE_LIMIT_DEFAULT["unit"]).lower()
                if unit not in RATE_UNITS:
                    raise ResponseRefused(f"a rate is in {' or '.join(RATE_UNITS)}, not {unit!r}")
                try:
                    rate = int(out["params"].get("rate", RATE_LIMIT_DEFAULT["rate"]))
                    burst = int(out["params"].get("burst", RATE_LIMIT_DEFAULT["burst"]))
                except (TypeError, ValueError):
                    raise ResponseRefused("a rate and a burst are whole numbers") from None
                if rate < 1 or burst < 0:
                    raise ResponseRefused(f"a rate is 1 or more and a burst 0 or more, not "
                                          f"{rate} and {burst}")
                meter_id = flow_ops.free_meter_id(read["meters"], read["features"],
                                                  flows=read["flows"])
                flags = [RATE_UNITS[unit], "STATS"] + (["BURST"] if burst else [])
                out["params"].update(unit=unit, rate=rate, burst=burst, meter_id=meter_id)
                changes.append({"do": "add_meter", "meter": {
                    "meter_id": meter_id, "flags": flags,
                    "bands": [{"type": "DROP", "rate": rate, "burst_size": burst}]}})
                targets = [t for t in detection.get("targets") or [] if t]
                if not targets:
                    raise ResponseRefused("the evidence names no destination of the source's "
                                          "traffic, so there is no forwarding to meter: drop "
                                          "it instead")
                pairs = []
                for target in targets:
                    ports = _forwarding(read["flows"], source, target)
                    if len(ports) != 1:
                        continue
                    pairs.append(target)
                    changes.append({"do": "add_flow", "flow": {
                        "table_id": 0, "priority": priority, "cookie": flow_intent.new_cookie(),
                        "idle_timeout": 0, "hard_timeout": hard,
                        "match": _pair_match(source, target),
                        "actions": [{"type": "METER", "meter_id": meter_id},
                                    {"type": "OUTPUT", "port": ports[0]}]}})
                if not pairs:
                    raise ResponseRefused(
                        f"no single forwarding port for {source}'s traffic to "
                        f"{', '.join(targets)} is in switch {dpid}'s table, so there is "
                        "nothing to meter: drop it instead")
                out["params"]["targets"] = pairs
        else:
            ref = (detection.get("subject") or {}).get("value")
            found = _flow_by_ref(read["flows"], conn, dpid, ref)
            if found is None:
                raise ResponseRefused(f"the flow {ref} is no longer in switch {dpid}'s table: "
                                      "nothing to remove")
            target = {k: found.get(k) for k in ("table_id", "priority", "match", "cookie")}
            changes.append({"do": "remove_flow", "target": target})
            for r in intent["flows"]:
                if r.get("dpid") == dpid and flow_ops._same_place(r, found) and not any(
                        f.get("cookie") == r.get("cookie") for f in read["flows"]):
                    changes.append({"do": "add_flow", "reinstall": True, "flow": {
                        k: r.get(k) for k in ("table_id", "priority", "cookie", "match",
                                              "actions", "idle_timeout", "hard_timeout")}})
            out["params"].update(flow=ref, cookie=flow_intent.cookie_hex(found.get("cookie")))
        out["ask"] = {"connection": conn, "dpid": dpid, "changes": changes,
                      "response": action_id != "remove_flow",
                      "detection": {k: detection.get(k) for k in
                                    ("key", "rule", "title", "dpid_hex", "source", "words",
                                     "at")}}
        out["ok"] = True
    except (ResponseRefused, flow_ops.Refused) as exc:
        out["error"] = str(exc)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("sdn respond: the response could not be built (%s)", type(exc).__name__)
        out["error"] = f"the response could not be built: {type(exc).__name__}: {exc}"
    return out


def respond_to_threat(network: str, detection: dict, action_id: str = None,
                      params: dict = None, *, confirm: dict = None, actor: str = "",
                      actor_verified: str = "", mode: str = "hitl", autonomous: dict = None,
                      driver=None, **apply_kwargs) -> dict:
    """S8: answer *detection* with a catalogue action, through the flow-operation core.

    Without *confirm*: the PREVIEW, writing nothing: ``{"ok", "error", "action", "risk",
    "params", "ask", "plan"}``, the plan carrying the exact requests and their hash.
    With *confirm* ``{"ask", "hash"}`` (the preview's ask, carried back unchanged, and the hash
    the person confirmed): the APPLY (`flow_ops.apply`), as *actor*, in *mode* (``hitl``: a
    person's confirm; ``auto``: *autonomous* names the setting and its reason), recorded with
    the detection it answers."""
    from modules.sdn import flow_ops

    if confirm is None:
        built = build_response(network, detection, action_id, params, driver=driver)
        if not built["ok"]:
            return dict(built, plan=None)
        p = flow_ops.plan(network, built["ask"], driver=driver)
        return dict(built, plan=p, ok=p["ok"], error=p["error"])
    ask = (confirm or {}).get("ask")
    if not isinstance(ask, dict):
        return {"ok": False, "error": "a confirm carries the previewed ask", "outcome": "refused"}
    response = {"kind": "response", "action": action_id, "risk": CATALOGUE.get(
        action_id or "", {}).get("risk", ""), "detection": ask.get("detection") or {},
        "classified_by": "the catalogue's default (no AI: C1843)"}
    return flow_ops.apply(network, ask, (confirm or {}).get("hash", ""), actor=actor,
                          actor_verified=actor_verified, mode=mode, autonomous=autonomous,
                          response=response, driver=driver, **apply_kwargs)
