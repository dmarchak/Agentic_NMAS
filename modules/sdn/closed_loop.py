"""The SDN closed loop's named functions (PHASE8_PLAN 17.1 S13): what the loop reads, judges and
does, in one module, so a report can show their code. `collect_threat_data` (S4),
`classify_threat` (S7, the one AI step) and `respond_to_threat` (S8) are here.

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

**`classify_threat(network, detection, ...)`** asks a model, through the AI gateway, what a
detection the rules already found is: the lab's schema (`ThreatAssessment`: threat_detected,
threat_type, severity, affected_devices, recommended_action, reasoning), plus `action_id` from
the catalogue (or ``none``), its parameters and the evidence ids it cites. Its evidence is the
detection's evidence pack, its ``sdn`` section the topology class (sent only while the class is
allowed for the network). **The model proposes; code checks; a person or AUTO decides**: the
answer is checked against what was sent (`check_classification`), and a passing answer only
changes which catalogue action is proposed, which then goes through HITL or AUTO exactly as the
catalogue's default does. Two triggers reach it: the loop's (`loop.py`), a background call the
gateway refuses unless the feature ``sdn_classify`` is on for the network and within its caps
(PHASE8_PLAN 18.3; off by default), after which the loop proposes the catalogue's default for
the rule (`DEFAULT_ACTION`), said as chosen in code; and a person's Classify on a response
awaiting them (SDN › Responses).

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
from enum import Enum

from modules.ai.schemas import StrictModel, register

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

#: The task's pin (`profiles.TASKS`) and the background feature's name (`background.FEATURES`).
CLASSIFY_FEATURE = "sdn_classify"
CLASSIFY_PROMPT = ("sdn_classify", 1)
#: The classifier's steps, each named on its How it works page (modules/manual.py).
CLASSIFY_STEPS = (
    ("pack", "the detection's evidence pack, as kept when it fired, its hash checked: a pack "
             "changed since, or none kept, is refused and nothing is sent"),
    ("egress", "the flows and port rates are the topology class: sent only while the class is "
               "allowed for the network, else nothing is sent"),
    ("ask", "one recorded, capped call through the AI gateway: a person's Classify, or the "
            "loop's background call, which the gateway refuses unless the feature is on for "
            "the network and within its caps"),
    ("check", "in code: the action is the catalogue's and answers the detection's rule; the "
              "source is one the detection saw, the flow the one it names, the timeout within "
              "the network's ceiling; at least one evidence id is cited and every one cited was "
              "sent; every affected device named was in the evidence. One that fails is refused "
              "and nothing of it is used"),
    ("propose", "the classification kept with the response awaiting a person and its action "
                "proposed; nothing is sent: the response still goes through HITL (a person's "
                "confirm by hash) or AUTO (within its allowed risk)"),
)
#: What a response proposed with no AI classification says (the feature off, or no answer).
DEFAULT_WORDS = "the catalogue's default for the rule, chosen in code (no AI classification)"
#: The action the classifier names when no catalogue action should run.
NO_ACTION = "none"


def _canon(name) -> str:
    """A name as compared: an address in its compressed form, anything else lower-case."""
    import ipaddress

    text = str(name or "").strip()
    try:
        return ipaddress.ip_address(text).compressed
    except ValueError:
        return text.lower()


def _sdn_section(pack: dict) -> dict:
    from modules import evidence_pack as EP

    return next((s for s in (pack or {}).get("sections") or []
                 if s.get("name") == EP.SDN_SECTION), {})


def piece_id(piece: dict) -> str:
    """A piece's evidence id, the one scheme the classifier is sent and may cite (C1969): its
    own (a flow's, a port's, an earlier sighting's: `flow_ref`, `port_ref`), else one made from
    what it is, the detection ``detection:<rule>:<dpid>`` and the switch's coverage
    ``coverage:<dpid>`` (a section holds one of each). Never the pack's ``sdn:<n>``
    references: those are the pack's own (Explain's), and are not sent here."""
    if piece.get("id"):
        return str(piece["id"])
    kind = piece.get("kind") or "piece"
    if kind == "detection":
        return f"detection:{piece.get('rule') or ''}:{piece.get('dpid') or ''}"
    if kind == "sighting":
        return f"sighting:{piece.get('port') or ''}"
    return f"{kind}:{piece.get('dpid') or ''}"


def as_sent(piece: dict, ids: set) -> dict:
    """*piece* as the classifier reads it: its evidence id (`piece_id`) and nothing of the
    pack's reference scheme; the detection's own list of the evidence it rests on cut to the
    ids sent, the rest counted (C1969: a scan rests on some 260 flows and the section keeps the
    50 busiest, so the other ids named flows whose figures were never sent; they were most of
    the request's size)."""
    out = {k: v for k, v in piece.items() if k != "ref"}
    out["id"] = piece_id(piece)
    if piece.get("kind") == "detection":
        rests = list(piece.get("evidence") or [])
        out["evidence"] = [i for i in rests if i in ids]
        out["evidence_not_sent"] = len(rests) - len(out["evidence"])
    return out


def sent_evidence(section: dict) -> dict:
    """What the classifier is given of a pack's sdn section, and what its answer may name:
    ``{"detection", "pieces", "ids", "names", "sources"}``, each piece as sent (`as_sent`).
    *ids* every evidence id sent, exactly: each piece's (`piece_id`), the one scheme of what is
    sent and what is accepted (C1969); *names* what an affected device may be (the switch's
    DPID, every host address the evidence holds); *sources* the addresses the detection saw
    sending."""
    stored = list(section.get("pieces") or [])
    ids = {piece_id(p) for p in stored}
    pieces = [as_sent(p, ids) for p in stored]
    det = next((p for p in pieces if p.get("kind") == "detection"), {})
    names = {_canon(det.get("dpid"))} if det.get("dpid") else set()
    for addr in [det.get("source")] + list(det.get("targets") or []):
        if addr:
            names.add(_canon(addr))
    for p in pieces:
        if p.get("kind") == "flow":
            for k, v in (p.get("match") or {}).items():
                if k.startswith(("ipv4_", "ipv6_")) and isinstance(v, str) and "/" not in v:
                    names.add(_canon(v))
        if p.get("kind") == "sighting" and p.get("dst"):
            names.add(_canon(p["dst"]))
    names.discard("")
    return {"detection": det, "pieces": [p for p in pieces if p is not det], "ids": ids,
            "names": sorted(names), "sources": [s for s in [det.get("source")] if s]}


def check_classification(answer, detection: dict, sent: dict, limits: dict) -> tuple:
    """``(why, params)``: why the answer is refused ("" when it passes), and the action's
    parameters as `build_response` takes them. Compared in code with what was sent: the
    action is the catalogue's and answers the detection's rule; no threat proposes no action;
    the source is one the detection saw (its address compared in canonical form), the flow
    the one it names, the hard timeout within the network's ceiling; at least one evidence id
    is cited and every one cited was sent; every affected device was in the evidence."""
    action = answer.action_id.value
    p = answer.parameters
    refs = list(answer.evidence_refs or [])
    if not refs:
        return "it cites no evidence id: an answer must rest on what it was given", {}
    stray = [r for r in refs if r not in sent["ids"]]
    if stray:
        return (f"it cites {', '.join(stray[:3])}{' and more' if len(stray) > 3 else ''}, "
                "which the evidence sent does not hold"), {}
    names = set(sent["names"])
    unknown = [d for d in answer.affected_devices if _canon(d) not in names]
    if unknown:
        return (f"it names {', '.join(unknown[:3])} as affected, which the evidence does not "
                f"name (it names {', '.join(sent['names']) or 'nothing'})"), {}
    if not answer.threat_detected and action != NO_ACTION:
        return f"it finds no threat and proposes {action}", {}
    if action == NO_ACTION:
        return "", {}
    rule = (detection or {}).get("rule") or sent["detection"].get("rule")
    if rule not in CATALOGUE[action]["rules"]:
        return (f"{action} answers {', '.join(CATALOGUE[action]['rules'])}, not the "
                f"detection's rule {rule}"), {}
    params = {}
    if action in ("drop_source", "rate_limit_source"):
        seen = [_canon(s) for s in _sources(detection or {}) if _canon(s) in names] or \
            [_canon(s) for s in sent["sources"]]
        if _canon(p.source) not in seen:
            return (f"its source {p.source!r} is not one the detection saw "
                    f"({', '.join(seen) or 'none'})"), {}
        params["source"] = _canon(p.source)
    if action == "remove_flow":
        subject = ((detection or {}).get("subject") or {}).get("value")
        if p.flow != subject:
            return f"its flow {p.flow!r} is not the one the detection names ({subject})", {}
    ceiling = limits["sdn_response_max_seconds"]
    if p.hard_timeout:
        if not 1 <= p.hard_timeout <= ceiling:
            return (f"its hard timeout {p.hard_timeout} s is outside 1 to {ceiling} s (the "
                    "network's sdn_response_max_seconds)"), {}
        params["hard_timeout"] = p.hard_timeout
    if action == "rate_limit_source" and p.rate:
        if p.rate < 0 or p.burst < 0:
            return f"its rate {p.rate} and burst {p.burst} are not 0 or more", {}
        params.update(rate=p.rate, unit=p.unit.value, burst=p.burst)
    return "", params


def detection_pack(network: str, key: str) -> tuple:
    """``(pack or None, why)``: the evidence pack kept when detection *key* fired on
    *network*: the one its firing entry names, else (it resolved since) the newest SDN pack of
    the network whose alert is that detection."""
    from modules import evidence_pack as EP
    from modules.sdn import detect

    got = detect.read_state()
    pid = ""
    if got["state"] == "ok":
        net = (got["doc"].get("networks") or {}).get(network) or {}
        pid = ((net.get("firing") or {}).get(key) or {}).get("pack") or ""
    if pid:
        pack, _state, _err = EP.find(pid)
        if pack is not None:
            return pack, ""
    packs = EP.read()
    if packs["state"] == "unreadable":
        return None, f"the evidence packs cannot be read ({packs['error']})"
    for pack in reversed(packs["rows"]):
        if pack.get("store") != detect.STORE or pack.get("network") != network:
            continue
        alert = next((s for s in pack.get("sections") or [] if s.get("name") == "alert"), {})
        if any(p.get("fingerprint") == key for p in alert.get("pieces") or []):
            return pack, ""
    return None, f"no evidence pack was kept for the detection {key} on {network}"


def classify_threat(network: str, detection: dict, *, actor: str, trigger: dict, send=None,
                    today: str = None) -> dict:
    """S7: classify *detection* (`detect`'s) on *network* with AI, through the gateway, as
    *actor* with *trigger* (`triggers.person` for a person's Classify, `triggers.background`
    for the loop's call; the gateway refuses the latter unless the feature is on for the
    network). Its evidence is the pack kept when it fired (`detection_pack`); see
    `classify_pack` for the answer."""
    pack, why = detection_pack(network, (detection or {}).get("key") or "")
    if pack is None:
        return {"ok": False, "error": "no_pack", "detail": f"{why}; nothing was sent",
                "call_id": "", "cost_usd": 0.0}
    return classify_pack(network, detection, pack, actor=actor, trigger=trigger, send=send,
                         today=today)


def classify_pack(network: str, detection: dict, pack: dict, *, actor: str, trigger: dict,
                  send=None, today: str = None, prompt: tuple = CLASSIFY_PROMPT,
                  intact: bool = True) -> dict:
    """`classify_threat` with its pack in hand (a stored one, or a recorded case's,
    scripts/nmas-sdn-cases). In order (`CLASSIFY_STEPS`): the pack's hash (*intact* False is a
    case's section, never hashed); the classification marking and the topology class; the
    network's response limits; one call through the gateway; the answer checked in code
    (`check_classification`). The model proposes and never confirms.

    ``{"ok", "error", "detail", "call_id", "cost_usd", "classification", "action", "params",
    "pack_id"}``: *classification* what is shown and kept (the answer's fields, the call's id,
    model and cost); *action* the catalogue action proposed, or ``none``; *params* its checked
    parameters. Refused: *error* names the kind (the gateway's own, ``changed``,
    ``classified``, ``withheld``, ``limits`` or ``couldnt_classify``)."""
    from modules import evidence_pack as EP
    from modules.ai import calls, egress_classes, gateway, profiles
    from modules.sdn import flow_ops

    pack_id = (pack or {}).get("id") or ""
    out = {"ok": False, "error": "", "detail": "", "call_id": "", "cost_usd": 0.0,
           "classification": None, "action": "", "params": {}, "pack_id": pack_id}
    if intact and not EP.intact(pack):
        return dict(out, error="changed", detail="the evidence pack's hash does not match: it "
                    "changed since it was kept, so it is not classified; nothing was sent")
    marked = egress_classes.classification_marking(network)
    if marked:
        return dict(out, error="classified", detail=f"{network} carries the classification "
                    f"marking {marked!r}, which forces AI off; nothing was sent")
    gate = egress_classes.topology_allowed(network)
    if not gate["allowed"]:
        return dict(out, error="withheld", detail="the detection's flows and port rates are the "
                    f"topology class, and {gate['why']}; nothing was sent")
    limits = flow_ops.settings_of(network)
    if not limits["ok"]:
        return dict(out, error="limits", detail=f"{limits['error']}; nothing was sent")
    section = _sdn_section(pack)
    sent = sent_evidence(section)
    if not sent["detection"]:
        return dict(out, error="no_pack", detail="the pack holds no SDN detection to classify; "
                    "nothing was sent")
    schema = ThreatAssessment
    v = limits["values"]
    data = {
        "detection": json.dumps(sent["detection"], sort_keys=True, separators=(",", ":")),
        "evidence": json.dumps({"pieces": sent["pieces"], "counts": section.get("counts"),
                                "total_flows": section.get("total"),
                                "subset": bool(section.get("subset"))},
                               sort_keys=True, separators=(",", ":")),
        "names": json.dumps(sent["names"]),
        "limits": json.dumps({"hard_timeout_default_s": v["sdn_response_hard_timeout_seconds"],
                              "hard_timeout_max_s": v["sdn_response_max_seconds"],
                              "rate_limit_default": RATE_LIMIT_DEFAULT}, sort_keys=True),
    }
    context = {"catalogue": json.dumps(catalogue_for_ai(), sort_keys=True,
                                       separators=(",", ":"))}
    subject = {"kind": "sdn_detection", "id": (detection or {}).get("key") or "",
               "rule": (detection or {}).get("rule") or "", "devices": []}
    got = gateway.ask(CLASSIFY_FEATURE, tuple(prompt), schema, data, actor=actor,
                      trigger=trigger, context=context, send=send, today=today,
                      subject=subject, network=network)
    out.update(call_id=got.get("call_id", ""), cost_usd=got.get("cost_usd", 0.0))
    if not got["ok"]:
        return dict(out, error=got["error"], detail=got.get("detail", ""))
    answer = got["output"]
    why, params = check_classification(answer, detection, sent, v)
    links = {"page": "/v2/sdn/responses", "anchor": f"sdn-c-{subject['id']}"}
    if why:
        calls.record_use(got["call_id"], "refused by validation", actor=actor, detail=why,
                         links=links)
        return dict(out, error="couldnt_classify", why=why,
                    detail=f"couldn't classify: {why}; nothing of the answer is used")
    action = answer.action_id.value
    calls.record_use(got["call_id"], f"proposed: {action}" if action != NO_ACTION
                     else "shown: no catalogue action", actor=actor, links=links)
    shown = answer.model_dump(mode="json")
    shown.update(call_id=got["call_id"], cost_usd=got.get("cost_usd", 0.0),
                 model=profiles.TASKS[CLASSIFY_FEATURE]["model"],
                 trigger=(trigger or {}).get("kind", ""), params=params)
    return dict(out, ok=True, classification=shown, action=action, params=params)


def catalogue_for_ai() -> list:
    """The response catalogue as the classifier is given it: each action's id, what it does,
    its risk, the rules it answers and the parameters it takes; and ``none``."""
    takes = {"drop_source": ["source", "hard_timeout"],
             "rate_limit_source": ["source", "hard_timeout", "rate", "unit", "burst"],
             "remove_flow": ["flow"]}
    out = [{"action_id": k, "label": e["label"], "does": e["words"], "risk": e["risk"],
            "answers": list(e["rules"]), "parameters": takes[k]} for k, e in CATALOGUE.items()]
    out.append({"action_id": NO_ACTION, "label": "No catalogue action",
                "does": "nothing is proposed; a person decides", "risk": "none",
                "answers": list(DEFAULT_ACTION), "parameters": []})
    return out


def detection_frequency(network: str, now: float = None, days: int = 30) -> dict:
    """How often a detection rule fired on *network* (a list's folder name), for the
    background feature's estimate (`background.FEATURES`): ``{"per_day", "basis"}``, from the
    network's own detection history, the SDN transitions in the alert history over the last
    *days* days. Measured over the days the history covers (from its first SDN row in the
    window, at least one); with no SDN row for the network, unknown (None), never guessed.

    **Measured in whole UTC days, so the answer moves only when the measurement does
    (C1954):** the window starts at the UTC midnight *days* days before today's, and the span
    is the count of UTC midnights from the first SDN row's day to today's (at least one), so
    within a day the figures and the basis change only when a detection is recorded. The
    estimate's digest is taken over them (`background.estimate`), and an admin's Turn on is
    refused only when they moved; a span in fractions of a day grew with the clock and moved
    the digest within about three minutes. They can still move at a UTC midnight, once a
    day."""
    from modules import alert_history
    from modules.config import list_slug
    from modules.sdn import detect

    now = time.time() if now is None else now
    got = alert_history.read()
    if got["state"] == "unreadable":
        return {"per_day": None, "basis": ("unknown: the alert history cannot be read "
                                           f"({got['error']})")}
    today = int(now // 86400)
    since = (today - days) * 86400
    rows = [r for r in alert_history.transitions(got["rows"])
            if r.get("store") == detect.STORE
            and network in {list_slug(n) for n in r.get("networks") or []}]
    stamped = [(alert_history.epoch(r.get("at")), r) for r in rows]
    stamped = [(t, r) for t, r in stamped if t is not None and t >= since]
    if not stamped:
        return {"per_day": None, "basis": (f"unknown: no SDN detection is in {network}'s alert "
                                           f"history in the last {days} days (the loop has not "
                                           "run there, or nothing fired)")}
    fired = sum(1 for _t, r in stamped if r.get("to") == "condition")
    first = min(t for t, _r in stamped)
    span = max(today - int(first // 86400), 1)
    return {"per_day": round(fired / span, 3),
            "basis": (f"measured: {fired} detection(s) fired on {network} over the "
                      f"{span} whole UTC day(s) its alert history covers since "
                      f"{_iso(first)}")}


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
                      classified_by: str = DEFAULT_WORDS, driver=None, **apply_kwargs) -> dict:
    """S8: answer *detection* with a catalogue action, through the flow-operation core.

    Without *confirm*: the PREVIEW, writing nothing: ``{"ok", "error", "action", "risk",
    "params", "ask", "plan"}``, the plan carrying the exact requests and their hash.
    With *confirm* ``{"ask", "hash"}`` (the preview's ask, carried back unchanged, and the hash
    the person confirmed): the APPLY (`flow_ops.apply`), as *actor*, in *mode* (``hitl``: a
    person's confirm; ``auto``: *autonomous* names the setting and its reason), recorded with
    the detection it answers and *classified_by*, who chose the action: the catalogue's
    default in code, or the AI call that proposed it (`classified_words`)."""
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
        "classified_by": classified_by or DEFAULT_WORDS}
    return flow_ops.apply(network, ask, (confirm or {}).get("hash", ""), actor=actor,
                          actor_verified=actor_verified, mode=mode, autonomous=autonomous,
                          response=response, driver=driver, **apply_kwargs)


def classified_words(classification: dict, action: str) -> str:
    """Who chose *action* for a response: the AI call that proposed it (its id and model), when
    *classification* is kept and proposes that action; else the catalogue's default."""
    c = classification or {}
    if c.get("call_id") and c.get("action_id") == action:
        return f"proposed by AI call {c['call_id']} ({c.get('model', '')}), checked in code"
    return DEFAULT_WORDS


# ───────────────────────────────────────────────────────────────────────────── classify's schema

class ThreatType(str, Enum):
    port_scan = "port_scan"
    flood = "flood"
    unauthorised_flow = "unauthorised_flow"
    other = "other"
    none = "none"


class Severity(str, Enum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


#: The catalogue's actions and ``none``, as the classifier may name them.
ActionId = Enum("ActionId", {a: a for a in (*CATALOGUE, NO_ACTION)}, type=str)


class RateUnit(str, Enum):
    kbps = "kbps"
    pktps = "pktps"


class Parameters(StrictModel):
    """The action's parameters: the source address (drop and rate-limit), the flow's evidence
    id (remove), the hard timeout in seconds (0: the network's default), the rate (0: the
    catalogue's default rate and burst), its unit and its burst."""
    source: str
    flow: str
    hard_timeout: int
    rate: int
    unit: RateUnit
    burst: int


@register("sdn_classify", 1)
class ThreatAssessment(StrictModel):
    """The lab's schema (threat_detected, threat_type, severity, affected_devices,
    recommended_action, reasoning), the reasoning first, then the catalogue action, its
    parameters and the evidence ids it rests on."""
    reasoning: str
    threat_detected: bool
    threat_type: ThreatType
    severity: Severity
    affected_devices: list[str]
    recommended_action: str
    action_id: ActionId
    parameters: Parameters
    evidence_refs: list[str]
