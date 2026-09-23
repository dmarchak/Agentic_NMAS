"""event_monitor.py

Background event monitor for the autonomous AI agent.

Runs a daemon thread that polls for actionable events on a configurable
interval: Jenkins build completions across all registered pipelines, passive
config-drift checks (running vs golden), and compliance failures post-CI.
Events are written to a 50-entry in-memory ring buffer; the Flask API exposes
GET /ai/events so the frontend can acknowledge events and prompt the AI to
investigate when the user is idle.
"""

import os
import json
import time
import threading
import logging
from typing import Optional

log = logging.getLogger(__name__)

MAX_EVENTS = 50
_POLL_INTERVAL = 15   # seconds between Jenkins result polls
_DRIFT_INTERVAL = 300  # seconds between passive drift checks (5 min)

# Shared in-memory event queue — thread-safe via _lock
_events: list[dict] = []
_lock   = threading.Lock()
_monitor_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

# Track the last known build state per job so we only fire on transitions
_last_build_state: dict = {}   # job_name → {"build_number": N, "result": "SUCCESS"|"FAILURE"|"RUNNING"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_pending_events(ack_ids: list[str] | None = None) -> list[dict]:
    """
    Return unacknowledged events.
    If ack_ids is provided, mark those events as acknowledged first.
    """
    with _lock:
        if ack_ids:
            for ev in _events:
                if ev.get("id") in ack_ids:
                    ev["acked"] = True
        return [ev for ev in _events if not ev.get("acked")]


def clear_events() -> None:
    """Remove all events (called on list switch or session clear)."""
    with _lock:
        _events.clear()
        _last_build_state.clear()


def start_monitor() -> None:
    """Start the background monitor daemon thread (idempotent)."""
    global _monitor_thread
    if _monitor_thread and _monitor_thread.is_alive():
        return
    _stop_event.clear()
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name="event-monitor")
    _monitor_thread.start()
    log.info("event_monitor: started")


def stop_monitor() -> None:
    """Signal the monitor thread to stop (graceful shutdown)."""
    _stop_event.set()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _push_event(event_type: str, title: str, detail: str, severity: str = "info",
                metadata: dict | None = None) -> None:
    """Add an event to the ring buffer."""
    import uuid
    ev = {
        "id":        str(uuid.uuid4())[:8],
        "type":      event_type,
        "title":     title,
        "detail":    detail,
        "severity":  severity,           # "info" | "warning" | "error"
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "acked":     False,
        "metadata":  metadata or {},
    }
    with _lock:
        _events.append(ev)
        # Keep ring buffer bounded
        if len(_events) > MAX_EVENTS:
            _events.pop(0)
    log.debug("event_monitor: pushed [%s] %s", event_type, title)


def _load_jenkins_results() -> dict:
    """Load results from the current list's jenkins_results.json."""
    try:
        from modules.jenkins_runner import _results_file
        path = _results_file()
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _load_golden_configs() -> list:
    """Load golden config metadata for the current list."""
    try:
        from modules.ai_assistant import _list_golden_configs
        return _list_golden_configs()
    except Exception:
        return []


def _check_jenkins_results() -> None:
    """
    First sync the latest build results from the Jenkins API (so scheduled/cron
    builds are visible), then compare against last known state and push events on change.
    """
    try:
        from modules.jenkins_runner import sync_scheduled_build_results
        sync_scheduled_build_results()
    except Exception as exc:
        log.debug("event_monitor: jenkins sync error: %s", exc)

    results = _load_jenkins_results()
    for job, info in results.items():
        if not isinstance(info, dict):
            continue
        build_num = info.get("build_number")
        result    = info.get("result", "UNKNOWN")
        key       = job

        prev = _last_build_state.get(key, {})
        if prev.get("build_number") == build_num and prev.get("result") == result:
            continue  # No change

        _last_build_state[key] = {"build_number": build_num, "result": result}

        if result == "FAILURE":
            _push_event(
                event_type="jenkins_failure",
                title=f"Jenkins pipeline FAILED: {job}",
                detail=(
                    f"Build #{build_num} failed. The agent should diagnose the console "
                    f"and fix the root cause automatically."
                ),
                severity="error",
                metadata={"job": job, "build_number": build_num},
            )
        elif result == "SUCCESS" and prev.get("result") == "FAILURE":
            # Recovered from failure — possibly golden config should be saved
            _push_event(
                event_type="jenkins_recovered",
                title=f"Jenkins pipeline recovered: {job}",
                detail=(
                    f"Build #{build_num} passed after a previous failure. "
                    f"Consider saving golden configs for any recently modified devices."
                ),
                severity="info",
                metadata={"job": job, "build_number": build_num},
            )


def _check_missing_golden_configs() -> None:
    """Push an event if any device in the inventory lacks a golden config.

    Two corrections, both Stage 3.3:

    * The population comes from `load_saved_devices()`, the single dispatch
      point, rather than from opening `devices.csv` by hand. A NetBox-sourced
      list has no CSV, so the hand-rolled reader fell through to
      `DATA_DIR/Devices.csv` -- **a different list's devices** -- and reported
      them missing against this list's goldens.
    * `_load_golden_configs()` now enumerates the repo. It listed the
      deprecated `golden_configs/` directory, so every device onboarded after
      the migration was reported as having no golden while its golden sat in
      `config_repo/`. A warning banner that is wrong about devices you know
      are fine is how an operator learns to dismiss the banner.
    """
    try:
        from modules.device import get_current_device_list, load_saved_devices

        _name, list_file = get_current_device_list()
        device_ips = [d.get("ip", "").strip() for d in load_saved_devices(list_file)
                      if d.get("ip")]
        if not device_ips:
            return

        golden_ips = {e["device_ip"] for e in _load_golden_configs()}
        missing = [ip for ip in device_ips if ip not in golden_ips]

        if missing:
            # Only push this event once per session (check if already queued)
            with _lock:
                already = any(
                    ev["type"] == "missing_golden_configs" and not ev["acked"]
                    for ev in _events
                )
            if not already:
                _push_event(
                    event_type="missing_golden_configs",
                    title=f"{len(missing)} device(s) have no golden config",
                    detail=(
                        f"Devices without a verified baseline: {', '.join(missing)}. "
                        f"After the next successful CI run, the agent should call "
                        f"save_golden_config for each."
                    ),
                    severity="warning",
                    metadata={"missing_ips": missing},
                )
    except Exception as exc:
        log.debug("event_monitor: golden config check error: %s", exc)


def _check_empty_variables() -> None:
    """Push an event if the current list has devices but no stored variables."""
    try:
        from modules.ai_assistant import _load_variables
        variables = _load_variables()
        if variables:
            return   # variables exist — nothing to do

        # Through the single dispatch point, for the same reason as
        # `_check_missing_golden_configs`: a NetBox-sourced list has no
        # devices.csv, and the DATA_DIR fallback counted a DIFFERENT list's
        # devices against this list's (empty) variable store.
        from modules.device import get_current_device_list, load_saved_devices

        _name, list_file = get_current_device_list()
        device_count = sum(1 for d in load_saved_devices(list_file) if d.get("ip"))
        if device_count == 0:
            return

        # Avoid spamming — only push once until resolved
        with _lock:
            already = any(
                ev["type"] == "empty_variables" and not ev.get("acked")
                for ev in _events
            )
        if already:
            return

        _push_event(
            event_type="empty_variables",
            title=f"No network facts stored for this list ({device_count} devices)",
            detail=(
                f"The variable store is empty. The agent should survey the network and "
                f"store key facts: device roles, loopback IPs, OSPF process IDs, routing "
                f"protocols, interface assignments, and BGP AS numbers."
            ),
            severity="warning",
            metadata={"device_count": device_count},
        )
    except Exception as exc:
        log.debug("event_monitor: empty variables check error: %s", exc)


def _monitor_loop() -> None:
    """Main daemon loop — polls Jenkins and checks golden configs on a schedule.
    Timer intervals are read from agent_timers each cycle so changes take effect
    without restarting the server."""
    last_periodic_check = 0.0

    while not _stop_event.is_set():
        try:
            from modules.agent_timers import get as _get_timer
            poll_interval  = _get_timer("jenkins_poll_interval")
            event_interval = _get_timer("event_check_interval")
        except Exception:
            poll_interval  = _POLL_INTERVAL
            event_interval = _DRIFT_INTERVAL

        try:
            _check_jenkins_results()
        except Exception as exc:
            log.debug("event_monitor: jenkins check error: %s", exc)

        now = time.time()
        if now - last_periodic_check >= event_interval:
            try:
                _check_missing_golden_configs()
            except Exception as exc:
                log.debug("event_monitor: golden config check error: %s", exc)
            try:
                _check_empty_variables()
            except Exception as exc:
                log.debug("event_monitor: empty variables check error: %s", exc)
            last_periodic_check = now

        _stop_event.wait(timeout=poll_interval)

    log.info("event_monitor: stopped")
