"""The toolbar assistant's panel and its ask (card P7, stage 1; stage 2, docs/design/assistant.md;
PHASE8_PLAN 16.10; modules/ai/assistant.py): a question answered from the manual's passages and
the reads a person has of what is on screen, drawn in the panel's thread in place; a question
the manual does not cover is said and recorded as a manual gap.

The panel's open state is the browser's (nmas_v2.js); its thread is Mercury's, kept per person
(`assistant_threads`), so opening it, changing page or refreshing draws the same exchanges and
makes no call. The one call is a person's press of Ask."""
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


def _place(path: str, nav: str = "") -> dict:
    """What the page at *path* is about (`assistant_context.resolve`), on the network the
    request names (the page's own, `routes/page_network`), else the installation's."""
    from modules.ai import assistant_context
    from modules.nsot import listref
    from routes.list_param import named_list

    return assistant_context.resolve(path, network=named_list(request) or listref.active_name(),
                                     nav=nav)


@bp.route("/panel", methods=["GET"])
def panel():
    """The panel's head and body, asked the first time a person opens it on a page (the top
    bar's Assistant), so a page carries only its shell and the AI control's state is the one
    at opening. *path* is the page's own path and query, resolved by the server into what the
    panel is looking at; *nav* is the page's sidebar item, the screen whose passages rank first
    when the path names none. The person's thread is read, never asked again."""
    from modules import identity
    from modules.ai import assistant_threads

    place = _place(request.args.get("path", ""), request.args.get("nav", ""))
    thread = assistant_threads.read(identity.request_actor())
    return _strict(render_template("v2/_assistant_panel.html", place=place, thread=thread))


@bp.route("/ask", methods=["POST"])
def ask():
    """A person's question, answered as the person who asked (one recorded, capped AI call a
    pass; the reads it asks for of the device or incident in view, each recorded), or why not;
    a manual gap recorded; the exchange kept in the person's thread."""
    from modules import identity, redact
    from modules.ai import assistant, assistant_threads, triggers

    question = request.form.get("question", "")
    place = _place(request.form.get("path", ""))
    screen = place.get("screen") or request.form.get("screen", "")
    actor = identity.request_actor()
    got = assistant.answer(question, screen=screen, place=place, actor=actor,
                           trigger=triggers.person(actor))
    if got.get("gap"):
        assistant.record_gap(question, screen=screen, state=got["state"], actor=actor,
                             call_id=got.get("call_id") or "")
    # What the answer draws; whether it was a gap is the route's to record, said in the words.
    drawn = {k: v for k, v in got.items() if k not in ("ok", "gap", "error")}
    if drawn.get("plan"):
        # The plan acts on the network the person asked from: its preview is that network's.
        drawn["plan"] = dict(drawn["plan"], list=place.get("network") or "")
    drawn["question"] = redact.redact_typed(" ".join(question.split()))[:assistant.MAX_QUESTION]
    drawn["looking_at"] = place.get("label") or ""
    if got.get("state") != "refused" or got.get("call_id"):
        # A question refused before any call (empty, too long) is said, never kept.
        kept = assistant_threads.keep(actor, question, drawn["looking_at"], drawn)
        drawn["kept"] = "" if kept["ok"] else kept["error"]
    return _strict(render_template("v2/_assistant_answer.html", got=drawn))
