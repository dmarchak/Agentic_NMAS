"""routes/topology_v2.py — OBSERVE › Topology (P.11 step 2; NSOT_TOPOLOGY_BRIEF, boards A to C
signed off 2026-10-04).

How each network is connected, layer by layer, and where it is weak: drawn from the topology
reader's stored value (modules/topology_page.py), never read per request. The map region
redraws when the reader announces `topology`; a layer, a path trace or a search asks for the
region again with its question. Marking an island expected is a verified person's act, with a
reason, recorded (modules/topology_expected.py).
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("topology_v2", __name__, url_prefix="/v2/topology")


def _list_name() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return (request.form.get("list") or "").strip() or named_list(request) or \
        listref.active().name


def _ctx(**extra) -> dict:
    from modules import topology_page
    from modules.preview_confirm import confirm_part

    v = topology_page.view(_list_name(), (request.values.get("layer") or "physical").strip(),
                           (request.values.get("a") or "").strip(),
                           (request.values.get("b") or "").strip(),
                           (request.values.get("q") or "").strip())
    return dict({"t": v, "may": confirm_part(request, "configure")}, **extra)


def _region(code: int = 200, **extra):
    return _strict(render_template("v2/_topology_map.html", **_ctx(**extra)), code)


@bp.route("", methods=["GET"])
def page():
    """The page. A read: the reader's stored value, drawn."""
    from routes.v2 import _page

    return _page("v2/topology.html", active_nav="topology", list_name=_list_name(), **_ctx())


@bp.route("/map", methods=["GET"])
def region():
    """The map region alone: re-read when `topology` is announced, and asked again with a
    layer, a path trace or a search. Writes nothing."""
    return _region()


@bp.route("/expected", methods=["GET"])
def expected_form():
    """Mark as expected…: the reason asked for, in place; nothing written."""
    return _region(op={"state": "form", "device": (request.args.get("device") or "").strip()})


@bp.route("/expected", methods=["POST"])
def expected_declare():
    """Declare an island expected, with why, as the verified person; recorded."""
    from modules import identity, topology_expected

    device = (request.form.get("device") or "").strip()
    got = topology_expected.declare(_list_name(), device, request.form.get("reason", ""),
                                    identity.request_actor())
    if not got["ok"]:
        return _region(400, op={"state": "form", "device": device, "refused": got["error"],
                                "reason": request.form.get("reason", "")})
    return _region(op=dict(got, state="declared", device=device))


@bp.route("/expected/withdraw", methods=["POST"])
def expected_withdraw():
    """Withdraw a declaration, as the verified person: the island warns again; recorded."""
    from modules import identity, topology_expected

    device = (request.form.get("device") or "").strip()
    got = topology_expected.withdraw(_list_name(), device, identity.request_actor())
    if not got["ok"]:
        return _region(409, op={"state": "refused", "device": device, "refused": got["error"]})
    return _region(op=dict(got, state="withdrawn", device=device))
