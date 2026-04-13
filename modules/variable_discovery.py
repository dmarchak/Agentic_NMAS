"""variable_discovery.py

Regex-based network variable extraction from device running configurations.

SSHes to all devices in the current list in parallel, runs `show running-config`,
and extracts facts (hostname, loopback0 IP, OSPF process/area, BGP AS, MPLS,
VRFs, EIGRP, ISIS, router-id, BGP neighbors, etc.) using compiled regex patterns.
Results are merged into the list's variables.json store.  Called by the background
agent runner when the variable store is empty, avoiding unnecessary AI token usage
for straightforward fact collection.
"""

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex patterns for IOS/IOS-XE running config parsing
# ---------------------------------------------------------------------------

_RE_HOSTNAME    = re.compile(r"^hostname\s+(\S+)", re.MULTILINE)
_RE_LOOPBACK0   = re.compile(
    r"interface\s+Loopback0.*?^\s+ip address\s+(\d[\d.]+)\s+(\d[\d.]+)",
    re.MULTILINE | re.DOTALL,
)
_RE_OSPF_PID    = re.compile(r"^router ospf\s+(\d+)", re.MULTILINE)
_RE_OSPF_AREA   = re.compile(r"^\s+network\s+\S+\s+\S+\s+area\s+(\S+)", re.MULTILINE)
_RE_BGP_AS      = re.compile(r"^router bgp\s+(\d+)", re.MULTILINE)
_RE_MPLS        = re.compile(r"^\s+mpls ip", re.MULTILINE)
_RE_VRF_DEF     = re.compile(r"^(?:vrf definition|ip vrf)\s+(\S+)", re.MULTILINE)
_RE_EIGRP_AS    = re.compile(r"^router eigrp\s+(\d+)", re.MULTILINE)
_RE_ISIS        = re.compile(r"^router isis\s*(\S*)", re.MULTILINE)
_RE_MGMT_IF     = re.compile(
    r"interface\s+(Management\S+|GigabitEthernet0/0|FastEthernet0/0).*?^\s+ip address\s+(\d[\d.]+)",
    re.MULTILINE | re.DOTALL,
)
_RE_ROUTER_ID   = re.compile(r"^\s+router-id\s+(\d[\d.]+)", re.MULTILINE)
_RE_LDP         = re.compile(r"^mpls ldp router-id|^\s+mpls ip", re.MULTILINE)
_RE_BGP_NEIGHBOR = re.compile(r"^\s+neighbor\s+(\d[\d.]+)\s+remote-as\s+(\d+)", re.MULTILINE)


def parse_running_config(config: str, device_ip: str) -> dict:
    """
    Parse a running config string and return a flat dict of discovered facts.
    Keys are prefixed with the device hostname (e.g. 'Core-1_loopback0').
    """
    facts = {}

    # Hostname
    m = _RE_HOSTNAME.search(config)
    hostname = m.group(1) if m else device_ip.replace(".", "_")
    prefix = hostname  # use hostname as key prefix

    facts[f"{prefix}_hostname"]   = hostname
    facts[f"{prefix}_mgmt_ip"]    = device_ip

    # Infer role from hostname
    hn_lower = hostname.lower()
    if any(x in hn_lower for x in ("core", "-c", "_c")):
        role = "P"
    elif any(x in hn_lower for x in ("pe-", "_pe", "pe1", "pe2", "pe3", "pe4")):
        role = "PE"
    elif any(x in hn_lower for x in ("ce-", "_ce", "ce1", "ce2")):
        role = "CE"
    elif any(x in hn_lower for x in ("rr", "reflector")):
        role = "RR"
    elif any(x in hn_lower for x in ("isp", "provider", "t1", "t3")):
        role = "ISP"
    elif any(x in hn_lower for x in ("internal", "int-")):
        role = "internal"
    elif any(x in hn_lower for x in ("access", "acc-")):
        role = "access"
    else:
        role = "unknown"
    facts[f"{prefix}_role"] = role

    # Loopback0
    m = _RE_LOOPBACK0.search(config)
    if m:
        facts[f"{prefix}_loopback0"] = m.group(1)

    # OSPF
    m = _RE_OSPF_PID.search(config)
    if m:
        facts[f"{prefix}_ospf_pid"] = m.group(1)
        # Grab the first area we can find
        am = _RE_OSPF_AREA.search(config)
        if am:
            facts[f"{prefix}_ospf_area"] = am.group(1)
        # Router-ID
        rim = _RE_ROUTER_ID.search(config)
        if rim:
            facts[f"{prefix}_ospf_router_id"] = rim.group(1)

    # BGP
    m = _RE_BGP_AS.search(config)
    if m:
        facts[f"{prefix}_bgp_as"] = m.group(1)
        # BGP neighbors summary
        neighbors = _RE_BGP_NEIGHBOR.findall(config)
        if neighbors:
            neighbor_summary = ", ".join(f"{ip}(AS{asn})" for ip, asn in neighbors[:8])
            facts[f"{prefix}_bgp_neighbors"] = neighbor_summary

    # EIGRP
    m = _RE_EIGRP_AS.search(config)
    if m:
        facts[f"{prefix}_eigrp_as"] = m.group(1)

    # IS-IS
    m = _RE_ISIS.search(config)
    if m:
        facts[f"{prefix}_isis"] = m.group(1) or "yes"

    # MPLS
    facts[f"{prefix}_mpls"] = "yes" if _RE_MPLS.search(config) else "no"

    # VRFs
    vrfs = [v for v in _RE_VRF_DEF.findall(config) if v.lower() not in ("mgmt", "management", "Mgmt-vrf")]
    if vrfs:
        facts[f"{prefix}_vrfs"] = ", ".join(vrfs)

    # Routing protocol summary
    protos = []
    if f"{prefix}_ospf_pid" in facts:
        protos.append("OSPF")
    if f"{prefix}_bgp_as" in facts:
        protos.append("BGP")
    if f"{prefix}_eigrp_as" in facts:
        protos.append("EIGRP")
    if f"{prefix}_isis" in facts:
        protos.append("ISIS")
    if not protos:
        protos.append("static")
    facts[f"{prefix}_routing_protocols"] = ", ".join(protos)

    return facts


def discover_variables_for_list(devices: list, status_cache: dict = None) -> dict:
    """
    SSH to each device in parallel, pull running-config, parse facts.
    Returns a merged dict of all discovered variables, and also writes
    them directly to variables.json for the current list.

    Only attempts devices that are marked online in status_cache (if provided).
    """
    from modules.device import get_current_device_list, load_saved_devices
    from modules.connection import get_persistent_connection
    from modules.commands import run_device_command

    # Filter to reachable devices
    if status_cache:
        targets = [d for d in devices if status_cache.get(d.get("ip", ""), False)]
    else:
        targets = list(devices)

    if not targets:
        log.warning("variable_discovery: no reachable devices")
        return {}

    log.info("variable_discovery: starting for %d device(s)", len(targets))

    all_facts: dict = {}
    errors: list = []
    pool_store: dict = {}  # per-call private pool — no sharing
    lock = threading.Lock()

    def _discover_one(dev: dict) -> tuple[str, dict, Optional[str]]:
        ip = dev.get("ip", "")
        try:
            priv_pool = {}
            priv_lock = threading.Lock()
            conn   = get_persistent_connection(dev, priv_pool, priv_lock)
            config = run_device_command(conn, "show running-config")
            if not config or len(config) < 50:
                return ip, {}, f"empty config response"
            facts = parse_running_config(config, ip)
            hostname = facts.get(next(
                (k for k in facts if k.endswith("_hostname")), ""), ip)
            log.info("variable_discovery: parsed %d facts from %s (%s)",
                     len(facts), hostname, ip)
            return ip, facts, None
        except Exception as exc:
            log.warning("variable_discovery: %s failed — %s", ip, exc)
            return ip, {}, str(exc)

    max_workers = min(len(targets), 6)
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="vardisc") as pool:
        futures = {pool.submit(_discover_one, dev): dev for dev in targets}
        for fut in as_completed(futures):
            ip, facts, err = fut.result()
            if err:
                errors.append(f"{ip}: {err}")
            else:
                all_facts.update(facts)

    if errors:
        log.warning("variable_discovery: %d device(s) failed: %s", len(errors), errors)

    # Write directly to variables.json
    if all_facts:
        _merge_and_save(all_facts)
        log.info("variable_discovery: stored %d variables", len(all_facts))

    return all_facts


def _merge_and_save(new_facts: dict) -> None:
    """
    Merge new facts into the existing variable store without overwriting manual entries.
    Holds the module-level variables lock for the entire read-modify-write cycle to
    prevent concurrent writers from corrupting the file.
    """
    from modules.ai_assistant import _get_variables_path, _variables_lock
    import json, os

    path = _get_variables_path()
    tmp  = path + ".tmp"
    now  = time.strftime("%Y-%m-%d %H:%M")

    with _variables_lock:
        # Load inside the lock so no other writer can slip in between load and save
        try:
            with open(path, encoding="utf-8") as fh:
                existing = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            existing = {}

        merged = dict(existing)
        for key, value in new_facts.items():
            if key not in merged:
                merged[key] = {
                    "value":       str(value),
                    "description": f"auto: discovered {now}",
                    "updated":     now,
                }
            elif merged[key].get("description", "").startswith("auto:"):
                # Update stale auto-discovered values; preserve manually set ones
                merged[key] = {
                    "value":       str(value),
                    "description": f"auto: discovered {now}",
                    "updated":     now,
                }
            # else: keep the manually set value

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
        os.replace(tmp, path)   # atomic rename
