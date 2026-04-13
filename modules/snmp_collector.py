"""snmp_collector.py

SNMP trap collection and basic polling for network devices.

Provides OID-level GET and WALK (pure-Python BER decoder, no net-snmp dependency),
a `get_device_summary` helper that pulls uptime/hostname/interface status, and a
UDP trap receiver daemon that decodes incoming v1/v2c trap PDUs and stores them in
a per-list ring buffer.  The agent_runner consumes the trap buffer to trigger AI
investigation of actionable events (link-down, BGP state change, etc.).

Listens on UDP port 1162 by default (no root required).
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

# Optional callback invoked (in a daemon thread) immediately after each trap is saved.
# Set via set_trap_callback() — used by agent_runner for real-time alerting.
_trap_callback = None


def set_trap_callback(fn) -> None:
    """Register a function to be called whenever a new trap is received."""
    global _trap_callback
    _trap_callback = fn

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
                log.info("snmp_collector: trap from %s — %s", addr[0], trap.get("trap_type") or trap.get("enterprise", ""))
                cb = _trap_callback
                if cb:
                    threading.Thread(
                        target=cb, args=(trap,), daemon=True,
                        name="trap-cb"
                    ).start()
        except socket.timeout:
            continue
        except Exception as exc:
            log.debug("snmp_collector: trap recv error: %s", exc)

    sock.close()
    log.info("snmp_collector: trap receiver stopped")


def _parse_trap(data: bytes, src_ip: str) -> Optional[dict]:
    """
    BER trap parser — decodes SNMPv1 (RFC 1157) and SNMPv2c (RFC 1905) trap PDUs.
    Returns a rich dict with enterprise OID, generic/specific trap type, and varbinds.
    """
    trap: dict = {
        "id":          _short_id(),
        "received_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_ip":   src_ip,
        "community":   "",
        "version":     2,
        "trap_type":   "",
        "trap_oid":    "",
        "enterprise":  "",
        "varbinds":    [],
        "summary":     "",
    }
    try:
        pos = 0
        # Outer SEQUENCE
        pos = _ber_skip_tl(data, pos)
        # Version INTEGER (0=v1, 1=v2c)
        pos, version_val = _ber_read_int(data, pos)
        trap["version"] = version_val + 1
        # Community OCTET STRING
        pos, community_b = _ber_read_octet(data, pos)
        trap["community"] = community_b.decode("ascii", errors="replace")

        pdu_tag = data[pos]

        if pdu_tag == 0xA4:
            # SNMPv1 Trap-PDU
            pos = _ber_skip_tl(data, pos)
            # Enterprise OID
            pos, enterprise = _ber_read_oid(data, pos)
            trap["enterprise"] = enterprise
            # Agent address (4-byte OCTET STRING or IpAddress)
            pos, _ = _ber_read_raw(data, pos)
            # Generic trap type
            pos, generic = _ber_read_int(data, pos)
            # Specific trap type
            pos, specific = _ber_read_int(data, pos)
            # Time stamp (TimeTicks)
            pos, _ = _ber_read_raw(data, pos)
            # Varbinds
            trap["varbinds"] = _ber_read_varbinds(data, pos)
            trap["trap_type"] = _generic_trap_name(generic, specific, enterprise)
            trap["varbind_labels"] = [s for s in (
                _humanize_varbind(n, v) for n, v in trap["varbinds"]
            ) if s]
            trap["summary"]   = _build_summary_v1(trap)

        elif pdu_tag == 0xA7:
            # SNMPv2c/v3 SNMPv2-Trap-PDU
            pos = _ber_skip_tl(data, pos)
            pos, _ = _ber_read_int(data, pos)   # request-id
            pos, _ = _ber_read_int(data, pos)   # error-status
            pos, _ = _ber_read_int(data, pos)   # error-index
            trap["varbinds"] = _ber_read_varbinds(data, pos)
            # snmpTrapOID.0 is the second varbind
            trap_oid = ""
            for name, val in trap["varbinds"]:
                if "1.3.6.1.6.3.1.1.4.1" in name:
                    trap_oid = val
                    break
            trap["trap_oid"]  = trap_oid
            trap["trap_type"] = _lookup_trap_oid(trap_oid)
            trap["varbind_labels"] = [s for s in (
                _humanize_varbind(n, v) for n, v in trap["varbinds"]
            ) if s]
            trap["summary"]   = _build_summary_v2(trap)

        else:
            trap["summary"] = f"SNMP trap from {src_ip} (unknown PDU tag 0x{pdu_tag:02x})"

    except Exception as exc:
        trap["summary"] = f"SNMP trap from {src_ip} (parse error: {exc})"

    return trap


# ---------------------------------------------------------------------------
# OID lookups and summary builders
# ---------------------------------------------------------------------------

# Generic v1 trap type names (RFC 1157)
_GENERIC_TRAP = {
    0: "coldStart",
    1: "warmStart",
    2: "linkDown",
    3: "linkUp",
    4: "authenticationFailure",
    5: "egpNeighborLoss",
    6: "enterpriseSpecific",
}

# Well-known trap OIDs (SNMPv2c snmpTrapOID values)
_TRAP_OID_NAMES = {
    "1.3.6.1.6.3.1.1.5.1": "coldStart",
    "1.3.6.1.6.3.1.1.5.2": "warmStart",
    "1.3.6.1.6.3.1.1.5.3": "linkDown",
    "1.3.6.1.6.3.1.1.5.4": "linkUp",
    "1.3.6.1.6.3.1.1.5.5": "authenticationFailure",
    "1.3.6.1.6.3.1.1.5.6": "egpNeighborLoss",
    # Cisco OSPF traps
    "1.3.6.1.4.1.9.10.99.1.1": "ciscoOspfNbrStateChange",
    "1.3.6.1.2.1.14.16.2.2":   "ospfNbrStateChange",
    "1.3.6.1.2.1.14.16.2.1":   "ospfVirtNbrStateChange",
    # BGP
    "1.3.6.1.2.1.15.7":        "bgpEstablished",
    "1.3.6.1.2.1.15.8":        "bgpBackwardTransition",
    # Cisco env / chassis
    "1.3.6.1.4.1.9.9.13.3.0.1": "ciscoPowerSupplyFailed",
    "1.3.6.1.4.1.9.9.13.3.0.2": "ciscoPowerSupplyOk",
    "1.3.6.1.4.1.9.9.13.3.0.3": "ciscoFanFailed",
    "1.3.6.1.4.1.9.9.43.2.0.1": "ciscoConfigChangeTrap",
    "1.3.6.1.4.1.9.9.43.2.0.2": "ciscoConfigSaveTrap",
    "1.3.6.1.4.1.9.9.41.2.0.1": "clogMessageGenerated",
    # Cisco enterprise-specific link traps (SNMPv2c format wrapping SNMPv1 generic traps)
    "1.3.6.1.4.1.9.0.1": "ciscoLinkDown",
    "1.3.6.1.4.1.9.0.2": "ciscoLinkUp",
    # Cisco IOS interface-related
    "1.3.6.1.4.1.9.2.2.1.0.1": "ciscoLinkDown",
    "1.3.6.1.4.1.9.2.2.1.0.2": "ciscoLinkUp",
}

# OID prefix → friendly label for varbind display
_OID_LABELS = {
    "1.3.6.1.2.1.1.3.0":     "sysUpTime",
    "1.3.6.1.6.3.1.1.4.1.0": "trapOID",
    # Interface table
    "1.3.6.1.2.1.2.2.1.1":   "ifIndex",
    "1.3.6.1.2.1.2.2.1.2":   "ifDescr",
    "1.3.6.1.2.1.2.2.1.3":   "ifType",
    "1.3.6.1.2.1.2.2.1.4":   "ifMtu",
    "1.3.6.1.2.1.2.2.1.5":   "ifSpeed",
    "1.3.6.1.2.1.2.2.1.7":   "ifAdminStatus",
    "1.3.6.1.2.1.2.2.1.8":   "ifOperStatus",
    # OSPF
    "1.3.6.1.2.1.14.1.1":    "ospfRouterId",
    "1.3.6.1.2.1.14.10.1.3": "ospfNbrIpAddr",
    "1.3.6.1.2.1.14.10.1.6": "ospfNbrState",
    # BGP
    "1.3.6.1.2.1.15.3.1.1":  "bgpPeerRemoteAddr",
    "1.3.6.1.2.1.15.3.1.2":  "bgpPeerState",
    # Cisco config change
    "1.3.6.1.4.1.9.9.43.1.1.6.1.2": "ccmHistEventCommandSource",
    # Cisco interface extended varbinds (sent alongside linkDown/Up)
    "1.3.6.1.4.1.9.2.2.1.1.20": "locIfReason",
}

_IF_STATUS = {"1": "up", "2": "down", "3": "testing"}
_IF_TYPE   = {
    "1": "other", "6": "ethernetCsmacd", "24": "softwareLoopback",
    "53": "propVirtual", "131": "tunnel", "161": "ieee8023adLag",
    "166": "mpls",
}
_OSPF_STATES = {"1":"down","2":"attempt","3":"init","4":"twoWay","5":"exchangeStart",
                "6":"exchange","7":"loading","8":"full"}
_BGP_STATES  = {"1":"idle","2":"connect","3":"active","4":"openSent","5":"openConfirm","6":"established"}


def _generic_trap_name(generic: int, specific: int, enterprise: str) -> str:
    if generic == 6:
        # Look up enterprise-specific
        key = f"{enterprise}.0.{specific}"
        return _TRAP_OID_NAMES.get(key, f"enterpriseSpecific({specific})")
    return _GENERIC_TRAP.get(generic, f"generic({generic})")


def _lookup_trap_oid(oid: str) -> str:
    # Exact match
    name = _TRAP_OID_NAMES.get(oid)
    if name:
        return name
    # Prefix match (e.g. OID ends in .0 variant)
    for prefix, name in _TRAP_OID_NAMES.items():
        if oid.startswith(prefix):
            return name
    return oid or "unknown"


def _label_oid(oid: str) -> str:
    """Return a short human label for a varbind OID."""
    # Exact match
    lbl = _OID_LABELS.get(oid)
    if lbl:
        return lbl
    # Prefix match — strip trailing index digits
    for prefix, label in _OID_LABELS.items():
        if oid.startswith(prefix):
            suffix = oid[len(prefix):]
            return f"{label}{suffix}"
    return oid


def _humanize_varbind(name: str, val: str) -> str:
    """Convert raw OID name+value into a readable 'key=value' string."""
    label = _label_oid(name)
    # Decode status/type integers
    if "ifOperStatus" in label or "ifAdminStatus" in label:
        val = _IF_STATUS.get(val, val)
    elif "ifType" in label:
        val = _IF_TYPE.get(val, val)
    elif "ospfNbrState" in label:
        val = _OSPF_STATES.get(val, val)
    elif "bgpPeerState" in label:
        val = _BGP_STATES.get(val, val)
    elif label == "trapOID":
        val = _lookup_trap_oid(val)
    # Skip sysUpTime and trapOID from inline display (already in header)
    if label in ("sysUpTime", "trapOID"):
        return ""
    # Skip raw OIDs that weren't resolved (avoid noise from unknown enterprise varbinds)
    if label == name and name.startswith("1.3.6.1.4.1."):
        return ""
    return f"{label}={val}"


def _build_summary_v1(trap: dict) -> str:
    trap_type = trap["trap_type"]
    parts = [trap_type]
    vb_parts = [_humanize_varbind(n, v) for n, v in trap["varbinds"]]
    vb_parts = [p for p in vb_parts if p]
    if vb_parts:
        parts.append(" | ".join(vb_parts))
    return " — ".join(parts) if parts else f"v1 trap from {trap['source_ip']}"


def _build_summary_v2(trap: dict) -> str:
    trap_type = trap["trap_type"]
    parts = [trap_type]
    vb_parts = [_humanize_varbind(n, v) for n, v in trap["varbinds"]]
    vb_parts = [p for p in vb_parts if p]
    if vb_parts:
        parts.append(" | ".join(vb_parts))
    return " — ".join(parts) if parts else f"v2c trap from {trap['source_ip']}"


def _short_id() -> str:
    import uuid
    return str(uuid.uuid4())[:8]


def _ber_length(data: bytes, pos: int) -> tuple:
    """Read BER length at pos, return (new_pos, length)."""
    b = data[pos]; pos += 1
    if b & 0x80:
        n = b & 0x7f
        length = int.from_bytes(data[pos:pos + n], "big")
        pos += n
    else:
        length = b
    return pos, length


def _ber_skip_tl(data: bytes, pos: int) -> int:
    """Skip a BER tag+length, return position of value."""
    pos += 1   # tag
    pos, _ = _ber_length(data, pos)
    return pos


def _ber_read_int(data: bytes, pos: int) -> tuple:
    """Read a BER INTEGER (tag 0x02), return (new_pos, value)."""
    assert data[pos] == 0x02, f"Expected INTEGER at {pos}, got 0x{data[pos]:02x}"
    pos += 1
    pos, length = _ber_length(data, pos)
    val = int.from_bytes(data[pos:pos + length], "big", signed=True)
    return pos + length, val


def _ber_read_octet(data: bytes, pos: int) -> tuple:
    """Read a BER OCTET STRING (tag 0x04), return (new_pos, bytes)."""
    assert data[pos] == 0x04, f"Expected OCTET STRING at {pos}, got 0x{data[pos]:02x}"
    pos += 1
    pos, length = _ber_length(data, pos)
    val = data[pos:pos + length]
    return pos + length, val


def _ber_read_raw(data: bytes, pos: int) -> tuple:
    """Read any BER TLV, return (new_pos, raw_value_bytes)."""
    pos += 1  # tag
    pos, length = _ber_length(data, pos)
    val = data[pos:pos + length]
    return pos + length, val


def _ber_read_oid(data: bytes, pos: int) -> tuple:
    """Read a BER OID (tag 0x06), return (new_pos, dotted-string)."""
    assert data[pos] == 0x06, f"Expected OID at {pos}, got 0x{data[pos]:02x}"
    pos += 1
    pos, length = _ber_length(data, pos)
    raw = data[pos:pos + length]
    # Decode OID
    if not raw:
        return pos + length, ""
    components = []
    first = raw[0]
    components.append(str(first // 40))
    components.append(str(first % 40))
    val = 0
    for b in raw[1:]:
        if b & 0x80:
            val = (val << 7) | (b & 0x7f)
        else:
            val = (val << 7) | b
            components.append(str(val))
            val = 0
    return pos + length, ".".join(components)


def _ber_read_varbinds(data: bytes, pos: int) -> list:
    """
    Read the VarBindList SEQUENCE-OF VarBind from pos.
    Returns list of (oid_string, value_string) tuples.
    """
    result = []
    try:
        # Skip outer VarBindList SEQUENCE
        pos = _ber_skip_tl(data, pos)
        while pos < len(data):
            # Each VarBind is a SEQUENCE { OID, value }
            if data[pos] != 0x30:
                break
            vb_start = pos
            pos += 1
            pos, vb_len = _ber_length(data, pos)
            vb_end = pos + vb_len
            # Read OID
            oid_pos, oid = _ber_read_oid(data, pos)
            # Read value (any type)
            val_tag = data[oid_pos]
            val_str = _ber_read_value(data, oid_pos, val_tag)
            result.append((oid, val_str))
            pos = vb_end
    except Exception:
        pass
    return result


def _ber_read_value(data: bytes, pos: int, tag: int) -> str:
    """Decode a BER value at pos to a readable string."""
    try:
        if tag == 0x02:  # INTEGER
            _, val = _ber_read_int(data, pos)
            return str(val)
        if tag == 0x04:  # OCTET STRING
            _, raw = _ber_read_octet(data, pos)
            try:
                return raw.decode("ascii", errors="replace")
            except Exception:
                return raw.hex()
        if tag == 0x06:  # OID
            _, oid = _ber_read_oid(data, pos)
            return oid
        if tag == 0x40:  # IpAddress
            pos += 1  # skip tag
            pos, length = _ber_length(data, pos)
            raw = data[pos:pos + length]
            if len(raw) == 4:
                return ".".join(str(b) for b in raw)
            return raw.hex()
        if tag == 0x41:  # Counter32
            pos += 1
            pos, length = _ber_length(data, pos)
            return str(int.from_bytes(data[pos:pos + length], "big"))
        if tag == 0x42:  # Gauge32
            pos += 1
            pos, length = _ber_length(data, pos)
            return str(int.from_bytes(data[pos:pos + length], "big"))
        if tag == 0x43:  # TimeTicks
            pos += 1
            pos, length = _ber_length(data, pos)
            ticks = int.from_bytes(data[pos:pos + length], "big")
            secs = ticks // 100
            h, r = divmod(secs, 3600)
            m, s = divmod(r, 60)
            return f"{h:02}:{m:02}:{s:02}"
        if tag == 0x44:  # Opaque
            _, raw = _ber_read_raw(data, pos)
            return raw.hex()
        if tag == 0x46:  # Counter64
            pos += 1
            pos, length = _ber_length(data, pos)
            return str(int.from_bytes(data[pos:pos + length], "big"))
        # Unknown — return hex
        _, raw = _ber_read_raw(data, pos)
        return raw.hex()
    except Exception:
        return "?"
