"""drained.py

A device DRAINED by a person: taken out of service on purpose (traffic moved off it, for a
patch, a reload, a cable move), so the tool says so everywhere and does not raise a row for
the traffic falling that the drain itself causes (the operator, 2026-10-06, the smallest
form, approved without a mockup: a badge, and a Set/Clear card in the Actions menu).

**Set and cleared by a verified person, with a reason** (the authorisations' shape,
`authorisation.reason_problem`), from the device page's Actions menu (`routes/device_v2`),
recorded with who, when and why in the network's own store, append-only:
`<list data dir>/drained.jsonl`, one line per event (``drained`` or ``cleared``). A device's
state is its newest event. The device's History reads the same events.

**What it changes:** the Devices list and the device page draw a "Drained" badge (who, when,
why on hover); Needs attention lists a Grafana alert on a drained device under What was
checked, naming the drain, instead of raising it as a row. Nothing is sent to any device:
draining the TRAFFIC is the person's intent change (a deploy); this records that the device
is out of service.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

FILE = "drained.jsonl"
DRAINED, CLEARED = "drained", "cleared"

#: `mark()`'s steps, each named on its manual page (modules/manual.py OPERATIONS).
STEPS = (("check", "a verified person, a reason, a state to move from"),
         ("record", "the event appended to the network's drained record"))


class Refused(ValueError):
    """The mark was not set or cleared; the message says why."""


def _path(list_name: str) -> str:
    """The network's store, or "" when no network has that name (a read creates no list)."""
    from modules.nsot import listref
    if not list_name or not listref.exists(list_name):
        return ""
    return os.path.join(listref.resolve(list_name).data_dir, FILE)


def events(list_name: str, device: str = "") -> list:
    """Every recorded event, oldest first; only *device*'s when named. A missing store is no
    events; an unreadable line is skipped and logged, never a guessed state."""
    path = _path(list_name)
    if not path or not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                log.error("drained: %s line %d is not a record; skipped", path, n)
                continue
            if not device or row.get("device") == device:
                out.append(row)
    return out


def current(list_name: str) -> dict:
    """``{device: its drained event}`` for each device drained now (its newest event)."""
    latest = {}
    for row in events(list_name):
        latest[row.get("device")] = row
    return {d: row for d, row in latest.items() if d and row.get("state") == DRAINED}


def state_of(list_name: str, device: str) -> dict:
    """The device's drained event if it is drained now, else None."""
    return current(list_name).get(device)


def mark(list_name: str, device: str, state: str, *, why: str, by: str,
         verified: str) -> dict:
    """Record *device* drained or cleared, as *by*, with *why*. Refused, naming why: no
    verified person, a reason not the shape of one, a state it is already in, or no
    network of that name."""
    from modules.config import open_secure
    from modules.filestore import PathLock
    from modules.nsot.authorisation import reason_problem
    from modules.redact import redact_text

    if state not in (DRAINED, CLEARED):
        raise Refused(f"{state!r} is not drained or cleared")
    if not by:
        raise Refused("no verified person: marking a device drained is a person's word")
    problem = reason_problem({"line": f"{device} {state}", "reason": (why or "").strip()})
    if problem:
        raise Refused(problem)
    path = _path(list_name)
    if not path:
        raise Refused(f"no network is named {list_name!r}")
    with PathLock(path):
        now = state_of(list_name, device)
        if state == DRAINED and now:
            raise Refused(f"{device} is already drained (by {now.get('by')} at {now.get('at')})")
        if state == CLEARED and not now:
            raise Refused(f"{device} is not drained, so there is nothing to clear")
        entry = {"device": device, "state": state, "why": redact_text(why.strip()), "by": by,
                 "verified": verified,
                 "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    log.info("drained: %s %s by %s", device, state, by)
    return entry


def words(event: dict) -> str:
    """"drained by X at T: why", for a badge's hover and a note."""
    return (f"drained by {event.get('by') or 'someone'} at {event.get('at') or '?'}: "
            f"{event.get('why') or 'no reason recorded'}")
