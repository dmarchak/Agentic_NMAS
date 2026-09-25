"""Scheduled-job health: are the jobs NMAS depends on succeeding?

A READ that reports. It never withholds on a degraded state -- a job that is
failing, stale or not installed is exactly what this answers -- and a
systemctl or journal it cannot ask is reported as ``unknown``, never ``ok``.
"""

import logging

from flask import Blueprint, jsonify

log = logging.getLogger(__name__)

bp = Blueprint("jobs", __name__, url_prefix="/jobs")


@bp.route("/health", methods=["GET"])
def jobs_health():
    from modules.job_health import health
    return jsonify(health())
