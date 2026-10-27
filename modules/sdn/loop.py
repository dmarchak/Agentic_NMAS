"""The SDN closed loop as a job, one per network (PHASE8_PLAN 17.1 S10): detect, classify and
respond in the network's mode, each pass logged, stoppable. Deterministic but for the classify
step, which makes no AI call (below).

**A pass** (`run_pass`):
1. AUTO's expiry, if it passed, recorded once (`modes.record_expiry`);
2. `closed_loop.collect_threat_data(network)`, then `detect.observe` (each detection an alert
   with its evidence pack);
3. for each detection that fired in this pass: **classify** (`closed_loop.classify_threat`,
   called with a background trigger: it refuses, C1843, and makes no call), then the
   catalogue's default action for the rule (`closed_loop.DEFAULT_ACTION`), marked as chosen in
   code;
4. **respond in the mode** (`modes.decide`): in AUTO, an action within the allowed risk is
   previewed and applied through the flow-operation core as Mercury, recorded as autonomous
   with the setting and its reason; otherwise (HITL, the default) the response is kept as
   awaiting a person (`pending`), whose preview is built fresh when a person opens it;
5. a response's meter whose flows have expired is removed (`flow_ops.expire_meters`).

**The log** (``sdn_loop.jsonl`` in the network's folder): one line per step of each pass, with
its time, what it read and decided; `log_lines` reads the newest. **The job** runs in a thread
of the process that started it (`start`), sleeping the interval between passes; `stop` ends it
after its current pass, recording who and when. One loop per network: a second start is
refused, naming who started the first.

**Pending responses** (``sdn_responses.jsonl``): ``proposed`` (the detection, the action, its
risk, when), then one of ``confirmed`` (the operation that answered it), ``dismissed`` (by whom
and why) or ``cleared`` (the detection resolved before anyone acted).
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
            now: float = None) -> dict:
    """Keep a response awaiting a person. One per detection key: a second for a key already
    awaiting is not added."""
    now = time.time() if now is None else now
    for row in awaiting(network)["rows"]:
        if row.get("detection", {}).get("key") == detection.get("key"):
            return row
    row = {"kind": "proposed", "id": f"resp-{secrets.token_hex(5)}", "at": _iso(now),
           "action": action, "risk": risk, "why": why, "detection": detection}
    _append(network, PENDING_FILE, row)
    return row


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
    """The responses awaiting a person, oldest first."""
    got = _read(network, PENDING_FILE)
    open_rows = {}
    for r in got["rows"]:
        if r.get("kind") == "proposed":
            open_rows[r["id"]] = r
        else:
            open_rows.pop(r.get("id"), None)
    return dict(got, rows=list(open_rows.values()))


# ───────────────────────────────────────────────────────────────────────────── one pass

def run_pass(network: str, *, interval: float = SAMPLE_INTERVAL, driver=None, now=time.time,
             sleep=time.sleep, collect=None, observe=None) -> dict:
    """One pass of the loop (the module's docstring). ``{"ok", "error", "fired", "proposed",
    "applied", "cleared", "lines"}``."""
    from modules.sdn import closed_loop, detect, flow_ops, modes

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
            verdict = closed_loop.classify_threat(d, trigger="background")
            action = closed_loop.DEFAULT_ACTION[d["rule"]]
            risk = closed_loop.CATALOGUE[action]["risk"]
            line("classify", f"{verdict['error']}; proposed {action} (risk {risk})")
            decision = modes.decide(network, risk, now())
            if not decision["auto"]:
                row = propose(network, d, action, risk, why=decision["words"], now=now())
                out["proposed"].append(row["id"])
                line("respond", f"HITL, awaiting a person ({row['id']}): {decision['words']}")
                continue
            preview = closed_loop.respond_to_threat(network, d, action, driver=driver)
            if not preview["ok"]:
                line("respond", f"AUTO could not preview {action}: {preview['error']}")
                continue
            done = closed_loop.respond_to_threat(
                network, d, action, confirm={"ask": preview["ask"],
                                             "hash": preview["plan"]["hash"]},
                actor="Mercury (AUTO)", actor_verified="system", mode="auto",
                autonomous=decision["autonomous"], driver=driver, sleep=sleep, now=now)
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
        job = {"by": actor, "since": _iso(time.time()), "interval": interval,
               "stop": stop_event}

        def run():
            while not stop_event.is_set():
                run_pass(network, driver=driver)
                stop_event.wait(interval)

        job["thread"] = threading.Thread(target=run, name=f"sdn-loop-{network}", daemon=True)
        _jobs[network] = job
    say(network, "start", f"started by {actor}, every {interval:g} s")
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
