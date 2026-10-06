"""nsot/expected_effects.py

What a change INTENDS, so verify can tell an intended effect from a failure (C506, board
approved 2026-10-06).

Verify compared COUNTS before and after. So a program's own `shutdown` counted as a loss and
was rolled back, and because interfaces were counted, not named, a cable move that downs Gi3
and brings up Gi4 netted to zero and would hide an untouched interface lost at the same moment.

This module answers two questions, both by NAME:

* :func:`derive`: the effects the program itself implies. An interface section it shuts is
  expected to go down; one it brings up (`no shutdown`) is expected to be up when verify ends.
* :func:`interface_states`: each interface's state from the read verify already makes
  (`show interfaces | include (line protocol|Internet address)`).

and :func:`judge` compares them: an interface up before and down after that the program did
not shut is UNEXPECTED (a hard failure, rolled back after a short settle), one it shut is
expected, and one it brings up that is not up is the intended end state not reached.
"""

import re

#: IOS abbreviations, longest first, to the name `show interfaces` prints.
_ABBREVIATIONS = (
    ("tengigabitethernet", "TenGigabitEthernet"), ("te", "TenGigabitEthernet"),
    ("gigabitethernet", "GigabitEthernet"), ("gi", "GigabitEthernet"),
    ("fastethernet", "FastEthernet"), ("fa", "FastEthernet"),
    ("ethernet", "Ethernet"), ("et", "Ethernet"),
    ("port-channel", "Port-channel"), ("po", "Port-channel"),
    ("loopback", "Loopback"), ("lo", "Loopback"),
    ("tunnel", "Tunnel"), ("tu", "Tunnel"),
    ("vlan", "Vlan"), ("vl", "Vlan"),
)

_STATE_LINE = re.compile(r"^(\S+) is (administratively down|up|down|deleted)[^,]*, "
                         r"line protocol is (up|down)", re.I)


def canonical(name: str) -> str:
    """*name* as `show interfaces` prints it (`Gi3` -> `GigabitEthernet3`); unknown prefixes are
    returned as given."""
    m = re.match(r"^([A-Za-z-]+)\s*([0-9/.:]+)$", (name or "").strip())
    if not m:
        return (name or "").strip()
    word, number = m.group(1).lower(), m.group(2)
    for short, full in _ABBREVIATIONS:
        if word == short:
            return full + number
    return m.group(1) + number


def interface_states(output: str) -> dict:
    """``{interface: "up" | "down" | "admin_down"}`` from the interfaces read; "up" only when
    the line protocol is up. Empty when nothing could be parsed (the caller then falls back to
    counting, and says so)."""
    states = {}
    for line in (output or "").splitlines():
        m = _STATE_LINE.match(line.strip())
        if not m:
            continue
        name, admin, proto = m.group(1), m.group(2).lower(), m.group(3).lower()
        if admin == "administratively down":
            states[name] = "admin_down"
        elif proto == "up":
            states[name] = "up"
        else:
            states[name] = "down"
    return states


def derive(commands) -> dict:
    """The interface effects the program implies: ``{"down": [...], "up": [...]}``, sorted
    canonical names. Within an `interface X` section, `shutdown` expects X down and
    `no shutdown` expects X up; the last of the two in a section wins, as on the device."""
    effect = {}
    current = None
    for raw in commands or []:
        line = (raw or "").rstrip()
        stripped = line.strip()
        if not stripped or stripped == "!":
            continue
        if not line.startswith(" ") and not line.startswith("\t"):
            m = re.match(r"^interface\s+(\S+)", stripped, re.I)
            current = canonical(m.group(1)) if m else None
            if stripped.lower() in ("exit", "end"):
                current = None
            continue
        if current is None:
            continue
        if stripped.lower() == "shutdown":
            effect[current] = "down"
        elif stripped.lower() == "no shutdown":
            effect[current] = "up"
    return {"down": sorted(n for n, e in effect.items() if e == "down"),
            "up": sorted(n for n, e in effect.items() if e == "up")}


def judge(expected: dict, before: dict, after: dict) -> dict:
    """Compare the interface states by name against the expected effects.

    ``{"lost_expected": [...], "lost_unexpected": [...], "not_up": [...], "came_up": [...]}``:
    up before and not up after, split by whether the program shut it; an interface the program
    brings up that is not up; and anything that came up. Interfaces missing from either read
    are not judged (a read that lists fewer interfaces is the caller's to treat as unreadable)."""
    down = set(expected.get("down") or [])
    up = set(expected.get("up") or [])
    lost = sorted(n for n, s in before.items() if s == "up" and n in after and after[n] != "up")
    return {
        "lost_expected": [n for n in lost if n in down],
        "lost_unexpected": [n for n in lost if n not in down],
        "not_up": sorted(n for n in up if after.get(n) != "up"),
        "came_up": sorted(n for n, s in after.items() if s == "up" and before.get(n) != "up"),
    }
