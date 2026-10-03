"""What is running on this list's devices now, and what finished recently.

Register C99: a restore ran for fifty seconds with nothing on screen, the
operator concluded it had staged something, started a deploy of the same
device, and the silence produced a second change (C98's hole). The standing
rule that followed: every process tells the person what happened or what to
do next, and one that is still RUNNING says so, since when, and what it is
waiting on.

One read serves every screen: C98's per-device lock already records who holds
each device, since when, and its last progress step, across processes (the
CLIs included). Operations that FINISHED in the last half hour come from their
receipts, so a reload in the middle of one no longer loses its result.
"""

import calendar
import logging
import time

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("operations", __name__, url_prefix="/operations")

#: How far back "finished recently" reaches. Long enough to outlive a reload
#: and a coffee; short enough that the panel is about now.
RECENT_SECONDS = 1800


def _recent(list_name: str, now: float) -> tuple:
    """``(rows, state)`` from the receipts: deploy and restore, per device.
    A capture writes no receipt (its commit is its record), and says so."""
    from modules.nsot import receipts

    got = receipts.read(list_name, limit=100)
    if got["state"] != "ok":
        return [], got["state"]
    rows = []
    for r in got["rows"]:
        try:
            at = calendar.timegm(time.strptime(r.get("at", ""), "%Y-%m-%dT%H:%M:%SZ"))
        except (ValueError, OverflowError):
            continue
        if now - at > RECENT_SECONDS:
            break                                   # newest first
        rows.append({"device": r.get("device", ""), "action": r.get("action", ""),
                     "outcome": r.get("outcome", ""), "at": r.get("at", ""),
                     "actor": r.get("actor", ""), "reason": r.get("reason", ""),
                     "commit_state": r.get("commit_state", "")})
    return rows, "ok"


@bp.route("/in_flight", methods=["GET"])
def in_flight():
    """``{"ok", "list", "running", "recent", "recent_state", "window_s"}``.
    A READ: it lists lock files and reads the receipt log; it writes nothing."""
    from modules.config import get_current_list_name
    from modules.nsot import device_ops
    from routes.list_param import named_list

    list_name = named_list(request) or get_current_list_name()
    now = time.time()
    try:
        from modules import op_progress

        # An operation that holds no device (a NetBox preview or import) is
        # running too, and says so here in the same row shape.
        running = device_ops.in_flight(list_name, now) + op_progress.running(now)
        recent, state = _recent(list_name, now)
    except Exception as exc:                  # noqa: BLE001
        log.exception("operations: in-flight read failed for %s", list_name)
        return jsonify({"ok": False, "list": list_name,
                        "error": f"{type(exc).__name__}: {exc}"}), 500
    return jsonify({"ok": True, "list": list_name, "running": running,
                    "recent": recent, "recent_state": state,
                    "window_s": RECENT_SECONDS,
                    "not_recorded": ("A capture writes no receipt: its golden commit "
                                     "is its record, on the Git tab.")})
