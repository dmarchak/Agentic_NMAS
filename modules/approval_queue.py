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

QUEUE_FILE = "approval_queue.json"


def _queue_path(list_name: str = "") -> str:
    """The queue of *list_name* when given (a caller that knows its list
    CARRIES it: a golden commit supersedes items in its own list's queue),
    else the active list's, as every older caller reads it."""
    if list_name:
        from modules.nsot import listref
        return os.path.join(listref.resolve(list_name).data_dir, QUEUE_FILE)
    from modules.config import get_current_list_data_dir
    return os.path.join(get_current_list_data_dir(), QUEUE_FILE)


# The store's concurrency (CONCURRENCY_AUDIT R4, 2026-10-02). It truncated in place with no
# lock, read an unreadable file as an empty queue, and its READS wrote it: the main page polls
# the queue from every tab every 30 s, so a torn read followed by that save erased the queue,
# and `resolve()` saved a stale list twice around its execution, overwriting whatever the
# drift run (up to six threads) added in between. Now every read-modify-write holds ONE
# cross-process lock (`filestore.PathLock`), writes replace the file atomically, an
# unreadable queue refuses every write (kept as `.corrupt-<ts>`) and is its own answer to a
# read, and reads write nothing (expiry applies in memory; a write persists it).

def _lock(list_name: str = ""):
    from modules.filestore import PathLock
    return PathLock(lambda: _queue_path(list_name))


def _load_queue(list_name: str = "") -> list:
    """The queue for a read-modify-write, under `_lock()`: [] when ABSENT; raises
    `filestore.StoreUnreadable` (the file preserved) when it cannot be read."""
    from modules.filestore import StoreUnreadable, read_json_for_write
    entries = read_json_for_write(_queue_path(list_name), empty=[])
    if not isinstance(entries, list):
        raise StoreUnreadable("approval_queue.json does not hold a list, so nothing was "
                              "written: saving would have replaced it")
    return entries


def _read(list_name: str = "") -> list:
    """The queue for a READ: writes nothing. [] when absent; an unreadable queue raises
    `filestore.StoreUnreadable`, because "no approval is waiting" and "the queue could not
    be read" must not share an answer."""
    return _read_path(_queue_path(list_name))


def read_list(ref) -> list:
    """The queue of an already-resolved list (`listref.ListRef`), for a READ that holds one:
    resolving it again by name creates the list's folder (`get_list_data_dir`), and a read
    creates no list (C359's History source did, caught by the suite's store check)."""
    return _read_path(os.path.join(ref.data_dir, QUEUE_FILE))


def _read_path(path: str) -> list:
    from modules.filestore import StoreUnreadable
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh)
        if not isinstance(entries, list):
            raise ValueError("not a list")
    except (OSError, ValueError) as exc:
        raise StoreUnreadable(f"the approval queue could not be read "
                              f"({type(exc).__name__})") from exc
    return entries


def _save_queue(entries: list, list_name: str = "") -> None:
    """Replace the queue atomically (a temp per write, then `os.replace`): never a
    truncate in place, which a concurrent read could catch half-written."""
    from modules.filestore import write_atomic
    write_atomic(_queue_path(list_name), json.dumps(entries, indent=2))


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
CONFIRM_ENDING_ACTIONS = ("revert_to_golden", "update_golden_config")


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
    with _lock():
        return _add_locked(action_type, description, device_ip, device_hostname, diff,
                           action_params, context)


def _add_locked(action_type, description, device_ip, device_hostname, diff, action_params,
                context) -> str:
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
        "status":          "pending",        # pending | approved | rejected | expired | withdrawn
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


def read_pending() -> tuple:
    """``(pending, None)`` or ``(None, reason)``, and it WRITES NOTHING.

    For a reader that polls (Needs attention, 7.2). `get_pending()` saves the
    queue on every call to persist expiry, and `_load_queue()` reads an
    unreadable file as empty, so a poll of it is a write, and a torn read
    followed by that write empties the queue (register C159). Here expiry is
    applied in memory only, and unreadable is its own answer, because "no
    approval is waiting" and "the queue could not be read" must not share
    one."""
    path = _queue_path()
    if not os.path.exists(path):
        return [], None
    try:
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh)
        if not isinstance(entries, list):
            raise ValueError("not a list")
    except (OSError, ValueError) as exc:
        return None, f"the approval queue could not be read ({type(exc).__name__})"
    cutoff = time.time() - EXPIRY_HOURS * 3600
    return [e for e in entries if e.get("status") == "pending"
            and not (e.get("created_ts") and e["created_ts"] < cutoff)], None


def get_pending() -> list:
    """Return all pending (not yet resolved, not expired) approval requests. A READ: it
    writes nothing (expiry applies in memory) and raises `StoreUnreadable` for a queue it
    cannot read."""
    return [e for e in _expire_old(_read()) if e.get("status") == "pending"]


def get_all(limit: int = 100) -> list:
    """Return all entries (newest first), including resolved and expired ones. A READ."""
    return list(reversed(_expire_old(_read())))[:limit]


def get_pending_count() -> int:
    return len(get_pending())


def resolve(entry_id: str, action: str, actor: str = "") -> dict:
    """An unreadable queue is a refusal naming it (`unreadable`), never an
    empty queue and never a raise at the route (CONCURRENCY_AUDIT R4)."""
    from modules.filestore import StoreUnreadable
    try:
        return _resolve_unguarded(entry_id=entry_id, action=action, actor=actor)
    except StoreUnreadable as exc:
        return {"ok": False, "error": str(exc), "unreadable": True}


def _resolve_unguarded(entry_id: str, action: str, actor: str = "") -> dict:
    """
    Resolve an approval entry.

    action: 'approve' | 'reject'

    If approved, executes the action immediately and returns the result.
    Returns {"ok": True, "entry": {...}, "execution": {...}}
    """
    # Compare-and-set under the lock: two approvers at once, the second is told it is
    # already decided, and the save writes the queue as it is NOW, never a stale copy.
    with _lock():
        entries = _expire_old(_load_queue())
        entry   = next((e for e in entries if e["id"] == entry_id), None)
        if not entry:
            return {"ok": False, "error": f"Approval {entry_id!r} not found"}
        if entry["status"] != "pending":
            return {"ok": False, "error": f"Approval is already {entry['status']}"}

        entry["status"]      = "approved" if action == "approve" else "rejected"
        entry["resolved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        # WHO decided, from the route's verified identity (C81). The executor
        # attributes what it commits to this person.
        entry["resolved_by"] = actor
        _save_queue(entries)
        entry = dict(entry)

    execution = {}
    if action == "approve":
        execution = _execute(entry, actor=actor)

        # A confirm-ending action is not finished by approving it. Approving
        # opens the preview; the work happens when the operator confirms the
        # program. Marking it approved here would leave the queue claiming a
        # change was made that nobody has sent yet — and would hide the item
        # from the operator who still has to act on it.
        if execution.get("needs_confirmation"):
            entry = _update_after(entry_id, entry["status"], {
                "status": "pending", "resolved_at": None,
                "context": ("Awaiting confirmation: the command list is computed fresh and "
                            "must be confirmed before anything is sent.")}) or entry
            log.info("approval_queue: %s handed to its confirmed operation (%s)",
                     entry.get("device_hostname", entry["id"]),
                     "capture" if execution.get("capture") else "restore")
            return {"ok": True, "entry": entry, "execution": execution,
                    "needs_confirmation": True}

        # If execution failed, revert the entry to pending so it can be retried.
        # A silent "approved" with a failed execution would let the drift check
        # generate the same approval again on the next restart.
        if execution.get("error"):
            entry = _update_after(entry_id, entry["status"], {
                "status": "pending", "resolved_at": None,
                "context": f"Last attempt failed: {execution['error']}"}) or entry
            log.warning(
                "approval_queue: execution failed for %s — reverted to pending: %s",
                entry.get("device_hostname", entry["id"]), execution["error"],
            )

    return {"ok": True, "entry": entry, "execution": execution}


def _update_after(entry_id: str, expected_status: str, fields: dict):
    """After an execution that ran OUTSIDE the lock: re-read the queue under it and update
    ONE entry, only if it still has the status this resolve gave it. Everything else in
    the queue (an item the drift run added meanwhile) is kept as it is now. Returns the
    entry, or None when it moved (said in the log, never overwritten)."""
    with _lock():
        entries = _load_queue()
        entry = next((e for e in entries if e.get("id") == entry_id), None)
        if entry is None or entry.get("status") != expected_status:
            log.warning("approval_queue: [%s] moved while it executed (now %s); left as "
                        "it is", entry_id, (entry or {}).get("status", "gone"))
            return None
        entry.update(fields)
        _save_queue(entries)
        return dict(entry)


# ---------------------------------------------------------------------------
# Action executors — called when user approves
# ---------------------------------------------------------------------------

def mark_done(entry_id: str, note: str = "", actor: str = "") -> dict:
    """An unreadable queue is a refusal naming it (`unreadable`), never an
    empty queue and never a raise at the route (CONCURRENCY_AUDIT R4)."""
    from modules.filestore import StoreUnreadable
    try:
        return _mark_done_unguarded(entry_id=entry_id, note=note, actor=actor)
    except StoreUnreadable as exc:
        return {"ok": False, "error": str(exc), "unreadable": True}


def _mark_done_unguarded(entry_id: str, note: str = "", actor: str = "") -> dict:
    """Close an item whose work completed elsewhere.

    A confirm-ending item is finished by the restore or capture it handed off
    to, not by
    ``resolve()``. Without this the item stays pending for ever and the
    operator learns to clear the queue by rejecting things — which is the habit
    that makes an approval queue worthless.
    """
    with _lock():
        entries = _expire_old(_load_queue())
        entry = next((e for e in entries if e["id"] == entry_id), None)
        if not entry:
            return {"ok": False, "error": f"Approval {entry_id!r} not found"}
        if entry["status"] != "pending":
            return {"ok": False, "error": f"Approval is already {entry['status']}"}

        entry["status"] = "approved"
        entry["resolved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        # WHO confirmed the operation that finished it (C326: an item closed here
        # recorded nobody, unlike one resolve() closes).
        entry["resolved_by"] = actor
        entry["context"] = note or "Completed via its confirmed operation"
        _save_queue(entries)
    log.info("approval_queue: [%s] closed — %s", entry_id, entry["context"])
    return {"ok": True, "entry": entry}


#: The kind a drift check queues: "record the running config as the golden".
DRIFT_ACTION = "update_golden_config"


def withdraw(entry_id: str, reason: str, by: str, list_name: str = "") -> dict:
    """An unreadable queue is a refusal naming it (`unreadable`), never an
    empty queue and never a raise at the route (CONCURRENCY_AUDIT R4)."""
    from modules.filestore import StoreUnreadable
    try:
        return _withdraw_unguarded(entry_id=entry_id, reason=reason, by=by, list_name=list_name)
    except StoreUnreadable as exc:
        return {"ok": False, "error": str(exc), "unreadable": True}


def _withdraw_unguarded(entry_id: str, reason: str, by: str, list_name: str = "") -> dict:
    """Close a pending item that no longer stands, recording WHY and BY WHAT
    (the operator, 2026-10-01: drift items created before C302 stopped
    counting a regenerated certificate waited for someone to approve a diff
    that no longer counted). ``withdrawn`` is its own state: never
    ``approved`` (nothing was approved) and never ``rejected`` (nobody
    refused it)."""
    if not reason or not by:
        return {"ok": False, "error": "a withdrawal records its reason and what withdrew it"}
    with _lock(list_name):
        entries = _expire_old(_load_queue(list_name))
        entry = next((e for e in entries if e["id"] == entry_id), None)
        if not entry:
            return {"ok": False, "error": f"Approval {entry_id!r} not found"}
        if entry["status"] != "pending":
            return {"ok": False, "error": f"Approval is already {entry['status']}"}
        entry.update(status="withdrawn", resolved_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                     withdrawn_reason=reason, withdrawn_by=by)
        _save_queue(entries, list_name)
    log.info("approval_queue: [%s] withdrawn by %s -- %s", entry_id, by, reason)
    return {"ok": True, "entry": entry}


def supersede_drift(hostnames, reason: str, by: str, list_name: str = "",
                    before_ts: float = None, leave=()) -> list:
    """Withdraw every PENDING drift item for *hostnames* created before
    *before_ts* (default now): a newer golden or a clean drift run means the
    diff it carries no longer describes the device. Returns the ids
    withdrawn. Never raises: a queue it cannot read leaves the items as they
    are and says so in the log. *leave* names items a caller was HANDED and
    closes itself (a capture opened from the queue marks its own item done)."""
    names = {h for h in (hostnames or []) if h}
    leave = set(leave or ())
    if not names:
        return []
    cutoff = time.time() if before_ts is None else before_ts
    try:
        entries = _read(list_name)
    except Exception as exc:                   # noqa: BLE001
        log.error("approval_queue: could not read the queue to supersede %s: %s",
                  sorted(names), exc)
        return []
    done = []
    for e in entries:
        if (e.get("status") == "pending" and e.get("action_type") == DRIFT_ACTION
                and e.get("device_hostname") in names
                and float(e.get("created_ts") or 0) < cutoff and e["id"] not in leave):
            if withdraw(e["id"], reason, by, list_name).get("ok"):
                done.append(e["id"])
    return done


def _execute(entry: dict, actor: str = "") -> dict:
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
            return _exec_update_golden(entry, actor=actor)
        elif atype == "revert_to_golden":
            return _exec_revert_golden(entry)
        else:
            return {"error": f"Unknown action type: {atype}"}
    except Exception as exc:
        log.exception("approval_queue: execution error for [%s]: %s", entry["id"], exc)
        return {"error": str(exc)}


def _exec_update_golden(entry: dict, actor: str = "") -> dict:
    """Hand off to the capture operation. Reads nothing, records nothing.

    A drift item's "make the running config the golden" IS a capture of one
    device, and the capture operation already implements it: the device is
    read now, the diff against its golden and its departure from committed
    intent are previewed, the confirm is bound to the capture's hash, the
    device is held while it is recorded, and the commit names the verified
    person (`Source: capture`).

    This executor read the device and committed with NO preview, one click
    per item: a second capture path inside the queue, and the least guarded
    one, since drift queues an item for every drifted device (minimalism,
    NSOT_STAGE7_PLAN section 6a; register C105). Its history: it committed
    as `ai-agent` until C81, and required an approving person after.

    The queued diff is what the drift check saw, when it saw it: context,
    never an input, as for a revert.
    """
    hostname = entry.get("device_hostname") or entry.get("device_ip", "")
    if not hostname:
        return {"error": "No device named in the approval item"}
    return {
        "needs_confirmation": True,
        "capture": {"devices": [hostname],
                    "approvals": {hostname: [entry.get("id", "")]}},
        "advisory_diff": entry.get("diff", ""),
        "message": (f"Opening the capture preview for {hostname}: its running config "
                    "is read NOW and recorded only when you confirm it."),
    }


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
