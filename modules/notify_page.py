"""Settings › Installation › Notifications' model (board H, artboard B; H9;
docs/HEAL_TO_INTENT.md section 10): what `templates/v2/_notify.html` draws, read from
`modules/notify` (the teams store, the delivery log, the relay's settings) and
`modules/heal_notify.py` (which networks tell each team). Reads only, and never a secret's
value: a password or a signing secret is drawn as set or not, a webhook's URL as its scheme and
host (its path may be a receiver's token), a code never.
"""

import logging
import time
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

#: Every webhook format the board names, in its order, and whether it is built (the rest are
#: deferred to after Lab 10, not cut: C2387).
FORMAT_WORDS = (("generic", "Generic, signed"), ("slack", "Slack-compatible"),
                ("teams", "Teams-compatible"), ("pagerduty", "PagerDuty Events v2"))
#: The relay's Security choices, as the card says them.
TLS_WORDS = {"starttls": "STARTTLS (required)", "implicit": "TLS from the start",
             "none": "None (only to a relay on this host)"}
#: The record kind a relay password's Replace keeps, in the installation's settings record.
PASSWORD_KIND = "card_replace"
RELAY_CARD = "relay"


def hhmm(iso: str) -> str:
    """``2026-11-03T18:31:05Z`` as ``18:31``; anything else as it is."""
    try:
        return time.strftime("%H:%M", time.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return str(iso or "")


def day(iso: str) -> str:
    """``2026-11-03T18:31:05Z`` as ``3 Nov``."""
    try:
        t = time.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return str(iso or "")
    return f"{t.tm_mday} {time.strftime('%b', t)}"


def url_shown(url: str) -> str:
    """A webhook's URL as a page may draw it: its scheme and host, then ``/…`` when it has a
    path (never the path: a receiver's token may be in it)."""
    from modules.notify import addresses

    try:
        parts = urlsplit(url or "")
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return "(not a URL)"
    host = addresses.url_host(url)
    if not parts.scheme or not host:
        return "(not a URL)"
    return f"{parts.scheme}://{host}{port}" + ("/…" if parts.path.strip("/") or parts.query
                                               else "")


def _state(dest: dict) -> tuple:
    """A destination's chip: (words, colour)."""
    if dest.get("verified_at"):
        if dest.get("enabled"):
            return (f"verified {day(dest['verified_at'])}", "ok")
        return (f"verified {day(dest['verified_at'])}, off", "muted")
    if dest.get("code_waiting"):
        return (f"code sent {hhmm((dest.get('code_at') or ''))}".strip(), "warn")
    return ("not verified", "warn")


def _last(dest: dict) -> dict:
    last = dest.get("last") or {}
    outcome = last.get("outcome", "")
    if not outcome:
        return {"words": "nothing sent yet", "kind": "muted", "error": ""}
    words = {"sent": "delivered", "failed": "failed", "refused": "refused"}.get(outcome, outcome)
    return {"words": f"{words} {hhmm(last.get('at'))}", "error": last.get("error", ""),
            "kind": "ok" if outcome == "sent" else "danger"}


def _dest(team_id: str, dest_id: str, dest: dict, team_name: str) -> dict:
    """One destination as the tab draws it, and nothing more: never its code's hash or its
    secret's reference (`teams.public`), never a webhook's path."""
    from modules.notify import addresses, teams

    pub = teams.public(dest)
    pub["code_at"] = ((dest.get("code") or {}).get("at") or "")
    out = {"id": dest_id, "team": team_id, "team_name": team_name,
           "channel": pub.get("channel", ""), "verified_at": pub.get("verified_at") or "",
           "enabled": bool(pub.get("enabled")), "code_waiting": pub["code_waiting"],
           "last_words": _last(dest), "chip": _state(pub)}
    if out["channel"] == "email":
        out["label"] = pub.get("address", "")
    else:
        out.update(name=pub.get("name", ""), secret_set=bool(pub.get("secret_set")),
                   label=pub.get("name") or addresses.url_host(pub.get("url", "")) or "webhook",
                   url_shown=url_shown(pub.get("url", "")),
                   format_words=dict(FORMAT_WORDS).get(pub.get("format", ""),
                                                       pub.get("format")))
    return out


def relay_card() -> dict:
    """The relay card's fields as `installation_settings.card("relay")` holds them, what its
    form drew (``loaded``, R17), its title and note."""
    from modules import installation_settings as I

    c = I.card(RELAY_CARD)
    return {"name": c["name"], "fields": c["fields"], "loaded": c["loaded"],
            "title": c["spec"]["title"], "note": c["spec"]["note"]}


def relay_view(emails: list = None) -> dict:
    """What the relay card draws: its card, its head and password, the addresses a test may
    go to, and the Security choices' words."""
    from modules.notify import delivery

    if emails is None:
        emails = [d for d in view_teams()[0] if d["channel"] == "email"]
    return {"card": relay_card(), "relay": _relay(delivery.read_log()["rows"]),
            "emails": [{"to": f"{d['team']}:{d['id']}", "label": d["label"],
                        "team_name": d["team_name"]} for d in emails],
            "tls_words": TLS_WORDS}


def view_teams() -> tuple:
    """``(destinations, team rows, store)``: every destination, each team with its own."""
    from modules import heal_notify
    from modules.notify import teams

    store = teams.read()
    every, team_rows = [], []
    for team_id, team in sorted(store["teams"].items(),
                                key=lambda kv: (kv[1].get("name") or "").lower()):
        name = team.get("name", "")
        dests = [_dest(team_id, d_id, d, name) for d_id, d in
                 sorted((team.get("destinations") or {}).items(),
                        key=lambda kv: (kv[1].get("channel", ""), kv[1].get("added_at", "")))]
        every += dests
        team_rows.append({"id": team_id, "name": name, "dests": dests,
                          "told_about": heal_notify.told_about(team_id)})
    return every, team_rows, store


def _relay(store_rows: list) -> dict:
    """The relay card's head chip and its password's provenance."""
    from modules import credentials
    from modules import installation_settings as I
    from modules.notify import relay
    from modules.settings_schema import get_setting

    host = (get_setting("notify_smtp_host", "") or "").strip()
    try:
        relay.config()
        problem = ""
    except relay.NotConfigured as exc:
        problem = str(exc)
    mails = [r for r in store_rows if r.get("channel") == "email" and r.get("final", True)]
    newest = mails[0] if mails else None
    if not host:
        chip = ("off: no relay", "muted")
    elif newest is None:
        chip = ("nothing sent yet", "muted")
    elif newest.get("outcome") == "sent":
        chip = (f"last sent {hhmm(newest.get('at'))} UTC", "ok")
    else:
        chip = (f"last {newest.get('outcome')} {hhmm(newest.get('at'))} UTC", "danger")
    got = I.changes(kinds=(PASSWORD_KIND,))
    rows = [r for r in got.get("rows") or [] if r.get("card") == RELAY_CARD]
    set_by = rows[0] if rows else None
    return {"chip": chip, "problem": problem, "host": host,
            "password_set": credentials.notify_secret_set("relay"),
            "password_by": ({"day": day(set_by.get("at_iso")),
                             "who": set_by.get("actor_label") or set_by.get("actor", "")}
                            if set_by else None),
            "record_state": got["state"]}


def view() -> dict:
    """Everything the tab draws."""
    from modules.notify import delivery, teams

    every, team_rows, store = view_teams()
    deliveries = delivery.read_log()
    return {"teams": team_rows, "webhooks": [d for d in every if d["channel"] == "webhook"],
            "state": store["state"], "error": store["error"],
            "log_state": deliveries["state"], "log_error": deliveries.get("error", ""),
            "rl": relay_view([d for d in every if d["channel"] == "email"]),
            "formats": FORMAT_WORDS, "built_formats": teams.FORMATS,
            "code_minutes": teams.CODE_TTL_S // 60, "secret_min": teams.SECRET_MIN}
