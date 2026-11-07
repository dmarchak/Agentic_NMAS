"""routes/ai_classes_v2.py — a network's "What AI may send" card (board H, artboard N; H28;
docs/HEAL_TO_INTENT.md 19.5, the operator's N20).

The network's AI data classes on its Settings › Network tab: allowed, topology, device state
and configuration, each with its state. **Device state** is off by default; Turn on… opens a
reason in place, and an admin (a verified person) turns it on for this network with a reason
of at least three words; Turn off is one press, no confirm, effective at once. Every write is
`modules/ai/egress_classes.py`'s and recorded in the network's settings record; nothing here
contacts a device or a provider. The card's model is `egress_classes.classes_view`.
"""

import logging

from flask import Blueprint, render_template, request

log = logging.getLogger(__name__)

bp = Blueprint("ai_classes_v2", __name__, url_prefix="/v2/settings/network/<list_name>/ai-classes")


def _who() -> dict:
    """The verified actor, how it was established, and whether it is a person."""
    from modules import identity

    actor = identity.request_actor()
    ident = identity.verified_identity()
    return {"actor": actor, "actor_verified": identity.actor_verification(actor),
            "person": bool(ident is not None and ident.kind == "person")}


def _card(list_name: str, code: int = 200, **ctx):
    """The card for *list_name*, drawn again with an answer in place."""
    from modules.ai import egress_classes as E
    from modules.nsot import listref
    from routes.device_v2 import _strict

    if not listref.exists(list_name):
        code, ctx = 404, dict(ctx, refused=f"no network is named {list_name!r}: nothing was "
                                           "changed")
        aic = {"marked": "", "rows": [], "device_state_on": False}
    else:
        aic = E.classes_view(list_name)
    return _strict(render_template("v2/_ai_classes.html", aic=aic, list_name=list_name,
                                   **ctx), code)


@bp.route("", methods=["GET"])
def card(list_name):
    """The card alone: re-read when `settings` is announced, and what Cancel puts back."""
    return _card(list_name)


@bp.route("/device-state/on", methods=["GET"])
def device_state_form(list_name):
    """Turn on…: the reason's field in place; nothing written."""
    return _card(list_name, open_on=True)


@bp.route("/device-state/on", methods=["POST"])
def device_state_on(list_name):
    """Turn device state on for this network as the verified person, with the reason typed;
    refused, naming why, with nothing changed, otherwise."""
    from modules.ai import egress_classes as E
    from modules.nsot import listref

    if not listref.exists(list_name):
        return _card(list_name)
    who = _who()
    reason = request.form.get("reason", "")
    try:
        out = E.turn_on_device_state(list_name, reason, actor=who["actor"],
                                     actor_verified=who["actor_verified"],
                                     person=who["person"])
    except E.DeviceStateRefused as exc:
        return _card(list_name, 403 if "verified person" in str(exc) else 409, open_on=True,
                     refused=str(exc), reason=reason)
    return _card(list_name, turned=out)


@bp.route("/device-state/off", methods=["POST"])
def device_state_off(list_name):
    """Turn off: one press, no confirm, effective at once, recorded with who and when."""
    from modules.ai import egress_classes as E
    from modules.nsot import listref

    if not listref.exists(list_name):
        return _card(list_name)
    who = _who()
    try:
        out = E.turn_off_device_state(list_name, actor=who["actor"],
                                      actor_verified=who["actor_verified"],
                                      person=who["person"])
    except E.DeviceStateRefused as exc:
        return _card(list_name, 403 if "verified person" in str(exc) else 409,
                     refused=str(exc))
    return _card(list_name, turned=out)
