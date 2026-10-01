"""Changing an IP SLA operation that is RUNNING: delete it, re-create it from
intent, reschedule it.

IOS refuses to modify a scheduled IP SLA entry ("Entry already running and
cannot be modified (only can delete (no) and start over)"), so an intent edit
to a running operation, sent as the ordinary merge (`ip sla 1` then
` frequency 60`), is refused by the device and rolled back. The operator's
case (2026-10-01): s3's probe to r1, every 10 s, slowed to 60 s to take load
off the management gateway (register C93).

This module is the COMPUTATION, and nothing here connects to anything. For an
operation the device runs and intent defines DIFFERENTLY (its body, or its
schedule):

- :func:`plan` gives the program: ``no ip sla N`` (which deletes the entry and
  its schedule), then the operation as intent defines it and its schedule,
  built by the one builder deploys use (`merge_commands`), so its exits follow
  the definition's own indentation. The ordinary merge never sees the
  operation (:func:`exclude`), so the refused in-place edit is never sent.
- :func:`undo_program` restores the OLD definition from the pre-change
  snapshot the same way: delete, then the device's own lines put back. Its
  provenance is the snapshot by construction.
- :func:`unmatched` reads an operation back: what a config shows of it against
  what it should show. Verify asks it of the new definition; the rollback's
  read-back asks it of the old one.

**The delete is MEASURED, like every Mode B removal.** `no ip sla N` is the
removal shape ``global.ip-sla-operation`` (removal.SHAPES): until
`scripts/nmas-removal-probe` has measured on the device's PLATFORM that it
removes exactly the operation and its own schedule line, a re-create is
refused, naming the probe. The refusal blocks the device; nothing is sent.

**Refused, with the reason, never guessed**: an operation another line on the
device refers to (a `track` object, a reaction configuration, a group
schedule). Deleting the operation takes or breaks those, and intent does not
model them, so the re-create would change configuration nobody planned.
"""

import logging
import re

log = logging.getLogger(__name__)

HEADER = re.compile(r"^ip sla (\d+)$")
SCHEDULE = re.compile(r"^ip sla schedule (\d+)\b")

#: The removal shape whose measurement allows the delete.
SHAPE_KEY = "global.ip-sla-operation"


def _dependents(n: str) -> list:
    """Top-level lines that name operation *n* and are not its own definition
    or schedule: deleting the operation removes or breaks each."""
    return [re.compile(rf"^ip sla (reaction-configuration|reaction-trigger|enable reaction-alert)"
                       rf"\s+{n}\b"),
            re.compile(rf"^ip sla group schedule \S+ .*\b{n}\b"),
            re.compile(rf"^track \d+ (ip sla|rtr) {n}\b")]


def operations(config: str) -> dict:
    """``{number: {"body": [lines, verbatim], "schedule": [lines]}}`` for every
    IP SLA operation *config* defines."""
    ops, current = {}, None
    for raw in (config or "").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip() == "!":
            if line.strip() == "!":
                current = None
            continue
        if not line.startswith(" "):
            current = None
            m = HEADER.match(line)
            if m:
                current = ops.setdefault(m.group(1), {"body": [], "schedule": []})
                continue
            s = SCHEDULE.match(line)
            if s:
                ops.setdefault(s.group(1), {"body": [], "schedule": []})["schedule"].append(line)
            continue
        if current is not None:
            current["body"].append(line)
    return ops


def _same(a: dict, b: dict) -> bool:
    return ([l.strip() for l in a["body"]] == [l.strip() for l in b["body"]]
            and [l.strip() for l in a["schedule"]] == [l.strip() for l in b["schedule"]])


def _fragment(n: str, op: dict) -> str:
    return "\n".join([f"ip sla {n}"] + op["body"] + op["schedule"]) + "\n"


def _definition_program(n: str, op: dict) -> list:
    """The operation and its schedule, sent as a definition from nothing."""
    from modules.nsot.deploy import merge_commands
    return merge_commands(_fragment(n, op), "")


def plan(intended: str, captured: str, *, dialect: str) -> dict:
    """``{"units", "commands", "refused"}`` for every operation the device runs
    that intent defines differently. A unit is ``{"number", "old", "new"}``;
    a refusal ``{"number", "reason"}``. An operation the device lacks is the
    ordinary merge's (a new operation is not running), and one intent lacks is
    Mode B's (removed only when a person selects it)."""
    from modules.nsot.removal import _unmeasured

    want, have = operations(intended), operations(captured)
    top = [l.rstrip() for l in (captured or "").splitlines() if l and not l.startswith(" ")]
    units, refused, commands = [], [], []
    for n in sorted(set(want) & set(have), key=int):
        new, old = want[n], have[n]
        # A device schedules what it defines; an entry with no body on either
        # side is a schedule alone, not an operation to re-create.
        if not new["body"] or not old["body"] or _same(new, old):
            continue
        why = _unmeasured([], f"ip sla {n}", "stanza", dialect)
        if why:
            refused.append({"number": n, "reason": (
                f"ip sla {n} is running, and IOS refuses to modify a running operation, so "
                f"the change deletes it and re-creates it; that delete is not allowed: {why}")})
            continue
        named = [l for l in top for p in _dependents(n) if p.search(l)]
        if named:
            refused.append({"number": n, "reason": (
                f"ip sla {n} is running and must be deleted to change it, and the device has "
                f"configuration naming it that deleting it removes or breaks, which intent does "
                f"not model: " + "; ".join(named))})
            continue
        units.append({"number": n, "old": old, "new": new})
        commands += [f"no ip sla {n}"] + _definition_program(n, new)
    if commands:
        from modules.nsot.deploy import assert_sendable
        assert_sendable(commands)
    return {"units": units, "commands": commands, "refused": refused}


def exclude(config: str, units: list) -> str:
    """*config* without the re-created operations' definitions and schedules,
    so the ordinary merge never sends the in-place edit the device refuses."""
    numbers = {u["number"] for u in units or []}
    if not numbers:
        return config
    out, skipping = [], False
    for raw in (config or "").splitlines():
        if raw and not raw.startswith(" "):
            m, s = HEADER.match(raw.rstrip()), SCHEDULE.match(raw.rstrip())
            skipping = bool(m and m.group(1) in numbers)
            if skipping or (s and s.group(1) in numbers):
                continue
        elif skipping:
            continue
        out.append(raw)
    return "\n".join(out) + ("\n" if (config or "").endswith("\n") else "")


def undo_program(units: list, pre_config: str) -> list:
    """Restore each re-created operation's OLD definition from the snapshot:
    delete what is there now, then the device's own lines put back."""
    before = operations(pre_config)
    commands = []
    for u in units or []:
        n = u["number"]
        old = before.get(n)
        if not old or not old["body"]:
            raise RuntimeError(f"ip sla {n} is not in the pre-change snapshot, so its old "
                               f"definition cannot be put back")
        commands += [f"no ip sla {n}"] + _definition_program(n, old)
    return commands


def unmatched(units: list, config: str, side: str) -> list:
    """The units whose operation *config* does not show as their *side*
    (``new`` after the change, ``old`` after a rollback), each with what it
    shows instead."""
    now = operations(config)
    out = []
    for u in units or []:
        n, want = u["number"], u[side]
        got = now.get(n) or {"body": [], "schedule": []}
        if not _same(want, got):
            out.append({"number": n, "expected": [l.strip() for l in want["body"] + want["schedule"]],
                        "found": [l.strip() for l in got["body"] + got["schedule"]]})
    return out


def describe(unit: dict) -> dict:
    """The preview's note for one re-created operation: what it says and the
    definition it replaces."""
    n = unit["number"]
    return {"title": (f"ip sla {n} is running, and IOS refuses to modify a running "
                      f"operation: the program deletes it, re-creates it from intent and "
                      f"reschedules it. Its counters and history start again. What it "
                      f"replaces on the device:"),
            "lines": [f"ip sla {n}"] + unit["old"]["body"] + unit["old"]["schedule"]}
