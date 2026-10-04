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

    def monitor(self, *, limit: int = 10, hours: int = 6) -> dict:
        """The last few log lines, newest first.

        Uses `loki_selector_template` when it has no placeholder left to fill;
        a template naming a specific device is not a fleet query, so the card
        falls back to a bare job matcher rather than silently showing one
        device's logs under a heading that says otherwise.
        """
        import time

        selector = self._setting("loki_selector_template", '{host="{ip}"}') or ""
        if "{ip}" in selector or "{hostname}" in selector:
            selector = '{job=~".+"}'
        now = time.time()
        r = self._get("loki/api/v1/query_range", query=selector, limit=limit,
                      start=int((now - hours * 3600) * 1e9), end=int(now * 1e9),
                      direction="backward")
        if not r["ok"]:
            return r
        try:
            streams = r["response"].json().get("data", {}).get("result", [])
        except Exception as exc:              # noqa: BLE001
            return {"ok": False, "error": f"unreadable response: {exc}"}

        lines = []
        for stream in streams:
            labels = stream.get("stream", {})
            source = labels.get("host") or labels.get("job") or ""
            for stamp, text in stream.get("values", []):
                lines.append((int(stamp), source, text))
        lines.sort(reverse=True)
        return {
            "ok": True,
            "metrics": [{"label": "lines", "value": str(len(lines)),
                         "suffix": f"last {hours}h"}],
            "detail": [{"text": f"{source} {text}".strip()[:160]}
                       for _stamp, source, text in lines[:limit]],
        }
