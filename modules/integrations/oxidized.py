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

    def monitor(self) -> dict:
        """Per-device last fetch status and time.

        This is the backup half of "version control": a device Oxidized has
        stopped fetching stops appearing in history, and nothing else in the
        GUI says so.
        """
        r = self._get("nodes.json")
        if not r["ok"]:
            return r
        try:
            nodes = r["response"].json()
        except Exception as exc:              # noqa: BLE001
            return {"ok": False, "error": f"unreadable response: {exc}"}

        rows, failing = [], 0
        for node in nodes if isinstance(nodes, list) else []:
            status = (node.get("status") or "").lower()
            good = status == "success"
            failing += 0 if good else 1
            rows.append({
                "text": node.get("name") or node.get("ip") or "?",
                "value": (node.get("time") or "never")[:19],
                "state": "up" if good else "down",
                "note": "" if good else (status or "no fetch recorded"),
            })
        rows.sort(key=lambda row: (row["state"] == "up", row["text"]))
        return {
            "ok": True,
            "metrics": [
                {"label": "nodes", "value": str(len(rows))},
                {"label": "failing", "value": str(failing),
                 "state": "down" if failing else "up"},
            ],
            "detail": rows,
        }
