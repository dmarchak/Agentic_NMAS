"""routes/heal_proposal_v2.py — a self-healing proposal's preview, approve and decline (board H,
parts H5 and H9; docs/HEAL_TO_INTENT.md sections 9 (artboard E) and 11; `modules/heal/propose.py`).

A Tier 2 fix waits for a person: the proposal is read (its program, the process reset it needs,
what that affects and why rollback cannot undo it, whether it is measured, and the hash an
approval confirms); approved by that hash as a verified person with a reason, which starts its
act as a job as that person; or declined as a verified person with a reason, which sends
nothing. Every write is `modules/heal/propose.py`'s.

**Where it is drawn** (board H, artboard E; H9): the Needs attention row ``heal``/``proposal``
(`attention.heal_source`) opens to this proposal's card (`templates/v2/_heal_proposal.html`),
read by `proposal` when the row is opened; its **Approve and run on <device>** and **Decline**
post `approve` and `decline` with htmx, and each is answered with the card again, its answer
in place (approved and its job, declined, or the refusal with the reason typed kept). A request
that is not htmx's is answered ``{"ok", "error", ...}`` as H5 built them. A proposal the heal's
own pass withdrew (C2470: its device read back at intent, or changed) is drawn as withdrawn,
naming why, and its approval is refused naming the hash confirmed and both states.

**Lift the halt** (artboard E's second row, C2471): the Needs attention row ``heal``/``halted``
(`attention._heal_halted_rows`) carries its card (`templates/v2/_heal_halt.html`): a reason,
kept outside any form so Enter submits nothing (C2472) and sent by the button's
``hx-include``, and **Lift the halt**, which posts `lift` (`decisions.lift`: a verified person,
a reason of three words or more, the halt in force by its id), answered with the card again,
lifted or refused naming both operands.

**Download the change record (.md)** (artboards C and K, C2773): History's heal row links
`change_record_md`, a read of the incident's change record as the step log keeps it.

The routes' declarations live in their tables (`route_gates.GATES`, `invalidation.DECLARED`,
`operation_stages.STAGES` and `HISTORY`), placed there by H9 with the card; `gates()`,
`invalidates()`, `stages()` and `history()` are views of those tables.
"""

import logging
import re

from flask import Blueprint, jsonify, render_template, request

log = logging.getLogger(__name__)

bp = Blueprint("heal_proposal_v2", __name__, url_prefix="/v2")


def _prefix_rows(table: dict) -> dict:
    return {k: v for k, v in table.items() if k.startswith(bp.name + ".")}


def gates() -> dict:
    """These routes' rows of `modules/route_gates.py`'s GATES. Approve and decline refuse
    anyone but a verified person too, whatever a service is granted."""
    from modules.route_gates import GATES

    return _prefix_rows(GATES)


def invalidates() -> dict:
    """These routes' rows of `modules/invalidation.py`'s DECLARED."""
    from modules.invalidation import DECLARED

    return _prefix_rows(DECLARED)


def stages() -> dict:
    """The approve route's five stages, its row of `modules/operation_stages.py`'s STAGES."""
    from modules.operation_stages import STAGES

    return _prefix_rows(STAGES)


def history() -> dict:
    """Where each route's record is read later, its rows of `operation_stages.HISTORY`."""
    from modules.operation_stages import HISTORY

    return _prefix_rows(HISTORY)


def _htmx() -> bool:
    return bool(request.headers.get("HX-Request"))


def _answer(body: dict, code: int = 200):
    return jsonify(dict({"ok": code == 200, "error": ""}, **body)), code


def _code(exc) -> int:
    from modules.heal import propose

    return 403 if isinstance(exc, propose.NotAPerson) else 409


def _refused(exc) -> tuple:
    return _answer({"ok": False, "error": str(exc)}, _code(exc))


def _who() -> dict:
    """The verified actor, how it was established, and whether it is a person."""
    from modules import identity

    actor = identity.request_actor()
    ident = identity.verified_identity()
    return {"actor": actor, "actor_verified": identity.actor_verification(actor),
            "person": bool(ident is not None and ident.kind == "person")}


def _card(list_name: str, decision_id: str, code: int = 200, **ctx):
    """The proposal's card, read again, with an answer in place (`ctx`). A proposal no longer
    held (declined, approved or never there) is drawn as that, never as an empty card."""
    from modules import preview_confirm
    from modules.heal import propose
    from routes.device_v2 import _strict

    try:
        v = propose.view(list_name, decision_id)
        gone = ""
    except propose.Refused as exc:
        v, gone = None, str(exc)
    html = render_template("v2/_heal_proposal.html", v=v, gone=gone, list_name=list_name,
                           decision_id=decision_id,
                           confirming=preview_confirm.confirm_part(request,
                                                                   "confirm")["statement"],
                           **ctx)
    return _strict(html, code if v is not None or ctx else 404)


@bp.route("/network/<list_name>/heal/proposal/<decision_id>", methods=["GET"])
def proposal(list_name, decision_id):
    """The proposal as a person reads it before deciding; reads only Mercury's records."""
    from modules.heal import propose

    if _htmx():
        return _card(list_name, decision_id)
    try:
        v = propose.view(list_name, decision_id)
    except propose.Refused as exc:
        return _answer({"ok": False, "error": str(exc)}, 404)
    return _answer({"proposal": v})


@bp.route("/network/<list_name>/heal/proposal/<decision_id>/approve", methods=["POST"])
def approve(list_name, decision_id):
    """Approve the proposal as previewed: a verified person, a reason, the proposal's hash;
    its act started as a job, as that person."""
    from modules import identity
    from modules.heal import propose

    form = request.form
    try:
        out = propose.approve(list_name, decision_id, confirmed_hash=form.get("hash") or "",
                              reason=form.get("reason") or "",
                              ident=identity.verified_identity(), **_who())
    except propose.Refused as exc:
        if _htmx():
            return _card(list_name, decision_id, _code(exc), refused=str(exc),
                         reason=form.get("reason") or "")
        return _refused(exc)
    if _htmx():
        return _card(list_name, decision_id, approved=out)
    return _answer(out)


def _halt_card(list_name: str, halt_id: str, code: int = 200, **ctx):
    """A halt's Lift the halt card (board H artboard E's second row, C2471), drawn again with
    its answer in place: lifted, or the refusal with the reason typed kept. Drawn by the
    person's own request, so it holds a live redraw until Show it now (`data-holds-live`)."""
    from modules.heal import decisions
    from routes.device_v2 import _strict

    try:
        h = decisions.halt_row(list_name, halt_id)
    except Exception as exc:
        h = {}
        ctx.setdefault("refused", f"{list_name}'s heal decisions cannot be read ({exc})")
    html = render_template("v2/_heal_halt.html", list_name=list_name, halt_id=halt_id,
                           device=((h.get("operands") or {}).get("device") or ""), halt=h,
                           answered=True, **ctx)
    return _strict(html, code)


@bp.route("/network/<list_name>/heal/halt/<halt_id>/lift", methods=["POST"])
def lift(list_name, halt_id):
    """Lift the halt in force on a network (board H artboard E, C2471): a verified person and
    a reason of three words or more, recorded in the network's heal decisions
    (`decisions.lift`); self-healing on it then runs under its policy again. Sends nothing."""
    from modules.heal import decisions

    reason = request.form.get("reason") or ""
    w = _who()
    try:
        row = decisions.lift(list_name, halt_id, by=w["actor"],
                             actor_verified=w["actor_verified"], person=w["person"],
                             reason=reason)
    except (decisions.Refused, RuntimeError) as exc:
        code = 403 if isinstance(exc, decisions.NotAPerson) else 409
        if _htmx():
            return _halt_card(list_name, halt_id, code, refused=str(exc), reason=reason)
        return _answer({"ok": False, "error": str(exc)}, code)
    if _htmx():
        return _halt_card(list_name, halt_id, lifted=row)
    return _answer({"lifted": row})


def _mark_card(list_name: str, decision_id: str, code: int = 200, **ctx):
    """A dry-run record's Right / Wrong (board H artboard C, C2399), drawn again with its
    answer in place: the mark recorded, or the refusal with the reason typed kept."""
    from routes.device_v2 import _strict

    html = render_template("v2/_heal_mark.html", list_name=list_name, decision_id=decision_id,
                           answered=True, **ctx)
    return _strict(html, code)


@bp.route("/network/<list_name>/heal/decision/<decision_id>/mark", methods=["POST"])
def mark(list_name, decision_id):
    """Mark a dry-run record right or wrong (board H artboard C, "Was this the right fix?";
    docs/HEAL_TO_INTENT.md section 7, C2399): a verified person; Wrong with why it was wrong.
    Recorded in the network's heal decisions (`decisions.mark`), counted per fix kind as the
    false-positive rate the enablement path reads; the record's Needs attention item leaves.
    Sends nothing."""
    from modules.heal import decisions

    right = (request.form.get("right") or "").strip().lower()
    why = request.form.get("why") or ""
    w = _who()
    try:
        if right not in ("yes", "no"):
            raise decisions.Refused(f"a mark is right=yes or right=no, and {right or 'nothing'!r}"
                                    " was sent")
        d = decisions.mark(list_name, decision_id, right == "yes", by=w["actor"],
                           actor_verified=w["actor_verified"], person=w["person"], why=why)
    except (decisions.Refused, RuntimeError) as exc:
        code = 403 if isinstance(exc, decisions.NotAPerson) else 409
        if _htmx():
            return _mark_card(list_name, decision_id, code, refused=str(exc), why=why)
        return _answer({"ok": False, "error": str(exc)}, code)
    if _htmx():
        return _mark_card(list_name, decision_id, mark=d.get("mark") or {}, marked=True)
    return _answer({"mark": d.get("mark") or {}})


@bp.route("/network/<list_name>/heal/proposal/<decision_id>/decline", methods=["POST"])
def decline(list_name, decision_id):
    """Decline the proposal: a verified person and a reason; nothing is sent."""
    from modules.heal import propose

    form = request.form
    try:
        out = propose.decline(list_name, decision_id, reason=form.get("reason") or "",
                              **_who())
    except propose.Refused as exc:
        if _htmx():
            return _card(list_name, decision_id, _code(exc), refused=str(exc),
                         reason=form.get("reason") or "")
        return _refused(exc)
    if _htmx():
        return _card(list_name, decision_id, declined=out)
    return _answer(out)


@bp.route("/network/<list_name>/heal/incident/<incident_id>/change-record.md", methods=["GET"])
def change_record_md(list_name, incident_id):
    """A heal's change record as text (C2773; board H, artboards C and K, "Download the change
    record (.md)"): the markdown `modules/heal/change_record.py` made and the step log keeps in
    the incident's ``act`` row (``records.change_record``), masked as stored and again on the
    way out, for a heal to intent and for an action (H23) alike. History's heal row draws the
    link when the record was made (`history_sources.heal`, ``heal_record``). A read of the
    step log: it writes nothing, creates no network and calls no model. An unknown network or
    incident, or an incident with no record (a dry run, a refusal before its program), is a
    404 naming which and why; a step log that cannot be read is a 503 saying so."""
    from flask import Response

    from modules.heal import steplog
    from modules.nsot import listref
    from modules.redact import redact_text
    from routes.v2 import _HEAL_INCIDENT

    def said(words, code):
        return Response(f"Not available: {words}.\n", status=code, mimetype="text/plain")

    net, iid = list_name[:80], incident_id[:40]
    if not listref.exists(net):
        return said(f"{net!r} is no network Mercury holds", 404)
    if not _HEAL_INCIDENT.match(iid):
        return said(f"{iid!r} is no self-healing incident id (hi- and 12 hex digits)", 404)
    try:
        e = steplog.incident(net, iid)
    except RuntimeError as exc:
        return said(str(exc), 503)
    if not e:
        return said(f"{net}'s self-healing step log holds no incident {iid}", 404)
    cr = (e.get("records") or {}).get("change_record") or {}
    if cr.get("state") != "made" or not cr.get("markdown"):
        why = redact_text(cr.get("words") or (
            "a dry run sends nothing, so it has no change record" if e.get("mode") == "dry_run"
            else "its step log records no change record for it"))
        return said(f"incident {iid} on {net} has no change record: {why}", 404)
    host = re.sub(r"[^A-Za-z0-9._-]", "_", e.get("device") or "device")
    resp = Response(redact_text(cr["markdown"]), mimetype="text/markdown")
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="change-record-{host}-{iid}.md"')
    return resp
