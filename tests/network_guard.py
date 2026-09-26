"""The harness's network rules (register C46). No side effects on import.

"No test touches a live network" was enforced for nothing a test STARTS. A
test ran the clab sync script with its default URL, which on the deployment
host IS the NMAS, and the live app logged the request on every host run
(2026-09-26). Two layers, because each covers what the other cannot:

1. **The test process.** `install()` makes a connect to anything but loopback
   raise `NetworkRefused`. Measured before it was added: the whole suite made
   NO such connect (an audit hook over every `socket.connect` and
   `getaddrinfo`, with a positive control that it sees one), so it enforces
   the rule as it already holds. It works on every machine.
2. **Every process a test starts.** Only the kernel covers those, whatever
   language they are written in: `scripts/nmas-test` runs the suite in a
   network namespace with loopback alone. `confinement()` MEASURES whether
   that holds, by asking the kernel for a route, which sends no packet.

The deployment host cannot create the namespace (Ubuntu 24.04 restricts
unprivileged user namespaces through AppArmor), so a run there reports itself
NOT confined, in words, rather than claiming a property it does not have.
"""

import errno
import ipaddress
import socket

#: Set by `scripts/nmas-test` (and so by CI): an unconfined run then stops at
#: session start instead of reporting itself.
REQUIRE_ENV = "NMAS_REQUIRE_NETWORK_CONFINEMENT"

#: Documentation addresses (RFC 5737, RFC 3849). A UDP connect to them is a
#: route lookup and sends nothing.
PROBES = ((socket.AF_INET, ("192.0.2.1", 9)), (socket.AF_INET6, ("2001:db8::1", 9)))

# In a Python process a test started, `sitecustomize` has already wrapped
# connect; the confinement probe (a route lookup that sends nothing) needs the
# original, or a nested pytest measures its own guard and reports UNKNOWN.
_real_connect = getattr(socket, "_nmas_real_connect", socket.socket.connect)
_real_connect_ex = getattr(socket, "_nmas_real_connect_ex", socket.socket.connect_ex)


class NetworkRefused(ConnectionRefusedError):
    """Raised by the harness, never by a network: a test tried to leave the
    machine."""


def is_loopback(address) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, bytes):
        host = host.decode()
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _refuse(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6) and not is_loopback(address):
        raise NetworkRefused(
            errno.ECONNREFUSED,
            f"the test harness refused a connection to {address!r}: tests do not "
            "touch a network (C46). Mock the call, or use a loopback address.")


def _guarded_connect(self, address):
    _refuse(self, address)
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    _refuse(self, address)
    return _real_connect_ex(self, address)


def install():
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex


def confinement(connect=None):
    """``(confined, reason)``: True when the kernel has no route to any
    non-loopback address in either family, False when it has one, None when
    the question could not be answered. *connect* is replaceable for tests."""
    connect = connect or _real_connect
    for family, address in PROBES:
        try:
            sock = socket.socket(family, socket.SOCK_DGRAM)
        except OSError:
            continue                    # the family does not exist here: no route
        try:
            connect(sock, address)
        except OSError as exc:
            if exc.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EADDRNOTAVAIL):
                continue
            return None, f"could not tell: {address[0]} answered {exc!r}"
        else:
            return False, f"the kernel has a route to {address[0]}"
        finally:
            sock.close()
    return True, "no route to any non-loopback address, in either family"


def report_line(state=None):
    confined, reason = state or confinement()
    if confined:
        return f"network: CONFINED ({reason}); processes a test starts cannot reach a network"
    if confined is False:
        return (f"network: NOT CONFINED ({reason}). The test process refuses non-loopback "
                "connects; processes a test starts are NOT covered. Run through scripts/nmas-test.")
    return f"network: UNKNOWN ({reason}). Treat as not confined."


# ---------------------------------------------------------------------------
# Layer 3: every process a test STARTS, by construction (C46's open half)
# ---------------------------------------------------------------------------
# The namespace covers children where it can be made, and the deployment host
# cannot make one (declined 2026-09-26: a root-owned path the test harness
# invokes, on the machine holding key.key, is the wrong trade after the
# harness reached the live NMAS). So every child is given an environment in
# which a real endpoint is not reachable by the ordinary routes, and every
# attempt is RECORDED and fails the test that made it:
#   - Python children load `sitecustomize` first, which refuses any
#     non-loopback connect and any DNS name but localhost;
#   - ssh, scp, sftp, rsync, curl, wget, nc, ncat and telnet resolve to shims
#     that refuse, because PATH starts with the shim directory;
#   - git may use only local paths (GIT_ALLOW_PROTOCOL=file), which also
#     covers the ssh that git starts itself.
# An EXPLICIT env (a test passing only PATH and HOME, as C46's test did) is
# rewritten too: the wrapper sits on subprocess.Popen, the one spawn path the
# tests and the program use (measured: nothing calls os.system, os.exec* or
# posix_spawn under test; app.py's execv is the app restarting itself).

import os
import subprocess

SHIMMED = ("ssh", "scp", "sftp", "rsync", "curl", "wget", "nc", "ncat", "telnet")
LOG_ENV = "NMAS_TEST_SPAWN_LOG"
NODE_ENV = "NMAS_TEST_NODEID"

# A FAKE a test builds for itself (an `ssh` that records its argv, in the
# test's tmp_path) is not a network: the shim runs the next tool on PATH when
# that tool lives under pytest's own temporary tree, and refuses anything
# else, which is every real binary.
_SHIM = """#!/bin/sh
tool="$(basename "$0")"; here="$(cd "$(dirname "$0")" && pwd)"
old_ifs="$IFS"; IFS=:
for d in $PATH; do
  [ "$d" = "$here" ] && continue
  if [ -x "$d/$tool" ]; then
    case "$d/" in "${NMAS_TEST_FAKES_UNDER:-/nonexistent}"/*) IFS="$old_ifs"; exec "$d/$tool" "$@" ;; esac
    break
  fi
done
IFS="$old_ifs"
printf '%s\\t%s\\t%s\\n' "$(basename "$0")" "$*" "${NMAS_TEST_NODEID:-}" >> "${NMAS_TEST_SPAWN_LOG:-/dev/null}"
echo "the test harness refused $(basename "$0") $*: tests do not touch a network (C46)" >&2
exit 255
"""

_SITECUSTOMIZE = '''"""Installed by the test harness in every Python process a test starts (C46)."""
import errno as _errno, ipaddress as _ip, os as _os, socket as _socket

_log = _os.environ.get("NMAS_TEST_SPAWN_LOG")
_node = _os.environ.get("NMAS_TEST_NODEID", "")


def _record(what):
    if _log:
        with open(_log, "a", encoding="utf-8") as fh:
            fh.write("python\\t%s\\t%s\\n" % (what, _node))


def _local(host):
    if isinstance(host, bytes):
        host = host.decode()
    try:
        return _ip.ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost", "") or host is None


def _refuse(sock, address):
    if sock.family in (_socket.AF_INET, _socket.AF_INET6) and not _local(address[0]):
        _record("connect %r" % (address,))
        raise ConnectionRefusedError(_errno.ECONNREFUSED,
            "the test harness refused a connection to %r: tests do not touch a network (C46)" % (address,))


_connect, _connect_ex, _gai = _socket.socket.connect, _socket.socket.connect_ex, _socket.getaddrinfo


def _guarded_connect(self, address):
    _refuse(self, address)
    return _connect(self, address)


def _guarded_connect_ex(self, address):
    _refuse(self, address)
    return _connect_ex(self, address)


def _guarded_getaddrinfo(host, *a, **k):
    if host is not None and not _local(host):
        try:
            _ip.ip_address(host.decode() if isinstance(host, bytes) else host)
        except ValueError:
            _record("resolve %r" % (host,))
            raise _socket.gaierror(_socket.EAI_NONAME,
                "the test harness refused to resolve %r: tests do not touch a network (C46)" % (host,))
    return _gai(host, *a, **k)


_socket._nmas_real_connect, _socket._nmas_real_connect_ex = _connect, _connect_ex

# A write into the checkout's data/ by a process a test started is recorded
# like a network attempt, and fails that test by name.
_forbidden = _os.environ.get("NMAS_TEST_CHECKOUT_DATA")
if _forbidden:
    import sys as _sys
    _forbidden = _os.path.realpath(_forbidden)
    _W = _os.O_WRONLY | _os.O_RDWR | _os.O_CREAT | _os.O_TRUNC | _os.O_APPEND
    # (path argument, its dir_fd argument): a dir_fd-relative path is resolved
    # through /proc/self/fd, never against the cwd (tests/store_guard.py).
    _EV = {"os.mkdir": ((0, 2),), "os.rmdir": ((0, 1),), "os.remove": ((0, 1),),
           "os.rename": ((0, 2), (1, 3)), "os.chmod": ((0, 2),), "os.utime": ((0, 3),),
           "shutil.rmtree": ((0, 1),)}

    def _inside(p, fd=None):
        try:
            if isinstance(p, int):
                return None
            p = _os.fsdecode(p)
            if isinstance(fd, int) and fd >= 0 and not _os.path.isabs(p):
                p = _os.path.join(_os.readlink("/proc/self/fd/%d" % fd), p)
            full = _os.path.realpath(p)
        except (TypeError, ValueError, OSError):
            return None
        return full if full == _forbidden or full.startswith(_forbidden + _os.sep) else None

    def _write_hook(event, args):
        try:
            hits = []
            if event == "open":
                a = list(args) + [None, None, None]
                if (isinstance(a[1], str) and any(c in a[1] for c in "wax+")) or \
                        (isinstance(a[2], int) and a[2] != -1 and a[2] & _W):
                    hits = [_inside(a[0])]
            elif event in _EV:
                hits = [_inside(args[i], args[f] if f < len(args) else None)
                        for i, f in _EV[event] if i < len(args)]
            for h in hits:
                if h:
                    _record("write %s %s" % (event, h))
        except Exception:
            pass

    _sys.addaudithook(_write_hook)
_socket.socket.connect = _guarded_connect
_socket.socket.connect_ex = _guarded_connect_ex
_socket.getaddrinfo = _guarded_getaddrinfo
'''


class SpawnGuard:
    """Rewrites the environment of every process a test starts."""

    def __init__(self, root):
        self.root = root
        self.shims = os.path.join(root, "shims")
        self.site = os.path.join(root, "site")
        self.log = os.path.join(root, "attempts.tsv")
        self.current = ""
        self.spawned = 0
        self.fakes_under = ""          # pytest's basetemp, set at session start
        self.checkout_data = ""        # the checkout's data/, which no child may write
        os.makedirs(self.shims, exist_ok=True)
        os.makedirs(self.site, exist_ok=True)
        for tool in SHIMMED:
            path = os.path.join(self.shims, tool)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_SHIM)
            os.chmod(path, 0o755)
        with open(os.path.join(self.site, "sitecustomize.py"), "w", encoding="utf-8") as fh:
            fh.write(_SITECUSTOMIZE)
        open(self.log, "a").close()
        self.offset = 0

    def take(self):
        """For a test that triggers an attempt ON PURPOSE: the attempts since
        the test began, consumed so the per-test check does not fail it."""
        self.offset, lines = self.attempts(self.offset)
        return lines

    def child_env(self, env):
        env = dict(os.environ if env is None else env)
        env["PATH"] = self.shims + os.pathsep + env.get("PATH", os.defpath)
        env["PYTHONPATH"] = self.site + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["GIT_ALLOW_PROTOCOL"] = "file"
        env[LOG_ENV] = self.log
        env[NODE_ENV] = self.current
        # A child uses the TEST store unless the test chose one: an explicit
        # env of PATH and HOME would otherwise send a child that imports the
        # program to the checkout's data/.
        if os.environ.get("NMAS_DATA_DIR"):
            env.setdefault("NMAS_DATA_DIR", os.environ["NMAS_DATA_DIR"])
        if self.checkout_data:
            env["NMAS_TEST_CHECKOUT_DATA"] = self.checkout_data
        if self.fakes_under:
            env["NMAS_TEST_FAKES_UNDER"] = self.fakes_under
        return env

    def attempts(self, start=0):
        """``(new_offset, [lines])``: what spawned processes tried since *start*."""
        with open(self.log, encoding="utf-8") as fh:
            fh.seek(start)
            text = fh.read()
            return fh.tell(), [ln for ln in text.splitlines() if ln]


_guard = None
_real_popen_init = subprocess.Popen.__init__


def _guarded_popen_init(self, args, *rest, **kw):
    if _guard is not None:
        if len(rest) >= 10:                  # env is Popen's 11th parameter
            rest = list(rest)
            rest[9] = _guard.child_env(rest[9])
        else:
            kw["env"] = _guard.child_env(kw.get("env"))
        _guard.spawned += 1
    return _real_popen_init(self, args, *rest, **kw)


def install_spawn_guard(root):
    global _guard
    _guard = SpawnGuard(root)
    subprocess.Popen.__init__ = _guarded_popen_init
    return _guard


def spawn_guard():
    return _guard
