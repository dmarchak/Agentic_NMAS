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
import functools
import json
import logging
import os
import re
import threading
import time
import uuid

log = logging.getLogger(__name__)

_lock = threading.Lock()

#: The record's store on the records database (one file for the installation).
STORE = "ai_calls"
#: The verdict of a press that joined another's call (C1854, `gateway._joined`): the joiner's
#: own row, cost 0, ``joined`` the call's id. No call was made: `spent_usd` counts none.
JOINED = "joined"


def _path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, "ai_calls.jsonl")


def version():
    """What changes whenever a row is appended to the record, for a reader that holds a value
    computed from it (C3788: the measured cost per call, read 24 to 26 times per Incidents page):
    the file's identity, size and modification time; None on the records database or when the
    file cannot be read, so such a reader computes again every time, never holds a stale one."""
    from modules import records_db

    try:
        if records_db.backend(STORE) == records_db.POSTGRES:
            return None
        st = os.stat(_path())
    except Exception:                               # noqa: BLE001 (no version: compute again)
        return None
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


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
    return _stamp_day(at, zone or boundary())


@functools.lru_cache(maxsize=1 << 17)
def _stamp_day(at: str, zone: str) -> str:
    """The cap's day of the stamp *at* in *zone*: a pure function of the two, kept, so a month
    of rows read again on every Needs attention render is parsed once a process (C2225: its
    `strptime` was 0.8 s of each render on the host, 2026-10-29). At most `maxsize` stamps."""
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
            at = records_migrate.store_append(STORE, _path(), row)
        recorded = True
    except Exception as exc:                  # noqa: BLE001
        log.error("ai_calls: COULD NOT RECORD the call %s (%s)", row.get("id"), exc)
    else:
        if at and row.get("id") and "use_of" not in row:
            _index_add(str(row["id"]), *at)
    return dict(row, recorded=recorded)


def record_use(call_id: str, use: str, *, actor: str = "", detail: str = "",
               links: dict = None, drafts: list = None, needs: list = None) -> dict:
    """Append what became of a call's answer, its own row keyed by the call's id (PHASE8_PLAN
    15.14: the use is recorded at the source, append-only, never an edit of the call's row):
    *use* is the feature's own word ("filled", "shown", "refused by validation"), *detail*
    why, *links* where what it produced is (a page and its anchor). *drafts* are the digests
    of what a draft offered to commit (feature 7's part 2: a commit is refused unless what it
    is handed is one of them). *needs* are a needs round's lookups, each with its state
    (`needs.run`). Never raises."""
    row = {"use_of": call_id, "use": use, "actor": actor, "detail": detail,
           "links": dict(links or {})}
    if drafts:
        row["drafts"] = list(drafts)
    if needs:
        row["needs"] = list(needs)
    return record(row)


def _all() -> dict:
    from modules import records_migrate

    got = records_migrate.store_rows(STORE, _path(), skip_unparsable=True)
    if got["state"] == "unreadable":
        log.error("ai_calls: unreadable (%s)", got["error"])
    return got


def read() -> dict:
    """Every call, newest first: ``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``.
    Calls only: a use row (`record_use`) is no call, so it neither counts nor costs. A press
    that joined another's call is its own row here (verdict `JOINED`, cost 0, ``joined`` the
    call's id), drawn as a join."""
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


# ── C3839: where each call's row starts, so `find` is one seek ─────────────────────────────
#
# `find` read the whole record for one id: 471 MB on the host, 8.00 s for one History "Show
# the prompt and the answer" (2026-11-16). A second file beside the record, `ai_calls.offsets`,
# holds one line per call, ``<id> <offset> <length>``, appended as the call is recorded: the
# offset is read under the record's own cross-process lock (`records_migrate.store_append`),
# so it is where the row starts; the index line is one O_APPEND write of under 100 bytes, so
# writers in several processes never interleave one. Lines ``# built <dev> <ino> <end>`` say
# the record's bytes before *end* have all been indexed (the record's identity beside it).
#
# What was recorded before the index existed, or by a process that did not write it, is
# indexed by `_catch_up`, from the last built end to the record's end, under the index's own
# cross-process lock (`PathLock`), once: a second process waiting on it reads the new end and
# scans nothing. Only the bytes past the last build are ever scanned again, so the first ask
# after the deploy pays the one scan (said in the log, with its bytes and time) and no other.
#
# Nothing in the index is trusted: every row it points at is read and parsed, and returned
# only when its id is the one asked and it is a call, not a use row. An entry that does not
# hold (the record rewritten, a torn line) is passed over, and an id every entry of which
# failed is read the old way, the whole record (`_find_scan`), never answered as absent.

#: A call's id as `new_id` makes it, the shape the catch-up indexes (a nested id too: each
#: entry is checked on use, so one that is no call's row is passed over).
_ID_IN_LINE = re.compile(rb'"id": "(ai-[0-9a-f]{16})"')
#: The block the catch-up reads the record in.
_SCAN_BLOCK = 8 * 1024 * 1024

_index = {"ident": None, "end": 0, "map": {}, "built": None}
_index_lock = threading.Lock()


def _index_path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, "ai_calls.offsets")


def _index_write(text: str) -> None:
    """Append *text* (whole lines) to the index in one write, owner-only."""
    from modules.config import open_secure
    with open_secure(_index_path(), "ab") as fh:
        fh.write(text.encode("ascii"))


def _index_add(call_id: str, offset: int, length: int) -> None:
    """Note where the call *call_id*'s row is. Never raises: a call the index misses is found
    by the catch-up, so a failed write costs one later scan of the bytes past it, logged."""
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", call_id):
        return
    try:
        _index_write(f"{call_id} {int(offset)} {int(length)}\n")
    except Exception as exc:                  # noqa: BLE001
        log.warning("ai_calls: the offsets index missed %s (%s); the catch-up finds it",
                    call_id, exc)


def _index_refresh() -> dict:
    """The index as this process holds it, after reading the lines appended since (the whole
    file again when it is another file or shorter). Called under `_index_lock`."""
    path = _index_path()
    try:
        st = os.stat(path)
    except FileNotFoundError:
        _index.update(ident=None, end=0, map={}, built=None)
        return _index
    ident = (st.st_dev, st.st_ino)
    if _index["ident"] != ident or st.st_size < _index["end"]:
        _index.update(ident=ident, end=0, map={}, built=None)
    if st.st_size > _index["end"]:
        with open(path, "rb") as fh:
            fh.seek(_index["end"])
            added = fh.read(st.st_size - _index["end"])
        whole = added.rfind(b"\n") + 1
        for raw in added[:whole].split(b"\n"):
            parts = raw.decode("ascii", "replace").split()
            if len(parts) == 5 and parts[:2] == ["#", "built"]:
                try:
                    _index["built"] = (int(parts[2]), int(parts[3]), int(parts[4]))
                except ValueError:
                    pass
            elif len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                _index["map"].setdefault(parts[0], []).append((int(parts[1]), int(parts[2])))
        _index["end"] += whole
    return _index


def _candidates(call_id: str) -> list:
    """Where the index says *call_id*'s row may be, the newest entry first."""
    with _index_lock:
        return list(reversed(_index_refresh()["map"].get(call_id) or []))


def _row_at(path: str, call_id: str, spots: list):
    """The call *call_id*'s row at the first of *spots* that holds it, or None."""
    try:
        with open(path, "rb") as fh:
            for offset, length in spots:
                fh.seek(offset)
                raw = fh.read(length)
                try:
                    row = json.loads(raw.decode("utf-8"))
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("id") == call_id and "use_of" not in row:
                    return row
    except OSError as exc:
        log.warning("ai_calls: could not read a call's row at its offset (%s)", exc)
    return None


def _catch_up(path: str) -> None:
    """Index the record's bytes from the last built end to its end, once across processes."""
    from modules.filestore import PathLock

    with PathLock(_index_path()):
        st = os.stat(path)
        with _index_lock:
            built = _index_refresh()["built"]
        start = built[2] if built and built[:2] == (st.st_dev, st.st_ino) \
            and built[2] <= st.st_size else 0
        if start >= st.st_size:
            return
        t, lines, pos, out = time.monotonic(), 0, start, []
        with open(path, "rb") as fh:
            fh.seek(start)
            rest = b""
            while pos + len(rest) < st.st_size:
                chunk = fh.read(min(_SCAN_BLOCK, st.st_size - pos - len(rest)))
                if not chunk:
                    break
                buf = rest + chunk
                at = 0
                while True:
                    nl = buf.find(b"\n", at)
                    if nl < 0:
                        break
                    line = buf[at:nl]
                    for found in dict.fromkeys(_ID_IN_LINE.findall(line)):
                        out.append(f"{found.decode('ascii')} {pos + at} {nl + 1 - at}\n")
                    lines += 1
                    at = nl + 1
                pos += at
                rest = buf[at:]
        # A last line still being written is left for the next catch-up: `pos` ends at the
        # last whole line.
        out.append(f"# built {st.st_dev} {st.st_ino} {pos}\n")
        _index_write("".join(out))
        log.info("ai_calls: indexed %d lines (%d bytes from %d) in %.1f s", lines,
                 pos - start, start, time.monotonic() - t)


def _find_scan(call_id: str) -> dict:
    """The old read: the whole record for one id (the index's last resort)."""
    got = _all()
    if got["state"] == "unreadable":
        return {"state": "unreadable", "row": None, "uses": [], "error": got["error"]}
    row = next((r for r in got["rows"] if r.get("id") == call_id and "use_of" not in r), None)
    return {"state": "ok" if row else "absent", "row": row, "error": "",
            "uses": [r for r in got["rows"] if r.get("use_of") == call_id]}


def _uses_of(call_id: str) -> list:
    """What became of the call, oldest first, from the rows this process keeps (`kept_all`,
    which drops only the request a use row never has)."""
    return [r for r in kept_all().get("rows") or [] if r.get("use_of") == call_id]


def find(call_id: str) -> dict:
    """``{"state", "row", "uses", "error"}``: one call by its id, and what became of it. On
    the file, one seek through the offsets index (the section above); on the records
    database, its read."""
    from modules import records_db

    if records_db.backend(STORE) == records_db.POSTGRES:
        return _find_scan(call_id)
    path = _path()
    if not os.path.exists(path):
        return {"state": "absent", "row": None, "uses": [], "error": ""}
    spots = _candidates(call_id)
    row = _row_at(path, call_id, spots) if spots else None
    if row is None:
        try:
            _catch_up(path)
        except Exception as exc:              # noqa: BLE001 (the scan answers instead)
            log.warning("ai_calls: the offsets index could not catch up (%s)", exc)
            return _find_scan(call_id)
        again = _candidates(call_id)
        row = _row_at(path, call_id, again) if again else None
        if row is None and (again or not re.fullmatch(r"ai-[0-9a-f]{16}", call_id or "")):
            # Entries that do not hold, or an id the catch-up does not index: the whole record.
            return _find_scan(call_id)
    if row is None:
        return {"state": "absent", "row": None, "uses": [], "error": ""}
    return {"state": "ok", "row": row, "error": "", "uses": _uses_of(call_id)}


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


#: How far before a window's start a windowed read keeps reading back: a row's `at` is stamped
#: before `record` waits for the file's lock, so rows are in time order only to within that
#: wait (seconds); ten minutes is far past it (`records_migrate.store_rows_since`).
ORDER_SLACK_S = 600.0


def day_start(day: str, zone: str = None):
    """When the cap's *day* (``YYYY-MM-DD``) begins: its midnight in the boundary's zone, as
    an aware UTC datetime. ValueError for a day that is no date. A midnight a daylight-saving
    change skips is read with the offset before it, which is the instant the day's first hour
    begins; a repeated one, its first occurrence (zoneinfo's fold 0)."""
    z = _zone(zone or boundary())
    midnight = datetime.datetime.combine(datetime.date.fromisoformat(day), datetime.time(0, 0),
                                         tzinfo=z)
    return midnight.astimezone(datetime.timezone.utc)


#: What a windowed row leaves out: the request as sent, which no spend figure reads and which
#: the window's rows, kept per process (`records_migrate._tail_rows_kept`), would otherwise
#: hold (125 of the record's 140 MiB on the host, 2026-10-27). `find` gives a call whole.
WINDOW_WITHOUT = ("request",)


def rows_since(start) -> dict:
    """Every call recorded at or after *start* (an aware datetime), OLDEST first, read without
    reading the rest of the record: the bound every spend figure is read within (the record
    grows for ever; a window does not). Calls only, as `read`, each without the keys in
    `WINDOW_WITHOUT`. ``{"state", "rows", "error"}``.
    Its premise: the record is in time order to within `ORDER_SLACK_S`, because `record`
    stamps each row as it writes it and no product writer hands in a time of its own
    (tests/test_ai_spend.py holds both)."""
    from modules import records_migrate

    got = records_migrate.store_rows_since(STORE, _path(), start, ORDER_SLACK_S,
                                           skip_unparsable=True, drop=WINDOW_WITHOUT)
    if got["state"] == "unreadable":
        log.error("ai_calls: unreadable (%s)", got["error"])
    return dict(got, rows=[r for r in got["rows"] if "use_of" not in r])


#: Before any row the record holds: `kept_all`'s window, all of it.
EVER = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)


def kept_all() -> dict:
    """Every row, calls and their use rows, OLDEST first, each without the keys in
    `WINDOW_WITHOUT`, through the one kept read `rows_since` uses (`records_migrate.
    _tail_rows_kept`: the record parsed once a process, then only the lines appended since):
    History's AI calls, which draw no request (an opened row reads its call whole by `find`).
    The whole-record read, twice a load, was History's 13 s on the host (416 MB, 2026-10-29),
    and the same rows were already kept for Needs attention's month of spend, so keeping them
    from `EVER` holds nothing more. ``{"state", "rows", "error"}``."""
    from modules import records_migrate

    got = records_migrate.store_rows_since(STORE, _path(), EVER, ORDER_SLACK_S,
                                           skip_unparsable=True, drop=WINDOW_WITHOUT)
    if got["state"] == "unreadable":
        log.error("ai_calls: unreadable (%s)", got["error"])
    return got


def warm() -> None:
    """Read the record once into the kept rows (`kept_all`), so a page's first read after a
    start is not the cold parse (10 s on the host, 2026-10-29). Started by the app's own
    start-up on a background task, never on import; a failure is logged and the first read
    pays it instead. The offsets index catches up here too (C3839), so the first "Show the
    prompt and the answer" after a deploy is one seek, not the one scan."""
    t = time.monotonic()
    got = kept_all()
    log.info("ai_calls: kept %d rows in %.1f s (%s)", len(got.get("rows") or []),
             time.monotonic() - t, got.get("state"))
    try:
        from modules import records_db
        if records_db.backend(STORE) != records_db.POSTGRES and os.path.exists(_path()):
            _catch_up(_path())
    except Exception as exc:                  # noqa: BLE001 (the first find catches up instead)
        log.warning("ai_calls: the offsets index could not catch up at start (%s)", exc)


def day_rows(day: str, zone: str = None) -> dict:
    """``{"state", "rows", "error"}``: the calls recorded on the cap's *day*, oldest first,
    read within that day's window (`rows_since`). A day that is no date holds no row."""
    zone = zone or boundary()
    try:
        start = day_start(day, zone)
    except (TypeError, ValueError):
        return {"state": "ok", "rows": [], "error": ""}
    got = rows_since(start)
    # A row is the day's when its recorded time falls in it: one with no readable time is no
    # day's (read without a default, which no row could tell from another).
    return dict(got, rows=[r for r in got["rows"] if _row_day(r, zone) == day])


def spent_usd(day: str, zone: str = None) -> dict:
    """``{"state", "usd", "calls", "error"}``: what the calls recorded on the cap's *day*
    (``YYYY-MM-DD``, its midnight the boundary's) cost, read within the day's window
    (`day_rows`), never the whole record. An unreadable record is said, never read as nothing
    spent."""
    got = day_rows(day, zone)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "usd": None, "calls": 0, "error": got["error"]}
    rows = got["rows"]
    # A press that joined another's call (verdict "joined", C1854) cost nothing and made no
    # call: it is summed (its 0) but never counted as a call.
    return {"state": got["state"], "usd": sum(float(r.get("cost_usd") or 0) for r in rows),
            "calls": sum(1 for r in rows if r.get("verdict") != JOINED), "error": ""}
