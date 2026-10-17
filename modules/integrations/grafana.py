"""Grafana integration: the connection test, panel queries (reads), and ONE write: a
silence for a planned restart (`put_silence`, B3 of the W2 walk, 2026-10-17).

Deep links are the default. Embedding needs ``allow_embedding = true`` in
Grafana's config, and auth proxies commonly block iframes, which is why the
link mode exists and is preferred.

**The one write.** Mercury writes nothing else to Grafana. A planned-restart window
(`modules/restarts.py`, `record_planned`) silences the alerts on the devices it covers, as
the person who declared it and with their reason, so a reload does not page anyone; the
silence's id is kept on the window, and ending the window early moves its end. The write
refuses any silence that is not that shape (matchers on `device` or `instance` only, a person,
a reason, an end after its start), is sent ONCE (a retried POST could set two silences), and
never raises: a silence that could not be set is said on the window's result.
"""

import logging
import re

from modules.integrations.base import IntegrationClient, _refusal_words

log = logging.getLogger(__name__)

#: Grafana's own Alertmanager: the silences endpoint (create, or update by id).
SILENCES_PATH = "api/alertmanager/grafana/api/v2/silences"
#: The labels a planned-restart silence may match: the device a rule names (telemetry,
#: heartbeat, the syslog rule's origin-id) and the polled address an SNMP rule carries
#: (`modules/readers/grafana_alerts.py`, "Which device"). Nothing else is silenced.
SILENCE_LABELS = ("device", "instance")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


class GrafanaIntegration(IntegrationClient):
    name = "grafana"
    label = "Grafana"
    url_key = "grafana_url"
    secret_keys = ("grafana_token",)
    plain_keys = ("grafana_embed_mode", "grafana_verify_tls",
                  "grafana_fleet_dashboard_uid", "grafana_device_dashboard_uid",
                  "grafana_device_variable", "grafana_device_variable_value",
                  "grafana_token_expires")
    #: The one path `query` asks: Grafana's query endpoint, a read (History › Query's Code
    #: mode asks nothing else, modules/history_query.READS).
    QUERY_PATH = "api/ds/query"

    def query(self, body: dict, timeout: float = 20.0) -> dict:
        """Run panel queries through Grafana's own query endpoint
        (`api/ds/query`), exactly as Grafana's front end runs them: a POST that
        READS, with the Viewer token, so a panel's data source and its macros
        (`$__rate_interval`, `$__range`: measured, the back end expands them)
        need no second configuration here. Never raises."""
        if not self.is_configured():
            return {"ok": False, "error": "Grafana is not configured — set it in Settings"}
        url = f"{self.url}/{self.QUERY_PATH}"
        try:
            r = self.session().post(url, json=body, timeout=timeout)
        except Exception as exc:                  # noqa: BLE001 - never raise into a handler
            return {"ok": False, "error": f"Grafana did not answer: {type(exc).__name__}"}
        if r.status_code >= 400:
            try:
                why = (r.json() or {}).get("message") or ""
            except ValueError:
                why = ""
            return {"ok": False, "error": f"HTTP {r.status_code}" + (f": {why}" if why else ""),
                    "status": r.status_code}
        try:
            return {"ok": True, "body": r.json()}
        except ValueError:
            return {"ok": False, "error": "Grafana's answer is not JSON"}

    def put_silence(self, *, matchers: list, starts_at: str, ends_at: str, created_by: str,
                    comment: str, silence_id: str = "", timeout: float = 10.0) -> dict:
        """THE write: set (or, with *silence_id*, move the end of) one silence in Grafana's
        Alertmanager. ``{"ok", "id", "error"}``; never raises.

        Refused before anything is sent: a matcher on a label other than `SILENCE_LABELS`, no
        person, no reason, or an end not after its start (UTC ``...Z`` strings). Sent once,
        with no retry: two POSTs could leave two silences. Grafana answers a moved end with
        the same id when the silence is active and its start and matchers are unchanged, and
        a new id otherwise; the id returned is the one to keep."""
        names = [m.get("name") for m in matchers or []]
        problem = (
            "no matcher" if not matchers else
            f"a matcher on {', '.join(n for n in names if n not in SILENCE_LABELS)}, and a "
            f"planned-restart silence matches only {', '.join(SILENCE_LABELS)}"
            if any(n not in SILENCE_LABELS for n in names) else
            "no person to record it as" if not (created_by or "").strip() else
            "no reason" if not (comment or "").strip() else
            f"a time that is not UTC ({starts_at!r}, {ends_at!r})"
            if not (_UTC.match(starts_at or "") and _UTC.match(ends_at or "")) else
            f"an end ({ends_at}) not after its start ({starts_at})"
            if ends_at <= starts_at else "")
        if problem:
            return {"ok": False, "id": "", "error": f"refused before sending: {problem}"}
        if not self.is_configured():
            return {"ok": False, "id": "", "error": "Grafana is not configured for this "
                                                    "network"}
        import requests

        body = {"matchers": [{"name": m["name"], "value": str(m.get("value", "")),
                              "isRegex": bool(m.get("isRegex")), "isEqual": True}
                             for m in matchers],
                "startsAt": starts_at, "endsAt": ends_at, "createdBy": created_by.strip(),
                "comment": comment.strip()}
        if silence_id:
            body["id"] = silence_id
        try:
            r = requests.post(f"{self.url}/{SILENCES_PATH}", json=body, timeout=timeout,
                              headers={"Accept": "application/json", **self._auth_headers()},
                              verify=self.verify_tls)
        except Exception as exc:                  # noqa: BLE001 - said on the window
            return {"ok": False, "id": "", "error": f"Grafana did not answer: "
                                                    f"{type(exc).__name__}"}
        if r.status_code in (401, 403):
            return {"ok": False, "id": "", "status": r.status_code, "refused": True,
                    "error": f"HTTP {r.status_code}: Grafana refused the tool's credential for "
                             "a silence (its account needs permission to create silences)"}
        if r.status_code >= 400:
            why = _refusal_words(r)
            try:
                why = why or str((r.json() or {}).get("message") or "")
            except ValueError:
                pass
            return {"ok": False, "id": "", "status": r.status_code,
                    "error": f"HTTP {r.status_code}" + (f": {why}" if why else "")}
        try:
            sid = str((r.json() or {}).get("silenceID") or "")
        except ValueError:
            sid = ""
        if not sid:
            return {"ok": False, "id": "", "error": "Grafana answered without a silence id, so "
                                                    "whether a silence was set is not known"}
        log.info("grafana: silence %s %s by %s until %s (%s)", sid,
                 "moved" if silence_id else "set", created_by, ends_at,
                 ", ".join(f"{m['name']}{'=~' if m.get('isRegex') else '='}{m.get('value')}"
                           for m in matchers))
        return {"ok": True, "id": sid, "error": ""}

    def _auth_headers(self) -> dict:
        token = self._secret("grafana_token")
        return {"Authorization": f"Bearer {token}"} if token else {}

    def test_connection(self) -> dict:
        # With a token, ask an endpoint that NEEDS it (C354, P.21: /api/health answers without
        # one, so a refused token read as up until a Grafana reader raised 401). A refusal is
        # its own state, naming the token, never "reachable".
        if self._secret("grafana_token"):
            r = self._get("api/user")
            if r["ok"]:
                return {"ok": True, "message": "Connected; the token is accepted"}
            return r
        # No token: /api/health needs no auth on most deployments and reports the version.
        r = self._get("api/health")
        if r["ok"]:
            try:
                data = r["response"].json()
                return {"ok": True, "message": f"Grafana {data.get('version', '?')}"}
            except Exception:
                return {"ok": True, "message": "Connected"}
        return r
