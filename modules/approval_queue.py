"""approval_queue.py

Human-in-the-loop approval queue for AI-proposed network changes.

When the AI agent wants to perform a potentially destructive action (e.g.,
updating a golden config baseline or reverting a device), it submits an entry
here instead of acting immediately.  The user reviews and approves or rejects
from the UI; approved entries are executed at that point by the backend.
Entries auto-expire after 48 hours and are stored per device-list at
data/lists/{slug}/approval_queue.json.
"""

import json
import logging
import os
import time
import uuid
from typing import Optional

log = logging.getLogger(__name__)

EXPIRY_HOURS = 48   # auto-expire unreviewed approvals after 48 hours

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _queue_path() -> str:
    from modules.config import get_current_list_data_dir
    return os.path.join(get_current_list_data_dir(), "approval_queue.json")


def _load_queue() -> list:
    try:
        with open(_queue_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_queue(entries: list) -> None:
    path = _queue_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)


def _expire_old(entries: list) -> list:
    """Mark entries as expired if they are older than EXPIRY_HOURS."""
    cutoff = time.time() - EXPIRY_HOURS * 3600
    for e in entries:
        if e.get("status") == "pending":
            ts = e.get("created_ts", 0)
            if ts and ts < cutoff:
                e["status"]      = "expired"
                e["resolved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

#: Action types whose execution **ends in a confirmation** rather than in a
#: result — the operator is shown a freshly computed program and confirms it
#: under the normal hash discipline.
#:
#: These must never be bulk-approved. "Approve all" exists to clear a queue of
#: decided outcomes; looping a confirmation through it would either
#: auto-confirm programs nobody was shown — which is precisely what the confirm
#: hash exists to prevent — or stack N modal dialogs on one click. Skipping and
#: saying so is the only honest third option.
CONFIRM_ENDING_ACTIONS = ("revert_to_golden",)


def is_confirm_ending(entry: dict) -> bool:
    """Does approving this entry end in a confirmation the operator must give?"""
    return entry.get("action_type", "") in CONFIRM_ENDING_ACTIONS


def add_approval(
    action_type:  str,
    description:  str,
    device_ip:    str,
    device_hostname: str = "",
    diff:         str = "",
    action_params: Optional[dict] = None,
    context:      str = "",
) -> str:
    """
    Add a pending approval request.  Returns the new entry's ID.

    action_type values:
      'update_golden_config'  — save current running-config as new golden for device
      'revert_to_golden'      — restore golden config to device (destructive)
    """
    entries = _expire_old(_load_queue())

    # Deduplicate: don't add if there is already a pending entry for the same
    # device and action type (avoid flooding the queue with repeated drift checks)
    for e in entries:
        if (
            e.get("status") == "pending"
            and e.get("action_type") == action_type
            and e.get("device_ip")   == device_ip
        ):
            log.debug("approval_queue: skipping duplicate for %s / %s", action_type, device_ip)
            return e["id"]

    entry_id = uuid.uuid4().hex[:10]
    entry = {
        "id":              entry_id,
        "action_type":     action_type,
        "status":          "pending",        # pending | approved | rejected | expired
        "created_at":      time.strftime("%Y-%m-%d %H:%M:%S"),
        "created_ts":      time.time(),
        "expires_at":      time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(time.time() + EXPIRY_HOURS * 3600),
        ),
        "device_ip":       device_ip,
        "device_hostname": device_hostname or device_ip,
        "description":     description,
        "diff":            diff,
        "context":         context,
        "action_params":   action_params or {},
        "resolved_at":     None,
    }
    entries.append(entry)
    _save_queue(entries)
    log.info("approval_queue: added [%s] %s — %s", entry_id, action_type, description[:80])
    return entry_id


def get_pending() -> list:
    """Return all pending (not yet resolved, not expired) approval requests."""
    entries = _expire_old(_load_queue())
    _save_queue(entries)
    return [e for e in entries if e.get("status") == "pending"]


def get_all(limit: int = 100) -> list:
    """Return all entries (newest first), including resolved and expired ones."""
    entries = _expire_old(_load_queue())
    _save_queue(entries)
    return list(reversed(entries))[:limit]


def get_pending_count() -> int:
    return len(get_pending())


def resolve(entry_id: str, action: str) -> dict:
    """
    Resolve an approval entry.

    action: 'approve' | 'reject'

    If approved, executes the action immediately and returns the result.
    Returns {"ok": True, "entry": {...}, "execution": {...}}
    """
    entries = _expire_old(_load_queue())
    entry   = next((e for e in entries if e["id"] == entry_id), None)
    if not entry:
        return {"ok": False, "error": f"Approval {entry_id!r} not found"}
    if entry["status"] != "pending":
        return {"ok": False, "error": f"Approval is already {entry['status']}"}

    entry["status"]      = "approved" if action == "approve" else "rejected"
    entry["resolved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save_queue(entries)

    execution = {}
    if action == "approve":
        execution = _execute(entry)

        # A confirm-ending action is not finished by approving it. Approving
        # opens the preview; the work happens when the operator confirms the
        # program. Marking it approved here would leave the queue claiming a
        # change was made that nobody has sent yet — and would hide the item
        # from the operator who still has to act on it.
        if execution.get("needs_confirmation"):
            entry["status"] = "pending"
            entry["resolved_at"] = None
            entry["context"] = (
                "Awaiting confirmation: the command list is computed fresh and "
                "must be confirmed before anything is sent.")
            _save_queue(entries)
            log.info("approval_queue: %s handed to the confirmed restore path",
                     entry.get("device_hostname", entry["id"]))
            return {"ok": True, "entry": entry, "execution": execution,
                    "needs_confirmation": True}

        # If execution failed, revert the entry to pending so it can be retried.
        # A silent "approved" with a failed execution would let the drift check
        # generate the same approval again on the next restart.
        if execution.get("error"):
            entry["status"]      = "pending"
            entry["resolved_at"] = None
            entry["context"]     = f"Last attempt failed: {execution['error']}"
            _save_queue(entries)
            log.warning(
                "approval_queue: execution failed for %s — reverted to pending: %s",
                entry.get("device_hostname", entry["id"]), execution["error"],
            )

    return {"ok": True, "entry": entry, "execution": execution}


# ---------------------------------------------------------------------------
# Action executors — called when user approves
# ---------------------------------------------------------------------------

def mark_done(entry_id: str, note: str = "") -> dict:
    """Close an item whose work completed elsewhere.

    A confirm-ending item is finished by the restore it handed off to, not by
    ``resolve()``. Without this the item stays pending for ever and the
    operator learns to clear the queue by rejecting things — which is the habit
    that makes an approval queue worthless.
    """
    entries = _expire_old(_load_queue())
    entry = next((e for e in entries if e["id"] == entry_id), None)
    if not entry:
        return {"ok": False, "error": f"Approval {entry_id!r} not found"}
    if entry["status"] != "pending":
        return {"ok": False, "error": f"Approval is already {entry['status']}"}

    entry["status"] = "approved"
    entry["resolved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    entry["context"] = note or "Completed via the confirmed restore path"
    _save_queue(entries)
    log.info("approval_queue: [%s] closed — %s", entry_id, entry["context"])
    return {"ok": True, "entry": entry}


def _execute(entry: dict) -> dict:
    """Dispatch to the correct executor based on action_type."""
    atype = entry.get("action_type", "")

    # A device that has disappeared from NetBox is inert: its artifacts stay
    # readable, but nothing may act on it. See modules/inventory.is_stale.
    device_ip = entry.get("device_ip", "")
    try:
        from modules.inventory import is_stale, stale_message
        if device_ip and is_stale(device_ip):
            log.info("approval_queue: refusing [%s] — %s is stale", entry.get("id"), device_ip)
            return {"error": stale_message(device_ip)}
    except ImportError:
        pass

    try:
        if atype == "update_golden_config":
            return _exec_update_golden(entry)
        elif atype == "revert_to_golden":
            return _exec_revert_golden(entry)
        else:
            return {"error": f"Unknown action type: {atype}"}
    except Exception as exc:
        log.exception("approval_queue: execution error for [%s]: %s", entry["id"], exc)
        return {"error": str(exc)}


def _exec_update_golden(entry: dict) -> dict:
    """Save the current running-config as the new golden config for a device."""
    from modules.ai_assistant import (
        _save_golden_config_file, _get_running_config_for_golden,
        _safe_device_name, _get_golden_configs_dir,
    )
    device_ip = entry.get("device_ip", "")
    hostname  = entry.get("device_hostname", device_ip)
    if not device_ip:
        return {"error": "No device_ip in action_params"}

    try:
        # Fetch current running config via SSH
        config_text = _get_running_config_for_golden(device_ip, hostname)
        if config_text is None:
            return {"error": f"Could not fetch running config for {hostname} ({device_ip})"}

        # Use the shared helper so hostname-based naming is applied consistently
        _save_golden_config_file(device_ip, hostname, config_text)
        fname = f"{_safe_device_name(hostname)}.cfg"
        fpath = os.path.join(_get_golden_configs_dir(), fname)

        log.info("approval_queue: golden config updated for %s (%s)", hostname, device_ip)
        return {"saved": fpath, "device": device_ip, "hostname": hostname}
    except Exception as exc:
        return {"error": str(exc)}


def _exec_revert_golden(entry: dict) -> dict:
    """Hand off to the confirmed restore path. Sends nothing.

    A single-device ``revert_to_golden`` **is** a Mode A re-apply of that
    device's golden at HEAD, and the restore path already implements it with
    the confirm hash, the ASCII guard, provenance, ``error_pattern``, failure
    capture, rollback and the circuit breaker.

    This executor used to parse the stored diff and push the result straight at
    a device: every ``-`` line verbatim, every ``+`` line as ``no <command>``.
    No confirm hash, no mask check, no sendability check, no failure capture,
    and unbounded negation — which is precisely what
    ``assert_rollback_provenance()`` exists to bound.

    **The queued diff never reaches a device.** It was computed when the drift
    was noticed, which is not when the operator is looking, and a program the
    approver never read is what the confirm hash exists to prevent. It is
    returned as *advisory context* — what the agent saw — beside a program
    computed now, from the device as it is now.
    """
    hostname = entry.get("device_hostname") or entry.get("device_ip", "")
    return {
        "needs_confirmation": True,
        "restore": {"ref": "HEAD", "devices": [hostname],
                    "approval_id": entry.get("id", "")},
        # What the agent saw, when it saw it. Context for the reader, never an
        # input to anything that runs.
        "advisory_diff": entry.get("diff", ""),
        "advisory_note": (
            "This diff was captured when the drift was detected. The program "
            "you confirm is computed fresh from the device's current state — "
            "the two may differ, and the fresh one is what is sent."),
        "message": (
            f"Re-applying {hostname}'s golden config needs your confirmation. "
            "The exact command list is computed now and shown before anything "
            "is sent."),
    }
