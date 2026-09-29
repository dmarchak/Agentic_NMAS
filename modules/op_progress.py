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
"""

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


def update(op_id: str, **fields) -> None:
    with _lock:
        op = _ops.get(op_id)
        if op is not None:
            op.update(fields)
            op["moved_at"] = time.time()


def tick(op_id: str) -> None:
    """One request made (a session response hook calls this)."""
    with _lock:
        op = _ops.get(op_id)
        if op is not None:
            op["requests"] += 1
            op["moved_at"] = time.time()


def finish(op_id: str, outcome: str = "done") -> None:
    with _lock:
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
    return [{"device": op["label"], "operation": op["kind"], "words": op["kind"],
             "actor": op.get("actor", ""), "pid": None,
             "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(op["started_at"])),
             "held_for_s": round(now - op["started_at"]),
             "step": op.get("phase", ""), "step_words": step_words(op),
             "step_ago_s": round(now - op["moved_at"]),
             "stalled": now - op["moved_at"] > 60,
             "text": f"{op['label']}: {op['kind']}, {step_words(op)}"} for op in ops]
