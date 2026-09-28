"""A READER JOB: one background read of an outside service, stored, dated,
watched, and announced.

Stage 7.2 (NSOT_STAGE7_PLAN.md, "the rest of 7.2"). Grafana's alert state is
the first reader; Oxidized freshness, the status bar's integration health and
C92's reader reuse this module. They inherit its rules by REUSE, not by
reading the plan, so the rules are written here, where the next reader is
built (the operator's point, 2026-09-28). Each rule names the finding that
produced it.

1. **A consumer reads the CACHE, never the service.** A page load that asks
   Grafana is per-request I/O to an outside service (the scale rule: nothing
   does per-device, or per-service, work per request), and a slow service
   makes a slow page. One job reads; every consumer (Needs attention, the
   agent's triage in 8.6) reads what it stored.

2. **A stored value is dated by its VALUE, never by the read of the store**
   (`value_at`, 7.2 step 1). Reading a file written an hour ago at 10:00
   does not make its contents 10:00's. `value_at` is when the read BEGAN, so
   the value is at least that fresh and never claimed fresher.

3. **A failed read KEEPS the last good value and says the attempt failed.**
   It never replaces the value with empty: "Grafana could not be asked" and
   "nothing is firing" must not share a state (absent versus empty, which
   erased the settings file). A consumer draws the old value WITH its date
   and the failure beside it.

4. **The reader names its endpoints and its time**, on every stored result.
   A lookup that misses is a fact about the query, not about the system:
   C165 read "0 firing" from one endpoint while the other held two instances,
   and the report was only checkable because it named which one it read.

5. **A read that returns exactly its page size is truncated** (the state
   history's 100-row cap made "Device unreachable never alerted" false; it
   alerted 38 times). A reader that pages declares its limit and calls
   `refuse_truncated()`, which refuses rather than storing a partial answer
   as a whole one.

6. **A claim about all time needs a window that covers all time.** A reader
   states the window its value covers (`window` in the stored result), so a
   consumer cannot turn "none in the last hour" into "never".

7. **Its liveness is a job-health row** (`health_rows()`), decided from the
   store, so a reader that stopped is visible from ANY process, including one
   that never ran it: `not_run`, `failing` (since the streak began),
   `never_succeeded`, `stale` (no attempt for `stale_after_intervals` times
   the interval: the thread has stopped), `unknown` (the store is
   unreadable). A reader that fails into a log nobody reads has not reported
   (C14).

8. **Its interval is derived from a measurement and says which**
   (`interval_basis`). Reading faster than the service changes buys nothing;
   reading slower is a window in which the screen is wrong.

9. **It ANNOUNCES when it finishes** (C58), naming the data keys its result
   feeds (`invalidates`, from `invalidation.VOCABULARY`, checked at
   registration like a route's declaration). A panel re-fetches on the
   announcement, never on a timer of its own. The announcement is sent after
   a failed read too, because the failure changes what the page must say.
   An announcement that could not be sent is counted (`announce_health()`),
   never raised into the read.

10. **A cache is re-derivable, so an UNREADABLE one is replaced, never
    refused.** The opposite of a record (`filestore.read_json_for_write`
    refuses, because a record lost is lost): the next read rebuilds it. The
    damaged file is preserved as ``.corrupt-<ts>`` first, and the row that
    replaces it says so, because a replaced cache also lost its last good
    value and a consumer must not read that as "nothing was ever read".

Nothing here starts a thread at import (C36): `start()` is called from the
app's `_start_background_daemons()`, and only there.
"""

import calendar
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from modules import config as _config
from modules import filestore as _filestore

log = logging.getLogger(__name__)

_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")


class ReaderRefused(ValueError):
    """A reader declared wrongly: refused at registration, not at its first run."""


class Truncated(RuntimeError):
    """A paged read came back exactly full: the answer is partial (rule 5)."""


@dataclass(frozen=True)
class Reader:
    """One reader. Every field is required except the last two, because each
    is a claim a consumer relies on and an omitted one is a guess."""

    name: str                 # the store file and the job-health unit
    what: str                 # a sentence: what this reads and why
    endpoints: tuple          # every endpoint read, named on each result (rule 4)
    interval_seconds: int
    interval_basis: str       # the measurement the interval comes from (rule 8)
    read: Callable[[], dict]  # returns the value; raises when it could not ask
    invalidates: tuple        # data keys the result feeds (rule 9)
    remedy: str = ""          # what a person does when it fails, if anything is known
    stale_after_intervals: int = 3
    window: str = field(default="")   # what time range the value covers (rule 6)


_REGISTRY: dict = {}
_REGISTRY_MU = threading.Lock()


def register(reader: Reader) -> Reader:
    """Declare a reader. Refused here, loudly, rather than at its first run."""
    from modules.invalidation import VOCABULARY

    problems = []
    if not _NAME.match(reader.name or ""):
        problems.append(f"name {reader.name!r} is not a slug")
    if not (reader.what or "").strip():
        problems.append("it says nothing about what it reads")
    if not reader.endpoints:
        problems.append("it names no endpoint (rule 4)")
    if not isinstance(reader.interval_seconds, int) or reader.interval_seconds <= 0:
        problems.append(f"interval {reader.interval_seconds!r} is not a positive number of seconds")
    if not (reader.interval_basis or "").strip():
        problems.append("its interval states no measurement (rule 8)")
    if not callable(reader.read):
        problems.append("its read is not callable")
    if not reader.invalidates:
        problems.append("it announces no data key (rule 9)")
    unknown = [k for k in reader.invalidates if k not in VOCABULARY]
    if unknown:
        problems.append(f"it announces keys the vocabulary does not hold: {', '.join(unknown)}")
    if reader.stale_after_intervals < 2:
        problems.append("stale after fewer than two intervals would call one slow read a stop")
    with _REGISTRY_MU:
        if reader.name in _REGISTRY and _REGISTRY[reader.name] is not reader:
            problems.append(f"a reader named {reader.name!r} is already registered")
        if problems:
            raise ReaderRefused(f"reader {reader.name!r} refused: " + "; ".join(problems))
        _REGISTRY[reader.name] = reader
    return reader


def unregister(name: str) -> None:
    """For tests, which register their own readers."""
    with _REGISTRY_MU:
        _REGISTRY.pop(name, None)


def readers() -> list:
    """Every registered reader, the declared ones imported first, so the
    population does not depend on what happened to be imported (C132)."""
    for mod in DECLARED_MODULES:
        __import__(mod)
    with _REGISTRY_MU:
        return [_REGISTRY[k] for k in sorted(_REGISTRY)]


#: The modules that register a reader when imported. A reader module is
#: listed here, or it is not in the population job health watches.
DECLARED_MODULES: tuple = ()


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------

def store_path(name: str) -> str:
    """Derived from `config.DATA_DIR` at call time (the harness points it at
    a temporary store before anything imports)."""
    return os.path.join(_config.DATA_DIR, "readers", f"{name}.json")


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _parse_iso(value):
    try:
        return calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def refuse_truncated(items, limit: int, what: str):
    """Rule 5. *items* came from a read capped at *limit*: exactly full is
    partial, so it raises, and the reader's failure is recorded with the
    last good value kept."""
    if limit and len(items) >= limit:
        raise Truncated(f"{what} returned {len(items)} of a {limit}-item page: the answer is "
                        "partial, and a partial answer stored as whole is how \"never\" "
                        "becomes false")
    return items


def read_cached(name: str) -> dict:
    """``{"state": "absent"|"unreadable"|"ok", "doc": ..., "why": ...}``.
    Absent and unreadable are different facts (rule 3's sibling)."""
    path = store_path(name)
    if not os.path.exists(path):
        return {"state": "absent", "doc": None, "why": f"no reader has written {path}"}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "doc": None,
                "why": f"{os.path.basename(path)} could not be read ({type(exc).__name__})"}
    return {"state": "ok", "doc": doc, "why": ""}


def _redacted(text: str) -> str:
    try:
        from modules.redact import redact_text
        return redact_text(text)
    except Exception:                                   # noqa: BLE001
        return "(the error text could not be redacted, so it is withheld)"


_ANNOUNCE = {"sent": 0, "failed": 0, "last_error": ""}


def announce_health() -> dict:
    """Announcements sent and failed by THIS process (rule 9)."""
    return dict(_ANNOUNCE)


def announce_via_page(keys, name: str, ok: bool) -> None:
    """The app's announcer: the keys to every open page, by this reader."""
    from modules import invalidation
    invalidation.announce(keys, f"reader:{name}", ok)


def run_once(reader: Reader, announce=None, clock=time.time) -> dict:
    """Read, store, announce. Returns the stored document.

    A read that raises is a failed ATTEMPT: recorded with its error, the last
    good value kept (rule 3). A store that cannot be written raises, because
    nothing else can record it; the stale row then says the reader stopped
    (rule 7)."""
    started = clock()
    t0 = time.monotonic()
    value, error = None, ""
    try:
        value = reader.read()
        if not isinstance(value, dict):
            error = f"the read returned {type(value).__name__}, not a mapping"
    except Exception as exc:                            # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    took = int((time.monotonic() - t0) * 1000)

    path = store_path(reader.name)
    with _filestore.PathLock(path):
        prior = read_cached(reader.name)
        replaced = ""
        if prior["state"] == "unreadable":
            # Rule 10: a cache is replaced, and the replacement says so.
            _filestore.preserve_corrupt(path, prior["why"])
            replaced = prior["why"]
        before = prior["doc"] or {}
        doc = {
            "reader": reader.name,
            "what": reader.what,
            "endpoints": list(reader.endpoints),
            "window": reader.window,
            "interval_seconds": reader.interval_seconds,
            "interval_basis": reader.interval_basis,
            "last_attempt": {"at": _iso(started), "ok": not error, "took_ms": took,
                             **({"error": _redacted(error)} if error else {})},
            "last_good": before.get("last_good"),
            "failing_since": None,
        }
        if replaced:
            doc["replaced_unreadable"] = {"at": _iso(started), "why": replaced}
        elif before.get("replaced_unreadable") and error:
            doc["replaced_unreadable"] = before["replaced_unreadable"]
        if error:
            was_failing = before.get("failing_since")
            doc["failing_since"] = was_failing or _iso(started)
            log.error("reader %s: the read failed (%s); the last good value from %s is kept",
                      reader.name, doc["last_attempt"]["error"],
                      (doc["last_good"] or {}).get("value_at", "never"))
        else:
            doc["last_good"] = {"value": value, "value_at": _iso(started), "took_ms": took}
        _filestore.write_atomic(path, json.dumps(doc, indent=1, sort_keys=True))

    if announce is not None:
        try:
            announce(list(reader.invalidates), reader.name, doc["last_attempt"]["ok"])
            _ANNOUNCE["sent"] += 1
        except Exception as exc:                        # noqa: BLE001
            _ANNOUNCE["failed"] += 1
            _ANNOUNCE["last_error"] = f"{type(exc).__name__}: {exc}"
            log.error("reader %s: its announcement could not be sent (%s); panels will "
                      "show the value at their next load", reader.name, exc)
    return doc


# ---------------------------------------------------------------------------
# Liveness (rule 7)
# ---------------------------------------------------------------------------

def health_rows(now: float = None, population: list = None) -> list:
    """One job-health row per reader, decided from its store alone."""
    now = time.time() if now is None else now
    rows = []
    for r in (readers() if population is None else population):
        unit = f"reader:{r.name}"
        base = {"unit": unit, "what": r.what, "state": "ok",
                "max_age_minutes": (r.interval_seconds * r.stale_after_intervals) // 60}
        got = read_cached(r.name)
        if got["state"] == "absent":
            rows.append({**base, "state": "not_run",
                         "detail": (f"it has never run here: {got['why']}. It runs in the app "
                                    "process, started with the app's background services"),
                         "action": {"label": "Read the app log for this reader's start; it "
                                             "runs only in a started app (python app.py or "
                                             "flask-app.service)"}})
            continue
        if got["state"] == "unreadable":
            rows.append({**base, "state": "unknown",
                         "detail": f"{got['why']}; the next run replaces it"})
            continue
        doc = got["doc"]
        attempt = doc.get("last_attempt") or {}
        good = doc.get("last_good") or {}
        at = _parse_iso(attempt.get("at"))
        stale_after = r.interval_seconds * r.stale_after_intervals
        if at is None or now - at > stale_after:
            since = _iso(at + stale_after) if at is not None else None
            rows.append({**base, "state": "stale", "since": since,
                         "detail": (f"no read since {attempt.get('at', 'ever')} (it reads every "
                                    f"{r.interval_seconds} s; stale after {stale_after} s): the "
                                    "reader has stopped. What it last stored is from "
                                    f"{good.get('value_at', 'never')}"),
                         "action": {"label": "Read the app log for this reader; its thread "
                                             "has stopped, and a restart starts it again"}})
            continue
        if not attempt.get("ok"):
            state = "failing" if good else "never_succeeded"
            rows.append({**base, "state": state, "since": doc.get("failing_since"),
                         "detail": (f"its last read of {', '.join(doc.get('endpoints') or [])} "
                                    f"at {attempt.get('at')} failed: {attempt.get('error', '?')}. "
                                    + (f"The value shown is from {good['value_at']}"
                                       if good else "It has never read a value")),
                         **({"action": {"label": r.remedy}} if r.remedy else {})})
            continue
        rows.append({**base, "detail": (f"read at {good.get('value_at')} in "
                                        f"{good.get('took_ms')} ms, every {r.interval_seconds} s "
                                        f"({r.interval_basis})")})
    return rows


# ---------------------------------------------------------------------------
# The scheduler: one thread per reader, so a slow service delays only itself
# ---------------------------------------------------------------------------

_threads: dict = {}
_stop = threading.Event()


def _loop(reader: Reader, announce) -> None:
    while not _stop.is_set():
        try:
            run_once(reader, announce=announce)
        except Exception as exc:                        # noqa: BLE001
            # The store could not be written: logged here, and the stale row
            # names it at the next health read, from any process.
            log.error("reader %s: its result could not be stored: %s", reader.name, exc)
        _stop.wait(reader.interval_seconds)


def start(announce=None) -> list:
    """Start every registered reader's thread once. Returns their names."""
    _stop.clear()
    started = []
    for r in readers():
        t = _threads.get(r.name)
        if t is not None and t.is_alive():
            continue
        t = threading.Thread(target=_loop, args=(r, announce), daemon=True,
                             name=f"reader:{r.name}")
        _threads[r.name] = t
        t.start()
        started.append(r.name)
    if started:
        log.info("readers started: %s", ", ".join(started))
    return started


def stop() -> None:
    _stop.set()
