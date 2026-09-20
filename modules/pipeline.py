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


class ConfirmedCommandsOverwritten(PipelineError):
    """Something tried to render a substitute for a confirmed command list."""


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
    #: Set by a caller that has already decided the exact commands to send —
    #: the NSoT deploy path, where the operator confirmed this exact list.
    #: ``None`` means "nobody has decided yet, stage 2 should render".
    #: A non-None value makes :attr:`rendered_commands` *derive* from it, so
    #: stage 2 cannot overwrite the confirmed list even by assigning to it.
    confirmed_commands: dict = None
    #: Stage 2's own output. Reached only when nothing was confirmed.
    _rendered: dict = field(default_factory=dict, init=False, repr=False)
    ci_passed:         bool = False                         # Stage 3
    pre_snapshots:     dict = field(default_factory=dict)  # Stage 4: ip -> snapshot
    diff_summary:      dict = field(default_factory=dict)  # Stage 5: ip -> summary
    push_results:      dict = field(default_factory=dict)  # Stage 6: ip -> result
    post_snapshots:    dict = field(default_factory=dict)  # Stage 7: ip -> snapshot
    verify_result:     dict = field(default_factory=dict)  # Stage 8: ip -> result
    rollback_performed: bool = False
    #: ip -> what the device actually looked like after a failed push, diffed
    #: against the pre-change snapshot. Populated before any rollback runs.
    failure_state: dict = field(default_factory=dict)

    # ---- Phase 3c: convergence and golden-save state ---------------------
    convergence:         dict = field(default_factory=dict)  # Stage 8: ip -> checks
    pending_convergence: list = field(default_factory=list)  # not-yet-converged notes
    golden_result:       dict = field(default_factory=dict)  # Stage 8.5
    golden_skipped:      list = field(default_factory=list)
    warnings:            list = field(default_factory=list)
    rolled_back_ips:     list = field(default_factory=list)
    deploy_failures:     list = field(default_factory=list)
    #: Sleep function used by the verify settle windows. Tests pass a no-op;
    #: a caller could pass one that shortens the wait. Defaults to real sleep.
    settle_sleep:        Any = None

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

    # ── the command list ───────────────────────────────────────────────────
    #
    # Derived, not assigned. A pass-through flag would still be a convention,
    # and conventions are what failed here twice: stage 2 ended with
    # ``ctx.rendered_commands = rendered``, discarding a list the operator had
    # already confirmed. Making the confirmed list win *by construction* means
    # no later edit to stage 2 can reintroduce that, and an attempt to assign
    # over it raises rather than silently succeeding.

    @property
    def rendered_commands(self) -> dict:
        """The commands to send. A confirmed list wins and cannot be replaced."""
        if self.confirmed_commands is not None:
            return self.confirmed_commands
        return self._rendered

    @rendered_commands.setter
    def rendered_commands(self, value: dict) -> None:
        if self.confirmed_commands is not None:
            raise ConfirmedCommandsOverwritten(
                "refusing to replace a confirmed command list: the operator "
                f"approved {len(self.confirmed_commands)} device list(s) and "
                "something tried to render a substitute")
        self._rendered = value

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
    ("save_golden",     "continue"),  # 8.5 records what was actually pushed
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
            _stage_save_golden,
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
                    log.error("pipeline: stage '%s' FAILED: %s", name, exc)
                    if on_failure == "continue":
                        # The config is already on the device. Failing to
                        # *record* it is worth reporting, not worth rolling a
                        # successful deploy back over.
                        self.ctx.warnings.append(f"{name}: {exc}")
                        self._next_expected = idx + 1
                        continue
                    self.ctx.error        = str(exc)
                    self.ctx.final_status = "failed"
                    # Record what actually landed BEFORE rolling back, or the
                    # evidence is destroyed by the repair. "The push failed"
                    # and "the device is unchanged" are different claims.
                    if on_failure == "rollback":
                        _capture_failure_state(self.ctx)
                    # A push was ATTEMPTED if any device has a push result —
                    # including a failed one. The old condition required
                    # "deploy" in stages_completed, which is false precisely
                    # when the deploy stage is the thing that failed: a
                    # mid-push failure, the case rollback exists for, rolled
                    # back nothing.
                    attempted = (bool(self.ctx.push_results)
                                 or "deploy" in self.ctx.stages_completed)
                    if on_failure == "rollback" and attempted:
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

    from modules.nsot import build_render_context

    for dev in ctx.selected_devices:
        ip       = dev["ip"]
        hostname = dev.get("hostname", ip)
        try:
            # One context builder feeds the pipeline, render previews, the
            # onboarding wizard and the AI tools — see modules/nsot/context.py.
            built = build_render_context(hostname, params=ctx.device_params(ip))
            context = built["context"]
            intended[ip] = {
                "device":     context["device"] or None,
                "interfaces": context["interfaces"],
                "site":       context["site"],
                "context":    context,
                "error":      None if built["ok"] else built["error"],
            }
            if not built["ok"]:
                errors.append(f"{hostname}: {built['error']}")
        except Exception as exc:
            intended[ip] = {"device": None, "interfaces": [], "site": {},
                            "context": {}, "error": str(exc)}
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

    **A confirmed command list is never re-rendered.** The NSoT deploy path
    (Phase 3c) computes its command list outside the pipeline entirely — it has
    to, because the operator confirmed that exact list and it is the only thing
    that may be sent. This stage used to end with ``ctx.rendered_commands =
    rendered`` unconditionally, so a caller that populated it beforehand had
    its work discarded and then failed on an unknown ``config_type``.
    Re-rendering would have broken the confirm guarantee even if it *succeeded*:
    the pipeline would decide what to send after the operator approved
    something else.

    The early return below is the intended path. The assignment at the end of
    this function is also refused by the setter now, so deleting the return
    would raise rather than quietly substitute.
    """
    from modules.configure import generate_config_commands

    if ctx.confirmed_commands is not None:
        if not ctx.confirmed_commands:
            raise PipelineStageError(
                "a confirmed command list was declared but is empty — refusing "
                "to render a substitute for a list the operator confirmed")
        log.info("pipeline[2/template_render]: %d confirmed command list(s) — "
                 "not rendering", len(ctx.confirmed_commands))
        return

    tpl_path = _config_template_path(ctx.config_type)
    rendered: dict[str, list[str]] = {}
    errors:   list[str]            = []

    for dev in ctx.selected_devices:
        ip       = dev["ip"]
        hostname = dev.get("hostname", ip)
        p        = ctx.device_params(ip)
        per_device = (ctx.intended_config.get("devices", {}).get(ip, {}) or {})
        nb_dev     = per_device.get("device") or {}
        # Stage 1 fetched these; stage 2 used to read only ["device"] and throw
        # the rest away, so templates never saw an interface or an IP address.
        render_ctx = per_device.get("context") or {}
        try:
            if tpl_path and os.path.isfile(tpl_path):
                cmds = _render_jinja2(tpl_path, p, nb_dev, render_ctx)
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


def _render_jinja2(tpl_path: str, params: dict, nb_device: dict,
                   render_ctx: dict = None) -> list[str]:
    """
    Render a Jinja2 config template.

    Jinja2 is part of Flask's dependency tree — no additional install required.

    Templates receive the full render context (see
    ``modules/nsot/context.py``): ``device``, ``interfaces`` (each with
    ``ip_addresses``), ``site``, ``vars``, and ``params``. ``netbox`` is kept as
    an alias for ``device`` so templates written against the previous signature
    keep working.
    """
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    env = Environment(
        loader       = FileSystemLoader(os.path.dirname(tpl_path)),
        undefined    = StrictUndefined,
        trim_blocks  = True,
        lstrip_blocks= True,
    )
    ctx = dict(render_ctx or {})
    tpl      = env.get_template(os.path.basename(tpl_path))
    rendered = tpl.render(
        params     = params,
        netbox     = nb_device,                    # backwards-compatible alias
        device     = ctx.get("device", nb_device),
        interfaces = ctx.get("interfaces", []),
        site       = ctx.get("site", {}),
        vars       = ctx.get("vars", {}),
    )
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

    Transport comes from the platform map, per device: a platform whose
    ``supports_netconf`` is false goes straight to SSH with **no NETCONF
    attempt at all**, rather than falling back after a socket timeout.

    ``netconf_enabled`` survives as a master off-switch only — it can disable
    NETCONF everywhere, never enable it on a platform that lacks it.
    """
    # Transport is decided PER PLATFORM, before anything connects. The previous
    # behaviour gated NETCONF on one global setting and fell back to SSH only
    # after a failed attempt — on a batch containing vIOS-L2, which has no
    # NETCONF at all, that is one socket timeout per device before anything
    # happens, and a deploy that looks hung.
    try:
        from modules.nsot.deploy import transport_for
        transport = transport_for(dev.get("_platform", "") or dev.get("platform", ""))
    except Exception:                          # noqa: BLE001
        transport = "ssh"

    if transport != "netconf":
        return _push_via_netmiko(dev, cmds, pool, lock)

    try:
        import ncclient  # noqa: F401 — availability probe
        return _push_via_netconf(dev, cmds)
    except ImportError:
        log.debug("pipeline: ncclient not installed — using Netmiko SSH")
    except Exception as nc_exc:
        log.warning("pipeline: NETCONF push failed (%s) — falling back to SSH", nc_exc)
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
            snap = _capture_operational_snapshot(conn, ip, hostname)

            # The operational snapshot is metrics only — neighbours, interface
            # counts. Stage 8.5 needs the post-deploy CONFIG to commit as
            # golden; without this it would commit stage 4's pre-deploy copy
            # and record the wrong thing entirely.
            try:
                from modules.commands import run_device_command
                snap["running_config"] = run_device_command(
                    conn, "show running-config")
            except Exception as cfg_exc:
                log.warning("pipeline[7/post_snapshot]: %s config capture failed: %s",
                            hostname, cfg_exc)
                snap["running_config"] = ""

            ctx.post_snapshots[ip] = snap
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

from modules.nsot.convergence import (
    CONVERGED as _CONVERGED, FAILED as _FAILED, NOT_YET as _NOT_YET,
    SKIPPED as _SKIPPED, wait_for as _wait_for, window_for as _window_for,
)


def _await_neighbour_convergence(ctx, ip: str, hostname: str, protocol: str,
                                 pre_count: int) -> dict:
    """Re-poll a device's neighbour count within the protocol's settle window.

    Returns ``{"state", "count", "elapsed", "window"}``. Three outcomes:

    * ``converged``          — the count recovered
    * ``not_yet_converged``  — still short, but the protocol is alive and
                               updating, so this very likely is not a failure
    * ``failed``             — still short with no sign of life

    For RIP, "sign of life" is a recent entry in the Routing Information
    Sources table: updates arriving means convergence is in progress.
    """
    from modules.connection import get_persistent_connection

    dev = next((d for d in ctx.selected_devices if d["ip"] == ip), None)
    window = _window_for(protocol)
    if dev is None:
        return {"state": _FAILED, "count": -1, "elapsed": 0.0, "window": window}

    latest = {"count": -1, "snapshot": {}}

    def _probe():
        conn = get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)
        snapshot = _detect_routing_neighbors(conn)
        latest["count"] = snapshot.get("count", -1)
        latest["snapshot"] = snapshot
        return snapshot

    # ctx.settle_sleep lets a caller run verification without real delays —
    # tests pass a no-op, and it is the seam for a future "verify now, do not
    # wait" mode. Defaults to real sleeping.
    result = _wait_for(
        protocol, _probe,
        lambda snap: (snap.get("count", -1) - pre_count) >= -_NEIGHBOR_DROP_TOLERANCE,
        sleep=ctx.settle_sleep or time.sleep,
    )

    count = latest["count"]
    if result["state"] == _CONVERGED:
        state = _CONVERGED
    elif _protocol_shows_progress(latest["snapshot"], count):
        state = _NOT_YET
    else:
        state = _FAILED

    return {"state": state, "count": count, "elapsed": result["elapsed"],
            "window": window, "attempts": result["attempts"]}


def _protocol_shows_progress(snapshot: dict, count: int) -> bool:
    """Is the protocol still doing something, or has it simply stopped?

    A partial recovery counts. For RIP, so does a recent update from any
    remaining source — the gateway is still talking, the table is just not
    complete yet.
    """
    if count > 0:
        return True
    for source in snapshot.get("sources", []) or []:
        stamp = source.get("last_update", "")
        # "00:00:12" — anything under a minute means updates are flowing.
        if re.match(r"^00:00:\d{2}$", stamp):
            return True
    return False


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
                # Do not call it a failure on the first look. A protocol that
                # has just had its config changed needs time: RIP sends updates
                # every 30 seconds, so a neighbour check run two seconds after a
                # RIP change reports a drop that is not real.
                settled = _await_neighbour_convergence(
                    ctx, ip, hostname, pre_proto, pre_count)
                ctx.convergence.setdefault(ip, {})["neighbors"] = settled

                if settled["state"] == _CONVERGED:
                    log.info("pipeline[8/verify]: %s %s neighbours recovered "
                             "(%d) after %.0fs", hostname, pre_proto,
                             settled["count"], settled["elapsed"])
                elif settled["state"] == _NOT_YET:
                    # Reported, not counted against the deploy. Calling a slow
                    # protocol a failure is what makes an operator distrust the
                    # verifier and start skipping it.
                    log.warning("pipeline[8/verify]: %s %s not yet converged "
                                "(%d → %d after %.0fs)", hostname, pre_proto,
                                pre_count, settled["count"], settled["elapsed"])
                    ctx.pending_convergence.append(
                        f"{hostname}: {pre_proto} {pre_count} → {settled['count']} "
                        f"(still converging after {settled['elapsed']:.0f}s)")
                else:
                    issues.append(
                        f"{pre_proto} neighbors dropped: {pre_count} → "
                        f"{settled['count']} and did not recover within "
                        f"{settled['window']['timeout']}s "
                        f"(tolerance={_NEIGHBOR_DROP_TOLERANCE})")
        elif pre_count >= 0 and post_count < 0:
            # Protocol was present before but not detected after — treat as full loss.
            issues.append(
                f"{pre_proto} neighbor table unreadable after deploy "
                f"(pre={pre_count}, post=unavailable)"
            )
        elif pre_count < 0:
            # No routing protocol detected at all. Record it explicitly so a
            # device that checked nothing cannot look the same as one that
            # checked something and passed.
            ctx.convergence.setdefault(ip, {})["neighbors"] = {
                "state": _SKIPPED, "protocol": "none",
                "reason": "no routing protocol detected on this device"}

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

def _capture_failure_state(ctx: PipelineContext) -> None:
    """Read each attempted device back and diff it against the pre-snapshot.

    ``send_config_set`` raising means something was *already sent*. Reporting
    only "the push failed" conflates that with "the device is unchanged", and
    the difference is the whole question an operator has after a failure. The
    corrupted description on the first real run was found by a human going and
    looking; the pipeline had the connection and did not look.

    Runs before rollback, so the record survives the repair.
    """
    from modules.ai_assistant import _load_pre_change_file
    from modules.connection import get_persistent_connection

    for ip, result in ctx.push_results.items():
        if result.get("skipped"):
            continue
        dev = next((d for d in ctx.selected_devices if d["ip"] == ip), None)
        if not dev:
            continue
        hostname = dev.get("hostname", ip)
        entry = {"device": hostname, "ip": ip, "push_ok": bool(result.get("ok"))}
        try:
            conn = get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)
            post = conn.send_command("show running-config")
            pre = _load_pre_change_file(ip) or ""
            pre_lines = [l.rstrip() for l in pre.splitlines()]
            post_lines = [l.rstrip() for l in post.splitlines()]
            pre_set, post_set = set(pre_lines), set(post_lines)
            entry.update({
                "landed": [l for l in post_lines if l and l not in pre_set],
                "lost": [l for l in pre_lines if l and l not in post_set],
                "have_pre_snapshot": bool(pre),
            })
            entry["device_changed"] = bool(entry["landed"] or entry["lost"])
            if entry["device_changed"]:
                log.warning("pipeline[failure-state]: %s CHANGED despite a failed "
                            "push — %d line(s) landed, %d lost", hostname,
                            len(entry["landed"]), len(entry["lost"]))
            else:
                log.info("pipeline[failure-state]: %s unchanged", hostname)
        except Exception as exc:               # noqa: BLE001
            entry.update({"error": str(exc), "device_changed": None})
            log.error("pipeline[failure-state]: could not read %s back: %s",
                      hostname, exc)
        ctx.failure_state[ip] = entry


def _stage_rollback(ctx: PipelineContext) -> None:
    """
    Restore the pre-change running-config on every device that was successfully pushed.
    Uses the file written by _save_pre_change_file in Stage 4.
    """
    from modules.ai_assistant  import _load_pre_change_file
    from modules.connection    import get_persistent_connection

    # Every device a push was ATTEMPTED on, not only the ones that succeeded.
    # A failed send_config_set means commands were already going down the wire
    # when it gave up — that device is *more* likely to need restoring than one
    # that completed cleanly, and it was the only one the old filter excluded.
    targets = [ip for ip, r in ctx.push_results.items() if not r.get("skipped")]
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
# Stage 8.5 — Save golden
# ---------------------------------------------------------------------------

def _stage_save_golden(ctx: PipelineContext) -> None:
    """Commit the post-deploy config as the new golden baseline.

    Part of the flow, not a callback afterwards. Containerlab nodes are
    ephemeral: pushed config does not survive a redeploy, so the golden commit
    is the durable record of what was actually put on the device.

    Runs **after verify**, so it never records config that is about to be rolled
    back, and on **partial success**: devices that deployed and verified get
    their golden saved even when siblings failed. Losing a good record because
    another device failed would be the worst outcome here.
    """
    import os as _os

    from modules.config import get_current_list_name, get_list_data_dir
    from modules.nsot import manifest as _manifest
    from modules.nsot.repo import GoldenItem, save_golden

    repo = _os.path.join(get_list_data_dir(get_current_list_name()), "config_repo")
    rolled_back = set(ctx.rolled_back_ips or [])
    failed_ips = {f.get("ip") for f in (ctx.deploy_failures or [])
                  if isinstance(f, dict)}

    items, skipped = [], []
    for dev in ctx.selected_devices:
        ip = dev["ip"]
        hostname = dev.get("hostname", ip)

        if ip in rolled_back or ip in failed_ips:
            skipped.append({"hostname": hostname, "reason": "not deployed successfully"})
            continue

        config = (ctx.post_snapshots.get(ip) or {}).get("running_config", "")
        if not config:
            # No post-deploy capture: record nothing rather than commit the
            # pre-deploy config and claim it is what the device now has.
            skipped.append({"hostname": hostname,
                            "reason": "no post-deploy config captured"})
            continue

        # Resolve the identity the manifest already holds. The inventory row
        # carries one only if the CSV has a device_uid or NetBox supplied an
        # id; when it does not, save_golden used to mint a fresh uid and the
        # device silently acquired a SECOND manifest entry. A deploy is never
        # an onboarding.
        netbox_id = dev.get("_netbox_id")
        device_uid = dev.get("device_uid", "")
        if not _manifest.identity_for(netbox_id, device_uid):
            existing, _entry = _manifest.find_by_ip(repo, ip)
            if not existing:
                existing, _entry = _manifest.find_by_name(repo, hostname)
            if existing and existing.startswith("uid:"):
                device_uid = existing.split(":", 1)[1]
            elif existing and existing.startswith("nb:"):
                netbox_id = existing.split(":", 1)[1]

        items.append(GoldenItem(hostname, config, ip,
                                netbox_id=netbox_id,
                                device_uid=device_uid))

    ctx.golden_skipped = skipped
    if not items:
        log.info("pipeline[8.5/save_golden]: nothing to record (%d skipped)",
                 len(skipped))
        ctx.golden_result = {"ok": True, "commit": "", "changed": []}
        return

    # allow_new=False: a pipeline deploy targets a device the inventory
    # already knows. Reaching here with no identity is a bug, not a new device.
    result = save_golden(get_current_list_name(), items, source="pipeline",
                         actor="pipeline", pipeline_id=ctx.config_id,
                         allow_new=False)
    ctx.golden_result = result

    if not result.get("ok"):
        raise PipelineStageError(
            f"golden save failed: {result.get('error')} — the config IS on the "
            "device, but was not recorded")

    log.info("pipeline[8.5/save_golden]: recorded %d device(s) in %s (%d skipped)",
             len(result.get("changed", [])), result.get("commit", "")[:8], len(skipped))


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


def _parse_rip_sources(show_ip_protocols: str):
    """Gateways RIP is hearing routes from, with the age of the last update.

    Parses the ``Routing Information Sources`` table that appears under the RIP
    section of ``show ip protocols``::

        Routing Information Sources:
          Gateway         Distance      Last Update
          10.255.2.10          120      00:00:12

    Returns a list of ``{"gateway", "distance", "last_update"}``, or None when
    the section is absent. An empty list is a real answer — RIP is configured
    but hearing from nobody — and is distinct from None, which means RIP was
    not found at all.
    """
    lines = (show_ip_protocols or "").splitlines()
    sources = []
    in_section = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Routing Information Sources"):
            in_section = True
            continue
        if not in_section:
            continue
        if stripped.startswith("Gateway"):
            continue
        # The section ends at the next unindented line or a new heading.
        if stripped.startswith("Distance:") or (stripped and not line.startswith(" ")):
            break
        match = re.match(r"^(\d[\d.]+)\s+(\d+)\s+(\S+)", stripped)
        if match:
            sources.append({"gateway": match.group(1),
                            "distance": int(match.group(2)),
                            "last_update": match.group(3)})
    return sources if in_section else None


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

    # ── RIP ───────────────────────────────────────────────────────────────
    # RIP is distance-vector: it has no adjacencies, so there is no
    # `show ip rip neighbor` to read. Its equivalent is the "Routing
    # Information Sources" table in `show ip protocols`, which lists each
    # gateway RIP is hearing from and how long ago.
    #
    # Probed last so a device running OSPF *and* RIP keeps its existing primary
    # protocol. Before this, a RIP-only device (S1/S2) matched nothing, returned
    # count -1, and the verify stage skipped the neighbour check entirely — so
    # it reported "verified" having checked no neighbour state at all. A verify
    # that silently checks nothing is worse than no verify.
    try:
        out = run_device_command(conn, "show ip protocols")
        if "rip" in out.lower():
            sources = _parse_rip_sources(out)
            if sources is not None:
                return {"protocol": "rip", "count": len(sources),
                        "sources": sources, "output": out[:2000]}
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
