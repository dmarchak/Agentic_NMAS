"""Mode B: remove a line the device has and intent does not (7.3 step 2).

Every deploy is merge-only and a restore is additive, so until this module a
line on the device that intent lacks could leave only by a person on the
console, or by being adopted into intent. "A hand change becomes permanent in
the record until someone undoes it by hand" (the operator, 2026-09-28). Four
places waited on it: r2's `load-interval 30`, which denies every baseline;
C12's heartbeat block, add-only; C139's old community after a rotation; and a
restore's residue, reported as "will NOT be removed".

This module is the COMPUTATION, and nothing here connects to anything:

- :func:`candidates` lists what CAN be selected for removal. It lists residue
  lines (on the device, not mentioned by the target) and whole stanzas whose
  header the target lacks, as one unit with the stanza's children listed.
- :func:`removal_program` turns the units a person SELECTED into the exact
  program, refusing each unit it will not remove, with the reason.

**Selected, never inferred.** Nothing here removes "everything intent lacks".
A person chooses each unit, with a reason. Converging a device to intent
automatically would decide, for the person, which side of a departure is
right. That is the one decision the tool is built to leave with a person
(C184's two resolutions).

**Verbatim.** A removal is ``no`` plus the device's own line, never a rebuilt
one (onboarding's rule for the RW community, generalised): a rebuilt line
drops an ACL, a view or a spacing the device has, and then it does not match.
A line that is itself a ``no`` is removed by its positive form.

**Refused, with the reason, never guessed** (the classes and why):

- A construct IOS will not remove, or removes differently: a physical
  interface (``default interface`` resets one; not built), a ``line`` stanza,
  ``hostname``, ``version``, the boot markers.
- A NUMBERED access-list entry: ``no access-list 10 permit ...`` deletes the
  WHOLE of list 10 on IOS, not the one entry.
- The path the tool reaches the device on. A rollback would travel over the
  thing being changed (the repair-path class): the management interface's
  stanza, the vty lines, SSH, AAA, the RSA key, a static route or a default
  gateway, which may be the manager's path.
- An account: removing one is retirement's or rotation's job, never a residue
  clean-up.
- A named object something else still uses (a prefix-list a neighbour
  references, a VRF its interfaces sit in): removing a VRF strips the
  addresses from every member interface. Conservative on purpose: any other
  line naming the object refuses, and the reason names that line.

A line in a secret position is removable, and flagged ``secret_position``, so
the preview can require a stated reason for it the way C79 does. The flag is
set from `redact.redact_positional`, the same slots every mask uses.
"""

import logging
import re

log = logging.getLogger(__name__)

#: Interface kinds that can be created, and therefore removed, with
#: `no interface <name>`. Anything else is physical: `default interface`.
VIRTUAL_INTERFACES = ("Loopback", "Tunnel", "Vlan", "Port-channel", "BDI",
                      "Virtual-Template", "NVE", "Virtual-PPP", "Dialer")

#: Global lines and headers IOS will not remove with `no`, each with why.
UNREMOVABLE = (
    (re.compile(r"^hostname\b"), "the hostname cannot be removed, only changed in intent"),
    (re.compile(r"^version\b"), "the image version is not configuration"),
    (re.compile(r"^boot-(start|end)-marker\b"), "a boot marker is not configuration"),
    (re.compile(r"^line\s"), "a line stanza cannot be removed; change its settings instead"),
    (re.compile(r"^end$"), "`end` is not configuration"),
)

#: The management path, at the global level. Each may be how the tool
#: reaches the device, and a removal that breaks it cannot be undone by the
#: tool (the rollback would travel over it).
MANAGEMENT_GLOBAL = (
    (re.compile(r"^ip ssh\b"), "SSH is how the tool reaches the device"),
    (re.compile(r"^aaa\b"), "AAA decides whether the tool can log in"),
    (re.compile(r"^crypto key\b"), "the RSA key is what SSH runs on"),
    (re.compile(r"^ip domain[ -]name\b"), "the RSA key depends on the domain name"),
    (re.compile(r"^ip(v6)? route\b"), "a static route may be the path to the manager"),
    (re.compile(r"^ip default-gateway\b"), "the default gateway may be the path to the manager"),
)

ACCOUNT = re.compile(r"^(username\s|enable (secret|password)\b)")
NUMBERED_ACL = re.compile(r"^access-list\s+\d+\s")

#: Headers or lines that DEFINE a named object, and the group holding the name.
DEFINES = (
    re.compile(r"^ip(v6)? access-list (?:(?:standard|extended)\s+)?(?P<name>\S+)"),
    re.compile(r"^ip(v6)? prefix-list (?P<name>\S+)\s"),
    re.compile(r"^route-map (?P<name>\S+)"),
    re.compile(r"^vrf definition (?P<name>\S+)"),
    re.compile(r"^ip vrf (?P<name>\S+)"),
    re.compile(r"^class-map (?:match-\S+\s+)?(?P<name>\S+)"),
    re.compile(r"^policy-map (?P<name>\S+)"),
    re.compile(r"^key chain (?P<name>\S+)"),
    re.compile(r"^object-group \S+ (?P<name>\S+)"),
)


def _chains(config: str) -> list:
    """``[(line, chain)]``, the same section model the merge and the rollback
    use, so a removal is placed where they place an addition."""
    from modules.nsot.deploy import _section_chains
    return [(line, tuple(chain)) for line, chain in _section_chains(config)]


def _headers(entries: list) -> set:
    return {chain[:depth + 1] for _line, chain in entries for depth in range(len(chain))}


def candidates(target_config: str, running_config: str) -> list:
    """What can be selected for removal: ``[{"chain", "line", "kind",
    "children"}]``. A stanza whose header the target lacks is ONE unit
    (``kind: "stanza"``), with its children listed and never offered
    separately, because removing the header removes them. Every other residue
    line is a ``leaf``. The residue is `classify_diff`'s, so what the preview
    calls "will NOT be removed" and what can be selected are the same set."""
    from modules.nsot.deploy import classify_diff
    from modules.nsot import ifnames

    running = _chains(running_config)
    target = _chains(target_config)
    target_present = {chain + (line,) for line, chain in target} | _headers(target)
    headers = _headers(running)
    residue = {ifnames.canonicalise_line(r.rstrip())
               for r in classify_diff(target_config, running_config)["residue"]}

    out, gone = [], []
    for line, chain in running:
        path = chain + (line,)
        if any(path[:len(g)] == g for g in gone):
            continue                     # inside a stanza already offered whole
        if path in headers and path not in target_present:
            children = [l for l, c in running if c[:len(path)] == path]
            out.append({"chain": list(chain), "line": line, "kind": "stanza",
                        "children": children})
            gone.append(path)
        elif path not in headers and line in residue and path not in target_present:
            out.append({"chain": list(chain), "line": line, "kind": "leaf", "children": []})
    return out


def _negate(line: str) -> str:
    indent = line[:len(line) - len(line.lstrip())]
    text = line.strip()
    if text.startswith("no "):
        return indent + text[3:]
    return indent + "no " + text


def _management_interfaces(running: list, mgmt_ip: str) -> set:
    """Interface headers the tool may reach the device through: the one
    holding the address the tool connects to, and any addressed by DHCP
    (whose address is the lease's, so the config cannot show it is not the
    path)."""
    out = set()
    for line, chain in running:
        if len(chain) == 1 and chain[0].startswith("interface "):
            words = line.split()
            if words[:2] == ["ip", "address"] and len(words) > 2 and (
                    words[2] == "dhcp" or (mgmt_ip and words[2] == mgmt_ip)):
                out.add(chain[0])
    return out


def _is_physical(header: str) -> bool:
    name = header.split(None, 1)[1] if " " in header else ""
    return bool(name) and "." not in name and not name.startswith(VIRTUAL_INTERFACES)


def _refusal(unit: dict, running: list, mgmt_ifaces: set) -> str:
    chain, line = tuple(unit["chain"]), unit["line"]
    text = line.strip()
    top = chain[0] if chain else text
    if not chain:
        for pattern, why in UNREMOVABLE:
            if pattern.search(text):
                return why
        if text.startswith("interface ") and _is_physical(text):
            return ("a physical interface cannot be removed; `default interface` resets "
                    "one, and that is not built")
        if ACCOUNT.search(text):
            return ("an account is removed by retiring or rotating, never as residue: "
                    "removing the tool's own account locks it out")
        if NUMBERED_ACL.search(text):
            return ("IOS deletes the WHOLE numbered access-list for `no access-list <n> "
                    "...`, not this entry")
        for pattern, why in MANAGEMENT_GLOBAL:
            if pattern.search(text):
                return "the management path: " + why
    if top in mgmt_ifaces or text in mgmt_ifaces:
        return (f"the management path: {top if chain else text} is the interface the tool "
                "reaches this device on, and a rollback would travel over it")
    if top.startswith("line vty"):
        return "the management path: the vty lines are how the tool logs in"
    name = _defined_name(text) if not chain else ""
    if name:
        uses = _references(name, unit, running)
        if uses:
            return (f"{name} is still used by: " + "; ".join(uses[:3])
                    + (f" (and {len(uses) - 3} more)" if len(uses) > 3 else "")
                    + ". Remove or change those first")
    return ""


def _defined_name(text: str) -> str:
    for pattern in DEFINES:
        m = pattern.search(text)
        if m:
            return m.group("name")
    return ""


def _references(name: str, unit: dict, running: list) -> list:
    """Every other line naming *name* as a whole word, outside the object's
    own definition: its own stanza, and (for a list defined line by line,
    such as a prefix-list) its other entries."""
    own = tuple(unit["chain"]) + (unit["line"],)
    word = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")
    out = []
    for line, chain in running:
        path = chain + (line,)
        if path[:len(own)] == own:
            continue
        if _defined_name(line.strip()) == name and not chain:
            continue
        if word.search(line):
            out.append(" > ".join(list(chain) + [line.strip()]))
    return out


def removal_program(running_config: str, selected: list, *, mgmt_ip: str = "") -> dict:
    """The exact program removing *selected* units from *running_config*.

    ``{"commands", "removed", "refused", "secret_position"}``. Each unit is
    ``{"chain", "line"}`` as :func:`candidates` gives it. A unit not on the
    device is refused (the device moved, or the unit was never there); a unit
    inside a stanza also selected is implied and sends nothing of its own."""
    from modules.nsot import ifnames
    from modules.nsot.deploy import assert_sendable
    from modules.redact import redact_positional

    running = _chains(running_config)
    present = {chain + (line,) for line, chain in running}
    mgmt_ifaces = _management_interfaces(running, mgmt_ip)
    units = []
    for u in selected or []:
        chain = tuple(ifnames.canonicalise_line(c) for c in u.get("chain") or [])
        units.append({"chain": list(chain), "line": ifnames.canonicalise_line(u.get("line", ""))})
    whole = {tuple(u["chain"]) + (u["line"],) for u in units}

    removed, refused, secret, pending = [], [], [], []
    for u in units:
        path = tuple(u["chain"]) + (u["line"],)
        if path not in present:
            refused.append({**u, "reason": "not on the device: it moved since the preview, "
                                           "or was never there"})
            continue
        if any(path[:len(w)] == w and path != w for w in whole):
            continue                     # implied by a stanza also selected
        why = _refusal(u, running, mgmt_ifaces)
        if why:
            refused.append({**u, "reason": why})
            continue
        removed.append(u)
        if redact_positional(u["line"]) != u["line"]:
            secret.append(u)
        pending.append((list(u["chain"]), _negate(u["line"])))

    commands, open_chain = [], []

    def _close():
        for _level in open_chain:
            commands.append("exit")
        open_chain.clear()

    for chain, command in pending:
        if chain != open_chain:
            _close()
            commands.extend(chain)
            open_chain.extend(chain)
        commands.append(command)
    _close()
    assert_sendable(commands)
    return {"commands": commands, "removed": removed, "refused": refused,
            "secret_position": secret}
