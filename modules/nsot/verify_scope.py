"""Which verify a program gets: QUICK for a management-only change, FULL for
anything that can affect forwarding (the operator, 2026-10-01).

The vty standardisation sent five lines under `line vty 0 4` to r1 to r4,
and r3 and r4 each took three to four minutes: verify waits out BGP's hold
time after every push (C178, up to 180 s), because a session a change broke
reads Established until then. A change to the terminal lines cannot break a
BGP session, so that wait proved nothing about it.

**The rule.** A program is classified by the top-level section of every line
it sends. When EVERY section is one of the management families below, verify
is QUICK: the device answers on a new session (the post-change read is
always a fresh login, C272), the tool can still log in (that same login), and
each new line is read back from the device's configuration (a FULL verify reads
them back too since C732, 2026-10-13). BGP's hold-time watch is skipped. Every other check still runs once (neighbour, route and
interface counts, and a drop is still waited out), because a management
change that drops a neighbour is exactly what verify exists to catch.
Anything else, or anything not recognised, is FULL: interfaces, ACLs, route
maps, prefix lists, VRFs, routing processes, static routes, IP SLA (which a
`track` can tie to routing), and every section nobody has named here. A
family joins MANAGEMENT by a decision written here, never by resemblance.

One function for the preview and the pipeline, so the preview says the
verify that will run.
"""

import re

#: The management families: (what it is, its top-level line). A line under a
#: section (` length 0` under `line vty 0 4`) is the section's.
MANAGEMENT = (
    ("terminal lines", re.compile(r"^line (vty|con|aux) ")),
    ("logging", re.compile(r"^(no )?logging ")),
    ("SNMP", re.compile(r"^(no )?snmp-server ")),
    ("NTP", re.compile(r"^(no )?ntp ")),
    ("banners", re.compile(r"^(no )?banner ")),
    ("users", re.compile(r"^(no )?username ")),
    # Where TFTP and the SSH client leave from (the management profile, P1): what the device
    # sends from, never what it routes or how Mercury reaches it.
    ("management sources", re.compile(r"^(no )?ip (tftp|ssh) source-interface ")),
)

QUICK, FULL = "quick", "full"
_TERMINATORS = {"exit", "end", "!"}


def _sections(commands: list) -> list:
    """The distinct top-level section of every line the program sends, in order."""
    from modules.nsot.deploy import program_structure

    out = []
    for e in program_structure(list(commands or [])):
        line = (e.get("line") or "").strip()
        if not line or line in _TERMINATORS:
            continue
        chain = list(e.get("chain") or [])
        top = (chain[0] if chain else line).strip()
        if top not in out:
            out.append(top)
    return out


def family(section: str) -> str:
    """The management family *section* belongs to, or ``""``."""
    return next((name for name, rx in MANAGEMENT if rx.match(section)), "")


def classify(commands: list) -> dict:
    """``{"scope": quick|full, "why", "sections", "forwarding"}`` for one
    device's program. An empty program is FULL with nothing to classify: it
    sends nothing, and no verify runs on a device that received nothing."""
    sections = _sections(commands)
    if not sections:
        return {"scope": FULL, "why": "nothing is sent, so there is nothing to classify",
                "sections": [], "forwarding": []}
    other = [s for s in sections if not family(s)]
    if other:
        named = ", ".join(f"`{s}`" for s in other[:3]) + (
            f" and {len(other) - 3} more" if len(other) > 3 else "")
        return {"scope": FULL, "sections": sections, "forwarding": other,
                "why": (f"it changes {named}, which can affect forwarding or is not a "
                        "management section: neighbours, routes and interfaces are "
                        "watched, BGP is read again after its hold time, and each new "
                        "line is read back")}
    families = list(dict.fromkeys(family(s) for s in sections))
    return {"scope": QUICK, "sections": sections, "forwarding": [],
            "why": (f"every line is management ({', '.join(families)}): the device is read "
                    "on a new login and each new line is read back; BGP's hold time is not "
                    "waited out, because no line here can affect a session")}


def vlan_reads(commands: list) -> list:
    """The VLANs whose ``vlan <N>`` lines (bare, or heading a ``name``) *read_back* reads
    where the device keeps them (C1646): each id once, in the program's order."""
    from modules.nsot.deploy import program_leaves

    out = []
    for leaf in program_leaves(list(commands or [])):
        vlan = _vlan_judged(leaf)
        if vlan and vlan not in out:
            out.append(vlan)
    return out


def _vlan_judged(leaf):
    """The VLAN id whose ``show vlan id`` read judges *leaf*, or None: a bare ``vlan <N>``
    (the VLAN exists) and the ``name`` under one (its name). Any other line under a ``vlan``
    stanza is read from the running configuration as before."""
    from modules.nsot.vlan_read import vlan_of

    line = leaf.line.strip()
    if not leaf.chain:
        return vlan_of(line)
    if len(leaf.chain) == 1 and line.split()[:1] == ["name"] and len(line.split()) == 2:
        return vlan_of(leaf.chain[0].strip())
    return None


def read_back(commands: list, running: str, vlans: dict = None) -> dict:
    """Each new line of a program, quick or full (C732), looked for in *running*
    under its section. ``{"missing": [...], "skipped": [{line, why}], "checked": n,
    "unread": [{line, vlan, why}]}``.

    **A VLAN where the device keeps it (C1646).** A switch in VTP server or client mode keeps
    its VLANs in the VLAN database and does not print them in its running configuration, so a
    bare ``vlan <N>`` and the ``name`` under one are judged by *vlans*, ``{id: the answer to
    `show vlan id <id>`}`` (`vlan_reads` names the ids, `vlan_read.parse` reads each): the VLAN
    must be in the database, and named as the program names it. A VLAN the read shows absent,
    or under another name, is missing, naming what the read showed; a read not made or not
    understood is ``unread``, which neither passes nor fails.

    Skipped, each with its reason: a `no` line (its effect is an absence or
    the device's default, and Mode B's removals are verified on their own);
    a line in a secret's position (the device stores it transformed, `secret
    0` as `secret 9`); a banner (the device prints its own delimiter).

    **Terminal lines by member (C1541).** A device prints a `line` range as it
    pleases: a router sent `line vty 0 4` prints `line vty 0`, `line vty 1` and
    `line vty 2 4` (2026-10-22). A line under a `line <type> <a> [<b>]` stanza is read back
    for each member a..b, in whichever printed stanza covers that member, and is
    held only when EVERY member holds it; the miss names the members that lack
    it and the members no printed stanza covers. A stanza the device prints
    exactly as the program wrote it is matched there, its miss unchanged; the
    device printing one range over members the program sent one by one
    (`line vty 1` against `line vty 0 4`) is the same rule. Every other section
    is matched on its exact stanza chain, as before."""
    from modules.nsot import ifnames, platform_defaults
    # One parser of a terminal-line range, deploy's (C307's rollback reads the same headers).
    from modules.nsot.deploy import (_line_range, _pre_line_stanzas, config_leaves,
                                     program_leaves)
    from modules.redact import redact_positional

    def key(chain, line):
        return (tuple(ifnames.canonicalise_line(c).strip() for c in chain),
                " ".join(ifnames.canonicalise_line(line).split()))

    leaves = config_leaves(running or "")
    held = {key(l.chain, l.line) for l in leaves}
    # Every printed terminal-line stanza, by its range, and what each holds (the rest of
    # the chain below the stanza, and the line). A stanza printed with nothing under it
    # still covers its members (and holds nothing).
    stanzas = {rng: set() for _h, rng, _c in _pre_line_stanzas(running or "")}
    for l in leaves:
        rng = _line_range(l.chain[0].strip()) if l.chain else None
        if rng:
            stanzas.setdefault(rng, set()).add(key(l.chain[1:], l.line))

    def problems(chain, line) -> list:
        """What keeps *line* under *chain* from reading back: [] when it is held."""
        rng = _line_range(chain[0].strip()) if chain else None
        if rng is None:
            return [] if key(chain, line) in held else [""]
        kind, first, last = rng
        want = key(chain[1:], line)
        if rng in stanzas:
            # The device prints the stanza as the program wrote it (`line con 0`, an
            # unsplit `line vty 0 4`): matched there, and a miss reads as it always has.
            return [] if want in stanzas[rng] else [""]
        lacking, uncovered = [], []
        for member in range(first, last + 1):
            covering = [held_here for (k, a, b), held_here in stanzas.items()
                        if k == kind and a <= member <= b]
            if not covering:
                uncovered.append(str(member))
            elif not any(want in held_here for held_here in covering):
                lacking.append(str(member))
        out = []
        if lacking:
            out.append(f"missing on {kind} {', '.join(lacking)}")
        if uncovered:
            out.append(f"no printed stanza covers {kind} {', '.join(uncovered)}")
        return out

    from modules.nsot.vlan_read import command as vlan_command
    from modules.nsot.vlan_read import parse as vlan_parse

    missing, skipped, checked, unread = [], [], 0, []
    vlans = vlans or {}
    for leaf in program_leaves(list(commands or [])):
        line = leaf.line.strip()
        top = (leaf.chain[0] if leaf.chain else line).strip()
        shown = " > ".join(list(leaf.chain) + [line])
        vlan = None if line.startswith("no ") else _vlan_judged(leaf)
        if vlan:
            read = vlan_command(vlan)
            got = vlan_parse(vlan, vlans[vlan]) if vlan in vlans else \
                {"state": "unreadable", "why": "it was not read"}
            if got["state"] == "unreadable":
                unread.append({"line": shown, "vlan": vlan, "why": f"`{read}`: {got['why']}"})
                continue
            checked += 1
            want = line.split()[1] if leaf.chain else ""
            if got["state"] == "absent":
                missing.append(f"{shown} (`{read}`: {got['why']})")
            elif want and got["name"] != want:
                missing.append(f"{shown} (`{read}` names VLAN {vlan} {got['name']!r}, the "
                               f"program {want!r})")
            continue
        if line.startswith("no "):
            skipped.append({"line": shown, "why": "a `no` line reads back as an absence"})
        elif redact_positional(line) != line:
            skipped.append({"line": redact_positional(shown),
                            "why": "a secret the device stores in another form"})
        elif family(top) == "banners":
            skipped.append({"line": shown, "why": "a banner reads back in the device's "
                                                  "own delimiter"})
        elif platform_defaults.hidden(leaf.chain, line) and \
                problems(leaf.chain, leaf.line):
            # Printed only when not at its default (C14): absent is its default, not a miss.
            skipped.append({"line": shown, "why": platform_defaults.hidden(leaf.chain, line)})
        else:
            checked += 1
            found = problems(leaf.chain, leaf.line)
            why = [p for p in found if p]
            if found:
                missing.append(f"{shown} ({'; '.join(why)})" if why else shown)
    return {"missing": missing, "skipped": skipped, "checked": checked, "unread": unread}
