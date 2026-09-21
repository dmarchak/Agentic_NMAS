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

    # EVERY write to the credential store, not just template secrets. Profiles,
    # device overrides, deletions and the scope migration all change what
    # redaction must match, and this is the one place they all pass through.
    # Invalidating at six call sites is six chances to add a seventh and forget;
    # the rotation in item (4) is precisely when a stale table would leave a
    # brand-new router password unredacted while the rotation logs its commands.
    try:
        from modules.redact import invalidate_cache
        invalidate_cache()
    except Exception:                         # noqa: BLE001
        pass                                  # never fail a write over a cache


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


class SecretOwnedByAnotherList(Exception):
    """A write would replace a secret a different device list owns."""


def template_secret_key(list_name: str, hostname: str, ref: str) -> str:
    """The ONE place a template-secret key is built: ``<slug>:<host>:<ref>``.

    The key used to be ``<hostname>:<ref>``, built by four separate f-strings
    in three modules, in a single installation-wide store. Two lists that each
    contain a device called ``r1`` — the actual name in the reference lab, and
    the likeliest name in any second one — therefore shared one key. The second
    list's extraction silently replaced the first's, and the first network then
    rendered and deployed the second network's SNMP community, with every guard
    on the deploy path satisfied: none of them asks which network a secret
    belongs to.

    Same correction as ``sections.chains()`` and ``deploy._command_keys()``:
    a value four call sites re-derive is a value that will eventually be
    derived four different ways. Building it here means the scoping rule can
    only be changed in one place.
    """
    from modules.config import list_slug
    return f"{list_slug(list_name)}:{hostname}:{ref}"


def split_template_secret_key(name: str) -> tuple:
    """``(slug, hostname, ref)``; slug is ``""`` for a legacy unscoped key."""
    parts = (name or "").split(":")
    if len(parts) >= 3:
        return parts[0], parts[1], ":".join(parts[2:])
    if len(parts) == 2:
        return "", parts[0], parts[1]
    return "", "", name or ""


def device_credential_values() -> dict:
    """``{value: label}`` for every credential this installation stores.

    Profiles, per-device overrides, and the devices.csv rows of every list.
    Used only by :mod:`modules.redact` to keep these out of payloads leaving
    the process — a device password reaches the agent through
    ``show running-config``, a failed-login message, or a connection error,
    none of which go through the template-secret store.

    Values only, never names. Failures are logged and skipped rather than
    raised: redaction must degrade to "redact what we could read", and a
    credential store that will not open is a separate problem.
    """
    import csv as _csv
    import glob as _glob

    from modules.config import LISTS_DIR

    out = {}

    def _add(value, label):
        value = (value or "").strip()
        if value:
            out.setdefault(value, label)

    try:
        data = _load()
        for name, profile in (data.get("profiles") or {}).items():
            _add(decrypt_value(profile.get("password", "")), "device-password")
            _add(decrypt_value(profile.get("secret", "")), "enable-secret")
        for ip, override in (data.get("device_overrides") or {}).items():
            _add(decrypt_value(override.get("password", "")), "device-password")
            _add(decrypt_value(override.get("secret", "")), "enable-secret")
    except Exception as exc:                  # noqa: BLE001
        log.error("credentials: could not read profiles for redaction: %s", exc)

    # Every list, not the active one: a payload is redacted for what it holds.
    #
    # CSV fields use RAW Fernet (`gAAAAA…`); settings and profiles use
    # secrets_store's prefixed form. `decrypt_value()` returns anything
    # unprefixed unchanged, so using it here collected ciphertext — and
    # redaction then searched payloads for a string no device will ever echo.
    # Measured: every CSV credential came back 100 characters long.
    from modules.device import decrypt_field

    for path in _glob.glob(os.path.join(LISTS_DIR, "*", "devices.csv")):
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                for row in _csv.DictReader(fh):
                    for field, label in (("password", "device-password"),
                                         ("secret", "enable-secret")):
                        raw = (row.get(field) or "").strip()
                        if not raw:
                            continue
                        try:
                            _add(decrypt_field(raw), label)
                        except Exception:     # noqa: BLE001
                            # Undecryptable (rotated key) — skip it rather than
                            # adding ciphertext that can never match.
                            continue
        except Exception as exc:              # noqa: BLE001
            log.debug("credentials: skipping %s for redaction: %s", path, exc)
    return out


def set_template_secret(name: str, value: str, secret_kind: str = "plaintext",
                        list_name: str = "") -> dict:
    """Store a named secret referenced by a template.

    ``secret_kind`` is ``hash`` for an IOS password hash, which must be emitted
    verbatim and can never be re-derived — Part 2's rotation must skip those,
    because "rotating" one means asking the device to generate a new hash.

    **Refuses to replace a secret another list owns.** List-scoped keys already
    make a cross-list collision impossible through
    :func:`template_secret_key`, so this guard exists for the case that
    actually caused the bug: a caller that builds the key itself. Ownership is
    recorded on the entry and checked on write, so the rule holds even when the
    key is constructed somewhere this module cannot see.
    """
    from modules.config import list_slug

    slug = list_slug(list_name) if list_name else split_template_secret_key(name)[0]
    with _lock:
        data = _load()
        store = data.setdefault("template_secrets", {})
        existing = store.get(name)
        if existing:
            owner = existing.get("list", "")
            if owner and slug and owner != slug:
                raise SecretOwnedByAnotherList(
                    f"secret '{name}' belongs to device list '{owner}'; "
                    f"'{slug}' may not overwrite it. This is the collision that "
                    "made one network deploy another network's credentials — "
                    "use a list-scoped key from template_secret_key().")
        store[name] = {
            "value": encrypt_value(value),
            "secret_kind": secret_kind,
            "list": slug,
            "device": split_template_secret_key(name)[1],
            "last_rotated": time.time() if secret_kind != "hash" else None,
        }
        _save(data)
    log.info("credentials: stored template secret '%s' (kind=%s, list=%s)",
             name, secret_kind, slug or "unscoped")
    return {"ok": True}


def get_template_secret(name: str) -> str:
    """Decrypt a named template secret. Empty if unknown."""
    entry = _load().get("template_secrets", {}).get(name)
    return decrypt_value(entry.get("value", "")) if entry else ""


def delete_template_secret(name: str) -> dict:
    """Remove a secret from the store — e.g. one that has just been rotated.

    The old plaintext is dead the moment the device stops accepting it, and a
    dead credential kept in the store is a live copy of something nobody needs.
    Returns ``existed`` so a caller can tell "removed" from "was not there".
    """
    with _lock:
        data = _load()
        existed = name in (data.get("template_secrets") or {})
        if existed:
            del data["template_secrets"][name]
            _save(data)
    if existed:
        log.info("credentials: deleted template secret '%s'", name)
    return {"ok": True, "existed": existed}


def list_template_secrets(list_name: str = "") -> list:
    """Names and kinds only — never values. Filtered to *list_name* when given."""
    from modules.config import list_slug

    want = list_slug(list_name) if list_name else ""
    out = []
    for name, entry in sorted(_load().get("template_secrets", {}).items()):
        slug = entry.get("list", "") or split_template_secret_key(name)[0]
        if want and slug != want:
            continue
        out.append({"name": name, "secret_kind": entry.get("secret_kind", "plaintext"),
                    "rotatable": entry.get("secret_kind") != "hash",
                    "list": slug, "device": entry.get("device", "")})
    return out


def migrate_template_secrets_to_list_scope(list_name: str,
                                           dry_run: bool = True) -> dict:
    """Move legacy ``<host>:<ref>`` keys into *list_name*'s namespace.

    Every key predating list scoping belongs to whichever list was the only one
    — unambiguous here because there has only ever been one. A key that already
    carries a slug is left alone, so this is idempotent and safe to re-run.

    Values are re-encrypted through ``set_template_secret``'s own path rather
    than copied, so the stored shape is whatever that function produces today.
    """
    from modules.config import list_slug

    slug = list_slug(list_name)
    data = _load()
    store = data.get("template_secrets", {})

    moves, skipped = [], []
    for name, entry in sorted(store.items()):
        key_slug, hostname, ref = split_template_secret_key(name)
        if key_slug or entry.get("list"):
            skipped.append({"name": name, "reason": "already list-scoped"})
            continue
        moves.append({"from": name,
                      "to": template_secret_key(list_name, hostname, ref),
                      "secret_kind": entry.get("secret_kind", "plaintext")})

    if dry_run or not moves:
        return {"ok": True, "dry_run": dry_run, "moved": moves,
                "skipped": skipped, "count": len(moves)}

    with _lock:
        data = _load()
        store = data.setdefault("template_secrets", {})
        for move in moves:
            entry = store.get(move["from"])
            if not entry:
                continue
            store[move["to"]] = {**entry, "list": slug,
                                 "device": split_template_secret_key(move["to"])[1]}
            del store[move["from"]]
        _save(data)
    log.warning("credentials: migrated %d template secret(s) into list '%s'",
                len(moves), slug)
    return {"ok": True, "dry_run": False, "moved": moves, "skipped": skipped,
            "count": len(moves)}


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
