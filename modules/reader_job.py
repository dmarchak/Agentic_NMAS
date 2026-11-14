"""A READER JOB: one background read of an outside service, stored, dated,
watched, and announced.

Stage 7.2 (NSOT_STAGE7_PLAN.md, "the rest of 7.2"). Grafana's alert state is
the first reader; the status bar's integration health and C92's reader reuse
this module (Oxidized freshness did too, until Phase 3 removed it). They
inherit its rules by REUSE, not by reading the plan, so the rules are written here, where the next reader is
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
   **A reader whose value moves every cycle** (a probe time) may announce only
   when something a page draws CHANGES (`announce_if`), and then MUST announce
   at least every `announce_at_least_every` seconds regardless: without the
   keepalive, a reader that stopped and a reader with nothing new are the same
   silence (the operator's point about the live-data contract). Registration
   refuses the first without the second. The page's promise for such a value is
   2.5 keepalives, because the page's copy is legitimately that old; the
   reader's own liveness row still judges the read cycle (C92's reader).
   **Every other completed check refreshes open pages, changed or not** (the
   operator, 2026-10-01, rule 13 applied to the schedule): the Update page
   read "asked 7 min ago" from a reader asking every 300 s, because an
   unchanged answer was not announced and the page kept its older copy. A
   reader may skip an unchanged run only where it is named in
   `CHANGE_ONLY`, with why no page draws what the skipped run would refresh.

10. **A cache is re-derivable, so an UNREADABLE one is replaced, never
    refused.** The opposite of a record (`filestore.read_json_for_write`
    refuses, because a record lost is lost): the next read rebuilds it. The
    damaged file is preserved as ``.corrupt-<ts>`` first, and the row that
    replaces it says so, because a replaced cache also lost its last good
    value and a consumer must not read that as "nothing was ever read".

11. **A CHECK stays live; only a REPORT is cached** (the operator, 2026-09-28,
    on the freshness gate). A report describes the world as of some time, and
    a stored value with its time is the right shape for it. A check guards an
    action at the moment of acting: the sanitiser's freshness gate (removed in
    Phase 3) compared the exact bytes it was about to write, and no stored value can stand for
    those. Cache everything is the tempting wrong answer, so ask of each new
    reader: is anything DECIDING on this value at the moment it acts? If so,
    that decision reads live, and the reader serves only the ones reading.

12. **A reader's promise is about how fast NMAS NOTICES, never about how fast
    the source notices the world.** The freshness reader (removed in Phase 3) re-read
    every 300 s, and Oxidized polled each device every 3600 s: two latencies, and a page
    must never let the first stand for the second. State both where a person
    reads the value.

13. **A stored answer says what CAUSED it, and a run a person asked for is
    answered to that person** (the operator, 2026-09-30, on About's Check
    again). Every run records its trigger (`scheduled`, `request` with the
    person, `after_commit`) on the attempt and on the value, and the last
    `RUNS_KEPT` runs are kept with their time and duration, so "did my click
    run, and how long did it take" is answered from the store, and each run
    on request is logged at INFO with both. A run on request ALWAYS announces:
    `announce_if` saves pages a redraw nobody waits for, and a person pressing
    a button is waiting. It did not: the check found nothing new, announced
    nothing, and the button, which had reported only that the REQUEST was
    accepted, reverted on a 5 s timer while the text still said "asking".
    `request_run()` starts one at a time per reader; `request_in_flight()` says
    a run is still owed an answer until the store holds it, so a page drawn
    mid-run stays busy; `answer_bound()` is how long a page waits before
    saying the answer is late, 2.5x the slowest recorded run. Needs attention's
    **Run the check again** is such a run (modules/recheck.py), refused while
    the reader is `in_progress` or inside its minimum spacing or its backoff.

14. **A read that fails because its dependency is not answering YET is retried
    on a short backoff, and within a start grace it is waiting, never failing**
    (the operator, 2026-11-05; C2568: NetBox's boot left `netbox-secrets`
    critical for its whole hourly interval after NetBox answered). "Not
    answering" is connection-level only (`not_answering`): refused, reset or
    aborted, or timed out before any HTTP answer; an HTTP error, a TLS failure,
    a name that does not resolve or a wrong answer is the dependency ANSWERING,
    and is the failure it is today. Such a failure is retried after
    `BACKOFF_FIRST_SECONDS`, doubling to `BACKOFF_CAP_SECONDS` or the interval,
    whichever is shorter, until a read succeeds (exponential backoff with a cap,
    as Kubernetes restarts a container: 10 s doubling to 300 s); the store
    records the next try (`retry`). A reader that declares its `dependency`
    also records `waiting`: since when, and the grace (`Dependency`, about 2.5x
    the dependency's measured start) measured from the dependency's OWN start,
    or from Mercury's start when that cannot be read, said so in
    `grace_from_basis`. Within the grace, `health_rows` says `waiting` and the
    consumer draws it under What was checked, never as a row and never as ok;
    past it, the row it is today. The retry is never scheduled past the grace's
    end, so the judgement at the end is a read's, not a guess. A read whose
    value carries one part a dependency did not answer (`NOT_ANSWERING`: the
    credential health's NetBox token) is backed off and waits the same way, its
    value stored. Known edge: a dependency answering after the last try inside
    the grace and before its end is a row for the length of the read at the end.

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


#: How many intervals may pass before a reader's value is stale: one late
#: read is not a stop. Stored with the value (`stale_after_seconds`), so the
#: page judges the same promise on its own clock.
STALE_AFTER_INTERVALS = 3


#: Rule 14's backoff (C2568): the first retry after a read found its dependency not
#: answering, doubled each retry, capped here or at the reader's interval, whichever is
#: shorter. Practice: Kubernetes' container restart backoff, 10 s doubling to 300 s. A
#: dependency that stays down is asked about 12 times an hour instead of once.
BACKOFF_FIRST_SECONDS = 15
BACKOFF_CAP_SECONDS = 300

#: The key a read's VALUE may carry (a list of `Dependency.key`) when one part of it found
#: that dependency not answering and the rest was read (rule 14).
NOT_ANSWERING = "not_answering"


@dataclass(frozen=True)
class Dependency:
    """A service a reader cannot read without (rule 14). Its grace is how long after its own
    start it is expected to be answering: about 2.5x its measured start, with the measurement
    in `grace_basis`."""

    key: str
    label: str
    start_grace_seconds: int
    grace_basis: str
    #: () -> epoch seconds of the dependency's own start, or None when it cannot be read.
    started_at: Callable = None
    #: Why its start cannot be read, said where the grace is measured from Mercury's instead.
    start_unreadable: str = ""


NETBOX = Dependency(
    key="netbox", label="NetBox", start_grace_seconds=120,
    # Measured read-only on the Mercury host (the 2026-10-09 boot; its containers' StartedAt and
    # the netbox container's log): the container started 03:21:00.9Z, granian listened at
    # 03:21:31.5Z (30.5 s), its four workers were up at 03:21:34.8Z (33.8 s), and the first
    # request was answered at 03:21:47.4Z: 46.5 s. 2.5x is 116 s; 120 s.
    grace_basis=("about 2.5x NetBox's measured start: 46.5 s from its container's start to "
                 "its first answered request (the Mercury host, 2026-10-09)"),
    start_unreadable=("NetBox's API reports no start time, and where NetBox runs (its "
                      "containers or its service) is not Mercury's to read"))


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
    stale_after_intervals: int = STALE_AFTER_INTERVALS
    window: str = field(default="")   # what time range the value covers (rule 6)
    announce_if: Callable = None      # (previous value, value) -> announce? (rule 9)
    announce_at_least_every: int = 0  # the keepalive that makes announce_if safe
    after_store: Callable = None      # run after each stored read, before the announcement
    #: P.8 step 5: the settings groups this reader's outside service is configured by (e.g.
    #: ``("grafana",)``). With them, the reader reads each distinct configuration across every
    #: network ONCE, through ``read_for(list_name)`` for a list that uses it, and stores each
    #: apart: Default's under the reader's own name (unchanged), another's as ``name@id``.
    per_group: tuple = ()
    read_for: Callable = None         # (list name) -> value; required with per_group
    #: Rule 14: the service whose start this reader waits out (a `Dependency`), if any.
    dependency: Dependency = None
    #: (reader, read_cached's answer, now) -> its liveness rows, in place of the job-health
    #: row rule 7 draws: a reader whose stopping is its own Needs attention row (self-healing's
    #: detection, C3330), each unit under `LIVE_UNIT_PREFIXES`.
    liveness: Callable = None
    #: A page where what this reader holds is drawn with its age: its rows' action opens it
    #: (C3330: the Logs pages say when the logs-tail's lines are held past its promise).
    remedy_href: str = ""


#: The units drawn live from `health_rows` (never from the job-health reader's stored copy).
LIVE_UNIT_PREFIXES = ("reader:", "self-healing:")


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
    if reader.announce_if is not None and not reader.announce_at_least_every:
        problems.append("it announces only on change with no keepalive, so its silence cannot "
                        "be told from its stopping (rule 9)")
    if reader.stale_after_intervals < 2:
        problems.append("stale after fewer than two intervals would call one slow read a stop")
    if reader.per_group and not callable(reader.read_for):
        problems.append("it reads per configuration (per_group) with no read_for(list_name)")
    dep = reader.dependency
    if dep is not None and (not isinstance(dep, Dependency) or dep.start_grace_seconds <= 0
                            or not (dep.grace_basis or "").strip()):
        problems.append("its dependency is not a Dependency with a positive start grace and "
                        "the measurement it comes from (rule 14)")
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
        # A RETIRED reader is out of the population even when something imported its module:
        # never started, never a job-health row.
        return [_REGISTRY[k] for k in sorted(_REGISTRY)
                if getattr(_REGISTRY[k].read, "__module__", "") not in RETIRED]


#: The modules that register a reader when imported. A reader module is
#: listed here, or it is not in the population job health watches.
DECLARED_MODULES: tuple = ("modules.readers.reachability",
                           "modules.readers.job_health_reader",
                           "modules.readers.grafana_alerts",
                           "modules.readers.grafana_dashboards",
                           "modules.readers.integration_health",
                           "modules.readers.ci_verdict",
                           "modules.readers.scheduled_jobs",
                           "modules.readers.ci_agreement",
                           "modules.readers.baseline_usability",
                           "modules.readers.intent_format",
                           "modules.readers.netbox_secrets",
                           "modules.readers.netbox_lag",
                           "modules.readers.remote_publication",
                           "modules.readers.app_pushed",
                           "modules.readers.adjacencies",
                           "modules.readers.adjacency_log",
                           "modules.readers.restarts",
                           "modules.readers.credential_health",
                           "modules.readers.coverage_reporting",
                           "modules.readers.platform_facts",
                           "modules.readers.records_check",
                           "modules.readers.rip",
                           "modules.readers.endpoints",
                           "modules.readers.topology_graph",
                           "modules.readers.logs_summary",
                           "modules.readers.logs_tail",
                           "modules.heal.detect_read",
                           "modules.readers.loki_labels",
                           "modules.readers.dhcp",
                           "modules.readers.ztp_discovery",
                           "modules.readers.host_key_windows",
                           "modules.readers.onboarding_progress",
                           "modules.readers.sdn_controllers",
                           "modules.readers.drained_state",
                           "modules.readers.read_account_coverage")

#: Readers switched OFF, each with why: not imported, never started, no job-health row, no
#: Needs attention source. Removed with their system (the operator decides when).
#: None now: Oxidized freshness, switched off here on 2026-10-08 (C555), was removed with its
#: reader in Phase 3; the drift check covers a change made outside Mercury.
RETIRED: dict = {}


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


# ---------------------------------------------------------------------------
# Rule 14: a dependency not answering yet
# ---------------------------------------------------------------------------

def _no_answer(exc) -> bool:
    """*exc* itself (not its causes) is connection-level: True, an answer of some kind: False,
    neither: None."""
    import socket
    import ssl

    import requests.exceptions as rx
    import urllib3.exceptions as ux

    # An answer, or a fault that is not the dependency starting: a TLS failure, a proxy's
    # refusal, an HTTP status, a name that does not resolve.
    answered = (ssl.SSLError, socket.gaierror, rx.SSLError, rx.ProxyError, rx.HTTPError,
                rx.InvalidURL, rx.ChunkedEncodingError, rx.ContentDecodingError, ux.SSLError,
                ux.ProxyError, ux.NameResolutionError)
    if isinstance(exc, answered):
        return False
    if isinstance(exc, rx.ConnectionError):
        # requests wraps urllib3's reason (MaxRetryError.reason) in args, not as a cause.
        reason = getattr(exc.args[0], "reason", None) if exc.args else None
        if reason is not None and _no_answer(reason) is False:
            return False
        return True
    if isinstance(exc, (rx.Timeout, ux.NewConnectionError, ux.ConnectTimeoutError,
                        ux.ReadTimeoutError, ux.ProtocolError)):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError)):
        # Refused, reset, aborted, a broken pipe, http.client's RemoteDisconnected, a socket
        # timeout: nothing answered.
        return True
    return None


def not_answering(exc) -> bool:
    """Rule 14: did *exc* happen because nothing answered (refused, reset, aborted, or timed
    out before any HTTP answer)? An HTTP error, a TLS failure, a name that does not resolve
    or a wrong answer is the dependency answering: False. Its explicit cause and its context
    are read too, so a wrapper's error still says what happened under it."""
    seen = 0
    while exc is not None and seen < 8:
        got = _no_answer(exc)
        if got is not None:
            return got
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
        seen += 1
    return False


_STARTED_AT = None
_IMPORTED_AT = time.time()


def mercury_started() -> float:
    """When this process's readers started (`start`), or when it imported this module where
    none did: the grace's start when a dependency's own cannot be read."""
    return _STARTED_AT if _STARTED_AT is not None else _IMPORTED_AT


def mark_started(at=None) -> None:
    """Record when this process's readers started (`start` calls it once); None returns the
    grace's start to the module's import. A test sets it and puts it back."""
    global _STARTED_AT
    _STARTED_AT = at


def _grace_from(dep: Dependency) -> tuple:
    """``(epoch, basis)``: the dependency's own start when it can be read, else Mercury's."""
    why = dep.start_unreadable or f"{dep.label}'s own start cannot be read"
    if dep.started_at is not None:
        try:
            at = dep.started_at()
        except Exception as exc:                        # noqa: BLE001 (said in the basis)
            at, why = None, f"{dep.label}'s start could not be read ({type(exc).__name__})"
        if at:
            return float(at), f"{dep.label}'s own start"
    return mercury_started(), f"Mercury's start, because {why}"


def waiting(doc: dict, now: float = None) -> dict:
    """Rule 14: the stored wait for a dependency, when the latest attempt found it not
    answering and its start grace has not passed (judged on *now*, so a reader that stops
    trying is a row once the grace ends); else None."""
    w = (doc or {}).get("waiting")
    if not isinstance(w, dict):
        return None
    until = _parse_iso(w.get("grace_until"))
    now = time.time() if now is None else now
    if until is None or now > until:
        return None
    return dict(w)


def waiting_words(w: dict) -> str:
    """How a wait is drawn under What was checked."""
    return (f"waiting for {w.get('label') or 'its dependency'} to answer (since "
            f"{w.get('since')}, grace until {w.get('grace_until')})")


def next_wait(reader: Reader, doc: dict) -> int:
    """Seconds the scheduler waits after a run that stored *doc*: its backoff when it found
    its dependency not answering (rule 14), else the interval."""
    retry = (doc or {}).get("retry") or {}
    got = retry.get("in_seconds")
    if isinstance(got, (int, float)) and 0 < got < reader.interval_seconds:
        return int(got)
    return reader.interval_seconds


#: The records database's store for the stored values (C1330): a document per reader's store,
#: read and written through the process's pool once moved (Settings › Installation ›
#: Connections, Record stores). On its files until then, as before.
VALUES_STORE = "reader_values"


def _on_database() -> bool:
    """Whether the stored values are on the records database now, read at each call so every
    process follows a move together. Raises when the settings cannot be read."""
    from modules import records_db

    return records_db.backend(VALUES_STORE) == records_db.POSTGRES


def _read_from_database(name: str) -> dict:
    """`read_cached`'s answer from the records database. A database that could not be asked is
    ``unanswered``: unreadable, and a run refuses to store over it (`_run_once`)."""
    from modules import records_docs
    from modules.filestore import StoreUnreadable

    try:
        doc = records_docs.load(VALUES_STORE, name, None)
    except StoreUnreadable as exc:
        cause = exc.__cause__
        if cause is None:
            return {"state": "unreadable", "doc": None,
                    "why": f"{name}'s stored value in the records database is not an object"}
        first = (str(cause).strip().splitlines() or [type(cause).__name__])[0]
        return {"state": "unreadable", "doc": None, "unanswered": True,
                "why": (f"the records database could not be asked for {name}'s stored value "
                        f"({type(cause).__name__}: {first})")}
    if doc is None:
        return {"state": "absent", "doc": None,
                "why": f"no reader has stored {name} in the records database"}
    return {"state": "ok", "doc": doc, "why": ""}


def read_cached(name: str) -> dict:
    """``{"state": "absent"|"unreadable"|"ok", "doc": ..., "why": ...}``.
    Absent and unreadable are different facts (rule 3's sibling). From the records database
    once the stored values are moved there (C1330), else the reader's file."""
    try:
        on_database = _on_database()
    except Exception as exc:                            # noqa: BLE001 (said, never a raise)
        return {"state": "unreadable", "doc": None, "unanswered": True,
                "why": (f"where {name}'s stored value is kept could not be read from the "
                        f"settings ({type(exc).__name__})")}
    if on_database:
        return _read_from_database(name)
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


_ANNOUNCE = {"sent": 0, "failed": 0, "last_error": "", "skipped_unchanged": 0}
_LAST_ANNOUNCED: dict = {}


def page_promise(reader: Reader) -> int:
    """How long a PAGE's copy of this reader's value stays current: 2.5
    keepalives for a reader that announces only on change, else the read
    cycle's own staleness."""
    if reader.announce_at_least_every:
        return int(reader.announce_at_least_every * 2.5)
    return reader.interval_seconds * reader.stale_after_intervals


def announce_health() -> dict:
    """Announcements sent and failed by THIS process (rule 9)."""
    return dict(_ANNOUNCE)


def announce_via_page(keys, name: str, ok: bool) -> None:
    """The app's announcer: the keys to every open page, by this reader."""
    from modules import invalidation
    invalidation.announce(keys, f"reader:{name}", ok)


RUNS_KEPT = 20
SCHEDULED = {"kind": "scheduled"}

#: The readers that may skip announcing an unchanged scheduled run (rule 9),
#: each with why no page draws what the skipped run would refresh. Every other
#: reader announces every completed run. `tests/test_reader_job.py` holds the
#: registered readers with `announce_if` equal to these names.
CHANGE_ONLY = {
    "reachability": ("it probes every 5 s, and its pages draw each device's state, never "
                     "the probe's time: a redraw of every device row each 5 s would change "
                     "nothing a person reads (its 60 s keepalive proves it alive)"),
    "grafana-dashboards": ("the Monitoring tab re-renders every chart on its announcement and "
                           "draws no read time of this reader: a redraw every 5 min would "
                           "reset every chart on an open page for nothing"),
    "coverage-reporting": ("it reads every 60 s and Coverage draws each cell's verdict; the "
                           "arrival ages are only on hover: a redraw of the whole grid every "
                           "minute would change nothing a person reads unless a verdict could "
                           "move (its 300 s keepalive proves it alive)"),
    "platform-facts": ("its value is what each device is, which changes with its software; "
                       "the device page draws the model and where it came from, never this "
                       "read's time, so announcing device_state every 10 min would redraw an "
                       "open page's history for nothing (its hourly keepalive proves it alive)"),
    "topology-graph": ("it reads every 60 s and Topology redraws the whole map on its "
                       "announcement, drawing the value's age only on hover: the brief "
                       "(NSOT_TOPOLOGY_BRIEF 1) announces only a change, so an unchanged "
                       "network redraws nothing (its 600 s keepalive proves it alive)"),
    "logs-summary": ("it reads every 300 s and Logs redraws its device table on its "
                     "announcement; the read's time is drawn only on hover: unchanged counts "
                     "redraw nothing (its 1800 s keepalive proves it alive)"),
    "logs-tail": ("it reads every 5 s and Logs redraws its lines on its announcement; the page "
                  "says it checks every 5 s and draws the newest line's time, the read's only on "
                  "hover: a window with nothing new redraws nothing (its 300 s keepalive proves "
                  "it alive). A device's Logs tab, its drift row and Syslog by device draw the "
                  "buffer's read time as the page's copy holds it, at most one keepalive old, "
                  "and redraw when a line or a heartbeat arrives (C3166)"),
    "heal-detect": ("it reads every 5 s for self-healing's detection, and no page draws its "
                    "lines: it announces when it holds lines (so its steps run), caught up, "
                    "fell behind or could not scan a span; its 300 s keepalive proves it alive "
                    "and its liveness is its own Needs attention row (C3330)"),
    "loki-labels": ("it reads every 300 s and the logs builder draws its choices from it, the "
                    "read's time beside them: unchanged labels redraw nothing (its 1800 s "
                    "keepalive proves it alive; C3166)"),
    "dhcp": ("it reads every 300 s and DHCP redraws its tabs on its announcement; the read's "
             "time is drawn only on hover: an unchanged Kea redraws nothing (its 1800 s "
             "keepalive proves it alive)"),
    "ztp-discovery": ("it reads every 30 s and Onboard devices › Discovered redraws on its "
                      "announcement; the page draws each device's last request, its age only "
                      "on hover: a range where nobody asked anew redraws nothing (its 600 s "
                      "keepalive proves it alive)"),
    "onboarding-progress": ("it reads every 10 s and a pending device's page and the In "
                            "progress chip redraw on its announcement; a probe's time is drawn "
                            "as an age, so a device whose stage and answer stand still redraws "
                            "nothing (its 600 s keepalive proves it alive)"),
    "drained": ("it reads every 60 s and the device header's badge and Devices redraw on its "
                "announcement; while the measurement is switched off (C552) its value never "
                "moves, and a verdict standing still redraws nothing a person reads (its 300 s "
                "keepalive proves it alive; the badge's hover names when it was measured)"),
}


#: Steps run after EVERY reader's store, each given the reader (C1192: Needs attention's record
#: sights its rows when a reader it draws finishes). Installed where the readers start
#: (`start`), so a process that runs no readers runs none of these.
_AFTER_ANY_STORE: list = []


def after_any_store(step, remove: bool = False) -> None:
    """Add *step*, called after each store with the reader and whether what a page draws
    moved (its `announce_if`, or True), or remove it."""
    if remove:
        while step in _AFTER_ANY_STORE:
            _AFTER_ANY_STORE.remove(step)
    elif step not in _AFTER_ANY_STORE:
        _AFTER_ANY_STORE.append(step)


def run_once(reader: Reader, announce=None, clock=time.time, trigger: dict = None) -> dict:
    """Read, store, announce. Returns the stored document.

    A read that raises is a failed ATTEMPT: recorded with its error, the last
    good value kept (rule 3). A store that cannot be written raises, because
    nothing else can record it; the stale row then says the reader stopped
    (rule 7). *trigger* is what caused this run (rule 13): the schedule when
    omitted.

    **One run per reader at a time, across processes** (CONCURRENCY_AUDIT R28): the
    scheduled loop, a run on request and the post-commit refresh could all run one reader
    at once, each reading before the store's lock, so a slower run that started first
    stored last over a fresher value, and two `app-pushed` runs fetched one checkout at
    once. A run now waits for the one in progress, so it reads after that one stored.

    While it holds the reader's run lock, the run is `in_progress` in this process (its
    start and cause), so a person's Run the check again is refused by name rather than
    queued behind it (modules/recheck.py)."""
    with _filestore.PathLock(store_path(reader.name) + ".run"):
        t = dict(trigger or SCHEDULED)
        # The wall clock, never *clock*: a test's clock counts its own calls.
        _IN_PROGRESS[reader.name] = {"since": time.time(), "kind": t.get("kind") or "",
                                     "by": t.get("by") or "", "run": t.get("run") or ""}
        try:
            if not reader.per_group:
                return _run_once(reader, announce, clock, trigger)
            # P.8 step 5: one run per distinct configuration. Each is a reader of its own in
            # the store (its last good value, its failing streak, its runs), so every rule
            # above holds per configuration; Default's keeps the reader's own name and is
            # returned.
            out = None
            for v in configuration_readers(reader):
                doc = _run_once(v, announce, clock, trigger)
                if v.name == reader.name:
                    out = doc
            return out
        finally:
            with _RUN_END_LOCK:
                ended = _IN_PROGRESS.pop(reader.name, None)
                steps = _AT_RUN_END.pop(reader.name, [])
            for step in steps:
                try:
                    step(dict(ended or {}))
                except Exception as exc:                # noqa: BLE001 (the run itself stands)
                    log.error("reader %s: a step waiting for its run to end failed: %s: %s",
                              reader.name, type(exc).__name__, exc)


#: reader name -> the run holding its run lock in THIS process now (`run_once`):
#: ``{"since", "kind", "by", "run"}``. Memory only: read by a press, never by a page.
_IN_PROGRESS: dict = {}

#: reader name -> the steps waiting for the run in progress now to end (`when_run_ends`).
#: Memory only; taken with the run's entry under one lock, so each step is called once.
_AT_RUN_END: dict = {}
_RUN_END_LOCK = threading.Lock()


def when_run_ends(name: str, step) -> dict:
    """Call *step* once the run of *name* in progress in this process now ends (stored or
    raised), on that run's thread, with a copy of its entry; a step that fails is logged.
    Returns the run waited on (a copy), or None when none is in progress, and *step* is then
    never called. A person's Run the check again that finds a run it did not start
    (modules/recheck.py) is told so when that run ends, rather than asking on a timer."""
    with _RUN_END_LOCK:
        got = _IN_PROGRESS.get(name)
        if not got:
            return None
        _AT_RUN_END.setdefault(name, []).append(step)
        return dict(got)


def in_progress(name: str) -> dict:
    """The run of *name* in progress in this process now (scheduled, on request or after an
    operation), or None. A copy; nothing waits on it."""
    got = _IN_PROGRESS.get(name)
    return dict(got) if got else None


def configuration_readers(reader: Reader) -> list:
    """*reader* once per distinct configuration of its groups (`integration_groups`): each a
    copy named for its store, reading through a list that uses it. A reader with no groups is
    itself."""
    import dataclasses

    from modules import integration_groups as IG

    if not reader.per_group:
        return [reader]
    out = []
    for g in IG.groups(tuple(reader.per_group)):
        if g["id"] == IG.DEFAULT_GROUP:
            # Default's configuration is the reader's own `read`, exactly as before P.8, so
            # a single-network installation reads what it always read.
            out.append(dataclasses.replace(reader, per_group=(), read_for=None))
            continue
        rep = g["list"]
        out.append(dataclasses.replace(
            reader, name=IG.store_name(reader.name, g["id"]),
            what=f"{reader.what} (the configuration of {', '.join(g['lists'])})",
            read=(lambda rep=rep: reader.read_for(rep)), per_group=(), read_for=None))
    return out


def store_for(name: str, list_name: str) -> tuple:
    """``(store, None)``: the store holding *name*'s value for the network *list_name* (its
    configuration's; a reader with no groups has one store for every network), or ``(None,
    refused)`` when the network has none, *refused* being what `read_cached_for` answers: a
    service declared not applicable (``not_applicable``) or not configured there
    (``not_configured``). One home for the store a network reads, for a read and for a run
    asked of that store (a heal's heartbeat, C3164)."""
    from modules import integration_groups as IG

    # Asked before the reader's module was imported, its groups are unknown, and Default's
    # store would answer for every network: so the declared modules are imported first.
    reader = _REGISTRY.get(name) or {r.name: r for r in readers()}.get(name)
    if reader is None or not reader.per_group:
        return name, None
    gid = IG.combined_id(tuple(reader.per_group), list_name)
    if gid is None:
        return None, {"state": "not_applicable", "doc": None,
                      "why": f"{list_name} declared {', '.join(reader.per_group)} not applicable"}
    missing = IG.unconfigured(tuple(reader.per_group), list_name)
    if missing:
        from modules.settings_scope import group_label

        labels = " and ".join(group_label(g) for g in missing)
        return None, {"state": "not_configured", "doc": None, "groups": missing,
                      "why": (f"{labels} {'is' if len(missing) == 1 else 'are'} not configured "
                              f"for {list_name}: nothing is set for it there, and it takes "
                              "nothing from Default, so there is nothing to read")}
    return IG.store_name(name, gid), None


def read_cached_for(name: str, list_name: str) -> dict:
    """*name*'s stored value for the network *list_name*: its configuration's store
    (`store_for`). A reader with no groups has one store for every network. A network that
    declared the service not applicable has none, and says so: ``{"state": "not_applicable",
    ...}``."""
    store, refused = store_for(name, list_name)
    return refused if store is None else read_cached(store)


def _record_backoff(doc: dict, before: dict, reader: Reader, started: float) -> None:
    """Rule 14, on *doc*: the next try (`retry`), and, for a reader that declares its
    dependency and found it not answering, the wait (`waiting`) with its grace."""
    streak = 0
    for run in reversed(doc["runs"]):
        if not run.get("no_answer"):
            break
        streak += 1
    delay = min(BACKOFF_FIRST_SECONDS * 2 ** min(max(streak - 1, 0), 16), BACKOFF_CAP_SECONDS,
                reader.interval_seconds)
    dep = reader.dependency
    if dep is not None and doc["runs"][-1].get("no_answer"):
        grace_from, basis = _grace_from(dep)
        until = grace_from + dep.start_grace_seconds
        prev = before.get("waiting") or {}
        doc["waiting"] = {
            "for": dep.key, "label": dep.label,
            "since": (prev.get("since") if prev.get("for") == dep.key and prev.get("since")
                      else _iso(started)),
            "grace_from": _iso(grace_from), "grace_from_basis": basis,
            "grace_seconds": dep.start_grace_seconds, "grace_basis": dep.grace_basis,
            "grace_until": _iso(until)}
        if started < until:
            # Never past the grace's end: the judgement there is a read's.
            delay = min(delay, max(1, int(until - started)))
    doc["retry"] = {"in_seconds": int(delay),
                    "why": (f"nothing answered {streak} read(s) running: retried after "
                            f"{BACKOFF_FIRST_SECONDS} s, doubling to "
                            f"{min(BACKOFF_CAP_SECONDS, reader.interval_seconds)} s, until a "
                            "read is answered (rule 14)")}


def _run_once(reader: Reader, announce, clock, trigger) -> dict:
    trigger = dict(trigger or SCHEDULED)
    # Asked for (a person's request, or a host job that finished): logged, and
    # announced even when the answer did not change, because something is
    # waiting on it. Every such run carries its run id.
    requested = bool(trigger.get("run"))
    started = clock()
    t0 = time.monotonic()
    value, error, no_answer = None, "", False
    try:
        value = reader.read()
        if not isinstance(value, dict):
            error = f"the read returned {type(value).__name__}, not a mapping"
    except Exception as exc:                            # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        no_answer = not_answering(exc)
    took = int((time.monotonic() - t0) * 1000)
    # Rule 14: did its dependency not answer, the whole read or one part of it?
    dep = reader.dependency
    dep_down = dep is not None and (
        no_answer if error else dep.key in ((value or {}).get(NOT_ANSWERING) or ()))
    backoff = no_answer or dep_down

    path = store_path(reader.name)
    # The lock stays on the file's path when the value is on the records database (C1330), as
    # every document store's owner keeps its own (records_docs), so runs stay one at a time.
    with _filestore.PathLock(path):
        prior = read_cached(reader.name)
        replaced = ""
        if prior["state"] == "unreadable" and prior.get("unanswered"):
            # Nothing could ask where the last good value is: storing now would replace it with
            # none, so this run's value is not stored (its failure is logged where a failed
            # file write is) and the last good one stands.
            raise _filestore.StoreUnreadable(f"reader {reader.name}: {prior['why']}: nothing "
                                             "was stored")
        on_database = _on_database()
        if prior["state"] == "unreadable":
            # Rule 10: a cache is replaced, and the replacement says so. On the records
            # database there is no file to keep aside; the row is replaced.
            if not on_database:
                _filestore.preserve_corrupt(path, prior["why"])
            replaced = prior["why"]
        before = prior["doc"] or {}
        previous_value = (before.get("last_good") or {}).get("value")
        doc = {
            "reader": reader.name,
            "what": reader.what,
            "endpoints": list(reader.endpoints),
            "window": reader.window,
            "interval_seconds": reader.interval_seconds,
            "interval_basis": reader.interval_basis,
            "stale_after_seconds": page_promise(reader),
            "last_attempt": {"at": _iso(started), "ok": not error, "took_ms": took,
                             "trigger": trigger,
                             **({"error": _redacted(error)} if error else {})},
            "last_good": before.get("last_good"),
            "failing_since": None,
            "runs": ((before.get("runs") or [])[-(RUNS_KEPT - 1):]
                     + [{"at": _iso(started), "ok": not error, "took_ms": took, "trigger": trigger,
                         **({"no_answer": True} if backoff else {})}]),
        }
        if backoff:
            _record_backoff(doc, before, reader, started)
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
        elif ((before.get("last_good") or {}).get("read_started") or 0) > started:
            # A value read AFTER this read began is already stored (a run in another
            # process, or one that did not wait): it is kept, never replaced by an older
            # one (R28). This attempt is still in `runs`.
            log.warning("reader %s: a value read later is already stored; this run's older "
                        "value is not stored over it", reader.name)
        else:
            doc["last_good"] = {"value": value, "value_at": _iso(started), "took_ms": took,
                                "trigger": trigger, "read_started": started}
        if on_database:
            from modules import records_docs

            # One transaction; raises naming why the database did not take it, as a file that
            # could not be written raises.
            records_docs.save(VALUES_STORE, reader.name, doc)
        else:
            _filestore.write_atomic(path, json.dumps(doc, indent=1, sort_keys=True))
    if requested:
        # Rule 13: "did my click run, and how long did it take" in the log too.
        log.info("reader %s: run %s on %s by %s took %d ms: %s", reader.name,
                 trigger.get("run", "?"), trigger.get("kind"),
                 trigger.get("by") or "nobody identified", took,
                 "ok" if not error else "failed, " + doc["last_attempt"]["error"])

    acted = None
    if reader.after_store is not None:
        # What acts on the value just stored (the Update page's wait for CI):
        # before the announcement, so a panel re-drawn by it sees the result.
        # A failure is logged and never stops the reader. A truthy answer
        # means it acted, which is announced like a changed value.
        try:
            acted = reader.after_store()
        except Exception as exc:                        # noqa: BLE001
            log.error("reader %s: its after-store step failed: %s: %s", reader.name,
                      type(exc).__name__, exc)
    # Did what a page draws move? A reader that announces only on change (rule 9: the 5 s
    # reachability probe, the 10 s onboarding progress) says so by its own `announce_if`;
    # any other reader's finish counts as a move, and so does a failed read.
    moved = True
    if not error and reader.announce_if is not None:
        try:
            moved = bool(reader.announce_if(previous_value, value)) or bool(acted)
        except Exception:                               # noqa: BLE001
            moved = True                                # when unsure, it moved
    for step in list(_AFTER_ANY_STORE):
        # Before the announcement too, so the record holds what the page will draw. A step
        # that fails is logged and never stops the reader.
        try:
            step(reader, moved)
        except Exception as exc:                        # noqa: BLE001
            log.error("reader %s: an after-any-store step failed: %s: %s", reader.name,
                      type(exc).__name__, exc)

    should = True
    if announce is not None and not error and reader.announce_if is not None and not requested:
        try:
            moved = bool(reader.announce_if(previous_value, value))
        except Exception:                               # noqa: BLE001
            moved = True                                # when unsure, announce
        due = started - _LAST_ANNOUNCED.get(reader.name, 0) >= reader.announce_at_least_every
        should = moved or due or bool(acted)
        if not should:
            _ANNOUNCE["skipped_unchanged"] += 1
    if announce is not None and should:
        _LAST_ANNOUNCED[reader.name] = started
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

def _each_configuration(population) -> list:
    """Every reader, a per-configuration one once per configuration (P.8 step 5), so each
    store has its own liveness row. When the configurations cannot be read (a list's settings
    store unreadable), Default's is kept and the failure is logged: liveness is never lost."""
    out = []
    for r in population:
        try:
            out.extend(configuration_readers(r))
        except Exception as exc:                        # noqa: BLE001
            log.error("reader %s: its configurations could not be listed (%s); only "
                      "Default's is watched", r.name, exc)
            out.append(r)
    return out


def _href(reader: Reader) -> dict:
    """The page a reader's row opens, when it names one (`remedy_href`)."""
    return {"href": reader.remedy_href} if reader.remedy_href else {}


def health_rows(now: float = None, population: list = None) -> list:
    """One job-health row per reader, decided from its store alone."""
    now = time.time() if now is None else now
    rows = []
    for r in _each_configuration(readers() if population is None else population):
        unit = f"reader:{r.name}"
        base = {"unit": unit, "what": r.what, "state": "ok",
                "max_age_minutes": (r.interval_seconds * r.stale_after_intervals) // 60}
        got = read_cached(r.name)
        if r.liveness is not None:
            # Its own rows, never this reader row (C3330: self-healing's detection).
            try:
                rows.extend(r.liveness(r, got, now))
            except Exception as exc:                    # noqa: BLE001 (said, never lost)
                rows.append({**base, "unit": f"self-healing:{r.name}", "state": "unknown",
                             "detail": (f"its liveness could not be judged: "
                                        f"{type(exc).__name__}: {exc}")})
            continue
        restarts = restart_row(r, now)
        if restarts is not None:
            rows.append({**base, **restarts})
            continue
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
                         "detail": (f"{got['why']}; nothing is stored until it can be asked"
                                    if got.get("unanswered") else
                                    f"{got['why']}; the next run replaces it")})
            continue
        doc = got["doc"]
        attempt = doc.get("last_attempt") or {}
        good = doc.get("last_good") or {}
        at = _parse_iso(attempt.get("at"))
        stale_after = r.interval_seconds * r.stale_after_intervals
        if at is None or now - at > stale_after:
            # `since` is epoch seconds, as every job-health row carries it
            # (Needs attention formats it); an ISO string here crashed the
            # page's source on the first stopped reader.
            since = at + stale_after if at is not None else None
            rows.append({**base, "state": "stale", "since": since,
                         "detail": (f"no read since {attempt.get('at', 'ever')} (it reads every "
                                    f"{r.interval_seconds} s; stale after {stale_after} s): the "
                                    "reader has stopped. What it last stored is from "
                                    f"{good.get('value_at', 'never')}"),
                         "action": {"label": "Read the app log for this reader; its thread "
                                             "has stopped, and a restart starts it again",
                                    **_href(r)}})
            continue
        w = waiting(doc, now) if not attempt.get("ok") else None
        if w:
            # Rule 14: inside its dependency's start grace, waiting: never failing, never ok.
            rows.append({**base, "state": "waiting", "since": _parse_iso(w.get("since")),
                         "headline": f"{unit} is {waiting_words(w)}", "waiting": w,
                         "detail": (f"its last read of {', '.join(doc.get('endpoints') or [])} "
                                    f"at {attempt.get('at')} found nothing answering: "
                                    f"{attempt.get('error', '?')}. The grace is "
                                    f"{w.get('grace_seconds')} s ({w.get('grace_basis')}), from "
                                    f"{w.get('grace_from_basis')}; it is retried in "
                                    f"{(doc.get('retry') or {}).get('in_seconds', '?')} s, and "
                                    "past the grace it is a row. "
                                    + (f"The value shown is from {good['value_at']}"
                                       if good else "It has never read a value"))})
            continue
        if not attempt.get("ok"):
            state = "failing" if good else "never_succeeded"
            rows.append({**base, "state": state, "since": _parse_iso(doc.get("failing_since")),
                         "detail": (f"its last read of {', '.join(doc.get('endpoints') or [])} "
                                    f"at {attempt.get('at')} failed: {attempt.get('error', '?')}. "
                                    + (f"The value shown is from {good['value_at']}"
                                       if good else "It has never read a value")),
                         **({"action": {"label": r.remedy, **_href(r)}} if r.remedy else {})})
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


def _loop(reader: Reader, announce, stop=None) -> None:
    """*stop* is the event that ends it and is waited on between runs (the module's own)."""
    stop = _stop if stop is None else stop
    while not stop.is_set():
        doc = None
        try:
            doc = run_once(reader, announce=announce)
        except Exception as exc:                        # noqa: BLE001
            # The store could not be written: logged here, and the stale row
            # names it at the next health read, from any process.
            log.error("reader %s: its result could not be stored: %s", reader.name, exc)
        # Rule 14: a read that found nothing answering is tried again on its backoff.
        stop.wait(next_wait(reader, doc))


# ---------------------------------------------------------------------------
# The supervisor: a reader thread that STOPS is started again by Mercury itself (C3330)
# ---------------------------------------------------------------------------
#
# A read that keeps failing is a live thread, and its job-health row says so (rule 7's
# `failing`). A thread can still die: anything `_loop` does not catch (a BaseException that is
# not an Exception, such as SystemExit raised in a read, or a fault in the loop itself) ends
# it, and before this the reader's row read `stale` until a person restarted the app. The
# supervisor looks at this process's own reader threads every `SUPERVISE_EVERY_SECONDS` and
# starts a dead one again, on a backoff, recording each restart in History ("Mercury's
# self-healing", the reader, why, the exception's type). It restarts only the threads in
# `_threads` (this process's, started by `start`): never by pattern, never a process, never
# anything outside Mercury.

#: How often the threads are looked at: the shortest reader interval (5 s, logs-tail and
#: detection), so a dead thread is started again within one of its own intervals. A look is
#: one `is_alive()` per reader.
SUPERVISE_EVERY_SECONDS = 5
#: The restart backoff: the first restart at the next look, then rule 14's backoff (15 s
#: doubling to 300 s, as Kubernetes restarts a container), so a thread that dies at once is
#: started about 12 times an hour, never in a loop.
RESTART_FIRST_SECONDS = BACKOFF_FIRST_SECONDS
RESTART_CAP_SECONDS = BACKOFF_CAP_SECONDS
#: A person's row only when it keeps stopping: this many restarts inside the window. One or
#: two restarts in an hour are Mercury's to handle and History's to show; three is a thread
#: that dies again after each restart (with the backoff, three within about 45 s of the first).
RESTARTS_BEFORE_ROW = 3
RESTART_WINDOW_SECONDS = 3600
#: The restarts kept, newest last (one line each): every reader's restarts over days at most.
RESTARTS_KEPT = 500
RESTARTS_LOG = "reader_restarts.jsonl"
#: Who a restart is recorded as (History's who).
RESTART_DOER = "Mercury's self-healing"

#: reader name -> what ended its thread: ``{"at", "type", "error"}`` (memory; the restart's why).
_DEATHS: dict = {}
_supervisor = {"thread": None}
_RESTART_MU = threading.Lock()


def _thread_body(reader: Reader, announce) -> None:
    """A reader's thread: its loop, and what ended it when anything escapes (recorded for the
    supervisor's restart, then the thread ends as it would have)."""
    try:
        _loop(reader, announce)
    except BaseException as exc:                        # noqa: BLE001 (recorded, then ends)
        _DEATHS[reader.name] = {"at": time.time(), "type": type(exc).__name__,
                                "error": _redacted(str(exc))[:300]}
        log.error("reader %s: its thread stopped: %s: %s", reader.name, type(exc).__name__, exc)


def _spawn(reader: Reader, announce) -> threading.Thread:
    t = threading.Thread(target=_thread_body, args=(reader, announce), daemon=True,
                         name=f"reader:{reader.name}")
    _threads[reader.name] = t
    t.start()
    return t


def restarts_path() -> str:
    return os.path.join(_config.DATA_DIR, RESTARTS_LOG)


def restarts(since: float = None) -> dict:
    """``{"rows", "error"}``: the restarts recorded, oldest first (each ``{"at", "reader",
    "why", "type", "who", "attempt"}``), from *since* when given. An unreadable record is its
    error, never no restarts."""
    path = restarts_path()
    if not os.path.exists(path):
        return {"rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError) as exc:
        return {"rows": [], "error": f"{RESTARTS_LOG} could not be read ({type(exc).__name__})"}
    if since is not None:
        rows = [r for r in rows if float(r.get("at_ts") or 0) >= since]
    return {"rows": rows, "error": ""}


def _record_restart(row: dict) -> None:
    """Append one restart, keeping the newest `RESTARTS_KEPT`, under the record's lock."""
    path = restarts_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _filestore.PathLock(path):
        got = restarts()
        rows = (got["rows"] if not got["error"] else []) + [row]
        _filestore.write_atomic(path, "".join(json.dumps(r, sort_keys=True) + "\n"
                                              for r in rows[-RESTARTS_KEPT:]))


def _restart_delay(recent: int) -> int:
    """Seconds after the last restart before the next: none for the first in the window."""
    if recent <= 0:
        return 0
    return min(RESTART_FIRST_SECONDS * 2 ** min(recent - 1, 16), RESTART_CAP_SECONDS)


def supervise_once(now: float = None, announce=None, spawn=None) -> list:
    """Look at this process's reader threads once; start each dead one again when its backoff
    allows, recording why. Returns the names restarted. Never raises."""
    now = time.time() if now is None else now
    spawn = spawn or _spawn
    if _stop.is_set():
        return []
    out = []
    with _RESTART_MU:
        # A thread that ran and ended (its ident set): never one that was never started.
        dead = [n for n, t in list(_threads.items())
                if isinstance(t, threading.Thread) and t.ident is not None and not t.is_alive()]
        if not dead:
            return []
        by_name = {r.name: r for r in readers()}
        got = restarts(since=now - RESTART_WINDOW_SECONDS)
        for name in dead:
            reader = by_name.get(name)
            if reader is None:
                continue                                # unregistered since: not Mercury's now
            mine = [r for r in got["rows"] if r.get("reader") == name]
            last = max((float(r.get("at_ts") or 0) for r in mine), default=None)
            if last is not None and now - last < _restart_delay(len(mine)):
                continue
            death = _DEATHS.pop(name, None) or {}
            why = (f"its thread stopped: {death['type']}: {death['error']}" if death else
                   "its thread was found stopped, with no exception recorded")
            row = {"at": _iso(now), "at_ts": now, "reader": name, "why": why,
                   "type": death.get("type", ""), "who": RESTART_DOER,
                   "attempt": len(mine) + 1, "pid": os.getpid()}
            try:
                _record_restart(row)
            except Exception as exc:                    # noqa: BLE001 (restarted all the same)
                log.error("reader %s: its restart could not be recorded: %s", name, exc)
            try:
                spawn(reader, announce)
            except Exception as exc:                    # noqa: BLE001 (tried again next look)
                log.error("reader %s: its thread could not be started again: %s", name, exc)
                continue
            log.warning("reader %s: started again by Mercury (%s; restart %d in the last %d s)",
                        name, why, len(mine) + 1, RESTART_WINDOW_SECONDS)
            out.append(name)
    return out


def restart_row(reader: Reader, now: float):
    """The reader's row when its thread keeps stopping (`RESTARTS_BEFORE_ROW` restarts within
    `RESTART_WINDOW_SECONDS`), else None. Read from the record, so any process judges it."""
    got = restarts(since=now - RESTART_WINDOW_SECONDS)
    mine = [r for r in got["rows"] if r.get("reader") == reader.name]
    if len(mine) < RESTARTS_BEFORE_ROW:
        return None
    last = mine[-1]
    return {"state": "restarting", "since": float(mine[0].get("at_ts") or now),
            "detail": (f"its thread stopped and Mercury started it again {len(mine)} times "
                       f"in the last {RESTART_WINDOW_SECONDS // 60} minutes (a row from "
                       f"{RESTARTS_BEFORE_ROW}); the last at {last.get('at')}: {last.get('why')}. "
                       "History › Reader threads restarted holds each. Clears when it has "
                       f"run {RESTART_WINDOW_SECONDS // 60} minutes with fewer than "
                       f"{RESTARTS_BEFORE_ROW} restarts"),
            "action": {"label": ("Read the app log for the exception that stops this reader's "
                                 "thread: Mercury restarts it, and the cause is in its read"),
                       "href": "/v2/history?kind=reader_restarts"}}


def _supervise_loop(announce) -> None:
    while not _stop.wait(SUPERVISE_EVERY_SECONDS):
        try:
            supervise_once(announce=announce)
        except Exception as exc:                        # noqa: BLE001 (the next look tries)
            log.error("readers: the supervisor's look failed: %s: %s", type(exc).__name__, exc)


def start(announce=None) -> list:
    """Start every registered reader's thread once. Returns their names.

    The integration clients are imported HERE, in the starting thread, before any reader runs
    (C836): each reader imports what it needs inside its read, so after a restart the readers'
    threads make their first imports of `modules.integrations` and its submodules together,
    and the DHCP reader's read failed with `_DeadlockError` on `modules.integrations.loki` (the
    operator, 2026-10-15, after the 18:40 UTC restart; not reproduced by two threads alone).
    A package imported whole before the threads start is one no thread has to initialise."""
    import modules.integrations  # noqa: F401 (imported for its effect: every client loaded)

    # C1192's record of Needs attention's rows is sighted by the background store's passes
    # (`attention_store._sight`, C3182), never by computing every source after a reader.
    # Board H, H2: the heal triggers ride on the readers' stores ("check this device now").
    from modules.heal import triggers as heal_triggers
    heal_triggers.install()
    # Board H, H19: the flap record (guard 13e) rides on self-healing's own syslog read.
    from modules.heal import flaps as heal_flaps
    heal_flaps.install()
    if _STARTED_AT is None:
        # Rule 14: Mercury's start, the grace's start where a dependency's own cannot be read.
        mark_started(time.time())
    _stop.clear()
    started = []
    for r in readers():
        t = _threads.get(r.name)
        if t is not None and t.is_alive():
            continue
        _spawn(r, announce)
        started.append(r.name)
    if started:
        log.info("readers started: %s", ", ".join(started))
    sup = _supervisor["thread"]
    if sup is None or not sup.is_alive():
        # C3330: a reader thread that stops is started again by Mercury, on a backoff.
        sup = threading.Thread(target=_supervise_loop, args=(announce,), daemon=True,
                               name="readers:supervisor")
        _supervisor["thread"] = sup
        sup.start()
    return started


def running(name: str) -> bool:
    """Is *name*'s reader thread alive in THIS process? The app starts them;
    a CLI, a test or another process does not, and asks nothing on demand."""
    t = _threads.get(name)
    return t is not None and t.is_alive()


# ---------------------------------------------------------------------------
# A run a person asked for (rule 13)
# ---------------------------------------------------------------------------

_REQUESTS: dict = {}
_REQUESTS_LOCK = threading.Lock()


def request_run(reader: Reader, by: str, announce=None, clock=time.time,
                kind: str = "request", on_done=None) -> dict:
    """Run *reader* once now, on its own thread, for *by*. One at a time per
    reader: a second request while one runs gets that run back
    (``started: False``), so its page waits for the same answer. *kind* is the
    cause recorded (rule 13): ``request`` for a person, ``job_finished`` for a
    host job that just ended (*by* naming the unit). *on_done*, when given, is called
    once the run is done (stored and announced, or raised) with a copy of its entry and
    ``raised``, on the run's own thread; its failure is logged and changes nothing."""
    import uuid

    with _REQUESTS_LOCK:
        current = _REQUESTS.get(reader.name)
        if current is not None and not current["done"]:
            return {**current, "started": False}
        entry = {"run": uuid.uuid4().hex[:12], "by": by or "", "since": clock(), "done": False}
        _REQUESTS[reader.name] = entry

    # The bound the page is waiting with, fixed BEFORE the run (the run itself
    # moves it): a run past it was drawn as "no answer" to the person who
    # asked, so the log says so (the operator, 2026-10-01: "No answer after
    # 12 s", and nothing in the app log).
    bound = answer_bound(reader.name).get("seconds")

    def _go():
        t0 = time.monotonic()
        raised = False
        try:
            run_once(reader, announce=announce, clock=clock,
                     trigger={"kind": kind, "by": entry["by"], "run": entry["run"]})
        except Exception:                               # noqa: BLE001
            raised = True
            log.exception("reader %s: run %s on request by %s raised; nothing was stored",
                          reader.name, entry["run"], entry["by"] or "nobody identified")
        finally:
            took = time.monotonic() - t0
            if bound and took > bound:
                log.warning("reader %s: run %s on request by %s answered after %.1f s, past the "
                            "%d s its page waits: the page said there was no answer",
                            reader.name, entry["run"], entry["by"] or "nobody identified",
                            took, bound)
            # Done last (C1758): a run is done once its record of lateness is written, so
            # whoever waits on `done` reads that record too (CI #1190 read it in between).
            entry["done"] = True
            if on_done is not None:
                try:
                    on_done(dict(entry, raised=raised))
                except Exception as exc:                # noqa: BLE001
                    log.error("reader %s: run %s's step after it ended failed: %s: %s",
                              reader.name, entry["run"], type(exc).__name__, exc)

    threading.Thread(target=_go, name=f"request:{reader.name}", daemon=True).start()
    return {**entry, "started": True}


def last_request(name: str) -> dict:
    """The latest run on request of *name* in this process, done or not (a copy), or None:
    memory only, so a page drawing a press's state reads no store."""
    entry = _REQUESTS.get(name)
    return dict(entry) if entry is not None else None


def request_in_flight(name: str) -> dict:
    """The run on request still owed an answer, or None. Owed until the store
    holds it: its thread marks it done only after announcing, and a page
    re-fetched on that announcement must already read it as answered."""
    entry = _REQUESTS.get(name)
    if entry is None or entry["done"]:
        return None
    doc = read_cached(name).get("doc") or {}
    if ((doc.get("last_attempt") or {}).get("trigger") or {}).get("run") == entry["run"]:
        return None
    return dict(entry)


def answer_bound(name: str) -> dict:
    """How long a page waits for an answer on request before saying it is
    late: 2.5x the slowest run this reader recorded (bounds from measurement).
    ``seconds`` is None when no run has been timed here, and ``basis`` says so."""
    doc = read_cached(name).get("doc") or {}
    took = [r.get("took_ms") for r in (doc.get("runs") or []) if isinstance(r.get("took_ms"), int)]
    if not took and isinstance((doc.get("last_attempt") or {}).get("took_ms"), int):
        took = [doc["last_attempt"]["took_ms"]]
    if not took:
        return {"seconds": None, "basis": "no run of this check has been timed here yet"}
    slowest = max(took)
    return {"seconds": max(1, -(-int(slowest * 2.5) // 1000)),
            "basis": (f"2.5x the slowest of its last {len(took)} run(s), "
                      f"{slowest / 1000:.1f} s")}


def trigger_words(trigger: dict, viewer: str = "") -> str:
    """What caused a stored answer, in words, for the person *viewer*."""
    trigger = trigger or {}
    kind = trigger.get("kind")
    if kind == "request":
        by = trigger.get("by") or ""
        if by and by == viewer:
            return "checked on your request"
        return f"checked on request by {by}" if by else "checked on request by somebody not identified"
    if kind == "scheduled":
        return "the scheduled check"
    if kind == "after_commit":
        return "re-read after a commit"
    if kind == "job_finished":
        return f"re-read when {trigger.get('by') or 'a host job'} finished"
    if kind == "after_operation":
        # C539: an operation that changes this reader's answer re-reads it at once.
        return f"re-read at once after {trigger.get('by') or 'an operation'}"
    return "what started it was not recorded" if not kind else f"started by {kind}"


def stop() -> None:
    _stop.set()
