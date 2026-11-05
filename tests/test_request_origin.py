"""The Host and same-origin checks (modules/request_origin.py; the operator, 2026-11-05).

The final SDN lab's laptop install runs with the identity gates off for its hardware sitting
(C2520's option (c)), so nothing stands between a page the laptop's browser opens and a write to
Mercury. The operator's conditions: a request whose Host is not 127.0.0.1 or localhost is
refused (DNS rebinding); a write whose Origin is not Mercury's own is refused; a write carrying
none of Origin, Referer and Sec-Fetch-Site is refused. Each is planted here, through the real
app and its real hook, with the settings in a temporary settings file. Both checks are off by
default, the prior behaviour, and the server keeps them off until the operator's report.
"""
import json

import pytest

OWN = "http://127.0.0.1:5080"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """A temporary settings file; the test writes the two keys it needs."""
    from modules import config

    path = tmp_path / "user_settings.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(path))

    def put(**values):
        path.write_text(json.dumps(values), encoding="utf-8")
    return put


@pytest.fixture
def kit(settings, monkeypatch):
    """The laptop kit's values: loopback names only, same-origin writes, Mercury on 5080."""
    from modules import config

    settings(allowed_host_names="127.0.0.1, localhost, ::1", require_same_origin_writes=True)
    monkeypatch.setattr(config, "FLASK_PORT", 5080)


def _client(base=OWN):
    import app as A

    A.app.config["TESTING"] = True
    return A.app.test_client(), base


def _post(headers=None, base=OWN):
    c, base = _client(base)
    return c.post("/restarts/planned", base_url=base, headers=headers or {}, data={})


def _ours(resp) -> str:
    """This hook's refusal text, or "" when the answer is someone else's (a gate, a 404)."""
    body = resp.get_json(silent=True) or {}
    err = body.get("error") or ""
    return err if ("allowed_host_names" in err or "require_same_origin_writes" in err) else ""


class TestTheHostHeader:
    def test_a_foreign_host_is_refused_naming_both(self, kit):
        r = _post({"Origin": "http://evil.example:5080"}, base="http://evil.example:5080")
        assert r.status_code == 400
        assert "'evil.example'" in _ours(r) and "127.0.0.1, localhost, ::1" in _ours(r)

    def test_a_foreign_host_is_refused_on_a_read_too(self, kit):
        c, _ = _client("http://evil.example:5080")
        r = c.get("/health", base_url="http://evil.example:5080")
        assert r.status_code == 400 and "evil.example" in _ours(r)

    @pytest.mark.parametrize("base", [OWN, "http://localhost:5080", "http://[::1]:5080"])
    def test_loopback_names_pass_ipv4_ipv6_and_localhost(self, kit, base):
        c, _ = _client(base)
        r = c.get("/health", base_url=base)
        assert r.status_code == 200, r.get_json()

    def test_ipv6_host_header_is_read_without_its_port(self):
        from modules import request_origin as R

        assert R.host_name("[::1]:5080") == "::1"
        assert R.host_name("127.0.0.1:5080") == "127.0.0.1"
        assert R.host_name("[2001:db8::1]") == "2001:db8::1"


class TestAWritesOrigin:
    def test_a_foreign_origin_is_refused_naming_both(self, kit):
        r = _post({"Origin": "http://evil.example"})
        assert r.status_code == 403
        assert "'http://evil.example'" in _ours(r) and OWN in _ours(r)

    def test_cross_site_fetch_metadata_is_refused(self, kit):
        r = _post({"Sec-Fetch-Site": "cross-site", "Origin": OWN})
        assert r.status_code == 403 and "'cross-site'" in _ours(r)

    def test_a_foreign_referer_without_origin_is_refused(self, kit):
        r = _post({"Referer": "http://evil.example/page"})
        assert r.status_code == 403 and "http://evil.example" in _ours(r)

    def test_a_write_with_none_of_the_three_is_refused(self, kit):
        r = _post({})
        assert r.status_code == 403
        assert "none of Origin, Referer and Sec-Fetch-Site" in _ours(r)

    @pytest.mark.parametrize("headers", [
        {"Origin": OWN},
        {"Origin": OWN, "Sec-Fetch-Site": "same-origin"},
        {"Referer": OWN + "/v2/settings"},
        {"Sec-Fetch-Site": "same-origin"},
    ])
    def test_mercurys_own_pages_pass(self, kit, headers):
        assert _ours(_post(headers)) == ""

    def test_a_read_needs_no_origin(self, kit):
        c, _ = _client()
        assert c.get("/health", base_url=OWN).status_code == 200


class TestOffByDefault:
    def test_with_neither_setting_nothing_is_refused(self, settings):
        settings()
        assert _ours(_post({}, base="http://evil.example")) == ""
        assert _ours(_post({"Origin": "http://evil.example"})) == ""

    def test_the_defaults_are_off(self):
        from modules.settings_schema import DEFAULTS

        assert DEFAULTS["allowed_host_names"] == ""
        assert DEFAULTS["require_same_origin_writes"] is False


class TestTheSocketHandshake:
    def test_off_accepts_every_origin_as_star_did(self, settings):
        from modules import request_origin as R

        settings()
        assert R.socket_origin_allowed("http://evil.example")

    @pytest.mark.parametrize("origin,ok", [
        (OWN, True),
        ("http://localhost:5080", True),
        ("http://[::1]:5080", True),
        ("http://evil.example:5080", False),
        ("http://127.0.0.1:9999", False),
        ("", False),
    ])
    def test_on_accepts_only_mercurys_own(self, kit, origin, ok):
        from modules import request_origin as R

        assert R.socket_origin_allowed(origin) is ok

    def test_the_app_hands_engineio_this_check(self):
        import app as A
        from modules import request_origin as R

        assert A.socketio.server.eio.cors_allowed_origins is R.socket_origin_allowed

    def test_the_hook_runs_before_the_route_gate(self):
        import app as A
        from modules import request_origin as R, route_gates

        hooks = A.app.before_request_funcs[None]
        assert hooks.index(R.enforce) < hooks.index(route_gates.enforce)
