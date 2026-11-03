"""The toolbar assistant's ask (card P7, stage 1; PHASE8_PLAN 16.10; modules/ai/assistant.py):
a question answered from the manual's passages, drawn in the panel in place; a question the
manual does not cover is said and recorded as a manual gap."""
import logging

from flask import Blueprint, render_template, request

from modules import csp

log = logging.getLogger(__name__)

bp = Blueprint("assistant_v2", __name__, url_prefix="/v2/assistant")


def _strict(resp, code=200):
    from flask import make_response

    r = make_response(resp, code)
    r.headers["Content-Security-Policy"] = csp.STRICT_POLICY
    return r


@bp.route("/panel", methods=["GET"])
def panel():
    """The panel's head and body, asked the first time a person opens it on a page (the top
    bar's Assistant), so a page carries only its shell and the AI control's state is the one
    at opening. *nav* is the page's sidebar item, the screen whose passages rank first."""
    return _strict(render_template("v2/_assistant_panel.html",
                                   active_nav=request.args.get("nav", "")))


@bp.route("/ask", methods=["POST"])
def ask():
    """A person's question, answered from the manual as the person who asked (one recorded,
    capped AI call), or why not; a manual gap recorded."""
    from modules import identity
    from modules.ai import assistant, triggers

    question = request.form.get("question", "")
    screen = request.form.get("screen", "")
    actor = identity.request_actor()
    got = assistant.answer(question, screen=screen, actor=actor,
                           trigger=triggers.person(actor))
    if got.get("gap"):
        assistant.record_gap(question, screen=screen, state=got["state"], actor=actor,
                             call_id=got.get("call_id") or "")
    # What the answer draws; whether it was a gap is the route's to record, said in the words.
    drawn = {k: v for k, v in got.items() if k not in ("ok", "gap", "error", "cost_usd")}
    return _strict(render_template("v2/_assistant_answer.html", got=drawn))
