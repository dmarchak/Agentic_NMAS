"""collector_config.py

Monitoring collector configuration (SNMP, NetFlow, syslog) per device list.

Stores and auto-detects the local server IP that network devices should use as
the trap/flow/syslog destination — specifically the interface that shares a
subnet with the list's devices, not the loopback.  Also persists per-list
settings for SNMP community, trap port, NetFlow port, and syslog port.
Configuration is saved at data/lists/{slug}/collector_config.json.
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
    """Atomically, and created 0600: this file holds both SNMP communities
    (register C55). It was `open(path, "w")`: truncate in place (the shape
    that erased user_settings.json) at the process umask."""
    from modules.config import open_secure

    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open_secure(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


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


class NoCommunity(LookupError):
    """No SNMP community is held for this device. Never answered with a
    default: a default that equals a live secret is how the fleet's community
    came to be configured by source code (C139, C141)."""


#: What the community's owner is, for a reader of the monitoring config.
COMMUNITY_OWNER = ("each device's own secret in the credential store "
                   "(`<list>:<host>:snmp_community_ro`, the one intent renders "
                   "from); set by the rotation, never here")


def device_community(list_name: str, hostname: str) -> str:
    """The SNMP community *hostname* holds, from its OWN secret: the value the
    device's committed intent renders (C139, the operator's decision). ONE
    owner per fact, and per DEVICE, so the state between two devices'
    rotations is not a special case. No fallback, ever."""
    from modules.credentials import get_template_secret, template_secret_key

    value = get_template_secret(template_secret_key(list_name, hostname, "snmp_community_ro"))
    if not value:
        raise NoCommunity(
            f"no SNMP community is held for {hostname} in list {list_name}: its secret "
            "snmp_community_ro is not in the credential store (extract its intent, or "
            "rotate it). Nothing was polled; no default is ever used.")
    return value


def community_for_address(list_name: str, ip: str) -> tuple:
    """``(hostname, community)`` for the inventory device at *ip*. An address
    no device in the list holds refuses by name rather than polling blind."""
    from modules.device import get_device_lists, load_saved_devices
    from modules.config import LISTS_DIR

    slug = next((l["filename"] for l in get_device_lists() if l["name"] == list_name), None)
    rows = load_saved_devices(os.path.join(LISTS_DIR, slug, "devices.csv")) if slug else []
    host = next((r.get("hostname") for r in rows if r.get("ip") == ip), None)
    if not host:
        raise NoCommunity(f"no device at {ip} in list {list_name}, so no community is "
                          "known for it. Nothing was polled.")
    return host, device_community(list_name, host)


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


def public_config() -> dict:
    """The collector config as it may leave this host: the communities are
    WRITE-ONLY (register C55, as B11 decided for every secret). Whether each
    is set is carried; its value never is. `get_full_config()` below is for
    the collectors themselves."""
    full = get_full_config()
    full["snmp_community"] = COMMUNITY_OWNER
    return full


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


def get_or_detect_collector_ip() -> dict:
    """Alias for get_full_config — returns dict with collector_ip and collector_ip_source."""
    return get_full_config()


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
