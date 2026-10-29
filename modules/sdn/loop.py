"""The SDN closed loop as a job, one per network (PHASE8_PLAN 17.1 S10): detect, classify and
respond in the network's mode, each pass logged, stoppable. Deterministic but for the classify
step, the one AI call, which runs only where its feature is on (below).

**A pass** (`run_pass`):
1. AUTO's expiry, if it passed, recorded once (`modes.record_expiry`);
2. `closed_loop.collect_threat_data(network)`, then `detect.observe` (each detection an alert
   with its evidence pack);
3. the detections that fired in this pass, not already mitigated (C2005, below), grouped into
   **incidents** (C1999, `modules/sdn/incidents.py`: the same rule and source, in one
   spelling, within the rule's own window; one that joins an incident already awaiting a
   person is recorded there as seen also, ``seen``, and nothing more); for each new incident,
   its response is proposed at its ingress switch (the switch where the source's host port is,
   from the controller's topology as the SDN reader stored it; when that cannot be told, the
   switch that saw it first, said why), and the other switches are recorded as seen also, so
   one attack on 50 switches is one AI call, one response and one Needs attention row;
   **classify** (`closed_loop.classify_threat`), once per incident, on its ingress detection,
   as a BACKGROUND call, the job's, on that detection (`triggers.background("sdn_classify",
   <job>, <network>, "detection", <its key>)`). The gateway refuses it, records the refusal
   and sends nothing unless the feature is on for the network and within its caps
   (`background.admit`, `over_cap`; off by default). The detection's evidence pack is the one
   `detect.observe` kept in this pass, in hand (C1970: finding it again read every pack in
   the store), its hash checked as ever. A classification that passes the code's check
   proposes its catalogue action and parameters; one proposing no catalogue action is kept
   for a person, never AUTO's. **Fail-safe (C1968):** a classification refused by the check,
   failed or unavailable (the feature off, a cap, the provider) never drops the detection: the
   rule's default in the network's response policy (`closed_loop.policy`) is kept awaiting a
   person, said as such ("AI classification refused: <why>; proposed by the catalogue
   default", with the refused answer's AI call), and AUTO never acts on it; a policy that
   cannot be read proposes no action, said, for a person. **At once (C1970):** the pass's
   detections are classified concurrently, each its own call (`fanout.read_each`, at most
   `CLASSIFY_WORKERS` at a time), so a pass of N detections waits about one call, not N (an
   AUTO pass of two took 31 s one after the other). Each detection's outcome is its own: a
   call that raises is that detection's "no AI classification (exception: …)", and a cap
   refusal is recorded for that detection alone. Each call's worst case is reserved against
   the caps under one lock across threads and processes (`ai.reservations`, C2039), so calls
   at once never pass a cap together; which of them a cap refuses, when it fits only some, is
   the order they reach that lock. Everything after the calls stays in the detections'
   order, never the order the calls finish: each detection's classify line ("the step took
   X s", its own call's time), then its response, one after the other (an AUTO apply holds
   its switch; a write is never concurrent), then the pass's classify total;
4. **respond in the mode** (`modes.decide`): in AUTO, an action of a classification that
   passed, within the allowed risk, is previewed and applied through the flow-operation core
   as Mercury, recorded as autonomous with the setting and its reason, and with who chose the
   action; otherwise (HITL, the default) the response is kept as awaiting a person
   (`pending`), with the classification when there is one, its preview built fresh when a
   person opens it. **AUTO's own preview failing (C2159)** sends nothing and keeps the
   response awaiting a person as HITL does, the failure said on it ("HITL for this one: AUTO
   could not preview <action>: <why>"), so its card and its Needs attention row name it,
   where it was once said only in this log. A detection that fires again while its response
   awaits a person is not classified again: the response is marked active again;
5. a response's meter whose flows have expired is removed (`flow_ops.expire_meters`).

**Already mitigated (C2005).** A detection that fires while one of Mercury's responses already
holds its source off is recorded, never proposed: no card, no AI call, nothing sent. The scan
rule's 60 s window still held the source's ports after its rate limit was applied, so the walk
of 2026-10-28 (section D) raised a second card for the same scan, and AUTO would have applied
the same response again on every re-fire. The check runs before the classify step, since it
needs only deterministic data in hand (the detection, the flow intent, this pass's
collection), so a re-fire under a response spends no AI call: by CLAUDE.md's AI cost rules a
background call runs only when deterministic code has found something, and a threat Mercury is
already answering is not a new finding. A response **holds** the detection (`holds`,
`covering`) when it is one of `HOLDING_ACTIONS` recorded in the flow intent (installed, not
withdrawn), for the same rule, on the same connection and switch (its flows act on that switch
only), and for the same subject: the detection's own key, or every source it names among the
sources the response's flows match (IPv4 and IPv6 in one spelling, a MAC address lower-case;
a flood over MAC-only flows names no address and is held by its key, its port); AND its hard
timeout has not passed; AND it is **in force**: every one of its flows is on the switch as this
pass's collection read it (a switch whose flows were not read is not judged, so not held), and
the SDN reader's stored value does not read its meter missing (`reapply.lost`; the collection
reads no meters). A response that matches and is not in force is **lost** (C2018): the
detection is answered as new, and its line names the lost response, what is missing, and that
Needs attention has its row and SDN › Flows its Re-apply…; one that matches and has expired is
named too. The record (``mitigated`` in the response store, with the response, its operation
and until when) and the log line are drawn in the loop's log on SDN › Responses, as a
detection that fires again while its response awaits a person is. A held detection is checked
again on every pass while it stays detected: once its response is no longer in force (expired,
or lost) the hold is ``released``, saying why, and the detection is classified and answered as
new in that pass; a detection that resolves releases its hold too. **At incident level
(C1999):** a response applied at its incident's known ingress switch holds the source off on
every switch of its connection (`covering`'s *across*), since the source enters by that port:
another switch's detection of the same rule and source under it is already mitigated too. A
response applied where the ingress could not be told holds its own switch only.

A detection that resolves (`detect.observe`: a collection that judged its subject no longer
shows it) never closes its response: the response stays awaiting a person, marked "threat no
longer active since <time>", its classification kept, until a person approves or dismisses
it (C1968).

**The log** (``sdn_loop.jsonl`` in the network's folder): one line per step of each pass, with
its time, what it read and decided; `log_lines` reads the newest. A pass with no new detection
says which it is: "network healthy: no threat detected" only when the collection read every
switch whole and no detection is active; "no new threat; N still active: …" naming them; or
that the collection was partial, or read no switch, never called healthy. **A response's line**
(`closed_loop.log_response`, AUTO's apply here and a person's confirm on the page alike): who
applied which action on which switch, the operation's id, and the resulting entries as its
Verify read them back (each flow's match, actions, priority, idle and hard timeouts and cookie,
a meter's band; one not read back said so). **The job** runs in a thread
of the process that started it (`start`), its passes scheduled start to start every interval
(`schedule`, C1972): a pass that takes longer starts the next at once and says so in the log;
`stop` ends it after its current pass, recording who and when. One loop per network: a second
start is refused, naming who started the first.

**Pending responses** (``sdn_responses.jsonl``), one per incident: ``proposed`` (the detection
it is proposed at, the action, its risk, when, the classification if the loop's call made one,
or the refused call, and its ``incident``: key, window, ingress, the switches seen also), then
any number of ``classified`` (a person's Classify: the classification, and the action it
proposes), ``seen`` (other switches seeing it later, within its window; C1999), ``inactive``
(none of its switches shows it any longer: since when) and ``active`` (it fired again),
then one of ``confirmed`` (the operation that answered it) or ``dismissed`` (by whom and why).
``cleared`` (the detection resolved before anyone acted) is no longer written, and still read
as closed in an older record. A hold (C2005) is ``mitigated`` (the detection, the response
holding it, its operation and until when) then ``released`` (why); its id (``mit-…``) is never
a response's, so `awaiting` passes over both.
"""

import calendar
import json
import logging
import math
import os
import re
import secrets
import threading
import time

log = logging.getLogger(__name__)

LOG_FILE = "sdn_loop.jsonl"
PENDING_FILE = "sdn_responses.jsonl"
DEFAULT_INTERVAL = 10.0
MIN_INTERVAL = 5.0
MAX_INTERVAL = 600.0
#: The loop's collection samples port counters this far apart within a pass (seconds).
SAMPLE_INTERVAL = 5.0
LOG_KEEP = 200

_jobs = {}
_jobs_lock = threading.Lock()


def _path(network: str, name: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), name)


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _append(network: str, name: str, row: dict) -> None:
    from modules.config import open_secure
    from modules.filestore import PathLock

    path = _path(network, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PathLock(path):
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _read(network: str, name: str) -> dict:
    path = _path(network, name)
    if not os.path.exists(path):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"state": "ok", "error": "",
                    "rows": [json.loads(line) for line in fh if line.strip()]}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": f"{name}: {exc}"}


def say(network: str, step: str, words: str, now: float = None, **extra) -> dict:
    """One line of the loop's log."""
    now = time.time() if now is None else now
    row = {"at": _iso(now), "step": step, "words": words, **extra}
    _append(network, LOG_FILE, row)
    return row


def log_lines(network: str, limit: int = 50) -> dict:
    got = _read(network, LOG_FILE)
    return dict(got, rows=got["rows"][-limit:])


# ───────────────────────────────────────────────────────────────────────────── runs (C1971)
# The log is one file of every run on the network. A RUN is its ``start`` line and every line
# after it up to the next ``start``; lines written before any recorded start (a log older than
# the start line) are one run of their own, named `BEFORE_FIRST_START`.

#: The run's name for lines written before any recorded start.
BEFORE_FIRST_START = "before-the-first-recorded-start"
#: The start line's words name its job (`start`): "... as job <id>".
_JOB_IN_WORDS = re.compile(r" as job (sdn-loop-\S+)$")


def _run_job(network: str, row: dict) -> str:
    """The job id a ``start`` line names: its ``job`` field when it carries one, else the id
    its words end with, else `job_id` at the line's own time."""
    if row.get("job"):
        return str(row["job"])
    m = _JOB_IN_WORDS.search(row.get("words") or "")
    if m:
        return m.group(1)
    try:
        since = calendar.timegm(time.strptime(row.get("at") or "", "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        since = None
    return job_id(network, since)


def _runs_of(network: str, rows: list) -> list:
    """*rows* (the log, oldest first) cut into runs, oldest first, each ``{"job", "at",
    "until", "count", "rows"}``."""
    runs = []
    for row in rows:
        if row.get("step") == "start" or not runs:
            started = row.get("step") == "start"
            runs.append({"job": _run_job(network, row) if started else BEFORE_FIRST_START,
                         "at": row.get("at") or "", "rows": []})
        runs[-1]["rows"].append(row)
    for r in runs:
        r["count"] = len(r["rows"])
        r["until"] = r["rows"][-1].get("at") or ""
    return runs


def run_log(network: str, job: str = "") -> dict:
    """One run of the loop on *network*, whole: the run named *job*, else the newest.
    ``{"state", "error", "job", "at", "until", "rows" (oldest first), "runs"}``; *runs* names
    every run in the log, newest first (``{"job", "at", "count"}``). *state* is ``absent`` (no
    log yet), ``unreadable``, ``unknown`` (no run is named *job*: *error* names it and how many
    runs there are) or ``ok``."""
    got = _read(network, LOG_FILE)
    out = {"state": got["state"], "error": got["error"], "job": "", "at": "", "until": "",
           "rows": [], "runs": []}
    if got["state"] != "ok":
        return out
    runs = _runs_of(network, got["rows"])
    out["runs"] = [{"job": r["job"], "at": r["at"], "count": r["count"]}
                   for r in reversed(runs)]
    if not runs:
        return out
    pick = next((r for r in runs if r["job"] == job), None) if job else runs[-1]
    if pick is None:
        return dict(out, state="unknown", error=(f"no run {job} is in {network}'s loop log, "
                                                 f"which holds {len(runs)} run(s)"))
    return dict(out, job=pick["job"], at=pick["at"], until=pick["until"], rows=pick["rows"])


def run_text(network: str, job: str = "") -> dict:
    """A run's log as plain text, for its download: ``{"state", "error", "job", "text"}``. A
    header names the network, the run, its first and last line's times and the line count;
    then one line per log line, oldest first: its time, step and words, then any other field
    (``key=value``, sorted). Masked on the way out (`redact.redact_text`)."""
    from modules.redact import redact_text

    got = run_log(network, job)
    if got["state"] != "ok" or not got["rows"]:
        return {"state": got["state"] if got["state"] != "ok" else "absent",
                "error": got["error"] or f"{network}'s loop has written no log yet",
                "job": got["job"], "text": ""}
    lines = [f"# Mercury SDN loop log: network {network}, run {got['job']}",
             f"# {got['at']} to {got['until']}, {len(got['rows'])} line(s), oldest first"]
    for r in got["rows"]:
        extra = " ".join(f"{k}={r[k]}" for k in sorted(r) if k not in ("at", "step", "words"))
        lines.append(f"{r.get('at', '')} {r.get('step', '')}: {r.get('words', '')}"
                     + (f" [{extra}]" if extra else ""))
    return {"state": "ok", "error": "", "job": got["job"],
            "text": redact_text("\n".join(lines) + "\n")}


# ───────────────────────────────────────────────────────────────────────────── pending

def propose(network: str, detection: dict, action: str, risk: str, *, why: str,
            now: float = None, classification: dict = None, params: dict = None,
            classified: str = "", refused_call: str = "", incident: dict = None,
            auto_failed: str = "") -> dict:
    """Keep a response awaiting a person: one incident's (C1999). One per detection key: a
    second for a key already awaiting (its incident's own, or one seen also) is not added.
    *classification* the loop's AI classification, when one passed; *params* the action's
    checked parameters; *classified* why there is none, in words; *refused_call* the AI call
    whose answer the check refused, when one was; *incident* `incidents.record`'s answer (its
    key, window, ingress and the switches seen also), kept on the row, the detection carrying
    its compact copy (`incidents.stamp`). Without one the response is an incident of its
    detection alone. *auto_failed* why AUTO, having decided to act, sent nothing: its own
    preview's failure (C2159) or its confirm's refusal before any request (C2195): the
    response is a person's as if AUTO were off, and the failure is kept on it, for its card
    and its Needs attention row."""
    from modules.sdn import incidents

    now = time.time() if now is None else now
    for row in awaiting(network)["rows"]:
        if detection.get("key") in row.get("members", ()):
            return row
    row = {"kind": "proposed", "id": f"resp-{secrets.token_hex(5)}", "at": _iso(now),
           "action": action, "risk": risk, "why": why,
           "detection": incidents.stamp(detection, incident) if incident else detection,
           "classification": classification, "params": dict(params or {}),
           "classified": classified, "refused_call": refused_call}
    if auto_failed:
        row["auto_failed"] = auto_failed
    if incident:
        row["incident"] = incident
    _append(network, PENDING_FILE, row)
    return row


def seen_also(network: str, response_id: str, detections: list, *, now: float = None) -> dict:
    """Record *detections* (another switch's sighting of the same rule and source, within its
    window) as seen also by the incident awaiting a person as *response_id* (C1999): not
    classified again, nothing proposed."""
    from modules.sdn import incidents

    now = time.time() if now is None else now
    row = {"kind": "seen", "id": response_id, "at": _iso(now),
           "detections": [incidents.brief(d) for d in detections]}
    _append(network, PENDING_FILE, row)
    return row


def mark(network: str, response_id: str, how: str, *, since: str = "",
         now: float = None) -> dict:
    """Mark a response awaiting a person ``inactive`` (its detection resolved; *since* the
    collection that no longer showed it) or ``active`` (it fired again). Neither closes it:
    only a person does (C1968)."""
    if how not in ("inactive", "active"):
        raise ValueError(f"a response is marked inactive or active, not {how!r}")
    now = time.time() if now is None else now
    row = {"kind": how, "id": response_id, "at": _iso(now), "since": since or _iso(now)}
    _append(network, PENDING_FILE, row)
    return row


def classified(network: str, response_id: str, got: dict, *, actor: str,
               now: float = None) -> dict:
    """Keep a person's classification (`closed_loop.classify_threat`'s passing answer *got*)
    with the response awaiting them: its catalogue action and parameters become what is
    proposed, and ``none`` keeps the action as it was (a person decides). The response stays
    awaiting a person: nothing is sent."""
    from modules.sdn import closed_loop

    row = next((r for r in awaiting(network)["rows"] if r.get("id") == response_id), None)
    if row is None:
        raise ValueError(f"no response {response_id!r} is awaiting a person on {network}")
    action = got.get("action") or ""
    keep = action == closed_loop.NO_ACTION or action not in closed_loop.CATALOGUE
    now = time.time() if now is None else now
    out = {"kind": "classified", "id": response_id, "at": _iso(now), "actor": actor,
           "classification": got.get("classification"),
           "action": row.get("action") if keep else action,
           "risk": row.get("risk") if keep else closed_loop.CATALOGUE[action]["risk"],
           "params": dict(row.get("params") or {}) if keep else dict(got.get("params") or {})}
    _append(network, PENDING_FILE, out)
    return out


def resolve(network: str, response_id: str, how: str, *, actor: str, why: str = "",
            operation: str = "", now: float = None) -> dict:
    """Close an awaiting response, a person's act: ``confirmed`` (with its operation's id) or
    ``dismissed`` (a reason required). Nothing else closes one: a detection that resolves
    marks its response inactive (`mark`), never closes it (C1968)."""
    if how not in ("confirmed", "dismissed"):
        raise ValueError(f"a response is confirmed or dismissed by a person, not {how!r}")
    if how == "dismissed" and not (why or "").strip():
        raise ValueError("a dismissal names its reason")
    if not any(r.get("id") == response_id for r in awaiting(network)["rows"]):
        raise ValueError(f"no response {response_id!r} is awaiting a person on {network}")
    now = time.time() if now is None else now
    row = {"kind": how, "id": response_id, "at": _iso(now), "actor": actor,
           "why": (why or "").strip(), "operation": operation}
    _append(network, PENDING_FILE, row)
    return row


#: The kinds that close a response: a person's, or (an older record's) ``cleared``.
CLOSED = ("confirmed", "dismissed", "cleared")


def awaiting(network: str) -> dict:
    """The responses awaiting a person, oldest first, each with its latest classification,
    ``inactive_since`` (its incident's threat no longer active since then, "" while it is),
    and its incident (C1999): ``seen_also`` (each other switch that saw it, the record's and
    each later ``seen``), ``members`` (every detection key it holds, its own first) and
    ``last_seen`` (its latest sighting: a detection's time, or its firing again)."""
    got = _read(network, PENDING_FILE)
    open_rows = {}
    for r in got["rows"]:
        kind, rid = r.get("kind"), r.get("id")
        if kind == "proposed":
            d = r.get("detection") or {}
            also = list((r.get("incident") or {}).get("seen_also") or [])
            open_rows[rid] = dict(r, inactive_since="", seen_also=also,
                                  members=[d.get("key")] + [s.get("key") for s in also],
                                  last_seen=max(d.get("at") or "", r.get("at") or ""))
        elif rid not in open_rows:
            continue
        elif kind == "seen":
            row = open_rows[rid]
            new = [s for s in r.get("detections") or [] if s.get("key") not in row["members"]]
            open_rows[rid] = dict(row, seen_also=row["seen_also"] + new,
                                  members=row["members"] + [s.get("key") for s in new],
                                  last_seen=max([row["last_seen"], r.get("at") or ""]
                                                + [s.get("at") or "" for s in new]))
        elif kind == "classified":
            open_rows[rid] = dict(open_rows[rid], **{
                k: r.get(k) for k in ("classification", "action", "risk", "params")},
                classified_at=r.get("at"), classified_by=r.get("actor"))
        elif kind == "inactive":
            open_rows[rid] = dict(open_rows[rid], inactive_since=r.get("since") or r.get("at"))
        elif kind == "active":
            open_rows[rid] = dict(open_rows[rid], inactive_since="",
                                  last_seen=max(open_rows[rid]["last_seen"], r.get("at") or ""))
        elif kind in CLOSED:
            open_rows.pop(rid, None)
    return dict(got, rows=list(open_rows.values()))


# ───────────────────────────────────────────────────────────────────── already mitigated (C2005)

#: The catalogue actions whose response holds a source off on its switch until its hard
#: timeout. Removing an unauthorised flow holds nothing off: a flow added again is a new one.
HOLDING_ACTIONS = ("drop_source", "rate_limit_source")


def canon_source(value) -> str:
    """A source in one spelling: an IPv4 or IPv6 address compressed, a MAC address lower-case
    with colons; "" for none or anything else."""
    import ipaddress

    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return ipaddress.ip_address(text).compressed
    except ValueError:
        pass
    mac = re.fullmatch(r"([0-9A-Fa-f]{2})(?:[:-]([0-9A-Fa-f]{2})){5}", text)
    if mac:
        return ":".join(re.findall(r"[0-9a-f]{2}", text.lower()))
    return ""


def _answered_by(network: str) -> dict:
    """``{operation: response id}``: each response a person confirmed, by the operation that
    applied it (AUTO's responses have no response id: their operation names them)."""
    return {r.get("operation"): r.get("id") for r in _read(network, PENDING_FILE)["rows"]
            if r.get("kind") == "confirmed" and r.get("operation")}


def _meters_lost(network: str, now: float, cached: dict = None) -> dict:
    """``{operation: words}``: each response whose meter the SDN reader's stored value reads
    missing (`reapply.lost`), and an ``error`` key's words when that value cannot be read.
    *cached* is that value as `reader_job.read_cached_for` answered it, when the caller has
    already read it (Needs attention's source, C2070); otherwise it is read here."""
    from modules import reader_job
    from modules.readers import sdn_controllers as R
    from modules.sdn import reapply

    try:
        if cached is None:
            cached = reader_job.read_cached_for(R.READER_NAME, network) or {}
    except Exception as exc:                          # noqa: BLE001 (said in the hold's words)
        return {"error": f"the SDN reader's stored value could not be read ({type(exc).__name__})"}
    good = ((cached.get("doc") or {}).get("last_good") or {})
    out = {}
    for x in reapply.lost(good.get("value") or {}, now=now):
        if x.get("meter") is not None:
            out[x["key"]] = (f"its meter {x['meter']} is missing from the switch as the SDN reader "
                             f"read it at {x.get('as_of') or good.get('value_at') or '?'}")
    if not good:
        out["error"] = "the SDN reader has no stored value for this network yet"
    return out


def holds(network: str, collected: dict, now: float, *, cached: dict = None) -> dict:
    """Mercury's responses on *network* that hold a source off (`HOLDING_ACTIONS`), each judged
    against *collected* (this pass's collection, or the SDN reader's stored value in its shape:
    `reapply.as_collected`) at *now*, its meters against the SDN reader's stored value
    (*cached*, `_meters_lost`): ``{"state" ("ok" or "unreadable"),
    "error", "holds": [{"key" (its operation), "id" (the response a person confirmed, else the
    operation), "action", "rule", "detection_key", "sources", "connection", "dpid",
    "dpid_hex", "cookies", "until" (epoch: its first flow's hard timeout), "state", "words"}]}``.
    *state* is ``active`` (every flow on the switch as read now, its hard timeout ahead, its
    meter not read missing), ``expired``, ``lost`` (C2018: something missing while it has time
    left; *words* say what), or ``not_judged`` (the switch's flows were not read in this
    collection, or a flow has no hard timeout recorded)."""
    from modules.sdn import flow_intent, reapply

    intent = flow_intent.intent(network)
    if intent["state"] != "ok":
        return {"state": "unreadable", "error": intent["error"], "holds": []}
    groups = {}
    for r in intent["flows"]:
        resp = r.get("response")
        if not reapply.is_response(resp) or resp.get("action") not in HOLDING_ACTIONS:
            continue
        gk = (r.get("connection"), r.get("dpid"),
              reapply.group_key(resp, f"cookie:{r.get('cookie_hex')}"))
        groups.setdefault(gk, []).append(r)
    if not groups:
        return {"state": "ok", "error": "", "holds": []}
    switches = {(c.get("connection"), s.get("dpid")): s
                for c in (collected or {}).get("controllers") or []
                for s in c.get("switches") or []}
    answered, meters = _answered_by(network), None
    out = []
    for (conn, dpid, key), rows in sorted(groups.items(), key=lambda kv: str(kv[0])):
        resp = rows[0]["response"]
        det = resp.get("detection") or {}
        sources = {canon_source(det.get("source"))} | {
            canon_source((f.get("match") or {}).get(field))
            for f in rows for field in ("ipv4_src", "ipv6_src")}
        ends = [f["installed_at"] + f["hard_timeout"] for f in rows
                if f.get("hard_timeout") and isinstance(f.get("installed_at"), (int, float))]
        cookies = [f.get("cookie_hex") or flow_intent.cookie_hex(f.get("cookie")) for f in rows]
        hold = {"key": key, "id": answered.get(key) or key, "action": resp.get("action"),
                "rule": det.get("rule") or "", "detection_key": det.get("key") or "",
                # C1999: applied at its incident's known ingress switch, so it holds the
                # source off on every switch of its connection (`covering`'s *across*).
                "ingress": bool((det.get("incident") or {}).get("ingress")),
                "sources": sorted(s for s in sources if s), "connection": conn, "dpid": dpid,
                "dpid_hex": rows[0].get("dpid_hex") or det.get("dpid_hex") or "",
                "cookies": cookies, "until": min(ends) if len(ends) == len(rows) else None}
        sw = switches.get((conn, dpid))
        if hold["until"] is None:
            hold.update(state="not_judged", words="a flow of it has no hard timeout recorded")
        elif now >= hold["until"]:
            hold.update(state="expired", words=f"its hard timeout ended at {_iso(hold['until'])}")
        elif sw is None or sw.get("active_flows") is None:
            hold.update(state="not_judged",
                        words=f"switch {hold['dpid_hex'] or dpid}'s flows were not read in this "
                              "collection")
        else:
            held = {f.get("cookie") for f in sw.get("flows") or []}
            gone = [c for f, c in zip(rows, cookies) if f.get("cookie") not in held]
            if meters is None:
                meters = _meters_lost(network, now, cached)
            if gone:
                left = reapply.left_words(hold["until"] - now)
                hold.update(state="lost", words=(
                    f"{len(gone)} of its {len(rows)} flow(s) ({', '.join(gone)}) are not on "
                    f"the switch as this collection read it, with {left} of its hard timeout "
                    "left"))
            elif key in meters:
                hold.update(state="lost", words=meters[key])
            else:
                hold.update(state="active", words=(
                    f"its {len(rows)} flow(s) on the switch as this collection read it"
                    + (f"; its meter as the SDN reader read it ({meters['error']})"
                       if resp.get("action") == "rate_limit_source" and "error" in meters
                       else "")))
        out.append(hold)
    return {"state": "ok", "error": "", "holds": out}


def covering(d: dict, judged: list, *, across: bool = False) -> tuple:
    """The response holding detection *d* off among `holds`' *judged*, and the others that
    would have held it but are not in force: ``(active hold or None, [the others])``. A hold
    covers *d* when it is for the same rule on the same connection and switch, and its
    detection was *d*'s own (the same key) or every source *d* names is one it holds off.
    With *across* (the loop's own judgement, C1999), a hold applied at its incident's known
    ingress switch (``ingress``) covers *d* on any switch of the same connection when every
    source *d* names is one it holds off: the source enters by that switch's port, so it is
    held off from every switch behind it."""
    from modules.sdn import closed_loop
    from modules.sdn.drivers.base import SpecError, parse_dpid

    try:
        dpid = parse_dpid(d.get("dpid") if d.get("dpid") is not None else d.get("dpid_hex"))
    except SpecError:
        return None, []
    named = {canon_source(s) for s in closed_loop._sources(d)}
    by_source = bool(named) and "" not in named
    match = [h for h in judged
             if h["rule"] == d.get("rule") and h["connection"] == d.get("connection")
             and ((h["dpid"] == dpid
                   and ((h["detection_key"] and h["detection_key"] == d.get("key"))
                        or (by_source and named <= set(h["sources"]))))
                  or (across and h.get("ingress") and by_source
                      and named <= set(h["sources"])))]
    active = [h for h in match if h["state"] == "active"]
    if active:
        return max(active, key=lambda h: h["until"]), []
    return None, match


def mitigated(network: str, d: dict, hold: dict, *, now: float = None) -> dict:
    """Record that detection *d* fired while *hold* (a `holds` row, ``active``) holds its
    source off: no card, no AI call, nothing sent. Its hold stays open until `release`."""
    now = time.time() if now is None else now
    row = {"kind": "mitigated", "id": f"mit-{secrets.token_hex(5)}", "at": _iso(now),
           "key": d.get("key"), "by": hold["id"], "operation": hold["key"],
           "action": hold["action"], "until": _iso(hold["until"]),
           "until_epoch": hold["until"], "cookies": list(hold["cookies"]),
           "detection": {k: d.get(k) for k in ("key", "rule", "title", "connection", "dpid_hex",
                                               "source", "port", "words", "at")}}
    _append(network, PENDING_FILE, row)
    return row


def release(network: str, hold_id: str, why: str, *, now: float = None) -> dict:
    """Close the hold *hold_id*, saying *why* (its response no longer in force, or its
    detection resolved)."""
    now = time.time() if now is None else now
    row = {"kind": "released", "id": hold_id, "at": _iso(now), "why": why}
    _append(network, PENDING_FILE, row)
    return row


def open_holds(network: str) -> dict:
    """The holds still open (`mitigated`, not `release`d), oldest first."""
    got = _read(network, PENDING_FILE)
    out = {}
    for r in got["rows"]:
        if r.get("kind") == "mitigated":
            out[r.get("id")] = r
        elif r.get("kind") == "released":
            out.pop(r.get("id"), None)
    return dict(got, rows=list(out.values()))


def _judge_holds(network: str, collected: dict, seen: dict, candidates: list,
                 now: float) -> tuple:
    """The pass's holds (C2005), judged before any AI call: ``(holding, notes, releasing)``.
    *candidates* the detections that fired and await no person; *holding* ``{key: hold}``
    for each candidate, or held detection released here, that an active response covers
    (`covering`); *notes* ``{key: [words]}`` for its log lines (a hold released, a response
    that would cover it lost, expired or not judged); *releasing* each detection held so far
    that is still detected and whose response no longer holds it off (its hold released here).
    A held detection that resolved, or is no longer detected, has its hold released; one not
    judged in this collection stays held."""
    holding, notes, releasing = {}, {}, []
    still_open = open_holds(network)["rows"]
    if not candidates and not still_open:
        return holding, notes, releasing
    judged = holds(network, collected, now)
    fired = set(seen.get("fired") or [])
    current = {d["key"]: d for d in seen.get("detections") or []}
    resolved = set(seen.get("resolved") or [])
    unjudged = {u.get("key") for u in seen.get("unjudged") or []}
    by_op = {h["key"]: h for h in judged["holds"]}
    for r in still_open:
        key = r.get("key")
        if key in resolved or key in fired:
            release(network, r["id"], "its detection resolved" if key in resolved else
                    "its detection fired again, judged afresh", now=now)
        elif key in current:
            h = by_op.get(r.get("operation"))
            if judged["state"] == "ok" and h is not None and h["state"] == "active":
                continue
            why = (f"whether it is in force could not be read ({judged['error']})"
                   if judged["state"] != "ok" else
                   "it is no longer recorded as installed (withdrawn)" if h is None else
                   h["words"])
            release(network, r["id"], why, now=now)
            releasing.append(current[key])
            notes.setdefault(key, []).append(
                f"{_source_words(current[key])} is still detected, and response {r.get('by')} "
                f"no longer holds it off ({why}): hold {r['id']} released")
        elif key not in unjudged:
            release(network, r["id"], "its detection is no longer detected", now=now)
    for d in candidates + releasing:
        key = d["key"]
        if judged["state"] != "ok":
            notes.setdefault(key, []).append(
                f"{_source_words(d)}: whether a response already holds it off could not be "
                f"read ({judged['error']}): answered as new")
            continue
        active, others = covering(d, judged["holds"], across=True)
        if active is not None:
            holding[key] = active
            continue
        for h in others:
            named = f"response {h['id']} ({h['action']}, operation {h['key']})"
            notes.setdefault(key, []).append(
                f"{named} would hold {_source_words(d)} off and is not in force: {h['words']}; "
                "Needs attention names it and SDN › Flows offers its Re-apply… (C2018); "
                "answered as new" if h["state"] == "lost" else
                f"{named} held {_source_words(d)} off until {_iso(h['until'])} UTC, its hard "
                "timeout; answered as new" if h["state"] == "expired" else
                f"{named} may hold {_source_words(d)} off and is not judged: {h['words']}; "
                "answered as new")
    return holding, notes, releasing


#: How many switches an incident's log line names before it counts the rest.
SWITCHES_NAMED = 5


def _switches_words(members: list) -> str:
    names = [m.get("dpid_hex") or str(m.get("dpid")) for m in members]
    shown = ", ".join(names[:SWITCHES_NAMED])
    more = len(names) - SWITCHES_NAMED
    return (f"{len(names)} switch{'es' if len(names) != 1 else ''} ({shown}"
            + (f" and {more} more" if more > 0 else "") + ")")


def _incident_words(inc: dict) -> str:
    first = inc["members"][0]
    return f"{first.get('title') or inc.get('rule')} from {inc.get('source') or '?'}"


def _incidents(network: str, seen: dict, fresh: list, rows_waiting: list, now: float) -> tuple:
    """The pass's new detections (*fresh*: fired or released, awaiting nobody and held by
    nothing) as incidents (C1999; `modules/sdn/incidents.py`): ``({key: incident}, todo)``,
    each incident ``joined`` (the incident awaiting a person it joins, among *rows_waiting*,
    or None) and, when new, ``chosen`` (its ingress, `incidents.ingress`) and ``record``;
    *todo* the one detection per new incident its classification reads, its ingress's. The
    windows are the thresholds this collection was judged by (`detect.observe`'s), else the
    network's; the controller's topology is the SDN reader's stored value, read at most once."""
    from modules.sdn import detect, incidents

    unique = []
    for d in fresh:
        if all(u["key"] != d["key"] for u in unique):
            unique.append(d)
    if not unique:
        return {}, []
    values = seen.get("thresholds") or {}
    if not values:
        th = detect.thresholds(network)
        values = th["values"] if th.get("ok") else {}
    topo = {}

    def stored():
        if "v" not in topo:
            try:
                from modules.sdn import topology
                topo["v"] = topology.stored(network)
            except Exception as exc:                  # noqa: BLE001 (said on the card)
                topo["v"] = {"state": "could not read", "why": type(exc).__name__}
        return topo["v"]

    incident_of, todo = {}, []
    for inc in incidents.group(unique, values):
        joined = next((r for r in (incidents.joinable(rows_waiting, m, now)
                                   for m in inc["members"]) if r is not None), None)
        inc["joined"] = joined
        if joined is not None and inc["key"].startswith(incidents.SINGLE + "|"):
            # A link port's detection joining by the host its flows carry (C2106): seen also,
            # saying why, under the incident's own source.
            inc["source"] = incidents.key_of(joined).partition("|")[2]
            inc["members"] = [incidents.via_link(m, incidents.key_of(joined))
                              for m in inc["members"]]
        if joined is None:
            chosen = incidents.ingress(network, inc, stored() if inc["source"] else {})
            inc.update(chosen=chosen, record=incidents.record(inc, chosen))
            todo.append(chosen["detection"])
        for m in inc["members"]:
            incident_of[m["key"]] = inc
    return incident_of, todo


def _source_words(d: dict) -> str:
    src = d.get("source") or ", ".join(d.get("sources") or [])
    return f"{d.get('title') or d.get('rule')} " + (
        f"from {src}" if src else f"on port {d.get('port')}") + f" on {d.get('dpid_hex')}"


# ───────────────────────────────────────────────────────────────────────────── one pass

def job_id(network: str, since: float = None) -> str:
    """The loop's job id on *network*, what its background AI calls name (``job:<id>``): the
    network's folder name, and the time the loop started when it is known."""
    from modules.config import list_slug

    stamp = time.strftime("-%Y%m%dT%H%M%SZ", time.gmtime(since)) if since else ""
    return f"sdn-loop-{list_slug(network)}{stamp}"


#: Why a response whose classification did not pass awaits a person, even in AUTO (C1968).
NOT_CLASSIFIED_WHY = ("no AI classification passed the check, so a person decides (AUTO acts "
                      "only on one that did)")
#: Who an autonomous response is applied as, in its record and its log line.
AUTO_ACTOR = "Mercury (AUTO)"

#: The most detections the Lab 8 walk's loop fired in one pass (measured 2026-10-27 over every
#: detection it classified, tests/fixtures/ai_cases/sdn_classify/recorded_walk.json, by the
#: collection each fired in: four, at 23:13:48 and 23:33:24 UTC; two switches, three rules).
#: tests/test_sdn_loop_parallel.py reads it again from that file.
BUSIEST_PASS_MEASURED = 4
#: A bound over what was measured (CLAUDE.md: about 2.5x).
BOUND_FACTOR = 2.5
#: The most classify calls one pass makes at once (C1970): `BOUND_FACTOR` times the busiest
#: pass measured, 10. A pass with more classifies them all, this many at a time, the rest as
#: each finishes; the bound keeps a storm of detections on a large network from opening that
#: many provider requests at once (each one the provider may rate-limit, and each reserved
#: against the caps while it is in flight). Its cost: a pass of more than 10 waits about
#: ceil(N / 10) calls, not one.
CLASSIFY_WORKERS = math.ceil(BOUND_FACTOR * BUSIEST_PASS_MEASURED)


def classify(network: str, d: dict, job: str, *, send=None, pack: dict = None) -> dict:
    """The pass's classify step for detection *d*: one background call through the gateway
    (`closed_loop.classify_pack` on *pack*, the pack `detect.observe` kept in this pass, else
    `closed_loop.classify_threat`, which finds it), and what it proposes (`verdict_of`). The
    pass runs one per detection at once (`run_pass`, `CLASSIFY_WORKERS`): nothing here is
    shared between two detections' calls but the gateway's own stores, each locked across
    threads and processes (the record of AI calls, the caps' reservations, the presses)."""
    from modules.ai import triggers
    from modules.config import list_slug
    from modules.sdn import closed_loop

    trigger = triggers.background(closed_loop.CLASSIFY_FEATURE, job, list_slug(network),
                                  "detection", d.get("key") or "")
    if pack is not None:
        got = closed_loop.classify_pack(network, d, pack, actor=triggers.actor_of(trigger),
                                        trigger=trigger, send=send)
    else:
        got = closed_loop.classify_threat(network, d, actor=triggers.actor_of(trigger),
                                          trigger=trigger, send=send)
    return verdict_of(network, d, got)


def verdict_of(network: str, d: dict, got: dict) -> dict:
    """What the classify step's answer *got* (`closed_loop.classify_pack`'s) proposes for
    detection *d*: ``{"action", "risk", "params", "classification", "words", "person", "why",
    "refused_call"}``. *person* True when only a person may act on it, *why* saying so: the AI
    proposed no catalogue action, or no classification passed (C1968: refused by the check,
    failed or unavailable, the rule's catalogue default is proposed for a person, never
    AUTO's; *refused_call* the refused answer's AI call). A call that raised is *got*
    ``{"ok": False, "error": "exception", "detail": <it>}`` (`run_pass`), the same fail-safe."""
    from modules.sdn import closed_loop

    # The rule's default is the network's response policy's (`closed_loop.policy`); a policy
    # that cannot be read proposes no action, said, and a person decides.
    pol = closed_loop.policy(network)
    default = ((pol["rules"].get(d["rule"]) or {}).get("default") or "") if pol["ok"] else ""
    out = {"action": default, "risk": closed_loop.CATALOGUE[default]["risk"] if default else "",
           "params": {}, "classification": None, "person": False, "why": "",
           "refused_call": ""}
    if not default:
        return dict(out, person=True, why=NOT_CLASSIFIED_WHY,
                    refused_call=got.get("call_id") if got.get("error") == "couldnt_classify"
                    else "",
                    words=(f"no action proposed: {pol['error'] or 'the policy names none'}; a "
                           "person decides"))
    if not got.get("ok"):
        if got.get("error") == "couldnt_classify":
            return dict(out, person=True, why=NOT_CLASSIFIED_WHY,
                        refused_call=got.get("call_id") or "",
                        words=(f"AI classification refused: {got.get('why')}; proposed by the "
                               f"catalogue default, {default} (AI call {got.get('call_id')})"))
        return dict(out, person=True, why=NOT_CLASSIFIED_WHY,
                    words=(f"no AI classification ({got.get('error')}: {got.get('detail')}); "
                           f"proposed {default}, {closed_loop.DEFAULT_WORDS}"))
    c = got["classification"]
    if got["action"] == closed_loop.NO_ACTION:
        return dict(out, classification=c, person=True,
                    why="the AI proposed no catalogue action, so a person decides", words=(
            f"AI call {got['call_id']}: {'a ' + c['threat_type'] if c['threat_detected'] else 'no'}"
            f" threat, no catalogue action proposed; {default} is drawn for a person to decide, "
            "never AUTO's"))
    action = got["action"]
    return dict(out, action=action, risk=closed_loop.CATALOGUE[action]["risk"],
                params=got["params"], classification=c,
                words=(f"AI call {got['call_id']}: a {c['threat_type']} threat, severity "
                       f"{c['severity']}"
                       + (f" (raised in code from the model's {c['severity_from_model']}: "
                          f"{c['severity_floor']})" if c.get("severity_floor") else "")
                       + f"; proposed {action}, checked in code"))


def run_pass(network: str, *, interval: float = SAMPLE_INTERVAL, driver=None, now=time.time,
             sleep=time.sleep, collect=None, observe=None, job: str = "", send=None,
             clock=time.monotonic) -> dict:
    """One pass of the loop (the module's docstring). ``{"ok", "error", "fired", "proposed",
    "applied", "inactive", "mitigated", "released", "lines"}``: *inactive* the responses still
    awaiting a person whose detection resolved in this pass (C1968: never closed by it);
    *mitigated* each detection recorded as already mitigated (C2005: ``{"key", "by", "until",
    "hold"}``); *released* each held detection answered as new because its response is no
    longer in force. *job* is the loop's id (`job_id`), what its background AI calls name;
    *send* replaces the AI provider (tests)."""
    from modules.fanout import Failed, read_each
    from modules.sdn import closed_loop, detect, flow_ops, incidents, modes

    job = job or job_id(network)

    out = {"ok": False, "error": "", "fired": [], "proposed": [], "applied": [], "inactive": [],
           "mitigated": [], "released": [], "incidents": [], "seen_also": [], "lines": []}

    def line(step, words, **extra):
        out["lines"].append(say(network, step, words, now(), **extra))

    def to_person(d, inc, rec, verdict, failed):
        """AUTO decided to act and sent nothing (*failed*, its preview's failure, C2159, or its
        confirm's refusal before any request, C2195): the detection is a person's, as if AUTO
        were off, through the HITL path's own response, the failure on it, so its card and
        its Needs attention row say why AUTO did not act."""
        row = propose(network, d, verdict["action"], verdict["risk"], now=now(), why=(
            f"HITL for this one: {failed}; nothing was sent, and a person previews it again "
            "and confirms or dismisses it"),
            classification=verdict["classification"], params=verdict["params"],
            classified=verdict["words"], refused_call=verdict["refused_call"],
            incident=rec, auto_failed=failed)
        out["proposed"].append(row["id"])
        out["incidents"].append({"key": inc["key"], "id": row["id"], "joined": False,
                                 "switches": 1 + len(rec["seen_also"])})
        line("respond", f"{failed}: nothing was sent; awaiting a person ({row['id']})",
             response=row["id"])

    try:
        if modes.record_expiry(network, now())["recorded"]:
            line("mode", "AUTO reached its expiry: the mode is HITL again")
        collected = collect() if collect else closed_loop.collect_threat_data(
            network, interval, sleep=sleep, driver=driver)
        s = collected.get("summary") or {}
        line("read", f"read {s.get('switches', 0)} switch(es): {s.get('flows', 0)} flows, port "
                     f"rates over {interval:g} s ({collected.get('state')})")
        began = clock()
        seen = (observe or detect.observe)(network, collected)
        judged_s = clock() - began
        if not seen.get("ok"):
            line("detect", f"nothing judged: {seen.get('error')}")
            out["error"] = seen.get("error") or ""
            return out
        fired = [d for d in seen.get("detections") or [] if d["key"] in set(seen["fired"])]
        resolved = list(seen.get("resolved") or [])
        # Each detection key an incident awaiting a person holds: its own and each seen also.
        rows_waiting = awaiting(network)["rows"]
        waiting = {k: r for r in rows_waiting
                   for k in r.get("members") or [(r.get("detection") or {}).get("key")]}
        held = [waiting[k] for k in resolved if k in waiting]
        # A pass with no new detection says which of four it is (objective 3.1): healthy only
        # when the collection read every switch whole and nothing is active; a detection still
        # active (or one whose subject was not read, so it stays firing) is named; a read that
        # failed in part, or covered no switch, is said and never called healthy.
        still = [d.get("words") or d.get("key") for d in seen.get("detections") or []
                 if d["key"] not in set(seen["fired"])] + [
            f"{u.get('title') or u.get('key')} ({u.get('words')})"
            for u in seen.get("unjudged") or []]
        state, switches = collected.get("state"), s.get("switches", 0)
        quiet = (f"no new threat; {len(still)} still active: {'; '.join(still)}" if still else
                 "network healthy: no threat detected" if state == "ok" and switches else
                 f"no threat detected on the switches read, but the collection was {state} "
                 f"({collected.get('error') or 'no reason given'}): not called healthy"
                 if switches else
                 f"no switch was read ({state}"
                 + (f": {collected.get('error') or collected.get('words')}"
                    if collected.get("error") or collected.get("words") else "")
                 + "): nothing judged healthy")
        line("detect", ("; ".join(d["words"] for d in fired) if fired else quiet)
             + (f"; {len(resolved)} no longer active (the collection judged its subject and "
                "no longer shows it)" if resolved else "")
             + (f", {len(held)} of them with a response still awaiting a person" if held
                else "") + (f" (judged in {judged_s:.1f} s)" if fired else ""),
             took_s=round(judged_s, 2))
        since = seen.get("collected_at") or _iso(now())
        # An incident is no longer active once none of its switches still shows it (C1999):
        # one switch's detection resolving while another's fires keeps it active.
        still = {d["key"] for d in seen.get("detections") or []} | {
            u.get("key") for u in seen.get("unjudged") or []}
        for row in held:
            if row["id"] in out["inactive"] or row.get("inactive_since") or \
                    set(row.get("members") or ()) & still:
                continue
            mark(network, row["id"], "inactive", since=since, now=now())
            out["inactive"].append(row["id"])
        kept = seen.get("kept") or {}
        # Already mitigated (C2005), before any AI call: a detection a response in force holds
        # off is recorded, not classified or proposed; a held one whose response is no longer
        # in force while it is still detected is answered as new in this pass (`releasing`).
        holding, notes, releasing = _judge_holds(
            network, collected, seen, [d for d in fired if d["key"] not in waiting], now())
        # Incidents (C1999), before any AI call: the new detections grouped by rule and source
        # within the rule's window; one joining an incident already awaiting a person is seen
        # also there; a new incident's response is proposed at its ingress switch.
        incident_of, todo = _incidents(network, seen, [
            d for d in fired + releasing if d["key"] not in waiting and d["key"] not in holding],
            rows_waiting, now())
        # Classified at once, each its own call (C1970): one per incident, its ingress
        # detection's, in the detections' order whatever order the calls finish in
        # (`fanout.read_each`); one that raises is its own Failed.
        took = {}

        def one(d):
            began = clock()
            try:
                return classify(network, d, job, send=send, pack=kept.get(d["key"]))
            finally:
                took[d["key"]] = clock() - began

        began = clock()
        verdicts = dict(zip([d["key"] for d in todo], read_each(
            one, todo, name="sdn-classify", max_workers=CLASSIFY_WORKERS)))
        classify_s = clock() - began
        released = {d["key"] for d in releasing}          # never one that fired (`_judge_holds`)
        for d in fired + releasing:
            out["released" if d["key"] in released else "fired"].append(d["key"])
            again = waiting.get(d["key"])
            if again is not None:
                if again.get("inactive_since"):
                    mark(network, again["id"], "active", now=now())
                line("respond", f"fired again while its response {again['id']} awaits a "
                                "person: not classified again")
                continue
            for words in notes.get(d["key"], ()):
                line("respond", words)
            hold = holding.get(d["key"])
            if hold is not None:
                row = mitigated(network, d, hold, now=now())
                out["mitigated"].append({"key": d["key"], "by": hold["id"],
                                         "until": row["until"], "hold": row["id"]})
                log.info("sdn loop: %s on %s fired again while mitigated by response %s until "
                         "%s: recorded, not proposed", d.get("rule"), d.get("dpid_hex"),
                         hold["id"], row["until"])
                line("respond", (
                    f"{_source_words(d)} fired again while mitigated by response {hold['id']} "
                    f"({hold['action']}, operation {hold['key']}) until {row['until']} UTC: "
                    f"{hold['words']}; recorded as already mitigated ({row['id']}), not "
                    "proposed: no AI call, nothing sent"), hold=row["id"], by=hold["id"])
                continue
            inc = incident_of.get(d["key"])
            if inc is None:
                continue
            if inc["joined"] is not None:
                # Seen also by an incident awaiting a person: recorded once for the pass's
                # members, at its first; not classified again, nothing proposed.
                if d["key"] == inc["members"][0]["key"]:
                    row = inc["joined"]
                    seen_also(network, row["id"], inc["members"], now=now())
                    if row.get("inactive_since"):
                        mark(network, row["id"], "active", now=now())
                    keys = [m["key"] for m in inc["members"]]
                    out["seen_also"] += keys
                    out["incidents"].append({"key": inc["key"], "id": row["id"],
                                             "joined": True, "switches": len(keys)})
                    line("incident", (
                        f"{_incident_words(inc)} seen also on {_switches_words(inc['members'])}"
                        f", within {inc['window']['seconds']} s of its last sighting: joins "
                        f"incident {row['id']}, awaiting a person since {row.get('at')}; not "
                        "classified again, nothing proposed"), incident=row["id"])
                continue
            if d["key"] != inc["chosen"]["detection"]["key"]:
                continue                      # seen also: said on its incident's line
            rec = inc["record"]
            if rec["seen_also"]:
                out["seen_also"] += [s["key"] for s in rec["seen_also"]]
                line("incident", (
                    f"{_incident_words(inc)} seen on {1 + len(rec['seen_also'])} switches "
                    f"({inc['window']['words']}): one incident, one AI call, one response; "
                    f"{rec['ingress_words']}; seen also on "
                    f"{_switches_words(rec['seen_also'])}"), switches=1 + len(rec["seen_also"]))
            d = incidents.stamp(d, rec)
            verdict = verdicts[d["key"]]
            if isinstance(verdict, Failed):
                # The call raised (not one of the gateway's own refusals): this detection's
                # fail-safe alone, the others' outcomes untouched.
                verdict = verdict_of(network, d, {"ok": False, "error": "exception",
                                                  "detail": str(verdict)})
            action, risk, params = verdict["action"], verdict["risk"], verdict["params"]
            # The step's time beside its words (C1970): this detection's own call, from its
            # start to its answer; the AI call's own latency is its row in the record of AI
            # calls, so the rest of the step is this less that.
            mine = took[d["key"]]
            line("classify", f"{verdict['words']} (risk {risk}; the step took {mine:.1f} s)",
                 took_s=round(mine, 2))
            # AUTO never acts on an inferred source (C2147): the detection and its action are
            # handed in, so a source the flows do not name goes to a person.
            decision = modes.decide(network, risk, now(), detection=d, action=action)
            if verdict["person"]:
                decision = {"auto": False, "words": verdict["why"]}
            if not decision["auto"]:
                row = propose(network, d, action, risk, why=decision["words"], now=now(),
                              classification=verdict["classification"], params=params,
                              classified=verdict["words"],
                              refused_call=verdict["refused_call"], incident=rec)
                out["proposed"].append(row["id"])
                out["incidents"].append({"key": inc["key"], "id": row["id"], "joined": False,
                                         "switches": 1 + len(rec["seen_also"])})
                line("respond", f"HITL, awaiting a person ({row['id']}): {decision['words']}")
                continue
            preview = closed_loop.respond_to_threat(network, d, action, params, driver=driver)
            if not preview["ok"]:
                # AUTO's own preview failed (C2159): nothing is sent, and the detection is a
                # person's, as if AUTO were off (`to_person`).
                to_person(d, inc, rec, verdict, f"AUTO could not preview {action}: "
                                                f"{preview.get('error') or 'no reason given'}")
                continue
            done = closed_loop.respond_to_threat(
                network, d, action, confirm={"ask": preview["ask"],
                                             "hash": preview["plan"]["hash"]},
                actor=AUTO_ACTOR, actor_verified="system", mode="auto",
                autonomous=decision["autonomous"],
                classified_by=closed_loop.classified_words(verdict["classification"], action),
                driver=driver, sleep=sleep, now=now)
            if done.get("outcome") == "refused":
                # AUTO's confirm refused before any request reached the controller (C2195):
                # what moved between its preview and its confirm (the policy or the connection
                # saved, the switch or its table changed, the switch held by another
                # operation), in the refusal's own words. ``refused`` is only ever before the
                # send: `respond_to_threat`'s own refusals return before `flow_ops.apply`, and
                # `apply` leaves ``refused`` at its first request, its outcome then verified,
                # rolled back or rollback failed, which stay the response's logged line below.
                # The detection is a person's, as if AUTO were off, as a failed preview is.
                to_person(d, inc, rec, verdict, f"AUTO could not confirm {action}: " + (
                    (done.get("error") or "no reason given").rstrip(".")))
                continue
            out["applied"].append({"id": done.get("id"), "outcome": done.get("outcome")})
            out["incidents"].append({"key": inc["key"], "id": done.get("id"), "joined": False,
                                     "switches": 1 + len(rec["seen_also"])})
            # The one writer of a response's line (`closed_loop.log_response`): the switch, the
            # operation and the entries as Verify read them back, as a person's confirm logs.
            out["lines"].append(closed_loop.log_response(
                network, done, action=action, who=AUTO_ACTOR, ask=preview["ask"], now=now()))
        if len(todo) > 1:
            # The pass's total beside each call's own (one detection's line is its total).
            line("classify", f"classified {len(todo)} detections at once, each its own call "
                             f"(at most {CLASSIFY_WORKERS} at a time): {classify_s:.1f} s in "
                             "all", took_s=round(classify_s, 2), detections=len(todo))
        expired = flow_ops.expire_meters(network, driver=driver, now=now)
        if expired["removed"]:
            line("expire", f"removed expired meter(s) {expired['removed']}")
        out["ok"] = True
        # Every screen shows the new state (C1868, C2003): the Alerts tab when the alert
        # history moved, SDN › Responses when a response did. A pass that only logged leaves
        # its lines to the SDN reader's own announcement (every 30 s), so the region is not
        # redrawn every pass. A classify is a background AI call, sent or refused, and recorded
        # (C1843): `ai_calls`, so the top bar's AI chip and an open spend panel read again.
        keys = (["alerts"] if seen.get("changed") else []) + (
            ["sdn"] if out["fired"] or out["proposed"] or out["applied"] or out["inactive"]
            or out["released"] or expired["removed"] else []) + (["ai_calls"] if todo else [])
        if keys:
            out["announced"] = _announce(network, keys, job)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("sdn loop: a pass on %s failed (%s)", network, type(exc).__name__)
        out["error"] = f"{type(exc).__name__}: {exc}"
        try:
            line("error", f"the pass failed: {out['error']}")
        except OSError:
            pass
    return out


def _announce(network: str, keys: list, job: str) -> dict:
    """Announce *keys* as the loop's job: ``{"keys", "ok", "error"}``. A failed announcement
    is logged and said in the pass's answer, never raised: the pass's work stands, and the
    page catches up at the SDN reader's next announcement."""
    from modules import invalidation

    try:
        invalidation.announce(keys, f"job:{job}")
        return {"keys": keys, "ok": True, "error": ""}
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.warning("sdn loop: announcing %s on %s failed (%s)", keys, network,
                    type(exc).__name__)
        return {"keys": keys, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ───────────────────────────────────────────────────────────────────────────── the job

def status(network: str) -> dict:
    """Whether the loop runs on *network* in this process, since when, by whom, how often."""
    with _jobs_lock:
        job = _jobs.get(network)
        if job and job["thread"].is_alive():
            return {"running": True, **{k: job[k] for k in ("by", "since", "interval")}}
    got = _read(network, LOG_FILE)
    stops = [r for r in got["rows"] if r.get("step") == "stop"]
    return {"running": False, "stopped": stops[-1] if stops else None}


def schedule(network: str, interval: float, stop_event, one_pass, *, clock=time.monotonic,
             wall=time.time) -> None:
    """Run *one_pass* every *interval* seconds, start to start, until *stop_event* is set
    (C1972: "every 10 s" was a 10 s wait after a pass of 5 s or more). A pass that takes the
    interval or longer starts the next at once, and the log says so, naming how long it took
    against the interval."""
    while not stop_event.is_set():
        began = clock()
        one_pass()
        took = clock() - began
        if stop_event.is_set():
            return
        left = interval - took
        if left > 0:
            stop_event.wait(left)
            continue
        say(network, "cadence", f"the pass took {took:.1f} s, at or over the {interval:g} s "
                                "interval: the next starts at once", wall())


def start(network: str, *, actor: str, interval: float = DEFAULT_INTERVAL, driver=None) -> dict:
    """Start the loop on *network* as *actor*, every *interval* seconds. Refuses a second loop
    on the network, or an interval out of bounds."""
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or \
            not MIN_INTERVAL <= interval <= MAX_INTERVAL:
        raise ValueError(f"the loop's interval is from {MIN_INTERVAL:g} to {MAX_INTERVAL:g} s, "
                         f"not {interval!r}")
    with _jobs_lock:
        job = _jobs.get(network)
        if job and job["thread"].is_alive():
            raise ValueError(f"the loop on {network} is running, started by {job['by']} at "
                             f"{job['since']}")
        stop_event = threading.Event()
        started = time.time()
        job = {"by": actor, "since": _iso(started), "interval": interval,
               "stop": stop_event, "id": job_id(network, started)}

        def run():
            schedule(network, interval, stop_event,
                     lambda: run_pass(network, driver=driver, job=job["id"]))

        job["thread"] = threading.Thread(target=run, name=f"sdn-loop-{network}", daemon=True)
        _jobs[network] = job
    say(network, "start", f"started by {actor}, every {interval:g} s, as job {job['id']}")
    job["thread"].start()
    return status(network)


#: Who a stop recorded at the app's start names (C2000).
RESTART_ACTOR = "the app's restart"


def ran_until_now(rows: list) -> dict:
    """The log's last start when no stop follows it (the loop was running when its process
    ended), else None."""
    starts = [n for n, r in enumerate(rows) if r.get("step") == "start"]
    if not starts or any(r.get("step") == "stop" for r in rows[starts[-1]:]):
        return None
    return rows[starts[-1]]


def after_restart(networks=None, now: float = None) -> list:
    """At the app's start (C2000): each network whose loop was running when its process ended
    (a start with no stop after it) has the stop recorded, naming the restart, the last line's
    time and that it does not start again by itself: a loop that resumed unattended would make
    background AI calls and, in AUTO, act with no person present. ``[{network, last_at}]``."""
    from modules.nsot import listref

    out = []
    for network in (listref.names() if networks is None else networks):
        got = _read(network, LOG_FILE)
        if got["state"] != "ok" or not ran_until_now(got["rows"]):
            continue
        last = got["rows"][-1].get("at") or "?"
        say(network, "stop", f"stopped by {RESTART_ACTOR}: its last line was at {last} UTC; "
                             "the loop does not start again by itself: start it on SDN › "
                             "Responses", now, by=RESTART_ACTOR, last_at=last)
        out.append({"network": network, "last_at": last})
    return out


def stopped_by_restart(network: str) -> dict:
    """The stop the app's restart recorded on *network*, when it is the loop's latest event
    (no start since), else None."""
    got = _read(network, LOG_FILE)
    rows = [r for r in got["rows"] if r.get("step") in ("start", "stop")]
    if not rows or rows[-1].get("step") != "stop" or rows[-1].get("by") != RESTART_ACTOR:
        return None
    return rows[-1]


def stop(network: str, *, actor: str) -> dict:
    """Stop the loop on *network* after its current pass, recording who."""
    with _jobs_lock:
        job = _jobs.get(network)
        if not job or not job["thread"].is_alive():
            raise ValueError(f"no loop is running on {network} in this process")
        job["stop"].set()
    say(network, "stop", f"stopped by {actor}")
    return {"running": False, "stopped_by": actor}
