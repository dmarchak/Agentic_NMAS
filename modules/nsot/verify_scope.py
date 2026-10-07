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
each new line is read back from the device's configuration. BGP's hold-time
watch is skipped. Every other check still runs once (neighbour, route and
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
                        "watched, and BGP is read again after its hold time")}
    families = list(dict.fromkeys(family(s) for s in sections))
    return {"scope": QUICK, "sections": sections, "forwarding": [],
            "why": (f"every line is management ({', '.join(families)}): the device is read "
                    "on a new login and each new line is read back; BGP's hold time is not "
                    "waited out, because no line here can affect a session")}


def read_back(commands: list, running: str) -> dict:
    """Each new line of a QUICK program, looked for in *running* under its
    section. ``{"missing": [...], "skipped": [{line, why}], "checked": n}``.

    Skipped, each with its reason: a `no` line (its effect is an absence or
    the device's default, and Mode B's removals are verified on their own);
    a line in a secret's position (the device stores it transformed, `secret
    0` as `secret 9`); a banner (the device prints its own delimiter)."""
    from modules.nsot import ifnames
    from modules.nsot.deploy import config_leaves, program_leaves
    from modules.redact import redact_positional

    def key(chain, line):
        return (tuple(ifnames.canonicalise_line(c).strip() for c in chain),
                " ".join(ifnames.canonicalise_line(line).split()))

    held = {key(l.chain, l.line) for l in config_leaves(running or "")}
    missing, skipped, checked = [], [], 0
    for leaf in program_leaves(list(commands or [])):
        line = leaf.line.strip()
        top = (leaf.chain[0] if leaf.chain else line).strip()
        shown = " > ".join(list(leaf.chain) + [line])
        if line.startswith("no "):
            skipped.append({"line": shown, "why": "a `no` line reads back as an absence"})
        elif redact_positional(line) != line:
            skipped.append({"line": redact_positional(shown),
                            "why": "a secret the device stores in another form"})
        elif family(top) == "banners":
            skipped.append({"line": shown, "why": "a banner reads back in the device's "
                                                  "own delimiter"})
        else:
            checked += 1
            if key(leaf.chain, leaf.line) not in held:
                missing.append(shown)
    return {"missing": missing, "skipped": skipped, "checked": checked}
