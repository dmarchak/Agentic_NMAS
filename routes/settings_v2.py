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
