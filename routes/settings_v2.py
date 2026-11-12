"""routes/settings_v2.py — Settings per network on v2 (P.8 step 7; boards A to J, approved
2026-10-05).

A network's page is ``/v2/settings/network/<list_name>`` (the path converter `list_param`
validates, so a page about a list nobody has is refused before anything resolves a path).
Its reads come from `modules/settings_page.py`; its switches from `modules/list_settings.py`,
each previewed in place of the card it changes, confirmed against the preview's fingerprint
by the verified person (`route_gates`: configure), and recorded. Nothing here contacts a
device.
"""

import json
import logging

from flask import Blueprint, render_template, request
from modules.outbound import no_store

from routes.device_v2 import _strict, _who

log = logging.getLogger(__name__)

bp = Blueprint("settings_v2", __name__, url_prefix="/v2/settings")


def _page(template: str, **ctx):
    return _strict(render_template(template, who=_who(), active_nav="settings", **ctx))


def _fragment(template: str, code: int = 200, **ctx):
    return _strict(render_template(template, **ctx), code)


@bp.route("", methods=["GET"])
def index():
    """Settings opens on the network the viewer is on: that network's page, its own address
    in every link it draws."""
    from modules.nsot import listref

    return network(listref.active().name)


@bp.route("/installation", methods=["GET"])
def installation():
    """Board F: Settings › Installation, the installation's own settings for every network. Its
    Connections tab holds the Records database card (F2), the Record stores card and the NetBox
    connection, Proxmox, Commit author and Server (F3) cards; its other tabs are Access and
    identity, Platforms and roles, and Diagnostics (`installation_settings`' tabs)."""
    from modules import installation_settings as I
    from modules import settings_page
    from modules.nsot import listref

    tab = request.args.get("tab") or "connections"
    if tab not in dict(I.TABS):
        tab = "connections"
    v = {"scope": dict(settings_page.scope_bar(listref.active().name), is_installation=True),
         "mode_words": ""}
    # A card with its own template (the relay's) is drawn by its tab's own template.
    cards = [I.card(name) for name, spec in I.CARDS.items()
             if spec["tab"] == tab and not spec.get("template")]
    diag = {}
    if tab == "platforms":
        from modules import platform_maps as P
        diag = {"pm": P.view()}
    if tab == "access":
        from modules import identity
        diag = {"acc": I.access_view(identity.identify(request))}
    if tab == "diagnostics":
        from modules import installation_diagnostics as D
        diag = {"red": D.redaction(), "dr": D.drift(), "fl": D.in_flight(),
                "lg": D.app_log(None)}
    if tab == "connections":
        from modules import records_migrate as RM
        diag = {"st": RM.view()}
    if tab == "console":
        from routes.console_servers_v2 import view as console_servers
        diag = {"cs": console_servers()}
    if tab == "notifications":
        # Board H, artboard B (H9): the relay (its card in `cards`), the webhooks and the teams.
        from modules import notify_page
        diag = {"n": notify_page.view()}
    if tab == "ai":
        from modules.ai import feedback, settings_view
        # The AI (hosted) card is in `cards` (moved here whole from Connections, C1953).
        diag = {"ai": settings_view.view(request.args.get("network") or ""),
                # Answers said wrong (PHASE8_PLAN 16.11 item 1, board FB): to review first.
                "fbr": feedback.view()}
    return _page("v2/settings_installation.html", tab=tab, tabs=I.TABS, built=I.BUILT_TABS,
                 v=v, r=I.records_card() if tab == "connections" else None, cards=cards,
                 **diag)


def _records(status: int = 200, **ctx):
    from modules import installation_settings as I

    return _fragment("v2/_records_db_card.html", status, r=I.records_card(), **ctx)


@bp.route("/installation/records", methods=["GET"])
def records_card():
    """F2's card, drawn again (Cancel, and a page's refresh after a change)."""
    return _records()


@bp.route("/installation/records/save", methods=["POST"])
def records_save():
    """F2: save the card's fields as sent, recorded with the verified person and the fields'
    names. Never opens the database, so it works with the database down or the password
    wrong (the operator's condition 1)."""
    from modules import identity
    from modules import installation_settings as I

    from modules.settings_schema import loaded_from

    form = {k: request.form.get(k) for k in I.FIELDS}
    try:
        saved = I.save(form, identity.request_actor(), _verified(),
                       loaded=loaded_from(request.form.get("loaded")))
    except I.Refused as exc:
        return _records(409, refused=str(exc))
    return _records(saved=saved)


@bp.route("/installation/records/test", methods=["POST"])
def records_test():
    """F2: the Test, its six checks named (condition 2); the answer kept and drawn."""
    from modules import identity
    from modules import installation_settings as I

    return _records(tested=I.test(identity.request_actor(), _verified()))


@bp.route("/installation/records/replace", methods=["GET"])
def records_replace_form():
    """F2 state 4: Replace… opens in place of the card, the rotation order first."""
    from modules import installation_settings as I

    return _fragment("v2/_records_db_replace.html", r=I.records_card())


@bp.route("/installation/records/replace", methods=["POST"])
def records_replace():
    """F2 state 4: store the new password as a secret, record it, then Test (condition 3: the
    server was changed first, by postgres-rotate.sh). The value is never drawn back."""
    from modules import identity
    from modules import installation_settings as I

    try:
        out = I.replace_password(request.form.get("records_db_password") or "",
                                 identity.request_actor(), _verified())
    except I.Refused as exc:
        return _fragment("v2/_records_db_replace.html", 409, r=I.records_card(),
                         refused=str(exc))
    return _records(replaced=out, tested=out["tested"])


# ── Networks: create and delete (board I's pattern; networks live in Settings) ─────────────

def _net_card(template: str, code: int = 200, **ctx):
    return _fragment(template, code, **ctx)


@bp.route("/networks/new", methods=["GET"])
def network_new():
    """New network…: the name's form, in place of the tab's body."""
    return _net_card("v2/_network_create.html")


@bp.route("/networks/new/preview", methods=["POST"])
def network_create_preview():
    """What Create would make: the folder its name derives, or why it cannot; writes nothing."""
    from modules import network_admin as NA

    return _net_card("v2/_network_create.html", pv=NA.create_preview(request.form.get("name", "")))


@bp.route("/networks/new", methods=["POST"])
def network_create():
    """Create the network as previewed, recorded as the verified person."""
    from modules import identity
    from modules import network_admin as NA

    try:
        done = NA.create(request.form.get("name", ""), request.form.get("fingerprint", ""),
                         identity.request_actor(), _verified())
    except NA.Refused as exc:
        return _net_card("v2/_network_create.html", 409, refused=str(exc),
                         pv=NA.create_preview(request.form.get("name", "")))
    return _net_card("v2/_network_create.html", done=done)


@bp.route("/scope", methods=["GET"])
def scope():
    """Board H's scope bar alone, read again when a network is created or deleted (`lists`,
    P7-05): *at* is the network the page is about, or empty on Installation. A network deleted
    since the page drew is said, and nothing of it is read."""
    from modules import list_settings as L
    from modules import settings_page
    from modules.nsot import listref

    at = (request.args.get("at") or "").strip()
    if not at:
        v = {"scope": dict(settings_page.scope_bar(listref.active_name()), is_installation=True),
             "mode_words": ""}
        return _fragment("v2/_settings_scope.html", v=v)
    words = ""
    if not listref.exists(at):
        words = "deleted: it has left every page"
    elif not L.is_default(at):
        try:
            words = L.MODE_WORDS[L.load(at)["mode"]]
        except L.ListSettingsUnreadable:
            words = ""
    return _fragment("v2/_settings_scope.html",
                     v={"scope": settings_page.scope_bar(at), "mode_words": words})


@bp.route("/network/<list_name>/delete", methods=["GET"])
def network_delete_card(list_name):
    """The network's Delete card at rest (Cancel)."""
    return _net_card("v2/_network_delete.html", name=list_name)


@bp.route("/network/<list_name>/delete/preview", methods=["POST"])
def network_delete_preview(list_name):
    """What deleting the network removes, and where its data goes; writes nothing."""
    from modules import network_admin as NA

    try:
        pv = NA.delete_preview(list_name)
    except NA.Refused as exc:
        return _net_card("v2/_network_delete.html", 404, name=list_name, refused=str(exc))
    return _net_card("v2/_network_delete.html", name=list_name, pv=pv)


@bp.route("/network/<list_name>/delete", methods=["POST"])
def network_delete(list_name):
    """Delete the network as previewed: its name typed, the preview's fingerprint."""
    from modules import identity
    from modules import network_admin as NA

    try:
        done = NA.delete(list_name, request.form.get("typed", ""),
                         request.form.get("fingerprint", ""), identity.request_actor(),
                         _verified())
    except NA.Refused as exc:
        return _net_card("v2/_network_delete.html", 409, name=list_name, refused=str(exc))
    return _net_card("v2/_network_delete.html", name=list_name, done=done)


# ── A network's inventory source ────────────────────────────────────────────────────────────

def _source(list_name: str, code: int = 200, **ctx):
    from modules import network_source as NS

    return _fragment("v2/_network_source.html", code, src=NS.view(list_name), **ctx)


@bp.route("/network/<list_name>/source", methods=["GET"])
def network_source(list_name):
    """The Inventory source card at rest (Cancel)."""
    return _source(list_name)


@bp.route("/network/<list_name>/source/preview", methods=["POST"])
def network_source_preview(list_name):
    """What changing the source does, NetBox read once with the new filters; writes nothing."""
    from modules import network_source as NS

    try:
        pv = NS.preview(list_name, request.form)
    except NS.Refused as exc:
        return _source(list_name, 409, refused=str(exc))
    return _source(list_name, pv=pv)


@bp.route("/network/<list_name>/source", methods=["POST"])
def network_source_apply(list_name):
    """The change as previewed: written, the inventory refreshed, recorded."""
    from modules import identity
    from modules import network_source as NS

    try:
        done = NS.apply(list_name, request.form, request.form.get("fingerprint", ""),
                        identity.request_actor(), _verified())
    except NS.Refused as exc:
        return _source(list_name, 409, refused=str(exc))
    return _source(list_name, done=done)


@bp.route("/network/<list_name>/source/refresh", methods=["POST"])
def network_source_refresh(list_name):
    """Refresh now: NetBox read for this network now, as the schedule does anyway."""
    from modules import network_source as NS

    try:
        got = NS.refresh(list_name)
    except NS.Refused as exc:
        return _source(list_name, 409, refused=str(exc))
    return _source(list_name, refreshed=got)


# ── Phase 4: the record stores, moved to the records database and back ────────────────────

DIRECTIONS = ("move", "back")


def _stores(status: int = 200, **ctx):
    from modules import records_migrate as RM

    return _fragment("v2/_records_stores.html", status, st=RM.view(), **ctx)


@bp.route("/installation/records/stores", methods=["GET"])
def records_stores():
    """Each record store: where it is, its last check; drawn again when the records-check
    reader announces, and by Cancel."""
    return _stores()


@bp.route("/installation/records/stores/<direction>/preview", methods=["POST"])
def records_store_preview(direction):
    """What moving a record store (the form's `store`, deploy receipts when it names none) to
    the records database, or back, would do, every network's counts read now; writes nothing."""
    from modules import records_migrate as RM

    if direction not in DIRECTIONS:
        return _stores(404, refused=f"no such operation {direction!r}: move or back")
    store = request.form.get("store") or RM.STORE
    try:
        planned = RM.plan(store=store)
    except RM.Refused as exc:
        return _stores(404, refused=str(exc))
    return _stores(pv=dict(planned, direction=direction,
                           steps=[(s, RM.STEP_WORDS[s]) for s in
                                  (RM.MOVE_STEPS if direction == "move" else RM.BACK_STEPS)]))


@bp.route("/installation/records/stores/<direction>", methods=["POST"])
def records_store_apply(direction):
    """The confirm, bound to the preview's fingerprint: the move (copy, switch, copy again,
    check, read-only) or the move back (export, switch, check), recorded as the person."""
    from modules import identity
    from modules import records_migrate as RM

    if direction not in DIRECTIONS:
        return _stores(404, refused=f"no such operation {direction!r}: move or back")
    run = RM.move if direction == "move" else RM.move_back
    store = request.form.get("store") or RM.STORE
    try:
        words = RM.store_of(store).words
        out = run(request.form.get("fingerprint", ""), identity.request_actor(), _verified(),
                  store=store)
    except RM.Refused as exc:
        return _stores(409, refused=str(exc))
    return _stores(done=dict(out, direction=direction, store=store, words=words))


def _install(name: str, status: int = 200, typed: dict = None, **ctx):
    """One F3 card drawn, with an action's answer in place; an unknown card is a 404 saying
    which cards there are. *typed*: a refused Save's form, its fields drawn as typed so the
    refusal can be corrected (never a secret: a card's fields are settings)."""
    from modules import installation_settings as I

    if name not in I.CARDS:
        return _fragment("v2/_settings_refused.html", 404, list_name="", group="",
                         why=f"{name!r} is not an Installation card: {', '.join(I.CARDS)}")
    if I.CARDS[name].get("template"):
        # The email relay's card (board H, artboard B) is drawn by its own template, from
        # notify_page's view of it.
        from modules import notify_page
        return _fragment(I.CARDS[name]["template"], status,
                         rl=notify_page.relay_view(typed=typed), **ctx)
    return _fragment("v2/_install_card.html", status, k=I.card(name, typed=typed), **ctx)


@bp.route("/installation/card/<name>", methods=["GET"])
def install_card(name):
    """Board F3: one card drawn again (Cancel, and a refresh after a change)."""
    return _install(name)


@bp.route("/installation/card/<name>/save", methods=["POST"])
def install_save(name):
    """Board F3: save the fields the person changed, recorded with the verified person and each
    field's old and new value; a switch the form did not send is off. The card sends what it
    drew (`loaded`, R17): a changed field another person moved since is refused, naming both.
    A large increase of the AI day cap, or No cap, is drawn as its confirmation first and
    nothing is written (409 when No cap's words were typed wrong)."""
    from modules import identity
    from modules import installation_settings as I
    from modules.settings_schema import loaded_from

    if name not in I.CARDS:
        return _install(name)
    form = {k: request.form.get(k) for k in I.form_keys(name)}
    try:
        saved = I.save_card(name, form, identity.request_actor(), _verified(),
                            loaded=loaded_from(request.form.get("loaded")))
    except I.Refused as exc:
        # Drawn again as typed, every field (none is a secret), so it can be corrected.
        return _install(name, 409, typed=form, refused=str(exc))
    if saved.get("confirm"):
        return _install(name, 409 if saved["confirm"]["refused"] else 200,
                        confirm=saved["confirm"])
    return _install(name, saved=saved)


@bp.route("/installation/card/<name>/test", methods=["POST"])
def install_test(name):
    """Board F3: the card's Test, its integration asked now with what is saved (the AI card's:
    one recorded call through the gateway, as the person who pressed it)."""
    from modules import identity
    from modules import installation_settings as I

    if name not in I.CARDS:
        return _install(name)
    try:
        tested = I.test_card(name, actor=identity.request_actor())
    except I.Refused as exc:
        return _install(name, 409, refused=str(exc))
    return _install(name, tested=tested)


@bp.route("/installation/card/<name>/replace", methods=["GET"])
def install_replace_form(name):
    """Board F3: Replace… opens in the card."""
    from modules import installation_settings as I

    if name not in I.CARDS:
        return _install(name)
    if not I.CARDS[name]["secret"]:
        return _install(name, 409, refused=f"{I.CARDS[name]['title']} holds no secret to replace")
    return _fragment("v2/_install_card_replace.html", k=I.card(name, ai_state=False))


@bp.route("/installation/card/<name>/replace", methods=["POST"])
def install_replace(name):
    """Board F3: store the new secret (with its id for Proxmox), record it, then Test. The
    value is never drawn back."""
    from modules import identity
    from modules import installation_settings as I

    if name not in I.CARDS:
        return _install(name)
    spec = I.CARDS[name]
    keys = [k for k in ((spec["secret"] or (None,))[0], (spec["with_id"] or (None,))[0]) if k]
    try:
        out = I.replace_secret(name, {k: request.form.get(k) for k in keys},
                               identity.request_actor(), _verified())
    except I.Refused as exc:
        return _fragment("v2/_install_card_replace.html", 409, k=I.card(name, ai_state=False),
                         refused=str(exc))
    return _install(name, replaced=out, tested=out["tested"])


@bp.route("/installation/ai/allow", methods=["POST"])
def install_ai_allow():
    """Allow hosted AI: a verified person's decision, with their reason, recorded (PHASE8_PLAN
    15.8). The gateway refuses every call until it is set."""
    from modules import identity
    from modules import installation_settings as I

    try:
        out = I.ai_allow(request.form.get("reason", ""), identity.request_actor(), _verified())
    except I.Refused as exc:
        return _install("ai", 409, refused=str(exc))
    return _install("ai", ai_allowed=out)


@bp.route("/installation/ai/off", methods=["POST"])
def install_ai_off():
    """Turn hosted AI off, recorded: the next call is refused."""
    from modules import identity
    from modules import installation_settings as I

    try:
        out = I.ai_off(identity.request_actor(), _verified())
    except I.Refused as exc:
        return _install("ai", 409, refused=str(exc))
    return _install("ai", ai_off=out)


# ── Settings › AI: background features per network (board AI3 and AI3b; C1843) ─────────────

def _ai_section(network: str, status: int = 200, **ctx):
    """The background-features section of *network*, with an action's answer in place."""
    from modules.ai import settings_view

    return _fragment("v2/_settings_ai_bg.html", status, ai=settings_view.view(network), **ctx)


def _ai_form(network: str, feature: str, status: int = 200, **ctx):
    """The section with Turn on…'s form open on the feature's row (a refusal's answer): the
    estimate measured now, so a moved one is drawn to accept again."""
    from modules.ai import background, settings_view

    try:
        o = settings_view.turn_on_form(network, feature)
    except background.Refused as exc:
        return _ai_section(network, 404, refused=str(exc))
    return _ai_section(network, status, open_on=o, **ctx)


def _ai_person() -> str:
    """"" when this request is a verified person's, else why not, naming what it is. Turning
    a background feature on, off or changing its caps is an admin's decision; Mercury holds no
    roles yet, so every verified person is an admin (NSOT_AUTHORIZATION section 6), and a
    service or an unverified request never is, whatever `configure`'s settings allow."""
    from modules import identity

    ident = identity.verified_identity()
    if ident is None:
        return ("a background AI feature is changed by a verified person (an admin); this "
                "request's identity is not verified")
    if ident.kind != "person":
        return ("a background AI feature is changed by a verified person (an admin); this "
                f"request is a {ident.kind or 'requester of unknown kind'} "
                f"({ident.actor}), not a person")
    return ""


@bp.route("/installation/ai/background", methods=["GET"])
def ai_background():
    """Board AI3: the background-features section on the network chosen (Network ▾, Cancel)."""
    return _ai_section(request.args.get("network") or "")


@bp.route("/installation/ai/background/<network>/<feature>/on", methods=["GET"])
def ai_on_form(network, feature):
    """Board AI3b: Turn on… opens the estimate in place of the feature's row; writes nothing."""
    return _ai_form(network, feature)


@bp.route("/installation/ai/background/<network>/<feature>/on", methods=["POST"])
def ai_on(network, feature):
    """Board AI3b: turn *feature* on for *network* with the estimate the person saw (its
    digest, ``shown``), their acceptance and their caps; refused, naming why, with nothing
    changed, when they are not a verified person, did not accept, gave a cap out of range, or
    the estimate moved (both digests named, the estimate now drawn to accept again)."""
    from modules import identity
    from modules.ai import background
    from modules.ai.settings_view import caps_value, drawn_entry, pick

    form = request.form
    kept = {"day_typed": form.get("day_cap_usd", ""), "month_typed": form.get("month_cap_usd", "")}
    why = _ai_person()
    if not why and form.get("accept") != "on":
        why = ("the estimate was not accepted: tick “I have read the estimate” to turn it on; "
               "nothing was changed")
    if why:
        return _ai_form(network, feature, 403 if "verified person" in why else 409,
                        form_refused=why, **kept)
    try:
        out = background.turn_on(network, feature,
                                 day_cap_usd=caps_value(form.get("day_cap_usd")),
                                 month_cap_usd=caps_value(form.get("month_cap_usd")),
                                 shown=form.get("shown", ""),
                                 actor=identity.request_actor(), verified=_verified())
    except background.Refused as exc:
        return _ai_form(network, feature, 409, form_refused=str(exc), **kept)
    return _ai_section(network, turned_on=dict(
        pick(out, "recorded", "record_error"), feature=feature,
        entry=drawn_entry(out["entry"], "day_cap_usd", "month_cap_usd")))


def _ai_spend_panel(network: str, status: int = 200, **ctx):
    """The spend panel (board AI2) with Turn off's answer in place: the same write path and
    gate as Settings › AI's Turn off, drawn where it was pressed (``?answer=panel``), naming
    the network it was pressed for."""
    from modules.ai import spend_view
    from routes.operations import viewer_key

    return _fragment("v2/_ai_spend.html", status, s=spend_view.panel(viewer_key()),
                     off_network=spend_view.network_name(network), **ctx)


@bp.route("/installation/ai/background/<network>/<feature>/off", methods=["POST"])
def ai_off(network, feature):
    """Board AI3: Turn off, one click, no confirm (it spends nothing); recorded. Pressed in the
    top bar's spend panel (board AI2, ``?answer=panel``), the panel is its answer, read after
    the write; the write and its gate are this route's either way (one home for the action)."""
    from modules import identity
    from modules.ai import background
    from modules.ai.settings_view import pick

    panel = request.args.get("answer") == "panel"

    def answer(status=200, **ctx):
        return (_ai_spend_panel if panel else _ai_section)(network, status, **ctx)
    why = _ai_person()
    if why:
        return answer(403, refused=why)
    try:
        out = background.turn_off(network, feature, actor=identity.request_actor(),
                                  verified=_verified())
    except background.Refused as exc:
        return answer(409, refused=str(exc))
    return answer(turned_off=dict(
        pick(out, "nothing", "actor_label", "at_iso", "recorded", "record_error"),
        feature=feature))


@bp.route("/installation/ai/background/<network>/<feature>/caps", methods=["GET"])
def ai_caps_form(network, feature):
    """Board AI3: Change caps… opens in place of the feature's row; writes nothing."""
    from modules.ai import background

    try:
        background._spec(feature)
    except background.Refused as exc:
        return _ai_section(network, 404, refused=str(exc))
    return _ai_section(network, open_caps=feature)


@bp.route("/installation/ai/background/<network>/<feature>/caps", methods=["POST"])
def ai_caps(network, feature):
    """Board AI3: an on feature's caps changed by an admin, within the installation's day cap;
    recorded with both values. Mercury never raises a cap by itself."""
    from modules import identity
    from modules.ai import background
    from modules.ai.settings_view import caps_value, pick

    form = request.form
    why = _ai_person()
    if not why:
        try:
            out = background.set_caps(network, feature,
                                      day_cap_usd=caps_value(form.get("day_cap_usd")),
                                      month_cap_usd=caps_value(form.get("month_cap_usd")),
                                      actor=identity.request_actor(), verified=_verified())
            return _ai_section(network, caps_set=dict(
                pick(out, "recorded", "record_error"), feature=feature,
                entry=pick(out["entry"], "day_cap_usd", "month_cap_usd", "caps_by",
                           "caps_at")))
        except background.Refused as exc:
            why = str(exc)
    return _ai_section(network, 403 if "verified person" in why else 409, open_caps=feature,
                       form_refused=why, day_typed=form.get("day_cap_usd", ""),
                       month_typed=form.get("month_cap_usd", ""))


@bp.route("/installation/netbox/writes-off", methods=["POST"])
def install_writes_off():
    """Board F3: turn NetBox's master switch off, recorded. Turning it on stays an authorised
    NetBox write's confirm."""
    from modules import identity
    from modules import installation_settings as I

    try:
        out = I.netbox_writes_off(identity.request_actor(), _verified())
    except I.Refused as exc:
        return _install("netbox", 409, refused=str(exc))
    return _install("netbox", writes_off=out)


# ── Board F4, Platforms and roles: preview, Test, bound confirm ─────────────────────────────

def _platforms(status: int = 200, **ctx):
    from modules import platform_maps as P

    return _fragment("v2/_install_platforms.html", status, pm=P.view(), **ctx)


@bp.route("/installation/platforms", methods=["GET"])
def platforms_card():
    """The two map cards drawn again (Cancel, and after a change)."""
    return _platforms()


@bp.route("/installation/platforms/preview", methods=["POST"])
def platforms_preview():
    """Preview changes (Remove and Add too): every device whose driver or role the change
    moves, from each NetBox list's last inventory; nothing is written."""
    from modules import platform_maps as P

    try:
        pv = P.preview(request.form.get("kind", ""), request.form)
    except P.Refused as exc:
        return _platforms(409, refused=str(exc))
    return _platforms(pv=pv)


@bp.route("/installation/platforms/test", methods=["POST"])
@no_store
def platforms_test():
    """The Test: one read-only session to one affected device with the new driver, as a reads
    job; answered in place when the job announces."""
    from modules import identity
    from modules import platform_maps as P

    network, _, rest = (request.form.get("target") or "").partition("|")
    device, _, driver = rest.partition("|")
    try:
        got = P.test(network, device, driver, identity.request_actor())
    except P.Refused as exc:
        got = {"refused": str(exc)}
    from modules import discovery
    t = {"network": network, "device": device, "driver": driver, "run": got.get("run", ""),
         "command": discovery.version_command(driver) or P.TEST_COMMAND}
    if got.get("refused"):
        return _fragment("v2/_install_platforms_test.html", 409,
                         t=dict(t, state="refused", why=got["refused"]))
    return _fragment("v2/_install_platforms_test.html", t=dict(t, state="started"))


@bp.route("/installation/platforms/test/<network>/<run_id:run_id>", methods=["GET"])
def platforms_test_status(network, run_id):
    """The Test's answer, read from its run's record: a read."""
    from modules.nsot import reads

    record = reads.get(network, run_id) or {}
    device = (record.get("devices") or [""])[0]
    driver = (record.get("drivers") or {}).get(device, "")
    from modules import platform_maps as P
    t = {"network": network, "device": device, "driver": driver, "run": run_id,
         "command": (record.get("commands") or [P.TEST_COMMAND])[0]}
    out = (record.get("results") or {}).get(device)
    if not record or record.get("state") == "running" or out is None:
        return _fragment("v2/_install_platforms_test.html", t=dict(t, state="running"))
    answers = out.get("answers") or []
    first = "\n".join(((answers[0].get("answer") or "") if answers else "").splitlines()[:6])
    return _fragment("v2/_install_platforms_test.html",
                     t=dict(t, state=out.get("state"), why=out.get("why", ""),
                            took_s=out.get("took_s"), first=first))


@bp.route("/installation/platforms/apply", methods=["POST"])
def platforms_apply():
    """The confirm, bound to the preview's fingerprint: written, recorded, each NetBox list
    refreshed so its devices take the change."""
    from modules import identity
    from modules import platform_maps as P

    try:
        out = P.apply(request.form.get("proposal", ""), request.form.get("fingerprint", ""),
                      identity.request_actor(), _verified())
    except P.Refused as exc:
        return _platforms(409, refused=str(exc))
    return _platforms(applied=out)


# ── Board F4, Access and identity: read-only; Record this decision the one control ─────────

@bp.route("/installation/access", methods=["GET"])
def install_access():
    """The Access and identity cards at rest, read again when a response announces `posture`
    (P7-05); a result stays where Record this decision drew it."""
    from modules import identity
    from modules import installation_settings as I

    return _fragment("v2/_install_access.html", acc=I.access_view(identity.identify(request)))


@bp.route("/installation/access/record", methods=["POST"])
def install_ratify():
    """Record this decision: each named access or identity setting that is defaulted gets the
    value already in force written, so nothing changes; recorded in the installation's settings
    record (C625). A person, as today's ratify (`ratify_setting`)."""
    from modules import identity
    from modules import installation_settings as I

    ident = identity.identify(request)
    try:
        out = I.ratify_keys(request.form.getlist("keys"), identity.request_actor(), _verified())
    except I.Refused as exc:
        return _fragment("v2/_install_access.html", 409, acc=I.access_view(ident),
                         refused=str(exc))
    return _fragment("v2/_install_access.html", acc=I.access_view(ident), done=out)


# ── Board E2a, Display names (the operator, 2026-11-11): how each person is named on
#    Mercury's screens, records' summaries and exports (modules/display_names.py). ───────────

def _display_names(status: int = 200, **ctx):
    """The Display names card for this request's viewer: their own row, then every other
    person who has one. A verified person may change their own; an admin anyone's, and Mercury
    holds no roles yet, so every verified person is an admin (NSOT_AUTHORIZATION section 6); a
    service or an unverified request changes none."""
    from modules import display_names, identity

    ident = identity.viewer()
    person = bool(ident.is_identified and ident.kind == "person")
    how = {identity.LOCAL_ACCOUNT: "with this installation's local account",
           identity.ACCESS: "through Cloudflare Access"}.get(
               identity.verification_of(ident), "") if person else ""
    return _fragment("v2/_display_names.html", status,
                     dn=display_names.view(ident.actor if person else "", how, admin=person),
                     **ctx)


@bp.route("/installation/display-names", methods=["GET"])
def display_names_card():
    """The Display names card at rest, read again when a response or an announcement names
    `people`; a result (saved or refused) stays where its Save drew it."""
    return _display_names()


@bp.route("/installation/display-names/save", methods=["POST"])
def display_name():
    """Set one person's display name, or return it to the default (Use the default, or an
    empty name): the viewer's own, or another listed person's by the key their row carries
    (never their identity, which the page does not hold outside its record). Recorded in the
    store's row with who set it and how they were verified. Refused, naming both sides, with
    nothing changed: a name holding an "@", one over 32 printable characters, one another
    person already has, a name Mercury uses for itself, an unreadable store, and a request
    that is no verified person's."""
    from modules import display_names, identity, invalidation

    ident = identity.verified_identity()
    if ident is None or ident.kind != "person":
        return _display_names(403, refused=(
            "A display name is set by a verified person: this request's identity is not "
            "verified." if ident is None else
            "A display name is set by a verified person: this request is a "
            f"{ident.kind or 'requester of unknown kind'} "
            f"({identity.display_name(ident.actor)}), not a person."))
    actor, form = identity.request_actor(), request.form
    # What was typed stays in its row's form through a refusal (the viewer's own row when
    # the key names nobody).
    kept = {"typed": form.get("name", ""), "typed_for": display_names.person_key(actor)}
    try:
        person = display_names.resolve(form.get("person", ""), actor)
        if person:
            kept["typed_for"] = display_names.person_key(person)
        if not person:
            raise display_names.Refused(
                "No person on this card was named: it was drawn before a change, and is "
                "drawn again here.")
        out = display_names.set_name(
            person, "" if form.get("use_default") else form.get("name", ""), by=actor,
            actor_verified=_verified(), admin=True)
    except display_names.Refused as exc:
        return _display_names(403 if str(exc).startswith("Only an admin") else 409,
                              refused=str(exc), **kept)
    except display_names.Unreadable as exc:
        return _display_names(409, refused=(f"The display names could not be read "
                                            f"({exc.kind}), so nothing was saved."), **kept)
    if not out["nothing"]:
        # Every other open page draws people too (its chip, Needs attention): told at once.
        try:
            invalidation.announce(invalidation.ANNOUNCERS["display-names"], by="display-names")
        except Exception as exc:                        # noqa: BLE001 (the name is saved)
            log.warning("display names: the change was not announced (%s); each page draws "
                        "it at its next read", type(exc).__name__)
    return _display_names(done={"you": person == actor, "shown": out["shown"],
                                "was": out["was"] or display_names.default(person),
                                "default": out["default"], "nothing": out["nothing"]})


# ── Time zone (the operator, 2026-11-12): the zone each person's screens draw their times in,
#    kept per person as a display name is (modules/time_zones.py). ────────────────────────────

def _time_zone(status: int = 200, **ctx):
    """The Time zone card for this request's viewer: their own zone, where it came from, and
    Change…; a service or an unverified request has none to set."""
    from modules import identity, time_zones

    ident = identity.viewer()
    person = bool(ident.is_identified and ident.kind == "person")
    return _fragment("v2/_time_zone.html", status,
                     tz=time_zones.view(ident.actor if person else ""), **ctx)


@bp.route("/installation/time-zone", methods=["GET"])
def time_zone_card():
    """The Time zone card at rest; a result (saved or refused) stays where its Save drew it."""
    return _time_zone()


@bp.route("/installation/time-zone/save", methods=["POST"])
def time_zone():
    """Set the viewer's own time zone: from the card's Change… (``source`` absent, a person's
    choice), or from the page's script on a first visit (``source=browser``, the browser's own
    zone, set only while none is stored). Recorded in the store's row with who set it, how they
    were verified and where it came from. Refused, naming both sides, with nothing changed: a
    zone `zoneinfo` does not know, an unreadable store, and a request that is no verified
    person's."""
    from modules import identity, time_zones

    ident = identity.verified_identity()
    if ident is None or ident.kind != "person":
        return _time_zone(403, refused=(
            "A time zone is set by a verified person: this request's identity is not "
            "verified." if ident is None else
            "A time zone is set by a verified person: this request is a "
            f"{ident.kind or 'requester of unknown kind'} "
            f"({identity.display_name(ident.actor)}), not a person."))
    actor, form = identity.request_actor(), request.form
    source = "browser" if form.get("source") == "browser" else "person"
    typed = form.get("zone", "")
    try:
        out = time_zones.set_zone(actor, typed, by=actor, actor_verified=_verified(),
                                  source=source)
    except time_zones.Refused as exc:
        return _time_zone(409, refused=str(exc), typed=typed)
    except time_zones.Unreadable as exc:
        return _time_zone(409, refused=(f"The time zones could not be read ({exc.kind}), so "
                                        "nothing was saved."), typed=typed)
    return _time_zone(done={"zone": out["zone"], "was": out["was"], "nothing": out["nothing"],
                            "source": out["source"]})


# ── The installation's one local account (modules/local_account.py): its card, sign-in and
#    sign-out. Off by default, and only where Mercury listens on loopback only. ─────────────

def _local_card(status: int = 200, signed_in_as: str = None, **ctx):
    """The card. *signed_in_as* is the response's own change (a name on a sign-in, "" on a
    sign-out), which this request's cookie does not carry yet."""
    from modules import local_account as LA

    la = LA.view(request)
    if signed_in_as is not None:
        la = dict(la, signed_in=bool(signed_in_as), name=signed_in_as)
    return _fragment("v2/_local_account.html", status, la=la, **ctx)


@bp.route("/installation/local-account", methods=["GET"])
def local_account_card():
    """The local account's card: the sign-in form, who is signed in, or why it is not offered."""
    return _local_card()


@bp.route("/installation/local-account/sign-in", methods=["POST"])
@no_store
def local_sign_in():
    """Sign the local account in: a signed session cookie when the name and password are the
    account's. The password is read from the form and never drawn back, logged or kept."""
    from modules import local_account as LA

    got = LA.sign_in(request, request.form.get("name", ""), request.form.get("password", ""))
    if not got["ok"]:
        return _local_card(403 if got["why"].startswith(("refused", "local sign-in is off"))
                           else 401, la_refused=got["why"])
    out = _local_card(signed_in_as=got["name"])
    out.set_cookie(LA.COOKIE, got["cookie"], **LA.cookie_args(request))
    # Every part of the page draws the viewer: read it all again as the person signed in.
    out.headers["HX-Refresh"] = "true"
    return out


@bp.route("/installation/local-account/sign-out", methods=["POST"])
@no_store
def local_sign_out():
    """Sign the local account out: the session cookie cleared."""
    from modules import local_account as LA

    st = LA.state()
    why = (f"local sign-in is off: {st['why']}" if not st["enabled"]
           else LA.origin_refusal(request))
    if why:
        return _local_card(403, la_not_out=why)
    out = _local_card(signed_in_as="")
    out.delete_cookie(LA.COOKIE, path="/")
    out.headers["HX-Refresh"] = "true"
    return out


@bp.after_app_request
def _local_session_seen(response):
    """A local session's last-seen time, written again when `local_account.identity` found it
    older than its refresh interval: the session ends by idleness, not by its first issue."""
    try:
        from flask import current_app, g

        sess = getattr(g, "nmas_local_refresh", None)
        if sess:
            from modules import local_account as LA

            acct = LA.account()
            if acct and acct.get("name") == sess.get("name"):
                response.set_cookie(LA.COOKIE, LA.issue(acct, current_app.secret_key,
                                                        issued=sess["issued"]),
                                    **LA.cookie_args(request))
    except Exception:                                   # noqa: BLE001 (never breaks a response)
        pass
    return response


# ── Board F4, Diagnostics: four cards; the drift card's controls are the only writes ────────

@bp.route("/installation/diagnostics/redaction", methods=["GET"])
def diag_redaction():
    """Log redaction, measured now (C624): a read that writes nothing."""
    from modules import installation_diagnostics as D

    return _fragment("v2/_diag_redaction.html", red=D.redaction())


def _drift(status: int = 200, **ctx):
    from modules import installation_diagnostics as D

    return _fragment("v2/_diag_drift.html", status, dr=D.drift(), **ctx)


@bp.route("/installation/diagnostics/drift", methods=["GET"])
def diag_drift():
    """The drift card drawn again (a drift run recorded announces `drift`)."""
    return _drift()


@bp.route("/installation/diagnostics/drift/interval", methods=["POST"])
def diag_drift_interval():
    """The drift schedule, one for every network, saved and recorded."""
    from modules import identity
    from modules import installation_diagnostics as D
    from modules import installation_settings as I

    try:
        out = D.save_drift_interval(request.form.get("interval_s"), identity.request_actor(),
                                    _verified())
    except I.Refused as exc:
        return _drift(409, refused=str(exc))
    words = ("Nothing changed: the schedule already was that." if out.get("nothing") else
             f"Saved by {out.get('actor_label')}: every network is checked on the new "
             "schedule, recorded in the installation's settings record.")
    return _drift(done=dict(out, words=words))


@bp.route("/installation/diagnostics/drift/<network>/<to>", methods=["POST"])
def diag_drift_switch(network, to):
    """A network's drift checks turned off or on, with who and when, recorded."""
    from modules import identity
    from modules import installation_diagnostics as D
    from modules import installation_settings as I

    if to not in ("off", "on"):
        return _drift(404, refused=f"{to!r} is neither off nor on")
    try:
        out = D.set_drift_off(network, to == "off", identity.request_actor(), _verified())
    except I.Refused as exc:
        return _drift(409, refused=str(exc))
    words = (f"{network}'s drift checks already were {to}." if out.get("nothing") else
             f"{network}'s drift checks turned {to} by {out.get('actor_label')}, recorded.")
    return _drift(done=dict(out, words=words))


@bp.route("/installation/diagnostics/drift/<network>/check", methods=["POST"])
def diag_drift_check(network):
    """Check now: a network's drift check started in the background (the schedule does it
    anyway, only later); the card redraws when it is recorded."""
    from modules import installation_diagnostics as D
    from modules import installation_settings as I

    try:
        out = D.check_now(network)
    except I.Refused as exc:
        return _drift(409, refused=str(exc))
    return _drift(done=dict(out, recorded=True,
                            words=f"A drift check of {network} started: this card redraws "
                                  "when it finishes, and what it finds is on Needs attention."))


@bp.route("/installation/diagnostics/inflight", methods=["GET"])
def diag_inflight():
    """Every network's running operations and recent receipts: a read."""
    from modules import installation_diagnostics as D

    return _fragment("v2/_diag_inflight.html", fl=D.in_flight())


@bp.route("/installation/diagnostics/log", methods=["GET"])
def diag_log():
    """The app's log, its last lines filtered: a read."""
    from modules import installation_diagnostics as D

    return _fragment("v2/_diag_log.html", lg=D.app_log(request.args.get("lines"),
                                                       request.args.get("contains", "")))


@bp.route("/network/<list_name>", methods=["GET"])
def network(list_name):
    from modules import network_admin
    from modules import settings_page
    from modules.nsot import listref

    if not listref.exists(list_name):
        # C1029: a DELETED network's page (`list_param` lets only this one through) says when
        # it was deleted and where its data is, and offers nothing: every write naming it is
        # refused before its view. It drew every card with Save and Preview, live.
        gone = network_admin.deletion(list_name)
        v = {"network": list_name, "deleted": gone,
             "scope": settings_page.scope_bar(list_name),
             "mode_words": "deleted: it has left every page"}
        return _strict(render_template("v2/settings.html", who=_who(), active_nav="settings",
                                       v=v), 410)
    v = settings_page.network_view(list_name, request.args.get("tab") or "integrations")
    src = sdn = aic = crepo = None
    if v.get("tab") == "network" and not v.get("error"):
        from modules import coderepo
        from modules import network_source as NS
        from modules.ai import egress_classes
        src = NS.view(list_name)
        # Board H, artboard N (H28): the network's AI data classes, its device state switch.
        aic = egress_classes.classes_view(list_name)
        # Board code-repository, artboard A: the network's code repository and Fetch now.
        crepo = coderepo.card(list_name)
    if v.get("tab") == "integrations" and not v.get("error"):
        from modules import sdn_page
        sdn = sdn_page.card(list_name)
    heal = None
    if v.get("tab") == "heal" and not v.get("error"):
        # Board H, artboard A (H9): the network's Self-healing tab, its own template.
        from modules import heal_page
        heal = heal_page.view(list_name)
    return _page("v2/settings.html", v=v, list_name=list_name, src=src, sdn=sdn, heal=heal,
                 aic=aic, crepo=crepo)


@bp.route("/network/<list_name>/group/<group>", methods=["GET"])
def group_card(list_name, group):
    """One card, drawn again (Cancel, Close, and a page's refresh after a switch)."""
    return _card(list_name, group)


def _card(list_name: str, group: str, result: dict = None, saved: dict = None,
          tested: dict = None):
    from modules import list_settings as L
    from modules import settings_page

    if not settings_page.is_group(group):
        return _fragment("v2/_settings_refused.html", 404, list_name=list_name, group="",
                         why=f"{group!r} is not a settings group a network chooses for")
    try:
        c = settings_page.one_card(list_name, group)
    except L.ListSettingsUnreadable as exc:
        return _fragment("v2/_settings_refused.html", 409, list_name=list_name, group="",
                         why=str(exc))
    return _fragment("v2/_settings_card.html", c=c, list_name=list_name,
                     is_default=L.is_default(list_name), result=result, saved=saved,
                     tested=tested)


@bp.route("/network/<list_name>/group/<group>/switch", methods=["GET"])
def group_preview(list_name, group):
    """The preview of one group's switch, in place of its card (boards B, C and J2)."""
    from modules import list_settings as L
    from modules import preview_confirm

    from modules import settings_page

    to = (request.args.get("to") or "").strip()
    try:
        plan = L.plan_group(list_name, group, to, entering=(to == L.OWN))
        fields = settings_page.form_fields(list_name, group) if to == L.OWN else []
    except (L.SwitchRefused, L.ListSettingsUnreadable) as exc:
        return _fragment("v2/_settings_refused.html", 409, why=str(exc), list_name=list_name,
                         group=group)
    return _fragment("v2/_settings_switch.html", p=plan, list_name=list_name, fields=fields,
                     confirm=preview_confirm.confirm_part(request, "configure"))


@bp.route("/network/<list_name>/group/<group>/switch", methods=["POST"])
def group_switch(list_name, group):
    """Make the group's switch as confirmed: bound to the preview's fingerprint, its typed
    values validated and written as sent, recorded with the verified person."""
    from modules import identity
    from modules import list_settings as L
    from modules.settings_scope import group_keys

    from modules.secrets_store import SECRET_KEYS

    form = request.form
    to = (form.get("to") or "").strip()
    # A field the form sent empty is not set here any more (None); an empty SECRET keeps what
    # is stored, because a secret is never drawn back into the form to be sent again.
    values = {}
    if to == L.OWN:
        for k in group_keys(group):
            if k not in form:
                continue
            if (form.get(k) or "") == "":
                if k not in SECRET_KEYS:
                    values[k] = None
                continue
            values[k] = form.get(k)
    try:
        seen = json.loads(form.get("seen") or "null")
    except ValueError:
        seen = None
    try:
        out = L.apply_group(list_name, group, to, form.get("fingerprint") or "",
                            identity.request_actor(), _verified(),
                            values=_typed(values), reason=form.get("reason") or "", seen=seen)
    except (L.SwitchRefused, L.ListSettingsUnreadable) as exc:
        return _fragment("v2/_settings_refused.html", 409, why=str(exc), list_name=list_name,
                         group=group)
    return _card(list_name, group, result=out)


@bp.route("/network/<list_name>/group/<group>/save", methods=["POST"])
def group_save(list_name, group):
    """Boards A and D: save a card's fields as sent, for Default or a network's own group,
    recorded with the verified person and the fields' names. An empty field keeps what is
    stored; the card is drawn again with the result in place.

    Only what the person changed is saved (CONCURRENCY_AUDIT R17): the card sends what it drew
    (`loaded`), so a field still as drawn is never written, and a changed field another person
    moved since is refused, naming both values, nothing saved. Compared and written under one
    hold of the settings lock."""
    from modules import identity
    from modules import list_settings as L
    from modules import settings_page
    from modules.config import settings_lock
    from modules.secrets_store import SECRET_KEYS
    from modules.settings_schema import (NOT_LOADED, changed_since_loaded, loaded_from,
                                         moved_words)
    from modules.settings_scope import group_keys

    form = request.form
    loaded = loaded_from(form.get("loaded"))
    if loaded is None:
        return _fragment("v2/_settings_refused.html", 409, why=NOT_LOADED, list_name=list_name,
                         group=group)
    values = {k: form.get(k) for k in group_keys(group) if (form.get(k) or "") != ""}
    try:
        with settings_lock():
            now = settings_page.drawn(settings_page.form_fields(list_name, group))
            plain, moved = changed_since_loaded(
                {k: v for k, v in values.items() if k not in SECRET_KEYS}, loaded, now)
            if moved:
                raise L.SwitchRefused("; ".join(moved_words(moved)))
            # A secret is never drawn, so one typed is always a change.
            plain.update({k: v for k, v in values.items() if k in SECRET_KEYS})
            out = L.save_values(list_name, group, _typed(plain), identity.request_actor(),
                                _verified())
    except (L.SwitchRefused, L.ListSettingsUnreadable) as exc:
        return _fragment("v2/_settings_refused.html", 409, why=str(exc), list_name=list_name,
                         group=group)
    return _card(list_name, group, saved=out)


@bp.route("/network/<list_name>/group/<group>/test", methods=["POST"])
def group_test(list_name, group):
    """Boards A and D: test the integration a card configures, with its saved values, and draw
    the answer in the card. Changes no setting."""
    from modules import list_settings as L
    from modules import settings_page

    cls = settings_page.integration_for(group)
    if cls is None:
        return _fragment("v2/_settings_refused.html", 404, list_name=list_name, group=group,
                         why=f"{group!r} configures no integration to test")
    client = cls(list_name="" if L.is_default(list_name) else list_name)
    if not client.is_configured():
        result = {"ok": False, "error": "not configured: save its values first"}
    else:
        try:
            result = client.test_connection()
        except Exception as exc:                          # noqa: BLE001 (said in the card)
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return _card(list_name, group, tested=result)


# ── SDN controllers (PHASE8_PLAN 17.1 S2's interface; board SdnSettings, signed off 2026-10-27)

def _sdn(list_name: str, code: int = 200, editing: str = "", **ctx):
    """The SDN controllers card on a network's Integrations tab, drawn whole."""
    from modules import sdn_page

    return _fragment("v2/_sdn_settings.html", code, k=sdn_page.card(list_name, editing),
                     list_name=list_name, **ctx)


def _sdn_answer(list_name: str, code: int = 200, **ctx):
    """An answer drawn in place beside the control that asked (Test, a refused Save)."""
    return _fragment("v2/_sdn_answer.html", code, list_name=list_name, **ctx)


@bp.route("/network/<list_name>/sdn", methods=["GET"])
def sdn_card(list_name):
    """The card, drawn again (Cancel, and Edit's Cancel)."""
    return _sdn(list_name)


@bp.route("/network/<list_name>/sdn/edit/<name>", methods=["GET"])
def sdn_edit(list_name, name):
    """Edit: the card with its form holding the connection's values, its credential never
    drawn (a blank keeps it)."""
    return _sdn(list_name, editing=name)


@bp.route("/network/<list_name>/sdn/test", methods=["POST"])
def sdn_test(list_name):
    """Test connection with the form's values as typed, before anything is saved: the
    controller's switches and version, or why it could not connect, in place. A Test that
    answered hands the form its receipt (`sdn_page.tested_receipt`), which Save needs. Writes
    nothing."""
    from modules import sdn_page
    from modules.sdn import connections

    values = sdn_page.form_values(request.form, sdn_page.loaded_of(request.form))
    got = connections.test_connection(dict(values, network=list_name))
    receipt = sdn_page.tested_receipt(list_name, values) if got.get("ok") else ""
    return _sdn_answer(list_name, tested=got, receipt=receipt, url=values.get("url"))


@bp.route("/network/<list_name>/sdn/save", methods=["POST"])
def sdn_save(list_name):
    """Save: refused while Test has not answered for the URL as typed (board SdnSettings),
    and when the connection moved since the form drew it; else saved FOR the network, recorded
    with the verified person, and the card drawn again with the result. A refusal is drawn
    beside Save, the form kept as typed."""
    from flask import make_response

    from modules import identity
    from modules import sdn_page
    from modules.sdn import connections

    loaded = sdn_page.loaded_of(request.form)
    values = sdn_page.form_values(request.form, loaded)
    problem = sdn_page.tested_problem(list_name, values, request.form.get("tested") or "")
    if problem:
        return _sdn_answer(list_name, 409, refused=problem)
    try:
        saved = connections.save_connection(list_name, values, identity.request_actor(),
                                            _verified(), loaded=loaded)
    except connections.ConnectionRefused as exc:
        return _sdn_answer(list_name, 409, refused=str(exc))
    resp = make_response(_sdn(list_name, saved=saved))
    # The answer replaces the whole card (its list now holds the connection), not the slot
    # beside Save that a refusal is drawn in.
    resp.headers["HX-Retarget"] = "#sdn-card"
    resp.headers["HX-Reswap"] = "outerHTML"
    return resp


@bp.route("/network/<list_name>/sdn/<name>/test", methods=["POST"])
def sdn_saved_test(list_name, name):
    """Test connection on a saved connection, with what is saved: in place, on its row."""
    from modules.sdn import connections

    return _sdn_answer(list_name, tested=connections.test_saved(list_name, name), name=name)


@bp.route("/network/<list_name>/sdn/<name>/remove", methods=["GET"])
def sdn_remove_card(list_name, name):
    """Remove…: in place of the card, what removing it does and what survives, with Remove
    and Cancel."""
    from modules import sdn_page

    k = sdn_page.card(list_name)
    if not any(c["name"] == name for c in k["connections"]):
        return _sdn(list_name, 409, refused=f"{list_name} has no controller connection "
                                            f"{name!r}; nothing to remove")
    return _fragment("v2/_sdn_settings.html", k=k, list_name=list_name, removing=name)


@bp.route("/network/<list_name>/sdn/<name>/remove", methods=["POST"])
def sdn_remove(list_name, name):
    """Remove the connection and its credential, recorded; the card drawn again saying what
    survives."""
    from modules import identity
    from modules.sdn import connections

    try:
        out = connections.remove_connection(list_name, name, identity.request_actor(),
                                            _verified())
    except connections.ConnectionRefused as exc:
        return _sdn(list_name, 409, refused=str(exc))
    return _sdn(list_name, removed={k: out[k] for k in ("name", "credential_cleared",
                                                         "recorded", "survives")})


@bp.route("/network/<list_name>/sdn/stage", methods=["POST"])
def sdn_stage(list_name):
    """Mark the network lab, pilot or production (C2009; PHASE8_PLAN 17.7's guard: AUTO is
    turned on only on a network marked lab until the AUTO production-readiness gate is
    complete), as the verified person with their reason, recorded in the network's settings
    record with the stage before and after; refused when it moved since the card drew it. The
    card drawn again with the answer, a refusal in it."""
    from modules import identity
    from modules.sdn import modes

    try:
        out = modes.set_stage(list_name, request.form.get("stage") or "",
                              actor=identity.request_actor(), actor_verified=_verified(),
                              reason=request.form.get("reason") or "",
                              loaded=request.form.get("loaded"))
    except modes.ModeRefused as exc:
        return _sdn(list_name, 409, refused=str(exc))
    return _sdn(list_name, staged={k: out[k] for k in ("before", "after", "unchanged",
                                                        "recorded")})


# ── A network's code repository (the SDN platform design revision 7, 11c.2 and 11c.3; board
#    docs/boards/code-repository.html, signed off under the Phase 7 mode 2026-11-08): its
#    location and branch, and Fetch now, on the Network tab's Code repository card. ───────────

def _code_repo(list_name: str, code: int = 200, **ctx):
    """The Code repository card, drawn whole with *ctx*'s answer at its top."""
    from modules import coderepo

    return _fragment("v2/_code_repo.html", code, r=coderepo.card(list_name),
                     list_name=list_name, **ctx)


@bp.route("/network/<list_name>/code-repository", methods=["GET"])
def code_repo_card(list_name):
    """The card, drawn again (on `code_repo`: another person's save or fetch). A read."""
    return _code_repo(list_name)


@bp.route("/network/<list_name>/code-repository", methods=["POST"])
def code_repo_save(list_name):
    """Set the network's code repository (its location and branch) as the verified person,
    refused when it moved since the card drew it, recorded in the network's settings record;
    the card drawn again with the answer, a refusal keeping what was typed."""
    from modules import coderepo, identity

    typed = {"location": request.form.get("location") or "",
             "branch": request.form.get("branch") or ""}
    try:
        out = coderepo.set_location(list_name, typed["location"], typed["branch"],
                                    actor=identity.request_actor(), actor_verified=_verified(),
                                    loaded=request.form.get("loaded"))
    except coderepo.Refused as exc:
        return _code_repo(list_name, 409, refused=str(exc), typed=typed)
    return _code_repo(list_name, saved={
        "unchanged": out["unchanged"], "before_words": coderepo.setting_words(out["before"]),
        "after_words": coderepo.setting_words(out["after"])})


@bp.route("/network/<list_name>/code-review", methods=["POST"])
def code_review_save(list_name):
    """Who may publish the network's app versions (C2854; board app-publish E), set as the
    verified person, refused when it moved since the card drew it, recorded in the network's
    settings record; the card drawn again with the answer."""
    from modules import coderepo, identity

    try:
        out = coderepo.set_review(list_name, request.form.get("review") or "",
                                  actor=identity.request_actor(), actor_verified=_verified(),
                                  loaded=request.form.get("loaded_review"))
    except coderepo.Refused as exc:
        return _code_repo(list_name, 409, refused=str(exc))
    return _code_repo(list_name, saved={
        "unchanged": out["unchanged"],
        "review_words": coderepo.REVIEW_CHOICES.get(out["after"], out["after"])})


@bp.route("/network/<list_name>/code-repository/fetch", methods=["POST"])
def code_repo_fetch(list_name):
    """Fetch now: the network's code repository fetched into Mercury's read-only copy and what
    is at the fetched commit registered, for the verified person; a failed fetch is recorded
    and said. Nothing is written to the repository it copies."""
    from modules import coderepo, identity

    try:
        out = coderepo.fetch(list_name, actor=identity.request_actor(),
                             actor_verified=_verified())
    except coderepo.Refused as exc:
        return _code_repo(list_name, 409, refused=str(exc))
    return _code_repo(list_name, 200 if out["ok"] else 502, fetched=out)


@bp.route("/network/<list_name>/mode/banner", methods=["GET"])
def mode_banner(list_name):
    """The mode's banner, drawn again (the preview's Cancel)."""
    from modules import settings_page

    v = settings_page.network_view(list_name)
    if v["is_default"] or v["error"]:
        return _fragment("v2/_settings_refused.html", 409, list_name=list_name, group="",
                         why=v["error"] or "Default is the base layer: it has no mode")
    return _fragment("v2/_settings_mode.html", s=v, list_name=list_name)


@bp.route("/network/<list_name>/mode", methods=["GET"])
def mode_preview(list_name):
    """J1: making the network standalone, or inheriting again, as a preview."""
    from modules import list_settings as L
    from modules import preview_confirm

    to = (request.args.get("to") or "").strip()
    try:
        plan = L.plan_mode(list_name, to)
    except (L.SwitchRefused, L.ListSettingsUnreadable) as exc:
        return _fragment("v2/_settings_refused.html", 409, why=str(exc), list_name=list_name)
    return _fragment("v2/_settings_mode.html", p=plan, list_name=list_name,
                     confirm=preview_confirm.confirm_part(request, "configure"))


@bp.route("/network/<list_name>/mode", methods=["POST"])
def mode_switch(list_name):
    from modules import identity
    from modules import list_settings as L

    form = request.form
    try:
        seen = json.loads(form.get("seen") or "null")
    except ValueError:
        seen = None
    try:
        out = L.apply_mode(list_name, (form.get("to") or "").strip(),
                           form.get("fingerprint") or "", identity.request_actor(),
                           _verified(), seen=seen)
    except (L.SwitchRefused, L.ListSettingsUnreadable) as exc:
        return _fragment("v2/_settings_refused.html", 409, why=str(exc), list_name=list_name)
    return _fragment("v2/_settings_mode.html", result=out, list_name=list_name)


def _verified() -> str:
    """How the actor was established, as every commit's ``Actor-Verified:`` says it."""
    from modules import identity

    return identity.actor_verification(identity.request_actor())


def _typed(values: dict) -> dict:
    """A form sends text: each value as its schema's type (a whole number, a switch, a list
    or table as JSON). One that cannot be read as its type is passed as sent, and the schema's
    validation refuses it, naming the key."""
    from modules.settings_schema import DEFAULTS

    out = {}
    for k, v in values.items():
        d = DEFAULTS.get(k)
        try:
            if v is None:
                out[k] = None
            elif isinstance(d, bool):
                out[k] = str(v).lower() in ("1", "true", "on", "yes")
            elif isinstance(d, int):
                out[k] = int(v)
            elif isinstance(d, (list, dict)):
                out[k] = json.loads(v)
            else:
                out[k] = v
        except (TypeError, ValueError):
            out[k] = v
    return out
