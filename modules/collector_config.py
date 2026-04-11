"""
collector_config.py — OOB management collector IP for each device list

When configuring SNMP trap destinations, NetFlow export targets, syslog
receivers, etc. on network devices, the device needs the IP address of
THIS server on the OOB management network — not 127.0.0.1 or any other
interface.

This module stores and auto-detects the correct local IP by finding the
server interface that shares a subnet with the list's devices.
"""

import ipaddress
import json
import logging
import os
import socket

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _config_path() -> str:
    from modules.config import get_current_list_data_dir
    return os.path.join(get_current_list_data_dir(), "collector_config.json")


def _load() -> dict:
    try:
        with open(_config_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save(data: dict) -> None:
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_collector_ip() -> str | None:
    """Return the stored collector IP for the current list."""
    return _load().get("collector_ip")


def set_collector_ip(ip: str) -> None:
    """Persist the collector IP for the current list."""
    data = _load()
    data["collector_ip"] = ip
    _save(data)
    log.info("collector_config: collector IP set to %s", ip)


def get_snmp_community(direction: str = "ro") -> str:
    """Return stored SNMP community string.  direction: 'ro' | 'rw'"""
    key = "snmp_community_ro" if direction == "ro" else "snmp_community_rw"
    return _load().get(key, "public" if direction == "ro" else "private")


def set_snmp_community(community: str, direction: str = "ro") -> None:
    key = "snmp_community_ro" if direction == "ro" else "snmp_community_rw"
    data = _load()
    data[key] = community
    _save(data)


def get_netflow_port() -> int:
    return int(_load().get("netflow_port", 9996))


def set_netflow_port(port: int) -> None:
    data = _load()
    data["netflow_port"] = port
    _save(data)


def get_snmp_trap_port() -> int:
    return int(_load().get("snmp_trap_port", 1162))


def set_snmp_trap_port(port: int) -> None:
    data = _load()
    data["snmp_trap_port"] = port
    _save(data)


def get_full_config() -> dict:
    """Return all collector settings for the current list."""
    data = _load()
    detected = None
    if not data.get("collector_ip"):
        detected = detect_collector_ip(_get_device_ips())
    return {
        "collector_ip":      data.get("collector_ip") or detected,
        "collector_ip_source": "stored" if data.get("collector_ip") else (
            "detected" if detected else "none"
        ),
        "snmp_community_ro": data.get("snmp_community_ro", "public"),
        "snmp_community_rw": data.get("snmp_community_rw", "private"),
        "snmp_trap_port":    data.get("snmp_trap_port", 1162),
        "netflow_port":      data.get("netflow_port", 9996),
    }


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------

def detect_collector_ip(device_ips: list) -> str | None:
    """
    Find the local interface IP that shares a subnet with any device IP.
    Uses psutil to enumerate all interfaces.  Falls back to socket approach
    if psutil is not available.
    """
    if not device_ips:
        return None

    # psutil approach (most reliable)
    try:
        import psutil
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family != socket.AF_INET:
                    continue
                if not addr.netmask or addr.address.startswith("127."):
                    continue
                try:
                    net = ipaddress.IPv4Network(
                        f"{addr.address}/{addr.netmask}", strict=False
                    )
                    for dev_ip in device_ips:
                        dev_ip = dev_ip.strip()
                        if not dev_ip:
                            continue
                        if ipaddress.IPv4Address(dev_ip) in net:
                            log.info(
                                "collector_config: auto-detected %s on %s (matches device %s in %s)",
                                addr.address, iface, dev_ip, net,
                            )
                            return addr.address
                except Exception:
                    continue
    except ImportError:
        pass
    except Exception as exc:
        log.debug("collector_config: psutil detection error: %s", exc)

    # Socket approach — connect to first device and read local end
    for dev_ip in device_ips:
        try:
            dev_ip = dev_ip.strip()
            if not dev_ip:
                continue
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0)
            s.connect((dev_ip, 1))   # doesn't send anything
            local_ip = s.getsockname()[0]
            s.close()
            if local_ip and not local_ip.startswith("127."):
                log.info("collector_config: socket-detected collector IP %s for device %s",
                         local_ip, dev_ip)
                return local_ip
        except Exception:
            continue

    return None


def detect_and_store() -> str | None:
    """Detect the collector IP and store it.  Returns the IP or None."""
    ips = _get_device_ips()
    detected = detect_collector_ip(ips)
    if detected:
        set_collector_ip(detected)
    return detected


def _get_device_ips() -> list:
    """Load device IPs from the current list's devices CSV."""
    import csv
    try:
        from modules.config import get_current_list_data_dir, DATA_DIR
        list_dir = get_current_list_data_dir()
        for path in [
            os.path.join(list_dir, "devices.csv"),
            os.path.join(DATA_DIR, "Devices.csv"),
        ]:
            if os.path.exists(path):
                ips = []
                with open(path, encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        ip = (row.get("ip") or row.get("IP") or
                              row.get("host") or "").strip()
                        if ip:
                            ips.append(ip)
                return ips
    except Exception as exc:
        log.debug("collector_config: device IP load error: %s", exc)
    return []


def list_local_interfaces() -> list:
    """Return all local IPv4 interfaces as [{"name": ..., "ip": ..., "netmask": ...}]."""
    result = []
    try:
        import psutil
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    result.append({
                        "name":    iface,
                        "ip":      addr.address,
                        "netmask": addr.netmask or "",
                    })
    except ImportError:
        # Fallback: hostname resolution only
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip and not ip.startswith("127."):
                result.append({"name": "default", "ip": ip, "netmask": ""})
        except Exception:
            pass
    return result
