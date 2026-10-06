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


#: The key `_load_state` returns ALONE when the state file exists and cannot be read
#: (CONCURRENCY_AUDIT R19): never empty, never the legacy file.
UNREADABLE = "_unreadable"


class DriftStateUnreadable(RuntimeError):
    """The state file exists and cannot be read: nothing is written over it."""


class DriftRunning(RuntimeError):
    """A drift run for this list is already in progress, in this process or another."""

    def __init__(self, holder: dict):
        self.holder = holder or {}
        super().__init__(
            "A drift check is already running for this list (started "
            f"{self.holder.get('started_at', '?')}, {self.holder.get('triggered_by', '?')}, "
            f"process {self.holder.get('pid', '?')}); this one did not start. Its result "
            "will be on the panel when it finishes.")


def _state_lock(list_name: str = ""):
    """Every read-modify-write of a list's state, across processes (CONCURRENCY_AUDIT R19):
    one RLock in one function guarded it, so a run storing its result and a golden answering
    its rows, or the app and a second process, lost each other's update."""
    from modules.filestore import PathLock
    return PathLock(lambda: _state_file(list_name))


def _load_state(list_name: str = "") -> dict:
    """This list's state, migrating the installation-wide file forward once.

    The old file is **copied, not moved**: it is the only record that drift
    was ever switched on, and for one installation it is the only record of
    *when* and, by its stored last run, *why*.

    **Absent and unreadable are different** (CONCURRENCY_AUDIT R19). Only an ABSENT file
    adopts the legacy one: a torn read used to adopt it and write it over the list's state,
    which could drop `disabled`. An unreadable file is ``{UNREADABLE: why}``, which every
    writer refuses and the scheduler reads as paused.
    """
    path = _state_file(list_name)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
        return {UNREADABLE: f"{_STATE_FILE_NAME} is not a mapping"}
    except FileNotFoundError:
        pass
    except (ValueError, OSError) as exc:
        return {UNREADABLE: f"{_STATE_FILE_NAME} could not be read ({type(exc).__name__})"}

    try:
        with open(_legacy_state_file(), encoding="utf-8") as fh:
            legacy = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}

    with _state_lock(list_name):
        if os.path.exists(path):              # another writer created it meanwhile
            return _load_state(list_name)
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

    Under the state lock, across processes; an unreadable file raises
    `DriftStateUnreadable` with the file preserved beside it (R19).
    """
    with _state_lock(list_name):
        merged = _load_state(list_name)
        if UNREADABLE in merged:
            from modules.filestore import preserve_corrupt
            path = _state_file(list_name)
            preserve_corrupt(path, merged[UNREADABLE])
            raise DriftStateUnreadable(
                f"{merged[UNREADABLE]}, so nothing was written: saving would have replaced "
                "the disabled switch and the last run. The damaged file is preserved beside "
                "it; move it aside to start a fresh state.")
        merged.update(data)
        _write_state(merged, list_name)


def _write_state(data: dict, list_name: str = "") -> None:
    """Replaced atomically, a temp file per write (it was truncated in place)."""
    from modules.filestore import write_atomic

    path = _state_file(list_name)
    try:
        write_atomic(path, json.dumps(data, indent=2))
    except Exception as exc:
        log.warning("drift_check: could not save state: %s", exc)




def _run_lock_path(list_name: str = "") -> str:
    """``DATA_DIR/drift_runs/<list>.lock``, by the list's NAME, as device holds are: resolving
    a list's folder creates it, and a lock beside a relative device-list path landed in
    whatever the working directory was."""
    import re as _re

    from modules.config import DATA_DIR, get_current_list_name

    name = (list_name or get_current_list_name() or "default").lower()
    return os.path.join(DATA_DIR, "drift_runs",
                        (_re.sub(r"[^a-z0-9_.-]", "_", name) or "_") + ".lock")


def running_now(list_name: str = ""):
    """The run in progress for this list, by any process, or None. A READ."""
    try:
        import fcntl
    except ImportError:
        return None
    path = _run_lock_path(list_name)
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            text = os.read(fd, 1 << 16).decode("utf-8", "replace")
            try:
                return json.loads(text) if text.strip() else {}
            except ValueError:
                return {}
        fcntl.flock(fd, fcntl.LOCK_UN)
        return None
    finally:
        os.close(fd)


class _OneRun:
    """One drift run per list at a time, across processes (CONCURRENCY_AUDIT R19): Check
    now never set the scheduler's flag, so two people pressing it, or Check now during the
    scheduled run, ran two full passes, and the queue's check-then-append added two items
    for one device. An exclusive `flock` the kernel releases with its holder; a second run
    raises `DriftRunning` naming the first, never waits."""

    def __init__(self, path: str, triggered_by: str):
        self.path, self.triggered_by, self.fd = path, triggered_by, None

    def __enter__(self):
        try:
            import fcntl
        except ImportError:
            return self
        path = self.path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            text = os.read(fd, 1 << 16).decode("utf-8", "replace")
            os.close(fd)
            try:
                holder = json.loads(text) if text.strip() else {}
            except ValueError:
                holder = {}
            raise DriftRunning(holder) from None
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({
            "pid": os.getpid(), "triggered_by": self.triggered_by,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}).encode())
        self.fd = fd
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            import fcntl
            try:
                os.ftruncate(self.fd, 0)
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None
        return False


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


_UNREADABLE_SAID = set()


def _is_disabled(list_name: str = "") -> bool:
    """*list_name*'s switch (else the active list's). An unreadable state reads as PAUSED
    (R19): its switch cannot be known, and nothing a run produced could be recorded. Logged
    once per cause."""
    state = _load_state(list_name)
    if UNREADABLE in state:
        if state[UNREADABLE] not in _UNREADABLE_SAID:
            _UNREADABLE_SAID.add(state[UNREADABLE])
            log.error("drift_check: the scheduler is paused: %s", state[UNREADABLE])
        return True
    return bool(state.get("disabled", False))


def set_disabled(disabled: bool, actor: str = "", list_name: str = "") -> None:
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
    }, list_name)


# ---------------------------------------------------------------------------
# Core drift logic (pure Python, no AI)
# ---------------------------------------------------------------------------

def answer_by_golden(list_name: str, hosts, why: str) -> list:
    """A golden just recorded for *hosts* answers the stored run's rows for
    them (the operator, 2026-10-01: five Critical "has drifted" rows from the
    23:40 run stood after Save All recorded those devices at 23:52). The new
    golden IS the device as captured, so the device is at its golden now:
    each is moved from the run's drifted (or no-golden) list to clean, and the
    run's record says which, by what and when. Nothing is re-read; the next
    run measures again. Returns the hostnames answered; never raises."""
    names = {h for h in (hosts or []) if h}
    if not names:
        return []
    try:
        with _state_lock(list_name):
            state = _load_state(list_name)
            last = state.get("last_result")
            if not isinstance(last, dict):
                return []
            drifted = list(last.get("drifted_devices") or [])
            skipped = list(last.get("skipped") or [])
            gone = [d["hostname"] for d in drifted if d.get("hostname") in names]
            golden_now = [d["hostname"] for d in skipped if d.get("hostname") in names
                          and d.get("reason") == "no golden config saved"]
            answered = gone + golden_now
            if not answered:
                return []
            last["drifted_devices"] = [d for d in drifted if d.get("hostname") not in gone]
            last["skipped"] = [d for d in skipped if d.get("hostname") not in golden_now]
            last["drifted"] = len(last["drifted_devices"])
            last["clean"] = int(last.get("clean") or 0) + len(gone)
            last["checked"] = int(last.get("checked") or 0) + len(golden_now)
            at = time.strftime("%Y-%m-%d %H:%M:%S")
            last.setdefault("answered", []).extend(
                {"hostname": h, "at": at, "why": why} for h in answered)
            last["summary"] = ((last.get("summary") or "")
                               + f" Since this run: {', '.join(answered)} at its golden ({why}).")
            _save_state({"last_result": last}, list_name)
        log.info("drift_check: %s answered by a new golden (%s)", answered, why)
        return answered
    except Exception as exc:                   # noqa: BLE001
        log.error("drift_check: could not answer %s's drift rows: %s", sorted(names), exc)
        return []


def network_for(req, data=None) -> str:
    """The network a drift route acts on (C491): the one the request names (`?list=`, or
    `list_name` in its body), else the active one. The scheduler runs every network on its
    own; a route reads or changes ONE, named."""
    from modules.config import get_current_list_name
    from routes.list_param import named_list
    return ((data or {}).get("list_name") or "").strip() or named_list(req) or \
        get_current_list_name()


def run_drift_check(triggered_by: str = "scheduled", list_name: str = "") -> dict:
    """One drift run of *list_name* (else the active list), and only one at a time per list
    across processes (CONCURRENCY_AUDIT R19): raises `DriftRunning` naming the run in
    progress. Every read and write of the run is that list's (C491: its inventory, goldens,
    stale check and approval queue were the ACTIVE list's)."""
    from modules.config import get_current_list_name

    name = list_name or get_current_list_name()
    with _OneRun(_run_lock_path(name), triggered_by):
        result = _run_drift_check(triggered_by, name)
    result["list"] = name
    return result


def _run_drift_check(triggered_by: str = "scheduled", list_name: str = "") -> dict:
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
    from modules.ai_assistant import _golden_record
    from modules.approval_queue import add_approval
    from modules.filestore import StoreUnreadable
    from modules.device import get_current_device_list, load_saved_devices
    from modules.commands import run_device_command
    from modules.connection import close_persistent_connection, get_persistent_connection

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    def _result(**kw):
        base = {"ok": True, "inventory": 0, "checked": 0, "drifted": 0,
                "clean": 0, "skipped": [], "errors": [],
                "drifted_devices": [], "summary": "",
                "timestamp": timestamp, "triggered_by": triggered_by}
        base.update(kw)
        return base

    if list_name:
        from modules.nsot import listref
        list_file = listref.resolve(list_name).csv_path
    else:
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
    cert_list:    list[str]             = []
    comment_list: list[str]             = []

    def _check_one(dev: dict) -> None:
        device_ip = dev.get("ip", "")
        hostname  = dev.get("hostname") or device_ip or "(unnamed)"

        # Stale devices are inert — skip rather than open a session to a device
        # that is no longer part of this list.
        try:
            from modules.inventory import is_stale
            if is_stale(device_ip, list_name=list_name):
                log.info("drift_check: skipping stale device %s (%s)", hostname, device_ip)
                skip_list.append((hostname, "no longer in NetBox for this list"))
                return
        except ImportError:
            pass

        record = _golden_record(device_ip, list_name)
        golden_text = record["text"]
        if golden_text is None and record["refused"]:
            # A golden this tool will not use is not "no golden": saying so
            # would send the reader to save one that is already there.
            skip_list.append((hostname, f"golden refused: {record['refused']}"))
            return
        if golden_text is None:
            # Previously a bare `return` — the device left no trace at all.
            # "Has no baseline" is the single most actionable thing a drift
            # check can report, and it was the one thing it stayed silent about.
            log.info("drift_check: %s (%s) has no golden config — skipped",
                     hostname, device_ip)
            skip_list.append((hostname, "no golden config saved"))
            return

        from modules import config_read
        try:
            conn    = get_persistent_connection(dev, _pool, _pool_lock)
            # ONE read, checked (modules/config_read.py): a stitched read
            # would be drift that never happened, or hide drift that did.
            current = config_read.check(run_device_command(conn, "show running-config"),
                                        hostname, previous=golden_text)
        except config_read.UnreliableRead as exc:
            # The session may still carry the rest of the output: never
            # reused, or the next command on it reads this one's tail.
            close_persistent_connection(device_ip, _pool, _pool_lock)
            log.warning("drift_check: %s", exc)
            error_list.append((hostname, str(exc)))
            return
        except Exception as exc:
            log.warning("drift_check: SSH error on %s: %s", device_ip, exc)
            error_list.append((hostname, f"SSH error: {exc}"))
            return

        # The device's own self-signed certificate is regenerated at every
        # boot (normalize.strip_self_signed_certs): not drift, and said in one
        # line rather than drawn as its hex. Comment lines are not drift either
        # (2026-10-02: IOS-XE writes "! Call-home is enabled by Smart-Licensing."
        # itself, by licensing state, and r3's crash-reboot dropped it): set aside
        # by normalize.strip_comments and said in one line.
        from modules.nsot.normalize import (comment_note, self_signed_note,
                                            strip_comments, strip_self_signed_certs)
        diff = list(difflib.unified_diff(
            _clean("\n".join(strip_comments(strip_self_signed_certs(golden_text)))),
            _clean("\n".join(strip_comments(strip_self_signed_certs(current)))),
            fromfile=f"{hostname} — golden config",
            tofile=f"{hostname} — running config",
            lineterm="",
        ))
        note = self_signed_note(golden_text, current)
        if note:
            cert_list.append(hostname)
        c_note = comment_note(golden_text, current)
        if c_note:
            comment_list.append(hostname)

        if not diff:
            log.debug("drift_check: %s clean", hostname)
            clean_list.append(hostname)
            # An item queued by an earlier run no longer stands: this run, under
            # the rules in force now, finds the device at its golden.
            from modules.approval_queue import supersede_drift
            supersede_drift([hostname], f"the drift check at {timestamp} ({triggered_by}) "
                                        f"found {hostname} at its golden under the current "
                                        "rules, so the queued diff no longer stands",
                            by="drift check", list_name=list_name)
            return
        if note:
            diff.append(note)
        if c_note:
            diff.append(c_note)

        diff_text = "\n".join(diff[:200]) + ("\n[...truncated]" if len(diff) > 200 else "")
        log.info("drift_check: drift on %s (%d diff lines)", hostname, len(diff))
        drifted_list.append((hostname, len(diff)))

        try:
            add_approval(
                action_type     = "update_golden_config",
                description     = f"Config drift detected on {hostname} — {len(diff)} changed lines",
                device_ip       = device_ip,
                device_hostname = hostname,
                diff            = diff_text,
                action_params   = {"device_ip": device_ip, "hostname": hostname},
                context         = f"Detected by {triggered_by} drift check",
                list_name       = list_name,
            )
        except StoreUnreadable as exc:
            # The drift is recorded (it is in this run's result); the queue that would
            # carry its approval cannot be read, and Needs attention says so.
            log.error("drift_check: %s drifted and its approval could not be queued: %s",
                      hostname, exc)

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

    if cert_list:
        from modules.nsot.normalize import CERT_REGENERATED
        summary += (f" {CERT_REGENERATED[0].upper()}{CERT_REGENERATED[1:]}, not drift: "
                    + ", ".join(sorted(cert_list)) + ".")
    if comment_list:
        from modules.nsot.normalize import COMMENTS_DIFFER
        summary += (f" {COMMENTS_DIFFER[0].upper()}{COMMENTS_DIFFER[1:]}, not drift: "
                    + ", ".join(sorted(comment_list)) + ".")
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
    """Standalone background drift-check scheduler, for EVERY network on its own schedule
    (C491).

    It followed the active list: one schedule, one run of whichever list was active, and its
    result saved to whichever list was active at save time. So every other network went
    unchecked while one was active (Default's last run was the moment the throwaway network
    was made active). Now each network has its own next run (its last run plus the interval),
    its own switch and its own state; a run is for one named network; the active list
    decides nothing here.

    Runs independently of the AI assistant -- the scheduler thread is always alive while the
    app is running; the interval is read from agent_timers (one interval, every network)."""

    def __init__(self) -> None:
        self._stop    = threading.Event()
        self._trigger = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running_lock = threading.Lock()
        self._running: set = set()      # the networks with a run in flight here
        self._next: dict = {}           # network -> epoch of its next run
        self._started = time.time()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @staticmethod
    def networks() -> list:
        """Every network the installation holds, by name: each gets its own schedule."""
        from modules.nsot import listref
        return sorted(listref._registry())

    @staticmethod
    def _name(list_name: str = "") -> str:
        from modules.config import get_current_list_name
        return list_name or get_current_list_name()

    def next_ts(self, list_name: str) -> float:
        """*list_name*'s next run: its last recorded run plus the interval, or the startup
        grace for a network never checked. Rebuilt from its state file, never stored there."""
        if list_name not in self._next:
            last = 0.0
            try:
                last = float(_load_state(list_name).get("last_check_ts") or 0)
            except Exception:                  # noqa: BLE001
                last = 0.0
            self._next[list_name] = (last + _get_interval() if last > 0
                                     else self._started + _STARTUP_GRACE)
        return self._next[list_name]

    def is_running(self, list_name: str = "") -> bool:
        return self._name(list_name) in self._running

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="drift-scheduler")
        self._thread.start()
        log.info("drift_check: scheduler started for %d network(s)", len(self.networks()))

    def stop(self) -> None:
        self._stop.set()
        self._trigger.set()
        if self._thread:
            self._thread.join(timeout=5)

    def trigger(self, list_name: str = "") -> None:
        """Request an immediate drift check of *list_name* (else the active list)."""
        self._next[self._name(list_name)] = time.time()
        self._trigger.set()

    def rearm(self) -> None:
        """The interval changed: every network's next run is rebuilt from its last run."""
        self._next.clear()
        self._trigger.set()

    def set_disabled(self, disabled: bool, actor: str = "", list_name: str = "") -> None:
        """Switch *list_name*'s checks off or on, recording who (see `set_disabled`)."""
        name = self._name(list_name)
        set_disabled(disabled, actor=actor, list_name=name)
        if not disabled:
            self._next[name] = time.time() + _get_interval()
            self._trigger.set()

    def record(self, list_name: str, result: dict) -> None:
        """Store *list_name*'s run in ITS state file and schedule its next run. `_save_state`
        merges; `next_ts` is deliberately not written (it is rebuilt from the last run)."""
        now = time.time()
        self._next[list_name] = now + _get_interval()
        _save_state({"last_check_ts": now, "last_result": result}, list_name)

    def status(self, list_name: str = "") -> dict:
        """What the scheduler will do next for *list_name* (else the active list).

        ``state`` is the field the panel reads: **disabled**, **idle** (on, nothing due yet)
        or **running**."""
        name = self._name(list_name)
        interval = _get_interval()
        state = _load_state(name)
        unreadable = state.get(UNREADABLE)
        disabled = bool(state.get("disabled", False))
        # A run another person or process started is running too (R19).
        elsewhere = running_now(name)
        if unreadable:
            phase = "unreadable"
        elif disabled:
            phase = "disabled"
        elif name in self._running or elsewhere is not None:
            phase = "running"
        else:
            phase = "idle"
        last_result = state.get("last_result")
        last_ts = state.get("last_check_ts") or 0
        nxt = self.next_ts(name)
        return {
            "list":        name,
            "state":       phase,
            "running":     name in self._running or elsewhere is not None,
            "running_run": elsewhere,
            "unreadable":  unreadable,
            "disabled":    disabled,
            "disabled_at": state.get("disabled_at"),
            "disabled_by": state.get("disabled_by"),
            "last_run":    last_result,
            "last_ts":     last_ts,
            "last_at":     time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_ts))
                           if last_ts else None,
            # Computed in memory, not read from the state file -- see `_state_file`.
            "next_from":   "memory",
            "next_ts":     nxt if not disabled else None,
            "next_at":     time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(nxt))
                           if (nxt and not disabled) else None,
            "interval_s":  interval,
            "interval_h":  round(interval / 3600, 1),
        }

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def run_one(self, list_name: str, triggered_by: str = "scheduled") -> Optional[dict]:
        """One run of *list_name* by this scheduler, its result recorded in its own state;
        None when another run holds the network (it records its own; this retries in a
        minute, R19)."""
        with self._running_lock:
            if list_name in self._running:
                return None
            self._running.add(list_name)
        try:
            try:
                result = run_drift_check(triggered_by=triggered_by, list_name=list_name)
            except DriftRunning as exc:
                log.info("drift_check: %s's %s run not started: %s", list_name,
                         triggered_by, exc)
                self._next[list_name] = time.time() + 60
                return None
            except Exception as exc:            # noqa: BLE001
                log.exception("drift_check: %s: unexpected error: %s", list_name, exc)
                result = {
                    "ok": False, "checked": 0, "drifted": 0, "clean": 0, "list": list_name,
                    "errors": [{"hostname": "scheduler", "reason": str(exc)}],
                    "summary": f"Drift check failed: {exc}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "triggered_by": triggered_by,
                }
        finally:
            with self._running_lock:
                self._running.discard(list_name)
        try:
            self.record(list_name, result)
        except DriftStateUnreadable as exc:
            log.error("drift_check: %s's run was not recorded: %s", list_name, exc)
        return result

    def _loop(self) -> None:
        log.info("drift_check: scheduler loop running")
        while not self._stop.is_set():
            names = self.networks()
            # Sequential across networks: each run is already concurrent across its own
            # devices (`_run_drift_check`'s pool), and a network's run is one record.
            for name in names:
                if self._stop.is_set():
                    break
                if time.time() < self.next_ts(name):
                    continue
                if _is_disabled(name):
                    continue   # paused: its next run stays due, and enabling re-arms it
                self.run_one(name)
            waits = [max(0.0, self.next_ts(n) - time.time()) for n in names]
            # Wake when the soonest is due or on trigger(), whichever first; at least once a
            # minute, so a network added or a switch turned on is noticed.
            self._trigger.wait(timeout=min(min(waits) + 1 if waits else 60, 60))
            self._trigger.clear()
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
