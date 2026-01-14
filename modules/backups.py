"""
Configuration Backup and Restore Module

Handles backup operations for device configurations:
- Save running-config to startup-config
- Download configs to local machine
- View backup history
- Compare configurations (diff view)
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Optional
import difflib

# Configuration
BACKUPS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "backups"))
BACKUP_INDEX_FILE = os.path.join(BACKUPS_DIR, "backup_index.json")

# Ensure backups directory exists
os.makedirs(BACKUPS_DIR, exist_ok=True)


def save_running_to_startup(conn) -> str:
    """
    Save running-config to startup-config on the device.

    Args:
        conn: Active Netmiko connection object

    Returns:
        str: Command output
    """
    output = conn.send_command_timing("write memory")
    return output


def get_running_config(conn) -> str:
    """
    Retrieve the running configuration from a device.

    Args:
        conn: Active Netmiko connection object

    Returns:
        str: Running configuration text
    """
    config = conn.send_command("show running-config", read_timeout=30)
    return config


def get_startup_config(conn) -> str:
    """
    Retrieve the startup configuration from a device.

    Args:
        conn: Active Netmiko connection object

    Returns:
        str: Startup configuration text
    """
    config = conn.send_command("show startup-config", read_timeout=30)
    return config


def save_config_backup(ip: str, hostname: str, config: str, config_type: str = "running") -> Dict[str, str]:
    """
    Save a configuration backup to local storage.

    Args:
        ip: Device IP address
        hostname: Device hostname
        config: Configuration text to save
        config_type: Type of config ("running" or "startup")

    Returns:
        dict: Backup metadata (filename, timestamp, size)
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{hostname}_{ip}_{config_type}_{timestamp}.cfg"
    filepath = os.path.join(BACKUPS_DIR, filename)

    # Save config file
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(config)

    # Get file size
    file_size = os.path.getsize(filepath)

    # Create backup metadata
    backup_info = {
        "filename": filename,
        "ip": ip,
        "hostname": hostname,
        "config_type": config_type,
        "timestamp": timestamp,
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "size": file_size,
        "filepath": filepath
    }

    # Update backup index
    _update_backup_index(backup_info)

    return backup_info


def get_backup_history(ip: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """
    Get backup history for all devices or a specific device.

    Args:
        ip: Optional IP address to filter by
        limit: Maximum number of backups to return

    Returns:
        list: List of backup metadata dictionaries
    """
    if not os.path.exists(BACKUP_INDEX_FILE):
        return []

    with open(BACKUP_INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)

    backups = index.get("backups", [])

    # Filter by IP if specified
    if ip:
        backups = [b for b in backups if b.get("ip") == ip]

    # Sort by timestamp (newest first)
    backups.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    # Apply limit
    return backups[:limit]


def get_backup_content(filename: str) -> Optional[str]:
    """
    Read the content of a backup file.

    Args:
        filename: Name of the backup file

    Returns:
        str: Configuration content or None if not found
    """
    filepath = os.path.join(BACKUPS_DIR, filename)

    if not os.path.exists(filepath):
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def compare_configs(config1: str, config2: str) -> str:
    """
    Compare two configurations and return unified diff.

    Args:
        config1: First configuration (older)
        config2: Second configuration (newer)

    Returns:
        str: Unified diff output
    """
    diff = difflib.unified_diff(
        config1.splitlines(keepends=True),
        config2.splitlines(keepends=True),
        fromfile="Config 1",
        tofile="Config 2",
        lineterm=""
    )

    return "".join(diff)


def delete_backup(filename: str) -> bool:
    """
    Delete a backup file and remove from index.

    Args:
        filename: Name of the backup file to delete

    Returns:
        bool: True if successful, False otherwise
    """
    filepath = os.path.join(BACKUPS_DIR, filename)

    try:
        # Delete file
        if os.path.exists(filepath):
            os.remove(filepath)

        # Remove from index
        if os.path.exists(BACKUP_INDEX_FILE):
            with open(BACKUP_INDEX_FILE, "r", encoding="utf-8") as f:
                index = json.load(f)

            index["backups"] = [b for b in index.get("backups", []) if b.get("filename") != filename]

            with open(BACKUP_INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump(index, f, indent=2)

        return True
    except Exception:
        return False


def _update_backup_index(backup_info: Dict) -> None:
    """
    Update the backup index file with new backup information.

    Args:
        backup_info: Backup metadata dictionary
    """
    # Load existing index
    if os.path.exists(BACKUP_INDEX_FILE):
        with open(BACKUP_INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {"backups": []}

    # Add new backup
    index["backups"].append(backup_info)

    # Save updated index
    with open(BACKUP_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def get_backup_stats() -> Dict[str, int]:
    """
    Get statistics about backups.

    Returns:
        dict: Statistics (total_backups, total_devices, total_size_mb)
    """
    backups = get_backup_history(limit=10000)

    total_backups = len(backups)
    unique_devices = len(set(b.get("ip") for b in backups))
    total_size = sum(b.get("size", 0) for b in backups)
    total_size_mb = round(total_size / (1024 * 1024), 2)

    return {
        "total_backups": total_backups,
        "total_devices": unique_devices,
        "total_size_mb": total_size_mb
    }
