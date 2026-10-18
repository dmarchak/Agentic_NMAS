"""A network's inventory source on v2 (CUTOVER: "the network's Settings page"; drawn under the
Phase 7 mode, docs/STANDING_APPROVAL_LOG.md): where its devices come from, its own list on this
host or NetBox through filters, with the designated list its NetBox devices take credentials
from and how often NetBox is read again.

A change is previewed: switching to NetBox, or changing its filters, reads NetBox once with the
new filters through the inventory's own fetch and adapt, read-only, so the preview says how many
devices the network would hold and how many would be skipped, by name; switching to its own list
says how many its file holds. The confirm is bound to the preview's fingerprint, written through
`source_config.save`, the cached inventory invalidated and, for NetBox, refreshed, and recorded.
**Refresh now** reads NetBox for a NetBox network now, as the schedule does anyway. Nothing here
writes to NetBox or contacts a device.
"""

import hashlib
import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

STEPS = ("check", "write", "refresh", "record")
FILTERS = ("site", "role", "tag", "status")
#: NetBox's slugs: letters, digits, "-" and "_". A filter is one, or empty (no filter).
_SLUG = re.compile(r"[A-Za-z0-9_-]{0,100}")
#: The inventory's own default is 300 s; read no faster than a minute, no slower than a day.
INTERVAL_MIN, INTERVAL_MAX = 60, 86400


class Refused(ValueError):
    """Nothing was changed; the message names the field or what moved."""


def _fp(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def _local_count(name: str) -> int:
    from modules.config import list_data_path
    from modules.device import _load_devices_csv

    path = os.path.join(list_data_path(name), "devices.csv")
    return len(_load_devices_csv(path)) if os.path.exists(path) else 0


def _local_lists(exclude: str = "") -> list:
    from modules.inventory.source_config import get_source
    from modules.integration_groups import network_names
    from modules.nsot import listref

    return [n for n in network_names()
            if n != exclude and listref.exists(n) and get_source(n) == "local"]


#: What a skipped or warned device's NetBox field means, and where it is put right (C1160): the
#: field is the inventory adapter's (`netbox_source.adapt_devices`, and `credentials` from a
#: rehydrate). A field not named here is drawn as itself, with no fix said.
FIELD_WORDS = {
    "primary_ip4": ("no primary IPv4 address", "set one on the device in NetBox"),
    "platform": ("a platform Mercury does not map",
                 "map it under Settings › Installation › Platforms and roles"),
    "credentials": ("no login resolves", "add a credential profile that covers it, on "
                                         "Credentials › Profiles, or name a credentials "
                                         "network here"),
    "role": ("a role NetBox does not classify",
             "set the role's Mercury kind in NetBox (each line says how)"),
}


def _at(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch)) if epoch else ""


def _groups(entries: list) -> list:
    """The inventory's skipped or warned devices, grouped by the NetBox field that put them
    there (most first): each group's words, where it is put right, and its devices by name,
    each with the inventory's own reason."""
    by: dict = {}
    for e in entries or []:
        by.setdefault(e.get("field") or "device", []).append(
            {"name": e.get("name") or e.get("hostname") or "", "reason": e.get("reason") or ""})
    out = []
    for field, devices in by.items():
        words, fix = FIELD_WORDS.get(field, (field, ""))
        out.append({"field": field, "words": words, "fix": fix, "count": len(devices),
                    "devices": sorted(devices, key=lambda d: d["name"])})
    return sorted(out, key=lambda g: (-g["count"], g["field"]))


def _gone(name: str) -> list:
    """The devices NetBox no longer returns for this network (the inventory's stale record):
    each one's name, address, since when (the refresh that first did not find it) and why."""
    from modules.inventory import get_stale_devices

    rows = [{"name": e.get("hostname") or ip, "ip": ip, "since": _at(e.get("last_seen") or 0),
             "reason": e.get("reason") or ""}
            for ip, e in (get_stale_devices(name) or {}).items()]
    return sorted(rows, key=lambda r: (r["since"], r["name"]), reverse=True)


def view(name: str) -> dict:
    """The card: the source as configured, its freshness, the devices NetBox holds that are not
    in the inventory (skipped, by the field and the reason), those loaded with a warning, and
    those NetBox no longer returns (C1160), and the choices a change offers."""
    from modules.inventory import get_status
    from modules.inventory.source_config import load

    cfg = load(name)
    out = {"network": name, "source": cfg["source"], "filters": dict(cfg["filters"]),
           "credential_list": cfg.get("credential_list", ""),
           "refresh_interval": cfg.get("refresh_interval", 300),
           "local_count": _local_count(name), "credential_choices": _local_lists(name),
           "bounds": (INTERVAL_MIN, INTERVAL_MAX), "status": None}
    if cfg["source"] == "netbox":
        try:
            st = get_status(name)
            skipped, warned = _groups(st.get("skipped")), _groups(st.get("warnings"))
            gone = _gone(name)
            out["status"] = {"count": st.get("device_count", 0),
                             "skipped": sum(g["count"] for g in skipped),
                             "warnings": sum(g["count"] for g in warned),
                             "gone": len(gone),
                             "skipped_groups": skipped, "warning_groups": warned,
                             "gone_devices": gone,
                             "fetched_at": _at(st.get("fetched_at") or 0),
                             "stale": bool(st.get("stale")),
                             "error": st.get("error") or st.get("stale_reason") or ""}
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            out["status"] = {"count": 0, "skipped": 0, "warnings": 0, "gone": 0,
                             "skipped_groups": [], "warning_groups": [], "gone_devices": [],
                             "fetched_at": None, "stale": True,
                             "error": f"its inventory could not be read: {exc}"}
    return out


def proposal(name: str, form: dict) -> dict:
    """The change as the schema types it, refusing (naming the field) what is not one."""
    source = (form.get("source") or "").strip()
    if source not in ("local", "netbox"):
        raise Refused(f"Source {source!r} is not one of: local, netbox")
    filters = {}
    for f in FILTERS:
        v = (form.get(f"filter_{f}") or "").strip()
        if not _SLUG.fullmatch(v):
            raise Refused(f"The {f} filter {v!r} is not a NetBox slug (letters, digits, - and _)")
        filters[f] = v
    cred = (form.get("credential_list") or "").strip()
    if cred and cred not in _local_lists(name):
        raise Refused(f"Credentials from {cred!r}: it is not a network with its own list here")
    raw = (form.get("refresh_interval") or "").strip() or "300"
    if not raw.isdigit() or not INTERVAL_MIN <= int(raw) <= INTERVAL_MAX:
        raise Refused(f"Read NetBox every {raw!r} seconds: it is {INTERVAL_MIN} to {INTERVAL_MAX}")
    if source == "netbox" and not any(filters.values()):
        raise Refused("A NetBox network needs at least one filter: with none it would take every "
                      "device NetBox holds")
    return {"source": source, "filters": filters, "credential_list": cred,
            "refresh_interval": int(raw)}


def preview(name: str, form: dict) -> dict:
    """What the change does, read now; writes nothing."""
    from modules.inventory.netbox_source import adapt_devices, fetch_netbox_devices

    now = view(name)
    p = proposal(name, form)
    out = {"network": name, "now": now, "to": p, "would": None}
    if p["source"] == "netbox":
        got = fetch_netbox_devices(p["filters"])
        if got.get("ok"):
            devices, skipped, _warnings = adapt_devices(got["devices"],
                                                        credential_list=p["credential_list"],
                                                        kinds=got.get("kinds"))
            out["would"] = {"count": len(devices),
                            "names": sorted(d.get("hostname", "") for d in devices)[:20],
                            "skipped": [{"name": s.get("name") or s.get("hostname") or "",
                                         "why": s.get("reason") or s.get("why") or ""}
                                        for s in skipped][:20],
                            "skipped_count": len(skipped), "error": ""}
        else:
            out["would"] = {"count": 0, "names": [], "skipped": [], "skipped_count": 0,
                            "error": got.get("error") or "NetBox did not answer"}
    out["fingerprint"] = _fp([name, now["source"], now["filters"], now["credential_list"],
                              now["refresh_interval"], p])
    return out


def apply(name: str, form: dict, fingerprint: str, actor: str, verified: str) -> dict:
    """Write the change as previewed (STEPS), refresh a NetBox network, and record it."""
    from modules import installation_settings as IS
    from modules.inventory import invalidate, refresh_async
    from modules.inventory.source_config import save

    now = view(name)                                                          # check
    p = proposal(name, form)
    fresh = _fp([name, now["source"], now["filters"], now["credential_list"],
                 now["refresh_interval"], p])
    if fresh != fingerprint:
        raise Refused(f"the source changed since the preview (preview {fingerprint}, now "
                      f"{fresh}): preview again")
    save(name, p)                                                             # write
    invalidate(name)
    if p["source"] == "netbox":                                               # refresh
        refresh_async(name)
    entry = IS._record({"kind": "inventory_source", "actor": actor, "actor_verified": verified,
                        "fields": [name, p["source"]]})                       # record
    return dict(entry, ok=True, network=name, to=p)


def refresh(name: str) -> dict:
    """Read NetBox for a NetBox network now (the schedule does anyway): its answer."""
    from modules.inventory import refresh_list

    got = refresh_list(name)
    if not got.get("ok"):
        raise Refused(got.get("error") or "NetBox did not answer")
    return {"count": got.get("device_count", 0), "skipped": len(got.get("skipped") or []),
            "warnings": len(got.get("warnings") or [])}
