"""modules/topology_positions.py — a network's ARRANGED Topology map: where people put each device
and segment (C655; P.11 step 3; the operator, 2026-10-10: "topology needs to be re-arrangable by
the user (drag and drop). Don't enforce Core, Edge, etc placements. Let the user design the
diagram after initial generation").

The reader lays the map out once, by bands, as a STARTING point; a person drags nodes on the page
(Arrange) and saves, and that layout is the network's, the same for everyone: shared, recorded
with who and when, and drawn in place of the generated one. A node with no saved place (a device
added since) takes its generated place. Reset withdraws the saved layout. Kept beside the
network's inventory (`lists/<slug>/topology_positions.json`), written whole and atomically under a
lock; each save and reset is a line in `topology_positions_log.jsonl`.
"""

import json
import logging
import math
import os
import time

log = logging.getLogger(__name__)

STORE = "topology_positions.json"
LOG = "topology_positions_log.jsonl"
#: The map's coordinate space is 880 wide (modules/topology_layout.W); a place is kept inside
#: a generous frame, so a node dragged to an edge is not lost.
MAX_X, MAX_Y = 2000, 4000
#: A network of thousands is not arranged by hand; this bounds what one save may carry.
MAX_NODES = 2000


def _path(list_name: str) -> str:
    from modules.nsot import listref
    return os.path.join(listref.resolve(list_name).data_dir, STORE)


def read(list_name: str) -> dict:
    """``{"state": "absent"|"ok"|"unreadable", "positions": {node: [x, y]}, "by", "at",
    "error"}``. Absent and unreadable are different states."""
    path = _path(list_name)
    if not os.path.exists(path):
        return {"state": "absent", "positions": {}, "by": "", "at": "", "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        positions = doc.get("positions") if isinstance(doc, dict) else None
        if not isinstance(positions, dict):
            raise ValueError("it holds no positions table")
        return {"state": "ok", "positions": positions, "by": doc.get("by", ""),
                "at": doc.get("at", ""), "error": ""}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "positions": {}, "by": "", "at": "",
                "error": f"{STORE} could not be read: {exc}"}


def parse(text: str, known: set) -> tuple:
    """``(positions, error)`` from the page's JSON (``{node: [x, y]}``): every node one the map
    draws, every place two finite numbers inside the frame. Refuses the whole save on the first
    fault, naming it."""
    try:
        got = json.loads(text or "")
    except ValueError as exc:
        return {}, f"the layout sent could not be read ({exc})"
    if not isinstance(got, dict) or not got:
        return {}, "the layout sent holds no places"
    if len(got) > MAX_NODES:
        return {}, f"the layout sent holds {len(got)} places, more than {MAX_NODES}"
    out = {}
    for node, xy in got.items():
        if node not in known:
            return {}, f"{node!r} is not on this network's map"
        if not (isinstance(xy, list) and len(xy) == 2 and
                all(isinstance(v, (int, float)) and math.isfinite(v) for v in xy)):
            return {}, f"{node}'s place is not two numbers: {xy!r}"
        x, y = xy
        if not (0 <= x <= MAX_X and 0 <= y <= MAX_Y):
            return {}, f"{node}'s place ({x:.0f}, {y:.0f}) is outside the map's frame"
        out[node] = [round(x), round(y)]
    return out, ""


def save(list_name: str, positions: dict, actor: str) -> dict:
    """The network's layout, for everyone: ``{"ok", "error", "recorded"}``."""
    return _change(list_name, positions, actor, "arranged")


def reset(list_name: str, actor: str) -> dict:
    """Withdraw the saved layout: the generated one is drawn again."""
    return _change(list_name, None, actor, "reset")


def _change(list_name: str, positions, actor: str, action: str) -> dict:
    from modules import filestore

    path = _path(list_name)
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with filestore.PathLock(lambda: path):
        got = read(list_name)
        if got["state"] == "unreadable":
            return {"ok": False, "error": got["error"] + ": nothing was written"}
        if positions is None:
            if got["state"] == "absent":
                return {"ok": False, "error": "the map is not arranged: it is the generated "
                                              "layout already"}
            os.remove(path)
        else:
            filestore.write_atomic(path, json.dumps(
                {"positions": positions, "by": actor or "unauthenticated", "at": at},
                indent=1, sort_keys=True))
    log.info("topology_positions: %s %s %s (%s places)", actor, action, list_name,
             len(positions or {}))
    entry = {"at": at, "action": action, "places": len(positions or {}),
             "actor": actor or "unauthenticated", "list": list_name}
    try:
        with open(os.path.join(os.path.dirname(path), LOG), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("topology_positions: COULD NOT RECORD %s by %s (%s)", action, actor, exc)
        return {"ok": True, "error": "", "recorded": False,
                "record_error": f"{LOG} could not be written: {exc}"}
    return {"ok": True, "error": "", "recorded": True, "record_error": ""}


def history(data_dir: str) -> dict:
    """Every save and reset in the network folder *data_dir*, oldest first: ``{"rows",
    "error"}``. Takes the folder (History holds the network's resolved paths), so a read never
    resolves, or creates, one."""
    path = os.path.join(data_dir or "", LOG)
    if not os.path.exists(path):
        return {"rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"rows": [json.loads(l) for l in fh if l.strip()], "error": ""}
    except (OSError, ValueError) as exc:
        return {"rows": [], "error": f"{LOG} could not be read: {exc}"}
