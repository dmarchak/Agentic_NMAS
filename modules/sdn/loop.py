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

**Link down is a fact, never classified** (Lab 9 B3, board F; `modules/sdn/link_failure.py`).
The pass's collection reads link status (each switch's port descriptions and each connection's
links), so `detect.observe` runs the link-down rule; a link-down detection is never classified
(no AI call) and never answered by the catalogue: `link_failure.step` opens its card in the
network's mode (`modes.decide`, the read's risk the least) and, in AUTO, verifies the forwarding
app's reroute from the trace at each pass until it is final; the card closes when the link is
listed and up again. **What each switch can do** (`capable`, the capability matrix read at the
loop's start, `modules/sdn/capability.py`): a rate limit on a switch whose meters are none is a
drop of the source instead, said on its line, where the policy allows a drop. **The loop stops
by itself** (`start`'s *run_for*, `RUN_FOR_CHOICES`, and `max_passes`): its log's stop line names
the bound that ended it and the passes run.

**High packet rate is watched, never answered** (board S-HR, C2238; PHASE8_PLAN 17.8). A rate
alone names no threat (`detect.WATCH_ONLY`): its detection is never classified (no AI call)
and never proposed. It is kept as one ``watching`` row per incident (`watch`, grouped by
source as scan and flood are, within the flood's window), action ``none``, no Approve, and
the system closes it (C1968's one exception, said on the row): ``joined`` when the flood rule
fires for the same switch and port or the same source (the flood's response then carries
"began as High packet rate at <time>", `began`), or ``ended`` when none of its switches shows
it any longer, "ended, never more than a rate". A new one on traffic a flood already answers
is said and not watched apart (`_watch_pass`).

A detection that resolves (`detect.observe`: a collection that judged its subject no longer
shows it) never closes its response: the response stays awaiting a person, marked "threat no
longer active since <time>", its classification kept, until a person approves or dismisses
it (C1968).

**The log** (``sdn_loop.jsonl`` in the network's folder): one line per step of each pass, with
its time, what it read and decided; `log_lines` reads the newest. A pass with no new detection
says which it is: "network healthy: no threat detected" only when the collection read every
switch whole and no detection is active; "no new threat; N still active: …" naming them; or
that the collection was partial, or read no switch, never called healthy. **A classified detection's timing line** (``timing``,
C1970: the walk's classify landed about 60 s after its detection although its AI call took 4 to
6 s), after its response's line: where its time went, stage names and seconds only, and the
same as ``stages`` (`_timing_words`): the pass's ``detect`` (`detect.observe`, its own pack's
build and keep inside it, ``pack``), ``holds`` (from the judging to the holds judged:
the responses awaiting a person read, any marked no longer active, `_judge_holds`),
``incidents`` (`_incidents`), then its own: ``queued`` (waiting for one of `CLASSIFY_WORKERS`),
``classify`` (its call, start to answer; inside it `closed_loop.classify_pack`'s ``prepare``,
``gateway`` and ``check``, and the provider's ``count`` and ``send`` from the call's row in the
record of AI calls, so the gateway's rest, its gates, the caps' reservation and the record, is
said), ``waited`` (its answer to its line: the slower calls and the earlier detections'
responses), ``respond``, and ``total``, from the detection's judging to its response; and the
``read`` before it. **A response's line**
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
a response's, so `awaiting` passes over both. A watching row (High packet rate) is
``watching``, any number of ``seen``, then one of ``joined``, ``ended`` or ``dismissed``
(`watching` reads them); its id (``watch-…``) is never a response's either. A flood response
it joined carries ``began`` (``began_as`` on `awaiting`'s row).
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
#: The loop's stop condition besides Stop (Lab 9 B3; board F; the handout's ground rule: never
#: leave a monitoring loop running unattended): it runs for a bound a person chooses at its
#: start, 20 minutes by default, at least a minute and at most an hour (`RUN_FOR_CHOICES` are
#: the ones SDN › Responses offers; the five-minute demonstration runs inside the default),
#: and at most `max_passes` passes, the bound's passes at the interval and one more: whichever
#: comes first ends it, and its log says which (`STOP_REASONS`). Cost: a long run is started
#: again by a person every hour. Prevents: a loop (and its background AI calls, and AUTO's
#: actions) running on with no person present.
DEFAULT_RUN_FOR_S = 20 * 60
MIN_RUN_FOR_S = 60
MAX_RUN_FOR_S = 60 * 60
RUN_FOR_CHOICES = (5 * 60, 20 * 60, 60 * 60)
STOP_REASONS = ("run_for", "pass_cap", "stop")
#: Who a stop the loop's own bound recorded names.
BOUND_ACTOR = "the loop's own bound"

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
    marks its response inactive (`mark`), never closes it (C1968). A watching row (High packet
    rate, `watch`) a person may dismiss, never confirm: nothing is proposed on it."""
    if how not in ("confirmed", "dismissed"):
        raise ValueError(f"a response is confirmed or dismissed by a person, not {how!r}")
    if how == "dismissed" and not (why or "").strip():
        raise ValueError("a dismissal names its reason")
    watched_row = how == "dismissed" and any(
        r.get("id") == response_id for r in watching(network)["rows"])
    if not watched_row and not any(r.get("id") == response_id
                                   for r in awaiting(network)["rows"]):
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
        elif kind == "began":
            open_rows[rid] = dict(open_rows[rid], began_as={
                k: r.get(k) for k in ("watch", "since", "words")})
        elif kind in CLOSED:
            open_rows.pop(rid, None)
    return dict(got, rows=list(open_rows.values()))


# ─────────────────────────────────────────────── watched, never answered (board S-HR, C2238)

#: The kinds that close a watching row (PHASE8_PLAN 17.8): the system's own, ``joined`` (the
#: flood rule fired for the same traffic) and ``ended`` (it no longer fires), or a person's
#: ``dismissed`` or ``proposed_by_person`` (C2313: a rate limit proposed from a watched
#: large-packet stream, `propose_from_watch`).
WATCH_CLOSED = ("joined", "ended", "dismissed", "proposed_by_person")


def watch(network: str, detection: dict, incident: dict, *, now: float = None) -> dict:
    """Keep a High packet rate incident (`detect.WATCH_ONLY`) as watching: nothing proposed,
    nothing asked of the classifier, its action ``none``. *incident* its key, source, window
    and the switches seen also, as `incidents.record` keeps a proposed one's."""
    now = time.time() if now is None else now
    row = {"kind": "watching", "id": f"watch-{secrets.token_hex(5)}", "at": _iso(now),
           "action": "none", "detection": detection, "incident": incident}
    _append(network, PENDING_FILE, row)
    return row


def watched(network: str, watch_id: str, how: str, *, why: str, incident: str = "",
            now: float = None) -> dict:
    """Close the watching row *watch_id* by the system (C1968's one exception, said on the
    row): ``joined`` (the flood incident *incident* answers the same traffic) or ``ended``;
    *why* its words."""
    if how not in ("joined", "ended"):
        raise ValueError(f"the system closes a watching row joined or ended, not {how!r}")
    now = time.time() if now is None else now
    row = {"kind": how, "id": watch_id, "at": _iso(now), "why": why, "incident": incident}
    _append(network, PENDING_FILE, row)
    return row


class ProposalRefused(ValueError):
    """A person's proposal from a watching row refused, in words naming why."""


def propose_from_watch(network: str, watch_id: str, *, actor: str, actor_verified: str,
                       actor_kind: str, now: float = None, stored: dict = None) -> dict:
    """A person's "Rate-limit this source…" on a watched large-packet stream (C2313's
    condition, the operator's decision of 2026-11-03, option (i)): the watching row *watch_id*
    made a response awaiting a person, and the row closed ``proposed_by_person``. Its action
    `closed_loop.PERSON_ACTION`, its parameters the catalogue's defaults, its detection the
    watched one with its evidence, its incident the watching row's (its switches seen also),
    proposed at the switch the source enters by where the controller's topology tells it
    (`incidents.ingress`; *stored* its stored read, read when None). Nothing is sent and no AI
    is asked: the response then goes through the normal preview, confirm by hash, apply,
    Verify and record. Refused (`ProposalRefused`, naming why) unless *actor* is a verified
    person (*actor_verified* neither empty nor ``none``, *actor_kind* ``person``: a verified
    service is not one, whatever the gate's settings), the row is open, and
    `closed_loop.person_proposal_refusal` passes: a large-packet stream, a source to act on,
    and the network's response policy allowing the rate limit for the flood rule, the rule a
    large-packet stream is checked as (the flood rule's held candidate). ``{"response",
    "closed"}``, the rows appended."""
    from modules import identity
    from modules.sdn import closed_loop, incidents

    if (not actor or actor == identity.UNVERIFIED or actor_verified in ("", "none")
            or actor_kind != "person"):
        raise ProposalRefused(f"a rate limit is proposed from a watching row by a verified "
                              f"person, and this request's is {actor or 'nobody'} "
                              f"(verified: {actor_verified or 'none'}, a "
                              f"{actor_kind or 'caller of no kind'}): nothing was proposed")
    row = next((r for r in watching(network)["rows"] if r.get("id") == watch_id), None)
    if row is None:
        raise ProposalRefused(f"no watching row {watch_id} is open on {network}: nothing was "
                              "proposed")
    d = row.get("detection") or {}
    refusal = closed_loop.person_proposal_refusal(network, d)
    if refusal:
        raise ProposalRefused(f"{refusal}: nothing was proposed")
    inc = dict(row.get("incident") or {})
    src = inc.get("source") or d.get("source") or ""
    chosen = incidents.ingress(network, {"members": [d], "source": src}, stored)
    rec = dict(inc, ingress_known=bool(chosen["known"]), ingress_words=chosen["words"],
               ingress_port=chosen["port"], seen_also=list(row.get("seen_also") or []))
    action = closed_loop.PERSON_ACTION
    now = time.time() if now is None else now
    response = propose(
        network, d, action, closed_loop.CATALOGUE[action]["risk"], now=now,
        why=f"proposed by {actor} from a watched large-packet stream",
        params=dict(closed_loop.RATE_LIMIT_DEFAULT),
        classified=(f"no AI classification: {actor} proposed the rate limit from watching row "
                    f"{watch_id}, checked as the flood rule's under the network's response "
                    "policy"), incident=rec)
    closed = {"kind": "proposed_by_person", "id": watch_id, "at": _iso(now), "actor": actor,
              "actor_verified": actor_verified, "why": "proposed by a person",
              "response": response["id"]}
    _append(network, PENDING_FILE, closed)
    log.info("sdn: %s proposed %s on %s from watching row %s as %s", actor, action, network,
             watch_id, response["id"])
    return {"response": response, "closed": closed}


def began(network: str, response_id: str, row: dict, *, now: float = None) -> dict:
    """Mark the flood response *response_id* as begun as the watching row *row*: its card
    says "began as High packet rate at <time>"."""
    now = time.time() if now is None else now
    out = {"kind": "began", "id": response_id, "at": _iso(now), "watch": row["id"],
           "since": row.get("at"), "words": f"began as High packet rate at {row.get('at')}"}
    _append(network, PENDING_FILE, out)
    return out


def watching(network: str) -> dict:
    """The watching rows still open, oldest first, each with ``seen_also``, ``members`` and
    ``last_seen`` as `awaiting` gives a response's."""
    got = _read(network, PENDING_FILE)
    open_rows = {}
    for r in got["rows"]:
        kind, rid = r.get("kind"), r.get("id")
        if kind == "watching":
            d = r.get("detection") or {}
            also = list((r.get("incident") or {}).get("seen_also") or [])
            open_rows[rid] = dict(r, seen_also=also,
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
        elif kind in WATCH_CLOSED:
            open_rows.pop(rid, None)
    return dict(got, rows=list(open_rows.values()))


def same_traffic(a: dict, b: dict) -> bool:
    """Whether detections *a* and *b* name the same traffic: the same connection, switch and
    port, or the same source in one spelling (`canon_source`)."""
    if a.get("port") is not None and (a.get("connection"), a.get("dpid"), a.get("port")) == (
            b.get("connection"), b.get("dpid"), b.get("port")):
        return True
    src = canon_source(a.get("source"))
    return bool(src) and src == canon_source(b.get("source"))


def _watch_pass(network: str, seen: dict, fired: list, floods: list, now: float,
                line) -> dict:
    """High packet rate in one pass (board S-HR, C2238; PHASE8_PLAN 17.8): never classified,
    never proposed. *fired* this pass's new `detect.WATCH_ONLY` detections; *floods*
    ``[(detection, id)]``, each flood detection active in this pass with the response that
    answers it (awaiting a person, applied, or holding its source off). Each open watching row
    joins the flood naming the same traffic (`same_traffic`: closed ``joined``, the flood's
    response marked as begun as it, `began`), or ends once none of its switches shows it;
    then each new incident joins a flood already answering its traffic (said, no row), joins an
    open watching row of its source within its window (seen also), or opens a watching row.
    ``{"watching", "joined", "ended", "seen_also"}``, ids and keys."""
    from modules.sdn import incidents

    res = {"watching": [], "joined": [], "ended": [], "seen_also": []}
    active = {d["key"] for d in seen.get("detections") or []} | {
        u.get("key") for u in seen.get("unjudged") or []}

    def members_of(row):
        src = (row.get("incident") or {}).get("source") or ""
        return [row.get("detection") or {}] + [dict(s, source=src)
                                               for s in row.get("seen_also") or []]

    def flood_of(members):
        return next(((f, fid) for f, fid in floods
                     if any(same_traffic(m, f) for m in members)), None)

    open_rows = []
    for row in watching(network)["rows"]:
        hit = flood_of(members_of(row))
        if hit is not None:
            f, fid = hit
            watched(network, row["id"], "joined", incident=fid, now=now,
                    why=f"joined flood incident {fid}")
            began(network, fid, row, now=now)
            res["joined"].append(row["id"])
            line("watch", f"High packet rate {row['id']} (since {row.get('at')}) joined flood "
                          f"incident {fid}: {f.get('words')}", watch=row["id"], incident=fid)
        elif not set(row["members"]) & active:
            watched(network, row["id"], "ended", now=now, why="ended, never more than a rate")
            res["ended"].append(row["id"])
            line("watch", f"High packet rate {row['id']} (since {row.get('at')}) ended, never "
                          "more than a rate: none of its switches shows it now",
                 watch=row["id"])
        else:
            open_rows.append(row)
    new = [d for d in fired if not any(d["key"] in r["members"] for r in open_rows)]
    for inc in incidents.group(new, seen.get("thresholds") or {}):
        hit = flood_of(inc["members"])
        if hit is not None:
            line("watch", f"{_switches_words(inc['members'])}: a high packet rate on traffic "
                          f"flood incident {hit[1]} already answers: not watched apart",
                 incident=hit[1])
            continue
        joined = next((r for r in (incidents.joinable(open_rows, m, now)
                                   for m in inc["members"]) if r is not None), None)
        if joined is not None:
            seen_also(network, joined["id"], inc["members"], now=now)
            res["seen_also"] += [m["key"] for m in inc["members"]]
            line("watch", f"High packet rate seen also on {_switches_words(inc['members'])}: "
                          f"joins watching row {joined['id']}", watch=joined["id"])
            continue
        d = incidents.first_seen(inc["members"])
        w = inc["window"]
        rec = {"key": inc["key"], "rule": inc["rule"], "source": inc.get("source") or "",
               "window_s": w["seconds"], "window_setting": w["setting"],
               "window_words": w["words"],
               "seen_also": [incidents.brief(m) for m in inc["members"]
                             if m.get("key") != d.get("key")]}
        row = watch(network, d, rec, now=now)
        open_rows.append(dict(row, seen_also=rec["seen_also"], last_seen=row["at"],
                              members=[d["key"]] + [s["key"] for s in rec["seen_also"]]))
        res["watching"].append(row["id"])
        line("watch", f"{d.get('words')}: watched as High packet rate ({row['id']}), not "
                      "called a scan or a flood: nothing proposed, no AI call; it joins the "
                      "flood rule's incident if that fires for this traffic, and ends when it "
                      "no longer fires", watch=row["id"])
    return res


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
    # One attack on one target (C2279, PHASE8_PLAN 17.10): the pass's new flood incidents that
    # send to one address are one attack, classified once, on its first incident.
    new = [inc for inc in dict((id(i), i) for i in incident_of.values()).values()
           if inc["joined"] is None]
    for att in attacks(new):
        lead = att["lead"]
        for inc in att["members"]:
            rec = dict(inc["record"], attack=att["record"])
            inc.update(record=rec, attack=att["record"])
            if inc is not lead:
                todo = [d for d in todo if d["key"] != inc["chosen"]["detection"]["key"]]
    return incident_of, todo


def attacks(new: list) -> list:
    """The attacks among a pass's new incidents (C2279, PHASE8_PLAN 17.10): flood incidents
    whose detections send to one address (`detect._destinations`: the flows' destinations, and
    the topology's for MAC-only flows, C2237), that address none of their own sources or
    replying hosts, two or more of them. Each ``{"target", "lead", "members", "record"}``:
    *lead* the first incident in the pass's order, classified for all; *record* what each
    member's response keeps (the target, the lead's key, the members' keys and sources). An
    incident is a member of one attack at most, the first that takes it."""
    from modules.sdn import detect

    by_target, taken, out = {}, set(), []
    for inc in new:
        if inc.get("rule") != "flood":
            continue
        own = set()
        dests = set()
        for m in inc["members"]:
            own |= {canon_source(s) for s in [m.get("source")] + list(m.get("sources") or [])
                    + list(m.get("replying_hosts") or []) if s}
            dests |= detect._destinations(m)
        for t in sorted(dests - own):
            by_target.setdefault(t, []).append(inc)
    for target, incs in by_target.items():
        members = [i for i in incs if id(i) not in taken]
        if len(members) < 2:
            continue
        taken |= {id(i) for i in members}
        sources = sorted({canon_source(i["chosen"]["detection"].get("source"))
                          for i in members if i["chosen"]["detection"].get("source")})
        out.append({"target": target, "lead": members[0], "members": members,
                    "record": {"key": f"attack|{target}", "target": target,
                               "lead": members[0]["key"],
                               "lead_detection": members[0]["chosen"]["detection"]["key"],
                               "incidents": [i["key"] for i in members],
                               "sources": sources}})
    return out


def member_verdict(lead: dict, d: dict, attack: dict) -> dict:
    """An attack's member's verdict (C2279): the lead's classification and action for *d*,
    its parameters the lead's but for the source, *d*'s own; always a person's to confirm,
    since the parameters were checked against the lead's evidence, not *d*'s."""
    params = {k: v for k, v in (lead.get("params") or {}).items() if k != "source"}
    if d.get("source"):
        params["source"] = d["source"]
    words = (f"classified with the attack on {attack['target']} (its first incident's: "
             f"{lead.get('words')}); no call of its own")
    return dict(lead, params=params, person=True, refused_call=lead.get("refused_call") or "",
                why=("one attack, classified once on its first incident: a person confirms "
                     "each source's response"), words=words)


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


def classify(network: str, d: dict, job: str, *, send=None, pack: dict = None,
             clock=time.monotonic) -> dict:
    """The pass's classify step for detection *d*: one background call through the gateway
    (`closed_loop.classify_pack` on *pack*, the pack `detect.observe` kept in this pass, else
    `closed_loop.classify_threat`, which finds it), and what it proposes (`verdict_of`). The
    pass runs one per detection at once (`run_pass`, `CLASSIFY_WORKERS`): nothing here is
    shared between two detections' calls but the gateway's own stores, each locked across
    threads and processes (the record of AI calls, the caps' reservations, the presses).
    The verdict carries the step's *took* (`classify_pack`'s, by *clock*) and the call's id
    (*call_id*, "" when none was recorded), for the pass's timing line (C1970)."""
    from modules.ai import triggers
    from modules.config import list_slug
    from modules.sdn import closed_loop

    trigger = triggers.background(closed_loop.CLASSIFY_FEATURE, job, list_slug(network),
                                  "detection", d.get("key") or "")
    if pack is not None:
        got = closed_loop.classify_pack(network, d, pack, actor=triggers.actor_of(trigger),
                                        trigger=trigger, send=send, clock=clock)
    else:
        got = closed_loop.classify_threat(network, d, actor=triggers.actor_of(trigger),
                                          trigger=trigger, send=send, clock=clock)
    return dict(verdict_of(network, d, got), took=dict(got.get("took") or {}),
                call_id=got.get("call_id") or "")


def _call_times(call_ids: list, since: float) -> dict:
    """``{call id: {"count", "send"}}``: the provider's own seconds on each of *call_ids*, its
    token count's (``prompt_count.latency_s``) and its send's (``latency_s``: every attempt and
    the waits between them, `anthropic_adapter.send`), from its row in the record of AI calls,
    read once within the window from *since* (epoch, the pass's calls' start; `calls.rows_since`,
    which parses only what was appended since its last read). A figure its row does not hold
    (no count asked, nothing sent) is absent, and so is a call whose row is not found; a record
    that cannot be read answers none, never raised (the timing line is a measurement, never a
    gate)."""
    import datetime

    wanted = {c for c in call_ids if c}
    if not wanted:
        return {}
    try:
        from modules.ai import calls
        got = calls.rows_since(datetime.datetime.fromtimestamp(since, datetime.timezone.utc))
    except Exception as exc:                          # noqa: BLE001 (a measurement, said)
        log.warning("sdn loop: the calls' times could not be read (%s)", type(exc).__name__)
        return {}
    out = {}
    for r in got.get("rows") or []:
        if r.get("id") not in wanted:
            continue
        times = {}
        count = (r.get("prompt_count") or {}).get("latency_s")
        if isinstance(count, (int, float)) and not isinstance(count, bool):
            times["count"] = float(count)
        send = r.get("latency_s")
        if isinstance(send, (int, float)) and not isinstance(send, bool):
            times["send"] = float(send)
        out[r["id"]] = times
    return out


def _classify_stages(verdict: dict, provider: dict) -> dict:
    """The classify step's own stages for the timing line: `classify_pack`'s *took*
    (``prepare``, ``gateway``, ``check``, those it reached) and, from the call's row
    (`_call_times`'s *provider*), the provider's ``count`` and ``send``."""
    took = verdict.get("took") or {}
    out = {k: float(took[k]) for k in ("prepare", "gateway", "check") if k in took}
    out.update((provider or {}).get(verdict.get("call_id") or "") or {})
    return out


def _timing_words(st: dict) -> str:
    """A classified detection's timing line (C1970): each stage's name and its seconds, in the
    order the pass ran them, then the total from its detection to its response and the read
    before it. The gateway's rest is its time less the provider's count and send: its gates,
    the caps' reservation and the record (never below 0: the row's times are within it)."""
    def s(v):
        return f"{v:.1f} s"

    inner = []
    if "prepare" in st:
        inner.append(f"prepare {s(st['prepare'])}")
    if "gateway" in st:
        provider = [f"{k} {s(st[k])}" for k in ("count", "send") if k in st]
        rest = max(0.0, st["gateway"] - st.get("count", 0.0) - st.get("send", 0.0))
        inner.append(f"gateway {s(st['gateway'])}"
                     + (": " + ", ".join(provider + [f"the rest {s(rest)}"]) if provider
                        else ""))
    if "check" in st:
        inner.append(f"check {s(st['check'])}")
    return (f"detect {s(st['detect'])}"
            + (f" (its pack {s(st['pack'])})" if "pack" in st else "")
            + f", holds {s(st['holds'])}, incidents {s(st['incidents'])}, queued "
            f"{s(st['queued'])}, classify {s(st['classify'])}"
            + (f" ({'; '.join(inner)})" if inner else "")
            + f", waited {s(st['waited'])}, respond {s(st['respond'])}: {s(st['total'])} from "
            f"detection to response (read before it {s(st['read'])})")


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
    if got.get("decided_in_code"):
        # C2305: benign traffic decided in code, no AI call: nothing is proposed for AUTO, and
        # the rule's default is drawn for a person, who may dismiss it.
        return dict(out, classification=c, person=True,
                    why="decided in code to be no threat, so a person decides", words=(
                        f"{got['decided_in_code']['words']}; {default} is drawn for a person "
                        "to decide, never AUTO's"))
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


#: A rate limit's parameters a drop does not take (`capable`).
_RATE_PARAMS = ("unit", "rate", "burst", "meter_id", "targets", "not_metered", "ports_from")


def capable(network: str, d: dict, verdict: dict, *, got: dict = None) -> dict:
    """*verdict* (`verdict_of`'s) as the switch of detection *d* can carry it (Lab 9 B3, the
    capability matrix, `modules/sdn/capability.py`): a rate limit on a switch whose meters
    are none is a drop instead, said in the verdict's words, where the network's response
    policy allows a drop for the rule; where it does not, the rate limit is kept for a person,
    saying why. Any other verdict, or a switch not in the matrix, is unchanged. *got* is the
    matrix (`capability.stored`'s; read when None)."""
    from modules.sdn import capability, closed_loop

    row = capability.row_for(network, d.get("connection") or "", d.get("dpid"), got=got)
    fb = capability.fallback(verdict.get("action") or "", row)
    if not fb["fell_back"]:
        return verdict
    rule = closed_loop.answered_rule(d)
    refused = closed_loop.policy_refusal(network, rule, fb["action"])
    if refused:
        why = f"{fb['words']}, but {refused}: a person decides"
        return dict(verdict, person=True, why=why, capability_words=why,
                    words=f"{verdict.get('words')}; {fb['words']}, but {refused}")
    params = {k: v for k, v in (verdict.get("params") or {}).items() if k not in _RATE_PARAMS}
    return dict(verdict, action=fb["action"], params=params, fell_back=fb["words"],
                capability_words=fb["words"],
                risk=closed_loop.CATALOGUE[fb["action"]]["risk"],
                words=f"{verdict.get('words')}; {fb['words']}")


def run_pass(network: str, *, interval: float = SAMPLE_INTERVAL, driver=None, now=time.time,
             sleep=time.sleep, collect=None, observe=None, job: str = "", send=None,
             clock=time.monotonic) -> dict:
    """One pass of the loop (the module's docstring). ``{"ok", "error", "fired", "proposed",
    "applied", "inactive", "mitigated", "released", "lines"}``: *inactive* the responses still
    awaiting a person whose detection resolved in this pass (C1968: never closed by it);
    *mitigated* each detection recorded as already mitigated (C2005: ``{"key", "by", "until",
    "hold"}``); *released* each held detection answered as new because its response is no
    longer in force; *watching*, *joined* and *ended* the High packet rate rows opened, joined
    to a flood and ended in this pass (`_watch_pass`). *job* is the loop's id (`job_id`), what
    its background AI calls name;
    *send* replaces the AI provider (tests)."""
    from modules.fanout import Failed, read_each
    from modules.sdn import closed_loop, detect, flow_ops, incidents, link_failure, modes

    job = job or job_id(network)

    out = {"ok": False, "error": "", "fired": [], "proposed": [], "applied": [], "inactive": [],
           "mitigated": [], "released": [], "incidents": [], "seen_also": [], "watching": [],
           "joined": [], "ended": [], "lines": [],
           "links": {"opened": [], "verified": [], "restored": []}}

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

    def respond(d, inc, rec, verdict):
        """Detection *d*'s response in the network's mode (the module's docstring, step 4),
        on its classification *verdict*, for its new incident *inc* (*rec* its record)."""
        verdict = capable(network, d, verdict)
        if verdict.get("capability_words"):
            line("respond", verdict["capability_words"])
        action, risk, params = verdict["action"], verdict["risk"], verdict["params"]
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
            return
        preview = closed_loop.respond_to_threat(network, d, action, params, driver=driver)
        if not preview["ok"]:
            # AUTO's own preview failed (C2159): nothing is sent, and the detection is a
            # person's, as if AUTO were off (`to_person`).
            to_person(d, inc, rec, verdict, f"AUTO could not preview {action}: "
                                            f"{preview.get('error') or 'no reason given'}")
            return
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
            return
        out["applied"].append({"id": done.get("id"), "outcome": done.get("outcome")})
        out["incidents"].append({"key": inc["key"], "id": done.get("id"), "joined": False,
                                 "switches": 1 + len(rec["seen_also"])})
        # The one writer of a response's line (`closed_loop.log_response`): the switch, the
        # operation and the entries as Verify read them back, as a person's confirm logs.
        out["lines"].append(closed_loop.log_response(
            network, done, action=action, who=AUTO_ACTOR, ask=preview["ask"], now=now()))

    try:
        if modes.record_expiry(network, now())["recorded"]:
            line("mode", "AUTO reached its expiry: the mode is HITL again")
        reading = clock()
        # With link status (Lab 9 B3): each switch's port descriptions and each connection's
        # discovered links, which the link-down rule judges (`link_failure.rule`).
        collected = collect() if collect else closed_loop.collect_threat_data(
            network, interval, sleep=sleep, driver=driver, links=True)
        read_s = clock() - reading
        s = collected.get("summary") or {}
        line("read", f"read {s.get('switches', 0)} switch(es): {s.get('flows', 0)} flows, port "
                     f"rates over {interval:g} s ({collected.get('state')})")
        began = clock()
        detected_at = began                       # the timing line's start (C1970)
        seen = (observe(network, collected) if observe else
                detect.observe(network, collected, clock=clock))
        judged_s = clock() - began
        if not seen.get("ok"):
            line("detect", f"nothing judged: {seen.get('error')}")
            out["error"] = seen.get("error") or ""
            return out
        fired = [d for d in seen.get("detections") or [] if d["key"] in set(seen["fired"])]
        # High packet rate (board S-HR, C2238) is watched, never classified or proposed
        # (`_watch_pass`, after the responses): kept apart from here on.
        said, rated = fired, [d for d in fired if d.get("rule") in detect.WATCH_ONLY]
        # A link down (Lab 9 B3) is a fact, never classified or answered by the catalogue: its
        # card and its reroute's verify are `link_failure.step`'s, after the responses.
        linked = [d for d in fired if d.get("rule") in detect.LINK_RULES]
        fired = [d for d in fired if d.get("rule") not in detect.WATCH_ONLY
                 and d.get("rule") not in detect.LINK_RULES]
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
        # A flood candidate inside its hold is not health (C2238's sibling, F6 on 2026-10-29:
        # "network healthy" logged for 19 s while about 60 Mbit/s of flood ran, the rule's
        # 30 s hold under way): each is named with how long it has held.
        pending = [f"{p.get('port')} {p.get('words')}" for p in seen.get("pending") or []]
        quiet = (f"no new threat; {len(still)} still active: {'; '.join(still)}" if still else
                 f"no threat fired yet; {len(pending)} flood candidate(s) over threshold, "
                 f"held until the rule's window passes: {'; '.join(pending)}: not called "
                 "healthy" if pending else
                 "network healthy: no threat detected" if state == "ok" and switches else
                 f"no threat detected on the switches read, but the collection was {state} "
                 f"({collected.get('error') or 'no reason given'}): not called healthy"
                 if switches else
                 f"no switch was read ({state}"
                 + (f": {collected.get('error') or collected.get('words')}"
                    if collected.get("error") or collected.get("words") else "")
                 + "): nothing judged healthy")
        line("detect", ("; ".join(d["words"] for d in said) if said else quiet)
             + (f"; {len(resolved)} no longer active (the collection judged its subject and "
                "no longer shows it)" if resolved else "")
             + (f", {len(held)} of them with a response still awaiting a person" if held
                else "") + (f" (judged in {judged_s:.1f} s)" if said else ""),
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
        holds_s = clock() - began - judged_s
        grouping = clock()
        incident_of, todo = _incidents(network, seen, [
            d for d in fired + releasing if d["key"] not in waiting and d["key"] not in holding],
            rows_waiting, now())
        incidents_s = clock() - grouping
        # Classified at once, each its own call (C1970): one per incident, its ingress
        # detection's, in the detections' order whatever order the calls finish in
        # (`fanout.read_each`); one that raises is its own Failed.
        took, started, ended = {}, {}, {}

        def one(d):
            began = started[d["key"]] = clock()
            try:
                return classify(network, d, job, send=send, pack=kept.get(d["key"]),
                                clock=clock)
            finally:
                ended[d["key"]] = clock()
                took[d["key"]] = ended[d["key"]] - began

        began = clock()
        # The record's window for the calls' rows: from the second the calls began, as a
        # row's time is stamped to the second (`calls.record`).
        since_wall = float(int(time.time()))
        verdicts = dict(zip([d["key"] for d in todo], read_each(
            one, todo, name="sdn-classify", max_workers=CLASSIFY_WORKERS)))
        classify_s = clock() - began
        provider = _call_times([v.get("call_id") or "" for v in verdicts.values()
                                if isinstance(v, dict)], since_wall)
        # Each classified detection's own stages, in its timing line after its response
        # (`_timing_words`): the pass's shared ones, then its own.
        shared = {"read": read_s, "detect": judged_s, "holds": holds_s,
                  "incidents": incidents_s}
        pool_began = began
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
            att = inc.get("attack")
            if att and att["lead_detection"] != d["key"]:
                # A member of an attack (C2279): the lead's verdict, no call of its own.
                lead = verdicts[att["lead_detection"]]
                if isinstance(lead, Failed):
                    lead = verdict_of(network, d, {"ok": False, "error": "exception",
                                                   "detail": str(lead)})
                verdict = member_verdict(lead, d, att)
                line("classify", f"{verdict['words']} (risk {verdict['risk']})",
                     attack=att["key"])
                respond(d, inc, rec, verdict)
                continue
            verdict = verdicts[d["key"]]
            if isinstance(verdict, Failed):
                # The call raised (not one of the gateway's own refusals): this detection's
                # fail-safe alone, the others' outcomes untouched.
                verdict = verdict_of(network, d, {"ok": False, "error": "exception",
                                                  "detail": str(verdict)})
            risk = verdict["risk"]
            # The step's time beside its words (C1970): this detection's own call, from its
            # start to its answer; the AI call's own latency is its row in the record of AI
            # calls, so the rest of the step is this less that.
            mine = took[d["key"]]
            waited_s = clock() - ended[d["key"]]
            line("classify", f"{verdict['words']} (risk {risk}; the step took {mine:.1f} s)",
                 took_s=round(mine, 2))
            responding = clock()
            respond(d, inc, rec, verdict)
            # Where this detection's time went (C1970), its stages' names and seconds only.
            pack_s = (seen.get("took") or {}).get(d["key"])
            stages = dict(shared, **({"pack": float(pack_s)} if pack_s is not None else {}),
                          queued=started[d["key"]] - pool_began, classify=mine,
                          **_classify_stages(verdict, provider), waited=waited_s,
                          respond=clock() - responding)
            stages["total"] = clock() - detected_at
            line("timing", _timing_words(stages),
                 stages={k: round(v, 3) for k, v in stages.items()})
        # High packet rate (board S-HR, C2238; PHASE8_PLAN 17.8), after the responses so a
        # flood answered in this pass is the incident it joins: each flood active now with the
        # response that answers it (awaiting a person, applied, or holding its source off).
        answered = {i["key"]: i["id"] for i in out["incidents"]}
        floods = [(d, fid) for d in seen.get("detections") or [] if d.get("rule") == "flood"
                  for fid in [(waiting.get(d["key"]) or {}).get("id")
                              or (holding.get(d["key"]) or {}).get("id")
                              or answered.get((incident_of.get(d["key"]) or {}).get("key"))]
                  if fid]
        # A watched stream a person made a response from (C2313, `propose_from_watch`) is that
        # response's, awaiting a person: firing again, it is not watched again beside it, and
        # its response is active again as any response's is.
        for d in rated:
            again = waiting.get(d["key"])
            if again is not None and again.get("inactive_since"):
                mark(network, again["id"], "active", now=now())
        watched_now = _watch_pass(network, seen, [d for d in rated if d["key"] not in waiting],
                                  floods, now(), line)
        out["seen_also"] += watched_now.pop("seen_also")
        out.update(watched_now)
        # Link failure (Lab 9 B3, board F): a card per link down, in the network's mode; in
        # AUTO the reroute verified at each pass until it is final; restored when it resolves.
        out["links"] = link_failure.step(network, linked, resolved, now=now(), line=line)
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
            or out["released"] or out["watching"] or out["joined"] or out["ended"]
            or out["seen_also"] or expired["removed"] or any(out["links"].values())
            else []) + (
            ["ai_calls"] if todo else [])
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
    """Whether the loop runs on *network* in this process, since when, by whom, how often, and
    when it stops by itself (``until``, its ``run_for_s`` and ``max_passes``, the ``passes``
    run so far)."""
    with _jobs_lock:
        job = _jobs.get(network)
        if job and job["thread"].is_alive():
            return {"running": True, **{k: job.get(k) for k in (
                "by", "since", "interval", "until", "run_for_s", "max_passes")},
                    "passes": job.get("passes", {}).get("n", 0)}
    got = _read(network, LOG_FILE)
    stops = [r for r in got["rows"] if r.get("step") == "stop"]
    return {"running": False, "stopped": stops[-1] if stops else None}


def max_passes(run_for_s: float, interval: float) -> int:
    """The loop's pass cap for a run of *run_for_s* at *interval*: the passes its bound holds,
    start to start, and one more (a pass at the start and one at the end)."""
    return int(math.ceil(run_for_s / interval)) + 1


def schedule(network: str, interval: float, stop_event, one_pass, *, clock=time.monotonic,
             wall=time.time, until: float = None, passes_cap: int = None,
             counted: dict = None) -> str:
    """Run *one_pass* every *interval* seconds, start to start, until *stop_event* is set
    (C1972: "every 10 s" was a 10 s wait after a pass of 5 s or more), or the loop's bound
    ends it (Lab 9 B3): *until* the *clock* time it runs to, *passes_cap* the most passes it
    runs. A pass that takes the interval or longer starts the next at once, and the log says
    so, naming how long it took against the interval. Answers why it ended, one of
    `STOP_REASONS`; *counted* ``{"n"}`` counts the passes run."""
    counted = counted if counted is not None else {"n": 0}
    while not stop_event.is_set():
        if passes_cap is not None and counted["n"] >= passes_cap:
            return "pass_cap"
        if until is not None and clock() >= until:
            return "run_for"
        began = clock()
        one_pass()
        counted["n"] += 1
        took = clock() - began
        if stop_event.is_set():
            return "stop"
        left = interval - took
        if until is not None:
            left = min(left, until - clock())
        if left > 0:
            stop_event.wait(left)
            continue
        if until is not None and clock() >= until:
            continue
        say(network, "cadence", f"the pass took {took:.1f} s, at or over the {interval:g} s "
                                "interval: the next starts at once", wall())
    return "stop"


def _bound_words(reason: str, job: dict) -> str:
    minutes = f"{job['run_for_s'] / 60:g} minute{'s' if job['run_for_s'] != 60 else ''}"
    passes = job["passes"]["n"]
    if reason == "run_for":
        return (f"stopped by itself: it ran for its bound of {minutes} (until {job['until']} "
                f"UTC), {passes} pass{'es' if passes != 1 else ''}; start it again on SDN › "
                "Responses")
    return (f"stopped by itself: it reached its pass cap of {job['max_passes']} passes "
            f"(its {minutes} at every {job['interval']:g} s, and one more) before its bound; "
            "start it again on SDN › Responses")


def run_for_problem(run_for_s) -> str:
    """Why *run_for_s* is not a bound the loop takes, or "" (`MIN_RUN_FOR_S` to
    `MAX_RUN_FOR_S`)."""
    if isinstance(run_for_s, bool) or not isinstance(run_for_s, (int, float)) or \
            not MIN_RUN_FOR_S <= run_for_s <= MAX_RUN_FOR_S:
        return (f"the loop runs for {MIN_RUN_FOR_S // 60} to {MAX_RUN_FOR_S // 60} minutes "
                f"(a loop is never left running unattended), not {run_for_s!r} s")
    return ""


def start(network: str, *, actor: str, interval: float = DEFAULT_INTERVAL, driver=None,
          run_for: float = DEFAULT_RUN_FOR_S, clock=time.monotonic) -> dict:
    """Start the loop on *network* as *actor*, every *interval* seconds, for *run_for* seconds
    at most (and at most `max_passes` passes): it then stops by itself, recording why. Refuses
    a second loop on the network, an interval out of bounds, or a bound out of bounds."""
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or \
            not MIN_INTERVAL <= interval <= MAX_INTERVAL:
        raise ValueError(f"the loop's interval is from {MIN_INTERVAL:g} to {MAX_INTERVAL:g} s, "
                         f"not {interval!r}")
    problem = run_for_problem(run_for)
    if problem:
        raise ValueError(problem)
    with _jobs_lock:
        job = _jobs.get(network)
        if job and job["thread"].is_alive():
            raise ValueError(f"the loop on {network} is running, started by {job['by']} at "
                             f"{job['since']}")
        stop_event = threading.Event()
        started = time.time()
        job = {"by": actor, "since": _iso(started), "interval": interval,
               "stop": stop_event, "id": job_id(network, started), "run_for_s": run_for,
               "until": _iso(started + run_for), "max_passes": max_passes(run_for, interval),
               "passes": {"n": 0}}
        ends_at = clock() + run_for

        def run():
            # What each switch can do (the capability matrix, Lab 9 B3), read once at the
            # start, so a response's fallback is the switches' as they are now.
            from modules.sdn import capability

            caps = capability.read(network, driver=driver)
            n = sum(len(c["switches"]) for c in caps["controllers"])
            say(network, "capabilities", (
                f"read what {n} switch{'es' if n != 1 else ''} can do (the capability matrix)"
                if caps["ok"] else f"the capability matrix could not be read: {caps['error']}"))
            reason = schedule(network, interval, stop_event,
                              lambda: run_pass(network, driver=driver, job=job["id"]),
                              clock=clock, until=ends_at, passes_cap=job["max_passes"],
                              counted=job["passes"])
            if reason in ("run_for", "pass_cap"):
                say(network, "stop", _bound_words(reason, job), by=BOUND_ACTOR,
                    reason=reason, passes=job["passes"]["n"])

        job["thread"] = threading.Thread(target=run, name=f"sdn-loop-{network}", daemon=True)
        _jobs[network] = job
    say(network, "start", f"started by {actor}, every {interval:g} s, for at most "
                          f"{run_for / 60:g} minutes (until {job['until']} UTC) or "
                          f"{job['max_passes']} passes, as job {job['id']}",
        run_for_s=run_for, until=job["until"], max_passes=job["max_passes"])
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
