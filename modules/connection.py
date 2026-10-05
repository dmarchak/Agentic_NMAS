"""connection.py

SSH connection management via Netmiko for the Network Device Manager.

Provides three connection patterns:
  - `with_temp_connection`: open a connection, run a callable, then close.
  - `get_persistent_connection` / `close_persistent_connection`: maintain a
    per-IP connection pool for repeated operations (status checks, etc.).
  - `session_reaper`: background daemon thread that closes idle pooled
    sessions (C97). Probing devices moved to the reachability reader (C92,
    `modules/readers/reachability.py`), which judges over consecutive probes.

Device credentials are decrypted on the fly using the Fernet key managed by
modules.device; they are never stored in the connection pool in plaintext
beyond the lifetime of each ConnectHandler object.
"""

from netmiko import ConnectHandler
import threading
import logging
import ipaddress
import time
import os
from modules.device import decrypt_field, load_saved_devices
from modules.config import DEVICES_FILE, FAST_CLI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection parameters — ONE construction, every caller
# ---------------------------------------------------------------------------


#: The SSH connect bound, in seconds (C205, the operator's decision 2026-09-29):
#: 2.5 times the slowest connect measured, s3's 13.7 s at the 2026-09-29 Save All
#: preview (vIOS switches connect 2 to 4 times slower than the IOS-XE routers).
#: Netmiko's default is 10 s and nothing had chosen it, so the slowest device
#: failed whenever it was slow. The cost, accepted: a device that is truly down
#: takes 35 s to report. Re-derive it when the measurement moves; per platform,
#: and per network once P.8 exists, is the recorded follow-up.
CONNECT_TIMEOUT_S = 35


def read_floor() -> float:
    """The least any read on a tool session may wait: the config read's
    measured bound (`nsot_config_read_timeout`, 120 s), never Netmiko's fixed
    ones.

    Netmiko waits a FIXED 10 s for a command's echo (`command_echo_read`, set
    by no argument a caller can pass), 10 s for the prompt and for `terminal
    width 511` while logging in, and 20 s for `terminal length 0`. Measured on
    the host 2026-10-01: an echo took up to 5.9 s with every device read at
    once, a vIOS `show running-config | include ^username` 31.6 s alone (s3),
    a login 46 s, and at 06:03 the hourly startup check met all four bounds at
    once: r1 to r4 at the echo, s1 at the login prompt, s3 and s4 in session
    preparation. A bound smaller than what it bounds is how a slow device
    reads as an unreadable one."""
    try:
        from modules.config_read import read_timeout
        return float(read_timeout())
    except Exception:                                   # noqa: BLE001
        return 120.0


def prompt_terminator(base_prompt: str):
    """The pattern a show command's read ends on: the device's OWN prompt, as
    the last line of what has arrived after the command's echo, or None when
    the base prompt is not a hostname (a NUL read, C272), so the caller's
    default stands.

    Netmiko's default with no prompt probe is the bare base prompt, which
    `hostname r1` matches mid-configuration; with one, a 10 s probe per
    command. Anchored to a line of its own and to the end of the text, a
    hostname inside the output cannot end the read. The echo still comes
    first: measured on r1 and s1, prompts left over from logging in sit in the
    channel before it (`\\nr1#\\nr1#\\nr1#\\nr1#show startup-config`), and a
    read ending on the prompt alone answered every command with the previous
    command's output (tests/fixtures/transcripts/)."""
    import re as _re

    bp = (base_prompt or "").strip()
    if not bp or not _re.fullmatch(r"[\w.\-]+", bp):
        return None
    return (r"(?m)^" + _re.escape(bp) + r"[\w.\-]*(?:\([^)\n]*\))?[>#][ \t]*\Z")


def floor_reads(conn, floor: float = None) -> None:
    """Make every read on *conn* wait at least *floor* seconds (read_floor()),
    and end a show command on prompt_terminator(): login, Netmiko's session
    preparation, each echo and each command. A caller's LONGER bound is kept;
    nothing here shortens a wait. Applied by open_ssh() before the session
    logs in, so the session preparation is bounded too."""
    floor = read_floor() if floor is None else float(floor)
    until = getattr(conn, "read_until_pattern", None)
    if callable(until):
        def read_until_pattern(*args, **kwargs):
            args = list(args)
            if len(args) >= 2:
                if args[1] and args[1] < floor:
                    args[1] = floor
            else:
                given = kwargs.get("read_timeout", 10.0)
                if given and given < floor:
                    kwargs["read_timeout"] = floor
            return until(*args, **kwargs)
        conn.read_until_pattern = read_until_pattern
    send = getattr(conn, "send_command", None)
    if callable(send):
        def send_command(*args, **kwargs):
            given = kwargs.get("read_timeout", 10.0)
            if given and given < floor:
                kwargs["read_timeout"] = floor
            if len(args) < 2 and kwargs.get("expect_string") is None:
                pattern = prompt_terminator(getattr(conn, "base_prompt", ""))
                if pattern:
                    kwargs["expect_string"] = pattern
            return send(*args, **kwargs)
        conn.send_command = send_command
    conn._nmas_read_floor = floor


def connection_params(dev: dict, *, password: str, secret: str = None) -> dict:
    """Build the ConnectHandler kwargs. The only place they are assembled.

    Five call sites used to build these independently, all of them agreeing by
    coincidence rather than by construction. That is survivable until one
    transport setting is needed — legacy KEX or host-key algorithms for older
    IOS against a modern client, a timeout, a device-type quirk — at which
    point it is added where the failure was noticed and the other four are
    silently left behind.

    That asymmetry is specifically dangerous on the rotation path. If the
    verify negotiates differently from the session that just pushed the new
    credential, it fails for a **transport** reason, the classifier reads a
    connection failure as a device verdict, and a rotation that actually
    succeeded gets reverted. A fake device cannot catch it either: it models
    the credential exchange, not the negotiation.

    **The password is always passed explicitly.** Callers holding an inventory
    row decrypt first; the rotation holds a plaintext value that has never been
    stored and passes it straight through. Deciding internally whether to
    decrypt is what produced the r2 defect — a function that guesses which of
    those two it was handed will eventually guess wrong.
    """
    return {
        "device_type": dev["device_type"],
        "ip": dev["ip"],
        "username": dev["username"],
        "password": password,
        # An EMPTY secret means "none stored", and falls back to the login
        # password, exactly as None always did (register B14, P.3 step 11).
        # Every device here stored a copy of its password as its "secret", used
        # for nothing, since no device has an enable secret and Netmiko sends
        # one only when asked. Emptying those copies must not turn an empty
        # string into an enable password somebody might be asked for.
        "secret": secret or password,
        "port": 22,
        "fast_cli": FAST_CLI,
    }


def stored_connection_params(dev: dict) -> dict:
    """:func:`connection_params` for a device row, decrypting as it goes."""
    return connection_params(
        dev,
        password=decrypt_field(dev["password"]),
        secret=decrypt_field(dev["secret"]),
    )

# ---------------------------------------------------------------------------
# Per-device send locks
# ---------------------------------------------------------------------------
# Each device IP gets one RLock that serialises all SSH sends/receives.
# Using RLock so callers that explicitly hold the lock for a multi-step
# sequence don't deadlock when LockedConnection re-acquires it per-method.

_send_locks: dict = {}
_send_locks_mu = threading.Lock()


def get_device_send_lock(ip: str) -> threading.RLock:
    """Return (creating if needed) the per-device send-serialisation RLock."""
    with _send_locks_mu:
        if ip not in _send_locks:
            _send_locks[ip] = threading.RLock()
        return _send_locks[ip]


class LockedConnection:
    """Thread-safe proxy for a Netmiko ConnectHandler.

    Every method call acquires the per-device RLock before delegating to the
    underlying connection, preventing two threads from interleaving commands
    on the same SSH session.

    Callers that need to execute a *sequence* of commands atomically should
    hold the same lock explicitly::

        with get_device_send_lock(ip):
            conn.send_command_timing(cmd1)
            conn.send_command_timing(cmd2)

    Because the lock is an RLock the nested acquire inside each method does
    not deadlock.
    """

    __slots__ = ('_conn', '_lock')

    def __init__(self, conn: ConnectHandler, lock: threading.RLock) -> None:
        object.__setattr__(self, '_conn', conn)
        object.__setattr__(self, '_lock', lock)

    def __getattr__(self, name: str):
        conn = object.__getattribute__(self, '_conn')
        lock = object.__getattribute__(self, '_lock')
        attr = getattr(conn, name)
        if callable(attr):
            def _locked(*args, **kwargs):
                with lock:
                    _touch(conn)
                    return attr(*args, **kwargs)
            return _locked
        return attr

    def __setattr__(self, name: str, value) -> None:
        conn = object.__getattribute__(self, '_conn')
        setattr(conn, name, value)


# ---------------------------------------------------------------------------
# Every SSH session this process holds, per device (register C97)
# ---------------------------------------------------------------------------
# The tool locked itself out of r2 (2026-09-27): all five vty lines held by
# its own idle sessions, so SSH was refused and the device read as offline
# while nothing was wrong with it. Each deploy and restore left its pipeline
# pool open, the capture reader left one per read, and nothing counted them.
# A Netmiko session is not closed by dropping the reference: paramiko's
# transport thread keeps it alive until the DEVICE times it out
# (`exec-timeout 10 0`, the IOS default, measured on a C8000v and a vIOS).
#
# So every session is opened through `open_ssh()`, which:
#   * counts the sessions this process holds per device, with who owns each;
#   * refuses past a BUDGET: the device's vty lines minus one kept free for a
#     person, because the tool locking a human out of a device it manages is
#     the worst version of this, and the console is not always there;
#   * logs every open and close naming the device and the owner (paramiko's
#     own "Connected" line names neither);
#   * lets `reap_idle()` close a long-lived pool's idle session itself,
#     rather than waiting on the device's timeout.
# The budget counts every process of this tool (CONCURRENCY_AUDIT R11, 2026-10-04): each
# session takes a slot, a `flock` on `<store>/ssh_slots/<ip>/<n>.lock`, so the app and a host
# CLI share it, and a process that dies frees its slots. Oxidized and a person's own sessions
# take lines too, which is why one is kept rather than none.

RESERVED_FOR_PEOPLE = 1
#: IOS's own default (`line vty 0 4`), used when the device's golden cannot
#: say: the smallest vty count in the fleet, so an unknown is never generous.
DEFAULT_VTY_LINES = 5
#: A pooled session idle this long is closed by the tool, well inside the
#: device's own ten minutes.
IDLE_REAP_SECONDS = 120
_VTY_CACHE_SECONDS = 300


class SessionBudgetExceeded(RuntimeError):
    """Opening another session would leave no vty line for a person."""


_sessions: dict = {}          # ip -> {sid: info}
_sessions_mu = threading.Lock()
_sid_counter = [0]
_vty_cache: dict = {}         # ip -> (lines, source, at)


def _count_vty_lines(config: str) -> int:
    """The vty lines a config declares (`line vty 0 4` is five)."""
    import re

    total = 0
    for first, last in re.findall(r"^line vty (\d+)(?: (\d+))?\s*$", config or "", re.M):
        total += (int(last) - int(first) + 1) if last else 1
    return total


def _golden_for_ip(ip: str):
    """The committed golden TEXT for *ip*, found through each list's manifest,
    READING ONLY. Opening a session must not write: it used to go through the agent's
    golden lookup, whose import creates directories and whose legacy path
    makes one, so every session opened from a read-only CLI touched the
    store (found by `nmas-capture-output`'s own audit hook, 2026-09-27)."""
    from modules import config
    from modules.nsot import manifest

    if not os.path.isdir(config.LISTS_DIR):
        return None
    for slug in sorted(os.listdir(config.LISTS_DIR)):
        repo = os.path.join(config.LISTS_DIR, slug, "config_repo")
        if not os.path.exists(manifest.manifest_path(repo)):
            continue
        _identity, entry = manifest.find_by_ip(repo, ip)
        if entry:
            from modules.nsot.repo import committed_golden_for
            text = committed_golden_for(repo, entry)["text"]   # as COMMITTED (C104)
            if text:
                return text
    return None


def vty_lines(ip: str) -> tuple:
    """``(lines, source)`` for a device, from its golden config."""
    now = time.time()
    cached = _vty_cache.get(ip)
    if cached and now - cached[2] < _VTY_CACHE_SECONDS:
        return cached[0], cached[1]
    lines, source = DEFAULT_VTY_LINES, "IOS default: the golden does not say"
    try:
        text = _golden_for_ip(ip)
        if text:
            counted = _count_vty_lines(text)
            if counted:
                lines, source = counted, "its golden config"
    except Exception:                          # noqa: BLE001
        logger.debug("ssh: vty count unreadable for %s", ip, exc_info=True)
    _vty_cache[ip] = (lines, source, now)
    return lines, source


def session_budget(ip: str) -> dict:
    lines, source = vty_lines(ip)
    return {"lines": lines, "source": source,
            "budget": max(0, lines - RESERVED_FOR_PEOPLE)}


def _caller_label() -> str:
    """module:function of the code asking for a session, for attribution."""
    import sys

    frame = sys._getframe(1)
    while frame and frame.f_globals.get("__name__") == __name__:
        frame = frame.f_back
    if not frame:
        return "?"
    return f"{frame.f_globals.get('__name__', '?')}:{frame.f_code.co_name}"


#: A slot held by THIS process: (ip, n) -> (fd, sid).
_slots: dict = {}


def _slot_dir(ip: str) -> str:
    import re
    from modules import config
    return os.path.join(config.DATA_DIR, "ssh_slots", re.sub(r"[^0-9A-Za-z_.-]", "_", ip))


def _take_slot(ip: str, budget: int, owner: str):
    """``(n, fd, [])`` for a session slot taken ACROSS PROCESSES, or ``(None, None, holders)``
    naming each slot's holder (CONCURRENCY_AUDIT R11: the budget counted one process, while host
    CLIs open their own sessions). A slot is a `flock` on ``ssh_slots/<ip>/<n>.lock`` in the
    store: the kernel frees it when its holder dies, so a crash never keeps a vty line. Called
    under ``_sessions_mu``; a slot this process holds for a session no longer counted (a test
    clearing the count, a lost close) is released first."""
    import fcntl

    for (sip, n), (fd, sid) in list(_slots.items()):
        if sip == ip and sid not in _sessions.get(ip, {}):
            _slots.pop((sip, n), None)
            try:
                os.close(fd)
            except OSError:
                pass
    folder = _slot_dir(ip)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    holders = []
    for n in range(budget):
        fd = os.open(os.path.join(folder, f"{n}.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                said = os.pread(fd, 300, 0).decode("utf-8", "replace").strip()
            finally:
                os.close(fd)
            holders.append(said or "a process that recorded nothing")
            continue
        os.ftruncate(fd, 0)
        os.pwrite(fd, f"{owner} (pid {os.getpid()})".encode(), 0)
        return n, fd, []
    return None, None, holders


def _free_slot(ip: str, sid: int) -> None:
    for key, (fd, held_sid) in list(_slots.items()):
        if key[0] == ip and held_sid == sid:
            _slots.pop(key, None)
            try:
                os.ftruncate(fd, 0)
                os.close(fd)
            except OSError:
                pass


def open_ssh(params: dict, *, owner: str = "", pool: dict = None, pool_lock=None):
    """Open ONE SSH session, counted, attributed, and within the budget.

    The only place in the program a Netmiko session is opened (a test holds
    it to that). Closing it with ``disconnect()`` removes it from the count.
    """
    ip = params["ip"]
    owner = owner or _caller_label()
    budget = session_budget(ip)
    with _sessions_mu:
        held = _sessions.setdefault(ip, {})
        if len(held) >= budget["budget"]:
            holders = ", ".join(sorted(i["owner"] for i in held.values())) or "none"
            raise SessionBudgetExceeded(
                f"refusing to open another SSH session to {ip}: this tool already "
                f"holds {len(held)} ({holders}), and its budget is {budget['budget']} "
                f"of the device's {budget['lines']} vty line(s) ({budget['source']}), "
                f"keeping {RESERVED_FOR_PEOPLE} free for a person. Wait for one to "
                "finish; if none is running, a session has leaked (register C97).")
        # ACROSS PROCESSES (R11): a host CLI's sessions count against the same budget.
        n, fd, holders = _take_slot(ip, budget["budget"], owner)
        if n is None:
            raise SessionBudgetExceeded(
                f"refusing to open another SSH session to {ip}: every one of its "
                f"{budget['budget']} session slot(s) is held ({'; '.join(holders)}), its budget "
                f"of the device's {budget['lines']} vty line(s) ({budget['source']}), "
                f"keeping {RESERVED_FOR_PEOPLE} free for a person. Wait for one to finish.")
        _sid_counter[0] += 1
        sid = _sid_counter[0]
        _slots[(ip, n)] = (fd, sid)
        now = time.time()
        held[sid] = {"owner": owner, "opened": now, "last_used": now,
                     "pool": pool, "pool_lock": pool_lock, "conn": None}
    try:
        # Looked up at CALL time, like the callers that used to open their own
        # sessions did, so a fake installed at the Netmiko boundary reaches here.
        import netmiko

        # The connect bound is CHOSEN here, from a measurement (C205): it was
        # Netmiko's default 10 s, set by nothing, while s3's connect measured
        # 13.7 s, so a Save All gave up on a device that was answering. A
        # caller's own value wins.
        #
        # The session logs in only after floor_reads(): Netmiko's login and
        # session preparation read with its own 10 s and 20 s bounds, and at
        # 06:03 on 2026-10-01 s1, s3 and s4 failed inside them.
        conn = netmiko.ConnectHandler(**{"conn_timeout": CONNECT_TIMEOUT_S,
                                         "auto_connect": False, **params})
        floor_reads(conn)
        login = getattr(conn, "_open", None)
        if callable(login):
            try:
                login()
            except Exception:
                try:
                    conn.disconnect()
                except Exception:                       # noqa: BLE001
                    pass
                raise
    except Exception:
        _drop(ip, sid, "connect failed")
        raise
    with _sessions_mu:
        info = _sessions.get(ip, {}).get(sid)
        if info is not None:
            info["conn"] = conn
        count = len(_sessions.get(ip, {}))
    original = conn.disconnect

    def _disconnect(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        finally:
            _drop(ip, sid, "closed")

    conn.disconnect = _disconnect
    conn._nmas_session = (ip, sid)
    _guard_writes(conn, ip)
    logger.info("ssh: opened %s for %s (%d of %d this tool may hold; %d vty line(s), "
                "%d kept for a person)", ip, owner, count, budget["budget"],
                budget["lines"], RESERVED_FOR_PEOPLE)
    return conn


class UnheldDeviceWrite(RuntimeError):
    """A write on a session whose thread does not hold the device (C101)."""


#: Methods that change a device whatever their arguments.
_WRITE_METHODS = ("send_config_set", "send_config_from_file", "save_config",
                  "config_mode", "commit")
#: Methods that change a device when the command is not a read.
_COMMAND_METHODS = ("send_command", "send_command_timing", "send_command_expect")
_MULTILINE_METHODS = ("send_multiline", "send_multiline_timing")


def _guard_writes(conn, ip: str) -> None:
    """The lock's population, enforced where the write HAPPENS (C101).

    C98's lock was taken by a LIST of functions, so a new path that changed
    a device and forgot it raced silently, and five pre-existing ones never
    took it (Save Device Config's `write memory`, the bulk operations,
    `/run_command`, bulk reload). Every session comes through this opener,
    and the ONE read-only allowlist (C61) already says what a read is, so:
    a command it refuses, or a config or save call, is sent only while this
    thread holds the device. A path that forgets fails on first use, loudly.
    The refusal names the verb, never the command: a command can carry a
    secret (a rotation's password line)."""
    from modules.nsot import device_ops
    from modules.readonly_commands import refusal

    def refuse(what):
        raise UnheldDeviceWrite(
            f"refusing to send {what} to {ip}: it is not a read, and this operation "
            "does not hold the device (register C98, C101). Every change to a device "
            "holds it from apply to commit; a path that does not is refused here, on "
            "first use, rather than racing another operation.")

    def verb(cmd) -> str:
        words = str(cmd or "").split()
        return repr(words[0]) if words else "an empty line"

    def writing(name, original):
        def guarded(*args, **kwargs):
            if not device_ops.may_write(ip):
                refuse(f"{name}()")
            return original(*args, **kwargs)
        return guarded

    def commanding(original):
        def guarded(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("command_string", "")
            if refusal(cmd) and not device_ops.may_write(ip):
                refuse(verb(cmd))
            return original(*args, **kwargs)
        return guarded

    def multiline(original):
        def guarded(*args, **kwargs):
            cmds = args[0] if args else kwargs.get("commands", [])
            for cmd in cmds or []:
                cmd = cmd[0] if isinstance(cmd, (list, tuple)) else cmd
                if refusal(cmd) and not device_ops.may_write(ip):
                    refuse(verb(cmd))
            return original(*args, **kwargs)
        return guarded

    for name in _WRITE_METHODS:
        original = getattr(conn, name, None)
        if callable(original):
            setattr(conn, name, writing(name, original))
    for name in _COMMAND_METHODS:
        original = getattr(conn, name, None)
        if callable(original):
            setattr(conn, name, commanding(original))
    for name in _MULTILINE_METHODS:
        original = getattr(conn, name, None)
        if callable(original):
            setattr(conn, name, multiline(original))


def _drop(ip: str, sid: int, why: str) -> None:
    with _sessions_mu:
        info = _sessions.get(ip, {}).pop(sid, None)
        left = len(_sessions.get(ip, {}))
        _free_slot(ip, sid)
    if info is not None:
        logger.info("ssh: %s %s for %s after %.0fs (%d still held)", why, ip,
                    info["owner"], time.time() - info["opened"], left)


def _touch(conn) -> None:
    ip_sid = getattr(conn, "_nmas_session", None)
    if ip_sid:
        with _sessions_mu:
            info = _sessions.get(ip_sid[0], {}).get(ip_sid[1])
            if info is not None:
                info["last_used"] = time.time()


def held_sessions() -> dict:
    """``{ip: {"held": n, "budget": b, "lines": l, "sessions": [...]}}``: what
    this process holds now. Read by job health; names owners, never secrets."""
    now = time.time()
    with _sessions_mu:
        snapshot = {ip: [dict(i) for i in held.values()] for ip, held in _sessions.items()
                    if held}
    out = {}
    for ip, infos in snapshot.items():
        b = session_budget(ip)
        out[ip] = {"held": len(infos), "budget": b["budget"], "lines": b["lines"],
                   "sessions": [{"owner": i["owner"], "age_s": round(now - i["opened"]),
                                 "idle_s": round(now - i["last_used"]),
                                 "pooled": i["pool"] is not None} for i in infos]}
    return out


def reap_idle(max_idle: float = IDLE_REAP_SECONDS) -> int:
    """Close long-lived pools' sessions idle longer than *max_idle*.

    Only a POOLED session is reaped: a per-operation one is closed by its
    operation. A session in use (its device's send lock held) or whose pool
    is busy is skipped this round, never waited for, so the reaper cannot
    deadlock against a caller holding the pool lock then the send lock."""
    now = time.time()
    with _sessions_mu:
        idle = [(ip, sid, dict(i)) for ip, held in _sessions.items()
                for sid, i in held.items()
                if i["pool"] is not None and i["conn"] is not None
                and now - i["last_used"] > max_idle]
    closed = 0
    for ip, _sid, info in idle:
        send_lock = get_device_send_lock(ip)
        if not send_lock.acquire(blocking=False):
            continue
        try:
            pool_lock = info["pool_lock"]
            if pool_lock is not None and not pool_lock.acquire(blocking=False):
                continue
            try:
                entry = info["pool"].get(ip)
                raw = (object.__getattribute__(entry, "_conn")
                       if isinstance(entry, LockedConnection) else entry)
                if raw is info["conn"]:
                    info["pool"].pop(ip, None)
            finally:
                if pool_lock is not None:
                    pool_lock.release()
            try:
                logger.info("ssh: closing %s for %s, idle %.0fs", ip, info["owner"],
                            now - info["last_used"])
                info["conn"].disconnect()
                closed += 1
            except Exception:                  # noqa: BLE001
                logger.debug("ssh: idle close of %s failed", ip, exc_info=True)
        finally:
            send_lock.release()
    return closed

# This module provides two connection styles:

#   `with_temp_connection`: create a short-lived connection, run a
#   provided callable, then disconnect.

#   `get_persistent_connection` / `close_persistent_connection`: keep
#   a lightweight persistent connection per-IP for status checks and
#   infrequent operations


def verify_device_connection(
    ip: str, username: str, password: str, secret: str, device_type: str
) -> str:
    """
    Attempts to connect to a device using Netmiko and returns the hostname prompt.
    Raises exception if connection fails.
    """
    conn = open_ssh(connection_params(
        {"device_type": device_type, "ip": ip, "username": username},
        password=password, secret=secret), owner="verify_device_connection")
    try:
        conn.enable()
        prompt = conn.find_prompt()
    finally:
        # It returned before disconnecting when enable() or find_prompt()
        # raised, leaving the session open until the device timed it out (C97).
        conn.disconnect()
    # Extract hostname from prompt (e.g., 'R1#' -> 'R1')
    hostname = prompt.rstrip("#>").strip()
    return hostname


def is_device_online(ip: str) -> bool:
    """Returns True if device at IP responds to ping or accepts TCP on port 22.

    ping3 needs a raw ICMP socket, which requires root/CAP_NET_RAW on Linux.
    When that's unavailable (e.g. unprivileged systemd service) every ping
    raises PermissionError, so fall back to a plain TCP connect to the SSH
    port, which is what this app actually needs reachable anyway.
    """
    from ping3 import ping

    try:
        response = ping(ip, timeout=2, unit="ms")
        if response and response > 0:
            return True
    except Exception:
        logger.debug("Ping error for %s", ip, exc_info=True)

    import socket

    try:
        with socket.create_connection((ip, 22), timeout=2):
            return True
    except Exception:
        logger.debug("TCP:22 check failed for %s", ip, exc_info=True)
        return False


def session_reaper(interval: int = 5) -> None:
    """Background thread: close idle pooled sessions (C97).

    It was `ping_worker`, which also probed every device of the active list
    each cycle and wrote one probe's answer into the status cache. Probing
    moved to the reachability reader (C92), which counts consecutive misses
    and probes every list; only the reaping stays here."""

    def worker():
        while True:
            # The long-lived pools' idle sessions are closed by the tool, not
            # left for the device's own ten-minute timeout (C97).
            try:
                reap_idle()
            except Exception:
                logger.exception("ssh: idle reaper failed")
            time.sleep(interval)

    t = threading.Thread(target=worker, daemon=True, name="session-reaper")
    t.start()


def get_persistent_connection(
    dev: dict, connections: dict, lock: threading.Lock
) -> 'LockedConnection':
    """Return a thread-safe LockedConnection for the device.

    The pool lock (`lock`) guards the connections dict.  The per-device
    send lock is acquired while checking liveness and during reconnect so
    that a health-check never races with an in-flight send_command from
    another thread.
    """
    ip        = dev["ip"]
    send_lock = get_device_send_lock(ip)
    with lock:
        with send_lock:
            conn = connections.get(ip)
            # Unwrap LockedConnection to get the raw ConnectHandler for is_alive
            raw = object.__getattribute__(conn, '_conn') if isinstance(conn, LockedConnection) else conn
            # A session whose read failed is replaced, never read again (C272):
            # its channel may still carry that read's output.
            from modules.config_read import spent
            if raw and spent(raw):
                logger.info("connection: replacing %s's pooled session: %s", ip, spent(raw))
            if not raw or spent(raw) or not getattr(raw, "is_alive", lambda: True)():
                try:
                    if raw:
                        raw.disconnect()
                except Exception:
                    pass
                raw = open_ssh(stored_connection_params(dev), pool=connections,
                               pool_lock=lock)
                try:
                    raw.enable()
                except Exception:
                    raw.disconnect()
                    raise
                connections[ip] = LockedConnection(raw, send_lock)
            elif not isinstance(conn, LockedConnection):
                connections[ip] = LockedConnection(raw, send_lock)
        return connections[ip]


def close_persistent_connection(
    ip: str, connections: dict, lock: threading.Lock
) -> None:
    #Closes and removes persistent Netmiko connection for given IP.
    with lock:
        conn = connections.pop(ip, None)
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


def with_temp_connection(dev: dict, func) -> any:
    #Creates a temporary Netmiko connection to run func(conn), then disconnects.
    try:
        logger.debug(
            "Attempting connection to %s as %s", dev.get("ip"), dev.get("username")
        )
        conn = open_ssh(stored_connection_params(dev))
        logger.debug("Connected to %s", dev.get("ip"))
        try:
            conn.enable()
            return func(conn)
        finally:
            try:
                conn.disconnect()
                logger.debug("Disconnected from %s", dev.get("ip"))
            except Exception as e:
                logger.debug("Disconnect error for %s: %s", dev.get("ip"), e)
    except Exception:
        logger.exception("Connection to %s failed", dev.get("ip"))
        raise
