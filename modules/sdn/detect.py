"""SDN detection rules (PHASE8_PLAN 17.1 S6): deterministic, in code, never AI. Each rule takes
`closed_loop.collect_threat_data`'s answer and returns detections; `observe` runs the three
over one collection, keeps what they need between collections, and makes each detection an
alert in Mercury's alert stream with an evidence pack, so Explain works on it unchanged.

**The rules** (thresholds per network, `thresholds`; settings_schema, docs/SETTINGS.md):
- **Scan** (`scan`). Where a switch's flows are L4 (its ``coverage`` says ``scan_by_ports``):
  the distinct destination ports (``tcp/22``, ``udp/53``: TCP's and UDP's apart) each source
  address reached on that switch within the window (`sdn_scan_ports`, 20, in
  `sdn_scan_window_seconds`, 60). A flow is a sighting whether or not it counted a packet: a
  reactive application installs a flow on a SYN's packet-in, and that packet is sent by the
  controller, never counted by the flow. Sightings are kept between collections and dropped
  past the window, so a scan spread over several collections is counted whole, and a scan
  that stopped resolves when its sightings age out. **Confidence high.** Where the flows are
  not L4 (L3, L2, none, or not read): **the fallback**, each port receiving at least
  `sdn_scan_fallback_pps` packets a second (100) over the collection's sample, **confidence
  lower**, saying why (the switch's coverage words: its flows cannot show destination ports,
  and a rate alone cannot tell a scan from other heavy traffic).
- **Flood** (`flood`): a port's received packet rate at or above `sdn_flood_factor` (5) times
  its baseline, held for `sdn_flood_window_seconds` (30): each collection over it since the
  first; one not over clears it. Received (``rx``), the switch's view of what the attached
  host sends: the source side, which a response acts on. A port with no baseline yet reads
  "no baseline yet", never a detection.
- **Unauthorised flow** (`unauthorised`): every flow `flow_intent.classify` calls
  ``unauthorised`` on a switch whose table was read whole. With the flow intent unreadable,
  nothing is judged, and the answer says so.

**The source of a port's detection** (C2002; `port_source`). A flood, and the scan rule's
packet-rate fallback, judge a port, not a source. Their source is the one address the flows
entering that port name; where those flows name none (they match MAC addresses only, as a
reactive application's L2 pairs do), it is the host the controller's topology lists on that
port (the SDN reader's stored read, `topology.stored`), by its address (its first IPv4, else
its first IPv6 that is not link-local), the detection's ``source_from`` saying how it was
found ("from the controller's topology: the one host on port 2, ..."). A topology that cannot
resolve the port to exactly one host leaves the source unnamed, and ``source_from`` says why
and in which state (`SOURCE_STATES`): none listed there, a host with no address to match,
port of a link to another switch (the source is not attached there), the topology not read
now, or several hosts, each named with its address, which a person chooses among on the
card (SDN › Responses' source picker; `closed_loop.build_response` refuses any other). A host
listed with no address beside one with an address does not make the port ambiguous: it
cannot be matched, and it is named. Where the flows name several sources, the detection's
``sources`` lists them and the source stays unnamed, as before. A rule called with no
topology (*topo* None: a recorded case's rebuild) names nothing from it and adds no
``source_from``. On a link port (state ``link``) the detection also keeps ``link_sources``
(`link_sources`): each source MAC address its entering flows match, with the addresses the
topology lists for that MAC's host; candidates, never the source, by which `incidents` joins
it to the attack's incident (C2106). It is not in the evidence piece the classifier is sent.

**The baseline** (`baseline_of`, `update_baseline`): per port, the median of the received
packet rate over the last `BASELINE_SAMPLES` (12) earlier collections. A port has one once
`BASELINE_READY` (5) collections have sampled it, so it is ready five of the loop's intervals
after its first collection. A sample is taken only while the port is not over its flood
threshold, so a flood never becomes its own baseline. A baseline not sampled for
`BASELINE_STALE_SECONDS` (an hour: the loop stopped) is dropped and starts again. An idle
port's median is 0, and every packet is infinitely many times 0, so a baseline below
`BASELINE_FLOOR_PPS` counts as that floor.

**What a detection carries:** its rule, its key (the rule, the network, the connection, the
switch and its subject: a source address, a port or a flow), the switch (DPID) and connection,
the source and target addresses or the port, the measurement and the threshold it was held
against (each naming its value, its unit, its window and the setting), its confidence and why,
and the evidence ids it rests on (`closed_loop.flow_ref`, `port_ref`): what the classifier
(S7) cites. An unauthorised flow's also carries, in code (C2004, C2021): each Mercury flow it
displaced (``displaced``, `flow_intent.displaced`: recorded, not installed, at its table,
priority and match), each a citable piece with its own id (`displaced_piece`) among the
evidence; and its ``effect`` (`flow_intent.effect`: forwards, diverts, drops, shadows, lifts or
unknown, in words, with the flows it rests on), said in its words too. Its severity is the
classifier's above the floor its effect sets in code (`closed_loop.SEVERITY_FLOOR`, the
operator's ruling of 2026-10-28): a lower rating is raised, the model's own kept beside it.

**The state** (`STATE_FILE`, ``sdn_detect.json`` in the data folder): one document, per
network the baselines, the ports over their flood threshold and since when, the scan
sightings, the detections firing (each with its alert instance and its pack), and the alert
transitions not yet recorded. One read-modify-write per collection under the store's
cross-process lock (`filestore.PathLock`), written atomically and owner-only
(`filestore.write_atomic`); one that exists and cannot be read refuses the write and is kept
aside (`filestore.read_json_for_write`), never read as empty. An older collection than the one
last judged is refused.

**Each detection is an alert** (`observe`), in the reader's instance shape, the store ``sdn``:
- **it fires** when a detection is first seen: a transition recorded in the alert history
  (`alert_history.from_detections`, keyed as the reader keys its own) and its evidence pack
  built from the collection in hand (`evidence_pack.build_detection`: the alert, the device
  absent, and the ``sdn`` section of the flows and port rates it rests on, captured);
- **it resolves** when a collection that judged its subject no longer shows it: a resolve
  recorded. A subject not judged (its switch's flows or its port not read) keeps it firing,
  counted as not judged: absent and unread are different;
- a transition the history could not take is kept and offered again with the next
  collection (the history keeps a transition once, by its key).
The Alerts tab draws the detections firing (`evidence_pack.sdn_firing`, `firing`), and History
their episodes. ``changed`` in the answer says the loop (S10) is to announce ``alerts``.

**Fleet scale.** A job calls `observe` (the loop, S10), never a request handler: the rules walk
the collection once each, and one state document is read and written per collection.
"""

import copy
import hashlib
import ipaddress
import json
import logging
import os
import statistics
import time

log = logging.getLogger(__name__)

#: The alert source: every transition, pack and card of a detection names it.
STORE = "sdn"
STATE_FILE = "sdn_detect.json"
SCHEMA = 1
RULES = ("scan", "flood", "unauthorised_flow")
#: Each rule's alert, as the Alerts tab and History name it.
TITLES = {"scan": "SDN scan", "flood": "SDN flood",
          "unauthorised_flow": "SDN unauthorised flow"}
RULE_UIDS = {"scan": "sdn-scan", "flood": "sdn-flood",
             "unauthorised_flow": "sdn-unauthorised-flow"}
#: The thresholds, per network (`modules/settings_schema.py`), each with its default.
THRESHOLDS = {"sdn_scan_ports": 20, "sdn_scan_window_seconds": 60, "sdn_scan_fallback_pps": 100,
              "sdn_flood_factor": 5, "sdn_flood_window_seconds": 30}
CONFIDENCE = ("high", "lower")
#: The baseline: a median over this many earlier collections, ready after this many.
BASELINE_SAMPLES = 12
BASELINE_READY = 5
#: A baseline not sampled for this long is dropped (the loop stopped): an hour.
BASELINE_STALE_SECONDS = 3600
#: An idle port's baseline counts as at least this (packets a second), so a quiet port is not
#: flooded by its first ping. Not measured: the operator's first run of the slice measures
#: normal traffic (C1837).
BASELINE_FLOOR_PPS = 10.0
#: The most flows an evidence pack's ``sdn`` section keeps for one detection; the rest counted.
SECTION_FLOWS = 50
#: At most this many earlier sightings in a pack's section, the newest first (C2006), as the
#: flows are bounded: a re-fired scan's sightings had taken its request past the task's bound.
SECTION_SIGHTINGS = 50


class Refused(RuntimeError):
    """A collection `observe` will not judge, naming why."""


# ───────────────────────────────────────────────────────────────────────────── thresholds

def thresholds(network: str) -> dict:
    """*network*'s thresholds: ``{"ok", "error", "values"}``. A value that cannot be read, or
    is not a positive number, refuses the run, naming it: rules held against a guessed
    threshold would look like rules that ran."""
    from modules import list_settings

    values = {}
    for key, default in THRESHOLDS.items():
        try:
            got = list_settings.value(network, key, default)
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            return {"ok": False, "values": {},
                    "error": f"{network}'s {key} could not be read ({type(exc).__name__}: "
                             f"{exc}), so no rule was run"}
        # A window of 0 fires a flood at its first collection over; every other threshold is
        # positive.
        zero_allowed = key == "sdn_flood_window_seconds"
        if isinstance(got, bool) or not isinstance(got, (int, float)) or got < 0 or \
                (got == 0 and not zero_allowed):
            return {"ok": False, "values": {},
                    "error": f"{network}'s {key} is {got!r}, not a number a rule can hold a "
                             "measurement against, so no rule was run"}
        values[key] = got
    return {"ok": True, "error": "", "values": values}


# ───────────────────────────────────────────────────────────────────────────── helpers

def _epoch(text) -> float:
    from modules import alert_history

    got = alert_history.epoch(text)
    return float(got) if got is not None else None


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _switches(collected: dict):
    for c in collected.get("controllers") or []:
        for s in c.get("switches") or []:
            yield c, s


def _address(match: dict, side: str):
    """A host address the match names on *side* (``src``, ``dst``), canonical; None for none
    or a prefix (a prefix is not one host)."""
    for field in (f"ipv4_{side}", f"ipv6_{side}"):
        value = (match or {}).get(field)
        if isinstance(value, str) and "/" not in value:
            try:
                return ipaddress.ip_address(value.strip()).compressed
            except ValueError:
                return None
    return None


def _dst_port(match: dict):
    """``tcp/<n>`` or ``udp/<n>`` for a match naming a transport destination port."""
    for field, proto in (("tcp_dst", "tcp"), ("udp_dst", "udp")):
        value = (match or {}).get(field)
        if value is None:
            continue
        try:
            return f"{proto}/{int(str(value).strip())}"
        except ValueError:
            return f"{proto}/{value}"
    return None


def _in_port(match: dict):
    value = (match or {}).get("in_port")
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


#: The states of a port detection's ``source_from`` (`port_source`): ``named`` the one host's
#: address taken; ``several`` hosts a person chooses among; the rest leave it unnamed, with
#: nothing to choose (``unread`` may resolve when the topology is read again).
SOURCE_STATES = ("named", "several", "none", "no_address", "link", "unread")


def host_address(host: dict) -> str:
    """The address a response matches a topology host by: its first IPv4, else its first IPv6
    that is not link-local (a link-local address is not a source a flow on another link can
    match), canonical; "" for none."""
    for value in list(host.get("ipv4") or []) + list(host.get("ipv6") or []):
        try:
            addr = ipaddress.ip_address(str(value).strip())
        except ValueError:
            continue
        if addr.is_unspecified or (addr.version == 6 and addr.is_link_local):
            continue
        return addr.compressed
    return ""


def _host_words(h: dict) -> str:
    return f"{h['address']} ({h['mac']})" if h.get("mac") else h["address"]


def port_source(topo, connection: str, dpid, port) -> dict:
    """Which host the controller's topology lists on switch *dpid*'s *port* (C2002), from *topo*
    (`topology.stored`'s answer: ``{"state", "why", "controllers": [{"name", "state", "why",
    "read_at", "hosts", "links"}]}``) for *connection*: ``{"how": "topology", "state", "port",
    "source", "hosts", "read_at", "words"}``. *state* one of `SOURCE_STATES`; *source* the one
    host's address when ``named``, else None; *hosts* every host on the port with an address
    to match (``{"mac", "address"}``), the choices when ``several``; *words* how it was found,
    or why it was not."""
    from modules.sdn.drivers.base import parse_dpid

    out = {"how": "topology", "state": "unread", "port": port, "source": None, "hosts": [],
           "read_at": "", "words": ""}
    try:
        port = int(port)
        dpid = parse_dpid(dpid)
    except (TypeError, ValueError):            # parse_dpid's SpecError is a ValueError
        out.update(state="none", words=f"port {port!r} is not a switch port number")
        return out
    out["port"] = port
    topo = topo or {}
    ctl = next((c for c in topo.get("controllers") or [] if c.get("name") == connection), None)
    if topo.get("state") != "read":
        why = topo.get("why") or topo.get("state") or "no answer"
    elif ctl is None:
        why = f"the SDN reader holds no topology for {connection}"
    elif ctl.get("state") != "read":
        why = ctl.get("why") or ctl.get("state") or "no answer"
    else:
        why = ""
    if why:
        out["words"] = f"not named: the controller's topology could not be read ({why})"
        return out
    out["read_at"] = ctl.get("read_at") or ""
    for link in ctl.get("links") or []:
        for end, other in (("src", "dst"), ("dst", "src")):
            e, o = link.get(end) or {}, link.get(other) or {}
            try:
                here = (parse_dpid(e.get("dpid")), int(e.get("port_no")))
            except (TypeError, ValueError):     # a malformed end is skipped
                continue
            if here == (dpid, port):
                peer = o.get("dpid_hex") or o.get("dpid")
                out.update(state="link", words=(
                    f"not named: port {port} is a link to switch {peer}, so the source is not "
                    "attached here; the switch it enters by names it"))
                return out
    on = []
    for h in ctl.get("hosts") or []:
        try:
            if (parse_dpid(h.get("dpid")), int(h.get("port_no"))) != (dpid, port):
                continue
        except (TypeError, ValueError):        # a malformed host is skipped
            continue
        on.append(h)
    if not on:
        out.update(state="none",
                   words=f"not named: the controller's topology lists no host on port {port}")
        return out
    hosts, bare = [], []
    for h in on:
        addr = host_address(h)
        mac = str(h.get("mac") or "").lower()
        if addr:
            if addr not in [x["address"] for x in hosts]:
                hosts.append({"mac": mac, "address": addr})
        else:
            bare.append(mac)
    out["hosts"] = hosts
    also = (f"; {', '.join(bare)} also listed there, with no address to match" if bare and hosts
            else "")
    if not hosts:
        out.update(state="no_address", words=(
            f"not named: the controller's topology lists {', '.join(bare)} on port {port}, "
            "with no address to match"))
    elif len(hosts) == 1:
        out.update(state="named", source=hosts[0]["address"], words=(
            f"from the controller's topology: the one host on port {port}, "
            f"{_host_words(hosts[0])}{also}"))
    else:
        out.update(state="several", words=(
            f"not named: the controller's topology lists {len(hosts)} hosts on port {port} ("
            + ", ".join(_host_words(h) for h in hosts) + f"){also}"))
    return out


def _flow_sources(entering: list) -> list:
    """Each source address the flows entering a port name, in the flows' order."""
    out = []
    for f in entering:
        src = _address(f.get("match"), "src")
        if src and src not in out:
            out.append(src)
    return out


def _port_detection_source(entering: list, topo, connection: str, dpid, port) -> tuple:
    """``(source, sources, extra)`` for a detection on *port*: the flows' one source; else,
    with *topo* given, the topology's (`port_source`), carried as ``source_from`` in *extra*."""
    sources = _flow_sources(entering)
    if sources:
        return (sources[0] if len(sources) == 1 else None), sources, {}
    if topo is None:
        return None, sources, {}
    found = port_source(topo, connection, dpid, port)
    extra = {"source_from": {
        k: found[k] for k in ("how", "state", "port", "hosts", "read_at", "words")}}
    if found["state"] == "link":
        # C2106: a link port names no source, but its flows say whose traffic arrives on it;
        # what `incidents` joins the incident of that host's own port by (never sent: the
        # evidence piece keeps `source_from` only).
        extra["link_sources"] = link_sources(entering, topo, connection)
    return found["source"], sources, extra


def link_sources(entering: list, topo, connection: str) -> list:
    """Whose traffic the flows *entering* a link port carry (C2106): each source MAC address
    they match (``eth_src``, lower-case, in the flows' order: most packets first), with every
    address the controller's topology (*topo*, `topology.stored`'s) lists for the host of that
    MAC on *connection*: ``[{"mac", "addresses"}]``, *addresses* [] when no host is listed
    with it. A link port carries every host behind it, so this names candidates, never the
    source: `incidents.group` joins the one incident among them, or none."""
    hosts = {}
    ctl = next((c for c in (topo or {}).get("controllers") or []
                if c.get("name") == connection), None) or {}
    for h in ctl.get("hosts") or []:
        mac = str(h.get("mac") or "").lower()
        for value in list(h.get("ipv4") or []) + list(h.get("ipv6") or []):
            try:
                addr = ipaddress.ip_address(str(value).strip())
            except ValueError:
                continue
            if not addr.is_unspecified and addr.compressed not in hosts.setdefault(mac, []):
                hosts[mac].append(addr.compressed)
    out = []
    for f in entering:
        mac = str((f.get("match") or {}).get("eth_src") or "").strip().lower()
        if mac and "/" not in mac and mac not in [x["mac"] for x in out]:
            out.append({"mac": mac, "addresses": list(hosts.get(mac) or [])})
    return out


def flows_scope(connection: str, dpid_hex: str) -> str:
    """What a flow rule judges: one switch's flow table."""
    return f"flows:{connection}:{dpid_hex}"


def detection_key(rule: str, network: str, connection: str, dpid_hex: str, subject) -> str:
    return hashlib.sha256(json.dumps([rule, network, connection, dpid_hex, subject],
                                     default=str).encode()).hexdigest()[:20]


def _detection(rule: str, collected: dict, ctl: dict, sw: dict, *, subject: tuple, scope: str,
               words: str, measurement: dict, threshold: dict, confidence: str,
               confidence_why: str, evidence: list, source=None, targets=(), port=None,
               **extra) -> dict:
    assert rule in RULES and confidence in CONFIDENCE, (rule, confidence)
    network, conn = collected.get("network") or "", ctl.get("connection") or ""
    return {"rule": rule, "title": TITLES[rule],
            "key": detection_key(rule, network, conn, sw["dpid_hex"], list(subject)),
            "network": network, "connection": conn, "dpid": sw["dpid"],
            "dpid_hex": sw["dpid_hex"], "subject": {"kind": subject[0], "value": subject[1]},
            "scope": scope, "source": source, "targets": list(targets), "port": port,
            "measurement": measurement, "threshold": threshold, "confidence": confidence,
            "confidence_why": confidence_why, "evidence": list(evidence), "words": words,
            "at": collected.get("collected_at") or "", **extra}


# ───────────────────────────────────────────────────────────────────────────── scan

def scan(collected: dict, values: dict, seen: dict = None, topo: dict = None) -> dict:
    """The scan rule over one collection: ``{"detections", "judged", "seen", "notes"}``.
    *values* the thresholds (`thresholds`' ``values``); *seen* the sightings kept from earlier
    collections (``{key: {"connection", "dpid_hex", "source", "ports": {port: {"at", "id",
    "dst"}}}}``), answered updated and pruned to the window; *topo* the controllers' stored
    topology (`topology.stored`), where a fallback's port names its source when its flows name
    none (`port_source`); None names none from it."""
    at = _epoch(collected.get("collected_at"))
    need, window = values["sdn_scan_ports"], values["sdn_scan_window_seconds"]
    pps = values["sdn_scan_fallback_pps"]
    seen = copy.deepcopy(seen or {})
    detections, judged, notes = [], set(), []
    by_ports = {}
    for ctl, sw in _switches(collected):
        conn, dh = ctl.get("connection") or "", sw["dpid_hex"]
        cov = sw.get("coverage")
        if cov and cov.get("scan_by_ports"):
            judged.add(flows_scope(conn, dh))
            by_ports[(conn, dh)] = (ctl, sw)
            unsourced = 0
            for f in sw.get("flows") or []:
                match = f.get("match") or {}
                port = _dst_port(match)
                if port is None:
                    continue
                src = _address(match, "src")
                if src is None:
                    unsourced += 1
                    continue
                entry = seen.setdefault(f"{conn}|{dh}|{src}", {
                    "connection": conn, "dpid_hex": dh, "source": src, "ports": {}})
                entry["ports"][port] = {"at": at, "id": f.get("id"),
                                        "dst": _address(match, "dst")}
            if unsourced:
                notes.append(f"{unsourced} L4 flow(s) on {dh} ({conn}) name no single source "
                             "address and were not counted")
            continue
        # The fallback: the flows cannot show destination ports.
        why = (cov["words"] if cov else
               "this switch's flows could not be read, so destination ports cannot be counted")
        for p in sw.get("ports") or []:
            if "rx_pps" not in p:
                continue
            judged.add(p["id"])
            if p["rx_pps"] < pps:
                continue
            entering = _entering(sw, p["port_no"])
            source, _sources, named = _port_detection_source(entering, topo, conn, sw["dpid"],
                                                             p["port_no"])
            detections.append(_detection(
                "scan", collected, ctl, sw, subject=("port", p["port_no"]), scope=p["id"],
                port=p["port_no"], source=source,
                words=(f"port {p['port_no']} of switch {dh} ({conn}) received {p['rx_pps']:g} "
                       f"packets a second over {sw['sample'].get('elapsed_s')} s, at or above "
                       f"the scan fallback's {pps:g} (sdn_scan_fallback_pps); lower "
                       "confidence: " + why),
                measurement={"what": "packets received a second", "value": p["rx_pps"],
                             "unit": "pps", "sample_s": sw["sample"].get("elapsed_s")},
                threshold={"what": "the scan fallback's rate", "value": pps, "unit": "pps",
                           "setting": "sdn_scan_fallback_pps"},
                confidence="lower",
                confidence_why=(why + "; a rate alone cannot tell a scan from other heavy "
                                "traffic"),
                evidence=[p["id"]] + [f["id"] for f in entering],
                basis="rate", **named))
    # Prune every sighting past the window, then count each source on the switches judged.
    for key in list(seen):
        entry = seen[key]
        entry["ports"] = {k: v for k, v in entry["ports"].items()
                          if at is not None and at - v["at"] <= window}
        if not entry["ports"]:
            del seen[key]
            continue
        held = by_ports.get((entry["connection"], entry["dpid_hex"]))
        if held is None or len(entry["ports"]) < need:
            continue
        ctl, sw = held
        ports = entry["ports"]
        now_ids = {f.get("id") for f in sw.get("flows") or []}
        targets = sorted({v["dst"] for v in ports.values() if v["dst"]})
        detections.append(_detection(
            "scan", collected, ctl, sw, subject=("source", entry["source"]),
            scope=flows_scope(entry["connection"], entry["dpid_hex"]),
            source=entry["source"], targets=targets,
            words=(f"{entry['source']} reached {len(ports)} distinct destination ports on "
                   f"switch {entry['dpid_hex']} ({entry['connection']}) in the last {window} s, "
                   f"at or above the threshold of {need} (sdn_scan_ports)"),
            measurement={"what": "distinct destination ports from one source",
                         "value": len(ports), "unit": "ports", "window_s": window,
                         "in_this_collection": sum(v["id"] in now_ids for v in ports.values()),
                         "ports": sorted(ports, key=_port_order)},
            threshold={"what": "the scan's ports in its window", "value": need,
                       "unit": "ports", "window_s": window, "setting": "sdn_scan_ports",
                       "window_setting": "sdn_scan_window_seconds"},
            confidence="high",
            confidence_why=("this switch's flows match transport ports (L4), so each "
                            "destination port the source reached is a flow of its own"),
            evidence=sorted({v["id"] for v in ports.values() if v["id"]}),
            basis="ports",
            sightings=[dict(v, port=k) for k, v in sorted(ports.items(),
                                                          key=lambda kv: _port_order(kv[0]))]))
    return {"detections": detections, "judged": judged, "seen": seen, "notes": notes}


def _port_order(port: str):
    proto, _, number = port.partition("/")
    return (proto, int(number) if number.isdigit() else 0, number)


def _entering(sw: dict, port_no) -> list:
    """The switch's flows matching traffic arriving on *port_no*, most packets first."""
    flows = [f for f in sw.get("flows") or [] if _in_port(f.get("match")) == port_no]
    return sorted(flows, key=lambda f: -(f.get("packet_count") or 0))


# ───────────────────────────────────────────────────────────────────────────── the baseline

def baseline_of(baseline: dict, port_id: str, at: float = None) -> tuple:
    """``(median packets a second or None, samples held)``: *port_id*'s baseline, None until
    it holds `BASELINE_READY` samples, or when it was last sampled past
    `BASELINE_STALE_SECONDS` before *at*."""
    entry = (baseline or {}).get(port_id)
    if not entry:
        return None, 0
    if at is not None and at - entry.get("at", 0) > BASELINE_STALE_SECONDS:
        return None, 0
    samples = entry.get("samples") or []
    if len(samples) < BASELINE_READY:
        return None, len(samples)
    return round(statistics.median(samples[-BASELINE_SAMPLES:]), 3), len(samples)


def update_baseline(baseline: dict, collected: dict, exclude=()) -> dict:
    """*baseline* with this collection's received rate added for every port it measured,
    but those in *exclude* (over their flood threshold), each kept to the last
    `BASELINE_SAMPLES`; a stale entry starts again, and one unsampled past staleness is
    dropped."""
    at = _epoch(collected.get("collected_at"))
    out = copy.deepcopy(baseline or {})
    for _ctl, sw in _switches(collected):
        for p in sw.get("ports") or []:
            if "rx_pps" not in p or p["id"] in exclude:
                continue
            entry = out.get(p["id"])
            if not entry or at - entry.get("at", 0) > BASELINE_STALE_SECONDS:
                entry = {"samples": []}
            entry["samples"] = (entry["samples"] + [p["rx_pps"]])[-BASELINE_SAMPLES:]
            entry["at"] = at
            out[p["id"]] = entry
    return {k: v for k, v in out.items() if at - v.get("at", 0) <= BASELINE_STALE_SECONDS}


# ───────────────────────────────────────────────────────────────────────────── flood

def flood(collected: dict, baseline: dict, values: dict, over: dict = None,
          topo: dict = None) -> dict:
    """The flood rule over one collection: ``{"detections", "judged", "over", "pending",
    "no_baseline"}``. *baseline* the earlier collections' (`baseline_of`); *over* each port
    over its threshold and since when (epoch), answered updated; *topo* the controllers' stored
    topology (`topology.stored`), where the port names its source when its flows name none
    (`port_source`); None names none from it."""
    at = _epoch(collected.get("collected_at"))
    factor, window = values["sdn_flood_factor"], values["sdn_flood_window_seconds"]
    over = dict(over or {})
    detections, judged, pending, no_baseline = [], set(), [], []
    for ctl, sw in _switches(collected):
        conn, dh = ctl.get("connection") or "", sw["dpid_hex"]
        for p in sw.get("ports") or []:
            if "rx_pps" not in p:
                continue
            pid, rate = p["id"], p["rx_pps"]
            judged.add(pid)
            median, samples = baseline_of(baseline, pid, at)
            if median is None:
                over.pop(pid, None)
                no_baseline.append({"port": pid, "samples": samples, "needed": BASELINE_READY,
                                    "words": f"no baseline yet ({samples} of {BASELINE_READY} "
                                             "earlier collections)"})
                continue
            limit = round(factor * max(median, BASELINE_FLOOR_PPS), 3)
            if rate < limit:
                over.pop(pid, None)
                continue
            since = over.setdefault(pid, at)
            held = round(at - since, 3)
            measured = {"what": "packets received a second", "value": rate, "unit": "pps",
                        "sample_s": sw["sample"].get("elapsed_s"), "held_s": held,
                        "since": _iso(since)}
            limit_said = {"what": "the factor times the port's baseline", "value": limit,
                          "unit": "pps", "factor": factor, "baseline_pps": median,
                          "baseline_samples": min(samples, BASELINE_SAMPLES),
                          "floor_pps": BASELINE_FLOOR_PPS, "window_s": window,
                          "setting": "sdn_flood_factor",
                          "window_setting": "sdn_flood_window_seconds"}
            if held < window:
                pending.append({"port": pid, "measurement": measured, "threshold": limit_said,
                                "words": f"over its threshold for {held:g} s of {window} s"})
                continue
            entering = _entering(sw, p["port_no"])
            source, sources, named = _port_detection_source(entering, topo, conn, sw["dpid"],
                                                            p["port_no"])
            detections.append(_detection(
                "flood", collected, ctl, sw, subject=("port", p["port_no"]), scope=pid,
                port=p["port_no"], source=source,
                targets=sorted({a for f in entering for a in [_address(f.get("match"), "dst")]
                                if a}),
                words=(f"port {p['port_no']} of switch {dh} ({conn}) received {rate:g} packets "
                       f"a second, at or above {factor:g}x its baseline of {median:g} "
                       f"({limit:g}), for {held:g} s since {_iso(since)} (the window is "
                       f"{window} s)"),
                measurement=measured, threshold=limit_said, confidence="high",
                confidence_why=("the port's own counters, read twice a stated interval apart, "
                                "against its own earlier collections"),
                evidence=[pid] + [f["id"] for f in entering], basis="rate", since=since,
                sources=sources, **named))
    return {"detections": detections, "judged": judged, "over": over, "pending": pending,
            "no_baseline": no_baseline}


# ───────────────────────────────────────────────────────────────────────────── unauthorised

def unauthorised(collected: dict, intent: dict, now: float = None) -> dict:
    """The unauthorised-flow rule: ``{"detections", "judged", "error"}``, each flow
    `flow_intent.classify` calls unauthorised on a switch whose table was read; *intent*
    `flow_intent.intent`'s answer. An unreadable intent judges nothing, and says so."""
    from modules.sdn import flow_intent

    if (intent or {}).get("state") != "ok":
        return {"detections": [], "judged": set(),
                "error": ("the flow intent could not be read "
                          f"({(intent or {}).get('error') or 'no answer'}), so no flow was "
                          "judged authorised or not")}
    detections, judged = [], set()
    for ctl, sw in _switches(collected):
        if sw.get("active_flows") is None:
            continue
        conn, dh = ctl.get("connection") or "", sw["dpid_hex"]
        judged.add(flows_scope(conn, dh))
        connection = {"name": conn, "own_cookies": ctl.get("own_cookies") or []}
        got = flow_intent.classify(sw.get("flows") or [], connection, intent,
                                   read_switches=[sw["dpid"]], now=now)
        records = len([r for r in intent.get("flows") or [] if r.get("connection") == conn])
        for f in got["flows"]:
            if f["owner"] != "unauthorised":
                continue
            match = f.get("match") or {}
            moved = [displaced_piece(conn, dh, r)
                     for r in flow_intent.displaced(f, got["records"])]
            effect = flow_intent.effect(f, got["flows"], moved)
            detections.append(_detection(
                "unauthorised_flow", collected, ctl, sw, subject=("flow", f["id"]),
                scope=flows_scope(conn, dh), source=_address(match, "src"),
                targets=[a for a in [_address(match, "dst")] if a],
                port=_in_port(match) if "in_port" in match else None,
                words=(f"a flow on switch {dh} ({conn}), cookie "
                       f"{flow_intent.cookie_hex(f.get('cookie'))}, priority "
                       f"{f.get('priority')}, actions {flow_intent.action_words(f.get('actions'))}"
                       f": unauthorised, {f['words']}; it {effect['words']}"),
                measurement={"what": "the flow's owner (flow_intent.classify)",
                             "value": "unauthorised",
                             "cookie": flow_intent.cookie_hex(f.get("cookie")),
                             "why": f["words"]},
                threshold={"what": "an authorised flow's cookie: recorded as Mercury's on this "
                                   "connection, or declared as the controller application's own",
                           "recorded": records,
                           "own_cookies": [flow_intent.cookie_hex(c)
                                           for c in connection["own_cookies"]]},
                confidence="high",
                confidence_why="the flow's cookie against Mercury's records and the "
                               "connection's declared cookies, the switch's table read whole",
                evidence=[f["id"]] + [p["id"] for p in moved], basis="intent",
                effect=effect, displaced=moved))
    return {"detections": detections, "judged": judged, "error": ""}


def displaced_piece(connection: str, dpid_hex: str, record: dict) -> dict:
    """A Mercury flow an unauthorised flow displaced (`flow_intent.displaced`, C2004) as an
    evidence piece of its own: its id (``intent:<connection>:<dpid hex>:<cookie>``: the flow
    intent's record, never the switch's flow id, which the unauthorised flow now holds), what it
    was (cookie, table, priority, match, actions, timeouts), when it was installed and the
    response that installed it, where the record says (its kind, action, risk and operation;
    never who)."""
    from modules.sdn import flow_intent

    cookie = flow_intent.cookie_hex(record.get("cookie"))
    response = record.get("response") or {}
    return {"kind": "displaced_flow", "id": f"intent:{connection}:{dpid_hex}:{cookie}",
            "cookie": cookie, "table_id": record.get("table_id"),
            "priority": record.get("priority"), "match": record.get("match") or {},
            "actions": record.get("actions") or [],
            "actions_words": flow_intent.action_words(record.get("actions")),
            "idle_timeout": record.get("idle_timeout"),
            "hard_timeout": record.get("hard_timeout"),
            "installed_at": record.get("installed_at"), "state": record.get("state"),
            "response": {k: response[k] for k in ("kind", "action", "risk", "operation")
                         if response.get(k) not in (None, "")},
            "words": "Mercury's flow, recorded as installed at the unauthorised flow's place (the "
                     "same table, priority and match) and not installed: the unauthorised flow "
                     "took its place"}


# ───────────────────────────────────────────────────────────────────────────── the state

def _path() -> str:
    from modules.config import DATA_DIR

    return os.path.join(DATA_DIR, STATE_FILE)


def _empty_network() -> dict:
    return {"collected_at": "", "updated_at": "", "baseline": {}, "over": {}, "seen": {},
            "firing": {}, "unrecorded": []}


def read_state() -> dict:
    """The state, for a reader: ``{"state": "ok"|"absent"|"unreadable", "doc", "error"}``."""
    path = _path()
    if not os.path.exists(path):
        return {"state": "absent", "doc": {"schema": SCHEMA, "networks": {}}, "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict) or not isinstance(doc.get("networks"), dict):
            raise ValueError("not a detection state document")
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "doc": None,
                "error": f"{STATE_FILE} could not be read ({type(exc).__name__}: {exc})"}
    if doc.get("schema") != SCHEMA:
        return {"state": "unreadable", "doc": None,
                "error": f"{STATE_FILE} is schema {doc.get('schema')!r}; this release reads "
                         f"{SCHEMA}"}
    return {"state": "ok", "doc": doc, "error": ""}


def firing() -> dict:
    """The detections firing now, every network's: ``{"state", "error", "updated_at",
    "instances"}``, each an alert instance in the reader's shape. Absent (nothing judged
    yet) and unreadable are different answers."""
    got = read_state()
    if got["state"] != "ok":
        return {"state": got["state"], "error": got["error"], "updated_at": "",
                "instances": []}
    nets = got["doc"]["networks"]
    instances = [entry["inst"] for _n, net in sorted(nets.items())
                 for _k, entry in sorted((net.get("firing") or {}).items())]
    updated = max((net.get("updated_at") or "" for net in nets.values()), default="")
    return {"state": "ok", "error": "", "updated_at": updated, "instances": instances}


# ───────────────────────────────────────────────────────────────────────────── the alert

def instance(d: dict, since: float, fired_at: float, window: int = 0) -> dict:
    """Detection *d* as an alert instance in the reader's shape: its condition held from
    *since*, alerting from *fired_at*; its labels its identity (the network, connection,
    switch and subject), never a measured value."""
    title = TITLES[d["rule"]]
    labels = {"alertname": title, "network": d["network"], "connection": d["connection"],
              "dpid": d["dpid_hex"], d["subject"]["kind"]: str(d["subject"]["value"])}
    m, t = d["measurement"], d["threshold"]
    value = (f"{m.get('value')} {m.get('unit', '')} against {t.get('value')} "
             f"{t.get('unit', '')}".strip() if d["rule"] != "unauthorised_flow" else
             f"cookie {m.get('cookie')}")
    return {"rule": title, "rule_uid": RULE_UIDS[d["rule"]], "kind": "condition",
            "state": "Alerting", "value": value, "labels": labels, "device": "", "address": "",
            "device_from": "none", "active_at": _iso(since), "starts_at": _iso(fired_at),
            "fingerprint": d["key"], "for_seconds": int(window or 0), "window_seconds": 0,
            "silences": []}


def flow_piece(f: dict) -> dict:
    """A collected flow as an evidence piece: its id, table, priority, cookie, match,
    actions (and in words), timeouts and counters. One shape for a detection's section and
    a collection's (`closed_loop.collection_request`)."""
    from modules.sdn import flow_intent

    return {"kind": "flow", "id": f["id"], "table_id": f.get("table_id"),
            "priority": f.get("priority"),
            "cookie": flow_intent.cookie_hex(f.get("cookie")),
            "match": f.get("match") or {}, "actions": f.get("actions") or [],
            "actions_words": flow_intent.action_words(f.get("actions")),
            "idle_timeout": f.get("idle_timeout"),
            "hard_timeout": f.get("hard_timeout"),
            "packet_count": f.get("packet_count"), "byte_count": f.get("byte_count"),
            "duration_sec": f.get("duration_sec")}


def section(d: dict, collected: dict, sw: dict) -> dict:
    """The pack's ``sdn`` section for detection *d*: the detection itself, then the flows and
    ports it rests on as collected (each with its evidence id), the flows its effect names
    (an unauthorised flow's, `flow_intent.effect`), the Mercury flows it displaced, earlier
    sightings for a scan, and the switch's coverage. At most `SECTION_FLOWS` flows, the
    detection's own first; the rest counted."""
    ids = set(d["evidence"])
    effect = d.get("effect") or {}
    named = [i for i in effect.get("evidence") or [] if i not in ids]
    own = [f for f in sw.get("flows") or [] if f.get("id") in ids]
    by_id = {f.get("id"): f for f in sw.get("flows") or []}
    also = [by_id[i] for i in named if i in by_id]
    total = len(own) + len(also)
    flows = (sorted(own, key=lambda f: -(f.get("packet_count") or 0)) + also)[:SECTION_FLOWS]
    piece = {"kind": "detection", "rule": d["rule"], "title": d["title"], "words": d["words"],
             "connection": d["connection"], "dpid": d["dpid_hex"], "source": d["source"],
             "targets": d["targets"], "port": d["port"], "measurement": d["measurement"],
             "threshold": d["threshold"], "confidence": d["confidence"],
             "confidence_why": d["confidence_why"], "evidence": d["evidence"]}
    if effect:
        piece["effect"] = effect
    if d.get("source_from"):
        # How a port's source was found in the controller's topology, or why it was not (C2002):
        # what the card draws and the classifier reads.
        piece["source_from"] = d["source_from"]
    pieces = [piece]
    for p in sw.get("ports") or []:
        if p.get("id") in ids:
            pieces.append(dict({k: v for k, v in p.items()}, kind="port",
                               sample=sw.get("sample")))
    for f in flows:
        pieces.append(flow_piece(f))
    displaced = list(d.get("displaced") or [])
    pieces += displaced
    now_ids = {f.get("id") for f in sw.get("flows") or []}
    earlier = [s for s in d.get("sightings") or [] if s.get("id") not in now_ids]
    # Every section is bounded, not the flows alone (C2006: a re-fired scan's sightings took
    # its request past the task's bound): the newest sightings, the rest counted.
    earlier_sent = sorted(earlier, key=lambda s: -(s.get("at") or 0))[:SECTION_SIGHTINGS]
    for s in earlier_sent:
        pieces.append({"kind": "sighting", "id": s.get("id"), "port": s.get("port"),
                       "dst": s.get("dst"), "seen_at": _iso(s["at"]),
                       "words": "seen in an earlier collection within the window; its flow "
                                "is no longer installed"})
    # The detection's own evidence list names only what is sent, the rest counted: a cited id
    # resolves in the pack, and the list never outgrows the pieces it points at.
    sent = {p.get("id") for p in pieces if p.get("id")}
    kept = [i for i in d["evidence"] if i in sent]
    if len(kept) < len(d["evidence"]):
        piece["evidence"] = kept
        piece["evidence_not_sent"] = len(d["evidence"]) - len(kept)
    pieces.append({"kind": "coverage", "dpid": d["dpid_hex"], **(sw.get("coverage") or {
        "granularity": "not read", "words": "this switch's flows could not be read"})})
    return {"source": (f"the SDN collection of {collected.get('network')} "
                       f"(closed_loop.collect_threat_data): controller {d['connection']}, switch "
                       f"{d['dpid_hex']}, port rates over {sw['sample'].get('elapsed_s')} s"),
            "read_at": collected.get("collected_at") or "", "as_of": collected.get("collected_at"),
            "pieces": pieces,
            "counts": dict({"flows": len(flows), "ports": sum(p["kind"] == "port" for p in pieces),
                            "earlier_sightings": len(earlier)},
                           **({"earlier_sightings_sent": len(earlier_sent)}
                              if len(earlier_sent) < len(earlier) else {}),
                           **({"displaced_flows": len(displaced)} if effect else {})),
            "total": total, "subset": total > len(flows) or len(earlier_sent) < len(earlier)}


# ───────────────────────────────────────────────────────────────────────────── observe

def _switch_of(collected: dict, d: dict):
    for ctl, sw in _switches(collected):
        if ctl.get("connection") == d["connection"] and sw["dpid_hex"] == d["dpid_hex"]:
            return sw
    return {}


def _stored_topology(network: str) -> dict:
    """The SDN reader's stored topology for *network* (`topology.stored`), or why it could not
    be read, in its shape: a port detection's source is looked up there (C2002)."""
    try:
        from modules.sdn import topology

        return topology.stored(network)
    except Exception as exc:                          # noqa: BLE001 (said as the reason)
        log.error("sdn detect: %s's stored topology could not be read (%s)", network,
                  type(exc).__name__)
        return {"state": "could not read", "why": f"{type(exc).__name__}: {exc}",
                "controllers": []}


def observe(network: str, collected: dict, *, values: dict = None, intent: dict = None,
            topo: dict = None, clock=time.monotonic) -> dict:
    """Run the three rules over *collected* (`collect_threat_data(network)`'s answer) and
    make each detection an alert: fired when first seen (a transition in the alert history and
    its evidence pack), resolved when a collection that judged its subject no longer shows it.
    *values* the thresholds (default: the network's); *intent* the flow intent (default: the
    network's); *topo* the controllers' topology a port's source is looked up in (default: the
    SDN reader's stored read, `topology.stored`). Never raises: ``{"ok", "error", ...}``,
    naming what was judged, what fired, what resolved, what is pending, which ports have no
    baseline yet, and what was not judged; *kept* each fired detection's pack as kept, by its
    key, so the loop classifies the pack in hand rather than reading every kept pack to find
    it again (C1970); *took* the seconds each fired detection's pack took to build and keep,
    by its key, by *clock* (the loop's timing line, C1970)."""
    from modules import alert_history, evidence_pack
    from modules.filestore import PathLock, StoreUnreadable, read_json_for_write, write_atomic
    from modules.sdn import flow_intent

    out = {"ok": False, "error": "", "network": network, "collected_at": "",
           "detections": [], "fired": [], "resolved": [], "firing": 0, "unjudged": [],
           "pending": [], "no_baseline": [], "notes": [], "packs": {"built": 0, "failed": []},
           "kept": {}, "took": {},
           "history": {}, "changed": False, "thresholds": {}}
    if (collected or {}).get("network") != network:
        out["error"] = (f"the collection is {(collected or {}).get('network')!r}'s, not "
                        f"{network!r}'s: nothing was judged")
        return out
    out["collected_at"] = collected.get("collected_at") or ""
    at = _epoch(collected.get("collected_at"))
    if at is None or collected.get("state") in ("none",) or \
            (collected.get("state") == "unreadable" and not collected.get("controllers")):
        out["error"] = (f"nothing to judge: the collection is {collected.get('state')!r}"
                        + (f" ({collected.get('error') or collected.get('words')})"
                           if collected.get("error") or collected.get("words") else ""))
        return out
    if values is None:
        th = thresholds(network)
        if not th["ok"]:
            out["error"] = th["error"]
            return out
        values = th["values"]
    out["thresholds"] = dict(values)
    if intent is None:
        intent = flow_intent.intent(network)
    if topo is None:
        topo = _stored_topology(network)
    try:
        with PathLock(_path):
            doc = read_json_for_write(_path(), empty={"schema": SCHEMA, "networks": {}})
            if doc.get("schema") != SCHEMA:
                raise StoreUnreadable(f"{STATE_FILE} is schema {doc.get('schema')!r}; this "
                                      f"release writes {SCHEMA}")
            net = doc.setdefault("networks", {}).setdefault(network, _empty_network())
            last = _epoch(net.get("collected_at"))
            if last is not None and at < last:
                raise Refused(f"this collection ({collected['collected_at']}) is older than the "
                              f"one last judged ({net['collected_at']}): nothing was judged")
            scanned = scan(collected, values, net.get("seen"), topo=topo)
            flooded = flood(collected, net.get("baseline"), values, net.get("over"), topo=topo)
            unauth = unauthorised(collected, intent, now=at)
            detections = scanned["detections"] + flooded["detections"] + unauth["detections"]
            judged = scanned["judged"] | flooded["judged"] | unauth["judged"]
            if unauth["error"]:
                out["notes"].append(unauth["error"])
            out["notes"] += scanned["notes"]
            current = {d["key"]: d for d in detections}
            fired, resolved = [], []
            firing_now = net.get("firing") or {}
            window = values["sdn_flood_window_seconds"]
            for key, d in current.items():
                if key in firing_now:
                    firing_now[key]["detection"] = d
                    continue
                since = d.get("since", at)
                inst = instance(d, since, at, window if d["rule"] == "flood" else 0)
                sw = _switch_of(collected, d)
                pack_id = ""
                pack_error = ""
                building = clock()
                try:
                    pack = evidence_pack.build_detection(
                        inst, network=network, sdn=section(d, collected, sw), now=at,
                        switch_words=f"switch {d['dpid_hex']} on {d['connection']}",
                        trigger=(f"Mercury's SDN detection found it in the collection of "
                                 f"{collected['collected_at']}: {d['words']}"))
                    kept = evidence_pack.record(pack)
                    if kept["ok"]:
                        pack_id = pack["id"]
                        out["packs"]["built"] += 1
                        out["kept"][key] = pack
                    else:
                        pack_error = kept["error"]
                except Exception as exc:              # noqa: BLE001 (said, never raised)
                    pack_error = f"{type(exc).__name__}: {exc}"
                out["took"][key] = round(clock() - building, 3)
                if pack_error:
                    out["packs"]["failed"].append({"key": key, "error": pack_error})
                    log.error("sdn detect: the pack for %s on %s could not be kept (%s)",
                              d["title"], d["dpid_hex"], pack_error)
                firing_now[key] = {"since": since, "fired_at": at, "inst": inst,
                                   "pack": pack_id, "pack_error": pack_error, "detection": d}
                fired.append(inst)
                out["fired"].append(key)
            for key in sorted(set(firing_now) - set(current)):
                entry = firing_now[key]
                if entry["detection"]["scope"] not in judged:
                    out["unjudged"].append({"key": key, "title": entry["inst"]["rule"],
                                            "scope": entry["detection"]["scope"],
                                            "words": "its subject was not read in this "
                                                     "collection, so it stays firing"})
                    continue
                resolved.append((entry["inst"], at))
                out["resolved"].append(key)
                del firing_now[key]
            rows = list(net.get("unrecorded") or []) + alert_history.from_detections(
                STORE, [network], fired, resolved, now=time.time())
            got = alert_history.record([dict(r) for r in rows]) if rows else {
                "ok": True, "added": 0, "held": 0, "unopened": 0, "error": ""}
            out["history"] = got
            net["unrecorded"] = [] if got["ok"] else rows
            exclude = set(flooded["over"])
            net.update(collected_at=collected["collected_at"], updated_at=_iso(time.time()),
                       baseline=update_baseline(net.get("baseline"), collected, exclude),
                       over=flooded["over"], seen=scanned["seen"], firing=firing_now)
            write_atomic(_path(), json.dumps(doc, sort_keys=True, default=str))
    except (Refused, StoreUnreadable) as exc:
        out["error"] = str(exc)
        return out
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("sdn detect: %s's collection could not be judged (%s)", network, exc)
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    out.update(ok=True, detections=detections, firing=len(firing_now),
               pending=flooded["pending"], no_baseline=flooded["no_baseline"],
               changed=bool(out["fired"] or out["resolved"] or out["packs"]["built"]))
    if not got["ok"]:
        out["notes"].append(f"{len(rows)} transition(s) could not be kept in the alert history "
                            f"({got['error']}); offered again with the next collection")
    return out
