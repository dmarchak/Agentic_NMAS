"""nsot/manifest.py

``config_repo/.nsot/manifest.json`` — the identity map for a network's repo.

Devices are keyed on **stable identity**, never on hostname:

* ``nb:<netbox_id>`` for a device that comes from NetBox
* ``uid:<uuid4>``    for a device that comes from a CSV list

That is what lets a rename be a ``git mv`` of the device's golden file rather
than a new file plus an orphaned old one, so ``git log --follow`` keeps working
across renames.

```json
{
  "schema_version": 1,
  "devices": {
    "nb:42": {
      "name": "R1", "mgmt_ip": "…", "netbox_id": 42,
      "platform": "cisco-ios-xe", "golden": "golden/R1.cfg",
      "pending_rename": null
    }
  }
}
```

**Inventory refresh never writes to git.** A refresh that notices a renamed
device records ``pending_rename`` here and stops. The ``git mv`` happens at the
next :func:`modules.nsot.repo.save_golden`, or when the operator runs "Sync
device names to repo". Reads resolve through the manifest while a rename is
pending, so the golden config stays reachable under either name.
"""

import json
import logging
import os
import threading
import time
import uuid

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_MANIFEST_REL = os.path.join(".nsot", "manifest.json")
_locks: dict = {}
_locks_guard = threading.Lock()


def _lock_for(repo: str) -> threading.Lock:
    with _locks_guard:
        if repo not in _locks:
            _locks[repo] = threading.Lock()
        return _locks[repo]


def manifest_path(repo: str) -> str:
    return os.path.join(repo, _MANIFEST_REL)


def identity_for(netbox_id=None, device_uid: str = "") -> str:
    """Build a manifest key from whichever stable identifier exists."""
    if netbox_id not in (None, ""):
        return f"nb:{netbox_id}"
    if device_uid:
        return device_uid if device_uid.startswith("uid:") else f"uid:{device_uid}"
    return ""


def new_device_uid() -> str:
    """Mint a local identity for a CSV device."""
    return f"uid:{uuid.uuid4()}"


def load(repo: str) -> dict:
    path = manifest_path(repo)
    if not os.path.exists(path):
        return {"schema_version": SCHEMA_VERSION, "devices": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        log.error("manifest: unreadable at %s (%s) — starting empty", path, exc)
        return {"schema_version": SCHEMA_VERSION, "devices": {}}
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("devices", {})
    return data


def save(repo: str, data: dict) -> None:
    path = manifest_path(repo)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def upsert_device(repo: str, identity: str, name: str, mgmt_ip: str = "",
                  netbox_id=None, platform: str = "", golden: str = "") -> dict:
    """Record or update a device. Returns its manifest entry."""
    if not identity:
        raise ValueError("a manifest entry needs a stable identity")
    with _lock_for(repo):
        data = load(repo)
        entry = data["devices"].get(identity, {})
        entry.update({
            "name":      name or entry.get("name", ""),
            "mgmt_ip":   mgmt_ip or entry.get("mgmt_ip", ""),
            "netbox_id": netbox_id if netbox_id is not None else entry.get("netbox_id"),
            "platform":  platform or entry.get("platform", ""),
            "golden":    golden or entry.get("golden", f"golden/{name}.cfg"),
        })
        # Deliberately no "last_seen" here. The manifest is version-controlled,
        # so a timestamp touched on every call would produce a one-line diff on
        # every refresh and make the migration non-idempotent. Freshness is
        # runtime state and lives in the (gitignored) inventory cache.
        entry.setdefault("pending_rename", None)
        data["devices"][identity] = entry
        save(repo, data)
        return entry


def record_pending_rename(repo: str, identity: str, new_name: str) -> dict:
    """Note that a device has been renamed, without touching git.

    Called from the inventory refresh, which runs on a background thread and
    must never take the repo lock or create a commit.
    """
    with _lock_for(repo):
        data = load(repo)
        entry = data["devices"].get(identity)
        if entry is None:
            return {"ok": False, "error": f"unknown device identity '{identity}'"}
        old_name = entry.get("name", "")
        if old_name == new_name:
            entry["pending_rename"] = None
            save(repo, data)
            return {"ok": True, "changed": False}
        entry["pending_rename"] = {"from": old_name, "to": new_name,
                                   "noticed_at": time.time()}
        save(repo, data)
    log.info("manifest: pending rename %s → %s (identity %s) — git mv deferred",
             old_name, new_name, identity)
    return {"ok": True, "changed": True, "from": old_name, "to": new_name}


def pending_renames(repo: str) -> list:
    """Renames noticed but not yet applied to the repo."""
    out = []
    for identity, entry in load(repo)["devices"].items():
        pending = entry.get("pending_rename")
        if pending:
            out.append({"identity": identity, **pending})
    return out


def clear_pending_rename(repo: str, identity: str, new_name: str,
                         new_golden: str) -> None:
    """Mark a rename as applied to the repo."""
    with _lock_for(repo):
        data = load(repo)
        entry = data["devices"].get(identity)
        if entry is None:
            return
        entry["name"] = new_name
        entry["golden"] = new_golden
        entry["pending_rename"] = None
        save(repo, data)


# ---------------------------------------------------------------------------
# Resolution — the fallback chain
# ---------------------------------------------------------------------------

def find_by_identity(repo: str, identity: str):
    return load(repo)["devices"].get(identity)


def find_by_ip(repo: str, mgmt_ip: str):
    """Resolve by management IP. Returns ``(identity, entry)`` or ``(None, None)``."""
    if not mgmt_ip:
        return None, None
    for identity, entry in load(repo)["devices"].items():
        if entry.get("mgmt_ip") == mgmt_ip:
            return identity, entry
    return None, None


def find_by_name(repo: str, name: str):
    """Resolve by current name, or by a pending rename in either direction.

    While a rename is pending the golden file is still on disk under the old
    name, so both names must resolve or the config would appear to vanish.
    """
    if not name:
        return None, None
    lowered = name.lower()
    for identity, entry in load(repo)["devices"].items():
        if (entry.get("name") or "").lower() == lowered:
            return identity, entry
        pending = entry.get("pending_rename") or {}
        if lowered in ((pending.get("from") or "").lower(),
                       (pending.get("to") or "").lower()):
            return identity, entry
    return None, None


def golden_path_for(repo: str, entry: dict) -> str:
    """Absolute path of a device's golden file, honouring a pending rename.

    While a rename is pending the file has not moved yet, so the on-disk path is
    still the one recorded in ``golden``.
    """
    return os.path.join(repo, entry.get("golden", ""))
