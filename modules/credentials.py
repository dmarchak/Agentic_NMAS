"""credentials.py

Encrypted credential profiles and the resolver that decides which credentials a
NetBox-sourced device uses.

NetBox holds identity, never secrets, so a NetBox-sourced device has to get its
SSH credentials from somewhere local. Resolution order, first match wins:

1. **Per-device override** — set in NMAS for one device.
2. **Designated local list** — the list named by ``credential_list`` in the
   NetBox list's ``source.json``. Exactly one list, never a scan of all of them,
   so credential origin stays predictable.
3. **Role profile** → 4. **Site profile** → 5. **Default profile**.

Every resolution records ``_cred_source`` on the device dict (for example
``"local-list:Lab Devices"`` or ``"profile:default"``) so the origin is visible
in the UI instead of inferred. A device that resolves to nothing is skipped with
a clear reason rather than failing later inside netmiko.

Stored values are Fernet-encrypted via :mod:`modules.secrets_store`. Profiles
carry ``last_rotated`` and ``rotation_policy``; both are unused here and exist
as the hook for Part 2's automatic rotation.
"""

import json
import logging
import os
import threading
import time

from modules.config import DATA_DIR
from modules.secrets_store import decrypt_value, encrypt_value

log = logging.getLogger(__name__)

_FILE = os.path.join(DATA_DIR, "credential_profiles.json")
_lock = threading.Lock()

DEFAULT_PROFILE = "default"


# ---------------------------------------------------------------------------
# Profile storage
# ---------------------------------------------------------------------------

def _load() -> dict:
    if not os.path.exists(_FILE):
        return {"profiles": {}, "device_overrides": {}}
    try:
        with open(_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        log.error("credentials: unreadable store (%s) — treating as empty", exc)
        return {"profiles": {}, "device_overrides": {}}
    data.setdefault("profiles", {})
    data.setdefault("device_overrides", {})
    return data


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    tmp = _FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, _FILE)


def save_profile(name: str, username: str, password: str, secret: str = "",
                 rotation_policy: str = "") -> dict:
    """Create or update a credential profile. Values are encrypted at rest.

    An empty *password* or *secret* leaves the stored one untouched, matching
    the write-only secret fields elsewhere in Settings.
    """
    with _lock:
        data = _load()
        existing = data["profiles"].get(name, {})
        data["profiles"][name] = {
            "username":        username if username else existing.get("username", ""),
            "password":        encrypt_value(password) if password else existing.get("password", ""),
            "secret":          encrypt_value(secret) if secret else existing.get("secret", ""),
            "rotation_policy": rotation_policy or existing.get("rotation_policy", ""),
            "last_rotated":    time.time() if password else existing.get("last_rotated"),
        }
        _save(data)
    log.info("credentials: saved profile '%s'", name)
    return {"ok": True, "profile": name}


def delete_profile(name: str) -> dict:
    with _lock:
        data = _load()
        data["profiles"].pop(name, None)
        _save(data)
    return {"ok": True}


def list_profiles() -> list:
    """Profiles with secrets masked — never returns a credential value."""
    data = _load()
    return [
        {"name": name,
         "username": p.get("username", ""),
         "password_set": bool(p.get("password")),
         "secret_set": bool(p.get("secret")),
         "rotation_policy": p.get("rotation_policy", ""),
         "last_rotated": p.get("last_rotated")}
        for name, p in sorted(data["profiles"].items())
    ]


def set_device_override(device_key: str, username: str, password: str,
                        secret: str = "") -> dict:
    """Set a one-off credential for a single device, keyed by management IP."""
    with _lock:
        data = _load()
        data["device_overrides"][device_key] = {
            "username": username,
            "password": encrypt_value(password) if password else "",
            "secret":   encrypt_value(secret) if secret else "",
        }
        _save(data)
    log.info("credentials: set device override for %s", device_key)
    return {"ok": True}


def clear_device_override(device_key: str) -> dict:
    with _lock:
        data = _load()
        data["device_overrides"].pop(device_key, None)
        _save(data)
    return {"ok": True}


def has_device_override(device_key: str) -> bool:
    return device_key in _load()["device_overrides"]


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _from_profile(profiles: dict, name: str):
    """Return plaintext ``(username, password, secret)`` for a profile."""
    p = profiles.get(name)
    if not p or not p.get("username"):
        return None
    return (p.get("username", ""),
            decrypt_value(p.get("password", "")),
            decrypt_value(p.get("secret", "")))


def _from_credential_list(credential_list: str, mgmt_ip: str):
    """Credentials for *mgmt_ip* from the designated local list (amendment 2).

    Reads the list's CSV directly rather than going through the inventory
    dispatch, so a NetBox list can never inherit from another NetBox list and
    recurse.
    """
    if not credential_list or not mgmt_ip:
        return None
    try:
        import csv as _csv

        from modules.config import LISTS_DIR, list_slug
        path = os.path.join(LISTS_DIR, list_slug(credential_list), "devices.csv")
        if not os.path.exists(path):
            return None
        with open(path, newline="", encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                if (row.get("ip") or "").strip() == mgmt_ip:
                    return (row.get("username", ""),
                            decrypt_value(row.get("password", "")),
                            decrypt_value(row.get("secret", "")))
    except Exception as exc:                  # noqa: BLE001
        log.warning("credentials: could not read credential list '%s': %s",
                    credential_list, exc)
    return None


def resolve(mgmt_ip: str, role: str = "", site: str = "",
            credential_list: str = "") -> dict:
    """Resolve credentials for one device.

    Returns ``{"ok", "username", "password", "secret", "source"}`` with
    **plaintext** values; the caller re-encrypts to match the CSV dict shape.
    ``ok`` is False when nothing matched, which the adapter turns into a skip.
    """
    data = _load()
    profiles = data["profiles"]

    override = data["device_overrides"].get(mgmt_ip)
    if override and override.get("username"):
        return {"ok": True, "username": override["username"],
                "password": decrypt_value(override.get("password", "")),
                "secret":   decrypt_value(override.get("secret", "")),
                "source":   "device-override"}

    inherited = _from_credential_list(credential_list, mgmt_ip)
    if inherited and inherited[0]:
        return {"ok": True, "username": inherited[0], "password": inherited[1],
                "secret": inherited[2], "source": f"local-list:{credential_list}"}

    if role:
        found = _from_profile(profiles, f"role:{role}")
        if found:
            return {"ok": True, "username": found[0], "password": found[1],
                    "secret": found[2], "source": f"profile:role:{role}"}

    if site:
        found = _from_profile(profiles, f"site:{site}")
        if found:
            return {"ok": True, "username": found[0], "password": found[1],
                    "secret": found[2], "source": f"profile:site:{site}"}

    found = _from_profile(profiles, DEFAULT_PROFILE)
    if found:
        return {"ok": True, "username": found[0], "password": found[1],
                "secret": found[2], "source": f"profile:{DEFAULT_PROFILE}"}

    return {"ok": False, "username": "", "password": "", "secret": "",
            "source": "",
            "error": ("no credentials — set a device override, a default profile, "
                      "or a credential list for this NetBox list")}


def copy_inherited_to_overrides(list_name: str) -> dict:
    """Freeze inherited credentials into per-device overrides (amendment 2).

    Decouples a NetBox list from its designated credential list, so deleting
    that list no longer strands it.
    """
    from modules.inventory import load_netbox_devices
    from modules.inventory.source_config import load as load_source

    cfg = load_source(list_name)
    credential_list = cfg.get("credential_list", "")
    if not credential_list:
        return {"ok": False, "error": "This list does not inherit credentials."}

    devices, _skipped, _meta = load_netbox_devices(list_name, use_cache=True)
    copied, skipped = [], []
    for dev in devices:
        ip = dev.get("ip", "")
        if not ip or has_device_override(ip):
            continue
        found = _from_credential_list(credential_list, ip)
        if found and found[0]:
            set_device_override(ip, found[0], found[1], found[2])
            copied.append(dev.get("hostname", ip))
        else:
            skipped.append(dev.get("hostname", ip))

    log.info("credentials: copied %d inherited credential(s) into overrides for '%s'",
             len(copied), list_name)
    return {"ok": True, "copied": copied, "skipped": skipped,
            "message": (f"Copied credentials for {len(copied)} device(s). "
                        f"'{list_name}' no longer depends on '{credential_list}'.")}
