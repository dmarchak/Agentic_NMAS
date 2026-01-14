from netmiko import ConnectHandler
import threading
import logging
import ipaddress
import time
import os
from modules.device import decrypt_field, load_saved_devices
from modules.config import DEVICES_FILE, FAST_CLI

logger = logging.getLogger(__name__)

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
    conn = ConnectHandler(
        device_type=device_type,
        ip=ip,
        username=username,
        password=password,
        secret=secret,
        port=22,
        fast_cli=FAST_CLI,
    )
    conn.enable()
    prompt = conn.find_prompt()
    conn.disconnect()
    # Extract hostname from prompt (e.g., 'R1#' -> 'R1')
    hostname = prompt.rstrip("#>").strip()
    return hostname


def is_device_online(ip: str) -> bool:
    """Returns True if device at IP responds to ping."""
    from ping3 import ping

    try:
        response = ping(ip, timeout=2, unit="ms")
        return bool(response and response > 0)
    except Exception:
        logger.debug("Ping error for %s", ip, exc_info=True)
        return False


def ping_worker(
    device_status_cache: dict, filename: str = None, interval: int = 5
) -> None:
    #Background thread: pings devices periodically and updates status cache.

    def worker():
        last_mtime = None
        devices = []
        while True:
            try:
                fn = filename or DEVICES_FILE
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
) -> ConnectHandler:
    #Returns a persistent Netmiko connection for status checks.
    ip = dev["ip"]
    with lock:
        conn = connections.get(ip)
        if not conn or not getattr(conn, "is_alive", lambda: True)():
            try:
                if conn:
                    conn.disconnect()
            except Exception:
                pass
            conn = ConnectHandler(
                device_type=dev["device_type"],
                ip=dev["ip"],
                username=dev["username"],
                password=decrypt_field(dev["password"]),
                secret=decrypt_field(dev["secret"]),
                port=22,
                fast_cli=FAST_CLI,
            )
            conn.enable()
            connections[ip] = conn
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
        conn = ConnectHandler(
            device_type=dev["device_type"],
            ip=dev["ip"],
            username=dev["username"],
            password=decrypt_field(dev["password"]),
            secret=decrypt_field(dev["secret"]),
            port=22,
            fast_cli=FAST_CLI,
        )
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
