"""config.py

Central configuration for the Network Device Manager.

Defines all runtime file paths (data dir, device lists, encryption key, quick actions),
per-list data directory helpers, user settings load/save helpers, and application
constants (Flask host/port, SSH timeout, TFTP settings, connection flags).
Handles both normal Python execution and PyInstaller frozen executables by resolving
BASE_DIR at import time.
"""

import os
import sys
import json
import re as _re

# Determine base path - handles both normal Python and PyInstaller frozen executable
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Running as normal Python script
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Data directory - stored alongside executable or in project root
DATA_DIR = os.path.join(BASE_DIR, "data")

# Per-list data directories live under data/lists/{slug}/
LISTS_DIR = os.path.join(DATA_DIR, "lists")

# Ensure the data directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LISTS_DIR, exist_ok=True)

# Runtime file paths
DEFAULT_DEVICES_FILE = os.path.join(DATA_DIR, "Devices.csv")
DEVICES_FILE = DEFAULT_DEVICES_FILE  # For backwards compatibility
DEVICE_LISTS_CONFIG = os.path.join(DATA_DIR, "device_lists.json")
QUICK_ACTIONS_FILE = os.path.join(DATA_DIR, "quick_actions.json")
KEY_FILE = os.path.join(DATA_DIR, "key.key")
SECRET_KEY_FILE = os.path.join(DATA_DIR, "secret.key")
USER_SETTINGS_FILE = os.path.join(DATA_DIR, "user_settings.json")


# ---------------------------------------------------------------------------
# Per-list data directory helpers
# ---------------------------------------------------------------------------

def list_slug(name: str) -> str:
    """Convert a list name to a filesystem-safe folder slug."""
    return _re.sub(r"[^\w]+", "_", name.lower()).strip("_") or "default"


def get_list_data_dir(list_name: str) -> str:
    """Return (and create) the data directory for a specific device list."""
    path = os.path.join(LISTS_DIR, list_slug(list_name))
    os.makedirs(path, exist_ok=True)
    return path


def get_current_list_name() -> str:
    """Return the name of the currently active device list."""
    try:
        with open(DEVICE_LISTS_CONFIG) as fh:
            return json.load(fh).get("current_list", "Default")
    except Exception:
        return "Default"


def get_current_list_data_dir() -> str:
    """Return (and create) the data directory for the current device list."""
    return get_list_data_dir(get_current_list_name())


# ---------------------------------------------------------------------------
# User Settings Functions
# ---------------------------------------------------------------------------

def load_user_settings() -> dict:
    """Load user settings from JSON file."""
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_user_settings(settings: dict) -> bool:
    """Save user settings to JSON file."""
    try:
        with open(USER_SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        return True
    except IOError:
        return False


def get_user_setting(key: str, default=None):
    """Get a specific user setting."""
    settings = load_user_settings()
    return settings.get(key, default)


def set_user_setting(key: str, value) -> bool:
    """Set a specific user setting."""
    settings = load_user_settings()
    settings[key] = value
    return save_user_settings(settings)

# Application settings
PING_INTERVAL = 5
FAST_CLI = True

# Flask web server settings
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_DEBUG = False

# File transfer settings
# TFTP settings for file upload functionality
# Update these values to match your TFTP server configuration
TFTP_ROOT = "C:/TFTP-Root"  # Local TFTP root directory

# Default TFTP server IP - can be overridden by user settings
_DEFAULT_TFTP_SERVER_IP = "192.168.0.30"
TFTP_SERVER_IP = get_user_setting("tftp_server_ip", _DEFAULT_TFTP_SERVER_IP)

# Ensure TFTP root exists
os.makedirs(TFTP_ROOT, exist_ok=True)

# File transfer method: 'tftp' or 'scp'
# SCP is more reliable and secure but requires SCP to be enabled on the device
# NOTE: SCP requires 'ip scp server enable' on Cisco devices
FILE_TRANSFER_METHOD = "tftp"  # Options: 'tftp', 'scp'

# Connection timeouts
SSH_TIMEOUT = 60  # Seconds for SSH command execution
SSH_PORT = 22  # Default SSH port
