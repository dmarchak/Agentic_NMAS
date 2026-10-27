"""The SDN closed loop as a job, one per network (PHASE8_PLAN 17.1 S10): detect, classify and
respond in the network's mode, each pass logged, stoppable. Deterministic but for the classify
step, the one AI call, which runs only where its feature is on (below).

**A pass** (`run_pass`):
1. AUTO's expiry, if it passed, recorded once (`modes.record_expiry`);
2. `closed_loop.collect_threat_data(network)`, then `detect.observe` (each detection an alert
   with its evidence pack);
3. for each detection that fired in this pass: **classify** (`closed_loop.classify_threat`)
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
   cannot be read proposes no action, said, for a person;
4. **respond in the mode** (`modes.decide`): in AUTO, an action of a classification that
   passed, within the allowed risk, is previewed and applied through the flow-operation core
   as Mercury, recorded as autonomous with the setting and its reason, and with who chose the
   action; otherwise (HITL, the default) the response is kept as awaiting a person
   (`pending`), with the classification when there is one, its preview built fresh when a
   person opens it. A detection that fires again while its response awaits a person is not
   classified again: the response is marked active again;
5. a response's meter whose flows have expired is removed (`flow_ops.expire_meters`).

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

**Pending responses** (``sdn_responses.jsonl``): ``proposed`` (the detection, the action, its
risk, when, and the classification if the loop's call made one, or the refused call), then
any number of ``classified`` (a person's Classify: the classification, and the action it
proposes), ``inactive`` (its detection resolved: since when) and ``active`` (it fired again),
then one of ``confirmed`` (the operation that answered it) or ``dismissed`` (by whom and why).
``cleared`` (the detection resolved before anyone acted) is no longer written, and still read
as closed in an older record.
"""

import calendar
import json
import logging
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
            classified: str = "", refused_call: str = "") -> dict:
    """Keep a response awaiting a person. One per detection key: a second for a key already
    awaiting is not added. *classification* the loop's AI classification, when one passed;
    *params* the action's checked parameters; *classified* why there is none, in words;
    *refused_call* the AI call whose answer the check refused, when one was."""
    now = time.time() if now is None else now
    for row in awaiting(network)["rows"]:
        if row.get("detection", {}).get("key") == detection.get("key"):
            return row
    row = {"kind": "proposed", "id": f"resp-{secrets.token_hex(5)}", "at": _iso(now),
           "action": action, "risk": risk, "why": why, "detection": detection,
           "classification": classification, "params": dict(params or {}),
           "classified": classified, "refused_call": refused_call}
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
    """The responses awaiting a person, oldest first, each with its latest classification and
    ``inactive_since`` (its detection's threat no longer active since then, "" while it is)."""
    got = _read(network, PENDING_FILE)
    open_rows = {}
    for r in got["rows"]:
        kind, rid = r.get("kind"), r.get("id")
        if kind == "proposed":
            open_rows[rid] = dict(r, inactive_since="")
        elif rid not in open_rows:
            continue
        elif kind == "classified":
            open_rows[rid] = dict(open_rows[rid], **{
                k: r.get(k) for k in ("classification", "action", "risk", "params")},
                classified_at=r.get("at"), classified_by=r.get("actor"))
        elif kind == "inactive":
            open_rows[rid] = dict(open_rows[rid], inactive_since=r.get("since") or r.get("at"))
        elif kind == "active":
            open_rows[rid] = dict(open_rows[rid], inactive_since="")
        elif kind in CLOSED:
            open_rows.pop(rid, None)
    return dict(got, rows=list(open_rows.values()))


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


def classify(network: str, d: dict, job: str, *, send=None, pack: dict = None) -> dict:
    """The pass's classify step for detection *d*: one background call through the gateway
    (`closed_loop.classify_pack` on *pack*, the pack `detect.observe` kept in this pass, else
    `closed_loop.classify_threat`, which finds it), and what it proposes: ``{"action", "risk",
    "params", "classification", "words", "person", "why", "refused_call"}``. *person* True when
    only a person may act on it, *why* saying so: the AI proposed no catalogue action, or no
    classification passed (C1968: refused by the check, failed or unavailable, the rule's
    catalogue default is proposed for a person, never AUTO's; *refused_call* the refused
    answer's AI call)."""
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
                       f"{c['severity']}; proposed {action}, checked in code"))


def run_pass(network: str, *, interval: float = SAMPLE_INTERVAL, driver=None, now=time.time,
             sleep=time.sleep, collect=None, observe=None, job: str = "", send=None,
             clock=time.monotonic) -> dict:
    """One pass of the loop (the module's docstring). ``{"ok", "error", "fired", "proposed",
    "applied", "inactive", "lines"}``: *inactive* the responses still awaiting a person whose
    detection resolved in this pass (C1968: never closed by it). *job* is the loop's id
    (`job_id`), what its background AI calls name; *send* replaces the AI provider (tests)."""
    from modules.sdn import closed_loop, detect, flow_ops, modes

    job = job or job_id(network)

    out = {"ok": False, "error": "", "fired": [], "proposed": [], "applied": [], "inactive": [],
           "lines": []}

    def line(step, words, **extra):
        out["lines"].append(say(network, step, words, now(), **extra))

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
        waiting = {r.get("detection", {}).get("key"): r for r in awaiting(network)["rows"]}
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
        for row in held:
            if not row.get("inactive_since"):
                mark(network, row["id"], "inactive", since=since, now=now())
                out["inactive"].append(row["id"])
        kept = seen.get("kept") or {}
        for d in fired:
            out["fired"].append(d["key"])
            again = waiting.get(d["key"])
            if again is not None:
                if again.get("inactive_since"):
                    mark(network, again["id"], "active", now=now())
                line("respond", f"fired again while its response {again['id']} awaits a "
                                "person: not classified again")
                continue
            began = clock()
            verdict = classify(network, d, job, send=send, pack=kept.get(d["key"]))
            took = clock() - began
            action, risk, params = verdict["action"], verdict["risk"], verdict["params"]
            # The step's time beside its words (C1970): the AI call's own latency is its row
            # in the record of AI calls, so the rest of the step is this less that.
            line("classify", f"{verdict['words']} (risk {risk}; the step took {took:.1f} s)",
                 took_s=round(took, 2))
            decision = modes.decide(network, risk, now())
            if verdict["person"]:
                decision = {"auto": False, "words": verdict["why"]}
            if not decision["auto"]:
                row = propose(network, d, action, risk, why=decision["words"], now=now(),
                              classification=verdict["classification"], params=params,
                              classified=verdict["words"],
                              refused_call=verdict["refused_call"])
                out["proposed"].append(row["id"])
                line("respond", f"HITL, awaiting a person ({row['id']}): {decision['words']}")
                continue
            preview = closed_loop.respond_to_threat(network, d, action, params, driver=driver)
            if not preview["ok"]:
                line("respond", f"AUTO could not preview {action}: {preview['error']}")
                continue
            done = closed_loop.respond_to_threat(
                network, d, action, confirm={"ask": preview["ask"],
                                             "hash": preview["plan"]["hash"]},
                actor=AUTO_ACTOR, actor_verified="system", mode="auto",
                autonomous=decision["autonomous"],
                classified_by=closed_loop.classified_words(verdict["classification"], action),
                driver=driver, sleep=sleep, now=now)
            out["applied"].append({"id": done.get("id"), "outcome": done.get("outcome")})
            # The one writer of a response's line (`closed_loop.log_response`): the switch, the
            # operation and the entries as Verify read them back, as a person's confirm logs.
            out["lines"].append(closed_loop.log_response(
                network, done, action=action, who=AUTO_ACTOR, ask=preview["ask"], now=now()))
        expired = flow_ops.expire_meters(network, driver=driver, now=now)
        if expired["removed"]:
            line("expire", f"removed expired meter(s) {expired['removed']}")
        out["ok"] = True
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("sdn loop: a pass on %s failed (%s)", network, type(exc).__name__)
        out["error"] = f"{type(exc).__name__}: {exc}"
        try:
            line("error", f"the pass failed: {out['error']}")
        except OSError:
            pass
    return out


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


def stop(network: str, *, actor: str) -> dict:
    """Stop the loop on *network* after its current pass, recording who."""
    with _jobs_lock:
        job = _jobs.get(network)
        if not job or not job["thread"].is_alive():
            raise ValueError(f"no loop is running on {network} in this process")
        job["stop"].set()
    say(network, "stop", f"stopped by {actor}")
    return {"running": False, "stopped_by": actor}
