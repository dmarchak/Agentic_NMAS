"""Grafana integration (Phase 0: connection test only).

Deep links are the default. Embedding needs ``allow_embedding = true`` in
Grafana's config, and auth proxies commonly block iframes, which is why the
link mode exists and is preferred.
"""

from modules.integrations.base import IntegrationClient
from modules.secrets_store import get_secret
from modules.settings_schema import get_setting


class GrafanaIntegration(IntegrationClient):
    name = "grafana"
    label = "Grafana"
    url_key = "grafana_url"
    secret_keys = ("grafana_token",)
    plain_keys = ("grafana_embed_mode", "grafana_device_dashboard_url",
                  "grafana_verify_tls")

    def _auth_headers(self) -> dict:
        token = get_secret("grafana_token")
        return {"Authorization": f"Bearer {token}"} if token else {}

    def test_connection(self) -> dict:
        # /api/health needs no auth on most deployments and reports the version.
        r = self._get("api/health")
        if r["ok"]:
            try:
                data = r["response"].json()
                return {"ok": True, "message": f"Grafana {data.get('version', '?')}"}
            except Exception:
                return {"ok": True, "message": "Connected"}
        # A reachable Grafana behind an auth proxy can 401/403 on /api/health;
        # that still proves the endpoint exists.
        if r.get("status") in (401, 403):
            return {"ok": True, "message": "Reachable (authentication required)"}
        return r

    def monitor(self) -> dict:
        """Reachable, plus the dashboard link.

        No embedding and no iframe: the browser reaches NMAS through the
        Cloudflare tunnel and Grafana is LAN-only, so an iframe would render
        a broken frame for every remote viewer. The link is honest about
        being a link.
        """
        probe = self.test_connection()
        if not probe.get("ok"):
            return probe
        url = get_setting("grafana_device_dashboard_url", "") or self.url
        return {
            "ok": True,
            "metrics": [{"label": "status", "value": probe.get("message", "Connected")}],
            "link": {"href": url, "text": "Open Grafana",
                     "note": "reachable from the LAN only"},
        }
