"""routes/intent_v2.py — the device page's Intent tab, edited in place (board H, signed off
2026-10-04; C444, C481).

Edit turns the read-only card into H's editor: the committed document in a text area, checked
as you type (the checks, the render of the edit against what is committed, what a deploy would
send, the lines the parser does not model and whether each is acknowledged), then one commit
with its reason, bound to the version opened. Every step is `modules/nsot/intent_edit.py`'s,
the code today's editor uses too. The device's own list is carried on every call (a write
path carries its list), never the installation's active one. Nothing here contacts a device.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _device_or_404, _strict

log = logging.getLogger(__name__)

bp = Blueprint("intent_v2", __name__, url_prefix="/v2/device")


def may_commit() -> dict:
    """Whether the viewer may commit intent (route_gates: approve), from the gate's own
    functions, so the screen cannot disagree with the commit."""
    from modules import preview_confirm

    return preview_confirm.confirm_part(request, "approve")


def editor_ctx(ref, dev, text: str = None, base: str = None, summary: str = "",
               refused: dict = None) -> dict:
    """What H's editing card draws: the document (the committed one unless *text* carries an
    edit in progress), the blob it was opened at, who last changed it, the reason typed."""
    from modules.nsot import hostvars, intent_edit

    host = dev.get("hostname", "")
    opened = {}
    if text is None:
        opened = intent_edit.open_doc(ref.name, host)
        if not opened.get("ok"):
            return {"state": "refused", "host": host, "list": ref.name,
                    "why": opened.get("error", "the committed intent could not be read")}
        text, base = opened["yaml"], opened["base"]
    last = hostvars.last_intent_commit(intent_edit._repo_for(ref.name), host) or {}
    return {"state": "editing", "host": host, "list": ref.name, "text": text, "base": base,
            "summary": summary, "last": last, "refused": refused or {},
            "confirm": may_commit()}


def _card(ctx: dict, code: int = 200):
    return _strict(render_template("v2/_intent_edit.html", c=ctx), code)


@bp.route("/<name>/intent/edit", methods=["GET"])
def edit(name):
    """H's editor in place of the read-only card."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _card(editor_ctx(ref, dev))


@bp.route("/<name>/intent/check", methods=["POST"])
def check(name):
    """The edit, checked as typed: `intent_edit.preview`. Writes nothing."""
    from modules.nsot import intent_edit

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    text = request.form.get("yaml", "")
    p = intent_edit.preview(ref.name, dev.get("hostname", ""), text)
    return _strict(render_template("v2/_intent_check.html", p=p, host=dev.get("hostname", ""),
                                   text=text, list_name=ref.name))


@bp.route("/<name>/intent/acknowledge", methods=["POST"])
def acknowledge(name):
    """The editor again, its document's ``unmodeled_ack`` set to the lines ticked (C481).
    Writes nothing: the acknowledgement is committed with the edit, in git, with its reason."""
    from modules.nsot import intent_edit

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    text = intent_edit.acknowledge(request.form.get("yaml", ""), request.form.getlist("ack"))
    return _card(editor_ctx(ref, dev, text=text, base=request.form.get("base", ""),
                            summary=request.form.get("summary", "")))


@bp.route("/<name>/intent/commit", methods=["POST"])
def commit(name):
    """Commit the edit as the verified person, bound to the version opened: the result in
    place, or the refusal when intent moved (both changes; the edit placed on theirs when
    they touch different lines), or the editor again with its error."""
    from modules import identity
    from modules.nsot import intent_edit

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    host = dev.get("hostname", "")
    text, base = request.form.get("yaml", ""), request.form.get("base", "")
    summary = request.form.get("summary", "")
    got = intent_edit.commit(ref.name, host, text, summary, base, identity.request_actor())
    if got.get("stage") == "moved":
        return _card({"state": "moved", "host": host, "list": ref.name, "m": got,
                      "text": text, "summary": summary}, 409)
    if not got.get("ok"):
        return _card(editor_ctx(ref, dev, text=text, base=base, summary=summary, refused=got),
                     got.get("status", 400))
    p = intent_edit.preview(ref.name, host, text)
    return _card({"state": "done", "host": host, "list": ref.name, "r": got, "p": p,
                  "summary": summary, "actor": identity.request_actor()})


@bp.route("/<name>/intent/reopen", methods=["POST"])
def reopen(name):
    """After intent moved: the editor opened at what is committed now, the person's edit
    placed on it (only when the two touched different lines). Nothing is committed for them."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _card(editor_ctx(ref, dev, text=request.form.get("yaml", ""),
                            base=request.form.get("base", ""),
                            summary=request.form.get("summary", "")))
