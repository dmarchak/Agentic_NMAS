"""routes/control_v2.py — the control strip (C3748), on Troubleshoot › Incidents, and G6's
one-button batch, on Needs attention (C3789; `modules/control_strip.py`, `modules/heal/batch.py`).

- ``GET /v2/control/strip`` (``list``, ``part``): the strip for the page's network, drawn from
  the settings and this server's job registry; ``part=run`` its run part alone, as Needs
  attention draws it; it re-reads itself when self-healing announces, a setting is saved, or a
  run moves (no polling).
- ``POST /v2/control/<list_name>/heal`` (``on`` 1 or 0): the Self-healing toggle, as a verified
  person who may change self-healing settings: on is Auto for the network's default duration,
  off is Dry run, through the policy's own write; the strip again with the answer in place.
  With ``hash`` (C3823), on is the batch of the open problems its line drew, bound to that
  hash (`control_strip.switch_on`): restores and saved scripts, never the AI; refused, nothing
  turned on, when they moved since drawn, the strip drawn again with the new line. C3866: the
  press is checked against the line as this process drew it (no second preview), turns Auto
  on and records the batch's approval inside the request, and answers at once with the switch
  On and "Starting N fixes…"; the fixes are the batch's job, drawn live on the strip.
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


def _strip(network: str, code: int = 200, run_only: bool = False, drawn: bool = True,
           **answer):
    """The strip for *network*, or (*run_only*, C3789) its run part alone, as Needs attention
    draws it under G6's batch card: one template, one model (`control_strip.view`,
    `control_strip.run_view`). *drawn* (C3866): a press's answer draws each switch's line as
    this process last drew it, so it waits on no preview; the strip's GET reads them again."""
    from modules import control_strip
    from routes.device_v2 import _strict

    s = (control_strip.run_view(network, **answer) if run_only
         else control_strip.view(network, drawn=drawn, **answer))
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
    return _strip(_network(), run_only=request.args.get("part") == "run", drawn=False)


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
    shown = request.form.get("hash") or ""
    if on and shown:
        # C3823: turned on with the open problems its line drew, bound to that line's hash:
        # C3819's batch (restores and saved scripts, all at once; never the AI),
        # which turns self-healing on itself; refused, nothing turned on, when they moved.
        # C3866 (the operator, 2026-11-16: "Every switch flips instantly; the work it starts
        # happens after, in the background"): the press is checked against the line as drawn,
        # turns Auto on and records the approval here, and answers with the switch On and
        # "Starting N fixes…"; the fixes are the batch's job, its run drawn live below.
        try:
            got = control_strip.switch_on(list_name, shown, actor=who["actor"],
                                          verified=who["verified"], ident=who["ident"])
        except batch.TurnedOn as exc:
            return _strip(list_name, 409, refused=f"Nothing was fixed: {exc}")
        except batch.Refused as exc:
            code = 403 if "verified person" in str(exc) or "may not" in str(exc) else 409
            return _strip(list_name, code, refused=f"Self-healing was not changed: {exc}")
        except Exception as exc:                      # noqa: BLE001 (readable, never a bare 500)
            log.exception("control strip: the Self-healing switch on %s failed", list_name)
            return _strip(list_name, 500, refused=(
                f"The switch's press did not finish ({type(exc).__name__}: {exc}); the switch "
                "below shows self-healing as it is now"))
        return _strip(list_name, starting=control_strip.starting_words(
            got["preview"]["fixable"]))
    # C3789: the strip, and so its toggle, is on Troubleshoot › Incidents alone
    # (`control_strip.set_heal`'s page).
    try:
        got = control_strip.set_heal(list_name, on, actor=who["actor"],
                                     verified=who["verified"], person=who["person"])
    except policy.PolicyRefused as exc:
        return _strip(list_name, 409, refused=f"Self-healing was not changed: {exc}")
    return _strip(list_name, heal_set=got["words"])


@bp.route("/<list_name>/run-seen", methods=["POST"])
def run_seen(list_name):
    """A finished batch run's one line dismissed from the strip by the person looking (the
    operator, 2026-11-16), kept in the In progress list's own per-person marks
    (`seen_runs.mark`, ``dismissed``; no store of its own): it leaves their strip, list and
    chip; everyone else still sees it until its bound (`control_strip.RUN_LINE_S`). Form:
    ``job``, which must be this network's newest batch job; ``part=run`` draws the run part
    alone (Needs attention's). Refused, nothing written, with no verified person."""
    from modules import control_strip, seen_runs
    from routes.operations import viewer_key

    run_only = request.form.get("part") == "run"
    job = (request.form.get("job") or "").strip()
    newest = control_strip.newest_batch_job(list_name)
    if not job or newest is None or newest["job"] != job:
        return _strip(list_name, 409, run_only=run_only,
                      refused=f"Nothing was dismissed: the run named ({job[:12] or 'none'}) "
                              f"is not this network's newest batch run "
                              f"({(newest or {}).get('job', 'none')[:12]})")
    got = seen_runs.mark(viewer_key(), [job], "dismissed")
    if not got.get("ok"):
        return _strip(list_name, 403 if "verified" in (got.get("error") or "") else 409,
                      run_only=run_only, refused=f"Nothing was dismissed: {got.get('error')}")
    if got.get("news"):
        # As the In progress list's own mark announces it (`operations.mark_seen`).
        from modules import invalidation
        from modules.nsot import capture_job
        try:
            invalidation.announce(capture_job.MOVED_KEYS, by=capture_job.MOVED_ANNOUNCER,
                                  ok=True)
        except RuntimeError:
            pass                                      # no emitter: nobody else to tell
        except Exception as exc:                      # noqa: BLE001 (said in the log)
            log.warning("control strip: a dismissal was not announced to open pages: %s", exc)
    return _strip(list_name, run_only=run_only)


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
