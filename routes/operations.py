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

import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("operations", __name__, url_prefix="/operations")


@bp.route("/in_flight", methods=["GET"])
def in_flight():
    """``{"ok", "list", "running", "recent", "recent_state", "window_s"}``, from the one read
    every screen shares (modules/in_flight). A READ: it writes nothing.

    Asked by v2's top bar (an htmx request, C537): the In progress chip, drawn, for every
    network, as the person looking sees it (`in_flight.chip`)."""
    from modules import in_flight as F
    from modules.config import get_current_list_name
    from routes.list_param import named_list

    if request.headers.get("HX-Request"):
        return _chip()
    list_name = named_list(request) or get_current_list_name()
    try:
        got = F.read(list_name)
    except Exception as exc:                  # noqa: BLE001
        log.exception("operations: in-flight read failed for %s", list_name)
        return jsonify({"ok": False, "list": list_name,
                        "error": f"{type(exc).__name__}: {exc}"}), 500
    return jsonify({"ok": True, "list": list_name, **got,
                    "window_s": F.RECENT_SECONDS, "not_recorded": F.NOT_RECORDED})


def viewer_key() -> str:
    """Whose "not opened yet" the chip draws: the verified person looking, or "" for anyone
    not identified (who can look, and share one mark)."""
    from modules import identity

    ident = identity.viewer()
    return ident.actor if ident.is_identified else ""


def _chip():
    """The In progress chip (boards A and B): nothing while nothing runs and nothing waits to
    be opened; else the chip and its list. A read that fails is drawn as unknown, never as
    nothing running (C99)."""
    from flask import render_template

    from modules import in_flight as F
    from modules import integration_groups as IG
    from routes.device_v2 import _strict

    try:
        ip = F.chip(IG.network_names(), viewer_key())
    except Exception as exc:                      # noqa: BLE001
        log.exception("operations: the In progress chip could not be read")
        ip = {"error": f"{type(exc).__name__}: {exc}", "shown": True, "level": "danger",
              "words": "could not be read", "running": [], "finished": [], "unread": [],
              "counts": {}}
    resp = _strict(render_template("v2/_in_progress.html", ip=ip))
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Vary"] = "HX-Request"
    return resp
