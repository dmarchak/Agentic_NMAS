"""Needs attention: one list, every source, one row shape (Stage 7.2).

NSOT_STAGE7_PLAN section 1a, and NSOT_PLAN 8.6 for what Stage 8 needs left
room for. "Approvals", "Jobs" and "Drift" as places would each be one source
of needs attention, which is the four-places failure the operator named, so
each is a SOURCE here and this module is the one place that joins them.

THE ROW. Every row, from every source, has the same parts: WHAT is wrong,
which DEVICES (or none: a job is not a device), SINCE when (None when the
source does not record it, drawn as "not recorded", never as now), the CAUSE
in the source's own words, the OPERANDS it compared, the ONE ACTION that
addresses it, a LEVEL (decided here, only drawn in the browser), and an empty
TRIAGE slot that Stage 8's report fills. `row()` is the only constructor and
refuses a row with no cause or no action, as `preview_confirm` refuses a
silent part: a row that says something is wrong and not why, or not what to
do, is the complaint every other panel in this tool was rebuilt to stop
making. An action a source does not record is stated as not known
(``known: False``), never invented.

THE SOURCE. Each source is read into one result: its state (``read`` or
``unreadable``), WHEN it was read, how long the read took, and WHAT it looked
at. A source that could not be read is a ROW, never an absence, because "the
check could not run" and "the check found nothing" otherwise print the same
empty list. An empty page therefore names every source and its time: an empty
list must say what was looked at.

Nothing here does per-device work per request (section 0a). job health is
read live because its cost is per JOB, not per device; its read time is
reported beside it, so the host's measurement decides whether it moves to a
cache, rather than a guess.
"""

import logging
import time

log = logging.getLogger(__name__)

#: Worst first. The browser draws the level; it never decides it.
LEVELS = ("danger", "warning", "unknown")


class RowRefused(ValueError):
    """A row missing a part it must have."""


def _iso(ts) -> str:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def row(*, source: str, key: str, what: str, cause: str, action: dict,
        level: str, devices=(), since=None, operands: dict = None,
        attach_to: str = None) -> dict:
    """The only constructor for a Needs attention row.

    *attach_to* names another row's id this one is ABOUT (a queued drift
    item is about its device's drift row). The page merges it into that row
    instead of drawing a second row about one event; it stands alone only
    when that row is absent."""
    missing = [n for n, v in (("source", source), ("key", key), ("what", what),
                              ("cause", cause)) if not str(v or "").strip()]
    if not isinstance(action, dict) or not str(action.get("label") or "").strip():
        missing.append("action")
    if missing:
        raise RowRefused(f"a Needs attention row without {', '.join(missing)} "
                         "says something is wrong and not why or what to do")
    if level not in LEVELS:
        raise RowRefused(f"level {level!r} is not one of {LEVELS}")
    return {"id": f"{source}:{key}", "source": source, "what": what,
            "devices": [d for d in devices if d], "since": _iso(since),
            "cause": cause, "operands": dict(operands or {}),
            "action": {"known": True, **action}, "level": level,
            "attach_to": attach_to, "attached": [],
            # Stage 8 attaches its triage HERE, on the row, never as a row of
            # its own (NSOT_PLAN 8.6): two rows about one event is the
            # three-reports problem restated on the page.
            "triage": None}


def source_result(source: str, label: str, *, read_at: float, took_ms: int,
                  rows=None, checked: str = "", error: str = "",
                  value_at: float = None, stale_after_seconds: int = None,
                  reader: str = None, detail: str = "") -> dict:
    """One source, read. *error* makes the source a row of its own.

    *read_at* is when this request read the source; *value_at* is the time of
    the VALUE it shows (section 1a), which for a stored result (the last drift
    run) is earlier, and for a live read (job health) is the same. Collapsing
    them would draw a day-old drift run as read "just now".

    *stale_after_seconds* is how long the value stays current, by the
    source's own promise (a reader's interval times its staleness factor, a
    drift run's interval times two). The PAGE judges age against it on its
    own clock (the live-data contract, 7.2 step 13), so a stored value whose
    producer has stopped is drawn stale without another request. None means
    the value was read for this request, and its freshness is the panel's.

    *reader* names the reader job behind a stored value, so the page can tell
    that job health's row for a stopped reader already covers a stale source
    and not draw the same fact twice.

    *checked* says what was FOUND, for a person; *detail* is the debugger's
    part (endpoints, read costs), drawn one level down, on hover (the
    operator's presentation rule, 2026-09-28)."""
    if error:
        # Kept where it outlives the row (the operator, 2026-09-29): a transient
        # "could not be read: Approvals" cleared on the next read, and nothing
        # anywhere said which read failed or why.
        log.warning("attention: %s could not be read: %s", label, error)
        return {"source": source, "label": label, "state": "unreadable",
                "read_at": _iso(read_at), "value_at": None, "took_ms": took_ms,
                "checked": "nothing: the read failed",
                "rows": [row(source=source, key="unreadable", level="unknown",
                             what=f"{label} could not be read",
                             cause=(f"{error}. This is not the same as nothing needing "
                                    "attention: whatever this source would show is "
                                    "unknown until it can be read"),
                             action={"label": "Find why the source cannot be read; "
                                              "the cause above is all that is known",
                                     "known": False})]}
    if not checked:
        raise RowRefused(f"source {source!r} read without saying what it looked at: "
                         "an empty result must say what was checked")
    return {"source": source, "label": label, "state": "read",
            "read_at": _iso(read_at),
            "value_at": _iso(read_at if value_at is None else value_at),
            "stale_after_seconds": stale_after_seconds, "reader": reader, "detail": detail,
            "took_ms": took_ms, "checked": checked, "rows": list(rows or [])}


# ---------------------------------------------------------------------------
# Source: job health (the first source; C54's rows already had the shape)
# ---------------------------------------------------------------------------

#: How each job-health state reads as WHAT is wrong, and how loud it is.
_JOB_STATES = {
    "failing": ("is failing", "danger"),
    "never_succeeded": ("has never succeeded", "danger"),
    "not_installed": ("is not installed", "danger"),
    "stale": ("has not succeeded recently", "warning"),
    "unknown": ("could not be checked", "unknown"),
    "unset_guard": ("is an empty setting that switches off a guard", "warning"),
    "contradiction": ("is declared not applicable and is also set", "warning"),
    "not_safe_to_reboot": ("would not survive a reboot", "danger"),
    "not_recorded": ("was rotated and not recorded", "danger"),
    "revert_failed": ("failed a rotation and its revert", "danger"),
    "neither_accepted": ("accepts neither its staged nor its recorded credential", "danger"),
    "at_budget": ("has no SSH session left for the next operation", "warning"),
    "leaked": ("holds an operation's SSH session past ten minutes", "warning"),
    "mixed_version": ("is running a different commit from its checkout", "danger"),
    "socket_down": ("is not listening", "danger"),
    "mismatch": ("does not match what was declared", "warning"),
    "not_run": ("has never run on this host", "warning"),
    "not_monitored": ("is not configured for an integration the network uses", "warning"),
    "breakglass_stale": ("is not recoverable from the break-glass record: it holds an "
                         "older credential", "danger"),
    # The Update button's root-owned updater (docs/UPDATE.md).
    "writable": ("is run as root and writable by someone else", "danger"),
    "path_inactive": ("is not watching for update requests", "danger"),
    "differs": ("differs from this release's copy", "warning"),
}


def _job_action(job: dict) -> dict:
    """The ONE action for a job-health row, where the source records one."""
    from modules import job_health as J

    # The row's OWN action first (C164): the builder that wrote the remedy
    # into the detail is the one place that knows it, and names it as a field.
    if isinstance(job.get("action"), dict) and job["action"].get("label"):
        return dict(job["action"])
    systemd_units = {j["unit"] for j in J.JOBS}
    unit, state = job.get("unit", ""), job.get("state", "")
    if unit in systemd_units:
        if state == "not_installed":
            return {"label": "Install and enable the unit on the host",
                    "reference": "docs/DEPLOY_LINUX.md"}
        return {"label": "Read the job's own output on the host",
                "command": f"journalctl -u {unit}.service -n 50 --no-pager"}
    # A row with no action of its own is a state with no remedy to name (an
    # `unknown`: the check could not ask), and it says so rather than
    # inventing one.
    return {"label": "No remedy is recorded for this state: the cause above is the "
                     "whole of what is known", "known": False}


JOB_HEALTH_READER = "job-health"


def job_health_source(health=None, now=None, cached=None, readers_now=None) -> dict:
    """Every job-health row that is not ok, as a Needs attention row.

    By default from the job-health READER's stored value, never from systemd
    (rule 1 of modules/reader_job.py): read live, it was 9.8 s of a 10 s
    page (measured on the host, 2026-09-28). *health* is a live read for a
    caller that has one (the tests; `/jobs/health` stays live by design).

    The readers' OWN liveness is judged now, from their stores (*readers_now*,
    a file read each), never taken from the cached value: a stopped
    job-health reader would otherwise report itself ok for ever."""
    from modules import job_health as J
    from modules import reader_job

    started = time.time()
    value_at = None
    if health is not None:
        try:
            h = health()
            jobs = list(h["jobs"])
        except Exception as exc:                   # noqa: BLE001
            log.error("attention: job health could not be read: %s", exc)
            return source_result("job_health", "Job health", read_at=started,
                                 took_ms=int((time.time() - started) * 1000),
                                 error=f"it raised {type(exc).__name__}: {exc}")
        where, promise = "read now", None
    else:
        got = reader_job.read_cached(JOB_HEALTH_READER) if cached is None else cached
        doc = got.get("doc") or {}
        good = doc.get("last_good") or {}
        took = int((time.time() - started) * 1000)
        if got["state"] != "ok" or not good:
            # Never a "nothing needs attention": no value is not an empty value.
            why = (got.get("why") if got["state"] != "ok" else
                   "the job-health reader has never stored a value; its last attempt: "
                   + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
            return source_result("job_health", "Job health", read_at=started, took_ms=took,
                                 error=f"not read yet: {why} (it runs in the app, every "
                                       f"{doc.get('interval_seconds') or 'few'} s)")
        try:
            jobs = [j for j in good["value"]["health"]["jobs"]
                    if not str(j.get("unit", "")).startswith("reader:")]
        except (KeyError, TypeError) as exc:
            return source_result("job_health", "Job health", read_at=started, took_ms=took,
                                 error=f"the stored value has no job rows ({type(exc).__name__})")
        value_at = reader_job._parse_iso(good.get("value_at"))
        promise = doc.get("stale_after_seconds")
        where = f"stored by the reader, read in {good.get('took_ms', '?')} ms"
        try:
            live = (reader_job.health_rows() if readers_now is None else list(readers_now))
        except Exception as exc:                   # noqa: BLE001
            live = [{"unit": "reader:*", "what": "the reader jobs' liveness", "state": "unknown",
                     "detail": f"the readers could not be judged: {type(exc).__name__}: {exc}"}]
        jobs += live
    took = int((time.time() - started) * 1000)
    rows = []
    for job in jobs:
        state = job.get("state", "")
        if state in J.OK_STATES:
            continue
        # An unmapped state is drawn LOUD with its own name: a state added
        # to job_health later must not arrive here as something quieter.
        words, level = _JOB_STATES.get(state, (f"reads {state}", "danger"))
        device = job.get("device") or job.get("address")
        rows.append(row(
            source="job_health", key=job.get("unit", "?"),
            # A row may name its own headline, in the reader's words ("r6 is not
            # monitored by SNMP"); otherwise the unit and its state's words.
            what=job.get("headline") or f"{job.get('unit', '?')} {words}",
            devices=[device] if device else [],
            since=job.get("since"),
            cause=job.get("detail") or f"state {state}, with no detail recorded",
            operands={"job": job.get("what", ""), "state": state},
            action=_job_action(job), level=level))
    n_ok = len(jobs) - len(rows)
    return source_result("job_health", "Job health", read_at=started, took_ms=took,
                         rows=rows, value_at=value_at, stale_after_seconds=promise,
                         reader=JOB_HEALTH_READER if promise else None, detail=where,
                         checked=f"{len(jobs)} job-health row(s), {n_ok} ok")


# ---------------------------------------------------------------------------
# Source: drift, with coverage (C96: the checker ran, found drift, and the
# panel drew none of it)
# ---------------------------------------------------------------------------

#: A stored run older than this many intervals is itself a row: the value on
#: the page is from a run that should have been superseded.
DRIFT_STALE_INTERVALS = 2

#: A drifted device's action when nothing is queued for it: both remedies
#: are on its Device page (7.1 steps 4 and 5). A queued drift item, when
#: there is one, attaches and its action replaces this.
_DRIFT_ACTION = {"label": "From its Device page: Capture the running config as the "
                          "golden, or Restore from the golden"}


def drift_source(status=None, now=None) -> dict:
    """The LAST drift run for the list on screen, from its stored record
    (section 0a: nothing re-checks a device to draw this page). Every device
    the run did not clear is a row, and so is the checker's own state: off,
    never run, a failed run, or a stored run too old to describe the network
    now."""
    from modules import drift_check as D

    started = time.time()
    now = now or started
    try:
        st = status() if status else D.get_checker().status()
        interval = D._get_interval()
    except Exception as exc:                       # noqa: BLE001
        log.error("attention: drift status could not be read: %s", exc)
        return source_result("drift", "Drift", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    lst = st.get("list") or "?"
    last, last_ts = st.get("last_run"), st.get("last_ts") or None
    rows = []

    def add(key, what, cause, action, level, devices=(), since=None, operands=None):
        rows.append(row(source="drift", key=f"{lst}:{key}", what=what, cause=cause,
                        action=action, level=level, devices=devices, since=since,
                        operands={"list": lst, **(operands or {})}))

    if st.get("disabled"):
        by = st.get("disabled_by") or "nobody recorded"
        add("disabled", f"Drift checking is switched off for {lst}",
            f"switched off by {by}; nothing compares the devices with their "
            "goldens until it is switched back on",
            {"label": "Switch drift checking back on in the Drift panel"},
            "warning", since=_ts(st.get("disabled_at")))
    if not last:
        add("never", f"Drift has never been checked for {lst}",
            "no drift run is recorded for this list, so whether any device has "
            "drifted is unknown",
            {"label": "Run a drift check from the Drift panel"}, "unknown")
        return source_result("drift", "Drift", read_at=started, took_ms=took, rows=rows,
                             checked=f"list {lst}: no drift run recorded")
    if last.get("ok") is False:
        add("failed", f"The last drift check for {lst} failed",
            last.get("summary") or last.get("error") or "no reason recorded",
            {"label": "Run a drift check from the Drift panel and read its reason"},
            "unknown", since=last_ts)
    elif last_ts and now - last_ts > DRIFT_STALE_INTERVALS * interval:
        add("stale", f"The last drift check for {lst} is old",
            f"it ran {int((now - last_ts) // 3600)} h ago, over "
            f"{DRIFT_STALE_INTERVALS} intervals of {int(interval // 60)} min: "
            "what it found describes the network as it was then",
            {"label": "Run a drift check from the Drift panel"}, "warning",
            since=last_ts + DRIFT_STALE_INTERVALS * interval)
    coverage = f"checked {last.get('checked', 0)} of {last.get('inventory', 0)}"
    for d in last.get("drifted_devices") or []:
        add(f"drifted:{d['hostname']}", f"{d['hostname']} has drifted from its golden",
            f"the running config differs from the committed golden by "
            f"{d.get('diff_lines', '?')} diff line(s), seen by the drift check at "
            f"{_iso(last_ts) or 'an unrecorded time'}; since when it has differed "
            "is not recorded", _DRIFT_ACTION, "danger", devices=[d["hostname"]],
            operands={"diff_lines": d.get("diff_lines"), "coverage": coverage})
    for d in last.get("skipped") or []:
        no_golden = d.get("reason") == "no golden config saved"
        add(f"skipped:{d['hostname']}", f"{d['hostname']} was not checked for drift",
            d.get("reason") or "no reason recorded",
            {"label": "Capture its golden from its Device page, or with Save All's "
                      "no-golden scope"} if no_golden else
            {"label": "The reason above is all that is recorded", "known": False},
            "warning", devices=[d["hostname"]], operands={"coverage": coverage})
    for d in last.get("errors") or []:
        add(f"unreachable:{d['hostname']}", f"{d['hostname']} could not be checked for drift",
            d.get("reason") or "no reason recorded",
            {"label": "The reason above is all that is recorded", "known": False},
            "unknown", devices=[d["hostname"]], operands={"coverage": coverage})
    return source_result("drift", "Drift", read_at=started, took_ms=took, rows=rows,
                         value_at=last_ts,
                         stale_after_seconds=int(DRIFT_STALE_INTERVALS * interval) or None,
                         checked=f"list {lst}, the run of {_iso(last_ts) or 'an unrecorded time'}: "
                                 f"{coverage}, triggered by {last.get('triggered_by') or 'unrecorded'}")


def _ts(value):
    """An epoch from a stored time that may be epoch or ISO text; None if neither."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        import calendar
        return float(calendar.timegm(time.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S")))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Source: the approval queue
# ---------------------------------------------------------------------------

#: The action types drift queues, one item per drifted device. Each is ABOUT
#: that device's drift row and attaches to it.
_DRIFT_ITEM_TYPES = ("update_golden_config",)


def approvals_source(read=None) -> dict:
    """Every pending approval, through a read that writes nothing. A queued
    drift item attaches to its device's drift row (the page must not count
    one event twice); anything else is a row of its own."""
    from modules import approval_queue as Q
    from modules.config import get_current_list_name

    started = time.time()
    try:
        lst = get_current_list_name()
        pending, reason = (read or Q.read_pending)()
    except Exception as exc:                       # noqa: BLE001
        pending, reason = None, f"it raised {type(exc).__name__}: {exc}"
    took = int((time.time() - started) * 1000)
    if reason:
        return source_result("approvals", "Approvals", read_at=started, took_ms=took,
                             error=reason)
    rows = []
    for e in pending:
        host = e.get("device_hostname") or e.get("device_ip") or ""
        drift_item = e.get("action_type") in _DRIFT_ITEM_TYPES and host
        rows.append(row(
            source="approvals", key=e.get("id") or "?",
            what=f"An approval is waiting: {e.get('description') or e.get('action_type')}",
            cause=(e.get("context") or "queued with no context recorded")
                  + "; nothing is done until a person approves it",
            action={"label": "Review it in Approvals"
                             + (": approving opens the capture preview"
                                if e.get("action_type") in Q.CONFIRM_ENDING_ACTIONS else "")},
            level="warning", devices=[host] if host else [], since=e.get("created_ts"),
            operands={"kind": e.get("action_type", ""), "list": lst},
            attach_to=f"drift:{lst}:drifted:{host}" if drift_item else None))
    return source_result("approvals", "Approvals", read_at=started, took_ms=took,
                         rows=rows, checked=f"list {lst}: {len(rows)} pending approval(s)")


# ---------------------------------------------------------------------------
# Source: pending onboardings
# ---------------------------------------------------------------------------

def pending_onboarding_source(pending=None, now=None) -> dict:
    """Devices onboarded and never reached. `in_flight` (under a day) is the
    normal state of an onboarding and is counted, not listed; overdue, stale
    and a staged credential nothing can find are rows. ZTP progress is not
    asked here: it asks Kea per device (section 0a); the pending banner
    carries it."""
    import os

    from modules.config import get_current_list_name, get_list_data_dir
    from modules.nsot.manifest import pending_devices

    started = time.time()
    try:
        lst = get_current_list_name()
        devices = (pending or (lambda: pending_devices(
            os.path.join(get_list_data_dir(lst), "config_repo"))))()
    except Exception as exc:                       # noqa: BLE001
        return source_result("onboarding", "Pending onboardings", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    rows = []
    for d in devices:
        name, state = d.get("name") or d.get("identity") or "?", d.get("state")
        since = _ts(d.get("onboarded_at"))
        if d.get("credential_findable") is False:
            rows.append(row(
                source="onboarding", key=f"{lst}:{name}:credential", level="danger",
                what=f"{name} cannot be verified: its staged credential cannot be found",
                cause=("the credential staged for it is not where verification looks, so "
                       "Verify would try a profile the device refuses; nothing has reached "
                       "the device, so there is nothing to undo"),
                action={"label": "Abandon it and onboard it again, from the pending banner"},
                devices=[name], since=since, operands={"list": lst, "state": state}))
        elif state in ("overdue", "stale"):
            hours = int((d.get("age_seconds") or 0) // 3600)
            rows.append(row(
                source="onboarding", key=f"{lst}:{name}", level="warning",
                what=f"{name} was onboarded {hours} h ago and has never been reached",
                cause=("it is in the manifest and git and not in the inventory: nothing "
                       "polls, backs up or drift-checks it until Verify reaches it"),
                action={"label": "Verify it, or Abandon it, from the pending banner"},
                devices=[name], since=since, operands={"list": lst, "state": state,
                                                       "address_source": d.get("address_source")}))
    quiet = sum(1 for d in devices if d.get("state") == "in_flight"
                and d.get("credential_findable") is not False)
    return source_result("onboarding", "Pending onboardings", read_at=started, took_ms=took,
                         rows=rows,
                         checked=f"list {lst}: {len(devices)} pending, {quiet} within their "
                                 "first day")


# ---------------------------------------------------------------------------
# Source: rollback blocks
# ---------------------------------------------------------------------------

#: Revert intent and retry are the remedies, and both are routes with no
#: page yet; 7.3's Device actions are their home (C164). Stated, not hidden.
_ROLLBACK_ACTION = {"label": "Revert the intent that failed, or authorise a retry: "
                             "neither has a screen yet (7.3's Device actions)",
                    "known": False}


def rollback_source(notes=None) -> dict:
    """Devices whose rolled-back change still blocks their next plan. Uses
    the ONE classifier the listing uses (`rolled_back_notes`): a note blocks
    only while the program a fresh plan would send still contains what failed,
    so a stale note is counted, never listed as needing attention. Its work
    is per NOTED device, bounded by the rollbacks on record."""
    from modules.config import get_current_list_name

    started = time.time()
    try:
        lst = get_current_list_name()
        if notes is None:
            from routes.templatize import rolled_back_notes
            got = rolled_back_notes(lst)
        else:
            got = notes()
    except Exception as exc:                       # noqa: BLE001
        return source_result("rollback", "Rollback blocks", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    rows = []
    if got.get("unreadable"):
        # One row for the list: the record blocks EVERY plan, and a row per
        # device would be one event counted N times.
        rows.append(row(source="rollback", key=f"{lst}:record", level="danger",
                        what=f"Every plan on {lst} is blocked: the rolled-back record "
                             "cannot be read",
                        cause=got["unreadable"],
                        action={"label": "Repair the record from its preserved copy; "
                                         "nothing here can rewrite it", "known": False},
                        operands={"list": lst}))
    for host, note in sorted((got.get("applies") or {}).items()):
        unknown = note.get("applicability") == "unknown"
        rows.append(row(
            source="rollback", key=f"{lst}:{host}", level="unknown" if unknown else "warning",
            what=(f"{host}'s rolled-back change may still block its next plan" if unknown
                  else f"{host}'s next plan is blocked: its intent still sends what was "
                       "rolled back"),
            cause=(f"rolled back at {note.get('at') or 'an unrecorded time'}"
                   + (f" ({note['reason']})" if note.get("reason") else "")
                   + ("; whether the note still applies could not be computed"
                      if unknown else "")),
            action=_ROLLBACK_ACTION, devices=[host], since=_ts(note.get("at")),
            operands={"list": lst, "failed_lines": len(note.get("commands") or []),
                      "intent_commit": (note.get("intent_commit") or "")[:10]}))
    n_stale = len(got.get("stale") or {})
    return source_result("rollback", "Rollback blocks", read_at=started, took_ms=took,
                         rows=rows,
                         checked=(f"list {lst}: the rolled-back record could not be read"
                                  if got.get("unreadable") else
                                  f"list {lst}: {len(got.get('applies') or {})} standing, "
                                  f"{n_stale} no longer blocking"))


# ---------------------------------------------------------------------------
# Source: a deploy or restore that did not finish clean
# ---------------------------------------------------------------------------

def deploy_source(read=None) -> dict:
    """Each device's LATEST deploy or restore receipt, judged by the ONE
    decision the result screen uses (`preview_confirm.result_level`): a row
    unless it finished clean. A later clean run supersedes an earlier
    failure, so a device leaves the page by being deployed, not by aging.
    Danger when a program was SENT (the device may be part-changed), warning
    when nothing was (a refusal changed nothing, and the change it was for
    still has not landed)."""
    from modules.config import get_current_list_name
    from modules.nsot import receipts
    from modules.preview_confirm import OUTCOME_WORDS, result_level

    started = time.time()
    try:
        lst = get_current_list_name()
        got = (read or (lambda: receipts.read(lst, limit=10 ** 6)))()
    except Exception as exc:                       # noqa: BLE001
        got = {"state": "unreadable", "error": f"it raised {type(exc).__name__}: {exc}"}
    took = int((time.time() - started) * 1000)
    if got.get("state") == "unreadable":
        return source_result("deploys", "Deploys and restores", read_at=started, took_ms=took,
                             error=f"the deploy receipts could not be read ({got.get('error')})")
    latest = {}
    for r in got.get("rows") or []:                # newest first
        latest.setdefault(r.get("device") or "?", r)
    rows = []
    for host, r in sorted(latest.items()):
        if result_level([r], receipt_ok=True) == "success":
            continue
        outcome = r.get("outcome", "")
        rb = r.get("rollback") or {}
        checks = r.get("checks") or {}
        issues = [str(i) for i in checks.get("issues") or []]
        unmet = [str(p) for p in checks.get("intent_unmet") or []]
        cause = "; ".join(x for x in (
            r.get("reason"),
            f"stopped at {r['stage']}" if r.get("stage") else "",
            f"verify found: {'; '.join(issues)}" if issues else "",
            f"declared by intent and not up after: {', '.join(unmet)}" if unmet else "",
            f"rollback: {rb.get('state')}" if rb.get("performed") else "",
            "the program sent does NOT match the one confirmed"
            if r.get("matches_confirmed") is False else "") if x) or \
            f"its receipt records {outcome or 'no outcome'} with no reason"
        rows.append(row(
            source="deploys", key=f"{lst}:{host}",
            level="danger" if r.get("sent") else "warning",
            what=f"The last {r.get('action') or 'deploy'} to {host}: "
                 f"{OUTCOME_WORDS.get(outcome, outcome.replace('_', ' ') or 'no outcome')}",
            cause=cause,
            action={"label": "Read its receipt on the device's Changes tab, then plan again"},
            devices=[host], since=_ts(r.get("at")),
            operands={"list": lst, "action": r.get("action"), "outcome": outcome,
                      "sent_lines": r.get("program_lines") if r.get("sent") else 0,
                      "by": r.get("actor")}))
    return source_result("deploys", "Deploys and restores", read_at=started, took_ms=took,
                         rows=rows,
                         checked=(f"list {lst}: no deploy or restore recorded"
                                  if got.get("state") == "absent" else
                                  f"list {lst}: the latest receipt of {len(latest)} device(s), "
                                  f"{len(latest) - len(rows)} clean"))


# ---------------------------------------------------------------------------
# Source: the last baseline decision (a baseline that was not earned)
# ---------------------------------------------------------------------------

def baseline_source(log_fn=None) -> dict:
    """The NEWEST `Baseline:` decision recorded in the list's golden history
    (`save_golden()` writes it into the commit it judged). A row when that
    decision was a denial, with its reasons; a later earned baseline
    supersedes it. One `git log`, never a read per device (section 0a).
    Commits before 2026-09-28 carry no decision, and the source says so
    rather than reading their silence as either answer."""
    import os

    from modules.config import get_current_list_name, get_list_data_dir

    started = time.time()
    try:
        lst = get_current_list_name()
        if log_fn is None:
            from modules.nsot.repo import git
            repo = os.path.join(get_list_data_dir(lst), "config_repo")
            rc, out, err = git(repo, "log", "-1", "-E", "--grep=^Baseline: ",
                               "--format=%H%x1f%ct%x1f%B")
            if rc != 0:
                raise RuntimeError(f"git log failed: {err.strip() or rc}")
        else:
            out = log_fn()
    except Exception as exc:                       # noqa: BLE001
        return source_result("baseline", "Baseline", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    if not out.strip():
        # The host's state on 2026-09-28: no decision recorded yet, and no
        # baseline usable. The usability row must not wait for a decision.
        usability = _baseline_usability_row(lst)
        return source_result("baseline", "Baseline", read_at=started, took_ms=took,
                             rows=usability["rows"],
                             checked=f"list {lst}: no baseline decision recorded yet "
                                     "(decisions are recorded from 2026-09-28); "
                                     + usability["checked"])
    sha, ct, body = out.split("\x1f", 2)
    decision = next((ln.split(":", 1)[1].strip() for ln in body.splitlines()
                     if ln.startswith("Baseline: ")), "")
    source_line = next((ln.split(":", 1)[1].strip() for ln in body.splitlines()
                        if ln.startswith("Source: ")), "")
    at = float(ct)
    rows = []
    reasons = decision.split(":", 1)[1].strip() if ":" in decision else ""
    # ONE row when the last decision was a denial AND no stored baseline is
    # usable: both say "there is no restore point", and the denial names the
    # blocker, which the usability row's remedy must name too (the operator,
    # 2026-09-28: "take a current one with Save All" was followed and could
    # not succeed while r2 departed from its intent).
    blocker = ({"reasons": reasons or "the decision recorded no reason",
                "commit": sha[:10], "at": _iso(at)}
               if decision.startswith("denied") else None)
    usability = _baseline_usability_row(lst, blocker=blocker)
    if decision.startswith("denied") and not usability["rows"]:
        rows.append(row(
            source="baseline", key=f"{lst}:last", level="warning",
            what=f"The network's last baseline was not earned ({source_line or 'a save'})",
            # The decision's OWN commit and time: a Save All that changed
            # nothing since decided without a commit to carry it, so this can
            # be older than the newest save, and the row says whose it is.
            cause=(reasons or "the decision recorded no reason")
                  + f" (decided by commit {sha[:10]} at {_iso(at)}; a save since that made "
                    "no decision, a one-device capture or a Save All that changed nothing, "
                    "leaves it standing)",
            action={"label": "Resolve each departure the reasons name, one of two ways "
                             "that mean opposite things: change the DEVICE (a line intent "
                             "has is deployed; a line only the device has is removed by hand, "
                             "since the tool never removes one) if intent is right, or Edit "
                             "INTENT if the device is right. Then Save All"},
            since=at, operands={"list": lst, "commit": sha[:10], "source": source_line}))
    rows += usability["rows"]
    return source_result("baseline", "Baseline", read_at=started, took_ms=took, rows=rows,
                         value_at=at,
                         checked=f"list {lst}: the last baseline decision, {sha[:10]}: "
                                 f"{decision.split(':', 1)[0] or 'unreadable'}; "
                                 + usability["checked"])


def _baseline_usability_row(lst: str, cached=None, blocker: dict = None) -> dict:
    """No stored baseline can be re-applied (the operator, 2026-09-28): every
    one predates a credential rotation (the restore's guard refuses each,
    C75) or is withdrawn. The Baselines panel said it once per row and never
    once. Read from the `baseline-usability` reader (the per-row check costs
    8 to 9 s on the host); a reader that has not answered is job health's row,
    so this says only what it read."""
    from modules import reader_job

    got = reader_job.read_cached("baseline-usability") if cached is None else cached
    good = ((got.get("doc") or {}).get("last_good") or {})
    value = ((good.get("value") or {}).get("lists") or {}).get(lst)
    if got.get("state") != "ok" or value is None:
        return {"rows": [], "checked": "whether a baseline can be re-applied: not judged yet"}
    if value.get("error"):
        return {"rows": [], "checked": f"whether a baseline can be re-applied: {value['error']}"}
    if value.get("usable"):
        return {"rows": [], "checked": f"{value['usable']} can be re-applied"}
    if not value.get("count"):
        return {"rows": [], "checked": "no baseline is stored yet"}
    newest = next((b for b in value["baselines"] if not b["withdrawn"]), None)
    withdrawn = [b["tag"] for b in value["baselines"] if b["withdrawn"]]
    cause = (f"all {value['count']} stored baseline(s) predate a credential rotation or are "
             "withdrawn, so the restore's credential guard (C75) refuses part of any re-apply."
             + (f" The newest, {newest['tag']}, would change the credential on "
                f"{', '.join(newest['stale'])}." if newest else "")
             + (f" Withdrawn: {', '.join(withdrawn)}." if withdrawn else "")
             + " A baseline's usefulness decays with every rotation."
             + (f" A new one cannot be earned right now: the last Save All was denied "
                f"({blocker['reasons']}; commit {blocker['commit']} at {blocker['at']})."
                if blocker else ""))
    action = ({"label": "Resolve each departure the denial names, one of two ways that mean "
                        "opposite things: change the DEVICE if intent is right (a line only the "
                        "device has is removed by hand: the tool never removes one), or Edit "
                        "INTENT if the device is right. Then Save All. Save All alone will be "
                        "refused again while it departs"}
              if blocker else
              {"label": "Take a current baseline: Save All captures every device, and earns "
                        "a baseline if each is at its committed intent; if not, it records "
                        "the denial and names the device and its lines"})
    return {"rows": [row(
        source="baseline", key=f"{lst}:unusable", level="warning",
        what=("No stored baseline can be re-applied, and a new one cannot be earned yet"
              if blocker else "No stored baseline can be re-applied"),
        cause=cause,
        action=action,
        operands={"list": lst, "baselines": str(value["count"]),
                  "newest": newest["tag"] if newest else "none"},
        since=_ts(good.get("value_at")))],
        "checked": "no baseline can be re-applied"}


# ---------------------------------------------------------------------------
# Source: a line authorised again and again (C140 (1))
# ---------------------------------------------------------------------------

#: How many authorisations of ONE line on ONE device make a pattern. Twice
#: can be a retry after a failed push; a third time is a routine, and an
#: exception that is routine is what 8.8 wants seen ("ok" typed thirty
#: times is the finding, not a defeat of the control).
REPEAT_THRESHOLD = 3


def authorisation_source(counts=None) -> dict:
    """The same dangerous or secret line authorised on the same device at
    least `REPEAT_THRESHOLD` times, from ONE read of the receipts through the
    counting the preview's aggregate uses. It makes behaviour visible; it
    blocks nothing."""
    from modules.config import get_current_list_name
    from modules.nsot import receipts

    started = time.time()
    try:
        lst = get_current_list_name()
        got = (counts or (lambda: receipts.authorisations_by_device(lst)))()
    except Exception as exc:                       # noqa: BLE001
        got = {"state": "unreadable", "error": f"it raised {type(exc).__name__}: {exc}"}
    took = int((time.time() - started) * 1000)
    if got.get("state") == "unreadable":
        return source_result("authorisations", "Repeated authorisations", read_at=started,
                             took_ms=took,
                             error=f"the deploy receipts could not be read ({got.get('error')})")
    rows, n_lines = [], 0
    for device, lines in sorted((got.get("devices") or {}).items()):
        for line, e in sorted(lines.items()):
            n_lines += 1
            if e.get("count", 0) < REPEAT_THRESHOLD:
                continue
            rows.append(row(
                source="authorisations", key=f"{lst}:{device}:{line}", level="warning",
                what=f"{line.strip()!r} has been authorised {e['count']} times on {device}",
                cause=(f"last by {e.get('last_actor') or 'an unrecorded actor'} at "
                       f"{e.get('last_at') or 'an unrecorded time'}, stated reason: "
                       f"{e.get('last_reason')}. An exception authorised again and again "
                       "is a routine, not an exception"),
                action={"label": "Read the stated reasons on the device's Changes tab: a line "
                                 "authorised routinely belongs in intent, or its cause does"},
                devices=[device], since=_ts(e.get("first_at")),
                operands={"list": lst, "count": e["count"], "threshold": REPEAT_THRESHOLD,
                          "last_at": e.get("last_at")}))
    return source_result("authorisations", "Repeated authorisations", read_at=started,
                         took_ms=took, rows=rows,
                         checked=(f"list {lst}: no deploy or restore recorded"
                                  if got.get("state") == "absent" else
                                  f"list {lst}: {n_lines} authorised line(s) across "
                                  f"{len(got.get('devices') or {})} device(s), a row from "
                                  f"{REPEAT_THRESHOLD} authorisations"))


#: Every source, in the order a person reads them. Section 1a's other
#: sources (freshness, Grafana alerts) join HERE through `source_result`,
#: both through the reader-job pattern.
# ---------------------------------------------------------------------------
# Source: Grafana's alerts, from the grafana-alerts READER's cache (7.2; the
# reader-job pattern's second instance, and 8.6's constraints on 7.2)
# ---------------------------------------------------------------------------

GRAFANA_READER = "grafana-alerts"

#: Instances whose ONSETS fall within this of the previous one form one
#: incident (8.6: grouping is on the onset, never on startsAt, because
#: per-device windows fire one Loki outage up to 536 s apart). 360 s is a
#: heartbeat onset's own uncertainty: the silence began somewhere in the
#: device's last heartbeat period (300 s), and the rule notices it on its
#: next evaluation (60 s). Two onsets closer than that cannot be told apart.
INCIDENT_GAP_SECONDS = 360

_KIND_WORDS = {"condition": "is alerting", "no_data": "reads no data",
               "error": "cannot evaluate", "unknown_state": "is in a state this page does not know"}


def _onset(inst: dict):
    """(epoch or None, basis). A windowed rule fires one window after the
    silence began, so its onset is the alert's start minus the window."""
    starts, active = _ts(inst.get("starts_at")), _ts(inst.get("active_at"))
    window = inst.get("window_seconds")
    if window and (starts or active):
        return (starts or active) - window, f"the alert's start minus the rule's {window} s window"
    if active:
        return active, "when the condition first held"
    if starts:
        return starts - (inst.get("for_seconds") or 0), "the alert's start minus the rule's pending time"
    return None, "not recorded"


def _incidents(instances: list) -> list:
    """Groups of instances, each group one incident, by onset; an instance
    with no onset is an incident of its own (never merged on a guess)."""
    timed = sorted((i for i in instances if i["onset"] is not None), key=lambda i: i["onset"])
    groups, current = [], []
    for inst in timed:
        if current and inst["onset"] - current[-1]["onset"] > INCIDENT_GAP_SECONDS:
            groups.append(current)
            current = []
        current.append(inst)
    if current:
        groups.append(current)
    return groups + [[i] for i in instances if i["onset"] is None]


def _inventory():
    """(hostnames, address -> hostname), or (None, reason) when unreadable."""
    try:
        from modules.device import load_saved_devices
        devices = load_saved_devices()
    except Exception as exc:                       # noqa: BLE001
        return None, f"the inventory could not be read ({type(exc).__name__})"
    return ({d.get("hostname") for d in devices if d.get("hostname")},
            {d.get("ip"): d.get("hostname") for d in devices if d.get("ip")}), ""


def _member(inst: dict, inv) -> dict:
    """One instance as an incident member, naming where its device came from."""
    names, by_ip = inv if inv else (None, None)
    source = inst.get("device_from")
    device, note = inst.get("device"), ""
    if source == "address":
        addr = inst.get("address")
        device = (by_ip or {}).get(addr)
        note = (f"from the polled address {addr}" if device else
                f"the polled address {addr} matches no device's address in the inventory")
    elif source in ("label", "line"):
        note = ("from the rule's device label" if source == "label" else
                "from the syslog line's origin-id")
        if names is not None and device not in names:
            note += ", and it is NOT in the inventory (a rule left behind by a device that left)"
    else:
        note = "the rule names no device"
    if inv is None:
        note += " (the inventory could not be read, so the name is unchecked)"
    return {"rule": inst.get("rule"), "kind": inst.get("kind"), "device": device,
            "device_from": source, "device_note": note, "state": inst.get("state"),
            "fingerprint": inst.get("fingerprint"), "starts_at": inst.get("starts_at"),
            "onset": _iso(inst["onset"]), "onset_basis": inst["onset_basis"],
            "silenced_by": inst.get("silenced_by") or [],
            "silences": inst.get("silences") or []}


def silence_words(silences: list) -> str:
    """"silenced in Grafana by X until T ("comment")", one clause per
    silence. An unresolved one is named by its id and said to be unresolved:
    who and until when are never guessed."""
    parts = []
    for s in silences or []:
        if s.get("unresolved"):
            parts.append(f"silenced in Grafana by silence {s.get('id')}, whose author and end "
                         "Grafana's silence list did not return")
            continue
        text = f"silenced in Grafana by {s.get('created_by') or 'an unnamed account'}"
        text += f" until {s.get('ends_at') or 'an unrecorded time'}"
        if s.get("comment"):
            text += f" (\"{s['comment']}\")"
        parts.append(text)
    return "; ".join(parts)


def grafana_source(cached=None) -> dict:
    """Grafana's alert state, read from the reader's cache, NEVER from
    Grafana (rule 1 of modules/reader_job.py). The reader's own liveness is
    job health's row (`reader:grafana-alerts`), judged at request time."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached(GRAFANA_READER) if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("grafana", "Grafana alerts", read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    v = good.get("value") or {}
    inv, inv_why = _inventory()
    rows = []

    def add(key, what, cause, action, level, **kw):
        rows.append(row(source="grafana", key=key, what=what, cause=cause, action=action,
                        level=level, **kw))

    # Grafana answering and not evaluating reads exactly like a healthy
    # fleet (8.6: the Proxmox listing's 200 with 0 items).
    for g in v.get("stalled_groups") or []:
        add(f"stalled:{g.get('group')}", f"Grafana has stopped evaluating {g.get('group')}",
            f"its last evaluation was {g.get('last_evaluation') or 'never'}, more than three "
            f"of its {g.get('interval_seconds')} s intervals before the read; every rule in it "
            "reads as quiet whether or not its condition holds",
            {"label": "Check Grafana's alert scheduler: its log, then a restart"}, "danger")

    alerting = [dict(i) for i in v.get("instances") or [] if i.get("kind") != "pending"]
    for inst in alerting:
        inst["onset"], inst["onset_basis"] = _onset(inst)
    heartbeat_rules = {r.get("uid") for r in v.get("rules") or []
                       if (r.get("labels") or {}).get("nmas") == "heartbeat"}
    for group in _incidents(alerting):
        members = [_member(i, inv) for i in group]
        devices = sorted({m["device"] for m in members if m["device"]})
        first = group[0]
        heartbeats = {i.get("rule_uid") for i in group} & heartbeat_rules
        whole_pipeline = bool(heartbeat_rules) and heartbeats == heartbeat_rules
        if whole_pipeline:
            what = "Every device's syslog heartbeat stopped at once"
            cause = ("all " + str(len(heartbeat_rules)) + " heartbeat rules are alerting with "
                     "onsets together, so no heartbeat is arriving from any device: the "
                     "subject is the path they share (rsyslog, Alloy, Loki or the route to "
                     "them), not each device")
            action = {"label": "Check the syslog pipeline first: rsyslog, Alloy and Loki on the "
                               "monitoring host"}
        elif len(members) == 1:
            m = members[0]
            what = (f"{m['rule']} {_KIND_WORDS.get(m['kind'], m['kind'])}"
                    + (f" on {m['device']}" if m["device"] else ""))
            cause = f"{m['state']}; the device is {m['device_note']}"
            action = ({"label": "Check the device's syslog path: the heartbeat cannot say which "
                                "of the device, its logging block, rsyslog, Alloy or Loki stopped"}
                      if first.get("rule_uid") in heartbeat_rules else
                      {"label": f"Read the rule \"{m['rule']}\" in Grafana: this page records that "
                                "it fired and where its device came from, not why",
                       "known": False})
        else:
            what = f"{len(members)} alerts began together"
            cause = ("; ".join(f"{m['rule']}" + (f" on {m['device']}" if m["device"] else "")
                               + f" ({m['kind']})" for m in members)
                     + f". Grouped because their onsets fall within {INCIDENT_GAP_SECONDS} s "
                       "of each other; whether they share a cause is not decided here")
            action = {"label": "Read the members together: one cause may explain them, "
                               "or none", "known": False}
        # A silence set in Grafana hides nothing here (the operator,
        # 2026-09-30): the row keeps its level and says who silenced it and
        # until when, so a silence is a visible decision, never a quiet one.
        silenced = [m for m in members if m["silences"]]
        if silenced:
            what += (" (silenced in Grafana)" if len(silenced) == len(members) else
                     f" ({len(silenced)} of {len(members)} silenced in Grafana)")
            cause += ". " + "; ".join(
                (f"{m['rule']}" + (f" on {m['device']}" if m["device"] else "") + ": "
                 if len(members) > 1 else "") + silence_words(m["silences"])
                for m in silenced)
        level = "danger" if any(m["kind"] == "condition" for m in members) else "unknown"
        add(f"incident:{first.get('rule_uid') or first.get('rule')}:{_iso(first['onset']) or 'untimed'}",
            what, cause, action, level, devices=devices, since=first["onset"],
            operands={"members": members, "grouped_within_seconds": INCIDENT_GAP_SECONDS,
                      "onset_basis": first["onset_basis"]})

    # A rule that cannot see its data, or cannot evaluate, with no alerting
    # instance saying so (C166, C168: rules sat in no-data for days).
    covered = {i.get("rule_uid") for i in alerting}
    for r in v.get("rules") or []:
        health = r.get("health")
        if health in ("nodata", "error") and r.get("uid") not in covered:
            add(f"rule:{r.get('uid')}",
                f"{r.get('title')} {'reads no data' if health == 'nodata' else 'cannot evaluate'}",
                (f"its query returns nothing, so whether its condition holds is unknown "
                 f"(its no-data state is {r.get('no_data_state') or 'unrecorded'})"
                 if health == "nodata" else
                 f"its last evaluation failed: {r.get('last_error') or 'no error recorded'}"),
                {"label": f"Read the rule \"{r.get('title')}\"'s query in Grafana", "known": False},
                "warning" if health == "nodata" else "unknown")

    # The floor (8.6): every device should have a heartbeat rule the reader
    # SEES. Fewer is a permission or provisioning gap, and a monitor's
    # permissions can hide what it monitors behind a 200.
    if inv is not None:
        seen = {(r.get("labels") or {}).get("device") for r in v.get("rules") or []
                if (r.get("labels") or {}).get("nmas") == "heartbeat"}
        missing = sorted(inv[0] - seen)
        if missing:
            add("heartbeat-floor", f"{len(missing)} device(s) have no heartbeat rule Grafana shows",
                "no heartbeat rule the reader can see names " + ", ".join(missing)
                + ": the rule is missing, or the reader's account cannot see it",
                {"label": "Regenerate the heartbeat rules (NSOT_PLAN P.1 step 5), then check "
                          "the reader's Grafana role can read them"}, "warning", devices=missing)

    c = v.get("counts") or {}
    return source_result(
        "grafana", "Grafana alerts", read_at=started, took_ms=took, rows=rows,
        value_at=_ts(good.get("value_at")), stale_after_seconds=doc.get("stale_after_seconds"),
        reader=GRAFANA_READER, detail="read from " + ", ".join(doc.get("endpoints") or []),
        checked=(f"{c.get('rules', 0)} rule(s); "
                 f"{c.get('condition', 0)} alerting, {c.get('no_data', 0)} no data, "
                 f"{c.get('error', 0)} error, {c.get('pending', 0)} pending, "
                 f"{c.get('normal_no_data', 0)} reading no data as healthy by decision"
                 + (f"; {inv_why}" if inv is None else "")))


# ---------------------------------------------------------------------------
# Source: Oxidized freshness, from the freshness READER's cache (7.2): a
# device whose Oxidized copy is not the approved state would come back on it
# at the next redeploy.
# ---------------------------------------------------------------------------

def freshness_source(cached=None) -> dict:
    """UNAPPROVED is a row (a change nobody approved is what a redeploy
    would bake in); INCONCLUSIVE is a row (the comparison cannot say); a
    poll race and an authorised divergence are counted, never rows: the
    first self-corrects at the next poll, the second is a recorded
    decision."""
    from modules import reader_job
    from modules.config import get_current_list_name

    started = time.time()
    got = reader_job.read_cached("freshness") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("freshness", "Freshness", read_at=started, took_ms=took,
                             error=f"not compared yet: {why}")
    lst = get_current_list_name()
    report = ((good.get("value") or {}).get("lists") or {}).get(lst)
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    if report is None:
        return source_result("freshness", "Freshness", read_at=started, took_ms=took,
                             error=f"the stored comparison holds no answer for list {lst}")
    rows = []
    if not report.get("ok"):
        rows.append(row(source="freshness", key=f"{lst}:not-compared", level="unknown",
                        what=f"Freshness could not be compared for {lst}",
                        cause=(report.get("error") or report.get("defect") or "no reason recorded")
                              + ". This is not the same as nothing having diverged",
                        action={"label": "The reason above is what is known", "known": False}))
        return source_result("freshness", "Freshness", read_at=started, took_ms=took,
                             rows=rows, value_at=value_at, stale_after_seconds=promise,
                             checked=f"list {lst}: not compared")
    from modules.redact import redact_text
    for d in report.get("devices") or []:
        verdict = d.get("verdict")
        if verdict not in ("unapproved", "inconclusive"):
            continue
        extra = [redact_text(l) for l in (d.get("only_right") or [])[:3]]
        rows.append(row(
            source="freshness", key=f"{lst}:{d.get('device')}",
            what=(f"{d.get('device')}: Oxidized holds a change nobody approved"
                  if verdict == "unapproved" else
                  f"{d.get('device')}: whether Oxidized's copy is approved cannot be told"),
            devices=[d.get("device")], since=_ts(d.get("oxidized_at")),
            cause=redact_text(d.get("reason") or "no reason recorded")
                  + (f"; in Oxidized and not the golden: {extra}" if extra else ""),
            operands={"golden_at": d.get("golden_at"), "oxidized_at": d.get("oxidized_at"),
                      "fingerprint": (d.get("fingerprint") or "")[:16]},
            action=({"label": "Capture the device's golden if the change is wanted, or put "
                              "it back; a redeploy before then boots it"}
                    if verdict == "unapproved" else
                    {"label": "The reason above is what is known", "known": False}),
            level="warning" if verdict == "unapproved" else "unknown"))
    c = report.get("counts") or {}
    return source_result(
        "freshness", "Freshness", read_at=started, took_ms=took, rows=rows,
        value_at=value_at, stale_after_seconds=promise, reader="freshness",
        checked=(f"list {lst}: {report.get('checked', 0)} of {report.get('population', 0)} "
                 f"compared; {c.get('match', 0)} approved, {c.get('poll_race', 0)} poll race, "
                 f"{c.get('authorised', 0)} authorised"))


# ---------------------------------------------------------------------------
# Source: integration health, from the integration-health READER (7.2): the
# same stored value the status bar draws, so the two cannot disagree.
# ---------------------------------------------------------------------------

def integrations_source(cached=None) -> dict:
    """A configured integration that does not answer is a row; one left
    unconfigured is a state, counted (job health names the guard it gates)."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached("integrations") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("integrations", "Integrations", read_at=started, took_ms=took,
                             error=f"not probed yet: {why}")
    v = good.get("value") or {}
    rows = []
    for i in v.get("integrations") or []:
        if i.get("state") != "down":
            continue
        rows.append(row(source="integrations", key=i.get("name", "?"), level="danger",
                        what=f"{i.get('label')} is not answering",
                        cause=f"its health probe failed: {i.get('message') or 'no reason recorded'}",
                        operands={"probe_ms": i.get("took_ms")},
                        action={"label": f"Check {i.get('label')} at the URL set in Settings > "
                                         "Integrations; its Test button probes it now"}))
    c = v.get("counts") or {}
    # Named, never only counted: "2 not configured" hid that one of the two
    # was the NSoT repository committing all evening (C171).
    unset = [i.get("label") for i in v.get("integrations") or []
             if i.get("state") == "not_configured"]
    return source_result(
        "integrations", "Integrations", read_at=started, took_ms=took, rows=rows,
        value_at=_ts(good.get("value_at")), stale_after_seconds=doc.get("stale_after_seconds"),
        reader="integrations",
        checked=(f"{len(v.get('integrations') or [])} integration(s): {c.get('up', 0)} up, "
                 f"{c.get('down', 0)} down, {c.get('not_configured', 0)} not configured"
                 + (f" ({', '.join(unset)})" if unset else "")))


# ---------------------------------------------------------------------------
# Source: the running commit's CI verdict, from the ci-verdict READER (7.2):
# nmas-deploy's own gate, never a second implementation of it.
# ---------------------------------------------------------------------------

_CI_ROWS = {"failed": ("its CI run failed", "danger"),
            "cancelled": ("its CI run was cancelled, so no verdict exists", "warning"),
            "pending": ("its CI run is still going", "warning"),
            "could_not_ask": ("whether it passed CI could not be asked", "unknown")}


def ci_source(cached=None) -> dict:
    """A running commit CI did not pass is a row; a verified one is not."""
    from modules import reader_job
    from routes import health

    started = time.time()
    got = reader_job.read_cached("ci-verdict") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("ci", "Running commit's CI", read_at=started, took_ms=took,
                             error=f"not judged yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    commit = str(v.get("commit") or "")
    if commit != str(health._COMMIT or ""):
        return source_result("ci", "Running commit's CI", read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise,
                             checked=f"the stored verdict is for {commit[:10]}, not the running "
                                     f"{str(health._COMMIT)[:10]}: not judged yet")
    rows = []
    if v.get("state") in _CI_ROWS:
        words, level = _CI_ROWS[v["state"]]
        rows.append(row(source="ci", key=commit[:10], level=level,
                        what=f"The running commit {commit[:10]}: {words}",
                        cause=v.get("sentence") or "no sentence recorded",
                        action=({"label": "Deploy a commit CI passed (nmas-deploy refuses one it "
                                          "did not; a person's step)",
                                 "command": "scripts/nmas-deploy --wait"}
                                if v["state"] in ("failed", "cancelled") else
                                {"label": "Read nmas-deploy's sentence above: it names the run "
                                          "and what it found", "known": False})))
    return source_result("ci", "Running commit's CI", read_at=started, took_ms=took, rows=rows,
                         value_at=value_at, stale_after_seconds=promise, reader="ci-verdict",
                         checked=f"{commit[:10]}: {v.get('state')}")


# ---------------------------------------------------------------------------
# Source: reachability, from the reachability READER (C92, 7.2): a device not
# answering over consecutive probes, never one miss.
# ---------------------------------------------------------------------------

def reachability_source(cached=None) -> dict:
    """ONE row listing every device not answering, each with its misses and
    since when: C92 measured genuine outages six to eight devices at once (the
    path from the NMAS, not each device), and nine rows would bury that. The
    claim names the probe (on the host, a TCP connection to port 22)."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached("reachability") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("reachability", "Reachability", read_at=started, took_ms=took,
                             error=f"not probed yet: {why}")
    v = good.get("value") or {}
    down = sorted((d for d in (v.get("devices") or {}).values() if not d.get("answering")),
                  key=lambda d: d.get("since") or "")
    rows = []
    if down:
        names = [d.get("hostname") or d.get("address") for d in down]
        rows.append(row(
            source="reachability", key="not-answering", level="danger",
            what=(f"{names[0]} is not answering" if len(down) == 1
                  else f"{len(down)} devices are not answering"),
            devices=names, since=_ts(down[0].get("since")),
            cause="; ".join(f"{d.get('hostname') or d.get('address')} ({d.get('address')}): "
                            f"{d.get('consecutive_misses')} consecutive misses, the threshold is "
                            f"{d.get('threshold')}; {d.get('claim')}" for d in down)
                  + (". Several at once is more often the path from the NMAS than each device"
                     if len(down) > 1 else ""),
            operands={"probe": "ICMP, then TCP 22"},
            action={"label": "Check the path from the NMAS first when several stop together; "
                             "one alone, its own management interface",
                    "known": False}))
    c = v.get("counts") or {}
    return source_result(
        "reachability", "Reachability", read_at=started, took_ms=took, rows=rows,
        value_at=_ts(good.get("value_at")), stale_after_seconds=doc.get("stale_after_seconds"),
        reader="reachability",
        checked=(f"{c.get('answering', 0)} answering, {c.get('not_answering', 0)} not answering"
                 + (f", {c.get('missed_last_probe', 0)} missed only the last probe"
                    if c.get("missed_last_probe") else "")))


def netbox_secrets_source(cached=None) -> dict:
    """A credential NetBox holds in a device's stored config context is a live
    exposure in a shared system (the operator, 2026-09-29): one row per device,
    naming the slot kinds and never a value, with the action that can clear it.
    Where NMAS recorded writing the context it may mask it; where it did not,
    it is somebody's data, and the row says to remove it in NetBox."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached("netbox-secrets") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("netbox-secrets", "NetBox stored credentials", read_at=started,
                             took_ms=took, error=f"not read yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    if not v.get("configured"):
        return source_result("netbox-secrets", "NetBox stored credentials", read_at=started,
                             took_ms=took, value_at=value_at, stale_after_seconds=promise,
                             reader="netbox-secrets",
                             checked=f"no NetBox configured ({v.get('why') or 'no reason'}): "
                                     "nothing to hold one")
    rows = []
    for d in v.get("devices") or []:
        name = d.get("name") or f"device {d.get('id')}"
        held = ", ".join(d.get("slots") or []) or "a credential"
        comm = d.get("communities") or 0
        cause = (f"NetBox device {d.get('id')} ({name}) holds {held} unmasked in its stored "
                 f"config context" + (f", and {comm} structured SNMP community value(s)"
                                      if comm else "")
                 + ": readable by everyone who can read NetBox")
        if d.get("record_unreadable"):
            cause += (f". Whether NMAS wrote it cannot be told: the modification record is "
                      f"unreadable ({d['record_unreadable']})")
            action = {"label": "The reason above is what is known", "known": False}
        elif d.get("wrote"):
            cause += f". NMAS wrote this context ({d['wrote']}), so it may mask it"
            action = {"label": "Mask it with the import's own masking, read back",
                      "command": f"nmas-netbox-mask-context --device {name} --apply"}
        else:
            cause += ". NMAS has no record of writing it, so it is somebody's data and NMAS "
            cause += "will not change it"
            action = {"label": f"Remove the credential lines from {name}'s config context in "
                               "NetBox by hand"}
        rows.append(row(source="netbox-secrets", key=f"netbox:{d.get('id')}", level="danger",
                        what=f"NetBox holds a credential for {name}", devices=[name],
                        cause=cause, operands={"netbox_id": d.get("id")}, action=action))
    return source_result(
        "netbox-secrets", "NetBox stored credentials", read_at=started, took_ms=took,
        rows=rows, value_at=value_at, stale_after_seconds=promise, reader="netbox-secrets",
        checked=f"{v.get('scanned', 0)} NetBox device(s) scanned, "
                f"{len(v.get('devices') or [])} holding a credential")


# ---------------------------------------------------------------------------
# Source: history committed and not on its remote (C223)
# ---------------------------------------------------------------------------

_PUSHED_LEVEL = {"behind": "warning", "behind_unfetched": "warning", "not_on_remote": "warning"}


def pushed_source(cached=None) -> dict:
    """The host running something other than what is pushed (the operator,
    2026-09-30: the commit left the top bar, so when it is wrong it is here),
    from the `app-pushed` reader: this process's commit against origin/main,
    asked by `git ls-remote`. Quiet at the tip; a row when behind or off it."""
    from modules import reader_job
    from modules.readers import app_pushed
    from routes import health

    started = time.time()
    got = reader_job.read_cached("app-pushed") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    label = "Running commit against origin/main"
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("pushed", label, read_at=started, took_ms=took,
                             error=f"not compared yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    running = str(v.get("running") or "")
    if running != str(health._COMMIT or ""):
        return source_result("pushed", label, read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise,
                             checked=f"the stored comparison is for {running[:10]}, not the running "
                                     f"{str(health._COMMIT)[:10]}: not compared yet")
    rows = []
    if v.get("state") in _PUSHED_LEVEL:
        from modules import update_op

        sentence = app_pushed.words(v)
        # THE UPDATE BUTTON (the operator, 2026-09-30): the app knows it is out
        # of date, so its action is the Update operation, never a terminal.
        tip = str(v.get("tip") or "")
        action = ({"label": f"Update to {tip[:10]}: preview the commits and CI's verdict, "
                            "then confirm", "open": "app_update"}
                  if v["state"] != "not_on_remote" else
                  {"label": "The host should run only pushed commits: find where this one came "
                            "from before updating over it", "known": False})
        cause = (f"origin/{v.get('branch') or 'main'} was asked with git ls-remote; "
                 "the host moves only when a person updates it")
        last = (update_op.outcome().get("value") or {})
        level = _PUSHED_LEVEL[v["state"]]
        if last.get("outcome") in ("refused", "rolled_back", "rollback_failed", "failed") \
                and last.get("from") == running:
            # One event, one row: the update that did not happen is this row's
            # cause, not a second row beside it.
            cause += (f". The last update, to {str(last.get('to') or '?')[:10]} by "
                      f"{last.get('requested_by') or '?'}, "
                      f"{update_op.OUTCOME_WORDS.get(last['outcome'], last['outcome'])} "
                      f"({last.get('ended_at') or last.get('at') or '?'}): {last.get('reason')}")
            if last["outcome"] == "rollback_failed":
                level = "danger"
        rows.append(row(source="pushed", key=running[:10], level=level,
                        what=sentence[0].upper() + sentence[1:],
                        since=_ts(v.get("behind_since")),
                        cause=cause, action=action))
    return source_result("pushed", label, read_at=started, took_ms=took, rows=rows,
                         value_at=value_at, stale_after_seconds=promise, reader="app-pushed",
                         checked=app_pushed.words(v))


def remote_source(cached=None) -> dict:
    """A list whose commits are not on its remote, from the `remote-publication`
    reader: HEAD against the remote's own branch, asked by `git ls-remote`,
    never the push hook's record (C223: abandon's commit never reached the
    hook, and the hook's record said nothing). Its sentence is
    `remote_publication.describe()`, the one the Git tab and the Remote card
    draw. An unreadable remote record (C172) is named on the row."""
    from modules import reader_job
    from modules.readers import remote_publication as P

    started = time.time()
    got = reader_job.read_cached(P.READER.name) if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("remote", "Publication to the remote", read_at=started,
                             took_ms=took, error=f"not read yet: {why}")
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    lists = (good.get("value") or {}).get("lists") or {}
    rows, fine = [], []
    for name, pub in sorted(lists.items()):
        said = P.describe(pub, now=started)
        if said["state"] in ("in_sync", "no_remote") and said["level"] == "success":
            fine.append(name)
            continue
        if said["state"] == "no_remote":
            continue
        remote = pub.get("remote") or "its remote"
        if said["state"] == "ahead":
            what = f"{pub.get('ahead', 0)} commit(s) on {name} not pushed to {remote}"
            since = pub.get("oldest_at")
            action = {"label": "Push now, on the Remote card: the Devices tab, below the "
                               "device list, in the golden repository section. The next "
                               "commit's push also sends every commit before it. If it does "
                               "not go, the card names the failure"}
        elif said["state"] == "in_sync":
            # In step today, and the record the push hook reads cannot be read,
            # so the NEXT commit will not be pushed (C172).
            what = f"{name}'s remote record cannot be read, so its next commit will not be pushed"
            since = None
            action = {"label": "Repair or re-adopt the list's remote from the Remote card (the "
                               "Devices tab, below the device list); the record is "
                               "data/lists/<list>/remote.json on the host"}
        elif said["state"] in ("remote_ahead", "diverged"):
            what = f"{name}'s history and {remote} do not match"
            since = None
            action = {"label": "Resolve it by hand on the host: NMAS never force-pushes, so "
                               "compare the two histories and decide which is the record"}
        else:
            what = f"Whether {name}'s history is on {remote} is not known"
            since = None
            action = {"label": "Read the reason: it names what could not be asked. A remote "
                               "that cannot be asked also cannot be pushed to"}
        rows.append(row(
            source="remote", key=f"{name}:{said['state']}", level=(
                "danger" if said["level"] == "danger" else "warning"),
            what=what, cause=f"{name}: {said['clause']}. {said['detail']}".strip(),
            action=action, since=since,
            operands={"list": name, "head": str(pub.get("head", ""))[:7],
                      "remote_head": str(pub.get("remote_head", ""))[:7],
                      "not_pushed": str(pub.get("ahead", "")), "record": pub.get("record", "")}))
    return source_result(
        "remote", "Publication to the remote", read_at=started, took_ms=took, rows=rows,
        value_at=value_at, stale_after_seconds=promise, reader=P.READER.name,
        checked=(f"{len(lists)} list repository(ies) compared with their remote's branch; "
                 f"published: {', '.join(fine) or 'none'}"))


SOURCES = (job_health_source, drift_source, approvals_source, pending_onboarding_source,
           rollback_source, deploy_source, baseline_source, authorisation_source,
           grafana_source, freshness_source, integrations_source, ci_source,
           reachability_source, netbox_secrets_source, remote_source, pushed_source)


def _attach(rows: list) -> list:
    """Fold each row that is ABOUT another row into it (NSOT_PLAN 8.6: two
    rows about one event is the three-reports problem). The target keeps its
    own cause and takes the attached row's action, since a queued item is the
    prepared path to the fix; an attached row whose target is absent stands
    alone."""
    by_id = {r["id"]: r for r in rows}
    kept = []
    for r in rows:
        target = by_id.get(r.get("attach_to") or "")
        if target is None or target is r:
            kept.append(r)
            continue
        target["attached"].append({"source": r["source"], "what": r["what"],
                                   "since": r["since"]})
        target["action"] = r["action"]
    return kept


def needs_attention(sources=None) -> dict:
    """The page: every row from every source, worst first, and every source
    with its read time, so an empty page says what it looked at."""
    results = []
    for src in (SOURCES if sources is None else sources):
        try:
            results.append(src())
        except Exception as exc:                   # noqa: BLE001
            # A source whose ADAPTER raised is still a row, never an absence.
            name = getattr(src, "__name__", "source")
            log.error("attention: source %s raised: %s", name, exc)
            results.append(source_result(name, name, read_at=time.time(), took_ms=0,
                                         error=f"its adapter raised {type(exc).__name__}: {exc}"))
    rows = _attach([r for res in results for r in res["rows"]])
    rows.sort(key=lambda r: (LEVELS.index(r["level"]), r["source"], r["id"]))
    unreadable = [res["label"] for res in results if res["state"] != "read"]
    if rows:
        headline = f"{len(rows)} thing(s) need attention"
    else:
        headline = "Nothing needs attention"
    return {"ok": True, "headline": headline, "rows": rows,
            "unreadable": unreadable,
            "sources": [{k: res[k] for k in ("source", "label", "state", "read_at",
                                             "value_at", "took_ms", "checked")}
                        | {"count": len(res["rows"])} for res in results]}
