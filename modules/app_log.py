"""The app's own log, read on request: one reader for today's `/logs/server` and Settings ›
Installation › Diagnostics (board F4).

`logs/device_manager.log` holds app.py and every module's logger (the root logger's rotating
handler, 10 MB a file). Every line was masked as it was WRITTEN, by the redacting filter on
every handler (`modules/redact`, whose health the same tab draws); nothing here unmasks or
re-reads a secret. A read writes nothing.
"""

import os

#: How many lines a read may ask for, and the choices the Diagnostics tab offers.
MAX_LINES = 5000
CHOICES = (200, 500, 2000)
DEFAULT_LINES = 500


def path() -> str:
    from modules.config import BASE_DIR

    return os.path.join(BASE_DIR, "logs", "device_manager.log")


def lines_asked(raw, default: int = DEFAULT_LINES) -> int:
    """A request's line count, bounded to 1..MAX_LINES; anything not a number is *default*."""
    try:
        return min(max(int(raw), 1), MAX_LINES)
    except (TypeError, ValueError):
        return default


def tail(n: int = DEFAULT_LINES, contains: str = "") -> dict:
    """The last *n* lines, then those containing *contains* (case-insensitive) among them:
    ``{"state": "ok"|"absent"|"unreadable", "lines", "read", "error"}``, ``read`` being how
    many lines the tail held before the filter. Absent and unreadable are different states."""
    p = path()
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            got = fh.readlines()[-lines_asked(n):]
    except FileNotFoundError:
        return {"state": "absent", "lines": [], "read": 0, "error": ""}
    except OSError as exc:
        return {"state": "unreadable", "lines": [], "read": 0,
                "error": f"{type(exc).__name__}: {exc}"}
    needle = (contains or "").strip().lower()
    kept = [line.rstrip("\n") for line in got if not needle or needle in line.lower()]
    return {"state": "ok", "lines": kept, "read": len(got), "error": ""}
