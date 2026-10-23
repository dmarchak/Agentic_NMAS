"""Platform console profiles: versioned data that says how a platform's console reads.

docs/LAB9_PLAN.md section 8, piece 3 (out-of-band ZTP for legacy devices): a profile names, per
platform, the prompt patterns by state (what the session state machine, console_session.py,
recognises), the lines that never decide a state (a syslog message arriving mid-session), the
factory-blank check (a read and how to find the startup configuration's size in its output),
the read that shows the base MAC, and the kick-start's template lines (console_survey.py renders
them). It is DATA, shipped beside this module (`console_profiles/<name>.json`), approved like a
template: the loader validates every field, refuses an unknown key, and returns the profile with
its sha256 over a canonical JSON form, the hash a later approval binds to.

Nothing here touches a device: the commands a profile names are checked to be reads
(modules/readonly_commands.py), and a template line holding a credential word is refused (the
one-time credential never crosses the console; it is only in the fetched bootstrap).
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass

from modules import readonly_commands

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "console_profiles")

#: The states a profile's prompt patterns name. Every profile names every one.
BOOT = "boot"
SETUP_DIALOG = "setup_dialog"
PRESS_RETURN = "press_return"
USER_EXEC = "user_exec"
PRIV_EXEC = "priv_exec"
CONFIG = "config"
LOGIN_USER = "login_user"
LOGIN_PASSWORD = "login_password"
MORE = "more"
#: IOS's one question a kick-start's copy answers, ``Destination filename [running-config]?``
#: (C1594), with RETURN. Any other question is a partial line no pattern names, which stops the
#: session once it has been quiet (console_session's unknown prompt).
COPY_DESTINATION = "copy_destination"
#: The order a line is classified in, first match wins: a config prompt (`Switch(config)#`) also
#: matches the privileged prompt's pattern, and a pager or a login prompt must never read as
#: anything else.
PROMPT_STATES = (MORE, LOGIN_PASSWORD, LOGIN_USER, SETUP_DIALOG, PRESS_RETURN, COPY_DESTINATION,
                 CONFIG, PRIV_EXEC, USER_EXEC, BOOT)

#: The parameter shapes a kick-start template may declare (console_survey.SHAPES checks them).
#: ``ipv4_address`` and ``ipv4_mask`` carry the static path's address, mask and gateway (C1592):
#: out-of-band ZTP is IPv4 only (C1245), and an IPv6 value is refused by name.
PARAM_SHAPES = ("interface", "vlan", "hostname", "ipv4_address", "ipv4_mask")
#: IOS's refusals, one per form (console_session.refusal): no profile's ``ignore`` pattern may
#: match one, or a refused line would read as a message and the kick-start would type on past
#: it (C1593).
REFUSAL_EXAMPLES = ("% Invalid input detected at '^' marker.", "% Incomplete command.",
                    "% Ambiguous command:  \"sh\"",
                    "% Unknown command or computer name, or unable to find computer address",
                    "%Error opening tftp://server/device.cfg (Timed out)",
                    "% Bad IP address or host name", "%Warning: an unmeasured warning")
#: A template's placeholder: `{name}`, a declared parameter's name.
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
#: Words no kick-start line may hold: the credential never crosses the console.
CREDENTIAL_WORDS = re.compile(r"\b(username|password|secret|key)\b", re.I)
#: The console timeout is the renderer's, always finite (C1544): never written in a template.
TIMEOUT_WORDS = re.compile(r"^\s*(line\s+con|exec-timeout)\b", re.I)
KICKSTART_FIRST = "configure terminal"
KICKSTART_LAST = "end"

TOP_KEYS = ("name", "platform", "version", "description", "prompts", "ignore", "blank_check",
            "mac", "kickstart")
BLANK_KEYS = ("command", "startup_entry")
MAC_KEYS = ("command", "pattern")
KICKSTART_KEYS = ("params", "lines")
PROFILE_NAME = re.compile(r"[a-z0-9_]{1,64}")


class ProfileError(ValueError):
    """A profile refused; the text names the field and what was wrong with it."""


@dataclass(frozen=True)
class Profile:
    name: str
    platform: str
    version: int
    sha256: str
    data: dict
    prompts: dict          # state -> tuple of compiled patterns
    ignore: tuple          # compiled patterns of lines that never decide a state
    startup_entry: object  # compiled; group 1 is the startup configuration's size in bytes
    mac_pattern: object    # compiled; group 1 is the base MAC

    @property
    def blank_command(self) -> str:
        return self.data["blank_check"]["command"]

    @property
    def mac_command(self) -> str:
        return self.data["mac"]["command"]

    @property
    def kickstart_params(self) -> dict:
        return dict(self.data["kickstart"]["params"])

    @property
    def kickstart_lines(self) -> tuple:
        return tuple(self.data["kickstart"]["lines"])


def canonical(data: dict) -> bytes:
    """The bytes a profile's hash is taken over: sorted keys, no spaces, ASCII."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _keys(obj, keys: tuple, where: str) -> None:
    if not isinstance(obj, dict):
        raise ProfileError(f"{where} is {type(obj).__name__}, not an object")
    unknown = sorted(set(obj) - set(keys))
    missing = [k for k in keys if k not in obj]
    if unknown:
        raise ProfileError(f"{where} has unknown key(s) {unknown}; known: {list(keys)}")
    if missing:
        raise ProfileError(f"{where} lacks {missing}")


def _text(value, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"{where} is {value!r}, not a non-empty string")
    if any(not " " <= c <= "~" for c in value):
        raise ProfileError(f"{where} {value!r} holds a character outside printable ASCII")
    return value


def _pattern(value, where: str, groups: int = 0):
    _text(value, where)
    try:
        compiled = re.compile(value)
    except re.error as e:
        raise ProfileError(f"{where} {value!r} is not a regular expression: {e}") from None
    if compiled.groups != groups:
        raise ProfileError(f"{where} {value!r} has {compiled.groups} group(s), {groups} expected")
    return compiled


def _patterns(value, where: str, empty_ok: bool = False) -> tuple:
    if not isinstance(value, list) or (not value and not empty_ok):
        raise ProfileError(f"{where} is {value!r}, not a "
                           + ("list" if empty_ok else "non-empty list") + " of patterns")
    return tuple(_pattern(v, f"{where}[{i}]") for i, v in enumerate(value))


def _read_command(value, where: str) -> str:
    _text(value, where)
    why = readonly_commands.refusal(value)
    if why:
        raise ProfileError(f"{where} {value!r} is not a read: {why}")
    return value


def check_template(lines, params: dict) -> None:
    """A kick-start template's lines: printable ASCII, `configure terminal` first and `end`
    last, every placeholder a declared parameter, no other brace, no credential word, and no
    console timeout of its own (the renderer always adds the finite one)."""
    if not isinstance(lines, list) or len(lines) < 2:
        raise ProfileError(f"kickstart.lines is {lines!r}, not a list of at least two lines")
    for i, line in enumerate(lines):
        where = f"kickstart.lines[{i}]"
        _text(line, where)
        word = CREDENTIAL_WORDS.search(line)
        if word:
            raise ProfileError(f"{where} {line!r} holds {word.group(1)!r}: no credential "
                               "crosses the console")
        if TIMEOUT_WORDS.search(line):
            raise ProfileError(f"{where} {line!r} sets the console line: the renderer adds its "
                               "finite timeout itself")
        for name in PLACEHOLDER.findall(line):
            if name not in params:
                raise ProfileError(f"{where} {line!r} names {{{name}}}, not a declared "
                                   f"parameter ({sorted(params)})")
        if "{" in PLACEHOLDER.sub("", line) or "}" in PLACEHOLDER.sub("", line):
            raise ProfileError(f"{where} {line!r} holds a brace that is not a placeholder")
    if lines[0] != KICKSTART_FIRST or lines[-1] != KICKSTART_LAST:
        raise ProfileError(f"kickstart.lines runs {lines[0]!r} to {lines[-1]!r}; it must run "
                           f"{KICKSTART_FIRST!r} to {KICKSTART_LAST!r}")


def validate(data, expected_name: str = None) -> Profile:
    """The Profile for *data* (a parsed profile), or ProfileError naming the first fault."""
    _keys(data, TOP_KEYS, "the profile")
    name = _text(data["name"], "name")
    if not PROFILE_NAME.fullmatch(name):
        raise ProfileError(f"name {name!r} must match {PROFILE_NAME.pattern}")
    if expected_name is not None and name != expected_name:
        raise ProfileError(f"name {name!r} is not the file's, {expected_name!r}")
    platform = _text(data["platform"], "platform")
    version = data["version"]
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ProfileError(f"version {version!r} is not a positive integer")
    _text(data["description"], "description")
    _keys(data["prompts"], PROMPT_STATES, "prompts")
    prompts = {s: _patterns(data["prompts"][s], f"prompts.{s}") for s in PROMPT_STATES}
    ignore = _patterns(data["ignore"], "ignore", empty_ok=True)
    for i, pattern in enumerate(ignore):
        hidden = [r for r in REFUSAL_EXAMPLES if pattern.search(r)]
        if hidden:
            raise ProfileError(f"ignore[{i}] {pattern.pattern!r} matches IOS's refusal "
                               f"{hidden[0]!r}: a refused line would read as a message (C1593)")
    _keys(data["blank_check"], BLANK_KEYS, "blank_check")
    _read_command(data["blank_check"]["command"], "blank_check.command")
    startup = _pattern(data["blank_check"]["startup_entry"], "blank_check.startup_entry", 1)
    _keys(data["mac"], MAC_KEYS, "mac")
    _read_command(data["mac"]["command"], "mac.command")
    mac = _pattern(data["mac"]["pattern"], "mac.pattern", 1)
    _keys(data["kickstart"], KICKSTART_KEYS, "kickstart")
    params = data["kickstart"]["params"]
    if not isinstance(params, dict):
        raise ProfileError(f"kickstart.params is {params!r}, not an object")
    for pname, shape in params.items():
        if not PLACEHOLDER.fullmatch("{" + str(pname) + "}"):
            raise ProfileError(f"kickstart.params name {pname!r} must match [a-z_]+")
        if shape not in PARAM_SHAPES:
            raise ProfileError(f"kickstart.params.{pname} shape {shape!r} is not one of "
                               f"{list(PARAM_SHAPES)}")
    check_template(data["kickstart"]["lines"], params)
    return Profile(name=name, platform=platform, version=version,
                   sha256=hashlib.sha256(canonical(data)).hexdigest(), data=data,
                   prompts=prompts, ignore=ignore, startup_entry=startup, mac_pattern=mac)


def load_text(text: str, expected_name: str = None) -> Profile:
    """A profile from its JSON text."""
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ProfileError(f"the profile is not JSON: {e}") from None
    return validate(data, expected_name)


def load(name: str, folder: str = HERE) -> Profile:
    """The shipped profile *name* (`console_profiles/<name>.json`)."""
    if not isinstance(name, str) or not PROFILE_NAME.fullmatch(name):
        raise ProfileError(f"profile name {name!r} must match {PROFILE_NAME.pattern}")
    path = os.path.join(folder, name + ".json")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        raise ProfileError(f"profile {name!r} could not be read: {e}") from None
    return load_text(text, expected_name=name)


def shipped(folder: str = HERE) -> list:
    """The names of the shipped profiles, sorted."""
    return sorted(f[:-5] for f in os.listdir(folder) if f.endswith(".json"))
