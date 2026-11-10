"""routes/sdn_policies_v2.py — OBSERVE › SDN › Policies, the intent controller (Lab 9 Objective
B2; board docs/boards/lab9-sdn.html artboard E, self-signed under the Phase 7 mode;
docs/fidelity/sdn-policies.md).

The tab is a read: the network's committed policies, from its flow intent
(`policy_intent.committed`), and the words box. Its operations, each drawn in place:
- **Draft the policy** (`draft`): one recorded, capped AI call as the person who pressed, on
  the ``sdn_policy`` pin, after the names are resolved in code (an ambiguous name asked back as
  buttons, an unknown one refused, both with no call); the answer checked in code
  (`policy_intent.draft`). Nothing is sent to a switch.
- **Drop instead…**, **Rate-limit at <switch> instead…** (`check`): an impossible rate limit's
  offers, the drafted policy checked again in code with the person's choice; no AI.
- **Preview the flows…** (`preview`): the checked policy compiled and planned by the
  flow-operation core (`flow_ops.plan`): the effect in words, every REST body, the hash.
  Writes nothing.
- **Send** (`confirm`): every check again, the same requests compiled, then `flow_ops.apply`
  as the verified person, bound to the hash; recorded in the flow intent as the policy.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("sdn_policies_v2", __name__, url_prefix="/v2/sdn/policies")


def _list_name() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return named_list(request) or listref.active().name


def _network_of_form() -> str:
    from routes.list_param import submitted_list

    name, _refusal = submitted_list(request)
    return name or _list_name()


def _ctx() -> dict:
    from modules import sdn_page, sdn_policies_page
    from routes.sdn_v2 import TABS

    return {"g": sdn_policies_page.policies_view(_list_name()), "tabs": TABS,
            "fresh": sdn_page.redraw_promise()}


@bp.route("", methods=["GET"])
def page():
    """SDN › Policies (board lab9-sdn, artboard E). A read."""
    from routes.v2 import _page

    return _page("v2/sdn_policies.html", active_nav="sdn", list_name=_list_name(), **_ctx())


@bp.route("/view", methods=["GET"])
def region():
    """The tab's region alone, re-read when `sdn` is announced. Writes nothing."""
    return _strict(render_template("v2/_sdn_policies.html", **_ctx()))


def _answer(a: dict, status: int = 200):
    return _strict(render_template("v2/_sdn_policy_answer.html", a=a)), status


@bp.route("/draft", methods=["POST"])
def draft():
    """Draft the policy: the names resolved in code, then one recorded, capped AI call as the
    person who pressed, its answer checked in code. Writes nothing; nothing reaches a switch.
    *word* and *pick* are the person's answer to Mercury's own question (which host a word
    means); Neither (an empty *pick*) ends the draft with nothing sent."""
    from modules import identity, sdn_policies_page
    from modules.ai import triggers
    from modules.sdn import policy_intent

    network = _network_of_form()
    sentence = request.form.get("words", "")
    word, pick = (request.form.get("word") or "").strip(), request.form.get("pick")
    if word and pick is not None and not pick.strip():
        return _answer(sdn_policies_page.answer_view(network, dict(
            policy_intent.mercury("refused", "neither", (
                f"You chose neither for \"{word}\": name the host as NetBox does, and draft "
                "again; nothing was sent")), words_typed=" ".join(sentence.split()))), 409)
    picks = {word: pick.strip()} if word and pick else None
    actor = identity.request_actor()
    got = policy_intent.draft(network, sentence, actor=actor, trigger=triggers.person(actor),
                              picks=picks)
    return _answer(sdn_policies_page.answer_view(network, got),
                   200 if got.get("state") in ("checked", "asked", "question") else 409)


def _carried():
    from modules.sdn import policy_intent

    try:
        return policy_intent.carried(request.form.get("policy", "")), ""
    except policy_intent.Refused as exc:
        return None, str(exc)


@bp.route("/check", methods=["POST"])
def check():
    """Drop instead… or Rate-limit at <switch> instead… on an impossible rate limit: the
    drafted policy checked again in code with the person's choice, each held to what the
    refusal offered. No AI; writes nothing."""
    from modules import sdn_policies_page
    from modules.sdn import policy_intent

    network = _network_of_form()
    policy, refused = _carried()
    if refused:
        return _answer(sdn_policies_page.answer_view(network, policy_intent.mercury(
            "refused", "malformed", refused)), 400)
    kind, place = (request.form.get("instead_kind") or "").strip(), \
        (request.form.get("instead_place") or "").strip()
    instead = {"kind": kind} if kind else {"place": int(place)} if place.isdigit() else None
    if instead is None:
        return _answer(sdn_policies_page.answer_view(network, policy_intent.mercury(
            "refused", "malformed", "the form names no choice (drop instead, or a switch)")),
            400)
    got = policy_intent.check(network, policy, instead=instead)
    got["words_typed"] = policy.get("words", "")
    return _answer(sdn_policies_page.answer_view(network, got), 200 if got["ok"] else 409)


def _op_card(d: dict, status: int = 200):
    return _strict(render_template("v2/_sdn_op.html", d=d)), status


@bp.route("/preview", methods=["POST"])
def preview():
    """Preview the flows…: the checked policy compiled and planned by the flow-operation core,
    read from the switch now: the effect in words, every request and its undo, the hash.
    Writes nothing."""
    from modules import sdn_ops_page, sdn_policies_page
    from modules.sdn import policy_intent

    network = _network_of_form()
    policy, refused = _carried()
    if refused:
        return _op_card(sdn_ops_page.refused(network, "policy", refused), 400)
    got = policy_intent.preview(network, policy)
    return _op_card(sdn_policies_page.preview_card(network, got), 200 if got["ok"] else 409)


@bp.route("/confirm", methods=["POST"])
def confirm():
    """Apply the previewed policy as the verified person, bound to the preview's hash: every
    check again, the same requests compiled, then the flow-operation core's apply."""
    from modules import identity, sdn_ops_page
    from modules.sdn import policy_intent

    network = _network_of_form()
    policy, refused = _carried()
    ask, refused_ask = sdn_ops_page.carried_ask(request.form)
    if refused or refused_ask:
        return _op_card(sdn_ops_page.refused(network, "policy", refused or refused_ask), 400)
    actor = identity.request_actor()
    done = policy_intent.confirm(network, policy, ask, (request.form.get("hash") or "").strip(),
                                 actor=actor, actor_verified=identity.actor_verification(actor))
    return _op_card(sdn_ops_page.result(network, "policy", done),
                    200 if done.get("outcome") != "refused" else 409)
