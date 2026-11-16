"""Self-healing's two findings, in place of its time-based limits (the operator, 2026-11-16:
"Remove all time-based holds from self-healing ... Replace the limits with: (a) a recurrence
finding ... (b) a fight finding"). Each is read from the stores (the incidents, open and
closed, and the decisions) and reads no device; neither stops a fix, but the fight stops one
when the network's ``heal_fight_stop`` is on.

- **Recurrence** (`recurrences`): the same problem (device, object, condition and cause, as
  `problem.classify` names them) opened ``heal_recurrence_count`` times or more within
  ``heal_recurrence_hours``: Needs attention's ``heal``/``recurrence`` row.
- **Fight** (`fights`): the same fix (the same operation on the same device and object)
  verified, then the same problem back within ``heal_fight_minutes``, ``heal_fight_count``
  times or more within ``heal_recurrence_hours``: Needs attention's ``heal``/``fight`` row and
  one ``heal_fight`` notice per fight (`notify_fights`).

An incident tagged a declared fault drill or drill exercise (`fault_drills.tag_of`, taken at
its creation) counts toward neither (`real`, C3842): its fault was injected on purpose.
"""

import calendar
import json
import logging
import os
import time

log = logging.getLogger(__name__)

#: The notice's event (`notify.message.EVENTS`), sent to the team told about the network's
#: can't-fix (`heal_notify.teams_for`): a fight is a problem Mercury cannot end by itself.
EVENT = "heal_fight"
TOLD_AS = "cant_fix"
FILE = "fight_notices.json"


def _epoch(iso) -> float:
    try:
        return float(calendar.timegm(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S")))
    except (TypeError, ValueError):
        return 0.0


def _hhmm(epoch: float) -> str:
    return time.strftime("%H:%M", time.gmtime(float(epoch)))


def started(inc: dict) -> float:
    """When *inc* began: its first trigger's time, else when it opened."""
    got = [float(t.get("epoch") or 0) for t in inc.get("triggers") or []
           if isinstance(t, dict) and t.get("epoch")]
    return min(got) if got else _epoch(inc.get("opened_at"))


def problem_key(inc: dict) -> tuple:
    """``(device, object, condition, cause)`` of *inc* (`problem.classify` on its record), or
    ``()`` when nothing it holds names a condition."""
    from modules import problem

    p = problem.classify({"incident": inc, "entry": {}, "decisions": []})
    return (p.device, p.object, p.condition, p.cause) if p.condition else ()


def real(incidents: list) -> list:
    """*incidents* less those tagged a declared fault drill or drill exercise at their creation
    (`fault_drills.tag_of`, C3842): a fault injected on purpose counts toward no recurrence or
    fight, as the guards' drill exemption already counts its heals apart
    (`guards.GUARDS_A_DRILL_PASSES`)."""
    from modules import fault_drills

    return [i for i in incidents or [] if isinstance(i, dict) and not fault_drills.tag_of(i)]


def recurrences(incidents: list, now: float, count: int, hours: float,
                after: float = None) -> list:
    """Each problem opened *count* times or more since *hours* ago: ``{"key", "incidents",
    "since"}``, its incidents oldest first. A drill's or an exercise's incident is not counted
    (`real`). *after* (a person's acknowledgement of the finding, the operator, 2026-11-16:
    "count from then") starts the count there when it is later than the window's start."""
    since = max(now - float(hours) * 3600, float(after or 0))
    by = {}
    for inc in real(incidents):
        at = started(inc)
        key = problem_key(inc) if at >= since else ()
        if key:
            by.setdefault(key, []).append((at, inc))
    return [{"key": k, "incidents": [i for _a, i in sorted(v, key=lambda p: p[0])],
             "since": min(a for a, _i in v)}
            for k, v in sorted(by.items()) if len(v) >= int(count)]


def _fixes(incidents: list, decisions: list) -> list:
    """Each verified fix: ``(at, device, operation, incident)``: a heal applied ``healed``,
    and an incident closed on its fix's own device check (``fixed``, `detect._fixed`)."""
    by_id = {i.get("id"): i for i in incidents or []}
    out = []
    for d in decisions or []:
        a = d.get("applied") or {}
        inc = by_id.get(d.get("incident"))
        if a.get("outcome") == "healed" and inc:
            out.append((_epoch(a.get("at")), d.get("device") or "", d.get("kind") or "heal",
                        inc))
    from modules.heal.act import CONFIRM_MARK

    for inc in incidents or []:
        f = inc.get("fixed") or {}
        # A confirmation's proof (`act.CONFIRM_MARK`: Mercury read it already fixed) is no
        # fix of its own: it makes no fight or recurrence finding (the review, finding 10).
        if f.get("epoch") and f.get("by") != CONFIRM_MARK:
            out.append((float(f["epoch"]), f.get("device") or inc.get("device") or "",
                        f.get("operation") or "fix", inc))
    return out


def later_fix(decision: dict, incidents: list, fixes: list = None,
              decisions: list = None) -> tuple:
    """The first verified fix of *decision*'s problem made after it, ``(at, device, operation,
    incident)``, or ``()``: a fix of its own incident (a later decision of it applied
    ``healed``, or the incident closed on its fix's own device check), or of a later incident
    of the same problem (`problem_key`). The operator, 2026-11-16: a dry-run record whose
    problem was later fixed is closed by that fix, never asked "Was that right?" for a week.
    *fixes*: `verified_fixes`'s, computed once by a caller judging many records."""
    fixes = verified_fixes(incidents, decisions or []) if fixes is None else fixes
    at, own = float(decision.get("epoch") or 0), decision.get("incident")
    inc = next((i for i in incidents or [] if i.get("id") == own), None) if own else None
    key = problem_key(inc) if inc else ()
    for fix in sorted(fixes, key=lambda f: f[0]):
        if fix[0] <= at:
            continue
        if (own and fix[3].get("id") == own) or (key and problem_key(fix[3]) == key):
            return fix
    return ()


def verified_fixes(incidents: list, decisions: list) -> list:
    """Each verified fix, ``(at, device, operation, incident)`` (`_fixes`): for `later_fix`."""
    return _fixes(incidents, decisions)


def fights(incidents: list, decisions: list, now: float, count: int, minutes: float,
           hours: float, after: float = None) -> list:
    """Each fix verified and then undone *count* times or more since *hours* ago (the same
    problem back within *minutes* of it): ``{"device", "object", "operation", "what",
    "times", "fixes", "back"}``, *back* the incidents it came back in, oldest first. *after*
    (a person's acknowledgement of the fight) starts the count there, as `recurrences`'."""
    since = max(now - float(hours) * 3600, float(after or 0))
    within = float(minutes) * 60
    # C3842: a drill's or an exercise's incident is neither a fix nor a coming back (`real`).
    incidents = real(incidents)
    keyed = [(started(i), problem_key(i), i) for i in incidents]
    by = {}
    for at, device, op, inc in _fixes(incidents, decisions):
        key = problem_key(inc)
        if at < since or not key:
            continue
        back = next((i for s, k, i in sorted(keyed, key=lambda p: p[0])
                     if k == key and i.get("id") != inc.get("id") and at < s <= at + within),
                    None)
        if back:
            by.setdefault((device, key[1], op), []).append((at, inc, back, key))
    out = []
    for (device, obj, op), got in sorted(by.items()):
        if len(got) >= int(count):
            got.sort(key=lambda p: p[0])
            out.append({"device": device, "object": obj, "operation": op,
                        "what": f"{obj or key_words(got[-1][3])}", "times": len(got),
                        "fixes": [g[1] for g in got], "back": [g[2] for g in got],
                        "first": got[0][0]})
    return out


def key_words(key: tuple) -> str:
    """A problem key in a few words: its object, else its condition."""
    return (key[1] or key[2].replace("_", " ")) if key else "a problem"


def settings(mode: dict) -> dict:
    """The network's findings settings from its policy (`policy.current`)."""
    from modules.heal.guards import value
    from modules.settings_schema import DEFAULTS

    return {k: value(mode, k) if value(mode, k) is not None else DEFAULTS.get(k)
            for k in ("heal_recurrence_count", "heal_recurrence_hours", "heal_fight_count",
                      "heal_fight_minutes", "heal_fight_stop")}


def fight_on(network: str, device: str, obj: str, *, mode: dict, now: float) -> dict:
    """The fight on *device*'s *obj* now, or ``{}``: for the decision's stop
    (``heal_fight_stop``). Reads the stores; ``{}`` when they cannot be read (said)."""
    from modules.heal import decisions, incidents

    s = settings(mode)
    try:
        incs = incidents.read(network).get("incidents") or []
        rows = decisions.decisions(network)
    except Exception as exc:                          # noqa: BLE001 (no stop on an unread store)
        log.error("heal: %s's fights could not be read: %s", network, exc)
        return {}
    for f in fights(incs, rows, now, s["heal_fight_count"], s["heal_fight_minutes"],
                    s["heal_recurrence_hours"]):
        if f["device"] == device and (not obj or f["object"] == obj):
            return f
    return {}


def _path(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), "heal", FILE)


def notify_fights(network: str, now: float = None, *, deliver=None) -> list:
    """One ``heal_fight`` notice per fight (keyed by its device, object, operation and first
    fix), to the team told about *network*'s can't-fix; a fight that ended is forgotten. Returns
    the keys sent. Never raises."""
    from modules import filestore, heal_notify
    from modules.heal import decisions, incidents, policy

    now = time.time() if now is None else float(now)
    try:
        mode = policy.current(network, now)
        if mode.get("mode") == "off":
            return []
        s = settings(mode)
        got = fights(incidents.read(network).get("incidents") or [],
                     decisions.decisions(network), now, s["heal_fight_count"],
                     s["heal_fight_minutes"], s["heal_recurrence_hours"])
        live = {f"{f['device']}|{f['object']}|{f['operation']}|{int(f['first'])}": f
                for f in got}
        path = _path(network)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sent = []
        with filestore.PathLock(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    told = json.load(fh).get("told") or {}
            except (OSError, ValueError):
                told = {}
            told = {k: v for k, v in told.items() if k in live}
            for key, f in live.items():
                if key in told:
                    continue
                teams = heal_notify.teams_for(network, TOLD_AS)
                event = notice(network, f, stop=bool(s["heal_fight_stop"]))
                if deliver is None:
                    from modules.notify import delivery
                    result = delivery.deliver_event(event, teams) if teams else {"sent": 0}
                else:
                    result = deliver(event, teams)
                told[key] = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                             "sent": result.get("sent", 0)}
                sent.append(key)
            filestore.write_atomic(path, json.dumps({"told": told}, indent=1, sort_keys=True))
        return sent
    except Exception as exc:                          # noqa: BLE001 (never fails the pass)
        log.error("heal: %s's fight notices could not be judged or sent: %s: %s", network,
                  type(exc).__name__, exc)
        return []


def headline(f: dict) -> str:
    """The fight in the operator's words (2026-11-16)."""
    return (f"Mercury keeps fixing {f['what']} on {f['device']} and something keeps undoing "
            "it")


def notice(network: str, f: dict, *, stop: bool) -> dict:
    """The ``heal_fight`` event for *f* (`notify.message.FIELDS` only)."""
    from modules.heal.incidents import incident_href

    newest = f["back"][-1]
    return {"incident": str(newest.get("id") or "")[:80], "event": EVENT, "network": network,
            "device": f["device"], "title": headline(f)[:120],
            "happened": (f"{f['operation']} fixed {f['what']} on {f['device']} and it came "
                         f"back {f['times']} times since {_hhmm(f['first'])} UTC"),
            "outcome": ("self-healing stops fixing it (heal_fight_stop is on)" if stop else
                        "self-healing keeps fixing it"),
            "todo": f"find what keeps changing {f['what']} on {f['device']}",
            "link": incident_href(network, str(newest.get("id") or ""), device=f["device"])}
