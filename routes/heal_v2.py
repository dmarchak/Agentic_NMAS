"""routes/heal_v2.py — heal to intent's Self-healing tab and its policy routes (board H, parts
H1 and H9; docs/HEAL_TO_INTENT.md sections 6, 7, 9, 10 and 16).

Each network's heal policy, previewed and confirmed by hash as a verified person with a reason;
its one-click Turn off; who is told about its healing; and the installation's kill switch (stop
at once, resume previewed and confirmed by hash). Every policy write is `modules/heal/policy.py`'s
and Who is told's `modules/heal_notify.py`'s; nothing here contacts a device.

The Self-healing tab (board H, artboard A: `templates/v2/_heal.html`, its model
`modules/heal_page.py`) posts each route with htmx and is answered with its fragment: the tab
again with the result in place, or with the change's modal opened again (C3158), holding the
refusal and what was sent.
A request that is not htmx's is answered ``{"ok", "error", ...}`` as H1 built them.
"""

import json
import logging

from flask import Blueprint, jsonify, render_template, request

log = logging.getLogger(__name__)

bp = Blueprint("heal_v2", __name__, url_prefix="/v2/settings")


def _prefix_rows(table: dict) -> dict:
    return {k: v for k, v in table.items() if k.startswith(bp.name + ".")}


def gates() -> dict:
    """These routes' rows of `modules/route_gates.py`'s GATES, where they are declared (H9
    moved them there with the tab that posts them)."""
    from modules.route_gates import GATES

    return _prefix_rows(GATES)


def invalidates() -> dict:
    """These routes' rows of `modules/invalidation.py`'s DECLARED."""
    from modules.invalidation import DECLARED

    return _prefix_rows(DECLARED)


def history() -> dict:
    """These routes' rows of `modules/operation_stages.py`'s HISTORY."""
    from modules.operation_stages import HISTORY

    return _prefix_rows(HISTORY)


def _htmx() -> bool:
    return bool(request.headers.get("HX-Request"))


def _answer(body: dict, code: int = 200):
    return jsonify(dict({"ok": code == 200, "error": ""}, **body)), code


def _code(exc) -> int:
    from modules.heal import policy as H

    return 403 if isinstance(exc, H.NotAPerson) else 409


def _refused(exc) -> tuple:
    return _answer({"ok": False, "error": str(exc)}, _code(exc))


def _who() -> dict:
    """The verified actor, how it was established, and whether it is a person."""
    from modules import identity

    actor = identity.request_actor()
    ident = identity.verified_identity()
    return {"actor": actor, "actor_verified": identity.actor_verification(actor),
            "person": bool(ident is not None and ident.kind == "person")}


def _fragment(template: str, code: int = 200, **ctx):
    from routes.device_v2 import _strict

    return _strict(render_template(template, **ctx), code)


def _tab(list_name: str, code: int = 200, change: dict = None, **ctx):
    """The Self-healing tab, drawn again with an answer in place (`ctx`): every change it
    offers drawn as its own modal, and *change*'s (a refused confirm's) opened again holding
    what was sent."""
    from modules import heal_page
    from routes.v2 import viewer_zone

    for kind in heal_page.ANSWER_KEYS:
        if ctx.get(kind):
            ctx[kind] = heal_page.answer(kind, ctx[kind])
    h = heal_page.view(list_name)
    h["modals"] = heal_page.modals(h, list_name, change, zone=viewer_zone())
    return _fragment("v2/_heal.html", code, h=h, list_name=list_name, **ctx)


def _until(form, out: dict, now: float = None) -> str:
    """AUTO's expiry as the form sent it, into *out* (C3158): the date-time picker's time, in
    the viewer's own zone (`routes.v2.viewer_zone`, the zone every time on the screen is drawn
    in), else a quick choice (hours from now), each converted once here to the UTC instant
    the policy keeps; the tab's picker sent empty with no quick choice is no expiry, which the
    policy refuses naming it. A request that is not the tab's (H1's callers) sends
    ``heal_mode_until`` as people write a UTC time, or as the policy keeps it. Returns how it
    was given: ``picker``, ``quick``, ``typed`` or ""."""
    from modules import heal_page
    from modules.heal import policy as H
    from routes.v2 import viewer_zone

    local = (form.get(heal_page.UNTIL_LOCAL_FIELD) or "").strip()
    quick = (form.get(heal_page.UNTIL_FOR_FIELD) or "").strip()
    if local:
        out[H.UNTIL_KEY] = heal_page.parse_until_local(local, viewer_zone())
        return "picker"
    if quick:
        out[H.UNTIL_KEY] = heal_page.until_in(quick, now)
        return "quick"
    if heal_page.UNTIL_LOCAL_FIELD in form:
        out[H.UNTIL_KEY] = ""
        return ""
    if out.get(H.UNTIL_KEY):
        out[H.UNTIL_KEY] = heal_page.parse_until(out[H.UNTIL_KEY])
        return "typed"
    return ""


def _proposed(form, given: dict = None) -> dict:
    """The policy values the form sent, each as its schema's type. A list is sent as one
    field per item beside an empty one (so none ticked is an empty list), or as JSON. AUTO's
    expiry as `_until` reads it; *given*, when passed, is told how (``{"until": ...}``)."""
    from modules.heal import policy as H
    from routes.settings_v2 import _typed

    lists = (H.KINDS_AUTO_KEY, H.KINDS_PROPOSE_KEY)
    sent = {k: form.get(k) for k in H.POLICY_KEYS if k in form and k not in lists}
    out = _typed(sent)
    for k in lists:
        if k not in form:
            continue
        items = form.getlist(k)
        if len(items) == 1 and items[0].strip().startswith("["):
            out.update(_typed({k: items[0]}))
        else:
            out[k] = [i for i in items if i]
    how = _until(form, out)
    if given is not None:
        given.update(until=how, at=out.get(H.UNTIL_KEY, ""))
    return out


def _part(form) -> str:
    return (form.get("part") or "mode").strip()


def _drawn_until(form, given: dict) -> dict:
    """What the preview draws again beside "Auto until"'s picker (`_heal_change.html`
    `until_utc`, `until_picker`): only for the tab's Auto modal (its picker was sent), the
    instant it previewed (*at*, "" when none), and *quick* when a quick choice gave it, with
    the picker's *value* for it in the viewer's zone, so the picker is drawn holding that time
    and the confirm sends exactly it."""
    from modules import heal_page
    from modules.heal import policy as H
    from routes.v2 import viewer_zone

    if heal_page.UNTIL_LOCAL_FIELD not in form:
        return {}
    at = given.get("at", "") if given.get("until") else ""
    try:
        H.parse_until(at)
    except H.PolicyRefused:                              # not an instant: none drawn
        at = ""
    quick = bool(at) and given.get("until") == "quick"
    return {"at": at, "quick": quick,
            "value": heal_page.local_value(at, viewer_zone()) if quick else ""}


# ── The tab's reads ─────────────────────────────────────────────────────────────────────────

@bp.route("/network/<list_name>/heal/tab", methods=["GET"])
def tab(list_name):
    """The Self-healing tab at rest (Cancel, and Close after an answer)."""
    return _tab(list_name)


# Change mode (the dropdown), a kind's toggle, Change fix kinds… and a hard stop's Edit… each
# open their modal over the tab (`_heal_change.html`, drawn with the tab by `heal_page.modals`):
# no route draws a change card (C3158; the operator's rule of 2026-11-12).

# ── A change: preview, then confirm ─────────────────────────────────────────────────────────

@bp.route("/network/<list_name>/heal/preview", methods=["POST"])
def policy_preview(list_name):
    """What the change to the network's heal policy does, in the six parts; writes nothing.
    Its fragment also draws, beside "Auto until"'s picker, the UTC of the time it previewed,
    and the picker holding a quick choice's time (`until`)."""
    from modules import heal_page, preview_confirm
    from modules.heal import policy as H

    given = {}
    try:
        p = H.plan(list_name, _proposed(request.form, given))
    except H.PolicyRefused as exc:
        if _htmx():
            return _fragment("v2/_heal_preview.html", 409, list_name=list_name,
                             refused=str(exc), until=_drawn_until(request.form, given))
        return _refused(exc)
    pv = preview_confirm.heal_policy_preview(p, preview_confirm.confirm_part(request,
                                                                            "configure"))
    if _htmx():
        return _fragment("v2/_heal_preview.html", list_name=list_name,
                         p=heal_page.preview(list_name, p, _part(request.form)),
                         pv=heal_page.six_parts(pv), until=_drawn_until(request.form, given))
    return _answer({"network": list_name, "fingerprint": p["fingerprint"],
                    "confirmable": p["confirmable"], "operands": p["operands"],
                    "preview": pv})


@bp.route("/network/<list_name>/heal", methods=["POST"])
def policy_confirm(list_name):
    """The change as previewed: a verified person, a reason, the preview's fingerprint;
    re-planned and compared, written, recorded."""
    from modules import heal_page
    from modules.heal import policy as H
    from routes.v2 import viewer_zone

    form = request.form
    try:
        seen = json.loads(form.get("seen") or "null")
    except ValueError:
        seen = None
    try:
        out = H.apply(list_name, _proposed(form), form.get("fingerprint") or "",
                      reason=form.get("reason") or "", seen=seen, **_who())
    except H.PolicyRefused as exc:
        if _htmx():
            try:
                ch = heal_page.change(list_name, _part(form), form, zone=viewer_zone())
            except H.PolicyRefused:
                ch = None
            return _tab(list_name, _code(exc), change=ch, refused=str(exc))
        return _refused(exc)
    if _htmx():
        return _tab(list_name, saved=out)
    return _answer(out)


@bp.route("/network/<list_name>/heal/off", methods=["POST"])
def turn_off(list_name):
    """Turn off: one press, no confirm, effective at once, recorded with who and when."""
    from modules.heal import policy as H

    who = _who()
    try:
        out = H.turn_off(list_name, actor=who["actor"], actor_verified=who["actor_verified"])
    except H.PolicyRefused as exc:
        if _htmx():
            return _tab(list_name, _code(exc), refused=str(exc))
        return _refused(exc)
    if _htmx():
        return _tab(list_name, off=out)
    return _answer(out)


# ── Who is told ─────────────────────────────────────────────────────────────────────────────

@bp.route("/network/<list_name>/heal/notify", methods=["POST"])
def notify_save(list_name):
    """Who is told: the network's team and the events that tell it, compared with what the
    card drew, written and recorded."""
    from modules import heal_notify

    who = _who()
    form = request.form
    try:
        loaded = json.loads(form.get("loaded") or "null")
    except ValueError:
        loaded = None
    try:
        out = heal_notify.save(list_name, form.get("team") or "", form.getlist("events"),
                               actor=who["actor"], actor_verified=who["actor_verified"],
                               loaded=loaded)
    except heal_notify.Refused as exc:
        return _tab(list_name, 409, told_refused=str(exc))
    return _tab(list_name, told_saved=out)


# ── The installation's kill switch ──────────────────────────────────────────────────────────

def _network() -> str:
    """The network whose tab asked (its address's ``list_name``, which `list_param` checks):
    the tab drawn again is that one's."""
    from modules.list_settings import DEFAULT_LIST

    return (request.args.get("list_name") or DEFAULT_LIST).strip()


@bp.route("/installation/heal/stop/ask", methods=["GET"])
def stop_ask():
    """Stop self-healing everywhere…: the tab with the stop's card open, asking why (never
    required: a stop must not wait on typing)."""
    return _tab(_network(), stopping=True)


@bp.route("/installation/heal/stop", methods=["POST"])
def stop_everywhere():
    """Stop self-healing everywhere: one press, no confirm, recorded with who, when and why."""
    from modules.heal import policy as H

    who = _who()
    try:
        out = H.stop(actor=who["actor"], actor_verified=who["actor_verified"],
                     why=request.form.get("why") or "")
    except H.PolicyRefused as exc:
        if _htmx():
            return _tab(_network(), _code(exc), stopping=True, refused=str(exc))
        return _refused(exc)
    if _htmx():
        return _tab(_network(), stopped_now=out)
    return _answer(out)


@bp.route("/installation/heal/resume/preview", methods=["POST"])
def resume_preview():
    """What resuming does, network by network, and the fingerprint its confirm sends; writes
    nothing."""
    from modules import preview_confirm
    from modules.heal import policy as H

    try:
        p = H.resume_plan()
    except H.PolicyRefused as exc:
        if _htmx():
            return _tab(_network(), _code(exc), refused=str(exc))
        return _refused(exc)
    confirm = preview_confirm.confirm_part(request, "configure")
    if _htmx():
        from modules import heal_page
        return _tab(_network(), resuming=heal_page.resuming(p, confirm))
    return _answer({"networks": p["networks"], "fingerprint": p["fingerprint"],
                    "stopped": p["stopped"], "why": p["why"], "confirm": confirm})


@bp.route("/installation/heal/resume", methods=["POST"])
def resume():
    """Resume self-healing as previewed: a verified person, a reason, the fingerprint."""
    from modules import preview_confirm
    from modules.heal import policy as H

    try:
        out = H.resume(request.form.get("fingerprint") or "",
                       reason=request.form.get("reason") or "", **_who())
    except H.PolicyRefused as exc:
        if _htmx():
            try:
                p = H.resume_plan()
            except H.PolicyRefused:
                return _tab(_network(), _code(exc), refused=str(exc))
            from modules import heal_page
            return _tab(_network(), _code(exc), refused=str(exc),
                        resuming=heal_page.resuming(
                            p, preview_confirm.confirm_part(request, "configure"),
                            request.form.get("reason") or ""))
        return _refused(exc)
    if _htmx():
        return _tab(_network(), resumed=out)
    return _answer(out)
