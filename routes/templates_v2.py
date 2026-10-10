"""routes/templates_v2.py — Source of truth › Templates, approval and revocation on v2 (7.6,
boards A to C, signed off 2026-10-05; C481).

A: the network's configuration templates, each with its approval, the devices bound to it and
the one action it needs. B: Approve… runs the check on every bound device's captured
configuration and names, device by device, the comparison and every line that failed (an
unmodelled line not acknowledged in the device's committed intent links to its Intent tab's
editor); the confirm is bound to the template's fingerprint and to the check's outcome as
read. C: the result in place, the row redrawn; Revoke… asks why. Every step is
`modules/nsot/approve_op.py`'s, the code today's `/templates/approve` and `/templates/revoke`
run too. The network is named on every call (a write path carries its list). Edit… (cutover
blocker 5, intent editor H's pattern) is `modules/nsot/template_edit.py`'s: checked as typed
against each governed device's committed golden, committed bound to the version opened.
Nothing here contacts a device.
"""

import logging

from flask import Blueprint, render_template, request
from html import escape

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


def _bring_op(name: str, path: str) -> dict:
    from modules.nsot import template_bring
    b = template_bring.preview(name, path)
    return {"state": "bring", "list": name, "b": b, "may": _may()}


@bp.route("/bring", methods=["GET"])
def bring_form():
    """C566, board B: Bring in the shipped version…'s preview, `template_bring.preview`: the
    diff, and what each bound device's render gains and loses. Writes nothing."""
    name, path = _list_name(), (request.args.get("path") or "").strip()
    if not path:
        return _card({"state": "refused", "list": name,
                      "why": "No template was named, so there is nothing to bring in."}, 400)
    return _card(_bring_op(name, path))


@bp.route("/bring", methods=["POST"])
def bring():
    """The confirm: the shipped file committed over the network's stale copy as the verified
    person, bound to both blobs previewed; its approvals revoked with it; the result in place."""
    from modules import identity
    from modules.nsot import template_bring

    name, path = _list_name(), (request.form.get("path") or "").strip()
    actor = identity.request_actor()
    got = template_bring.bring(name, path, request.form.get("copy_blob") or "",
                               request.form.get("shipped_blob") or "", actor)
    if got.get("ok"):
        op = {"state": "brought", "list": name, "path": path, "r": got, "actor": actor}
    else:
        op = dict(_bring_op(name, path), refused=got.get("error", "not brought in"))
    return _region(name, op, got.get("status", 200))


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
    bring_path = (request.args.get("bring") or "").strip()
    edit_path = (request.args.get("edit") or "").strip()
    if request.args.get("seed"):
        return _page("v2/templates.html", active_nav="templates", known=True,
                     **_lib_ctx(name, _seed_view(name)))
    op = _check_op(name, approve_path) if approve_path else \
        _revoke_op(name, revoke_path) if revoke_path else \
        _bring_op(name, bring_path) if bring_path else \
        dict(_editor(name, edit_path), editor=True) if edit_path else None
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


@bp.route("/rows", methods=["GET"])
def rows():
    """The table alone (C516), re-read when `templates` is announced: an approval or a
    revocation made elsewhere (another tab, a template edit that revokes) shows here without a
    reload, and the op card below it is left as it is. Writes nothing."""
    name = _list_name()
    if not _known(name):
        return _strict(f'<div class="notice notice-danger" role="alert"><p>Couldn\'t load: no '
                       f'network is named {escape(name)}, so nothing was read.</p></div>'), 404
    return _strict(render_template("v2/_templates_table.html", **_lib_ctx(name)))


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


def _edit_card(ctx: dict, code: int = 200):
    return _strict(render_template("v2/_template_edit.html", c=ctx), code)


def _editor(name: str, path: str, text: str = None, base: str = None, summary: str = "",
            refused: str = "") -> dict:
    """What the editing card draws: the template (the committed text unless *text* carries an
    edit in progress), the blob it was opened at, what it governs and what a commit revokes."""
    from modules.nsot import template_edit

    opened = template_edit.open_doc(name, path)
    if not opened.get("ok"):
        return {"state": "refused", "list": name, "path": path, "why": opened.get("error")}
    if text is None:
        text, base = opened["text"], opened["base"]
    return {"state": "editing", "list": name, "path": path, "text": text, "base": base or "",
            "last": opened["last"], "governs": opened["governs"], "revokes": opened["revokes"],
            "summary": summary, "refused": refused, "confirm": _may()}


@bp.route("/edit", methods=["GET"])
def edit_form():
    """Edit…: the template in an editor in place, checked as typed. Writes nothing."""
    name, path = _list_name(), (request.args.get("path") or "").strip()
    if not path:
        return _edit_card({"state": "refused", "list": name, "path": "",
                           "why": "No template was named, so there is nothing to edit."}, 400)
    ctx = _editor(name, path)
    return _edit_card(ctx, 404 if ctx["state"] == "refused" else 200)


@bp.route("/edit/check", methods=["POST"])
def edit_check():
    """The edit, checked as typed: its syntax, and its render for every device it governs
    against that device's committed golden (`template_edit.check`). Writes nothing."""
    from modules.nsot import template_edit
    from modules.outbound import mask_payload

    name, path = _list_name(), (request.form.get("path") or "").strip()
    # Masked on the way out: a line the render misses is a golden's line, verbatim (C77).
    return _strict(render_template("v2/_template_check.html", list_name=name,
                                   k=mask_payload(template_edit.check(
                                       name, path, request.form.get("text", "")))))


@bp.route("/edit", methods=["POST"])
def edit_commit():
    """Commit the edit as the verified person, bound to the version opened (``base``): the
    result in place (what it revoked, Approve… next), the refusal when it moved, or the editor
    again with its error."""
    from modules import identity
    from modules.nsot import template_edit

    name, path = _list_name(), (request.form.get("path") or "").strip()
    text, base = request.form.get("text", ""), request.form.get("base", "")
    summary = request.form.get("summary", "")
    actor = identity.request_actor()
    got = template_edit.commit(name, path, text, summary, base, actor)
    if got.get("stage") == "moved":
        return _edit_card({"state": "moved", "list": name, "path": path, "m": got,
                           "text": text, "summary": summary}, 409)
    if not got.get("ok"):
        return _edit_card(_editor(name, path, text=text, base=base, summary=summary,
                                  refused=got.get("error", "not committed")),
                          got.get("status", 400))
    return _strict(render_template(
        "v2/_templates_lib.html", **_lib_ctx(name, {"state": "edited", "list": name,
                                                    "path": path, "r": got, "actor": actor,
                                                    "summary": summary})))


def _seed_view(name: str) -> dict:
    """What Seed the library… adds: each shipped file the network has not committed, and the
    shipped library's signature the confirm is bound to."""
    from modules.nsot import approve_op, templates_repo

    repo = approve_op.repo_for(name)
    have = set(approve_op.committed_templates(repo))
    if templates_repo.committed_blob(repo, templates_repo.BINDINGS_FILE):
        have.add(templates_repo.BINDINGS_FILE)
    return {"state": "seed", "list": name, "may": _may(),
            "adds": sorted(templates_repo.seed_paths() - have),
            "signature": templates_repo.library_signature()}


@bp.route("/seed", methods=["GET"])
def seed_form():
    """Seed the library…: the shipped files the network would gain. Writes nothing."""
    return _card(_seed_view(_list_name()))


@bp.route("/seed", methods=["POST"])
def seed():
    """Seed the network's library from the shipped one as the verified person, bound to the
    shipped library previewed; never overwriting a file; the result in place."""
    from modules import identity
    from modules.nsot import approve_op, templates_repo
    from routes.templates import _seed_and_commit

    name = _list_name()
    shown = (request.form.get("signature") or "").strip()
    now = templates_repo.library_signature()
    if shown != now:
        return _card(dict(_seed_view(name), refused=(
            f"the shipped library changed since your preview (previewed {shown or 'none'}, "
            f"now {now or 'unreadable'}): look again")), 409)
    actor = identity.request_actor()
    got = _seed_and_commit(name, approve_op.repo_for(name), actor=actor)
    return _region(name, {"state": "seeded", "list": name, "actor": actor,
                          "added": got.get("untracked") or [], "commit": got.get("commit", ""),
                          "left": got.get("uncommitted_edits") or []})


def _bindings_card(ctx: dict, code: int = 200):
    return _strict(render_template("v2/_template_bindings.html", b=ctx), code)


def _bindings_view(name: str, **extra) -> dict:
    from modules.nsot import template_bindings
    return dict(template_bindings.view(name), list=name, may=_may(), **extra)


@bp.route("/bindings", methods=["GET"])
def bindings_form():
    """Bindings…: which template renders which device, the form in place. Writes nothing."""
    return _bindings_card(dict(_bindings_view(_list_name()), state="form"))


@bp.route("/bindings/preview", methods=["POST"])
def bindings_preview():
    """The change previewed: every device whose template moves, and whether each one it moves
    to is approved. Writes nothing."""
    from modules.nsot import template_bindings

    name = _list_name()
    pv = template_bindings.preview(name, request.form)
    if not pv["ok"]:
        return _bindings_card(dict(_bindings_view(name), state="form", refused=pv["refused"]),
                              400)
    return _bindings_card(dict(_bindings_view(name), state="preview", pv=pv,
                               form=list(request.form.items(multi=True))))


@bp.route("/bindings", methods=["POST"])
def bindings_apply():
    """Commit the bindings previewed as the verified person, bound to the file committed at the
    preview and to the change previewed; the result in place, the table redrawn."""
    from modules import identity
    from modules.nsot import template_bindings

    name = _list_name()
    actor = identity.request_actor()
    got = template_bindings.apply(name, request.form, request.form.get("base", ""),
                                  request.form.get("fingerprint", ""),
                                  request.form.get("summary", ""), actor)
    if not got.get("ok"):
        return _bindings_card(dict(_bindings_view(name), state="form",
                                   refused=got.get("error", "not committed")),
                              got.get("status", 400))
    return _strict(render_template(
        "v2/_templates_lib.html", **_lib_ctx(name, {"state": "bound", "list": name, "r": got,
                                                    "actor": actor,
                                                    "summary": request.form.get("summary",
                                                                                "")})))


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
