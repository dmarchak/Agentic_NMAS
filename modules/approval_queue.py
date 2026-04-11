"""
approval_queue.py — Persistent human-approval queue

The agent adds entries here instead of acting autonomously on actions that
are reversible but potentially destructive (updating a golden config,
reverting a device, etc.).  The user approves or rejects from the UI.

When approved, the action is executed immediately by the backend.

Storage: data/lists/{slug}/approval_queue.json  (per-list, like other list data)
Entries expire after EXPIRY_HOURS if not acted on.
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

    return {"ok": True, "entry": entry, "execution": execution}


# ---------------------------------------------------------------------------
# Action executors — called when user approves
# ---------------------------------------------------------------------------

def _execute(entry: dict) -> dict:
    """Dispatch to the correct executor based on action_type."""
    atype = entry.get("action_type", "")
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
    """Push the golden config back to the device (restore)."""
    # This is intentionally left as a stub — revert via SSH is complex and
    # should go through the AI agent with full verification. Flag it instead.
    return {
        "note": (
            "Revert requires AI agent execution with pre-change snapshot and CI verification. "
            "Open the AI chat and say: 'Revert <hostname> to golden config and verify with CI.'"
        )
    }
