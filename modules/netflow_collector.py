"""netflow_collector.py

NetFlow v5/v9 UDP collector and flow summarizer.

Listens for NetFlow export packets from Cisco IOS devices, decodes v5
(fixed 48-byte records) and v9 (template-based) formats, and stores recent
flows in a 500-entry ring buffer along with per-source traffic aggregates.
The AI assistant can query flow data to identify top talkers and bandwidth
consumers.  Default listen port is 9996, configurable per list via
collector_config.  Runs as a daemon thread started on server startup.
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

_MAX_FLOWS   = 500          # ring buffer size
_flows: list = []
_flow_lock   = threading.Lock()
_flow_stats: dict = {}      # src_ip → {packets, bytes, flows} aggregated

_netflow_thread: Optional[threading.Thread] = None
_netflow_stop   = threading.Event()


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _flow_file() -> str:
    try:
        from modules.config import get_current_list_data_dir
        return os.path.join(get_current_list_data_dir(), "netflow_flows.json")
    except Exception:
        return os.path.join(os.path.dirname(__file__), "..", "data", "netflow_flows.json")


def _load_flows() -> None:
    """Restore persisted flows from disk into the in-memory ring buffer."""
    global _flows
    try:
        path = _flow_file()
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as fh:
            stored = json.load(fh)
        if isinstance(stored, list):
            with _flow_lock:
                _flows = stored[-_MAX_FLOWS:]
            log.info("netflow_collector: loaded %d persisted flows", len(_flows))
    except Exception as exc:
        log.warning("netflow_collector: could not load persisted flows: %s", exc)


def _save_flows(new_flows: list) -> None:
    with _flow_lock:
        _flows.extend(new_flows)
        if len(_flows) > _MAX_FLOWS:
            del _flows[:len(_flows) - _MAX_FLOWS]
        data = list(_flows)
    try:
        path = _flow_file()
        tmp  = path + ".tmp"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def get_recent_flows(n: int = 100, device_ips: set | None = None) -> list:
    with _flow_lock:
        flows = list(reversed(_flows))
    if device_ips is not None:
        flows = [f for f in flows if f.get("exporter_ip") in device_ips]
    return flows[:n]


def clear_flows() -> None:
    """Clear the in-memory flow buffer and remove the persisted file."""
    global _flows, _flow_stats
    with _flow_lock:
        _flows.clear()
        _flow_stats.clear()
    try:
        path = _flow_file()
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    log.info("netflow_collector: flow buffer cleared")


def get_flow_stats(device_ips: set | None = None) -> dict:
    """Aggregated stats: top talkers, protocol breakdown, filtered to device_ips if given."""
    with _flow_lock:
        flows_copy = list(_flows)

    if device_ips is not None:
        flows_copy = [f for f in flows_copy if f.get("exporter_ip") in device_ips]

    top_src: dict  = {}
    top_dst: dict  = {}
    by_proto: dict = {}

    for f in flows_copy:
        src   = f.get("src_ip", "?")
        dst   = f.get("dst_ip", "?")
        proto = _proto_name(f.get("protocol", 0))
        octets = f.get("octets", 0)

        top_src[src]    = top_src.get(src, 0) + octets
        top_dst[dst]    = top_dst.get(dst, 0) + octets
        by_proto[proto] = by_proto.get(proto, 0) + octets

    def _top(d, n=10):
        return sorted(d.items(), key=lambda x: x[1], reverse=True)[:n]

    return {
        "total_flows":      len(flows_copy),
        "top_sources":      [{"ip": k, "bytes": v} for k, v in _top(top_src)],
        "top_destinations": [{"ip": k, "bytes": v} for k, v in _top(top_dst)],
        "by_protocol":      [{"proto": k, "bytes": v} for k, v in _top(by_proto)],
    }


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------

def start_netflow_receiver(port: int = 9996) -> None:
    """Start the NetFlow UDP receiver daemon thread (idempotent)."""
    global _netflow_thread
    if _netflow_thread and _netflow_thread.is_alive():
        return
    _load_flows()  # restore persisted flows before starting the receiver
    _netflow_stop.clear()
    _netflow_thread = threading.Thread(
        target=_netflow_loop, args=(port,), daemon=True, name="netflow-receiver"
    )
    _netflow_thread.start()
    log.info("netflow_collector: receiver started on UDP port %d", port)


def stop_netflow_receiver() -> None:
    _netflow_stop.set()


def _netflow_loop(port: int) -> None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        sock.settimeout(2.0)
        log.info("netflow_collector: listening on 0.0.0.0:%d", port)
    except Exception as exc:
        log.error("netflow_collector: cannot bind UDP %d — %s", port, exc)
        return

    # v9 template cache: {(exporter_ip, template_id): field_list}
    v9_templates: dict = {}

    while not _netflow_stop.is_set():
        try:
            data, addr = sock.recvfrom(65535)
            exporter_ip = addr[0]
            flows = _parse_packet(data, exporter_ip, v9_templates)
            if flows:
                _save_flows(flows)
                log.debug("netflow_collector: %d flow(s) from %s", len(flows), exporter_ip)
        except socket.timeout:
            continue
        except Exception as exc:
            log.debug("netflow_collector: recv error: %s", exc)

    sock.close()
    log.info("netflow_collector: receiver stopped")


# ---------------------------------------------------------------------------
# Packet parsers
# ---------------------------------------------------------------------------

def _parse_packet(data: bytes, exporter_ip: str, v9_templates: dict) -> list:
    if len(data) < 2:
        return []
    version = struct.unpack_from("!H", data, 0)[0]
    if version == 5:
        return _parse_v5(data, exporter_ip)
    elif version == 9:
        return _parse_v9(data, exporter_ip, v9_templates)
    else:
        log.debug("netflow_collector: unsupported version %d from %s", version, exporter_ip)
        return []


# ── NetFlow v5 ────────────────────────────────────────────────────────────

_V5_HEADER = struct.Struct("!HHIIIIBBH")   # 24 bytes
_V5_RECORD = struct.Struct("!4s4s4sHHIIIIHHBBBBHHBBH")   # 48 bytes

def _parse_v5(data: bytes, exporter_ip: str) -> list:
    if len(data) < 24:
        return []
    hdr = _V5_HEADER.unpack_from(data, 0)
    version, count, sys_uptime, unix_secs = hdr[0], hdr[1], hdr[2], hdr[3]

    flows = []
    offset = 24
    for i in range(min(count, 30)):   # cap at 30 records per packet
        if offset + 48 > len(data):
            break
        rec = _V5_RECORD.unpack_from(data, offset)
        offset += 48
        (src_addr, dst_addr, nexthop, input_if, output_if,
         packets, octets, first, last,
         src_port, dst_port, pad1, tcp_flags, protocol, tos,
         src_as, dst_as, src_mask, dst_mask, pad2) = rec

        flows.append({
            "exporter_ip": exporter_ip,
            "received_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(unix_secs)),
            "src_ip":      socket.inet_ntoa(src_addr),
            "dst_ip":      socket.inet_ntoa(dst_addr),
            "src_port":    src_port,
            "dst_port":    dst_port,
            "protocol":    protocol,
            "protocol_name": _proto_name(protocol),
            "packets":     packets,
            "octets":      octets,
            "input_if":    input_if,
            "output_if":   output_if,
            "tcp_flags":   tcp_flags,
            "tos":         tos,
            "src_as":      src_as,
            "dst_as":      dst_as,
            "version":     5,
        })
    return flows


# ── NetFlow v9 ────────────────────────────────────────────────────────────

# Field type → (name, size) — a subset of common field types
_V9_FIELD_TYPES = {
    1:  ("in_bytes",    4),
    2:  ("in_pkts",     4),
    4:  ("protocol",    1),
    5:  ("tos",         1),
    6:  ("tcp_flags",   1),
    7:  ("src_port",    2),
    8:  ("src_addr",    4),
    9:  ("src_mask",    1),
    10: ("input_if",    2),
    11: ("dst_port",    2),
    12: ("dst_addr",    4),
    13: ("dst_mask",    1),
    14: ("output_if",   2),
    15: ("nexthop",     4),
    16: ("src_as",      2),
    17: ("dst_as",      2),
    21: ("last_switched", 4),
    22: ("first_switched", 4),
    27: ("src_addr_v6", 16),
    28: ("dst_addr_v6", 16),
}

def _parse_v9(data: bytes, exporter_ip: str, v9_templates: dict) -> list:
    if len(data) < 20:
        return []

    # v9 header: version(2) count(2) sys_uptime(4) unix_secs(4) seq(4) source_id(4)
    version, count, sys_uptime, unix_secs, seq, source_id = struct.unpack_from("!HHIIII", data, 0)
    flows   = []
    offset  = 20

    for _ in range(count):
        if offset + 4 > len(data):
            break
        flowset_id, length = struct.unpack_from("!HH", data, offset)
        if length < 4:
            break
        flowset_data = data[offset + 4: offset + length]

        if flowset_id == 0:
            # Template FlowSet
            _parse_v9_templates(flowset_data, exporter_ip, source_id, v9_templates)
        elif flowset_id >= 256:
            # Data FlowSet — look up template
            tpl_key = (exporter_ip, source_id, flowset_id)
            template = v9_templates.get(tpl_key)
            if template:
                new = _decode_v9_data(flowset_data, template, exporter_ip, unix_secs)
                flows.extend(new)

        offset += length
        if length == 0:
            break

    return flows


def _parse_v9_templates(data: bytes, exporter_ip: str,
                         source_id: int, v9_templates: dict) -> None:
    offset = 0
    while offset + 4 <= len(data):
        template_id, field_count = struct.unpack_from("!HH", data, offset)
        offset += 4
        if template_id == 0 or field_count == 0:
            break
        fields = []
        for _ in range(field_count):
            if offset + 4 > len(data):
                break
            field_type, field_len = struct.unpack_from("!HH", data, offset)
            offset += 4
            fields.append((field_type, field_len))
        key = (exporter_ip, source_id, template_id)
        v9_templates[key] = fields
        log.debug("netflow_collector: learned v9 template %d (%d fields) from %s",
                  template_id, field_count, exporter_ip)


def _decode_v9_data(data: bytes, template: list,
                     exporter_ip: str, unix_secs: int) -> list:
    record_size = sum(f[1] for f in template)
    if record_size == 0:
        return []
    flows = []
    offset = 0
    while offset + record_size <= len(data):
        flow: dict = {
            "exporter_ip": exporter_ip,
            "received_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(unix_secs)),
            "version":     9,
        }
        for field_type, field_len in template:
            raw = data[offset:offset + field_len]
            offset += field_len
            info = _V9_FIELD_TYPES.get(field_type)
            if not info:
                continue
            fname, _ = info
            if fname in ("src_addr", "dst_addr", "nexthop") and field_len == 4:
                flow[fname] = socket.inet_ntoa(raw)
            elif field_len <= 4:
                flow[fname] = int.from_bytes(raw, "big")
            else:
                flow[fname] = raw.hex()

        # Normalize to common field names
        flow["src_ip"]    = flow.pop("src_addr", flow.get("src_ip", "?"))
        flow["dst_ip"]    = flow.pop("dst_addr", flow.get("dst_ip", "?"))
        flow["packets"]   = flow.pop("in_pkts",  flow.get("packets", 0))
        flow["octets"]    = flow.pop("in_bytes",  flow.get("octets", 0))
        if "protocol" in flow:
            flow["protocol_name"] = _proto_name(flow["protocol"])
        flows.append(flow)

    return flows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROTO_NAMES = {
    1: "ICMP", 6: "TCP", 17: "UDP", 47: "GRE", 50: "ESP",
    51: "AH", 89: "OSPF", 103: "PIM", 112: "VRRP",
}

def _proto_name(proto: int) -> str:
    return _PROTO_NAMES.get(proto, str(proto))
