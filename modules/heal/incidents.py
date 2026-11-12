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
- ``claimed``: the decision has it (H3, then H4's act and verify); it closes it, or leaves it
  standing;
- ``standing`` (C2813): decided, and its cause still stands: a dry run's would-heal, a can't
  fix, or a hold a person resolves (no until). It stays OPEN, so the rules below still hold
  for it: a symptom arriving later on another device folds into it (its blast radius, its far
  end) within `FOLD_STANDING_S` of its decision, and a later trigger of the same cause joins
  it (`sight`). Its ``standing`` names the
  decision, its outcome and the departure it judged, and ``on``: ``departure`` (the device
  had departed from its golden) or ``symptom`` (it was at its golden, with a symptom: a Tier 3
  can't-fix). What happens next:
  - a drift record of THE SAME departure joins it: no second incident, no second decision;
  - any other cause (a configuration change, a person's revert, a drift record of another
    departure) sends it back to ``watching``, judged again after the grace period as a ready
    incident is (`_rejudge`); read again with the same departure, it stands on its decision
    again (`restand`), never a second decision of the same thing;
  - it closes when the device is read back at its golden or intent: a later decision of
    nothing to heal, a drift run that read the device at its golden after its decision (an
    ``on: departure`` incident, `triggers.after_drift_record`), or, for ``on: symptom``, every
    symptom it named read gone and quiet for the flap window (`detect`'s standing step, and
    the can't-fix notice's diagnosis, C2825); and when self-healing is turned off;
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
OPEN_STATES = ("watching", "ready", "claimed", "standing")
STATES = OPEN_STATES + ("closed",)
#: The decision's outcomes that leave an incident standing (C2813): the cause is still there
#: after them. ``held`` stands only without an until (a person resolves it); with one it is
#: deferred (`defer`). ``heal`` and ``propose`` stay claimed for H4 and H5; every other
#: outcome closes it.
STANDS = ("would_heal", "cant_fix", "held")
#: How long after its decision a standing incident takes in a symptom on ANOTHER device (its
#: blast radius, its far end): 2.5 times the longest measured, H11's W7 (a lost telemetry
#: stream 99 s after its changed neighbour's decision; W2's alert 64 s, W3's IP SLA alert 57
#: and 89 s). Later, the symptom is
#: judged on its own, so a decision that stood for days never swallows an unrelated fault. A
#: trigger on the incident's own device, or a member's, always joins it.
FOLD_STANDING_S = 250.0


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


def incident_href(network: str, incident_id: str, *, device: str) -> str:
    """The incident's page, as Mercury's own path (the ONE place an incident's address is
    built: the operator, 2026-11-12, objective 2: "the can't-fix email ... links to the
    incident"). Until the incident's own page exists, that is its device's page on its
    network, opened on History with the incident's card (``result``: `run_card.named_heal`
    draws it from the step log, a can't-fix decision's as a run's, after any restart), so a
    card that cannot be drawn still leaves the reader on History, where the incident's row
    is. The incident page's slice changes this function alone. ``""`` without a device or an
    id: no link is better than one to the wrong page."""
    from urllib.parse import quote

    if not device or not incident_id:
        return ""
    return (f"/v2/device/{quote(device, safe='')}?list={quote(network or '', safe='')}"
            f"&tab=history&result={quote(incident_id, safe='')}")


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


def _drill(network: str, device: str, now: float, tag="look") -> dict:
    """The fault-drill tag, at creation and in the same write (the operator's decision,
    2026-11-11; `fault_drills.tag_for`): ``{"fault_drill": {...}}`` when *device* at *now* is
    inside a declared, unexpired drill, else ``{}``. *tag* given (a member moved to an
    incident of its own, or folded into another) is the record's own tag, carried: never
    looked up again."""
    from modules import fault_drills

    if tag == "look":
        tag = fault_drills.tag_for(network, device, now)
    return {fault_drills.FIELD: tag} if tag else {}


def _new(network: str, device: str, trigger: dict, now: float, tag="look") -> dict:
    return {"id": "hi-" + uuid.uuid4().hex[:12], "network": network, "device": device,
            "state": "watching",
            "cause": "change" if trigger["kind"] in CAUSE_KINDS else "symptom",
            "opened_at": _iso(now), "opened_epoch": now, "updated_at": _iso(now),
            "triggers": [], "triggers_seen": 0, "reads": [], "attached": [], "related": [],
            "fold": {}, "settled": None, **_drill(network, device, now, tag)}


def _member(network: str, device: str, trigger: dict, now: float, why: str) -> dict:
    return {"device": device, "attached_at": _iso(now), "why": why, "triggers": [trigger],
            "triggers_seen": 1, "reads": [], **_drill(network, device, now)}


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


def _too_late(inc: dict, now: float) -> str:
    """Why a symptom on ANOTHER device at *now* does not fold into *inc*, a standing incident
    decided more than `FOLD_STANDING_S` ago, or ``""``: a symptom that late is judged on its
    own, never swallowed by a decision made before it (C2813)."""
    s = inc.get("standing") or {}
    if inc.get("state") != "standing" or now - float(s.get("epoch") or now) <= FOLD_STANDING_S:
        return ""
    return (f"{inc['device']}'s {inc['id']} stood on its decision since {s.get('at')}, more than "
            f"{int(FOLD_STANDING_S)} s before this symptom, so it is judged on its own")


def _fold_target(doc: dict, device: str, trigger: dict, radius_of, now: float = None) -> tuple:
    """``(incident, why)``: the open incident a symptom on *device* folds into, or ``(None,
    why)``. A standing incident takes a symptom on another device only within
    `FOLD_STANDING_S` of its decision (`_too_late`)."""
    now = time.time() if now is None else float(now)
    related = set(trigger.get("related") or [])
    whys = []
    for inc in _open(doc):
        if inc.get("device") in related:
            late = _too_late(inc, now)
            if late:
                whys.append(late)
                continue
            return inc, (f"{inc['device']} is the far end of the link this "
                         f"{KIND_WORDS.get(trigger['kind'], trigger['kind'])} names")
    for inc in _open(doc):
        if inc.get("cause") != "change":
            continue
        late = _too_late(inc, now)
        if late:
            whys.append(late)
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
        # A member keeps its own fault-drill tag: the one its incident took at creation.
        from modules import fault_drills
        tag = fault_drills.tag_of(other)
        m = {"device": other["device"], "attached_at": _iso(now), "why": reason,
             "triggers": list(other.get("triggers") or []),
             "triggers_seen": other.get("triggers_seen") or 0,
             "reads": list(other.get("reads") or []), "from_incident": other["id"],
             **({fault_drills.FIELD: tag} if tag else {})}
        inc.setdefault("attached", []).append(m)
        inc["attached"].extend(other.get("attached") or [])
        other.update(state="closed", closed_at=_iso(now), updated_at=_iso(now),
                     closed_why=f"folded into {inc['id']} ({inc['device']}): {reason}",
                     folded_into=inc["id"])
        taken.append(other["device"])
    return taken


def same_departure(standing: dict, trigger: dict) -> bool:
    """Whether *trigger* is a drift record of THE departure a standing incident's decision
    judged (C2813): both fingerprints present and equal (`drift_check.departure`, the masked
    differing lines). A departure the decision did not judge, or a read with none, is not the
    same: it is judged again."""
    if trigger.get("kind") != "drift":
        return False
    dep = (trigger.get("read") or {}).get("departure") or trigger.get("departure") or ""
    return bool(dep) and dep == (standing or {}).get("departure")


def _rejudge(inc: dict, trigger: dict, now: float) -> None:
    """A standing incident's device changed again (a configuration change, a revert, or a
    drift record of another departure): back to watching, judged again after the grace period
    as a ready incident is. ``stood`` keeps what it stood on (a read of the same departure
    stands on it again, `restand`); for a departure, the symptoms it held before this change
    were that departure's (``judged_from``: the decision judges only the symptoms after it,
    so a revert that puts the device back is nothing to heal, never a can't-fix on a symptom
    the reverted change caused). A symptom-only incident's symptoms are still its cause."""
    s = inc.get("standing") or {}
    inc.update(state="watching", settled=None, claimed=None, stood=s, standing=None,
               updated_at=_iso(now),
               unsettled={"at": _iso(now), "why": trigger.get("words") or "",
                          "from": f"standing on {s.get('decision') or '?'}"})
    if s.get("on") == "departure":
        inc["judged_from"] = float(trigger.get("epoch") or now)


def sight(network: str, device: str, trigger: dict, *, now: float = None,
          radius_of=None) -> dict:
    """Record *trigger* ("check *device* now") in *network*'s incidents: ``{"action",
    "incident", "words"}``, *action* one of ``opened``, ``added``, ``attached``, ``promoted``,
    ``moved`` or ``duplicate`` (a trigger already held, by its ``key``). *trigger* is
    ``{"kind", "key", "epoch", "at", "source", "words", "related"?, ...}``; *radius_of(device)*
    gives a device's blast radius (`blast_radius.radius`'s answer). On a STANDING incident
    (C2813) a symptom is ``added``; a drift record of the departure its decision judged is
    ``joined`` (no second decision); any other cause is ``rejudged``: back to watching."""
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
            if inc.get("state") == "standing":
                s = inc.get("standing") or {}
                if not cause:
                    return {"action": "added", "incident": inc["id"],
                            "words": (f"{device}'s incident {inc['id']} takes it: it stands on "
                                      f"its decision {s.get('decision') or '?'}")}
                if same_departure(s, trigger):
                    return {"action": "joined", "incident": inc["id"],
                            "words": (f"{device}'s incident {inc['id']} takes it: the same "
                                      f"departure its decision {s.get('decision') or '?'} judged "
                                      f"({s['departure']}), so no second decision")}
                _rejudge(inc, trigger, now)
                return {"action": "rejudged", "incident": inc["id"],
                        "words": (f"{device} changed again, so its incident {inc['id']} is judged "
                                  f"again after the grace period (it stood on "
                                  f"{s.get('decision') or '?'})")}
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
                # Each keeps the fault-drill tag its device took at creation: the incident
                # now the member's device carries the member's, the old device its own.
                from modules import fault_drills
                was, own = fault_drills.tag_of(inc), fault_drills.tag_of(member)
                old = {"device": inc["device"], "attached_at": _iso(now),
                       "why": f"{device} changed, and this device only showed a symptom",
                       "triggers": inc.get("triggers") or [],
                       "triggers_seen": inc.get("triggers_seen") or 0,
                       "reads": inc.get("reads") or [], **_drill(network, "", now, was)}
                inc["attached"] = [m for m in inc["attached"] if m is not member] + [old]
                inc.pop(fault_drills.FIELD, None)
                inc.update(device=device, cause="change", reads=member.get("reads") or [],
                           triggers=member.get("triggers") or [],
                           triggers_seen=member.get("triggers_seen") or 0,
                           updated_at=_iso(now), **_drill(network, "", now, own))
                _push(inc, trigger)
                _absorb(doc, inc, radius_of, now)
                return {"action": "promoted", "incident": inc["id"],
                        "words": f"{device} changed, so it is {inc['id']}'s device now"}
            inc["attached"] = [m for m in inc["attached"] if m is not member]
            # The member's own tag, from when it was attached: never looked up again.
            from modules import fault_drills
            new = _new(network, device, trigger, now, tag=fault_drills.tag_of(member))
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
            target, why = _fold_target(doc, device, trigger, radius_of, now)
            if target is not None:
                target.setdefault("attached", []).append(_member(network, device, trigger, now,
                                                                 why))
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


def defer(network: str, incident_id: str, until: float, why: str, now: float = None,
          quiet: bool = False) -> dict:
    """The decision (H3) sends a claimed incident back to watching until *until* (a planned
    window's end and its settle time, the topology hold's end, a person working): no read
    before it, and the grace period restarts at it (`detect.outside_changes`), so the decision
    sees the device as it is after it, never as it was inside it. *quiet* (C2825): deferred
    because its symptom read gone inside the flap window, which is done once an incident
    (``quiet_deferred``), so a link still flapping is told about after one window, never
    deferred for ever."""
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
        if quiet:
            inc["quiet_deferred"] = True
        return inc

    return _mutate(network, change)


def stand(network: str, incident_id: str, decision: dict = None, *, settled: dict = None,
          now: float = None) -> dict:
    """C2813: a claimed incident whose decision leaves its cause standing (`STANDS`) stays
    open, ``standing`` on *decision* (``{"id", "outcome", "words", "departure"}``). Its
    departure is the decision's, else the one its grace period settled on; ``on`` is
    ``symptom`` when the grace period found the device at its golden, else ``departure``.
    *decision* None puts back a standing incident taken by `take_standing` (a decision that
    could not be recorded)."""
    now = time.time() if now is None else float(now)

    def change(doc):
        inc = _find(doc, incident_id)
        if inc.get("state") != "claimed":
            raise Refused(f"{incident_id} is {inc.get('state')}, not claimed, so it does not "
                          "stand")
        if decision is None:
            if not inc.get("standing"):
                raise Refused(f"{incident_id} stood on nothing, so it is not put back")
            inc.update(state="standing", claimed=None, updated_at=_iso(now))
            return inc
        how = ((settled if settled is not None else inc.get("settled")) or {})
        dep = (decision.get("departure") or (how.get("operands") or {}).get("departure")
               or "")
        inc.update(state="standing", claimed=None, updated_at=_iso(now), stood=None,
                   standing={"decision": decision.get("id") or "",
                             "outcome": decision.get("outcome") or "",
                             "words": (decision.get("words") or "")[:300],
                             "at": _iso(now), "epoch": now, "departure": dep,
                             "guard": (decision.get("guard") or {}).get("guard"),
                             "on": "symptom" if how.get("how") == "at_golden" else "departure"})
        return inc

    return _mutate(network, change)


def restand(network: str, incident_id: str, judged: dict, now: float = None) -> dict:
    """C2813: a standing incident sent back to watching (`_rejudge`) whose grace period settled
    on THE departure its decision judged stands on that decision again: the device changed
    nothing that decision did not already judge, so there is no second decision of it."""
    now = time.time() if now is None else float(now)

    def change(doc):
        inc = _find(doc, incident_id)
        s = inc.get("stood") or {}
        dep = ((judged or {}).get("operands") or {}).get("departure") or ""
        if inc.get("state") != "watching" or not s.get("departure") or dep != s["departure"]:
            raise Refused(f"{incident_id} is {inc.get('state')}, and settled on "
                          f"{dep or 'no departure'} against {s.get('departure') or 'none'}, so "
                          "it does not stand again")
        inc.update(state="standing", stood=None, updated_at=_iso(now),
                   standing=dict(s, reread={"at": _iso(now),
                                            "words": (judged or {}).get("words") or ""}))
        return inc

    return _mutate(network, change)


def take_standing(network: str, incident_id: str, *, by: str, now: float = None) -> dict:
    """A standing incident taken to be closed by what read its device back (`decide.
    end_standing`): ``claimed`` by *by*, refused when it is not standing (another took it, or a
    change sent it back to watching)."""
    now = time.time() if now is None else float(now)

    def change(doc):
        inc = _find(doc, incident_id)
        if inc.get("state") != "standing":
            raise Refused(f"{incident_id} is {inc.get('state')}, not standing, so it is not "
                          "taken")
        inc.update(state="claimed", claimed={"by": by, "at": _iso(now), "from": "standing"},
                   updated_at=_iso(now))
        return inc

    return _mutate(network, change)


def drill_of(network: str, incident_id: str, device: str = ""):
    """The fault-drill tag incident *incident_id* took at its creation (`fault_drills.tag_of`),
    or None: for the guards' callers that hold an incident's id, not its record (a bounce, a
    session clear). *device* an attached member of it: the member's own tag. An incident not
    found, or a store that cannot be read, is real: every guard applies to it."""
    from modules import fault_drills

    got = read(network)
    inc = next((i for i in got["incidents"] if i.get("id") == incident_id), None)
    if not inc:
        return None
    member = next((m for m in inc.get("attached") or [] if device and m.get("device") == device
                   and inc.get("device") != device), None)
    return fault_drills.tag_of(member if member is not None else inc)


def standing_of(network: str, device: str) -> dict:
    """*device*'s standing incident in *network*, as its device (a read), or ``{}``."""
    got = read(network)
    return next((i for i in got["incidents"] if i.get("state") == "standing"
                 and i.get("device") == device), {})


def ends_at_golden(standing: dict) -> bool:
    """Whether a read of the device AT ITS GOLDEN ends what *standing* stands on (C2813): a
    decision that judged a departure from the golden (a would-heal, a can't-fix, a hold of many
    devices or of the rate), never one at its golden with a symptom (the symptom is its cause,
    `detect`'s standing step reads it) and never guard 4's (its cause is a golden that departs
    from intent, which a device at that golden does not end)."""
    s = standing or {}
    return s.get("on") == "departure" and bool(s.get("departure")) and s.get("guard") != 4


#: How many symptoms a drift's words name; the rest are counted.
DRIFT_SYMPTOMS_NAMED = 3


def drift_cases(network: str) -> dict:
    """C2824 (the operator, 2026-11-09): what self-healing holds about each device that CHANGED,
    for the drift row and the drift card to choose their actions by. A read: ``{"state",
    "error", "devices": {device: {"case", "who", "symptoms"}}}``, *state* the store's (``ok``,
    ``absent``, ``unreadable``). A device is here when it is the cause (a configuration change
    from outside Mercury, or the drift record) of an OPEN incident, standing ones included
    (C2813: a would-heal, a can't-fix or a hold leaves it open while its cause stands):
    - ``broke``: the incident also holds a symptom (an alert, an adjacency down, a logged drop,
      a duplicate router-id), on the device or on a device attached to it: a change from outside
      Mercury and something broke at the same time;
    - ``quiet``: it holds none.
    *who* says whose change it was in words: the configuration-change line's attribution (never
    Mercury's: `triggers.from_logs_tail` sights no change of Mercury's), the line's time and who
    the line names; or, with no such line, that Mercury holds no record of making it, so it is
    treated as from outside (the attribution rule: an unknown change is an outside one).
    *symptoms* names each symptom's device and kind."""
    got = read(network)
    out = {"state": got["state"], "error": got["error"], "devices": {}}
    for inc in got["incidents"]:
        if inc.get("state") not in OPEN_STATES:
            continue
        holders = [inc] + list(inc.get("attached") or [])
        seen, symptoms = set(), []
        for h in holders:
            for t in h.get("triggers") or []:
                if t.get("kind") in SYMPTOM_KINDS:
                    words = f"{h.get('device') or '?'}: {KIND_WORDS[t['kind']]}"
                    if words not in seen:
                        seen.add(words)
                        symptoms.append(words)
        for h in holders:
            changes = [t for t in h.get("triggers") or [] if t.get("kind") in CAUSE_KINDS]
            if not h.get("device") or not changes:
                continue
            lines = [t for t in changes if t["kind"] == "config_change"]
            out["devices"][h["device"]] = {"case": "broke" if symptoms else "quiet",
                                           "who": _change_words(lines[-1] if lines else None),
                                           "symptoms": symptoms}
    return out


def _change_words(trigger) -> str:
    """Whose change a configuration-change trigger records, in words (C2824); with none, that
    Mercury holds no record of making it."""
    if not trigger:
        return ("changed with no record of Mercury making it (no configuration-change line from "
                "it was received), so it is treated as from outside Mercury")
    by = (trigger.get("attribution") or {}).get("by")
    whose = ("from outside Mercury" if by != "unknown" else
             "by a change not known to be Mercury's (a record it is judged by could not be "
             "read), so treated as from outside Mercury")
    person = (trigger.get("person") or {}).get("words") or "the line names nobody"
    return f"changed {whose} at {trigger.get('at') or 'an unrecorded time'} ({person})"


def symptoms_words(symptoms: list) -> str:
    """The symptoms a drift's words name: the first `DRIFT_SYMPTOMS_NAMED`, the rest counted."""
    named = list(symptoms[:DRIFT_SYMPTOMS_NAMED])
    if len(symptoms) > DRIFT_SYMPTOMS_NAMED:
        named.append(f"{len(symptoms) - DRIFT_SYMPTOMS_NAMED} more")
    return "; ".join(named)


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
    """Close every incident still watching, and every one standing on its decision (C2813),
    when self-healing is turned off for the network or stopped everywhere: nothing new starts,
    and nothing later folds into an incident decided before. Returns their ids. Ready and
    claimed incidents are left to the decision, which checks the mode first (guard 2)."""
    now = time.time() if now is None else float(now)
    shut = ("watching", "standing")
    got = read(network)
    if got["state"] != "ok" or not any(i.get("state") in shut for i in got["incidents"]):
        return []

    def change(doc):
        out = []
        for inc in doc["incidents"]:
            if inc.get("state") in shut:
                inc.update(state="closed", closed_at=_iso(now), closed_why=why,
                           updated_at=_iso(now))
                out.append(inc["id"])
        return out

    return _mutate(network, change)
