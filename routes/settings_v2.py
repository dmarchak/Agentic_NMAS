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
    Connections tab holds the Records database card (F2) and the NetBox connection, Proxmox and
    Commit author cards, and its Server tab the Server card (F3); tabs not yet drawn here say so
    and link to today's Settings page."""
    from modules import installation_settings as I
    from modules import settings_page
    from modules.nsot import listref

    tab = request.args.get("tab") or "connections"
    if tab not in dict(I.TABS):
        tab = "connections"
    v = {"scope": dict(settings_page.scope_bar(listref.active().name), is_installation=True),
         "mode_words": ""}
    cards = [I.card(name) for name, spec in I.CARDS.items() if spec["tab"] == tab]
    diag = {}
    if tab == "diagnostics":
        from modules import installation_diagnostics as D
        diag = {"red": D.redaction(), "dr": D.drift(), "fl": D.in_flight(),
                "lg": D.app_log(None)}
    return _page("v2/settings_installation.html", tab=tab, tabs=I.TABS, built=I.BUILT_TABS,
                 v=v, r=I.records_card() if tab == "connections" else None, cards=cards,
                 a=I.agent_state() if tab == "ai" else None, **diag)


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

    form = {k: request.form.get(k) for k in I.FIELDS}
    try:
        saved = I.save(form, identity.request_actor(), _verified())
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


def _install(name: str, status: int = 200, **ctx):
    """One F3 card drawn, with an action's answer in place; an unknown card is a 404 saying
    which cards there are."""
    from modules import installation_settings as I

    if name not in I.CARDS:
        return _fragment("v2/_settings_refused.html", 404, list_name="", group="",
                         why=f"{name!r} is not an Installation card: {', '.join(I.CARDS)}")
    return _fragment("v2/_install_card.html", status, k=I.card(name), **ctx)


@bp.route("/installation/card/<name>", methods=["GET"])
def install_card(name):
    """Board F3: one card drawn again (Cancel, and a refresh after a change)."""
    return _install(name)


@bp.route("/installation/card/<name>/save", methods=["POST"])
def install_save(name):
    """Board F3: save a card's fields as sent, recorded with the verified person and the
    fields' names; a switch the form did not send is off."""
    from modules import identity
    from modules import installation_settings as I

    if name not in I.CARDS:
        return _install(name)
    form = {f["key"]: request.form.get(f["key"]) for f in I.CARDS[name]["fields"]}
    try:
        saved = I.save_card(name, form, identity.request_actor(), _verified())
    except I.Refused as exc:
        return _install(name, 409, refused=str(exc))
    return _install(name, saved=saved)


@bp.route("/installation/card/<name>/test", methods=["POST"])
def install_test(name):
    """Board F3: the card's Test, its integration asked now with what is saved."""
    from modules import installation_settings as I

    if name not in I.CARDS:
        return _install(name)
    try:
        tested = I.test_card(name)
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
    return _fragment("v2/_install_card_replace.html", k=I.card(name))


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
        return _fragment("v2/_install_card_replace.html", 409, k=I.card(name),
                         refused=str(exc))
    return _install(name, replaced=out, tested=out["tested"])


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
    from modules import settings_page

    v = settings_page.network_view(list_name, request.args.get("tab") or "integrations")
    return _page("v2/settings.html", v=v, list_name=list_name)


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
    stored; the card is drawn again with the result in place."""
    from modules import identity
    from modules import list_settings as L
    from modules.settings_scope import group_keys

    form = request.form
    values = {k: form.get(k) for k in group_keys(group) if (form.get(k) or "") != ""}
    try:
        out = L.save_values(list_name, group, _typed(values), identity.request_actor(),
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
