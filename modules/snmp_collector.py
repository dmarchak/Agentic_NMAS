"""
snmp_collector.py — SNMP polling and trap receiver

Provides:
  - snmp_get(host, oids, community, version)  — fetch one or more OIDs
  - snmp_walk(host, oid, community, version)  — walk a subtree
  - get_device_summary(host, community)       — uptime, hostname, interfaces
  - start_trap_receiver(port)                 — daemon UDP trap listener
  - get_recent_traps(n)                       — return last N traps

SNMP version support: v1, v2c  (v3 via USM is outside scope here)
Trap receiver listens on UDP port 1162 by default (no root required).
Configure devices to send traps to: <collector_ip>:<trap_port>
"""

import json
import logging
import os
import socket
import struct
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Common OID reference
# ---------------------------------------------------------------------------
WELL_KNOWN_OIDS = {
    "sysDescr":      "1.3.6.1.2.1.1.1.0",
    "sysUpTime":     "1.3.6.1.2.1.1.3.0",
    "sysContact":    "1.3.6.1.2.1.1.4.0",
    "sysName":       "1.3.6.1.2.1.1.5.0",
    "sysLocation":   "1.3.6.1.2.1.1.6.0",
    "ifNumber":      "1.3.6.1.2.1.2.1.0",
    # Interface table subtrees (walk these)
    "ifDescr":       "1.3.6.1.2.1.2.2.1.2",
    "ifOperStatus":  "1.3.6.1.2.1.2.2.1.8",   # 1=up, 2=down
    "ifAdminStatus": "1.3.6.1.2.1.2.2.1.7",
    "ifInOctets":    "1.3.6.1.2.1.2.2.1.10",
    "ifOutOctets":   "1.3.6.1.2.1.2.2.1.16",
    "ifInErrors":    "1.3.6.1.2.1.2.2.1.14",
    "ifOutErrors":   "1.3.6.1.2.1.2.2.1.20",
    "ifSpeed":       "1.3.6.1.2.1.2.2.1.5",
    # Cisco-specific
    "cpmCPUTotal5min":     "1.3.6.1.4.1.9.9.109.1.1.1.1.8.1",
    "ciscoMemFreePool":    "1.3.6.1.4.1.9.2.1.8.0",
    "ciscoMemUsedPool":    "1.3.6.1.4.1.9.2.1.7.0",
}

# ---------------------------------------------------------------------------
# Trap ring buffer
# ---------------------------------------------------------------------------
_MAX_TRAPS = 200
_traps: list = []
_trap_lock = threading.Lock()

_trap_thread: Optional[threading.Thread] = None
_trap_stop   = threading.Event()

def _trap_file() -> str:
    try:
        from modules.config import get_current_list_data_dir
        return os.path.join(get_current_list_data_dir(), "snmp_traps.json")
    except Exception:
        return os.path.join(os.path.dirname(__file__), "..", "data", "snmp_traps.json")


def _load_traps_from_disk() -> None:
    try:
        with open(_trap_file(), encoding="utf-8") as fh:
            loaded = json.load(fh)
        with _trap_lock:
            _traps.extend(loaded[-_MAX_TRAPS:])
    except Exception:
        pass


def _save_trap(trap: dict) -> None:
    with _trap_lock:
        _traps.append(trap)
        if len(_traps) > _MAX_TRAPS:
            _traps.pop(0)
        data = list(_traps)
    try:
        path = _trap_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def get_recent_traps(n: int = 50) -> list:
    with _trap_lock:
        return list(reversed(_traps))[:n]


# ---------------------------------------------------------------------------
# SNMP polling (requires pysnmp or pysnmp-lextudio)
# ---------------------------------------------------------------------------

def _check_pysnmp():
    try:
        import pysnmp  # noqa: F401
        return True
    except ImportError:
        return False


def snmp_get(host: str, oids: list, community: str = "public",
             version: int = 2, port: int = 161, timeout: int = 5) -> list:
    """
    Fetch one or more OIDs from a device.
    Returns list of (oid_str, value_str) tuples.
    Raises RuntimeError on SNMP error or if pysnmp is not installed.
    """
    if not _check_pysnmp():
        raise RuntimeError("pysnmp is not installed. Run: pip install pysnmp")

    # Resolve friendly names to numeric OIDs
    resolved = [WELL_KNOWN_OIDS.get(o, o) for o in oids]

    import asyncio

    async def _get():
        from pysnmp.hlapi.asyncio import (
            getCmd, SnmpEngine, CommunityData, UdpTransportTarget,
            ContextData, ObjectType, ObjectIdentity,
        )
        mp_model = 1 if version == 2 else 0
        var_binds_arg = [ObjectType(ObjectIdentity(o)) for o in resolved]

        error_indication, error_status, error_index, var_binds = await getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=mp_model),
            UdpTransportTarget((host, port), timeout=timeout, retries=1),
            ContextData(),
            *var_binds_arg,
        )
        if error_indication:
            raise RuntimeError(f"SNMP error: {error_indication}")
        if error_status:
            raise RuntimeError(
                f"SNMP error: {error_status.prettyPrint()} "
                f"at {error_index and var_binds[int(error_index) - 1][0] or '?'}"
            )
        return [(str(vb[0]), _format_snmp_value(vb[1])) for vb in var_binds]

    try:
        # Run the coroutine synchronously from this thread.
        # If an event loop is already running (e.g. gevent/Flask-SocketIO),
        # create a new one in a separate thread to avoid nesting.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(asyncio.run, _get())
                return fut.result(timeout=timeout + 5)
        else:
            return asyncio.run(_get())
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"SNMP get error: {exc}") from exc


def snmp_walk(host: str, oid: str, community: str = "public",
              version: int = 2, port: int = 161, timeout: int = 10,
              max_rows: int = 256) -> list:
    """
    Walk an OID subtree.  Returns list of (oid_str, value_str) tuples.
    """
    if not _check_pysnmp():
        raise RuntimeError("pysnmp is not installed. Run: pip install pysnmp")

    base_oid = WELL_KNOWN_OIDS.get(oid, oid)
    import asyncio

    async def _walk():
        from pysnmp.hlapi.asyncio import (
            walkCmd, SnmpEngine, CommunityData, UdpTransportTarget,
            ContextData, ObjectType, ObjectIdentity,
        )
        mp_model = 1 if version == 2 else 0
        results  = []
        async for error_indication, error_status, error_index, var_binds in walkCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=mp_model),
            UdpTransportTarget((host, port), timeout=timeout, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
        ):
            if error_indication or error_status:
                break
            for vb in var_binds:
                results.append((str(vb[0]), _format_snmp_value(vb[1])))
            if len(results) >= max_rows:
                break
        return results

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(asyncio.run, _walk())
                return fut.result(timeout=timeout + 5)
        else:
            return asyncio.run(_walk())
    except Exception as exc:
        raise RuntimeError(f"SNMP walk error: {exc}") from exc


def _format_snmp_value(val) -> str:
    """Convert a pysnmp value object to a human-readable string."""
    try:
        type_name = type(val).__name__
        if "TimeTicks" in type_name:
            ticks = int(val)
            secs  = ticks // 100
            days, rem = divmod(secs, 86400)
            hrs,  rem = divmod(rem, 3600)
            mins, sec = divmod(rem, 60)
            return f"{days}d {hrs:02}:{mins:02}:{sec:02}"
    except Exception:
        pass
    try:
        return val.prettyPrint()
    except Exception:
        return str(val)


def get_device_summary(host: str, community: str = "public",
                       version: int = 2) -> dict:
    """
    Poll a device for a standard summary: system info + interface table.
    Returns a structured dict suitable for display or storage as a variable.
    """
    result: dict = {"host": host, "polled_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    # System scalars
    sys_oids = ["sysName", "sysDescr", "sysUpTime", "sysLocation", "sysContact"]
    try:
        rows = snmp_get(host, sys_oids, community, version)
        labels = ["name", "description", "uptime", "location", "contact"]
        result["system"] = {lbl: val for (_, val), lbl in zip(rows, labels)}
    except Exception as exc:
        result["system_error"] = str(exc)
        return result

    # Interface table — walk ifDescr, ifOperStatus, ifInOctets, ifOutOctets
    iface_data: dict = {}
    for oid_name in ("ifDescr", "ifOperStatus", "ifInOctets", "ifOutOctets", "ifSpeed"):
        try:
            rows = snmp_walk(host, oid_name, community, version, max_rows=64)
            for oid_str, val in rows:
                idx = oid_str.rsplit(".", 1)[-1]
                iface_data.setdefault(idx, {})["idx"] = idx
                iface_data[idx][oid_name] = val
        except Exception:
            pass

    # Format interface table
    interfaces = []
    for idx, info in sorted(iface_data.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        status = info.get("ifOperStatus", "?")
        status_label = "up" if status == "1" else "down" if status == "2" else status
        interfaces.append({
            "index":      idx,
            "name":       info.get("ifDescr", "?"),
            "status":     status_label,
            "in_octets":  info.get("ifInOctets", "0"),
            "out_octets": info.get("ifOutOctets", "0"),
            "speed_bps":  info.get("ifSpeed", "0"),
        })
    result["interfaces"] = interfaces

    return result


# ---------------------------------------------------------------------------
# SNMP Trap receiver  (pure Python, no root required on port >1024)
# ---------------------------------------------------------------------------

def start_trap_receiver(port: int = 1162) -> None:
    """Start the UDP trap listener daemon thread (idempotent)."""
    global _trap_thread
    if _trap_thread and _trap_thread.is_alive():
        return
    _load_traps_from_disk()
    _trap_stop.clear()
    _trap_thread = threading.Thread(
        target=_trap_loop, args=(port,), daemon=True, name="snmp-trap-receiver"
    )
    _trap_thread.start()
    log.info("snmp_collector: trap receiver started on UDP port %d", port)


def stop_trap_receiver() -> None:
    _trap_stop.set()


def _trap_loop(port: int) -> None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        sock.settimeout(2.0)
        log.info("snmp_collector: listening for traps on 0.0.0.0:%d", port)
    except Exception as exc:
        log.error("snmp_collector: cannot bind UDP %d — %s", port, exc)
        return

    while not _trap_stop.is_set():
        try:
            data, addr = sock.recvfrom(65535)
            trap = _parse_trap(data, addr[0])
            if trap:
                _save_trap(trap)
                log.info("snmp_collector: trap from %s — %s", addr[0], trap.get("enterprise", ""))
        except socket.timeout:
            continue
        except Exception as exc:
            log.debug("snmp_collector: trap recv error: %s", exc)

    sock.close()
    log.info("snmp_collector: trap receiver stopped")


def _parse_trap(data: bytes, src_ip: str) -> Optional[dict]:
    """
    Minimal ASN.1/BER trap parser.
    Returns a dict with: source_ip, timestamp, community, enterprise, varbinds_raw.
    Falls back to raw hex if parsing fails.
    """
    trap: dict = {
        "id":         _short_id(),
        "received_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_ip":  src_ip,
    }
    try:
        # Try pysnmp full decode first
        from pysnmp.carrier.asyncore.dgram import udp
        from pysnmp.entity import engine, config
        # Full decode is complex; use simpler heuristic approach
        raise ImportError("use fallback")
    except Exception:
        pass

    # Heuristic: extract community string and OIDs from raw BER
    try:
        trap["raw_hex"] = data.hex()
        # Community string is typically the second OCTET STRING in SNMPv1/v2c
        pos = 0
        # Skip outer SEQUENCE tag + length
        pos = _ber_skip_tl(data, pos)
        # Version INTEGER
        pos, version_val = _ber_read_int(data, pos)
        trap["version"] = version_val
        # Community OCTET STRING
        pos, community = _ber_read_octet(data, pos)
        trap["community"] = community.decode("ascii", errors="replace")
        trap["summary"] = f"SNMP trap from {src_ip} (v{version_val + 1}, community={trap['community']})"
    except Exception as exc:
        trap["summary"] = f"SNMP trap from {src_ip} (raw, parse error: {exc})"

    return trap


def _short_id() -> str:
    import uuid
    return str(uuid.uuid4())[:8]


def _ber_skip_tl(data: bytes, pos: int) -> int:
    """Skip a BER tag+length, return position of value."""
    pos += 1   # tag
    length = data[pos]; pos += 1
    if length & 0x80:
        n = length & 0x7f
        pos += n
    return pos


def _ber_read_int(data: bytes, pos: int) -> tuple:
    """Read a BER INTEGER, return (new_pos, value)."""
    assert data[pos] == 0x02, f"Expected INTEGER at {pos}, got {data[pos]:02x}"
    pos += 1
    length = data[pos]; pos += 1
    val = int.from_bytes(data[pos:pos + length], "big", signed=True)
    return pos + length, val


def _ber_read_octet(data: bytes, pos: int) -> tuple:
    """Read a BER OCTET STRING, return (new_pos, bytes)."""
    assert data[pos] == 0x04, f"Expected OCTET STRING at {pos}, got {data[pos]:02x}"
    pos += 1
    length = data[pos]; pos += 1
    if length & 0x80:
        n = length & 0x7f
        length = int.from_bytes(data[pos:pos + n], "big")
        pos += n
    val = data[pos:pos + length]
    return pos + length, val
