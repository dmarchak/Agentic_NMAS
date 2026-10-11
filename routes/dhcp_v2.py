"""routes/dhcp_v2.py — SOURCE OF TRUTH › DHCP: one network's Kea (C529 step 1; board A, "Item 5,
DHCP on v2", approved 2026-10-06; docs/fidelity/dhcp.md).

A read: the DHCP reader's stored value, drawn by modules/dhcp_page.py; never a Kea call per
view. The region redraws when the reader announces `dhcp`, with its question.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("dhcp_v2", __name__, url_prefix="/v2/dhcp")


def _list_name() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return named_list(request) or listref.active().name


def _ctx() -> dict:
    from modules import dhcp_page
    return {"g": dhcp_page.view(_list_name(), request.args)}


@bp.route("", methods=["GET"])
def page():
    """The page. A read: the reader's stored value, drawn."""
    from routes.v2 import _page

    return _page("v2/dhcp.html", active_nav="dhcp", list_name=_list_name(), **_ctx())


@bp.route("/view", methods=["GET"])
def region():
    """The page's region alone: re-read when `dhcp` is announced, and asked again with a tab, a
    filter, a search or a group opened. Writes nothing."""
    return _strict(render_template("v2/_dhcp_view.html", **_ctx()))
