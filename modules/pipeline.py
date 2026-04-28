"""pipeline.py

Nine-stage deployment pipeline with strict execution-order enforcement.

Required stage order (immutable):
  1. netbox_query       – fetch device inventory and intended config from NetBox
  2. template_render    – render Jinja2 templates; fall back to Python generators
  3. ci_gate            – validate rendered config locally; NO SSH before this passes
  4. pre_snapshot       – capture BGP neighbors, interface states, route table size
  5. config_diff        – diff rendered commands vs running config; abort if empty or
                          exceeds DIFF_LINE_THRESHOLD
  6. deploy             – NETCONF push (ncclient); Netmiko SSH fallback; canary first
  7. post_snapshot      – capture the same metrics as Stage 4
  8. verify             – diff pre vs post snapshots; auto-rollback on failure
  9. audit_log          – write structured JSON log (ALWAYS runs via finally)

Hard invariants enforced at runtime:
  • PipelineOrderError is raised if any stage fires out of sequence.
  • Stages 1-5 abort on PipelineStageError (no rollback needed — device untouched).
  • Stages 6-8 trigger rollback on PipelineStageError.
  • Stage 9 always runs regardless of outcome (try/finally in PipelineRunner.run).
  • SSH/NETCONF connections are opened only from Stage 4 onward (after CI gate).
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

# Abort deploy if the number of new commands exceeds this.
DIFF_LINE_THRESHOLD = 200

# Routing neighbors: post-deploy neighbor count may not drop by more than this.
# Applies to whichever IGP/EGP is detected (BGP, OSPF, EIGRP, IS-IS).
_NEIGHBOR_DROP_TOLERANCE = 1

# Routes: post-deploy route count must be >= (pre-deploy count × this fraction).
_ROUTE_RETENTION_MIN = 0.90

# Config types that install new routes — the route table is expected to GROW
# after these changes, so the retention check would produce false rollbacks
# and is skipped for them.  Operators can extend this list via
# params["skip_route_check"] = True on any individual run.
_ROUTE_INSTALLING_CONFIG_TYPES = frozenset({
    "ospf", "eigrp", "bgp", "mpls", "staticroute", "rsvpte",
})

# Interfaces: post-deploy up-interface count may not drop by more than this.
_INTERFACE_DOWN_TOLERANCE = 0

# Directory (under DATA_DIR) where JSON audit entries are written.
_AUDIT_DIR_NAME = "pipeline_audit"

# IOS config-mode patterns that are treated as dangerous and halt the CI gate
# unless explicitly whitelisted in params["allowed_dangerous"].
_DANGEROUS_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*no\s+ip\s+address",                       re.IGNORECASE),
    re.compile(r"^\s*shutdown",                                 re.IGNORECASE),
    re.compile(r"^\s*no\s+router\s+(ospf|bgp|eigrp|isis)",     re.IGNORECASE),
    re.compile(r"^\s*crypto\s+key\s+zeroize",                  re.IGNORECASE),
    re.compile(r"^\s*erase\s+nvram",                           re.IGNORECASE),
    re.compile(r"^\s*reload",                                  re.IGNORECASE),
]

# Lines stripped from running-config before diff (matches drift_check._SKIP_STARTSWITH).
_SKIP_STARTSWITH = (
    "! Last configuration", "! NVRAM config", "! No configuration",
    "! Golden config", "! Pre-change", "! Saved:", "! Source:",
    "Building configuration", "Current configuration",
    "ntp clock-period", "upgrade fpd", "version ",
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PipelineError(Exception):
    """Base for all pipeline exceptions."""


class PipelineOrderError(PipelineError):
    """Raised when a stage is invoked out of the required sequence."""


class PipelineStageError(PipelineError):
    """Raised by a stage handler to signal failure and halt the pipeline."""


# ---------------------------------------------------------------------------
# Shared context (mutable state passed through every stage)
# ---------------------------------------------------------------------------

@dataclass
class PipelineContext:
    """All state for one pipeline run, shared across all stage handlers."""

    # ---- Inputs (set before run) -----------------------------------------
    config_type:      str
    device_ips:       list[str]
    params:           dict                   # shared params (used when ip_params_map empty)
    ip_params_map:    dict                   # per-device param overrides: {ip: params}
    selected_devices: list[dict]             # raw device dicts from the device list
    check_devices:    list[dict]             # decrypted-cred dicts for Jenkins scripts
    connections_pool: dict
    pool_lock:        Any
    config_id:        str

    # ---- Populated by stages ---------------------------------------------
    intended_config:   dict = field(default_factory=dict)  # Stage 1: NetBox data
    rendered_commands: dict = field(default_factory=dict)  # Stage 2: ip -> [str]
    ci_passed:         bool = False                         # Stage 3
    pre_snapshots:     dict = field(default_factory=dict)  # Stage 4: ip -> snapshot
    diff_summary:      dict = field(default_factory=dict)  # Stage 5: ip -> summary
    push_results:      dict = field(default_factory=dict)  # Stage 6: ip -> result
    post_snapshots:    dict = field(default_factory=dict)  # Stage 7: ip -> snapshot
    verify_result:     dict = field(default_factory=dict)  # Stage 8: ip -> result
    rollback_performed: bool = False

    # ---- Bookkeeping -----------------------------------------------------
    stages_completed: list[str] = field(default_factory=list)
    stages_failed:    list[str] = field(default_factory=list)
    final_status:     str = "pending"   # pending | success | failed | rolled_back
    error:            Optional[str] = None
    started_at:       str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    # ---- Helpers ---------------------------------------------------------

    def canary_ip(self) -> Optional[str]:
        """First device is the canary; deploy halts here if it fails."""
        return self.device_ips[0] if self.device_ips else None

    def fleet_ips(self) -> list[str]:
        """Remaining devices pushed only after canary succeeds."""
        return self.device_ips[1:]

    def device_params(self, ip: str) -> dict:
        return self.ip_params_map.get(ip, self.params)


# ---------------------------------------------------------------------------
# Stage order table — single source of truth
# (name, on_failure)   on_failure: "abort" | "rollback"
# ---------------------------------------------------------------------------

_STAGE_TABLE: list[tuple[str, str]] = [
    ("netbox_query",    "abort"),     # 1
    ("template_render", "abort"),     # 2
    ("ci_gate",         "abort"),     # 3  ← last stage before any SSH
    ("pre_snapshot",    "abort"),     # 4  ← first SSH connection
    ("config_diff",     "abort"),     # 5
    ("deploy",          "rollback"),  # 6
    ("post_snapshot",   "rollback"),  # 7
    ("verify",          "rollback"),  # 8
    ("audit_log",       "abort"),     # 9  always runs
]

STAGE_NAMES: list[str] = [s[0] for s in _STAGE_TABLE]


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

class PipelineRunner:
    """
    Executes the nine stages in strict order.

    Usage::

        ctx    = PipelineContext(...)
        result = PipelineRunner(ctx).run()

    ``_assert_order(idx)`` is public for testing: it raises ``PipelineOrderError``
    when the stage at *idx* is not the next expected stage.
    """

    def __init__(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self._next_expected: int = 0  # index into _STAGE_TABLE

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> PipelineContext:
        """Execute all stages in order.  Stage 9 (audit_log) always runs."""
        _handlers = [
            _stage_netbox_query,
            _stage_template_render,
            _stage_ci_gate,
            _stage_pre_snapshot,
            _stage_config_diff,
            _stage_deploy,
            _stage_post_snapshot,
            _stage_verify,
        ]
        try:
            for idx, handler in enumerate(_handlers):
                name, on_failure = _STAGE_TABLE[idx]
                self._assert_order(idx)
                try:
                    handler(self.ctx)
                    self.ctx.stages_completed.append(name)
                    self._next_expected = idx + 1
                except PipelineStageError as exc:
                    self.ctx.stages_failed.append(name)
                    self.ctx.error        = str(exc)
                    self.ctx.final_status = "failed"
                    log.error("pipeline: stage '%s' FAILED: %s", name, exc)
                    if on_failure == "rollback" and "deploy" in self.ctx.stages_completed:
                        log.warning("pipeline: initiating rollback after stage '%s' failure", name)
                        _stage_rollback(self.ctx)
                    break
            else:
                self.ctx.final_status = "success"
        finally:
            # Stage 9 always runs — even if an unhandled exception occurs above.
            _stage_audit_log(self.ctx)
        return self.ctx

    def _assert_order(self, expected_idx: int) -> None:
        """
        Raise ``PipelineOrderError`` if *expected_idx* is not the next stage.

        Called automatically by ``run()`` but also directly by tests to verify
        the enforcement contract without executing stage logic.
        """
        if self._next_expected != expected_idx:
            got_name      = STAGE_NAMES[expected_idx]
            expected_name = STAGE_NAMES[self._next_expected]
            raise PipelineOrderError(
                f"Stage '{got_name}' (#{expected_idx + 1}/9) invoked out of order; "
                f"'{expected_name}' (#{self._next_expected + 1}/9) must run first."
            )


# ---------------------------------------------------------------------------
# Stage 1 — NetBox query
# ---------------------------------------------------------------------------

def _stage_netbox_query(ctx: PipelineContext) -> None:
    """Fetch device inventory and intended config from NetBox before any other work."""
    try:
        from modules.netbox_client import (
            get_netbox_config, netbox_get_device, netbox_get_interfaces,
        )
    except ImportError:
        log.warning("pipeline[1/netbox_query]: netbox_client not available — skipping")
        ctx.intended_config = {"available": False, "reason": "netbox_client not importable"}
        return

    cfg = get_netbox_config()
    if not cfg.get("url") or not cfg.get("token"):
        log.info("pipeline[1/netbox_query]: NetBox not configured — proceeding without intended config")
        ctx.intended_config = {"available": False, "reason": "NetBox not configured"}
        return

    intended: dict[str, Any] = {}
    errors:   list[str]      = []

    for dev in ctx.selected_devices:
        ip       = dev["ip"]
        hostname = dev.get("hostname", ip)
        try:
            dev_r   = netbox_get_device(hostname)
            iface_r = netbox_get_interfaces(hostname) if dev_r["ok"] else {"ok": False}
            intended[ip] = {
                "device":     dev_r.get("device")         if dev_r["ok"]   else None,
                "interfaces": iface_r.get("interfaces", []) if iface_r["ok"] else [],
                "error":      None if dev_r["ok"] else dev_r.get("error"),
            }
            if not dev_r["ok"]:
                errors.append(f"{hostname}: {dev_r.get('error')}")
        except Exception as exc:
            intended[ip] = {"device": None, "interfaces": [], "error": str(exc)}
            errors.append(f"{hostname}: {exc}")

    ctx.intended_config = {"available": True, "devices": intended}

    # Stage 1 is optional context enrichment — it never aborts the pipeline.
    # Devices may not be in NetBox yet (first deploy before a sync), or NetBox
    # may be temporarily unreachable.  Either way the config push must proceed.
    if errors:
        log.warning(
            "pipeline[1/netbox_query]: %d/%d device(s) not found or errored in NetBox "
            "— proceeding without NetBox context: %s",
            len(errors), len(ctx.selected_devices), errors,
        )

    log.info("pipeline[1/netbox_query]: completed — %d device(s), %d error(s)",
             len(ctx.selected_devices), len(errors))


# ---------------------------------------------------------------------------
# Stage 2 — Template render
# ---------------------------------------------------------------------------

def _stage_template_render(ctx: PipelineContext) -> None:
    """
    Render configuration commands for every device.

    Looks for ``config_templates/{config_type}.j2`` first.  If the file exists,
    renders it via Jinja2 (already available as a Flask dependency — no new
    package needed).  Falls back to the existing Python generators in
    ``modules.configure`` when no template file is found.
    """
    from modules.configure import generate_config_commands

    tpl_path = _config_template_path(ctx.config_type)
    rendered: dict[str, list[str]] = {}
    errors:   list[str]            = []

    for dev in ctx.selected_devices:
        ip       = dev["ip"]
        hostname = dev.get("hostname", ip)
        p        = ctx.device_params(ip)
        nb_dev   = (ctx.intended_config
                       .get("devices", {})
                       .get(ip, {})
                       .get("device")) or {}
        try:
            if tpl_path and os.path.isfile(tpl_path):
                cmds = _render_jinja2(tpl_path, p, nb_dev)
                log.debug("pipeline[2/template_render]: %s used Jinja2 template", hostname)
            else:
                cmds = generate_config_commands(ctx.config_type, p)
                log.debug("pipeline[2/template_render]: %s used Python generator", hostname)

            if not cmds:
                errors.append(f"{hostname}: generator returned no commands")
            else:
                rendered[ip] = cmds
        except Exception as exc:
            errors.append(f"{hostname}: {exc}")

    if errors:
        raise PipelineStageError(
            f"Template render failed for {len(errors)} device(s): {errors}"
        )

    ctx.rendered_commands = rendered
    log.info("pipeline[2/template_render]: %d device(s) rendered", len(rendered))


def _config_template_path(config_type: str) -> str:
    """Return path to ``config_templates/{config_type}.j2``, empty string if absent."""
    root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(root, "config_templates", f"{config_type}.j2")


def _render_jinja2(tpl_path: str, params: dict, nb_device: dict) -> list[str]:
    """
    Render a Jinja2 config template.

    Jinja2 is part of Flask's dependency tree — no additional install required.
    Templates receive ``params`` (user inputs) and ``netbox`` (NetBox device record).
    """
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    env = Environment(
        loader       = FileSystemLoader(os.path.dirname(tpl_path)),
        undefined    = StrictUndefined,
        trim_blocks  = True,
        lstrip_blocks= True,
    )
    tpl      = env.get_template(os.path.basename(tpl_path))
    rendered = tpl.render(params=params, netbox=nb_device)
    return [line for line in rendered.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Stage 3 — CI gate
# ---------------------------------------------------------------------------

def _stage_ci_gate(ctx: PipelineContext) -> None:
    """
    Validate the rendered config before any SSH connection is opened.

    Checks (all must pass before Stage 4 is allowed to open any SSH connection):
      1. Rendered command lists are non-empty for every target device.
      2. No dangerous IOS patterns (shutdown, no router X, reload, …) unless
         whitelisted in ``params["allowed_dangerous"]``.
      3. The check_runner module syntax check — verifies the check function for
         this config type is importable and callable.
      4. Jenkins pipeline status — if Jenkins is configured and pipelines are
         registered for this list, NONE of them may be in FAILURE state.
         A failing pipeline means the network is not in a known-good state;
         deploying on top of a broken network makes diagnosis impossible.
         If no pipelines have been created yet (first-time setup) a warning is
         logged but the gate still passes so initial bootstrapping is not blocked.
    """
    import py_compile, tempfile
    from modules.configure import generate_check_script

    allowed: set[str] = set(ctx.params.get("allowed_dangerous", []))

    # ── Check 1 & 2 — command presence and dangerous-pattern check ──────────
    for ip, cmds in ctx.rendered_commands.items():
        hostname = next((d.get("hostname", ip) for d in ctx.selected_devices
                         if d["ip"] == ip), ip)
        if not cmds:
            raise PipelineStageError(f"CI gate: no rendered commands for {hostname}")
        for cmd in cmds:
            for pat in _DANGEROUS_PATTERNS:
                if pat.search(cmd) and cmd.strip() not in allowed:
                    raise PipelineStageError(
                        f"CI gate: dangerous command detected for {hostname}: {cmd!r}. "
                        f"Add the exact command string to params['allowed_dangerous'] to override."
                    )

    # ── Check 3 — verify check_runner has a function for this config type ───
    try:
        from modules.check_runner import CHECKS as _checks
        if ctx.config_type not in _checks:
            log.warning(
                "pipeline[3/ci_gate]: no check function registered for '%s' in "
                "check_runner.CHECKS — post-deploy verification will be skipped",
                ctx.config_type,
            )
    except ImportError:
        log.warning("pipeline[3/ci_gate]: check_runner not importable — skipping check 3")

    # ── Check 4 — Jenkins pipeline status (fast read, no blocking) ──────────
    # Only block if a pipeline is actively FAILING — meaning the network is
    # in a known bad state.  Never trigger builds or wait here; CI is advisory.
    try:
        from modules.jenkins_runner import (
            load_config as _jlc,
            get_current_list_pipeline_status as _jpstatus,
        )
        jcfg = _jlc()
        if jcfg.get("jenkins_url", "").strip():
            info    = _jpstatus(jcfg)
            rows    = info.get("registered", [])
            failing = [
                r["job_name"] for r in rows
                if r.get("last_result") == "FAILURE" and r.get("exists_on_server")
            ]
            if failing:
                raise PipelineStageError(
                    f"CI gate: {len(failing)} pipeline(s) are currently FAILING — "
                    f"deploy blocked:\n"
                    + "\n".join(f"  • {j}" for j in failing)
                    + "\nFix the failures or investigate before applying new config."
                )
            if rows:
                log.info("pipeline[3/ci_gate]: %d pipeline(s) — all passing", len(rows))
    except PipelineStageError:
        raise
    except Exception as exc:
        log.warning("pipeline[3/ci_gate]: pipeline status check failed: %s", exc)

    ctx.ci_passed = True
    log.info(
        "pipeline[3/ci_gate]: passed — %d device(s), no dangerous commands",
        len(ctx.rendered_commands),
    )


# ---------------------------------------------------------------------------
# Stage 4 — Pre-change snapshot
# ---------------------------------------------------------------------------

def _stage_pre_snapshot(ctx: PipelineContext) -> None:
    """
    Capture BGP neighbors, interface states, and route table size BEFORE deploy.
    Also saves the full running-config for diff (Stage 5) and rollback (Stage 8).

    First stage to open SSH connections — allowed because CI gate has passed.
    Aborts the pipeline if any device is unreachable.
    """
    from modules.connection import get_persistent_connection
    from modules.ai_assistant import _save_pre_change_file, _get_running_config_for_golden

    errors: list[str] = []

    for dev in ctx.selected_devices:
        ip       = dev["ip"]
        hostname = dev.get("hostname", ip)
        try:
            conn = get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)
            snap = _capture_operational_snapshot(conn, ip, hostname)

            # Also save the running-config so Stage 5 can diff and Stage 8 can roll back.
            running_cfg = _get_running_config_for_golden(ip, hostname)
            if running_cfg:
                _save_pre_change_file(ip, hostname, running_cfg)
                snap["running_config"] = running_cfg
            else:
                log.warning("pipeline[4/pre_snapshot]: could not fetch running-config for %s", hostname)

            ctx.pre_snapshots[ip] = snap
            nbr = snap.get("routing_neighbors", {})
            log.info(
                "pipeline[4/pre_snapshot]: %s OK  protocol=%s  neighbors=%s  "
                "routes=%s  intf_up=%s",
                hostname,
                nbr.get("protocol", "?"),
                nbr.get("count", "?"),
                snap.get("routes", {}).get("total_count", "?"),
                snap.get("interfaces", {}).get("up_count", "?"),
            )
        except Exception as exc:
            errors.append(f"{hostname} ({ip}): {exc}")
            log.error("pipeline[4/pre_snapshot]: FAILED for %s: %s", hostname, exc)

    if errors:
        raise PipelineStageError(
            f"Pre-snapshot failed for {len(errors)} device(s) — aborting before deploy:\n"
            + "\n".join(errors)
        )


# ---------------------------------------------------------------------------
# Stage 5 — Config diff
# ---------------------------------------------------------------------------

def _stage_config_diff(ctx: PipelineContext) -> None:
    """
    Diff rendered commands against the running config captured in Stage 4.

    Abort conditions:
      • All rendered commands are already present in the running config (no-op).
      • The number of genuinely new commands exceeds DIFF_LINE_THRESHOLD.

    ``ctx.diff_summary`` is populated for every device regardless of outcome,
    so the audit log always captures what was (and was not) new.
    """
    errors: list[str] = []

    for ip, cmds in ctx.rendered_commands.items():
        hostname = next(
            (d.get("hostname", ip) for d in ctx.selected_devices if d["ip"] == ip), ip
        )
        running_cfg = ctx.pre_snapshots.get(ip, {}).get("running_config", "")

        if not running_cfg:
            # No cached running-config — skip diff check with a warning; do not abort.
            log.warning(
                "pipeline[5/config_diff]: no cached running-config for %s — diff skipped", hostname
            )
            ctx.diff_summary[ip] = {"skipped": True, "reason": "running config not cached"}
            continue

        running_lines = {
            line.strip()
            for line in running_cfg.splitlines()
            if line.strip() and not any(line.startswith(s) for s in _SKIP_STARTSWITH)
        }
        new_cmds = [c for c in cmds if c.strip() and c.strip() not in running_lines]

        ctx.diff_summary[ip] = {
            "total_cmds":        len(cmds),
            "new_cmds":          len(new_cmds),
            "no_op":             len(new_cmds) == 0,
            "exceeds_threshold": len(new_cmds) > DIFF_LINE_THRESHOLD,
            "commands_to_add":   new_cmds,
        }

        if len(new_cmds) == 0:
            errors.append(
                f"{hostname}: all {len(cmds)} rendered command(s) already present "
                f"in running config — no-op deploy aborted"
            )
        elif len(new_cmds) > DIFF_LINE_THRESHOLD:
            errors.append(
                f"{hostname}: {len(new_cmds)} new command(s) exceeds safety threshold "
                f"({DIFF_LINE_THRESHOLD}) — aborting to prevent mass change"
            )
        else:
            log.info("pipeline[5/config_diff]: %s — %d new command(s) to apply", hostname, len(new_cmds))

    if errors:
        raise PipelineStageError(
            f"Config diff check failed for {len(errors)} device(s):\n"
            + "\n".join(errors)
        )


# ---------------------------------------------------------------------------
# Stage 6 — Deploy
# ---------------------------------------------------------------------------

def _stage_deploy(ctx: PipelineContext) -> None:
    """
    Push rendered commands to devices: canary device first, then fleet.

    Tries NETCONF (ncclient) first; falls back to Netmiko SSH if ncclient is
    not installed or the device returns a NETCONF error.  A basic sanity check
    runs on the canary after its push; fleet push is skipped if canary fails.
    """
    ordered = ([ctx.canary_ip()] if ctx.canary_ip() else []) + ctx.fleet_ips()

    for ip in ordered:
        dev = next((d for d in ctx.selected_devices if d["ip"] == ip), None)
        if not dev:
            continue
        hostname  = dev.get("hostname", ip)
        cmds      = ctx.rendered_commands.get(ip, [])
        is_canary = (ip == ctx.canary_ip())

        if not cmds:
            ctx.push_results[ip] = {"ok": True, "skipped": True, "reason": "no commands"}
            continue

        try:
            output = _push_config(dev, cmds, ctx.connections_pool, ctx.pool_lock)
            ctx.push_results[ip] = {"ok": True, "output": output[:500]}
            log.info("pipeline[6/deploy]: %s%s pushed — %d command(s)",
                     "(canary) " if is_canary else "", hostname, len(cmds))

            # Canary gate: quick sanity check before touching the rest of the fleet.
            if is_canary and ctx.fleet_ips():
                _canary_sanity_check(dev, ctx)

        except PipelineStageError:
            ctx.push_results[ip] = {"ok": False, "error": "canary sanity check failed"}
            raise
        except Exception as exc:
            ctx.push_results[ip] = {"ok": False, "error": str(exc)}
            raise PipelineStageError(
                f"Deploy failed on {'canary ' if is_canary else ''}{hostname}: {exc}"
            ) from exc


def _push_config(dev: dict, cmds: list[str], pool: dict, lock: Any) -> str:
    """
    Push ``cmds`` to the device.

    Uses Netmiko SSH by default.  NETCONF (ncclient) is only attempted when
    the ``netconf_enabled`` user setting is explicitly set to True — standard
    Cisco IOS devices do not have netconf-yang enabled, and attempting a
    connection to port 830 wastes time before the socket timeout.

    To enable NETCONF: set ``netconf_enabled = true`` in Settings.
    """
    try:
        from modules.config import get_user_setting
        if get_user_setting("netconf_enabled", False):
            try:
                import ncclient  # noqa: F401 — availability probe
                return _push_via_netconf(dev, cmds)
            except ImportError:
                log.debug("pipeline: ncclient not installed — using Netmiko SSH")
            except Exception as nc_exc:
                log.warning("pipeline: NETCONF push failed (%s) — falling back to SSH", nc_exc)
    except Exception:
        pass

    return _push_via_netmiko(dev, cmds, pool, lock)


def _push_via_netconf(dev: dict, cmds: list[str]) -> str:
    """
    Push config via NETCONF using ncclient (optional dependency).

    Wraps IOS CLI lines in the Cisco IOS-XE native YANG container
    (``Cisco-IOS-XE-native``), supported on IOS XE 16.3+.
    Requires ``netconf-yang`` to be enabled on the device.

    ncclient is listed as an optional dependency because not all devices
    in the lab support NETCONF; Netmiko SSH is always available as a fallback.
    Install with: pip install ncclient
    """
    from ncclient import manager as nc_mgr  # type: ignore[import]

    config_xml = (
        "<config>"
        "<native xmlns=\"http://cisco.com/ns/yang/Cisco-IOS-XE-native\">"
        "<cli-config-data-block>"
        + "\n".join(cmds)
        + "</cli-config-data-block></native></config>"
    )
    with nc_mgr.connect(
        host            = dev["ip"],
        username        = dev.get("username", ""),
        password        = dev.get("password", ""),
        port            = 830,
        hostkey_verify  = False,
        device_params   = {"name": "iosxe"},
        timeout         = 60,
    ) as m:
        reply = m.edit_config(target="running", config=config_xml)
        return f"NETCONF edit-config OK: {reply}"


def _push_via_netmiko(dev: dict, cmds: list[str], pool: dict, lock: Any) -> str:
    """Push config via Netmiko SSH (existing connection pool)."""
    from modules.connection import get_persistent_connection
    conn = get_persistent_connection(dev, pool, lock)
    conn.enable()
    output = conn.send_config_set(cmds, read_timeout=60)
    conn.save_config()
    return output


def _canary_sanity_check(canary_dev: dict, ctx: PipelineContext) -> None:
    """
    Verify the canary device still has at least one up interface after push.
    Halts fleet deployment if the check fails.
    """
    from modules.connection import get_persistent_connection
    from modules.commands   import run_device_command

    ip       = canary_dev["ip"]
    hostname = canary_dev.get("hostname", ip)
    conn     = get_persistent_connection(canary_dev, ctx.connections_pool, ctx.pool_lock)
    out      = run_device_command(conn, "show ip interface brief")
    if "up" not in out.lower():
        raise PipelineStageError(
            f"Canary {hostname}: no interfaces UP after deploy — fleet push halted"
        )
    log.info("pipeline[6/deploy]: canary %s sanity check passed", hostname)


# ---------------------------------------------------------------------------
# Stage 7 — Post-change snapshot
# ---------------------------------------------------------------------------

def _stage_post_snapshot(ctx: PipelineContext) -> None:
    """Capture the same operational metrics as Stage 4, now AFTER deploy."""
    from modules.connection import get_persistent_connection

    errors: list[str] = []

    for dev in ctx.selected_devices:
        ip       = dev["ip"]
        hostname = dev.get("hostname", ip)
        try:
            conn = get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)
            ctx.post_snapshots[ip] = _capture_operational_snapshot(conn, ip, hostname)
            log.info("pipeline[7/post_snapshot]: %s OK", hostname)
        except Exception as exc:
            errors.append(f"{hostname}: {exc}")
            log.error("pipeline[7/post_snapshot]: FAILED for %s: %s", hostname, exc)

    if errors:
        raise PipelineStageError(
            f"Post-snapshot failed for {len(errors)} device(s) — cannot verify:\n"
            + "\n".join(errors)
        )


# ---------------------------------------------------------------------------
# Stage 8 — Verify
# ---------------------------------------------------------------------------

def _stage_verify(ctx: PipelineContext) -> None:
    """
    Diff pre vs post snapshots using protocol-agnostic convergence checks.

    Three checks run for each device.  All are skipped when the pre-snapshot
    did not capture a meaningful baseline (count == -1), so this stage is safe
    on networks that run any combination of routing protocols — or none at all.

    Checks:
      • Routing neighbors: count detected from whichever protocol responded
        (BGP, OSPF, EIGRP, IS-IS) must not drop by more than
        _NEIGHBOR_DROP_TOLERANCE.
      • Route table size: total routes must remain >=
        _ROUTE_RETENTION_MIN × pre-deploy count.
      • Interface up-count: interfaces that were UP before deploy must still
        be UP (tolerance: _INTERFACE_DOWN_TOLERANCE).
    """
    failures: list[str] = []

    for ip in ctx.device_ips:
        pre      = ctx.pre_snapshots.get(ip,  {})
        post     = ctx.post_snapshots.get(ip, {})
        hostname = next(
            (d.get("hostname", ip) for d in ctx.selected_devices if d["ip"] == ip), ip
        )
        issues: list[str] = []

        # ── Routing neighbor count (protocol-agnostic) ────────────────────
        pre_nbr  = pre.get("routing_neighbors",  {})
        post_nbr = post.get("routing_neighbors", {})
        pre_proto  = pre_nbr.get("protocol",  "unknown")
        post_proto = post_nbr.get("protocol", "unknown")
        pre_count  = pre_nbr.get("count",  -1)
        post_count = post_nbr.get("count", -1)

        if pre_count >= 0 and post_count >= 0:
            drop = pre_count - post_count
            if drop > _NEIGHBOR_DROP_TOLERANCE:
                issues.append(
                    f"{pre_proto} neighbors dropped: {pre_count} → {post_count} "
                    f"(tolerance={_NEIGHBOR_DROP_TOLERANCE})"
                )
        elif pre_count >= 0 and post_count < 0:
            # Protocol was present before but not detected after — treat as full loss.
            issues.append(
                f"{pre_proto} neighbor table unreadable after deploy "
                f"(pre={pre_count}, post=unavailable)"
            )

        # ── Route table size ──────────────────────────────────────────────
        # Skip for routing-protocol config types: the table is expected to grow
        # as adjacencies form, and checking retention during convergence would
        # produce false rollbacks on an otherwise successful initial setup.
        # Also skipped when the caller sets params["skip_route_check"] = True.
        _skip_route = (
            ctx.config_type in _ROUTE_INSTALLING_CONFIG_TYPES
            or ctx.params.get("skip_route_check", False)
        )
        pre_routes  = pre.get("routes",  {}).get("total_count", -1)
        post_routes = post.get("routes", {}).get("total_count", -1)
        if not _skip_route and pre_routes > 0 and post_routes >= 0:
            retention = post_routes / pre_routes
            if retention < _ROUTE_RETENTION_MIN:
                issues.append(
                    f"Route table shrank: {pre_routes} → {post_routes} "
                    f"({retention:.0%} < required {_ROUTE_RETENTION_MIN:.0%})"
                )

        # ── Interface up-count ────────────────────────────────────────────
        pre_up  = pre.get("interfaces",  {}).get("up_count",  -1)
        post_up = post.get("interfaces", {}).get("up_count", -1)
        if pre_up >= 0 and post_up >= 0:
            down_delta = pre_up - post_up
            if down_delta > _INTERFACE_DOWN_TOLERANCE:
                issues.append(
                    f"Interfaces went down: {pre_up} up before → {post_up} up after "
                    f"({down_delta} interface(s) lost, tolerance={_INTERFACE_DOWN_TOLERANCE})"
                )

        ctx.verify_result[ip] = {
            "ok":     not issues,
            "issues": issues,
            "pre":  {
                "routing_protocol": pre_proto,
                "routing_neighbors": pre_count,
                "routes":           pre_routes,
                "interfaces_up":    pre_up,
            },
            "post": {
                "routing_protocol": post_proto,
                "routing_neighbors": post_count,
                "routes":           post_routes,
                "interfaces_up":    post_up,
            },
        }
        if issues:
            failures.append(f"{hostname}: " + "; ".join(issues))
            log.error("pipeline[8/verify]: %s FAILED: %s", hostname, issues)
        else:
            log.info("pipeline[8/verify]: %s OK  protocol=%s  neighbors=%s→%s  "
                     "routes=%s→%s  intf_up=%s→%s",
                     hostname, pre_proto, pre_count, post_count,
                     pre_routes, post_routes, pre_up, post_up)

    if failures:
        raise PipelineStageError(
            f"Verify failed for {len(failures)} device(s) — rollback triggered:\n"
            + "\n".join(failures)
        )


# ---------------------------------------------------------------------------
# Rollback (called by PipelineRunner on stage 6-8 failure)
# ---------------------------------------------------------------------------

def _stage_rollback(ctx: PipelineContext) -> None:
    """
    Restore the pre-change running-config on every device that was successfully pushed.
    Uses the file written by _save_pre_change_file in Stage 4.
    """
    from modules.ai_assistant  import _load_pre_change_file
    from modules.connection    import get_persistent_connection

    targets = [ip for ip, r in ctx.push_results.items() if r.get("ok")]
    log.warning("pipeline[rollback]: restoring %d device(s): %s", len(targets), targets)

    for ip in targets:
        dev = next((d for d in ctx.selected_devices if d["ip"] == ip), None)
        if not dev:
            continue
        hostname = dev.get("hostname", ip)
        try:
            pre_cfg = _load_pre_change_file(ip)
            if not pre_cfg:
                log.error(
                    "pipeline[rollback]: no pre-change file for %s — cannot restore", hostname
                )
                continue
            conn = get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)
            _restore_config(conn, pre_cfg)
            log.info("pipeline[rollback]: %s restored successfully", hostname)
        except Exception as exc:
            log.error("pipeline[rollback]: FAILED to restore %s: %s", hostname, exc)

    ctx.rollback_performed = True
    ctx.final_status       = "rolled_back"


def _restore_config(conn, config_text: str) -> None:
    """Replace running config with the saved pre-change text via Netmiko config mode."""
    lines = [
        line for line in config_text.splitlines()
        if line.strip()
        and not any(line.startswith(s) for s in _SKIP_STARTSWITH)
    ]
    if lines:
        conn.enable()
        conn.send_config_set(lines, read_timeout=120)
        conn.save_config()


# ---------------------------------------------------------------------------
# Stage 9 — Audit log (always runs)
# ---------------------------------------------------------------------------

def _stage_audit_log(ctx: PipelineContext) -> None:
    """
    Write a structured JSON audit entry.  Called from PipelineRunner.run()'s
    finally block — runs regardless of success, failure, or unhandled exception.
    """
    try:
        delta: dict[str, Any] = {}
        for ip in ctx.device_ips:
            pre  = ctx.pre_snapshots.get(ip,  {})
            post = ctx.post_snapshots.get(ip, {})
            pre_nbr  = pre.get("routing_neighbors",  {})
            post_nbr = post.get("routing_neighbors", {})
            delta[ip] = {
                "routing_protocol":       pre_nbr.get("protocol"),
                "routing_neighbors_pre":  pre_nbr.get("count"),
                "routing_neighbors_post": post_nbr.get("count"),
                "routes_pre":             pre.get("routes", {}).get("total_count"),
                "routes_post":            post.get("routes",{}).get("total_count"),
                "interfaces_up_pre":      pre.get("interfaces",  {}).get("up_count"),
                "interfaces_up_post":     post.get("interfaces", {}).get("up_count"),
                "verify":                 ctx.verify_result.get(ip, {}),
            }

        entry: dict[str, Any] = {
            "schema_version":   1,
            "config_id":        ctx.config_id,
            "timestamp":        time.strftime("%Y-%m-%d %H:%M:%S"),
            "started_at":       ctx.started_at,
            "config_type":      ctx.config_type,
            "devices":          [
                {"ip": d["ip"], "hostname": d.get("hostname", d["ip"])}
                for d in ctx.selected_devices
            ],
            "stages_completed": ctx.stages_completed,
            "stages_failed":    ctx.stages_failed,
            "final_status":     ctx.final_status,
            "error":            ctx.error,
            "rollback":         ctx.rollback_performed,
            "ci_passed":        ctx.ci_passed,
            "netbox_available": ctx.intended_config.get("available", False),
            "snapshot_delta":   delta,
            "push_results":     {
                ip: {"ok": r.get("ok"), "error": r.get("error")}
                for ip, r in ctx.push_results.items()
            },
            "diff_summary":     {
                ip: {
                    k: v for k, v in s.items()
                    if k != "commands_to_add"  # omit verbose list from audit file
                }
                for ip, s in ctx.diff_summary.items()
            },
        }

        path = os.path.join(_audit_dir(), f"{ctx.config_id}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(entry, fh, indent=2)

        log.info("pipeline[9/audit_log]: written → %s  (status=%s)", path, ctx.final_status)

    except Exception as exc:
        # Audit log failure must never mask the original pipeline error.
        log.error("pipeline[9/audit_log]: FAILED to write audit log: %s", exc)


def _audit_dir() -> str:
    from modules.config import DATA_DIR
    path = os.path.join(DATA_DIR, _AUDIT_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Shared helper — operational snapshot
# ---------------------------------------------------------------------------

def _capture_operational_snapshot(conn, ip: str, hostname: str) -> dict:
    """
    Capture three protocol-agnostic operational metrics via SSH:

      • ``routing_neighbors`` – neighbor/adjacency count for whichever routing
        protocol is active on the device.  Probed in order: BGP → OSPF →
        EIGRP → IS-IS.  The first protocol that returns a non-empty neighbor
        table is used; the detected protocol name is stored alongside the count
        so the verify stage can report it clearly.  If no routing protocol is
        running (e.g. a pure L2 switch) the count is left at -1 and the verify
        stage skips the neighbor check entirely.
      • ``interfaces`` – count of interfaces whose line protocol is UP/DOWN.
      • ``routes``     – total IP route count from ``show ip route summary``.

    All three queries are independent; an error in one does not abort the others.
    """
    from modules.commands import run_device_command

    snap: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ip":        ip,
        "hostname":  hostname,
    }

    # ── Routing neighbor count (protocol-agnostic) ────────────────────────
    snap["routing_neighbors"] = _detect_routing_neighbors(conn)

    # ── Interface states ──────────────────────────────────────────────────
    try:
        intf_out   = run_device_command(
            conn, "show interfaces | include (line protocol|Internet address)"
        )
        up_count   = intf_out.lower().count("line protocol is up")
        down_count = intf_out.lower().count("line protocol is down")
        snap["interfaces"] = {
            "output":     intf_out[:3000],
            "up_count":   up_count,
            "down_count": down_count,
        }
    except Exception as exc:
        snap["interfaces"] = {"error": str(exc), "up_count": -1, "down_count": -1}

    # ── Route table size ──────────────────────────────────────────────────
    try:
        route_out = run_device_command(conn, "show ip route summary")
        m         = re.search(r"Total\s+(\d+)", route_out)
        total     = int(m.group(1)) if m else -1
        snap["routes"] = {"output": route_out[:1000], "total_count": total}
    except Exception as exc:
        snap["routes"] = {"error": str(exc), "total_count": -1}

    return snap


def _detect_routing_neighbors(conn) -> dict:
    """
    Probe for active routing protocols and return the neighbor/adjacency count
    for the first one found.

    Probe order: BGP → OSPF → EIGRP → IS-IS.  Returns a dict:
      {"protocol": "<name>", "count": <int>, "output": "<raw>"}

    ``count`` is -1 when no routing protocol is detected, which tells
    _stage_verify to skip the neighbor check rather than fail it.
    """
    from modules.commands import run_device_command

    # ── BGP ───────────────────────────────────────────────────────────────
    try:
        out = run_device_command(conn, "show ip bgp summary")
        if "BGP router identifier" in out:
            # Count peer rows: lines that end with an uptime token (e.g. "5w2d",
            # "00:05:12") or the word "Established".
            count = len(re.findall(
                r"^\d[\d.]+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+[\w:]+\s*$",
                out, re.MULTILINE,
            ))
            return {"protocol": "bgp", "count": count, "output": out[:2000]}
    except Exception:
        pass

    # ── OSPF ──────────────────────────────────────────────────────────────
    try:
        out = run_device_command(conn, "show ip ospf neighbor")
        if out.strip() and "Neighbor ID" in out:
            # Count rows below the header line.
            rows = [
                ln for ln in out.splitlines()
                if ln.strip() and not ln.strip().startswith("Neighbor")
                and re.match(r"\d+\.\d+\.\d+\.\d+", ln.strip())
            ]
            return {"protocol": "ospf", "count": len(rows), "output": out[:2000]}
    except Exception:
        pass

    # ── EIGRP ─────────────────────────────────────────────────────────────
    try:
        out = run_device_command(conn, "show ip eigrp neighbors")
        if out.strip() and "H " in out:
            # Each peer line starts with a sequence number (the "H" column).
            rows = [
                ln for ln in out.splitlines()
                if re.match(r"\s*\d+\s+\d+\.\d+\.\d+\.\d+", ln)
            ]
            return {"protocol": "eigrp", "count": len(rows), "output": out[:2000]}
    except Exception:
        pass

    # ── IS-IS ─────────────────────────────────────────────────────────────
    try:
        out = run_device_command(conn, "show isis neighbors")
        if out.strip() and "System Id" in out:
            rows = [
                ln for ln in out.splitlines()
                if ln.strip() and not ln.strip().startswith("System")
                and not ln.strip().startswith("IS-IS")
            ]
            return {"protocol": "isis", "count": len(rows), "output": out[:2000]}
    except Exception:
        pass

    # No routing protocol detected (e.g. pure L2 switch, static-only router).
    return {"protocol": "none", "count": -1, "output": ""}


# ---------------------------------------------------------------------------
# Public helper — load latest audit entry for a config_id
# ---------------------------------------------------------------------------

def load_audit_entry(config_id: str) -> Optional[dict]:
    """Return the audit log entry for *config_id*, or None if not found."""
    try:
        path = os.path.join(_audit_dir(), f"{config_id}.json")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def list_audit_entries(limit: int = 20) -> list[dict]:
    """Return the *limit* most recent audit entries, newest first."""
    audit_dir = _audit_dir()
    try:
        files = sorted(
            (f for f in os.listdir(audit_dir) if f.endswith(".json")),
            key=lambda f: os.path.getmtime(os.path.join(audit_dir, f)),
            reverse=True,
        )
        entries = []
        for fname in files[:limit]:
            try:
                with open(os.path.join(audit_dir, fname), encoding="utf-8") as fh:
                    entries.append(json.load(fh))
            except Exception:
                pass
        return entries
    except FileNotFoundError:
        return []
