"""Scheduled-job health: a host job tells the app it finished.

Job health itself is read by the job-health reader (modules/readers/job_health_reader.py),
whose stored value Needs attention draws; `nmas-jobs` asks it live on the host. The live JSON
read, GET /jobs/health, left at 7.8 on 2026-10-15: no page called it.
"""

import logging

from flask import Blueprint, jsonify

log = logging.getLogger(__name__)

bp = Blueprint("jobs", __name__, url_prefix="/jobs")


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
    # The readers whose source this job WRITES are read now too (the operator,
    # 2026-10-01: a reader read two minutes before a job rewrote its source,
    # and its rows stood for another ten).
    woke = []
    for name in WAKES.get(unit, ()):
        reader = next((r for r in reader_job.readers() if r.name == name), None)
        if reader is not None and reader_job.running(name):
            reader_job.request_run(reader, unit, kind="job_finished",
                                   announce=reader_job.announce_via_page)
            woke.append(name)
    return jsonify({"ok": True, "unit": unit, "started": got["started"], "run": got["run"],
                    "woke": woke}), (202 if got["started"] else 200)


#: A job -> the readers whose source it writes, read when it finishes. None today: the one
#: entry was the lab's sync waking the lab-startup reader, and both left the product (C663).
WAKES: dict = {}
