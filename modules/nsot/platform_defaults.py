"""Lines a device holds without printing them, when they are at its default (register C14).

A device's running configuration leaves out a setting at its default value: `ip sla 1` sent
with ` frequency 60` prints no frequency line (vIOS, measured on s2 for C713, 2026-10-12). Every
comparison of what Mercury means against what the device prints meets this: the deploy's diff
would send the line on every deploy and never converge, verify's read-back would call it
missing, and Intent-Match would call intent ahead of a device that holds exactly it. ONE table
here, and each comparison asks it:

- `deploy.classify_diff`, and through it `merge_diff` and so the program `merge_commands`
  sends: a target line at its default, in a section the device holds, with no counterpart
  there, is satisfied and never sent (a counterpart printing another value is still a
  replace, so a return to the default is never lost; a section the device does not hold yet
  is created with the line, since nothing there is at any default);
- `verify_scope.read_back`: such a line is skipped, with this table's reason;
- `roundtrip.canonical_lines` (`change_rows`, `canonical_diff`), `roundtrip.compare` (the
  render report Intent-Match reads, C1401) and `ip_sla_policy.compare`: such lines are left
  out of both sides.

**A rule joins by measurement, or by the vendor's documented default with the measurement
named as owed; never by resemblance.** The syntax is IOS's (both of Mercury's dialects); a
line in another dialect's syntax matches no rule.
"""

import re

#: The IP SLA operation's frequency when none is set (seconds): the device's own value.
DEVICE_DEFAULT_FREQUENCY = 60

#: ``(section, line, depth, reason)``: a line matching *line* (stripped), under a top-level
#: section matching *section*, is the device's default and is not printed. *depth* is the
#: number of parents the line has, or None for any depth (IOS-XE nests `frequency` under
#: `icmp-echo`, vIOS does not).
HIDDEN = (
    (re.compile(r"^ip sla \d+$"), re.compile(rf"^frequency {DEVICE_DEFAULT_FREQUENCY}$"), None,
     f"an IP SLA operation's frequency at its default ({DEVICE_DEFAULT_FREQUENCY} s) is not "
     "printed (measured on vIOS, s2, C713; IOS-XE's documented default, its print owed a "
     "measurement)"),
    # C1401: an interface that is up prints no `no shutdown`; only `shutdown` is ever printed,
    # so intent bringing an interface up never converged and every plan sent it again. A
    # direct child of the interface only: a `no shutdown` nested deeper (a VRRP group's) is
    # unmeasured and stays compared.
    (re.compile(r"^interface \S+"), re.compile(r"^no shutdown$"), 1,
     "an interface that is up prints no `no shutdown` line, only a shut one prints "
     "`shutdown` (measured on IOS-XE 17.06 after a deploy that sent it, C1401; every up "
     "interface in the fleet's IOS and IOS-XE captures prints neither)"),
)


#: The opposite direction (Restore or keep's prerequisite, docs/RESTORE_OR_KEEP_DESIGN.md item 1):
#: lines an image PRINTS when nothing sets them. *section* matches
#: the line's container path as `roundtrip._sections` keys it ("" for a top-level line), *line*
#: the line exactly. Left out of the DEVICE's side of Intent-Match only, where intent lacks the
#: line (`roundtrip.compare`), so a first boot from a startup file reads at intent; never in a
#: deploy's program or verify's read-back (unlike `HIDDEN`, whose target lines a deploy never
#: sends: a printed default there would keep intent's `no mop enabled` from ever reaching a
#: device printing `mop enabled`). A changed value (`mop enabled`) is no rule's line and still
#: differs. Measured 2026-11-28 on the C8000v (IOS-XE 17), identical on
#: three routers' goldens after their first boot from a startup file (C4300, C1538).
_TOP = re.compile(r"^$")
_INTERFACE = re.compile(r"^interface \S+$")
_C8000V = ("printed by the C8000v image when nothing sets it (measured 2026-11-28 on three "
           "routers' goldens after their first boot from a startup file, C4300)")
#: ``(dialect, section, line, reason)``: a rule holds only for the dialect it was measured on
#: (an IOS device printing `spanning-tree extend system-id` set it, and it stays compared).
#: NOT here: `license boot level …`, which the review of the first slice found is configuration
#: (an image's install step can set it, and it is kept as configuration by the operator's
#: 2026-10-09 ruling), so a level a person sets is a departure intent must state.
PRINTED = (
    ("cisco_iosxe", _TOP, "spanning-tree extend system-id", _C8000V),
    ("cisco_iosxe", _TOP, "mgcp behavior rsip-range tgcp-only", _C8000V),
    ("cisco_iosxe", _TOP, "mgcp behavior comedia-role none", _C8000V),
    ("cisco_iosxe", _TOP, "mgcp behavior comedia-check-media-src disable", _C8000V),
    ("cisco_iosxe", _TOP, "mgcp behavior comedia-sdp-force disable", _C8000V),
    ("cisco_iosxe", _TOP, "mgcp profile default", _C8000V),
    ("cisco_iosxe", _INTERFACE, "no mop enabled", _C8000V),
    ("cisco_iosxe", _INTERFACE, "no mop sysid", _C8000V),
)


def printed(section: str, line: str, platform: str = "") -> str:
    """The reason *line* under the container path *section* (`roundtrip._sections`'s key, ""
    for a top-level line) is a default an image of *platform* (a dialect) prints when nothing
    sets it, or "". No platform, no rule: a caller that cannot name the dialect compares all."""
    text = (line or "").strip()
    for dialect, where, exactly, reason in PRINTED:
        if dialect == (platform or "").strip() and text == exactly and where.match(section or ""):
            return reason
    return ""


def hidden(chain, line: str) -> str:
    """The reason *line* under *chain* (its parent lines, outermost first) is a default the
    device does not print, or ""."""
    top = (chain[0] if chain else "").strip()
    text = (line or "").strip()
    for section, pattern, depth, reason in HIDDEN:
        if depth is not None and len(chain or ()) != depth:
            continue
        if chain and section.match(top) and pattern.match(text):
            return reason
    return ""


def strip(text: str) -> str:
    """*text* (a configuration) without the lines `hidden` names. Indentation decides each
    line's parents, as the device prints them."""
    out, stack = [], []
    for raw in (text or "").splitlines():
        if not raw.strip():
            out.append(raw)
            continue
        depth = len(raw) - len(raw.lstrip(" "))
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if not hidden([s for _d, s in stack], raw):
            out.append(raw)
        stack.append((depth, raw.strip()))
    return "\n".join(out) + ("\n" if (text or "").endswith("\n") else "")
