"""backups.py

Configuration backup retrieval and local storage for network devices.

Fetches running-config and startup-config via SSH (Netmiko), saves them as
timestamped .cfg files under data/lists/{slug}/backups/, and maintains a
backup_index.json for history and stats.  Provides unified-diff comparison
between any two stored configs.  All paths are scoped to the currently active
device list so switching lists gives each list its own backup history.
"""

import logging
import os
import json
import re
from datetime import datetime
from typing import List, Dict, Optional
import difflib


def get_backups_dir() -> str:
    """Return (and create) the backups directory for the current device list."""
    from modules.config import get_current_list_data_dir
    path = os.path.join(get_current_list_data_dir(), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def get_backup_index_file() -> str:
    """Return the path to the backup index for the current device list."""
    return os.path.join(get_backups_dir(), "backup_index.json")


def get_running_config(conn) -> str:
    return conn.send_command("show running-config", read_timeout=30)


def get_startup_config(conn) -> str:
    return conn.send_command("show startup-config", read_timeout=30)


def save_config_backup(ip: str, hostname: str, config: str, config_type: str = "running") -> Dict[str, str]:
    """
    Save a configuration backup to the current list's backup directory.

    Returns dict: Backup metadata (filename, timestamp, size, …)
    """
    backups_dir = get_backups_dir()
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    # A NEW file, never over another backup (the operator, 2026-10-01): the
    # name is to the second, so two backups of one device in one second (a
    # double click on Backup Config, the agent's backup beside a person's)
    # had the second silently replace the first. Created exclusively; a name
    # already taken gets the next free `_2`, `_3`.
    stem = f"{hostname}_{ip}_{config_type}_{timestamp}"
    n = 1
    while True:
        filename = f"{stem}.cfg" if n == 1 else f"{stem}_{n}.cfg"
        filepath = os.path.join(backups_dir, filename)
        try:
            with open(filepath, "x", encoding="utf-8") as f:
                f.write(config)
            break
        except FileExistsError:
            n += 1

    backup_info = {
        "filename":    filename,
        "ip":          ip,
        "hostname":    hostname,
        "config_type": config_type,
        "timestamp":   timestamp,
        "datetime":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "size":        os.path.getsize(filepath),
        "filepath":    filepath,
    }

    _update_backup_index(backup_info)
    return backup_info


def get_backup_history(ip: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """
    Get backup history for the current list — optionally filtered by device IP.
    """
    index_file = get_backup_index_file()
    if not os.path.exists(index_file):
        return []

    with open(index_file, "r", encoding="utf-8") as f:
        index = json.load(f)

    backups = index.get("backups", [])
    if ip:
        backups = [b for b in backups if b.get("ip") == ip]

    backups.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return backups[:limit]


log = logging.getLogger(__name__)

#: What a backup file is called: the name save_config_backup() writes, nothing else.
_BACKUP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*\.cfg$")


def backup_path(filename: str) -> Optional[str]:
    """The path of the backup *filename* in the current list's backups folder, or None.

    THE ONE resolver for a name a request supplies (C324, 2026-10-02): compare joined the
    form's names onto the folder unchecked, so ``../../key.key`` read the Fernet key and an
    absolute path read any file the service can, from an ungated route. A name with a
    separator, a leading dot, or anything but a backup's ``.cfg`` name is refused, and so is a
    real path outside the folder (a symlink planted inside it)."""
    if not filename or os.path.basename(filename) != filename or not _BACKUP_NAME.match(filename):
        log.warning("backups: refused a name that is not a backup file name")
        return None
    folder = os.path.realpath(get_backups_dir())
    path = os.path.realpath(os.path.join(folder, filename))
    if os.path.dirname(path) != folder:
        log.warning("backups: refused a backup name resolving outside the backups folder")
        return None
    return path


def get_backup_content(filename: str) -> Optional[str]:
    """Read the content of a backup file from the current list's backup directory; None
    for a name ``backup_path()`` refuses or a file that is not there."""
    filepath = backup_path(filename)
    if filepath is None or not os.path.isfile(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def compare_configs(config1: str, config2: str) -> str:
    """Return a unified diff of two configuration strings."""
    diff = difflib.unified_diff(
        config1.splitlines(keepends=True),
        config2.splitlines(keepends=True),
        fromfile="Config 1",
        tofile="Config 2",
        lineterm="",
    )
    return "".join(diff)


def delete_backup(filename: str) -> bool:
    """Delete a backup file and remove it from the index."""
    index_file  = get_backup_index_file()
    filepath    = backup_path(filename)
    if filepath is None:
        return False

    try:
        if os.path.exists(filepath):
            os.remove(filepath)

        if os.path.exists(index_file):
            from modules.filestore import PathLock, read_json_for_write, write_atomic
            with PathLock(index_file):          # the save's lock: one index, one writer
                index = read_json_for_write(index_file, empty={"backups": []})
                index["backups"] = [b for b in index.get("backups", [])
                                    if b.get("filename") != filename]
                write_atomic(index_file, json.dumps(index, indent=2))

        return True
    except Exception:
        return False


def _update_backup_index(backup_info: Dict) -> None:
    """Append backup metadata to the current list's index file."""
    from modules.filestore import PathLock, read_json_for_write, write_atomic

    index_file = get_backup_index_file()
    # Two backups at once (the same event the name above handles) each read
    # the index and wrote it whole, truncating in place: one entry was lost.
    # The store's own fix (C158): the lock, a refusal on an unreadable index,
    # and an atomic replace.
    with PathLock(index_file):
        index = read_json_for_write(index_file, empty={"backups": []})
        index.setdefault("backups", []).append(backup_info)
        write_atomic(index_file, json.dumps(index, indent=2))


def get_backup_stats() -> Dict[str, int]:
    """Return backup statistics for the current list."""
    backups       = get_backup_history(limit=10000)
    total_size    = sum(b.get("size", 0) for b in backups)
    return {
        "total_backups":  len(backups),
        "total_devices":  len(set(b.get("ip") for b in backups)),
        "total_size_mb":  round(total_size / (1024 * 1024), 2),
    }
