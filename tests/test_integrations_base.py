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


# TestSecretHandling left with the clients' get_config and save_config (7.8, 2026-10-15): their
# one caller was today's Integrations card. v2's cards draw a secret as set or not set and keep
# a blank one (tests/test_settings_v2.py, tests/test_installation_settings.py).


class TestRegistry:
    def test_expected_integrations_registered(self):
        for expected in ("netbox", "prometheus", "grafana", "loki",
                         "kea", "nsot_git", "s3"):
            assert expected in REGISTRY
        assert "oxidized" not in REGISTRY, "Oxidized is retired (Phase 3)"

    def test_unknown_integration_returns_none(self):
        assert get_integration("not-a-tool") is None

    def test_every_client_declares_its_keys(self):
        for name, cls in REGISTRY.items():
            # A client that speaks to no HTTP tool (the monitoring profile's
            # connectors) declares `http = False` and owns plain keys instead.
            assert cls.name and cls.label, name
            assert cls.url_key or (getattr(cls, "http", True) is False and cls.plain_keys), name
