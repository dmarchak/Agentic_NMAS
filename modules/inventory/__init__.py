"""inventory — where a device list's devices come from.

A list is either ``local`` (a CSV, the default and the behaviour of every list
that predates this) or ``netbox`` (built by querying NetBox).

**Dispatch never performs network I/O.** ``load_saved_devices`` sits on 79 call
sites across 11 modules, several inside request handlers and tight loops, so a
NetBox round trip there would put remote latency on every one. Instead:

* A background refresh queries NetBox, adapts the records, resolves and
  **encrypts credentials once per refresh**, and stores the finished dicts.
* Dispatch serves those finished dicts from memory. It is a dict copy.
* The last good inventory is persisted to
  ``data/lists/{slug}/netbox_inventory_cache.json`` — **identity fields only,
  never credentials** — so a restart during a NetBox outage still yields the
  last known device list, flagged stale.

Credentials are re-resolved when the persisted cache is rehydrated, because they
are deliberately not written to that file.
"""

import copy
import json
import logging
import os
import threading
import time

from modules.config import get_list_data_dir
from modules.inventory.source_config import (
    SOURCE_LOCAL, SOURCE_NETBOX, apply_device_order, is_netbox_sourced, load as load_source,
)

log = logging.getLogger(__name__)

_CACHE_FILE = "netbox_inventory_cache.json"

#: Presentation-only keys, stripped before a dict reaches netmiko.
_METADATA_KEYS = ("_source", "_netbox_id", "_cred_source", "_platform", "_site", "_stale")

# In-memory cache: list_name -> {devices, skipped, warnings, fetched_at, stale, error}
_memory: dict = {}
_lock = threading.Lock()
_refreshing: set = set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_metadata(device: dict) -> dict:
    """Return *device* without NMAS presentation-only keys."""
    return {k: v for k, v in device.items() if k not in _METADATA_KEYS}


def _cache_path(list_name: str) -> str:
    return os.path.join(get_list_data_dir(list_name), _CACHE_FILE)


def _persist(list_name: str, entry: dict) -> None:
    """Write identity fields of the last good inventory. Never credentials."""
    payload = {
        "fetched_at": entry.get("fetched_at", 0),
        "devices": [
            {k: v for k, v in d.items()
             if k not in ("username", "password", "secret")}
            for d in entry.get("devices", [])
        ],
        "skipped":  entry.get("skipped", []),
        "warnings": entry.get("warnings", []),
    }
    try:
        path = _cache_path(list_name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("inventory: could not persist cache for '%s': %s", list_name, exc)


def _rehydrate(list_name: str) -> dict:
    """Load the persisted inventory and re-resolve credentials.

    Credentials are not persisted, so they are resolved again here. A device
    whose credentials no longer resolve becomes a skip, exactly as it would on a
    live refresh.
    """
    path = _cache_path(list_name)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("inventory: unreadable cache for '%s': %s", list_name, exc)
        return {}

    from modules.credentials import resolve as resolve_credentials
    from modules.inventory.netbox_source import _encrypt_for_shape

    cfg = load_source(list_name)
    devices, skipped = [], list(payload.get("skipped", []))
    for dev in payload.get("devices", []):
        creds = resolve_credentials(dev.get("ip", ""), role=dev.get("role", ""),
                                    site=dev.get("_site", ""),
                                    credential_list=cfg.get("credential_list", ""))
        if not creds["ok"]:
            skipped.append({"name": dev.get("hostname", ""), "field": "credentials",
                            "reason": creds["error"]})
            continue
        devices.append({**dev,
                        "username": creds["username"],
                        "password": _encrypt_for_shape(creds["password"]),
                        "secret":   _encrypt_for_shape(creds["secret"]),
                        "_cred_source": creds["source"]})

    return {"devices": devices, "skipped": skipped,
            "warnings": payload.get("warnings", []),
            "fetched_at": payload.get("fetched_at", 0),
            "stale": True, "error": "",
            "stale_reason": "restored from cache — not yet refreshed from NetBox"}


# ---------------------------------------------------------------------------
# Refresh (the only place that talks to NetBox)
# ---------------------------------------------------------------------------

def refresh_list(list_name: str, block: bool = True) -> dict:
    """Query NetBox and rebuild the cached inventory for *list_name*."""
    from modules.inventory.netbox_source import adapt_devices, fetch_netbox_devices

    cfg = load_source(list_name)
    if cfg["source"] != SOURCE_NETBOX:
        return {"ok": False, "error": f"'{list_name}' is not a NetBox-sourced list"}

    result = fetch_netbox_devices(cfg["filters"])
    if not result["ok"]:
        with _lock:
            entry = _memory.get(list_name)
            if entry:
                # Keep serving the last good inventory, flagged stale.
                entry["stale"] = True
                entry["error"] = result["error"]
                entry["stale_reason"] = f"NetBox unreachable: {result['error']}"
        log.warning("inventory: refresh failed for '%s': %s", list_name, result["error"])
        return {"ok": False, "error": result["error"]}

    devices, skipped, warnings = adapt_devices(
        result["devices"], credential_list=cfg.get("credential_list", ""))
    devices = apply_device_order(list_name, devices)

    # Capture what the previous refresh saw BEFORE overwriting the cache —
    # _previous_ips reads that same file, so persisting first would make every
    # refresh compare the new list against itself and never detect a departure.
    previous_ips = _previous_ips(list_name)

    entry = {"devices": devices, "skipped": skipped, "warnings": warnings,
             "fetched_at": time.time(), "stale": False, "error": "", "stale_reason": ""}
    with _lock:
        _memory[list_name] = entry
    _persist(list_name, entry)

    _record_stale_devices(list_name, devices, previous_ips)
    _record_renames(list_name, devices)
    _record_platforms(list_name)

    log.info("inventory: refreshed '%s' — %d device(s), %d skipped, %d warning(s)",
             list_name, len(devices), len(skipped), len(warnings))
    return {"ok": True, "device_count": len(devices), "skipped": skipped,
            "warnings": warnings}


def refresh_async(list_name: str) -> None:
    """Refresh in the background, one refresh per list at a time."""
    with _lock:
        if list_name in _refreshing:
            return
        _refreshing.add(list_name)

    def _run():
        try:
            refresh_list(list_name)
        except Exception as exc:              # noqa: BLE001
            log.error("inventory: background refresh failed for '%s': %s", list_name, exc)
        finally:
            with _lock:
                _refreshing.discard(list_name)

    threading.Thread(target=_run, daemon=True,
                     name=f"inventory-refresh-{list_name}").start()


# ---------------------------------------------------------------------------
# Dispatch — no network I/O
# ---------------------------------------------------------------------------

def load_netbox_devices(list_name: str, use_cache: bool = True) -> tuple:
    """Return ``(devices, skipped, meta)`` for a NetBox-sourced list.

    Serves the in-memory cache, rehydrating from disk on first access. Triggers
    a background refresh when the entry is missing or past its refresh interval;
    it never waits on one.
    """
    cfg = load_source(list_name)
    with _lock:
        entry = _memory.get(list_name)

    if entry is None:
        entry = _rehydrate(list_name)
        if entry:
            with _lock:
                _memory[list_name] = entry
        refresh_async(list_name)

    if not entry:
        # Nothing cached and nothing on disk: a refresh is already running.
        return [], [], {"stale": True, "fetched_at": 0, "never_loaded": True,
                        "stale_reason": "loading from NetBox…", "warnings": []}

    age = time.time() - entry.get("fetched_at", 0)
    if use_cache and age > cfg["refresh_interval"]:
        refresh_async(list_name)

    meta = {"stale": entry.get("stale", False), "fetched_at": entry.get("fetched_at", 0),
            "age_seconds": int(age), "error": entry.get("error", ""),
            "stale_reason": entry.get("stale_reason", ""),
            "warnings": entry.get("warnings", []), "never_loaded": False}
    return copy.deepcopy(entry["devices"]), list(entry.get("skipped", [])), meta


def load_devices_for_list(list_name: str, csv_path: str = "") -> list:
    """Devices for *list_name*, from whichever source it is configured to use."""
    if is_netbox_sourced(list_name):
        devices, _skipped, _meta = load_netbox_devices(list_name)
        return devices
    from modules.device import _load_devices_csv
    return _load_devices_csv(csv_path)


def get_status(list_name: str) -> dict:
    """Freshness, skips, and warnings for the UI banner."""
    if not is_netbox_sourced(list_name):
        return {"source": SOURCE_LOCAL}
    devices, skipped, meta = load_netbox_devices(list_name)
    return {"source": SOURCE_NETBOX, "device_count": len(devices),
            "skipped": skipped, **meta}


def invalidate(list_name: str = "") -> None:
    """Drop cached inventory so the next access refetches."""
    with _lock:
        if list_name:
            _memory.pop(list_name, None)
        else:
            _memory.clear()


# ---------------------------------------------------------------------------
# Renames
# ---------------------------------------------------------------------------

def _record_renames(list_name: str, devices: list) -> None:
    """Note devices whose NetBox name changed — in the manifest only.

    This runs on the background refresh thread, which must never take the repo
    lock or create a commit. The actual ``git mv`` happens at the next
    ``save_golden``, or when the operator runs "Sync device names to repo".
    Until then the manifest resolves either name, so the golden config stays
    reachable under both.
    """
    import os as _os

    try:
        from modules.config import get_list_data_dir
        from modules.nsot import manifest as _m
    except ImportError:
        return

    repo = _os.path.join(get_list_data_dir(list_name), "config_repo")
    if not _os.path.isdir(repo):
        return                                 # nothing committed yet

    for dev in devices:
        identity = _m.identity_for(dev.get("_netbox_id"), dev.get("device_uid", ""))
        if not identity:
            continue
        entry = _m.find_by_identity(repo, identity)
        if entry is None:
            continue                           # first sighting: save_golden records it
        current_name = dev.get("hostname", "")
        if current_name and entry.get("name") != current_name:
            _m.record_pending_rename(repo, identity, current_name)


def _record_platforms(list_name: str) -> None:
    """Refresh the manifest's platform for every device — manifest only.

    The inventory is the authority on config dialect, and it can be corrected
    after migration: a device mis-recorded as ``cisco_ios`` and later fixed to
    ``cisco_iosxe`` must reach the manifest, because Phase 4 onboarding and
    parser selection read it from there. Runs on the refresh thread, so like
    :func:`_record_renames` it takes no repo lock and creates no commit.
    """
    import os as _os

    try:
        from modules.config import get_list_data_dir
        from modules.nsot import manifest as _m
    except ImportError:
        return

    repo = _os.path.join(get_list_data_dir(list_name), "config_repo")
    if not _os.path.isdir(repo):
        return
    try:
        _m.sync_platforms(repo, list_name)
    except Exception as exc:                   # noqa: BLE001
        log.debug("inventory: platform sync failed for '%s': %s", list_name, exc)


def sync_device_names_to_repo(list_name: str, actor: str = "user") -> dict:
    """Apply pending renames to the repo as their own commits.

    The explicit half of the deferred-rename design: a refresh records the
    rename, this applies it. Also runs automatically at the next save_golden.
    """
    import os as _os

    from modules.config import get_list_data_dir
    from modules.nsot.repo import apply_pending_renames

    repo = _os.path.join(get_list_data_dir(list_name), "config_repo")
    if not _os.path.isdir(repo):
        return {"ok": True, "renamed": [], "message": "No repository yet."}
    result = apply_pending_renames(repo, actor)
    result["message"] = (
        f"Renamed {len(result['renamed'])} device file(s) in the repo."
        if result["renamed"] else "No pending renames."
    )
    return result


def pending_renames(list_name: str) -> list:
    """Renames noticed by a refresh but not yet committed."""
    import os as _os

    try:
        from modules.config import get_list_data_dir
        from modules.nsot.manifest import pending_renames as _pending
    except ImportError:
        return []
    repo = _os.path.join(get_list_data_dir(list_name), "config_repo")
    return _pending(repo) if _os.path.isdir(repo) else []


# ---------------------------------------------------------------------------
# Stale devices (amendment 4)
# ---------------------------------------------------------------------------

_STALE_FILE = "stale_devices.json"


def _stale_path(list_name: str) -> str:
    return os.path.join(get_list_data_dir(list_name), _STALE_FILE)


def _record_stale_devices(list_name: str, current_devices: list,
                          previous_ips: dict = None) -> None:
    """Record devices that have disappeared from NetBox.

    Their golden configs, backups, and history stay on disk — a NetBox-side
    change never destroys local artifacts — but the device itself becomes
    inert: see :func:`is_stale`.
    """
    path = _stale_path(list_name)
    try:
        known = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                known = json.load(fh)
    except (json.JSONDecodeError, OSError):
        known = {}

    current_ips = {d["ip"]: d.get("hostname", "") for d in current_devices}
    for ip, hostname in current_ips.items():
        known.pop(ip, None)                   # back in NetBox: no longer stale

    previous = previous_ips if previous_ips is not None else _previous_ips(list_name)
    for ip, hostname in previous.items():
        if ip not in current_ips and ip not in known:
            known[ip] = {"hostname": hostname, "last_seen": time.time(),
                         "reason": "no longer returned by NetBox for this list's filters"}
            log.info("inventory: '%s' device %s (%s) is now stale", list_name, hostname, ip)

    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(known, fh, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("inventory: could not record stale devices for '%s': %s", list_name, exc)

    _close_stale_sessions(list(known))


def _previous_ips(list_name: str) -> dict:
    """IP → hostname from the persisted cache, i.e. the previous refresh."""
    path = _cache_path(list_name)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        return {d["ip"]: d.get("hostname", "") for d in payload.get("devices", [])
                if d.get("ip")}
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def get_stale_devices(list_name: str) -> dict:
    """Devices that have vanished from NetBox but whose artifacts remain."""
    path = _stale_path(list_name)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def is_stale(device_ip: str, list_name: str = "") -> bool:
    """True if *device_ip* is a stale device of a NetBox-sourced list.

    Amendment 4: stale devices are inert. The approval executor, the drift
    checker, and the AI device tools all refuse to act on one.
    """
    if not device_ip:
        return False
    if not list_name:
        from modules.config import get_current_list_name
        list_name = get_current_list_name()
    if not is_netbox_sourced(list_name):
        return False
    return device_ip in get_stale_devices(list_name)


def stale_message(device_ip: str, list_name: str = "") -> str:
    """The refusal message shown when something tries to act on a stale device."""
    if not list_name:
        from modules.config import get_current_list_name
        list_name = get_current_list_name()
    entry = get_stale_devices(list_name).get(device_ip, {})
    hostname = entry.get("hostname", device_ip)
    return (f"{hostname} ({device_ip}) is no longer in NetBox for this list, so NMAS "
            "will not act on it. Its golden configs and backups are still available. "
            "Re-add it in NetBox, or adjust the list's filters, to make it active again.")


#: Module-level connection pools to sweep, as ``(module, pool_attr, lock_attr)``.
#: Only app.py holds a long-lived pool. drift_check and pipeline build theirs as
#: function locals that die with the run, so a stale device cannot keep a session
#: alive there and there is nothing to sweep.
_POOLS = (
    ("app", "connections", "lock"),
)


def _close_stale_sessions(stale_ips: list) -> None:
    """Close pooled SSH sessions for stale devices (amendment 4).

    A stale device must not keep an open session: it is no longer part of the
    list, and holding the socket would let background workers keep talking to it.
    """
    if not stale_ips:
        return
    import importlib

    from modules.connection import close_persistent_connection

    for module_name, pool_attr, lock_attr in _POOLS:
        try:
            module = importlib.import_module(module_name)
        except Exception:                      # noqa: BLE001 - module may not be loaded
            continue
        pool = getattr(module, pool_attr, None)
        lock = getattr(module, lock_attr, None)
        if not isinstance(pool, dict) or lock is None:
            continue
        for ip in stale_ips:
            if ip in pool:
                try:
                    close_persistent_connection(ip, pool, lock)
                    log.info("inventory: closed %s session for stale device %s",
                             module_name, ip)
                except Exception as exc:       # noqa: BLE001
                    log.debug("inventory: could not close session for %s: %s", ip, exc)
