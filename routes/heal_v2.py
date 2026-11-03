"""routes/heal_v2.py — heal to intent's policy routes (board H, part H1;
docs/HEAL_TO_INTENT.md sections 6, 7, 9 and 16).

Each network's heal policy, previewed and confirmed by hash as a verified person with a reason;
its one-click Turn off; and the installation's kill switch (stop at once, resume previewed and
confirmed by hash). Every write is `modules/heal/policy.py`'s; nothing here contacts a device.
Each answers ``{"ok", "error", ...}``; the Self-healing tab that draws and posts them is H9's
(board H, artboard A), which turns these answers into its fragments.
"""

import json
import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("heal_v2", __name__, url_prefix="/v2/settings")


def gates() -> dict:
    """The routes' gates, for `modules/route_gates.py`'s GATES. **Not registered until H9:** an
    endpoint with no page waits for its page (the coordinator's decision, 2026-11-03), so
    `routes/__init__.py` does not register `bp`, and H9 moves these into GATES, `invalidates`
    into `invalidation.DECLARED` and `history` into `operation_stages.HISTORY` in the commit
    that registers it. The policy's confirm and resume
    refuse anyone but a verified person too, whatever configure's settings allow a service."""
    from modules.route_gates import Gate

    K, N = "configure", "not_device"
    return {
        "heal_v2.policy_preview": Gate(N, "previews a change to one network's heal policy (its mode, AUTO's expiry, the kinds and the hard stops) in the six parts with the fingerprint its confirm sends; writes nothing and sends nothing to a device"),
        "heal_v2.policy_confirm": Gate(K, "sets one network's heal policy as previewed, bound to the preview's fingerprint, as a verified person with a reason (C2009: AUTO only on a network marked lab, at most 7 days, then dry run); recorded in the network's settings record with the values before and after; sends nothing to a device"),
        "heal_v2.turn_off": Gate(K, "turns self-healing off for one network at once, one press, no confirm; recorded with who and when; a heal already applying finishes its own verify and rollback"),
        "heal_v2.stop_everywhere": Gate(K, "stops self-healing on every network at once (the installation's kill switch), one press, no confirm; recorded with who, when and why"),
        "heal_v2.resume_preview": Gate(N, "previews resuming self-healing: each network's mode once resumed and the fingerprint its confirm sends; writes nothing"),
        "heal_v2.resume": Gate(K, "resumes self-healing everywhere as previewed, bound to the preview's fingerprint, as a verified person with a reason; recorded in the installation's settings record"),
    }


def invalidates() -> dict:
    """What each route invalidates, for `modules/invalidation.py`'s DECLARED (moved there by
    H9, as `gates` is): the policy and the kill switch are settings."""
    from modules.invalidation import Nothing

    return {
        "heal_v2.policy_preview": Nothing("previews a heal policy change; writes nothing"),
        "heal_v2.policy_confirm": ("settings",),
        "heal_v2.turn_off": ("settings",),
        "heal_v2.stop_everywhere": ("settings",),
        "heal_v2.resume_preview": Nothing("previews resuming self-healing; writes nothing"),
        "heal_v2.resume": ("settings",),
    }


def history() -> dict:
    """Where each configure route's record is read later, for `modules/operation_stages.py`'s
    HISTORY (moved there by H9, as `gates` is): each is kept in a settings record with who,
    when and why, and none is one device's record."""
    from modules.operation_stages import NOT_A_DEVICE

    return {k: NOT_A_DEVICE for k in ("heal_v2.policy_confirm", "heal_v2.turn_off",
                                      "heal_v2.stop_everywhere", "heal_v2.resume")}


def _answer(body: dict, code: int = 200):
    return jsonify(dict({"ok": code == 200, "error": ""}, **body)), code


def _refused(exc) -> tuple:
    from modules.heal import policy as H

    return _answer({"ok": False, "error": str(exc)}, 403 if isinstance(exc, H.NotAPerson)
                   else 409)


def _who() -> dict:
    """The verified actor, how it was established, and whether it is a person."""
    from modules import identity

    actor = identity.request_actor()
    ident = identity.verified_identity()
    return {"actor": actor, "actor_verified": identity.actor_verification(actor),
            "person": bool(ident is not None and ident.kind == "person")}


def _proposed(form) -> dict:
    """The policy values the form sent, each as its schema's type (a list as JSON). AUTO's
    expiry is sent as ``heal_mode_until`` (UTC) or as ``auto_hours`` from now."""
    import time

    from modules.heal import policy as H
    from routes.settings_v2 import _typed

    sent = {k: form.get(k) for k in H.POLICY_KEYS if k in form}
    out = _typed(sent)
    hours = (form.get("auto_hours") or "").strip()
    if hours and not out.get(H.UNTIL_KEY):
        try:
            out[H.UNTIL_KEY] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime(time.time() + float(hours) * 3600))
        except ValueError:
            raise H.PolicyRefused(f"AUTO's hours are a number, not {hours!r}") from None
    return out


@bp.route("/network/<list_name>/heal/preview", methods=["POST"])
def policy_preview(list_name):
    """What the change to the network's heal policy does, in the six parts; writes nothing."""
    from modules import preview_confirm
    from modules.heal import policy as H

    try:
        p = H.plan(list_name, _proposed(request.form))
    except H.PolicyRefused as exc:
        return _refused(exc)
    return _answer({"network": list_name, "fingerprint": p["fingerprint"],
                    "confirmable": p["confirmable"], "operands": p["operands"],
                    "preview": preview_confirm.heal_policy_preview(
                        p, preview_confirm.confirm_part(request, "configure"))})


@bp.route("/network/<list_name>/heal", methods=["POST"])
def policy_confirm(list_name):
    """The change as previewed: a verified person, a reason, the preview's fingerprint;
    re-planned and compared, written, recorded."""
    from modules.heal import policy as H

    form = request.form
    try:
        seen = json.loads(form.get("seen") or "null")
    except ValueError:
        seen = None
    try:
        out = H.apply(list_name, _proposed(form), form.get("fingerprint") or "",
                      reason=form.get("reason") or "", seen=seen, **_who())
    except H.PolicyRefused as exc:
        return _refused(exc)
    return _answer(out)


@bp.route("/network/<list_name>/heal/off", methods=["POST"])
def turn_off(list_name):
    """Turn off: one press, no confirm, effective at once, recorded with who and when."""
    from modules.heal import policy as H

    who = _who()
    try:
        out = H.turn_off(list_name, actor=who["actor"], actor_verified=who["actor_verified"])
    except H.PolicyRefused as exc:
        return _refused(exc)
    return _answer(out)


@bp.route("/installation/heal/stop", methods=["POST"])
def stop_everywhere():
    """Stop self-healing everywhere: one press, no confirm, recorded with who, when and why."""
    from modules.heal import policy as H

    who = _who()
    try:
        out = H.stop(actor=who["actor"], actor_verified=who["actor_verified"],
                     why=request.form.get("why") or "")
    except H.PolicyRefused as exc:
        return _refused(exc)
    return _answer(out)


@bp.route("/installation/heal/resume/preview", methods=["POST"])
def resume_preview():
    """What resuming does, network by network, and the fingerprint its confirm sends; writes
    nothing."""
    from modules import preview_confirm
    from modules.heal import policy as H

    try:
        p = H.resume_plan()
    except H.PolicyRefused as exc:
        return _refused(exc)
    return _answer({"networks": p["networks"], "fingerprint": p["fingerprint"],
                    "stopped": p["stopped"], "why": p["why"],
                    "confirm": preview_confirm.confirm_part(request, "configure")})


@bp.route("/installation/heal/resume", methods=["POST"])
def resume():
    """Resume self-healing as previewed: a verified person, a reason, the fingerprint."""
    from modules.heal import policy as H

    try:
        out = H.resume(request.form.get("fingerprint") or "",
                       reason=request.form.get("reason") or "", **_who())
    except H.PolicyRefused as exc:
        return _refused(exc)
    return _answer(out)
