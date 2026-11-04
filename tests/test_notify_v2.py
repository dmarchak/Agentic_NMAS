"""Settings › Installation › Notifications (board H, artboard B; part H9;
docs/HEAL_TO_INTENT.md section 10), through the real app, routes/notify_v2.py and
settings_v2.install_save, over modules/notify (H7). The relay's SMTP classes and the webhook's
POST are fakes handed in through the modules' attributes: no test touches a network. Secret
values here are placeholders made for the test.

- **The tab is drawn** with the board's three cards (Email relay, Webhooks, Teams) and every
  control on them; History's timeline listens for deliveries (C2384).
- **The relay:** Save writes what changed, recorded old and new, and refuses a host that is not
  one; an empty host is "off"; the password is stored, never drawn, with who and when; Test
  send to… sends through the relay as saved.
- **Teams:** an address added is unverified and off and gets its code; the code typed back
  verifies it and turns it on, a wrong one spends a try; Turn off; Remove… asks first.
- **Webhooks:** added with a secret never drawn and a URL drawn as its scheme and host; Test
  send; Edit… to a new URL is off again until verified; Remove erases its secret.
- **Told about** names the networks whose Self-healing tab chose the team.
"""

import re
import types

import pytest

from modules import credentials
from modules.notify import delivery, relay, teams, webhook
from tests.test_sdn_connections import make_networks

HX = {"HX-Request": "true"}
TAB = "/v2/settings/installation?tab=notifications"
BASE = "/v2/settings/installation/notify"
RELAY_PW = "Relay-Placeholder-Pw-H9-55"
HOOK_SECRET = "Hook-Signing-Placeholder-H9-0123456789"
HOOK_PATH = "/services/T0KEN-PLACEHOLDER-H9"


@pytest.fixture
def n(tmp_path, monkeypatch):
    """The store under *tmp_path*, the real app's client, a fake relay and a fake receiver."""
    import app as A

    make_networks(tmp_path, monkeypatch)
    e = types.SimpleNamespace(client=A.app.test_client(), mail=[], posts=[], status=[])

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, context=None):
            self.host = host

        def ehlo(self):
            pass

        def starttls(self, context=None):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            e.mail.append(msg)

        def quit(self):
            pass

    def fake_post(url, data=None, headers=None, timeout=None, allow_redirects=True):
        e.posts.append({"url": url, "data": data})
        return types.SimpleNamespace(status_code=e.status.pop(0) if e.status else 204)

    monkeypatch.setattr(relay, "SMTP", FakeSMTP)
    monkeypatch.setattr(relay, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(webhook, "POST", fake_post)
    monkeypatch.setattr(delivery, "SLEEP", lambda s: None)
    return e


def _get(n, path):
    r = n.client.get(path, headers=HX)
    return r, r.get_data(as_text=True)


def _post(n, path, data=None):
    r = n.client.post(path, data=data or {}, headers=HX)
    return r, r.get_data(as_text=True)


def _loaded(html):
    import html as h
    m = re.search(r"""<input type="hidden" name="loaded" value='([^']*)'>""", html)
    return h.unescape(m.group(1))


def _relay_on(n):
    from modules.settings_schema import write_settings
    assert write_settings({"notify_smtp_host": "smtp.example.com",
                           "notify_smtp_username": "mercury",
                           "notify_smtp_from": "mercury@example.com"}, actor="t")["ok"]
    credentials.set_notify_secret("relay", RELAY_PW)


def _code_in(msg) -> str:
    return re.search(r"verification code: (\d{6})", msg.get_content()).group(1)


def _team(name="Default on-call"):
    return teams.add_team(name, by="alex")["team"]


# ── The tab ───────────────────────────────────────────────────────────────────────────────

def test_the_tab_draws_the_boards_three_cards_and_their_controls(n):
    from modules import csp

    r = n.client.get(TAB)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
    assert 'aria-current="page">Notifications</a>' in html
    assert "Each network's Self-healing tab chooses which team it tells." in html
    body = html.split('id="notify-tab"', 1)[1]
    for words in ("Email relay", "Relay host", "Security", "STARTTLS (required)", "Username",
                  "Password", "From", "Replace…", "Test send to…", "Webhooks",
                  "Add a webhook…", "Teams", "Add a team…", "Delivery log (History › notification)",
                  "off: no relay"):
        assert words in body, words
    assert re.search(r'href="/v2/history\?kind=notifications["&]', body)
    # Pressed: Add a team…'s Add the team keeps the team, and the tab drawn again lists it.
    r, tab = _post(n, BASE + "/teams", {"name": "Default on-call"})
    assert r.status_code == 200
    assert [t["name"] for t in teams.read()["teams"].values()] == ["Default on-call"]
    assert "<h3 class=\"heal-h3\">Default on-call</h3>" in tab


def test_historys_timeline_listens_for_every_key_a_delivery_announces():
    """C2384: a delivery announces `notifications` (modules/notify/delivery.ANNOUNCE_KEYS,
    the notify announcer's keys); History draws the delivery log, so its timeline redraws on
    each, never only on the next page load."""
    import os

    from modules import invalidation
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "v2",
                        "_history_timeline.html")
    with open(path, encoding="utf-8") as fh:
        trigger = re.search(r'id="hist-timeline".*?hx-trigger="([^"]+)"', fh.read(), re.S).group(1)
    keys = set(invalidation.ANNOUNCERS["notify"]) | set(delivery.ANNOUNCE_KEYS)
    assert keys and "notifications" in keys
    for key in sorted(keys):
        assert f"nmas:{key} from:body" in trigger, key


# ── The relay ─────────────────────────────────────────────────────────────────────────────

def test_the_relay_saves_what_changed_and_refuses_a_host_that_is_not_one(n):
    from modules import installation_settings as I
    from modules.settings_schema import get_setting

    _r, card = _get(n, "/v2/settings/installation/card/relay")
    assert 'id="card-relay"' in card and "Relay host" in card
    loaded = _loaded(card)
    form = {"notify_smtp_host": "smtp.example.com", "notify_smtp_port": "587",
            "notify_smtp_tls": "starttls", "notify_smtp_username": "",
            "notify_smtp_from": "mercury@example.com", "notify_link_base": "", "loaded": loaded}
    r, html = _post(n, "/v2/settings/installation/card/relay/save", form)
    assert r.status_code == 200 and "Saved" in html and "Relay host empty → smtp.example.com" in html
    assert get_setting("notify_smtp_host") == "smtp.example.com"
    assert I.changes(kinds=("card_save",))["rows"][0]["card"] == "relay"
    r, html = _post(n, "/v2/settings/installation/card/relay/save",
                    dict(form, notify_smtp_host="not a host!", loaded=_loaded(html)))
    assert r.status_code == 409 and "Relay host" in html
    # An IPv6 relay is a relay, as an IPv4 one is.
    r, html = _post(n, "/v2/settings/installation/card/relay/save",
                    dict(form, notify_smtp_host="[2001:db8::25]", loaded=_loaded(html)))
    assert r.status_code == 200 and get_setting("notify_smtp_host") == "2001:db8::25"


def test_the_relays_password_is_stored_never_drawn_and_says_who_set_it(n):
    _r, card = _get(n, BASE + "/relay/password/form")
    assert 'type="password" name="password"' in card
    r, card = _post(n, BASE + "/relay/password", {"password": RELAY_PW})
    assert r.status_code == 200 and "Password replaced" in card
    assert RELAY_PW not in card and credentials.get_notify_secret("relay") == RELAY_PW
    _r, card = _get(n, "/v2/settings/installation/card/relay")
    assert "never shown" in card and "by test-person@example.invalid" in card
    assert RELAY_PW not in n.client.get(TAB).get_data(as_text=True)
    r, card = _post(n, BASE + "/relay/password", {"password": ""})
    assert r.status_code == 409 and credentials.get_notify_secret("relay") == RELAY_PW


def test_test_send_to_one_of_the_teams_addresses(n):
    _relay_on(n)
    team = _team()
    dest = teams.add_email(team, "noc@example.com", by="alex")["destination"]
    _r, card = _get(n, BASE + "/relay/test/form")
    assert f'value="{team}:{dest}"' in card and "noc@example.com" in card
    r, card = _post(n, BASE + "/relay/test", {"to": f"{team}:{dest}"})
    assert r.status_code == 200 and "Test sent" in card and len(n.mail) == 1
    assert "last sent" in card


# ── Teams ─────────────────────────────────────────────────────────────────────────────────

def test_an_address_is_verified_by_its_code_then_on(n):
    _relay_on(n)
    r, tab = _post(n, BASE + "/teams", {"name": "Default on-call"})
    assert r.status_code == 200 and "Team Default on-call added" in tab
    team = next(iter(teams.read()["teams"]))
    r, tab = _post(n, f"{BASE}/teams/{team}/email", {"address": "noc@example.com"})
    assert r.status_code == 200 and "Its code sent" in tab and "code sent" in tab
    code = _code_in(n.mail[-1])
    assert code not in tab
    dest = next(iter(teams.read()["teams"][team]["destinations"]))
    wrong = "000000" if code != "000000" else "111111"
    r, tab = _post(n, f"{BASE}/teams/{team}/{dest}/verify", {"code": wrong})
    assert r.status_code == 409 and "tries left" in tab
    r, tab = _post(n, f"{BASE}/teams/{team}/{dest}/verify", {"code": code})
    assert r.status_code == 200 and "Verified and on" in tab
    held = teams.read()["teams"][team]["destinations"][dest]
    assert held["enabled"] and held["verified_at"]
    r, tab = _post(n, f"{BASE}/teams/{team}/{dest}/enabled", {"on": ""})
    assert r.status_code == 200 and not teams.read()["teams"][team]["destinations"][dest]["enabled"]
    _r, tab = _get(n, f"{BASE}/teams/{team}/{dest}/remove/ask")
    assert "Remove noc@example.com?" in tab and dest in teams.read()["teams"][team]["destinations"]
    r, tab = _post(n, f"{BASE}/teams/{team}/{dest}/remove")
    assert r.status_code == 200 and not teams.read()["teams"][team]["destinations"]


def test_a_bad_address_is_refused_naming_it(n):
    team = _team()
    r, tab = _post(n, f"{BASE}/teams/{team}/email", {"address": "not an address"})
    assert r.status_code == 409 and "is not one email address" in tab
    assert teams.read()["teams"][team]["destinations"] == {}           # nothing was added


# ── Webhooks ──────────────────────────────────────────────────────────────────────────────

def test_a_webhook_keeps_its_secret_and_path_out_of_the_page(n):
    team = _team()
    url = "https://hooks.example.com" + HOOK_PATH
    r, tab = _post(n, BASE + "/webhooks", {"team": team, "name": "on-call chat", "url": url,
                                           "format": "generic", "secret": HOOK_SECRET})
    assert r.status_code == 200 and "Webhook added" in tab and len(n.posts) == 1
    assert HOOK_SECRET not in tab and HOOK_PATH not in tab
    assert "https://hooks.example.com/…" in tab and "on-call chat" in tab
    dest = next(iter(teams.read()["teams"][team]["destinations"]))
    n.status.append(503)
    r, tab = _post(n, f"{BASE}/teams/{team}/{dest}/test")
    assert r.status_code == 200 and "A test not sent (failed)" in tab and "HTTP 503" in tab
    # Verify it with the code the receiver was posted, then move it to a new URL: off again.
    import json as _json
    code = re.search(r"verification code: (\d{6})",
                     _json.loads(n.posts[0]["data"])["outcome"]).group(1)
    teams.confirm_code(team, dest, code, by="alex")
    teams.set_enabled(team, dest, True, by="alex")
    _r, form = _get(n, f"{BASE}/teams/{team}/{dest}/edit")
    assert "Signing secret" in form and HOOK_SECRET not in form
    r, tab = _post(n, f"{BASE}/teams/{team}/{dest}/edit/save",
                   {"name": "on-call chat", "url": "https://[2001:db8::40]/hooks/h9",
                    "secret": ""})
    assert r.status_code == 200 and "Its URL changed, so it is off" in tab
    held = teams.read()["teams"][team]["destinations"][dest]
    assert not held["enabled"] and not held["verified_at"]
    assert "https://[2001:db8::40]/…" in tab
    r, tab = _post(n, f"{BASE}/teams/{team}/{dest}/remove")
    assert r.status_code == 200 and not credentials.notify_secret_set(f"webhook/{dest}")


def test_a_format_not_built_is_refused_and_drawn_later(n):
    team = _team()
    _r, tab = _get(n, BASE + "/webhooks/new")
    assert '<option value="slack" disabled>Slack-compatible (later)</option>' in tab
    r, tab = _post(n, BASE + "/webhooks", {"team": team, "url": "https://hooks.example.com/x",
                                           "format": "slack", "secret": HOOK_SECRET})
    assert r.status_code == 409 and "C2387" in tab
    # Nothing was added, and nothing was posted to it.
    assert teams.read()["teams"][team]["destinations"] == {} and not n.posts


def test_told_about_names_the_networks_that_chose_the_team(n):
    """Branch's Self-healing tab chooses the team (Who is told's Save, pressed), and the team's
    Told about names Branch."""
    from modules import heal_notify
    team = _team()
    _r, tab = _get(n, "/v2/settings/network/Branch/heal/tab")
    loaded = _loaded(tab)
    r, _tab = _post(n, "/v2/settings/network/Branch/heal/notify",
                    {"team": team, "events": ["cant_fix"], "loaded": loaded})
    assert r.status_code == 200 and heal_notify.teams_for("Branch", "cant_fix") == [team]
    html = n.client.get(TAB).get_data(as_text=True)
    assert 'href="/v2/settings/network/Branch?tab=heal">Branch</a>' in html


# ── The secrets typed here, never drawn, recorded or logged (C2407's hand check) ──────────────

NEW_SECRET = "Hook-Signing-Placeholder-H9-new-9876543210"


class _Lines:
    """The module's own log, read past the masking net: a handler put on the logger's list
    directly, so `Logger.addHandler`'s masking filter is not on it (C235's lesson: the net masks
    a value once it is stored, so a test reading through it saw a logged secret masked)."""

    def __init__(self, name):
        import logging
        self.lines, self.logger = [], logging.getLogger(name)
        lines = self.lines
        self.handler = type("H", (logging.Handler,), {
            "emit": lambda s, rec: lines.append(rec.getMessage())})()
        self.level = self.logger.level

    def __enter__(self):
        import logging
        self.logger.handlers.append(self.handler)
        self.logger.setLevel(logging.DEBUG)
        return self.lines

    def __exit__(self, *exc):
        self.logger.handlers.remove(self.handler)
        self.logger.setLevel(self.level)


def _record_text():
    from modules import installation_settings as I
    import os
    path = I._path(I.RECORD)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def _webhook(n, team):
    url = "https://hooks.example.com" + HOOK_PATH
    r, _tab = _post(n, BASE + "/webhooks", {"team": team, "name": "on-call chat", "url": url,
                                            "format": "generic", "secret": HOOK_SECRET})
    assert r.status_code == 200
    return next(iter(teams.read()["teams"][team]["destinations"]))


def test_a_refused_relay_password_is_never_drawn_back(n):
    """M1, M2: a password the store refuses (two lines) answers 409 in the card with its field
    open again, neither the field nor the refusal carries what was typed, and the stored
    password is the one held before."""
    credentials.set_notify_secret("relay", RELAY_PW)
    typed = "Refused-Placeholder-Relay-Pw\nsecond-line"
    r, card = _post(n, BASE + "/relay/password", {"password": typed})
    assert r.status_code == 409 and 'name="password"' in card
    assert "Refused-Placeholder-Relay-Pw" not in card and "second-line" not in card
    assert credentials.get_notify_secret("relay") == RELAY_PW


def test_the_relay_password_is_in_no_record_history_draws(n):
    """M3, M16a: the installation record (History's installation source) names the field
    replaced, never its value."""
    r, _card = _post(n, BASE + "/relay/password", {"password": RELAY_PW})
    assert r.status_code == 200
    text = _record_text()
    assert '"relay password"' in text and RELAY_PW not in text


def test_a_refused_webhook_add_or_edit_never_draws_the_secret_back(n):
    """M6, M7: a refused add and a refused edit each answer 409 with the form open, and neither
    page carries the typed secret."""
    team = _team()
    r, tab = _post(n, BASE + "/webhooks", {"team": team, "name": "x", "secret": HOOK_SECRET,
                                           "url": "http://hooks.example.com/x"})
    assert r.status_code == 409 and HOOK_SECRET not in tab
    dest = _webhook(n, team)
    r, tab = _post(n, f"{BASE}/teams/{team}/{dest}/edit/save",
                   {"name": "x", "url": "http://hooks.example.com/x", "secret": NEW_SECRET})
    assert r.status_code == 409 and NEW_SECRET not in tab


def test_an_edits_new_secret_is_checked_stored_and_kept_out_of_the_record(n):
    """M8, M10, M16c: a short secret is refused and the stored one kept; a good one replaces it
    in the credential store, and the teams' record holds its reference, never the value."""
    team = _team()
    dest = _webhook(n, team)
    r, _tab = _post(n, f"{BASE}/teams/{team}/{dest}/edit/save",
                    {"name": "on-call chat", "secret": "fifteen-chars!!"})
    assert r.status_code == 409 and credentials.get_notify_secret(f"webhook/{dest}") == HOOK_SECRET
    r, tab = _post(n, f"{BASE}/teams/{team}/{dest}/edit/save",
                   {"name": "on-call chat", "secret": NEW_SECRET})
    assert r.status_code == 200 and "Saved: secret" in tab
    assert credentials.get_notify_secret(f"webhook/{dest}") == NEW_SECRET
    import json as _json
    held = _json.dumps(teams.read())
    assert NEW_SECRET not in held and HOOK_SECRET not in held


def test_a_refused_edit_keeps_the_stored_secret(n):
    """M11: an edit the store refuses (a second webhook moved onto the first's URL, which the
    team already has) changes no secret."""
    team = _team()
    first = _webhook(n, team)
    r, _tab = _post(n, BASE + "/webhooks", {"team": team, "name": "second", "format": "generic",
                                            "url": "https://hooks.example.com/second",
                                            "secret": HOOK_SECRET})
    assert r.status_code == 200
    second = next(d for d in teams.read()["teams"][team]["destinations"] if d != first)
    r, _tab = _post(n, f"{BASE}/teams/{team}/{second}/edit/save",
                    {"name": "second", "url": "https://hooks.example.com" + HOOK_PATH,
                     "secret": NEW_SECRET})
    assert r.status_code == 409
    assert credentials.get_notify_secret(f"webhook/{second}") == HOOK_SECRET


def test_a_new_url_drops_the_code_issued_for_the_old_one(n):
    """M13: a code sent to the old receiver does not verify the new one."""
    team = _team()
    dest = _webhook(n, team)
    assert teams.read()["teams"][team]["destinations"][dest].get("code")
    r, _tab = _post(n, f"{BASE}/teams/{team}/{dest}/edit/save",
                    {"name": "on-call chat", "url": "https://hooks.example.com/moved",
                     "secret": ""})
    assert r.status_code == 200
    assert "code" not in teams.read()["teams"][team]["destinations"][dest]


def test_no_secret_reaches_the_teams_log_on_an_add_or_an_edit(n):
    """M14, M15: the add's and the edit's log lines name the destination and what changed,
    read from the module's own log past the masking net."""
    team = _team()
    with _Lines("modules.notify.teams") as lines:
        dest = _webhook(n, team)
        _post(n, f"{BASE}/teams/{team}/{dest}/edit/save",
              {"name": "on-call chat", "secret": NEW_SECRET})
    text = "\n".join(lines)
    assert f"destination {dest} added" in text and f"webhook {dest} in team" in text
    assert HOOK_SECRET not in text and NEW_SECRET not in text
