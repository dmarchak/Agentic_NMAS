"""ccie_kb.py

Local CCIE-level knowledge base for Cisco IOS configuration.

All knowledge is stored as structured JSON files in ccie_kb/ at the project
root.  The AI queries this module instead of relying on LLM inference for
well-known protocol syntax — eliminating hallucinated commands and reducing
the API surface to intent interpretation and composition only.

Public API
──────────
  get_index()
      → dict   Full topic index (topic → file + subtopics list)

  query(topic, subtopic=None)
      → str    Formatted knowledge section for the requested topic

  compact_index()
      → str    One-line-per-topic summary for injection into stable context
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

_KB_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "ccie_kb")
)
_INDEX_FILE = os.path.join(_KB_DIR, "index.json")

_file_cache: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_index() -> dict:
    try:
        with open(_INDEX_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        log.warning("ccie_kb: could not load index: %s", exc)
        return {}


def _load_file(filename: str) -> dict:
    if filename in _file_cache:
        return _file_cache[filename]
    path = os.path.join(_KB_DIR, filename)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        _file_cache[filename] = data
        return data
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        log.warning("ccie_kb: could not load %s: %s", filename, exc)
        return {}


def _format_value(val, indent: int = 0) -> str:
    """Recursively format a JSON value into readable text."""
    pad = "  " * indent
    if isinstance(val, list):
        # If it's a list of strings that look like IOS commands, format as code block
        if all(isinstance(v, str) for v in val):
            return "\n".join(f"{pad}  {item}" for item in val)
        lines = []
        for item in val:
            lines.append(_format_value(item, indent))
        return "\n".join(lines)
    if isinstance(val, dict):
        lines = []
        for k, v in val.items():
            if k.startswith("_"):
                continue
            formatted = _format_value(v, indent + 1)
            lines.append(f"{pad}[{k}]\n{formatted}")
        return "\n".join(lines)
    return f"{pad}{val}"


def _extract_subtopic(data: dict, subtopic: str) -> Optional[str]:
    """Navigate nested dict by subtopic path (e.g. 'phase1' or 'verification')."""
    # Direct key lookup
    if subtopic in data:
        return _format_value(data[subtopic])
    # Case-insensitive search
    for k, v in data.items():
        if k.lower() == subtopic.lower():
            return _format_value(v)
    # Search one level deep
    for k, v in data.items():
        if isinstance(v, dict) and subtopic in v:
            return _format_value(v[subtopic])
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_index() -> dict:
    """Return the full topic index."""
    idx = _load_index()
    return idx.get("topics", {})


def compact_index() -> str:
    """
    One-line-per-topic summary for injection into stable context.
    Tells the AI what's in the KB without loading the content.
    """
    topics = get_index()
    if not topics:
        return ""
    lines = ["[CCIE KB — query_ccie_kb(topic, subtopic) for exact IOS command syntax]"]
    for topic, meta in sorted(topics.items()):
        subs = meta.get("subtopics", [])
        short_subs = ", ".join(subs[:6])
        if len(subs) > 6:
            short_subs += f" … +{len(subs)-6} more"
        lines.append(f"  {topic:<20s} → {short_subs}")
    lines.append(
        "Use query_ccie_kb BEFORE generating any IOS config — exact syntax, no guessing."
    )
    return "\n".join(lines)


def query(topic: str, subtopic: Optional[str] = None) -> str:
    """
    Return the knowledge section for *topic* (and optionally *subtopic*).

    If subtopic is None, returns the full topic section.
    Returns an empty string with a warning if topic is not found.
    """
    topics = get_index()
    topic_lower = topic.lower().replace("-", "_").replace(" ", "_")

    # Find the entry (exact or fuzzy)
    entry = topics.get(topic_lower)
    if not entry:
        # Try partial match
        matches = [k for k in topics if topic_lower in k or k in topic_lower]
        if matches:
            entry = topics[matches[0]]
            topic_lower = matches[0]
        else:
            return (
                f"Topic '{topic}' not found in CCIE KB.\n"
                f"Available topics: {', '.join(sorted(topics.keys()))}"
            )

    data = _load_file(entry["file"])
    if not data:
        return f"Could not load KB file for topic '{topic_lower}'."

    # Navigate to the topic within the file
    topic_data = data.get(topic_lower)
    if not topic_data:
        # Try to find by scanning all top-level keys
        for k, v in data.items():
            if k.lower() == topic_lower:
                topic_data = v
                break
    if not topic_data:
        return f"Topic '{topic_lower}' not found in {entry['file']}."

    if subtopic:
        result = _extract_subtopic(topic_data, subtopic)
        if result is None:
            available = [k for k in (topic_data.keys() if isinstance(topic_data, dict) else [])]
            return (
                f"Subtopic '{subtopic}' not found for '{topic_lower}'.\n"
                f"Available: {', '.join(available)}"
            )
        header = f"[CCIE KB: {topic_lower} / {subtopic}]\n"
        return header + result
    else:
        header = f"[CCIE KB: {topic_lower}]\n"
        return header + _format_value(topic_data)


def list_topics() -> list[str]:
    """Return all available topic names."""
    return sorted(get_index().keys())


# ---------------------------------------------------------------------------
# Field extraction — derive form schema from KB command templates
# ---------------------------------------------------------------------------

_PARAM_RE = re.compile(r'\{([^}|]+(?:\|[^}]*)?)\}')

_LABEL_MAP: dict[str, str] = {
    "a.b.c.d": "IP Address", "a_b_c_d": "IP Address",
    "asn": "AS Number", "local_as": "Local AS", "remote_as": "Remote AS",
    "pid": "Process ID", "process_id": "Process ID",
    "intf": "Interface", "interface": "Interface",
    "src_ip": "Source IP", "dst_ip": "Destination IP",
    "local_ip": "Local IP", "remote_ip": "Remote IP",
    "tunnel_ip": "Tunnel IP", "hub_tunnel_ip": "Hub Tunnel IP",
    "spoke_tunnel_ip": "Spoke Tunnel IP",
    "peer_ip": "Peer IP", "ce_ip": "CE IP",
    "psk": "Pre-Shared Key", "key": "Key / Password",
    "vrf_name": "VRF Name", "mtu": "MTU",
    "wildcard_mask": "Wildcard Mask", "wildcard": "Wildcard Mask",
    "wc": "Wildcard Mask", "wc_mask": "Wildcard Mask",
    "area_number": "Area Number", "area": "Area Number",
    "description": "Description", "descr": "Description",
    "network": "Network Address",
    "bw": "Bandwidth (kbps)", "bandwidth": "Bandwidth (kbps)",
    "nhrp_network_id": "NHRP Network ID",
    "hub_physical_ip": "Hub Physical IP",
    "spoke_physical_intf": "Spoke Physical Interface",
    "hub_physical_intf": "Hub Physical Interface",
    "rp_ip": "Rendezvous Point IP",
    "group_ip": "Multicast Group IP",
    "anycast_rp_ip": "Anycast RP IP",
}

_IP_HINTS    = {"ip", "address", "router_id", "a_b_c_d", "gateway", "server",
                "peer", "src_ip", "dst_ip", "nexthop", "hop", "hub", "spoke",
                "neighbor", "rp", "nhs", "collector"}
_MASK_HINTS  = {"mask", "wildcard", "wc"}
_NET_HINTS   = {"network", "prefix", "subnet"}
_INTF_HINTS  = {"intf", "interface", "source_int", "outside_int", "inside_int"}
_NUM_HINTS   = {"id", "asn", "number", "cost", "priority", "metric", "timeout",
                "interval", "count", "max_", "min_", "ttl", "port", "vid",
                "vlan", "mtu", "bandwidth", "bw", "group", "multiplier",
                "seq", "retries", "pps", "percent", "value", "weight"}
_PASS_HINTS  = {"key", "password", "secret", "psk", "community"}


def _infer_type(raw: str) -> dict:
    """Infer field type from a raw parameter token."""
    # Enum: {active|passive}, {1|2}
    if "|" in raw:
        opts = [o.strip() for o in raw.split("|")]
        return {"type": "select", "options": opts, "default": opts[0]}

    pn = raw.lower().replace(".", "_").replace("-", "_")

    if any(h in pn for h in _PASS_HINTS):
        return {"type": "password"}
    if any(h == pn or pn.endswith("_" + h) or pn.startswith(h + "_")
           for h in _IP_HINTS):
        return {"type": "text", "placeholder": "10.0.0.1"}
    if any(h in pn for h in _MASK_HINTS):
        return {"type": "text", "placeholder": "255.255.255.0"}
    if any(h == pn for h in _NET_HINTS):
        return {"type": "text", "placeholder": "10.0.0.0"}
    if any(h in pn for h in _INTF_HINTS):
        return {"type": "interface"}
    if any(h in pn for h in _NUM_HINTS):
        return {"type": "number", "placeholder": "1"}
    return {"type": "text", "placeholder": ""}


def _label(raw: str) -> str:
    norm = raw.lower().replace(".", "_").replace("-", "_")
    if norm in _LABEL_MAP:
        return _LABEL_MAP[norm]
    if raw in _LABEL_MAP:
        return _LABEL_MAP[raw]
    return raw.replace("_", " ").replace(".", " ").title()


def _extract_all_commands(data_node) -> list[str]:
    """Recursively pull all string lists that look like IOS command lists."""
    cmds: list[str] = []
    if isinstance(data_node, list):
        if all(isinstance(i, str) for i in data_node):
            return data_node
        for item in data_node:
            cmds.extend(_extract_all_commands(item))
    elif isinstance(data_node, dict):
        for k, v in data_node.items():
            if k.startswith("_"):
                continue
            if k == "commands" and isinstance(v, list):
                cmds.extend(v)
            elif k not in ("description", "notes", "note", "platforms",
                           "verification", "troubleshooting"):
                cmds.extend(_extract_all_commands(v))
    return cmds


def get_commands_for(topic: str, subtopic: Optional[str] = None) -> list[str]:
    """
    Return the IOS command list for *topic* (and optionally *subtopic*).
    Falls back to the topic's ``basic`` section if no subtopic is given.
    """
    topics = get_index()
    entry  = topics.get(topic.lower())
    if not entry:
        return []
    data       = _load_file(entry["file"])
    topic_data = data.get(topic.lower(), {})
    if not topic_data:
        return []

    if subtopic:
        node = _extract_subtopic.__wrapped__(topic_data, subtopic) if hasattr(
            _extract_subtopic, "__wrapped__") else None
        # Walk the dict directly
        target = topic_data
        for part in subtopic.split("."):
            if isinstance(target, dict) and part in target:
                target = target[part]
            else:
                target = None
                break
        if target is not None:
            cmds = _extract_all_commands(target)
            if cmds:
                return [c for c in cmds if isinstance(c, str)]

    # Fallback: basic section or top-level commands
    if isinstance(topic_data, dict):
        for key in ("basic", "commands"):
            if key in topic_data:
                node = topic_data[key]
                if isinstance(node, dict) and "commands" in node:
                    return node["commands"]
                if isinstance(node, list):
                    return [c for c in node if isinstance(c, str)]

    return _extract_all_commands(topic_data)


def get_fields(topic: str, subtopic: Optional[str] = None) -> list[dict]:
    """
    Return a list of form-field dicts for the given KB topic/subtopic.
    Each dict has: id, label, type (text/number/select/password/interface),
    placeholder, options (for select), required.
    """
    cmds = get_commands_for(topic, subtopic)
    seen: dict[str, dict] = {}

    for cmd in cmds:
        for m in _PARAM_RE.finditer(cmd):
            raw = m.group(1).strip()
            # Normalise to a stable field ID
            fid = (raw.lower()
                      .replace(".", "_")
                      .replace("-", "_")
                      .replace("|", "_or_")
                      .replace(" ", "_"))
            if fid in seen:
                continue
            meta = _infer_type(raw)
            seen[fid] = {
                "id":          fid,
                "raw":         raw,
                "label":       _label(raw),
                "required":    True,
                **meta,
            }

    return list(seen.values())
