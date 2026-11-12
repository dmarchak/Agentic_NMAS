"""routes/update.py — what the Update page posts and reads (modules/update_op.py;
docs/UPDATE.md). The page is `v2.update` (routes/v2.py).

- POST /update/apply   confirm by the preview's hash: writes the REQUEST the
                       root-owned updater acts on (gate `confirm`, a person).
                       Posted by htmx from the page's form fields (`hash`,
                       `when`, each ticked `host_step`); it answers with the
                       Update panel drawn again (`v2/_update.html`): the
                       stepper following the request, the wait, or the
                       refusal with its reason (C850: the one confirm
                       pattern, Stage 7 acceptance criterion 6);
- POST /update/host-step/done   a person says an AFTER host step is done (`sha`,
                       `step`); it answers with the panel drawn again;
- POST /update/host-step/decline   a person declines an AFTER host step the
                       running release owes, with a reason (`sha`, `step`,
                       `why`; the operator, 2026-11-11): recorded beside done,
                       no longer owed, kept by History; it answers with the
                       panel drawn again;
- GET  /update/status  what runs, what waits, what the updater last said: the
                       waiting page reads it beside /health;
- POST /update/check   runs the `app-pushed` reader now, on a thread, as the
                       person's request (reader_job rule 13), so a person need
                       not wait for its next run after a push; the answer is
                       announced even when nothing changed, and the reply names
                       the run and how long the page waits before calling it late.
"""

import logging
import time

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("update", __name__, url_prefix="/update")


def _panel(code: int, refusal: str = "", following: str = "", step_refusal: dict = None):
    """The Update panel drawn again (`v2/_update.html`, the page's own `v2.update_panel`), the
    answer to each confirm on it: htmx swaps it in place, so the stepper, the wait or the
    refusal is drawn by the server. *following*: the request just written, whose stepper the
    page follows from the updater's record (the same as a wait the app released,
    `update_op.following`). The ticked host steps are carried, as on a live redraw (C472)."""
    from flask import render_template

    from routes.device_v2 import _strict, _who
    from routes.v2 import _update_ctx

    ctx = _update_ctx()
    if following:
        ctx["p"] = dict(ctx["p"], following=following)
    return _strict(render_template("v2/_update.html", who=_who(), refusal=refusal,
                                   step_refusal=step_refusal or {}, **ctx), code)


@bp.route("/apply", methods=["POST"])
def apply():
    from modules import identity, update_op

    form = request.form
    when = str(form.get("when") or "")
    actor = identity.request_actor()
    if when == "stop":
        # Stop waiting for CI: nothing is updated; the panel is drawn with no wait.
        got = update_op.stop_waiting(actor)
        if not got["ok"]:
            return _panel(409, refusal="Not stopped: " + got["reason"])
        return _panel(200)
    ack = [str(a) for a in form.getlist("host_step") if a]
    confirmed = str(form.get("hash") or "")
    if when == "ci":
        # Update when CI passes: confirmed now, requested by the app the
        # moment CI passes this release (modules/update_op.py). The panel
        # draws the wait in force.
        got = update_op.defer(confirmed, ack, actor)
        if got["ok"] and got.get("waiting"):
            return _panel(202)
    else:
        got = update_op.request(confirmed, ack, actor)
    if not got["ok"]:
        return _panel(409, refusal="Not requested: " + got["reason"])
    # Requested: the updater re-checks CI itself, moves the checkout, restarts the app and
    # confirms the new commit, or rolls back; the panel follows its record and /health.
    return _panel(202, following=str(got.get("id") or ""))


@bp.route("/host-step/done", methods=["POST"])
def step_done():
    """A person says an AFTER host step no check can answer is done. Only a
    step the running release owes, and only one nothing can check: a check's
    answer is never overridden by a click."""
    from modules import host_steps, identity
    from routes import health

    sha = str(request.form.get("sha") or "")
    step = str(request.form.get("step") or "")

    def refused(why):
        return _panel(409, step_refusal={"sha": sha, "step": step, "error": why})

    owed = host_steps.owed(health._COMMIT or "")
    if not owed["ok"]:
        return refused(owed["error"])
    # One row may stand for several commits that asked for the same step
    # (host_steps.grouped): saying it done says it for each of them.
    match = [s for s in owed["steps"]
             if sha in (s.get("shas") or [s["sha"]]) and s["step"] == step]
    if not match:
        return refused(_closed_words(owed, sha, step)
                       or "that step is not one the running release owes")
    if match[0]["check_state"] != "not_checkable":
        return refused("the tool checks this step itself: " + match[0]["check_detail"])
    for each in match[0].get("shas") or [sha]:
        got = host_steps.record_done(each, step, identity.request_actor())
        if not got["ok"]:
            return refused(got["reason"])
    # Drawn back under "Host steps said done": who said so, and when.
    return _panel(200)


def _closed_words(owed: dict, sha: str, step: str) -> str:
    """Who already said *step* of *sha* done, or declined it, and when, or ""."""
    for key, verb in (("said_done", "said done"), ("declined", "declined")):
        for s in owed.get(key) or []:
            if sha in (s.get("shas") or [s.get("sha")]) and s.get("step") == step:
                from modules import display_names       # board E2a: a person by display name

                who = display_names.people(s.get("by") or "") or "an unnamed person"
                return (f"that step was already {verb} by {who} "
                        f"at {str(s.get('at') or 'an unrecorded time').replace('T', ' ')[:16]}"
                        f"{' UTC' if s.get('at') else ''}"
                        + (f": {s['why']}" if s.get("why") else ""))
    for s in owed.get("checked_done") or []:
        if sha in (s.get("shas") or [s.get("sha")]) and s.get("step") == step:
            return "the tool's check reads that step done: " + str(s.get("check_detail") or "")
    return ""


@bp.route("/host-step/decline", methods=["POST"])
def step_decline():
    """A person declines an AFTER host step the running release owes, with a reason (the
    operator, 2026-11-11: "decline the local-CI-runner steps (CI stays on GitHub-hosted
    runners)"). Refused: no reason; a step not owed (one already said done or declined is
    named with who and when); an unverified request. Declining is never saying it is done: a
    check's answer stays the check's."""
    from modules import host_steps, identity
    from routes import health

    sha = str(request.form.get("sha") or "")
    step = str(request.form.get("step") or "")
    why = str(request.form.get("why") or "")

    def refused(words):
        return _panel(409, step_refusal={"sha": sha, "step": step, "error": words,
                                         "decline": True})

    actor = identity.request_actor()
    if not actor or actor == identity.UNVERIFIED:
        return refused("no verified person: a host step is declined by a verified person")
    owed = host_steps.owed(health._COMMIT or "")
    if not owed["ok"]:
        return refused(owed["error"])
    match = [s for s in owed["steps"]
             if sha in (s.get("shas") or [s["sha"]]) and s["step"] == step]
    if not match:
        return refused(_closed_words(owed, sha, step)
                       or "that step is not one the running release owes")
    problem = host_steps.decline_reason_problem(why)
    if problem:
        return refused(problem)
    verified = identity.actor_verification(actor)
    # One row may stand for several commits that asked for the same step (host_steps.grouped):
    # declining it declines it for each of them.
    for each in match[0].get("shas") or [sha]:
        got = host_steps.record_decline(each, step, actor, why, verified=verified)
        if not got["ok"]:
            return refused(got["reason"])
    # Drawn back under "Host steps declined": who, when and why; History keeps it.
    return _panel(200)


@bp.route("/status", methods=["GET"])
def status():
    from modules import update_op

    return jsonify(dict(update_op.status(), ok=True))


@bp.route("/check", methods=["POST"])
def check():
    """Run the reader now, once; a second press while it runs is told so."""
    from modules import reader_job
    from modules.readers import app_pushed

    if not reader_job.running(app_pushed.READER.name):
        return jsonify({"ok": False, "error": (
            "the reader jobs do not run in this process, so nothing was asked; the app's "
            f"own reader asks every {app_pushed.INTERVAL_SECONDS} s")}), 409
    from modules import identity

    who = identity.viewer()
    # Recorded as the person's request (reader_job rule 13), announced even
    # when the answer did not change, because this person is waiting on it.
    got = reader_job.request_run(app_pushed.READER, who.actor if who.is_identified else "",
                                 announce=reader_job.announce_via_page)
    bound = reader_job.answer_bound(app_pushed.READER.name)
    # An age, never an epoch: the browser's clock is not the host's.
    body = {"ok": True, "started": got["started"], "run": got["run"],
            "running_for": round(time.time() - got["since"], 1),
            "bound_seconds": bound["seconds"], "bound_basis": bound["basis"],
            "message": ("asking origin and CI now; this stays busy until the answer arrives"
                        if got["started"] else
                        "a check is already running; this waits for its answer")}
    return jsonify(body), (202 if got["started"] else 200)
