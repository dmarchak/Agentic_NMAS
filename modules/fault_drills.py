"""Fault drills: a fault declared BEFORE it is injected, so its incident is tagged a drill at
creation (the incident page's board, section I; the operator's decision of 2026-11-11).

**What a declaration is.** One device of one network, the expected fault in words, a bound of
at most `MAX_MINUTES` from now, and who declared it, recorded by `record_declared` in the
network's ``heal/fault_drills.jsonl`` (append-only, owner-only), never rewritten. It is made
on the device page's Actions › Declare a fault drill… (``POST /v2/fault-drills/declared``)
or on the host by ``scripts/nmas-fault-drill``; both call `record_declared`, the one writer.

**It silences nothing, holds nothing and explains nothing.** A planned-restart window quiets
its devices (`restarts.record_planned`); a declaration does none of that: a drill's fault is
read, judged, healed, verified and rolled back exactly as a real one.

**The tag, at creation** (`tag_for`, called only by `modules/heal/incidents.py`): an incident
whose device and opening time fall inside a declared, unexpired drill carries
``fault_drill: {id, declared_by, expects, until}`` from the write that opens it; an attached
member keeps its own. The tag is read from the incident's record (`tag_of`), never from a
declaration looked up later, so a declaration that expires or is cancelled never changes an
incident already tagged.

**What the tag changes (the operator's decision, 2026-11-11, word for word):** "declared fault
drills are exempt from guard 11 (same change healed twice in 24 h) and from the per-device
rate holds. Nothing else: every other guard, the verify, the rollback and the neighbour hold
apply to a drill exactly as to a real fault." So `heal.guards.g9_device_rate` and
`g11_repeat` do not apply to a drill's incident and count real heals only for a real one
("Drill heals are recorded and counted as drills, never in the real figures"); guard 10 (per
network) counts every heal, a drill's included, because it bounds the network's load.

**Refused:** a declaration with no person, no device of the network, a bound outside 1 to
`MAX_MINUTES` minutes, or an expected fault under `EXPECTS_WORDS` words; a second open drill
on the same device; and a declaration made after the fault: an incident already open on the
device is named with both times, since a declaration after the fault never makes it a drill.
There is no back-dating.

**Ended early** (`record_ended`; the operator's overnight item 9, 2026-11-12): once its fault is
healed, a person ends the drill (the device page's Actions › End the fault drill, or
``scripts/nmas-fault-drill <network> <device> --end``), and an end row is appended to the same
file, naming the declaration; nothing is rewritten. Every reader merges it (`_merge`): an ended
drill's window closes at min(its until, its end), so an incident on the device from the end on
is real, and a new drill may be declared on it. An incident tagged before the end keeps its tag
(the tag is the incident's, from its creation); nothing re-tags. Refused, naming both operands,
when the drill is unknown, already ended or already past its bound, or no person ends it.
"""

import json
import logging
import os
import time
import uuid

log = logging.getLogger(__name__)

FILE = "fault_drills.jsonl"
#: The tag's field on an incident, an attached member, a decision and a step-log row.
FIELD = "fault_drill"
#: The longest a drill may be declared for: 2.5 times the slowest trigger measured, an alert's
#: onset (a heartbeat's 300 s plus the rule's 60 s evaluation), as the board's I1 states.
MAX_MINUTES = 15
DEFAULT_MINUTES = 10
#: The expected fault in words, at least this many: "the EEM heartbeat applet removed".
EXPECTS_WORDS = 3
#: The declaration's steps, for its How it works page (docs/manual/how-it-works/fault-drill.md).
STEPS = (("check", "Check the declaration: a person, a device of the network, the fault in "
                   "words, a bound of at most 15 minutes"),
         ("before", "Refuse a declaration after the fault: an incident already open on the "
                    "device, or a drill already open on it"),
         ("record", "Record the declaration, append-only"))
#: The tag's keys, as the incident carries them.
TAG_KEYS = ("id", "declared_by", "expects", "until")
#: An end row's field: the declaration it ends (`record_ended`). A row without it is a
#: declaration.
ENDS = "ends"


class Refused(ValueError):
    """A declaration refused, in words."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def path(network: str) -> str:
    from modules.heal.incidents import _dir

    return os.path.join(_dir(network), FILE)


def read(network: str) -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``, oldest first. A line that
    will not parse makes the whole read unreadable."""
    p = path(network)
    if not os.path.exists(p):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(p, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [],
                "error": f"{network}'s fault drills cannot be read ({type(exc).__name__})"}
    return {"state": "ok", "rows": rows, "error": ""}


def _rows(network: str) -> list:
    got = read(network)
    if got["state"] == "unreadable":
        raise RuntimeError(got["error"])
    return got["rows"]


def _merge(rows: list) -> list:
    """The declarations among *rows*, oldest first, each with its end merged when one is
    recorded (``ended_at``, ``ended_epoch``, ``ended_by``, ``ended_via``), and ``end_epoch``
    on every one: its effective end, min(its until, its end). The first end row of a drill
    counts (`record_ended` writes no second)."""
    ends = {}
    for r in rows:
        if r.get(ENDS):
            ends.setdefault(r[ENDS], r)
    out = []
    for r in rows:
        if r.get(ENDS):
            continue
        d = dict(r)
        until = float(d.get("until_epoch") or 0)
        e = ends.get(d.get("id"))
        if e:
            d.update(ended_at=e.get("ended_at") or "",
                     ended_epoch=float(e.get("ended_epoch") or 0),
                     ended_by=e.get("by") or "", ended_via=e.get("via") or "")
            d["end_epoch"] = min(until, d["ended_epoch"])
        else:
            d["end_epoch"] = until
        out.append(d)
    return out


def _covers(d: dict, at: float) -> bool:
    """Does declaration *d* (merged) cover *at*: from its from to its until, and before its
    end when it was ended (an incident at the end or after it is real)?"""
    at = float(at)
    if not float(d.get("from_epoch") or 0) <= at <= float(d.get("until_epoch") or 0):
        return False
    return not d.get("ended_at") or at < float(d.get("ended_epoch") or 0)


def _open(d: dict, now: float) -> bool:
    """Is declaration *d* (merged) open at *now*: not past its until, and not ended?"""
    if d.get("ended_at") and float(d.get("ended_epoch") or 0) <= float(now):
        return False
    return float(d.get("until_epoch") or 0) >= float(now)


def covering(network: str, device: str, at: float) -> dict:
    """The declaration covering *device* at *at* (its from to its effective end), or ``{}``.
    An unreadable record raises."""
    for r in reversed(_merge(_rows(network))):
        if r.get("device") == device and _covers(r, at):
            return r
    return {}


def open_on(network: str, device: str, now: float = None) -> dict:
    """The drill open on *device* now (declared, not past its until, not ended), or ``{}``:
    the device page's End the fault drill and ``nmas-fault-drill --end`` end this one. An
    unreadable record raises, never "no drill"."""
    now = time.time() if now is None else float(now)
    for r in reversed(_merge(_rows(network))):
        if r.get("device") == device and _open(r, now):
            return r
    return {}


def tag_for(network: str, device: str, at: float):
    """The tag an incident opened on *device* at *at* carries, or None: **called only by
    `modules/heal/incidents.py`, in the write that opens the incident or attaches the
    member.** A record that cannot be read tags nothing, logged: the incident is then real,
    and every guard applies to it."""
    try:
        r = covering(network, device, at)
    except Exception as exc:                          # noqa: BLE001 (real, said in the log)
        log.error("fault drills: %s's declarations could not be read, so %s's incident at %s "
                  "is real: %s", network, device, _iso(at), exc)
        return None
    if not r:
        return None
    return {"id": r["id"], "declared_by": r.get("by") or "", "expects": r.get("expects") or "",
            "until": r.get("until") or ""}


def tag_of(record):
    """The tag *record* (an incident, a member, a decision, a step-log entry) carries from
    its creation, or None. Never a declaration looked up now."""
    tag = (record or {}).get(FIELD) if isinstance(record, dict) else None
    return dict(tag) if isinstance(tag, dict) and tag.get("id") else None


def is_drill(record) -> bool:
    return tag_of(record) is not None


def real_only(rows: list) -> list:
    """*rows* (heal decisions) without a drill's: the real figures."""
    return [r for r in rows or [] if not is_drill(r)]


def _open_incident(network: str, device: str) -> dict:
    """The open incident holding *device* (as its device or an attached member), or ``{}``.
    An unreadable store raises: whether the fault came first cannot be told."""
    from modules.heal import incidents

    got = incidents.read(network)
    if got["state"] == "unreadable":
        raise RuntimeError(got["error"])
    for inc in got["incidents"]:
        if inc.get("state") not in incidents.OPEN_STATES:
            continue
        if inc.get("device") == device:
            return inc
        for m in inc.get("attached") or []:
            if m.get("device") == device:
                return dict(inc, opened_at=m.get("attached_at") or inc.get("opened_at"))
    return {}


def _inventory_device(network: str, device: str) -> dict:
    from modules import device_page
    from modules.nsot import listref

    _ref, dev = device_page.find_device(device, ref=listref.resolve(network))
    return dev


def record_declared(network: str, device: str, *, minutes, expects: str, by: str,
                    actor_verified: str = "", via: str, script: str = "", reason: str = "",
                    now: float = None, inventory=None) -> dict:
    """Declare a fault drill on *device* of *network* from *now* for *minutes* (1 to
    `MAX_MINUTES`): ``{"ok": True, "record"}`` or ``{"ok": False, "error"}``, the refusal
    naming both operands it compared. *via* is ``device page`` or ``nmas-fault-drill``;
    *script* names the injecting script, *reason* is optional words. *inventory(network,
    device)* finds the device (the inventory by default). Silences nothing, holds nothing."""
    from modules import filestore
    from modules.config import open_secure
    from modules.nsot import listref

    now = time.time() if now is None else float(now)
    device = (device or "").strip()
    text = " ".join((expects or "").split())
    if not by or actor_verified == "none":
        return {"ok": False, "error": "a fault drill is declared by a person, and this request "
                                      f"names none (actor {by or 'none'})"}
    if not network or not listref.exists(network):
        return {"ok": False, "error": f"{network or 'no network'} is no network, so no drill "
                                      "is declared"}
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return {"ok": False, "error": f"the bound is a whole number of minutes, 1 to "
                                      f"{MAX_MINUTES}, not {minutes!r}"}
    if not 1 <= minutes <= MAX_MINUTES:
        return {"ok": False, "error": f"a fault drill lasts 1 to {MAX_MINUTES} minutes, and "
                                      f"{minutes} was asked"}
    if len(text.split()) < EXPECTS_WORDS:
        return {"ok": False, "error": (f"the expected fault is said in {EXPECTS_WORDS} words or "
                                       f"more (\"the EEM heartbeat applet removed on {device}\"), "
                                       "and "
                                       f"{len(text.split())} were given")}
    try:
        dev = (inventory or _inventory_device)(network, device)
    except Exception as exc:                          # noqa: BLE001 (named)
        return {"ok": False, "error": f"{device or 'no device'} is not a device of {network}: "
                                      f"{exc}"}
    with filestore.PathLock(path(network)):
        try:
            rows = _rows(network)
            inc = _open_incident(network, device)
        except Exception as exc:                      # noqa: BLE001 (named)
            return {"ok": False, "error": (f"whether {device} already has an incident or a "
                                           f"drill cannot be told ({exc}), so no drill is "
                                           "declared")}
        open_drill = next((r for r in reversed(_merge(rows)) if r.get("device") == device
                           and _open(r, now)), None)
        if open_drill:
            from modules import display_names           # board E2a: a person by display name

            who = display_names.people(open_drill.get("by") or "") or "an unnamed person"
            return {"ok": False, "error": (f"{device} has a fault drill declared until "
                                           f"{open_drill.get('until')} ({open_drill.get('id')}, "
                                           f"by {who}): one drill per device "
                                           f"at a time; this one, at {_iso(now)}, is not "
                                           "declared")}
        if inc:
            return {"ok": False, "error": (f"{device} already has an incident open "
                                           f"({inc.get('id')}, opened {inc.get('opened_at')}), "
                                           f"before this declaration at {_iso(now)}: a "
                                           "declaration after the fault never makes it a "
                                           "drill, so none is declared")}
        row = {"id": "fd-" + uuid.uuid4().hex[:10], "list": network, "device": device,
               "device_id": (dev or {}).get("_netbox_id") if isinstance(dev, dict) else None,
               "expects": text, "minutes": minutes, "from": _iso(now), "from_epoch": now,
               "until": _iso(now + minutes * 60), "until_epoch": now + minutes * 60,
               "by": by, "actor_verified": actor_verified or "", "via": via,
               "script": (script or "").strip(), "reason": (reason or "").strip(),
               "recorded_at": _iso(time.time())}
        os.makedirs(os.path.dirname(path(network)), exist_ok=True)
        with open_secure(path(network), "a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    log.info("fault drills: %s declared a drill on %s in %s until %s via %s: %s", by, device,
             network, row["until"], via, text)
    return {"ok": True, "record": row}


def record_ended(network: str, drill_id: str, *, by: str, actor_verified: str = "", via: str,
                 device: str = "", now: float = None) -> dict:
    """End the open fault drill *drill_id* of *network* (on *device*, when named) at *now*,
    before its bound:
    ``{"ok": True, "record", "drill"}`` (the end row, and the declaration with its end merged)
    or ``{"ok": False, "error"}``, the refusal naming both operands it compared. One end row is
    appended to the declarations' own file, under its lock; nothing is rewritten, and no
    incident already tagged changes. *via* is ``device page`` or ``nmas-fault-drill``. Sends,
    silences and holds nothing."""
    from modules import filestore
    from modules.config import open_secure
    from modules.nsot import listref

    now = time.time() if now is None else float(now)
    drill_id = (drill_id or "").strip()
    if not by or actor_verified == "none":
        return {"ok": False, "error": "a fault drill is ended by a person, and this request "
                                      f"names none (actor {by or 'none'})"}
    if not network or not listref.exists(network):
        return {"ok": False, "error": f"{network or 'no network'} is no network, so no drill "
                                      "is ended"}
    with filestore.PathLock(path(network)):
        try:
            rows = _rows(network)
        except Exception as exc:                      # noqa: BLE001 (named)
            return {"ok": False, "error": (f"whether {drill_id or 'the drill'} is open cannot be "
                                           f"told ({exc}), so no drill is ended")}
        d = next((x for x in _merge(rows) if x.get("id") == drill_id), None)
        if not d:
            return {"ok": False, "error": (f"{network} has no fault drill "
                                           f"{drill_id or '(none named)'} declared, so none is "
                                           "ended")}
        if device and d.get("device") != device:
            return {"ok": False, "error": (f"{drill_id} is a drill on {d.get('device')}, not on "
                                           f"{device}, so it is not ended from {device}")}
        if d.get("ended_at"):
            from modules import display_names

            who = display_names.people(d.get("ended_by") or "") or "an unnamed person"
            return {"ok": False, "error": (f"{drill_id} on {d.get('device')} was ended at "
                                           f"{d['ended_at']} by {who}, before this end at "
                                           f"{_iso(now)}: a drill is ended once")}
        if float(d.get("until_epoch") or 0) < now:
            return {"ok": False, "error": (f"{drill_id} on {d.get('device')} ended at its bound, "
                                           f"{d.get('until')}, before this end at {_iso(now)}: "
                                           "there is nothing to end")}
        row = {ENDS: drill_id, "list": network, "device": d.get("device") or "",
               "device_id": d.get("device_id"), "ended_at": _iso(now), "ended_epoch": now,
               "by": by, "actor_verified": actor_verified or "", "via": via,
               "recorded_at": _iso(time.time())}
        with open_secure(path(network), "a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    log.info("fault drills: %s ended drill %s on %s in %s at %s (its bound %s) via %s", by,
             drill_id, row["device"], network, row["ended_at"], d.get("until"), via)
    drill = next(x for x in _merge(rows + [row]) if x.get("id") == drill_id)
    return {"ok": True, "record": row, "drill": drill}


def declared(network: str) -> list:
    """Every declaration of *network*, newest first, each with its end merged when it was
    ended (History's rows). Raises when unreadable."""
    return list(reversed(_merge(_rows(network))))
