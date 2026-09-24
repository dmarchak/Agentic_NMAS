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

    #: Kea lease states. 0 is the only one that means "a client is using
    #: this address"; 1 is declined and 2 is expired-reclaimed.
    LEASE_STATE_ACTIVE = 0

    @staticmethod
    def _active_leases(payload, now=None) -> list:
        """Leases in state 0 that have not expired.

        The same rule for both families, deliberately: counting v4 one way
        and v6 another would make "v4: 3 - v6: 1" two different measurements
        printed as though they were one.

        A lease with neither `expire` nor `cltt`/`valid-lft` is KEPT. Dropping
        a lease whose expiry cannot be read would undercount silently, and a
        quiet undercount on this card is exactly the failure that hid h4.
        """
        import time as _time

        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        leases = ((payload or {}).get("arguments") or {}).get("leases") or []
        now = _time.time() if now is None else now

        active = []
        for lease in leases:
            if lease.get("state", 0) != KeaIntegration.LEASE_STATE_ACTIVE:
                continue
            expire = lease.get("expire")
            if expire is None:
                cltt, lifetime = lease.get("cltt"), lease.get("valid-lft")
                expire = (cltt + lifetime) if (cltt is not None
                                               and lifetime is not None) else None
            if expire is not None and expire <= now:
                continue
            active.append(lease)
        return active

    def monitor(self) -> dict:
        """Active lease counts, v4 and v6.

        `lease4-get-all` / `lease6-get-all` rather than statistics: the
        statistic names are per-subnet and differ between deployments, so
        reading them means guessing a subnet id. Counting what comes back
        cannot be wrong about which subnet it counted.

        **Both families, because counting only v4 makes an IPv6-only host
        invisible.** Measured: h4 sits on the IPv6-only VLAN and only ever
        holds a DHCPv6 lease, so it never appeared on this card -- and the
        card said "active leases: 3" rather than anything that hinted a whole
        family was unread. A number with a silent scope is worse than a
        missing one.

        **The service is named explicitly per query**, not taken from
        `kea_services`. That setting may list both, and sending
        `lease4-get-all` to `dhcp6` is an error rather than an empty answer.

        Each family fails on its own. One dead service reports its reason
        beside the other's count instead of blanking the card.
        """
        families = (("v4", "lease4-get-all", "dhcp4"),
                    ("v6", "lease6-get-all", "dhcp6"))

        counts, detail, errors = [], [], []
        for label, command, service in families:
            result = self.command(command, service=[service])
            if not result.get("ok"):
                counts.append(f"{label}: unavailable")
                errors.append({"text": f"{service}: {result.get('error', 'failed')}",
                               "state": "down"})
                continue
            leases = self._active_leases(result.get("result"))
            counts.append(f"{label}: {len(leases)}")
            for lease in leases[:10]:
                detail.append({
                    "text": (lease.get("hostname") or lease.get("hw-address")
                             or lease.get("duid") or "?"),
                    "value": lease.get("ip-address", ""),
                    "note": label,
                })

        return {
            # True while ANY family answered: a v6 outage must not hide the
            # v4 count behind a card-wide error.
            "ok": len(errors) < len(families),
            "error": "; ".join(e["text"] for e in errors) if len(errors) == len(families) else "",
            "metrics": [{"label": "active leases",
                         "value": " \u00b7 ".join(counts),
                         "state": "down" if errors else "up"}],
            "detail": errors + detail,
        }

    # ── reservations ────────────────────────────────────────────────────────

    #: A reservation lookup that could not be performed. **Not "no
    #: reservation"** — absent and unreadable are different facts, and a
    #: precondition that could not be checked has not passed.
    UNKNOWN = "unknown"
    RESERVED = "reserved"
    NOT_RESERVED = "not_reserved"

    def reservation_for(self, mac: str) -> dict:
        """Is there a **host reservation** for *mac*?

        ``{"state": reserved | not_reserved | unknown, "address": str,
        "source": str, "error": str}``

        **A dynamic lease is not an address a source of truth can record.** It
        is correct on the day it is written and wrong at some renewal the tool
        is not watching — the two-stores-disagreeing shape with a clock
        attached, and nothing in this system would notice: the manifest, the
        CSV and NetBox would all agree with each other and all disagree with
        the device.

        Two sources, because one of them needs a hook library that is not
        always loaded:

        * ``reservation-get`` (the ``host_cmds`` hook), authoritative;
        * otherwise ``config-get``, scanning the subnets' own
          ``reservations`` — which is where a lab defines them.

        Neither readable is :data:`UNKNOWN`, never :data:`NOT_RESERVED`.
        """
        wanted = (mac or "").strip().lower().replace("-", ":")
        if not wanted:
            return {"state": self.UNKNOWN, "address": "", "source": "",
                    "error": "no MAC address given"}

        probe = self.command("reservation-get-all")
        entries, source = None, ""
        if probe.get("ok"):
            entries, source = self._reservations_from(probe["result"]), "host_cmds"
        if entries is None:
            config = self.command("config-get")
            if not config.get("ok"):
                return {"state": self.UNKNOWN, "address": "", "source": "",
                        "error": ("Kea could not be asked: "
                                  f"{config.get('error') or probe.get('error')}")}
            entries = self._reservations_from_config(config["result"])
            source = "config"
        if entries is None:
            return {"state": self.UNKNOWN, "address": "", "source": source,
                    "error": "Kea's answer could not be read"}

        for entry in entries:
            if (entry.get("hw-address") or "").strip().lower() == wanted:
                return {"state": self.RESERVED,
                        "address": entry.get("ip-address", ""),
                        "source": source, "error": ""}
        return {"state": self.NOT_RESERVED, "address": "", "source": source,
                "error": ""}

    @staticmethod
    def _reservations_from(result) -> list:
        """Reservations out of a ``reservation-get-all`` response."""
        rows = result if isinstance(result, list) else [result]
        found = []
        for row in rows:
            if not isinstance(row, dict):
                return None
            if row.get("result") not in (0, None):
                return None
            hosts = (row.get("arguments") or {}).get("hosts")
            if hosts is None:
                return None
            found.extend(h for h in hosts if isinstance(h, dict))
        return found

    @staticmethod
    def _reservations_from_config(result) -> list:
        """Reservations defined in the server's own configuration."""
        rows = result if isinstance(result, list) else [result]
        found = []
        for row in rows:
            if not isinstance(row, dict):
                return None
            arguments = row.get("arguments") or {}
            dhcp4 = arguments.get("Dhcp4")
            if not isinstance(dhcp4, dict):
                continue
            for subnet in dhcp4.get("subnet4") or []:
                found.extend(r for r in (subnet.get("reservations") or [])
                             if isinstance(r, dict))
            found.extend(r for r in (dhcp4.get("reservations") or [])
                         if isinstance(r, dict))
        return found
