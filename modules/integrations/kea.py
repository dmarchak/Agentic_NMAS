"""Kea Control Agent integration (Phase 0: connection test only).

The Control Agent takes JSON commands by POST to the base URL rather than
REST-style paths, so this client does not use the shared ``_get`` helper.
"""

import logging

import requests

from modules.integrations.base import IntegrationClient
from modules.secrets_store import get_secret
from modules.settings_schema import get_setting

log = logging.getLogger(__name__)


class KeaIntegration(IntegrationClient):
    name = "kea"
    label = "Kea DHCP"
    url_key = "kea_url"
    secret_keys = ("kea_password",)
    plain_keys = ("kea_username", "kea_services", "kea_verify_tls")

    def command(self, command: str, service=None) -> dict:
        """Send a Control Agent command. Never raises."""
        if not self.is_configured():
            return {"ok": False, "error": "Not configured — set in Settings"}
        payload = {"command": command}
        services = service or get_setting("kea_services", ["dhcp4"])
        if services:
            payload["service"] = services
        try:
            s = self.session()
            user = get_setting("kea_username", "")
            if user:
                s.auth = (user, get_secret("kea_password"))
            r = s.post(self.url, json=payload, timeout=self.timeout)
            if r.status_code >= 400:
                return {"ok": False, "error": f"HTTP {r.status_code}"}
            return {"ok": True, "result": r.json()}
        except requests.exceptions.ConnectionError:
            return {"ok": False, "error": f"Could not connect to {self.url}"}
        except requests.exceptions.Timeout:
            return {"ok": False, "error": f"Timed out after {self.timeout}s"}
        except Exception as exc:              # noqa: BLE001
            log.warning("kea: %s failed: %s", command, exc)
            return {"ok": False, "error": str(exc)}

    def test_connection(self) -> dict:
        r = self.command("status-get")
        if not r["ok"]:
            return r
        return {"ok": True, "message": "Control Agent responding"}
