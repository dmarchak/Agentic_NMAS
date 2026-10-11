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


def _op_region(op: dict, code: int = 200):
    """The Reservations tab with board B's card in place: the region for htmx, the whole page
    for a direct visit (the link without script, a bookmark)."""
    from modules import dhcp_reservations as D
    from modules.preview_confirm import confirm_part

    ctx = _ctx()
    ctx["g"]["s"] = dict(ctx["g"]["s"], tab="res")
    extra = dict(op=op, offered=D.OFFERED, words=D.WORDS, may=confirm_part(request, "confirm"))
    if not request.headers.get("HX-Request"):
        from routes.v2 import _page
        return _page("v2/dhcp.html", active_nav="dhcp", list_name=_list_name(), **extra,
                     **ctx), code
    return _strict(render_template("v2/_dhcp_view.html", **extra, **ctx), code)


@bp.route("/reservation", methods=["GET"])
def reservation_preview():
    """Board B's card in place of the Reservations tab: the form (Add, Edit) and, once it names
    the reservation, the preview: the change, its checks, what it does not do, and its hash.
    A read: Kea is asked and Mercury's file read; nothing is written."""
    from modules import dhcp_reservations as D

    s = D.ask(request.args)
    filled = s["op"] == "remove" or (s["family"] and s["subnet"] and s["identity"] and
                                     s["address"])
    p = D.plan(_list_name(), request.args) if filled else None
    return _op_region({"state": "preview" if filled else "form", "ask": s, "plan": p,
                       "subnets": _op_subnets()})


@bp.route("/reservation", methods=["POST"])
def reservation_confirm():
    """Apply the previewed change as the verified person, bound to the preview's hash: write
    Mercury's file for the subnet, reload Kea, read it back, record; the result in place."""
    from modules import dhcp_reservations as D
    from modules import identity

    actor = identity.request_actor()
    got = D.apply(_list_name(), request.form, request.form.get("hash", ""), actor=actor,
                  reason=request.form.get("reason", ""))
    s = D.ask(request.form)
    if not got["ok"]:
        return _op_region({"state": "refused", "ask": s, "plan": got.get("plan"),
                           "result": got, "subnets": _op_subnets(),
                           "reason": request.form.get("reason", "")},
                          409 if not got.get("rolled_back") else 502)
    return _op_region({"state": "done", "ask": s, "plan": got["plan"], "result": got,
                       "actor": actor, "subnets": _op_subnets()})


def _op_subnets() -> list:
    """The subnets a reservation can be made in, from the DHCP reader's stored value: every
    subnet of both families but ZTP's (onboarding's)."""
    from modules import dhcp_page

    st = dhcp_page.stored(_list_name())
    out = []
    for svc, fam in sorted(((st.get("value") or {}).get("families") or {}).items()):
        for sub in fam.get("subnets") or []:
            if not sub.get("ztp"):
                out.append({"family": fam.get("words", svc), "id": sub.get("id"),
                            "prefix": sub.get("prefix", "")})
    return out
