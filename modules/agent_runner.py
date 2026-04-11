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
_ACTIVITY_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "agent_activity.json"
)

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

# Which event types the agent handles autonomously
AUTO_HANDLE = {"jenkins_failure", "missing_golden_configs", "config_drift", "empty_variables"}


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
        "• Do NOT follow autonomous trigger rules (CONFIG PUSH, GOLDEN CONFIG, etc.).\n"
        "• Do NOT investigate or fix Jenkins failures unless the task explicitly says to.\n"
        "• Do NOT run Jenkins, compliance checks, or push any config unless the task says to.\n"
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

    if etype == "empty_variables":
        device_count = meta.get("device_count", 0)
        return (
            f"[AUTONOMOUS TASK] Extract network variables from running configs. "
            f"There are {device_count} device(s) in this list with no stored variables.\n\n"
            f"EXACT STEPS — do these and nothing else:\n"
            f"1. Call get_all_devices to get the list of device IPs.\n"
            f"2. For each device, call get_running_config to fetch its running config. "
            f"   Do NOT use show commands, do NOT check Jenkins, do NOT run compliance.\n"
            f"3. Parse each running config and extract these facts using set_variable:\n"
            f"   - <hostname>_role: device role inferred from hostname or config "
            f"(P/PE/CE/RR/access)\n"
            f"   - <hostname>_loopback0: Loopback0 IP address (from 'interface Loopback0')\n"
            f"   - <hostname>_ospf_pid: OSPF process ID (from 'router ospf <N>')\n"
            f"   - <hostname>_bgp_as: BGP AS number (from 'router bgp <N>')\n"
            f"   - <hostname>_mpls: 'yes' if 'mpls ip' appears in config, 'no' otherwise\n"
            f"   - <hostname>_vrfs: comma-separated VRF names (from 'vrf definition' or "
            f"'ip vrf' lines)\n"
            f"4. Stop. Do not run any other tools after set_variable calls are done.\n\n"
            f"Use the device hostname (from 'hostname' line in config) as the key prefix, "
            f"not the IP address. Skip any fact that is not present in the config."
        )

    return None


# ---------------------------------------------------------------------------
# Processor loop
# ---------------------------------------------------------------------------

def _processor_loop() -> None:
    """Daemon: drain agent event queue every _POLL_INTERVAL seconds.
    Also runs a scheduled drift check every _DRIFT_CHECK_INTERVAL seconds."""
    log.info("agent_runner: processor loop started")
    from modules.event_monitor import get_pending_events

    _last_drift_check = 0.0

    while not _stop_event.is_set():
        if _paused.is_set():
            _stop_event.wait(timeout=_POLL_INTERVAL)
            continue

        # ── Event queue drain ──────────────────────────────────────────────
        try:
            if _user_is_active():
                log.debug("agent_runner: user active — deferring event processing")
            else:
                events = get_pending_events()
                for ev in events:
                    if _stop_event.is_set() or _paused.is_set():
                        break
                    if _user_is_active():
                        log.debug("agent_runner: user became active mid-drain — deferring")
                        break
                    if ev.get("acked"):
                        continue
                    if ev.get("type") not in AUTO_HANDLE:
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
        if now - _last_drift_check >= _DRIFT_CHECK_INTERVAL:
            _last_drift_check = now
            if not _paused.is_set() and not _user_is_active():
                _run_drift_check()

        _stop_event.wait(timeout=_POLL_INTERVAL)

    log.info("agent_runner: processor loop stopped")


def _run_drift_check() -> None:
    """
    Run a drift check on all devices that have golden configs.
    For each device with drift, queue an approval request via the AI agent.
    """
    if not _devices_loader:
        return

    try:
        from modules.ai_assistant import _list_golden_configs
        golden = _list_golden_configs()
        if not golden:
            log.debug("agent_runner: drift check — no golden configs, skipping")
            return

        ips = [e["device_ip"] for e in golden]
        # Build a human-readable device list: "P1, P2, PE-1, ..." with IPs as fallback
        device_labels = [
            e["hostname"] if e["hostname"] != e["device_ip"] else e["device_ip"]
            for e in golden
        ]
        device_list = ", ".join(device_labels)
        log.info("agent_runner: running scheduled drift check on %d device(s): %s",
                 len(ips), device_list)

        prompt = (
            f"[SCHEDULED DRIFT CHECK] Read-only config comparison — no changes, no Jenkins.\n\n"
            f"Devices to check: {device_list}\n"
            f"Device IPs: {', '.join(ips)}\n\n"
            f"EXACT STEPS — do these and nothing else:\n"
            f"1. Call detect_config_drift with the device IPs above.\n"
            f"2. For each device with NO drift: report it as clean.\n"
            f"3. For each device WITH drift:\n"
            f"   a. Show the unified diff.\n"
            f"   b. Call request_approval with action_type='update_golden_config', "
            f"the device IP and hostname, and the full diff in the 'diff' field.\n"
            f"4. Stop. Do NOT run Jenkins. Do NOT push any config. Do NOT call log_change. "
            f"Do NOT run compliance. Do NOT call save_golden_config."
        )
        run_background_task(
            task=prompt,
            trigger_event={"type": "scheduled_drift_check"},
        )
    except Exception as exc:
        log.exception("agent_runner: drift check error: %s", exc)


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
