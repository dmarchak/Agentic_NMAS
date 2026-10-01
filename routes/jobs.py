"""Scheduled-job health: are the jobs NMAS depends on succeeding?

A READ that reports. It never withholds on a degraded state -- a job that is
failing, stale or not installed is exactly what this answers -- and a
systemctl or journal it cannot ask is reported as ``unknown``, never ``ok``.

It is a LIVE read, the ask-now diagnostic, and costs what the read costs
(9.8 s on the host, 2026-09-28). Pages read the job-health reader's stored
value instead (modules/readers/job_health_reader.py).
"""

import logging

from flask import Blueprint, jsonify

log = logging.getLogger(__name__)

bp = Blueprint("jobs", __name__, url_prefix="/jobs")


@bp.route("/health", methods=["GET"])
def jobs_health():
    from modules.job_health import health
    return jsonify(health())


@bp.route("/finished", methods=["POST"])
def job_finished():
    """A host job just ended: read job health NOW, not at the reader's next run.

    The operator, 2026-10-01: the startup check succeeded at 07:23, `nmas-jobs`
    read ok at 07:25, and Needs attention showed its old Critical row until the
    reader's next scheduled run about 07:30. Each job's unit names
    `nmas-job-finished@%N.service` in `OnSuccess=` and `OnFailure=`, which
    systemd starts after the job's result is recorded (a job a person starts by
    hand included), and that unit's `scripts/nmas-job-finished` posts here. The
    run is recorded with its cause (`job_finished`, by the unit) and announced
    whatever it found, so an open page redraws. It reads, and moves nothing; a
    second post while a run is going joins that run. Only a declared job's
    unit is accepted, so the cause recorded is one this app knows."""
    from flask import request

    from modules import job_health, reader_job
    from modules.readers import job_health_reader

    unit = str((request.get_json(silent=True) or {}).get("unit") or "").strip()
    unit = unit[:-len(".service")] if unit.endswith(".service") else unit
    declared = sorted(j["unit"] for j in job_health.JOBS)
    if unit not in declared:
        return jsonify({"ok": False, "error": (
            f"{unit or 'no unit'} is not a job this app reads; the declared jobs are "
            + ", ".join(declared))}), 400
    if not reader_job.running(job_health_reader.READER.name):
        return jsonify({"ok": False, "error": (
            "the reader jobs do not run in this process, so nothing was read; the app's own "
            f"reader reads job health every {job_health_reader.INTERVAL_SECONDS} s")}), 409
    got = reader_job.request_run(job_health_reader.READER, unit, kind="job_finished",
                                 announce=reader_job.announce_via_page)
    log.info("jobs: %s finished; job health %s (run %s)", unit,
             "read now" if got["started"] else "already being read", got["run"])
    return jsonify({"ok": True, "unit": unit, "started": got["started"], "run": got["run"]}), \
        (202 if got["started"] else 200)
