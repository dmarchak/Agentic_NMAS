"""config.py

Central configuration for the Network Device Manager.

Defines all runtime file paths (data dir, device lists, encryption key, quick actions),
per-list data directory helpers, user settings load/save helpers, and application
constants (Flask host/port, SSH timeout, TFTP settings, connection flags).
Handles both normal Python execution and PyInstaller frozen executables by resolving
BASE_DIR at import time.
"""

import logging
import os
import sys
import json
import re as _re

log = logging.getLogger(__name__)

# Determine base path - handles both normal Python and PyInstaller frozen executable
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Running as normal Python script
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Data directory - stored alongside executable or in project root.
#
# ONE OWNER. Fifteen places computed `<repo>/data` for themselves until
# 2026-09-26, so no single setting could say where the store is. The test
# suite found out why that matters: run from a checkout, it wrote fixture lists
# into the live store, and the only guard looked for NEW paths, so paths that
# already existed made it blind. `NMAS_DATA_DIR` moves the whole store; the
# suite sets it to a temporary directory before anything imports this module.
# Every other module derives its paths from DATA_DIR, and a test (AST, with a
# floor) refuses a second computation of the path.
DATA_DIR = os.environ.get("NMAS_DATA_DIR") or os.path.join(BASE_DIR, "data")

# Per-list data directories live under data/lists/{slug}/
LISTS_DIR = os.path.join(DATA_DIR, "lists")

# ---------------------------------------------------------------------------
# File modes — set at CREATION, not by hand afterwards
# ---------------------------------------------------------------------------

#: Owner-only. `data/` holds the Fernet key, every device credential, the
#: settings file and the golden repositories.
DIR_MODE = 0o700
#: Owner-only. Anything under `data/` plus `.env`.
FILE_MODE = 0o600

_IS_WINDOWS = os.name == "nt"


def secure_dir(path: str) -> str:
    """Create *path* owner-only, and tighten it if it already exists.

    **Nothing in this program set a mode before.** `os.makedirs()` and
    `open()` take the process umask, which on the deployment host is 022 —
    so `data/` was created 0755 and every file in it 0644, world-readable,
    including `key.key`. Measured on the live install: the Anthropic API key
    sat in a 0644 `.env` on a LAN-reachable host for three weeks.

    Fixing modes by hand fixes one install. The creation site fixes every
    install, which is why this is here rather than in a runbook.

    On Windows `chmod` cannot express owner-only and is largely a no-op; the
    call is made anyway and its failure ignored, because the deployment
    target is Linux and a development box raising here would be the tail
    wagging the dog.
    """
    os.makedirs(path, exist_ok=True)
    _chmod(path, DIR_MODE)
    return path


def secure_file(path: str) -> str:
    """Tighten an existing file to owner-only. Safe if it does not exist."""
    _chmod(path, FILE_MODE)
    return path


def open_secure(path: str, mode: str = "w", **kwargs):
    """`open()` for a secret-bearing file, created owner-only.

    The mode is applied **before** anything is written: creating 0644 and
    chmod-ing afterwards leaves a window in which the secret is on disk and
    world-readable, which is the whole defect in miniature.
    """
    if "w" not in mode and "a" not in mode and "x" not in mode:
        return open(path, mode, **kwargs)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    if not _IS_WINDOWS:
        flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if "a" in mode
                                            else os.O_TRUNC)
        fd = os.open(path, flags, FILE_MODE)
        # An existing file keeps its old mode through os.open, so tighten it
        # too -- the common case here is a file created before this existed.
        _chmod(path, FILE_MODE)
        return os.fdopen(fd, mode, **kwargs)
    handle = open(path, mode, **kwargs)
    _chmod(path, FILE_MODE)
    return handle


def _chmod(path: str, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        # Windows, or a file owned by someone else. Not fatal: the caller's
        # job is to write the file, and a mode that cannot be set is reported
        # by `scripts/nmas-check-secret-storage`, not by a crash here.
        pass


# Ensure the data directories exist, owner-only
secure_dir(DATA_DIR)
secure_dir(LISTS_DIR)

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

class SettingsUnreadable(RuntimeError):
    """The settings file exists and could not be read.

    **Distinct from absent, and that distinction is the whole point.** This
    function used to catch the parse error and return ``{}`` -- so an
    unreadable file was indistinguishable from a first run, and the next
    write persisted the empty dict. Measured: one truncated read followed by
    a single `set_user_setting()` left a file containing exactly that one
    key. Everything else was gone, including ``settings_schema_version``,
    which made the file read as v0 so the next panel load seeded 107
    defaults over it -- and the Cloudflare Access configuration materialised
    as empty strings.

    Same shape as `inconclusive` against `failed`, one layer under every
    setting in the program.
    """


#: Read failures, for the posture panel. A settings layer running on
#: defaults because it could not read its own file is the wrong-thing-
#: looking-right state, and `device_manager.log` is not read until something
#: else has already gone wrong.
_read_failure: dict = {}


def settings_read_health() -> dict:
    """``{}`` when the file reads cleanly, else what failed and when."""
    return dict(_read_failure)


def _preserve_corrupt(reason: str) -> str:
    """Copy the damaged file aside before anything can overwrite it.

    Owner-only: it is a settings file, and settings files hold secrets --
    true of this one in general even when the particular values are already
    lost.
    """
    import shutil
    import time

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    target = f"{USER_SETTINGS_FILE}.corrupt-{stamp}"
    try:
        if not os.path.exists(target):
            with open(USER_SETTINGS_FILE, "rb") as src:
                data = src.read()
            with open_secure(target, "wb") as dst:
                dst.write(data)
        log.error("settings: %s — preserved the damaged file as %s",
                  reason, os.path.basename(target))
    except OSError as exc:
        log.error("settings: %s — and it could not be preserved: %s",
                  reason, exc)
        return ""
    return target


def load_user_settings(strict: bool = False) -> dict:
    """Load user settings.

    A **missing** file is a first run and returns ``{}``. A file that exists
    and cannot be parsed raises :class:`SettingsUnreadable` -- because the
    caller that matters is the one about to write, and writing defaults over
    an unreadable file is what destroyed it.

    *strict* is accepted for callers that want the raise regardless; the
    raise is now the default behaviour for a parse failure either way.
    """
    global _read_failure

    if not os.path.exists(USER_SETTINGS_FILE):
        _read_failure = {}
        return {}
    try:
        with open(USER_SETTINGS_FILE, "r") as f:
            data = json.load(f)
        _read_failure = {}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        import time

        reason = f"{type(exc).__name__}: {exc}"
        preserved = _preserve_corrupt(reason)
        _read_failure = {
            "unreadable": True,
            "reason": reason,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "preserved_as": os.path.basename(preserved) if preserved else "",
            "effect": ("settings are being read from defaults; writes are "
                       "refused until the file is repaired or removed"),
        }
        raise SettingsUnreadable(reason) from exc


import threading as _threading
from contextlib import contextmanager as _contextmanager

_settings_rlock = _threading.RLock()
_settings_lock_depth = 0


@_contextmanager
def settings_lock():
    """Hold this across a READ-MODIFY-WRITE of ``user_settings.json``.

    Measured 2026-09-25 (register C20): two threads each calling
    `set_user_setting()` 150 times left the file UNREADABLE in both runs
    (`JSONDecodeError: Extra data`), and 141 writes failed. Two defects:
    every writer used the same temp name, so one truncated the temp file
    while the other was renaming it into place and two documents landed in
    one file; and nothing serialised the read-modify-write, so a writer that
    read before another's write put back its stale copy. The unreadable-file
    guard then refused every write -- nothing was erased, and nothing could
    be saved until the `.corrupt` copy was restored by hand.

    In-process, an RLock, re-entrant so `write_settings()` may call helpers
    that also take it. Across processes (a CLI such as `nmas-retire` writes
    settings while the app runs), an exclusive `flock` on
    ``user_settings.json.lock``, taken only at the outermost level: a second
    `flock` from the same process on a new descriptor would block on itself.
    `fcntl` does not exist on Windows (the development box); there the lock
    is in-process only.
    """
    global _settings_lock_depth
    with _settings_rlock:
        outermost = _settings_lock_depth == 0
        _settings_lock_depth += 1
        fd = None
        try:
            if outermost:
                fd = _acquire_settings_file_lock()
            yield
        finally:
            _settings_lock_depth -= 1
            if fd is not None:
                _release_settings_file_lock(fd)


def _acquire_settings_file_lock():
    try:
        import fcntl
    except ImportError:
        return None
    path = f"{USER_SETTINGS_FILE}.lock"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _release_settings_file_lock(fd) -> None:
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def save_user_settings(settings: dict) -> bool:
    """Save user settings to JSON file, owner-only.

    It holds every integration secret `secrets_store` covers. Encrypted at
    rest, but the key sits beside it in the same directory -- so the file
    mode is not redundant with the encryption, it is what stops the two being
    readable together.

    A caller that READ the settings to build *settings* must hold
    :func:`settings_lock` across the read and this call, or a concurrent
    writer's change is lost.
    """
    # ATOMIC. This used to open the real path with "w", which truncates in
    # place: a reader arriving mid-write got a partial document, and
    # `load_user_settings()` turned that into `{}`. Two settings requests
    # 10ms apart is enough. `credentials._save()` already had this shape;
    # this one did not, and the two defects together erased the file.
    #
    # A temp file PER WRITE (C20). A fixed `<file>.tmp` shared by every
    # writer let two of them write into one inode and install the result.
    # `mkstemp` creates it 0600, like `open_secure`, and in the same
    # directory so `os.replace` stays a rename. The name matches the
    # checker's `user_settings.json.*` secret pattern, so a crash leftover
    # is classified rather than unknown.
    import tempfile

    directory = os.path.dirname(USER_SETTINGS_FILE) or "."
    tmp = None
    try:
        with settings_lock():
            fd, tmp = tempfile.mkstemp(
                prefix=os.path.basename(USER_SETTINGS_FILE) + ".tmp-", dir=directory)
            with os.fdopen(fd, "w") as f:
                json.dump(settings, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, USER_SETTINGS_FILE)
        return True
    except OSError:
        log.error("settings: could not write %s", USER_SETTINGS_FILE)
        try:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def set_user_setting(key: str, value) -> bool:
    """Set a specific user setting.

    **Refuses while the file is unreadable.** `load_user_settings()` raises
    rather than returning `{}`, and that raise propagates here on purpose: a
    write built on defaults is exactly what erased every other key.
    """
    with settings_lock():
        settings = load_user_settings()
        settings[key] = value
        return save_user_settings(settings)


def get_user_setting(key: str, default=None):
    """Read one setting, surviving an unreadable file.

    **A read on defaults is survivable; a write on defaults destroyed the
    file.** So this catches what `set_user_setting()` deliberately does not,
    and the failure is recorded in `settings_read_health()` for the posture
    panel rather than only logged.
    """
    try:
        settings = load_user_settings()
    except SettingsUnreadable:
        return default
    return settings.get(key, default)

# Application settings
PING_INTERVAL = 5
FAST_CLI = True


# ---------------------------------------------------------------------------
# Portability
# ---------------------------------------------------------------------------
# Development is on Windows 11; the deployment target is headless Ubuntu. These
# resolve in the order: environment variable → user setting → OS-appropriate
# default, so neither platform needs a code change.
#
# Settings are read with get_user_setting rather than modules.settings_schema:
# settings_schema imports this module, so importing it here would be circular.

def _env_or_setting(env_key: str, setting_key: str, default):
    """Resolve a setting: environment wins, then user settings, then *default*."""
    raw = os.environ.get(env_key)
    if raw not in (None, ""):
        if isinstance(default, bool):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(default, int):
            try:
                return int(raw)
            except ValueError:
                pass
            return default
        return raw
    value = get_user_setting(setting_key, None)
    return default if value is None else value


IS_WINDOWS = os.name == "nt"

# Flask web server settings
FLASK_HOST  = _env_or_setting("NMAS_HOST", "flask_host", "0.0.0.0")
FLASK_PORT  = _env_or_setting("NMAS_PORT", "flask_port", 5000)
FLASK_DEBUG = False

# Open a browser at startup. Historically unconditional, which is wrong for a
# headless systemd unit; NMAS_HEADLESS=1 forces it off.
_HEADLESS = os.environ.get("NMAS_HEADLESS", "").strip().lower() in ("1", "true", "yes", "on")
AUTO_OPEN_BROWSER = False if _HEADLESS else bool(
    _env_or_setting("NMAS_AUTO_OPEN_BROWSER", "auto_open_browser", True)
)

# File transfer settings
# The historical default was the Windows path "C:/TFTP-Root". Combined with the
# import-time makedirs below, that created a literal directory named "C:" in the
# project root on Linux.
_DEFAULT_TFTP_ROOT = "C:/TFTP-Root" if IS_WINDOWS else "/srv/tftp"
TFTP_ROOT = _env_or_setting("NMAS_TFTP_ROOT", "tftp_root", _DEFAULT_TFTP_ROOT)

# TFTP server IP — no default address: a hardcoded one is wrong on every network
# but the one it came from. Set it in Settings.
TFTP_SERVER_IP = get_user_setting("tftp_server_ip", "")


def ensure_tftp_root() -> str:
    """Create the TFTP root on first use and return it.

    Deliberately not done at import time: importing a config module should not
    create directories, least of all from a path belonging to another OS.
    """
    try:
        os.makedirs(TFTP_ROOT, exist_ok=True)
    except OSError as exc:
        import logging
        logging.getLogger(__name__).warning(
            "config: could not create TFTP root '%s': %s", TFTP_ROOT, exc)
    return TFTP_ROOT

# File transfer method: 'tftp' or 'scp'
# SCP is more reliable and secure but requires SCP to be enabled on the device
# NOTE: SCP requires 'ip scp server enable' on Cisco devices
FILE_TRANSFER_METHOD = "tftp"  # Options: 'tftp', 'scp'

# Connection timeouts
SSH_TIMEOUT = 60  # Seconds for SSH command execution
SSH_PORT = 22  # Default SSH port
