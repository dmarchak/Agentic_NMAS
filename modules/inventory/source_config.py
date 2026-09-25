"""inventory/source_config.py

Per-device-list inventory source configuration,
``data/lists/{slug}/source.json``.

An **absent file means ``local``**, which is what every list that predates this
work has. Local lists therefore behave exactly as before, with no migration.

```json
{
  "source": "netbox",
  "filters": {"site": "lab", "role": "router", "tag": "", "status": ""},
  "credential_list": "Lab Devices",
  "refresh_interval": 300,
  "device_order": ["R1", "R2", "S1"],
  "schema_version": 1
}
```

``status`` is **empty by default** — see ``DEFAULT_CONFIG``. An operator may
set it, but nothing assumes it: NMAS no longer writes a device's status, so
filtering on one selects for whatever it happened to be when the device was
created.
"""

import json
import logging
import os
import threading

from modules.config import get_list_data_dir

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SOURCE_LOCAL = "local"
SOURCE_NETBOX = "netbox"
VALID_SOURCES = (SOURCE_LOCAL, SOURCE_NETBOX)

_FILE = "source.json"
_lock = threading.Lock()

DEFAULT_CONFIG = {
    "source":           SOURCE_LOCAL,
    # NO STATUS FILTER BY DEFAULT.
    #
    # It was `"active"`, which was the other half of a self-sealing loop: the
    # sync wrote `offline` from a ping result, the refresh queried
    # `?status=active`, the device was not returned — absent, not skipped,
    # not named — and the next sync iterated the inventory that no longer
    # contained it, so nothing could ever set it back.
    #
    # Dropping the status write closes the loop, and leaving this filter would
    # replace it with something quieter and permanent: with status frozen at
    # whatever it was when the device was created, a device that happened to
    # be unreachable during its first sync is invisible for ever. **If status
    # no longer tracks liveness, filtering on it selects for an accident of
    # onboarding.**
    #
    # An operator who genuinely wants only active devices can still set it;
    # what changed is that nothing assumes it.
    "filters":          {"site": "", "role": "", "tag": "", "status": ""},
    # Amendment 2: credentials are inherited from ONE designated local list,
    # never by scanning every list. Empty means "profiles only".
    "credential_list":  "",
    "refresh_interval": 300,
    # Amendment 5: drag-and-drop ordering still works for NetBox lists; the
    # order lives here because there is no CSV to reorder.
    "device_order":     [],
    "schema_version":   SCHEMA_VERSION,
}


def _path(list_name: str) -> str:
    return os.path.join(get_list_data_dir(list_name), _FILE)


def load(list_name: str) -> dict:
    """Return the source config for *list_name*, defaulted and validated."""
    cfg = dict(DEFAULT_CONFIG)
    cfg["filters"] = dict(DEFAULT_CONFIG["filters"])
    path = _path(list_name)
    if not os.path.exists(path):
        return cfg
    try:
        with open(path, encoding="utf-8") as fh:
            stored = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("source_config: unreadable config for '%s' (%s) — treating as local",
                    list_name, exc)
        return cfg

    if stored.get("source") in VALID_SOURCES:
        cfg["source"] = stored["source"]
    if isinstance(stored.get("filters"), dict):
        cfg["filters"].update({k: v for k, v in stored["filters"].items()
                               if k in cfg["filters"]})
    for key in ("credential_list",):
        if isinstance(stored.get(key), str):
            cfg[key] = stored[key]
    if isinstance(stored.get("refresh_interval"), int) and stored["refresh_interval"] > 0:
        cfg["refresh_interval"] = stored["refresh_interval"]
    if isinstance(stored.get("device_order"), list):
        cfg["device_order"] = [str(x) for x in stored["device_order"]]
    return cfg


def save(list_name: str, cfg: dict) -> dict:
    """Persist the source config for *list_name*."""
    merged = load(list_name)
    if cfg.get("source") in VALID_SOURCES:
        merged["source"] = cfg["source"]
    if isinstance(cfg.get("filters"), dict):
        merged["filters"].update({k: v for k, v in cfg["filters"].items()
                                  if k in merged["filters"]})
    if isinstance(cfg.get("credential_list"), str):
        merged["credential_list"] = cfg["credential_list"]
    if isinstance(cfg.get("refresh_interval"), int) and cfg["refresh_interval"] > 0:
        merged["refresh_interval"] = cfg["refresh_interval"]
    if isinstance(cfg.get("device_order"), list):
        merged["device_order"] = [str(x) for x in cfg["device_order"]]
    merged["schema_version"] = SCHEMA_VERSION

    with _lock:
        path = _path(list_name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
        os.replace(tmp, path)
    log.info("source_config: '%s' source=%s", list_name, merged["source"])
    return merged


def get_source(list_name: str) -> str:
    return load(list_name)["source"]


def is_netbox_sourced(list_name: str) -> bool:
    return get_source(list_name) == SOURCE_NETBOX


def set_device_order(list_name: str, order: list) -> dict:
    """Persist drag-and-drop ordering (amendment 5)."""
    return save(list_name, {"device_order": list(order)})


def apply_device_order(list_name: str, devices: list) -> list:
    """Sort *devices* by the stored order; unknown devices keep NetBox order, last."""
    order = load(list_name).get("device_order") or []
    if not order:
        return devices
    rank = {name: i for i, name in enumerate(order)}
    return sorted(devices, key=lambda d: (rank.get(d.get("hostname", ""), len(rank)),))


def lists_depending_on(credential_list: str) -> list:
    """NetBox-sourced lists that inherit credentials from *credential_list*.

    Amendment 2: deleting a list must warn about the NetBox lists that depend
    on it for credentials.
    """
    from modules.device import get_device_lists

    dependents = []
    for entry in get_device_lists():
        name = entry["name"]
        if name == credential_list:
            continue
        cfg = load(name)
        if cfg["source"] == SOURCE_NETBOX and cfg["credential_list"] == credential_list:
            dependents.append(name)
    return dependents
