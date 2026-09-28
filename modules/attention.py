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
        level: str, devices=(), since=None, operands: dict = None) -> dict:
    """The only constructor for a Needs attention row."""
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
            # Stage 8 attaches its triage HERE, on the row, never as a row of
            # its own (NSOT_PLAN 8.6): two rows about one event is the
            # three-reports problem restated on the page.
            "triage": None}


def source_result(source: str, label: str, *, read_at: float, took_ms: int,
                  rows=None, checked: str = "", error: str = "") -> dict:
    """One source, read. *error* makes the source a row of its own."""
    if error:
        return {"source": source, "label": label, "state": "unreadable",
                "read_at": _iso(read_at), "took_ms": took_ms,
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
            "read_at": _iso(read_at), "took_ms": took_ms, "checked": checked,
            "rows": list(rows or [])}


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


#: Every source, in the order a person reads them. Section 1a's other
#: sources (drift with coverage, freshness, Grafana alerts, approvals,
#: pending onboardings, rollback blocks, failed deploys, unearned baselines)
#: join HERE, each through `source_result`.
SOURCES = (job_health_source,)


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
    rows = [r for res in results for r in res["rows"]]
    rows.sort(key=lambda r: (LEVELS.index(r["level"]), r["source"], r["id"]))
    unreadable = [res["label"] for res in results if res["state"] != "read"]
    if rows:
        headline = f"{len(rows)} thing(s) need attention"
    else:
        headline = "Nothing needs attention"
    return {"ok": True, "headline": headline, "rows": rows,
            "unreadable": unreadable,
            "sources": [{k: res[k] for k in ("source", "label", "state", "read_at",
                                             "took_ms", "checked")}
                        | {"count": len(res["rows"])} for res in results]}
