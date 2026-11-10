"""The SDN analyst (Lab 9 B1, C2903; board I of docs/boards/lab9-sdn.html, SDN › Flows' "Analyse
this network"): live state from a network's switches, collected, kept as a snapshot, analysed
by one AI call, each finding checked against the snapshot, and compared with the issues a
person planted.

**The steps** (`STEPS`, each named on the manual's How it works page):
1. **collect** (`start_collection`, `collect_job`): a READ job, never a page view (CLAUDE.md,
   "Enterprise scale"). `closed_loop.collect_threat_data(network, links=True)` through each
   connection's controller driver (the one controller path, its REST): every switch's flows,
   its port counters twice `COLLECT_INTERVAL` apart, its port descriptions (link up or down
   from the LINK_DOWN state bit, C2602), and each connection's discovered links. One
   collection at a time per network, across processes (`RUNNING`, refused by name, never
   queued), bounded (`collection_bound_s`) and announced (``sdn``) when it ends.
2. **snapshot** (`build_snapshot`, `save_snapshot`): the collection in the analyst's shape,
   every fact with its evidence id (`ID_KINDS`), masked (`redact.egress_payload`; nothing secret
   is in a flow table, and it is masked anyway), sealed by its sha256 and kept under its own id
   (``snap-<16 hex>``) in the network's folder, so the same snapshot can be analysed again (B4's
   fixed snapshot: HEAL_TO_INTENT 19.13). A link an earlier snapshot discovered and this one
   does not is kept as "not discovered now", since when: the controller forgets a link whose
   LLDP stopped, and a lost redundant link is what the lab plants.
3. **egress**: the classification marking and the topology class (`egress_classes`): flows and
   port rates are the topology class, sent only while it is allowed for the network.
4. **ask** (`analyse`): ONE recorded, capped call through the gateway on the task
   ``sdn_analyse`` (its pin, modules/ai/pins/sdn_analyse.json: Haiku 5.5), a person's press
   only. No loop and no retry: an iteration limit of one call (B4 adds the loop). The prompt is
   the snapshot in its stated line form (`facts`) and nothing else: **no planted issue's name,
   evidence or note ever reaches it**.
5. **check** (`check`): the answer parsed strictly (the schema `NetworkAnalysis`, the gateway's
   validation: a malformed answer is refused, named, and nothing of it is used); then in code,
   every finding's evidence ids held to the snapshot's: an id the snapshot does not hold is
   removed, and a finding left citing nothing is dropped; each drop counted and said. Severity
   is the schema's fixed set; lengths are capped (`MAX_*`), a capped text said with "…".
6. **compare** (`marks`): each planted issue (a person's name for it and the evidence it should
   be found by, ids or ``*`` patterns over ids) is found when a kept finding cites an id it
   matches, else missed; "not in the collection" when none of its patterns matches anything the
   snapshot holds. Why is a person's note, editable. The sheet downloads as Markdown or CSV
   (`sheet_markdown`, `sheet_csv`), for the lab's document and B5's false-positive log.

**Evidence ids** reuse the collection's own where it has one: a flow's
``flow:<connection>:<dpid hex>:t<table>:p<priority>:<match digest>`` (`closed_loop.flow_ref`,
stable from one collection to the next) and a port's ``port:<connection>:<dpid hex>:<port>``
(`closed_loop.port_ref`), and add ``drop:`` (a flow with no actions, the rest of its flow id),
``rate:<connection>:<dpid hex>:<port>`` and ``link:<connection>:<dpid>:<port>-<dpid>:<port>``
(its two ends in order). Addresses never appear in an id, so IPv4 and IPv6 matches are alike.

**The store**, per network (`config.list_data_path`): ``sdn_analyst/snapshots/<id>.json``,
``sdn_analyst/analyses/<id>.json``, ``sdn_analyst/latest.json`` (the newest of each, what the
page reads), ``sdn_analyst/planted.json`` and ``sdn_analyst/running.json``. A page view reads
those small files and nothing else; it writes nothing and asks no controller.
"""

import csv
import fnmatch
import hashlib
import io
import json
import logging
import os
import re
import threading
import time
import uuid
from enum import Enum
from typing import List

from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)

FEATURE = "sdn_analyse"
PROMPT = ("sdn_analyse", 1)
#: The port counters' spacing for a collection's rates (seconds): the loop's own
#: (`loop.SAMPLE_INTERVAL`), within `closed_loop.MIN_INTERVAL` to `MAX_INTERVAL`.
COLLECT_INTERVAL = 5.0
#: Each switch's flows sent at most: the busiest by packets (every drop flow is sent beside
#: them); the rest counted, the snapshot saying it is a subset. Sized so the lab's five
#: switches stay well under the pin's prompt bound (pins/sdn_analyse.json).
FLOWS_PER_SWITCH = 60
#: The answer's bounds, applied in code (`check`).
MAX_FINDINGS = 20
MAX_FINDING_CHARS = 200
MAX_WHY_CHARS = 800
MAX_EVIDENCE = 12
#: Planted issues' bounds (`add_planted`, `set_why`).
MAX_PLANTED = 50
MAX_NAME_CHARS = 120
MAX_PATTERNS = 10
MAX_PATTERN_CHARS = 200
MAX_NOTE_CHARS = 600
#: The output a call is estimated at for the page's "about $X" (provisional, not measured:
#: a few findings; the per-call cap on the mark is the bound).
OUTPUT_TOKENS_ESTIMATE = 1500
#: The evidence id kinds, each with what its line holds.
ID_KINDS = {"port": "a port as its switch describes it: link and admin state, name, speed",
            "rate": "a port's rates over the interval, its drops, its load against its speed",
            "flow": "a flow that forwards or changes traffic",
            "drop": "a flow with no actions, which drops what it matches",
            "link": "a link between two switch ports, discovered by the controller or not now"}
SEVERITIES = ("info", "low", "medium", "high", "critical")
#: OpenFlow's reserved port for the switch's own stack: its LINK_DOWN is the switch's internal
#: port (Open vSwitch reports it down on a bridge with no address), said as such and never
#: counted among the ports down.
LOCAL = "LOCAL"
DIR = "sdn_analyst"
_ID = re.compile(r"^(snap|an)-[0-9a-f]{16}$")
_PLANTED_ID = re.compile(r"^pl-[0-9a-f]{12}$")
STEPS = (
    ("collect", "a read job (never a page view): every switch's flows, its port counters twice "
                f"{COLLECT_INTERVAL:g} s apart, its port descriptions (link up or down from the "
                "LINK_DOWN state) and each connection's discovered links, through the "
                "controller's driver; one at a time per network, bounded, announced when done"),
    ("snapshot", "the collection kept as a snapshot under its own id, every fact with its "
                 "evidence id, masked and sealed by its hash, so it can be analysed again; a "
                 "link an earlier snapshot discovered and this one does not is kept as not "
                 "discovered now"),
    ("egress", "flows and port rates are the topology class: sent only while it is allowed for "
               "the network, and never for a network carrying a classification marking"),
    ("ask", "one recorded, capped AI call through the gateway, a person's press only, with the "
            "snapshot's facts and nothing else (no planted issue reaches it); no retry"),
    ("check", "the answer parsed strictly; every evidence id held to the snapshot's: an id it "
              "does not hold is removed, a finding left citing nothing is dropped, each "
              "counted; severity from a fixed set; lengths capped"),
    ("compare", "each planted issue found when a kept finding cites evidence it names, else "
                "missed; its why a person's note; the sheet downloads as Markdown or CSV"),
)


# ───────────────────────────────────────────────────────────────────────────── the schema

class AnalystSeverity(str, Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Finding(StrictModel):
    severity: AnalystSeverity
    finding: str
    why: str
    evidence: List[str]


@register("sdn_analyse", 1)
class NetworkAnalysis(StrictModel):
    findings: List[Finding]


# ───────────────────────────────────────────────────────────────────────────── the store

def _dir(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), DIR)


def _read_json(path: str):
    """``(value, error)``: absent is ``(None, "")``; unreadable says why."""
    if not os.path.exists(path):
        return None, ""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), ""
    except (OSError, ValueError) as exc:
        return None, f"{os.path.basename(path)}: {type(exc).__name__}: {exc}"


def _write_json(path: str, value) -> None:
    from modules import filestore

    os.makedirs(os.path.dirname(path), exist_ok=True)
    filestore.write_atomic(path, json.dumps(value, sort_keys=True, indent=1, default=str))


def _lock(network: str):
    from modules.filestore import PathLock

    return PathLock(lambda: os.path.join(_dir(network), "store"))


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _digest(value: dict) -> str:
    body = {k: v for k, v in value.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     default=str).encode("utf-8")).hexdigest()


# ───────────────────────────────────────────────────────────────────────────── evidence ids

def rate_ref(connection: str, dpid_hex: str, port_no) -> str:
    return f"rate:{connection}:{dpid_hex}:{port_no}"


def drop_ref(flow_id: str) -> str:
    """A drop flow's id: ``drop:`` and the rest of its flow id."""
    return "drop:" + flow_id[len("flow:"):] if flow_id.startswith("flow:") else "drop:" + flow_id


def link_ref(connection: str, a: tuple, b: tuple) -> str:
    """A link's id, its two ends ``(dpid hex, port)`` in order, so both directions are one."""
    one, two = sorted([(str(a[0]), str(a[1])), (str(b[0]), str(b[1]))])
    return f"link:{connection}:{one[0]}:{one[1]}-{two[0]}:{two[1]}"


# ───────────────────────────────────────────────────────────────────────────── the snapshot

def _names(network: str) -> dict:
    """Each switch's own name (its ``dp_desc``) by dpid hex, from the SDN reader's stored value
    (a local read; {} when it has none)."""
    from modules import reader_job

    try:
        got = reader_job.read_cached_for("sdn-controllers", network)
    except Exception as exc:                                    # noqa: BLE001 (said, never raised)
        log.info("sdn analyst: the SDN reader's names could not be read (%s)", type(exc).__name__)
        return {}
    value = (((got.get("doc") or {}).get("last_good") or {}).get("value")) or {}
    return {s.get("dpid_hex"): s.get("name") for c in value.get("controllers") or []
            for s in c.get("switches") or [] if s.get("name")}


def _flow_row(f: dict) -> dict:
    return {k: f.get(k) for k in ("id", "table_id", "priority", "cookie", "match", "actions",
                                  "packet_count", "byte_count", "duration_sec", "idle_timeout",
                                  "hard_timeout")}


def build_snapshot(network: str, collected: dict, *, by: str, previous: dict = None,
                   names: dict = None) -> dict:
    """*collected* (`collect_threat_data(..., links=True)`'s answer) in the analyst's shape:
    ``{"id", "network", "collected_at", "interval_s", "by", "state", "error", "calls",
    "switches", "links", "unread", "subset", "hash"}``. Each switch row holds its ``ports`` (port
    descriptions, ``port:`` ids), ``rates`` (``rate:``), ``flows`` (``flow:``, at most
    `FLOWS_PER_SWITCH`, the busiest by packets) and ``drops`` (``drop:``, every one). *previous*
    is the network's last snapshot: a link it holds that this collection did not discover is kept,
    "not discovered now". Masked, then sealed (`_digest`)."""
    from modules import redact

    names = names or {}
    switches, links, unread = [], {}, []
    down = {}
    for c in (collected or {}).get("controllers") or []:
        conn = str(c.get("connection") or "")
        if c.get("state") == "unreadable" and not c.get("switches"):
            unread.append(f"controller {conn}: {c.get('error') or 'not read'}")
        if c.get("links_error"):
            unread.append(f"controller {conn}'s discovered links: {c['links_error']}")
        for sw in c.get("switches") or []:
            dhex = sw.get("dpid_hex")
            flows = [f for f in sw.get("flows") or [] if f.get("actions")]
            drops = [f for f in sw.get("flows") or [] if not f.get("actions")]
            busiest = sorted(flows, key=lambda f: -(f.get("packet_count") or 0))
            sent = busiest[:FLOWS_PER_SWITCH]
            ports = []
            for p in sw.get("port_desc") or []:
                ports.append({"id": f"port:{conn}:{dhex}:{p.get('port_no')}",
                              "port_no": p.get("port_no"), "name": p.get("name") or "",
                              "link_up": bool(p.get("link_up")),
                              "admin_up": bool(p.get("admin_up")),
                              "curr_speed": p.get("curr_speed") or 0})
                down[(conn, dhex, str(p.get("port_no")))] = not p.get("link_up")
            speed = {str(p["port_no"]): p["curr_speed"] for p in ports}
            rates = []
            for r in sw.get("ports") or []:
                row = {k: v for k, v in r.items() if k != "id"}
                row["id"] = rate_ref(conn, dhex, r.get("port_no"))
                kbps = speed.get(str(r.get("port_no"))) or 0
                if kbps and "rx_bytes_per_s" in r:
                    busier = max(r.get("rx_bytes_per_s") or 0, r.get("tx_bytes_per_s") or 0)
                    row["load_pct"] = round(busier * 8 / 1000 / kbps * 100, 1)
                rates.append(row)
            switches.append({
                "connection": conn, "dpid_hex": dhex, "name": names.get(dhex, ""),
                "state": sw.get("state"), "error": sw.get("error") or "",
                "coverage": (sw.get("coverage") or {}).get("granularity", "not read"),
                "flows_total": len(flows), "flows_sent": len(sent),
                "flows": [_flow_row(f) for f in sent],
                "drops": [dict(_flow_row(f), id=drop_ref(f["id"])) for f in drops],
                "ports": ports, "rates": rates,
                "sample_s": (sw.get("sample") or {}).get("elapsed_s")})
            if sw.get("state") != "ok":
                unread.append(f"switch {dhex} on {conn}: {sw.get('error') or 'not read whole'}")
        for ln in c.get("links") or []:
            a = (ln["src"]["dpid_hex"], ln["src"]["port_no"])
            b = (ln["dst"]["dpid_hex"], ln["dst"]["port_no"])
            lid = link_ref(conn, a, b)
            links[lid] = {"id": lid, "connection": conn, "ends": sorted([list(map(str, a)),
                                                                         list(map(str, b))]),
                          "discovered": True}
    for lid, ln in links.items():
        ends_down = [e for e in ln["ends"] if down.get((ln["connection"], e[0], e[1]))]
        ln.update(state="down" if ends_down else "up",
                  words=(f"discovered by the controller now, and the switch reports "
                         f"{' and '.join(f'{e[0]} port {e[1]}' for e in ends_down)} down"
                         if ends_down else "discovered by the controller now, both ends up"))
    at = (collected or {}).get("collected_at") or ""
    for old in (previous or {}).get("links") or []:
        if old.get("id") in links:
            continue
        since = old.get("since") or (previous or {}).get("collected_at") or ""
        ends_down = [e for e in old.get("ends") or []
                     if down.get((old.get("connection"), e[0], e[1]))]
        links[old["id"]] = dict(
            old, discovered=False, state="not discovered", since=since,
            words=(f"not discovered by the controller now; last discovered {since}"
                   + (f"; the switch reports {' and '.join(f'{e[0]} port {e[1]}' for e in ends_down)} down"
                      if ends_down else "")))
    snap = {"network": network, "collected_at": at,
            "interval_s": (collected or {}).get("interval_s"), "by": by,
            "state": (collected or {}).get("state") or "unreadable",
            "error": (collected or {}).get("error") or "",
            "calls": (collected or {}).get("calls") or 0,
            "switches": switches, "links": sorted(links.values(), key=lambda x: x["id"]),
            "unread": unread,
            "subset": any(s["flows_sent"] < s["flows_total"] for s in switches)}
    snap = redact.egress_payload(snap)
    digest = _digest(snap)
    snap["id"] = "snap-" + digest[:16]
    snap["hash"] = _digest(snap)
    return snap


def evidence_ids(snap: dict) -> set:
    """Every evidence id the snapshot holds (what a finding may cite)."""
    out = {ln["id"] for ln in snap.get("links") or []}
    for s in snap.get("switches") or []:
        for key in ("ports", "rates", "flows", "drops"):
            out.update(x["id"] for x in s.get(key) or [] if x.get("id"))
    return out


def intact(snap: dict) -> bool:
    return bool(snap) and snap.get("hash") == _digest(snap)


# ───────────────────────────────────────────────────────────────────────────── the facts sent

def _match_words(match: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in sorted((match or {}).items())) or "everything"


def _action_words(actions: list) -> str:
    if not actions:
        return "none (drops what it matches)"
    out = []
    for a in actions:
        rest = {k: v for k, v in a.items() if k != "type"}
        if a.get("type") == "OUTPUT":
            out.append(f"OUTPUT:{a.get('port')}")
        else:
            out.append(a.get("type", "?") + (
                "(" + ",".join(f"{k}={v}" for k, v in sorted(rest.items())) + ")" if rest
                else ""))
    return " ".join(out)


def _flow_words(f: dict) -> str:
    return (f"{f['id']} table {f.get('table_id', 0)}, priority {f.get('priority', 0)}, match "
            f"{_match_words(f.get('match'))}, actions {_action_words(f.get('actions'))}, "
            f"{f.get('packet_count') or 0} packets, {f.get('byte_count') or 0} bytes, age "
            f"{f.get('duration_sec') or 0} s, idle timeout {f.get('idle_timeout') or 0}, hard "
            f"timeout {f.get('hard_timeout') or 0}, cookie {hex(int(f.get('cookie') or 0))}")


def _rate_words(r: dict) -> str:
    if r.get("note"):
        return f"{r['id']} no rate: {r['note']}"
    load = f", at {r['load_pct']}% of its speed" if "load_pct" in r else ""
    return (f"{r['id']} rx {r.get('rx_pps', 0)} pps {r.get('rx_bytes_per_s', 0)} B/s, tx "
            f"{r.get('tx_pps', 0)} pps {r.get('tx_bytes_per_s', 0)} B/s, rx dropped "
            f"+{r.get('rx_dropped_delta', 0)}, tx dropped +{r.get('tx_dropped_delta', 0)}{load}")


def facts(snap: dict) -> str:
    """The snapshot as the model reads it: one fact a line, each line starting with its
    evidence id (lines without one say what the collection is and what it could not read)."""
    lines = [f"network: {snap.get('network')}",
             f"collected: {snap.get('collected_at')}, port rates over about "
             f"{snap.get('interval_s')} s between two counter reads",
             f"switches: {len(snap.get('switches') or [])}; links: "
             f"{len(snap.get('links') or [])}"]
    if snap.get("subset"):
        lines.append(f"each switch's flows are its busiest {FLOWS_PER_SWITCH} by packets, every "
                     "drop flow beside them; the rest are counted, not listed")
    for s in snap.get("switches") or []:
        label = f" ({s['name']})" if s.get("name") else ""
        lines.append(f"switch {s['dpid_hex']}{label} via {s['connection']}: read "
                     f"{s.get('state')}; {s.get('flows_total', 0)} forwarding flows "
                     f"({s.get('flows_sent', 0)} listed), {len(s.get('drops') or [])} drop "
                     f"flows, flow granularity {s.get('coverage')}")
        for p in s.get("ports") or []:
            own = " (the switch's own internal port)" if p["port_no"] == LOCAL else ""
            lines.append(f"{p['id']} link {'up' if p['link_up'] else 'DOWN'}, admin "
                         f"{'up' if p['admin_up'] else 'down'}, name {p.get('name') or '-'}"
                         f"{own}, speed {p.get('curr_speed') or 0} kbps")
        if not s.get("ports"):
            lines.append(f"switch {s['dpid_hex']}: no port description read")
        lines += [_rate_words(r) for r in s.get("rates") or []]
        lines += [_flow_words(f) for f in s.get("flows") or []]
        lines += [_flow_words(f) for f in s.get("drops") or []]
    for ln in snap.get("links") or []:
        lines.append(f"{ln['id']} {ln.get('state')}: {ln.get('words')}")
    for words in snap.get("unread") or []:
        lines.append(f"not read: {words}")
    return "\n".join(lines) + "\n"


def estimate(snap: dict) -> dict:
    """``{"tokens", "usd", "model", "model_words"}``: the call's input by the gateway's fallback
    over-estimate (`gateway.tokens_of_chars`) and its cost with `OUTPUT_TOKENS_ESTIMATE` output."""
    from modules.ai import gateway, profiles, prompts

    pin = profiles.task(FEATURE)
    chars = len(facts(snap)) + len(prompts.load(*PROMPT)["text"]) + 1500
    tokens = gateway.tokens_of_chars(chars)
    return {"tokens": tokens, "model": pin["model"],
            "model_words": profiles.profile(pin["model"])["words"],
            "usd": round(profiles.cost_usd(pin["model"], tokens, OUTPUT_TOKENS_ESTIMATE), 4)}


# ───────────────────────────────────────────────────────────────────────────── collect (a job)

def collection_bound_s(network: str) -> float:
    """How long a collection may run: the interval and six reads in a row at the slowest
    connection's timeout (the switch list and links, then flows, two port reads and the port
    description; each round's switches read at once), plus 30 s for the snapshot's write."""
    from modules.sdn import connections

    listed = connections.connections(network)
    slowest = max([float(c.get("timeout") or 10) for c in listed.get("connections") or []]
                  or [10.0])
    return COLLECT_INTERVAL + 6 * slowest + 30


def running(network: str, now: float = None) -> dict:
    """The collection running on *network* (``{"by", "at", "until"}``), or {} (none, or one past
    its bound, which is said as ``stale``)."""
    got, _err = _read_json(os.path.join(_dir(network), "running.json"))
    if not got:
        return {}
    now = time.time() if now is None else now
    if now > float(got.get("until_epoch") or 0):
        return {"stale": True, "by": got.get("by"), "at": got.get("at")}
    return got


def _spawn(fn) -> None:
    threading.Thread(target=fn, daemon=True, name="sdn-analyst-collect").start()


def start_collection(network: str, *, actor: str, spawn=None, now: float = None,
                     **job_kw) -> dict:
    """Start a collection on *network* as *actor*: ``{"ok", "error", "running"}``. Refused, by
    name, when the network has no controller connection or one is already running (never
    queued); otherwise the job (`collect_job`) is started (*spawn*, a thread by default)."""
    from modules.sdn import connections

    listed = connections.connections(network)
    if listed.get("state") != "ok" or not listed.get("connections"):
        return {"ok": False, "error": f"{network} has no SDN controller connection to collect "
                f"from ({listed.get('state')}{': ' + listed['error'] if listed.get('error') else ''})"}
    now = time.time() if now is None else now
    with _lock(network):
        held = running(network, now)
        if held and not held.get("stale"):
            return {"ok": False, "running": held,
                    "error": f"a collection started by {held.get('by')} at {held.get('at')} is "
                             f"running on {network} (until {held.get('until')} at the latest); "
                             "this one is refused, never queued"}
        bound = collection_bound_s(network)
        held = {"by": actor, "at": _iso(now), "until": _iso(now + bound),
                "until_epoch": now + bound, "bound_s": bound}
        _write_json(os.path.join(_dir(network), "running.json"), held)
    (spawn or _spawn)(lambda: collect_job(network, actor=actor, **job_kw))
    return {"ok": True, "error": "", "running": held}


def collect_job(network: str, *, actor: str, interval: float = COLLECT_INTERVAL, driver=None,
                sleep=time.sleep, clock=time.monotonic, now=time.time, announce=True) -> dict:
    """The collection job: collect, build and keep the snapshot, clear the running mark and
    announce ``sdn``, whatever happened. ``{"ok", "error", "snapshot"}``."""
    from modules.sdn import closed_loop

    out = {"ok": False, "error": "", "snapshot": None}
    try:
        collected = closed_loop.collect_threat_data(network, interval, sleep=sleep, clock=clock,
                                                    now=now, driver=driver, links=True)
        if not (collected.get("summary") or {}).get("switches"):
            out["error"] = (f"the collection read no switch ({collected.get('state')}: "
                            f"{collected.get('error') or collected.get('words') or 'no reason'})")
            _keep_failure(network, out["error"], actor, now())
            return out
        snap = build_snapshot(network, collected, by=actor, previous=latest_snapshot(network),
                              names=_names(network))
        save_snapshot(network, snap)
        out.update(ok=True, snapshot=snap)
        return out
    except Exception as exc:                                    # noqa: BLE001 (kept, said)
        log.warning("sdn analyst: the collection on %s failed: %s", network, type(exc).__name__)
        out["error"] = f"the collection failed: {type(exc).__name__}: {exc}"
        _keep_failure(network, out["error"], actor, now())
        return out
    finally:
        try:
            os.remove(os.path.join(_dir(network), "running.json"))
        except OSError:
            pass
        if announce:
            _announce(network)


def _announce(network: str) -> None:
    from modules import invalidation

    try:
        invalidation.announce(("sdn",), by="sdn-analyst")    # invalidation.ANNOUNCERS
    except Exception as exc:                                    # noqa: BLE001 (counted by its caller)
        log.info("sdn analyst: the announcement could not be sent (%s)", type(exc).__name__)


def _keep_failure(network: str, error: str, actor: str, at: float) -> None:
    with _lock(network):
        latest = _latest(network)
        latest["collect_failed"] = {"at": _iso(at), "by": actor, "error": error}
        _write_json(os.path.join(_dir(network), "latest.json"), latest)


def _latest(network: str) -> dict:
    got, _err = _read_json(os.path.join(_dir(network), "latest.json"))
    return got if isinstance(got, dict) else {}


def save_snapshot(network: str, snap: dict) -> None:
    """Keep *snap* under its id and make it the network's latest (with its estimate)."""
    with _lock(network):
        _write_json(os.path.join(_dir(network), "snapshots", f"{snap['id']}.json"), snap)
        latest = _latest(network)
        latest.pop("collect_failed", None)
        latest["snapshot"] = {
            "id": snap["id"], "collected_at": snap["collected_at"], "by": snap["by"],
            "state": snap["state"], "switches": len(snap["switches"]),
            "links": len(snap["links"]),
            "links_down": sum(ln.get("state") != "up" for ln in snap["links"]),
            "ports_down": sum(not p["link_up"] for s in snap["switches"] for p in s["ports"]
                              if p["port_no"] != LOCAL),
            "unread": len(snap["unread"]), "estimate": estimate(snap)}
        _write_json(os.path.join(_dir(network), "latest.json"), latest)


def snapshot(network: str, snap_id: str) -> dict:
    """``{"ok", "error", "snapshot"}``: a kept snapshot by its id, its seal checked."""
    if not _ID.match(str(snap_id or "")) or not str(snap_id).startswith("snap-"):
        return {"ok": False, "error": f"{snap_id!r} is not a snapshot id", "snapshot": None}
    got, err = _read_json(os.path.join(_dir(network), "snapshots", f"{snap_id}.json"))
    if err:
        return {"ok": False, "error": f"the snapshot {snap_id} cannot be read ({err})",
                "snapshot": None}
    if got is None:
        return {"ok": False, "error": f"no snapshot {snap_id} is kept for {network}",
                "snapshot": None}
    if not intact(got) or got.get("network") != network or got.get("id") != snap_id:
        return {"ok": False, "error": f"the snapshot {snap_id} changed since it was kept (its "
                "hash does not match), so it is not analysed", "snapshot": None}
    return {"ok": True, "error": "", "snapshot": got}


def latest_snapshot(network: str) -> dict:
    """The network's newest kept snapshot, or {}."""
    sid = (_latest(network).get("snapshot") or {}).get("id")
    return (snapshot(network, sid).get("snapshot") or {}) if sid else {}


# ───────────────────────────────────────────────────────────────────────────── ask and check

def _cap(text: str, limit: int) -> tuple:
    text = " ".join(str(text or "").split())
    return (text, False) if len(text) <= limit else (text[:limit - 1].rstrip() + "…", True)


def check(answer: NetworkAnalysis, ids: set) -> dict:
    """The model's *answer* held to the snapshot's evidence *ids*: ``{"findings", "dropped",
    "dropped_words", "removed_ids", "capped"}``. An id the snapshot does not hold is removed
    (counted in *removed_ids*); a finding left citing none is dropped, as is a blank one or one
    past `MAX_FINDINGS` (each counted in *dropped*, said in *dropped_words*); lengths capped."""
    kept, removed, capped = [], 0, 0
    dropped = {"uncited": 0, "unknown_only": 0, "blank": 0, "over_limit": 0}
    found = list(answer.findings)
    dropped["over_limit"] = max(0, len(found) - MAX_FINDINGS)
    for f in found[:MAX_FINDINGS]:
        cited = []
        for e in f.evidence:
            e = str(e).strip()
            if e and e not in cited:
                cited.append(e)
        known = [e for e in cited if e in ids][:MAX_EVIDENCE]
        unknown = [e for e in cited if e not in ids]
        removed += len(unknown)
        finding, a = _cap(f.finding, MAX_FINDING_CHARS)
        why, b = _cap(f.why, MAX_WHY_CHARS)
        if not finding:
            dropped["blank"] += 1
            continue
        if not known:
            dropped["unknown_only" if unknown else "uncited"] += 1
            continue
        severity = f.severity.value if isinstance(f.severity, Enum) else str(f.severity)
        if severity not in SEVERITIES:
            raise ValueError(f"severity {severity!r} is not one of {SEVERITIES}")
        capped += a + b
        kept.append({"severity": severity, "finding": finding, "why": why,
                     "evidence": known, "removed": unknown})
    kept.sort(key=lambda x: -SEVERITIES.index(x["severity"]))
    n = sum(dropped.values())
    said = (("uncited", "cited nothing"),
            ("unknown_only", "cited only ids the collection does not hold"),
            ("blank", "said nothing"), ("over_limit", f"past the first {MAX_FINDINGS}"))
    parts = [f"{dropped[k]} {words}" for k, words in said if dropped[k]]
    return {"findings": kept, "dropped": n, "dropped_by": dropped,
            "dropped_words": "; ".join(parts), "removed_ids": removed, "capped": capped}


def _refused(network: str, snap_id: str, actor: str, error: str, detail: str, **extra) -> dict:
    return dict({"ok": False, "error": error, "detail": detail, "network": network,
                 "snapshot_id": snap_id, "actor": actor, "call_id": "", "cost_usd": 0.0,
                 "findings": [], "dropped": 0}, **extra)


def analyse(network: str, snap_id: str, *, actor: str, trigger: dict, send=None,
            today: str = None, now: float = None) -> dict:
    """Analyse the kept snapshot *snap_id* of *network* as *actor* (`STEPS` 3 to 5): ONE call
    through the gateway, its answer checked (`check`), the analysis kept under its own id and
    made the network's latest. ``{"ok", "error", "detail", "id", "snapshot_id", "call_id",
    "cost_usd", "model", "findings", "dropped", "dropped_words", "removed_ids", "at", ...}``.
    Refused before any call: no such snapshot, one changed since kept, the classification
    marking, the topology class off. The gateway's own refusals (its trigger, hosted AI, the
    caps, the prompt's size) and a malformed answer (``schema``) are kept as such."""
    from modules.ai import calls, egress_classes, gateway, profiles

    now = time.time() if now is None else now
    got = snapshot(network, snap_id)
    if not got["ok"]:
        return _refused(network, snap_id, actor, "snapshot", f"{got['error']}; nothing was sent")
    snap = got["snapshot"]
    marked = egress_classes.classification_marking(network)
    if marked:
        return _refused(network, snap_id, actor, "classified", f"{network} carries the "
                        f"classification marking {marked!r}, which forces AI off; nothing was "
                        "sent")
    gate = egress_classes.topology_allowed(network)
    if not gate["allowed"]:
        return _refused(network, snap_id, actor, "withheld", "the snapshot's flows and port "
                        f"rates are the topology class, and {gate['why']}; nothing was sent")
    model = profiles.task(FEATURE)["model"]
    asked = gateway.ask(FEATURE, PROMPT, NetworkAnalysis, {"snapshot": facts(snap)},
                        actor=actor, trigger=trigger, send=send, today=today, network=network,
                        subject={"kind": "sdn_snapshot", "id": snap_id, "devices": []})
    out = {"ok": False, "error": "", "detail": "", "network": network, "snapshot_id": snap_id,
           "collected_at": snap.get("collected_at"), "actor": actor, "at": _iso(now),
           "call_id": asked.get("call_id", ""), "cost_usd": asked.get("cost_usd", 0.0),
           "model": model, "findings": [], "dropped": 0, "dropped_words": "",
           "removed_ids": 0}
    links = {"page": "/v2/sdn/flows", "anchor": "sdn-analyse"}
    if not asked["ok"]:
        out.update(error=asked["error"], detail=asked.get("detail", ""))
    else:
        checked = check(asked["output"], evidence_ids(snap))
        out.update(ok=True, **checked)
        calls.record_use(asked["call_id"], f"shown: {len(checked['findings'])} findings, "
                         f"{checked['dropped']} dropped by the check", actor=actor,
                         detail=checked["dropped_words"], links=links)
    out["id"] = "an-" + hashlib.sha256(f"{snap_id}|{out['call_id']}|{now}|{uuid.uuid4()}"
                                       .encode()).hexdigest()[:16]
    with _lock(network):
        _write_json(os.path.join(_dir(network), "analyses", f"{out['id']}.json"), out)
        latest = _latest(network)
        latest["analysis"] = out["id"]
        _write_json(os.path.join(_dir(network), "latest.json"), latest)
    return out


def analysis(network: str, an_id: str) -> dict:
    if not _ID.match(str(an_id or "")) or not str(an_id).startswith("an-"):
        return {}
    got, _err = _read_json(os.path.join(_dir(network), "analyses", f"{an_id}.json"))
    return got if isinstance(got, dict) else {}


# ───────────────────────────────────────────────────────────────────────────── planted issues

class PlantedRefused(ValueError):
    """A planted issue that cannot be kept, in words naming why."""


def _planted_path(network: str) -> str:
    return os.path.join(_dir(network), "planted.json")


def planted(network: str) -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "issues", "error"}``."""
    got, err = _read_json(_planted_path(network))
    if err:
        return {"state": "unreadable", "issues": [], "error": err}
    if got is None:
        return {"state": "absent", "issues": [], "error": ""}
    return {"state": "ok", "issues": list(got.get("issues") or []), "error": ""}


def _text(value, limit: int, what: str, required: bool = True) -> str:
    text = " ".join(str(value or "").split())
    if required and not text:
        raise PlantedRefused(f"{what} is empty")
    if len(text) > limit:
        raise PlantedRefused(f"{what} is {len(text)} characters, over {limit}")
    if any(not ch.isprintable() for ch in text):
        raise PlantedRefused(f"{what} holds a character that is not printable")
    return text


def patterns_of(text: str) -> list:
    """A planted issue's evidence, typed one to a line or separated by spaces or commas: each an
    evidence id or a ``*`` pattern over ids, of one of `ID_KINDS`."""
    items = [p for p in re.split(r"[\s,]+", str(text or "")) if p]
    if not items:
        raise PlantedRefused("no evidence is named: give the ids (or * patterns) it should be "
                             "found by, e.g. link:ctl-1:0000000000000003:3-0000000000000004:3")
    if len(items) > MAX_PATTERNS:
        raise PlantedRefused(f"{len(items)} pieces of evidence are named, over {MAX_PATTERNS}")
    for p in items:
        _text(p, MAX_PATTERN_CHARS, "a piece of evidence")
        kind = p.split(":", 1)[0]
        if kind not in ID_KINDS or ":" not in p:
            raise PlantedRefused(f"{p!r} is not an evidence id or pattern: it starts with one "
                                 f"of {', '.join(k + ':' for k in ID_KINDS)}")
    return items


def add_planted(network: str, name: str, evidence: str, *, actor: str, why: str = "",
                now: float = None) -> dict:
    """Keep a planted issue on *network*: ``{"ok", "error", "issue"}``, refused naming why."""
    now = time.time() if now is None else now
    try:
        issue = {"id": "pl-" + uuid.uuid4().hex[:12],
                 "name": _text(name, MAX_NAME_CHARS, "the planted issue's name"),
                 "evidence": patterns_of(evidence),
                 "why": _text(why, MAX_NOTE_CHARS, "why", required=False),
                 "by": actor, "at": _iso(now)}
    except PlantedRefused as exc:
        return {"ok": False, "error": str(exc), "issue": None}
    with _lock(network):
        got = planted(network)
        if got["state"] == "unreadable":
            return {"ok": False, "issue": None, "error": f"the planted issues cannot be read "
                    f"({got['error']}), so none is added"}
        if len(got["issues"]) >= MAX_PLANTED:
            return {"ok": False, "issue": None,
                    "error": f"{network} has {MAX_PLANTED} planted issues, the most kept"}
        _write_json(_planted_path(network), {"issues": got["issues"] + [issue]})
    return {"ok": True, "error": "", "issue": issue}


def set_why(network: str, pid: str, why: str, *, actor: str, now: float = None) -> dict:
    """A person's note on why a planted issue was found or missed: ``{"ok", "error"}``."""
    now = time.time() if now is None else now
    if not _PLANTED_ID.match(str(pid or "")):
        return {"ok": False, "error": f"{pid!r} is not a planted issue's id"}
    try:
        note = _text(why, MAX_NOTE_CHARS, "why", required=False)
    except PlantedRefused as exc:
        return {"ok": False, "error": str(exc)}
    with _lock(network):
        got = planted(network)
        if got["state"] == "unreadable":
            return {"ok": False, "error": f"the planted issues cannot be read ({got['error']})"}
        issues = got["issues"]
        hit = next((i for i in issues if i.get("id") == pid), None)
        if hit is None:
            return {"ok": False, "error": f"no planted issue {pid} on {network}"}
        hit.update(why=note, why_by=actor, why_at=_iso(now))
        _write_json(_planted_path(network), {"issues": issues})
    return {"ok": True, "error": ""}


def _matches(pattern: str, ident: str) -> bool:
    return fnmatch.fnmatchcase(ident, pattern) if "*" in pattern else ident == pattern


def marks(issues: list, result: dict, ids: set = None) -> list:
    """Each planted issue against an analysis *result* (`analyse`'s): ``found`` when a kept
    finding cites an id one of its patterns matches (``by`` names those findings), else
    ``missed``; ``in_collection`` False when none of its patterns matches an id the snapshot
    holds (*ids*; None when the snapshot is not read). No result: ``not analysed``."""
    out = []
    for issue in issues or []:
        row = dict(issue, found="not analysed", by=[], in_collection=None)
        if result and result.get("ok"):
            by = [f["finding"] for f in result.get("findings") or []
                  if any(_matches(p, e) for p in issue.get("evidence") or []
                         for e in f.get("evidence") or [])]
            row.update(found="found" if by else "missed", by=by)
        if ids is not None:
            row["in_collection"] = any(_matches(p, e) for p in issue.get("evidence") or []
                                       for e in ids)
        out.append(row)
    return out


def _sheet_rows(network: str) -> tuple:
    latest = _latest(network)
    result = analysis(network, latest.get("analysis") or "")
    snap = snapshot(network, result.get("snapshot_id") or "").get("snapshot") if result else None
    rows = marks(planted(network)["issues"], result, evidence_ids(snap) if snap else None)
    return result, rows


def sheet_csv(network: str, *, by: str, now: float = None) -> str:
    """The planted-issue sheet as CSV: its first lines name the network, the analysis, its
    snapshot and call, when it was made and by whom; then one row per planted issue."""
    now = time.time() if now is None else now
    result, rows = _sheet_rows(network)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["# network", network])
    w.writerow(["# analysis", result.get("id", "none"), "snapshot", result.get("snapshot_id", ""),
                "call", result.get("call_id", ""), "model", result.get("model", "")])
    w.writerow(["# made", _iso(now), "by", by])
    w.writerow(["planted", "found", "evidence", "found by", "in the collection", "why"])
    for r in rows:
        w.writerow([r["name"], r["found"], " ".join(r["evidence"]), " | ".join(r["by"]),
                    {True: "yes", False: "no", None: "not read"}[r["in_collection"]], r["why"]])
    return buf.getvalue()


def _md(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def sheet_markdown(network: str, *, by: str, now: float = None) -> str:
    """The planted-issue sheet as Markdown, with the same header facts as `sheet_csv`."""
    now = time.time() if now is None else now
    result, rows = _sheet_rows(network)
    lines = [f"# Planted issues on {_md(network)}", "",
             f"- Analysis: {result.get('id', 'none')} (snapshot {result.get('snapshot_id', '-')}, "
             f"collected {result.get('collected_at', '-')}; call {result.get('call_id', '-')}, "
             f"{result.get('model', '-')})",
             f"- Findings kept: {len(result.get('findings') or [])}; dropped by the check: "
             f"{result.get('dropped', 0)}",
             f"- Made {_iso(now)} by {_md(by)}", "",
             "| Planted | Found | Evidence | Found by | In the collection | Why |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| " + " | ".join(_md(x) for x in (
            r["name"], r["found"], " ".join(r["evidence"]), "; ".join(r["by"]) or "-",
            {True: "yes", False: "no", None: "not read"}[r["in_collection"]],
            r["why"] or "-")) + " |")
    return "\n".join(lines) + "\n"


# ───────────────────────────────────────────────────────────────────────────── the page's view

def view(network: str, now: float = None) -> dict:
    """What board I's region draws, from the network's small files only (no controller call, no
    write): the latest snapshot's summary and estimate, a collection running, the latest
    analysis and the planted issues marked against it."""
    from modules.ai import profiles

    latest = _latest(network)
    result = analysis(network, latest.get("analysis") or "")
    snap_sum = latest.get("snapshot") or {}
    issues = planted(network)
    rows = marks(issues["issues"], result)
    return {"network": network, "snapshot": snap_sum, "running": running(network, now),
            "collect_failed": latest.get("collect_failed") or {},
            "result": result, "planted": rows, "planted_state": issues["state"],
            "planted_error": issues["error"],
            "found": sum(r["found"] == "found" for r in rows),
            "missed": sum(r["found"] == "missed" for r in rows),
            "model_words": profiles.profile(profiles.task(FEATURE)["model"])["words"],
            "stale": bool(result and snap_sum and result.get("snapshot_id") != snap_sum.get("id"))}
