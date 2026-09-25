"""Are the scheduled jobs NMAS depends on actually succeeding?

Measured 2026-09-25: ``clab-sync.service`` failed every 30 minutes for ~36
hours (72 runs) with ``nmas-clab-targets: command not found``. The script
refused correctly, into a journal nobody read, and r6's startup config fell a
day behind its branch-site config. The evidence was durable and nothing
surfaced it -- the third such place in one session.

So each job NMAS depends on is DECLARED here with the age its last success
may reach, and this reads systemd and the journal and says, per job:

* ``ok`` -- the last run succeeded and the last success is recent enough;
* ``failing`` -- the last run failed; with how many in a row, since when,
  and the job's own last error line (its reason, not systemd's summary);
* ``stale`` -- nothing has failed, and nothing has succeeded recently either:
  a timer stopped, disabled, or never firing;
* ``never_succeeded`` -- failures in the journal window and no success;
* ``not_installed`` -- **never ok**: measured, systemd reports
  ``Result=success`` for a unit that does not exist, so a check reading
  ``Result`` alone calls a job that was never installed healthy.

A job NMAS depends on and cannot see is the failure this exists to catch, so
a systemctl or journal that cannot be asked is ``unknown``, never ``ok``.
"""

import logging
import subprocess
import time

log = logging.getLogger(__name__)

#: The jobs, what they are for, and how old their last success may get
#: (a few missed runs, never one). A job added to the host without a line
#: here is invisible -- adding it is part of installing it.
JOBS = (
    {"unit": "clab-sync", "max_age_minutes": 90,
     "what": "Oxidized configs into containerlab startup files, every 30 min"},
    {"unit": "nmas-netbox-backup", "max_age_minutes": 180,
     "what": "NetBox dump + config, hourly (NSOT_PLAN P.2)"},
    {"unit": "nmas-netbox-restore-test", "max_age_minutes": 50 * 60,
     "what": "NetBox restore into a scratch postgres, daily (P.2)"},
    {"unit": "nmas-heartbeat-check", "max_age_minutes": 180,
     "what": "each device's heartbeat window still fits its measured rate, hourly (C16)"},
)

JOURNAL_DAYS = 14

import re as _re

_NAMES_A_FAILURE = _re.compile(
    r"not found|REFUSED|FAILED|ERROR|Error|Traceback|denied|No such", _re.I)


def _run(cmd: list) -> tuple:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def _show(unit: str, run) -> dict:
    rc, out = run(["systemctl", "show", unit, "-p", "LoadState",
                   "-p", "ActiveState", "-p", "Result", "-p", "ExecMainStatus"])
    if rc != 0:
        return {}
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def _journal(unit: str, run) -> tuple:
    """``(ok, [(unix_ts, text)])``."""
    rc, out = run(["journalctl", "-u", unit, "-o", "short-unix", "--no-pager",
                   "--since", f"-{JOURNAL_DAYS}d"])
    if rc != 0:
        return False, []
    rows = []
    for line in out.splitlines():
        head, _, rest = line.partition(" ")
        try:
            rows.append((float(head), rest))
        except ValueError:
            continue
    return True, rows


def job_status(job: dict, now: float = None, run=None) -> dict:
    # Resolved at CALL time: a default of `run=_run` is bound when the
    # function is defined, so a replaced `_run` never reaches it -- which let
    # this module's own route test pass by asking the laptop's real systemd.
    run = run or _run
    now = now or time.time()
    unit = job["unit"] + ".service"
    out = {"unit": job["unit"], "what": job["what"],
           "max_age_minutes": job["max_age_minutes"]}
    show = _show(unit, run)
    if not show:
        return {**out, "state": "unknown",
                "detail": "systemctl could not be asked -- not the same as ok"}
    if show.get("LoadState") == "not-found":
        return {**out, "state": "not_installed",
                "detail": f"{unit} is not installed (systemd reports "
                          f"Result={show.get('Result', '?')} for it anyway)"}
    ok, rows = _journal(unit, run)
    if not ok:
        return {**out, "state": "unknown",
                "detail": "the journal could not be read -- not the same as ok"}

    # THE CAUSE, not the last line. A refusal is several lines and its last is
    # a continuation ("...into another lab."), measured live. So each run's
    # own output is collected, and the error is its first line that names a
    # failure -- here `nmas-clab-targets: command not found` -- falling back
    # to the run's first line.
    last_ok, last_fail, streak, last_error = None, None, 0, ""
    run_lines: list = []
    for ts, text in rows:
        if "systemd[" in text:
            if "Starting " in text or "Started " in text:
                run_lines = []
        elif text.strip():
            run_lines.append(text.split(": ", 1)[-1].strip())
        if "Deactivated successfully" in text:
            last_ok, streak = ts, 0
        elif "Failed with result" in text:
            last_fail, streak = ts, streak + 1
            named = [l for l in run_lines if _NAMES_A_FAILURE.search(l)]
            last_error = (named or run_lines or [""])[0]
            run_lines = []

    def ago(ts):
        return f"{int((now - ts) // 60)} min ago" if ts else "never"

    max_age = job["max_age_minutes"] * 60
    failed_last = last_fail is not None and (last_ok is None or last_fail > last_ok)
    if failed_last and last_ok is None:
        state = "never_succeeded"
    elif failed_last:
        state = "failing"
    elif last_ok is None or now - last_ok > max_age:
        state = "stale"
    else:
        state = "ok"
    detail = (f"last success {ago(last_ok)}"
              + (f"; {streak} consecutive failure(s), last {ago(last_fail)}"
                 if failed_last else "")
              + (f"; last error: {last_error}" if failed_last and last_error else ""))
    return {**out, "state": state, "detail": detail,
            "last_success": last_ok, "last_failure": last_fail,
            "consecutive_failures": streak if failed_last else 0,
            "last_error": last_error if failed_last else "",
            "active_state": show.get("ActiveState", "")}


def health(now: float = None, run=None) -> dict:
    jobs = [job_status(j, now, run) for j in JOBS]
    bad = [j["unit"] for j in jobs if j["state"] != "ok"]
    return {"ok": True, "jobs": jobs, "not_ok": bad,
            "headline": (f"{len(jobs) - len(bad)} of {len(jobs)} job(s) ok"
                         + (f"; not ok: {', '.join(bad)}" if bad else ""))}
