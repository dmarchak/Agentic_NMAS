"""What is running on the devices now, and what finished recently: one read for every screen
that draws it (today's in-flight panel through `/operations/in_flight`, and Settings ›
Installation › Diagnostics, board F4, for every network at once).

Register C99: a restore ran for fifty seconds with nothing on screen, the operator concluded it
had staged something, started a deploy of the same device, and the silence produced a second
change. C98's per-device lock already records who holds each device, since when, and its last
progress step, across processes (the CLIs included). Operations that FINISHED in the last half
hour come from their receipts, so a reload in the middle of one no longer loses its result.

A READ: it lists lock files and reads the receipt logs; it writes nothing.
"""

import calendar
import time

#: How far back "finished recently" reaches. Long enough to outlive a reload and a coffee;
#: short enough that the panel is about now.
RECENT_SECONDS = 1800
NOT_RECORDED = ("A capture writes no receipt: its golden commit is its record, on the Git "
                "tab.")


def recent(list_name: str, now: float) -> tuple:
    """``(rows, state)`` from *list_name*'s receipts: deploy and restore, per device, newest
    first, inside RECENT_SECONDS. A capture writes no receipt (its commit is its record)."""
    from modules.nsot import receipts

    got = receipts.read(list_name, limit=100)
    if got["state"] != "ok":
        return [], got["state"]
    rows = []
    for r in got["rows"]:
        try:
            at = calendar.timegm(time.strptime(r.get("at", ""), "%Y-%m-%dT%H:%M:%SZ"))
        except (ValueError, OverflowError):
            continue
        if now - at > RECENT_SECONDS:
            break                                   # newest first
        rows.append({"device": r.get("device", ""), "action": r.get("action", ""),
                     "outcome": r.get("outcome", ""), "at": r.get("at", ""),
                     "actor": r.get("actor", ""), "reason": r.get("reason", ""),
                     "commit_state": r.get("commit_state", "")})
    return rows, "ok"


def read(list_name: str, now: float = None) -> dict:
    """*list_name*'s held devices and running operations, and its recent receipts:
    ``{"running", "recent", "recent_state"}``. An operation that holds no device (a NetBox
    preview or import) is running too, in the same row shape. Raises on an unreadable lock
    folder: the caller says it."""
    from modules import op_progress
    from modules.nsot import device_ops

    now = time.time() if now is None else now
    running = device_ops.in_flight(list_name, now) + op_progress.running(now)
    rows, state = recent(list_name, now)
    return {"running": running, "recent": rows, "recent_state": state}


def read_all(networks, now: float = None) -> dict:
    """Every network's: the running operations (each held device once, with its network) and
    the recent receipts, newest first. A network whose read failed is named, never dropped:
    ``{"running", "recent", "unread": [(network, why)], "window_s"}``."""
    from modules import op_progress
    from modules.nsot import device_ops

    now = time.time() if now is None else now
    running, recent_rows, unread = [], [], []
    for name in networks:
        try:
            running += [dict(r, list=name) for r in device_ops.in_flight(name, now)]
            rows, state = recent(name, now)
            if state not in ("ok", "absent"):    # absent: no receipt yet, never deployed
                unread.append((name, f"its receipts are {state}"))
            recent_rows += [dict(r, list=name) for r in rows]
        except Exception as exc:                      # noqa: BLE001
            unread.append((name, f"{type(exc).__name__}: {exc}"))
    running += op_progress.running(now)
    recent_rows.sort(key=lambda r: r.get("at", ""), reverse=True)
    return {"running": running, "recent": recent_rows, "unread": unread,
            "window_s": RECENT_SECONDS}
