"""routes/control_v2.py — the control strip (C3748), on Troubleshoot › Incidents, and G6's
one-button batch, on Needs attention (C3789; `modules/control_strip.py`, `modules/heal/batch.py`).

- ``GET /v2/control/strip`` (``list``, ``part``): the strip for the page's network, drawn from
  the settings and this server's job registry; ``part=run`` its run part alone, as Needs
  attention draws it; it re-reads itself when self-healing announces, a setting is saved, or a
  run moves (no polling).
- ``POST /v2/control/<list_name>/heal`` (``on`` 1 or 0): the Self-healing toggle, as a verified
  person who may change self-healing settings: on is Auto for the network's default duration,
  off is Dry run, through the policy's own write; the strip again with the answer in place.
- ``POST /v2/control/<list_name>/fix-all`` (``hash``): Turn on self-healing and fix all, bound
  to the batch's hash as previewed on its card: the AI started on each incident with no fix,
  and the rest as one job (`heal.batch.press`); the strip's run part, with the run on its
  stepper, in place on Needs attention.

The AI toggle posts Settings › AI's own routes with ``answer=strip`` (`settings_v2.ai_on_form`,
`ai_on`, `ai_off`): one write path for turning the feature on and off. Every route is
declared in `route_gates.GATES`, `invalidation.DECLARED` and `operation_stages`; each draws the
viewer through `identity.viewer()` and carries the strict policy.
"""

import logging

from flask import Blueprint, render_template, request

log = logging.getLogger(__name__)

bp = Blueprint("control_v2", __name__, url_prefix="/v2/control")


def _strip(network: str, code: int = 200, run_only: bool = False, **answer):
    """The strip for *network*, or (*run_only*, C3789) its run part alone, as Needs attention
    draws it under G6's batch card: one template, one model (`control_strip.view`,
    `control_strip.run_view`)."""
    from modules import control_strip
    from routes.device_v2 import _strict

    s = (control_strip.run_view(network, **answer) if run_only
         else control_strip.view(network, **answer))
    return _strict(render_template("v2/_control_strip.html", s=s), code)


def _network() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return named_list(request) or listref.active().name


def _who() -> dict:
    from modules import identity

    actor = identity.request_actor()
    ident = identity.verified_identity()
    return {"actor": actor, "verified": identity.actor_verification(actor), "ident": ident,
            "person": bool(ident is not None and ident.kind == "person")}


@bp.route("/strip", methods=["GET"])
def strip():
    """The strip for the page's network; ``part=run``, its run part alone (Needs attention's,
    C3789), as it re-reads itself."""
    return _strip(_network(), run_only=request.args.get("part") == "run")


@bp.route("/<list_name>/heal", methods=["POST"])
def heal(list_name):
    """The Self-healing toggle: one press, no dialog; refused, naming why, with nothing changed,
    for anyone who may not change self-healing settings."""
    from modules import control_strip
    from modules.heal import batch, policy

    who = _who()
    why = batch.may_press(who["ident"])
    if why:
        return _strip(list_name, 403, refused=f"Self-healing was not changed: {why}")
    on = request.form.get("on") == "1"
    # C3789: the strip, and so its toggle, is on Troubleshoot › Incidents alone
    # (`control_strip.set_heal`'s page).
    try:
        got = control_strip.set_heal(list_name, on, actor=who["actor"],
                                     verified=who["verified"], person=who["person"])
    except policy.PolicyRefused as exc:
        return _strip(list_name, 409, refused=f"Self-healing was not changed: {exc}")
    return _strip(list_name, heal_set=got["words"])


@bp.route("/<list_name>/fix-all", methods=["POST"])
def fix_all(list_name):
    """Turn on self-healing and fix all, bound to the batch's hash as previewed. Its card is on
    Needs attention, so its answer is the strip's run part, drawn in place there (C3789)."""
    from modules import control_strip
    from modules.heal import batch

    who = _who()
    try:
        got = control_strip.fix_all(list_name, request.form.get("hash") or "",
                                    actor=who["actor"], verified=who["verified"],
                                    ident=who["ident"])
    except batch.Refused as exc:
        code = 403 if "verified person" in str(exc) or "may not" in str(exc) else 409
        return _strip(list_name, code, run_only=True, refused=f"Nothing was started: {exc}")
    ai = got.get("ai") or {}
    return _strip(list_name, run_only=True, pressed={"job": got["job"], "fixable": got["preview"]["fixable"],
                                      "ai_started": len(ai.get("started") or []),
                                      "ai_capped": len(ai.get("capped") or [])
                                      + len(ai.get("off") or []),
                                      "ai_skipped": len(ai.get("skipped") or [])
                                      + len(ai.get("failed") or [])})
