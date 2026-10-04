"""Prometheus / Thanos Query integration (Phase 0: connection test only)."""

from modules.integrations.base import IntegrationClient


class PrometheusIntegration(IntegrationClient):
    name = "prometheus"
    label = "Prometheus"
    url_key = "prometheus_url"
    secret_keys = ("prometheus_password", "prometheus_bearer_token")
    plain_keys = ("prometheus_auth_mode", "prometheus_username", "prometheus_verify_tls",
                  "prometheus_targets_dir")

    def _auth_headers(self) -> dict:
        mode = self._setting("prometheus_auth_mode", "none")
        if mode == "bearer":
            token = self._secret("prometheus_bearer_token")
            return {"Authorization": f"Bearer {token}"} if token else {}
        return {}

    def session(self):
        s = super().session()
        if self._setting("prometheus_auth_mode", "none") == "basic":
            s.auth = (self._setting("prometheus_username", ""),
                      self._secret("prometheus_password"))
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

    def monitor(self) -> dict:
        """Targets up / total. The one number that says "is scraping working"."""
        r = self._get("api/v1/targets", state="active")
        if not r["ok"]:
            return r
        try:
            targets = r["response"].json().get("data", {}).get("activeTargets", [])
        except Exception as exc:              # noqa: BLE001
            return {"ok": False, "error": f"unreadable response: {exc}"}
        up = sum(1 for t in targets if t.get("health") == "up")
        down = [t.get("labels", {}).get("instance", "?")
                for t in targets if t.get("health") != "up"]
        return {
            "ok": True,
            "metrics": [{"label": "targets up", "value": f"{up}/{len(targets)}"}],
            # Named, because "3/5 up" without saying which two are down is a
            # number the operator has to go elsewhere to act on.
            "detail": [{"text": name, "state": "down"} for name in down[:10]],
        }

    def targets_for(self, address: str) -> dict:
        """``{"ok", "jobs", "count", "error"}``: which ACTIVE targets scrape
        *address*, read-only. Retire uses it to say which scrape targets still
        poll a device NMAS is releasing: they are hand-kept on the host
        (C168), and NMAS does not write them. A target matches by its
        `instance` label's host, the SNMP exporter's `__param_target`, or its
        `__address__` host."""
        r = self._get("api/v1/targets", state="active")
        if not r["ok"]:
            return {"ok": False, "jobs": [], "count": 0, "error": r.get("error", "")}
        try:
            targets = r["response"].json().get("data", {}).get("activeTargets", [])
        except Exception as exc:              # noqa: BLE001
            return {"ok": False, "jobs": [], "count": 0,
                    "error": f"unreadable response: {exc}"}

        def host(value):
            value = str(value or "")
            if value.startswith("["):
                return value[1:value.find("]")]
            return value.rsplit(":", 1)[0] if value.count(":") == 1 else value

        hits = [t for t in targets
                if address and address in (host((t.get("labels") or {}).get("instance")),
                                           (t.get("discoveredLabels") or {}).get("__param_target"),
                                           host((t.get("discoveredLabels") or {}).get("__address__")))]
        jobs = sorted({(t.get("labels") or {}).get("job", "?") for t in hits})
        return {"ok": True, "jobs": jobs, "count": len(hits), "error": ""}
