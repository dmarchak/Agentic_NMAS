"""Grafana integration: the connection test, panel queries and a silence's read (reads), and
the silence writes: set or moved for a planned restart (`put_silence`, B3 of the W2 walk,
2026-10-17) and expired (`expire_silence`, C1089). Every write sent is recorded, whoever it was
for and whatever Grafana answered (`modules/grafana_writes.py`, History's "Grafana writes").

Deep links are the default. Embedding needs ``allow_embedding = true`` in
Grafana's config, and auth proxies commonly block iframes, which is why the
link mode exists and is preferred.

**The writes.** Mercury writes nothing else to Grafana. A planned-restart window
(`modules/restarts.py`, `record_planned`) silences the alerts on the devices it covers, as
the person who declared it and with their reason, so a reload does not page anyone; the
silence's id is kept on the window, and ending the window early moves its end. The write
refuses any silence that is not that shape (matchers on `device` or `instance` only, a person,
a reason, an end after its start), is sent ONCE (a retried POST could set two silences), and
never raises: a silence that could not be set is said on the window's result. A silence is
expired only by its id, as a person with a reason (`expire_silence`).
"""

import logging
import re

from modules.integrations.base import IntegrationClient, _refusal_words

log = logging.getLogger(__name__)

#: Grafana's own Alertmanager: the silences endpoint (create, or update by id).
SILENCES_PATH = "api/alertmanager/grafana/api/v2/silences"
#: One silence by its id: read (GET) or expire (DELETE).
SILENCE_PATH = "api/alertmanager/grafana/api/v2/silence/{id}"
_SILENCE_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
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
                    comment: str, silence_id: str = "", timeout: float = 10.0,
                    verified: str = "", via: str = "") -> dict:
        """See `_put_silence`; every silence SENT is recorded (`grafana_writes`), whatever
        Grafana answered, as *created_by* (*verified*: how they were established) through
        *via* (what asked for it)."""
        got = self._put_silence(matchers=matchers, starts_at=starts_at, ends_at=ends_at,
                                created_by=created_by, comment=comment, silence_id=silence_id,
                                timeout=timeout)
        if got.get("sent"):
            self._record("silence_moved" if silence_id else "silence_set", got,
                         by=created_by, verified=verified, via=via, matchers=matchers,
                         ends_at=ends_at, comment=comment, silence_id=silence_id)
        return got

    def _record(self, action: str, got: dict, *, by: str, verified: str, via: str,
                matchers: list = None, ends_at: str = "", comment: str = "",
                silence_id: str = "") -> None:
        """One write sent, kept; a record that could not be written is said on the result."""
        from modules import grafana_writes

        kept = grafana_writes.record(action=action, by=by, ok=bool(got.get("ok")),
                                     silence_id=got.get("id") or silence_id,
                                     matchers=matchers, ends_at=ends_at,
                                     error=got.get("error", ""), verified=verified, via=via,
                                     comment=comment, network=self.list_name)
        if not kept["ok"]:
            got["record_error"] = kept["error"]

    def get_silence(self, silence_id: str, timeout: float = 10.0) -> dict:
        """READ one silence by its id: ``{"ok", "silence": {"id", "state", "starts_at",
        "ends_at", "matchers", "created_by", "comment"}, "error"}``; never raises."""
        if not _SILENCE_ID.match(silence_id or ""):
            return {"ok": False, "error": f"not a silence id: {silence_id[:70]!r}"}
        r = self._get(SILENCE_PATH.format(id=silence_id))
        if not r["ok"]:
            return {"ok": False, "error": r.get("error", "not read")}
        try:
            s = r["response"].json() or {}
        except ValueError:
            return {"ok": False, "error": "Grafana's answer is not JSON"}
        return {"ok": True, "error": "", "silence": {
            "id": s.get("id", ""), "state": (s.get("status") or {}).get("state", ""),
            "starts_at": s.get("startsAt", ""), "ends_at": s.get("endsAt", ""),
            "created_by": s.get("createdBy", ""), "comment": s.get("comment", ""),
            "matchers": [f"{m.get('name')}{'=~' if m.get('isRegex') else '='}{m.get('value')}"
                         for m in s.get("matchers") or []]}}

    def expire_silence(self, silence_id: str, *, by: str, reason: str, verified: str = "",
                       via: str = "", timeout: float = 10.0) -> dict:
        """THE other write: expire one silence by its id, now. ``{"ok", "error"}``; never
        raises. Refused before sending: no id of a silence's shape, no person, no reason.
        Recorded once sent, whatever Grafana answered."""
        problem = ("no silence id" if not _SILENCE_ID.match(silence_id or "") else
                   "no person to record it as" if not (by or "").strip() else
                   "no reason" if not (reason or "").strip() else "")
        if problem:
            return {"ok": False, "error": f"refused before sending: {problem}"}
        if not self.is_configured():
            return {"ok": False, "error": "Grafana is not configured for this network"}
        import requests

        try:
            r = requests.delete(f"{self.url}/{SILENCE_PATH.format(id=silence_id)}",
                                timeout=timeout, verify=self.verify_tls,
                                headers={"Accept": "application/json", **self._auth_headers()})
        except Exception as exc:                  # noqa: BLE001 - said on the result
            got = {"ok": False, "id": silence_id, "sent": True,
                   "error": f"Grafana did not answer: {type(exc).__name__}"}
        else:
            if r.status_code in (401, 403):
                got = {"ok": False, "id": silence_id, "sent": True, "status": r.status_code,
                       "error": f"HTTP {r.status_code}: Grafana refused the tool's credential "
                                "to expire a silence"}
            elif r.status_code >= 400:
                why = _refusal_words(r)
                got = {"ok": False, "id": silence_id, "sent": True, "status": r.status_code,
                       "error": f"HTTP {r.status_code}" + (f": {why}" if why else "")}
            else:
                got = {"ok": True, "id": silence_id, "sent": True, "error": ""}
                log.info("grafana: silence %s expired by %s (%s)", silence_id, by, reason)
        self._record("silence_expired", got, by=by, verified=verified, via=via,
                     comment=reason.strip(), silence_id=silence_id)
        return got

    def _put_silence(self, *, matchers: list, starts_at: str, ends_at: str, created_by: str,
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
            return {"ok": False, "id": "", "sent": True, "error": f"Grafana did not answer: "
                                                                  f"{type(exc).__name__}"}
        if r.status_code in (401, 403):
            return {"ok": False, "id": "", "sent": True, "status": r.status_code,
                    "refused": True,
                    "error": f"HTTP {r.status_code}: Grafana refused the tool's credential for "
                             "a silence (its account needs permission to create silences)"}
        if r.status_code >= 400:
            why = _refusal_words(r)
            try:
                why = why or str((r.json() or {}).get("message") or "")
            except ValueError:
                pass
            return {"ok": False, "id": "", "sent": True, "status": r.status_code,
                    "error": f"HTTP {r.status_code}" + (f": {why}" if why else "")}
        try:
            sid = str((r.json() or {}).get("silenceID") or "")
        except ValueError:
            sid = ""
        if not sid:
            return {"ok": False, "id": "", "sent": True,
                    "error": "Grafana answered without a silence id, so whether a silence "
                             "was set is not known"}
        log.info("grafana: silence %s %s by %s until %s (%s)", sid,
                 "moved" if silence_id else "set", created_by, ends_at,
                 ", ".join(f"{m['name']}{'=~' if m.get('isRegex') else '='}{m.get('value')}"
                           for m in matchers))
        return {"ok": True, "id": sid, "sent": True, "error": ""}

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
