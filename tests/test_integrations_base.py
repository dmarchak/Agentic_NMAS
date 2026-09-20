"""Integration client framework.

Constraint 4: every integration is optional. An unconfigured or unreachable
tool reports a clear error and never raises into a request handler.

No test here touches a network — every HTTP call is mocked.
"""

import pytest
import requests

from modules.integrations import REGISTRY, all_statuses, get_integration
from modules.integrations.base import IntegrationClient


class DummyIntegration(IntegrationClient):
    name = "dummy"
    label = "Dummy"
    url_key = "dummy_url"
    secret_keys = ("dummy_token",)
    plain_keys = ("dummy_mode",)


@pytest.fixture
def unconfigured(monkeypatch):
    monkeypatch.setattr("modules.integrations.base.get_setting",
                        lambda key, default=None: "" if key == "dummy_url" else default)
    return DummyIntegration()


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr("modules.integrations.base.get_setting",
                        lambda key, default=None:
                        "http://tool.invalid" if key == "dummy_url" else default)
    return DummyIntegration()


class TestOptionality:
    def test_unconfigured_reports_clearly(self, unconfigured):
        assert unconfigured.is_configured() is False
        result = unconfigured._get("anything")
        assert result["ok"] is False
        assert "Not configured" in result["error"]

    def test_unconfigured_status_is_grey(self, unconfigured):
        st = unconfigured.status()
        assert st["state"] == "not_configured"

    def test_every_registered_client_handles_unconfigured(self):
        """No client may raise when nothing is set up."""
        for name in REGISTRY:
            client = get_integration(name)
            result = client.test_connection()
            assert isinstance(result, dict) and "ok" in result, name

    def test_all_statuses_never_raises(self):
        statuses = all_statuses()
        assert len(statuses) == len(REGISTRY)
        assert all(s["state"] in ("up", "down", "not_configured") for s in statuses)


class TestErrorsNeverEscape:
    @pytest.mark.parametrize("exc,expected", [
        (requests.exceptions.ConnectionError(), "Could not connect"),
        (requests.exceptions.Timeout(), "Timed out"),
        (requests.exceptions.SSLError("bad cert"), "TLS error"),
        (ValueError("something odd"), "something odd"),
    ])
    def test_transport_errors_become_results(self, configured, monkeypatch, exc, expected):
        class S:
            def get(self, *a, **kw):
                raise exc
        monkeypatch.setattr(configured, "session", lambda: S())
        result = configured._get("api/thing")
        assert result["ok"] is False
        assert expected in result["error"]

    def test_http_error_status_is_reported(self, configured, monkeypatch):
        class R:
            status_code = 503
        class S:
            def get(self, *a, **kw):
                return R()
        monkeypatch.setattr(configured, "session", lambda: S())
        result = configured._get("api/thing")
        assert result["ok"] is False and result["status"] == 503


class TestSecretHandling:
    def test_get_config_never_returns_secret_values(self, configured, monkeypatch):
        monkeypatch.setattr("modules.integrations.base.is_set", lambda key: True)
        cfg = configured.get_config()
        assert cfg["_secrets"] == {"dummy_token": True}
        assert "dummy_token" not in cfg          # only the indicator, never the value

    def test_blank_secret_does_not_overwrite_stored_one(self, configured, monkeypatch):
        written = {}
        monkeypatch.setattr("modules.integrations.base.set_secret",
                            lambda k, v: written.__setitem__(k, v))
        monkeypatch.setattr("modules.config.set_user_setting", lambda k, v: True)
        configured.save_config({"dummy_token": ""})
        assert written == {}, "an empty secret field must leave the stored value alone"

    def test_supplied_secret_is_written(self, configured, monkeypatch):
        written = {}
        monkeypatch.setattr("modules.integrations.base.set_secret",
                            lambda k, v: written.__setitem__(k, v))
        monkeypatch.setattr("modules.config.set_user_setting", lambda k, v: True)
        configured.save_config({"dummy_token": "new-token"})
        assert written == {"dummy_token": "new-token"}


class TestRegistry:
    def test_expected_integrations_registered(self):
        for expected in ("netbox", "prometheus", "grafana", "loki", "oxidized",
                         "kea", "topology_service", "nsot_git", "s3"):
            assert expected in REGISTRY

    def test_unknown_integration_returns_none(self):
        assert get_integration("not-a-tool") is None

    def test_every_client_declares_its_keys(self):
        for name, cls in REGISTRY.items():
            assert cls.name and cls.label and cls.url_key, name
