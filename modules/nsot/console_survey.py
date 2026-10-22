"""The console survey's reading and the kick-start's lines (out-of-band ZTP, O3).

docs/LAB9_PLAN.md section 8, piece 4 and the operator's additions of 2026-10-22. Pure: it reads
text a console session already received and renders lines a session will type; it touches
nothing.

- `blank_check`: the factory-blank check's output (`dir nvram:` on IOS) read for the startup
  configuration's size. Blank ONLY when the startup-config entry is present and 0 bytes; an
  absent entry, two entries, or output that does not parse is UNKNOWN, never blank.
- `survey`: the verdict. **A console found signed in** (a `>`, `#` or config prompt at attach,
  before any line was typed) **is not factory-blank as found** (the operator's rule: a device
  was left at `Switch#` on 2026-10-22): the result says `found_signed_in` and why, and is not
  blank whatever nvram says, so the operation never proceeds silently from it.
- `base_mac`: the MAC the device will DHCP from, from the profile's named read (`show
  version`'s "Base ethernet MAC Address"); not found is None, said so.
- `render_kickstart`: the exact lines typed, from the profile's template with only its
  declared parameters substituted, each checked to its shape; ALWAYS a finite console timeout
  under `line con 0` (C1544's class); never a credential; printable ASCII only.
"""

import re
from dataclasses import dataclass

from modules.nsot import console_profiles as P

#: The states at attach that say the console was signed in, and those that say it was not.
SIGNED_IN = (P.USER_EXEC, P.PRIV_EXEC, P.CONFIG)
NOT_SIGNED_IN = (P.PRESS_RETURN, P.SETUP_DIALOG)
#: A login prompt at attach: the device holds a configuration that asks for one.
LOGIN = (P.LOGIN_USER, P.LOGIN_PASSWORD)

#: Each declared parameter's shape, matched whole.
SHAPES = {
    "interface": re.compile(r"[A-Za-z][A-Za-z-]{0,30}[0-9]{1,4}(?:/[0-9]{1,4}){0,3}"
                            r"(?:\.[0-9]{1,5})?"),
    "vlan": re.compile(r"[1-9][0-9]{0,3}"),
    "hostname": re.compile(r"[A-Za-z](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"),
}
VLAN_MAX = 4094
#: The console's exec-timeout in minutes: the operator's default, and IOS's range (0 is never).
EXEC_TIMEOUT_MINUTES = 15
EXEC_TIMEOUT_MAX = 35791
CONSOLE_LINE = "line con 0"


@dataclass(frozen=True)
class BlankCheck:
    blank: object          # True, False, or None (unknown)
    size: object           # the startup configuration's bytes, or None
    reason: str


@dataclass(frozen=True)
class Found:
    value: object          # what was found, or None
    reason: str


@dataclass(frozen=True)
class SurveyResult:
    blank: object          # True only when factory-blank; False; None when unknown
    found_signed_in: bool
    found_state: object
    startup_config_bytes: object
    reasons: tuple


def blank_check(text: str, profile) -> BlankCheck:
    """The startup configuration's size from the blank check's output *text*."""
    lines = text.splitlines() if text else []
    sizes = [int(m.group(1)) for m in (profile.startup_entry.search(line) for line in lines) if m]
    command = profile.blank_command
    if not sizes:
        return BlankCheck(None, None, f"no startup-config entry in {command!r}'s output, so "
                                      "blank is unknown")
    if len(sizes) > 1:
        return BlankCheck(None, None, f"{len(sizes)} startup-config entries in {command!r}'s "
                                      f"output ({sizes}), so blank is unknown")
    size = sizes[0]
    if size == 0:
        return BlankCheck(True, 0, f"startup-config is 0 bytes in {command!r}'s output")
    return BlankCheck(False, size, f"startup-config is {size} bytes in {command!r}'s output: "
                                   "the device holds a saved configuration")


def survey(found_state, nvram_text: str, profile) -> SurveyResult:
    """The survey's verdict from the state found at attach (console_session's `attach_state`)
    and the blank check's output."""
    check = blank_check(nvram_text, profile)
    reasons = [check.reason]
    signed_in = found_state in SIGNED_IN
    if signed_in:
        blank = False
        reasons.insert(0, f"not factory-blank as found: the console was signed in at "
                          f"{found_state} before any line was typed")
    elif found_state in LOGIN:
        blank = False
        reasons.insert(0, f"not factory-blank as found: the console asked for a login "
                          f"({found_state}) at attach")
    elif found_state in NOT_SIGNED_IN:
        blank = check.blank
    else:
        blank = None
        reasons.insert(0, f"the state at attach is {found_state!r}, not one this survey can "
                          "judge, so blank is unknown")
    return SurveyResult(blank=blank, found_signed_in=signed_in, found_state=found_state,
                        startup_config_bytes=check.size, reasons=tuple(reasons))


def normal_mac(text: str) -> str:
    """*text* (`aabb.ccdd.eeff`, `aa:bb:...` or `aa-bb-...`) as lower-case colon pairs."""
    digits = re.sub(r"[.:-]", "", text).lower()
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2))


def base_mac(text: str, profile) -> Found:
    """The base MAC from the profile's MAC read's output *text*; None when it is not there."""
    for line in text.splitlines() if text else []:
        m = profile.mac_pattern.search(line)
        if m:
            return Found(normal_mac(m.group(1)), f"from {profile.mac_command!r}: {line.strip()}")
    return Found(None, f"no base MAC in {profile.mac_command!r}'s output: the MAC is unknown")


def check_param(name: str, shape: str, value) -> str:
    """*value* as typed, when it has *shape*; else ValueError naming the parameter."""
    text = str(value) if isinstance(value, int) and not isinstance(value, bool) else value
    if not isinstance(text, str) or not SHAPES[shape].fullmatch(text):
        raise ValueError(f"parameter {name} {value!r} is not a valid {shape} (it must match "
                         f"{SHAPES[shape].pattern})")
    if shape == "vlan" and int(text) > VLAN_MAX:
        raise ValueError(f"parameter {name} {value!r} is over VLAN {VLAN_MAX}")
    return text


def check_line(line: str) -> str:
    """*line* when it may be typed: printable ASCII and no credential word; else ValueError."""
    if not line or any(not " " <= c <= "~" for c in line):
        raise ValueError(f"kick-start line {line!r} is empty or holds a character outside "
                         "printable ASCII")
    word = P.CREDENTIAL_WORDS.search(line)
    if word:
        raise ValueError(f"kick-start line {line!r} holds {word.group(1)!r}: no credential "
                         "crosses the console")
    return line


def render_kickstart(profile, params: dict, exec_timeout_minutes: int = EXEC_TIMEOUT_MINUTES
                     ) -> tuple:
    """The exact lines the kick-start types, in order."""
    declared = profile.kickstart_params
    given = dict(params or {})
    unknown = sorted(set(given) - set(declared))
    missing = sorted(set(declared) - set(given))
    if unknown:
        raise ValueError(f"parameter(s) {unknown} are not declared by profile {profile.name} "
                         f"({sorted(declared)})")
    if missing:
        raise ValueError(f"parameter(s) {missing} are declared by profile {profile.name} and "
                         "not given")
    values = {n: check_param(n, declared[n], v) for n, v in given.items()}
    minutes = exec_timeout_minutes
    if not isinstance(minutes, int) or isinstance(minutes, bool) \
            or not 1 <= minutes <= EXEC_TIMEOUT_MAX:
        raise ValueError(f"exec-timeout {minutes!r} minutes is not a finite timeout from 1 to "
                         f"{EXEC_TIMEOUT_MAX}")
    template = list(profile.kickstart_lines)
    P.check_template(template, declared)
    lines = [P.PLACEHOLDER.sub(lambda m: values[m.group(1)], t) for t in template]
    # The finite console timeout goes just before the template's last line, its `end`.
    lines = lines[:-1] + [CONSOLE_LINE, f" exec-timeout {minutes} 0"] + lines[-1:]
    return tuple(check_line(line) for line in lines)
