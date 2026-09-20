"""Loki integration (Phase 0: connection test only)."""

from modules.integrations.base import IntegrationClient
from modules.secrets_store import get_secret
from modules.settings_schema import get_setting


class LokiIntegration(IntegrationClient):
    name = "loki"
    label = "Loki"
    url_key = "loki_url"
    secret_keys = ("loki_password", "loki_bearer_token")
    plain_keys = ("loki_auth_mode", "loki_username", "loki_verify_tls",
                  "loki_selector_template")

    def _auth_headers(self) -> dict:
        if get_setting("loki_auth_mode", "none") == "bearer":
            token = get_secret("loki_bearer_token")
            return {"Authorization": f"Bearer {token}"} if token else {}
        return {}

    def session(self):
        s = super().session()
        if get_setting("loki_auth_mode", "none") == "basic":
            s.auth = (get_setting("loki_username", ""), get_secret("loki_password"))
        return s

    def test_connection(self) -> dict:
        # /ready returns text, not JSON.
        r = self._get("ready")
        if not r["ok"]:
            return r
        return {"ok": True, "message": "Ready"}
