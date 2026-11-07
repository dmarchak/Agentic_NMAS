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
`HPProcurveSSH` sends `no page` after `enable`, `ArubaSSH` sends `no paging` after `enable`,
`HPComwareSSH` sends `screen-length disable`, each written to the channel, not through
`send_command`).

**Comware's `enable()` is configuration mode.** netmiko 4.3.0's `HPComwareBase.enable` is
`config_mode("system-view")` ("enable mode on Comware is system-view"), so on a driver marked
``no_enable`` the session's `enable` sends nothing: Comware's `display` commands run in
user view, and system-view is never entered. Every `config_mode` call stays refused. Linux's
`enable()` is `sudo -s`, a root shell, so an Open vSwitch server's (`ovs_linux`) sends nothing
either: its reads and its one write each run under `sudo -n` (`modules/sdn/ovs.py`).

**Open vSwitch (`ovs_linux`)** is read by `modules/sdn/ovs.py`'s shapes, and its session carries
ONE write, while the server is held: the OpenFlow configuration's `ovs-vsctl` transaction
(``held_write``; `modules/sdn/ovs_config.py`). Nothing else is ever sent to it.

**`display` is a read only on a Comware session (C2530).** It is on no other list, and the
read-only allowlist (`readonly_commands`) has no `display` verb. A command that is on a capture
list and that the allowlist refuses (`foreign_refusal`) is refused on every session that is not
that list's, held or not, so a held IOS read never sends it.

The table is keyed on Netmiko DRIVERS (the `device_type` a session opens with), never on a
dialect: none of these is a dialect (`platform.DIALECTS`), so everything that parses, renders,
records or sends a configuration already refuses them (`platform.require_platform`).

**The captures** are the reads engine's own records (`modules/nsot/reads.py`: one file per run,
each device's answers masked, timed and hashed), named here per device and command by
`captures` and read back by `capture`: the input for confirming a vendor OpenFlow template.
"""

import re

#: The capture lists, each command whole. "(inferred)" in the manual's table marks a command
#: not confirmed from netmiko's own source, ntc-templates' index or a vendor document cited in
#: docs/LAB9_DISCOVERY.md section 3.
_ARISTA = ("show version", "show running-config", "show interfaces status",
           "show ip interface brief", "show lldp neighbors", "show openflow",
           "show openflow flows", "show openflow ports",
           # ZTP status (inferred: a DISA STIG for EOS 4.x names it; not in Arista's manual).
           "show zerotouch")
_PROCURVE = ("show version", "show system", "show running-config", "show interfaces brief",
             "show vlans", "show lldp info remote-device", "show openflow",
             # DHCP auto-configuration's vendor class and state (inferred: an HPE community
             # answer; not found in an HPE command reference).
             "show dhcp client vendor-specific")
#: netmiko's `aruba_os` is its ArubaOS (wireless controller) driver (`ArubaSSH`, "For use with
#: Aruba OS Controllers"); on an AOS-CX switch, whose own driver `aruba_aoscx` is not in the
#: locked netmiko 4.3.0 (C2529), it is the nearest that opens a session (its `no paging` is
#: AOS-CX's `no page` prefix, inferred). Its list is AOS-CX's.
_AOSCX = ("show version", "show system", "show running-config", "show interface brief",
          "show vlan", "show lldp neighbors-info", "show openflow",
          # ZTP status (confirmed: HPE AOS-CX 10.06 command reference, `show ztp information`).
          "show ztp information")
#: Comware 7 (an HPE 5130, 5900 or the like; `hp_comware`, netmiko's `HPComwareSSH`).
_COMWARE = ("display version", "display device manuinfo", "display current-configuration",
            "display interface brief", "display vlan brief",
            "display lldp neighbor-information list", "display openflow summary",
            "display openflow instance")

#: Open vSwitch on a Linux server (`ovs_linux`): the literal reads; the bridge reads and the
#: one held write are `modules/sdn/ovs.py`'s shapes.
_OVS = ("ovs-vsctl --version", "sudo -n ovs-vsctl show", "sudo -n ovs-vsctl list-br",
        "sudo -n ovs-vsctl --columns=target,is_connected list controller")

#: A Linux host Mercury manages services on (C2608; the SDN design (revision 4) section 9a's
#: ``linux_host`` driver, keyed here by netmiko's own driver for it, ``linux``, as every entry
#: is keyed by the driver a session opens with). Its literal reads; the unit and folder reads
#: are shapes (`_LINUX_SHAPES`), each with one token of its own shape, since the controller's
#: unit and its app folder are the host's, not Mercury's.
_LINUX_HOST = ("cat /etc/os-release", "systemctl list-units --type=service --no-pager")
#: The host's shaped reads: the controller unit's status, its User and command line, its unit
#: file with every drop-in (`systemctl cat`), one app folder under /opt, and the interpreter
#: of a virtual environment under /opt (the controller app runtime's Python, which `mercury
#: app check` targets: `modules/sdn/controller_runtime.py`; the operator, 2026-11-07).
_UNIT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}\Z")
_FOLDER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
#: The interpreter read, declared and not yet run by any read Mercury has (the controller
#: host's read, P1b, runs it and records its answer through `controller_runtime`).
PYTHON_READ = "/opt/<folder>/bin/python --version"
_PYTHON_BIN = ("python", "python3")
_LINUX_SHAPES = ("systemctl status --no-pager <unit>", "systemctl show -p User -p ExecStart <unit>",
                 "systemctl cat <unit>", "ls -la /opt/<folder>", PYTHON_READ)


def is_python_read(command) -> bool:
    """Is *command* the interpreter read (`PYTHON_READ`: `/opt/<folder>/bin/python
    --version`, or `python3`), whole, with one folder token of its shape?"""
    words = str(command or "").split()
    if len(words) != 2 or words[1] != "--version":
        return False
    parts = words[0].split("/")
    return (len(parts) == 5 and parts[0] == "" and parts[1] == "opt"
            and bool(_FOLDER.match(parts[2])) and parts[3] == "bin" and parts[4] in _PYTHON_BIN)

#: driver -> the family in words, its capture list, the command its platform-map Test asks,
#: why netmiko's `enable()` for it is never sent (``no_enable``), and the one write its
#: session may carry while the device is held (``held_write``).
DRIVERS = {
    "arista_eos":     {"family": "Arista EOS", "commands": _ARISTA},
    "hp_procurve":    {"family": "HP ProCurve / ArubaOS-Switch", "commands": _PROCURVE},
    "aruba_osswitch": {"family": "HP ProCurve / ArubaOS-Switch", "commands": _PROCURVE},
    "aruba_procurve": {"family": "HP ProCurve / ArubaOS-Switch", "commands": _PROCURVE},
    "aruba_os":       {"family": "Aruba (netmiko's ArubaOS driver; AOS-CX's list)",
                       "commands": _AOSCX},
    "hp_comware":     {"family": "HP Comware", "commands": _COMWARE,
                       "version": "display version",
                       "no_enable": "netmiko's Comware enable() is system-view, config mode"},
    "ovs_linux":      {"family": "Open vSwitch", "commands": _OVS,
                       "version": "ovs-vsctl --version",
                       "no_enable": "netmiko's Linux enable() is `sudo -s`, a root shell",
                       "held_write": "the OpenFlow configuration's ovs-vsctl transaction"},
    # C2608: the host kind's driver. Its one held write is controller management's deploy
    # channel's command, P6's (`held_write_refusal`, C2673); its files are staged over the
    # session's guarded SFTP (`connection.open_sftp`).
    "linux":          {"family": "Linux host", "commands": _LINUX_HOST,
                       "shapes": _LINUX_SHAPES,
                       "version": "cat /etc/os-release",
                       "no_enable": "netmiko's Linux enable() is `sudo -s`, a root shell",
                       "held_write": ("controller management's deploy channel (P6): "
                                      "`sudo -n /usr/local/sbin/mercury-ryu-apply`")},
}


def _linux_refusal(command) -> str:
    """"" when *command* is one of a Linux host's reads (`_LINUX_HOST`, or a `_LINUX_SHAPES`
    shape with its one token), else why. Case matters in a unit's name: read as given."""
    words = str(command or "").split()
    if " ".join(words) in _LINUX_HOST:
        return ""
    if len(words) == 4 and words[:3] == ["systemctl", "status", "--no-pager"] \
            and _UNIT.match(words[3]):
        return ""
    if len(words) == 7 and words[:6] == ["systemctl", "show", "-p", "User", "-p", "ExecStart"] \
            and _UNIT.match(words[6]):
        return ""
    if len(words) == 3 and words[:2] == ["systemctl", "cat"] and _UNIT.match(words[2]):
        return ""
    if len(words) == 3 and words[:2] == ["ls", "-la"] and words[2].startswith("/opt/") \
            and _FOLDER.match(words[2][len("/opt/"):]):
        return ""
    if is_python_read(command):
        return ""
    return (f"REFUSED: {str(command or '')[:80]!r} is not one of a Linux host's reads "
            f"({'; '.join(_LINUX_HOST + _LINUX_SHAPES)}). Nothing was sent.")

#: OpenFlow instance names on ProCurve (`show openflow instance <name>`): one token of its shape.
_INSTANCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")
#: Comware's instance id (`display openflow instance <id> [controller|listened|flow-table]`,
#: H3C S5130-HI OpenFlow Command Reference, Release 1312-6W101): digits, one token.
_COMWARE_INSTANCE = re.compile(r"[0-9]{1,4}\Z")
_COMWARE_INSTANCE_VIEWS = ("controller", "listened", "flow-table")


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
    if driver == "ovs_linux":
        # Case matters in a bridge's name: OVS's own shapes, on the command as given.
        from modules.sdn import ovs
        why = ovs.read_refusal(command)
        return why and (f"{why} This is an {DRIVERS[driver]['family']} ({driver}) session, "
                        "read only by these shapes. Nothing was sent.")
    if driver == "linux":
        return _linux_refusal(command)
    if want in allowed:
        return ""
    words = want.split()
    if (driver in ("hp_procurve", "aruba_osswitch", "aruba_procurve") and len(words) == 4
            and words[:3] == ["show", "openflow", "instance"]
            and _INSTANCE.match(str(command).split()[3])):
        return ""
    if (driver == "hp_comware" and len(words) in (4, 5)
            and words[:3] == ["display", "openflow", "instance"]
            and _COMWARE_INSTANCE.match(words[3])
            and (len(words) == 4 or words[4] in _COMWARE_INSTANCE_VIEWS)):
        return ""
    shown = str(command or "")[:80]
    return (f"REFUSED: {shown!r} is not on the {DRIVERS[driver]['family']} capture list, and a "
            f"{driver} device is read only by that list until Mercury has a driver for it: "
            f"{'; '.join(allowed)}. Nothing was sent.")


def listed_on(command, drivers=None) -> tuple:
    """The discovery drivers (of *drivers*, or of all when ``None``) whose capture list allows
    *command* whole."""
    pool = DRIVERS if drivers is None else [str(d or "").strip().lower() for d in drivers]
    return tuple(d for d in pool if d in DRIVERS and not command_refusal(d, command))


def foreign_refusal(device_type, command) -> str:
    """Why *command* is never sent on a *device_type* session that is NOT a discovery driver:
    a command a capture list allows and the read-only allowlist refuses (Comware's `display`)
    is a read on that list's sessions only, held or not. ``""`` otherwise (the session's own
    rule then decides)."""
    from modules.readonly_commands import refusal as readonly_refusal
    driver = str(device_type or "").strip().lower()
    if driver in DRIVERS or not isinstance(command, str):
        return ""
    from modules.sdn import ovs
    on = listed_on(command) or (("ovs_linux",) if not ovs.write_refusal(command) else ())
    if not on or not readonly_refusal(command):
        return ""
    families = sorted({DRIVERS[d]["family"] for d in on})
    return (f"REFUSED: {command[:80]!r} is sent only on a {' or '.join(families)} discovery "
            f"session ({', '.join(on)}), and this session's driver is "
            f"{driver or '(none)'}, whose reads are Mercury's read-only allowlist, which "
            "refuses it. Nothing was sent.")


def held_write_refusal(device_type, command) -> str:
    """``""`` when *command* is *device_type*'s one held write (``held_write``: the OVS
    OpenFlow configuration's transaction, `modules/sdn/ovs.py`), else why. The session sends
    it only while the device is held (`connection._guard_writes`)."""
    driver = str(device_type or "").strip().lower()
    if not DRIVERS.get(driver, {}).get("held_write"):
        return write_refusal(device_type, "a write") or "REFUSED: not a discovery driver."
    if driver == "linux":
        # P6 (C2673): controller management's deploy channel, its one command exactly, no
        # argument and nothing else on the line (`modules/apps/transport.py`).
        from modules.apps.channel import APPLY_COMMAND
        if command == APPLY_COMMAND:
            return ""
        from modules.inventory.management import HOST_WRITE_REFUSAL
        return HOST_WRITE_REFUSAL.format(shown=repr(str(command or "")[:80]),
                                         command=APPLY_COMMAND)
    from modules.sdn import ovs
    return ovs.write_refusal(command)


def version_command(device_type) -> str:
    """The command *device_type*'s platform-map Test asks: its family's own, else ``""``."""
    return DRIVERS.get(str(device_type or "").strip().lower(), {}).get("version", "")


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


# --------------------------------------------------------------------------- the captures

def command_slug(command) -> str:
    """*command*, normalised, as one path segment: its words joined by ``_``."""
    return "_".join(_normal(command).split())


def capture_name(device: str, command: str, run_id: str) -> str:
    """A capture's name: ``<device>/<command>/<run id>`` (the run id is its UTC start)."""
    return f"{device}/{command_slug(command)}/{run_id}"


def captures(list_name: str, device: str = "", limit: int = 200) -> dict:
    """``{"captures": [...newest first], "unreadable": [names]}``: every answer a discovery
    driver's device gave in *list_name*'s reads (of *device* when named), each named by
    `capture_name`, with when it was read, its driver, its SHA-256 and whether the answer was
    cut at the cap or archived. Read from the reads engine's records; nothing is written."""
    from modules.nsot import reads
    got = reads.runs(list_name, device=device, limit=limit)
    out = []
    for r in got["runs"]:
        for host, res in sorted((r.get("results") or {}).items()):
            if device and host != device:
                continue
            driver = (res or {}).get("driver", "")
            if not is_driver(driver):
                continue
            for a in res.get("answers") or []:
                if a.get("state") != reads.ANSWERED:
                    continue
                out.append({"name": capture_name(host, a["command"], r["id"]), "device": host,
                            "driver": driver, "family": DRIVERS[driver]["family"],
                            "command": a["command"], "run": r["id"], "at": a.get("at"),
                            "sha256": a.get("sha256", ""), "bytes": a.get("bytes", 0),
                            "cut": bool(a.get("cut")), "archived": "answer" not in a})
    return {"captures": out, "unreadable": got["unreadable"]}


def capture(list_name: str, name: str):
    """The capture *name* names (`capture_name`), with its masked ``text``, or None when
    *list_name*'s reads hold no such answer. An archived answer has ``text`` ``""``."""
    from modules.nsot import reads
    parts = str(name or "").split("/")
    if len(parts) != 3:
        return None
    host, slug, run_id = parts
    try:
        record = reads.get(list_name, run_id)
    except ValueError:                                   # not a run id's shape
        return None
    res = ((record or {}).get("results") or {}).get(host) or {}
    if not is_driver(res.get("driver", "")):
        return None
    for a in res.get("answers") or []:
        if a.get("state") == reads.ANSWERED and command_slug(a.get("command")) == slug:
            return {"name": name, "device": host, "driver": res["driver"],
                    "command": a["command"], "run": run_id, "at": a.get("at"),
                    "sha256": a.get("sha256", ""), "cut": bool(a.get("cut")),
                    "archived": "answer" not in a, "text": a.get("answer", "")}
    return None
