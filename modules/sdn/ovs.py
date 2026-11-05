"""What a session to an Open vSwitch server may carry (docs/LAB9_OPENFLOW.md, section 2).

An OVS server is opened with netmiko's `ovs_linux` (`OvsLinuxSSH`, which is `LinuxSSH` with
nothing added) and is a discovery driver (`modules/discovery.py`) with ONE write: the OpenFlow
configuration's `ovs-vsctl` transaction (`modules/sdn/ovs_config.py`), sent only while the
server is held. Everything here is a positive allowlist of whole command shapes:

- **reads** (`read_refusal`): `ovs-vsctl --version`, and `sudo -n ovs-vsctl` / `sudo -n ovs-ofctl`
  reads of one bridge, each argument one token of its shape;
- **the write** (`write_refusal`): `sudo -n ovs-vsctl` followed by commands separated by a lone
  `--`, which ovs-vsctl runs as one atomic OVSDB transaction (ovs-vsctl(8): "any number of
  commands in a single run, implemented as a single atomic transaction against the database"),
  each command one of `WRITE_SHAPES` with token-shaped arguments. No shell metacharacter, no
  quote, no other program.

`sudo -n` never prompts: the server's sudoers grants the login `ovs-vsctl` and `ovs-ofctl`
without a password, or the command fails with sudo's own words and nothing is changed. netmiko's
Linux `enable()` is `sudo -s`, a root shell, so it is never sent (`discovery.DRIVERS`,
``no_enable``).
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
         "sudo -n ovs-vsctl --columns=target,is_connected list controller")
#: Reads of one bridge (`<bridge>` one NAME token).
BRIDGE_READS = (("get-controller", "<bridge>"), ("get-fail-mode", "<bridge>"),
                ("list-ports", "<bridge>"), ("get", "bridge", "<bridge>", "protocols"),
                ("get", "bridge", "<bridge>", "datapath_id"),
                ("--if-exists", "get", "bridge", "<bridge>", "other-config:datapath-id"))


def _safe(command) -> bool:
    return isinstance(command, str) and not (set(command) & _UNSAFE)


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


def read_refusal(command) -> str:
    """``""`` when *command* is one of the OVS reads, whole, else why."""
    if not _safe(command):
        return (f"REFUSED: {str(command)[:80]!r}: an OVS read carries no shell metacharacter "
                "or quote.")
    words = command.split()
    if " ".join(words) in READS:
        return ""
    if tuple(words[:3]) == SUDO_VSCTL and any(_fits(words[3:], s) for s in BRIDGE_READS):
        return ""
    if tuple(words[:3]) == SUDO_OFCTL and _fits(words[3:], ("-O", "OpenFlow13", "show",
                                                             "<bridge>")):
        return ""
    return (f"REFUSED: {command[:80]!r} is not an OVS read Mercury allows: "
            f"{'; '.join(READS)}; and `sudo -n ovs-vsctl` get-controller, get-fail-mode, "
            "list-ports, get bridge <bridge> protocols or datapath_id, --if-exists get bridge "
            "<bridge> other-config:datapath-id, or `sudo -n ovs-ofctl -O OpenFlow13 show "
            "<bridge>`, each <bridge> one interface name.")


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
        return (f"REFUSED: {str(command)[:80]!r}: the ovs-vsctl transaction carries no shell "
                "metacharacter or quote.")
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
