"""routes/sdn_v2.py — OBSERVE › SDN: a network's SDN controllers and their switches' flows
(PHASE8_PLAN 17.1 S11; boards SdnControllers, SdnFlows and SdnPhone, signed off 2026-10-27 under
the Phase 7 mode; docs/fidelity/sdn.md).

A read: the SDN reader's stored value, drawn by modules/sdn_page.py beside the network's
connection list; never a controller call per view. The region redraws when the reader announces
`sdn`. The one action here, Test connection on a controller's card, asks that controller now
with what is saved, and answers in place; it changes nothing. The connections themselves are
edited in Settings › Integrations (the card's "Edit connection").
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("sdn_v2", __name__, url_prefix="/v2/sdn")

TABS = (("controllers", "Controllers"), ("flows", "Flows"))


def _list_name() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return named_list(request) or listref.active().name


def _ctx(tab: str) -> dict:
    from modules import sdn_page

    network = _list_name()
    g = (sdn_page.flows_view(network, request.args) if tab == "flows"
         else sdn_page.controllers_view(network))
    return {"g": g, "tabs": TABS}


@bp.route("", methods=["GET"])
def page():
    """SDN › Controllers (board SdnControllers)."""
    from routes.v2 import _page

    return _page("v2/sdn.html", active_nav="sdn", list_name=_list_name(), **_ctx("controllers"))


@bp.route("/flows", methods=["GET"])
def flows():
    """SDN › Flows (board SdnFlows)."""
    from routes.v2 import _page

    return _page("v2/sdn.html", active_nav="sdn", list_name=_list_name(), **_ctx("flows"))


@bp.route("/view", methods=["GET"])
def region():
    """The page's region alone: re-read when `sdn` is announced, and asked again with a filter.
    Writes nothing."""
    tab = request.args.get("tab") if request.args.get("tab") in dict(TABS) else "controllers"
    return _strict(render_template("v2/_sdn_view.html", **_ctx(tab)))


@bp.route("/controller/<name>/test", methods=["POST"])
def controller_test(name):
    """Test connection on a controller's card: its driver's `test()` now, with what is saved,
    drawn in place. Changes nothing; the card's state stays the reader's until its next read."""
    from modules.sdn import connections

    tested = connections.test_saved(_list_name(), name)
    return _strict(render_template("v2/_sdn_answer.html", tested=tested, name=name,
                                   list_name=_list_name()))
