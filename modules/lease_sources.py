"""DHCP leases for the endpoint layer, through an optional, generic source (PHASE8_PLAN 15.15;
the operator, 2026-10-26: "DHCP leases through an optional integration, Kea first, the
interface generic").

A source is a function of the network that answers ``{"state", "why", "leases", "source"}``,
each lease ``{"mac", "address", "hostname", "family", "ends", "source"}``. Mercury reads every
registered source and joins them; a source that is not configured says so, and is never read
as "no leases". Kea's, the first, reads the DHCP reader's stored value (`readers/dhcp`), so the
endpoint layer asks Kea nothing itself.
"""

import logging

log = logging.getLogger(__name__)

#: The registered sources, by name: name -> function(network) -> answer.
SOURCES = {}


def register(name: str, fn) -> None:
    SOURCES[name] = fn


def leases(network: str) -> dict:
    """Every registered source's leases for *network*: ``{"leases", "said"}``, *said* naming
    each source that could not answer and why."""
    out, said = [], []
    for name, fn in sorted(SOURCES.items()):
        try:
            got = fn(network)
        except Exception as exc:                        # noqa: BLE001 (said, never raised)
            said.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        if got.get("state") != "read":
            said.append(f"{name}: {got.get('why') or got.get('state')}")
            continue
        out.extend(got.get("leases") or [])
    return {"leases": out, "said": said}


def kea(network: str) -> dict:
    """Kea's active leases as the DHCP reader stored them (both families)."""
    from modules import reader_job
    got = reader_job.read_cached("dhcp")
    good = (got.get("doc") or {}).get("last_good") or {}
    value = good.get("value") or {}
    if not good or value.get("configured") is False:
        return {"state": "not_configured", "why": "no Kea is configured, or the DHCP reader "
                "has not read it", "leases": [], "source": "Kea"}
    rows = []
    for fam in (value.get("families") or {}).values():
        for lease in (fam or {}).get("leases") or []:
            if lease.get("state", "active") != "active":
                continue
            rows.append({"mac": lease.get("mac", ""), "address": lease.get("address", ""),
                         "hostname": lease.get("hostname", ""),
                         "family": lease.get("family", ""), "ends": lease.get("ends", ""),
                         "source": "Kea's lease"})
    return {"state": "read", "why": "", "leases": rows, "source": "Kea",
            "read_at": good.get("value_at", "")}


register("kea", kea)
