"""Loki integration (Phase 0: connection test only)."""

from modules.integrations.base import IntegrationClient


class LokiIntegration(IntegrationClient):
    name = "loki"
    label = "Loki"
    url_key = "loki_url"
    secret_keys = ("loki_password", "loki_bearer_token")
    plain_keys = ("loki_auth_mode", "loki_username", "loki_verify_tls",
                  "loki_selector_template")

    def _auth_headers(self) -> dict:
        if self._setting("loki_auth_mode", "none") == "bearer":
            token = self._secret("loki_bearer_token")
            return {"Authorization": f"Bearer {token}"} if token else {}
        return {}

    def session(self):
        s = super().session()
        if self._setting("loki_auth_mode", "none") == "basic":
            s.auth = (self._setting("loki_username", ""), self._secret("loki_password"))
        return s

    def test_connection(self) -> dict:
        # With a credential, ask an endpoint that NEEDS it (C354, P.21: /ready answers without
        # one, so a refused credential read as ready): the label names, the cheapest query.
        if self._setting("loki_auth_mode", "none") in ("basic", "bearer"):
            r = self._get("loki/api/v1/labels")
            if not r["ok"]:
                return r
            return {"ok": True, "message": "Ready; the credential is accepted"}
        # /ready returns text, not JSON.
        r = self._get("ready")
        if not r["ok"]:
            return r
        return {"ok": True, "message": "Ready"}
