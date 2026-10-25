"""The record of every AI call: an append-only records store, `ai_calls` (PHASE8_PLAN 13.2
item 6, AI_ANTHROPIC_PLAN 2.3; the operator, 2026-10-25: a records store with the per-store
file or database switch).

One row per call, sent or refused: its id, when, who asked, the feature, the prompt (name,
version, sha256), the model, the request as it left the host (masked), the response's text
(masked again), the structured output, the verdict (`ok` or the error's kind), the tokens
(cache reads and writes too), the cost, the latency and the provider's rate-limit headers.
Never the API key, and nothing unmasked. History draws each row; the caps sum its costs.
"""
import logging
import os
import threading
import time
import uuid

log = logging.getLogger(__name__)

_lock = threading.Lock()

#: The record's store on the records database (one file for the installation).
STORE = "ai_calls"


def _path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, "ai_calls.jsonl")


def new_id() -> str:
    return "ai-" + uuid.uuid4().hex[:16]


def record(entry: dict) -> dict:
    """Append one call's row (its `at` set when absent). Returns the row with `recorded`.
    Never raises: a call that could not be recorded is logged loudly, and the gateway
    refuses the next one (an unrecorded call cannot be counted against the caps)."""
    row = dict(entry)
    row.setdefault("at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    recorded = False
    try:
        from modules import records_migrate
        with _lock:
            records_migrate.store_append(STORE, _path(), row)
        recorded = True
    except Exception as exc:                  # noqa: BLE001
        log.error("ai_calls: COULD NOT RECORD the call %s (%s)", row.get("id"), exc)
    return dict(row, recorded=recorded)


def read() -> dict:
    """Every call, newest first: ``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``."""
    from modules import records_migrate

    got = records_migrate.store_rows(STORE, _path(), skip_unparsable=True)
    if got["state"] == "unreadable":
        log.error("ai_calls: unreadable (%s)", got["error"])
    return dict(got, rows=list(reversed(got["rows"])))


def spent_usd(day: str) -> dict:
    """``{"state", "usd", "calls", "error"}``: what the calls recorded on the UTC *day*
    (``YYYY-MM-DD``) cost. An unreadable record is said, never read as nothing spent."""
    got = read()
    if got["state"] == "unreadable":
        return {"state": "unreadable", "usd": None, "calls": 0, "error": got["error"]}
    rows = [r for r in got["rows"] if str(r.get("at", "")).startswith(day)]
    return {"state": got["state"], "usd": sum(float(r.get("cost_usd") or 0) for r in rows),
            "calls": len(rows), "error": ""}
