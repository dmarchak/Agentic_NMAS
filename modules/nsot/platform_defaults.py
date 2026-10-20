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
