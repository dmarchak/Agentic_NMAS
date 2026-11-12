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


def covering(network: str, device: str, at: float) -> dict:
    """The declaration covering *device* at *at* (its from to its until), or ``{}``. An
    unreadable record raises."""
    for r in reversed(_rows(network)):
        if r.get("device") == device and \
                float(r.get("from_epoch") or 0) <= float(at) <= float(r.get("until_epoch") or 0):
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
        open_drill = next((r for r in reversed(rows) if r.get("device") == device
                           and float(r.get("until_epoch") or 0) >= now), None)
        if open_drill:
            return {"ok": False, "error": (f"{device} has a fault drill declared until "
                                           f"{open_drill.get('until')} ({open_drill.get('id')}, "
                                           f"by {open_drill.get('by')}): one drill per device "
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


def declared(network: str) -> list:
    """Every declaration of *network*, newest first (History's rows). Raises when unreadable."""
    return list(reversed(_rows(network)))
