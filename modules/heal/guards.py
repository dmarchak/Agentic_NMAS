"""The hard stops and guards, in section 6's order (board H, part H3; docs/HEAL_TO_INTENT.md
section 6). Each guard answers ``None`` (it does not apply) or ``{"guard", "name", "outcome",
"words", "operands", "until"}``: the first that applies is named in the decision with both
operands it compared. A guard that cannot be read applies: it fails closed, never open.

*outcome* is what the decision does when the guard applies:
- ``off``: self-healing is not on for the network (guards 1, 2);
- ``held`` with *until*: checked again after it (3, planned work a person declared, alone);
- ``held`` without *until*: an observe-only device or a host (4);
- ``cant_fix``: nothing is sent, the reason named (8).
**Round 2 of the speed pass** (the operator, 2026-11-17: "remove EVERY hold/gate from the
heal-path audit marked 'remove'"): nothing halts a network (guard 2's halt, 11, 14); guards 5
and 10's rates are removed; 7, 9, 11 (the repeat and the fight stop), 12 and 14 are kept doing
nothing for their callers. The decision store unread is a wait (`decide._decide_one`).
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
    judged). Round 2 of the speed pass (the operator, 2026-11-17): a halt holds nothing, so
    *halt* is kept for the callers and read no more; Off and Stop everywhere are the stops."""
    del halt
    if mode.get("mode") == "off":
        return hit(2, "off", mode.get("words") or "self-healing is off",
                   {"heal_mode": mode.get("set"), "state": mode.get("state")})
    return None


# ── 3: planned work ─────────────────────────────────────────────────────────────────────────

def g3_planned(network: str, device: str, now: float, *, explained=None, holder=None,
               window=None):
    """A planned restart window a person declared (the device's own, or one predicting it out
    of reach: `restarts.explained_by_person`, through ``POST /restarts/planned`` or the
    Reload's own window; never one a deploy or a heal declared itself, the operator,
    2026-11-17), the device held by another operation, or a no-change window. Checked again
    after the window's end plus `restarts.SETTLE_SECONDS` (PHASE8_PLAN 20.2 item 4)."""
    from modules import change_windows, restarts
    from modules.nsot import device_ops

    try:
        got = (explained or restarts.explained_by_person)(device, network, now)
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


# ── 4: heal off for this device (`decide._g4`); a departing golden holds nothing (C3909) ───

#: How many of the departing lines guard 4 records in its operands (the rest counted): the
#: lines its Needs attention row draws, each with its way out (C3581).
G4_LINES = 10


def g4_golden(golden: dict):
    """Retired as a hold (C3909, the operator, 2026-11-17: "remove the hold, but don't restore
    a golden that departs from intent"): the decision no longer asks it (`decide._g4` holds
    only an observe-only device or a host), and a departing golden is a can't-fix of
    Mercury's own; kept for the tests that still call it. *golden* is ``{"state":
    "at_intent"|"departs"|"unknown", "words", "commit", "lines", "adds", "removes"}``
    (`decide.Sources.golden`); its operands carry the departing lines as `intent_match` gave
    them (masked), the first `G4_LINES`, and how many more there are."""
    if golden.get("state") == "at_intent":
        return None
    lines = [str(x) for x in golden.get("lines") or []]
    total = max(len(lines), int(golden.get("adds") or 0) + int(golden.get("removes") or 0))
    from modules.nsot.intent_match import state_said
    return hit(4, "held", (f"heal off for this device: its golden differs from its intent "
                           f"({state_said(golden)}), so there is no "
                           "approved state to heal to; a person resolves it first (adopt the "
                           "change into intent, or capture after a revert)"),
               {"golden_commit": golden.get("commit", ""), "intent_match": golden.get("state"),
                "lines": lines[:G4_LINES], "lines_more": max(0, total - len(lines[:G4_LINES]))})


# ── 6: many devices at once ─────────────────────────────────────────────────────────────────

def g6_many(incidents: list, now: float, grace_s: float, most: int, *, at: float = None):
    """More than *most* devices of the network departed (their own change, not a symptom)
    within one grace period of this incident's own departure, either side, itself included
    (*at*, its opening; the operator, 2026-11-16, C3816): a bad rollout, a template or a
    systemic event; escalate. Anchored on the incident, not on the decision's instant: a
    change is decided only after its own grace, so a window before *now* missed the devices
    that departed before it, and the last devices of a fleet-wide departure were never held.
    *at* None anchors on *now* (a caller with no incident)."""
    anchor = float(now if at is None else at)
    devices = sorted({i["device"] for i in incidents if i.get("cause") == "change"
                      and anchor - grace_s <= float(i.get("opened_epoch") or 0)
                      <= min(anchor + grace_s, now)})
    if len(devices) > int(most):
        return hit(6, "held", (f"{len(devices)} devices of the network departed within "
                               f"{int(grace_s)} s of each other ({', '.join(devices[:6])}"
                               f"{'…' if len(devices) > 6 else ''}), more than "
                               f"{int(most)}: a fleet-wide departure is escalated, never healed"),
                   {"devices": len(devices), "heal_max_devices_drifting": int(most),
                    "within_seconds": int(grace_s)})
    return None


# ── 7: a person working ─────────────────────────────────────────────────────────────────────

def g7_person(incident: dict, now: float, changes: int, minutes: int):
    """Retired (C3879; the operator, 2026-11-17): holds nothing. Kept, doing nothing, because
    a test still calls it (`scripts/check_removed_definitions.py`)."""
    del incident, now, changes, minutes
    return None


# ── 8: the grace period ─────────────────────────────────────────────────────────────────────

def g8_grace(incident: dict):
    """The grace period settled the incident (H2's `grace.judge`). Only a departure that
    persisted is healed; a device that cannot be read or checked can't be fixed. At its golden
    is no departure: the decision goes on to say nothing to heal, or a Tier 3 can't-fix."""
    s = incident.get("settled") or {}
    if s.get("how") in ("not_checkable", "unreadable"):
        return hit(8, "cant_fix", f"the device could not be judged: {s.get('words')}",
                   {"settled": s.get("how")})
    # The operator, 2026-11-16: no time-based hold. An incident not settled is judged by the
    # decision's own fresh read (step 4), never held a minute.
    return None


# ── 11 (the operator, 2026-11-16): a fix something keeps undoing ────────────────────────────

def g11_fight(fight: dict, stop: bool):
    """Retired (the operator, 2026-11-17, round 2): the fight stop holds nothing; the fight
    finding (`findings.fights`) still says a fix something keeps undoing. Kept, doing nothing,
    for its callers."""
    del fight, stop
    return None


# ── 9, 11: the rates (retired) ──────────────────────────────────────────────────────────────

#: Declared fault drills (the operator's decision, 2026-11-11, `modules/fault_drills.py`): "exempt
#: from guard 11 (same change healed twice in 24 h) and from the per-device rate holds. Nothing
#: else". So guards 9 and 11 do not apply to an incident tagged a drill at its creation (its
#: *drill*, the tag its decision carries), and for a real one they count real heals only:
#: "Drill heals are recorded and counted as drills, never in the real figures". Guard 10
#: counts every heal, a drill's included: it bounds the network's load, and is not exempt.
GUARDS_A_DRILL_PASSES = (9, 11)


def g9_device_rate(rows: list, device: str, outcome: str, now: float, most: int, *,
                   drill=None):
    """Retired (C3879; the operator, 2026-11-17): holds nothing. Kept, doing nothing, because
    a test still calls it (`scripts/check_removed_definitions.py`)."""
    del rows, device, outcome, now, most, drill
    return None


def g11_repeat(rows: list, device: str, departure: str, outcome: str, now: float, hours: int,
               *, drill=None):
    """Retired (C3879; the operator, 2026-11-17): halts nothing. Kept, doing nothing, because
    a test still calls it (`scripts/check_removed_definitions.py`)."""
    del rows, device, departure, outcome, now, hours, drill
    return None


# ── 12: the program's size (retired) ────────────────────────────────────────────────────────

def g12_size(units: list, most_removed: int, most_sections: int):
    """Retired (the operator, 2026-11-17, round 2): a program's size refuses nothing; verify
    and rollback are the safety. Kept, doing nothing, for its callers (a test still calls
    it)."""
    del units, most_removed, most_sections
    return None


# ── 14: a rolled-back heal (retired) ────────────────────────────────────────────────────────

def g14_rolled_back(rows: list, device: str, last_halt_epoch: float):
    """Retired (the operator, 2026-11-17, round 2): a rolled-back heal halts nothing; it is a
    failure R1 sees. Kept, doing nothing, for its callers (a test still calls it)."""
    del rows, device, last_halt_epoch
    return None
