"""routes/heal_proposal_v2.py — a self-healing proposal's preview, approve and decline (board H,
part H5; docs/HEAL_TO_INTENT.md sections 9 (artboard E) and 11; `modules/heal/propose.py`).

A Tier 2 fix waits for a person: the proposal is read (its program, the process reset it needs,
what that affects and why rollback cannot undo it, whether it is measured, and the hash an
approval confirms); approved by that hash as a verified person with a reason, which starts its
act as a job as that person; or declined as a verified person with a reason, which sends
nothing. Every write is `modules/heal/propose.py`'s. Each answers ``{"ok", "error", ...}``.

**Not registered until H9.** An endpoint with no page waits for its page (the coordinator's
decision of 2026-11-03, as H1's routes waited): the Needs attention row ``heal``/``proposal``
with **Approve…** and **Decline…** (board H, artboard E) is H9's, and the commit that draws it
registers `bp` (`routes/__init__.py`) and moves `gates` into `route_gates.GATES`, `invalidates`
into `invalidation.DECLARED`, `stages` into `operation_stages.STAGES` and `history` into
`operation_stages.HISTORY`. Until then the tests put the blueprint on their own app.
"""

import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("heal_proposal_v2", __name__, url_prefix="/v2")


def gates() -> dict:
    """The routes' gates, for `modules/route_gates.py`'s GATES (placed by H9). Approve and
    decline refuse anyone but a verified person too, whatever a service is granted."""
    from modules.route_gates import Gate

    return {
        "heal_proposal_v2.approve": Gate("confirm", "approves one self-healing proposal (a Tier 2 fix, board H artboard E) bound to the proposal's hash as previewed, as a verified person with a reason: its program sent through THE apply as that person, holding the device, then the measured process reset it needs (refused until measured), verified, rolled back on failure and recorded", "heal_proposal"),
        "heal_proposal_v2.decline": Gate("configure", "declines one self-healing proposal as a verified person with a reason: recorded in the network's heal decisions and step log, its incident closed; sends nothing to a device"),
    }


def invalidates() -> dict:
    """What each route invalidates, for `modules/invalidation.py`'s DECLARED (placed by H9)."""
    from modules.invalidation import Nothing

    return {
        "heal_proposal_v2.approve": Nothing("starts the approved heal as a job and answers at "
                                            "once; the heal ANNOUNCES heal-act's keys as it "
                                            "finishes (ANNOUNCERS)"),
        "heal_proposal_v2.decline": ("drift",),
    }


def stages() -> dict:
    """The approve route's five stages, for `modules/operation_stages.py`'s STAGES (placed by
    H9): the preview is this blueprint's read of the proposal; the hash the proposal's; verify
    the pipeline's and then the reset's measured rule; rollback the pipeline's after verify
    (`roll_back_after`, the change put back when the reset was not made); the record the step
    log's act row, beside the receipt and the reset's Tier 2 record."""
    from modules.operation_stages import Stages

    return {"heal_proposal_v2.approve": Stages(
        "heal_proposal_v2.proposal", "hash", "modules.nsot.privileged.reset_verify",
        "modules.pipeline.roll_back_after", "modules.heal.steplog.record_act")}


def history() -> dict:
    """Where each route's record is read later, for `operation_stages.HISTORY` (placed by H9):
    the step log, the receipt and golden, and the reset's Tier 2 record."""
    return {"heal_proposal_v2.approve": ("heal", "receipts", "golden", "privileged"),
            "heal_proposal_v2.decline": ("heal",)}


def _answer(body: dict, code: int = 200):
    return jsonify(dict({"ok": code == 200, "error": ""}, **body)), code


def _refused(exc) -> tuple:
    from modules.heal import propose

    return _answer({"ok": False, "error": str(exc)},
                   403 if isinstance(exc, propose.NotAPerson) else 409)


def _who() -> dict:
    """The verified actor, how it was established, and whether it is a person."""
    from modules import identity

    actor = identity.request_actor()
    ident = identity.verified_identity()
    return {"actor": actor, "actor_verified": identity.actor_verification(actor),
            "person": bool(ident is not None and ident.kind == "person")}


@bp.route("/network/<list_name>/heal/proposal/<decision_id>", methods=["GET"])
def proposal(list_name, decision_id):
    """The proposal as a person reads it before deciding; reads only Mercury's records."""
    from modules.heal import propose

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
        return _refused(exc)
    return _answer(out)


@bp.route("/network/<list_name>/heal/proposal/<decision_id>/decline", methods=["POST"])
def decline(list_name, decision_id):
    """Decline the proposal: a verified person and a reason; nothing is sent."""
    from modules.heal import propose

    try:
        out = propose.decline(list_name, decision_id, reason=request.form.get("reason") or "",
                              **_who())
    except propose.Refused as exc:
        return _refused(exc)
    return _answer(out)
