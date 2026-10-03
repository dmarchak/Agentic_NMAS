"""Rotate a device's login credential from the Device page (7.3).

`modules/nsot/rotate_op.py` runs it; `scripts/nmas-rotate-credential` is the
other entry point into the same `credential_rotation`. The apply is a JOB:
rotate plus persist can pass the 100 s edge limit, and a request that dies
mid-rotation must not be the only thing that knew.
"""

import logging

from flask import Blueprint, jsonify, request

from modules.identity import request_actor

log = logging.getLogger(__name__)

bp = Blueprint("rotate", __name__, url_prefix="/rotate")


def _args(data: dict, *, carried: bool):
    from modules.config import get_current_list_name

    list_name = (data.get("list_name") or "").strip()
    if not list_name and not carried:
        list_name = get_current_list_name()
    return list_name, (data.get("device") or "").strip()


@bp.route("/preview", methods=["POST"])
def preview():
    """The plan: the preflight (which READS the device's account line, live),
    the masked program and the fingerprint. Changes nothing."""
    from modules.nsot import rotate_op
    from modules.nsot.device_ops import busy_text
    from modules.outbound import mask_payload
    from modules.preview_confirm import rotate_preview

    list_name, device = _args(request.get_json(silent=True) or {}, carried=False)
    if not device:
        return jsonify({"ok": False, "error": "No device named: nothing to preview"}), 400
    p = rotate_op.plan(list_name, device)
    return jsonify(mask_payload({
        "ok": True, "list": list_name,
        "preview": rotate_preview(p, busy=busy_text(list_name, device), request=request)}))


@bp.route("/apply", methods=["POST"])
def apply():
    """Start the confirmed rotation as a job, as the verified person. The plan
    is computed again first; a different fingerprint refuses with nothing sent
    and no job started. Answers 202 with the job's id."""
    from modules import identity
    from modules.nsot import rotate_op

    data = request.get_json(silent=True) or {}
    list_name, device = _args(data, carried=True)
    if not list_name:
        return jsonify({"ok": False, "error": (
            "No list named: a rotation records into one list's inventory and repository, so "
            "the list comes from the preview that was confirmed, never from whichever list is "
            "active. Nothing was sent.")}), 400
    confirmed = (data.get("fingerprint") or "").strip()
    if not device or not confirmed:
        return jsonify({"ok": False, "error": "Nothing confirmed: nothing was sent"}), 400
    got = rotate_op.confirm_and_start(list_name, device, confirmed, actor=request_actor(),
                                      ident=identity.verified_identity())
    if "error" in got:
        return jsonify({"ok": False, "error": got["error"]}), got["status"]
    job = got["job"]
    return jsonify({"ok": True, "job": job, "list": list_name, "running": True,
                    "note": ("The rotation runs as a job: this window can close. The in-flight "
                             "panel shows it; its result is read by id when it finishes.")}), 202


@bp.route("/result/<job>", methods=["GET"])
def result(job):
    """A rotation job's result by id: running, finished with its result, or
    failed with its reason. A job this server has no record of says so: a
    restart loses the job, and the device's rotation row and any staged
    credential (nmas-rotation-recover) are then the record."""
    from modules.nsot import capture_job

    got = capture_job.get(job)
    if got is None:
        return jsonify({"ok": False, "state": "unknown", "error": (
            "This server has no record of that rotation job: it expired, or the server "
            "restarted. The device's rotation row on Needs attention says what the last "
            "rotation reached, and a credential it staged and never cleared is named there "
            "with the command that settles it.")}), 404
    if got["state"] == "running":
        return jsonify({"ok": True, "state": "running", "elapsed_s": got["elapsed_s"]})
    if got["state"] == "failed":
        return jsonify({"ok": False, "state": "failed", "error": (
            f"The rotation job raised: {got['error']}. What it reached is in the device's "
            "rotation row, and a staged credential is named there with its command.")}), 500
    return jsonify({**(got.get("payload") or {}), "state": "done"})
