"""routes/notify_v2.py — Settings › Installation › Notifications (board H, artboard B; H9;
docs/HEAL_TO_INTENT.md section 10), over `modules/notify` (H7).

The email relay's fields are a card of `installation_settings.CARDS` ("relay"), saved by
`settings_v2.install_save`; its password's Replace… and its Test send to… are here. The
webhooks and the teams: add a team, add an address or a webhook (each unverified and off, a code
sent to it at once), type the code back (verified, and on), send again, turn one off or on, a
test send, edit a webhook, remove a destination. Each answer is the tab (or the relay card)
drawn again with its answer in place. A secret typed here goes to the credential store and is
never drawn back; a code is never stored, logged or drawn. Nothing here contacts a device.
"""

import logging

from flask import Blueprint, render_template, request

from modules.filestore import StoreUnreadable
from modules.notify.teams import Refused

log = logging.getLogger(__name__)

#: What a teams change refuses with: the store's words, or a store that cannot be read.
_REFUSED = (Refused, StoreUnreadable)

bp = Blueprint("notify_v2", __name__, url_prefix="/v2/settings/installation/notify")


def _fragment(template: str, code: int = 200, **ctx):
    from routes.device_v2 import _strict

    return _strict(render_template(template, **ctx), code)


def _tab(code: int = 200, **ctx):
    """The Notifications tab's body, drawn again with an answer (``answer``: where, ok, words)
    or a form open (``open``)."""
    from modules import notify_page

    return _fragment("v2/_notify.html", code, n=notify_page.view(), **ctx)


def _relay(code: int = 200, **ctx):
    from modules import notify_page

    return _fragment("v2/_notify_relay.html", code, rl=notify_page.relay_view(), **ctx)


def _actor() -> tuple:
    from modules import identity

    actor = identity.request_actor()
    return actor, identity.actor_verification(actor)


def _said(where: str, ok: bool, words: str) -> dict:
    return {"where": where, "ok": ok, "words": words}


def _sent_words(got: dict, what: str) -> str:
    if got.get("outcome") == "sent":
        return f"{what} sent"
    return f"{what} not sent ({got.get('outcome')}): {got.get('error') or 'no reason given'}"


# ── The relay: its password and Test send to… ──────────────────────────────────────────────

@bp.route("/relay/password/form", methods=["GET"])
def relay_password_form():
    """Replace…: the password's field opened in the relay card; nothing is stored until Save."""
    return _relay(replacing=True)


@bp.route("/relay/password", methods=["POST"])
def relay_password():
    """Store the relay's new password (typed by a person) encrypted, and record who and when;
    it is never drawn back."""
    from modules import credentials
    from modules import installation_settings as I

    actor, verified = _actor()
    value = request.form.get("password") or ""
    try:
        credentials.set_notify_secret("relay", value)
    except ValueError as exc:
        return _relay(409, replacing=True, refused=str(exc))
    entry = I._record({"kind": "card_replace", "card": "relay", "fields": ["relay password"],
                       "actor": actor, "actor_verified": verified})
    return _relay(replaced=entry)


@bp.route("/relay/test/form", methods=["GET"])
def relay_test_form():
    """Test send to…: one of the teams' addresses chosen in the relay card."""
    return _relay(testing=True)


@bp.route("/relay/test", methods=["POST"])
def relay_test():
    """A test message to the address chosen (``<team>:<destination>``), through the relay as
    saved; its outcome drawn in the card and kept in the delivery log."""
    from modules.notify import delivery, teams

    actor, _v = _actor()
    team, _sep, dest = (request.form.get("to") or "").partition(":")
    try:
        got = delivery.send_test(team, dest, by=actor)
    except _REFUSED as exc:
        return _relay(409, testing=True, refused=str(exc))
    return _relay(tested=got)


# ── Teams ───────────────────────────────────────────────────────────────────────────────────

@bp.route("/teams/new", methods=["GET"])
def team_add_form():
    """Add a team…: its name's field opened in the Teams card."""
    return _tab(open={"what": "team_new"})


@bp.route("/teams", methods=["POST"])
def team_add():
    from modules.notify import teams

    actor, _v = _actor()
    name = request.form.get("name") or ""
    try:
        teams.add_team(name, by=actor)
    except _REFUSED as exc:
        return _tab(409, open={"what": "team_new", "name": name},
                    answer=_said("teams", False, str(exc)))
    return _tab(answer=_said("teams", True, f"Team {name.strip()} added: add its addresses "
                                            "and webhooks, then choose it on a network's "
                                            "Self-healing tab"))


@bp.route("/teams/<team>/email", methods=["POST"])
def email_add(team):
    """Add an address and send it a code: it receives nothing but its code until the code is
    typed back."""
    from modules.notify import delivery, teams

    actor, _v = _actor()
    address = request.form.get("address") or ""
    try:
        dest = teams.add_email(team, address, by=actor)["destination"]
    except _REFUSED as exc:
        return _tab(409, answer=_said(f"team:{team}", False, str(exc)), typed=address)
    try:
        got = delivery.send_code(team, dest, by=actor)
    except _REFUSED as exc:
        return _tab(409, answer=_said(f"team:{team}", False, f"added, and no code sent: {exc}"))
    return _tab(answer=_said(f"team:{team}", got["outcome"] == "sent",
                             f"{address.strip()} added. " + _sent_words(got, "Its code")
                             + ("; type it within the time below" if got["outcome"] == "sent"
                                else "")))


@bp.route("/teams/<team>/<dest>/code", methods=["POST"])
def code_send(team, dest):
    """Send again: a new code (it replaces the last)."""
    from modules.notify import delivery, teams

    actor, _v = _actor()
    try:
        got = delivery.send_code(team, dest, by=actor)
    except _REFUSED as exc:
        return _tab(409, answer=_said(f"dest:{dest}", False, str(exc)))
    return _tab(answer=_said(f"dest:{dest}", got["outcome"] == "sent",
                             _sent_words(got, "A new code")))


@bp.route("/teams/<team>/<dest>/verify", methods=["POST"])
def code_verify(team, dest):
    """Verify: the code typed back. Right and in time, the destination is verified and turned
    on (verifying it is the person saying it should receive); wrong spends a try."""
    from modules.notify import delivery, teams

    actor, _v = _actor()
    try:
        got = delivery.confirm_code(team, dest, request.form.get("code") or "", by=actor)
        if got["ok"]:
            teams.set_enabled(team, dest, True, by=actor)
    except _REFUSED as exc:
        return _tab(409, answer=_said(f"dest:{dest}", False, str(exc)))
    if not got["ok"]:
        return _tab(409, answer=_said(f"dest:{dest}", False, got["error"]))
    return _tab(answer=_said(f"dest:{dest}", True, "Verified and on: it receives this team's "
                                                   "notices from now"))


@bp.route("/teams/<team>/<dest>/enabled", methods=["POST"])
def dest_enabled(team, dest):
    """Turn off, or Turn on (refused until verified)."""
    from modules.notify import teams

    actor, _v = _actor()
    on = (request.form.get("on") or "") == "on"
    try:
        teams.set_enabled(team, dest, on, by=actor)
    except _REFUSED as exc:
        return _tab(409, answer=_said(f"dest:{dest}", False, str(exc)))
    return _tab(answer=_said(f"dest:{dest}", True, "Turned on: it receives this team's notices"
                             if on else "Turned off: it receives nothing until turned on"))


@bp.route("/teams/<team>/<dest>/test", methods=["POST"])
def dest_test(team, dest):
    """Test send: one message to this destination, verified or not, its outcome in place."""
    from modules.notify import delivery, teams

    actor, _v = _actor()
    try:
        got = delivery.send_test(team, dest, by=actor)
    except _REFUSED as exc:
        return _tab(409, answer=_said(f"dest:{dest}", False, str(exc)))
    return _tab(answer=_said(f"dest:{dest}", got["outcome"] == "sent",
                             _sent_words(got, "A test")))


@bp.route("/teams/<team>/<dest>/remove/ask", methods=["GET"])
def dest_remove_ask(team, dest):
    """Remove…: what removing does, asked in place; nothing is removed until Remove."""
    return _tab(open={"what": "remove", "team": team, "dest": dest})


@bp.route("/teams/<team>/<dest>/remove", methods=["POST"])
def dest_remove(team, dest):
    from modules.notify import teams

    actor, _v = _actor()
    try:
        teams.remove_destination(team, dest, by=actor)
    except _REFUSED as exc:
        return _tab(409, answer=_said(f"team:{team}", False, str(exc)))
    return _tab(answer=_said(f"team:{team}", True, "Removed: it receives nothing, and a "
                             "webhook's signing secret was erased with it. Its delivery log "
                             "rows stay in History"))


# ── Webhooks ────────────────────────────────────────────────────────────────────────────────

@bp.route("/webhooks/new", methods=["GET"])
def webhook_add_form():
    """Add a webhook…: its fields opened in the Webhooks card."""
    return _tab(open={"what": "webhook_new"})


@bp.route("/webhooks", methods=["POST"])
def webhook_add():
    """Add a webhook to a team and send it a code: its signing secret, typed by a person, goes
    to the credential store and is never drawn back."""
    from modules.notify import delivery, teams

    actor, _v = _actor()
    form = request.form
    kept = {"team": form.get("team") or "", "name": form.get("name") or "",
            "url": form.get("url") or ""}
    try:
        dest = teams.add_webhook(kept["team"], kept["url"], form.get("secret") or "", by=actor,
                                 fmt=form.get("format") or "generic", name=kept["name"])
    except _REFUSED as exc:
        return _tab(409, open=dict(kept, what="webhook_new"),
                    answer=_said("webhooks", False, str(exc)))
    dest_id = dest["destination"]
    try:
        got = delivery.send_code(kept["team"], dest_id, by=actor)
    except _REFUSED as exc:
        return _tab(409, answer=_said("webhooks", False, f"added, and no code sent: {exc}"))
    return _tab(answer=_said(f"dest:{dest_id}", got["outcome"] == "sent",
                             "Webhook added. " + _sent_words(got, "Its code")
                             + ("; read it where the webhook posts and type it in its team"
                                if got["outcome"] == "sent" else "")))


@bp.route("/teams/<team>/<dest>/edit", methods=["GET"])
def webhook_edit_form(team, dest):
    """Edit…: the webhook's name, URL and signing secret opened in its row."""
    return _tab(open={"what": "webhook_edit", "team": team, "dest": dest})


@bp.route("/teams/<team>/<dest>/edit/save", methods=["POST"])
def webhook_edit(team, dest):
    """Save an edit: a new URL is a new receiver, so it is verified again before use."""
    from modules.notify import teams

    actor, _v = _actor()
    form = request.form
    try:
        got = teams.edit_webhook(team, dest, by=actor, name=form.get("name"),
                                 url=form.get("url"), secret=form.get("secret") or None)
    except _REFUSED as exc:
        return _tab(409, open={"what": "webhook_edit", "team": team, "dest": dest},
                    answer=_said(f"dest:{dest}", False, str(exc)))
    words = ("Nothing changed" if not got["changed"] else
             "Saved: " + ", ".join(got["changed"])
             + (". Its URL changed, so it is off until a code sent to it is typed back"
                if got["unverified"] else ""))
    return _tab(answer=_said(f"dest:{dest}", True, words))
