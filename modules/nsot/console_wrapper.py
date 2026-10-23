#!/usr/bin/env python3
"""The console host's SSH forced command: bridge one allowlisted console, refuse anything else.

docs/LAB9_PLAN.md section 8, "The security addition": the console host gives Mercury a DEDICATED
SSH key whose `authorized_keys` line forces this program, so the key's whole power is "bridge
stdin and stdout to the console of a container on the allowlist":

    restrict,command="/usr/local/lib/nmas/nmas-console-bridge /etc/nmas/console-allowlist" ssh-ed25519 ...

sshd runs it with the client's requested command in the environment, `SSH_ORIGINAL_COMMAND`,
which must be EXACTLY one token: a container name on the allowlist (argv[1]; one name a line,
`#` comments and blank lines ignored). On success it replaces itself with ONE fixed argv,
`bridge_argv(name)`, never a shell. On any refusal it writes one line to stderr naming the
comparison it made and both operands, runs nothing, and exits 2.

STANDARD LIBRARY ONLY: a host step installs this file BY NAME on a console host where Mercury is
not installed (tests/test_console_wrapper.py holds the imports to `sys.stdlib_module_names`).
"""

import os
import re
import stat
import sys

#: One container name: what the console host's container runtime accepts, at most 63 characters.
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}")
NAME_MAX = 63
#: Sequences refused even inside a name the pattern accepts: an option marker, and a parent
#: step (`..`; a path step, `../`, also needs a `/`, which NAME never accepts). The console-server
#: store refuses by this same rule (`name_refusal`): one home (C1558's class).
FORBIDDEN = ("--", "..")
#: Where the console listens inside the container (qemu's serial on a TCP port).
CONSOLE_HOST = "127.0.0.1"
CONSOLE_PORT = "5000"
#: The one program run: its stdin and stdout become the console. `socat`, not `nc`: a node
#: container may hold socat and telnet and no nc, measured before this was relied on (C1584).
BRIDGE_HEAD = ("docker", "exec", "-i")
BRIDGE_TAIL = ("socat", "-", f"TCP:{CONSOLE_HOST}:{CONSOLE_PORT}")
#: The forced command's environment variable, set by sshd to what the client asked to run.
COMMAND_VAR = "SSH_ORIGINAL_COMMAND"
PROGRAM = "nmas-console-bridge"
REFUSED = 2
EXEC_FAILED = 1


class Refused(Exception):
    """A refusal; its text names the comparison made and both operands."""


def bridge_argv(name: str) -> list:
    """The exact argv that bridges stdin and stdout to *name*'s console."""
    return [*BRIDGE_HEAD, name, *BRIDGE_TAIL]


def check_name(command) -> str:
    """*command* (SSH_ORIGINAL_COMMAND) when it is exactly one container name; else Refused."""
    if command is None:
        raise Refused(f"{COMMAND_VAR} is not set: this key opens a console, never a shell")
    why = name_refusal(command, COMMAND_VAR)
    if why:
        raise Refused(why)
    return command


def name_refusal(name, label: str = "the container name") -> str:
    """Why *name* is not one container name, or "": THE rule, for this wrapper (*label*
    `SSH_ORIGINAL_COMMAND`) and for Mercury's console-server store, which stores only names
    this would accept."""
    if not isinstance(name, str):
        return f"{label} {name!r} is not text"
    if len(name) > NAME_MAX:
        return (f"{label} is {len(name)} characters, over the {NAME_MAX} a container name may "
                f"have: {name[:NAME_MAX]!r}...")
    if not NAME.fullmatch(name):
        return f"{label} {name!r} is not one container name (it must match {NAME.pattern})"
    for seq in FORBIDDEN:
        if seq in name:
            return f"{label} {name!r} holds {seq!r}, which a name may not hold"
    return ""


def read_allowlist(path: str, uid: int = None) -> list:
    """The names in the allowlist file at *path*, in order.

    Refused: a file that is missing or unreadable, not a regular file, writable by others, or
    owned by neither root nor *uid* (default: the invoking user); and a line that is not one
    container name, so a typo never widens what the key reaches."""
    uid = os.getuid() if uid is None else uid
    try:
        with open(path, "rb") as fh:
            st = os.fstat(fh.fileno())
            data = fh.read()
    except OSError as e:
        raise Refused(f"the allowlist {path} could not be read: {e}") from None
    if not data.isascii():
        raise Refused(f"the allowlist {path} holds a byte outside ASCII")
    text = data.decode()
    if not stat.S_ISREG(st.st_mode):
        raise Refused(f"the allowlist {path} is not a regular file")
    if st.st_mode & stat.S_IWOTH:
        raise Refused(f"the allowlist {path} is writable by others (mode "
                      f"{stat.S_IMODE(st.st_mode):04o})")
    if st.st_uid not in (0, uid):
        raise Refused(f"the allowlist {path} is owned by uid {st.st_uid}, neither root (0) nor "
                      f"the invoking user ({uid})")
    names = []
    for number, line in enumerate(text.splitlines(), 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if not NAME.fullmatch(entry):
            raise Refused(f"the allowlist {path} line {number} {entry!r} is not one container "
                          f"name (it must match {NAME.pattern})")
        names.append(entry)
    return names


def decide(argv: list, environ, uid: int = None) -> list:
    """The argv to run for this invocation, or Refused: the forced command's whole decision."""
    if len(argv) != 2:
        raise Refused(f"{len(argv) - 1} arguments given, 1 expected: the allowlist's path "
                      f"(usage: {PROGRAM} <allowlist>)")
    name = check_name(environ.get(COMMAND_VAR))
    names = read_allowlist(argv[1], uid)
    if name not in names:
        raise Refused(f"{name!r} is not on the allowlist {argv[1]} ({len(names)} names)")
    return bridge_argv(name)


def main(argv: list, environ=None, execvp=os.execvp, stderr=None, uid: int = None) -> int:
    """Run the bridge for this invocation, or refuse it. Returns only when nothing was run (or
    the exec itself failed): REFUSED (2) for a refusal, EXEC_FAILED (1) for the exec."""
    environ = os.environ if environ is None else environ
    stderr = sys.stderr if stderr is None else stderr
    try:
        args = decide(argv, environ, uid)
    except Refused as e:
        stderr.write(f"{PROGRAM}: refused: {e}\n")
        return REFUSED
    try:
        execvp(args[0], args)
    except OSError as e:
        stderr.write(f"{PROGRAM}: could not run {args[0]}: {e}\n")
        return EXEC_FAILED
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
