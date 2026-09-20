"""NetBox integration settings wrapper.

The working NetBox client stays in :mod:`modules.netbox_client`; this class
exposes its settings through the shared Integrations panel and carries the
``allow_writes`` gate.
"""

from modules.integrations.base import IntegrationClient
from modules.secrets_store import get_secret
from modules.settings_schema import get_setting


class NetBoxIntegration(IntegrationClient):
    name = "netbox"
    label = "NetBox"
    url_key = "netbox_url"
    secret_keys = ("netbox_token",)
    plain_keys = ("netbox_auth_scheme", "netbox_verify_tls", "netbox_allow_writes",
                  "netbox_remove_on_list_delete")

    def is_configured(self) -> bool:
        return bool(self.url and get_secret("netbox_token"))

    def _auth_headers(self) -> dict:
        token = get_secret("netbox_token")
        if not token:
            return {}
        scheme = get_setting("netbox_auth_scheme", "Bearer")
        if scheme not in ("Bearer", "Token"):
            scheme = "Bearer"
        return {"Authorization": f"{scheme} {token}"}

    @property
    def allow_writes(self) -> bool:
        return bool(get_setting("netbox_allow_writes", False))

    def test_connection(self) -> dict:
        if not self.url:
            return {"ok": False, "error": "Not configured — set in Settings"}
        if not get_secret("netbox_token"):
            return {"ok": False, "error": "API token is not set"}
        r = self._get("api/status/")
        if not r["ok"]:
            return r
        try:
            data = r["response"].json()
            return {"ok": True, "message": f"NetBox {data.get('netbox-version', '?')}",
                    "version": data.get("netbox-version", "")}
        except Exception:
            return {"ok": True, "message": "Connected"}
