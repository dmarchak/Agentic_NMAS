"""routes/templates_v2.py — Source of truth › Templates, approval and revocation on v2 (7.6,
boards A to C, signed off 2026-10-05; C481).

A: the network's configuration templates, each with its approval, the devices bound to it and
the one action it needs. B: Approve… runs the check on every bound device's captured
configuration and names, device by device, the comparison and every line that failed (an
unmodelled line not acknowledged in the device's committed intent links to its Intent tab's
editor); the confirm is bound to the template's fingerprint and to the check's outcome as
read. C: the result in place, the row redrawn; Revoke… asks why. Every step is
`modules/nsot/approve_op.py`'s, the code today's `/templates/approve` and `/templates/revoke`
run too. The network is named on every call (a write path carries its list). Editing and
bindings stay on today's page until their own boards. Nothing here contacts a device.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("templates_v2", __name__, url_prefix="/v2/templates")


def _list_name() -> str:
    """The network the address names (``list``, the form's on a POST), else the active one."""
    from modules.nsot import listref
    from routes.list_param import named_list

    return (request.form.get("list") or "").strip() or named_list(request) or \
        listref.active().name


def _may() -> dict:
    """Whether the viewer may approve or revoke (route_gates: approve), from the gate's own
    functions, so the screen cannot disagree with the confirm."""
    from modules import preview_confirm

    return preview_confirm.confirm_part(request, "approve")


def _known(name: str) -> bool:
    from modules.nsot import listref
    return listref.exists(name)


def _lib_ctx(name: str, op: dict = None) -> dict:
    from modules.nsot import approve_op

    return {"list_name": name, "lib": approve_op.library(name), "op": op or {},
            "may": _may()}


def _region(name: str, op: dict = None, code: int = 200):
    return _strict(render_template("v2/_templates_lib.html", **_lib_ctx(name, op)), code)


def _card(op: dict, code: int = 200):
    return _strict(render_template("v2/_template_op.html", op=op), code)


def _check_op(name: str, path: str) -> dict:
    from modules.nsot import approve_op
    return {"state": "check", "list": name, "c": approve_op.check(name, path), "may": _may()}


def _revoke_op(name: str, path: str) -> dict:
    from modules.nsot import approval, approve_op
    return {"state": "revoke", "list": name, "path": path, "may": _may(),
            "status": approval.approval_status(approve_op.repo_for(name), path)}


@bp.route("", methods=["GET"])
def page():
    """A: the network's configuration templates and their approvals; ``approve=<path>`` or
    ``revoke=<path>`` opens that card in place (each row's link, and a deep link)."""
    from routes.v2 import _page

    name = _list_name()
    if not _known(name):
        return _page("v2/templates.html", active_nav="templates", list_name=name,
                     known=False)
    approve_path = (request.args.get("approve") or "").strip()
    revoke_path = (request.args.get("revoke") or "").strip()
    op = _check_op(name, approve_path) if approve_path else \
        _revoke_op(name, revoke_path) if revoke_path else None
    return _page("v2/templates.html", active_nav="templates", known=True,
                 **_lib_ctx(name, op))


@bp.route("/table", methods=["GET"])
def table():
    """The region alone (the table, no card): what Cancel and Close put back."""
    name = _list_name()
    if not _known(name):
        return _card({"state": "refused", "list": name,
                      "why": f"No network is named {name!r}: nothing was read."}, 404)
    return _region(name)


@bp.route("/approve", methods=["GET"])
def check():
    """B: Approve…'s preview, `approve_op.check`. Writes nothing."""
    name, path = _list_name(), (request.args.get("path") or "").strip()
    if not path:
        return _card({"state": "refused", "list": name,
                      "why": "No template was named, so there is nothing to check."}, 400)
    return _card(_check_op(name, path))


@bp.route("/approve", methods=["POST"])
def approve():
    """B's confirm: approve as the verified person, bound to the fingerprint shown and the
    check as read, and commit; C, the result in place and the row redrawn."""
    from modules import identity
    from modules.nsot import approve_op

    name, path = _list_name(), (request.form.get("path") or "").strip()
    got = approve_op.approve(name, path, request.form.get("fingerprint"),
                             identity.request_actor(),
                             seen=(request.form.get("seen") or "").strip())
    if got.get("ok"):
        op = {"state": "approved", "list": name, "path": path, "r": got}
    elif got.get("check"):
        op = {"state": "check", "list": name, "c": got["check"], "may": _may(),
              "refused": got.get("error", "")}
    else:
        op = {"state": "refused", "list": name, "path": path,
              "why": got.get("error", "not approved")}
    return _region(name, op, got.get("status", 200))


@bp.route("/revoke", methods=["GET"])
def revoke_form():
    """C's Revoke…: the reason asked for, nothing written."""
    name, path = _list_name(), (request.args.get("path") or "").strip()
    if not path:
        return _card({"state": "refused", "list": name,
                      "why": "No template was named, so there is nothing to revoke."}, 400)
    return _card(_revoke_op(name, path))


@bp.route("/revoke", methods=["POST"])
def revoke():
    """Withdraw the approval with the person's reason and commit; the result in place."""
    from modules import identity
    from modules.nsot import approve_op

    name, path = _list_name(), (request.form.get("path") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    got = approve_op.revoke(name, path, reason, identity.request_actor())
    if got.get("ok"):
        op = {"state": "revoked", "list": name, "path": path, "r": got}
    else:
        op = {"state": "revoke", "list": name, "path": path, "may": _may(),
              "refused": got.get("error", "not revoked"), "reason": reason, "status": {}}
    return _region(name, op, got.get("status", 200))
