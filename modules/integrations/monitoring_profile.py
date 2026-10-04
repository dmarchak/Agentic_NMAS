"""The monitoring profile's CONNECTORS (NSOT_PLAN P.9; the operator, 2026-09-30:
they were file-only, so setting them meant editing data/user_settings.json by
hand, a console step the no-console rule forbids).

Not a tool the app reads: the values the profile DERIVES each section from
(`profile_propose.connector_value`). They get a Settings card so they are set
where every other connector is, validated by the schema on save, and a Test
that checks what can be checked:

- snmp_exporter's file is readable and its auth module names a v1/v2c
  community (the value is never returned);
- Telegraf's listener accepts a TCP connection;
- each NTP server answers an SNTP query;
- syslog and traps are one-way UDP: nothing answers them, so they are said
  not testable rather than drawn as passing.
"""

import socket
import struct

from modules.integrations.base import IntegrationClient

#: Bounds from the lab, not a round number: a LAN TCP connect and an SNTP
#: answer each take milliseconds; 2 s is far past both and keeps the Test
#: (and the 60 s health probe) short when something does not answer.
PROBE_TIMEOUT_S = 2.0

SYSLOG_KEYS = ("syslog_host", "syslog_trap_level", "syslog_origin_id",
               "syslog_source_interface", "syslog_heartbeat_seconds")
CONNECTOR_KEYS = ("snmp_exporter_config", "snmp_exporter_auth", "snmp_trap_host",
                  "telemetry_receiver", "ntp_servers")


def sntp_answers(host: str, timeout: float = PROBE_TIMEOUT_S, port: int = 123) -> tuple:
    """(answered, words). One SNTP client request (RFC 4330, mode 3)."""
    pkt = b"\x1b" + 47 * b"\0"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(pkt, (host, port))
            data, _ = s.recvfrom(512)
    except OSError as exc:
        return False, f"{host}: no answer ({exc.strerror or type(exc).__name__})"
    if len(data) < 48:
        return False, f"{host}: answered {len(data)} bytes, not an NTP reply"
    stratum = data[1]
    return (stratum not in (0, 16)), (f"{host}: stratum {stratum}" if stratum not in (0, 16)
                                      else f"{host}: answered but unsynchronised (stratum {stratum})")


def tcp_accepts(addr: str, timeout: float = PROBE_TIMEOUT_S) -> tuple:
    host, _, port = addr.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, f"{addr} accepts a connection"
    except (OSError, ValueError) as exc:
        return False, f"{addr}: {getattr(exc, 'strerror', None) or exc}"


class MonitoringProfileIntegration(IntegrationClient):
    name = "monitoring_profile"
    label = "Monitoring profile"
    url_key = ""
    #: It speaks to no HTTP tool: its keys are the connectors it names.
    http = False
    plain_keys = SYSLOG_KEYS + CONNECTOR_KEYS

    @property
    def url(self) -> str:
        return ""

    def is_configured(self) -> bool:
        return any(self._setting(k) for k in ("syslog_host", "snmp_exporter_config",
                                            "telemetry_receiver", "ntp_servers"))

    def get_config(self) -> dict:
        cfg = {key: self._setting(key) for key in self.plain_keys}
        cfg["_secrets"] = {}
        cfg["_configured"] = self.is_configured()
        return cfg

    def save_config(self, values: dict) -> dict:
        from modules.config import set_user_setting

        if self.list_name:
            # FOR a network (P.8): its own store, through the one write path for lists.
            from modules import list_settings

            updates = {k: values[k] for k in self.plain_keys if k in values}
            return list_settings.write(self.list_name, updates) if updates else {"ok": True}
        for key in self.plain_keys:
            if key in values:
                set_user_setting(key, values[key])
        return {"ok": True}

    def checks(self) -> list:
        """``[{"name", "state": ok|failed|not_set|not_testable, "detail"}]``."""
        from modules.nsot.profile_propose import exporter_community

        out = []
        path, auth = self._setting("snmp_exporter_config") or "", self._setting("snmp_exporter_auth") or ""
        if path:
            value, why = exporter_community(path, auth or "public_v2")
            out.append({"name": "snmp_exporter config", "state": "ok" if value else "failed",
                        "detail": (f"{path}: auth module {auth!r} names a community (not shown)"
                                   if value else why)})
        else:
            out.append({"name": "snmp_exporter config", "state": "not_set",
                        "detail": "not set: the profile's SNMP section falls back to the fleet"})
        recv = self._setting("telemetry_receiver") or ""
        if recv:
            ok, words = tcp_accepts(recv)
            out.append({"name": "Telegraf listener", "state": "ok" if ok else "failed", "detail": words})
        else:
            out.append({"name": "Telegraf listener", "state": "not_set",
                        "detail": "not set: the profile's telemetry section falls back to the fleet"})
        servers = self._setting("ntp_servers") or []
        if servers:
            for host in servers:
                ok, words = sntp_answers(str(host))
                out.append({"name": f"NTP {host}", "state": "ok" if ok else "failed", "detail": words})
        else:
            out.append({"name": "NTP servers", "state": "not_set",
                        "detail": "not set: the profile's NTP section falls back to the fleet"})
        for key, what in (("syslog_host", "syslog"), ("snmp_trap_host", "SNMP traps")):
            val = self._setting(key) or ""
            out.append({"name": f"{what} to {val}" if val else what,
                        "state": "not_testable" if val else "not_set",
                        "detail": (f"{what} is one-way UDP: nothing answers, so it cannot be "
                                   "tested from here" if val else f"{key} is not set")})
        return out

    def test_connection(self) -> dict:
        rows = self.checks()
        failed = [r for r in rows if r["state"] == "failed"]
        words = "; ".join(f"{r['name']}: {r['detail']}" for r in rows)
        if failed:
            return {"ok": False, "error": words, "checks": rows}
        return {"ok": True, "message": words, "checks": rows}
