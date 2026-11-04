"""Heal incidents: one per cause, each a device to check, and the per-network heal lock (board
H, part H2; docs/HEAL_TO_INTENT.md sections 3 and 4). Deterministic; no device, no AI.

**What an incident is.** Each trigger asks one question, "check this device now" (section 3);
none of them heals. A trigger is SIGHTED into its network's incidents (`sight`): the device's
open incident takes it, or a new one opens. An incident holds its device, its triggers (each
with its kind, time, source and words), the reads the detect pass made of it
(`modules/heal/detect.py`) and, once the grace period settles, how it settled. Its states:
- ``watching``: open, its reads being made (detect's);
- ``ready``: settled (`grace.SETTLED_STATES`), waiting for the decision. **This is where H2
  ends and H3 begins:** `ready` lists them, and the decision takes one with `claim`;
- ``claimed``: the decision has it (H3, then H4's act and verify); it closes it;
- ``closed``: with why. Closed incidents are kept, the newest `CLOSED_KEPT`; the step log
  (H6) is the record.

**One incident per device at a time:** a device is the device of at most one open incident, or
a member attached to one, never both and never two.

**One incident per cause: the fold** (PHASE8_PLAN 20.5). A trigger is a CAUSE (the device
itself changed: a configuration-change line from outside Mercury, or the drift record) or a
SYMPTOM (an alert, an adjacency down, a logged adjacency drop). A symptom on a device with no
open incident of its own is ATTACHED to an open incident when:
- the incident's device is the far end of the symptom's link (an adjacency, or an alert naming
  an interface: the trigger's ``related``); or
- the incident's device CHANGED and the symptom's device is inside its blast radius
  (`blast_radius.radius`: the devices Mercury loses reach to without it, from committed
  intent's IPv4 subnets; a radius that cannot be judged, IPv6 alone included, folds nothing
  and says why).
A cause on a device with no incident opens one and takes in the open symptom-only incidents its
radius or its links hold. A cause on an attached member makes it the incident's device when the
incident's own device only showed a symptom (the member changed, the device it was attached to
did not); when both changed, the member is moved to an incident of its own and each names the
other (``related``): a cause spanning devices is the decision's to refuse (section 5, Tier 4).
An attached device is still read, and is never healed on its own.

**The per-network lock** (`HealLock`): one detect pass or decision per network at a time,
across processes, an exclusive `flock` the kernel releases with its holder, refused by name
(`HealBusy`, the holder's who, what and when), never waited on: `scheduled_rotation.RunLock`'s
pattern. The store itself is written under its own `filestore.PathLock`, so a trigger from a
reader's thread is never refused by a pass in progress.
"""

import json
import logging
import os
import time
import uuid

log = logging.getLogger(__name__)

STORE_DIR = "heal"
FILE = "incidents.json"
LOCK_FILE = "heal.lock"
VERSION = 1
#: The closed incidents kept in the working store (the step log, H6, is the record).
CLOSED_KEPT = 200
#: The newest triggers and reads kept on one incident; the count seen is kept beside them.
TRIGGERS_KEPT = 100
READS_KEPT = 20

CAUSE_KINDS = ("config_change", "drift")
SYMPTOM_KINDS = ("alert", "adjacency", "adjacency_log", "duplicate_router_id")
KIND_WORDS = {"config_change": "a configuration change from outside Mercury",
              "drift": "the drift check found it departed from its golden",
              "alert": "a firing alert", "adjacency": "a routing adjacency down",
              "adjacency_log": "a logged routing adjacency drop",
              "duplicate_router_id": "a duplicate OSPF router-id logged (C2446)"}
OPEN_STATES = ("watching", "ready", "claimed")
STATES = OPEN_STATES + ("closed",)


class HealBusy(Exception):
    """Another detect pass or decision holds the network: ``holder`` says who, what and when."""

    def __init__(self, network: str, holder: dict):
        self.network, self.holder = network, holder or {}
        super().__init__(
            f"self-healing on {network} is busy: {self.holder.get('trigger') or '?'} by "
            f"{self.holder.get('actor') or 'an unrecorded caller'} since "
            f"{self.holder.get('started_at') or 'an unrecorded time'} (pid "
            f"{self.holder.get('pid') or '?'}); one at a time per network, so nothing was "
            "started")


class Refused(ValueError):
    """A change to an incident refused, in words."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _dir(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), STORE_DIR)


def path(network: str) -> str:
    return os.path.join(_dir(network), FILE)


class HealLock:
    """One detect pass or decision per network at a time, across processes; a second raises
    `HealBusy` naming the first, never waits."""

    def __init__(self, network: str, actor: str, trigger: str):
        self.network, self.actor, self.trigger, self.fd = network, actor, trigger, None

    def __enter__(self):
        import fcntl

        from modules.nsot import listref

        if not listref.exists(self.network):
            raise Refused(f"{self.network} is no network, so it is not healed")
        lock = os.path.join(_dir(self.network), LOCK_FILE)
        os.makedirs(os.path.dirname(lock), exist_ok=True)
        fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            text = os.read(fd, 1 << 16).decode("utf-8", "replace")
            os.close(fd)
            try:
                holder = json.loads(text) if text.strip() else {}
            except ValueError:
                holder = {}
            raise HealBusy(self.network, holder) from None
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({"pid": os.getpid(), "actor": self.actor,
                                 "trigger": self.trigger,
                                 "started_at": _iso(time.time())}).encode())
        self.fd = fd
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            import fcntl
            try:
                os.ftruncate(self.fd, 0)
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None
        return False


# ── The store ───────────────────────────────────────────────────────────────────────────────

def _empty() -> dict:
    return {"version": VERSION, "incidents": []}


def read(network: str) -> dict:
    """*network*'s incidents: ``{"state": "ok"|"absent"|"unreadable", "incidents", "error"}``,
    oldest first. A read creates nothing; absent and unreadable are different facts."""
    p = path(network)
    if not os.path.exists(p):
        return {"state": "absent", "incidents": [], "error": ""}
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        return {"state": "ok", "incidents": list(doc.get("incidents") or []), "error": ""}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "incidents": [],
                "error": f"{network}'s heal incidents cannot be read ({type(exc).__name__})"}


def _mutate(network: str, fn):
    """Read, change and replace *network*'s store under its lock; *fn(doc)* changes it in place
    and returns the answer. A store that cannot be read raises `filestore.StoreUnreadable`
    (and is preserved), never replaced by an empty one. A network that does not exist is
    refused: a write creates no network."""
    from modules import filestore
    from modules.nsot import listref

    if not network or not listref.exists(network):
        raise Refused(f"{network or 'no network'} is no network, so nothing is recorded for it")
    p = path(network)
    with filestore.PathLock(p):
        doc = filestore.read_json_for_write(p, empty=_empty())
        doc.setdefault("incidents", [])
        out = fn(doc)
        closed = [i for i in doc["incidents"] if i.get("state") == "closed"]
        if len(closed) > CLOSED_KEPT:
            drop = {i["id"] for i in closed[:len(closed) - CLOSED_KEPT]}
            doc["incidents"] = [i for i in doc["incidents"] if i["id"] not in drop]
        filestore.write_atomic(p, json.dumps(doc, indent=1, sort_keys=True))
    return out


def _open(doc: dict) -> list:
    return [i for i in doc["incidents"] if i.get("state") in OPEN_STATES]


def _where(doc: dict, device: str) -> tuple:
    """``(incident, member)`` holding *device*: as its device (member None), as an attached
    member, or ``(None, None)``."""
    for inc in _open(doc):
        if inc.get("device") == device:
            return inc, None
        for m in inc.get("attached") or []:
            if m.get("device") == device:
                return inc, m
    return None, None


def _keys(inc: dict) -> set:
    out = {t.get("key") for t in inc.get("triggers") or []}
    for m in inc.get("attached") or []:
        out |= {t.get("key") for t in m.get("triggers") or []}
    return out


def _push(holder: dict, trigger: dict) -> None:
    holder.setdefault("triggers", []).append(trigger)
    holder["triggers_seen"] = int(holder.get("triggers_seen") or 0) + 1
    if len(holder["triggers"]) > TRIGGERS_KEPT:
        holder["triggers"] = holder["triggers"][-TRIGGERS_KEPT:]


def _new(network: str, device: str, trigger: dict, now: float) -> dict:
    return {"id": "hi-" + uuid.uuid4().hex[:12], "network": network, "device": device,
            "state": "watching",
            "cause": "change" if trigger["kind"] in CAUSE_KINDS else "symptom",
            "opened_at": _iso(now), "opened_epoch": now, "updated_at": _iso(now),
            "triggers": [], "triggers_seen": 0, "reads": [], "attached": [], "related": [],
            "fold": {}, "settled": None}


def _member(device: str, trigger: dict, now: float, why: str) -> dict:
    return {"device": device, "attached_at": _iso(now), "why": why, "triggers": [trigger],
            "triggers_seen": 1, "reads": []}


def _cut(radius_of, device: str) -> tuple:
    """``(devices cut, why)`` for *device*'s blast radius, or ``(None, why)`` when it cannot be
    judged."""
    if radius_of is None:
        return None, "no blast radius was given"
    try:
        got = radius_of(device) or {}
    except Exception as exc:
        return None, f"{device}'s blast radius could not be judged ({type(exc).__name__}: {exc})"
    if got.get("state") != "known":
        return None, got.get("why") or f"{device}'s blast radius is not known"
    return set(got.get("cut") or []), (f"{len(got.get('cut') or [])} device(s) Mercury loses "
                                       f"reach to without {device}, "
                                       f"{got.get('why') or 'from committed intent'}")


def _fold_target(doc: dict, device: str, trigger: dict, radius_of) -> tuple:
    """``(incident, why)``: the open incident a symptom on *device* folds into, or ``(None,
    why)``."""
    related = set(trigger.get("related") or [])
    for inc in _open(doc):
        if inc.get("device") in related:
            return inc, (f"{inc['device']} is the far end of the link this "
                         f"{KIND_WORDS.get(trigger['kind'], trigger['kind'])} names")
    whys = []
    for inc in _open(doc):
        if inc.get("cause") != "change":
            continue
        cut, why = _cut(radius_of, inc["device"])
        if cut is None:
            whys.append(why)
            continue
        if device in cut:
            return inc, (f"{device} is inside {inc['device']}'s blast radius ({why}), and "
                         f"{inc['device']} changed")
        whys.append(f"{device} is not inside {inc['device']}'s blast radius ({why})")
    return None, ("; ".join(whys) if whys else "no open incident's device changed, and none is "
                  "the far end of its link")


def _absorb(doc: dict, inc: dict, radius_of, now: float) -> list:
    """Take into *inc* (its device just changed) every open symptom-only incident its blast
    radius or its links hold. Returns the devices taken."""
    cut, why = _cut(radius_of, inc["device"])
    inc["fold"] = {"state": "judged" if cut is not None else "not_judged", "why": why}
    taken = []
    for other in list(_open(doc)):
        if other is inc or other.get("cause") != "symptom" or other.get("state") != "watching":
            continue
        linked = any(inc["device"] in (t.get("related") or []) for t in other.get("triggers")
                     or [])
        if not linked and not (cut and other["device"] in cut):
            continue
        reason = (f"{inc['device']} is the far end of its link" if linked else
                  f"{other['device']} is inside {inc['device']}'s blast radius ({why}), and "
                  f"{inc['device']} changed")
        m = {"device": other["device"], "attached_at": _iso(now), "why": reason,
             "triggers": list(other.get("triggers") or []),
             "triggers_seen": other.get("triggers_seen") or 0,
             "reads": list(other.get("reads") or []), "from_incident": other["id"]}
        inc.setdefault("attached", []).append(m)
        inc["attached"].extend(other.get("attached") or [])
        other.update(state="closed", closed_at=_iso(now), updated_at=_iso(now),
                     closed_why=f"folded into {inc['id']} ({inc['device']}): {reason}",
                     folded_into=inc["id"])
        taken.append(other["device"])
    return taken


def sight(network: str, device: str, trigger: dict, *, now: float = None,
          radius_of=None) -> dict:
    """Record *trigger* ("check *device* now") in *network*'s incidents: ``{"action",
    "incident", "words"}``, *action* one of ``opened``, ``added``, ``attached``, ``promoted``,
    ``moved`` or ``duplicate`` (a trigger already held, by its ``key``). *trigger* is
    ``{"kind", "key", "epoch", "at", "source", "words", "related"?, ...}``; *radius_of(device)*
    gives a device's blast radius (`blast_radius.radius`'s answer)."""
    now = time.time() if now is None else float(now)
    if trigger.get("kind") not in CAUSE_KINDS + SYMPTOM_KINDS:
        raise Refused(f"a trigger is one of {', '.join(CAUSE_KINDS + SYMPTOM_KINDS)}, not "
                      f"{trigger.get('kind')!r}")
    cause = trigger["kind"] in CAUSE_KINDS

    def change(doc):
        inc, member = _where(doc, device)
        if inc is not None and trigger.get("key") in _keys(inc):
            return {"action": "duplicate", "incident": inc["id"],
                    "words": f"{inc['id']} holds this trigger already"}
        if inc is not None and member is None:
            _push(inc, trigger)
            inc["updated_at"] = _iso(now)
            if cause and inc.get("cause") != "change":
                inc["cause"] = "change"
                _absorb(doc, inc, radius_of, now)
            if cause and inc.get("state") == "ready":
                # Settled on reads before this change: they no longer stand.
                inc.update(state="watching", settled=None,
                           unsettled={"at": _iso(now), "why": trigger.get("words") or ""})
            return {"action": "added", "incident": inc["id"],
                    "words": f"{device}'s incident {inc['id']} takes it"}
        if inc is not None:
            if not cause:
                _push(member, trigger)
                inc["updated_at"] = _iso(now)
                return {"action": "attached", "incident": inc["id"],
                        "words": f"{device} is attached to {inc['id']} ({inc['device']})"}
            if inc.get("cause") != "change" and inc.get("state") == "watching":
                # The member changed; the device it was attached to only showed a symptom.
                old = {"device": inc["device"], "attached_at": _iso(now),
                       "why": f"{device} changed, and this device only showed a symptom",
                       "triggers": inc.get("triggers") or [],
                       "triggers_seen": inc.get("triggers_seen") or 0,
                       "reads": inc.get("reads") or []}
                inc["attached"] = [m for m in inc["attached"] if m is not member] + [old]
                inc.update(device=device, cause="change", reads=member.get("reads") or [],
                           triggers=member.get("triggers") or [],
                           triggers_seen=member.get("triggers_seen") or 0,
                           updated_at=_iso(now))
                _push(inc, trigger)
                _absorb(doc, inc, radius_of, now)
                return {"action": "promoted", "incident": inc["id"],
                        "words": f"{device} changed, so it is {inc['id']}'s device now"}
            inc["attached"] = [m for m in inc["attached"] if m is not member]
            new = _new(network, device, trigger, now)
            new["reads"] = member.get("reads") or []
            new["triggers"] = member.get("triggers") or []
            new["triggers_seen"] = member.get("triggers_seen") or 0
            _push(new, trigger)
            why = (f"{device} and {inc['device']} both changed: a cause spanning devices")
            new["related"].append({"incident": inc["id"], "device": inc["device"], "why": why})
            inc.setdefault("related", []).append({"incident": new["id"], "device": device,
                                                  "why": why})
            doc["incidents"].append(new)
            return {"action": "moved", "incident": new["id"],
                    "words": f"{device} moved from {inc['id']} to its own {new['id']}: {why}"}
        if not cause:
            target, why = _fold_target(doc, device, trigger, radius_of)
            if target is not None:
                target.setdefault("attached", []).append(_member(device, trigger, now, why))
                target["updated_at"] = _iso(now)
                return {"action": "attached", "incident": target["id"],
                        "words": f"{device} is attached to {target['id']} ({target['device']}): "
                                 f"{why}"}
        new = _new(network, device, trigger, now)
        _push(new, trigger)
        if not cause:
            new["fold"] = {"state": "not_folded", "why": why}
        doc["incidents"].append(new)
        if cause:
            _absorb(doc, new, radius_of, now)
        return {"action": "opened", "incident": new["id"],
                "words": f"{device}'s incident {new['id']} opened"}

    return _mutate(network, change)


def _find(doc: dict, incident_id: str) -> dict:
    for inc in doc["incidents"]:
        if inc.get("id") == incident_id:
            return inc
    raise Refused(f"no heal incident {incident_id} is held")


def record_read(network: str, incident_id: str, device: str, got: dict) -> dict:
    """Keep one read the detect pass made of *device* (the incident's device or a member) on
    the incident. *got* is ``{"epoch", "at", "state", "departure", "changed_lines", "error",
    "by"}``: no configuration text, ever."""
    keep = {k: got.get(k) for k in ("epoch", "at", "state", "departure", "changed_lines",
                                     "error", "by")}

    def change(doc):
        inc = _find(doc, incident_id)
        holder = inc if inc.get("device") == device else next(
            (m for m in inc.get("attached") or [] if m.get("device") == device), None)
        if holder is None:
            raise Refused(f"{device} is not in {incident_id}")
        holder.setdefault("reads", []).append(keep)
        holder["reads"] = holder["reads"][-READS_KEPT:]
        inc["updated_at"] = keep.get("at") or inc.get("updated_at")
        return inc

    return _mutate(network, change)


def settle(network: str, incident_id: str, judged: dict, now: float = None) -> dict:
    """The grace period settled *incident_id* (`grace.judge`'s answer, a settled state): it is
    ``ready`` for the decision."""
    from modules.heal.grace import SETTLED_STATES

    now = time.time() if now is None else float(now)
    if judged.get("state") not in SETTLED_STATES:
        raise Refused(f"{judged.get('state')!r} does not settle an incident (only "
                      f"{', '.join(SETTLED_STATES)} do)")

    def change(doc):
        inc = _find(doc, incident_id)
        if inc.get("state") != "watching":
            raise Refused(f"{incident_id} is {inc.get('state')}, not watching")
        inc.update(state="ready", updated_at=_iso(now),
                   settled={"how": judged["state"], "words": judged.get("words") or "",
                            "at": _iso(now), "first": judged.get("first"),
                            "second": judged.get("second"),
                            "operands": judged.get("operands") or {}})
        return inc

    return _mutate(network, change)


def ready(network: str) -> list:
    """**The seam H3 takes:** *network*'s incidents ready for the decision, oldest first, each
    whole (its device, triggers, reads, members, how it settled). A read; it creates nothing.
    An unreadable store raises `filestore.StoreUnreadable`: no incident is never the answer to a
    store that could not be read."""
    from modules.filestore import StoreUnreadable

    got = read(network)
    if got["state"] == "unreadable":
        raise StoreUnreadable(got["error"])
    return [i for i in got["incidents"] if i.get("state") == "ready"]


def claim(network: str, incident_id: str, *, by: str, now: float = None) -> dict:
    """The decision (H3) takes a ready incident: ``claimed`` by *by*, refused when it is not
    ready (another took it, or a change after it settled sent it back to watching)."""
    now = time.time() if now is None else float(now)

    def change(doc):
        inc = _find(doc, incident_id)
        if inc.get("state") != "ready":
            raise Refused(f"{incident_id} is {inc.get('state')}, not ready, so it is not taken")
        inc.update(state="claimed", claimed={"by": by, "at": _iso(now)}, updated_at=_iso(now))
        return inc

    return _mutate(network, change)


def defer(network: str, incident_id: str, until: float, why: str, now: float = None) -> dict:
    """The decision (H3) sends a claimed incident back to watching until *until* (a planned
    window's end and its settle time, the topology hold's end, a person working): no read
    before it, and the grace period restarts at it (`detect.outside_changes`), so the decision
    sees the device as it is after it, never as it was inside it."""
    now = time.time() if now is None else float(now)
    if not (why or "").strip():
        raise Refused("an incident is deferred with why, and none was given")

    def change(doc):
        inc = _find(doc, incident_id)
        if inc.get("state") not in ("claimed", "ready"):
            raise Refused(f"{incident_id} is {inc.get('state')}, so it is not deferred")
        inc.update(state="watching", settled=None, claimed=None, updated_at=_iso(now),
                   defer_until=float(until), deferred={"at": _iso(now), "until": _iso(until),
                                                        "why": why})
        return inc

    return _mutate(network, change)


def close(network: str, incident_id: str, why: str, now: float = None) -> dict:
    now = time.time() if now is None else float(now)
    if not (why or "").strip():
        raise Refused("an incident is closed with why, and none was given")

    def change(doc):
        inc = _find(doc, incident_id)
        if inc.get("state") == "closed":
            return inc
        inc.update(state="closed", closed_at=_iso(now), closed_why=why, updated_at=_iso(now))
        return inc

    return _mutate(network, change)


def close_watching(network: str, why: str, now: float = None) -> list:
    """Close every incident still watching (self-healing turned off for the network, or
    stopped everywhere): nothing new starts. Returns their ids. Ready and claimed incidents
    are left to the decision, which checks the mode first (guard 2)."""
    now = time.time() if now is None else float(now)
    got = read(network)
    if got["state"] != "ok" or not any(i.get("state") == "watching" for i in got["incidents"]):
        return []

    def change(doc):
        out = []
        for inc in doc["incidents"]:
            if inc.get("state") == "watching":
                inc.update(state="closed", closed_at=_iso(now), closed_why=why,
                           updated_at=_iso(now))
                out.append(inc["id"])
        return out

    return _mutate(network, change)
