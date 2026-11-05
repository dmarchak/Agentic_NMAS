"""Read-only discovery of a device Mercury has no driver for (docs/LAB9_DISCOVERY.md).

A device whose Netmiko driver is one of `DRIVERS` may be READ, and nothing else, until Mercury
has a driver for its platform (docs/LAB9_SDN_GAP.md, 2.1). This is a positive allowlist of what
such a session may carry, never a list of what it may not:

- its commands are exactly its family's capture list (`DRIVERS[...]["commands"]`), each one
  whole: a command not on the list is refused, naming it, the driver and the list;
- no config, save or commit call at all, held or not (`connection._guard_writes` asks
  `write_refusal`), so a deploy, a save, a restore, a rotation or a Reload on such a device is
  refused at the session, naming the driver and what was asked;
- every answer is masked by `redact.redact_text` and then by `mask_lines`, which masks the rest
  of any line holding a credential word: `redact_text`'s positional rules are IOS's, and some of
  these platforms' credential lines are not IOS's shape (measured 2026-11-05: EOS's
  `username X privilege 15 role R secret sha512 <hash>` and AOS-CX's `password ciphertext`
  pass `redact_text` whole; ProCurve's `password manager user-name "x" sha1 "<hash>"` keeps its
  hash). Masking too much is the safe direction here: a capture is the driver build's input,
  read for its structure, never for a secret.

Paging needs no answer from any command here: each driver's own session preparation turns it
off before the first command (netmiko 4.3.0: `AristaSSH` sends `terminal length 0`,
`HPProcurveSSH` sends `no page` after `enable`, `ArubaSSH` sends `no paging` after `enable`).

The table is keyed on Netmiko DRIVERS (the `device_type` a session opens with), never on a
dialect: none of these is a dialect (`platform.DIALECTS`), so everything that parses, renders,
records or sends a configuration already refuses them (`platform.require_platform`).
"""

import re

#: The capture lists, each command whole. "(inferred)" in the manual's table marks a command
#: not confirmed from netmiko's own source or ntc-templates' index (docs/LAB9_DISCOVERY.md).
_ARISTA = ("show version", "show running-config", "show interfaces status",
           "show ip interface brief", "show lldp neighbors", "show openflow",
           "show openflow flows", "show openflow ports")
_PROCURVE = ("show version", "show system", "show running-config", "show interfaces brief",
             "show vlans", "show lldp info remote-device", "show openflow")
#: netmiko's `aruba_os` is its ArubaOS (wireless controller) driver (`ArubaSSH`, "For use with
#: Aruba OS Controllers"); on an AOS-CX switch, whose own driver `aruba_aoscx` is not in the
#: locked netmiko 4.3.0, it is the nearest that opens a session (its `no paging` is AOS-CX's
#: `no page` prefix, inferred). Its list is AOS-CX's.
_AOSCX = ("show version", "show system", "show running-config", "show interface brief",
          "show vlan", "show lldp neighbors-info", "show openflow")

#: driver -> the family in words, and its capture list.
DRIVERS = {
    "arista_eos":     {"family": "Arista EOS", "commands": _ARISTA},
    "hp_procurve":    {"family": "HP ProCurve / ArubaOS-Switch", "commands": _PROCURVE},
    "aruba_osswitch": {"family": "HP ProCurve / ArubaOS-Switch", "commands": _PROCURVE},
    "aruba_procurve": {"family": "HP ProCurve / ArubaOS-Switch", "commands": _PROCURVE},
    "aruba_os":       {"family": "Aruba (netmiko's ArubaOS driver; AOS-CX's list)",
                       "commands": _AOSCX},
}

#: OpenFlow instance names on ProCurve (`show openflow instance <name>`): one token of its shape.
_INSTANCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")


def is_driver(device_type) -> bool:
    """Is *device_type* a driver Mercury may only read with (discovery)?"""
    return str(device_type or "").strip().lower() in DRIVERS


def commands_for(device_type) -> tuple:
    """*device_type*'s capture list, or ``()`` when it is not a discovery driver."""
    entry = DRIVERS.get(str(device_type or "").strip().lower())
    return entry["commands"] if entry else ()


def _normal(command) -> str:
    return " ".join(str(command or "").split()).lower()


def command_refusal(device_type, command) -> str:
    """``""`` when *command* is on *device_type*'s capture list, whole, else why (naming the
    command, the driver and the list). ``""`` for a driver that is not a discovery driver: the
    read-only allowlist (`readonly_commands`) is that session's rule."""
    driver = str(device_type or "").strip().lower()
    if driver not in DRIVERS:
        return ""
    want = _normal(command)
    allowed = DRIVERS[driver]["commands"]
    if want in allowed:
        return ""
    words = want.split()
    if (driver in ("hp_procurve", "aruba_osswitch", "aruba_procurve") and len(words) == 4
            and words[:3] == ["show", "openflow", "instance"]
            and _INSTANCE.match(str(command).split()[3])):
        return ""
    shown = str(command or "")[:80]
    return (f"REFUSED: {shown!r} is not on the {DRIVERS[driver]['family']} capture list, and a "
            f"{driver} device is read only by that list until Mercury has a driver for it: "
            f"{'; '.join(allowed)}. Nothing was sent.")


def refusal(device_type, commands) -> str:
    """The first command of *commands* refused for *device_type*, or ``""``."""
    for c in commands or []:
        why = command_refusal(device_type, c)
        if why:
            return why
    return ""


def write_refusal(device_type, what: str) -> str:
    """Why *what* (a config, save or commit call) is never sent on a *device_type* session, or
    ``""`` when the driver is not a discovery driver."""
    driver = str(device_type or "").strip().lower()
    if driver not in DRIVERS:
        return ""
    return (f"REFUSED: {what} on a {driver} device ({DRIVERS[driver]['family']}): Mercury has no "
            "driver for this platform yet, so it is read only, by its capture list, and no "
            "deploy, save, restore, rotation or reload reaches it. Nothing was sent.")


#: A credential word, whole (not inside another word or a hyphenated one).
_CREDENTIAL_WORD = re.compile(
    r"(?i)(?<![\w-])(secret|password|passwd|passphrase|key|key-string|community|ciphertext|"
    r"plaintext|sha1|sha256|sha512|md5|hash|psk|pre-shared-key|auth-key|priv-key|"
    r"encrypted-password|shared-secret)(?![\w-])")
MASK = "<redacted:discovery>"


def mask_lines(text: str) -> str:
    """*text* with the rest of every line holding a credential word masked, after that word.
    Only ever given text `redact.redact_text` has masked (`masked`)."""
    out = []
    for line in (text or "").split("\n"):
        m = _CREDENTIAL_WORD.search(line)
        out.append(line[:m.end()] + " " + MASK if m else line)
    return "\n".join(out)


def masked(text: str, values: dict, device_type) -> str:
    """A device's answer as it leaves the reads engine: `redact.redact_text`, and on a
    discovery driver's session `mask_lines` after it."""
    from modules.redact import redact_text
    out = redact_text(text, values)
    return mask_lines(out) if is_driver(device_type) else out
