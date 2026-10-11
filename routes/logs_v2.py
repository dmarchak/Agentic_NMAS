"""routes/logs_v2.py — OBSERVE › Logs: the network's syslog as it arrives (C675; board D,
LogsTail, drawn 2026-10-11 under the Phase 7 mode), and the region of History › Query's Syslog by
device (C652; board C, AskLogs).

`/v2/logs` is the sidebar's Logs, the live tail (the operator, 2026-10-11): the logs-tail
reader's stored 15-minute window, filtered (modules/logs_tail_page.py), redrawn when the reader
announces `logs`. `/v2/logs/view` is Syslog by device's region, which History › Query draws
(modules/logs_page.py: the logs reader's counts; a device opened asks Loki for its lines, a
read). Mercury's own log stays in Settings › Installation › Diagnostics.
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


def _tail_ctx() -> dict:
    from modules import logs_tail_page
    return {"g": logs_tail_page.view(_list_name(), request.args)}


@bp.route("", methods=["GET"])
def page():
    """The sidebar's Logs: the network's syslog as it arrives (C675; the operator, 2026-10-11:
    a live tail; board D). The logs-tail reader's stored window, filtered; never a Loki call per
    view. Syslog by device is History › Query's (C667)."""
    from routes.v2 import _page

    return _page("v2/logs.html", active_nav="logs", list_name=_list_name(), **_tail_ctx())


@bp.route("/tail", methods=["GET"])
def tail():
    """The live tail's region alone: re-read when `logs` is announced, and asked again with a
    filter, Pause or Resume. Writes nothing."""
    return _strict(render_template("v2/_logs_tail.html", **_tail_ctx()))


@bp.route("/view", methods=["GET"])
def region():
    """The view alone: re-read when `logs` is announced, and asked again with a range, a
    severity, a device opened or its filters. Writes nothing."""
    return _strict(render_template("v2/_logs_view.html", **_ctx()))
