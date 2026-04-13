"""backups.py

Configuration backup retrieval and local storage for network devices.

Fetches running-config and startup-config via SSH (Netmiko), saves them as
timestamped .cfg files under data/lists/{slug}/backups/, and maintains a
backup_index.json for history and stats.  Provides unified-diff comparison
between any two stored configs.  All paths are scoped to the currently active
device list so switching lists gives each list its own backup history.
"""

import os
import json
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


def save_running_to_startup(conn) -> str:
    output = conn.send_command_timing("write memory")
    return output


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
    filename    = f"{hostname}_{ip}_{config_type}_{timestamp}.cfg"
    filepath    = os.path.join(backups_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(config)

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


def get_backup_content(filename: str) -> Optional[str]:
    """Read the content of a backup file from the current list's backup directory."""
    filepath = os.path.join(get_backups_dir(), filename)
    if not os.path.exists(filepath):
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
    backups_dir = get_backups_dir()
    index_file  = get_backup_index_file()
    filepath    = os.path.join(backups_dir, filename)

    try:
        if os.path.exists(filepath):
            os.remove(filepath)

        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
            index["backups"] = [b for b in index.get("backups", []) if b.get("filename") != filename]
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(index, f, indent=2)

        return True
    except Exception:
        return False


def _update_backup_index(backup_info: Dict) -> None:
    """Append backup metadata to the current list's index file."""
    index_file = get_backup_index_file()

    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {"backups": []}

    index["backups"].append(backup_info)

    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def get_backup_stats() -> Dict[str, int]:
    """Return backup statistics for the current list."""
    backups       = get_backup_history(limit=10000)
    total_size    = sum(b.get("size", 0) for b in backups)
    return {
        "total_backups":  len(backups),
        "total_devices":  len(set(b.get("ip") for b in backups)),
        "total_size_mb":  round(total_size / (1024 * 1024), 2),
    }
