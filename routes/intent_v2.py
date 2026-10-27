"""routes/intent_v2.py — the device page's Intent tab, edited in place (board H, signed off
2026-10-04; C444, C481).

Edit turns the read-only card into H's editor: the committed document in a text area, checked
as you type (the checks, the render of the edit against what is committed, what a deploy would
send, the lines the parser does not model and whether each is acknowledged), then one commit
with its reason, bound to the version opened. Every step is `modules/nsot/intent_edit.py`'s
(today's editor, which used it too, left at 7.8 on 2026-10-17, P7-23). The device's own list is carried on every call (a write
path carries its list), never the installation's active one. Nothing here contacts a device.
"""

import json
import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _device_or_404, _strict, carry_list

log = logging.getLogger(__name__)

bp = Blueprint("intent_v2", __name__, url_prefix="/v2/device")
bp.url_defaults(carry_list)       # the page's network on every URL it draws (C494)


def may_commit() -> dict:
    """Whether the viewer may commit intent (route_gates: approve), from the gate's own
    functions, so the screen cannot disagree with the commit."""
    from modules import preview_confirm

    return preview_confirm.confirm_part(request, "approve")


def editor_ctx(ref, dev, text: str = None, base: str = None, summary: str = "",
               refused: dict = None) -> dict:
    """What H's editing card draws: the document (the committed one unless *text* carries an
    edit in progress), the blob it was opened at, who last changed it, the reason typed."""
    from modules.nsot import hostvars, intent_edit

    host = dev.get("hostname", "")
    opened = {}
    if text is None:
        opened = intent_edit.open_doc(ref.name, host)
        if not opened.get("ok"):
            return {"state": "refused", "host": host, "list": ref.name,
                    "why": opened.get("error", "the committed intent could not be read")}
        text, base = opened["yaml"], opened["base"]
    last = hostvars.last_intent_commit(intent_edit._repo_for(ref.name), host) or {}
    return {"state": "editing", "host": host, "list": ref.name, "text": text, "base": base,
            "summary": summary, "last": last, "refused": refused or {},
            "confirm": may_commit()}


def _card(ctx: dict, code: int = 200):
    return _strict(render_template("v2/_intent_edit.html", c=ctx), code)


@bp.route("/<name>/intent/edit", methods=["GET"])
def edit(name):
    """H's editor in place of the read-only card."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _card(editor_ctx(ref, dev))


@bp.route("/<name>/intent/normalise", methods=["GET"])
def normalise(name):
    """Normalise the formatting… (C1693, board H-N): H's editor opened on the committed
    document in Mercury's own serialisation, at the blob it was read from. Writes nothing: the
    check proves it formatting only, and the commit is the editor's own, refused by the
    server unless the proof passes (`intent_edit.commit`)."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _card(normalise_ctx(ref, dev))


def normalise_ctx(ref, dev) -> dict:
    """H's editing card on the committed document in Mercury's own formatting, with how many
    of its lines changed formatting; the refusal when it cannot be normalised."""
    from modules.nsot import intent_normalise

    ctx = editor_ctx(ref, dev)
    if ctx["state"] != "editing":
        return ctx
    committed = ctx["text"]
    try:
        text = intent_normalise.normalised(committed, ctx["host"])
    except ValueError as exc:
        return {"state": "refused", "host": ctx["host"], "list": ref.name,
                "why": f"its formatting cannot be normalised: {exc}"}
    ctx.update(text=text, normalising={
        "changed": intent_normalise.changed_lines(committed, text),
        "total": len(text.splitlines())})
    return ctx


#: A draft's preview keys the row draws: `_intent_words.html`'s and the intent editor's check
#: partial's (`_intent_check.html`), and no others.
_DRAFT_DRAWN = ("changed", "changes", "device_keeps", "message", "yaml", "vs_intent_changed",
                "blocking_reasons",
                "column", "deployable", "diffs", "document_changed", "error", "intent_note",
                "line", "masked_not_compared", "ok", "rendered", "template", "unmodelled")
#: Of its `diffs`, what the check partial reads (`d.*`), with the golden's sha and time and each
#: pending line's words.
_DIFFS_DRAWN = ("edit_changes", "edit_rows", "from_edit", "from_edit_rows", "golden",
                "not_from", "not_removed", "replaces", "same", "sent")
_PENDING_DRAWN = ("at", "line", "section", "sha", "then", "words")


def _drawn(p: dict) -> dict:
    """A draft's preview cut to what the row draws (every carried field is drawn)."""
    out = {k: p[k] for k in _DRAFT_DRAWN if k in p}
    out["changes"] = [{"summary": c.get("summary", "")} for c in p.get("changes") or []
                      if isinstance(c, dict)]
    d = p.get("diffs")
    if isinstance(d, dict):
        out["diffs"] = {k: d[k] for k in _DIFFS_DRAWN if k in d}
        if isinstance(d.get("golden"), dict):
            out["diffs"]["golden"] = {k: d["golden"][k] for k in ("sha", "timestamp")
                                      if k in d["golden"]}
        out["diffs"]["not_from"] = [{k: n[k] for k in _PENDING_DRAWN if k in n}
                                    for n in d.get("not_from") or [] if isinstance(n, dict)]
    return out


@bp.route("/<name>/intent/words", methods=["POST"])
def words(name):
    """Change it in words (PHASE8_PLAN feature 7, 15.16; board F7): one recorded, capped AI
    call as the person who asked, its draft a patch to THIS device's intent alone, previewed by
    the intent editor (`intent_words.change`). Writes nothing; nothing reaches the device."""
    from modules import identity
    from modules.ai import intent_words, profiles, triggers

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    host = dev.get("hostname", "")
    sentence = request.form.get("words", "")
    # The person's answer to Mercury's own question (part 1): which of the candidates a
    # reference or an unknown name means, "*" for every one; it continues the same draft.
    phrase, chosen = request.form.get("phrase", ""), request.form.getlist("pick")
    picks = {phrase: "*" if "*" in chosen else chosen} if phrase and chosen else None
    # The person's answer to Mercury's other questions (C1907: both ends, alternatives, an
    # area, a description's text): a button's value, or the field's text; the same draft
    # continues from the sentence as decided.
    kind = request.form.get("ask", "")
    value = request.form.get("answer", "") or request.form.get("answer_text", "")
    answer = {"kind": kind, "value": value} if kind else None
    actor = identity.request_actor()
    got = intent_words.change(ref.name, sentence, actor=actor, trigger=triggers.person(actor),
                              devices=[host], picks=picks, answer=answer)
    pin = profiles.TASKS.get(intent_words.FEATURE) or {}
    model = f"{profiles.profile(pin['model'])['words']}, {pin['model']}" if pin else ""
    # What the row draws, and only that (every carried field is drawn): the answer in words,
    # how the names were read, Mercury's question or the unknown name with the device's
    # interfaces, and each preview as the editor's check partial reads it (the patch and its
    # base, which a commit will carry, are not drawn here).
    w = {k: got[k] for k in ("ok", "error", "detail", "clarify", "by", "cost_usd",
                             "resolutions", "resolution_said", "choose", "unknown", "call_id",
                             "decided")
         if k in got}
    if got.get("question"):
        q = got["question"]
        w["question"] = {"kind": q["kind"], "question": q["question"],
                         "choices": [{"label": c["label"], "value": str(c["value"])}
                                     for c in q.get("choices") or []],
                         "field": q.get("field")}
    w["previews"] = [_drawn(p) for p in got.get("previews") or []]
    for drawn, p in zip(w["previews"], got.get("previews") or []):
        drawn["hostname"] = p.get("hostname", "")
        if p.get("draft"):
            # Part 2: what Commit this draft posts back, exactly as drafted (its digest is on
            # the call's use row, so a commit handed anything else is refused).
            drawn.update(draft=p["draft"], base=p.get("base", ""),
                         patch_json=json.dumps(p.get("patch"), sort_keys=True))
    if got.get("pair"):
        # C1908: one draft of both ends; Commit both devices' intent posts both patches back,
        # exactly as drafted (the pair's digest is on the call's use row).
        pr = got["pair"]
        w["pair"] = {"device": pr["device"], "port": pr["port"], "far": pr["far"],
                     "far_port": pr["far_port"], "facts": list(pr.get("facts") or []),
                     "draft": pr.get("draft", ""), "pair_json": json.dumps(
                         [{"hostname": p.get("hostname"), "patch": p.get("patch"),
                           "base": p.get("base", "")} for p in got.get("previews") or []],
                         sort_keys=True) if pr.get("draft") else ""}
    return _strict(render_template("v2/_intent_words.html", host=host,
                                   w=dict(w, sentence=got.get("decided") or sentence,
                                          model=model)))


@bp.route("/<name>/intent/words/commit", methods=["POST"])
def words_commit(name):
    """Commit this draft (feature 7's part 2): the drafted patch committed to THIS device's
    intent by the verified person, through the intent editor's write path, as ``Source:
    ai-draft`` with the call's ``AI-Call:`` (`intent_words.commit_draft`): refused when the
    intent moved since the draft or the patch is not the one drafted. With ``plan``, the deploy
    preview opens next (the existing path: preview, confirm by hash, apply, verify, rollback),
    never confirmed for the person. Nothing reaches the device here."""
    from modules import identity
    from modules.ai import intent_words

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    host = dev.get("hostname", "")
    actor = identity.request_actor()
    call_id = request.form.get("call_id", "")
    if request.form.get("pair") == "1":
        # C1908: both ends of a link, one commit; no plan follows (the paired deploy, C1909,
        # is not built: each device is deployed from its page). The pair's patches travel in
        # `patch`, the field the confirm is bound to (operation_stages), as one device's does.
        got = intent_words.commit_pair(ref.name, call_id, request.form.get("patch", ""),
                                       request.form.get("summary", ""), actor)
        w = {"committed": {k: got.get(k) for k in ("ok", "commit", "changed", "error", "stage",
                                                    "message", "hostnames", "deploy")
                           if k in got},
             "call_id": call_id, "actor": actor, "sentence": request.form.get("words", "")}
        return _strict(render_template("v2/_intent_words.html", host=host, w=w),
                       200 if got.get("ok") else got.get("status", 400))
    got = intent_words.commit_draft(ref.name, host, call_id, request.form.get("patch", ""),
                                    request.form.get("base", ""), request.form.get("summary", ""),
                                    actor)
    if got.get("ok") and got.get("commit") and request.form.get("plan") == "1":
        from flask import make_response, redirect, url_for
        plan = url_for("device_v2.device", name=host, tab="intent", op="deploy", list=ref.name)
        if request.headers.get("HX-Request"):
            resp = make_response("", 204)
            resp.headers["HX-Redirect"] = plan
            return resp
        return redirect(plan)
    # The row again, saying what happened: the commit (and Plan deploy… next), or why not.
    w = {"committed": {k: got.get(k) for k in ("ok", "commit", "changed", "error", "stage",
                                                "message") if k in got},
         "call_id": call_id, "actor": actor, "sentence": request.form.get("words", "")}
    return _strict(render_template("v2/_intent_words.html", host=host, w=w),
                   200 if got.get("ok") else got.get("status", 400))


@bp.route("/<name>/intent/check", methods=["POST"])
def check(name):
    """The edit, checked as typed: `intent_edit.preview`. Writes nothing."""
    from modules.nsot import intent_edit

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    text = request.form.get("yaml", "")
    p = intent_edit.preview(ref.name, dev.get("hostname", ""), text)
    # The editor's Commit, drawn again beside the answer (out of band): for a formatting-only
    # edit it names it and waits on the proof (C1693, board H-N).
    return _strict(render_template("v2/_intent_check.html", p=p, host=dev.get("hostname", ""),
                                   text=text, list_name=ref.name,
                                   commit_oob=may_commit().get("may")))


@bp.route("/<name>/intent/acknowledge", methods=["POST"])
def acknowledge(name):
    """The editor again, its document's ``unmodeled_ack`` set to the lines ticked (C481).
    Writes nothing: the acknowledgement is committed with the edit, in git, with its reason."""
    from modules.nsot import intent_edit

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    text = intent_edit.acknowledge(request.form.get("yaml", ""), request.form.getlist("ack"))
    return _card(editor_ctx(ref, dev, text=text, base=request.form.get("base", ""),
                            summary=request.form.get("summary", "")))


@bp.route("/<name>/intent/commit", methods=["POST"])
def commit(name):
    """Commit the edit as the verified person, bound to the version opened: the result in
    place, or the refusal when intent moved (both changes; the edit placed on theirs when
    they touch different lines), or the editor again with its error."""
    from modules import identity
    from modules.nsot import intent_edit

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    host = dev.get("hostname", "")
    text, base = request.form.get("yaml", ""), request.form.get("base", "")
    summary = request.form.get("summary", "")
    got = intent_edit.commit(ref.name, host, text, summary, base, identity.request_actor())
    if got.get("stage") == "moved":
        return _card({"state": "moved", "host": host, "list": ref.name, "m": got,
                      "text": text, "summary": summary}, 409)
    if not got.get("ok"):
        # What the refusal draws, and only that (every carried field is drawn): its words, the
        # line and column it names, and a formatting-only commit's proof (C1693).
        refused = {k: got[k] for k in ("error", "line", "column", "proof") if k in got}
        return _card(editor_ctx(ref, dev, text=text, base=base, summary=summary,
                                refused=refused), got.get("status", 400))
    p = intent_edit.preview(ref.name, host, text)
    return _card({"state": "done", "host": host, "list": ref.name, "r": got, "p": p,
                  "summary": summary, "actor": identity.request_actor()})


@bp.route("/<name>/intent/reopen", methods=["POST"])
def reopen(name):
    """After intent moved: the editor opened at what is committed now, the person's edit
    placed on it (only when the two touched different lines). Nothing is committed for them."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _card(editor_ctx(ref, dev, text=request.form.get("yaml", ""),
                            base=request.form.get("base", ""),
                            summary=request.form.get("summary", "")))
