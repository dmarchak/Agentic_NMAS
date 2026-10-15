"""NetBox integration settings wrapper.

The working NetBox client stays in :mod:`modules.netbox_client`; this class
exposes its settings through the shared Integrations panel and carries the
``allow_writes`` gate.
"""

from modules.integrations.base import IntegrationClient


class NetBoxIntegration(IntegrationClient):
    name = "netbox"
    label = "NetBox"
    url_key = "netbox_url"
    secret_keys = ("netbox_token",)
    plain_keys = ("netbox_auth_scheme", "netbox_verify_tls", "netbox_allow_writes")

    def is_configured(self) -> bool:
        return bool(self.url and self._secret("netbox_token"))

    def _auth_headers(self) -> dict:
        token = self._secret("netbox_token")
        if not token:
            return {}
        scheme = self._setting("netbox_auth_scheme", "Bearer")
        if scheme not in ("Bearer", "Token"):
            scheme = "Bearer"
        return {"Authorization": f"{scheme} {token}"}

    @property
    def allow_writes(self) -> bool:
        return bool(self._setting("netbox_allow_writes", False))

    def test_connection(self) -> dict:
        if not self.url:
            return {"ok": False, "error": "Not configured — set in Settings"}
        if not self._secret("netbox_token"):
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

    def test_now(self) -> dict:
        """A person's Test (Settings › Installation, the NetBox connection card): with what
        is saved, in the card's own auth scheme, persisting nothing. NetBox's own reason for a
        refusal, and every type the tool reads asked by name (C468, `netbox_client.
        test_connection`): `api/status/` needs no permission, so a token missing a view
        passed `test_connection` above and failed later, in a sync. The integrations reader
        keeps `test_connection`, one request a minute."""
        from modules import netbox_client

        if not self.url:
            return {"ok": False, "error": "Not configured — set in Settings"}
        token = self._secret("netbox_token")
        if not token:
            return {"ok": False, "error": "API token is not set"}
        scheme = self._setting("netbox_auth_scheme", "Bearer")
        ok, said = netbox_client.test_connection(
            self.url, token, self.verify_tls, persist_scheme=False,
            schemes=(scheme if scheme in ("Bearer", "Token") else "Bearer",))
        return {"ok": True, "message": said} if ok else {"ok": False, "error": said}
