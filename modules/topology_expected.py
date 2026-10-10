"""modules/topology_expected.py — a network's EXPECTED islands: devices cabled apart on purpose,
each with why, who and when (P.11; the operator, 2026-10-10: "mark expected islands with their
reason, and keep the warning for a device that BECOMES an island").

A declaration, not a measurement: LLDP sees no link and cannot tell a device cabled apart by
design (a lab's own management segment) from one whose link failed. So a person declares it,
with a reason, from the Topology page, and the reader draws that island as expected instead of
warning. Kept beside the network's inventory (`lists/<slug>/topology_expected.json`), written
whole and atomically under a lock, never a value of the repository.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

STORE = "topology_expected.json"


def _path(list_name: str) -> str:
    from modules.nsot import listref
    return os.path.join(listref.resolve(list_name).data_dir, STORE)


def read(list_name: str) -> dict:
    """``{"state": "absent"|"ok"|"unreadable", "islands": {device: {reason, by, at}},
    "error"}``. Absent and unreadable are different states."""
    path = _path(list_name)
    if not os.path.exists(path):
        return {"state": "absent", "islands": {}, "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        islands = doc.get("islands") if isinstance(doc, dict) else None
        if not isinstance(islands, dict):
            raise ValueError("it holds no islands table")
        return {"state": "ok", "islands": islands, "error": ""}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "islands": {}, "error": f"{STORE} could not be read: {exc}"}


def declare(list_name: str, device: str, reason: str, actor: str) -> dict:
    """Declare *device* an expected island of *list_name*, with *reason*: ``{"ok", "error"}``.
    An unreadable store refuses (writing would erase the declarations it holds)."""
    return _change(list_name, device, actor, reason=reason)


def withdraw(list_name: str, device: str, actor: str) -> dict:
    """Withdraw a declaration: the device warns again if it is an island."""
    return _change(list_name, device, actor, reason=None)


def _change(list_name: str, device: str, actor: str, reason) -> dict:
    from modules import filestore

    device = (device or "").strip()
    if not device:
        return {"ok": False, "error": "no device was named"}
    if reason is not None:
        reason = " ".join((reason or "").split())
        if len(reason) < 12:
            return {"ok": False, "error": (
                f"say why {device} is apart on purpose, in a few words (got {reason!r}): the "
                "reason is what the map draws instead of the warning")}
    path = _path(list_name)
    with filestore.PathLock(lambda: path):
        got = read(list_name)
        if got["state"] == "unreadable":
            return {"ok": False, "error": got["error"] + ": nothing was written"}
        islands = dict(got["islands"])
        if reason is None:
            if device not in islands:
                return {"ok": False, "error": f"{device} is not declared expected: nothing to "
                                              "withdraw"}
            islands.pop(device)
        else:
            islands[device] = {"reason": reason, "by": actor or "unauthenticated",
                               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        filestore.write_atomic(path, json.dumps({"islands": islands}, indent=1, sort_keys=True))
    log.info("topology_expected: %s %s %s in %s", actor,
             "withdrew" if reason is None else "declared", device, list_name)
    return {"ok": True, "error": ""}
