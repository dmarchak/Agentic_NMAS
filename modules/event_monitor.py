"""event_monitor.py

Background event monitor for the autonomous AI agent.

Runs a daemon thread that polls for actionable events on a configurable
interval: devices with no golden config, and lists with empty variables.
(Jenkins build polling was removed in P.4.)
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
_POLL_INTERVAL = 15   # seconds between loop wakes
_DRIFT_INTERVAL = 300  # seconds between passive drift checks (5 min)

# Shared in-memory event queue — thread-safe via _lock
_events: list[dict] = []
_lock   = threading.Lock()
_monitor_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

# Track the last known build state per job so we only fire on transitions


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


def _check_missing_golden_configs() -> None:
    """Push an event if any device in the inventory lacks a golden config.

    Two corrections, both Stage 3.3:

    * The population comes from `load_saved_devices()`, the single dispatch
      point, rather than from opening `devices.csv` by hand. A NetBox-sourced
      list has no CSV, so the hand-rolled reader fell through to
      `DATA_DIR/Devices.csv` -- **a different list's devices** -- and reported
      them missing against this list's goldens.
    * The goldens come from the repo's one enumerator (`repo.list_goldens`, per network since
      C491). The old reader listed the
      deprecated `golden_configs/` directory, so every device onboarded after
      the migration was reported as having no golden while its golden sat in
      `config_repo/`. A warning banner that is wrong about devices you know
      are fine is how an operator learns to dismiss the banner.
    """
    try:
        from modules.device import load_saved_devices
        from modules.nsot import listref
        from modules.nsot.repo import list_goldens

        # EVERY network (C491): it read the active list's devices and goldens only, so a
        # network that was not active was never checked.
        for list_name in sorted(listref._registry()):
            device_ips = [d.get("ip", "").strip()
                          for d in load_saved_devices(listref.resolve(list_name).csv_path)
                          if d.get("ip")]
            if not device_ips:
                continue
            golden_ips = {e["device_ip"] for e in list_goldens(list_name)}
            missing = [ip for ip in device_ips if ip not in golden_ips]
            if not missing:
                continue
            # Only push this event once per network until acknowledged.
            with _lock:
                already = any(
                    ev["type"] == "missing_golden_configs" and not ev["acked"]
                    and (ev.get("metadata") or {}).get("list") == list_name
                    for ev in _events
                )
            if not already:
                _push_event(
                    event_type="missing_golden_configs",
                    title=f"{list_name}: {len(missing)} device(s) have no golden config",
                    detail=(
                        f"Devices in {list_name} without a verified baseline: "
                        f"{', '.join(missing)}. After the next successful CI run, the agent "
                        f"should call save_golden_config for each."
                    ),
                    severity="warning",
                    metadata={"missing_ips": missing, "list": list_name},
                )
    except Exception as exc:
        log.debug("event_monitor: golden config check error: %s", exc)


def _check_empty_variables() -> None:
    """Push an event if the current list has devices but no stored variables."""
    try:
        from modules.device import load_saved_devices
        from modules.nsot import listref

        # EVERY network (C491), each its own variable store. Devices through the single
        # dispatch point: a NetBox-sourced list has no devices.csv.
        for list_name in sorted(listref._registry()):
            ref = listref.resolve(list_name)
            try:
                with open(os.path.join(ref.data_dir, "variables.json"), encoding="utf-8") as fh:
                    if json.load(fh):
                        continue   # variables exist: nothing to do
            except FileNotFoundError:
                pass
            device_count = sum(1 for d in load_saved_devices(ref.csv_path) if d.get("ip"))
            if device_count == 0:
                continue
            # Avoid spamming: once per network until acknowledged.
            with _lock:
                already = any(
                    ev["type"] == "empty_variables" and not ev.get("acked")
                    and (ev.get("metadata") or {}).get("list") == list_name
                    for ev in _events
                )
            if already:
                continue
            _push_event(
                event_type="empty_variables",
                title=f"No network facts stored for {list_name} ({device_count} devices)",
                detail=(
                    f"{list_name}'s variable store is empty. The agent should survey the "
                    f"network and store key facts: device roles, loopback IPs, OSPF process "
                    f"IDs, routing protocols, interface assignments, and BGP AS numbers."
                ),
                severity="warning",
                metadata={"device_count": device_count, "list": list_name},
            )
    except Exception as exc:
        log.debug("event_monitor: empty variables check error: %s", exc)


def _monitor_loop() -> None:
    """Main daemon loop — checks golden configs and variables on a schedule.
    Timer intervals are read from agent_timers each cycle so changes take effect
    without restarting the server."""
    last_periodic_check = 0.0

    while not _stop_event.is_set():
        try:
            from modules.agent_timers import get as _get_timer
            event_interval = _get_timer("event_check_interval")
        except Exception:
            event_interval = _DRIFT_INTERVAL

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

        _stop_event.wait(timeout=_POLL_INTERVAL)

    log.info("event_monitor: stopped")
