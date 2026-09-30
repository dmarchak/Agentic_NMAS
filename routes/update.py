"""routes/update.py — the Update button's JSON half (modules/update_op.py;
docs/UPDATE.md). The page is `v2.update` (routes/v2.py); these are what it
calls.

- POST /update/apply   confirm by the preview's hash: writes the REQUEST the
                       root-owned updater acts on (gate `confirm`, a person);
- GET  /update/status  what runs, what waits, what the updater last said: the
                       waiting page reads it beside /health;
- POST /update/check   runs the `app-pushed` reader now, on a thread, as the
                       person's request (reader_job rule 13), so a person need
                       not wait for its next run after a push; the answer is
                       announced even when nothing changed, and the reply names
                       the run and how long the page waits before calling it late.
"""

import logging
import time

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("update", __name__, url_prefix="/update")


@bp.route("/apply", methods=["POST"])
def apply():
    from modules import identity, update_op

    data = request.get_json(silent=True) or {}
    got = update_op.request(str(data.get("hash") or ""),
                            [str(a) for a in (data.get("acknowledged") or []) if a],
                            identity.request_actor())
    if not got["ok"]:
        return jsonify({"ok": False, "error": got["reason"]}), 409
    return jsonify(dict(got, message=(
        f"Requested: the updater re-checks CI for {got['target'][:10]} itself, moves the "
        "checkout, restarts the app and confirms the new commit, or rolls back. This page "
        "waits on /health for the new commit."))), 202


@bp.route("/status", methods=["GET"])
def status():
    from modules import update_op

    return jsonify(dict(update_op.status(), ok=True))


@bp.route("/check", methods=["POST"])
def check():
    """Run the reader now, once; a second press while it runs is told so."""
    from modules import reader_job
    from modules.readers import app_pushed

    if not reader_job.running(app_pushed.READER.name):
        return jsonify({"ok": False, "error": (
            "the reader jobs do not run in this process, so nothing was asked; the app's "
            f"own reader asks every {app_pushed.INTERVAL_SECONDS} s")}), 409
    from modules import identity

    who = identity.viewer()
    # Recorded as the person's request (reader_job rule 13), announced even
    # when the answer did not change, because this person is waiting on it.
    got = reader_job.request_run(app_pushed.READER, who.actor if who.is_identified else "",
                                 announce=reader_job.announce_via_page)
    bound = reader_job.answer_bound(app_pushed.READER.name)
    # An age, never an epoch: the browser's clock is not the host's.
    body = {"ok": True, "started": got["started"], "run": got["run"],
            "running_for": round(time.time() - got["since"], 1),
            "bound_seconds": bound["seconds"], "bound_basis": bound["basis"],
            "message": ("asking origin and CI now; this stays busy until the answer arrives"
                        if got["started"] else
                        "a check is already running; this waits for its answer")}
    return jsonify(body), (202 if got["started"] else 200)
