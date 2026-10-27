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
   (`background.admit`, `over_cap`; off by default): then the catalogue's default action for
   the rule is proposed (`closed_loop.DEFAULT_ACTION`), said as chosen in code. A
   classification that passes the code's check proposes its catalogue action and parameters
   instead; one proposing no catalogue action is kept for a person, never AUTO's;
4. **respond in the mode** (`modes.decide`): in AUTO, an action within the allowed risk is
   previewed and applied through the flow-operation core as Mercury, recorded as autonomous
   with the setting and its reason, and with who chose the action; otherwise (HITL, the
   default) the response is kept as awaiting a person (`pending`), with the classification
   when there is one, its preview built fresh when a person opens it;
5. a response's meter whose flows have expired is removed (`flow_ops.expire_meters`).

**The log** (``sdn_loop.jsonl`` in the network's folder): one line per step of each pass, with
its time, what it read and decided; `log_lines` reads the newest. **The job** runs in a thread
of the process that started it (`start`), sleeping the interval between passes; `stop` ends it
after its current pass, recording who and when. One loop per network: a second start is
refused, naming who started the first.

**Pending responses** (``sdn_responses.jsonl``): ``proposed`` (the detection, the action, its
risk, when, and the classification if the loop's call made one), then any number of
``classified`` (a person's Classify: the classification, and the action it proposes), then one
of ``confirmed`` (the operation that answered it), ``dismissed`` (by whom and why) or
``cleared`` (the detection resolved before anyone acted).
"""

import json
import logging
import os
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


# ───────────────────────────────────────────────────────────────────────────── pending

def propose(network: str, detection: dict, action: str, risk: str, *, why: str,
            now: float = None, classification: dict = None, params: dict = None,
            classified: str = "") -> dict:
    """Keep a response awaiting a person. One per detection key: a second for a key already
    awaiting is not added. *classification* the loop's AI classification, when one passed;
    *params* the action's checked parameters; *classified* why there is none, in words."""
    now = time.time() if now is None else now
    for row in awaiting(network)["rows"]:
        if row.get("detection", {}).get("key") == detection.get("key"):
            return row
    row = {"kind": "proposed", "id": f"resp-{secrets.token_hex(5)}", "at": _iso(now),
           "action": action, "risk": risk, "why": why, "detection": detection,
           "classification": classification, "params": dict(params or {}),
           "classified": classified}
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
    """Close an awaiting response: ``confirmed`` (with its operation's id), ``dismissed`` (a
    reason required) or ``cleared``."""
    if how not in ("confirmed", "dismissed", "cleared"):
        raise ValueError(f"a response is confirmed, dismissed or cleared, not {how!r}")
    if how == "dismissed" and not (why or "").strip():
        raise ValueError("a dismissal names its reason")
    if not any(r.get("id") == response_id for r in awaiting(network)["rows"]):
        raise ValueError(f"no response {response_id!r} is awaiting a person on {network}")
    now = time.time() if now is None else now
    row = {"kind": how, "id": response_id, "at": _iso(now), "actor": actor,
           "why": (why or "").strip(), "operation": operation}
    _append(network, PENDING_FILE, row)
    return row


def awaiting(network: str) -> dict:
    """The responses awaiting a person, oldest first, each with its latest classification."""
    got = _read(network, PENDING_FILE)
    open_rows = {}
    for r in got["rows"]:
        if r.get("kind") == "proposed":
            open_rows[r["id"]] = r
        elif r.get("kind") == "classified":
            if r.get("id") in open_rows:
                open_rows[r["id"]] = dict(open_rows[r["id"]], **{
                    k: r.get(k) for k in ("classification", "action", "risk", "params")},
                    classified_at=r.get("at"), classified_by=r.get("actor"))
        else:
            open_rows.pop(r.get("id"), None)
    return dict(got, rows=list(open_rows.values()))


# ───────────────────────────────────────────────────────────────────────────── one pass

def job_id(network: str, since: float = None) -> str:
    """The loop's job id on *network*, what its background AI calls name (``job:<id>``): the
    network's folder name, and the time the loop started when it is known."""
    from modules.config import list_slug

    stamp = time.strftime("-%Y%m%dT%H%M%SZ", time.gmtime(since)) if since else ""
    return f"sdn-loop-{list_slug(network)}{stamp}"


def classify(network: str, d: dict, job: str, *, send=None) -> dict:
    """The pass's classify step for detection *d*: one background call through the gateway
    (`closed_loop.classify_threat`), and what it proposes: ``{"action", "risk", "params",
    "classification", "words", "person"}``. *person* True when only a person may act on it
    (the AI proposed no catalogue action). The feature off, or any refusal: the catalogue's
    default for the rule, said as chosen in code, with why."""
    from modules.ai import triggers
    from modules.config import list_slug
    from modules.sdn import closed_loop

    trigger = triggers.background(closed_loop.CLASSIFY_FEATURE, job, list_slug(network),
                                  "detection", d.get("key") or "")
    got = closed_loop.classify_threat(network, d, actor=triggers.actor_of(trigger),
                                      trigger=trigger, send=send)
    default = closed_loop.DEFAULT_ACTION[d["rule"]]
    out = {"action": default, "risk": closed_loop.CATALOGUE[default]["risk"], "params": {},
           "classification": None, "person": False}
    if not got.get("ok"):
        return dict(out, words=(f"no AI classification ({got.get('error')}: "
                                f"{got.get('detail')}); proposed {default}, "
                                f"{closed_loop.DEFAULT_WORDS}"))
    c = got["classification"]
    if got["action"] == closed_loop.NO_ACTION:
        return dict(out, classification=c, person=True, words=(
            f"AI call {got['call_id']}: {'a ' + c['threat_type'] if c['threat_detected'] else 'no'}"
            f" threat, no catalogue action proposed; {default} is drawn for a person to decide, "
            "never AUTO's"))
    action = got["action"]
    return dict(out, action=action, risk=closed_loop.CATALOGUE[action]["risk"],
                params=got["params"], classification=c,
                words=(f"AI call {got['call_id']}: a {c['threat_type']} threat, severity "
                       f"{c['severity']}; proposed {action}, checked in code"))


def run_pass(network: str, *, interval: float = SAMPLE_INTERVAL, driver=None, now=time.time,
             sleep=time.sleep, collect=None, observe=None, job: str = "", send=None) -> dict:
    """One pass of the loop (the module's docstring). ``{"ok", "error", "fired", "proposed",
    "applied", "cleared", "lines"}``. *job* is the loop's id (`job_id`), what its background
    AI calls name; *send* replaces the AI provider (tests)."""
    from modules.sdn import closed_loop, detect, flow_ops, modes

    job = job or job_id(network)

    out = {"ok": False, "error": "", "fired": [], "proposed": [], "applied": [], "cleared": [],
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
        seen = (observe or detect.observe)(network, collected)
        if not seen.get("ok"):
            line("detect", f"nothing judged: {seen.get('error')}")
            out["error"] = seen.get("error") or ""
            return out
        fired = [d for d in seen.get("detections") or [] if d["key"] in set(seen["fired"])]
        line("detect", ("; ".join(d["words"] for d in fired) if fired else "nothing new")
             + (f"; {len(seen.get('resolved') or [])} resolved" if seen.get("resolved") else ""))
        for key in seen.get("resolved") or []:
            for row in awaiting(network)["rows"]:
                if row.get("detection", {}).get("key") == key:
                    resolve(network, row["id"], "cleared", actor="Mercury",
                            why="the detection resolved before anyone acted", now=now())
                    out["cleared"].append(row["id"])
        for d in fired:
            out["fired"].append(d["key"])
            verdict = classify(network, d, job, send=send)
            action, risk, params = verdict["action"], verdict["risk"], verdict["params"]
            line("classify", f"{verdict['words']} (risk {risk})")
            decision = modes.decide(network, risk, now())
            if verdict["person"]:
                decision = {"auto": False, "words": "the AI proposed no catalogue action, so a "
                                                    "person decides"}
            if not decision["auto"]:
                row = propose(network, d, action, risk, why=decision["words"], now=now(),
                              classification=verdict["classification"], params=params,
                              classified=verdict["words"])
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
                actor="Mercury (AUTO)", actor_verified="system", mode="auto",
                autonomous=decision["autonomous"],
                classified_by=closed_loop.classified_words(verdict["classification"], action),
                driver=driver, sleep=sleep, now=now)
            out["applied"].append({"id": done.get("id"), "outcome": done.get("outcome")})
            line("respond", f"AUTO applied {action}: {done.get('outcome')}"
                            + (f" ({done.get('error')})" if done.get("error") else ""),
                 operation=done.get("id"))
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
            while not stop_event.is_set():
                run_pass(network, driver=driver, job=job["id"])
                stop_event.wait(interval)

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
