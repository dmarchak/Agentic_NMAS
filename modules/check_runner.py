"""check_runner.py

Standalone verification runner invoked by Jenkins pipeline stages.

All check logic lives here as importable Python functions — no Groovy
string embedding, no ``writeFile``, nothing to escape.  Jenkins pipelines
simply call:

    bat 'python modules\\check_runner.py --function ospf --list-slug mylist'
    bat 'python modules\\check_runner.py --config-id cfg-abc123 --function interface'

Exit codes: 0 = all checks passed, 1 = one or more failures.

Two invocation modes
─────────────────────
--function X --list-slug SLUG
    Scan golden configs for list SLUG, find every device that has function X
    configured, load credentials from devices.csv, run the check.
    Used by persistent function pipelines built by pipeline_builder.

--config-id ID [--function X]
    Read data/configure_jobs/{ID}.json for the device list.  Load credentials
    from the current device list matching those IPs.  Run the check for the
    config_type recorded in the job (or override with --function).
    Used by configure_apply verification pipelines.

Adding a new check
──────────────────
1.  Write a ``check_<name>(conn, device) -> Optional[str]`` function below.
    Return None on pass, a descriptive failure message on fail.
2.  Register it in the CHECKS dict at the bottom of this file.
3.  Add a schedule entry in pipeline_builder._FUNCTION_SCHEDULE if needed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# Check functions — one per network feature
# ---------------------------------------------------------------------------
# Each function receives:
#   conn    — a connected, enable-mode Netmiko session
#   device  — dict with hostname, ip, and feature-specific params (see
#              _device_params_for() below for what keys are populated)
# Returns None on pass, a non-empty string describing the failure on fail.


def check_ospf(conn, device: dict) -> Optional[str]:
    pid = device.get("ospf_pid", "1")
    proc = conn.send_command(f"show ip ospf {pid}")
    if "OSPF Router with ID" not in proc:
        return f"OSPF process {pid} not running on {device['hostname']}"
    nbrs = conn.send_command(f"show ip ospf {pid} neighbor")
    if nbrs.count("FULL/") == 0:
        return f"No OSPF neighbors in FULL state on {device['hostname']} (pid={pid})"
    return None


def check_bgp(conn, device: dict) -> Optional[str]:
    out = conn.send_command("show ip bgp summary")
    if "BGP router identifier" not in out:
        return f"BGP not running on {device['hostname']}"
    # An established peer row starts with an IP address and ends with a
    # numeric prefix count.  Idle/Active rows end with a text state word.
    established = sum(
        1 for ln in out.splitlines()
        if re.match(r"^\d+\.\d+\.\d+\.\d+", ln.strip())
        and re.search(r"\s+\d+\s*$", ln)
    )
    if established == 0:
        return f"BGP: no established peers on {device['hostname']}"
    return None


def check_eigrp(conn, device: dict) -> Optional[str]:
    asn = device.get("eigrp_as", "1")
    out = conn.send_command("show ip eigrp neighbors")
    if not out.strip() or "H " not in out:
        return f"No EIGRP neighbors on {device['hostname']} (AS {asn})"
    return None


def check_mpls(conn, device: dict) -> Optional[str]:
    ifaces = conn.send_command("show mpls interfaces")
    if not ifaces.strip() or "No MPLS" in ifaces:
        return f"MPLS not enabled on any interface on {device['hostname']}"
    ldp = conn.send_command("show mpls ldp neighbor")
    if not ldp.strip():
        return f"No LDP neighbors on {device['hostname']}"
    return None


def check_tunnel(conn, device: dict) -> Optional[str]:
    for tid in device.get("tunnel_ids", []):
        out = conn.send_command(f"show interface Tunnel{tid}")
        if "line protocol is down" in out.lower() or "invalid" in out.lower():
            return f"Tunnel{tid} is down or invalid on {device['hostname']}"
    return None


def check_nat(conn, device: dict) -> Optional[str]:
    stats = conn.send_command("show ip nat statistics")
    if "Total active translations" not in stats:
        return f"NAT not active on {device['hostname']}"
    return None


def check_snmp(conn, device: dict) -> Optional[str]:
    community = device.get("snmp_community", "")
    out = conn.send_command("show snmp community")
    if community and community not in out:
        return f"SNMP community '{community}' not found on {device['hostname']}"
    return None


def check_staticroute(conn, device: dict) -> Optional[str]:
    routes = device.get("static_routes", [])
    if not routes:
        return None
    v4_out = conn.send_command("show ip route static")
    for r in routes:
        prefix = r.get("prefix", "")
        if prefix and prefix not in v4_out:
            return f"Static route to {prefix} missing on {device['hostname']}"
    return None


def check_loopback(conn, device: dict) -> Optional[str]:
    for lb in device.get("loopbacks", []):
        num = str(lb.get("number", "0"))
        out = conn.send_command(f"show interface Loopback{num}")
        if "invalid" in out.lower() or "not found" in out.lower():
            return f"Loopback{num} does not exist on {device['hostname']}"
        if "line protocol is down" in out.lower():
            return f"Loopback{num} protocol is down on {device['hostname']}"
    return None


def check_interface(conn, device: dict) -> Optional[str]:
    for intf in device.get("check_interfaces", []):
        name = intf.get("interface", "")
        out  = conn.send_command(f"show interface {name}")
        if "line protocol is down" in out.lower():
            return f"Interface {name} protocol is down on {device['hostname']}"
        ip = intf.get("ip", "")
        if ip and f"Internet address is {ip}" not in out:
            return f"Expected IP {ip} not found on {name} of {device['hostname']}"
    return None


def check_dhcp(conn, device: dict) -> Optional[str]:
    pool = device.get("dhcp_pool", "")
    out  = conn.send_command(f"show ip dhcp pool {pool}")
    if pool and pool not in out:
        return f"DHCP pool '{pool}' not found on {device['hostname']}"
    return None


def check_vtp(conn, device: dict) -> Optional[str]:
    domain = device.get("vtp_domain", "")
    mode   = device.get("vtp_mode", "server")
    out    = conn.send_command("show vtp status")
    if domain and domain not in out:
        return f"VTP domain '{domain}' not found on {device['hostname']}"
    if mode and mode not in out.lower():
        return f"VTP mode '{mode}' not active on {device['hostname']}"
    return None


def check_rsvpte(conn, device: dict) -> Optional[str]:
    rsvp = conn.send_command("show ip rsvp interface")
    if not rsvp.strip() or "no rsvp" in rsvp.lower():
        return f"RSVP not active on any interface on {device['hostname']}"
    dest = device.get("tunnel_dest", "")
    if dest:
        te = conn.send_command("show mpls traffic-eng tunnels brief")
        if dest not in te and te.strip():
            return f"No MPLS TE tunnel to {dest} on {device['hostname']}"
    return None


# ---------------------------------------------------------------------------
# Check registry — maps function name to check function
# ---------------------------------------------------------------------------

CHECKS: dict[str, callable] = {
    "ospf":        check_ospf,
    "bgp":         check_bgp,
    "eigrp":       check_eigrp,
    "mpls":        check_mpls,
    "tunnel":      check_tunnel,
    "nat":         check_nat,
    "snmp":        check_snmp,
    "staticroute": check_staticroute,
    "loopback":    check_loopback,
    "interface":   check_interface,
    "interfaces":  check_interface,
    "dhcp":        check_dhcp,
    "vtp":         check_vtp,
    "rsvpte":      check_rsvpte,
}


# ---------------------------------------------------------------------------
# Device param extraction — per-function params read from golden config
# ---------------------------------------------------------------------------

def _device_params_for(function_type: str, cfg: str) -> dict:
    """Extract function-specific params from a golden config string."""
    p: dict = {}
    if function_type == "ospf":
        m = re.search(r"^router ospf (\d+)", cfg, re.MULTILINE)
        if m:
            p["ospf_pid"] = m.group(1)
            rid = re.search(r"router-id (\S+)", cfg[m.start(): m.start() + 500])
            if rid:
                p["router_id"] = rid.group(1)

    elif function_type == "bgp":
        m = re.search(r"^router bgp (\d+)", cfg, re.MULTILINE)
        if m:
            p["bgp_as"] = m.group(1)

    elif function_type == "eigrp":
        m = re.search(r"^router eigrp (\d+)", cfg, re.MULTILINE)
        if m:
            p["eigrp_as"] = m.group(1)

    elif function_type == "snmp":
        m = re.search(r"^snmp-server community (\S+)", cfg, re.MULTILINE)
        if m:
            p["snmp_community"] = m.group(1)

    elif function_type == "staticroute":
        routes = re.findall(r"^ip route (\d[\d.]+)\s+(\d[\d.]+)", cfg, re.MULTILINE)
        p["static_routes"] = [{"prefix": r[0], "mask": r[1]} for r in routes[:6]]

    elif function_type == "loopback":
        loopbacks = []
        for m in re.finditer(
            r"^interface Loopback(\d+)(.*?)(?=^interface|\Z)", cfg, re.MULTILINE | re.DOTALL
        ):
            ipv4 = re.search(r"ip address (\d[\d.]+)\s+(\d[\d.]+)", m.group(2))
            loopbacks.append({
                "number": m.group(1),
                "ipv4":   ipv4.group(1) if ipv4 else "",
                "mask":   ipv4.group(2) if ipv4 else "",
            })
        p["loopbacks"] = loopbacks

    elif function_type in ("interface", "interfaces"):
        intfs = []
        for m in re.finditer(
            r"^interface (\S+)(.*?)(?=^interface|\Z)", cfg, re.MULTILINE | re.DOTALL
        ):
            name = m.group(1)
            if "Loopback" in name or "Tunnel" in name:
                continue
            ipv4 = re.search(r"ip address (\d[\d.]+)", m.group(2))
            if ipv4:
                intfs.append({"interface": name, "ip": ipv4.group(1)})
        p["check_interfaces"] = intfs[:6]

    elif function_type == "tunnel":
        tids = re.findall(r"^interface Tunnel(\d+)", cfg, re.MULTILINE)
        p["tunnel_ids"] = tids[:4]

    elif function_type == "dhcp":
        m = re.search(r"^ip dhcp pool (\S+)", cfg, re.MULTILINE)
        if m:
            p["dhcp_pool"] = m.group(1)

    elif function_type == "vtp":
        dm = re.search(r"^vtp domain (\S+)", cfg, re.MULTILINE)
        mm = re.search(r"^vtp mode (\S+)",   cfg, re.MULTILINE)
        if dm:
            p["vtp_domain"] = dm.group(1)
        if mm:
            p["vtp_mode"] = mm.group(1)

    elif function_type == "rsvpte":
        m = re.search(r"tunnel destination (\S+)", cfg)
        if m:
            p["tunnel_dest"] = m.group(1)

    return p


# ---------------------------------------------------------------------------
# Device loading — credentials from encrypted device list
# ---------------------------------------------------------------------------

def _load_devices_with_creds(list_slug: str) -> list[dict]:
    """Return device list (with decrypted credentials) for a given list slug."""
    import sys
    sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
    from modules.config import DATA_DIR
    from modules.device import load_saved_devices, decrypt_field

    list_file = os.path.join(DATA_DIR, "lists", list_slug, "devices.csv")
    if not os.path.exists(list_file):
        raise FileNotFoundError(f"Device list not found: {list_file}")

    raw = load_saved_devices(list_file)
    devices = []
    for d in raw:
        try:
            pwd = decrypt_field(d.get("password", ""))
        except Exception:
            pwd = d.get("password", "")
        devices.append({
            "hostname": d.get("hostname", d["ip"]),
            "ip":       d["ip"],
            "username": d.get("username", ""),
            "password": pwd,
        })
    return devices


def _load_devices_for_config_job(config_id: str) -> tuple[list[dict], str]:
    """
    Return (devices_with_creds, function_type) for a configure_apply job.
    Credentials are resolved from the NMAS device list, not the job JSON.
    """
    import sys
    sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
    from modules.configure import load_config_job
    from modules.config import DATA_DIR, list_slug as _list_slug
    from modules.device import load_saved_devices, decrypt_field

    job = load_config_job(config_id)
    if not job:
        raise ValueError(f"Config job '{config_id}' not found")

    function_type = job.get("config_type", "")
    target_ips    = {d["ip"] for d in job.get("devices", [])}

    # Find which list has these IPs by scanning all lists.
    lists_dir = os.path.join(DATA_DIR, "lists")
    cred_map: dict[str, dict] = {}
    for slug in os.listdir(lists_dir):
        list_file = os.path.join(lists_dir, slug, "devices.csv")
        if not os.path.exists(list_file):
            continue
        for d in load_saved_devices(list_file):
            if d["ip"] in target_ips:
                try:
                    pwd = decrypt_field(d.get("password", ""))
                except Exception:
                    pwd = d.get("password", "")
                cred_map[d["ip"]] = {
                    "hostname": d.get("hostname", d["ip"]),
                    "ip":       d["ip"],
                    "username": d.get("username", ""),
                    "password": pwd,
                }

    devices = [cred_map[ip] for ip in target_ips if ip in cred_map]
    if not devices:
        raise ValueError(f"No credential-matched devices found for job '{config_id}'")

    return devices, function_type


# ---------------------------------------------------------------------------
# Check execution
# ---------------------------------------------------------------------------

def run_checks_on_devices(
    function_type: str,
    devices:       list[dict],
) -> tuple[list[str], list[str]]:
    """
    Run the check for *function_type* against every device in *devices*.

    Returns (passed_hostnames, failure_messages).
    """
    try:
        from netmiko import (
            ConnectHandler,
            NetmikoTimeoutException,
            NetmikoAuthenticationException,
        )
    except ImportError:
        print("ERROR: netmiko is not installed.  Run: pip install netmiko", file=sys.stderr)
        sys.exit(1)

    check_fn = CHECKS.get(function_type)
    if check_fn is None:
        print(f"ERROR: no check registered for function type '{function_type}'", file=sys.stderr)
        sys.exit(1)

    passed:   list[str] = []
    failures: list[str] = []

    for device in devices:
        hostname = device["hostname"]
        ip       = device["ip"]
        print(f"Checking {hostname} ({ip})…")
        conn_params = {
            "device_type": "cisco_ios",
            "ip":          ip,
            "username":    device.get("username", ""),
            "password":    device.get("password", ""),
        }
        try:
            conn   = ConnectHandler(**conn_params)
            conn.enable()
            result = check_fn(conn, device)
            conn.disconnect()
            if result:
                print(f"  FAIL: {result}")
                failures.append(result)
            else:
                print(f"  PASS")
                passed.append(hostname)
        except NetmikoTimeoutException:
            msg = f"TIMEOUT connecting to {hostname} ({ip})"
            print(f"  FAIL: {msg}")
            failures.append(msg)
        except NetmikoAuthenticationException:
            msg = f"AUTH FAILED for {hostname} ({ip})"
            print(f"  FAIL: {msg}")
            failures.append(msg)
        except Exception as exc:
            msg = f"ERROR on {hostname}: {exc}"
            print(f"  FAIL: {msg}")
            failures.append(msg)

    return passed, failures


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run NMAS network verification checks for Jenkins pipelines.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run OSPF checks for the 'csci5160final' device list
  python modules\\check_runner.py --function ospf --list-slug csci5160final

  # Run the verification for a specific configure_apply job
  python modules\\check_runner.py --config-id cfg-1745000000-ab12cd34

  # Override the function type recorded in the job
  python modules\\check_runner.py --config-id cfg-xxx --function bgp
""",
    )
    p.add_argument("--function",   metavar="TYPE",   help="Function type: ospf, bgp, mpls, …")
    p.add_argument("--list-slug",  metavar="SLUG",   help="Device list slug (with --function)")
    p.add_argument("--config-id",  metavar="ID",     help="configure_apply job ID")
    return p


def main(argv=None) -> int:
    parser = _build_arg_parser()
    args   = parser.parse_args(argv)

    # ── Mode 1: function pipeline (--function + --list-slug) ─────────────
    if args.function and args.list_slug and not args.config_id:
        function_type = args.function
        list_slug     = args.list_slug

        print(f"[check_runner] function={function_type}  list={list_slug}")

        devices_raw = _load_devices_with_creds(list_slug)
        if not devices_raw:
            print(f"ERROR: no devices found in list '{list_slug}'", file=sys.stderr)
            return 1

        # Load golden configs to find which devices have this function and
        # extract their per-device params.
        sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
        try:
            from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
        except ImportError:
            print("WARNING: could not import ai_assistant — running checks without per-device params")
            _list_golden_configs    = lambda: []
            _load_golden_config_file = lambda ip: None

        golden  = _list_golden_configs()
        ip_cfg  = {e["device_ip"]: _load_golden_config_file(e["device_ip"]) for e in golden}
        dev_map = {d["ip"]: d for d in devices_raw}

        devices: list[dict] = []
        for ip, cfg in ip_cfg.items():
            if ip not in dev_map or not cfg:
                continue
            # Check whether this device actually has the function configured.
            params = _device_params_for(function_type, cfg)
            # Simple presence heuristic — if no params were found, the
            # function might not be configured; skip unless forced.
            dev = dict(dev_map[ip])
            dev.update(params)
            devices.append(dev)

        # Fallback: if no golden configs exist, check all devices (best-effort).
        if not devices:
            print("WARNING: no golden configs found — checking all devices")
            devices = list(devices_raw)

    # ── Mode 2: configure_apply job (--config-id) ────────────────────────
    elif args.config_id:
        print(f"[check_runner] config-id={args.config_id}")
        devices, detected_function = _load_devices_for_config_job(args.config_id)
        function_type = args.function or detected_function
        if not function_type:
            print("ERROR: could not determine function type from job — use --function", file=sys.stderr)
            return 1
        # Enrich with per-device params from golden configs.
        sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
        try:
            from modules.ai_assistant import _load_golden_config_file
            for dev in devices:
                cfg = _load_golden_config_file(dev["ip"])
                if cfg:
                    dev.update(_device_params_for(function_type, cfg))
        except ImportError:
            pass
        print(f"[check_runner] function={function_type}  devices={[d['hostname'] for d in devices]}")

    # ── Neither mode ─────────────────────────────────────────────────────
    else:
        parser.print_help()
        return 1

    if not devices:
        print(f"WARNING: no devices found with function '{function_type}' configured")
        return 0  # nothing to test — not a failure

    passed, failures = run_checks_on_devices(function_type, devices)

    print(f"\n{'─' * 50}")
    print(f"Results: {len(passed)} passed, {len(failures)} failed")
    if failures:
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("  All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
