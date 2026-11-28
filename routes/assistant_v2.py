"""The toolbar assistant's panel and its chat (card P7, stage 1; stage 2, docs/design/assistant.md;
PHASE8_PLAN 16.10; the chat, the operator's order of 2026-11-28; modules/ai/assistant.py): a
question answered from the manual's passages and the reads a person has of what is on screen,
drawn in the person's conversation in place; a question the manual does not cover is said and
recorded as a manual gap.

The panel's open state and width are the browser's (nmas_v2.js, nmas_assistant.js); its
conversations are Mercury's, kept per person (`assistant_threads`), so opening it, changing page
or refreshing draws the same exchanges and makes no call. The one call is a person's press of
Send, run as a job (`assistant_turns`): the press is answered at once with its turn, which the
panel re-reads on each announced step (`assistant`) until its answer is drawn."""
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


def _args():
    """The page's path and sidebar item, from the form a press sends or the query a read
    asks with."""
    src = request.form if request.method == "POST" else request.args
    return src.get("path", ""), src.get("nav", "")


def _panel(notice: str = "", code: int = 200):
    from modules import identity
    from modules.ai import assistant_threads

    path, nav = _args()
    place = _place(path, nav)
    actor = identity.request_actor()
    thread = assistant_threads.read(actor)
    models, chosen = _models(thread)
    return _strict(render_template(
        "v2/_assistant_panel.html", place=place, nav=nav, thread=thread,
        turns=assistant_threads.running(actor), past=assistant_threads.past(actor),
        keep=assistant_threads.KEEP, notice=notice, models=models, chosen=chosen), code)


def _models(thread: dict) -> tuple:
    """The box's model selector: the models the assistant offers (`profiles.choices`), and the
    one chosen, the model this conversation's newest answer ran on while it is still offered
    (so a choice follows the person across pages and reloads, kept nowhere but the answer),
    else the pin's."""
    from modules.ai import assistant, profiles

    models = profiles.choices(assistant.FEATURE)
    offered = {m["model"] for m in models}
    chosen = profiles.task(assistant.FEATURE)["model"]
    for row in reversed(thread.get("rows") or []):
        ran = ((row or {}).get("got") or {}).get("model")
        if ran:
            if ran in offered:
                chosen = ran
            break
    return models, chosen


@bp.route("/panel", methods=["GET"])
def panel():
    """The panel's head, conversation and box, asked the first time a person opens it on a
    page (the top bar's Assistant), so a page carries only its shell and the AI control's state
    is the one at opening. *path* is the page's own path and query, resolved by the server into
    what the panel is looking at; *nav* is the page's sidebar item, the screen whose passages
    rank first when the path names none. The person's conversation is read, never asked
    again."""
    return _panel()


@bp.route("/place", methods=["GET"])
def place():
    """The head's Looking at chip for the page at *path* (the person moved within a page, its
    address changed): resolved by the server, as the panel's own is. A read."""
    path, nav = _args()
    return _strict(render_template("v2/_assistant_place.html", place=_place(path, nav)))


def _turn(state: dict, code: int = 200):
    return _strict(render_template("v2/_assistant_turn.html", t=state), code)


@bp.route("/ask", methods=["POST"])
def ask():
    """A person's question: refused at once when it is empty or too long (never kept), else
    its turn kept and its job started (`assistant_turns.start`: one recorded, capped AI call a
    pass as the person who asked, and the reads it asks for of the device or incident in view,
    each recorded), and the turn drawn working (which puts Stop in the box's place)."""
    from modules import identity
    from modules.ai import assistant, assistant_threads, assistant_turns

    question = request.form.get("question", "")
    place_ = _place(request.form.get("path", ""), request.form.get("nav", ""))
    screen = place_.get("screen") or request.form.get("screen", "")
    actor = identity.request_actor()
    model = request.form.get("model", "")
    refused = assistant.refusal(question) or _model_refusal(model)
    if refused:
        # A question refused before any call (empty, too long) is said, never kept.
        got = assistant_turns.drawn_of(refused, question, place_)
        return _turn({"state": "done", "row": {"question": got["question"], "got": got,
                                               "looking_at": got["looking_at"]}})
    begun = assistant_threads.begin(actor, question, place_.get("label") or "",
                                    place_.get("asked") or "")
    if not begun["ok"]:
        return _turn({"state": "refused", "why": begun["error"]}, 409)
    assistant_turns.start(actor, begun["turn"], question, screen, place_, model=model or None)
    return _turn(assistant_threads.turn_of(actor, begun["turn"]) | {"turn": begun["turn"]})


def _model_refusal(model: str):
    """The question's refusal, said at once and never kept, when *model* (the box's selector;
    "" for the pin's) is not one the assistant offers (`profiles.choice_refusal`, which the
    gateway asks again at the call); None when it is."""
    from modules.ai import assistant, profiles

    if not model:
        return None
    why = profiles.choice_refusal(assistant.FEATURE, model, person=True)
    if not why:
        return None
    return {"ok": False, "state": "refused", "error": "model_choice",
            "detail": f"Couldn't answer: {why}", "gap": False}


@bp.route("/turn/<turn>", methods=["GET"])
def turn(turn):
    """One question of the person's, as it is now: working with its step, stopping, its
    answer once kept, or lost (its job showed no sign of life: said; the person's next press
    keeps it in the conversation as lost, `assistant_threads.settle_lost`). A read. *turn*
    is the press's id, shaped `assistant_threads.TURN_ID`."""
    from modules import identity
    from modules.ai import assistant_threads

    actor = identity.request_actor()
    return _turn(dict(assistant_threads.turn_of(actor, turn), turn=turn))


@bp.route("/stop", methods=["POST"])
def stop():
    """Stop on the person's question being answered (one at a time per person, so it is the
    one): its turn marked stopped (`assistant_threads.stop`), read by its job; the turn drawn
    stopping, in its place, until its job ends. With none being answered, said."""
    from modules import identity
    from modules.ai import assistant_threads

    actor = identity.request_actor()
    working = [t for t in assistant_threads.running(actor) if t["state"] in ("working",
                                                                             "stopping")]
    if not working:
        return _turn({"state": "refused", "why": "no question of yours is being answered now"},
                     409)
    turn = working[-1]["turn"]
    assistant_threads.stop(actor, turn)
    return _turn(dict(assistant_threads.turn_of(actor, turn), turn=turn))


@bp.route("/new", methods=["POST"])
def new():
    """New conversation: the current one kept in the person's past conversations, as it is;
    the panel drawn again, empty."""
    from modules import identity
    from modules.ai import assistant_threads

    got = assistant_threads.new(identity.request_actor())
    return _panel("" if got["ok"] else f"Not started: {got['error']}.", 200 if got["ok"] else 409)


@bp.route("/reopen", methods=["POST"])
def reopen():
    """A past conversation made the current one again, the current one kept in its place;
    the panel drawn again with it."""
    from modules import identity
    from modules.ai import assistant_threads

    got = assistant_threads.reopen(identity.request_actor(), request.form.get("conversation", ""))
    return _panel("" if got["ok"] else f"Not reopened: {got['error']}.", 200 if got["ok"] else 409)
