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

    def test_unbuilt_tabs_and_cards_say_so_and_link_to_today_s_page(self, networks):
        _r, html = _get(networks, "/v2/settings/installation")
        assert "NetBox connection</strong> and <strong>Proxmox</strong> cards are on" in html
        assert "<strong>Commit author</strong> card is on" in html
        for key in ("access", "platforms", "server", "ai", "diagnostics"):
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
