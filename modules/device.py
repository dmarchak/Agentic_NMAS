"""device.py

Device CRUD, credential encryption, and multi-list management.

Stores the device inventory as per-list CSV files under data/lists/{slug}/devices.csv.
Credentials (password, enable secret) are encrypted with a Fernet key stored at
data/key.key; the key is auto-generated on first run.  Provides add/update/delete
operations, list create/rename/delete/switch, and a one-time migration that moves
pre-folder-structure data into the correct per-list directories.
"""

import csv
import os
import json
import re
import logging
from typing import Any
from cryptography.fernet import Fernet
from modules.config import (
    KEY_FILE, DEVICES_FILE, DATA_DIR, LISTS_DIR, DEVICE_LISTS_CONFIG,
    DEFAULT_DEVICES_FILE, list_slug, get_list_data_dir,
)

logger = logging.getLogger(__name__)

# Fernet instance is created once at module import time and used to
# encrypt/decrypt credential fields stored in the CSV. 


#: Columns of ``devices.csv``, defined once.
#:
#: ``device_type`` is the **Netmiko driver** — how to open a session.
#: ``platform`` is the **config dialect** — how to parse and render config.
#: They answer different questions and must not be conflated; see
#: modules/nsot/platform.py. Both ``platform`` and ``device_uid`` are additive
#: and blank-tolerant, so lists written before they existed load unchanged.
DEVICE_CSV_FIELDS = ["hostname", "device_type", "ip", "username", "password",
                     "secret", "role", "device_uid", "platform"]


def load_key() -> bytes:
    #Load or generate Fernet key stored at `KEY_FILE`.

    # The SECOND producer of key.key -- `secrets_store._get_fernet()` is the
    # other, deliberately, to avoid importing this module's device-list side
    # effects. Two producers means both must create it owner-only; a fix in
    # one is not a fix.
    from modules.config import open_secure, secure_file

    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open_secure(KEY_FILE, "wb") as f:
            f.write(key)
    else:
        # Created before this existed, quite possibly 0644.
        secure_file(KEY_FILE)
    with open(KEY_FILE, "rb") as f:
        return f.read()


fernet = Fernet(load_key())


def decrypt_field(value: str) -> str:
    #Decrypt a Fernet-encrypted CSV field value.
    return fernet.decrypt(value.encode()).decode()


def _list_name_for_path(filename: str) -> str:
    """Reverse a ``data/lists/{slug}/devices.csv`` path to its list name."""
    try:
        slug = os.path.basename(os.path.dirname(os.path.abspath(filename)))
        config = _load_device_lists_config()
        for name, list_slug_value in (config.get("lists") or {}).items():
            if list_slug_value == slug:
                return name
    except Exception:                          # noqa: BLE001
        pass
    return ""


def _load_devices_csv(filename: str | None = None) -> list[dict[str, Any]]:
    """Read a device CSV. Credential fields stay encrypted; callers decrypt."""
    if not filename:
        filename = DEVICES_FILE
    logger.debug("Loading devices from: %s", filename)
    if not os.path.isabs(filename):
        filename = os.path.abspath(filename)
    if not os.path.exists(filename):
        logger.debug("Devices file not found: %s", filename)
        return []
    with open(filename, mode="r", newline="") as f:
        return list(csv.DictReader(f))


class UnknownDeviceList(ValueError):
    """A path that names no list and is not on disk. See `load_saved_devices`."""


def active_devices_file() -> str:
    """The **active list's** CSV path.

    `DEVICES_FILE` is `data/Devices.csv`, a pre-lists constant kept "for
    backwards compatibility" that nothing has written since lists existed. It
    was also `load_saved_devices()`'s no-argument default, so an ad-hoc call
    read a file that does not exist and got `[]` — an honestly empty fleet,
    and every count downstream honestly zero.

    **A read may derive the active list; a write may not.** This is a read.
    """
    from modules.config import get_current_list_data_dir

    return os.path.join(get_current_list_data_dir(), "devices.csv")


def load_saved_devices(filename: str | None = None) -> list[dict[str, Any]]:
    """Load the devices for the list owning *filename*.

    The single dispatch point between a local CSV list and a NetBox-sourced one.
    There are ~87 call sites for this function across the codebase; routing the
    decision through here means none of them need to know which kind of list
    they are looking at.

    NetBox-sourced lists are served from a cache that a background thread keeps
    fresh — **this function never performs network I/O**, because several of its
    callers sit in request handlers and tight loops.

    **It takes a PATH, not a list name**, and two failures of that this week
    both ended in a silently empty fleet rather than a refusal:
    `nmas-netbox-repair-addresses` passed a name and reported *"nothing to
    create"*; and a no-argument call read `DEVICES_FILE` and returned zero
    rows. With ~87 call sites the blast radius is the point — every downstream
    count is *honestly* zero, which is the hardest kind of wrong to notice.

    So the two ways of not knowing which list was meant are now separated:

    * **no argument** resolves the **active list** (:func:`active_devices_file`)
      rather than a pre-lists constant nothing writes;
    * **a string that is not a path at all** — no separator, no `.csv`, and
      not a file — raises :class:`UnknownDeviceList`. Measured before changing
      it: of 87 call sites, **none** passes no argument and **none** passes a
      name-shaped variable, so no in-repo caller can reach the refusal, which
      is what makes refusing safe rather than brave.

    A correctly built path whose file is absent still returns `[]`: a list with
    no devices yet is a real state, and onboarding writes that file only at
    promotion. The first version of the refusal missed that and broke twelve
    tests passing `<tmpdir>/devices.csv` — the discriminator had to be measured
    against the real callers, not reasoned about.
    """
    if not filename:
        filename = active_devices_file()

    # THE REFUSAL IS SHAPE-BASED, and the shape was MEASURED against the real
    # callers rather than reasoned about. The first version refused any path
    # that named no known list and did not exist -- and broke twelve tests
    # passing `<tmpdir>/devices.csv`, which is a correctly built path for a
    # directory that has no file yet. That is a legitimate state; a bare list
    # name is not.
    #
    # So: no separator and no `.csv` suffix is not a path at all. It is the
    # `nmas-netbox-repair-addresses` shape exactly -- `"Default"` where
    # `data/lists/default/devices.csv` was wanted -- and no legitimate caller
    # can produce it.
    looks_like_a_path = (os.sep in filename or "/" in filename
                         or filename.lower().endswith(".csv"))
    if not looks_like_a_path and not os.path.exists(filename):
        raise UnknownDeviceList(
            f"{filename!r} is not a path. load_saved_devices() takes the PATH "
            "to a list's devices.csv, never a list NAME — resolve it through "
            "get_device_lists() or get_current_device_list(). Refusing rather "
            "than returning an empty fleet, which reads as 'this network has "
            "no devices' and makes every count downstream honestly zero.")

    list_name = _list_name_for_path(filename)
    if list_name:
        try:
            from modules.inventory.source_config import is_netbox_sourced
            if is_netbox_sourced(list_name):
                from modules.inventory import load_netbox_devices
                devices, _skipped, _meta = load_netbox_devices(list_name)
                return devices
        except Exception as exc:               # noqa: BLE001
            # A broken NetBox path must not take down every caller of this
            # function; fall through to whatever the CSV holds.
            logger.error("Inventory dispatch failed for '%s': %s", list_name, exc)

    return _load_devices_csv(filename)


def _refuse_if_netbox_sourced(filename: str | None, operation: str) -> None:
    """Raise if *filename* belongs to a NetBox-sourced list.

    Identity is owned by NetBox for those lists, so NMAS never writes the CSV.
    The UI disables these actions too; this is the backend half of that.
    """
    list_name = _list_name_for_path(filename or DEVICES_FILE)
    if not list_name:
        return
    try:
        from modules.inventory.source_config import is_netbox_sourced
    except ImportError:
        return
    if is_netbox_sourced(list_name):
        raise PermissionError(
            f"'{list_name}' takes its inventory from NetBox, so NMAS cannot {operation} "
            "a device here. Edit the device in NetBox and refresh the list."
        )


def save_device(device: dict, filename: str | None = None) -> None:
    #Add or update a device in the devices CSV (encrypting creds).
    _refuse_if_netbox_sourced(filename, "add or edit")
    if not filename:
        filename = DEVICES_FILE
    fieldnames = DEVICE_CSV_FIELDS
    encrypted = device.copy()
    encrypted["password"] = fernet.encrypt(device["password"].encode()).decode()
    encrypted["secret"] = fernet.encrypt(device["secret"].encode()).decode()
    encrypted.setdefault("role", "router")

    devices: list[dict] = []
    if os.path.exists(filename):
        with open(filename, mode="r", newline="") as f:
            devices = [row for row in csv.DictReader(f)]
            # replace if exists
            devices = [
                encrypted if row.get("ip") == device.get("ip") else row
                for row in devices
            ]
    if not any(row.get("ip") == device.get("ip") for row in devices):
        devices.append(encrypted)

    with _open_csv_secure(filename) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(devices)


def _open_csv_secure(path: str):
    """A devices.csv holds every device's Fernet-encrypted credentials, so it
    is written owner-only. Measured 2026-09-25: the live file (and two older
    copies) were 0664 from plain open() writes, and the secret-storage check
    did not know the file existed. open_secure also tightens an existing
    file, so the next write heals it."""
    from modules.config import open_secure
    return open_secure(path, "w", newline="")


def delete_device(ip: str, filename: str | None = None) -> None:
    _refuse_if_netbox_sourced(filename, "delete")
    #Delete a device by IP from the CSV file.
    if not filename:
        filename = DEVICES_FILE
    devices = [d for d in load_saved_devices(filename) if d.get("ip") != ip]
    fieldnames = DEVICE_CSV_FIELDS
    with _open_csv_secure(filename) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(devices)
    _sync_manifest_platforms(filename)


def _sync_manifest_platforms(csv_path: str) -> None:
    """Carry the CSV ``platform`` column into the manifest.

    The local-list counterpart of the NetBox refresh hook: a devices.csv
    rewrite *is* this list's inventory refresh. Best effort — a device list
    with no repo yet has nothing to update, and a failure here must never
    prevent the inventory itself from being saved.
    """
    try:
        from modules.nsot import manifest as _m
        list_name = _list_name_for_path(csv_path)
        if not list_name:
            return
        repo = os.path.join(os.path.dirname(os.path.abspath(csv_path)), "config_repo")
        if os.path.isdir(repo):
            _m.sync_platforms(repo, list_name)
    except Exception as exc:                   # noqa: BLE001
        logger.debug("device: manifest platform sync failed for %s: %s", csv_path, exc)


def get_device_context(dev: dict, filesystem: str | None = None):
    #Use a temporary connection to build filesystems and file list for device.

    def execute(conn):
        # Filesystems
        fs_output = conn.send_command_timing("dir ?")
        filesystems: list[str] = []
        for line in fs_output.splitlines():
            line = line.strip()
            parts = line.split()
            if parts and parts[0].endswith(":"):
                filesystems.append(parts[0])

        # Default to first filesystem
        fs = filesystem or (filesystems[0] if filesystems else "")

        # Files in selected filesystem
        file_list: list[str] = []
        if fs:
            dir_output = conn.send_command(f"dir {fs}")
            if "No files" not in dir_output and "Error opening" not in dir_output:
                for line in dir_output.splitlines():
                    line = line.strip()
                    if (
                        not line
                        or line.lower().startswith("directory")
                        or "bytes" in line.lower()
                        or "(" in line
                        or ")" in line
                        or line.endswith(":")
                    ):
                        continue
                    parts = line.split()
                    if len(parts) >= 1 and parts[-1] and not parts[-1].endswith(":"):
                        file_list.append(parts[-1])

        return filesystems, file_list, fs

    # Import here to avoid circular imports: modules.connection imports
    # modules.device in other places, load `with_temp_connection`
    # only when needed at runtime.
    from modules.connection import with_temp_connection

    # Run the small `execute` closure using a fresh temporary Netmiko
    # connection provided by `with_temp_connection`. This keeps the
    # device module synchronous and simple to test while delegating
    # connection lifecycle management to the connection module.
    return with_temp_connection(dev, execute)


def write_devices_csv(devices: list[dict], filename: str | None = None) -> None:
    _refuse_if_netbox_sourced(filename, "rewrite the device list for")
    #Write a list of device dicts to the CSV file.
    # Device passwords and enable secrets live here and are part of what
    # redaction matches, so a rewrite must invalidate the cached table — a new
    # password is otherwise unredacted until the TTL expires.
    try:
        from modules.redact import invalidate_cache
        invalidate_cache()
    except Exception:                          # noqa: BLE001
        pass
    if not filename:
        filename = DEVICES_FILE
    fieldnames = DEVICE_CSV_FIELDS
    with _open_csv_secure(filename) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(devices)


# ---------------------------------------------------------------------------
# Device List Management Functions
# ---------------------------------------------------------------------------

def _load_device_lists_config() -> dict:
    """Load the device lists configuration file, migrating old format if needed."""
    if os.path.exists(DEVICE_LISTS_CONFIG):
        with open(DEVICE_LISTS_CONFIG, "r") as f:
            config = json.load(f)
        # Migrate old format (values are CSV filenames) to new format (values are folder slugs)
        if _needs_migration(config):
            config = _migrate_to_folder_structure(config)
        return config
    # Fresh install — create default list folder and config
    default_slug = list_slug("Default")
    default_dir  = get_list_data_dir("Default")
    _ensure_devices_csv(default_dir)
    config = {"current_list": "Default", "lists": {"Default": default_slug}}
    _save_device_lists_config(config)
    return config


def _needs_migration(config: dict) -> bool:
    """Return True if device_lists.json still uses the old CSV-filename format."""
    for value in config.get("lists", {}).values():
        if isinstance(value, str) and value.endswith(".csv"):
            return True
    return False


def _migrate_to_folder_structure(config: dict) -> dict:
    """
    One-time migration: move each list's CSV into data/lists/{slug}/devices.csv,
    and move shared data (backups, playbooks, KB, notes) into the current list's folder.
    """
    import shutil

    lists   = config.get("lists", {})
    current = config.get("current_list", "Default")

    # 1. Move each CSV into its list folder
    for name, value in list(lists.items()):
        if not (isinstance(value, str) and value.endswith(".csv")):
            continue
        slug     = list_slug(name)
        list_dir = get_list_data_dir(name)
        old_csv  = os.path.join(DATA_DIR, value)
        new_csv  = os.path.join(list_dir, "devices.csv")
        if os.path.exists(old_csv) and not os.path.exists(new_csv):
            shutil.move(old_csv, new_csv)
            logger.info("Migrated %s → %s", old_csv, new_csv)
        elif not os.path.exists(new_csv):
            _ensure_devices_csv(list_dir)
        lists[name] = slug

    # 2. Move shared data into the current list's folder
    current_dir = get_list_data_dir(current)
    _move_if_absent(os.path.join(DATA_DIR, "backups"),     os.path.join(current_dir, "backups"))
    _move_if_absent(os.path.join(DATA_DIR, "playbooks"),   os.path.join(current_dir, "playbooks"))
    _move_if_absent(os.path.join(DATA_DIR, "network_kb.json"), os.path.join(current_dir, "network_kb.json"))
    _move_if_absent(os.path.join(DATA_DIR, "lab_notes.md"),    os.path.join(current_dir, "lab_notes.md"))

    config["lists"] = lists
    _save_device_lists_config(config)
    logger.info("Device list migration complete. Current list: %s → %s", current, current_dir)
    return config


def _move_if_absent(src: str, dst: str) -> None:
    """Move src to dst only if src exists and dst does not."""
    import shutil
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.move(src, dst)
        logger.info("Migrated %s → %s", src, dst)


def _ensure_devices_csv(list_dir: str) -> None:
    """Create an empty devices.csv with headers if it doesn't exist."""
    csv_path = os.path.join(list_dir, "devices.csv")
    if not os.path.exists(csv_path):
        with _open_csv_secure(csv_path) as f:
            csv.DictWriter(f, fieldnames=DEVICE_CSV_FIELDS).writeheader()


def _save_device_lists_config(config: dict) -> None:
    """Save the device lists configuration file."""
    with open(DEVICE_LISTS_CONFIG, "w") as f:
        json.dump(config, f, indent=2)


def get_device_lists() -> list[dict]:
    """Get all available device lists with their device counts."""
    config  = _load_device_lists_config()
    current = config.get("current_list", "Default")
    lists   = config.get("lists", {})

    result = []
    for name, slug in lists.items():
        csv_path     = os.path.join(LISTS_DIR, slug, "devices.csv")
        device_count = len(load_saved_devices(csv_path)) if os.path.exists(csv_path) else 0
        result.append({
            "name":         name,
            "filename":     slug,
            "device_count": device_count,
            "is_current":   name == current,
        })

    return sorted(result, key=lambda x: x["name"].lower())


def get_current_device_list() -> tuple[str, str]:
    """Return (list_name, full_path_to_devices.csv) for the active list."""
    config  = _load_device_lists_config()
    current = config.get("current_list", "Default")
    slug    = config.get("lists", {}).get(current, list_slug(current))
    csv_path = os.path.join(LISTS_DIR, slug, "devices.csv")
    return current, csv_path


def set_current_device_list(list_name: str) -> bool:
    """Set the current device list by name. Returns True on success."""
    config = _load_device_lists_config()
    if list_name not in config.get("lists", {}):
        return False
    config["current_list"] = list_name
    _save_device_lists_config(config)
    return True


def create_device_list(list_name: str) -> tuple[bool, str]:
    """Create a new device list. Returns (success, message)."""
    if not list_name or not list_name.strip():
        return False, "List name cannot be empty"

    list_name = list_name.strip()

    if not re.match(r'^[\w\s\-]+$', list_name):
        return False, "List name can only contain letters, numbers, spaces, hyphens, and underscores"

    if len(list_name) > 50:
        return False, "List name must be 50 characters or less"

    config = _load_device_lists_config()
    lists  = config.get("lists", {})

    for existing in lists:
        if existing.lower() == list_name.lower():
            return False, f"A list named '{existing}' already exists"

    # Ensure the slug is unique as a folder name
    slug = list_slug(list_name)
    counter = 1
    base_slug = slug
    while os.path.exists(os.path.join(LISTS_DIR, slug)):
        slug = f"{base_slug}_{counter}"
        counter += 1

    list_dir = os.path.join(LISTS_DIR, slug)
    os.makedirs(list_dir, exist_ok=True)
    _ensure_devices_csv(list_dir)

    lists[list_name] = slug
    config["lists"] = lists
    _save_device_lists_config(config)

    logger.info("Created device list: %s (folder: %s)", list_name, slug)
    return True, f"Device list '{list_name}' created successfully"


def delete_device_list(list_name: str) -> tuple[bool, str]:
    """Delete a device list and all its data. Returns (success, message)."""
    import shutil

    if not list_name:
        return False, "List name is required"

    config  = _load_device_lists_config()
    lists   = config.get("lists", {})
    current = config.get("current_list", "Default")

    if list_name not in lists:
        return False, f"List '{list_name}' not found"

    if len(lists) <= 1:
        return False, "Cannot delete the last device list"

    slug     = lists[list_name]
    list_dir = os.path.join(LISTS_DIR, slug)
    if os.path.exists(list_dir):
        import stat

        def _force_remove(func, path, _exc):
            # Windows marks some files read-only (e.g. golden config .cfg files);
            # clear the attribute and retry the failed delete operation.
            os.chmod(path, stat.S_IWRITE)
            func(path)

        shutil.rmtree(list_dir, onerror=_force_remove)
        logger.info("Deleted list folder: %s", list_dir)

    del lists[list_name]
    config["lists"] = lists

    if current == list_name:
        config["current_list"] = next(iter(lists.keys()))
        logger.info("Switched current list to: %s", config["current_list"])

    _save_device_lists_config(config)
    return True, f"Device list '{list_name}' deleted successfully"


def rename_device_list(old_name: str, new_name: str) -> tuple[bool, str]:
    """Rename a device list.

    Returns a tuple of (success, message).
    """
    if not old_name or not new_name:
        return False, "Both old and new names are required"

    new_name = new_name.strip()

    # Validate new name format
    if not re.match(r'^[\w\s\-]+$', new_name):
        return False, "List name can only contain letters, numbers, spaces, hyphens, and underscores"

    if len(new_name) > 50:
        return False, "List name must be 50 characters or less"

    config = _load_device_lists_config()
    lists = config.get("lists", {})
    current = config.get("current_list", "Default")

    if old_name not in lists:
        return False, f"List '{old_name}' not found"

    # Check if new name already exists (case-insensitive, excluding current)
    for existing_name in lists.keys():
        if existing_name.lower() == new_name.lower() and existing_name != old_name:
            return False, f"A list named '{existing_name}' already exists"

    # Keep the same folder slug — only the display name changes
    slug = lists[old_name]
    del lists[old_name]
    lists[new_name] = slug
    config["lists"] = lists

    # Update current if needed
    if current == old_name:
        config["current_list"] = new_name

    _save_device_lists_config(config)

    logger.info(f"Renamed device list: {old_name} -> {new_name}")
    return True, f"Device list renamed to '{new_name}'"
