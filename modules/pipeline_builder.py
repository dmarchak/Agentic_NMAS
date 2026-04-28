"""pipeline_builder.py

Builds and maintains persistent Jenkins verification pipelines keyed to
*network functions* (OSPF, BGP, MPLS, interfaces, …) rather than to
individual configure_apply runs.

Design principles
─────────────────
• Stable names   — each pipeline is named ``nmas-{list_slug}-{function}``
  (e.g. ``nmas-csci5160final-ospf``).  The same job is reused across runs;
  its check script is regenerated in-place whenever new devices are added.

• Auto-detect    — ``detect_network_functions`` scans golden configs and
  variables to find every function already active on the network, so
  pipelines can be bootstrapped from a clean state with no manual input.

• Auto-extend    — ``ensure_function_pipeline`` is called by configure_apply
  after every successful deploy.  It creates the function pipeline if it
  does not exist, or updates it to include the newly configured device.

• Cumulative     — pipelines accumulate over time.  Configuring BGP never
  removes the existing OSPF pipeline; both run on their own schedules.

Public API
──────────
  detect_network_functions(check_devices)
      → list[NetworkFunction]

  ensure_function_pipeline(config_type, newly_added_ips, params,
                            check_devices, jenkins_cfg, nmas_base)
      → dict  {"created": bool, "updated": bool, "job_name": str, ...}

  bootstrap_all_pipelines(check_devices, jenkins_cfg, nmas_base)
      → dict  {"created": [...], "skipped": [...], "errors": [...]}
"""

from __future__ import annotations

import json
import logging
import os
import re
import textwrap
import time
import xml.sax.saxutils as _sax
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cron schedule per function type (matches system-prompt defaults)
# ---------------------------------------------------------------------------
_FUNCTION_SCHEDULE: dict[str, str] = {
    "ospf":        "H/30 * * * *",   # every 30 min
    "eigrp":       "H/30 * * * *",
    "bgp":         "H/30 * * * *",
    "mpls":        "H/30 * * * *",
    "interface":   "H * * * *",      # hourly
    "interfaces":  "H * * * *",
    "loopback":    "H * * * *",
    "tunnel":      "H * * * *",
    "snmp":        "H H/2 * * *",    # every 2 h
    "nat":         "H * * * *",
    "dhcp":        "H H/4 * * *",    # every 4 h
    "vtp":         "H H/4 * * *",
    "staticroute": "H/30 * * * *",
    "rsvpte":      "H/30 * * * *",
}
_DEFAULT_SCHEDULE = "H H/2 * * *"   # fallback for unknown types


# ---------------------------------------------------------------------------
# Dataclass representing one detected network function
# ---------------------------------------------------------------------------

@dataclass
class NetworkFunction:
    """A protocol or feature detected on one or more devices in this list."""

    function_type: str                    # "ospf", "bgp", "mpls", …
    device_ips:    list[str]              # which devices have it configured
    # Per-device params extracted from golden configs (process IDs, AS numbers, …)
    params_by_ip:  dict[str, dict] = field(default_factory=dict)

    def job_name(self, list_slug: str) -> str:
        """Stable Jenkins job name for this function in this list."""
        safe = re.sub(r"[^\w-]", "-", list_slug.lower()).strip("-")
        return f"nmas-{safe}-{self.function_type}"

    def schedule(self) -> str:
        return _FUNCTION_SCHEDULE.get(self.function_type, _DEFAULT_SCHEDULE)


# ---------------------------------------------------------------------------
# Detection — scan golden configs to find active functions
# ---------------------------------------------------------------------------

def detect_network_functions(check_devices: list[dict]) -> list[NetworkFunction]:
    """
    Scan every saved golden config and return one NetworkFunction per detected
    protocol/feature.

    ``check_devices`` is the decrypted-credential device list (same format used
    by the check scripts) — it provides the SSH auth alongside the IPs.
    """
    try:
        from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
    except ImportError:
        log.warning("pipeline_builder: ai_assistant not importable — no golden configs read")
        return []

    golden_list = _list_golden_configs()
    if not golden_list:
        return []

    # Map IP → device dict (for SSH credentials)
    dev_by_ip: dict[str, dict] = {d["ip"]: d for d in check_devices}

    # Accumulate: function_type → NetworkFunction
    funcs: dict[str, NetworkFunction] = {}

    def _add(ftype: str, ip: str, params: dict) -> None:
        if ip not in dev_by_ip:
            return   # no SSH creds available for this device
        if ftype not in funcs:
            funcs[ftype] = NetworkFunction(function_type=ftype, device_ips=[])
        nf = funcs[ftype]
        if ip not in nf.device_ips:
            nf.device_ips.append(ip)
        nf.params_by_ip[ip] = params

    for entry in golden_list:
        ip       = entry["device_ip"]
        hostname = entry.get("hostname", ip)
        cfg      = _load_golden_config_file(ip)
        if not cfg:
            continue

        # ── OSPF ──────────────────────────────────────────────────────────
        for m in re.finditer(r"^router ospf (\d+)", cfg, re.MULTILINE):
            pid   = m.group(1)
            blk   = cfg[m.start(): m.start() + 600]
            rid_m = re.search(r"router-id (\S+)", blk)
            nbr_m = re.findall(r"neighbor (\d[\d.]+)", blk)
            _add("ospf", ip, {
                "process_id": pid,
                "router_id":  rid_m.group(1) if rid_m else "",
                "neighbors":  nbr_m[:4],
            })

        # ── BGP ───────────────────────────────────────────────────────────
        bgp_m = re.search(r"^router bgp (\d+)", cfg, re.MULTILINE)
        if bgp_m:
            blk   = cfg[bgp_m.start(): bgp_m.start() + 2000]
            peers = re.findall(r"neighbor (\d[\d.]+)\s+remote-as (\d+)", blk)
            _add("bgp", ip, {
                "local_as":  bgp_m.group(1),
                "neighbors": [{"ip": p[0], "remote_as": p[1]} for p in peers[:6]],
            })

        # ── EIGRP ─────────────────────────────────────────────────────────
        eigrp_m = re.search(r"^router eigrp (\d+)", cfg, re.MULTILINE)
        if eigrp_m:
            _add("eigrp", ip, {"as_number": eigrp_m.group(1)})

        # ── MPLS / LDP ────────────────────────────────────────────────────
        if re.search(r"\bmpls ip\b|\bmpls label protocol\b|\btag-switching ip\b",
                     cfg, re.MULTILINE | re.IGNORECASE):
            _add("mpls", ip, {})

        # ── GRE / DMVPN tunnels ───────────────────────────────────────────
        if re.search(r"^interface Tunnel", cfg, re.MULTILINE):
            tunnel_nums = re.findall(r"^interface Tunnel(\d+)", cfg, re.MULTILINE)
            _add("tunnel", ip, {"tunnel_ids": tunnel_nums[:4]})

        # ── NAT ───────────────────────────────────────────────────────────
        if re.search(r"\bip nat\b", cfg, re.MULTILINE):
            _add("nat", ip, {})

        # ── SNMP ──────────────────────────────────────────────────────────
        comm_m = re.search(r"^snmp-server community (\S+)", cfg, re.MULTILINE)
        if comm_m:
            _add("snmp", ip, {"community": comm_m.group(1)})

        # ── Static routes ─────────────────────────────────────────────────
        static = re.findall(r"^ip route (\d[\d.]+\s+\d[\d.]+)", cfg, re.MULTILINE)
        if static:
            _add("staticroute", ip, {
                "routes": [{"prefix": s.split()[0], "mask": s.split()[1]}
                            for s in static[:6]]
            })

        # ── Loopbacks with IPs ────────────────────────────────────────────
        lo_ips = {}
        for lo_m in re.finditer(r"^interface Loopback(\d+)(.*?)(?=^interface|\Z)",
                                 cfg, re.MULTILINE | re.DOTALL):
            num   = lo_m.group(1)
            ip_m2 = re.search(r"ip address (\d[\d.]+)\s+(\d[\d.]+)", lo_m.group(2))
            if ip_m2:
                lo_ips[num] = ip_m2.group(1)
        if lo_ips:
            _add("loopback", ip, {"loopbacks": [
                {"number": n, "ipv4": a, "mask": "255.255.255.255"}
                for n, a in lo_ips.items()
            ]})

        # ── Physical interfaces with IPs ──────────────────────────────────
        # Only add if the device has at least two non-loopback interfaces with IPs
        # (avoids a near-empty pipeline for management-only devices).
        intf_ips: list[dict] = []
        for intf_m in re.finditer(
            r"^interface (\S+)(.*?)(?=^interface|\Z)", cfg, re.MULTILINE | re.DOTALL
        ):
            iname = intf_m.group(1)
            if "Loopback" in iname or "Tunnel" in iname:
                continue
            ip_m3 = re.search(r"ip address (\d[\d.]+)\s+(\d[\d.]+)", intf_m.group(2))
            if ip_m3:
                intf_ips.append({"interface": iname, "ip": ip_m3.group(1),
                                  "mask": ip_m3.group(2)})
        if len(intf_ips) >= 2:
            _add("interface", ip, {"interfaces": intf_ips[:6]})

    return list(funcs.values())


# ---------------------------------------------------------------------------
# Check script generation — per-device params embedded in device dicts
# ---------------------------------------------------------------------------

# Maps function_type → a function that generates the run_checks body.
# Each generator receives the device dict (which carries per-device params)
# as the runtime context instead of a static params dict.

def _check_body_ospf() -> str:
    return textwrap.dedent("""\
        pid  = device.get("ospf_pid", "1")
        proc = conn.send_command(f"show ip ospf {pid}")
        if "OSPF Router with ID" not in proc:
            return f"OSPF process {pid} not running on {hostname}"
        nbrs = conn.send_command(f"show ip ospf {pid} neighbor")
        full = nbrs.count("FULL/")
        if full == 0:
            return f"No OSPF neighbors in FULL state on {hostname} (pid={pid})"
        return None
        """)


def _check_body_bgp() -> str:
    return textwrap.dedent("""\
        asn = device.get("bgp_as", "")
        out = conn.send_command("show ip bgp summary")
        if "BGP router identifier" not in out:
            return f"BGP process not running on {hostname}"
        # Count established peers (rows ending with an uptime token)
        import re as _re
        established = len(_re.findall(
            r"^\\d[\\d.]+\\s+\\d+\\s+\\d+\\s+\\d+\\s+\\d+\\s+\\d+\\s+\\d+\\s+[\\w:]+\\s*$",
            out, _re.MULTILINE,
        ))
        if established == 0:
            return f"BGP: no established peers on {hostname}"
        return None
        """)


def _check_body_eigrp() -> str:
    return textwrap.dedent("""\
        asn = device.get("eigrp_as", "1")
        out = conn.send_command("show ip eigrp neighbors")
        if not out.strip() or "H " not in out:
            return f"No EIGRP neighbors on {hostname} (AS {asn})"
        return None
        """)


def _check_body_mpls() -> str:
    return textwrap.dedent("""\
        ifaces = conn.send_command("show mpls interfaces")
        if not ifaces.strip() or "No MPLS" in ifaces:
            return f"MPLS not enabled on any interfaces on {hostname}"
        ldp = conn.send_command("show mpls ldp neighbor")
        if not ldp.strip():
            return f"No LDP neighbors on {hostname}"
        return None
        """)


def _check_body_tunnel() -> str:
    return textwrap.dedent("""\
        import re as _re
        tunnel_ids = device.get("tunnel_ids", [])
        for tid in tunnel_ids:
            out = conn.send_command(f"show interface Tunnel{tid}")
            if "line protocol is down" in out.lower() or "invalid" in out.lower():
                return f"Tunnel{tid} is down or invalid on {hostname}"
        return None
        """)


def _check_body_nat() -> str:
    return textwrap.dedent("""\
        stats = conn.send_command("show ip nat statistics")
        if "Total active translations" not in stats:
            return f"NAT not active on {hostname}"
        return None
        """)


def _check_body_snmp() -> str:
    return textwrap.dedent("""\
        community = device.get("snmp_community", "")
        out = conn.send_command("show snmp community")
        if community and community not in out:
            return f"SNMP community '{community}' not found on {hostname}"
        return None
        """)


def _check_body_staticroute() -> str:
    return textwrap.dedent("""\
        import re as _re
        routes = device.get("static_routes", [])
        if not routes:
            return None
        v4_out = conn.send_command("show ip route static")
        for r in routes:
            if r.get("prefix") and r["prefix"] not in v4_out:
                return f"Static route to {r['prefix']} missing on {hostname}"
        return None
        """)


def _check_body_loopback() -> str:
    return textwrap.dedent("""\
        loopbacks = device.get("loopbacks", [])
        for lb in loopbacks:
            num = str(lb.get("number", "0"))
            out = conn.send_command(f"show interface Loopback{num}")
            if "invalid" in out.lower() or "not found" in out.lower():
                return f"Loopback{num} does not exist on {hostname}"
            if "line protocol is down" in out.lower():
                return f"Loopback{num} protocol is down on {hostname}"
        return None
        """)


def _check_body_interface() -> str:
    return textwrap.dedent("""\
        interfaces = device.get("check_interfaces", [])
        for intf in interfaces:
            name = intf.get("interface", "")
            out  = conn.send_command(f"show interface {name}")
            if "line protocol is down" in out.lower():
                return f"Interface {name} protocol is down on {hostname}"
            ip = intf.get("ip", "")
            if ip and f"Internet address is {ip}" not in out:
                return f"Expected IP {ip} not found on {name} of {hostname}"
        return None
        """)


_CHECK_BODY_GENERATORS: dict[str, str] = {
    "ospf":        _check_body_ospf(),
    "bgp":         _check_body_bgp(),
    "eigrp":       _check_body_eigrp(),
    "mpls":        _check_body_mpls(),
    "tunnel":      _check_body_tunnel(),
    "nat":         _check_body_nat(),
    "snmp":        _check_body_snmp(),
    "staticroute": _check_body_staticroute(),
    "loopback":    _check_body_loopback(),
    "interface":   _check_body_interface(),
    "interfaces":  _check_body_interface(),
}


def _build_check_script(
    function: NetworkFunction,
    check_devices: list[dict],
) -> str:
    """
    Generate a self-contained Python verification script for one network function.

    Per-device parameters (process IDs, AS numbers, interface lists, etc.) are
    embedded directly in each device's dict in the DEVICES list so the check
    body can reference them as ``device.get("ospf_pid")``.
    """
    body = _CHECK_BODY_GENERATORS.get(function.function_type, "return None\n")

    # Build the device list with per-device params merged in.
    devices_with_params: list[dict] = []
    for dev in check_devices:
        ip = dev["ip"]
        if ip not in function.device_ips:
            continue
        p = function.params_by_ip.get(ip, {})
        entry = {
            "hostname": dev.get("hostname", ip),
            "ip":       ip,
            "username": dev.get("username", ""),
            "password": dev.get("password", ""),
        }
        # Embed function-specific params under stable keys the check body expects.
        ftype = function.function_type
        if ftype == "ospf":
            entry["ospf_pid"]  = p.get("process_id", "1")
            entry["router_id"] = p.get("router_id", "")
        elif ftype == "bgp":
            entry["bgp_as"]    = p.get("local_as", "")
        elif ftype == "eigrp":
            entry["eigrp_as"]  = p.get("as_number", "1")
        elif ftype == "snmp":
            entry["snmp_community"] = p.get("community", "")
        elif ftype == "staticroute":
            entry["static_routes"] = [
                {"prefix": r.get("prefix", ""), "mask": r.get("mask", "")}
                for r in p.get("routes", [])
            ]
        elif ftype == "loopback":
            entry["loopbacks"] = p.get("loopbacks", [])
        elif ftype in ("interface", "interfaces"):
            entry["check_interfaces"] = p.get("interfaces", [])
        elif ftype == "tunnel":
            entry["tunnel_ids"] = p.get("tunnel_ids", [])

        devices_with_params.append(entry)

    if not devices_with_params:
        return "# No devices with credentials found for this function\nimport sys; sys.exit(0)\n"

    # Build the header without textwrap.dedent — json.dumps output has lines
    # at column 0 (e.g. the closing ']') which would cause dedent to conclude
    # the common indent is 0 and strip nothing, leaving 'import sys' indented.
    devices_json = json.dumps(devices_with_params, indent=4)
    header = (
        f"# Auto-generated by pipeline_builder — "
        f"{function.function_type.upper()} verification\n"
        f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        "import sys\n"
        "try:\n"
        "    from netmiko import (\n"
        "        ConnectHandler, NetmikoTimeoutException,\n"
        "        NetmikoAuthenticationException,\n"
        "    )\n"
        "except ImportError:\n"
        "    print('netmiko not installed')\n"
        "    sys.exit(1)\n"
        "\n"
        f"DEVICES  = {devices_json}\n"
        "FAILURES = []\n"
        "\n"
        "def run_checks(conn, device):\n"
        "    hostname = device['hostname']\n"
    )

    footer = textwrap.dedent("""\

        for d in DEVICES:
            print(f"Checking {d['hostname']} ({d['ip']})...")
            dev = dict(device_type="cisco_ios", ip=d["ip"],
                       username=d["username"], password=d["password"])
            try:
                conn = ConnectHandler(**dev)
                conn.enable()
                result = run_checks(conn, d)
                conn.disconnect()
                if result:
                    print(f"  FAIL: {result}")
                    FAILURES.append(result)
                else:
                    print(f"  PASS")
            except NetmikoTimeoutException:
                msg = f"TIMEOUT connecting to {d['hostname']} ({d['ip']})"
                print(f"  FAIL: {msg}"); FAILURES.append(msg)
            except NetmikoAuthenticationException:
                msg = f"AUTH FAILED for {d['hostname']} ({d['ip']})"
                print(f"  FAIL: {msg}"); FAILURES.append(msg)
            except Exception as e:
                msg = f"ERROR on {d['hostname']}: {e}"
                print(f"  FAIL: {msg}"); FAILURES.append(msg)

        if FAILURES:
            print(f"\\n{len(FAILURES)} check(s) failed:")
            for f in FAILURES:
                print(f"  - {f}")
            sys.exit(1)
        print("\\nAll checks passed.")
        sys.exit(0)
        """)

    return header + textwrap.indent(body, "    ") + footer


# ---------------------------------------------------------------------------
# Jenkins pipeline XML generation (with cron schedule)
# ---------------------------------------------------------------------------

def _build_pipeline_xml(
    job_name:     str,
    function_type: str,
    list_slug:    str,
    cron:         str,
    description:  str = "",
) -> str:
    """
    Generate Jenkins config.xml for a persistent function verification pipeline.

    The pipeline calls ``modules\\check_runner.py`` directly — no Groovy string
    embedding, no writeFile, no escaping required.  All check logic lives in
    Python (modules/check_runner.py) and is versioned with the application code.
    """
    schedule_block = (
        f"<hudson.triggers.TimerTrigger><spec>{_sax.escape(cron)}</spec>"
        f"</hudson.triggers.TimerTrigger>"
        if cron else ""
    )

    groovy = textwrap.dedent(f"""\
        pipeline {{
            agent any
            options {{
                timeout(time: 15, unit: 'MINUTES')
                timestamps()
            }}
            stages {{
                stage('Install deps') {{
                    steps {{
                        bat 'pip install netmiko --quiet 2>NUL || echo netmiko already installed'
                    }}
                }}
                stage('Verify: {_sax.escape(function_type.upper())}') {{
                    steps {{
                        bat 'python modules\\\\check_runner.py --function {_sax.escape(function_type)} --list-slug {_sax.escape(list_slug)}'
                    }}
                }}
            }}
            post {{
                always {{ echo "Result: ${{currentBuild.currentResult}}" }}
                success {{ echo 'All {_sax.escape(job_name)} checks passed.' }}
                failure {{ echo '{_sax.escape(job_name)} verification FAILED.' }}
            }}
        }}
        """)

    return textwrap.dedent(f"""\
        <?xml version='1.1' encoding='UTF-8'?>
        <flow-definition plugin="workflow-job">
          <description>{_sax.escape(description or f"Auto-generated — {job_name}")}</description>
          <keepDependencies>false</keepDependencies>
          <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition"
                       plugin="workflow-cps">
            <script>{_sax.escape(groovy)}</script>
            <sandbox>true</sandbox>
          </definition>
          <triggers>{schedule_block}</triggers>
          <disabled>false</disabled>
        </flow-definition>
        """)


# ---------------------------------------------------------------------------
# Idempotent upsert — create or update one function pipeline
# ---------------------------------------------------------------------------

def ensure_function_pipeline(
    config_type:    str,
    newly_added_ips: list[str],
    params_by_ip:   dict[str, dict],
    jenkins_cfg:    dict,
    nmas_base:      str = "",
) -> dict:
    """
    Ensure a persistent verification pipeline exists for *config_type*.

    The pipeline XML calls ``modules\\check_runner.py`` — no device credentials
    are embedded in the XML.  The runner loads them at runtime from the
    encrypted device list.

    If the pipeline already exists it is updated in-place (newly configured
    devices are picked up automatically via golden config scan at run time).

    Returns a summary dict suitable for logging / returning to the caller.
    """
    from modules.config import list_slug as _list_slug, get_current_list_name
    from modules.jenkins_runner import (
        load_config as _jload, load_list_pipelines,
        create_jenkins_job, update_jenkins_job,
        register_pipeline, save_pipeline_schedule,
    )

    jenkins_url = jenkins_cfg.get("jenkins_url", "").rstrip("/")
    if not jenkins_url:
        return {"ok": False, "skipped": True, "reason": "Jenkins not configured"}

    try:
        list_name = get_current_list_name()
    except Exception:
        list_name = "default"

    slug     = _list_slug(list_name)
    function = NetworkFunction(
        function_type = config_type,
        device_ips    = newly_added_ips,
        params_by_ip  = params_by_ip,
    )

    # Device merging is no longer needed here — check_runner.py reads golden
    # configs at run time and finds all devices with the function configured.

    job_name     = function.job_name(slug)
    cron         = function.schedule()
    pipeline_xml = _build_pipeline_xml(
        job_name,
        function_type = config_type,
        list_slug     = slug,
        cron          = cron,
        description   = f"Auto-generated — {config_type.upper()} verification for {list_name}",
    )

    existing_jobs = load_list_pipelines()
    created = updated = False

    try:
        if job_name in existing_jobs:
            update_jenkins_job(jenkins_cfg, job_name, pipeline_xml)
            updated = True
            log.info("pipeline_builder: updated %s (%d device(s))",
                     job_name, len(function.device_ips))
        else:
            create_jenkins_job(jenkins_cfg, job_name, pipeline_xml)
            register_pipeline(job_name)
            save_pipeline_schedule(job_name, cron)
            created = True
            log.info("pipeline_builder: created %s (%d device(s), schedule=%s)",
                     job_name, len(function.device_ips), cron)
    except Exception as exc:
        log.error("pipeline_builder: failed to create/update %s: %s", job_name, exc)
        return {"ok": False, "job_name": job_name, "error": str(exc)}

    return {
        "ok":          True,
        "job_name":    job_name,
        "created":     created,
        "updated":     updated,
        "devices":     function.device_ips,
        "schedule":    cron,
        "config_type": config_type,
    }


# ---------------------------------------------------------------------------
# Bootstrap — scan golden configs and build all missing pipelines at once
# ---------------------------------------------------------------------------

def bootstrap_all_pipelines(
    check_devices: list[dict],   # used only for function detection; creds NOT embedded in XML
    jenkins_cfg:   dict,
    nmas_base:     str = "",
) -> dict:
    """
    Detect every network function active on the current list and ensure a
    verification pipeline exists for each one.

    Safe to call repeatedly — functions that already have a pipeline are
    updated (not duplicated), functions with no changes are skipped.
    """
    from modules.config import list_slug as _list_slug, get_current_list_name
    from modules.jenkins_runner import load_list_pipelines

    jenkins_url = jenkins_cfg.get("jenkins_url", "").rstrip("/")
    if not jenkins_url:
        return {
            "ok":      False,
            "skipped": True,
            "reason":  "Jenkins not configured",
            "created": [],
            "updated": [],
            "errors":  [],
        }

    try:
        list_name = get_current_list_name()
    except Exception:
        list_name = "default"

    functions    = detect_network_functions(check_devices)
    slug         = _list_slug(list_name)
    existing     = set(load_list_pipelines())

    created: list[str] = []
    updated: list[str] = []
    errors:  list[str] = []

    if not functions:
        log.info("pipeline_builder: bootstrap — no functions detected (no golden configs?)")
        return {
            "ok": True, "created": [], "updated": [], "errors": [],
            "message": "No network functions detected. Save golden configs first.",
        }

    for func in functions:
        job_name     = func.job_name(slug)
        cron         = func.schedule()
        pipeline_xml = _build_pipeline_xml(
            job_name,
            function_type = func.function_type,
            list_slug     = slug,
            cron          = cron,
            description   = f"Auto-generated — {func.function_type.upper()} verification for {list_name}",
        )

        try:
            from modules.jenkins_runner import (
                create_jenkins_job, update_jenkins_job,
                register_pipeline, save_pipeline_schedule,
            )
            if job_name in existing:
                update_jenkins_job(jenkins_cfg, job_name, pipeline_xml)
                updated.append(job_name)
                log.info("pipeline_builder: bootstrap updated %s", job_name)
            else:
                create_jenkins_job(jenkins_cfg, job_name, pipeline_xml)
                register_pipeline(job_name)
                save_pipeline_schedule(job_name, cron)
                created.append(job_name)
                log.info("pipeline_builder: bootstrap created %s (schedule=%s)", job_name, cron)
        except Exception as exc:
            errors.append(f"{job_name}: {exc}")
            log.error("pipeline_builder: bootstrap failed for %s: %s", job_name, exc)

    return {
        "ok":      not errors,
        "created": created,
        "updated": updated,
        "errors":  errors,
        "functions_detected": [f.function_type for f in functions],
    }
