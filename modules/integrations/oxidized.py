"""Oxidized (oxidized-web REST) integration (Phase 0: connection test only)."""

from modules.integrations.base import IntegrationClient
from modules.secrets_store import get_secret
from modules.settings_schema import get_setting


class OxidizedIntegration(IntegrationClient):
    name = "oxidized"
    label = "Oxidized"
    url_key = "oxidized_url"
    secret_keys = ("oxidized_password",)
    plain_keys = ("oxidized_username", "oxidized_node_identity", "oxidized_verify_tls")

    def session(self):
        s = super().session()
        user = get_setting("oxidized_username", "")
        if user:
            s.auth = (user, get_secret("oxidized_password"))
        return s

    def test_connection(self) -> dict:
        r = self._get("nodes.json")
        if not r["ok"]:
            return r
        try:
            nodes = r["response"].json()
            return {"ok": True, "message": f"{len(nodes)} node(s)"}
        except Exception:
            return {"ok": True, "message": "Connected"}
