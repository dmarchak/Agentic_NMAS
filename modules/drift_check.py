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

def _state_file(list_name: str = "") -> str:
    """Per list, not per installation.

    **What this file is, and is not.** It is a record plus two inputs, and
    the two are read at different times:

    * ``disabled`` — **live**. `_is_disabled()` re-reads it on every pass of
      the loop, so editing it takes effect within a minute.
    * ``last_check_ts`` — read **once, at process start**, to rebuild the
      schedule across a restart.
    * ``last_result`` — a record. Read at start for display, written after
      every run.

    **The schedule itself is in memory and the file cannot move it.**
    `DriftChecker._next_ts` is set at construction from
    ``last_check_ts + interval`` and thereafter only by the scheduler, by
    `trigger()`, by re-enabling, or by an interval change. Editing the file
    does not bring a run forward; only `trigger()` (the *Check now* button)
    does.

    It was ``DATA_DIR/drift_state.json`` while golden configs, approvals and
    the repo are all per list -- so disabling drift for one network disabled
    it for every network, and the "last run" shown on any list's panel
    belonged to whichever list ran most recently. One switch governing several
    networks is a switch whose position tells you nothing about the network
    you are looking at.
    """
    from modules.config import get_current_list_name, get_list_data_dir

    return os.path.join(get_list_data_dir(list_name or get_current_list_name()),
                        _STATE_FILE_NAME)


def _legacy_state_file() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, _STATE_FILE_NAME)


def _load_state(list_name: str = "") -> dict:
    """This list's state, migrating the installation-wide file forward once.

    The old file is **copied, not moved**: it is the only record that drift
    was ever switched on, and for one installation it is the only record of
    *when* and, by its stored last run, *why*.
    """
    path = _state_file(list_name)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    try:
        with open(_legacy_state_file(), encoding="utf-8") as fh:
            legacy = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}

    log.info("drift_check: adopting installation-wide state for list '%s'",
             list_name or "(current)")
    legacy["migrated_from"] = _legacy_state_file()
    # `_write_state`, not `_save_state`: the latter merges by loading, and
    # loading is what got us here.
    _write_state(legacy, list_name)
    return legacy


def _save_state(data: dict, list_name: str = "") -> None:
    """Merge into what is stored; never replace it wholesale.

    The scheduler's ``finally`` block wrote a fresh three-key dict, which
    dropped every key it did not itself set -- ``disabled`` among them. It was
    unreachable while disabled, so it never fired, but a switch that a
    completed run can silently flip is one bug away from switching itself back
    on, and the operator would have no record either way.
    """
    merged = _load_state(list_name)
    merged.update(data)
    _write_state(merged, list_name)


def _write_state(data: dict, list_name: str = "") -> None:
    path = _state_file(list_name)
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


def set_disabled(disabled: bool, actor: str = "") -> None:
    """Switch the scheduler off or on, and record that it happened.

    The state file was the **only** record that drift had ever been enabled,
    and it recorded nothing about the switch itself. Six months on, the
    reasoning behind a disabled checker was recoverable only by reading the
    last stored run and inferring it -- and the reason (baselines were ad hoc
    and stale) had been fixed for weeks with nothing to prompt a
    re-evaluation. A silenced check with no note is a check nobody will ever
    knowingly turn back on.
    """
    _save_state({
        "disabled":    bool(disabled),
        "disabled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                       if disabled else None,
        "disabled_by": actor or None if disabled else None,
    })


# ---------------------------------------------------------------------------
# Core drift logic (pure Python, no AI)
# ---------------------------------------------------------------------------

def run_drift_check(triggered_by: str = "scheduled") -> dict:
    """Check every device in the inventory for config drift.

    **The population is the inventory, not the golden store.** It used to
    iterate `_list_golden_configs()`, which listed the deprecated
    `golden_configs/` directory -- so a device onboarded after the migration,
    whose golden lives in `config_repo/`, was checked by nothing and appeared
    in no count. Not as an error, not as a skip: it was simply absent, and a
    report of "all 9 device(s) clean" over a 10-device inventory reads exactly
    like a report over a 9-device one.

    Every device now lands in exactly one bucket and the totals are asserted
    against the inventory size, so "checked 7 of 9" is sayable and the other
    two are named. A count that cannot be short is a count that cannot warn.

    Returns ``{ok, inventory, checked, drifted, clean, skipped, errors, ...}``.
    """
    from modules.ai_assistant import _load_golden_config_file
    from modules.approval_queue import add_approval
    from modules.device import get_current_device_list, load_saved_devices
    from modules.connection import get_persistent_connection
    from modules.commands import run_device_command
    from modules.jenkins_runner import is_jenkins_building

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    def _result(**kw):
        base = {"ok": True, "inventory": 0, "checked": 0, "drifted": 0,
                "clean": 0, "skipped": [], "errors": [],
                "drifted_devices": [], "summary": "",
                "timestamp": timestamp, "triggered_by": triggered_by}
        base.update(kw)
        return base

    try:
        if is_jenkins_building():
            log.info("drift_check: deferred — Jenkins build in progress")
            return _result(skipped_reason="Jenkins build in progress",
                           summary="Deferred — Jenkins build in progress")
    except Exception:
        pass

    _, list_file = get_current_device_list()
    devices = load_saved_devices(list_file)
    if not devices:
        log.info("drift_check: inventory is empty — nothing to check")
        return _result(summary="Inventory is empty — nothing to check")

    log.info("drift_check: %d device(s) in inventory [%s]", len(devices),
             triggered_by)

    _pool      = {}
    _pool_lock = threading.Lock()

    drifted_list: list[tuple[str, int]] = []
    clean_list:   list[str]             = []
    error_list:   list[tuple[str, str]] = []
    skip_list:    list[tuple[str, str]] = []

    def _check_one(dev: dict) -> None:
        device_ip = dev.get("ip", "")
        hostname  = dev.get("hostname") or device_ip or "(unnamed)"

        # Stale devices are inert — skip rather than open a session to a device
        # that is no longer part of this list.
        try:
            from modules.inventory import is_stale
            if is_stale(device_ip):
                log.info("drift_check: skipping stale device %s (%s)", hostname, device_ip)
                skip_list.append((hostname, "no longer in NetBox for this list"))
                return
        except ImportError:
            pass

        golden_text = _load_golden_config_file(device_ip)
        if golden_text is None:
            # Previously a bare `return` — the device left no trace at all.
            # "Has no baseline" is the single most actionable thing a drift
            # check can report, and it was the one thing it stayed silent about.
            log.info("drift_check: %s (%s) has no golden config — skipped",
                     hostname, device_ip)
            skip_list.append((hostname, "no golden config saved"))
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

    max_w = min(len(devices), 6)
    with __import__("concurrent.futures", fromlist=["ThreadPoolExecutor"]).ThreadPoolExecutor(
        max_workers=max_w, thread_name_prefix="drift"
    ) as ex:
        list(ex.map(_check_one, devices))

    checked     = len(clean_list) + len(drifted_list)
    accounted   = checked + len(error_list) + len(skip_list)
    unaccounted = len(devices) - accounted
    if unaccounted:
        # Not a silent discrepancy. A device that fell through every branch is
        # the exact failure this restructuring removed, so it is reported as a
        # device rather than as a smaller total.
        log.error("drift_check: %d device(s) produced no outcome", unaccounted)
        error_list.append(("(unaccounted)",
                           f"{unaccounted} device(s) produced no outcome — "
                           "this is a defect in the drift checker"))

    coverage = f"checked {checked} of {len(devices)}"
    if drifted_list:
        summary = (
            f"Drift detected on {len(drifted_list)} device(s): "
            + ", ".join(f"{h} ({n} lines)" for h, n in drifted_list)
            + f". Approval request(s) queued. ({coverage}.)"
        )
    elif checked == 0:
        summary = f"No device was checked. ({coverage}.)"
    else:
        # The coverage is stated on EVERY outcome, including the all-clean
        # one. "All 9 device(s) clean" reads identically for 9 of 9 and for 9
        # of 10, which is the sentence 3.3b exists to stop being sayable.
        summary = (f"All {len(clean_list)} checked device(s) clean — "
                   f"no config drift detected. ({coverage}.)")

    if skip_list:
        summary += " Not checked: " + ", ".join(
            f"{h} ({r})" for h, r in skip_list) + "."
    if error_list:
        summary += " Unreachable: " + ", ".join(h for h, _ in error_list) + "."

    log.info("drift_check: complete — %s", summary)

    return _result(
        inventory       = len(devices),
        checked         = checked,
        drifted         = len(drifted_list),
        clean           = len(clean_list),
        skipped         = [{"hostname": h, "reason": r} for h, r in skip_list],
        errors          = [{"hostname": h, "reason": r} for h, r in error_list],
        drifted_devices = [{"hostname": h, "diff_lines": n} for h, n in drifted_list],
        summary         = summary,
    )


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

    def set_disabled(self, disabled: bool, actor: str = "") -> None:
        """Forwards *actor* to the module-level recorder.

        Stage 3.3c added `actor` to `set_disabled()` and left this method --
        the one the route actually calls -- unchanged, so every attempt to
        toggle the scheduler from the panel raised `TypeError` before
        reaching the state file. The same shape as the `write_committed()`
        crash in the 1.4 repair: a caller written against a signature that
        does not exist, and tests that exercised the module function while
        the route went through the method.
        """
        set_disabled(disabled, actor=actor)
        if not disabled:
            # Re-arm: schedule next run one interval from now
            self._next_ts = time.time() + _get_interval()
            self._trigger.set()

    def status(self) -> dict:
        """What the scheduler will do next, and for which list.

        ``state`` is the field the panel reads: **disabled**, **idle** (on,
        nothing due yet) or **running**. They were distinguishable before only
        by noticing that ``next_at`` was null, and a scheduler that is alive
        and waiting looked exactly like one that is switched off.
        """
        from modules.config import get_current_list_name

        interval = _get_interval()
        list_name = get_current_list_name()
        state = _load_state(list_name)
        disabled = bool(state.get("disabled", False))

        if disabled:
            phase = "disabled"
        elif self._running:
            phase = "running"
        else:
            phase = "idle"

        # From the file, not from memory: one scheduler object serves every
        # list, so its in-memory last result belongs to whichever list ran
        # most recently, not necessarily the one being looked at.
        last_result = state.get("last_result") or (
            self._last_result if not state else None)
        last_ts = state.get("last_check_ts") or (
            self._last_ts if not state else 0)

        return {
            "list":        list_name,
            "state":       phase,
            "running":     self._running,
            "disabled":    disabled,
            "disabled_at": state.get("disabled_at"),
            "disabled_by": state.get("disabled_by"),
            "last_run":    last_result,
            "last_ts":     last_ts,
            "last_at":     time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_ts))
                           if last_ts else None,
            # Computed in memory, not read from the state file -- see
            # `_state_file`. Reported so the panel can say so rather than
            # presenting it as something the file decides.
            "next_from":   "memory",
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
                # `_save_state` merges. This used to hand `json.dump` a
                # fresh three-key dict, dropping `disabled` and anything else
                # the file held.
                # `next_ts` is deliberately NOT written. It was, and it was
                # read nowhere -- `__init__` rebuilds the schedule from
                # `last_check_ts + interval` and every other path sets
                # `self._next_ts` directly. A key that looks authoritative,
                # is not, and sits in the same file as `disabled` (which IS
                # live, re-read every iteration) cost an operator a
                # twenty-minute experiment: editing one works, editing the
                # other does nothing, with nothing on screen saying which.
                _save_state({
                    "last_check_ts": self._last_ts,
                    "last_result":   result,
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
