"""What a session to an Open vSwitch server may carry (docs/LAB9_OPENFLOW.md, section 2).

An OVS server is opened with netmiko's `ovs_linux` (`OvsLinuxSSH`, which is `LinuxSSH` with
nothing added) and is a discovery driver (`modules/discovery.py`) with ONE write: the OpenFlow
configuration's `ovs-vsctl` transaction (`modules/sdn/ovs_config.py`), sent only while the
server is held. Everything here is a positive allowlist of whole command shapes:

- **reads** (`read_refusal`; every form: `read_forms`): `ovs-vsctl --version`, and the
  `sudo -n ovs-vsctl` and `sudo -n ovs-ofctl -O OpenFlow13` verbs that only print (the database
  as `show` draws it, a table or one record of it, one column of a bridge, a bridge's flows,
  ports and tables), each argument one token of its shape, from a fixed set or one interface
  name. No option a caller chooses (`--db`, `--columns` of its own), no second command;
- **the write** (`write_refusal`): `sudo -n ovs-vsctl` followed by commands separated by a lone
  `--`, which ovs-vsctl runs as one atomic OVSDB transaction (ovs-vsctl(8): "any number of
  commands in a single run, implemented as a single atomic transaction against the database"),
  each command one of `WRITE_SHAPES` with token-shaped arguments. No shell metacharacter, no
  quote, no other program.

`sudo -n` never prompts: the server's sudoers grants the login `ovs-vsctl` and `ovs-ofctl`
without a password, or the command fails with sudo's own words and nothing is changed. netmiko's
Linux `enable()` is `sudo -s`, a root shell, so it is never sent (`discovery.DRIVERS`,
``no_enable``).

**A near miss is refused naming the listed form, never rewritten** (C2991, `listed_form`): a
person who types `ovs-vsctl show`, `sudo ovs-vsctl show` or `ovs-ofctl dump-flows <bridge>` is
told the form on the list (`sudo -n ovs-vsctl show`; `sudo -n ovs-ofctl -O OpenFlow13
dump-flows <bridge>`). What is sent is always the text a person saw and asked for.
"""

import ipaddress
import re

#: A bridge or port name: a Linux interface name (at most 15 characters).
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,14}\Z")
#: OVSDB's Bridge `protocols` values (ovs-vswitchd.conf.db(5), Bridge table).
PROTOCOLS = ("OpenFlow10", "OpenFlow11", "OpenFlow12", "OpenFlow13", "OpenFlow14", "OpenFlow15")
FAIL_MODES = ("secure", "standalone")
SUDO_VSCTL = ("sudo", "-n", "ovs-vsctl")
SUDO_OFCTL = ("sudo", "-n", "ovs-ofctl")
_HEX16 = re.compile(r"[0-9a-f]{16}\Z")
_UNSAFE = set(";|&$`<>\\'\"(){}*?!#~\n\r\t")

#: Reads with no argument, whole.
READS = ("ovs-vsctl --version", "sudo -n ovs-vsctl show", "sudo -n ovs-vsctl list-br",
         "sudo -n ovs-vsctl --columns=target,is_connected list controller",
         # The Controller table whole (C2991). Its records are named by UUID, not by an
         # interface name, so none is asked for by name.
         "sudo -n ovs-vsctl list controller")
#: A bridge's columns read whole by `get bridge <bridge> <column>` (ovs-vswitchd.conf.db(5),
#: Bridge table): a fixed set, never a column a caller names.
BRIDGE_COLUMNS = ("protocols", "datapath_id", "fail_mode", "other_config")
#: The tables `list <table> [<name>]` prints whole, or one record of by its name (ovs-vsctl(8),
#: Database Commands: `list` "lists the data in each specified record", all of them when none
#: is given): a fixed set, each with the token its record's name is.
LIST_TABLES = (("bridge", "<bridge>"), ("port", "<port>"), ("interface", "<port>"))
#: `sudo -n ovs-vsctl` reads (`<bridge>` and `<port>` one NAME token each).
VSCTL_READS = (
    (("get-controller", "<bridge>"), ("get-fail-mode", "<bridge>"), ("list-ports", "<bridge>"))
    + tuple(("get", "bridge", "<bridge>", column) for column in BRIDGE_COLUMNS)
    + (("--if-exists", "get", "bridge", "<bridge>", "other-config:datapath-id"),
       # A port's requested and given OpenFlow port number (C2603).
       ("get", "interface", "<port>", "ofport_request"),
       ("get", "interface", "<port>", "ofport"))
    + tuple(shape for table, name in LIST_TABLES
            for shape in (("list", table), ("list", table, name))))
#: `sudo -n ovs-ofctl -O OpenFlow13 <verb> <bridge>`: the verbs that only print (ovs-ofctl(8),
#: OpenFlow Switch Management Commands): the switch's features and ports (`show`), its flow
#: entries, its ports' counters, its ports' descriptions and its tables' statistics. Never a
#: verb that changes flows, ports or tables (`add-flow`, `mod-flows`, `del-flows`, `mod-port`).
OFCTL_VERBS = ("show", "dump-flows", "dump-ports", "dump-ports-desc", "dump-tables")
OFCTL_READS = tuple(("-O", "OpenFlow13", verb, "<bridge>") for verb in OFCTL_VERBS)
#: `ofport_request`'s range (ovs-vswitchd.conf.db(5), Interface table).
OFPORT_MIN, OFPORT_MAX = 1, 65279


def _safe(command) -> bool:
    """Printable ASCII only (space to `~`), and no shell metacharacter or quote: a character
    outside it is never one of a shape's own words, and whitespace that is not a plain space
    (a no-break space, a form feed) would be sent as typed while the check read it as a
    space."""
    return (isinstance(command, str) and all(" " <= ch <= "~" for ch in command)
            and not (set(command) & _UNSAFE))


def read_forms() -> tuple:
    """Every OVS read, as its form is written: the whole commands, then each shape with its
    token's place named (`<bridge>`, `<port>`)."""
    return (READS + tuple(" ".join(SUDO_VSCTL + shape) for shape in VSCTL_READS)
            + tuple(" ".join(SUDO_OFCTL + shape) for shape in OFCTL_READS))


def _fits(words: list, shape: tuple) -> bool:
    if len(words) != len(shape):
        return False
    for w, s in zip(words, shape):
        if s in ("<bridge>", "<port>"):
            if not NAME.match(w):
                return False
        elif w != s:
            return False
    return True


def _is_read(words: list) -> bool:
    if " ".join(words) in READS:
        return True
    if tuple(words[:3]) == SUDO_VSCTL and any(_fits(words[3:], s) for s in VSCTL_READS):
        return True
    return tuple(words[:3]) == SUDO_OFCTL and any(_fits(words[3:], s) for s in OFCTL_READS)


def listed_form(command) -> str:
    """The listed read *command* is a near miss of, or ``""``: the same words under
    `sudo -n` (typed bare, or under `sudo` alone), and for `ovs-ofctl` with its OpenFlow
    version named when it was left out. Only for a refusal's words: nothing is rewritten, and
    a command that is itself a read, or a near miss of none, answers ``""``."""
    if not _safe(command):
        return ""
    words = command.split()
    if _is_read(words):
        return ""
    bare = words[1:] if words[:1] == ["sudo"] else words
    bare = bare[1:] if words[:1] == ["sudo"] and bare[:1] == ["-n"] else bare
    if bare[:1] == ["ovs-vsctl"]:
        # `ovs-vsctl --version` is listed bare: it asks the database nothing.
        tries = [bare, list(SUDO_VSCTL) + bare[1:]]
    elif bare[:1] == ["ovs-ofctl"]:
        tries = [list(SUDO_OFCTL) + bare[1:],
                 list(SUDO_OFCTL) + ["-O", "OpenFlow13"] + bare[1:]]
    else:
        return ""
    return next((" ".join(t) for t in tries if _is_read(t)), "")


def read_refusal(command) -> str:
    """``""`` when *command* is one of the OVS reads, whole, else why: a near miss names the
    listed form it compared with (`listed_form`), anything else every form (`read_forms`)."""
    if not _safe(command):
        return (f"REFUSED: {str(command)[:80]!r}: an OVS read is printable ASCII and carries "
                "no shell metacharacter or quote.")
    if _is_read(command.split()):
        return ""
    form = listed_form(command)
    if form:
        return (f"REFUSED: {command[:80]!r} is not a listed read; the listed form is `{form}` "
                "(an Open vSwitch read is sent exactly as it is listed).")
    return (f"REFUSED: {command[:80]!r} is not an OVS read Mercury allows: "
            f"{'; '.join(read_forms())}; each <bridge> and <port> one interface name.")


def target_refusal(target: str) -> str:
    """``""`` when *target* is `tcp:<IPv4>:<port>` or `tcp:[<IPv6>]:<port>` (ovs-vsctl(8),
    Controller Connection Methods: "Wrap IPv6 addresses in square brackets")."""
    m = re.fullmatch(r"tcp:(\[([0-9A-Fa-f:.]+)\]|([0-9.]+)):([0-9]{1,5})", target or "")
    if not m:
        return f"{target!r} is not tcp:<IPv4>:<port> or tcp:[<IPv6>]:<port>"
    host = m.group(2) or m.group(3)
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return f"{target!r} names no address"
    if (addr.version == 6) != bool(m.group(2)):
        return f"{target!r}: an IPv6 address is written in brackets, an IPv4 one without"
    if not 1 <= int(m.group(4)) <= 65535:
        return f"{target!r}: the port is 1 to 65535"
    return ""


def _command_refusal(words: list) -> str:
    """``""`` when one ovs-vsctl command (*words*, no `--` in it) is one of the write shapes."""
    opt = words[0] if words and words[0] in ("--may-exist", "--if-exists") else ""
    w = words[1:] if opt else words
    if not w:
        return "an empty command"
    verb, args = w[0], w[1:]
    named = all(NAME.match(a) for a in args[:2])
    if verb in ("add-br", "del-br") and len(args) == 1 and named:
        return "" if opt in ("", "--may-exist" if verb == "add-br" else "--if-exists") else \
            f"{opt} does not go with {verb}"
    if verb in ("add-port", "del-port") and len(args) == 2 and named:
        return "" if opt in ("", "--may-exist" if verb == "add-port" else "--if-exists") else \
            f"{opt} does not go with {verb}"
    if opt:
        return f"{opt} goes only with add-br, add-port, del-br or del-port"
    if verb in ("del-controller", "del-fail-mode") and len(args) == 1 and named:
        return ""
    if verb == "set-fail-mode" and len(args) == 2 and NAME.match(args[0]) \
            and args[1] in FAIL_MODES:
        return ""
    if verb == "set-controller" and len(args) >= 2 and NAME.match(args[0]):
        bad = [target_refusal(t) for t in args[1:] if target_refusal(t)]
        return "; ".join(bad)
    if verb in ("set", "clear") and len(args) == 3 and args[0] == "interface" \
            and NAME.match(args[1]):
        if verb == "clear" and args[2] == "ofport_request":
            return ""
        key, _, value = args[2].partition("=")
        if verb == "set" and key == "ofport_request" and value.isdigit() \
                and not value.startswith("0") and OFPORT_MIN <= int(value) <= OFPORT_MAX:
            return ""
    if verb in ("set", "clear", "remove") and len(args) >= 3 and args[0] == "bridge" \
            and NAME.match(args[1]):
        rest = args[2:]
        if verb == "clear" and rest == ["protocols"]:
            return ""
        if verb == "remove" and rest == ["other-config", "datapath-id"]:
            return ""
        if verb == "set" and len(rest) == 1:
            key, _, value = rest[0].partition("=")
            if key == "protocols" and value and all(v in PROTOCOLS for v in value.split(",")):
                return ""
            if key == "other-config:datapath-id" and _HEX16.match(value) and set(value) != {"0"}:
                return ""
    return f"{' '.join(words)[:80]!r} is not one of the OpenFlow configuration's ovs-vsctl shapes"


def write_refusal(command) -> str:
    """``""`` when *command* is one `sudo -n ovs-vsctl` transaction of the write shapes, else
    why (naming the first command refused)."""
    if not _safe(command):
        return (f"REFUSED: {str(command)[:80]!r}: the ovs-vsctl transaction is printable ASCII "
                "and carries no shell metacharacter or quote.")
    words = command.split()
    if tuple(words[:3]) != SUDO_VSCTL:
        return f"REFUSED: {command[:60]!r} is not a `sudo -n ovs-vsctl` transaction."
    commands, cur = [], []
    for w in words[3:]:
        if w == "--":
            commands.append(cur)
            cur = []
        else:
            cur.append(w)
    commands.append(cur)
    for c in commands:
        why = _command_refusal(c)
        if why:
            return f"REFUSED: {why}. Nothing was sent."
    return ""
