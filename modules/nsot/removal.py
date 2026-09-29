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

**Allowed only where MEASURED** (the operator, 2026-09-28: "ask the platform
rather than reason about it; this is the one part of Mode B where being wrong
destroys config rather than refusing to"). `no <exact line>` can do more than
undo the line: `no access-list 10 <entry>` deletes the whole list, and the
same shape is suspected of a BGP neighbour's `remote-as` (the whole
neighbour), of `logging buffered` (turns logging off rather than restoring
the default), and of entries in any list. So a line is removed only if it
matches a SHAPE (:data:`SHAPES`) that `scripts/nmas-removal-probe` measured on
the device's PLATFORM, on a device, removing exactly that line and nothing
else (``removal_measured.json``). Anything else is refused as unmeasured,
naming the probe. An allowlist, the C61 lesson: a command added later cannot
outgrow it.

A line in a secret position is removable, and flagged ``secret_position``, so
the preview can require a stated reason for it the way C79 does. The flag is
set from `redact.redact_positional`, the same slots every mask uses.
"""

import json
import logging
import os
import re
from typing import NamedTuple

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
    (re.compile(r"^banner\s"), "a banner spans lines the line model cannot represent"),
    (re.compile(r"^crypto pki\b"), "a trustpoint or certificate body spans lines, and is "
                                   "the device's own"),
    # MEASURED, and retired from the probe so no run dirties a device to learn
    # it again (the operator, 2026-09-28).
    (re.compile(r"^logging buffered\b"),
     "measured on cisco_ios (s4, 2026-09-29): `no logging buffered <n>` turns buffered "
     "logging OFF and leaves `no logging buffered` behind, a state neither the device had "
     "nor intent names. Its absence means the platform default, and restoring a default is "
     "`default <command>`, which is not built"),
)


class Shape(NamedTuple):
    """A kind of line whose removal can be measured: where it sits
    (``context``), whether it is a line or a stanza, and the pattern."""
    key: str
    context: str
    kind: str
    pattern: str


#: Every shape the probe measures, including the ones SUSPECTED of removing
#: more than their line: they are measured so the record shows why they are
#: refused, never assumed. A line matching none is refused as unmeasured.
SHAPES = (
    Shape("interface.load-interval", "interface", "leaf", r"^load-interval \d+$"),
    Shape("interface.description", "interface", "leaf", r"^description .+$"),
    Shape("global.snmp-server-community", "global", "leaf",
          r"^snmp-server community \S+( view \S+)? (RO|RW)( \S+)?$"),
    Shape("global.logging-host", "global", "leaf", r"^logging host \S+( .+)?$"),
    Shape("global.event-manager-applet", "global", "stanza", r"^event manager applet \S+( .+)?$"),
    Shape("global.ip-prefix-list-entry", "global", "leaf",
          r"^ip prefix-list \S+ seq \d+ (permit|deny) .+$"),
    Shape("global.route-map-sequence", "global", "stanza",
          r"^route-map \S+ (permit|deny) \d+$"),
    Shape("global.numbered-acl-entry", "global", "leaf", r"^access-list \d+ .+$"),
    Shape("named-acl.entry", "ip access-list", "leaf", r"^(\d+ )?(permit|deny|remark) .+$"),
    Shape("bgp.neighbor-remote-as", "router bgp", "leaf", r"^neighbor \S+ remote-as \d+$"),
)

#: What a measurement found, in words.
RESULT_WORDS = {
    "exact": "removes exactly that line",
    "broader": "removes MORE than that line",
    "different": "changes other configuration",
    "incomplete": "does not remove the line",
    "overrides_default": ("leaves the device OFF its default: `no` turns the feature off "
                          "instead of restoring the default, and leaves a `no` line"),
    "refused": "is rejected by the device",
    "failed": "could not be measured",
}

MEASURED_FILE = os.path.join(os.path.dirname(__file__), "removal_measured.json")


def measured() -> dict:
    """``{"state": absent|unreadable|ok, "by_dialect": {dialect: {key: row}}}``.
    Absent and unreadable are different answers, and neither allows anything."""
    if not os.path.exists(MEASURED_FILE):
        return {"state": "absent", "by_dialect": {}}
    try:
        with open(MEASURED_FILE, encoding="utf-8") as fh:
            return {"state": "ok", "by_dialect": json.load(fh).get("by_dialect") or {}}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "by_dialect": {}, "error": str(exc)}


def _in_context(context: str, chain: tuple) -> bool:
    if context == "global":
        return not chain
    if len(chain) != 1:
        return False
    return chain[0].startswith({"interface": "interface ", "ip access-list": "ip access-list ",
                                "router bgp": "router bgp "}.get(context, "\0"))


def shape_for(chain, line: str, kind: str):
    """The measured shape this line is an instance of, or None."""
    text = line.strip()
    for shape in SHAPES:
        if shape.kind == kind and _in_context(shape.context, tuple(chain)) \
                and re.search(shape.pattern, text):
            return shape
    return None


def _unmeasured(chain, line: str, kind: str, dialect: str) -> str:
    """Why this unit may not be removed on *dialect* yet, or ""."""
    shape = shape_for(chain, line, kind)
    if shape is None:
        return ("no measured shape covers this line: what `no` does to it on the platform "
                "is not known, so nothing is sent. A shape is added to removal.SHAPES and "
                "measured with scripts/nmas-removal-probe first")
    if not dialect:
        return "the device's platform is not known, and removal is measured per platform"
    record = measured()
    if record["state"] == "unreadable":
        return f"the removal measurements could not be read ({record.get('error')})"
    row = (record["by_dialect"].get(dialect) or {}).get(shape.key)
    if not row:
        return (f"`{shape.key}` has not been measured on {dialect}: run "
                f"scripts/nmas-removal-probe --shape {shape.key} on a {dialect} device")
    if row.get("result") != "exact":
        return (f"measured on {dialect} ({row.get('device')}, {row.get('at')}): `no <line>` "
                f"{RESULT_WORDS.get(row.get('result'), row.get('result'))}"
                + (f": {row['detail']}" if row.get("detail") else ""))
    return ""

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


def negation_program(units: list) -> list:
    """The program for *units* (``{"chain", "line"}``), and nothing else:
    each negated verbatim in its stanza, one `exit` per open level. No gate
    runs here; :func:`removal_program` is the gated path, and the probe calls
    this to measure what the gates would allow."""
    from modules.nsot.deploy import assert_sendable

    commands, open_chain = [], []

    def _close():
        for _level in open_chain:
            commands.append("exit")
        open_chain.clear()

    for u in units:
        chain = list(u["chain"])
        if chain != open_chain:
            _close()
            commands.extend(chain)
            open_chain.extend(chain)
        commands.append(_negate(u["line"]))
    _close()
    assert_sendable(commands)
    return commands


def removal_program(running_config: str, selected: list, *, mgmt_ip: str = "",
                    dialect: str = "") -> dict:
    """The exact program removing *selected* units from *running_config*.

    ``{"commands", "removed", "refused", "secret_position"}``. Each unit is
    ``{"chain", "line"}`` as :func:`candidates` gives it. A unit not on the
    device is refused (the device moved, or the unit was never there); a unit
    inside a stanza also selected is implied and sends nothing of its own."""
    from modules.nsot import ifnames
    from modules.redact import redact_positional

    running = _chains(running_config)
    headers = _headers(running)
    present = {chain + (line,) for line, chain in running}
    mgmt_ifaces = _management_interfaces(running, mgmt_ip)
    units = []
    for u in selected or []:
        chain = tuple(ifnames.canonicalise_line(c) for c in u.get("chain") or [])
        units.append({"chain": list(chain), "line": ifnames.canonicalise_line(u.get("line", ""))})
    whole = {tuple(u["chain"]) + (u["line"],) for u in units}

    removed, refused, secret = [], [], []
    for u in units:
        path = tuple(u["chain"]) + (u["line"],)
        if path not in present:
            refused.append({**u, "reason": "not on the device: it moved since the preview, "
                                           "or was never there"})
            continue
        if any(path[:len(w)] == w and path != w for w in whole):
            continue                     # implied by a stanza also selected
        kind = "stanza" if path in headers else "leaf"
        why = (_refusal(u, running, mgmt_ifaces)
               or _unmeasured(u["chain"], u["line"], kind, dialect))
        if why:
            refused.append({**u, "reason": why})
            continue
        removed.append(u)
        if redact_positional(u["line"]) != u["line"]:
            secret.append(u)
    return {"commands": negation_program(removed), "removed": removed, "refused": refused,
            "secret_position": secret}
