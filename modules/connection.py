"""connection.py

SSH connection management via Netmiko for the Network Device Manager.

Provides three connection patterns:
  - `with_temp_connection`: open a connection, run a callable, then close.
  - `get_persistent_connection` / `close_persistent_connection`: maintain a
    per-IP connection pool for repeated operations (status checks, etc.).
  - `ping_worker`: background daemon thread that pings all devices on a
    configurable interval and updates a shared status cache.

Device credentials are decrypted on the fly using the Fernet key managed by
modules.device; they are never stored in the connection pool in plaintext
beyond the lifetime of each ConnectHandler object.
"""

from netmiko import ConnectHandler
import threading
import logging
import ipaddress
import time
import os
from modules.device import decrypt_field, load_saved_devices
from modules.config import DEVICES_FILE, FAST_CLI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection parameters — ONE construction, every caller
# ---------------------------------------------------------------------------


def connection_params(dev: dict, *, password: str, secret: str = None) -> dict:
    """Build the ConnectHandler kwargs. The only place they are assembled.

    Five call sites used to build these independently, all of them agreeing by
    coincidence rather than by construction. That is survivable until one
    transport setting is needed — legacy KEX or host-key algorithms for older
    IOS against a modern client, a timeout, a device-type quirk — at which
    point it is added where the failure was noticed and the other four are
    silently left behind.

    That asymmetry is specifically dangerous on the rotation path. If the
    verify negotiates differently from the session that just pushed the new
    credential, it fails for a **transport** reason, the classifier reads a
    connection failure as a device verdict, and a rotation that actually
    succeeded gets reverted. A fake device cannot catch it either: it models
    the credential exchange, not the negotiation.

    **The password is always passed explicitly.** Callers holding an inventory
    row decrypt first; the rotation holds a plaintext value that has never been
    stored and passes it straight through. Deciding internally whether to
    decrypt is what produced the r2 defect — a function that guesses which of
    those two it was handed will eventually guess wrong.
    """
    return {
        "device_type": dev["device_type"],
        "ip": dev["ip"],
        "username": dev["username"],
        "password": password,
        # An EMPTY secret means "none stored", and falls back to the login
        # password, exactly as None always did (register B14, P.3 step 11).
        # Every device here stored a copy of its password as its "secret", used
        # for nothing, since no device has an enable secret and Netmiko sends
        # one only when asked. Emptying those copies must not turn an empty
        # string into an enable password somebody might be asked for.
        "secret": secret or password,
        "port": 22,
        "fast_cli": FAST_CLI,
    }


def stored_connection_params(dev: dict) -> dict:
    """:func:`connection_params` for a device row, decrypting as it goes."""
    return connection_params(
        dev,
        password=decrypt_field(dev["password"]),
        secret=decrypt_field(dev["secret"]),
    )

# ---------------------------------------------------------------------------
# Per-device send locks
# ---------------------------------------------------------------------------
# Each device IP gets one RLock that serialises all SSH sends/receives.
# Using RLock so callers that explicitly hold the lock for a multi-step
# sequence don't deadlock when LockedConnection re-acquires it per-method.

_send_locks: dict = {}
_send_locks_mu = threading.Lock()


def get_device_send_lock(ip: str) -> threading.RLock:
    """Return (creating if needed) the per-device send-serialisation RLock."""
    with _send_locks_mu:
        if ip not in _send_locks:
            _send_locks[ip] = threading.RLock()
        return _send_locks[ip]


class LockedConnection:
    """Thread-safe proxy for a Netmiko ConnectHandler.

    Every method call acquires the per-device RLock before delegating to the
    underlying connection, preventing two threads from interleaving commands
    on the same SSH session.

    Callers that need to execute a *sequence* of commands atomically should
    hold the same lock explicitly::

        with get_device_send_lock(ip):
            conn.send_command_timing(cmd1)
            conn.send_command_timing(cmd2)

    Because the lock is an RLock the nested acquire inside each method does
    not deadlock.
    """

    __slots__ = ('_conn', '_lock')

    def __init__(self, conn: ConnectHandler, lock: threading.RLock) -> None:
        object.__setattr__(self, '_conn', conn)
        object.__setattr__(self, '_lock', lock)

    def __getattr__(self, name: str):
        conn = object.__getattribute__(self, '_conn')
        lock = object.__getattribute__(self, '_lock')
        attr = getattr(conn, name)
        if callable(attr):
            def _locked(*args, **kwargs):
                with lock:
                    return attr(*args, **kwargs)
            return _locked
        return attr

    def __setattr__(self, name: str, value) -> None:
        conn = object.__getattribute__(self, '_conn')
        setattr(conn, name, value)

# This module provides two connection styles:

#   `with_temp_connection`: create a short-lived connection, run a
#   provided callable, then disconnect.

#   `get_persistent_connection` / `close_persistent_connection`: keep
#   a lightweight persistent connection per-IP for status checks and
#   infrequent operations


def verify_device_connection(
    ip: str, username: str, password: str, secret: str, device_type: str = "cisco_ios"
) -> str:
    """
    Attempts to connect to a device using Netmiko and returns the hostname prompt.
    Raises exception if connection fails.
    """
    conn = ConnectHandler(**connection_params(
        {"device_type": device_type, "ip": ip, "username": username},
        password=password, secret=secret))
    conn.enable()
    prompt = conn.find_prompt()
    conn.disconnect()
    # Extract hostname from prompt (e.g., 'R1#' -> 'R1')
    hostname = prompt.rstrip("#>").strip()
    return hostname


def is_device_online(ip: str) -> bool:
    """Returns True if device at IP responds to ping or accepts TCP on port 22.

    ping3 needs a raw ICMP socket, which requires root/CAP_NET_RAW on Linux.
    When that's unavailable (e.g. unprivileged systemd service) every ping
    raises PermissionError, so fall back to a plain TCP connect to the SSH
    port, which is what this app actually needs reachable anyway.
    """
    from ping3 import ping

    try:
        response = ping(ip, timeout=2, unit="ms")
        if response and response > 0:
            return True
    except Exception:
        logger.debug("Ping error for %s", ip, exc_info=True)

    import socket

    try:
        with socket.create_connection((ip, 22), timeout=2):
            return True
    except Exception:
        logger.debug("TCP:22 check failed for %s", ip, exc_info=True)
        return False


def ping_worker(
    device_status_cache: dict, filename=None, interval: int = 5
) -> None:
    #Background thread: pings devices periodically and updates status cache.
    #filename can be a string path or a callable that returns the current path.

    def worker():
        last_mtime = None
        last_fn = None
        devices = []
        while True:
            try:
                # Support callable for dynamic device list selection
                if callable(filename):
                    fn = filename()
                else:
                    fn = filename or DEVICES_FILE

                # Reset mtime tracking if filename changed
                if fn != last_fn:
                    last_fn = fn
                    last_mtime = None

                if os.path.exists(fn):
                    mtime = os.path.getmtime(fn)
                    if mtime != last_mtime:
                        last_mtime = mtime
                        devices = load_saved_devices(fn)
                        safe = [
                            {"hostname": d.get("hostname"), "ip": d.get("ip")}
                            for d in devices
                        ]
                        logger.debug("ping_worker loaded devices (masked): %s", safe)
                else:
                    if devices:
                        devices = []
                        logger.debug("Devices file removed: %s", fn)

                # Prepare list of valid IPs to check
                ips = []
                for d in devices:
                    ip = d.get("ip")
                    if not ip:
                        continue
                    try:
                        addr = ipaddress.ip_address(ip)
                        if addr.is_unspecified or addr.is_multicast:
                            logger.debug("Skipping unspecified/multicast IP: %s", ip)
                            continue
                    except ValueError:
                        logger.debug("Skipping invalid IP: %s", ip)
                        continue
                    ips.append(ip)

                # Ping devices in parallel to reduce overall cycle time
                if ips:
                    from concurrent.futures import ThreadPoolExecutor, as_completed

                    max_workers = min(20, len(ips))
                    with ThreadPoolExecutor(max_workers=max_workers) as ex:
                        future_to_ip = {ex.submit(is_device_online, ip): ip for ip in ips}
                        for fut in as_completed(future_to_ip):
                            ip = future_to_ip[fut]
                            try:
                                status = bool(fut.result())
                            except Exception:
                                status = False
                            prev = device_status_cache.get(ip)
                            device_status_cache[ip] = status
                            if prev is None or prev != status:
                                logger.info("ping_worker: %s online=%s", ip, status)
            except Exception:
                logger.exception("Ping worker error")
            time.sleep(interval)

    t = threading.Thread(target=worker, daemon=True)
    t.start()


def get_persistent_connection(
    dev: dict, connections: dict, lock: threading.Lock
) -> 'LockedConnection':
    """Return a thread-safe LockedConnection for the device.

    The pool lock (`lock`) guards the connections dict.  The per-device
    send lock is acquired while checking liveness and during reconnect so
    that a health-check never races with an in-flight send_command from
    another thread.
    """
    ip        = dev["ip"]
    send_lock = get_device_send_lock(ip)
    with lock:
        with send_lock:
            conn = connections.get(ip)
            # Unwrap LockedConnection to get the raw ConnectHandler for is_alive
            raw = object.__getattribute__(conn, '_conn') if isinstance(conn, LockedConnection) else conn
            if not raw or not getattr(raw, "is_alive", lambda: True)():
                try:
                    if raw:
                        raw.disconnect()
                except Exception:
                    pass
                raw = ConnectHandler(**stored_connection_params(dev))
                raw.enable()
                connections[ip] = LockedConnection(raw, send_lock)
            elif not isinstance(conn, LockedConnection):
                connections[ip] = LockedConnection(raw, send_lock)
        return connections[ip]


def close_persistent_connection(
    ip: str, connections: dict, lock: threading.Lock
) -> None:
    #Closes and removes persistent Netmiko connection for given IP.
    with lock:
        conn = connections.pop(ip, None)
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


def with_temp_connection(dev: dict, func) -> any:
    #Creates a temporary Netmiko connection to run func(conn), then disconnects.
    try:
        logger.debug(
            "Attempting connection to %s as %s", dev.get("ip"), dev.get("username")
        )
        conn = ConnectHandler(**stored_connection_params(dev))
        conn.enable()
        logger.debug("Connected to %s", dev.get("ip"))
        try:
            return func(conn)
        finally:
            try:
                conn.disconnect()
                logger.debug("Disconnected from %s", dev.get("ip"))
            except Exception as e:
                logger.debug("Disconnect error for %s: %s", dev.get("ip"), e)
    except Exception:
        logger.exception("Connection to %s failed", dev.get("ip"))
        raise
