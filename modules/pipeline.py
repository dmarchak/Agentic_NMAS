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
#: 0 (C114, the operator's decision 2026-09-27). It was 1, checked as
#: `drop <= 1`, so any single loss passed WITHOUT opening the settle window,
#: including 1 -> 0: a device losing its only neighbour passed verify. The
#: settle window is the one mechanism for a transient drop: every loss is
#: re-polled for its protocol's window and fails only if it persists.
_NEIGHBOR_DROP_TOLERANCE = 0

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

def dangerous_commands(commands) -> list:
    """Every command in *commands* that the CI gate treats as dangerous.

    Exposed so a **plan** can flag these before anyone confirms, rather than
    the gate discovering them at stage 3 with no way to authorise them. The
    gate compares ``cmd.strip()`` against the allow-list, so that is what is
    returned — the exact string an authorisation must name.
    """
    flagged = []
    for command in commands or []:
        if any(pattern.search(command) for pattern in _DANGEROUS_PATTERNS):
            flagged.append(command.strip())
    return flagged


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

def _list_of(ctx) -> str:
    """The device list this run belongs to.

    The **only** place the pipeline may consult global state for it, and only
    when a caller supplied nothing. Every production caller sets
    ``ctx.list_name``; the fallback exists for older test contexts and logs
    loudly, because a deploy that has to guess which network it is writing to
    is a deploy that can write to the wrong one.
    """
    if getattr(ctx, "list_name", ""):
        return ctx.list_name
    from modules.config import get_current_list_name
    fallback = get_current_list_name()
    log.warning("pipeline: no list_name on the context — falling back to the "
                "active list %r. The caller should set ctx.list_name.", fallback)
    return fallback


@dataclass
class PipelineContext:
    """All state for one pipeline run, shared across all stage handlers."""

    # ---- Inputs (set before run) -----------------------------------------
    config_type:      str
    device_ips:       list[str]
    params:           dict                   # shared params (used when ip_params_map empty)
    ip_params_map:    dict                   # per-device param overrides: {ip: params}
    selected_devices: list[dict]             # raw device dicts from the device list
    connections_pool: dict
    pool_lock:        Any
    config_id:        str
    #: Which device list this run writes to. **Set once, by the originating
    #: request, and never re-derived.**
    #:
    #: The pipeline used to ask ``get_current_list_name()`` for this at three
    #: points, all of them *after* the push — including the golden commit. That
    #: function reads ``current_list`` out of a file on disk on every call, so
    #: it is neither per-request nor per-thread: any request that switches
    #: lists rewrites it. A deploy spans push plus a convergence settle window
    #: of 45s (OSPF), 60s (BGP) or 90s (RIP), and switching lists in the UI
    #: while waiting is one click — after which stage 8.5 committed network A's
    #: captured configs into network B's repository.
    #:
    #: ``allow_new=False`` masked this: a device B's manifest had never heard of
    #: failed identity resolution and the commit errored. That protection
    #: disappears exactly when it matters — two networks that both contain
    #: ``r1``, or both use the same management address, resolve cleanly and A's
    #: config is committed as B's golden.
    list_name:        str = ""

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
    #: ip -> the IP SLA operations that same read-back found (recreate.operations),
    #: so a rollback restores only an operation the push reached. Kept apart
    #: from failure_state, which the result returns.
    failure_sla: dict = field(default_factory=dict)
    #: ip -> the exact rollback program sent, reported verbatim.
    rollback_commands: dict = field(default_factory=dict)
    #: ip -> why a rollback could not complete.
    rollback_failures: dict = field(default_factory=dict)
    #: Set by a batch: stage 8.5 hands its captures back instead of committing.
    defer_golden: bool = False
    #: Captures handed to the batch when :attr:`defer_golden` is set.
    golden_pending: list = field(default_factory=list)
    #: ip -> pushed lines the device rejected, so there was nothing to undo.
    rollback_not_undone: dict = field(default_factory=dict)
    #: ip -> rollback lines that would have tripped the CI gate, exempt by
    #: provenance. Recorded so the exemption is visible in the report.
    rollback_dangerous: dict = field(default_factory=dict)
    #: ip -> what the rollback ACHIEVED (C112): ``{"state", "detail",
    #: "remaining"}``, state one of ROLLBACK_STATES. A rollback that raised,
    #: or never ran, used to be drawn "rolled back".
    rollback_outcome: dict = field(default_factory=dict)

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
    #: The clock the BGP hold watch measures with (C178). Tests pass one that
    #: advances when `settle_sleep` sleeps; defaults to `time.monotonic`.
    settle_clock:        Any = None
    #: ip -> when its push FINISHED, on `settle_clock` (C178): a BGP reading
    #: counts only once the hold time has passed since this moment.
    pushed_at:           dict = field(default_factory=dict)
    #: ip -> the routing protocols the TARGET intent declares (a deploy's
    #: committed intent, a restore's intent at the ref), or ``None`` when no
    #: intent is known. Carried by the caller, never derived: verify read
    #: its protocol list from the device's BEFORE state alone, so the
    #: protocol an operation exists to bring back was the one it could not
    #: check (C107's sibling, the operator's, C70 re-run 2026-09-27).
    declared_protocols:  dict = None
    #: ip -> ``{"units", "commands"}``: the removals a person selected (Mode B),
    #: the TAIL of the confirmed program. Verify reads back that each is gone;
    #: rollback undoes them by re-adding the device's own lines, never by
    #: `rollback_commands`, which would read a `no X` as never applied.
    removals:            dict = None

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
        # Each stage is PROGRESS on the device this run holds (C98): a second
        # operation refused meanwhile reads "last progress: verify, 20 s ago",
        # and a stall past ten minutes reads as possibly stuck.
        from modules.nsot import device_ops
        try:
            for idx, handler in enumerate(_handlers):
                name, on_failure = _STAGE_TABLE[idx]
                self._assert_order(idx)
                device_ops.note(name)
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
    """A DANGEROUS-COMMAND check, before any SSH connection is opened.

    The stage keeps its historical name, `ci_gate`, and is local: it checks
    that every target device has commands, and that no command matches
    `_DANGEROUS_PATTERNS` unless that exact line is authorised in
    ``params["allowed_dangerous"]``.

    It used to claim two more checks (P.4, docs/NSOT_CI.md):
    - a "syntax check", which only looked up a name in `check_runner.CHECKS`
      and logged "no check registered" on every deploy;
    - the last result of Jenkins jobs registered to the ACTIVE list, skipped
      silently when Jenkins was unconfigured (it always was), fail-open on any
      error, and keyed on the wrong list.

    Both were removed with Jenkins. A gate that describes a check it does not
    make is the wrong-and-looks-right state.
    """
    from modules.nsot.authorisation import key as _auth_key

    # KEYS, named by the one authorisation mechanism (C140): a line's key is
    # itself unless it holds a secret position, so the gate and the confirm
    # name a line the same way.
    allowed: set[str] = set(ctx.params.get("allowed_dangerous", []))

    for ip, cmds in ctx.rendered_commands.items():
        hostname = next((d.get("hostname", ip) for d in ctx.selected_devices
                         if d["ip"] == ip), ip)
        if not cmds:
            raise PipelineStageError(f"CI gate: no rendered commands for {hostname}")
        for cmd in cmds:
            for pat in _DANGEROUS_PATTERNS:
                if pat.search(cmd) and _auth_key(cmd) not in allowed:
                    raise PipelineStageError(
                        f"CI gate: dangerous command detected for {hostname}: {cmd!r}. "
                        f"Add the exact command string to params['allowed_dangerous'] to override."
                    )

    ctx.ci_passed = True
    log.info(
        "pipeline[3/ci_gate]: passed — %d device(s), no unauthorised dangerous "
        "commands", len(ctx.rendered_commands),
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
            get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)  # reachable, or raise
            snap = _capture_operational_snapshot(_session_for(ctx, dev), ip, hostname)
            bad = _unreadable(snap)
            if bad:
                # Refuse, never guess (C272): a baseline read that cannot be
                # trusted would make verify compare against nothing, so the
                # protocol it names would never be checked. Nothing is sent.
                errors.append(f"{hostname} ({ip}): could not be read reliably before the "
                              "change, so nothing was sent: " + "; ".join(bad))
                continue

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
            ctx.pushed_at[ip] = (ctx.settle_clock or time.monotonic)()
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


#: IOS rejects a malformed command by printing this and moving on. Netmiko does
#: not treat it as an error by default, so a cleanly rejected line returns
#: normally with the rejection sitting unread in the output: the push logs
#: "pushed — N command(s)", verify passes because nothing changed, and stage 8.5
#: commits a golden that correctly records a device which was never configured.
#: A successful deploy that configured nothing is the quietest failure available.
#:
#: That comment was right about the mechanism and wrong about the vocabulary.
#: It listed the ``% Invalid input`` family only, and IOS has a second one:
#: a semantic refusal of a *well-formed* command, printed as a bare ``ERROR:``
#: with no ``%`` at all. Measured on r2 (IOS-XE 17.06.01a)::
#:
#:     ERROR: Can not have both a user password and a user secret.
#:     Please choose one or the other.
#:
#: The credential rotation sent one command, the device refused it in plain
#: English, and the tool recorded a successful push — exactly the failure this
#: constant exists to prevent, through the half of the vocabulary it did not
#: cover.
#:
#: Anchored per line, and netmiko applies it with ``re.M``. That is what keeps
#: an echoed ``description ERROR: link flaps`` from firing it: netmiko echoes
#: each command after the prompt on the same line, so only device output
#: begins a line. The ``(?m)`` is inline so the pattern carries its own
#: semantics to any caller that does not pass the flag.
IOS_ERROR_PATTERN = (r"(?m)^\s*(?:%\s*(?:Invalid|Incomplete|Ambiguous|Unrecognized)"
                     r"|%?\s*ERROR:|%\s*Error:)")


def _push_via_netmiko(dev: dict, cmds: list[str], pool: dict, lock: Any) -> str:
    """Push config via Netmiko SSH (existing connection pool)."""
    from modules.connection import get_persistent_connection
    conn = get_persistent_connection(dev, pool, lock)
    conn.enable()
    output = conn.send_config_set(cmds, read_timeout=60,
                                  error_pattern=IOS_ERROR_PATTERN)
    conn.save_config()
    return output


def _canary_sanity_check(canary_dev: dict, ctx: PipelineContext) -> None:
    """
    Verify the canary device still has at least one up interface after push.
    Halts fleet deployment if the check fails.
    """
    from modules.connection import close_persistent_connection, get_persistent_connection
    from modules.commands   import run_device_command

    ip       = canary_dev["ip"]
    hostname = canary_dev.get("hostname", ip)
    # A new session, not the push's (C272: after a save its prompt read as `^@`).
    close_persistent_connection(ip, ctx.connections_pool, ctx.pool_lock)
    conn     = get_persistent_connection(canary_dev, ctx.connections_pool, ctx.pool_lock)
    out      = run_device_command(conn, "show ip interface brief")
    # A LOOPBACK does not count: it is up whatever the push did, so "any
    # interface up" passed on every device in this fleet (C67). The question
    # is whether an interface that carries traffic is still up and up.
    carrying = [line.split()[0] for line in out.splitlines()
                if line.split()[-2:] == ["up", "up"]
                and not line.lower().startswith(("loopback", "interface"))]
    if not carrying:
        raise PipelineStageError(
            f"Canary {hostname}: no non-loopback interface is up/up after deploy "
            "— fleet push halted"
        )
    log.info("pipeline[6/deploy]: canary %s sanity check passed", hostname)


# ---------------------------------------------------------------------------
# Stage 7 — Post-change snapshot
# ---------------------------------------------------------------------------

def _stage_post_snapshot(ctx: PipelineContext) -> None:
    """Capture the same operational metrics as Stage 4, now AFTER deploy,
    on a NEW session (C272): the push's session is where the prompt read as
    `^@` after a save, and a read on it could not see its own end."""
    from modules.connection import close_persistent_connection, get_persistent_connection

    errors: list[str] = []

    for dev in ctx.selected_devices:
        ip       = dev["ip"]
        hostname = dev.get("hostname", ip)
        try:
            close_persistent_connection(ip, ctx.connections_pool, ctx.pool_lock)
            get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)  # reachable, or raise
            snap = _capture_operational_snapshot(_session_for(ctx, dev), ip, hostname)

            # The operational snapshot is metrics only — neighbours, interface
            # counts. Stage 8.5 needs the post-deploy CONFIG to commit as
            # golden; without this it would commit stage 4's pre-deploy copy
            # and record the wrong thing entirely.
            try:
                from modules.commands import run_device_command
                # Asked of the pool again: a read above that failed spent its
                # session, and the pool replaces a spent one (C272).
                conn = get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)
                snap["running_config"] = run_device_command(
                    conn, "show running-config")
            except Exception as cfg_exc:
                log.warning("pipeline[7/post_snapshot]: %s config capture failed: %s",
                            hostname, cfg_exc)
                snap["running_config"] = ""
                # Verify says it could not read it (C272), never "not removed".
                snap["running_config_error"] = f"{type(cfg_exc).__name__}: {cfg_exc}"

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

#: A settle-window read that could not be trusted (C272): neither converged
#: nor failed, and said so.
_UNREADABLE = "unreadable"


def _await_neighbour_convergence(ctx, ip: str, hostname: str, protocol: str,
                                 pre_count: int, need: int = None) -> dict:
    """Re-poll a device's neighbour count within the protocol's settle window.

    Returns ``{"state", "count", "elapsed", "window"}``. Three outcomes:

    * ``converged``          — the count recovered
    * ``not_yet_converged``  — still short, but the protocol is alive and
                               updating, so this very likely is not a failure
    * ``failed``             — still short with no sign of life

    For RIP, "sign of life" is a recent entry in the Routing Information
    Sources table: updates arriving means convergence is in progress.

    ``need``, when given, is an absolute floor instead of "no worse than
    before": a protocol intent declares and the device was not running
    needs at least one neighbour, and the drop tolerance would otherwise
    let zero pass. It can only tighten the condition.
    """
    from modules.connection import get_persistent_connection

    dev = next((d for d in ctx.selected_devices if d["ip"] == ip), None)
    window = _window_for(protocol)
    if dev is None:
        return {"state": _FAILED, "count": -1, "elapsed": 0.0, "window": window}

    latest = {"count": -1, "snapshot": {}}
    seen: list = []

    def _probe():
        get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)  # reachable, or raise
        snapshot = _detect_routing_neighbors(_session_for(ctx, dev))
        # A read of THIS protocol that failed is not a count of zero (C272).
        latest["unreadable"] = _unread_protocol(snapshot, protocol)
        # THIS protocol's count and details, not the primary's (C62).
        latest["count"] = _protocol_counts(snapshot).get(protocol, -1)
        latest["snapshot"] = (snapshot.get("protocols") or {}).get(protocol) or snapshot
        seen.append(latest["count"])
        return snapshot

    # ctx.settle_sleep lets a caller run verification without real delays —
    # tests pass a no-op, and it is the seam for a future "verify now, do not
    # wait" mode. Defaults to real sleeping.
    if need is not None:
        def _met(snap):
            return _protocol_counts(snap).get(protocol, -1) >= need
    else:
        def _met(snap):
            return (_protocol_counts(snap).get(protocol, -1) - pre_count) \
                >= -_NEIGHBOR_DROP_TOLERANCE
    result = _wait_for(protocol, _probe, _met, sleep=ctx.settle_sleep or time.sleep)

    count = latest["count"]
    rose = len(seen) > 1 and max(seen[1:]) > seen[0]
    if result["state"] == _CONVERGED:
        state = _CONVERGED
    elif latest.get("unreadable"):
        # The last read could not be trusted: neither converged nor failed.
        return {"state": _UNREADABLE, "count": count, "elapsed": result["elapsed"],
                "window": window, "attempts": result["attempts"],
                "unreadable": latest["unreadable"], "snapshot": latest["snapshot"]}
    elif _protocol_shows_progress(latest["snapshot"], count, rose=rose):
        state = _NOT_YET
    else:
        state = _FAILED

    return {"state": state, "count": count, "elapsed": result["elapsed"],
            "window": window, "attempts": result["attempts"],
            "snapshot": latest["snapshot"]}


def _watch_bgp_hold(ctx, ip: str, baseline: int, config: str) -> dict:
    """Read BGP once more, no earlier than the hold time after the push
    (C178). ``{"state", "hold_s", "basis", "watched_s", "before", "after",
    "issue"?}``: ``converged`` when the established count held, ``failed``
    (with the issue verify records) when it fell or could not be read,
    ``skipped`` when the configuration names no BGP neighbor."""
    from modules.connection import get_persistent_connection
    from modules.nsot.convergence import bgp_hold_times

    holds = bgp_hold_times(config)
    if not holds["peers"]:
        return {"state": _SKIPPED, "why": holds["basis"]}
    clock = ctx.settle_clock or time.monotonic
    pushed = ctx.pushed_at.get(ip)
    since = "the push"
    if pushed is None:
        # Nothing records when this device's push ended: count the whole hold
        # time from now, which can only wait longer, never shorter.
        pushed, since = clock(), "this check (no push time was recorded)"
    hold = holds["max"]
    remaining = pushed + hold - clock()
    if remaining > 0:
        (ctx.settle_sleep or time.sleep)(remaining)
    out = {"hold_s": hold, "basis": holds["basis"], "since": since,
           "peers": {n: p["hold"] for n, p in holds["peers"].items()},
           "before": baseline}
    dev = next((d for d in ctx.selected_devices if d["ip"] == ip), None)
    try:
        if dev is None:
            raise RuntimeError("the device is not in this run")
        get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)  # reachable, or raise
        snap = _detect_routing_neighbors(_session_for(ctx, dev))
        after = _protocol_counts(snap).get("bgp", -1)
        unread = _unread_protocol(snap, "bgp")
    except Exception as exc:                  # noqa: BLE001
        after, why, unread = -1, f"{type(exc).__name__}: {exc}", ""
    else:
        why = "BGP was not in the read" if after < 0 else ""
    out["watched_s"] = round(clock() - pushed)
    out["after"] = after
    if unread:
        # Read, and the reply could not be trusted (C272): unknown, said so,
        # never a session lost.
        out["state"] = _UNREADABLE
        out["unreadable"] = (f"bgp at its {hold} s hold time could not be read "
                             f"reliably ({unread})")
    elif after < 0:
        out["state"] = _FAILED
        out["issue"] = (f"bgp not re-read after its {hold} s hold time ({why}): whether "
                        "the sessions survived to hold expiry is unknown")
    elif after < baseline:
        out["state"] = _FAILED
        out["issue"] = (f"bgp established {baseline} -> {after} when read {out['watched_s']} s "
                        f"after {since}, past the {hold} s hold time ({holds['basis']}): a "
                        "session did not survive to its hold expiry")
    else:
        out["state"] = _CONVERGED
    log.info("pipeline[8/verify]: %s bgp watched %s s after %s (hold %s s, %s): %s -> %s",
             ip, out["watched_s"], since, hold, holds["basis"], baseline, after)
    return out


def _read_route_total(conn) -> int:
    """The route count verify compares (C66: networks plus subnets)."""
    from modules.commands import run_device_command
    return _parse_route_total(run_device_command(conn, "show ip route summary"))


def _await_route_retention(ctx, ip: str, pre_count: int) -> dict:
    """Re-read the route count within the route window until it is back to
    the retention floor. ``converged``, ``not_yet_converged`` (it ROSE in the
    window and is still short) or ``failed``."""
    from modules.connection import get_persistent_connection

    dev = next((d for d in ctx.selected_devices if d["ip"] == ip), None)
    window = _window_for("routes")
    if dev is None:
        return {"state": _FAILED, "count": -1, "elapsed": 0.0, "window": window}
    seen: list = []

    def _probe():
        conn = get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)
        seen.append(_read_route_total(conn))
        return seen[-1]

    result = _wait_for("routes", _probe,
                       lambda n: n >= 0 and n >= pre_count * _ROUTE_RETENTION_MIN,
                       sleep=ctx.settle_sleep or time.sleep)
    count = seen[-1] if seen else -1
    if result["state"] == _CONVERGED:
        state = _CONVERGED
    elif len(seen) > 1 and max(seen[1:]) > seen[0]:
        state = _NOT_YET
    else:
        state = _FAILED
    return {"state": state, "count": count, "elapsed": result["elapsed"], "window": window}


def _protocol_shows_progress(snapshot: dict, count: int, rose: bool = False) -> bool:
    """Is the protocol still recovering, or has it settled short?

    Progress is MOVEMENT: the count ROSE during the settle window, or, for
    RIP, updates are still arriving from a remaining source. A count that
    is merely above zero is not progress (C68, found 2026-09-27 by the C62
    fix's own test on r3's real output). "Any count > 0" called a permanent
    loss of three of six OSPF adjacencies "not yet converged" for ever, and
    that state is reported without counting against the deploy, so a
    partial loss could never fail verify.
    """
    if rose:
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
      • Routing neighbours: for EVERY protocol read before the push (BGP
        established sessions, OSPF adjacencies, EIGRP, IS-IS, RIP sources),
        the count must not drop by more than _NEIGHBOR_DROP_TOLERANCE.
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

        # ── Routing neighbours, EVERY protocol the device runs (C62) ───────
        # Each protocol read before the push is compared on its own. The
        # first version compared one protocol per device, and on r3 and r4 the
        # one it chose (BGP) counted 0 on both sides (C64), so their verify
        # could not fail.
        pre_nbr  = pre.get("routing_neighbors",  {})
        post_nbr = post.get("routing_neighbors", {})
        pre_counts  = _protocol_counts(pre_nbr)
        post_counts = _protocol_counts(post_nbr)
        primary = pre_nbr.get("protocol", "unknown")
        record = ctx.convergence.setdefault(ip, {})
        # What the TARGET intent declares, carried in (None: unknown). A
        # protocol it declares is checked whether or not the device ran it
        # before: the operation may exist precisely to bring it back.
        from modules.nsot.golden_state import MEASURED, protocol_up
        declared = (ctx.declared_protocols or {}).get(ip)
        from_intent = sorted(p for p in (declared or [])
                             if p in MEASURED and pre_counts.get(p, 0) < 1)
        checked = sorted(set(pre_counts) | set(from_intent))
        record["checked_protocols"] = checked
        unmet: list[str] = []
        # Reads after the change that could not be trusted (C272): verify
        # neither passes nor fails on them. It says so, and nothing is rolled
        # back for them, because the tool cannot see what the change did.
        cant_read: list[str] = []

        for pre_proto, pre_count in sorted(pre_counts.items()):
            post_count = post_counts.get(pre_proto, -1)
            # A read that could not be trusted goes to the settle window below,
            # which reads again on a new session; only when that read cannot be
            # trusted either is it `unreadable` (C272), never "unreadable after
            # deploy" counted as a loss.
            if post_count < 0 and not _unread_protocol(post_nbr, pre_proto):
                # Present before, not read after: treat as full loss.
                issues.append(
                    f"{pre_proto} neighbor table unreadable after deploy "
                    f"(pre={pre_count}, post=unavailable)"
                )
                continue
            drop = pre_count - post_count
            if drop <= _NEIGHBOR_DROP_TOLERANCE:
                continue
            # Do not call it a failure on the first look. A protocol that
            # has just had its config changed needs time: RIP sends updates
            # every 30 seconds, so a neighbour check run two seconds after a
            # RIP change reports a drop that is not real.
            settled = _await_neighbour_convergence(
                ctx, ip, hostname, pre_proto, pre_count)
            record.setdefault("neighbors_by_protocol", {})[pre_proto] = settled
            if pre_proto == primary or "neighbors" not in record:
                record["neighbors"] = settled

            if settled["state"] == _UNREADABLE:
                cant_read.append(f"{pre_proto}: {settled['unreadable']}")
            elif settled["state"] == _CONVERGED:
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

        # ── What intent declares and the device was not running before ──
        # Required to be UP after the change, judged by the golden state's
        # one definition of "up". Not a rollback: the device did not run it
        # before either, so undoing the change cannot bring it back, and on
        # an unrelated deploy a rollback would undo a good change. It makes
        # verify NOT pass, recorded and drawn, so "verify passed" never
        # stands over a protocol intent requires and the device lacks.
        for proto in from_intent:
            settled = _await_neighbour_convergence(
                ctx, ip, hostname, proto, pre_counts.get(proto, 0), need=1)
            record.setdefault("neighbors_by_protocol", {})[proto] = settled
            up, why = protocol_up(proto, settled.get("snapshot") or {})
            if settled["state"] == _UNREADABLE:
                cant_read.append(f"{proto}: {settled['unreadable']}")
            elif settled["state"] == _CONVERGED and up:
                log.info("pipeline[8/verify]: %s %s declared by intent and now up: %s",
                         hostname, proto, why)
            elif settled["state"] == _NOT_YET:
                ctx.pending_convergence.append(
                    f"{hostname}: {proto} is declared by intent, was not running "
                    f"before, and is still coming up after {settled['elapsed']:.0f}s")
            else:
                unmet.append(f"{proto} is declared by intent and is not up after the "
                             f"change ({why}); it was not up before it either")

        # ── BGP, watched to its hold time (C178) ─────────────────────────
        # A session a change broke without resetting TCP reads Established
        # until its hold timer expires, so a reading before then could not
        # have shown the break. The counts above can pass at the FIRST read,
        # or at once, so BGP gets one more read no earlier than the hold time
        # after the push, and a session gone by then fails verify.
        bgp_failed = any(i.startswith("bgp ") for i in issues) or any(
            u.startswith("bgp ") for u in unmet)
        if "bgp" in checked and not bgp_failed:
            baseline = pre_counts.get("bgp", 0) or (1 if "bgp" in from_intent else 0)
            watch = _watch_bgp_hold(ctx, ip, baseline, post.get("running_config") or "")
            record["bgp_watch"] = watch
            if watch.get("issue"):
                issues.append(watch["issue"])
            if watch.get("unreadable"):
                cant_read.append(watch["unreadable"])

        if not checked:
            # No routing protocol detected at all. Record it explicitly so a
            # device that checked nothing cannot look the same as one that
            # checked something and passed.
            record["neighbors"] = {
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
        if not _skip_route and pre_routes > 0 and (post.get("routes") or {}).get("error"):
            cant_read.append(f"routes: `show ip route summary`: {post['routes']['error']}")
        if not _skip_route and pre_routes > 0 and post_routes >= 0:
            retention = post_routes / pre_routes
            if retention < _ROUTE_RETENTION_MIN:
                # Re-read within the route window before calling it (C115):
                # the table settles after its protocols, and a count read the
                # instant after a push can be mid-reconvergence.
                settled = _await_route_retention(ctx, ip, pre_routes)
                post_routes = settled["count"] if settled["count"] >= 0 else post_routes
                retention = post_routes / pre_routes
                if settled["state"] == _CONVERGED:
                    log.info("pipeline[8/verify]: %s routes recovered to %d after %.0fs",
                             hostname, post_routes, settled["elapsed"])
                elif settled["state"] == _NOT_YET:
                    ctx.pending_convergence.append(
                        f"{hostname}: routes {pre_routes} → {post_routes} (still rising "
                        f"after {settled['elapsed']:.0f}s)")
                else:
                    issues.append(
                        f"Route table shrank: {pre_routes} → {post_routes} "
                        f"({retention:.0%} < required {_ROUTE_RETENTION_MIN:.0%}) and did "
                        f"not recover within {settled['window']['timeout']}s")

        # ── Interface up-count ────────────────────────────────────────────
        pre_up  = pre.get("interfaces",  {}).get("up_count",  -1)
        post_up = post.get("interfaces", {}).get("up_count", -1)
        if pre_up >= 0 and (post.get("interfaces") or {}).get("error"):
            cant_read.append(f"interfaces: `{_INTERFACES_READ}`: "
                             f"{post['interfaces']['error']}")
        if pre_up >= 0 and post_up >= 0:
            down_delta = pre_up - post_up
            if down_delta > _INTERFACE_DOWN_TOLERANCE:
                issues.append(
                    f"Interfaces went down: {pre_up} up before → {post_up} up after "
                    f"({down_delta} interface(s) lost, tolerance={_INTERFACE_DOWN_TOLERANCE})"
                )

        # ── Removals (Mode B): each selected line must be GONE ────────────
        removed = ((ctx.removals or {}).get(ip) or {}).get("units") or []
        removals_left = []
        if removed:
            from modules.nsot.removal import still_present
            post_cfg = post.get("running_config") or ""
            if not post_cfg and post.get("running_config_error"):
                cant_read.append("removals: `show running-config`: "
                                 + post["running_config_error"])
            elif not post_cfg:
                issues.append("Removal not verified: the post-change config could not be read")
            else:
                removals_left = still_present(removed, post_cfg)
                if removals_left:
                    issues.append("Removal did not take, still on the device: " + "; ".join(
                        " > ".join(list(u["chain"]) + [u["line"].strip()])
                        for u in removals_left))

        # ── Re-created IP SLA operations: each must read back as intent
        # defines it (the device refuses to edit a running one, so it was
        # deleted and defined again; recreate.py).
        recreated = ((ctx.removals or {}).get(ip) or {}).get("recreates") or []
        recreates_off = []
        if recreated:
            from modules.nsot.recreate import unmatched
            post_cfg = post.get("running_config") or ""
            if not post_cfg and post.get("running_config_error"):
                cant_read.append("re-created IP SLA operations: `show running-config`: "
                                 + post["running_config_error"])
            elif not post_cfg:
                issues.append("Re-created IP SLA operation not verified: the post-change "
                              "config could not be read")
            else:
                recreates_off = unmatched(recreated, post_cfg, "new")
                for u in recreates_off:
                    issues.append(f"ip sla {u['number']} did not read back as intent defines it: "
                                  f"expected {u['expected']}, found {u['found'] or 'nothing'}")

        ctx.verify_result[ip] = {
            "ok":     not issues and not unmet and not cant_read,
            # Read after the change and not trustworthy (C272): verify did not
            # pass, did not fail on them, and rolled nothing back for them.
            "unreadable": cant_read,
            # The removals read back, by name (Mode B).
            "removals_checked": len(removed),
            # How long BGP was watched after the push, against which hold
            # time and on what basis (C178); absent when BGP was not checked.
            "bgp_watch": record.get("bgp_watch"),
            "removals_left": [u["line"].strip() for u in removals_left],
            # The re-created IP SLA operations read back, by number.
            "recreates_checked": [u["number"] for u in recreated],
            "recreates_off": [u["number"] for u in recreates_off],
            "issues": issues,
            # Declared by intent and not up: verify did not pass, and nothing
            # was rolled back (see above).
            "intent_unmet": unmet,
            "declared_protocols": declared,
            # Whether the route counts were COMPARED (C115): every deploy and
            # restore skips the retention check, and the counts were drawn as
            # if they had been compared.
            "routes_compared": not _skip_route,
            "from_intent": from_intent,
            "pre":  {
                "routing_protocol": pre_nbr.get("protocol", "unknown"),
                "routing_neighbors": pre_nbr.get("count", -1),
                "routing_protocols": pre_counts,
                "routes":           pre_routes,
                "interfaces_up":    pre_up,
            },
            "post": {
                "routing_protocol": post_nbr.get("protocol", "unknown"),
                "routing_neighbors": post_nbr.get("count", -1),
                "routing_protocols": post_counts,
                "routes":           post_routes,
                "interfaces_up":    post_up,
            },
            # What was actually compared, by name, so a record can say which
            # checks ran on this device (the deploy receipt, C60).
            "checked_protocols": checked,
        }
        if unmet:
            log.error("pipeline[8/verify]: %s intent not met (no rollback): %s",
                      hostname, unmet)
        if cant_read:
            log.error("pipeline[8/verify]: %s could not be read reliably after the change "
                      "(verify did not pass; no rollback for it): %s", hostname, cant_read)
        if issues:
            failures.append(f"{hostname}: " + "; ".join(issues))
            log.error("pipeline[8/verify]: %s FAILED: %s", hostname, issues)
        else:
            log.info("pipeline[8/verify]: %s OK  neighbours=%s→%s  "
                     "routes=%s→%s  intf_up=%s→%s",
                     hostname, pre_counts, post_counts,
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

    **On a fresh connection, deliberately.** This function runs only after
    something has gone wrong on the pooled session, which makes it the path
    most likely to be handed a broken one — and its failure mode is losing the
    evidence it exists to collect. On the first real rollback the pooled
    connection returned NUL bytes where a prompt should be
    (``Pattern not detected`` on a NUL prompt) and the capture reported nothing;
    ``is_alive()`` had returned true, because it checks that the transport is
    up, not that the channel is synchronised. One occurrence, plausible
    mechanism, not reproduced — the fix does not depend on knowing the trigger.

    A fresh SSH handshake costs nothing on a path that only runs on failure.
    """
    from modules.ai_assistant import _load_pre_change_file
    from modules.connection import close_persistent_connection, with_temp_connection

    for ip, result in ctx.push_results.items():
        if result.get("skipped"):
            continue
        dev = next((d for d in ctx.selected_devices if d["ip"] == ip), None)
        if not dev:
            continue
        hostname = dev.get("hostname", ip)
        entry = {"device": hostname, "ip": ip, "push_ok": bool(result.get("ok"))}
        try:
            # Netmiko's default read_timeout is 10s. This read happens moments
            # after `write memory`, and on an emulated device that leaves the
            # box slow for tens of seconds — measured at 5.5s idle and >16s
            # straight after a save. A timeout here loses the evidence, which
            # is the one thing this function exists to preserve.
            from modules.settings_schema import get_setting
            timeout = get_setting("nsot_config_read_timeout", 120)
            post = with_temp_connection(
                dev, lambda c: c.send_command("show running-config",
                                              read_timeout=timeout))
            from modules.nsot.recreate import operations as _sla_ops
            ctx.failure_sla[ip] = _sla_ops(post)
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
            # A fresh connection could not read it either, so the pooled one is
            # certainly no better. Drop it rather than leave a suspect session
            # for the rollback — which is the next thing to use it.
            close_persistent_connection(ip, ctx.connections_pool, ctx.pool_lock)
            log.warning("pipeline[failure-state]: dropped the pooled "
                        "connection to %s", hostname)
        ctx.failure_state[ip] = entry


#: What a rollback achieved on one device (C112). Only the first two leave
#: the device where it was before the push.
ROLLBACK_STATES = {
    "restored": "the undo program was sent and a read-back finds nothing left to undo",
    "nothing_to_undo": "nothing of the push landed, so there was nothing to undo",
    "incomplete": "the undo was sent and a read-back still finds pushed lines on the device",
    "sent_unverified": "the undo was sent and the device could not be read back",
    "failed": "sending the undo program failed",
    "not_attempted": "no rollback could be built (no pre-change snapshot, or no device)",
}
ROLLBACK_OK = ("restored", "nothing_to_undo")


def _rollback_readback(ctx, dev, pushed, pre_cfg, units=(), recreated=()) -> dict:
    """Read the device back after its undo (fresh connection, as the failure
    capture does) and compute the undo AGAIN against what landed now: an
    empty program means the push is gone."""
    from modules.connection import with_temp_connection
    from modules.nsot.deploy import rollback_commands
    from modules.settings_schema import get_setting

    try:
        timeout = get_setting("nsot_config_read_timeout", 120)
        post = with_temp_connection(
            dev, lambda c: c.send_command("show running-config", read_timeout=timeout))
    except Exception as exc:                    # noqa: BLE001
        return {"state": "sent_unverified",
                "detail": f"the device could not be read back: {exc}", "remaining": []}
    pre_set = {l.rstrip() for l in (pre_cfg or "").splitlines()}
    landed = [l.rstrip() for l in (post or "").splitlines()
              if l.strip() and l.rstrip() not in pre_set]
    remaining = rollback_commands(pushed, pre_cfg, landed=landed)
    if units:
        # A removed line that is still missing is an undo still needed.
        from modules.nsot.removal import restore_program
        remaining = remaining + restore_program(list(units), pre_cfg, post or "")
    if recreated:
        # A re-created IP SLA operation not back at its OLD definition: its
        # restore is still needed.
        from modules.nsot.recreate import undo_program, unmatched
        off = {u["number"] for u in unmatched(list(recreated), post or "", "old")}
        if off:
            remaining = remaining + undo_program(
                [u for u in recreated if u["number"] in off], pre_cfg)
    if remaining:
        return {"state": "incomplete", "remaining": remaining,
                "detail": f"{len(remaining)} line(s) of undo still needed after the rollback"}
    return {"state": "restored", "remaining": [],
            "detail": "read back: nothing of the push remains"}


def _unrestorable_is_incomplete(ctx, ip: str, unrestorable: list) -> None:
    """A re-created operation whose old definition could not be put back
    leaves the device NOT back, whatever else the undo did: never drawn as
    restored or as nothing to undo."""
    if unrestorable and ctx.rollback_outcome.get(ip, {}).get("state") in (
            "restored", "nothing_to_undo"):
        ctx.rollback_outcome[ip] = {
            "state": "incomplete", "remaining": [f"ip sla {n}" for n in unrestorable],
            "detail": ctx.rollback_failures.get(ip) or "a re-created operation could not be restored"}


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

    from modules.nsot.deploy import (assert_rollback_provenance,
                                     landed_leaves, rollback_commands)

    for ip in targets:
        dev = next((d for d in ctx.selected_devices if d["ip"] == ip), None)
        if not dev:
            ctx.rollback_outcome[ip] = {"state": "not_attempted", "remaining": [],
                                        "detail": "the device is not in this run's inventory"}
            continue
        hostname = dev.get("hostname", ip)
        try:
            pre_cfg = _load_pre_change_file(ip)
            if not pre_cfg:
                log.error(
                    "pipeline[rollback]: no pre-change file for %s — cannot restore", hostname
                )
                # Recorded, not only logged: it used to be in no list at all.
                ctx.rollback_outcome[ip] = {
                    "state": "not_attempted", "remaining": [],
                    "detail": "no pre-change snapshot, so no undo program could be built"}
                continue

            # Merge-computed, not replayed. Replaying the pre-change snapshot
            # is a MERGE: it re-applies lines and removes none. IOS omits
            # "no shutdown" from an up interface, so a snapshot taken before a
            # shutdown has no line to re-apply — the replay would leave the
            # interface down, save the config, and report success.
            pushed = ctx.rendered_commands.get(ip, [])
            # Mode B: the tail is the removals, undone by re-adding the device's
            # own lines. Treated as additions, `no X` would read as never
            # applied (it is not in `landed`), be left undone, and the read-back
            # would still say "restored".
            removal = (ctx.removals or {}).get(ip) or {}
            from modules.nsot.removal import restore_program, split_pushed
            pushed = split_pushed(pushed, removal.get("commands") or [])
            re_add = (restore_program(removal.get("units") or [], pre_cfg, "")
                      if removal.get("units") else [])
            # Before the removals, the re-created IP SLA operations: undone by
            # restoring each OLD definition from the snapshot (delete what is
            # there, put the device's own lines back), never by inverting the
            # program, whose `no ip sla N` has no line-by-line inverse.
            from modules.nsot.recreate import moved, operations, undo_program
            pushed = split_pushed(pushed, removal.get("recreate_commands") or [])
            recreated = removal.get("recreates") or []
            sla_not_undone = []
            if recreated and ip in ctx.failure_sla:
                # Undo what LANDED: an operation the device still holds as it
                # was was never deleted (the push stopped before its
                # `no ip sla N`), and restoring it would delete and re-create a
                # running operation nothing touched. With no read-back, every
                # one is restored, the conservative answer as for additions.
                reached = moved(recreated, ctx.failure_sla[ip])
                sla_not_undone = [f"ip sla {u['number']} (never deleted: the push stopped "
                                  "before it)" for u in recreated if u not in reached]
                recreated = reached
            # An operation the live snapshot lacks (deleted by hand after the
            # capture) cannot be put back from it: named, and never allowed to
            # stop the rest of the undo.
            have = operations(pre_cfg)
            unrestorable = [u["number"] for u in recreated
                            if not (have.get(u["number"]) or {}).get("body")]
            recreated = [u for u in recreated if u["number"] not in unrestorable]
            if unrestorable:
                ctx.rollback_failures[ip] = (
                    "not in the pre-change snapshot, so the old definition cannot be put "
                    "back: " + ", ".join(f"ip sla {n}" for n in unrestorable))
            restore_ops = undo_program(recreated, pre_cfg) if recreated else []
            # What actually reached the device, from the capture that ran
            # moments ago. On a partial push this is not the same as what was
            # pushed, and undoing a line the device rejected would send a
            # command answering something that never happened.
            state = ctx.failure_state.get(ip) or {}
            landed = state.get("landed") if state.get("landed") is not None else None
            undo = rollback_commands(pushed, pre_cfg, landed=landed)
            _applied, rejected = landed_leaves(pushed, landed)
            if rejected or sla_not_undone:
                ctx.rollback_not_undone[ip] = [e.line for e in rejected] + sla_not_undone
                log.info("pipeline[rollback]: %s — %d line(s) not undone, never "
                         "applied: %s", hostname, len(rejected),
                         [e.line for e in rejected])
            # `pre_cfg` too: without it the guard cannot tell a section this
            # push CREATED from one it merely entered, and refuses the single
            # negation that undoes a creation. Omitting it only ever makes the
            # guard stricter, which is why it is optional there and required
            # here -- this is the caller that knows.
            assert_rollback_provenance(undo, pushed, pre_cfg)
            undo = undo + restore_ops + re_add
            ctx.rollback_commands[ip] = undo

            if not undo:
                log.info("pipeline[rollback]: %s — nothing to undo", hostname)
                ctx.rollback_outcome[ip] = {"state": "nothing_to_undo", "remaining": [],
                                            "detail": ROLLBACK_STATES["nothing_to_undo"]}
                _unrestorable_is_incomplete(ctx, ip, unrestorable)
                continue

            # Rollback is EXEMPT from the dangerous-command gate, structurally:
            # it never passes through stage 3. Rolling back an authorised
            # `no shutdown` produces `shutdown`, and a gate that blocked the
            # repair would leave the device in the failed state it was called
            # to fix. assert_rollback_provenance() above is the authorisation —
            # every line inverts something this deploy just pushed. Recorded so
            # the exemption is visible rather than implicit.
            would_trip = dangerous_commands(undo)
            if would_trip:
                ctx.rollback_dangerous[ip] = would_trip
                log.warning("pipeline[rollback]: %s — %d rollback line(s) would "
                            "trip the CI gate and are exempt by provenance: %s",
                            hostname, len(would_trip), would_trip)

            conn = get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)
            _restore_config(conn, undo)
            ctx.rolled_back_ips.append(ip)
            log.info("pipeline[rollback]: %s undo sent, %d command(s): %s",
                     hostname, len(undo), undo)
            # Sent is not restored: read it back.
            ctx.rollback_outcome[ip] = _rollback_readback(
                ctx, dev, pushed, pre_cfg, removal.get("units") or [], recreated)
            _unrestorable_is_incomplete(ctx, ip, unrestorable)
            if ctx.rollback_outcome[ip]["state"] != "restored":
                log.error("pipeline[rollback]: %s NOT confirmed restored: %s", hostname,
                          ctx.rollback_outcome[ip]["detail"])
        except Exception as exc:
            ctx.rollback_failures[ip] = str(exc)
            ctx.rollback_outcome[ip] = {"state": "failed", "remaining": [],
                                        "detail": str(exc)}
            log.error("pipeline[rollback]: FAILED to restore %s: %s", hostname, exc)

    # Rollback restored the DEVICE. The intent still says the change should be
    # there, so without this the next plan proposes exactly what just failed.
    _note_rolled_back_intent(ctx)
    ctx.rollback_performed = True
    # "rolled_back" only when every device the push was attempted on is back.
    not_back = [ip for ip, o in ctx.rollback_outcome.items()
                if o.get("state") not in ROLLBACK_OK]
    ctx.final_status = "rollback_failed" if not_back else "rolled_back"


def _note_rolled_back_intent(ctx: PipelineContext) -> None:
    """Mark each rolled-back device's current intent, so a replan refuses."""
    import os as _os

    try:
        from modules.config import get_list_data_dir
        from modules.nsot import hostvars as _hv
    except ImportError:
        return

    repo = _os.path.join(get_list_data_dir(_list_of(ctx)), "config_repo")
    if not _os.path.isdir(repo):
        return
    for ip in ctx.rolled_back_ips:
        dev = next((d for d in ctx.selected_devices if d["ip"] == ip), None)
        if not dev:
            continue
        hostname = dev.get("hostname", ip)
        try:
            commits = _hv.intent_commits(repo, hostname, limit=1)
            # The ADDITIONS only. The block stands while its lines are still
            # among what a plan would send, and a plan's additions never hold
            # a removal line, so recording the removal tail would make a
            # combined program's block lift at once (Mode B, 7.3 step 2).
            from modules.nsot.removal import split_pushed
            removal = ((ctx.removals or {}).get(ip) or {}).get("commands") or []
            _hv.record_rolled_back(
                repo, hostname,
                commits[0]["sha"] if commits else "",
                reason=ctx.error or "deploy rolled back",
                pipeline_id=ctx.config_id,
                commands=split_pushed(ctx.rendered_commands.get(ip, []), removal))
        except Exception as exc:              # noqa: BLE001
            log.error("pipeline[rollback]: could not note rolled-back intent "
                      "for %s: %s", hostname, exc)


def _restore_config(conn, commands) -> None:
    """Send an already-computed rollback program through config mode.

    Takes a **command list**, not a config to replay. The name and the previous
    docstring both said "replace"; ``send_config_set`` merges, and nobody
    compared the two. See :func:`modules.nsot.deploy.rollback_commands`.
    """
    if isinstance(commands, str):
        lines = [line for line in commands.splitlines()
                 if line.strip()
                 and not any(line.startswith(s) for s in _SKIP_STARTSWITH)]
    else:
        lines = list(commands)
    if lines:
        conn.enable()
        # The same guard on the rollback path. A rejected rollback line
        # reported as a successful rollback is worse than a rejected forward
        # push: the forward failure at least leaves someone looking at it.
        conn.send_config_set(lines, read_timeout=120,
                             error_pattern=IOS_ERROR_PATTERN)
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

    from modules.config import get_list_data_dir
    from modules.nsot import manifest as _manifest
    from modules.nsot.repo import GoldenItem, save_golden, stage_post_deploy

    repo = _os.path.join(get_list_data_dir(_list_of(ctx)), "config_repo")
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

    # Park each capture where a crashed batch can recover it. Between here and
    # the batch's commit the config exists on the device and in this process
    # and nowhere else, and the device cannot be re-read later to reconstruct
    # it — by then it may have changed again.
    for item in items:
        stage_post_deploy(repo, item.hostname, item.config_text)

    if ctx.defer_golden:
        # A batch is an EVENT. One caller, one commit, one baseline — so the
        # batch collects captures and commits once at the end rather than each
        # device committing for itself. "One call is one commit" is preserved
        # rather than special-cased: this simply is not the caller.
        ctx.golden_pending = [
            {"hostname": i.hostname, "config_text": i.config_text,
             "mgmt_ip": i.mgmt_ip, "netbox_id": i.netbox_id,
             "device_uid": i.device_uid}
            for i in items]
        ctx.golden_result = {"ok": True, "commit": "", "deferred": True,
                             "changed": [i.hostname for i in items]}
        log.info("pipeline[8.5/save_golden]: %d capture(s) handed to the batch",
                 len(items))
        return

    # allow_new=False: a pipeline deploy targets a device the inventory
    # already knows. Reaching here with no identity is a bug, not a new device.
    result = save_golden(_list_of(ctx), items, source="pipeline",
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
                # Every protocol read, by name (C62): what the verify checked.
                "routing_protocols_pre":  _protocol_counts(pre_nbr),
                "routing_protocols_post": _protocol_counts(post_nbr),
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

def _conn_of(conn):
    """The session to send the next read on. *conn* is a session, or a
    callable returning one from the pool (C272): a read that fails spends its
    session (`config_read.SPENT_ATTR`), and asking the pool for each read gets
    a new one, so one untrustworthy read does not make every later read in a
    snapshot refuse."""
    if callable(conn) and not hasattr(conn, "send_command"):
        return conn()
    return conn


def _session_for(ctx, dev):
    """The pool's session for *dev*, asked again at every read (`_conn_of`)."""
    from modules.connection import get_persistent_connection
    return lambda: get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)


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
            _conn_of(conn), "show interfaces | include (line protocol|Internet address)"
        )                                             # _INTERFACES_READ
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
        route_out = run_device_command(_conn_of(conn), "show ip route summary")
        total     = _parse_route_total(route_out)
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
    text = show_ip_protocols or ""
    # RIP's OWN section: from `Routing Protocol is "rip"` to the next
    # protocol. Both platforms print an "application" pseudo-protocol first
    # with an empty sources table, and reading the first table found is what
    # made every RIP device read 0 (C65, measured on s1, 2026-09-27).
    m = re.search(r'^Routing Protocol is "rip"\s*$', text, re.MULTILINE)
    if not m:
        return None
    end = re.search(r"^Routing Protocol is ", text[m.end():], re.MULTILINE)
    text = text[m.start():m.end() + end.start()] if end else text[m.start():]
    lines = text.splitlines()
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


def _parse_bgp_summary(out: str) -> Optional[dict]:
    """Established and configured BGP peers, from THE one reader.

    ``modules.topology.parse_bgp_summary`` reads the rows. This copy of the
    job used to have its own pattern, which expected eight fields where the
    device prints ten and so counted nothing (C64), while topology's read the
    same output correctly: two readers of one output disagreeing. Returns
    None when BGP is not running, else ``{"established", "configured",
    "peers"}``.
    """
    if "BGP router identifier" not in (out or ""):
        return None
    from modules.topology import parse_bgp_summary

    peers = parse_bgp_summary(out)["peers"]
    return {"established": sum(1 for p in peers if p["established"]),
            "configured": len(peers), "peers": peers}


def _parse_route_total(route_summary: str) -> int:
    """Routes in ``show ip route summary``: networks PLUS subnets.

    The Total row's first column is Networks (classful major networks) and
    the second Subnets (C66, measured 2026-09-27: r3's ``Total 4 26 ...`` is
    30 routes, where the first version read 4, so a device could lose every
    OSPF subnet and keep its count). -1 when the row cannot be read.
    """
    m = re.search(r"^Total\s+(\d+)\s+(\d+)", route_summary or "", re.MULTILINE)
    return int(m.group(1)) + int(m.group(2)) if m else -1


def _parse_ospf_neighbor_rows(out: str) -> list:
    """``[{"neighbor_id", "state"}]`` from `show ip ospf neighbor` or
    `show ospfv3 neighbor`: both print Neighbor ID, Pri, State, ... and a
    row starts with the neighbour's router ID (measured on r1 and r3,
    tests/fixtures/operational/)."""
    rows = []
    for line in (out or "").splitlines():
        fields = line.split()
        if len(fields) >= 3 and re.match(r"^\d+\.\d+\.\d+\.\d+$", fields[0]):
            rows.append({"neighbor_id": fields[0], "state": fields[2]})
    return rows


def _parse_ripng_next_hops(out: str) -> list:
    """RIPng's neighbours: `show ipv6 rip next-hops`, one row per next hop
    (``FE80::…/GigabitEthernet3 [5 paths]``). RIPng has no adjacency table,
    and "learned a route" is the wrong evidence: r1 hears s1 and installs
    none, because OSPFv3 carries the same prefixes at a better distance
    (measured 2026-09-27). The next hops are what it is hearing."""
    hops = []
    for line in (out or "").splitlines():
        m = re.match(r"^\s*([0-9A-Fa-f:.]+)/(\S+)\s+\[(\d+) paths?\]", line)
        if m:
            hops.append({"address": m.group(1), "interface": m.group(2),
                         "paths": int(m.group(3))})
    return hops


# Probe order decides only which protocol is PRIMARY, for callers that read
# one name. Every protocol present is read and verified (C62).
_PROTOCOL_ORDER = ("bgp", "ospf", "eigrp", "isis", "rip", "ospfv3", "ripng")

#: The command each protocol's neighbour state is read with, so a read that
#: failed names the protocol it leaves unknown (C272).
_ROUTING_READS = {"bgp": "show bgp all summary", "ospf": "show ip ospf neighbor",
                  "eigrp": "show ip eigrp neighbors", "isis": "show isis neighbors",
                  "ospfv3": "show ospfv3 neighbor", "ripng": "show ipv6 rip next-hops",
                  "rip": "show ip protocols"}
_INTERFACES_READ = "show interfaces | include (line protocol|Internet address)"


def _read_routing_protocols(conn, unreadable: dict = None) -> dict:
    """Every routing protocol the device answers for, with its neighbour
    count: ``{name: {"count", "output", ...}}``.

    Each protocol is read on its own, so a device running OSPF and BGP (r3,
    r4) or OSPF and RIP (r1, r2) is verified for both. The first version
    returned the first protocol it found, so OSPF was never read on r3 and
    r4 and RIP never on r1 and r2 (C62).
    """
    from modules.commands import run_device_command

    # A read that failed is RECORDED with its reason (C272): it used to be
    # `pass`, so a protocol whose read could not be trusted vanished, read
    # before the push as "not running" (never checked) and after it as gone.
    unreadable = {} if unreadable is None else unreadable
    found: dict = {}

    try:
        # BOTH address families: r3's intent declares an IPv6 peer too, and
        # `show ip bgp summary` lists IPv4 sessions only.
        out = run_device_command(_conn_of(conn), "show bgp all summary")
        bgp = _parse_bgp_summary(out)
        if bgp is not None:
            found["bgp"] = {"count": bgp["established"], "configured": bgp["configured"],
                            "peers": bgp["peers"], "output": out[:2000]}
    except Exception as exc:                          # noqa: BLE001
        unreadable["show bgp all summary"] = f"{type(exc).__name__}: {exc}"

    try:
        out = run_device_command(_conn_of(conn), "show ip ospf neighbor")
        if out.strip() and "Neighbor ID" in out:
            # Counts adjacencies in any state: 2WAY between DROTHERs is a
            # steady state on a broadcast segment (r1 and s3 show three), so
            # counting only FULL would be wrong. The state is kept per row.
            rows = _parse_ospf_neighbor_rows(out)
            found["ospf"] = {"count": len(rows),
                             "states": [r["state"] for r in rows],
                             "neighbors": [r["neighbor_id"] for r in rows],
                             "output": out[:2000]}
    except Exception as exc:                          # noqa: BLE001
        unreadable["show ip ospf neighbor"] = f"{type(exc).__name__}: {exc}"

    try:
        out = run_device_command(_conn_of(conn), "show ip eigrp neighbors")
        if out.strip() and "H " in out:
            rows = [ln for ln in out.splitlines()
                    if re.match(r"\s*\d+\s+\d+\.\d+\.\d+\.\d+", ln)]
            found["eigrp"] = {"count": len(rows), "output": out[:2000]}
    except Exception as exc:                          # noqa: BLE001
        unreadable["show ip eigrp neighbors"] = f"{type(exc).__name__}: {exc}"

    try:
        out = run_device_command(_conn_of(conn), "show isis neighbors")
        if out.strip() and "System Id" in out:
            rows = [ln for ln in out.splitlines()
                    if ln.strip() and not ln.strip().startswith("System")
                    and not ln.strip().startswith("IS-IS")]
            found["isis"] = {"count": len(rows), "output": out[:2000]}
    except Exception as exc:                          # noqa: BLE001
        unreadable["show isis neighbors"] = f"{type(exc).__name__}: {exc}"

    try:
        out = run_device_command(_conn_of(conn), "show ospfv3 neighbor")
        if "Neighbor ID" in (out or ""):
            rows = _parse_ospf_neighbor_rows(out)
            found["ospfv3"] = {"count": len(rows), "states": [r["state"] for r in rows],
                               "neighbors": [r["neighbor_id"] for r in rows],
                               "output": out[:2000]}
    except Exception as exc:                          # noqa: BLE001
        unreadable["show ospfv3 neighbor"] = f"{type(exc).__name__}: {exc}"

    try:
        out = run_device_command(_conn_of(conn), "show ipv6 rip next-hops")
        if "RIP process" in (out or ""):
            hops = _parse_ripng_next_hops(out)
            found["ripng"] = {"count": len(hops), "next_hops": hops, "output": out[:2000]}
    except Exception as exc:                          # noqa: BLE001
        unreadable["show ipv6 rip next-hops"] = f"{type(exc).__name__}: {exc}"

    # RIP is distance-vector: no adjacencies. Its equivalent is the Routing
    # Information Sources table under RIP's own section of `show ip protocols`
    # (C65: not the first such table, which is the "application"
    # pseudo-protocol's).
    try:
        out = run_device_command(_conn_of(conn), "show ip protocols")
        sources = _parse_rip_sources(out)
        if sources is not None:
            found["rip"] = {"count": len(sources), "sources": sources,
                            "output": out[:2000]}
    except Exception as exc:                          # noqa: BLE001
        unreadable["show ip protocols"] = f"{type(exc).__name__}: {exc}"

    return found


def _detect_routing_neighbors(conn) -> dict:
    """Every routing protocol's neighbour state, plus a PRIMARY one.

    Returns ``{"protocol", "count", "output", "protocols": {name: {...}}}``.
    ``protocols`` holds every protocol present, and verify compares each
    (C62). ``protocol`` and ``count`` name the first present in
    ``_PROTOCOL_ORDER``, kept for callers that log one name; ``count`` is -1
    and ``protocol`` "none" when no routing protocol answers, which tells
    verify to record a skip rather than a pass.
    """
    unreadable: dict = {}
    protocols = _read_routing_protocols(conn, unreadable)
    primary = next((p for p in _PROTOCOL_ORDER if p in protocols), None)
    if primary is None:
        return {"protocol": "none", "count": -1, "output": "", "protocols": {},
                "unreadable": unreadable}
    result = {"protocol": primary, "protocols": protocols, "unreadable": unreadable}
    result.update(protocols[primary])
    return result


def _unreadable(snap: dict) -> list:
    """What an operational snapshot could not read, each `command: reason`
    (C272). Before a push it refuses the deploy with nothing sent; after it,
    verify says so rather than reading the gap as a protocol down or a check
    passed."""
    out = [f"`{cmd}`: {why}" for cmd, why in sorted(
        ((snap.get("routing_neighbors") or {}).get("unreadable") or {}).items())]
    for key, cmd in (("interfaces", _INTERFACES_READ), ("routes", "show ip route summary")):
        err = (snap.get(key) or {}).get("error")
        if err:
            out.append(f"`{cmd}`: {err}")
    if snap.get("running_config_error"):
        out.append(f"`show running-config`: {snap['running_config_error']}")
    return out


def _unread_protocol(nbr: dict, protocol: str) -> str:
    """'`<command>`: <reason>' when *protocol*'s read failed in this neighbour
    snapshot, else ''."""
    cmd = _ROUTING_READS.get(protocol, "")
    why = (nbr.get("unreadable") or {}).get(cmd)
    return f"`{cmd}`: {why}" if why else ""


def _protocol_counts(snapshot: dict) -> dict:
    """``{protocol: count}`` from a neighbour snapshot, old shape or new."""
    per = snapshot.get("protocols")
    if per:
        return {name: info.get("count", -1) for name, info in per.items()}
    name, count = snapshot.get("protocol"), snapshot.get("count", -1)
    return {name: count} if name and name != "none" and count >= 0 else {}


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
