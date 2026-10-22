"""Console transports and the driver loop: the bytes between a console and its session (O2).

docs/LAB9_PLAN.md section 8, piece 2 and the operator's cut (two drivers for Lab 9). A
transport reaches ONE console-server port and moves bytes; the session state machine
(console_session.py) decides every byte sent; `run_plan` carries them between the two and
composes nothing itself.

**The interface** (`ConsoleTransport`): `open()`, `read(max_bytes, timeout) -> bytes` (``b""``
when nothing arrived within *timeout*; `ConsoleClosed` when the far end closed),
`write(data)` (every byte sent, counted in `bytes_written`), `close()`; a context manager.

**The drivers:**
- `CommandBridge`: SSH to the console server and an exec channel whose command is ONLY the
  container's name. The console host's forced command (console_wrapper.py) reads it from
  ``SSH_ORIGINAL_COMMAND`` and bridges stdin and stdout to that container's console. The name
  is checked by the wrapper's own `check_name` (one home for the rule) before anything
  connects.
- `RawTcp`: a TCP connection to the console's host and port, optionally through an SSH jump
  host's ``direct-tcpip`` channel. It never answers telnet negotiation: the session strips
  what arrives, and the bytes written are ONLY what the plan sends.

Every SSH connection here (the console server, the jump host) is opened by
`connection.open_pinned_transport`: the server's host key compared with Mercury's record
before the key is offered (C906), signed in with the key Mercury holds under the port's
credential REFERENCE (console_keys.py). No key, password or credential value is logged,
returned or put in an exception here.

**One session per console port, across processes:** an exclusive ``flock`` on
``<data>/console_ports/<port id>.lock`` (the port's NetBox id), taken in `open()` before
anything connects and given up in `close()` whatever happened; a held port is REFUSED naming
its holder, never queued (connection._take_slot's pattern). The kernel frees a ``flock`` when
its process dies, so a crash never keeps a port.
"""

import ipaddress
import logging
import os
import re
import socket
import time
from dataclasses import dataclass

from modules import redact
from modules.nsot import console_wrapper

log = logging.getLogger(__name__)

#: A read's wait when nothing arrives, in seconds: the loop's cadence for telling the session
#: that time passed (`tick`). Not a bound on anything: it must sit under the session's settle
#: interval (0.5 s by default) so a prompt that has settled is acted on within one more wait.
POLL_S = 0.2
#: The most bytes one read takes.
CHUNK = 4096
#: Where the console-port locks live, under the data folder.
LOCK_FOLDER = "console_ports"
#: The stderr a closed bridge's refusal is read from, at most (the wrapper writes one line).
STDERR_MAX = 1000
#: How long a closed bridge's exit status is waited for, in seconds. Unmeasured: sshd sends
#: the exit status with the channel's close, so it is normally there already; the wait only
#: keeps a slow one from being reported as "no status". Explicit until measured.
EXIT_WAIT_S = 2.0
#: The SSH port when the store names none.
SSH_PORT = 22

#: One hostname label (RFC 1123).
LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
#: An IPv6 zone (``fe80::1%eth0``): an interface name's characters only, 15 at most.
ZONE = re.compile(r"[A-Za-z0-9_.-]{1,15}")


def connect_bound() -> float:
    """The connect bound, in seconds: the device SSH connect's (`connection.CONNECT_TIMEOUT_S`,
    35 s, 2.5 times the slowest device connect measured, 13.7 s on 2026-09-29; its basis is
    written beside it there). NOT measured against a console server or
    a jump host: none was reachable from the laptop while this was written, and a host answers
    faster than a vIOS, so the device's bound is the explicit, generous stand-in until the
    console server's connect is measured (re-derive it then)."""
    from modules.connection import CONNECT_TIMEOUT_S
    return CONNECT_TIMEOUT_S


class ConsoleRefused(RuntimeError):
    """Refused before or while connecting; the text names the comparison and both operands."""


class PortBusy(ConsoleRefused):
    """The console-server port is held by another session (refused, never queued)."""


class ConsoleClosed(RuntimeError):
    """The far end closed the console (or the bridge refused); the text says what it said."""


# ── checks ───────────────────────────────────────────────────────────────────────────────

def check_port_id(port_id) -> int:
    """*port_id* (a console-server port's NetBox id) when it is a positive integer."""
    if isinstance(port_id, bool) or not isinstance(port_id, int) or port_id <= 0:
        raise ConsoleRefused(f"a console-server port's id is a positive number, not "
                             f"{port_id!r}")
    return port_id


def check_tcp_port(what: str, value) -> int:
    """*value* when it is a TCP port number (1 to 65535)."""
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ConsoleRefused(f"{what} {value!r} is not a port number (1 to 65535)")
    return value


def canonical_host(host) -> str:
    """*host* as connected to and keyed in the host-key record: an IPv4 or IPv6 address in
    its canonical form (an IPv6 one unbracketed, compressed, its zone kept), or a hostname in
    lower case; else ConsoleRefused saying why.

    THE ONE HOME of the console-server host rule (C1558): the console-server store
    (`console_servers.host_refusal`) checks a host with this, so what the store keeps is what
    a transport connects to. Brackets only around an IPv6 address; a zone (``%eth0``) only on
    an IPv6 address, and only an interface name's characters (`ZONE`); no space or line break
    anywhere (`ipaddress` would keep one in a zone)."""
    text = host if isinstance(host, str) else ""
    bare = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    addr, has_zone, zone = bare.partition("%")
    try:
        address = ipaddress.ip_address(addr)
    except ValueError:
        address = None

    def refused(why: str = "") -> ConsoleRefused:
        return ConsoleRefused(f"{host!r} is not an IPv4 or IPv6 address or a hostname"
                              + (f": {why}" if why else ""))

    if address is not None:
        if bare != text and address.version != 6:
            raise refused("only an IPv6 address is written in brackets")
        if not has_zone:
            return str(address)
        if address.version != 6:
            raise refused("only an IPv6 address carries a zone")
        if not ZONE.fullmatch(zone):
            raise refused(f"the IPv6 zone {zone!r} is not an interface name")
        return f"{address}%{zone}"
    if ":" in text or "%" in text:
        raise refused("it is not an IPv6 address")
    name = text[:-1] if text.endswith(".") else text     # one trailing dot: fully qualified
    labels = name.split(".")
    if bare != text or len(name) > 253 or \
            not all(LABEL.fullmatch(label) for label in labels):
        raise refused()
    if all(label.isdigit() for label in labels):
        raise refused("it is not an IPv4 address")
    return name.lower()


# ── one session per console port ─────────────────────────────────────────────────────────

class PortLock:
    """An exclusive, non-blocking hold on one console-server port, across processes."""

    def __init__(self, port_id, owner: str):
        self.port_id = check_port_id(port_id)
        self.owner = owner
        self._fd = None

    def path(self) -> str:
        from modules import config
        return os.path.join(config.DATA_DIR, LOCK_FOLDER, f"{self.port_id}.lock")

    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> None:
        """Hold the port, or PortBusy naming who holds it."""
        import fcntl

        if self._fd is not None:
            raise PortBusy(f"console-server port {self.port_id} is already held by this "
                           f"session ({self.owner})")
        path = self.path()
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                # The first 300 bytes of the holder's record (UTF-8; a character cut there
                # reads as U+FFFD, never as a refusal that cannot say who holds the port).
                said = os.pread(fd, 300, 0).decode(errors="replace").strip()
            finally:
                os.close(fd)
            raise PortBusy(f"console-server port {self.port_id} is held by "
                           f"{said or 'a process that recorded nothing'}, so {self.owner} "
                           "was refused (one session per console port; never queued)") from None
        record = f"{self.owner} (pid {os.getpid()})".encode()
        os.pwrite(fd, record, 0)
        os.ftruncate(fd, len(record))         # a longer record a crash left is cut to this one
        self._fd = fd

    def release(self) -> None:
        """Give the port up (closing the file gives up the ``flock``); nothing when not held."""
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            os.ftruncate(fd, 0)
        finally:
            os.close(fd)


# ── the interface ────────────────────────────────────────────────────────────────────────

class ConsoleTransport:
    """One console-server port's byte stream. Subclasses connect (`_connect`), and name the
    pipe that carries the bytes (`_pipe`); the rest is here, once."""

    kind = ""

    def __init__(self, port_id, *, owner: str = "", connect_timeout: float = None):
        self.owner = owner or "an unnamed caller"
        self.lock = PortLock(port_id, self.owner)
        self.connect_timeout = connect_timeout
        self.bytes_written = 0
        self._opened = False

    # The subclass's part.
    def _check(self) -> None:
        """Refuse what is wrong before anything is held or connected."""

    def _connect(self, bound: float) -> None:
        raise NotImplementedError

    def _pipe(self):
        raise NotImplementedError

    def _disconnect(self) -> None:
        raise NotImplementedError

    def _closed(self) -> ConsoleClosed:
        return ConsoleClosed(f"{self.describe()} closed the console")

    def describe(self) -> str:
        raise NotImplementedError

    # The interface.
    def open(self):
        """Check, hold the port, connect; on any failure nothing stays held or connected."""
        if self._opened:
            raise ConsoleRefused(f"{self.describe()} is already open")
        self._check()
        self.lock.acquire()
        try:
            self._connect(self.connect_timeout or connect_bound())
        except BaseException:
            try:
                self._disconnect()
            finally:
                self.lock.release()
            raise
        self._opened = True
        log.info("console: opened %s for %s", self.describe(), self.owner)
        return self

    def _need_open(self) -> None:
        if not self._opened:
            raise ConsoleClosed(f"{self.describe()} is not open")

    def read(self, max_bytes: int, timeout: float) -> bytes:
        """Up to *max_bytes* that arrived within *timeout* seconds, ``b""`` when none did;
        ConsoleClosed when the far end has closed."""
        self._need_open()
        pipe = self._pipe()
        pipe.settimeout(timeout)
        try:
            data = pipe.recv(max_bytes)
        except socket.timeout:
            return b""
        if not data:
            raise self._closed()
        return data

    def write(self, data: bytes) -> int:
        """Send every byte of *data*, counted in `bytes_written`."""
        self._need_open()
        if not isinstance(data, bytes) or not data:
            raise ValueError(f"a console write is bytes, at least one: {data!r}")
        self._pipe().sendall(data)
        self.bytes_written += len(data)
        return len(data)

    def close(self) -> None:
        """Disconnect and give the port up, whatever happens on the way."""
        try:
            if self._opened:
                self._disconnect()
        finally:
            self._opened = False
            self.lock.release()

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()
        return False


class _SshMixin:
    """Signing in to a console server or jump host with the key under a reference."""

    def _sign_in(self, host: str, port: int, ref: str, bound: float):
        from modules import connection
        from modules.nsot import console_keys

        username, pkey = console_keys.load(ref)
        return connection.open_pinned_transport(host, port, username=username, pkey=pkey,
                                                owner=self.owner, timeout=bound)


class CommandBridge(_SshMixin, ConsoleTransport):
    """An SSH console server whose forced command bridges one container's console, chosen by
    its name (the exec command is the name and nothing else)."""

    kind = "command_bridge"

    def __init__(self, port_id, *, host: str, container: str, credential_ref: str,
                 ssh_port: int = SSH_PORT, owner: str = "", connect_timeout: float = None):
        super().__init__(port_id, owner=owner, connect_timeout=connect_timeout)
        self.host, self.container = host, container
        self.ssh_port, self.credential_ref = ssh_port, credential_ref
        self._ssh = self._chan = None

    def describe(self) -> str:
        return (f"console-server port {self.lock.port_id} ({self.container!r} on {self.host} "
                f"port {self.ssh_port})")

    def _check(self) -> None:
        try:
            console_wrapper.check_name(self.container)
        except console_wrapper.Refused as exc:
            raise ConsoleRefused(f"the console's container name was refused before "
                                 f"connecting: {exc}") from None
        self.host = canonical_host(self.host)
        check_tcp_port("the console server's SSH port", self.ssh_port)

    def _connect(self, bound: float) -> None:
        self._ssh = self._sign_in(self.host, self.ssh_port, self.credential_ref, bound)
        self._chan = self._ssh.open_session(timeout=bound)
        self._chan.exec_command(self.container)

    def _pipe(self):
        return self._chan

    def _closed(self) -> ConsoleClosed:
        chan = self._chan
        chan.status_event.wait(EXIT_WAIT_S)
        said = b""
        while chan.recv_stderr_ready() and len(said) < STDERR_MAX:
            said += chan.recv_stderr(STDERR_MAX - len(said))
        status = chan.recv_exit_status() if chan.exit_status_ready() else None
        words = redact.redact_text(said.decode(errors="replace").strip())
        return ConsoleClosed(f"{self.describe()} closed the bridge"
                             + (f" (exit {status})" if status is not None else "")
                             + (f": {words}" if words else ""))

    def _disconnect(self) -> None:
        chan, ssh, self._chan, self._ssh = self._chan, self._ssh, None, None
        try:
            if chan is not None:
                chan.close()
        finally:
            if ssh is not None:
                ssh.close()


class RawTcp(_SshMixin, ConsoleTransport):
    """A console on a TCP port, reached directly or through an SSH jump host's
    ``direct-tcpip`` channel. Answers nothing it is sent: telnet negotiation included."""

    kind = "raw_tcp"

    def __init__(self, port_id, *, host: str, tcp_port: int, jump_host: str = None,
                 ssh_port: int = SSH_PORT, credential_ref: str = None, owner: str = "",
                 connect_timeout: float = None):
        super().__init__(port_id, owner=owner, connect_timeout=connect_timeout)
        self.host, self.tcp_port = host, tcp_port
        self.jump_host, self.ssh_port, self.credential_ref = jump_host, ssh_port, credential_ref
        self._ssh = self._chan = self._sock = None

    def describe(self) -> str:
        via = f" via {self.jump_host} port {self.ssh_port}" if self.jump_host else ""
        return f"console-server port {self.lock.port_id} ({self.host} port {self.tcp_port}{via})"

    def _check(self) -> None:
        self.host = canonical_host(self.host)
        check_tcp_port("the console's TCP port", self.tcp_port)
        if self.jump_host:
            self.jump_host = canonical_host(self.jump_host)
            check_tcp_port("the jump host's SSH port", self.ssh_port)
            if not self.credential_ref:
                raise ConsoleRefused(f"the jump host {self.jump_host} needs a credential "
                                     "reference, and none was given")

    def _connect(self, bound: float) -> None:
        if not self.jump_host:
            self._sock = socket.create_connection((self.host, self.tcp_port), timeout=bound)
            return
        self._ssh = self._sign_in(self.jump_host, self.ssh_port, self.credential_ref, bound)
        # The originator is the address this SSH connection leaves from (informational to
        # the server, as OpenSSH's own client sends it).
        address, port = self._ssh.sock.getsockname()[:2]
        self._chan = self._ssh.open_channel("direct-tcpip", (self.host, self.tcp_port),
                                            (address, port), timeout=bound)

    def _pipe(self):
        return self._chan if self.jump_host else self._sock

    def _disconnect(self) -> None:
        chan, ssh, sock = self._chan, self._ssh, self._sock
        self._chan = self._ssh = self._sock = None
        try:
            for pipe in (chan, sock):
                if pipe is not None:
                    pipe.close()
        finally:
            if ssh is not None:
                ssh.close()


# ── the driver loop ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RunResult:
    outcome: str           # "done", "aborted", "bound" (the run's bound passed), "closed", or
    #                        "refused" (a send for a device this thread does not hold, C1559)
    reason: str            # masked
    state: str             # the session's state at the end
    attach_state: object   # the first prompt seen before a line was typed (the survey's input)
    sent: bytes            # every byte the session decided to send, in order
    bytes_written: int     # every byte the transport wrote during this run
    transcript: str        # masked


def unheld(device) -> str:
    """Why a console write for *device* (``(network, hostname)``) must not happen on this
    thread, or "" when this thread holds that device (`device_ops.held_here`)."""
    from modules.nsot import device_ops

    if not (isinstance(device, tuple) and len(device) == 2 and all(device)):
        return (f"a console write names the device it is for, as (network, hostname), and "
                f"{device!r} was given: nothing was written")
    if not device_ops.held_here(*device):
        return (f"this thread does not hold {device[1]} in {device[0]}, and a console write "
                "needs the device held by its operation (C1559): nothing was written")
    return ""


def run_plan(transport, session, clock=time.monotonic, *, bound_s: float,
             poll_s: float = POLL_S, chunk: int = CHUNK, device=None,
             plan=None, seed: bytes = b"") -> RunResult:
    """Drive *session* over an open *transport* until it is done or aborted, the far end
    closes, or *bound_s* seconds pass on *clock* from the run's start.

    **A send needs the device held** (C1559): every write is checked against *device*
    (``(network, hostname)``), which THIS thread must hold (`device_ops.hold`); otherwise the
    run ends ``refused`` with nothing written. A run that sends nothing needs no device.

    *plan*: the session's next plan (`ConsoleSession.continue_with`), begun from the prompt
    its last plan ended on; its first send is this run's, checked and written like any other.

    *seed*: console text an earlier session already received (the prompt a device printed
    before it was woken), fed to this new session first, so the decision it makes is this
    run's, checked and written like any other.

    *bound_s* is the caller's, required: the operation knows its budget (a survey's few reads,
    a kick-start that waits out a boot). The session's own step bound ends a stalled step
    sooner; this bound is the run's whole budget, so a run is bounded even if every step is
    answered just inside its own.

    Each chunk read is fed to the session; each wait that brings nothing tells it time passed
    (`tick`, which is how a settled prompt is acted on). The ONLY bytes written are a `send`
    decision's data, exactly; the loop composes none, answers nothing, and writes nothing
    after the end (no logout, no CR). *clock* is the session's clock (monotonic seconds)."""
    if not bound_s > 0:
        raise ValueError(f"bound_s {bound_s} must be above 0: a run is always bounded")
    if not 0 < poll_s < session.settle_s:
        raise ValueError(f"poll_s {poll_s} must be above 0 and under the session's settle_s "
                         f"{session.settle_s}, or a settled prompt waits a whole read")
    start = clock()
    written = transport.bytes_written
    if plan is not None:
        decision = session.continue_with(plan, start)
    elif seed:
        decision = session.feed(seed, start)
    else:
        decision = session.tick(start)
    while True:
        if decision.action == "send":
            why = unheld(device)
            if why:
                outcome, reason = "refused", why
                break
            try:
                transport.write(decision.data)
            except (OSError, ConsoleClosed) as exc:
                outcome, reason = "closed", (f"writing the plan's {len(decision.data)} bytes "
                                             f"failed: {exc}")
                break
        elif decision.action == "done":
            outcome, reason = "done", decision.reason
            break
        elif decision.action == "abort":
            outcome, reason = "aborted", decision.reason
            break
        if clock() - start >= bound_s:
            outcome, reason = "bound", (f"the run's bound of {bound_s:g} s passed in state "
                                        f"{session.state}, waiting for {session.expected()}")
            break
        try:
            data = transport.read(chunk, poll_s)
        except ConsoleClosed as exc:
            outcome, reason = "closed", str(exc)
            break
        now = clock()
        decision = session.feed(data, now) if data else session.tick(now)
    result = RunResult(outcome=outcome, reason=redact.redact_text(reason, session.values),
                       state=session.state, attach_state=session.attach_state,
                       sent=session.sent(), bytes_written=transport.bytes_written - written,
                       transcript=session.transcript())
    log.info("console: %s ended %s after %d bytes written (%s)", transport.describe(),
             outcome, result.bytes_written, result.reason)
    return result
