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

    def test_no_tab_links_to_today_s_page(self, networks):
        """Boards F to F4: every tab drawn (2026-10-10), so none sends a person to today's
        Settings page; the installation_settings cutover gap is closed."""
        from modules import installation_settings as I
        assert set(I.BUILT_TABS) == {key for key, _label in I.TABS}
        for key, _label in I.TABS:
            _r, tab = _get(networks, f"/v2/settings/installation?tab={key}")
            assert 'data-todays-page' not in tab.split('id="tab-body"')[1], key

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

#: Every separator a text has used for it: ">", "→", "›", and "->" (C622: the first scan
#: missed `nsot/platform.py`'s "Settings -> Integrations").
TODAYS_SETTINGS = re.compile(r"Settings\s*(?:->|>|→|›)\s*Integrations")


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


def _section(html, sid):
    m = re.search(rf'<section class="card set-card[^"]*" id="{sid}".*?</section>', html, re.S)
    assert m, f"no {sid} card"
    import html as html_mod
    return html_mod.unescape(re.sub(r"\s+", " ", m.group(0)))


UNHEALTHY = {"healthy": False, "canary_handlers_checked": 3, "canary_leaking": 1,
             "canary_leaking_detail": [{"handler": "StreamHandler",
                                        "leaked_shapes": ["password"], "ok": False}],
             "redaction_failures": 0, "first_failure_at": "", "last_failure_at": "",
             "last_error": "", "log_handlers_total": 3, "log_handlers_unprotected": 1,
             "unprotected_handler_types": ["StreamHandler"]}


class TestDiagnostics:
    """Board F4 (signed off 2026-10-10), Diagnostics: redaction (C624), drift checks, in flight
    and the app's log, nothing on the tab sending a person to today's page."""

    def test_the_tab_draws_its_four_cards_and_no_link_to_today_s_page(self, networks):
        _r, html = _get(networks, "/v2/settings/installation?tab=diagnostics")
        for sid in ("diag-redaction", "diag-drift", "diag-inflight", "diag-log"):
            _section(html, sid)
        assert 'data-todays-page' not in html.split('id="tab-body"')[1]

    def test_redaction_healthy_and_not_and_its_needs_attention_row(self, networks, monkeypatch):
        from modules import attention, redact
        card = _section(_get(networks, "/v2/settings/installation/diagnostics/redaction")[1],
                        "diag-redaction")
        assert "healthy" in card and "NOT healthy" not in card
        assert attention.redaction_source()["rows"] == [], "healthy: a state, never a row"
        monkeypatch.setattr(redact, "health", lambda: dict(UNHEALTHY))
        card = _section(_get(networks, "/v2/settings/installation/diagnostics/redaction")[1],
                        "diag-redaction")
        assert "NOT healthy" in card and "StreamHandler (password)" in card
        (row,) = attention.redaction_source()["rows"]
        assert row["level"] == "danger" and "StreamHandler" in row["cause"]
        assert row["action"]["href"] == "/v2/settings/installation?tab=diagnostics"
        assert attention.CLEARS[("redaction", "unhealthy")][0] == ("resolves",)

    def test_the_drift_schedule_saves_one_of_its_choices_and_records_it(self, networks):
        from modules import installation_settings as I
        from modules.drift_check import _get_interval
        _r, html = _post(networks, "/v2/settings/installation/diagnostics/drift/interval",
                         {"interval_s": "7200"})
        assert int(_get_interval()) == 7200 and "Saved by" in _section(html, "diag-drift")
        assert I.changes(kinds=("drift_interval",))["rows"][0]["fields"] == [
            "drift_check_interval"]
        r, html = _post(networks, "/v2/settings/installation/diagnostics/drift/interval",
                        {"interval_s": "60"})
        assert r.status_code == 409 and ("is not one of the drift schedule's choices"
                                         in _section(html, "diag-drift"))
        assert int(_get_interval()) == 7200

    def test_a_network_turned_off_and_on_says_who_and_is_recorded(self, networks):
        from modules import installation_settings as I
        from modules.drift_check import _is_disabled
        _r, html = _post(networks, "/v2/settings/installation/diagnostics/drift/Branch/off")
        assert _is_disabled("Branch") and "turned off by" in _section(html, "diag-drift")
        assert I.changes(kinds=("drift_off",))["rows"][0]["network"] == "Branch"
        _r, html = _post(networks, "/v2/settings/installation/diagnostics/drift/Branch/on")
        assert not _is_disabled("Branch")
        r, html = _post(networks, "/v2/settings/installation/diagnostics/drift/Nowhere/off")
        assert r.status_code == 409 and "'Nowhere' is not a network" in _section(html, "diag-drift")

    def test_check_now_starts_one_in_the_background_and_refuses_a_second(self, networks,
                                                                         monkeypatch):
        from modules.drift_check import get_checker
        started = []
        monkeypatch.setattr(get_checker(), "trigger", lambda name="": started.append(name))
        _r, html = _post(networks, "/v2/settings/installation/diagnostics/drift/Default/check")
        assert started == ["Default"] and "redraws when it finishes" in html
        monkeypatch.setattr(get_checker(), "is_running", lambda name="": True)
        r, html = _post(networks, "/v2/settings/installation/diagnostics/drift/Default/check")
        assert r.status_code == 409 and "already running" in html and started == ["Default"]

    def test_a_recorded_drift_run_is_announced(self, networks, monkeypatch):
        from modules import invalidation
        from modules.drift_check import get_checker
        heard = []
        monkeypatch.setattr(invalidation, "announce", lambda keys, by, ok=True: heard.append(
            (tuple(keys), by)))
        get_checker().record("Default", {"ok": True, "summary": "0 drifted"})
        assert heard == [(("drift",), "drift-check")]

    def test_the_app_log_reads_its_tail_filtered_and_says_absent_and_unreadable(
            self, networks, monkeypatch, tmp_path):
        from modules import app_log
        log = tmp_path / "device_manager.log"
        monkeypatch.setattr(app_log, "path", lambda: str(log))
        card = _section(_get(networks, "/v2/settings/installation/diagnostics/log")[1],
                        "diag-log")
        assert "does not exist yet" in card
        log.write_text("".join(f"line {i} {'WARNING' if i % 2 else 'INFO'}\n"
                               for i in range(600)))
        card = _section(_get(networks, "/v2/settings/installation/diagnostics/log?lines=200"
                                       "&contains=warning")[1], "diag-log")
        assert "100 of the last 200 lines contain \"warning\"" in card
        assert "line 599 WARNING" in card and "line 598 INFO" not in card
        log.chmod(0)
        try:
            card = _section(_get(networks, "/v2/settings/installation/diagnostics/log")[1],
                            "diag-log")
            assert "could not be read" in card
        finally:
            log.chmod(0o600)

    def test_in_flight_reads_every_network(self, networks, monkeypatch):
        from modules.nsot import device_ops
        monkeypatch.setattr(device_ops, "in_flight", lambda name, now: [
            {"device": "r2", "operation": "deploy", "words": "deploy", "actor": "op@x",
             "step_words": "verify", "held_for_s": 125, "stalled": False}]
            if name == "Branch" else [])
        card = _section(_get(networks, "/v2/settings/installation/diagnostics/inflight")[1],
                        "diag-inflight")
        assert "1 running" in card and "r2" in card and "Branch" in card and "2 min 5 s" in card
        assert "could not be read" not in card, "a network with no receipts yet is not unread"


class TestAccessAndIdentity:
    """Board F4, decision A (signed off 2026-10-10): read-only by design; Record this decision
    (ratify) the one control, writing the value in force and recorded (C625)."""

    def test_the_tab_draws_the_twelve_gates_and_nothing_to_change_them(self, networks):
        _r, html = _get(networks, "/v2/settings/installation?tab=access")
        gates = _section(html, "card-gates")
        assert "12 of 12 on" in gates and gates.count(">on<") == 12
        for sid in ("card-access", "card-services", "card-you"):
            _section(html, sid)
        body = html.split('id="tab-body"')[1]
        assert 'data-todays-page' not in body
        inputs = re.findall(r"<input[^>]*>", body)
        assert inputs and all('type="hidden"' in i for i in inputs), "read-only: hidden keys only"
        assert "Record this decision" in gates and "defaulted, nobody decided" in gates

    def test_record_this_decision_writes_the_value_in_force_and_records_who(self, networks):
        from modules import installation_settings as I
        from modules.settings_schema import get_setting, origin_of
        assert origin_of("require_identity_for_reveal") != "file"
        _r, html = _post(networks, "/v2/settings/installation/access/record",
                         {"keys": ["require_identity_for_reveal", "require_person_for_reveal"]})
        assert origin_of("require_identity_for_reveal") == "file"
        assert get_setting("require_identity_for_reveal") is True, "the value in force, unchanged"
        rec = I.changes(kinds=("ratify",))["rows"][0]
        assert rec["fields"] == ["require_identity_for_reveal", "require_person_for_reveal"]
        assert "Recorded" in html and "recorded by" in _section(html, "card-gates")

    def test_a_setting_that_is_not_access_or_identity_is_refused(self, networks):
        from modules.settings_schema import origin_of
        r, html = _post(networks, "/v2/settings/installation/access/record",
                        {"keys": ["netbox_url"]})
        from modules import installation_settings as I
        assert r.status_code == 409 and "is not an access or identity setting" in html
        assert origin_of("netbox_url") == "default" and I.changes(kinds=("ratify",))["rows"] == []

    def test_a_gate_turned_off_is_said_and_chosen(self, networks):
        from modules.settings_schema import write_settings
        write_settings({"require_person_for_configure": False}, actor="test")
        gates = _section(_get(networks, "/v2/settings/installation?tab=access")[1], "card-gates")
        assert "1 gate off" in gates and ">OFF<" in gates and "chosen: differs" in gates

    def test_a_key_cache_outside_its_bounds_is_said(self, networks, monkeypatch):
        from modules import identity
        monkeypatch.setattr(identity, "jwks_ttl",
                            lambda: (3600, "cf_access_jwks_ttl 0 is outside 300 to 86400 seconds"))
        card = _section(_get(networks, "/v2/settings/installation?tab=access")[1], "card-access")
        assert "the stored value is not used" in card and "0 is outside 300 to 86400" in card


NB_CACHE = {"devices": [
    {"hostname": "nb1", "device_type": "cisco_xe", "ip": "192.0.2.31", "role": "router",
     "_platform": "cisco-ios-xe", "_role_slug": "router"},
    {"hostname": "nb2", "device_type": "cisco_ios", "ip": "192.0.2.32", "role": "switch",
     "_platform": "cisco-ios", "_role_slug": "access-switch"}],
    "skipped": [{"name": "nb3", "field": "platform",
                 "reason": "platform 'nexus' is not in the platform map — skipped"}]}


@pytest.fixture
def netbox_branch(networks, monkeypatch):
    """Branch takes its devices from NetBox, its last inventory NB_CACHE: read through the
    module's own seams, so nothing asks NetBox or refreshes."""
    from modules import platform_maps as P
    from modules.inventory import source_config
    monkeypatch.setattr(source_config, "is_netbox_sourced", lambda name: name == "Branch")
    monkeypatch.setattr(P, "_cached", lambda name: json.loads(json.dumps(NB_CACHE)))
    refreshed = []
    import modules.inventory as inv
    monkeypatch.setattr(inv, "invalidate", lambda name="": None)
    monkeypatch.setattr(inv, "refresh_async", lambda name: refreshed.append(name))
    return refreshed


def _platform_form(**over):
    """The platform card's form as the page sends it: both rows as drawn, then *over*."""
    form = {"kind": "platforms", "slug": ["cisco-ios", "cisco-ios-xe"],
            "driver": ["cisco_ios", "cisco_xe"], "dialect": ["cisco_ios", "cisco_iosxe"],
            "transport": ["ssh", "ssh"], "netconf": ["cisco-ios-xe"], "default_driver": ""}
    form.update(over)
    return form


class TestPlatformsAndRoles:
    """Board F4, decision B with the operator's validation (2026-10-10): drivers chosen, never
    typed; Preview changes names every device moved; a Test of one read-only session; the
    confirm bound to the preview."""

    def test_the_tab_offers_only_supported_drivers_and_known_dialects(self, networks):
        from modules import platform_maps as P
        _r, html = _get(networks, "/v2/settings/installation?tab=platforms")
        card = _section(html, "card-platform-map")
        assert not re.search(r'<input[^>]*name="(new_)?driver"', card), "a driver is never typed"
        for d in P.supported_drivers():
            assert f"<option>{d}</option>" in card or f"<option selected>{d}</option>" in card
        assert "cisco_iosxe" in card and "cisco_ios_xe" not in card, "dialects, not folders"
        _section(html, "card-role-map")

    def test_a_driver_change_previews_each_device_it_moves(self, networks, netbox_branch):
        _r, html = _post(networks, "/v2/settings/installation/platforms/preview",
                         _platform_form(driver=["cisco_ios", "cisco_ios"]))
        pv = re.sub(r"<[^>]+>", "", _section(html, "card-platforms-preview"))
        assert "1 device changes" in pv and "nb1" in pv and "cisco_xe → cisco_ios" in pv
        assert "nb2" not in pv.split("The devices")[1].split("</table>")[0]
        assert "keep the driver their list names" in pv and "Default" in pv
        assert "Test with" in pv and 'value="Branch|nb1|cisco_ios"' in html

    def test_adding_a_platform_loads_what_was_skipped(self, networks, netbox_branch):
        _r, html = _post(networks, "/v2/settings/installation/platforms/preview",
                         _platform_form(new_slug="nexus", new_driver="cisco_ios",
                                        new_dialect="cisco_ios", new_transport="ssh"))
        assert "loaded after this: 1" in _section(html, "card-platforms-preview")

    def test_removing_a_platform_in_use_and_an_unsupported_driver_are_refused(
            self, networks, netbox_branch):
        r, html = _post(networks, "/v2/settings/installation/platforms/preview",
                        _platform_form(remove="cisco-ios"))
        assert r.status_code == 409 and "cisco-ios is used by nb2 (Branch)" in html
        r, html = _post(networks, "/v2/settings/installation/platforms/preview",
                        _platform_form(driver=["cisco_ios", "linux"]))
        import html as html_mod
        assert r.status_code == 409 and "'linux' is not one Mercury supports" in html_mod.unescape(html)

    def test_a_role_change_previews_each_device_it_moves(self, networks, netbox_branch):
        _r, html = _post(networks, "/v2/settings/installation/platforms/preview",
                         {"kind": "roles", "slug": ["access-switch", "router"],
                          "role": ["router", "router"]})
        pv = re.sub(r"<[^>]+>", "", _section(html, "card-platforms-preview"))
        assert "1 device changes" in pv and "nb2" in pv and "switch → router" in pv

    def test_the_confirm_is_bound_writes_records_and_refreshes(self, networks, netbox_branch):
        from modules import installation_settings as I
        from modules.settings_schema import get_setting
        _r, html = _post(networks, "/v2/settings/installation/platforms/preview",
                         _platform_form(driver=["cisco_ios", "cisco_ios"]))
        proposal = re.search(r'name="proposal" value="([^"]*)"', html).group(1)
        fp = re.search(r'name="fingerprint" value="([^"]*)"', html).group(1)
        import html as html_mod
        proposal = html_mod.unescape(proposal)
        r, out = _post(networks, "/v2/settings/installation/platforms/apply",
                       {"proposal": proposal, "fingerprint": "0" * 16})
        assert r.status_code == 409 and "moved since the preview" in html_mod.unescape(out)
        assert get_setting("platform_map")["cisco-ios-xe"]["netmiko_device_type"] == "cisco_xe"
        _r, out = _post(networks, "/v2/settings/installation/platforms/apply",
                        {"proposal": proposal, "fingerprint": fp})
        assert get_setting("platform_map")["cisco-ios-xe"]["netmiko_device_type"] == "cisco_ios"
        assert netbox_branch == ["Branch"] and "Refreshing Branch" in out
        rec = I.changes(kinds=("platforms_map",))["rows"][0]
        assert rec["devices_changed"] == 1 and "platform_map" in rec["fields"]

    def test_the_test_reads_one_device_with_the_new_driver(self, networks, monkeypatch):
        from modules.nsot import reads
        asked = []
        monkeypatch.setattr(reads, "start", lambda net, hosts, cmds, actor, **kw: (
            asked.append((net, hosts, cmds, kw.get("drivers"))) or {"job": "j1", "run": "r1"}))
        _r, html = _post(networks, "/v2/settings/installation/platforms/test",
                         {"target": "Branch|nb1|cisco_ios"})
        assert asked == [("Branch", ["nb1"], ["show version"], {"nb1": "cisco_ios"})]
        assert "testing" in html and "nmas:reads" in html
        monkeypatch.setattr(reads, "get", lambda net, run_id: {
            "state": "done", "devices": ["nb1"], "drivers": {"nb1": "cisco_ios"},
            "results": {"nb1": {"state": "answered", "took_s": 2.1, "answers": [
                {"command": "show version", "state": "answered",
                 "answer": "Cisco IOS XE Software, Version 17.9\nline 2"}]}}})
        _r, html = _get(networks, "/v2/settings/installation/platforms/test/Branch/r1")
        assert "passed" in html and "through <span class=\"mono\">cisco_ios</span>" in html
        assert "Version 17.9" in html


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
                           'C = "check Settings › Integrations › Grafana"\n'
                           'D = "add it in Settings -> Integrations"\n')
        found = [t for _f, t in _strings_naming_todays_settings([planted])]
        assert found == ["put it in Settings → Integrations",
                         "check Settings › Integrations › Grafana",
                         "add it in Settings -> Integrations"], "a docstring is not screen text"


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

    def test_the_ai_tab_draws_the_assistant_switch_and_the_agent_s_state_only(self, networks):
        """Board F4, decisions C and D: the assistant's switch, saved and recorded like every
        card; no workflow switch; the background agent its state, never a control."""
        from modules import installation_settings as I
        from modules.settings_schema import get_setting
        _r, html = _get(networks, "/v2/settings/installation?tab=ai")
        card, agent = _kcard(html, "assistant"), _kcard(html, "agent")
        assert 'name="ai_enabled"' in card and "read-only allowlist" in card
        assert "wf_" not in html, "decision C: the workflow switches are not drawn"
        assert "off until Stage 8" in agent and "<button" not in agent and "<input" not in agent
        assert 'data-todays-page' not in html.split('id="tab-body"')[1]
        _r, html = _post(networks, "/v2/settings/installation/card/assistant/save", {})
        assert get_setting("ai_enabled") is False and "Saved" in _kcard(html, "assistant")
        assert I.changes(kinds=("card_save",))["rows"][0]["fields"] == ["ai_enabled"]

    def test_an_agent_set_on_in_the_file_is_said_with_its_restart(self, networks):
        from modules.settings_schema import write_settings
        write_settings({"background_agent_enabled": True}, actor="test")
        _r, html = _get(networks, "/v2/settings/installation?tab=ai")
        agent = _kcard(html, "agent")
        assert "set on in the settings file" in agent and "starts only when Mercury restarts" in agent

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
