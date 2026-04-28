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


def load_key() -> bytes:
    #Load or generate Fernet key stored at `KEY_FILE`.

    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
    with open(KEY_FILE, "rb") as f:
        return f.read()


fernet = Fernet(load_key())


def decrypt_field(value: str) -> str:
    #Decrypt a Fernet-encrypted CSV field value.
    return fernet.decrypt(value.encode()).decode()


def load_saved_devices(filename: str | None = None) -> list[dict[str, Any]]:
    #Load devices from CSV and return a list of dicts.
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


def save_device(device: dict, filename: str | None = None) -> None:
    #Add or update a device in the devices CSV (encrypting creds).
    if not filename:
        filename = DEVICES_FILE
    fieldnames = ["hostname", "device_type", "ip", "username", "password", "secret", "role"]
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

    with open(filename, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(devices)


def delete_device(ip: str, filename: str | None = None) -> None:
    #Delete a device by IP from the CSV file.
    if not filename:
        filename = DEVICES_FILE
    devices = [d for d in load_saved_devices(filename) if d.get("ip") != ip]
    fieldnames = ["hostname", "device_type", "ip", "username", "password", "secret", "role"]
    with open(filename, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(devices)


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
    #Write a list of device dicts to the CSV file.
    if not filename:
        filename = DEVICES_FILE
    fieldnames = ["hostname", "device_type", "ip", "username", "password", "secret", "role"]
    with open(filename, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
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
        fieldnames = ["hostname", "device_type", "ip", "username", "password", "secret", "role"]
        with open(csv_path, mode="w", newline="") as f:
            csv.DictWriter(f, fieldnames=fieldnames).writeheader()


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
