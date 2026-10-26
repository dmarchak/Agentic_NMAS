"""The record of every AI call: an append-only records store, `ai_calls` (PHASE8_PLAN 13.2
item 6, AI_ANTHROPIC_PLAN 2.3; the operator, 2026-10-25: a records store with the per-store
file or database switch).

One row per call, sent or refused: its id, when, who asked, the feature, the prompt (name,
version, sha256), the model, the request as it left the host (masked), the response's text
(masked again), the structured output, the verdict (`ok` or the error's kind), the tokens
(cache reads and writes too), the cost, the latency and the provider's rate-limit headers.
Never the API key, and nothing unmasked. History draws each row; the caps sum its costs.
"""
import datetime
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


# ── the cap's day: one home for the counter, the gateway and every screen that shows it ──
#
# The day the day cap counts begins at midnight in the boundary's zone (`ai_cap_day_boundary`,
# a stated setting, default UTC; the operator, 2026-10-26: "the boundary is a stated setting,
# not implied"). A zone follows its daylight-saving changes. The counter (`spent_usd`), the
# gateway's refusal, the AI controls' reason and every "resets HH:MM" read these, so what a
# screen says and what the counter does cannot disagree.

DEFAULT_BOUNDARY = "UTC"


def _zone(name: str):
    from zoneinfo import ZoneInfo
    return datetime.timezone.utc if name in ("", "UTC") else ZoneInfo(name)


def valid_boundary(name: str) -> bool:
    """Whether *name* is "UTC" or a time zone this host's zone database holds."""
    try:
        _zone((name or "").strip() or DEFAULT_BOUNDARY)
        return True
    except Exception:                                   # noqa: BLE001 (any bad name: False)
        return False


def boundary() -> str:
    """The stated day boundary's zone; a stored value this host cannot read is UTC, logged."""
    from modules import settings_schema
    name = str(settings_schema.get_setting("ai_cap_day_boundary", DEFAULT_BOUNDARY)
               or DEFAULT_BOUNDARY).strip()
    if not valid_boundary(name):
        log.warning("ai: the day boundary %r is no time zone this host holds; UTC is used",
                    name)
        return DEFAULT_BOUNDARY
    return name


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def day_of(instant, zone: str = None) -> str:
    """The cap's day (``YYYY-MM-DD``) *instant* (an aware datetime) falls in."""
    return instant.astimezone(_zone(zone or boundary())).strftime("%Y-%m-%d")


def today(now=None, zone: str = None) -> str:
    """The cap's day now."""
    return day_of(now or _now(), zone)


def resets_at(now=None, zone: str = None):
    """When the cap's day after *now* begins: the next midnight in the boundary's zone, as an
    aware UTC datetime (a daylight-saving change between is followed)."""
    z = _zone(zone or boundary())
    local = (now or _now()).astimezone(z)
    tomorrow = (local + datetime.timedelta(days=1)).date()
    midnight = datetime.datetime.combine(tomorrow, datetime.time(0, 0), tzinfo=z)
    return midnight.astimezone(datetime.timezone.utc)


def reset_info(now=None, zone: str = None) -> dict:
    """What a screen says of the cap's reset: ``{"at", "utc", "zone", "zone_hm"}``, the reset
    instant (``YYYY-MM-DDTHH:MM:SSZ``) and its time in UTC and in the boundary's zone. The
    viewer's own time is drawn from *at* in the browser (nmas_v2.js `drawClock`), so every one
    is the same instant the counter turns over at."""
    zone = zone or boundary()
    at = resets_at(now or _now(), zone)
    return {"at": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "utc": at.strftime("%H:%M"), "zone": zone,
            "zone_hm": at.astimezone(_zone(zone)).strftime("%H:%M")}


def _row_day(row: dict, zone: str) -> str:
    """The cap's day a call's row was recorded on, or "" for a row with no readable time."""
    at = row.get("at")
    if not isinstance(at, str):
        return ""
    try:
        instant = datetime.datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except ValueError:
        return ""
    return day_of(instant, zone)


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
               links: dict = None, drafts: list = None) -> dict:
    """Append what became of a call's answer, its own row keyed by the call's id (PHASE8_PLAN
    15.14: the use is recorded at the source, append-only, never an edit of the call's row):
    *use* is the feature's own word ("filled", "shown", "refused by validation"), *detail*
    why, *links* where what it produced is (a page and its anchor). *drafts* are the digests
    of what a draft offered to commit (feature 7's part 2: a commit is refused unless what it
    is handed is one of them). Never raises."""
    row = {"use_of": call_id, "use": use, "actor": actor, "detail": detail,
           "links": dict(links or {})}
    if drafts:
        row["drafts"] = list(drafts)
    return record(row)


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
    """The prompt cache's effect on the cap's *day*'s answered calls (of *feature*, or all):
    ``{"state", "calls", "input", "cache_write", "cache_read", "hit_rate", "error"}``. The hit
    rate is the share of all prompt tokens read from the cache; None with no prompt tokens
    (no call answered), never 0 in its place."""
    got = read()
    if got["state"] == "unreadable":
        return {"state": "unreadable", "calls": 0, "input": 0, "cache_write": 0,
                "cache_read": 0, "hit_rate": None, "error": got["error"]}
    zone = boundary()
    rows = [r for r in got["rows"] if _row_day(r, zone) == day
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


def spent_usd(day: str, zone: str = None) -> dict:
    """``{"state", "usd", "calls", "error"}``: what the calls recorded on the cap's *day*
    (``YYYY-MM-DD``, its midnight the boundary's) cost. An unreadable record is said, never
    read as nothing spent."""
    got = read()
    if got["state"] == "unreadable":
        return {"state": "unreadable", "usd": None, "calls": 0, "error": got["error"]}
    # A row is the day's when its recorded time falls in it: one with no readable time is no
    # day's (read without a default, which no row could tell from another).
    zone = zone or boundary()
    rows = [r for r in got["rows"] if _row_day(r, zone) == day]
    return {"state": got["state"], "usd": sum(float(r.get("cost_usd") or 0) for r in rows),
            "calls": len(rows), "error": ""}
