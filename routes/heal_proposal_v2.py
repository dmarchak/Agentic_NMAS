"""routes/heal_proposal_v2.py — a self-healing proposal's preview, approve and decline (board H,
parts H5 and H9; docs/HEAL_TO_INTENT.md sections 9 (artboard E) and 11; `modules/heal/propose.py`).

A Tier 2 fix waits for a person: the proposal is read (its program, the process reset it needs,
what that affects and why rollback cannot undo it, whether it is measured, and the hash an
approval confirms); approved by that hash as a verified person with a reason, which starts its
act as a job as that person; or declined as a verified person with a reason, which sends
nothing. Every write is `modules/heal/propose.py`'s.

**Where it is drawn** (board H, artboard E; H9): the Needs attention row ``heal``/``proposal``
(`attention.heal_source`) opens to this proposal's card (`templates/v2/_heal_proposal.html`),
read by `proposal` when the row is opened; its **Approve and run on <device>** and **Decline**
post `approve` and `decline` with htmx, and each is answered with the card again, its answer
in place (approved and its job, declined, or the refusal with the reason typed kept). A request
that is not htmx's is answered ``{"ok", "error", ...}`` as H5 built them.

The routes' declarations live in their tables (`route_gates.GATES`, `invalidation.DECLARED`,
`operation_stages.STAGES` and `HISTORY`), placed there by H9 with the card; `gates()`,
`invalidates()`, `stages()` and `history()` are views of those tables.
"""

import logging

from flask import Blueprint, jsonify, render_template, request

log = logging.getLogger(__name__)

bp = Blueprint("heal_proposal_v2", __name__, url_prefix="/v2")


def _prefix_rows(table: dict) -> dict:
    return {k: v for k, v in table.items() if k.startswith(bp.name + ".")}


def gates() -> dict:
    """These routes' rows of `modules/route_gates.py`'s GATES. Approve and decline refuse
    anyone but a verified person too, whatever a service is granted."""
    from modules.route_gates import GATES

    return _prefix_rows(GATES)


def invalidates() -> dict:
    """These routes' rows of `modules/invalidation.py`'s DECLARED."""
    from modules.invalidation import DECLARED

    return _prefix_rows(DECLARED)


def stages() -> dict:
    """The approve route's five stages, its row of `modules/operation_stages.py`'s STAGES."""
    from modules.operation_stages import STAGES

    return _prefix_rows(STAGES)


def history() -> dict:
    """Where each route's record is read later, its rows of `operation_stages.HISTORY`."""
    from modules.operation_stages import HISTORY

    return _prefix_rows(HISTORY)


def _htmx() -> bool:
    return bool(request.headers.get("HX-Request"))


def _answer(body: dict, code: int = 200):
    return jsonify(dict({"ok": code == 200, "error": ""}, **body)), code


def _code(exc) -> int:
    from modules.heal import propose

    return 403 if isinstance(exc, propose.NotAPerson) else 409


def _refused(exc) -> tuple:
    return _answer({"ok": False, "error": str(exc)}, _code(exc))


def _who() -> dict:
    """The verified actor, how it was established, and whether it is a person."""
    from modules import identity

    actor = identity.request_actor()
    ident = identity.verified_identity()
    return {"actor": actor, "actor_verified": identity.actor_verification(actor),
            "person": bool(ident is not None and ident.kind == "person")}


def _card(list_name: str, decision_id: str, code: int = 200, **ctx):
    """The proposal's card, read again, with an answer in place (`ctx`). A proposal no longer
    held (declined, approved or never there) is drawn as that, never as an empty card."""
    from modules import preview_confirm
    from modules.heal import propose
    from routes.device_v2 import _strict

    try:
        v = propose.view(list_name, decision_id)
        gone = ""
    except propose.Refused as exc:
        v, gone = None, str(exc)
    html = render_template("v2/_heal_proposal.html", v=v, gone=gone, list_name=list_name,
                           decision_id=decision_id,
                           confirming=preview_confirm.confirm_part(request,
                                                                   "confirm")["statement"],
                           **ctx)
    return _strict(html, code if v is not None or ctx else 404)


@bp.route("/network/<list_name>/heal/proposal/<decision_id>", methods=["GET"])
def proposal(list_name, decision_id):
    """The proposal as a person reads it before deciding; reads only Mercury's records."""
    from modules.heal import propose

    if _htmx():
        return _card(list_name, decision_id)
    try:
        v = propose.view(list_name, decision_id)
    except propose.Refused as exc:
        return _answer({"ok": False, "error": str(exc)}, 404)
    return _answer({"proposal": v})


@bp.route("/network/<list_name>/heal/proposal/<decision_id>/approve", methods=["POST"])
def approve(list_name, decision_id):
    """Approve the proposal as previewed: a verified person, a reason, the proposal's hash;
    its act started as a job, as that person."""
    from modules import identity
    from modules.heal import propose

    form = request.form
    try:
        out = propose.approve(list_name, decision_id, confirmed_hash=form.get("hash") or "",
                              reason=form.get("reason") or "",
                              ident=identity.verified_identity(), **_who())
    except propose.Refused as exc:
        if _htmx():
            return _card(list_name, decision_id, _code(exc), refused=str(exc),
                         reason=form.get("reason") or "")
        return _refused(exc)
    if _htmx():
        return _card(list_name, decision_id, approved=out)
    return _answer(out)


@bp.route("/network/<list_name>/heal/proposal/<decision_id>/decline", methods=["POST"])
def decline(list_name, decision_id):
    """Decline the proposal: a verified person and a reason; nothing is sent."""
    from modules.heal import propose

    form = request.form
    try:
        out = propose.decline(list_name, decision_id, reason=form.get("reason") or "",
                              **_who())
    except propose.Refused as exc:
        if _htmx():
            return _card(list_name, decision_id, _code(exc), refused=str(exc),
                         reason=form.get("reason") or "")
        return _refused(exc)
    if _htmx():
        return _card(list_name, decision_id, declined=out)
    return _answer(out)
