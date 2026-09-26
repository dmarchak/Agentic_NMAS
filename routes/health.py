"""GET /health: which code this process is running, and since when.

A 200 from `/` proved only that SOMETHING answered. After a deploy, a process
that never restarted still answers 200, so `nmas-deploy` could report a deploy
the running service never loaded (the operator's finding, 2026-09-26). This
reports what the process LOADED, not what the checkout says now: the commit is
read once, when the process imports its code, with the process's pid.

**`started_at` is `time.time()` taken when this module loads**, early in the
process's start-up. It was psutil's `create_time()`, which on Linux is
`/proc/stat`'s boot time (WHOLE seconds, truncated) plus start ticks, so it
read up to a second EARLY, and measured 0.66 s before systemd's own start
timestamp: millisecond precision that was false. Identity is not decided from
it at all: `nmas-deploy` compares the PID with systemd's MainPID.

Not gated: a diagnostic that hides behind identity is useless when identity
breaks, and it echoes nothing secret (the repository is public).
"""

import datetime
import os
import subprocess
import time

from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _iso_ms(epoch: float) -> str:
    return (datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)
            .isoformat(timespec="milliseconds").replace("+00:00", "Z"))


def _commit_loaded() -> tuple:
    try:
        out = subprocess.run(["git", "-C", _ROOT, "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if out.returncode != 0:
        return None, out.stderr.strip() or f"git exited {out.returncode}"
    return out.stdout.strip(), ""


_COMMIT, _COMMIT_ERROR = _commit_loaded()
_STARTED = time.time()


@bp.route("/health", methods=["GET"])
def health():
    body = {"ok": _COMMIT is not None, "commit": _COMMIT,
            "started_at": _iso_ms(_STARTED), "pid": os.getpid()}
    if _COMMIT is None:
        body["error"] = f"the loaded commit is unknown: {_COMMIT_ERROR}"
    return jsonify(body)
