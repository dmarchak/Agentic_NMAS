"""modules/topology_positions.py — a network's ARRANGED Topology map: where people put each device
(C661; the operator, 2026-10-11: "User should be able to move devices and save their topology",
and the decisions that followed: one shared layout per network, every move recorded with who and
when on History, Reset layout, a new device placed near its neighbours without moving arranged
ones).

The reader lays the map out by the cabling's springs as a STARTING point; a person drags a device
on the page and drops it, and the map as it then stands is saved as the network's layout, the
same for everyone, recorded with who moved which device and when. A device with no saved place (a
device added since) is placed near its neighbours (`topology_layout.layout`). Reset withdraws the
saved layout. Kept beside the network's inventory (`lists/<slug>/topology_positions.json`),
written whole and atomically under a lock; each move and reset is a line in
`topology_positions_log.jsonl`.
"""

import json
import logging
import math
import os
import time

log = logging.getLogger(__name__)

#: Its own names: today's (v1) Topology page keeps ITS layout as `topology_positions.json` in
#: the same folder, places as ``{"x", "y"}`` in its own coordinates. Sharing that name made the
#: v2 page read v1's places as its own and fail whole (the operator's report, 2026-10-11 03:46
#: UTC: "KeyError: 0" on the host's Default network). One owner per piece of state.
STORE = "topology_layout.json"
LOG = "topology_layout_log.jsonl"
#: The map's coordinate space is at least 880 wide (modules/topology_layout.W) and grows with the
#: map: the spring layout of 150 devices spans about 5,800 by 4,300 (measured 2026-10-11). A place
#: is kept inside a generous frame, so a device dragged far out is not lost.
MAX_X, MAX_Y = 20000, 20000
#: A network of thousands is not arranged by hand; this bounds what one save may carry.
MAX_NODES = 2000


def _path(list_name: str) -> str:
    from modules.nsot import listref
    return os.path.join(listref.resolve(list_name).data_dir, STORE)


def read(list_name: str) -> dict:
    """``{"state": "absent"|"ok"|"unreadable", "positions": {node: [x, y]}, "by", "at",
    "error"}``. Absent and unreadable are different states. A network that does not exist has
    no layout, and is never created by asking (register C51: resolving creates the folder)."""
    from modules.nsot import listref
    if not listref.exists(list_name):
        return {"state": "absent", "positions": {}, "by": "", "at": "", "error": ""}
    path = _path(list_name)
    if not os.path.exists(path):
        return {"state": "absent", "positions": {}, "by": "", "at": "", "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        positions = doc.get("positions") if isinstance(doc, dict) else None
        if not isinstance(positions, dict):
            raise ValueError("it holds no positions table")
        # Every place two finite numbers, or the layout is unreadable, naming the first that is
        # not: a page draws the generated layout and says why, never fails whole.
        for node, xy in positions.items():
            if not (isinstance(xy, list) and len(xy) == 2 and
                    all(isinstance(v, (int, float)) and not isinstance(v, bool) and
                        math.isfinite(v) for v in xy)):
                raise ValueError(f"{node}'s place is not two numbers (a {type(xy).__name__})")
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


def save(list_name: str, positions: dict, actor: str, moved: str = "") -> dict:
    """The network's layout after a person moved *moved*, for everyone: ``{"ok", "error",
    "recorded"}``."""
    return _change(list_name, positions, actor, "moved", moved)


def reset(list_name: str, actor: str) -> dict:
    """Withdraw the saved layout: the generated one is drawn again."""
    return _change(list_name, None, actor, "reset")


def _change(list_name: str, positions, actor: str, action: str, moved: str = "") -> dict:
    from modules import filestore

    path = _path(list_name)
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    set_aside = ""
    with filestore.PathLock(lambda: path):
        got = read(list_name)
        if got["state"] == "unreadable" and positions is None:
            # Reset of a layout that cannot be read: set aside under a dated name (kept, never
            # deleted), so the generated layout is drawn and a person can move devices again.
            set_aside = f"{path}.unreadable-{at.replace(':', '')}"
            os.replace(path, set_aside)
        elif got["state"] == "unreadable":
            return {"ok": False, "error": got["error"] + ": nothing was written; Reset layout "
                                                         "sets it aside"}
        elif positions is None:
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
    if moved:
        entry["device"] = moved
        entry["to"] = (positions or {}).get(moved)
    if set_aside:
        entry["set_aside"] = os.path.basename(set_aside)
    try:
        with open(os.path.join(os.path.dirname(path), LOG), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("topology_positions: COULD NOT RECORD %s by %s (%s)", action, actor, exc)
        return {"ok": True, "error": "", "recorded": False,
                "record_error": f"{LOG} could not be written: {exc}"}
    return {"ok": True, "error": "", "recorded": True, "record_error": "",
            "set_aside": os.path.basename(set_aside) if set_aside else ""}


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
