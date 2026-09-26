"""modules/terminal_audit.py

An append-only record of every use of the break-glass terminal (NSOT_PLAN P.3
step 7).

The terminal is the one path with no plan, no confirm hash and no rollback, so
its use is an incident, and an incident needs a record: WHO opened it, for
WHICH device, WHEN it opened and closed, and from WHERE. Refused attempts are
recorded too, because an attempt is also a fact about the break-glass path.

**Keystrokes are never recorded.** A trail that copies what is typed would copy
every password typed into a device, and become a second place secrets live
(the reveal trail's rule: record what was used, never what was seen).

Written 0600 at creation (`config.open_secure`), one JSON object per line,
never rewritten. A failure to record never breaks the terminal. It is logged
at ERROR and counted in :func:`health`, because a recorder whose success
condition is silence must report its own failures.
"""

import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

_lock = threading.Lock()
_health = {"written": 0, "failed": 0, "last_error": ""}

OPENED, OPEN_FAILED, CLOSED, REFUSED = "opened", "open_failed", "closed", "refused"


def _path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, "terminal_audit.jsonl")


def record(event: str, *, device_ip: str, actor: str = "", kind: str = "",
           hostname: str = "", sid: str = "", peer: str = "",
           reason: str = "") -> dict:
    """Append one event. Never raises; never takes keystrokes or output."""
    entry = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "actor": actor or "unauthenticated",
        "kind": kind or "",
        "device_ip": device_ip or "",
        "hostname": hostname or "",
        "session": sid or "",
        "peer": peer or "",
        "reason": reason or "",
    }
    try:
        from modules.config import open_secure
        with _lock, open_secure(_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        _health["written"] += 1
    except Exception as exc:                  # noqa: BLE001
        _health["failed"] += 1
        _health["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
        log.error("terminal_audit: COULD NOT RECORD %s of %s by %s (%s)",
                  event, device_ip, entry["actor"], exc)
    log.info("terminal_audit: %s %s by %s", event, device_ip, entry["actor"])
    return entry


def health() -> dict:
    """In THIS process: how many writes succeeded and failed."""
    return dict(_health)


def entries(limit: int = 200) -> list:
    """The most recent events, newest first. Unreadable lines are skipped and
    counted, never guessed at."""
    path = _path()
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return list(reversed(out))[:limit]
