"""routes/logs_v2.py — OBSERVE › Logs: the network's syslog by device (C652; History › Query board
C, AskLogs, signed off 2026-10-04).

The sidebar's Logs opens it (the operator, 2026-10-10: "the queryable logs as approved on the
canvas mock up, not the app's own logs"; Mercury's own log stays in Settings › Installation ›
Diagnostics). The counts are the logs reader's, stored (modules/logs_page.py); a device opened
asks Loki for its lines, a read. The region redraws when the reader announces `logs`, with its
question.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("logs_v2", __name__, url_prefix="/v2/logs")


def _list_name() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return named_list(request) or listref.active().name


def _ctx() -> dict:
    from modules import logs_page
    return {"g": logs_page.view(_list_name(), request.args)}


@bp.route("", methods=["GET"])
def page():
    """The page. A read: the stored counts, and a device's lines when one is opened."""
    from routes.v2 import _page

    return _page("v2/logs.html", active_nav="logs", list_name=_list_name(), **_ctx())


@bp.route("/view", methods=["GET"])
def region():
    """The view alone: re-read when `logs` is announced, and asked again with a range, a
    severity, a device opened or its filters. Writes nothing."""
    return _strict(render_template("v2/_logs_view.html", **_ctx()))
