"""Settings per network on v2 (P.8 step 7; boards A to J, approved 2026-10-05), through the
real app, routes, templates and resolver, on a temporary store with four networks: Default
(Grafana and Loki set), Branch (its own Grafana), Lab-3 (inheriting everything) and Remote
(standalone: its Prometheus its own, Loki chosen to inherit, Grafana not configured).

- The page: under the strict policy, from the sidebar; each card's state, every field with
  where it came from, a secret never drawn; the mode banner; the scope bar's picker leading
  with the standalone networks; Default's cards counting only who chose to inherit.
- A group's switch: the preview in place of the card (today and after, a secret as set),
  the confirm bound to it, the card again with its result, recorded with the person; a
  confirm whose settings moved is refused naming both values; "its own" takes its values
  in the card (a secret encrypted, an emptied field cleared); not applicable needs a reason.
- The mode's switch (J1): the preview names exactly the groups that become not configured,
  the confirm switches and records.
- A viewer who may not confirm gets no confirm; a list nobody has is refused.
"""

import json
import re

import pytest

from modules import list_settings as L


@pytest.fixture
def networks(tmp_path, monkeypatch):
    from modules import config, device
    from modules.secrets_store import encrypt_value

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
    settings = tmp_path / "user_settings.json"
    settings.write_text(json.dumps({"grafana_url": "http://192.0.2.10:3000",
                                    "grafana_token": encrypt_value("default-token-xyz"),
                                    "loki_url": "http://192.0.2.10:3100"}), encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(settings))
    registry = tmp_path / "device_lists.json"
    registry.write_text(json.dumps({"current_list": "Default", "lists": {
        "Default": "default", "Branch": "branch", "Lab-3": "lab_3", "Remote": "remote"}}),
        encoding="utf-8")
    monkeypatch.setattr(device, "DEVICE_LISTS_CONFIG", str(registry))
    for slug in ("default", "branch", "lab_3", "remote"):
        (tmp_path / "lists" / slug).mkdir(parents=True, exist_ok=True)
    assert L.write("Branch", {"grafana_url": "http://192.0.2.60:3000",
                              "grafana_token": "branch-token-xyz"})["ok"]
    (tmp_path / "lists" / "remote" / "settings.json").write_text(json.dumps({
        "values": {"prometheus_url": "http://192.0.2.70:9090"}, "not_applicable": {},
        "mode": "standalone", "groups": {"loki": "inherit"}}), encoding="utf-8")
    import app as A
    return {"client": A.app.test_client(), "dir": tmp_path}


def _get(n, path):
    r = n["client"].get(path)
    return r, r.get_data(as_text=True)


def _card(html, group):
    m = re.search(rf'<section class="card set-card[^"]*" id="card-{group}".*?</section>', html, re.S)
    assert m, f"no card for {group}"
    return m.group(0)


def _form(html):
    """The preview's hidden fields and inputs, as the browser would send them."""
    fields = dict(re.findall(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"', html))
    fields.update(re.findall(r"<input type=\"hidden\" name=\"(seen)\" value='([^']*)'", html))
    return {k: v.replace("&#34;", '"').replace("&quot;", '"').replace("&#39;", "'")
            for k, v in fields.items()}




class TestThePage:
    def test_it_draws_under_the_strict_policy_from_the_sidebar(self, networks):
        from modules import csp

        r, html = _get(networks, "/v2/settings")
        assert r.status_code == 200 and "<h1>Settings · Default" in html, "opens on the active list"
        r, html = _get(networks, "/v2/settings/network/Branch")
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert re.search(r'class="nav-item active" href="/v2/settings"', html)
        assert 'data-manual="settings"' in html

    def test_each_card_says_where_its_values_come_from_and_never_a_secret(self, networks):
        _r, html = _get(networks, "/v2/settings/network/Branch")
        grafana = _card(html, "grafana")
        assert "its own" in grafana and "http://192.0.2.60:3000" in grafana
        loki = _card(html, "loki")
        assert "inherited from Default" in loki and "http://192.0.2.10:3100" in loki
        assert "A change in Default changes Branch" in loki
        assert "branch-token-xyz" not in html and "default-token-xyz" not in html
        # Branch's own Grafana is set here, so its card takes its fields (board A): the token
        # is drawn only as set, behind Replace…, never its value.
        token = re.search(r'<label for="f-grafana-grafana_token">Token</label>\s*<div>(.*?)</div>',
                          grafana, re.S).group(1)
        assert "Replace…" in token and "set: leave empty to keep it" in token
        assert 'type="password" value=""' in token

    def test_a_standalone_networks_page_says_so(self, networks):
        _r, html = _get(networks, "/v2/settings/network/Remote")
        assert "Remote is standalone: it takes nothing from Default." in html
        grafana = _card(html, "grafana")
        assert "not configured for this network" in grafana
        assert "nothing comes from Default" in grafana
        assert "http://192.0.2.10:3000" not in grafana, "Default's Grafana drawn on a standalone"
        assert "inherited from Default" in _card(html, "loki"), "a group's own choice stands"
        assert "Change to inheriting from Default…" in html

    def test_the_picker_leads_with_the_standalone_networks(self, networks):
        _r, html = _get(networks, "/v2/settings/network/Lab-3")
        menu = html[html.index('class="scope-menu"'):]
        assert menu.index("Standalone · 1") < menu.index("Inherit, with their own values · 1") \
            < menu.index("Inherit everything from Default · 1")
        assert "Remote" in menu[:menu.index("Inherit, with")]
        assert "own: Prometheus" in menu and "not configured: " in menu

    def test_defaults_cards_count_only_who_chose_to_inherit(self, networks):
        _r, html = _get(networks, "/v2/settings/network/Default")
        grafana = _card(html, "grafana")
        assert "inherited by 1" in grafana            # Lab-3 only
        assert "own Grafana in 1" in grafana          # Branch
        assert "not configured in 1" in grafana       # Remote, standalone
        loki = _card(html, "loki")
        assert "inherited by 3" in loki               # Branch, Lab-3 and Remote's own choice
        assert "(standalone)" in loki

    def test_a_list_nobody_has_is_refused(self, networks):
        r, _html = _get(networks, "/v2/settings/network/Nope")
        assert r.status_code == 404


class TestTheGroupSwitch:
    def test_back_to_inheriting_previews_confirms_and_records(self, networks):
        r, prev = _get(networks, "/v2/settings/network/Branch/group/grafana/switch?to=inherit")
        assert r.status_code == 200 and 'id="card-grafana"' in prev
        assert "It would pick up" in prev and "http://192.0.2.10:3000" in prev
        assert "default-token-xyz" not in prev and "branch-token-xyz" not in prev
        assert "Inherit Default's Grafana for Branch and remove its own 2" in prev
        out = networks["client"].post("/v2/settings/network/Branch/group/grafana/switch",
                                      data=_form(prev))
        html = out.get_data(as_text=True)
        assert out.status_code == 200 and "inherits from Default" in html
        assert "by test-person@example.invalid" in html
        assert L.resolve("Branch", "grafana_url") == ("http://192.0.2.10:3000", L.INHERITED)
        rec = L.changes("Branch")["rows"][0]
        assert rec["kind"] == "group" and rec["actor_verified"] == "access"

    def test_a_confirm_whose_settings_moved_is_refused_naming_both(self, networks):
        _r, prev = _get(networks, "/v2/settings/network/Lab-3/group/grafana/switch?to=own")
        L.write("Default", {"grafana_url": "http://192.0.2.99:3000"})
        out = networks["client"].post("/v2/settings/network/Lab-3/group/grafana/switch",
                                      data=_form(prev))
        html = out.get_data(as_text=True)
        assert out.status_code == 409 and "Nothing was saved" in html
        assert "http://192.0.2.10:3000" in html and "http://192.0.2.99:3000" in html

    def test_its_own_takes_values_in_the_card_and_an_empty_field_clears(self, networks):
        _r, prev = _get(networks, "/v2/settings/network/Branch/group/grafana/switch?to=own")
        assert 'type="password"' in prev and "branch-token-xyz" not in prev
        assert "set: leave empty to keep it" in prev
        form = _form(prev)
        form.update({"grafana_url": "http://192.0.2.61:3000", "grafana_token": "",
                     "grafana_token_expires": "", "grafana_verify_tls": "off"})
        out = networks["client"].post("/v2/settings/network/Branch/group/grafana/switch",
                                      data=form)
        assert out.status_code == 200, out.get_data(as_text=True)
        assert L.resolve("Branch", "grafana_url")[0] == "http://192.0.2.61:3000"
        assert L.resolve("Branch", "grafana_verify_tls") == (False, L.SET_HERE)
        assert L.secret("Branch", "grafana_token") == "branch-token-xyz", "an empty secret kept"

    def test_not_applicable_needs_a_reason(self, networks):
        _r, prev = _get(networks, "/v2/settings/network/Lab-3/group/kea/switch?to=not_applicable")
        assert 'name="reason"' in prev
        form = _form(prev)
        out = networks["client"].post("/v2/settings/network/Lab-3/group/kea/switch",
                                      data=dict(form, reason=""))
        assert out.status_code == 409 and "reason" in out.get_data(as_text=True)
        out = networks["client"].post("/v2/settings/network/Lab-3/group/kea/switch",
                                      data=dict(form, reason="addresses come from the ISP here"))
        assert out.status_code == 200
        assert L.resolve("Lab-3", "kea_url") == (None, L.NOT_APPLICABLE)

    def test_a_viewer_who_may_not_confirm_gets_no_confirm(self, networks, monkeypatch):
        from modules import identity

        monkeypatch.setattr(identity, "identify",
                            lambda r: identity.Identity(peer="198.51.100.7"))
        _r, prev = _get(networks, "/v2/settings/network/Branch/group/grafana/switch?to=inherit")
        assert "op-confirm" not in prev and "You may not confirm" in prev


class TestTheModeSwitch:
    def test_standalone_names_what_becomes_unconfigured_and_switches(self, networks):
        _r, prev = _get(networks, "/v2/settings/network/Lab-3/mode?to=standalone")
        assert "Make Lab-3 standalone" in prev
        assert "Grafana and Loki are inherited from Default today" in prev
        assert "2 groups become not configured" in prev
        out = networks["client"].post("/v2/settings/network/Lab-3/mode", data=_form(prev))
        html = out.get_data(as_text=True)
        assert out.status_code == 200 and "Lab-3 is standalone" in html
        assert L.mode("Lab-3") == L.STANDALONE
        assert L.changes("Lab-3")["rows"][0]["kind"] == "mode"

    def test_the_default_network_has_no_mode(self, networks):
        r, html = _get(networks, "/v2/settings/network/Default/mode?to=standalone")
        assert r.status_code == 409 and "base layer" in html


def _save(n, list_name, group, data):
    import html as html_mod
    r = n["client"].post(f"/v2/settings/network/{list_name}/group/{group}/save", data=data)
    return r, html_mod.unescape(r.get_data(as_text=True))


class TestSaveAndTest:
    """Boards A and D (approved 2026-10-05): a card set here, Default's included, takes its
    fields in place, with Save and Test (the operator's decision, 2026-10-08: a cutover gap
    built before the MinIO walk)."""

    def test_defaults_card_takes_its_fields_with_save_and_test(self, networks):
        _r, html = _get(networks, "/v2/settings/network/Default")
        grafana = _card(html, "grafana")
        assert 'name="grafana_url"' in grafana and 'value="http://192.0.2.10:3000"' in grafana
        assert ">Save</span>" in grafana and ">Test</span>" in grafana
        assert "default-token-xyz" not in grafana and "Replace…" in grafana
        assert "Every network that inherits Grafana reads what is saved here." in grafana

    def test_saving_default_writes_it_records_the_keys_and_never_the_values(self, networks):
        from modules.settings_schema import get_setting
        r, html = _save(networks, "Default", "grafana",
                        {"grafana_url": "http://192.0.2.11:3000", "grafana_token": ""})
        assert r.status_code == 200
        assert "Grafana saved" in html and "1 field (grafana_url)" in html
        assert "every network that inherits Grafana reads the new values" in html
        assert get_setting("grafana_url") == "http://192.0.2.11:3000"
        from modules.secrets_store import get_secret
        assert get_secret("grafana_token") == "default-token-xyz", "an empty secret keeps it"
        rec = L.changes("Default")["rows"][0]
        assert rec["kind"] == "values" and rec["written"] == ["grafana_url"]
        assert "192.0.2.11" not in json.dumps(rec), "the record names keys, never values"
        assert L.resolve("Lab-3", "grafana_url")[0] == "http://192.0.2.11:3000", "inherited"

    def test_a_new_secret_replaces_the_stored_one_and_is_never_drawn(self, networks):
        from modules.secrets_store import get_secret
        _r, html = _save(networks, "Default", "grafana", {"grafana_token": "new-token-abc"})
        assert get_secret("grafana_token") == "new-token-abc"
        assert "new-token-abc" not in html and "1 field (grafana_token)" in html

    def test_a_networks_own_group_saves_its_own_and_default_is_untouched(self, networks):
        from modules.settings_schema import get_setting
        _r, html = _save(networks, "Branch", "grafana", {"grafana_url": "http://192.0.2.61:3000"})
        assert "Grafana saved" in html
        assert L.resolve("Branch", "grafana_url") == ("http://192.0.2.61:3000", L.SET_HERE)
        assert get_setting("grafana_url") == "http://192.0.2.10:3000"

    def test_an_inherited_group_is_refused_naming_its_state(self, networks):
        r, html = _save(networks, "Branch", "loki", {"loki_url": "http://192.0.2.62:3100"})
        assert r.status_code == 409
        assert "Loki is not Branch's own (it is inherit from Default)" in html
        assert L.resolve("Branch", "loki_url")[1] == L.INHERITED

    def test_a_field_of_another_group_is_ignored_and_nothing_changed_is_said(self, networks):
        _r, html = _save(networks, "Default", "grafana",
                         {"grafana_url": "http://192.0.2.10:3000", "loki_url": "x"})
        assert "Nothing changed" in html
        assert L.resolve("Default", "loki_url")[0] == "http://192.0.2.10:3100"

    def test_test_draws_the_integrations_answer_in_the_card(self, networks, monkeypatch):
        from modules.integrations.grafana import GrafanaIntegration
        monkeypatch.setattr(GrafanaIntegration, "test_connection",
                            lambda self: {"ok": False, "error": "HTTP 401 from Grafana"})
        r = networks["client"].post("/v2/settings/network/Default/group/grafana/test")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "Test: failed." in html and "HTTP 401 from Grafana" in html

    def test_the_s3_archives_test_draws_its_four_steps(self, networks, monkeypatch):
        from modules.integrations.s3_archive import S3ArchiveIntegration
        steps = [{"name": n, "ok": True, "detail": n + " ok"}
                 for n in ("bucket", "put", "get", "stat")]
        monkeypatch.setattr(S3ArchiveIntegration, "is_configured", lambda self: True)
        monkeypatch.setattr(S3ArchiveIntegration, "test_connection",
                            lambda self: {"ok": True, "steps": steps, "message": "reachable"})
        html = networks["client"].post(
            "/v2/settings/network/Default/group/s3_archive/test").get_data(as_text=True)
        assert "Test: passed." in html
        assert all(f"{n}: {n} ok" in html for n in ("bucket", "put", "get", "stat"))

    def test_a_group_with_no_integration_has_no_test(self, networks):
        r = networks["client"].post("/v2/settings/network/Default/group/deploy_max_workers/test")
        assert r.status_code == 404 and "configures no integration to test" in r.get_data(
            as_text=True)


@pytest.fixture(scope="module")
def live_browser():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        yield browser, srv, b


@pytest.fixture
def served(networks, live_browser):
    browser, srv, b = live_browser
    yield {"b": b, "srv": srv}
    try:
        b.go("about:blank")
    finally:
        browser.close_socketio_sessions()


#: htmx binds a swapped-in control while it settles: click only once nothing settles.
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


class TestInARealBrowser:
    def test_a_groups_switch_and_the_mode_as_a_person_clicks_them(self, served):
        b = served["b"]
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
        b.go(served["srv"].url("/v2/settings/network/Branch"))
        b.wait_for("return !!window.Alpine && " + SETTLED, 15)
        b.js("window.__notReloaded = 1; return 1")
        b.click('#card-grafana .seg a.seg-btn[href$="to=inherit"]')
        b.wait_for("var c=document.getElementById('card-grafana');"
                   f"return c && c.querySelector('.op-confirm') && {SETTLED}", 15)
        assert L.resolve("Branch", "grafana_url")[1] == L.SET_HERE, "a choice saved nothing"
        b.click("#card-grafana .op-confirm")
        b.wait_for("var c=document.getElementById('card-grafana');"
                   f"return c && c.className.indexOf('set-card-done') >= 0 && {SETTLED}", 15)
        assert "inherits from Default" in b.js(
            "return document.getElementById('card-grafana').textContent")
        assert L.resolve("Branch", "grafana_url")[1] == L.INHERITED
        b.click('#settings-mode-banner a[data-op="settings-switch"]')
        b.wait_for(f"return document.querySelector('#settings-mode-op .op-confirm') && {SETTLED}",
                   15)
        b.click("#settings-mode-op .op-confirm")
        b.wait_for("var c=document.getElementById('settings-mode-op');"
                   f"return c && c.className.indexOf('op-ok') >= 0 && {SETTLED}", 15)
        assert L.mode("Branch") == L.STANDALONE
        assert b.js("return window.__notReloaded") == 1

    def test_at_phone_width_nothing_runs_past_the_screen(self, served, monkeypatch):
        from modules import csp
        monkeypatch.setattr(csp, "STRICT_POLICY", csp.STRICT_POLICY.replace(
            "frame-ancestors 'none'", "frame-ancestors 'self'"))
        b = served["b"]
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1200, "height": 900})
        b.go(served["srv"].url("/v2/settings/network/Remote"))
        b.wait_for("return !!window.Alpine", 10)
        b.js("var f=document.createElement('iframe'); f.id='phone'; f.width='390';"
             "f.height='800'; f.style.position='fixed'; f.style.left='0'; f.style.top='0';"
             "f.style.border='0'; f.style.zIndex='9999';"
             "f.src=location.origin + '/v2/settings/network/Remote';"
             "document.documentElement.appendChild(f); return 1")
        b.wait_for("var d=document.getElementById('phone').contentDocument;"
                   "return d && d.querySelector('#card-grafana')", 15)
        got = b.js("var w=document.getElementById('phone').contentWindow, d=w.document;"
                   "return {inner: w.innerWidth, scroll: d.documentElement.scrollWidth};")
        assert got["inner"] == 390 and got["scroll"] <= 390, got
