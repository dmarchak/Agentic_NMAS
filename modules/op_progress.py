"""Progress of an operation that holds no device: what it is doing NOW.

The operator, 2026-09-28: a NetBox import preview took 54 s (measured: 303
requests to NetBox, 176 ms mean, for nine devices) behind a bare spinner, "a
preview that takes 20 seconds with no feedback is the standing rule unmet,
even if the 20 seconds is unavoidable". C99's in-flight panel says what runs
on a DEVICE, from `device_ops`; a NetBox import holds no device, so it was
invisible there too.

The page gives each request an id; the operation records its phase, the
requests it has made (counted at the session, so every request counts), and
how many devices of how many it has done. The modal polls it by id and the
in-flight panel lists every one still running. In memory, like the one-shot
tokens: a restart loses it, and says so by answering "unknown".

**A run's own steps** (the operator, 2026-11-11: a Re-subscribe's entry "sat at 'starting'
for 8+ minutes with no detail. Every state shown must be the run's real current step"). A job
(`capture_job.start`, which runs its work `running_as` its id) hands this module the list it
records its steps in (`attach`: the SAME list its record keeps, never a copy, with the steps it
declares) and says when it wrote one (`moved`). The In progress list's words for the run are
then its newest step's (`run_stepper.current_words`), its card draws that list on THE stepper
(`run_stepper.from_record`), and every open page hears `device_progress`. One owner: the
run's own list. A run that attached nothing reads as before.
"""

import contextlib
import logging
import re
import threading
import time

log = logging.getLogger(__name__)

_ops: dict = {}
_lock = threading.Lock()

#: How long a finished operation is still answered, so a poll that arrives
#: just after the response still reads "done" rather than "unknown".
KEEP_FINISHED_S = 120
_MAX = 64
_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def valid_id(op_id) -> bool:
    return isinstance(op_id, str) and bool(_ID.match(op_id))


def _purge(now: float) -> None:
    for k in [k for k, v in _ops.items()
              if v.get("finished_at") and now - v["finished_at"] > KEEP_FINISHED_S]:
        del _ops[k]
    while len(_ops) > _MAX:
        _ops.pop(next(iter(_ops)))
    for k in [k for k in _runs if k not in _ops]:
        del _runs[k]


# ── A run's own steps ───────────────────────────────────────────────────────────────────────

#: op id -> ``{"declared": ((key, words), ...), "steps": <the run's own list>, "run": id}``.
_runs: dict = {}
_local = threading.local()
#: What a step written announces: the key every running card and the In progress list already
#: listen for (`invalidation.VOCABULARY`), by this announcer (`invalidation.ANNOUNCERS`).
STEP_KEYS = ("device_progress",)
STEP_ANNOUNCER = "run-progress"


@contextlib.contextmanager
def running_as(op_id: str):
    """Within the block this thread's work is operation *op_id*'s (`current`): the one job
    starter wraps every job's work in it, so an operation attaches its steps without being
    handed its job's id."""
    before = getattr(_local, "op", "")
    _local.op = op_id or ""
    try:
        yield
    finally:
        _local.op = before


def current() -> str:
    """The operation this thread's work belongs to, or ``""`` outside a job."""
    return getattr(_local, "op", "") or ""


def attach(declared, steps: list, *, run: str = "", op_id: str = None,
           labels: dict = None) -> bool:
    """This thread's job (or *op_id*) records its steps in *steps*, the list its own record
    keeps (``{"step", "result", "words", "at"}``, with ``began`` and ``wait_s`` on a step that
    said them), and declares them as *declared* (``(key, words)``, in order), with its short
    *labels* for them (``{key: two to four words}``) where it has them. *run* is its record's
    id where it has one. False, with nothing kept, outside a job."""
    op_id = current() if op_id is None else op_id
    with _lock:
        if op_id not in _ops:
            return False
        _runs[op_id] = {"declared": tuple((k, w) for k, w, *_ in declared), "steps": steps,
                        "run": run, "labels": dict(labels or {})}
    moved(op_id)
    return True


def moved(op_id: str = None) -> None:
    """The run wrote a step: its row's age starts again and every open page is told. A no-op
    outside a job, or for one that attached no steps."""
    op_id = current() if op_id is None else op_id
    with _lock:
        op = _ops.get(op_id)
        if op is None or op_id not in _runs:
            return
        op["moved_at"] = time.time()
    try:
        from modules import invalidation
        invalidation.announce(STEP_KEYS, by=STEP_ANNOUNCER, ok=True)
    except RuntimeError:
        pass                              # no emitter: a script, a test; nobody to tell
    except Exception as exc:              # noqa: BLE001 (the work goes on)
        log.warning("op_progress: %s's step was not announced: %s", op_id, exc)


def run_of(op_id: str):
    """*op_id*'s own steps as they stand now: ``{"declared", "steps", "run", "moved_at",
    "finished_at"}``, the steps a copy made at this instant; None for an operation that
    attached none, or that this server no longer holds."""
    with _lock:
        op, run = _ops.get(op_id), _runs.get(op_id)
        if op is None or run is None:
            return None
        return {"declared": run["declared"], "steps": [dict(s) for s in list(run["steps"])],
                "run": run["run"], "labels": dict(run["labels"]),
                "moved_at": op["moved_at"], "finished_at": op["finished_at"]}


def _run_words(op_id: str) -> str:
    """The run's newest step in words, or ``""`` for an operation with no steps of its own."""
    run = run_of(op_id)
    if run is None:
        return ""
    from modules import run_stepper
    return run_stepper.current_words(run["declared"], run["steps"], run["labels"])


def start(op_id: str, kind: str, label: str, actor: str = "", counts: str = "NetBox") -> bool:
    """Begin recording under *op_id*. Returns False (and records nothing)
    for an id that is not ours to use. *counts* names what `tick()` counts
    requests to; "" for an operation that counts none (a capture preview's
    device reads, C188), so its words never claim requests to NetBox."""
    if not valid_id(op_id):
        return False
    now = time.time()
    with _lock:
        _purge(now)
        _ops[op_id] = {"id": op_id, "kind": kind, "label": label, "actor": actor,
                       "started_at": now, "moved_at": now, "requests": 0,
                       "phase": "starting", "devices_done": 0, "devices_total": 0,
                       "current": "", "finished_at": None, "outcome": "",
                       "counts": counts}
    return True


#: op id -> a callable run when that operation's phase changes (`on_phase`).
_watchers: dict = {}


def on_phase(op_id: str, fn) -> None:
    """Call *fn()* each time *op_id*'s phase changes, outside the lock: a card that draws the
    phase as a step (THE stepper, the NetBox job's) announces then, so it redraws as the phase
    moves and never on a timer. Dropped when the operation finishes."""
    with _lock:
        _watchers[op_id] = fn


def update(op_id: str, **fields) -> None:
    fn = None
    with _lock:
        op = _ops.get(op_id)
        if op is not None:
            if "phase" in fields and fields["phase"] != op.get("phase"):
                fn = _watchers.get(op_id)
            op.update(fields)
            op["moved_at"] = time.time()
    if fn is not None:
        try:
            fn()
        except Exception as exc:                      # noqa: BLE001 (the work goes on)
            log.warning("op_progress: %s's phase watcher failed: %s", op_id, exc)


def tick(op_id: str) -> None:
    """One request made (a session response hook calls this)."""
    with _lock:
        op = _ops.get(op_id)
        if op is not None:
            op["requests"] += 1
            op["moved_at"] = time.time()


def finish(op_id: str, outcome: str = "done") -> None:
    with _lock:
        _watchers.pop(op_id, None)
        op = _ops.get(op_id)
        if op is not None:
            op["finished_at"] = time.time()
            op["outcome"] = outcome


def step_words(op: dict) -> str:
    """What it is doing now, in words, with its counts."""
    parts = ([f"{op['requests']} request(s) to {op['counts']} so far"]
             if op.get("counts", "NetBox") else [])
    if op.get("devices_total"):
        parts.append(f"device {min(op['devices_done'] + 1, op['devices_total'])} of "
                     f"{op['devices_total']}" + (f" ({op['current']})" if op.get("current") else "")
                     if op["devices_done"] < op["devices_total"] else
                     f"all {op['devices_total']} device(s) done")
    if op.get("phase"):
        parts.append(op["phase"])
    return "; ".join(parts)


def get(op_id: str, now: float = None):
    """What the operation is doing, or None when this server has no record
    of it (never started here, expired, or the server restarted)."""
    now = time.time() if now is None else now
    with _lock:
        _purge(now)
        op = _ops.get(op_id)
        op = dict(op) if op else None
    if op is None:
        return None
    op["elapsed_s"] = round((op["finished_at"] or now) - op["started_at"], 1)
    op["step_words"] = step_words(op)
    return op


def running(now: float = None) -> list:
    """Every operation still running, in the in-flight panel's row shape
    (`device_ops.in_flight`), so the one panel draws both."""
    now = time.time() if now is None else now
    with _lock:
        _purge(now)
        ops = [dict(v) for v in _ops.values() if not v.get("finished_at")]
    rows = []
    for op in ops:
        # A run that records its own steps reads as its newest one, never as the phase it
        # was given when it was registered ("starting", which no job moves).
        mine = _run_words(op["id"])
        words = mine or step_words(op)
        rows.append({"id": op["id"], "device": op["label"], "operation": op["kind"],
                     "words": op["kind"], "actor": op.get("actor", ""), "pid": None,
                     "started": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                              time.gmtime(op["started_at"])),
                     "held_for_s": round(now - op["started_at"]),
                     "step": op.get("phase", ""), "step_words": words, "own_steps": bool(mine),
                     "moved_at": op["moved_at"],
                     "step_ago_s": round(now - op["moved_at"]),
                     "stalled": now - op["moved_at"] > 60,
                     "text": f"{op['label']}: {op['kind']}, {words}"})
    return rows
