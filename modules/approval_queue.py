"""approval_queue.py

The drift check's queue: an item per drifted device, waiting for a person.

Nothing here acts on a device or a golden. An item closes when its device is captured through
the confirmed capture operation (`mark_done`), when it is withdrawn with a reason (`withdraw`,
`supersede_drift`), or when it expires after 48 hours. The approve-and-execute path left with
the AI family (D15, 2026-10-14; its executors were removed by C783). Entries are stored per
device list at data/lists/{slug}/approval_queue.json.
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
# and the approve path (removed, C783) saved a stale list twice around its execution,
# overwriting whatever the drift run (up to six threads) added in between. Now every read-modify-write holds ONE
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

def add_approval(
    action_type:  str,
    description:  str,
    device_ip:    str,
    device_hostname: str = "",
    diff:         str = "",
    action_params: Optional[dict] = None,
    context:      str = "",
    list_name:    str = "",
) -> str:
    """
    Add a pending approval request.  Returns the new entry's ID.

    action_type values:
      'update_golden_config'  — save current running-config as new golden for device
      'revert_to_golden'      — restore golden config to device (destructive)

    *list_name*: the queue of the device's own list (C491: the drift check of a network that
    is not active queued its items in the active one's); else the active list's.
    """
    with _lock(list_name):
        return _add_locked(action_type, description, device_ip, device_hostname, diff,
                           action_params, context, list_name)


def _add_locked(action_type, description, device_ip, device_hostname, diff, action_params,
                context, list_name: str = "") -> str:
    entries = _expire_old(_load_queue(list_name))

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
    _save_queue(entries, list_name)
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


def get_pending(list_name: str = "") -> list:
    """Return all pending (not yet resolved, not expired) approval requests. A READ: it
    writes nothing (expiry applies in memory) and raises `StoreUnreadable` for a queue it
    cannot read."""
    return [e for e in _expire_old(_read(list_name)) if e.get("status") == "pending"]


def get_all(limit: int = 100) -> list:
    """Return all entries (newest first), including resolved and expired ones. A READ."""
    return list(reversed(_expire_old(_read())))[:limit]


# ---------------------------------------------------------------------------
# Closing an item: a capture, a withdrawal
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

    An item is finished by the capture or restore that did its work. Without
    this the item stays pending for ever and the operator learns to clear the
    queue by dismissing things — which is the habit that makes a queue
    worthless.
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
        # once recorded nobody).
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
