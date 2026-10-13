"""Lines a device holds without printing them, when they are at its default (register C14).

A device's running configuration leaves out a setting at its default value: `ip sla 1` sent
with ` frequency 60` prints no frequency line (vIOS, measured on s2 for C713, 2026-10-12). Every
comparison of what Mercury means against what the device prints meets this: the deploy's diff
would send the line on every deploy and never converge, verify's read-back would call it
missing, and Intent-Match would call intent ahead of a device that holds exactly it. ONE table
here, and each comparison asks it:

- `deploy.classify_diff`: a target line at its default with no counterpart on the device is
  satisfied (a counterpart printing another value is still a replace, so a return to the
  default is never lost);
- `verify_scope.read_back`: such a line is skipped, with this table's reason;
- `roundtrip.canonical_lines` (Intent-Match, `change_rows`, `canonical_diff`) and
  `ip_sla_policy.compare`: such lines are left out of both sides.

**A rule joins by measurement, or by the vendor's documented default with the measurement
named as owed; never by resemblance.** The syntax is IOS's (both of Mercury's dialects); a
line in another dialect's syntax matches no rule.
"""

import re

#: The IP SLA operation's frequency when none is set (seconds): the device's own value.
DEVICE_DEFAULT_FREQUENCY = 60

#: ``(section, line, reason)``: a line matching *line* (stripped), under a top-level section
#: matching *section*, at any depth (IOS-XE nests `frequency` under `icmp-echo`, vIOS does
#: not), is the device's default and is not printed.
HIDDEN = (
    (re.compile(r"^ip sla \d+$"), re.compile(rf"^frequency {DEVICE_DEFAULT_FREQUENCY}$"),
     f"an IP SLA operation's frequency at its default ({DEVICE_DEFAULT_FREQUENCY} s) is not "
     "printed (measured on vIOS, s2, C713; IOS-XE's documented default, its print owed a "
     "measurement)"),
)


def hidden(chain, line: str) -> str:
    """The reason *line* under *chain* (its parent lines, outermost first) is a default the
    device does not print, or ""."""
    top = (chain[0] if chain else "").strip()
    text = (line or "").strip()
    for section, pattern, reason in HIDDEN:
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
