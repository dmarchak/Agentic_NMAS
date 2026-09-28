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
                  value_at: float = None) -> dict:
    """One source, read. *error* makes the source a row of its own.

    *read_at* is when this request read the source; *value_at* is the time of
    the VALUE it shows (section 1a), which for a stored result (the last drift
    run) is earlier, and for a live read (job health) is the same. Collapsing
    them would draw a day-old drift run as read "just now"."""
    if error:
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
    "at_budget": ("has no SSH session left for the next operation", "warning"),
    "leaked": ("holds an operation's SSH session past ten minutes", "warning"),
    "mixed_version": ("is running a different commit from its checkout", "danger"),
    "socket_down": ("is not listening", "danger"),
    "mismatch": ("does not match what was declared", "warning"),
}


def _job_action(job: dict) -> dict:
    """The ONE action for a job-health row, where the source records one."""
    from modules import job_health as J

    systemd_units = {j["unit"] for j in J.JOBS}
    unit, state = job.get("unit", ""), job.get("state", "")
    if unit in systemd_units:
        if state == "not_installed":
            return {"label": "Install and enable the unit on the host",
                    "reference": "docs/DEPLOY_LINUX.md"}
        return {"label": "Read the job's own output on the host",
                "command": f"journalctl -u {unit}.service -n 50 --no-pager"}
    # The other row families write their remedy INTO the detail (the
    # rotation and startup rows name `nmas-persist-native`). Lifting it into
    # a separate action is 7.2's next steps; until then the row says the
    # action is in the cause rather than inventing one.
    return {"label": "The cause above is the whole of what this row records; "
                     "no separate action is recorded yet", "known": False}


def job_health_source(health=None, now=None) -> dict:
    """Every job-health row that is not ok, as a Needs attention row."""
    from modules import job_health as J

    started = time.time()
    try:
        h = (health or J.health)()
        jobs = list(h["jobs"])
    except Exception as exc:                       # noqa: BLE001
        log.error("attention: job health could not be read: %s", exc)
        return source_result("job_health", "Job health", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
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
            what=f"{job.get('unit', '?')} {words}",
            devices=[device] if device else [],
            since=job.get("since"),
            cause=job.get("detail") or f"state {state}, with no detail recorded",
            operands={"job": job.get("what", ""), "state": state},
            action=_job_action(job), level=level))
    n_ok = len(jobs) - len(rows)
    return source_result("job_health", "Job health", read_at=started, took_ms=took,
                         rows=rows,
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


#: Every source, in the order a person reads them. Section 1a's other
#: sources (freshness, Grafana alerts, failed deploys, unearned baselines)
#: join HERE, each through `source_result`.
SOURCES = (job_health_source, drift_source, approvals_source, pending_onboarding_source,
           rollback_source)


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
