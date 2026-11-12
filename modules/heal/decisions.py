"""The heal decisions: what the decision found and did for each incident, the dry run's
Right / Wrong marks, and the network's halts (board H, part H3; docs/HEAL_TO_INTENT.md
sections 4 step 2, 6, 7 and 9). Deterministic; no device.

**One record per decision**, appended to the network's ``heal/decisions.jsonl``, owner-only
(`config.open_secure`), never rewritten. A decision holds: the incident and device, the
outcome (`OUTCOMES`), the mode it was decided in, the first guard that applied (its number,
name, words and both operands), each unit by kind and tier with its lines MASKED, the program's
hash (never its text), the departure it judged, the policy's fingerprint and who confirmed it.

**The seams it leaves:**
- **H4 (act and verify)** takes a decision whose outcome is ``heal`` (`to_apply`, then `take`):
  it reads the device again, recomputes the program with `decide.program` from that read and
  refuses unless its hash is the decision's ``program_hash`` (the confirm-by-hash property, a
  heal's second hash, section 11), then records what it did with `applied` (its outcome, and
  ``rolled_back`` halts the network: guard 14).
- **H5 (Tier 2)** takes a ``propose`` decision (`proposals`) for a person's approval by hash.

**Right / Wrong (section 7).** A person marks a dry-run record right or wrong (`mark`): a
verified person, with a reason for Wrong; the marks are counted per fix kind (`dry_run_counts`)
as the false-positive rate the enablement path reads. The mark's route and control are H9's,
with the History step log's screen.

**Halts.** Guards 10, 11 and 14 halt the network's policy (`halt`): self-healing on it stops,
recorded with the guard and both operands, until a verified person lifts it with a reason
(`lift`: Needs attention's ``heal``/``halted`` row and its Lift the halt, routes/
heal_proposal_v2.lift, C2471). A halt is read by guard 2 (`halted`).

**Withdrawn** (`withdraw`, C2470): the heal's own pass withdraws a proposal no person has
taken, its device read back at intent or changed since, in one row. In dry run a guard that would halt records its
outcome and halts nothing: dry run never stops itself.
"""

import json
import logging
import os
import time
import uuid

log = logging.getLogger(__name__)

FILE = "decisions.jsonl"
OUTCOMES = ("heal", "would_heal", "propose", "cant_fix", "nothing", "held", "halted", "off",
            "deferred")
OUTCOME_WORDS = {"heal": "healing", "would_heal": "would heal (dry run)",
                 "propose": "proposed for a person", "cant_fix": "can't fix",
                 "nothing": "nothing to heal", "held": "held", "halted": "halted",
                 "off": "off", "deferred": "checked again later"}
#: A proposal the heal's own pass withdrew (C2470): its row, its two ways, and what it keeps.
WITHDRAWN = "withdrawn"
WITHDRAWN_HOW = ("at_intent", "changed")
WITHDRAWN_KEYS = ("how", "by", "words", "at", "bound", "read")
#: A lift's reason, its shape (as an approval's, `propose.REASON_WORDS`).
LIFT_REASON_WORDS = 3
#: How long a dry-run record waits for its mark on the drift row (`attention.heal_source`).
MARK_DAYS = 7


class Refused(ValueError):
    """A mark, a take or a lift refused, in words."""


class NotAPerson(Refused):
    """A lift refused because the request is not a verified person's."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def path(network: str) -> str:
    from modules.heal.incidents import _dir

    return os.path.join(_dir(network), FILE)


def _append(network: str, row: dict) -> dict:
    from modules import filestore
    from modules.config import open_secure
    from modules.nsot import listref

    if not network or not listref.exists(network):
        raise Refused(f"{network or 'no network'} is no network, so nothing is recorded")
    p = path(network)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with filestore.PathLock(p):
        with open_secure(p, "a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def read(network: str) -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``, oldest first. A line that
    will not parse makes the whole read unreadable: a decision quietly missing from the record
    is what it exists to prevent."""
    p = path(network)
    if not os.path.exists(p):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(p, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [],
                "error": f"{network}'s heal decisions cannot be read ({type(exc).__name__})"}
    return {"state": "ok", "rows": rows, "error": ""}


def _rows(network: str) -> list:
    got = read(network)
    if got["state"] == "unreadable":
        raise RuntimeError(got["error"])
    return got["rows"]


def record(network: str, decision: dict, now: float = None) -> dict:
    """Append one decision (`decide`'s): it gains its id, ``row: decision`` and its time."""
    now = time.time() if now is None else float(now)
    if decision.get("outcome") not in OUTCOMES:
        raise Refused(f"a decision's outcome is one of {', '.join(OUTCOMES)}, not "
                      f"{decision.get('outcome')!r}")
    row = dict(decision, id="hd-" + uuid.uuid4().hex[:12], row="decision", at=_iso(now),
               epoch=now, network=network)
    return _append(network, row)


def decisions(network: str) -> list:
    """Every decision, oldest first, each with its mark, its take and what was applied."""
    rows = _rows(network)
    by = {r["id"]: dict(r) for r in rows if r.get("row") == "decision"}
    for r in rows:
        target = by.get(r.get("decision") or "")
        if target is None:
            continue
        if r.get("row") == "mark":
            target["mark"] = {k: r.get(k) for k in ("right", "by", "why", "at")}
        elif r.get("row") == "taken":
            target["taken"] = {k: r.get(k) for k in ("by", "at")}
        elif r.get("row") == "applied":
            target["applied"] = {k: r.get(k) for k in ("outcome", "by", "at", "words")}
        elif r.get("row") == WITHDRAWN:
            # One row, so a reader never sees it taken without its outcome (`interrupted.find`
            # would read that as an approved heal whose job ended first).
            target["taken"] = {"by": r.get("by"), "at": r.get("at")}
            target["applied"] = {"outcome": WITHDRAWN, "by": r.get("by"), "at": r.get("at"),
                                 "words": r.get("words")}
            target["withdrawn"] = {k: r.get(k) for k in WITHDRAWN_KEYS}
    return list(by.values())


def find(network: str, decision_id: str) -> dict:
    for d in decisions(network):
        if d["id"] == decision_id:
            return d
    raise Refused(f"no heal decision {decision_id} is held for {network}")


# ── The seams for H4 and H5 ─────────────────────────────────────────────────────────────────

def to_apply(network: str) -> list:
    """**H4's seam:** the ``heal`` decisions not yet taken, oldest first."""
    return [d for d in decisions(network) if d["outcome"] == "heal" and not d.get("taken")]


def proposals(network: str) -> list:
    """**H5's seam:** the ``propose`` decisions not yet taken."""
    return [d for d in decisions(network) if d["outcome"] == "propose" and not d.get("taken")]


def withdraw(network: str, decision_id: str, *, how: str, by: str, words: str, read: dict,
             now: float = None) -> dict:
    """The heal's own pass withdraws a proposal no person has taken (C2470; board H artboard
    E: "If <device> changes, the proposal is withdrawn and made again"): *how* is ``at_intent`` (its
    device read back at its golden, which matches its intent) or ``changed`` (read with a
    departure other than the one it was bound to). ONE row, taken and its outcome together,
    under the take's lock, so a person's approval and a withdrawal never both take it; a
    proposal taken already is refused by name. *read* is the read that withdrew it (its time,
    state and departure: no configuration text)."""
    from modules import filestore

    now = time.time() if now is None else float(now)
    if how not in WITHDRAWN_HOW:
        raise Refused(f"a proposal is withdrawn {' or '.join(WITHDRAWN_HOW)}, not {how!r}")
    with filestore.PathLock(path(network) + ".take"):
        d = find(network, decision_id)
        if d["outcome"] != "propose":
            raise Refused(f"{decision_id} is {d['outcome']}: only a proposal is withdrawn")
        if d.get("taken"):
            raise Refused(f"{decision_id} was taken by {d['taken']['by']} at "
                          f"{d['taken']['at']}, so it is not withdrawn")
        _append(network, {"row": WITHDRAWN, "decision": decision_id, "how": how, "by": by,
                          "words": words, "at": _iso(now),
                          "bound": {"departure": d.get("departure") or "",
                                    "at": d.get("at") or ""},
                          "read": {k: (read or {}).get(k) for k in ("at", "state",
                                                                     "departure")}})
    return find(network, decision_id)


def take(network: str, decision_id: str, *, by: str, now: float = None) -> dict:
    """H4 (or H5) takes a decision to act on it, once; a second take is refused."""
    from modules import filestore

    now = time.time() if now is None else float(now)
    with filestore.PathLock(path(network) + ".take"):
        d = find(network, decision_id)
        if d["outcome"] not in ("heal", "propose"):
            raise Refused(f"{decision_id} is {d['outcome']}: only a heal or a proposal is "
                          "taken")
        if d.get("taken"):
            raise Refused(f"{decision_id} was taken by {d['taken']['by']} at "
                          f"{d['taken']['at']}, so it is not taken again")
        _append(network, {"row": "taken", "decision": decision_id, "by": by, "at": _iso(now)})
    return find(network, decision_id)


def applied(network: str, decision_id: str, outcome: str, *, by: str, words: str,
            now: float = None) -> dict:
    """H4 records what a taken heal did (``healed``, ``partial``, ``refused``,
    ``rolled_back``, ...). A rolled-back heal halts the network (guard 14)."""
    now = time.time() if now is None else float(now)
    d = find(network, decision_id)
    _append(network, {"row": "applied", "decision": decision_id, "outcome": outcome,
                      "by": by, "words": words, "at": _iso(now)})
    if outcome == "rolled_back":
        halt(network, guard=14, name="a rolled-back heal",
             words=f"the heal of {d.get('device')} ({decision_id}) was rolled back: {words}",
             operands={"decision": decision_id, "device": d.get("device")}, now=now)
    return find(network, decision_id)


# ── Right / Wrong ───────────────────────────────────────────────────────────────────────────

def mark(network: str, decision_id: str, right: bool, *, by: str, actor_verified: str,
         person: bool, why: str = "", now: float = None) -> dict:
    """A person marks a dry-run record right or wrong (section 7). A verified person; Wrong
    needs why. Marked again, the newest mark counts, and every mark stays in the record."""
    now = time.time() if now is None else float(now)
    if not by or actor_verified in ("", "none") or not person:
        raise NotAPerson(f"a dry-run record is marked by a verified person, and this request is "
                      f"not one (actor {by or 'none'}, verified {actor_verified or 'none'})")
    if not right and not (why or "").strip():
        raise Refused("Wrong is recorded with why it was wrong, and none was given")
    d = find(network, decision_id)
    if d["outcome"] != "would_heal":
        raise Refused(f"{decision_id} is {d['outcome']}, not a dry-run record: only what self-"
                      "healing would have done is marked right or wrong")
    _append(network, {"row": "mark", "decision": decision_id, "right": bool(right), "by": by,
                      "actor_verified": actor_verified, "why": (why or "").strip(),
                      "at": _iso(now)})
    return find(network, decision_id)


def dry_run_counts(network: str) -> dict:
    """``{kind: {"records", "right", "wrong", "unmarked", "false_positive"}}`` over the dry-run
    records (section 7's counter): *false_positive* is wrong over marked, or None before a
    mark. A declared fault drill's records are never in it (the operator, 2026-11-11: "Drill
    heals are recorded and counted as drills, never in the real figures"): `drill_counts`."""
    from modules import fault_drills

    out = {}
    for d in fault_drills.real_only(decisions(network)):
        if d["outcome"] != "would_heal":
            continue
        c = out.setdefault(d.get("kind") or "?", {"records": 0, "right": 0, "wrong": 0,
                                                  "unmarked": 0})
        c["records"] += 1
        m = d.get("mark")
        c["unmarked" if not m else "right" if m["right"] else "wrong"] += 1
    for c in out.values():
        marked = c["right"] + c["wrong"]
        c["false_positive"] = round(c["wrong"] / marked, 3) if marked else None
    return out


def drill_counts(network: str) -> dict:
    """``{outcome: count}`` over the declared fault drills' decisions alone, apart from every
    real figure (`dry_run_counts`, guards 9 and 11): a drill healed is counted here."""
    from modules import fault_drills

    out = {}
    for d in decisions(network):
        if fault_drills.is_drill(d):
            out[d["outcome"]] = out.get(d["outcome"], 0) + 1
    return out


# ── Halts ───────────────────────────────────────────────────────────────────────────────────

def halt(network: str, *, guard: int, name: str, words: str, operands: dict,
         now: float = None) -> dict:
    """Halt self-healing on *network* until a person lifts it."""
    now = time.time() if now is None else float(now)
    row = {"row": "halt", "id": "hh-" + uuid.uuid4().hex[:12], "guard": guard, "name": name,
           "words": words, "operands": operands, "at": _iso(now), "epoch": now}
    log.warning("heal: %s halted by guard %s: %s", network, guard, words)
    return _append(network, row)


def halted(network: str) -> dict:
    """The network's halt in force, or ``{}``: the newest halt with no lift after it. An
    unreadable record raises (guard 2 then fails closed)."""
    current = {}
    for r in _rows(network):
        if r.get("row") == "halt":
            current = r
        elif r.get("row") == "lift" and current and r.get("halt") == current.get("id"):
            current = {}
    return current


def last_halt_epoch(network: str) -> float:
    """When the newest halt was recorded (0 for none): guard 14 reads it."""
    return max((float(r.get("epoch") or 0) for r in _rows(network) if r.get("row") == "halt"),
               default=0.0)


def halt_row(network: str, halt_id: str) -> dict:
    """The halt *halt_id* as recorded, with ``lifted`` (its lift's who, when and why) once a
    person lifted it, or ``{}`` for a halt never recorded. An unreadable record raises."""
    found = {}
    for r in _rows(network):
        if r.get("row") == "halt" and r.get("id") == halt_id:
            found = dict(r)
        elif r.get("row") == "lift" and found and r.get("halt") == halt_id:
            found["lifted"] = {k: r.get(k) for k in ("by", "actor_verified", "reason", "at")}
    return found


def lift(network: str, halt_id: str, *, by: str, actor_verified: str, person: bool,
         reason: str, now: float = None) -> dict:
    """A verified person lifts the halt in force, with a reason of `LIFT_REASON_WORDS` words or
    more (board H artboard E, "Lift the halt…"; a reason's shape, never its quality, as an
    approval's). Raises `NotAPerson` or `Refused` naming both operands; nothing is lifted."""
    now = time.time() if now is None else float(now)
    if not by or actor_verified in ("", "none") or not person:
        raise NotAPerson(f"a halt is lifted by a verified person, and this request is not one "
                         f"(actor {by or 'none'}, verified {actor_verified or 'none'})")
    text = (reason or "").strip()
    if not text:
        raise Refused("a halt is lifted with a recorded reason, and none was given")
    if len(text.split()) < LIFT_REASON_WORDS:
        raise Refused(f"a halt is lifted with a reason of {LIFT_REASON_WORDS} words or more, "
                      f"recorded as the person's statement ({len(text.split())} given): "
                      "nothing was lifted")
    from modules import filestore

    # The check and the lift under one lock, across processes: two people lifting at once
    # record one lift, and the second is told whose it was.
    with filestore.PathLock(path(network) + ".lift"):
        current = halted(network)
        if current.get("id") != halt_id:
            done = (halt_row(network, halt_id).get("lifted") or {}) if halt_id else {}
            raise Refused(f"the halt in force is {current.get('id') or 'none'}, not {halt_id}"
                          + (f" (lifted by {done.get('by')} at {done.get('at')})" if done
                             else "") + ": nothing was lifted")
        row = _append(network, {"row": "lift", "halt": halt_id, "by": by,
                                "actor_verified": actor_verified, "reason": text,
                                "at": _iso(now)})
    log.info("heal: %s's halt %s (guard %s) lifted by %s: %s", network, halt_id,
             current.get("guard"), by, text)
    return row
