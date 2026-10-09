"""Settings › Installation (board F) and its Records database card (board F2, approved
2026-10-09 with the operator's three conditions), through the real app, routes and templates on
a temporary store.

- Condition 1: Save and Test answer with the database down or the password wrong; Save never
  opens the database and is recorded in the installation's settings record, a file, as the
  person.
- Condition 2: Test checks what host step 6a made, six checks, and names the one that failed;
  the rest are "not tried". Against a real PostgreSQL 18 (tests/pg_instance.py): all six pass,
  then a wrong password fails the first.
- Condition 3: Replace… states the rotation order (the server first, postgres-rotate.sh) and
  tests at once; the password is never drawn back or recorded.
- The page: under the strict policy, the scope bar's Installation current, the unbuilt tabs and
  cards linked to today's page and saying so.
"""

import json
import re

import pytest

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

PW = "a-new-records-password-0123456789"


def _get(n, path):
    r = n["client"].get(path)
    return r, r.get_data(as_text=True)


def _post(n, path, data=None):
    r = n["client"].post(path, data=data or {}, headers={"HX-Request": "true"})
    return r, r.get_data(as_text=True)


def _card(html):
    m = re.search(r'<section class="card set-card[^"]*" id="records-db".*?</section>', html, re.S)
    assert m, "no records database card"
    return re.sub(r"\s+", " ", m.group(0))


def _no_db(monkeypatch):
    """Any attempt to open the database fails the test: Save must never try."""
    from modules import records_db

    def refuse(*a, **k):
        raise AssertionError("Save opened the database")
    monkeypatch.setattr(records_db, "connect", refuse)


def _record(n):
    p = n["dir"] / "settings_record.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


class TestThePage:
    def test_it_draws_under_the_strict_policy_with_installation_current(self, networks):
        from modules import csp

        r, html = _get(networks, "/v2/settings/installation")
        assert r.status_code == 200 and "<h1>Settings · Installation" in html
        assert r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert re.search(r'<a class="scope-item on" href="/v2/settings/installation" '
                         r'aria-current="page"><b>Installation</b>', html)
        assert "These settings apply to every network" in html

    def test_unbuilt_tabs_say_so_and_link_to_today_s_page(self, networks):
        for key in ("access", "platforms", "ai", "diagnostics"):
            _r, tab = _get(networks, f"/v2/settings/installation?tab={key}")
            assert 'data-todays-page="installation_settings"' in tab and "until it is drawn here" in tab
            assert 'id="records-db"' not in tab

    def test_a_network_s_page_links_installation_here_now(self, networks):
        _r, html = _get(networks, "/v2/settings/network/Branch")
        assert '<a class="scope-item" href="/v2/settings/installation">' in html


class TestOffAndSave:
    def test_off_says_every_store_is_on_its_files(self, networks):
        card = _card(_get(networks, "/v2/settings/installation")[1])
        assert "off: every store on its files" in card and "none yet: every store on its files" in card
        assert "Test needs a host and a password." in card

    def test_save_works_with_the_database_down_and_is_recorded_as_the_person(self, networks,
                                                                             monkeypatch):
        _no_db(monkeypatch)
        r, html = _post(networks, "/v2/settings/installation/records/save",
                        {"records_db_host": "127.0.0.1", "records_db_port": "5433",
                         "records_db_name": "mercury", "records_db_user": "mercury"})
        card = _card(html)
        assert r.status_code == 200 and "Saved</strong> by" in card
        assert "recorded in the installation's settings record, a file" in card.lower()
        from modules.settings_schema import get_setting
        assert get_setting("records_db_host") == "127.0.0.1"
        (row,) = _record(networks)
        assert row["kind"] == "records_db_save" and row["fields"] == ["records_db_host"]
        assert row["actor"] and row["scope"] == "installation" and "127.0.0.1" not in json.dumps(row)
        assert "not tested yet" in card

    def test_saving_what_is_stored_changes_nothing(self, networks):
        _r, html = _post(networks, "/v2/settings/installation/records/save",
                         {"records_db_host": "", "records_db_port": "5433",
                          "records_db_name": "mercury", "records_db_user": "mercury"})
        assert "Nothing changed" in _card(html) and _record(networks) == []

    @pytest.mark.parametrize("field, value, words", [
        ("records_db_port", "70000", "is not a port number"),
        ("records_db_host", "db;rm", "is not a host name or address"),
        ("records_db_name", "", "Database is empty"),
        ("records_db_user", "x y", "is not a PostgreSQL name")])
    def test_a_bad_field_is_refused_naming_it_and_nothing_is_saved(self, networks, field,
                                                                   value, words):
        data = {"records_db_host": "127.0.0.1", "records_db_port": "5433",
                "records_db_name": "mercury", "records_db_user": "mercury", field: value}
        r, html = _post(networks, "/v2/settings/installation/records/save", data)
        assert r.status_code == 409 and words in _card(html) and "Nothing was changed" in html
        assert _record(networks) == []


class TestReplace:
    def test_the_form_states_the_rotation_order_first(self, networks):
        _r, html = _get(networks, "/v2/settings/installation/records/replace")
        text = re.sub(r"\s+", " ", html)
        assert text.index("On the server first:") < text.index("Then here:")
        assert "scripts/host-steps/postgres-rotate.sh" in text and "Replace and Test" in text

    def test_a_password_the_server_could_not_have_is_refused(self, networks):
        r, html = _post(networks, "/v2/settings/installation/records/replace",
                        {"records_db_password": "short"})
        assert r.status_code == 409 and "24 characters or more" in html
        assert "The password Mercury holds is unchanged" in html and _record(networks) == []

    def test_replace_stores_records_without_the_value_and_tests_at_once(self, networks,
                                                                       monkeypatch):
        from modules import records_db
        from modules.secrets_store import get_secret

        monkeypatch.setattr(records_db, "test_connection", lambda: {
            "ok": False, "steps": [{"name": "connect", "ok": False, "detail": "no host"}],
            "error": "connect: no host"})
        r, html = _post(networks, "/v2/settings/installation/records/replace",
                        {"records_db_password": PW})
        assert r.status_code == 200 and "Password replaced</strong> by" in html
        assert get_secret("records_db_password") == PW and PW not in html
        (row,) = _record(networks)
        assert row["kind"] == "records_db_replace" and PW not in json.dumps(row)
        assert "Test failed" in html and "connect: no host" in html


@pytest.fixture(scope="module")
def pg():
    from tests import pg_instance

    inst = pg_instance.start()
    yield inst
    inst.stop()


class TestAgainstARealPostgreSQL:
    """Condition 2 end to end: Save, Replace (which tests), then a wrong password."""

    def test_six_checks_pass_then_a_wrong_password_names_the_first(self, networks, pg):
        from tests import pg_instance

        _post(networks, "/v2/settings/installation/records/save",
              {"records_db_host": "127.0.0.1", "records_db_port": str(pg.port),
               "records_db_name": "mercury", "records_db_user": "mercury"})
        _r, html = _post(networks, "/v2/settings/installation/records/replace",
                         {"records_db_password": pg_instance.MERCURY_PW})
        card = _card(html)
        assert "Test passed" in card and "answering" in card and "PostgreSQL 18." in card
        assert card.count(">pass<") == 6 and "FAILS" not in card
        # The answer is kept: the page drawn again shows it, by whom and when.
        page = _card(_get(networks, "/v2/settings/installation")[1])
        assert "answering" in page and "tested" in page and page.count(">pass<") == 6
        # The server first, Mercury not yet: the password Mercury holds no longer works.
        from modules.secrets_store import set_secret
        set_secret("records_db_password", "wrong-" + pg_instance.MERCURY_PW)
        _r, html = _post(networks, "/v2/settings/installation/records/test")
        card = _card(html)
        assert "not answering" in card and card.count(">FAILS<") == 1
        assert card.count(">not tried<") == 5 and "password authentication failed" in card
        assert "wrong-" not in card

    def test_save_with_nothing_listening_still_saves_and_test_says_so(self, networks, pg):
        from tests import pg_instance

        _r, html = _post(networks, "/v2/settings/installation/records/save",
                         {"records_db_host": "127.0.0.1",
                          "records_db_port": str(pg_instance._free_port()),
                          "records_db_name": "mercury", "records_db_user": "mercury"})
        assert "Saved</strong> by" in _card(html)
        from modules.secrets_store import set_secret
        set_secret("records_db_password", pg_instance.MERCURY_PW)
        _r, html = _post(networks, "/v2/settings/installation/records/test")
        assert "did not accept the connection" in _card(html)


# ── C617: no product text sends a person to today's Settings > Integrations ────────────────

TODAYS_SETTINGS = re.compile(r"Settings\s*(?:>|→|›)\s*Integrations")


def _strings_naming_todays_settings(paths):
    """Every string constant in *paths* (parsed, never grepped) naming today's Settings >
    Integrations, as (file, text). Docstrings are not screen text and are left out."""
    import ast
    out = []
    for p in paths:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        docs = {id(n.body[0].value) for n in ast.walk(tree)
                if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                  ast.AsyncFunctionDef))
                and n.body and isinstance(n.body[0], ast.Expr)
                and isinstance(n.body[0].value, ast.Constant)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docs and TODAYS_SETTINGS.search(node.value):
                out.append((str(p), node.value))
    return out


class TestNoTextSendsAPersonToTodaysSettings:
    """C617 (2026-10-09): nine texts sent a person to today's Settings > Integrations for
    NetBox, Proxmox and Grafana; each now names its v2 place (installation_settings.
    settings_place). The class is held, not the nine: no string in modules/ or routes/ says it.
    Today's own templates and scripts are not scanned: they leave at cutover."""

    def test_none_in_modules_or_routes(self):
        from pathlib import Path
        from tests import source_index
        paths = [Path(p) for p in source_index.tracked("modules", suffix=".py")
                 + source_index.tracked("routes", suffix=".py", recursive=False)]
        assert len(paths) >= 200, "the population shrank"
        assert _strings_naming_todays_settings(paths) == []

    def test_the_scan_finds_a_planted_one(self, tmp_path):
        planted = tmp_path / "x.py"
        planted.write_text('"""Settings > Integrations in a docstring."""\n'
                           'A = "put it in Settings → Integrations"\nB = "Settings › Default"\n'
                           'C = "check Settings › Integrations › Grafana"\n')
        found = [t for _f, t in _strings_naming_todays_settings([planted])]
        assert found == ["put it in Settings → Integrations",
                         "check Settings › Integrations › Grafana"], "a docstring is not screen text"


# ── Board F3 (signed off 2026-10-09): the other cards, every setting a control ─────────────


def _kcard(html, name):
    m = re.search(rf'<section class="card set-card[^"]*" id="card-{name}".*?</section>', html,
                  re.S)
    assert m, f"no {name} card"
    import html as html_mod
    return html_mod.unescape(re.sub(r"\s+", " ", m.group(0)))


class _Client:
    """A stand-in integration client: its test_connection's answer, and how often asked."""

    def __init__(self, answer):
        self.answer, self.asked = answer, 0

    def test_connection(self):
        self.asked += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _fake_integration(monkeypatch, answer):
    from modules import integrations

    c = _Client(answer)
    monkeypatch.setattr(integrations, "get_integration", lambda name: c)
    return c


class TestTheCards:
    def test_every_card_is_on_its_tab_and_nothing_links_to_today_s_page(self, networks):
        def body(html):
            m = re.search(r'<div class="tab-body" id="tab-body">(.*)', html, re.S)
            assert m, "no tab body"
            return m.group(1)

        _r, conn = _get(networks, "/v2/settings/installation")
        for name in ("netbox", "proxmox", "author"):
            _kcard(conn, name)
        assert 'id="records-db"' in conn and 'id="card-server"' not in conn
        assert 'data-todays-page' not in body(conn) and "today's" not in body(conn)
        _r, server = _get(networks, "/v2/settings/installation?tab=server")
        card = _kcard(server, "server")
        assert 'name="flask_host"' in card and 'name="flask_port"' in card
        assert "tftp" not in card.lower(), "the TFTP root retired (C616), not drawn"
        assert 'data-todays-page' not in body(server)

    def test_each_field_is_a_control_and_a_token_is_never_drawn(self, networks):
        from modules.secrets_store import set_secret
        set_secret("netbox_token", "nb-token-SECRET-123456")
        set_secret("proxmox_token_secret", "px-secret-SECRET-654321")
        _r, html = _get(networks, "/v2/settings/installation")
        nb, px = _kcard(html, "netbox"), _kcard(html, "proxmox")
        for key in ("netbox_url", "netbox_auth_scheme", "netbox_verify_tls"):
            assert f'name="{key}"' in nb
        for key in ("proxmox_url", "proxmox_node", "proxmox_token_expires",
                    "proxmox_verify_tls", "proxmox_backup_vmids", "proxmox_backup_storage"):
            assert f'name="{key}"' in px
        assert "SECRET" not in html and "Replace…" in nb and "Replace…" in px
        assert '<option selected>Bearer</option>' in nb
        # Board F3's order: the token after NetBox's URL and after Proxmox's node.
        assert nb.index('name="netbox_url"') < nb.index("API token") \
            < nb.index('name="netbox_auth_scheme"')
        assert px.index('name="proxmox_node"') < px.index("Replace…") \
            < px.index('name="proxmox_token_expires"')

    def test_save_writes_what_changed_records_names_never_values(self, networks):
        from modules import installation_settings as I
        from modules.settings_schema import get_setting
        _r, html = _post(networks, "/v2/settings/installation/card/netbox/save",
                         {"netbox_url": "https://192.0.2.30", "netbox_auth_scheme": "Token"})
        card = _kcard(html, "netbox")
        assert "Saved" in card and "netbox_auth_scheme" in card
        assert get_setting("netbox_url") == "https://192.0.2.30"
        assert get_setting("netbox_auth_scheme") == "Token"
        assert get_setting("netbox_verify_tls") is False, "a switch not sent is off"
        rec = I.changes(kinds=("card_save",))["rows"][0]
        assert rec["card"] == "netbox" and "netbox_url" in rec["fields"]
        assert "192.0.2.30" not in json.dumps(rec), "names, never values"
        _r, again = _post(networks, "/v2/settings/installation/card/netbox/save",
                          {"netbox_url": "https://192.0.2.30", "netbox_auth_scheme": "Token"})
        assert "Nothing changed" in _kcard(again, "netbox")

    def test_a_field_that_is_not_its_kind_is_refused_naming_it(self, networks):
        from modules.settings_schema import get_setting
        before = get_setting("proxmox_backup_vmids")
        for data, words in (({"proxmox_url": "ftp://x", "proxmox_backup_vmids": "100"},
                             "URL 'ftp://x' is not an http:// or https:// address"),
                            ({"proxmox_url": "", "proxmox_backup_vmids": "100,abc"},
                             "Backup VMs '100,abc' is not VM ids"),
                            ({"proxmox_url": "", "proxmox_token_expires": "2027-02-30"},
                             "Token expires '2027-02-30' is not a date")):
            r, html = _post(networks, "/v2/settings/installation/card/proxmox/save", data)
            assert r.status_code == 409 and words in _kcard(html, "proxmox"), words
        assert get_setting("proxmox_backup_vmids") == before

    def test_the_server_s_bind_and_port_wait_for_a_restart_and_say_so(self, networks):
        from modules.settings_schema import get_setting
        _r, html = _post(networks, "/v2/settings/installation/card/server/save",
                         {"flask_host": "127.0.0.1", "flask_port": "5001"})
        card = _kcard(html, "server")
        assert "take effect at the next restart" in card and get_setting("flask_port") == 5001
        r, html = _post(networks, "/v2/settings/installation/card/server/save",
                        {"flask_host": "127.0.0.1", "flask_port": "70000"})
        assert r.status_code == 409 and "is not a port number" in html

    def test_test_asks_now_and_draws_the_answer_or_the_service_s_words(self, networks,
                                                                        monkeypatch):
        c = _fake_integration(monkeypatch, {"ok": True, "message": "NetBox 4.1.2"})
        _r, html = _post(networks, "/v2/settings/installation/card/netbox/test")
        assert c.asked == 1 and "Test passed" in html and "NetBox 4.1.2" in html
        _fake_integration(monkeypatch, {"ok": False, "error": "401: Invalid token"})
        _r, html = _post(networks, "/v2/settings/installation/card/netbox/test")
        assert "Test failed" in html and "401: Invalid token" in html
        _fake_integration(monkeypatch, RuntimeError("boom"))
        _r, html = _post(networks, "/v2/settings/installation/card/proxmox/test")
        assert "the test raised RuntimeError: boom" in html
        r, _html = _post(networks, "/v2/settings/installation/card/author/test")
        assert r.status_code == 409, "a card with no service has no Test"

    def test_replace_stores_records_and_tests_never_drawing_the_token(self, networks,
                                                                       monkeypatch):
        from modules import installation_settings as I
        from modules.secrets_store import get_secret
        from modules.settings_schema import get_setting
        c = _fake_integration(monkeypatch, {"ok": True, "message": "Proxmox VE 8.2"})
        _r, form = _get(networks, "/v2/settings/installation/card/proxmox/replace")
        assert 'name="proxmox_token_id"' in form and 'name="proxmox_token_secret"' in form
        _r, html = _post(networks, "/v2/settings/installation/card/proxmox/replace",
                         {"proxmox_token_id": "nmas@pve!backup",
                          "proxmox_token_secret": "uuid-SECRET-0000"})
        assert "Token secret replaced" in html and "Test passed" in html and c.asked == 1
        assert "uuid-SECRET-0000" not in html
        assert get_secret("proxmox_token_secret") == "uuid-SECRET-0000"
        assert get_setting("proxmox_token_id") == "nmas@pve!backup"
        rec = I.changes(kinds=("card_replace",))["rows"][0]
        assert rec["fields"] == ["proxmox_token_id", "proxmox_token_secret"]
        assert "uuid-SECRET" not in json.dumps(rec)
        r, html = _post(networks, "/v2/settings/installation/card/proxmox/replace",
                        {"proxmox_token_id": "nobody", "proxmox_token_secret": "x"})
        assert r.status_code == 409 and "is not a Proxmox token id" in html
        assert get_secret("proxmox_token_secret") == "uuid-SECRET-0000", "nothing replaced"

    def test_turn_off_writes_it_off_records_who_and_never_turns_it_on(self, networks):
        from modules import installation_settings as I
        from modules.settings_schema import get_setting, write_settings
        write_settings({"netbox_allow_writes": True}, actor="test")
        _r, html = _get(networks, "/v2/settings/installation")
        nb = _kcard(html, "netbox")
        assert "Turn off" in nb
        assert "turned on by confirming an authorised NetBox write, never from this card" in nb
        _r, html = _post(networks, "/v2/settings/installation/netbox/writes-off")
        nb = _kcard(html, "netbox")
        assert get_setting("netbox_allow_writes") is False
        assert "NetBox writes turned off" in nb and "Turn off</span>" not in nb
        assert I.changes(kinds=("netbox_writes_off",))["rows"][0]["fields"] == [
            "netbox_allow_writes"]
        _r, html = _post(networks, "/v2/settings/installation/netbox/writes-off")
        assert "Already off" in html
        _r, html = _post(networks, "/v2/settings/installation/card/netbox/save",
                         {"netbox_url": "https://192.0.2.30", "netbox_auth_scheme": "Bearer",
                          "netbox_allow_writes": "on"})
        assert get_setting("netbox_allow_writes") is False, "Save never arms writes"

    def test_settings_place_names_the_v2_card(self):
        from modules import installation_settings as I
        assert I.settings_place("netbox", "NetBox") == (
            "Settings › Installation › Connections, NetBox connection")
        assert I.settings_place("proxmox", "Proxmox VE") == (
            "Settings › Installation › Connections, Proxmox")
        assert I.settings_place("grafana", "Grafana") == (
            "Settings › Default, the Grafana card (or the network's own)")

    def test_an_unknown_card_is_a_404_naming_the_cards(self, networks):
        r, html = _get(networks, "/v2/settings/installation/card/tftp")
        assert r.status_code == 404 and "netbox, proxmox, author, server" in html
