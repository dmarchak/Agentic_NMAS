"""routes/plans_v2.py — a plan of Mercury's operations, previewed together and approved once by
its hash (modules/plan_engine.py), drawn in place where it was offered (the toolbar assistant's
answer, `templates/v2/_assistant_answer.html`) by `templates/v2/_plan_card.html`.

- ``preview`` (GET): the plan named (``plan``) with its parameters (``params``, one JSON object),
  every step previewed by its own operation, the plan's hash, a reason, and Approve the plan,
  named for the work; with ``run`` (and ``job``), the run's state or its result in place.
- ``approve`` (POST): the plan started as a job as the verified person, bound to the plan's
  hash (``hash``); or the refusal drawn in place, nothing run.

Its declarations live in their tables (`route_gates.GATES`, `invalidation.DECLARED`,
`operation_stages.STAGES` and `HISTORY`).
"""

import json
import logging

from flask import Blueprint, render_template, request

from routes.assistant_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("plans_v2", __name__, url_prefix="/v2/plans")

#: The longest ``params`` a request may carry.
PARAMS_CHARS = 2000


def _list_name() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return named_list(request) or listref.active().name


def _params(text):
    """``(params, why)``: the request's ``params``, one JSON object, or why it is not."""
    text = str(text or "")
    if len(text) > PARAMS_CHARS:
        return None, f"the plan's parameters are {len(text)} characters, past {PARAMS_CHARS}"
    try:
        got = json.loads(text or "{}")
    except ValueError:
        return None, "the plan's parameters are not one JSON object"
    return (got, "") if isinstance(got, dict) else (None, "the plan's parameters are not one "
                                                          "JSON object")


def card(network: str, args, **answer) -> dict:
    """The card's context in the state its query names: ``preview``, ``running`` or
    ``result``; reads only Mercury's records (and each step's own dry run)."""
    from modules import plan_engine as E

    c = {"list": network, "plan": str(args.get("plan") or "")[:64], "error": "",
         "run": str(args.get("run") or "")[:80], "job": str(args.get("job") or "")[:80],
         "reason": str(args.get("reason") or "")[:300], "state": "preview",
         "outcome_words": dict(E.OUTCOME_WORDS)}
    c.update(answer)
    from modules.redact import redact_text
    # What a refusal says is drawn through the same mask as the preview (`redact_payload`).
    c["error"] = redact_text(c.get("error") or "")
    params, why = _params(args.get("params"))
    c["params_json"] = json.dumps(params or {}, sort_keys=True, separators=(",", ":"))
    if c["run"]:
        rec = E.record_of(network, c["run"])
        if rec is None or rec.get("state") == "running":
            c["state"] = "running"
            c["record"] = rec or {}
            c["job_failed"] = ""
            if c["job"]:
                # The job's own state while the record says running (or there is none yet): a
                # job that ended without its record's end (it raised before writing it) is said,
                # never drawn running for ever.
                from modules.nsot import capture_job
                job = capture_job.get(c["job"]) or {}
                if job.get("state") in ("failed", "done"):
                    c["job_failed"] = redact_text(job.get("error") or job.get("reason") or
                                       f"its job {c['job']} ended, and no record was written")
        else:
            c.update(state="result", record=rec,
                     level=("ok" if rec.get("state") == "done" else
                            "warn" if rec.get("outcome") == "partial" else "danger"))
        return c
    if why:
        c["preview"] = {"ok": False, "refused": why, "steps": []}
        return c
    # What the card draws of the engine's preview (its parameters are the card's own, carried
    # in `params_json`).
    got = E.preview(network, c["plan"], params)

    c["preview"] = dict({k: v for k, v in got.items() if k not in ("code", "params")},
                        refused=redact_text(got.get("refused") or ""),
                        steps=[{k: s.get(k) for k in ("n", "words", "drawn")}
                               for s in got.get("steps") or []])
    return c


def _draw(network: str, args, code: int = 200, **answer):
    return _strict(render_template("v2/_plan_card.html", c=card(network, args, **answer)),
                   code)


@bp.route("/preview", methods=["GET"])
def preview():
    """The plan's card: its steps each previewed by its own operation, or the run named. Asked
    in place (htmx), the card alone; otherwise (In progress's Open, a link, a reload) the
    plan's own page, the frame around the same card, which redraws itself while the run goes."""
    network = _list_name()
    if request.headers.get("HX-Request") != "true":
        from routes.v2 import _page

        return _page("v2/plan.html", c=card(network, request.args), active_nav="history")
    return _draw(network, request.args)


@bp.route("/approve", methods=["POST"])
def approve():
    """Approve the plan by its hash, as the verified person, with a reason: it runs in order,
    each step through its own operation, stopping at the first that does not pass."""
    from modules import identity
    from modules import plan_engine as E

    network, form = _list_name(), request.form
    params, why = _params(form.get("params"))
    again = {"plan": form.get("plan") or "", "params": form.get("params") or ""}
    if why:
        return _draw(network, again, 409, error=why + ". Nothing ran")
    actor = identity.request_actor()
    ident = identity.verified_identity()
    got = E.start(network, form.get("plan") or "", params, (form.get("hash") or "").strip(),
                  actor=actor, actor_verified=identity.actor_verification(actor),
                  person=bool(ident is not None and ident.kind == "person"),
                  reason=form.get("reason") or "")
    if got.get("refused"):
        return _draw(network, again, 403 if got.get("not_a_person") else 409,
                     error=got["refused"], reason=form.get("reason") or "")
    return _draw(network, dict(again, run=got["run"], job=got["job"]))
