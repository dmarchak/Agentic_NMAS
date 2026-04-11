"""
agent_runner.py — Background agent task executor

Runs a daemon thread that drains the event monitor queue and executes each
event as a full AI agent task — no browser or SSE required.  The AI uses the
same run_chat() generator as the normal chat flow, so it has access to every
tool (SSH, Jenkins, Ansible, golden configs, compliance, etc.).

Each background task gets its own fresh session so it never pollutes the
user's chat history.  Results are stored in a ring-buffer and persisted to
data/agent_activity.json so they survive server restarts.

Flask exposes:
  GET  /ai/agent_log           — return recent activity entries
  POST /ai/agent_run           — manually trigger a background task (body: {"task": "..."})
  POST /ai/agent_pause         — pause autonomous processing (events still queue)
  POST /ai/agent_resume        — resume autonomous processing
"""

import json
import logging
import os
import threading
import time
import uuid
from typing import Optional

log = logging.getLogger(__name__)

MAX_LOG_ENTRIES    = 100
_POLL_INTERVAL     = 30        # seconds between event-queue drains
_DRIFT_CHECK_INTERVAL = 4 * 3600   # run drift check every 4 hours
_STARTUP_GRACE     = 300       # seconds after startup before first drift check
_ACTIVITY_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "agent_activity.json"
)
_DRIFT_STATE_PATH  = os.path.join(
    os.path.dirname(__file__), "..", "data", "drift_state.json"
)
_TRAP_STATE_PATH   = os.path.join(
    os.path.dirname(__file__), "..", "data", "trap_analysis_state.json"
)
_TRAP_FLAP_WINDOW      = 15     # default: wait 15 s before dispatching AI task (overridden by agent_timers)
_TRAP_ALERT_AGE_MAX    = 3600   # ignore traps older than 1 hour at startup scan
_MAX_PROCESSED_IDS     = 500    # cap on persisted seen-trap-ID set size

# Pending flap-detection timers: key (src_ip, iface_or_peer) → threading.Timer
# A timer fires after _TRAP_FLAP_WINDOW seconds to dispatch the AI task.
# A matching recovery trap cancels the timer (flap detected — no task needed).
_pending_trap_timers: dict = {}
_pending_trap_lock = threading.Lock()

# Trap types that trigger full AI investigation
_TRAP_ACTIONABLE_DOWN = frozenset({
    "linkDown", "ciscoLinkDown",
    "bgpBackwardTransition",
    "ciscoPowerSupplyFailed", "ciscoFanFailed",
})
_TRAP_OSPF_CHANGE = frozenset({
    "ospfNbrStateChange", "ciscoOspfNbrStateChange", "ospfVirtNbrStateChange",
})
# Recovery traps — log informational entry, no AI needed
_TRAP_RECOVERY = frozenset({
    "linkUp", "ciscoLinkUp", "bgpEstablished",
})

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
_activity_log: list[dict] = []
_log_lock = threading.Lock()

_processor_thread: Optional[threading.Thread] = None
_stop_event   = threading.Event()
_paused       = threading.Event()   # set = paused, clear = running

# Rich live status for the currently executing background task (None when idle)
_running_task: Optional[dict] = None
_task_lock = threading.Lock()

# Device access — injected by start_agent_loop()
_devices_loader    = None
_status_cache: dict = {}
_connections_pool: dict = {}
_pool_lock         = None

# User activity tracking — background tasks yield when user is actively chatting
_last_user_activity: float = 0.0
_USER_IDLE_SECONDS  = 90   # wait this long after last user message before starting a background task

# Event types handled by the AI agent via run_background_task.
# Note: "config_drift" and "empty_variables" are handled directly in Python
# (_run_drift_check, _run_variable_discovery) and do NOT go through this set.
AUTO_HANDLE = {"jenkins_failure", "missing_golden_configs"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_activity_log() -> list[dict]:
    """Return all activity log entries (newest first)."""
    with _log_lock:
        return list(reversed(_activity_log))


def get_status() -> dict:
    """Return the agent's current operational status including live task detail."""
    with _task_lock:
        task = dict(_running_task) if _running_task else None
    return {
        "running":        bool(_processor_thread and _processor_thread.is_alive()),
        "paused":         _paused.is_set(),
        "user_active":    _user_is_active(),
        "current_task":   task,
    }


def notify_user_active() -> None:
    """
    Call this whenever the user sends a chat message.
    - Blocks new background tasks for _USER_IDLE_SECONDS.
    - Stops any background task currently in progress so it doesn't compete
      with the user's chat for SSH connections or API quota.
    """
    global _last_user_activity
    _last_user_activity = time.time()

    # If a background task is running, send it a stop signal so it finishes
    # at the next inter-tool boundary rather than continuing to run concurrently.
    with _task_lock:
        task = _running_task
    if task:
        try:
            from modules.ai_assistant import stop_session
            sid = task.get("session_id", "")
            if sid:
                stop_session(sid)
                log.info("agent_runner: stopped background session %s (user became active)", sid)
        except Exception:
            pass


def _user_is_active() -> bool:
    """Return True if the user sent a message within the idle window."""
    return (time.time() - _last_user_activity) < _USER_IDLE_SECONDS


def pause_agent() -> None:
    _paused.set()
    log.info("agent_runner: paused")


def resume_agent() -> None:
    _paused.clear()
    log.info("agent_runner: resumed")


def trigger_task(task: str) -> dict:
    """
    Manually queue a background task (returns immediately; task runs async).
    The task is submitted to a worker thread so it doesn't block the caller.
    """
    if not _devices_loader:
        return {"error": "agent_runner not initialized"}
    t = threading.Thread(
        target=run_background_task,
        args=(task,),
        kwargs={"trigger_event": {"type": "manual"}},
        daemon=True,
        name=f"agent-task-{uuid.uuid4().hex[:6]}",
    )
    t.start()
    return {"queued": True, "task": task[:200]}


def start_agent_loop(
    devices_loader,
    status_cache: dict,
    connections_pool: dict,
    pool_lock,
) -> None:
    """Start the background agent processor daemon (idempotent)."""
    global _processor_thread, _devices_loader, _status_cache, _connections_pool, _pool_lock

    _devices_loader   = devices_loader
    _status_cache     = status_cache
    _connections_pool = connections_pool
    _pool_lock        = pool_lock

    _load_persisted_log()

    if _processor_thread and _processor_thread.is_alive():
        return

    _stop_event.clear()
    _paused.clear()
    _processor_thread = threading.Thread(
        target=_processor_loop, daemon=True, name="agent-runner"
    )
    _processor_thread.start()

    # Register real-time trap callback so new traps trigger the agent immediately.
    try:
        from modules.snmp_collector import set_trap_callback
        set_trap_callback(_on_trap_received)
        log.info("agent_runner: real-time trap callback registered")
    except Exception as exc:
        log.warning("agent_runner: could not register trap callback: %s", exc)

    # Startup scan — mark any pre-existing traps as seen so we don't re-alert
    # on traps from a previous session, but do dispatch for very recent ones.
    threading.Thread(
        target=_run_trap_analysis, daemon=True, name="trap-startup-scan"
    ).start()

    log.info("agent_runner: started")


def stop_agent_loop() -> None:
    _stop_event.set()


# ---------------------------------------------------------------------------
# Core task runner
# ---------------------------------------------------------------------------

def run_background_task(task: str, trigger_event: Optional[dict] = None) -> dict:
    """
    Execute one agent task using a fresh chat session.

    Consumes the run_chat() SSE generator synchronously — every tool call the
    AI makes is executed in real time, exactly as it would be in the browser.
    Returns a summary dict and appends it to the activity log.
    """
    global _running_task
    from modules.ai_assistant import run_chat  # imported here to avoid circular at module load

    if not _devices_loader:
        return {"error": "agent_runner not initialized"}

    session_id  = f"__bg_{uuid.uuid4().hex[:8]}__"
    started_at  = time.strftime("%Y-%m-%d %H:%M:%S")
    started_ts  = time.time()
    trigger_type = (trigger_event or {}).get("type", "manual")

    text_parts:  list[str]  = []
    tools_used:  list[str]  = []
    errors:      list[str]  = []
    cost_usd:    float      = 0.0

    # Strip the [AUTONOMOUS TASK] / [SCHEDULED ...] prefix for display
    display_task = task
    for prefix in ("[AUTONOMOUS TASK] ", "[SCHEDULED DRIFT CHECK] ", "[AGENT EVENT] "):
        if display_task.startswith(prefix):
            display_task = display_task[len(prefix):]
            break

    def _update_status(**kwargs):
        with _task_lock:
            if _running_task is not None:
                _running_task.update(kwargs)

    with _task_lock:
        _running_task = {
            "session_id":    session_id,
            "task":          display_task[:300],
            "trigger":       trigger_type,
            "started_at":    started_at,
            "started_ts":    started_ts,
            "elapsed_s":     0,
            "current_tool":  None,
            "tools_called":  [],
            "tool_call_count": 0,
            "last_text":     "",
            "cost_usd":      0.0,
        }

    # Prepend a hard constraint block so autonomous trigger rules in the system
    # prompt cannot override the explicit steps in this background task.
    _BACKGROUND_CONSTRAINT = (
        "BACKGROUND TASK MODE — strict constraints:\n"
        "• Execute ONLY the numbered steps listed below. Nothing else.\n"
        "• Do NOT follow autonomous trigger rules (CONFIG PUSH, GOLDEN CONFIG, PLAYBOOK, etc.).\n"
        "• Do NOT investigate or fix Jenkins failures unless the task explicitly says to.\n"
        "• Do NOT run Jenkins, run_jenkins_checks, save_golden_config,\n"
        "  capture_pre_change_snapshot, or compliance checks unless the task explicitly says to.\n"
        "• Applying a direct restoration fix (e.g. 'no shutdown') is allowed when the task says so —\n"
        "  but do NOT trigger Jenkins, golden config saves, or snapshots afterward.\n"
        "• Do NOT ask for permission, confirmation, or approval at any point.\n"
        "  Do NOT say 'Should I continue?', 'Shall I proceed?', 'Would you like me to…', or any\n"
        "  similar phrase.  There is no human watching — just complete the task end-to-end.\n"
        "• When the steps are complete, STOP immediately.\n"
        "─────────────────────────────────────────────\n\n"
    )
    constrained_task = _BACKGROUND_CONSTRAINT + task

    log.info("agent_runner: starting task [%s]: %s", session_id, task[:80])

    try:
        for event in run_chat(
            session_id        = session_id,
            user_message      = constrained_task,
            devices_loader    = _devices_loader,
            status_cache      = _status_cache,
            connections_pool  = _connections_pool,
            pool_lock         = _pool_lock,
        ):
            # Stop immediately if the user started chatting mid-task
            if _user_is_active():
                try:
                    from modules.ai_assistant import stop_session
                    stop_session(session_id)
                except Exception:
                    pass
                log.info("agent_runner: interrupting task %s — user became active", session_id)
                break

            etype = event.get("type")
            if etype == "text":
                chunk = event.get("content", "")
                text_parts.append(chunk)
                # Keep a rolling window of the last ~200 chars of AI prose
                combined = "".join(text_parts)
                _update_status(
                    last_text  = combined[-200:].lstrip(),
                    elapsed_s  = round(time.time() - started_ts),
                )
            elif etype == "tool_start":
                tool_name = event.get("tool", "")
                label     = event.get("label", tool_name)
                tools_used.append(tool_name)
                log.debug("agent_runner [%s]: tool → %s", session_id, tool_name)
                _update_status(
                    current_tool     = label or tool_name,
                    tools_called     = list(dict.fromkeys(tools_used)),
                    tool_call_count  = len(tools_used),
                    elapsed_s        = round(time.time() - started_ts),
                )
            elif etype == "tool_result":
                # Tool finished — clear the "currently executing" indicator
                _update_status(
                    current_tool = None,
                    elapsed_s    = round(time.time() - started_ts),
                )
            elif etype == "usage":
                cost_usd += event.get("cost_usd", 0.0)
                _update_status(cost_usd=round(cost_usd, 6))
            elif etype == "error":
                errors.append(event.get("content", ""))
            elif etype == "interrupted":
                errors.append("Task was interrupted.")
                break
    except Exception as exc:
        errors.append(str(exc))
        log.exception("agent_runner: task error: %s", exc)
    finally:
        with _task_lock:
            _running_task = None

    summary = "".join(text_parts).strip()
    if len(summary) > 3000:
        summary = summary[:3000] + "…"

    entry = {
        "id":             session_id,
        "started_at":     started_at,
        "task":           task[:300],
        "trigger":        trigger_type,
        "tools_used":     list(dict.fromkeys(tools_used)),   # ordered dedup
        "tool_call_count": len(tools_used),
        "success":        not bool(errors),
        "errors":         errors[:5],
        "cost_usd":       round(cost_usd, 6),
        "summary":        summary,
    }

    _append_activity(entry)
    log.info(
        "agent_runner: done [%s] tools=%d success=%s cost=$%.4f",
        session_id, len(tools_used), entry["success"], cost_usd,
    )
    return entry


# ---------------------------------------------------------------------------
# Event → task translation
# ---------------------------------------------------------------------------

def _build_task_prompt(event: dict) -> Optional[str]:
    """Convert an event dict into an agent task prompt string."""
    etype = event.get("type")
    meta  = event.get("metadata", {})

    if etype == "jenkins_failure":
        job = meta.get("job", "unknown")
        num = meta.get("build_number", "?")
        return (
            f'[AUTONOMOUS TASK] The Jenkins pipeline "{job}" build #{num} has FAILED. '
            f"Retrieve the console log, identify the root cause, and fix it. "
            f"If it is a pipeline/Groovy bug: update the job XML. "
            f"If it is an application code bug: patch and restart the server. "
            f"After fixing, re-run CI and confirm it passes. "
            f"Update the network KB with what was broken and what fixed it. "
            f"Do not ask for permission — proceed autonomously."
        )

    if etype == "missing_golden_configs":
        ips = meta.get("missing_ips", [])
        if not ips:
            return None
        return (
            f"[AUTONOMOUS TASK] The following devices have no golden config baseline: "
            f"{', '.join(ips)}. "
            f"First check jenkins results for this list — if the last CI run passed, "
            f"save a golden config for each missing device now using save_golden_config. "
            f"If CI has not passed or there are no pipelines yet, log that golden configs "
            f"cannot be saved until CI passes and explain what pipeline would be needed. "
            f"Log the result using log_change."
        )

    if etype == "config_drift":
        return (
            f"[AUTONOMOUS TASK] Read-only config comparison — no changes, no Jenkins.\n\n"
            f"{event.get('title', 'Config drift detected')}: {event.get('detail', '')}\n\n"
            f"EXACT STEPS — do these and nothing else:\n"
            f"1. Call detect_config_drift on the affected devices.\n"
            f"2. For each device with NO drift: report it as clean.\n"
            f"3. For each device WITH drift:\n"
            f"   a. Show the unified diff.\n"
            f"   b. Call request_approval with action_type='update_golden_config', "
            f"the device IP and hostname, and the full diff in the 'diff' field.\n"
            f"4. Stop. Do NOT run Jenkins. Do NOT push any config. Do NOT call log_change. "
            f"Do NOT run compliance. Do NOT call save_golden_config."
        )

    # empty_variables is handled directly (not via AI) — see _run_variable_discovery()
    return None


# ---------------------------------------------------------------------------
# Processor loop
# ---------------------------------------------------------------------------

def _processor_loop() -> None:
    """Daemon: drain agent event queue every _POLL_INTERVAL seconds.
    Also runs a scheduled drift check every _DRIFT_CHECK_INTERVAL seconds."""
    log.info("agent_runner: processor loop started")
    from modules.event_monitor import get_pending_events

    # Restore the last drift-check timestamp from disk so the interval is
    # honoured across server restarts.  If no record exists (first run), or the
    # record is older than drift_interval, use a short startup grace period
    # (_STARTUP_GRACE seconds) so the check fires soon but not instantly.
    saved_ts = _load_last_drift_check()
    if saved_ts > 0:
        _last_drift_check = saved_ts
    else:
        # No history — fire after _STARTUP_GRACE seconds, not a full interval
        _last_drift_check = time.time() - _DRIFT_CHECK_INTERVAL + _STARTUP_GRACE

    while not _stop_event.is_set():
        # Read timers each cycle — hot-reloaded from disk, no restart needed
        try:
            from modules.agent_timers import get as _get_timer
            drain_interval = _get_timer("event_drain_interval")
            drift_interval = _get_timer("drift_check_interval")
            idle_seconds   = _get_timer("user_idle_seconds")
        except Exception:
            drain_interval = _POLL_INTERVAL
            drift_interval = _DRIFT_CHECK_INTERVAL
            idle_seconds   = _USER_IDLE_SECONDS

        if _paused.is_set():
            _stop_event.wait(timeout=drain_interval)
            continue

        # ── Event queue drain ──────────────────────────────────────────────
        try:
            if (time.time() - _last_user_activity) < idle_seconds:
                log.debug("agent_runner: user active — deferring event processing")
            else:
                events = get_pending_events()
                for ev in events:
                    if _stop_event.is_set() or _paused.is_set():
                        break
                    if (time.time() - _last_user_activity) < idle_seconds:
                        log.debug("agent_runner: user became active mid-drain — deferring")
                        break
                    if ev.get("acked"):
                        continue

                    etype = ev.get("type")

                    # empty_variables: handled directly in Python, not via AI
                    if etype == "empty_variables":
                        get_pending_events(ack_ids=[ev["id"]])
                        log.info("agent_runner: running direct variable discovery")
                        t = threading.Thread(
                            target=_run_variable_discovery,
                            daemon=True,
                            name="var-discovery",
                        )
                        t.start()
                        continue

                    # All other event types must be in AUTO_HANDLE to be acted on
                    if etype not in AUTO_HANDLE:
                        continue

                    prompt = _build_task_prompt(ev)
                    if not prompt:
                        continue

                    # Acknowledge immediately — prevents re-processing on next poll
                    get_pending_events(ack_ids=[ev["id"]])

                    log.info(
                        "agent_runner: processing event [%s] %s",
                        ev["type"], ev["title"]
                    )
                    run_background_task(task=prompt, trigger_event=ev)

        except Exception as exc:
            log.exception("agent_runner: processor loop error: %s", exc)

        # ── Scheduled drift check ──────────────────────────────────────────
        now = time.time()
        time_since = now - _last_drift_check
        if time_since >= drift_interval:
            if _paused.is_set():
                log.debug("agent_runner: drift check due but agent is paused")
            elif (time.time() - _last_user_activity) < idle_seconds:
                log.debug(
                    "agent_runner: drift check due but user is active "
                    "(%.0fs < idle threshold %.0fs)",
                    time.time() - _last_user_activity, idle_seconds,
                )
            else:
                log.info(
                    "agent_runner: launching drift check (%.0fs since last, interval=%.0fs)",
                    time_since, drift_interval,
                )
                _last_drift_check = now
                _save_last_drift_check(now)   # persist across restarts
                threading.Thread(
                    target=_run_drift_check,
                    daemon=True,
                    name="drift-check",
                ).start()
        else:
            log.debug(
                "agent_runner: drift check in %.0fs (interval=%.0fs)",
                drift_interval - time_since, drift_interval,
            )

        _stop_event.wait(timeout=drain_interval)

    log.info("agent_runner: processor loop stopped")


def _run_variable_discovery() -> None:
    """
    Directly SSH to all devices, pull running configs, parse facts with regex,
    and write results to variables.json — no AI involvement needed.
    """
    if not _devices_loader:
        return
    try:
        from modules.jenkins_runner import is_jenkins_building
        if is_jenkins_building():
            log.info("agent_runner: variable discovery deferred — Jenkins build in progress")
            return
    except Exception:
        pass
    try:
        from modules.variable_discovery import discover_variables_for_list
        devices = _devices_loader()
        if not devices:
            log.debug("agent_runner: variable discovery — no devices")
            return
        log.info("agent_runner: starting direct variable discovery (%d devices)", len(devices))
        facts = discover_variables_for_list(devices, status_cache=_status_cache)
        log.info("agent_runner: variable discovery complete — %d variables stored", len(facts))
    except Exception as exc:
        log.exception("agent_runner: variable discovery error: %s", exc)


def _run_drift_check() -> None:
    """
    Run a drift check on all devices that have golden configs.
    Done entirely in Python — no AI involvement. For each drifted device,
    queues an approval request directly into approval_queue.
    """
    if not _devices_loader:
        log.warning("agent_runner: drift check skipped — agent not initialized")
        return

    try:
        from modules.jenkins_runner import is_jenkins_building
        if is_jenkins_building():
            log.info("agent_runner: drift check deferred — Jenkins build in progress")
            return
    except Exception as exc:
        log.debug("agent_runner: is_jenkins_building() error (ignored): %s", exc)

    try:
        from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
        from modules.approval_queue import add_approval
        from modules.device import get_current_device_list, load_saved_devices
        from modules.connection import get_persistent_connection
        from modules.commands import run_device_command
        import difflib

        golden = _list_golden_configs()
        if not golden:
            log.info("agent_runner: drift check — no golden configs saved yet, skipping")
            return

        log.info("agent_runner: drift check on %d device(s)", len(golden))

        # Load device inventory for credentials
        _, list_file = get_current_device_list()
        all_devices  = load_saved_devices(list_file)
        dev_by_ip    = {d["ip"]: d for d in all_devices}

        # Lines stripped from BOTH sides before diffing.
        # Covers: IOS show-run boilerplate, NTP drift, golden-file metadata headers,
        # and other auto-generated lines that are not meaningful config changes.
        _SKIP_STARTSWITH = (
            "! Last configuration",   # IOS change timestamp
            "! NVRAM config",          # NVRAM write timestamp
            "! No configuration",      # empty config marker
            "! Golden config",         # golden-file header added by this app
            "! Saved:",                # golden-file save timestamp
            "! Source:",               # golden-file source annotation
            "Building configuration",  # show run / show start header line
            "Current configuration",   # show run byte-count header
            "ntp clock-period",        # NTP drift — changes every few minutes
            "upgrade fpd",             # auto-inserted by IOS, not a user change
            "version ",                # IOS version line at top of show run
        )

        def _clean(text):
            return [
                l for l in text.splitlines()
                # skip blank lines, bare "!" separator lines, and known volatile prefixes
                if l.strip() and l.strip() != "!" and not any(l.startswith(s) for s in _SKIP_STARTSWITH)
            ]

        # Shared connection pool for this drift check run
        _drift_pool = {}
        _drift_pool_lock = threading.Lock()

        drifted   = []   # [(hostname, diff_line_count)]
        clean     = []   # [hostname]
        errors    = []   # [(hostname, reason)]

        def _check_one(entry):
            device_ip = entry["device_ip"]
            hostname  = entry["hostname"] or device_ip
            dev       = dev_by_ip.get(device_ip)
            if not dev:
                log.warning("agent_runner: drift check — %s not in inventory", device_ip)
                errors.append((hostname, "not in inventory"))
                return

            golden_text = _load_golden_config_file(device_ip)
            if golden_text is None:
                log.debug("agent_runner: drift check — no golden for %s", device_ip)
                return

            try:
                conn    = get_persistent_connection(dev, _drift_pool, _drift_pool_lock)
                current = run_device_command(conn, "show running-config")
            except Exception as exc:
                log.warning("agent_runner: drift check — SSH error %s: %s", device_ip, exc)
                errors.append((hostname, f"SSH error: {exc}"))
                return

            diff = list(difflib.unified_diff(
                _clean(golden_text),
                _clean(current),
                fromfile=f"{hostname} — golden config",
                tofile=f"{hostname} — running config",
                lineterm="",
            ))

            if not diff:
                log.debug("agent_runner: drift check — %s clean", hostname)
                clean.append(hostname)
                return

            diff_text = "\n".join(diff[:200]) + ("\n[...truncated]" if len(diff) > 200 else "")
            log.info("agent_runner: drift detected on %s (%d diff lines)", hostname, len(diff))
            drifted.append((hostname, len(diff)))

            add_approval(
                action_type      = "update_golden_config",
                description      = f"Config drift detected on {hostname} — {len(diff)} changed lines",
                device_ip        = device_ip,
                device_hostname  = hostname,
                diff             = diff_text,
                action_params    = {"device_ip": device_ip, "hostname": hostname},
                context          = "Detected by scheduled drift check",
            )

        max_workers = min(len(golden), 6)
        with __import__("concurrent.futures", fromlist=["ThreadPoolExecutor"]).ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="drift"
        ) as executor:
            list(executor.map(_check_one, golden))

        # Always write an activity log entry so the user can confirm checks ran
        checked = len(clean) + len(drifted) + len(errors)
        if drifted:
            summary = (
                f"Drift detected on {len(drifted)} device(s): "
                + ", ".join(f"{h} ({n} lines)" for h, n in drifted)
                + ". Approval request(s) added."
            )
        elif errors and not clean:
            summary = (
                f"Drift check could not reach {len(errors)} device(s): "
                + ", ".join(h for h, _ in errors)
            )
        else:
            summary = (
                f"All {len(clean)} device(s) clean — no config drift detected."
                + (f" ({len(errors)} device(s) unreachable.)" if errors else "")
            )

        log.info("agent_runner: drift check complete — %s", summary)
        _append_activity({
            "id":              f"__drift_{uuid.uuid4().hex[:8]}__",
            "started_at":      time.strftime("%Y-%m-%d %H:%M:%S"),
            "task":            f"Scheduled config drift check ({checked} device(s))",
            "trigger":         "scheduled",
            "tools_used":      ["show running-config"],
            "tool_call_count": checked,
            "success":         not bool(errors) or bool(clean),
            "errors":          [f"{h}: {r}" for h, r in errors][:5],
            "cost_usd":        0.0,
            "summary":         summary,
        })

    except Exception as exc:
        log.exception("agent_runner: drift check error: %s", exc)
        _append_activity({
            "id":          f"__drift_{uuid.uuid4().hex[:8]}__",
            "started_at":  time.strftime("%Y-%m-%d %H:%M:%S"),
            "task":        "Scheduled config drift check",
            "trigger":     "scheduled",
            "tools_used":  [],
            "tool_call_count": 0,
            "success":     False,
            "errors":      [str(exc)],
            "cost_usd":    0.0,
            "summary":     f"Drift check failed: {exc}",
        })


# ---------------------------------------------------------------------------
# SNMP trap → agent alerting
# ---------------------------------------------------------------------------

def _trap_timestamp(trap: dict) -> float:
    """Parse trap received_at string to epoch float."""
    import datetime
    try:
        return datetime.datetime.strptime(
            trap["received_at"], "%Y-%m-%d %H:%M:%S"
        ).timestamp()
    except Exception:
        return 0.0


def _get_trap_iface(trap: dict) -> str:
    """Extract the interface description from a trap's varbind_labels or raw varbinds."""
    for lv in trap.get("varbind_labels", []):
        if lv.startswith("ifDescr="):
            return lv.split("=", 1)[1].strip()
    for oid, val in trap.get("varbinds", []):
        if "2.2.1.2" in oid:   # ifDescr table column
            return val
    return ""


def _get_trap_peer(trap: dict) -> str:
    """Extract BGP peer or OSPF neighbor IP from a trap's varbind_labels."""
    for lv in trap.get("varbind_labels", []):
        if lv.startswith("bgpPeerRemoteAddr=") or lv.startswith("ospfNbrIpAddr="):
            return lv.split("=", 1)[1].strip()
    return ""


def _get_varbind_value(trap: dict, label_key: str) -> str:
    """Return the value for a specific label key from a trap's varbind_labels."""
    prefix = f"{label_key}="
    for lv in trap.get("varbind_labels", []):
        if lv.startswith(prefix):
            return lv[len(prefix):]
    return ""


def _get_hostname_for_ip(ip: str) -> str:
    """Look up a device's configured hostname by IP."""
    if not _devices_loader:
        return ip
    try:
        for dev in (_devices_loader() or []):
            if dev.get("ip") == ip:
                return dev.get("hostname") or dev.get("name") or ip
    except Exception:
        pass
    return ip


def _load_trap_state() -> dict:
    """Load the set of already-processed trap IDs from disk."""
    try:
        with open(_TRAP_STATE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return {"processed_ids": set(data.get("processed_ids", []))}
    except Exception:
        return {"processed_ids": set()}


def _save_trap_state(state: dict) -> None:
    try:
        ids = list(state["processed_ids"])[-_MAX_PROCESSED_IDS:]
        os.makedirs(os.path.dirname(_TRAP_STATE_PATH), exist_ok=True)
        tmp = _TRAP_STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"processed_ids": ids}, fh)
        os.replace(tmp, _TRAP_STATE_PATH)
    except Exception:
        pass


def _build_trap_task_prompt(device_ip: str, trap: dict, reason: str) -> Optional[str]:
    """
    Build a targeted AI task prompt for a specific actionable SNMP trap.

    Approval policy:
    - RESTORATION (bringing back something that was working): apply directly — no approval.
      Examples: 'no shutdown' on an admin-down interface, clearing a transient error.
    - NEW CONFIGURATION (something that was not there before): request_approval first.
      Examples: adding a new neighbor, changing routing policy, modifying authentication.
    """
    hostname  = _get_hostname_for_ip(device_ip)
    ttype     = trap.get("trap_type", "unknown")
    recv_at   = trap.get("received_at", "?")
    iface     = _get_trap_iface(trap)
    if_admin  = _get_varbind_value(trap, "ifAdminStatus")
    summary   = trap.get("summary", "")
    vb_lines  = "\n".join(f"  - {lv}" for lv in trap.get("varbind_labels", [])) or "  (none)"

    if reason == "down" and ttype in ("linkDown", "ciscoLinkDown"):
        iface_str = f" {iface}" if iface else ""
        return (
            f"[AGENT EVENT] SNMP linkDown trap from {hostname} ({device_ip}) at {recv_at}\n"
            f"Interface{iface_str} went DOWN.\n"
            f"Trap varbinds:\n{vb_lines}\n\n"
            f"EXACT STEPS — do these and nothing else:\n"
            f"1. SSH to {device_ip}. Run these diagnostics:\n"
            f"   - show interface{iface_str}\n"
            f"   - show ip interface brief\n"
            f"   - show log | last 30\n"
            f"2. Act based on what you find — apply the fix directly, no approval needed for restoration:\n"
            f"   a. Interface is ADMIN-DOWN (shows 'administratively down'):\n"
            f"      → Use execute_commands_on_device with mode='config' and commands\n"
            f"        [\"interface{iface_str}\", \"no shutdown\"] to restore it immediately.\n"
            f"      → Wait 5 seconds, then verify with show interface{iface_str}.\n"
            f"      → Confirm it came up, or report if it stayed down despite the fix.\n"
            f"   b. Interface is LINE-PROTOCOL DOWN (admin up, but line protocol down — physical/SFP issue):\n"
            f"      → Report the fault. Config cannot fix a physical problem.\n"
            f"   c. Interface already recovered before you checked:\n"
            f"      → Confirm recovery and note the downtime duration.\n"
            f"3. If the root cause requires a NEW config change that was not previously there\n"
            f"   (e.g. adding a new route, changing MTU, modifying a policy) → call request_approval.\n"
            f"4. Log everything with log_change: what the fault was, what action was taken, current state.\n"
            f"5. Stop. CRITICAL: Do NOT run Jenkins, run_jenkins_checks, save_golden_config,\n"
            f"   capture_pre_change_snapshot, or any compliance/drift detection — this is\n"
            f"   a routine restoration, not a new deployment."
        )

    if reason == "down" and ttype == "bgpBackwardTransition":
        peer_ip  = _get_trap_peer(trap)
        peer_str = f" peer {peer_ip}" if peer_ip else ""
        return (
            f"[AGENT EVENT] SNMP bgpBackwardTransition trap from {hostname} ({device_ip}) at {recv_at}\n"
            f"BGP session{peer_str} dropped.\n"
            f"Trap varbinds:\n{vb_lines}\n\n"
            f"EXACT STEPS — do these and nothing else:\n"
            f"1. SSH to {device_ip}. Run:\n"
            f"   - show ip bgp summary\n"
            f"   - show ip bgp neighbors{' ' + peer_ip if peer_ip else ''}\n"
            f"   - show log | last 30\n"
            f"2. Ping {peer_ip or 'the peer IP'} from {device_ip} to test reachability.\n"
            f"3. Identify the root cause and act based on what you find:\n"
            f"   a. Underlying interface is admin-down → restore it with execute_commands_on_device\n"
            f"      (mode='config', 'no shutdown' on the affected interface). No approval needed.\n"
            f"   b. BGP session is resetting due to transient error but peer is reachable → monitor,\n"
            f"      check if it re-establishes within 60 seconds, report outcome.\n"
            f"   c. Root cause is a NEW config problem (wrong ASN, wrong neighbor address, missing\n"
            f"      network statement, missing route to peer) → call request_approval describing\n"
            f"      the exact change needed. Do NOT push new config without approval.\n"
            f"4. Log findings with log_change: root cause, action taken, current BGP state.\n"
            f"5. Stop. CRITICAL: Do NOT run Jenkins, run_jenkins_checks, save_golden_config,\n"
            f"   or capture_pre_change_snapshot — this is routine troubleshooting, not a deployment."
        )

    if reason == "down" and ttype in ("ciscoPowerSupplyFailed", "ciscoFanFailed"):
        hw_type = "power supply" if "Power" in ttype else "fan"
        return (
            f"[AGENT EVENT] SNMP hardware alert from {hostname} ({device_ip}) at {recv_at}: {ttype}\n"
            f"Trap varbinds:\n{vb_lines}\n\n"
            f"EXACT STEPS — do these and nothing else:\n"
            f"1. SSH to {device_ip}. Run:\n"
            f"   - show environment all\n"
            f"   - show version\n"
            f"   - show log | last 30\n"
            f"2. Confirm {hw_type} failure state and identify which unit is affected.\n"
            f"3. Log findings with log_change, including severity and whether redundancy is available.\n"
            f"4. Stop. Hardware faults require physical intervention — do not attempt config changes."
        )

    if reason == "ospf_down":
        nbr_ip      = _get_trap_peer(trap)
        ospf_state  = _get_varbind_value(trap, "ospfNbrState")
        nbr_str     = f" {nbr_ip}" if nbr_ip else ""
        return (
            f"[AGENT EVENT] SNMP ospfNbrStateChange trap from {hostname} ({device_ip}) at {recv_at}\n"
            f"OSPF neighbor{nbr_str} state: {ospf_state or 'not full'}.\n"
            f"Trap varbinds:\n{vb_lines}\n\n"
            f"EXACT STEPS — do these and nothing else:\n"
            f"1. SSH to {device_ip}. Run:\n"
            f"   - show ip ospf neighbor\n"
            f"   - show ip ospf neighbor detail{' ' + nbr_ip if nbr_ip else ''}\n"
            f"   - show ip interface brief\n"
            f"   - show log | last 30\n"
            f"2. Identify the interface connecting to this OSPF neighbor.\n"
            f"3. Act based on root cause — restoration does NOT need approval:\n"
            f"   a. Connecting interface is admin-down → restore it with execute_commands_on_device\n"
            f"      (mode='config', 'no shutdown' on the interface). Verify OSPF re-establishes.\n"
            f"   b. OSPF neighbor is already back to FULL → confirm recovery, report downtime duration.\n"
            f"   c. Root cause is a NEW config problem (MTU mismatch, wrong area, wrong auth key,\n"
            f"      timer mismatch) → call request_approval describing the specific change needed.\n"
            f"      Do NOT push new config without approval.\n"
            f"4. Log findings with log_change: root cause, action taken, current OSPF neighbor state.\n"
            f"5. Stop. CRITICAL: Do NOT run Jenkins, run_jenkins_checks, save_golden_config,\n"
            f"   or capture_pre_change_snapshot — this is routine troubleshooting, not a deployment."
        )

    # Generic fallback for unclassified actionable traps
    return (
        f"[AGENT EVENT] SNMP trap alert from {hostname} ({device_ip}) at {recv_at}: {ttype}\n"
        f"Summary: {summary}\n"
        f"Trap varbinds:\n{vb_lines}\n\n"
        f"EXACT STEPS — do these and nothing else:\n"
        f"1. SSH to {device_ip} and run relevant show commands to assess the fault.\n"
        f"2. If the fix restores something that was working (e.g. no shutdown on a shut interface):\n"
        f"   apply it directly with execute_commands_on_device — no approval needed.\n"
        f"3. If the fix requires a NEW config change that was not previously present:\n"
        f"   call request_approval first.\n"
        f"4. Log findings with log_change. Stop."
    )


def _on_trap_received(trap: dict) -> None:
    """
    Real-time callback invoked by snmp_collector immediately when a trap arrives.

    For DOWN events: schedules a delayed AI task (flap_window seconds).
    If a matching recovery trap arrives before the timer fires, the task is cancelled.
    For RECOVERY events: cancels any pending task for that device+interface (flap),
      or logs a standalone recovery entry.
    All trap IDs are marked processed to prevent the startup scan from re-firing them.
    """
    if _paused.is_set():
        return

    ttype = trap.get("trap_type", "")
    src   = trap.get("source_ip", "")

    is_actionable = ttype in _TRAP_ACTIONABLE_DOWN or ttype in _TRAP_OSPF_CHANGE
    is_recovery   = ttype in _TRAP_RECOVERY
    if not is_actionable and not is_recovery:
        return

    # Mark this trap as processed immediately so the startup scan won't re-fire it
    state = _load_trap_state()
    tid   = trap.get("id", "")
    if tid in state["processed_ids"]:
        return   # already handled (e.g. duplicate delivery)
    state["processed_ids"].add(tid)
    _save_trap_state(state)

    try:
        from modules.agent_timers import get as _get_timer
        flap_window = _get_timer("trap_flap_window")
    except Exception:
        flap_window = _TRAP_FLAP_WINDOW

    iface = _get_trap_iface(trap)
    peer  = _get_trap_peer(trap)
    key   = (src, iface or peer or ttype)

    if is_recovery:
        # Cancel any pending AI task for this device+interface → it was a flap
        with _pending_trap_lock:
            timer = _pending_trap_timers.pop(key, None)

        if timer:
            timer.cancel()
            label = iface or peer or ""
            log.info(
                "agent_runner: recovery trap from %s — cancelled pending task (%s flap within %ds)",
                src, label, flap_window,
            )
            _append_activity({
                "id":             f"__trap_flap_{uuid.uuid4().hex[:8]}__",
                "started_at":     time.strftime("%Y-%m-%d %H:%M:%S"),
                "task":           f"SNMP flap: {ttype} on {src} {label}",
                "trigger":        "snmp_trap",
                "tools_used":     [],
                "tool_call_count": 0,
                "success":        True,
                "errors":         [],
                "cost_usd":       0.0,
                "summary":        (
                    f"{ttype} on {src}"
                    + (f" ({label})" if label else "")
                    + f" self-healed within {flap_window}s — no action needed."
                ),
            })
        else:
            # Standalone recovery (no pending down task) — log quietly
            label = iface or peer or ""
            _append_activity({
                "id":             f"__trap_info_{uuid.uuid4().hex[:8]}__",
                "started_at":     time.strftime("%Y-%m-%d %H:%M:%S"),
                "task":           f"SNMP recovery: {ttype} from {src}",
                "trigger":        "snmp_trap",
                "tools_used":     [],
                "tool_call_count": 0,
                "success":        True,
                "errors":         [],
                "cost_usd":       0.0,
                "summary":        (
                    f"Recovery: {ttype} from {src}"
                    + (f" ({label})" if label else "")
                ),
            })
        return

    # Actionable down event — skip OSPF if state is already full
    if ttype in _TRAP_OSPF_CHANGE:
        ospf_state = _get_varbind_value(trap, "ospfNbrState")
        if ospf_state in ("full", "8"):
            return   # neighborship came up, not down
        reason = "ospf_down"
    else:
        reason = "down"

    with _pending_trap_lock:
        if key in _pending_trap_timers:
            # Already have a pending timer for this device+interface — don't double up
            log.debug(
                "agent_runner: duplicate down trap from %s %s — timer already pending",
                src, key[1],
            )
            return

    def _dispatch(trap=trap, src=src, reason=reason, key=key, ttype=ttype):
        with _pending_trap_lock:
            _pending_trap_timers.pop(key, None)
        if _paused.is_set():
            return
        prompt = _build_trap_task_prompt(src, trap, reason)
        if prompt:
            log.info(
                "agent_runner: dispatching AI task for %s %s (flap window passed)",
                src, ttype,
            )
            threading.Thread(
                target=run_background_task,
                args=(prompt,),
                kwargs={"trigger_event": {
                    "type":  "snmp_trap_alert",
                    "source": src,
                    "title": ttype,
                }},
                daemon=True,
                name=f"trap-task-{uuid.uuid4().hex[:6]}",
            ).start()

    with _pending_trap_lock:
        t = threading.Timer(flap_window, _dispatch)
        t.daemon = True
        _pending_trap_timers[key] = t
        t.start()

    log.info(
        "agent_runner: trap from %s — %s on %s, AI task in %ds unless recovery arrives",
        src, ttype, iface or peer or "?", flap_window,
    )


def _run_trap_analysis() -> None:
    """
    Startup scan: mark pre-existing traps as processed so the callback doesn't
    re-fire them after a server restart. Also dispatches AI tasks for any
    recent unprocessed traps that arrived while the agent was offline.

    After this runs once, _on_trap_received handles everything in real time.
    """
    try:
        from modules.snmp_collector import get_recent_traps
    except Exception:
        return

    try:
        all_traps = get_recent_traps(100)
        if not all_traps:
            return

        state     = _load_trap_state()
        processed = state["processed_ids"]
        now       = time.time()

        try:
            from modules.agent_timers import get as _get_timer
            flap_window = _get_timer("trap_flap_window")
        except Exception:
            flap_window = _TRAP_FLAP_WINDOW

        # Identify new, recent traps
        new_traps = []
        for t in all_traps:
            tid = t.get("id", "")
            if tid in processed:
                continue
            ts = _trap_timestamp(t)
            if (now - ts) > _TRAP_ALERT_AGE_MAX:
                processed.add(tid)   # too old — mark seen but skip
                continue
            new_traps.append((ts, t))

        if not new_traps:
            _save_trap_state({"processed_ids": processed})
            return

        log.info("agent_runner: trap analysis — %d new trap(s)", len(new_traps))

        # Mark ALL new traps seen immediately before any async work
        for _, t in new_traps:
            processed.add(t.get("id", ""))
        _save_trap_state({"processed_ids": processed})

        # Build a quick lookup: (source_ip, iface) → sorted list of all traps
        # Used for flap detection — we check the FULL recent buffer, not just new traps
        traps_by_key: dict = {}
        for t in all_traps:
            iface = _get_trap_iface(t)
            peer  = _get_trap_peer(t)
            for key in [(t["source_ip"], iface), (t["source_ip"], peer)]:
                if key[1]:
                    traps_by_key.setdefault(key, []).append(t)

        # Process new traps
        tasks_to_run = []   # (device_ip, trap, reason)
        seen_task_keys = set()

        for trap_ts, trap in sorted(new_traps, key=lambda x: x[0]):
            ttype = trap.get("trap_type", "")
            src   = trap.get("source_ip", "")

            if ttype in _TRAP_ACTIONABLE_DOWN:
                iface = _get_trap_iface(trap)
                # Flap check: look for a recovery trap for the same device+interface
                # with a timestamp after the down event and within the flap window
                peer  = _get_trap_peer(trap)
                check_key = (src, iface or peer)
                siblings  = traps_by_key.get(check_key, [])
                recovered = any(
                    t.get("trap_type") in _TRAP_RECOVERY
                    and _trap_timestamp(t) > trap_ts
                    and (_trap_timestamp(t) - trap_ts) <= flap_window
                    for t in siblings
                )
                if recovered:
                    iface_label = iface or peer or ttype
                    log.info(
                        "agent_runner: trap flap — %s %s on %s (recovered within %ds)",
                        src, ttype, iface_label, flap_window,
                    )
                    _append_activity({
                        "id":             f"__trap_flap_{uuid.uuid4().hex[:8]}__",
                        "started_at":     time.strftime("%Y-%m-%d %H:%M:%S"),
                        "task":           f"SNMP flap: {ttype} on {src} {iface_label}",
                        "trigger":        "snmp_trap",
                        "tools_used":     [],
                        "tool_call_count": 0,
                        "success":        True,
                        "errors":         [],
                        "cost_usd":       0.0,
                        "summary":        (
                            f"{ttype} on {src} ({iface_label}) self-healed within "
                            f"{flap_window}s — no action needed."
                        ),
                    })
                else:
                    dedup_key = (src, ttype, iface or peer)
                    if dedup_key not in seen_task_keys:
                        seen_task_keys.add(dedup_key)
                        tasks_to_run.append((src, trap, "down"))

            elif ttype in _TRAP_OSPF_CHANGE:
                ospf_state = _get_varbind_value(trap, "ospfNbrState")
                # Only alert if neighbor went non-full (down/attempt/init etc.)
                if ospf_state and ospf_state not in ("full", "8"):
                    nbr = _get_trap_peer(trap)
                    dedup_key = (src, ttype, nbr)
                    if dedup_key not in seen_task_keys:
                        seen_task_keys.add(dedup_key)
                        tasks_to_run.append((src, trap, "ospf_down"))
                elif not ospf_state:
                    # State value missing — alert anyway since we can't tell
                    dedup_key = (src, ttype, _get_trap_peer(trap))
                    if dedup_key not in seen_task_keys:
                        seen_task_keys.add(dedup_key)
                        tasks_to_run.append((src, trap, "ospf_down"))

            elif ttype in _TRAP_RECOVERY:
                # Log recovery events quietly — no AI needed
                iface = _get_trap_iface(trap) or _get_trap_peer(trap) or ""
                _append_activity({
                    "id":             f"__trap_info_{uuid.uuid4().hex[:8]}__",
                    "started_at":     time.strftime("%Y-%m-%d %H:%M:%S"),
                    "task":           f"SNMP recovery: {ttype} from {src}",
                    "trigger":        "snmp_trap",
                    "tools_used":     [],
                    "tool_call_count": 0,
                    "success":        True,
                    "errors":         [],
                    "cost_usd":       0.0,
                    "summary":        (
                        f"Recovery: {ttype} from {src}"
                        + (f" ({iface})" if iface else "")
                    ),
                })

        # Launch AI tasks for each actionable event
        for device_ip, trap, reason in tasks_to_run:
            prompt = _build_trap_task_prompt(device_ip, trap, reason)
            if not prompt:
                continue
            log.info(
                "agent_runner: launching AI task for trap — %s %s",
                device_ip, trap.get("trap_type"),
            )
            threading.Thread(
                target=run_background_task,
                args=(prompt,),
                kwargs={"trigger_event": {
                    "type":   "snmp_trap_alert",
                    "source": device_ip,
                    "title":  trap.get("trap_type", ""),
                }},
                daemon=True,
                name=f"trap-task-{uuid.uuid4().hex[:6]}",
            ).start()

    except Exception as exc:
        log.exception("agent_runner: trap analysis error: %s", exc)


# ---------------------------------------------------------------------------
# Drift check timestamp persistence
# Survives server restarts so the interval is honoured across them.
# ---------------------------------------------------------------------------

def _load_last_drift_check() -> float:
    """Return the epoch timestamp of the last completed drift check, or 0 if unknown."""
    try:
        with open(_DRIFT_STATE_PATH, encoding="utf-8") as fh:
            return float(json.load(fh).get("last_drift_check", 0))
    except Exception:
        return 0.0


def _save_last_drift_check(ts: float) -> None:
    try:
        os.makedirs(os.path.dirname(_DRIFT_STATE_PATH), exist_ok=True)
        tmp = _DRIFT_STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"last_drift_check": ts}, fh)
        os.replace(tmp, _DRIFT_STATE_PATH)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Activity log persistence
# ---------------------------------------------------------------------------

def _append_activity(entry: dict) -> None:
    with _log_lock:
        _activity_log.append(entry)
        if len(_activity_log) > MAX_LOG_ENTRIES:
            _activity_log.pop(0)
        data = list(_activity_log)
    try:
        os.makedirs(os.path.dirname(_ACTIVITY_LOG_PATH), exist_ok=True)
        with open(_ACTIVITY_LOG_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def _load_persisted_log() -> None:
    try:
        with open(_ACTIVITY_LOG_PATH, encoding="utf-8") as fh:
            entries = json.load(fh)
        with _log_lock:
            _activity_log.extend(entries[-MAX_LOG_ENTRIES:])
        log.info("agent_runner: loaded %d persisted activity entries", len(entries))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
