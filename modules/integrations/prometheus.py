"""Prometheus / Thanos Query integration (Phase 0: connection test only)."""

from modules.integrations.base import IntegrationClient
from modules.secrets_store import get_secret
from modules.settings_schema import get_setting


class PrometheusIntegration(IntegrationClient):
    name = "prometheus"
    label = "Prometheus"
    url_key = "prometheus_url"
    secret_keys = ("prometheus_password", "prometheus_bearer_token")
    plain_keys = ("prometheus_auth_mode", "prometheus_username", "prometheus_verify_tls")

    def _auth_headers(self) -> dict:
        mode = get_setting("prometheus_auth_mode", "none")
        if mode == "bearer":
            token = get_secret("prometheus_bearer_token")
            return {"Authorization": f"Bearer {token}"} if token else {}
        return {}

    def session(self):
        s = super().session()
        if get_setting("prometheus_auth_mode", "none") == "basic":
            s.auth = (get_setting("prometheus_username", ""),
                      get_secret("prometheus_password"))
        return s

    def test_connection(self) -> dict:
        # Works unchanged against Thanos Query, which serves the same API.
        r = self._get("api/v1/status/buildinfo")
        if not r["ok"]:
            return r
        try:
            data = r["response"].json().get("data", {})
            return {"ok": True, "message": f"Prometheus {data.get('version', '?')}"}
        except Exception:
            return {"ok": True, "message": "Connected"}
