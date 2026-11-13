"""The hard stops and guards, in section 6's order (board H, part H3; docs/HEAL_TO_INTENT.md
section 6). Each guard answers ``None`` (it does not apply) or ``{"guard", "name", "outcome",
"words", "operands", "until"}``: the first that applies is named in the decision with both
operands it compared. A guard that cannot be read applies: it fails closed, never open.

*outcome* is what the decision does when the guard applies:
- ``off``: self-healing is not on for the network (guards 1, 2);
- ``halted``: the network's policy is halted, or this decision halts it (2, 10, 11, 14);
- ``held`` with *until*: checked again after it (3, 5, 7): the incident goes back to watching,
  and its grace period restarts there;
- ``held`` without *until*: a person resolves it (4, 6, 9);
- ``cant_fix``: nothing is sent, the reason named (8, 12).
Guard 13 (the tier) is the decision's last step (`decide._outcome`): what remains is healed,
proposed or can't be fixed by its kinds' tiers.

The numbers and names are H1's (`policy.GUARDS`), one table.
"""

import logging
import time

log = logging.getLogger(__name__)


def _name(n: int) -> str:
    from modules.heal.policy import GUARDS

    return next(name for num, name, _keys in GUARDS if num == n)


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def hit(n: int, outcome: str, words: str, operands: dict, until: float = None) -> dict:
    return {"guard": n, "name": _name(n), "outcome": outcome, "words": words,
            "operands": operands, "until": until}


def value(mode: dict, key: str):
    """A hard stop's value now, as H1 resolves it (the network's own, its lab default, or the
    schema's)."""
    return (mode.get("guards") or {}).get(key, {}).get("value")


# ── 1, 2: the kill switch and the mode ──────────────────────────────────────────────────────

def g1_kill_switch(mode: dict):
    kill = mode.get("stopped") or {}
    if kill.get("stopped"):
        return hit(1, "off", kill.get("words") or "self-healing is stopped everywhere",
                   {"heal_stopped": True, "state": kill.get("state")})
    return None


def g2_mode(mode: dict, halt: dict):
    """The mode now (`policy.current`: off, unconfirmed, expired and the stage guard already
    judged), and a halt in force: a halted policy is not in force until a person lifts it."""
    if mode.get("mode") == "off":
        return hit(2, "off", mode.get("words") or "self-healing is off",
                   {"heal_mode": mode.get("set"), "state": mode.get("state")})
    if halt.get("unreadable"):
        return hit(2, "halted", f"whether the policy is halted cannot be read "
                                f"({halt['unreadable']}), and a halt that cannot be read holds",
                   {"halt": "unreadable"})
    if halt.get("id"):
        return hit(2, "halted", (f"{mode.get('network')}'s policy is halted since "
                                 f"{halt.get('at')} by guard {halt.get('guard')} "
                                 f"({halt.get('name')}): {halt.get('words')}; a person lifts it"),
                   {"halt": halt.get("id"), "halt_guard": halt.get("guard")})
    return None


# ── 3: planned work ─────────────────────────────────────────────────────────────────────────

def g3_planned(network: str, device: str, now: float, *, explained=None, holder=None,
               window=None):
    """A planned restart window (the device's own, or one predicting it out of reach), the
    device held by another operation, or a no-change window. Checked again after the window's
    end plus `restarts.SETTLE_SECONDS` (PHASE8_PLAN 20.2 item 4)."""
    from modules import change_windows, restarts
    from modules.nsot import device_ops

    try:
        got = (explained or restarts.explained_by)(device, network, now)
    except Exception as exc:
        return hit(3, "held", f"the planned windows cannot be read ({exc}), and planned work "
                              "that cannot be read holds", {"device": device}, now + 60)
    if got:
        until = float(got["end"]) + restarts.SETTLE_SECONDS
        return hit(3, "held", f"{got['words']}; checked again at {_iso(until)}",
                   {"device": device, "window_end": _iso(got["end"]),
                    "settle_seconds": restarts.SETTLE_SECONDS}, until)
    try:
        h = (holder or device_ops.holder)(network, device)
    except Exception as exc:
        return hit(3, "held", f"what holds {device} cannot be read ({exc})",
                   {"device": device}, now + 60)
    if h:
        return hit(3, "held", f"{device} is held by {h.get('operation') or 'an operation'} of "
                              f"{h.get('actor') or 'an unrecorded actor'}: one operation per "
                              "device; checked again in a minute",
                   {"device": device, "operation": h.get("operation")}, now + 60)
    w = (window or change_windows.holding)(now)
    if w:
        start, end = w.get("start", ""), w.get("end", "")
        return hit(3, "held", f"{change_windows.words(w, now)} holds every change now; checked "
                              "again after it", {"window": f"{start}-{end}"}, now + 15 * 60)
    return None


# ── 4: the golden departs from intent (N5) ──────────────────────────────────────────────────

def g4_golden(golden: dict):
    """*golden* is ``{"state": "at_intent"|"departs"|"unknown", "words", "commit"}``: the
    approved state is the device's last golden that matched its intent."""
    if golden.get("state") == "at_intent":
        return None
    return hit(4, "held", (f"heal off for this device: its golden departs from its intent "
                           f"({golden.get('words') or golden.get('state')}), so there is no "
                           "approved state to heal to; a person resolves it first (adopt the "
                           "change into intent, or capture after a revert)"),
               {"golden_commit": golden.get("commit", ""), "intent_match": golden.get("state")})


# ── 5: the topology hold (N3) ───────────────────────────────────────────────────────────────

def g5_topology(held: dict, now: float):
    if not held.get("held"):
        return None
    until = None
    if held.get("until"):
        from modules.heal.hold import _epoch
        until = _epoch(held["until"])
    return hit(5, "held", held["words"],
               {"minutes": held.get("minutes"), "changes": held.get("changes", [])[:3],
                "unreadable": held.get("unreadable", [])},
               until if until else now + 15 * 60)


# ── 6: many devices at once ─────────────────────────────────────────────────────────────────

def g6_many(incidents: list, now: float, grace_s: float, most: int):
    """More than *most* devices of the network departed (their own change, not a symptom)
    within one grace period: a bad rollout, a template or a systemic event; escalate."""
    devices = sorted({i["device"] for i in incidents if i.get("cause") == "change"
                      and now - grace_s <= float(i.get("opened_epoch") or 0) <= now})
    if len(devices) > int(most):
        return hit(6, "held", (f"{len(devices)} devices of the network departed within "
                               f"{int(grace_s)} s ({', '.join(devices[:6])}"
                               f"{'…' if len(devices) > 6 else ''}), more than "
                               f"{int(most)}: a fleet-wide departure is escalated, never healed"),
                   {"devices": len(devices), "heal_max_devices_drifting": int(most),
                    "within_seconds": int(grace_s)})
    return None


# ── 7: a person working ─────────────────────────────────────────────────────────────────────

def g7_person(incident: dict, now: float, changes: int, minutes: int):
    from modules.heal.detect import outside_changes

    window = float(minutes) * 60
    recent = [t for t in outside_changes(dict(incident, defer_until=None))
              if now - window <= t <= now]
    if len(recent) >= int(changes):
        who = next((t.get("person", {}).get("words") for t in reversed(incident["triggers"])
                    if t.get("kind") == "config_change" and t.get("person")), "")
        return hit(7, "held", (f"a person appears to be working on {incident['device']}: "
                               f"{len(recent)} changes from outside Mercury in {int(minutes)} "
                               f"minutes (at least {int(changes)} holds it)"
                               + (f"; {who}" if who else "")),
                   {"changes": len(recent), "heal_person_working_changes": int(changes),
                    "heal_person_working_minutes": int(minutes)},
                   max(recent) + window)
    return None


# ── 8: the grace period ─────────────────────────────────────────────────────────────────────

def g8_grace(incident: dict):
    """The grace period settled the incident (H2's `grace.judge`). Only a departure that
    persisted is healed; a device that cannot be read or checked can't be fixed. At its golden
    is no departure: the decision goes on to say nothing to heal, or a Tier 3 can't-fix."""
    s = incident.get("settled") or {}
    if s.get("how") in ("persisted", "at_golden"):
        return None
    if s.get("how") in ("not_checkable", "unreadable"):
        return hit(8, "cant_fix", f"the device could not be judged: {s.get('words')}",
                   {"settled": s.get("how")})
    return hit(8, "held", "the grace period has not settled it", {"settled": s.get("how")},
               time.time() + 60)


# ── 9, 10, 11: the rates ────────────────────────────────────────────────────────────────────

#: C2814: in dry run the rates count the would-heal decisions, as Auto counts heals, so dry run
#: measures Auto's rates; its words never say a heal that did not run.
DRY_COUNTED = "dry run's would-heal decisions, counted as Auto counts heals"


#: Declared fault drills (the operator's decision, 2026-11-11, `modules/fault_drills.py`): "exempt
#: from guard 11 (same change healed twice in 24 h) and from the per-device rate holds. Nothing
#: else". So guards 9 and 11 do not apply to an incident tagged a drill at its creation (its
#: *drill*, the tag its decision carries), and for a real one they count real heals only:
#: "Drill heals are recorded and counted as drills, never in the real figures". Guard 10
#: counts every heal, a drill's included: it bounds the network's load, and is not exempt.
GUARDS_A_DRILL_PASSES = (9, 11)


def counted(rows: list, outcome: str, since: float) -> list:
    return [d for d in rows if d.get("outcome") == outcome
            and float(d.get("epoch") or 0) >= since]


def g9_device_rate(rows: list, device: str, outcome: str, now: float, most: int, *,
                   drill=None):
    from modules import fault_drills

    if drill:
        return None
    got = [d for d in counted(fault_drills.real_only(rows), outcome, now - 3600)
           if d.get("device") == device]
    if len(got) >= int(most):
        did = ("was healed" if outcome == "heal" else "would have been healed")
        dry = "" if outcome == "heal" else f" ({DRY_COUNTED})"
        return hit(9, "held", (f"{device} {did} {len(got)} time(s) in the last hour{dry}, the "
                               f"most a device is ({int(most)}): flapping beyond the rate "
                               "limit; stop and escalate"),
                   {"heals_last_hour": len(got), "heal_max_per_device_hour": int(most)})
    return None


def g10_network_rate(rows: list, network: str, outcome: str, now: float, most: int):
    # Every heal, a declared fault drill's included (`GUARDS_A_DRILL_PASSES`: 9 and 11 only).
    got = counted(rows, outcome, now - 3600)
    if len(got) >= int(most):
        what = ("heal(s)" if outcome == "heal" else f"would-heal decision(s) ({DRY_COUNTED})")
        return hit(10, "halted", (f"{network} had {len(got)} {what} in the last hour, the most "
                                  f"a network has ({int(most)}): the policy halts until a "
                                  "person lifts it"),
                   {"heals_last_hour": len(got), "heal_max_per_network_hour": int(most)})
    return None


def g11_repeat(rows: list, device: str, departure: str, outcome: str, now: float, hours: int,
               *, drill=None):
    from modules import fault_drills

    if not departure or drill:
        return None
    got = [d for d in counted(fault_drills.real_only(rows), outcome, now - float(hours) * 3600)
           if d.get("device") == device and d.get("departure") == departure]
    if got:
        did = ("was healed" if outcome == "heal" else
               f"would have been healed ({DRY_COUNTED})")
        return hit(11, "halted", (f"the same deviation of {device} (departure {departure}) {did}"
                                  f" at {got[-1].get('at')}, within {int(hours)} hours: "
                                  "something keeps re-applying it, so the policy halts"),
                   {"departure": departure, "previous": got[-1].get("id"),
                    "heal_repeat_halts_hours": int(hours)})
    return None


# ── 12: the program's size ──────────────────────────────────────────────────────────────────

def g12_size(units: list, most_removed: int, most_sections: int):
    removed = [u for u in units if u["op"] == "remove"]
    sections = sorted({u["chain"][0] if u["chain"] else
                       (u["lines"][0] if u.get("stanza") else "the global configuration")
                       for u in units})
    if len(removed) > int(most_removed):
        return hit(12, "cant_fix", (f"the heal would remove {len(removed)} units (a unit is one "
                                    f"feature on one section, N13), more than "
                                    f"{int(most_removed)}"),
                   {"removal_units": len(removed), "heal_max_removed_units": int(most_removed)})
    if len(sections) > int(most_sections):
        return hit(12, "cant_fix", (f"the heal spans {len(sections)} sections, more than "
                                    f"{int(most_sections)}: never a partial heal"),
                   {"sections": len(sections), "heal_max_units": int(most_sections)})
    return None


# ── 14: a rolled-back heal ──────────────────────────────────────────────────────────────────

def g14_rolled_back(rows: list, device: str, last_halt_epoch: float):
    """A heal of the device rolled back after the newest halt was recorded (the halt its
    rollback writes is missing): it halts now. A halt in force is guard 2's."""
    from modules.heal.hold import _epoch

    back = [d for d in rows if d.get("device") == device
            and (d.get("applied") or {}).get("outcome") == "rolled_back"
            and _epoch(d["applied"].get("at")) > float(last_halt_epoch or 0)]
    if back:
        return hit(14, "halted", (f"the heal of {device} ({back[-1]['id']}) was rolled back, "
                                  "and the policy halts until a person lifts it"),
                   {"decision": back[-1]["id"]})
    return None
