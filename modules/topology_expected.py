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

from modules.identity import UNVERIFIED as _UNVERIFIED

log = logging.getLogger(__name__)

STORE = "topology_expected.json"
#: Each declaration and withdrawal, who and when: History's "Expected islands".
LOG = "topology_expected_log.jsonl"
#: A weak point accepted by design (C1487; the operator, 2026-10-21: the course's topology has
#: single points of failure and only links on purpose, and a warning on the map reads as a
#: flaw): declared like an island, keyed `spof:<device>` or `bridge:<a>~<b>` (the ends sorted),
#: holding what it cut off when declared, so it warns again when the graph changes that.
SPOF, BRIDGE = "spof:", "bridge:"


def key_for(kind: str, device: str = "", a: str = "", b: str = "") -> str:
    """The declaration's key: a device for an island, `spof:<device>`, or `bridge:<a>~<b>`."""
    if kind == "spof":
        return SPOF + device
    if kind == "bridge":
        return BRIDGE + "~".join(sorted((a, b)))
    return device


def keys_naming(table: dict, device: str) -> list:
    """Every declaration in *table* that names *device*: its island, its SPOF, and each only
    link it is an end of (Retire withdraws them all: a retired name inherits nothing)."""
    return sorted(k for k in table or {}
                  if k in (device, SPOF + device)
                  or (k.startswith(BRIDGE) and device in k[len(BRIDGE):].split("~")))


def words_for(key: str) -> str:
    """A key as a person reads it: "edge1", "edge1 as a single point of failure", "the only link
    core1 ↔ edge1"."""
    if key.startswith(SPOF):
        return f"{key[len(SPOF):]} as a single point of failure"
    if key.startswith(BRIDGE):
        return f"the only link {' ↔ '.join(key[len(BRIDGE):].split('~'))}"
    return key


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


def declare(list_name: str, device: str, reason: str, actor: str, holds=None) -> dict:
    """Declare *device* (or a weak point's key, `key_for`) expected in *list_name*, with
    *reason*: ``{"ok", "error"}``. *holds*: what a weak point cut off when declared, kept with
    it. An unreadable store refuses (writing would erase the declarations it holds)."""
    return _change(list_name, device, actor, reason=reason, holds=holds)


def withdraw(list_name: str, device: str, actor: str) -> dict:
    """Withdraw a declaration: the device warns again if it is an island."""
    return _change(list_name, device, actor, reason=None)


def _change(list_name: str, device: str, actor: str, reason, holds=None) -> dict:
    from modules import filestore

    device = (device or "").strip()
    if not device:
        return {"ok": False, "error": "no device was named"}
    if reason is not None:
        reason = " ".join((reason or "").split())
        if len(reason) < 12:
            what = ("is apart on purpose" if device == words_for(device) else "is by design")
            return {"ok": False, "error": (
                f"say why {words_for(device)} {what}, in a few words (got {reason!r}): the "
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
            islands[device] = {"reason": reason, "by": actor or _UNVERIFIED,
                               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            if holds is not None:
                islands[device]["holds"] = sorted(holds)
        filestore.write_atomic(path, json.dumps({"islands": islands}, indent=1, sort_keys=True))
    action = "withdrew" if reason is None else "declared"
    log.info("topology_expected: %s %s %s in %s", actor, action, device, list_name)
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "action": action,
             "device": device, "reason": reason or "", "actor": actor or _UNVERIFIED,
             "list": list_name}
    try:
        with open(os.path.join(os.path.dirname(path), LOG), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("topology_expected: COULD NOT RECORD %s of %s by %s (%s)", action, device,
                  actor, exc)
        return {"ok": True, "error": "", "recorded": False,
                "record_error": f"{LOG} could not be written: {exc}"}
    return {"ok": True, "error": "", "recorded": True, "record_error": ""}


def history(data_dir: str) -> dict:
    """Every declaration and withdrawal in the network folder *data_dir*, oldest first:
    ``{"rows", "error"}``. Takes the folder (History holds the network's resolved paths), so a
    read never resolves, or creates, one."""
    path = os.path.join(data_dir or "", LOG)
    if not os.path.exists(path):
        return {"rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"rows": [json.loads(l) for l in fh if l.strip()], "error": ""}
    except (OSError, ValueError) as exc:
        return {"rows": [], "error": f"{LOG} could not be read: {exc}"}
