"""drift_check.py

Standalone Python-based config drift checker.

Runs completely independently of the AI assistant — no Claude API calls are
ever made.  Works whether AI is enabled or not.

Lifecycle
---------
  DriftChecker.start()   — call once at app startup
  DriftChecker.stop()    — call on shutdown
  DriftChecker.trigger() — kick off an immediate check (non-blocking)
  DriftChecker.status()  — dict describing last run and next scheduled run

For each device that has a saved golden config, the checker:
  1. SSHes to the device and fetches ``show running-config``
  2. Cleans both golden and running configs (strips timestamps, boilerplate)
  3. Generates a unified diff with Python's ``difflib``
  4. If drift is found, calls ``approval_queue.add_approval()``
     (deduplication built into approval_queue prevents flooding)

The interval (seconds) is read from ``agent_timers`` each cycle so it can be
changed without restarting the server.  Default: 4 hours.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import threading
import time
import uuid
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------

_DEFAULT_INTERVAL  = 4 * 3600   # 4 hours
_STARTUP_GRACE     = 300         # fire first check 5 min after start (not instantly)
_STATE_FILE_NAME   = "drift_state.json"

# Lines stripped from BOTH sides before diffing.
_SKIP_STARTSWITH = (
    "! Last configuration",
    "! NVRAM config",
    "! No configuration",
    "! Golden config",
    "! Saved:",
    "! Source:",
    "Building configuration",
    "Current configuration",
    "ntp clock-period",
    "upgrade fpd",
    "version ",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _state_file() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, _STATE_FILE_NAME)


def _load_state() -> dict:
    try:
        with open(_state_file(), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(data: dict) -> None:
    path = _state_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception as exc:
        log.warning("drift_check: could not save state: %s", exc)


def _clean(text: str) -> list[str]:
    """Strip volatile/boilerplate lines before diffing."""
    return [
        line for line in text.splitlines()
        if line.strip()
        and line.strip() != "!"
        and not any(line.startswith(s) for s in _SKIP_STARTSWITH)
    ]


def _get_interval() -> float:
    try:
        from modules.agent_timers import get as _get_timer
        return float(_get_timer("drift_check_interval") or _DEFAULT_INTERVAL)
    except Exception:
        return _DEFAULT_INTERVAL


def _is_disabled() -> bool:
    return bool(_load_state().get("disabled", False))


def set_disabled(disabled: bool) -> None:
    state = _load_state()
    state["disabled"] = bool(disabled)
    _save_state(state)


# ---------------------------------------------------------------------------
# Core drift logic (pure Python, no AI)
# ---------------------------------------------------------------------------

def run_drift_check(triggered_by: str = "scheduled") -> dict:
    """
    Check all devices with golden configs for config drift.

    Returns a summary dict:
      {ok, checked, drifted, clean, errors, timestamp, triggered_by}
    """
    from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
    from modules.approval_queue import add_approval
    from modules.device import get_current_device_list, load_saved_devices
    from modules.connection import get_persistent_connection
    from modules.commands import run_device_command
    from modules.jenkins_runner import is_jenkins_building

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        if is_jenkins_building():
            log.info("drift_check: deferred — Jenkins build in progress")
            return {
                "ok": True, "checked": 0, "drifted": 0, "clean": 0,
                "errors": [], "timestamp": timestamp,
                "triggered_by": triggered_by,
                "skipped": "Jenkins build in progress",
            }
    except Exception:
        pass

    golden = _list_golden_configs()
    if not golden:
        log.info("drift_check: no golden configs saved yet — skipping")
        return {
            "ok": True, "checked": 0, "drifted": 0, "clean": 0,
            "errors": [], "timestamp": timestamp,
            "triggered_by": triggered_by,
            "skipped": "No golden configs saved",
        }

    log.info("drift_check: checking %d device(s) [%s]", len(golden), triggered_by)

    _, list_file = get_current_device_list()
    all_devices  = load_saved_devices(list_file)
    dev_by_ip    = {d["ip"]: d for d in all_devices}

    _pool      = {}
    _pool_lock = threading.Lock()

    drifted_list: list[tuple[str, int]] = []
    clean_list:   list[str]             = []
    error_list:   list[tuple[str, str]] = []

    def _check_one(entry: dict) -> None:
        device_ip = entry["device_ip"]
        hostname  = entry.get("hostname") or device_ip
        dev       = dev_by_ip.get(device_ip)
        if not dev:
            log.warning("drift_check: %s not in inventory", device_ip)
            error_list.append((hostname, "not in inventory"))
            return

        golden_text = _load_golden_config_file(device_ip)
        if golden_text is None:
            return

        try:
            conn    = get_persistent_connection(dev, _pool, _pool_lock)
            current = run_device_command(conn, "show running-config")
        except Exception as exc:
            log.warning("drift_check: SSH error on %s: %s", device_ip, exc)
            error_list.append((hostname, f"SSH error: {exc}"))
            return

        diff = list(difflib.unified_diff(
            _clean(golden_text),
            _clean(current),
            fromfile=f"{hostname} — golden config",
            tofile=f"{hostname} — running config",
            lineterm="",
        ))

        if not diff:
            log.debug("drift_check: %s clean", hostname)
            clean_list.append(hostname)
            return

        diff_text = "\n".join(diff[:200]) + ("\n[...truncated]" if len(diff) > 200 else "")
        log.info("drift_check: drift on %s (%d diff lines)", hostname, len(diff))
        drifted_list.append((hostname, len(diff)))

        add_approval(
            action_type     = "update_golden_config",
            description     = f"Config drift detected on {hostname} — {len(diff)} changed lines",
            device_ip       = device_ip,
            device_hostname = hostname,
            diff            = diff_text,
            action_params   = {"device_ip": device_ip, "hostname": hostname},
            context         = f"Detected by {triggered_by} drift check",
        )

    max_w = min(len(golden), 6)
    with __import__("concurrent.futures", fromlist=["ThreadPoolExecutor"]).ThreadPoolExecutor(
        max_workers=max_w, thread_name_prefix="drift"
    ) as ex:
        list(ex.map(_check_one, golden))

    checked = len(clean_list) + len(drifted_list) + len(error_list)

    if drifted_list:
        summary = (
            f"Drift detected on {len(drifted_list)} device(s): "
            + ", ".join(f"{h} ({n} lines)" for h, n in drifted_list)
            + ". Approval request(s) queued."
        )
    elif error_list and not clean_list:
        summary = (
            f"Could not reach {len(error_list)} device(s): "
            + ", ".join(h for h, _ in error_list)
        )
    else:
        summary = (
            f"All {len(clean_list)} device(s) clean — no config drift detected."
            + (f" ({len(error_list)} unreachable.)" if error_list else "")
        )

    log.info("drift_check: complete — %s", summary)

    return {
        "ok":          True,
        "checked":     checked,
        "drifted":     len(drifted_list),
        "clean":       len(clean_list),
        "errors":      [{"hostname": h, "reason": r} for h, r in error_list],
        "drifted_devices": [{"hostname": h, "diff_lines": n} for h, n in drifted_list],
        "summary":     summary,
        "timestamp":   timestamp,
        "triggered_by": triggered_by,
    }


# ---------------------------------------------------------------------------
# DriftChecker — background scheduler
# ---------------------------------------------------------------------------

class DriftChecker:
    """Standalone background drift-check scheduler.

    Runs independently of the AI assistant — the scheduler thread is always
    alive while the app is running; individual checks respect a configurable
    interval read from agent_timers.
    """

    def __init__(self) -> None:
        self._stop    = threading.Event()
        self._trigger = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running_lock = threading.Lock()
        self._running  = False         # True while a check is in flight
        self._last_result: Optional[dict] = None
        self._last_ts:    float = 0.0  # epoch of last completed check
        self._next_ts:    float = 0.0  # epoch of next scheduled check

        # Restore persisted timestamp so interval survives restarts
        state = _load_state()
        saved = state.get("last_check_ts", 0)
        if saved > 0:
            self._last_ts = saved
            interval = _get_interval()
            self._next_ts = saved + interval
        else:
            # First run — fire after startup grace period
            self._next_ts = time.time() + _STARTUP_GRACE

        # Also restore last result for display before the first check runs
        if state.get("last_result"):
            self._last_result = state["last_result"]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="drift-scheduler",
        )
        self._thread.start()
        log.info("drift_check: scheduler started (next check in %.0fs)",
                 max(0, self._next_ts - time.time()))

    def stop(self) -> None:
        self._stop.set()
        self._trigger.set()
        if self._thread:
            self._thread.join(timeout=5)

    def trigger(self) -> None:
        """Request an immediate drift check (non-blocking)."""
        self._next_ts = time.time()
        self._trigger.set()

    def set_disabled(self, disabled: bool) -> None:
        set_disabled(disabled)
        if not disabled:
            # Re-arm: schedule next run one interval from now
            self._next_ts = time.time() + _get_interval()
            self._trigger.set()

    def status(self) -> dict:
        interval = _get_interval()
        disabled = _is_disabled()
        return {
            "running":     self._running,
            "disabled":    disabled,
            "last_run":    self._last_result,
            "last_ts":     self._last_ts,
            "last_at":     time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._last_ts))
                           if self._last_ts else None,
            "next_ts":     self._next_ts if not disabled else None,
            "next_at":     time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._next_ts))
                           if (self._next_ts and not disabled) else None,
            "interval_s":  interval,
            "interval_h":  round(interval / 3600, 1),
        }

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        log.info("drift_check: scheduler loop running")
        while not self._stop.is_set():
            now      = time.time()
            due_in   = max(0.0, self._next_ts - now)
            # Wake up when due or when trigger() is called, whichever first
            self._trigger.wait(timeout=min(due_in + 1, 60))
            self._trigger.clear()

            if self._stop.is_set():
                break

            if _is_disabled():
                continue  # scheduler paused — keep loop alive so enable re-arms it

            if time.time() < self._next_ts:
                continue  # spurious wakeup — not time yet

            with self._running_lock:
                if self._running:
                    continue   # already in flight
                self._running = True

            try:
                result = run_drift_check(triggered_by="scheduled")
            except Exception as exc:
                log.exception("drift_check: unexpected error: %s", exc)
                result = {
                    "ok": False, "checked": 0, "drifted": 0, "clean": 0,
                    "errors": [{"hostname": "scheduler", "reason": str(exc)}],
                    "summary": f"Drift check failed: {exc}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "triggered_by": "scheduled",
                }
            finally:
                with self._running_lock:
                    self._running  = False
                self._last_result = result
                self._last_ts     = time.time()
                interval          = _get_interval()
                self._next_ts     = self._last_ts + interval
                _save_state({
                    "last_check_ts": self._last_ts,
                    "last_result":   result,
                    "next_ts":       self._next_ts,
                })

        log.info("drift_check: scheduler loop stopped")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_checker: Optional[DriftChecker] = None


def get_checker() -> DriftChecker:
    global _checker
    if _checker is None:
        _checker = DriftChecker()
    return _checker
