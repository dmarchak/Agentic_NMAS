"""Proxmox VE integration: READ-ONLY, for watching the nightly VM images (B6).

`job_health` cannot see Proxmox, so a vzdump job that fails, stops running,
or fills its destination would be C14 again: evidence on a host nobody reads.
This client reads four things through the Proxmox API and nothing else, with
an API token holding the PVEAuditor role (docs/VM_IMAGES.md section 6):

* the backups on the destination storage (newest image per VM, its size);
* the recent vzdump tasks (did the last run fail);
* the destination storage's status (mounted, and how much is free);
* the node's LVM-thin pools (data and metadata use).

The API wraps every answer as ``{"data": ...}``. Each method returns
``{"ok": True, "data": ...}`` or ``{"ok": False, "error": ...}`` and never
raises, like every integration.
"""

import logging

from modules.integrations.base import IntegrationClient
from modules.secrets_store import get_secret
from modules.settings_schema import get_setting

log = logging.getLogger(__name__)


class ProxmoxIntegration(IntegrationClient):
    name = "proxmox"
    label = "Proxmox VE"
    url_key = "proxmox_url"
    secret_keys = ("proxmox_token_secret",)
    plain_keys = ("proxmox_node", "proxmox_token_id", "proxmox_backup_storage",
                  "proxmox_backup_vmids", "proxmox_verify_tls")

    # ── configuration ───────────────────────────────────────────────────────

    @property
    def node(self) -> str:
        return (get_setting("proxmox_node", "") or "").strip()

    @property
    def storage(self) -> str:
        return (get_setting("proxmox_backup_storage", "") or "").strip()

    def vmids(self) -> list:
        """``proxmox_backup_vmids`` is text (``"100,102"``), so the settings
        card can carry it; a token that is not a number is an error, never
        silently dropped, because a dropped VM is a VM nobody watches."""
        raw = str(get_setting("proxmox_backup_vmids", "") or "")
        out, bad = [], []
        for token in raw.replace(" ", ",").split(","):
            if not token:
                continue
            (out if token.isdigit() else bad).append(token)
        if bad:
            raise ValueError(f"proxmox_backup_vmids holds non-numeric entries: {', '.join(bad)}")
        return [int(v) for v in out]

    def missing_settings(self) -> list:
        missing = [k for k in ("proxmox_url", "proxmox_node", "proxmox_token_id",
                               "proxmox_backup_storage", "proxmox_backup_vmids")
                   if not str(get_setting(k, "") or "").strip()]
        if not get_secret("proxmox_token_secret", ""):
            missing.append("proxmox_token_secret")
        return missing

    def is_configured(self) -> bool:
        return not self.missing_settings()

    def _auth_headers(self) -> dict:
        token_id = (get_setting("proxmox_token_id", "") or "").strip()
        secret = get_secret("proxmox_token_secret", "")
        if not (token_id and secret):
            return {}
        return {"Authorization": f"PVEAPIToken={token_id}={secret}"}

    # ── reads ───────────────────────────────────────────────────────────────

    def _data(self, path: str, **params) -> dict:
        result = self._get(f"api2/json/{path}", **params)
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error", "request failed")}
        try:
            return {"ok": True, "data": result["response"].json().get("data")}
        except ValueError as exc:
            return {"ok": False, "error": f"not JSON: {exc}"}

    def test_connection(self) -> dict:
        result = self._data("version")
        if not result["ok"]:
            return result
        return {"ok": True, "message": f"Proxmox VE {(result['data'] or {}).get('version', '?')}"}

    def backups(self) -> dict:
        return self._data(f"nodes/{self.node}/storage/{self.storage}/content",
                          content="backup")

    def vzdump_tasks(self, limit: int = 50) -> dict:
        return self._data(f"nodes/{self.node}/tasks", typefilter="vzdump",
                          limit=limit, source="all")

    def storage_status(self) -> dict:
        return self._data(f"nodes/{self.node}/storage/{self.storage}/status")

    def thin_pools(self) -> dict:
        return self._data(f"nodes/{self.node}/disks/lvmthin")
