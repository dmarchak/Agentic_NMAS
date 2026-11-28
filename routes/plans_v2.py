"""routes/plans_v2.py — a plan of Mercury's operations, previewed together and approved once by
its hash (modules/plan_engine.py), drawn in place where it was offered (the toolbar assistant's
answer, `templates/v2/_assistant_answer.html`) by `templates/v2/_plan_card.html`.

- ``preview`` (GET): the plan named (``plan``) with its parameters (``params``, one JSON object),
  every step previewed by its own operation, the plan's hash, a reason, and Approve the plan,
  named for the work; with ``run`` (and ``job``), the run's state or its result in place.
  ``card`` names the card's own id (`card_id`) when the assistant's conversation draws several.
- ``approve`` (POST): the plan started as a job as the verified person, bound to the plan's
  hash (``hash``); or the refusal drawn in place, nothing run.

Its declarations live in their tables (`route_gates.GATES`, `invalidation.DECLARED`,
`operation_stages.STAGES` and `HISTORY`).
"""

import json
import logging
import re

from flask import Blueprint, render_template, request

from routes.assistant_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("plans_v2", __name__, url_prefix="/v2/plans")

def _params_chars() -> int:
    """The longest ``params`` a request may carry (C4329: 2,000 refused a change of a few
    steps): the largest plan the step kinds take, `plan_engine.MOST_STEPS` steps each of
    `plan_engine.MOST_CHANGES` changes, each change's path, before and after within 512
    characters. Derived from the plan engine's own bounds, not measured; the chat never sends
    them in an address (its card is asked by the answer's id, `_answered_plan`)."""
    from modules import plan_engine as E

    return E.MOST_STEPS * E.MOST_CHANGES * 512


#: The longest ``params`` a request may carry (`_params_chars`: 163,840 today).
PARAMS_CHARS = _params_chars()


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


def _answered_plan(call_id: str, network: str) -> tuple:
    """``({"plan", "params"}, "")``: the plan the asking person's own assistant answer *call_id*
    proposed, as their conversation keeps it (C4329: the chat asks a card by its answer's id, so
    a long change's parameters never travel in an address); or ``(None, why)``: no answer of
    theirs with that id proposed one, or it was proposed on another network than *network*. A
    read of the person's own thread only (`assistant_threads.read`)."""
    from modules import identity
    from modules.ai import assistant_threads

    for row in assistant_threads.read(identity.request_actor()).get("rows") or []:
        got = (row or {}).get("got") or {}
        plan = got.get("plan") or {}
        if not call_id or got.get("call_id") != call_id or not plan:
            continue
        if (plan.get("list") or "") != network:
            return None, (f"that answer's plan is for {plan.get('list') or 'no network'}, "
                          f"not {network}")
        return {"plan": plan.get("plan") or "",
                "params": json.dumps(plan.get("params") or {}, sort_keys=True,
                                     separators=(",", ":"))}, ""
    return None, "no answer of yours in this conversation proposed that plan"


def _kept(rec: dict) -> dict:
    """The run's record as the card draws it: its steps are drawn by the stepper
    (`_run_view`), so the record goes without them (a route hands its template only what it
    draws)."""
    return {k: v for k, v in rec.items() if k != "plan_steps"}


def _run_view(network: str, rec: dict, job: str) -> dict:
    """A plan's run as its own page draws it (the operator, 2026-11-16: "A plan with no
    incident (an assistant plan) gets the same stepper on its own page, with its title, the
    device, and the exact actions"): ``{"steps", "devices", "actions"}``, *steps* the incident
    card's stepper (`fixit.progress.plan_lines`: each step's own operation's steps, the step
    running read live from *job*), *devices* those its steps act on, *actions* each step's
    words and what it sent (its own run's program, masked) or its parameters."""
    from modules import op_progress
    from modules.fixit import progress
    from modules.nsot import privileged
    from modules.redact import redact_text

    plan_steps = rec.get("plan_steps") or []
    devices = [d for d in dict.fromkeys(str((s.get("params") or {}).get("device") or "")
                                        for s in plan_steps) if d]
    actions = []
    for s in plan_steps:
        params = s.get("params") if isinstance(s.get("params"), dict) else {}
        run_id = str((s.get("receipt") or {}).get("run") or "")
        own = None
        if run_id:
            try:
                own = privileged.get(network, run_id)
            except (OSError, ValueError):
                own = None
        sent = [redact_text(str(x)) for x in (own or {}).get("program") or []]
        actions.append({"n": s.get("n"), "words": str(s.get("words") or ""),
                        "device": str(params.get("device") or ""), "lines": sent,
                        "params": [] if sent else [
                            (k, redact_text(", ".join(map(str, v)) if isinstance(v, (list, tuple))
                                            else str(v)))
                            for k, v in params.items() if k not in ("incident", "proposal")]})
    live = op_progress.run_of(job) if job else None
    return {"steps": progress.plan_lines(network, rec, devices[0] if len(devices) == 1 else "",
                                         live),
            "devices": devices, "actions": actions}


#: The card's own id: `CARD` alone, or with the answer's call id when the toolbar assistant's
#: conversation draws several plans at once (each card's Approve swaps its own card).
CARD = "plan-card"
_CARD_ID = re.compile(r"plan-card(?:-[A-Za-z0-9_-]{1,80})?\Z")


def card_id(value) -> str:
    """The card's id as the request names it (``card``), when it is one of a card's shape;
    `CARD` otherwise."""
    value = str(value or "")
    return value if _CARD_ID.match(value) else CARD


def card(network: str, args, **answer) -> dict:
    """The card's context in the state its query names: ``preview``, ``running`` or
    ``result``; reads only Mercury's records (and each step's own dry run)."""
    from modules import plan_engine as E

    answered_why = ""
    if args.get("answer") and not args.get("params"):
        # The chat's card, asked by its answer's id (C4329): the plan the person's own
        # conversation keeps, never one the address carries; not found, its refusal says why.
        found, answered_why = _answered_plan(str(args.get("answer") or "")[:64], network)
        args = dict(args.items(), **(found or {"plan": "", "params": ""}))
    c = {"list": network, "plan": str(args.get("plan") or "")[:64], "error": "",
         "run": str(args.get("run") or "")[:80], "job": str(args.get("job") or "")[:80],
         "reason": str(args.get("reason") or "")[:300], "state": "preview",
         "card": card_id(args.get("card")), "outcome_words": dict(E.OUTCOME_WORDS)}
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
            c["record"] = _kept(rec or {})
            # Its steps on the incident card's stepper once the run has recorded them, with its
            # title, its devices and each step's exact actions (`_run_view`).
            c.update(_run_view(network, rec, c["job"]) if rec and rec.get("plan_steps")
                     else {"steps": [], "devices": [], "actions": []})
            c["job_failed"], c["job_unknown"] = "", ""
            if c["job"]:
                # The job's own state while the record says running (or there is none yet): a
                # job that ended without its record's end (it raised before writing it) is said,
                # never drawn running for ever; and so is a job this server does not know
                # (C3651: never started here, expired, or the server restarted mid-run), its
                # redraw stopped.
                from modules.nsot import capture_job
                got = capture_job.get(c["job"])
                job = got or {}
                if job.get("state") in ("failed", "done"):
                    c["job_failed"] = redact_text(job.get("error") or job.get("reason") or
                                       f"its job {c['job']} ended, and no record was written")
                elif got is None:
                    c["job_unknown"] = (f"its job {c['job']} is not known to Mercury now: it may "
                                        "have ended in a restart, so whether its steps ran is "
                                        "not known here")
        else:
            c.update(_run_view(network, rec, ""))
            c.update(state="result", record=_kept(rec),
                     level=("ok" if rec.get("state") == "done" else
                            "warn" if rec.get("outcome") == "partial" else "danger"))
        return c
    why = answered_why or why
    if why:
        c["preview"] = {"ok": False, "refused": why, "steps": []}
        return c
    if not c["plan"]:
        # The page opened with no plan named (Stage 5 step 6, the survey's plan preview line:
        # "Refuse in words"): said as the page's sentence, never the engine's list of plan keys
        # and "'' was named".
        c["preview"] = {"ok": False, "refused": "", "none_chosen": True, "steps": []}
        return c
    # What the card draws of the engine's preview (its parameters are the card's own, carried
    # in `params_json`).
    got = E.preview(network, c["plan"], params)

    c["preview"] = dict({k: v for k, v in got.items() if k not in ("code", "params")},
                        refused=redact_text(got.get("refused") or ""),
                        steps=[{k: s.get(k) for k in ("n", "words", "drawn")}
                               for s in got.get("steps") or []])
    # Everything the plan's hash binds, drawn before Approve (C3725), masked as the preview is.
    c["preview"]["bound"] = ([(label, redact_text(words)) for label, words in E.bound_rows(
        network, got.get("plan") or "", got.get("params") or {}, got.get("steps") or [],
        got.get("hash") or "")] if got.get("ok") else [])
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
    again = {"plan": form.get("plan") or "", "params": form.get("params") or "",
             "card": form.get("card") or ""}
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
