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


def record_use(call_id: str, use: str, *, actor: str = "", detail: str = "",
               links: dict = None) -> dict:
    """Append what became of a call's answer, its own row keyed by the call's id (PHASE8_PLAN
    15.14: the use is recorded at the source, append-only, never an edit of the call's row):
    *use* is the feature's own word ("filled", "shown", "refused by validation"), *detail*
    why, *links* where what it produced is (a page and its anchor). Never raises."""
    return record({"use_of": call_id, "use": use, "actor": actor, "detail": detail,
                   "links": dict(links or {})})


def _all() -> dict:
    from modules import records_migrate

    got = records_migrate.store_rows(STORE, _path(), skip_unparsable=True)
    if got["state"] == "unreadable":
        log.error("ai_calls: unreadable (%s)", got["error"])
    return got


def read() -> dict:
    """Every call, newest first: ``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``.
    Calls only: a use row (`record_use`) is no call, so it neither counts nor costs."""
    got = _all()
    return dict(got, rows=[r for r in reversed(got["rows"]) if "use_of" not in r])


def uses() -> dict:
    """``{call id: [its use rows, oldest first]}``; an unreadable record reads as none (the
    calls' own reader says so)."""
    out = {}
    for r in _all().get("rows") or []:
        if "use_of" in r:
            out.setdefault(r["use_of"], []).append(r)
    return out


def find(call_id: str) -> dict:
    """``{"state", "row", "uses", "error"}``: one call by its id, and what became of it."""
    got = _all()
    if got["state"] == "unreadable":
        return {"state": "unreadable", "row": None, "uses": [], "error": got["error"]}
    row = next((r for r in got["rows"] if r.get("id") == call_id and "use_of" not in r), None)
    return {"state": "ok" if row else "absent", "row": row, "error": "",
            "uses": [r for r in got["rows"] if r.get("use_of") == call_id]}


def cache_summary(day: str, feature: str = None) -> dict:
    """The prompt cache's effect on the UTC *day*'s answered calls (of *feature*, or all):
    ``{"state", "calls", "input", "cache_write", "cache_read", "hit_rate", "error"}``. The hit
    rate is the share of all prompt tokens read from the cache; None with no prompt tokens
    (no call answered), never 0 in its place."""
    got = read()
    if got["state"] == "unreadable":
        return {"state": "unreadable", "calls": 0, "input": 0, "cache_write": 0,
                "cache_read": 0, "hit_rate": None, "error": got["error"]}
    rows = [r for r in got["rows"] if str(r.get("at", "")).startswith(day)
            and r.get("tokens") and (feature is None or r.get("feature") == feature)]
    sums = {"input": 0, "cache_write": 0, "cache_read": 0}
    for r in rows:
        t = r["tokens"]
        sums["input"] += int(t.get("input_tokens") or 0)
        sums["cache_write"] += int(t.get("cache_creation_input_tokens") or 0)
        sums["cache_read"] += int(t.get("cache_read_input_tokens") or 0)
    total = sum(sums.values())
    return dict(sums, state=got["state"], calls=len(rows), error="",
                hit_rate=(sums["cache_read"] / total) if total else None)


def spent_usd(day: str) -> dict:
    """``{"state", "usd", "calls", "error"}``: what the calls recorded on the UTC *day*
    (``YYYY-MM-DD``) cost. An unreadable record is said, never read as nothing spent."""
    got = read()
    if got["state"] == "unreadable":
        return {"state": "unreadable", "usd": None, "calls": 0, "error": got["error"]}
    # A row is the day's when its time is text that starts with it: one with no time is no
    # day's (read without a default, which no row could tell from another).
    rows = [r for r in got["rows"] if isinstance(r.get("at"), str) and r["at"].startswith(day)]
    return {"state": got["state"], "usd": sum(float(r.get("cost_usd") or 0) for r in rows),
            "calls": len(rows), "error": ""}
