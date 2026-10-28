"""routes/ai_feedback_v2.py — Was this right? on every AI answer, and its review (PHASE8_PLAN
16.11 item 1; board FB, `AiFeedback.dc.html`, signed off under the Phase 7 mode 2026-10-28).

Two writes, each gated in `route_gates` on `configure` and refused by `modules/ai/feedback.py`
for anyone but a verified person, recording `identity.request_actor()`:

- ``say``: Yes, or No with what was wrong, under one answer; the control redrawn in place;
- ``review``: a No accepted into its case draft (bound to the draft's hash) or dismissed with
  a reason, on Settings › Installation › AI; the row redrawn opened.

And three reads: the review card (filtered, paged), one row opened (its call read then), and
one task's accepted case drafts as JSON. Nothing here calls a model or contacts a device.
"""

import json
import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("ai_feedback_v2", __name__, url_prefix="/v2/ai/feedback")


@bp.route("/answer/<call_id>", methods=["POST"])
def say(call_id):
    """Was this right? pressed under the answer of *call_id*: the control redrawn with the
    viewer's verdict, or with the refusal in place and the buttons kept."""
    from modules.ai import feedback

    form = request.form
    try:
        feedback.say(call_id, form.get("verdict", ""), why=form.get("why", ""),
                     words=form.get("words", ""))
    except feedback.Refused as exc:
        return _strict(render_template("v2/_ai_feedback.html", fb=feedback.control(call_id),
                                       fb_refused=str(exc)), 409)
    return _strict(render_template("v2/_ai_feedback.html", fb=feedback.control(call_id)))


@bp.route("/review", methods=["GET"])
def card():
    """The review card, Answers said wrong, as the filter asks."""
    from modules.ai import feedback

    a = request.args
    return _strict(render_template("v2/_ai_feedback_review.html",
                                   fbr=feedback.view(a.get("status", feedback.TO_REVIEW),
                                                   a.get("feature", ""), a.get("q", ""),
                                                   a.get("older", 0))))


def _row(fb_id, code=200, **extra):
    from modules.ai import feedback

    d = feedback.detail(fb_id)
    if not d["ok"]:
        return _strict(render_template("v2/_ai_feedback_detail.html", d=d), 404)
    return _strict(render_template("v2/_ai_feedback_row.html", v=d["v"], d=d, **extra), code)


@bp.route("/review/<fb_id>/open", methods=["GET"])
def row(fb_id):
    """One row opened: its call and the review's controls (the detail alone, swapped into the
    row's body)."""
    from modules.ai import feedback

    d = feedback.detail(fb_id)
    return _strict(render_template("v2/_ai_feedback_detail.html", d=d), 200 if d["ok"] else 404)


@bp.route("/review/<fb_id>", methods=["POST"])
def review(fb_id):
    """Accept into a case draft, or Dismiss: the row redrawn opened, settled or refused."""
    from modules.ai import feedback

    form = request.form
    try:
        feedback.review(fb_id, form.get("outcome", ""), reason=form.get("reason", ""),
                        draft_seen=form.get("draft", ""))
    except feedback.Refused as exc:
        return _row(fb_id, 409, rv_refused=str(exc))
    return _row(fb_id)


@bp.route("/drafts/<task>.json", methods=["GET"])
def drafts(task):
    """A task's accepted case drafts, for a maintainer to add to its case file."""
    from flask import Response

    from modules.ai import feedback

    if task not in feedback.FEATURES:
        return Response(json.dumps({"ok": False, "error": f"no task named {task!r}"}), 404,
                        mimetype="application/json")
    got = feedback.drafts(task)
    if got["state"] == "unreadable":
        return Response(json.dumps({"ok": False, "error": got["error"]}), 503,
                        mimetype="application/json")
    body = json.dumps({"ok": True, "task": task, "drafts": got["drafts"]}, indent=1,
                      sort_keys=True)
    return Response(body, 200, mimetype="application/json", headers={
        "Content-Disposition": f'attachment; filename="{task}-case-drafts.json"'})
