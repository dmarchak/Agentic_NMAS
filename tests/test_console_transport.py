"""The console transports (modules/nsot/console_transport.py; docs/LAB9_PLAN.md section 8, O2, the
operator's cut: the command bridge and raw TCP through an SSH jump), against FAKE console
servers on loopback (tests/console_fakes.py), IPv4 and IPv6 each:

- bytes written are exactly the plan's and zero outside it, telnet negotiation arriving
  included (each fake console counts every byte it received);
- the bridge's exec command is exactly the container's name; a name the wrapper's own rule
  refuses is refused before anything connects; a name the console host does not allow comes
  back as the wrapper's refusal and its exit status;
- the server's host key: first contact kept, a changed key refused BEFORE the client key is
  offered, naming both fingerprints (the fake server records every sign-in it was offered);
- one session per console port across processes, refused naming the holder, never queued;
  closing always gives the port up, whatever failed;
- the connect and read bounds hold.

The driver loop's own cases are tests/test_console_run_plan.py."""

import os
import re
import socket
import subprocess
import sys
import time

import paramiko
import pytest

from modules import host_keys as HK
from modules.nsot import console_keys
from modules.nsot import console_profiles as P
from modules.nsot import console_session as S
from modules.nsot import console_transport as T
from tests.console_fakes import LOOPBACK, Console, RawServer, Silent, SshServer
from tests.test_console_run_plan import NEGOTIATE
from tests.test_console_session import PNP, SURVEY, session_fixture

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWITCH = P.load("cisco_ios_switch")
REF = "console-lab"
USER = "mercury"
NAME = "s5"
PORT_ID = 41
FAMILIES = pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6],
                                   ids=["ipv4", "ipv6"])
PLAN_BYTES = b"\renable\rdir nvram:\r"


@pytest.fixture(scope="module")
def host_keys():
    """Two RSA host keys, generated for this run: the server's, and a stranger's."""
    return [paramiko.RSAKey.generate(2048) for _ in range(2)]


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr("modules.config.DATA_DIR", str(data))
    monkeypatch.setattr("modules.credentials._FILE", str(data / "credential_profiles.json"))
    return data


@pytest.fixture
def client_key():
    """The key Mercury holds for the console server, generated and stored by reference."""
    return console_keys.generate(REF, username=USER, wrapper_path="/usr/local/bin/bridge",
                                 allowlist_path="/etc/nmas/allow")


def console():
    _sends, answers = session_fixture()
    return Console(greeting=PNP, answers=answers, negotiate=NEGOTIATE)


@pytest.fixture
def servers():
    made = []

    def start(cls, *args, **kwargs):
        server = cls(*args, **kwargs)
        made.append(server)
        return server

    yield start
    for s in made:
        s.close()


def ssh(servers, host_key, client_key, family=socket.AF_INET, allow=(NAME,)):
    return servers(SshServer, host_key, user=USER, client_public=client_key["public_key"],
                   allow=allow, make=console, family=family)


def session(settle=0.05, quiet=1.0, timeout=10.0):
    return S.ConsoleSession(SWITCH, SURVEY, start=time.monotonic(), settle_s=settle,
                            quiet_s=quiet, step_timeout_s=timeout, values={})


def run(transport):
    with transport:
        return T.run_plan(transport, session(), poll_s=0.02, bound_s=40.0)


def lock_free(port_id=PORT_ID) -> bool:
    lock = T.PortLock(port_id, "test:probe")
    try:
        lock.acquire()
    except T.PortBusy:
        return False
    lock.release()
    return True


def bridge(server, **over):
    args = dict(host=server.host, container=NAME, credential_ref=REF, ssh_port=server.port,
                owner="test:bridge", connect_timeout=5)
    args.update(over)
    return T.CommandBridge(PORT_ID, **args)


def raw(server, **over):
    args = dict(host=server.host, tcp_port=server.port, owner="test:raw", connect_timeout=5)
    args.update(over)
    return T.RawTcp(PORT_ID, **args)


# ── Exactly the plan's bytes, over each driver ───────────────────────────────────────────

@FAMILIES
def test_raw_tcp_writes_exactly_the_plans_bytes(servers, family):
    server = servers(RawServer, console, family=family)
    t = raw(server)
    result = run(t)
    assert (result.outcome, result.reason) == ("done", "ended in priv_exec")
    finished = server.finished()
    assert finished.received == PLAN_BYTES
    assert t.bytes_written == result.bytes_written == len(PLAN_BYTES) == 19
    assert result.attach_state == P.PRESS_RETURN
    assert lock_free()


@FAMILIES
def test_the_command_bridge_runs_the_name_and_writes_exactly_the_plans_bytes(
        servers, host_keys, client_key, family):
    server = ssh(servers, host_keys[0], client_key, family)
    result = run(bridge(server))
    assert result.outcome == "done", result.reason
    assert server.commands == [NAME.encode()]
    assert server.auth == [(USER, "ssh-ed25519", client_key["public_key"].split()[1])]
    assert server.ptys == 0
    finished = server.finished()
    assert finished.received == PLAN_BYTES
    assert lock_free()


@FAMILIES
def test_raw_tcp_through_a_jump_writes_exactly_the_plans_bytes(servers, host_keys, client_key,
                                                               family):
    console_server = servers(RawServer, console, family=family)
    jump = ssh(servers, host_keys[0], client_key, family, allow=())
    t = raw(console_server, jump_host=jump.host, ssh_port=jump.port, credential_ref=REF)
    result = run(t)
    assert result.outcome == "done", result.reason
    assert jump.destinations == [(console_server.host, console_server.port)]
    assert jump.commands == [] and jump.ptys == 0
    finished = console_server.finished()
    assert finished.received == PLAN_BYTES
    assert jump.origins[0][0] == LOOPBACK[family]          # where the SSH connection left from


@FAMILIES
def test_the_raw_console_receives_nothing_when_the_plan_sends_nothing(servers, family):
    """Telnet negotiation and a whole greeting arrive; a plan with no steps writes 0 bytes."""
    server = servers(RawServer, console, family=family)
    t = raw(server)
    with t:
        result = T.run_plan(t, S.ConsoleSession(
            SWITCH, S.Plan(steps=(), final=(P.PRESS_RETURN,)), start=time.monotonic(),
            settle_s=0.05, quiet_s=1.0, step_timeout_s=10.0, values={}), poll_s=0.02,
            bound_s=40.0)
    assert result.outcome == "done" and t.bytes_written == 0
    finished = server.finished()
    assert finished.received == b""


# ── The bridge's name ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["s5; reboot", "s5 && id", "s5|sh", "$(id)", "'s5'", "s5 x",
                                  "s5\n", "--privileged", "../s5", "", "a" * 64, None])
def test_a_name_the_wrapper_refuses_is_refused_before_connecting(servers, host_keys,
                                                                client_key, name):
    server = ssh(servers, host_keys[0], client_key)
    t = bridge(server, container=name)
    with pytest.raises(T.ConsoleRefused, match="refused before connecting"):
        t.open()
    assert server.accepted == 0 and server.commands == []
    assert lock_free() and not t.lock.held()


def test_a_name_the_console_host_does_not_allow_comes_back_as_its_refusal(servers, host_keys,
                                                                        client_key):
    server = ssh(servers, host_keys[0], client_key, allow=("s1",))
    t = bridge(server)
    result = run(t)
    assert result.outcome == "closed"
    assert result.reason == (f"console-server port {PORT_ID} ('s5' on {server.host} port "
                             f"{server.port}) closed the bridge (exit 2): nmas-console-bridge: "
                             "refused: 's5' is not on the allowlist")
    assert t.bytes_written == 0 and server.commands == [b"s5"]


# ── The server's host key ────────────────────────────────────────────────────────────────

@FAMILIES
def test_first_contact_keeps_the_key_and_a_changed_one_is_refused_before_the_key_is_offered(
        servers, host_keys, client_key, family):
    first = ssh(servers, host_keys[0], client_key, family)
    run(bridge(first))
    held = HK.held(first.host)
    assert held["fingerprint"] == HK.fingerprint_of(host_keys[0].asbytes())
    assert held["how"] == HK.FIRST_CONTACT and held["port"] == first.port
    stranger = ssh(servers, host_keys[1], client_key, family)
    with pytest.raises(HK.HostKeyRefused) as exc:
        bridge(stranger).open()
    words = str(exc.value)
    assert HK.fingerprint_of(host_keys[0].asbytes()) in words
    assert HK.fingerprint_of(host_keys[1].asbytes()) in words
    assert stranger.accepted == 1 and stranger.auth == [] and stranger.commands == []
    assert lock_free()


def test_who_met_the_key_is_the_sessions_owner(servers, host_keys, client_key):
    """The record says whose session met the key (the mutation run of 2026-10-22: the owner
    dropped, or replaced by the caller's code, survived)."""
    server = ssh(servers, host_keys[0], client_key)
    run(bridge(server, owner="operator@example.com (survey)"))
    assert HK.held(server.host)["kept_by"] == "no verified person (operator@example.com (survey))"


def test_an_unnamed_caller_is_named_by_its_code(servers, host_keys, client_key):
    from modules import connection
    server = ssh(servers, host_keys[0], client_key)
    username, pkey = console_keys.load(REF)
    t = connection.open_pinned_transport(server.host, server.port, username=username, pkey=pkey,
                                         timeout=5)
    t.close()
    # The code is `module:function`: this test (as the runner imported it, `tests.test_…` or
    # `test_…`), or mutmut's trampoline when mutmut stands between them (its copy calls the
    # function from there), never a stand-in (the mutation run of 2026-10-22: the default
    # owner made "XXXX" survived).
    kept_by = HK.held(server.host)["kept_by"]
    assert re.fullmatch(r"no verified person \([A-Za-z_][\w.]*:[A-Za-z_]\w*\)", kept_by)
    assert kept_by.endswith((":test_an_unnamed_caller_is_named_by_its_code)",
                             "mutmut.mutation.trampoline:trampoline)")), kept_by


def test_a_server_that_asks_for_a_second_factor_is_refused(servers, host_keys, client_key):
    """The key is accepted only in part (the server wants another factor): paramiko returns
    without raising, and the opener refuses, naming the server and the user."""
    server = servers(SshServer, host_keys[0], user=USER, client_public=client_key["public_key"],
                     allow=(NAME,), make=console, partial=True)
    t = bridge(server)
    with pytest.raises(paramiko.AuthenticationException) as exc:
        t.open()
    assert str(exc.value) == (f"{server.host} port {server.port} did not accept the key for "
                              "'mercury'")
    assert server.commands == [] and lock_free()


@pytest.fixture
def recorded(monkeypatch):
    """Every bound handed to the socket and to paramiko, by call, in order."""
    seen = []
    real_connect = socket.create_connection

    def connect(address, timeout=None, *a, **k):
        seen.append(("connect", timeout))
        return real_connect(address, timeout, *a, **k)

    def wrap(name, record):
        real = getattr(paramiko.Transport, name)

        def recording(self, *a, **k):
            seen.append(record(self, *a, **k))
            return real(self, *a, **k)
        monkeypatch.setattr(paramiko.Transport, name, recording)

    monkeypatch.setattr(socket, "create_connection", connect)
    wrap("start_client", lambda self, event=None, timeout=None: (
        "start_client", timeout, self.banner_timeout))
    wrap("auth_publickey", lambda self, *a, **k: ("auth", self.auth_timeout))
    wrap("open_session", lambda self, *a, **k: ("open_session", k.get("timeout")))
    wrap("open_channel", lambda self, kind, *a, **k: (kind, k.get("timeout")))
    return seen


def test_the_bridge_bounds_every_wait_with_its_connect_bound(servers, host_keys, client_key,
                                                            recorded):
    server = ssh(servers, host_keys[0], client_key)
    run(bridge(server, connect_timeout=2.5))
    assert recorded == [("connect", 2.5), ("start_client", 2.5, 2.5), ("auth", 2.5),
                        ("open_session", 2.5), ("session", 2.5)]


def test_the_jump_bounds_every_wait_with_its_connect_bound(servers, host_keys, client_key,
                                                          recorded):
    target = servers(RawServer, console)
    jump = ssh(servers, host_keys[0], client_key, allow=())
    run(raw(target, jump_host=jump.host, ssh_port=jump.port, credential_ref=REF,
            connect_timeout=2.5))
    assert recorded[:4] == [("connect", 2.5), ("start_client", 2.5, 2.5), ("auth", 2.5),
                            ("direct-tcpip", 2.5)]


def test_the_same_key_signs_in_again(servers, host_keys, client_key):
    server = ssh(servers, host_keys[0], client_key)
    assert run(bridge(server)).outcome == "done"
    assert run(bridge(server)).outcome == "done"
    assert len(server.auth) == 2


def test_the_jump_hosts_key_is_pinned_the_same_way(servers, host_keys, client_key):
    target = servers(RawServer, console)
    jump = ssh(servers, host_keys[0], client_key, allow=())
    run(raw(target, jump_host=jump.host, ssh_port=jump.port, credential_ref=REF))
    stranger = ssh(servers, host_keys[1], client_key, allow=())
    with pytest.raises(HK.HostKeyRefused):
        raw(target, jump_host=stranger.host, ssh_port=stranger.port, credential_ref=REF).open()
    assert stranger.auth == [] and stranger.destinations == []


def test_a_key_the_server_does_not_accept_is_refused_and_the_port_freed(servers, host_keys,
                                                                       client_key):
    other = {"public_key": console_keys.generate(
        "other", username=USER, wrapper_path="/b", allowlist_path="/a")["public_key"]}
    server = ssh(servers, host_keys[0], other)
    t = bridge(server)
    with pytest.raises(paramiko.AuthenticationException):
        t.open()
    assert [a[0] for a in server.auth] == [USER] and server.commands == []
    assert lock_free()


def test_no_stored_key_is_refused_before_connecting(servers, host_keys, client_key):
    server = ssh(servers, host_keys[0], client_key)
    with pytest.raises(console_keys.ConsoleKeyUnavailable, match="'absent'"):
        bridge(server, credential_ref="absent").open()
    assert server.accepted == 0 and lock_free()


def test_a_jump_without_a_credential_reference_is_refused(servers):
    target = servers(RawServer, console)
    with pytest.raises(T.ConsoleRefused, match="needs a credential reference"):
        raw(target, jump_host="::1", ssh_port=22).open()
    assert target.accepted == 0 and lock_free()


# ── One session per console port ─────────────────────────────────────────────────────────

def test_a_held_port_is_refused_naming_the_holder_and_nothing_connects(servers):
    server = servers(RawServer, console)
    holder = T.PortLock(PORT_ID, "operator@example.com (survey; test)")
    holder.acquire()
    try:
        with pytest.raises(T.PortBusy) as exc:
            raw(server).open()
        assert str(exc.value) == (
            f"console-server port {PORT_ID} is held by operator@example.com (survey; test) "
            f"(pid {os.getpid()}), so test:raw was refused (one session per console port; "
            "never queued)")
        assert server.accepted == 0
    finally:
        holder.release()
    assert run(raw(server)).outcome == "done"


def test_another_ports_session_is_not_held_up(servers):
    server = servers(RawServer, console)
    holder = T.PortLock(PORT_ID + 1, "test:other")
    holder.acquire()
    try:
        assert run(raw(server)).outcome == "done"
    finally:
        holder.release()


def test_a_port_held_by_another_process_is_refused(servers):
    """Across processes: a child holds the port through the same lock, and this process is
    refused, naming it; once the child ends, the kernel has given the port up."""
    from modules import config
    server = servers(RawServer, console)
    code = ("import sys; from modules import config; config.DATA_DIR = sys.argv[1]; "
            "from modules.nsot import console_transport as T; "
            f"lock = T.PortLock({PORT_ID}, 'a child (test)'); lock.acquire(); "
            "print('held', flush=True); sys.stdin.read()")
    child = subprocess.Popen([sys.executable, "-c", code, config.DATA_DIR], cwd=ROOT,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "held"
        with pytest.raises(T.PortBusy, match=r"held by a child \(test\) \(pid "
                                             f"{child.pid}\\)"):
            raw(server).open()
    finally:
        child.communicate("", timeout=30)
    assert lock_free() and server.accepted == 0


def test_the_lock_file_is_owner_only_and_empty_when_released(store):
    lock = T.PortLock(PORT_ID, "test:mode")
    lock.acquire()
    path = lock.path()
    assert path == os.path.join(str(store), "console_ports", f"{PORT_ID}.lock")
    assert open(path).read() == f"test:mode (pid {os.getpid()})"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.stat(os.path.dirname(path)).st_mode & 0o777 == 0o700
    lock.release()
    assert open(path).read() == ""
    lock.release()                                   # a second release does nothing


def test_a_longer_record_a_crash_left_is_replaced_whole(store):
    lock = T.PortLock(PORT_ID, "test:after")
    os.makedirs(os.path.dirname(lock.path()), mode=0o700, exist_ok=True)
    with open(lock.path(), "w") as fh:
        fh.write("a much longer record that a process which crashed left behind it")
    lock.acquire()
    try:
        assert open(lock.path()).read() == f"test:after (pid {os.getpid()})"
    finally:
        lock.release()


def test_a_holder_record_cut_inside_a_character_still_names_the_holder():
    """The refusal reads the first 300 bytes of the holder's record: a two-byte character cut
    there reads as U+FFFD, never as a refusal that fails to say who holds the port (the
    mutation run of 2026-10-22: the decode's error handler and the 300 survived)."""
    holder = T.PortLock(PORT_ID, "x" + "é" * 200)
    holder.acquire()
    try:
        with pytest.raises(T.PortBusy) as exc:
            T.PortLock(PORT_ID, "test:second").acquire()
    finally:
        holder.release()
    assert f"is held by x{'é' * 149}�, so test:second was refused" in str(exc.value)


def test_one_lock_object_cannot_be_taken_twice():
    lock = T.PortLock(PORT_ID, "test:twice")
    lock.acquire()
    try:
        with pytest.raises(T.PortBusy, match="already held by this session"):
            lock.acquire()
    finally:
        lock.release()


@pytest.mark.parametrize("port_id", [0, -1, "41", 4.1, True, None])
def test_a_port_id_that_is_not_a_netbox_id_is_refused(port_id):
    with pytest.raises(T.ConsoleRefused, match="positive number"):
        T.PortLock(port_id, "test")


# ── Closing always gives the port up ─────────────────────────────────────────────────────

def test_an_error_inside_the_session_still_frees_the_port(servers):
    server = servers(RawServer, console)
    with pytest.raises(ZeroDivisionError):
        with raw(server):
            assert not lock_free()
            raise ZeroDivisionError
    assert lock_free()


def test_a_failed_connect_frees_the_port(servers):
    server = servers(RawServer, console)
    port = server.port
    server.close()                                   # nothing listens there now
    with pytest.raises(OSError):
        raw(server, tcp_port=port).open()
    assert lock_free()


def test_open_twice_is_refused_and_close_twice_is_harmless(servers):
    server = servers(RawServer, console)
    t = raw(server)
    t.open()
    with pytest.raises(T.ConsoleRefused, match="already open"):
        t.open()
    t.close()
    t.close()
    assert lock_free()


def test_reading_or_writing_a_closed_transport_is_refused(servers):
    server = servers(RawServer, console)
    t = raw(server)
    for act in (lambda: t.read(10, 0.1), lambda: t.write(b"\r")):
        with pytest.raises(T.ConsoleClosed, match="is not open"):
            act()
    with t:
        pass
    with pytest.raises(T.ConsoleClosed, match="is not open"):
        t.write(b"\r")
    assert t.bytes_written == 0


# ── The interface ────────────────────────────────────────────────────────────────────────

@FAMILIES
def test_a_write_sends_every_byte_and_counts_them(servers, family):
    server = servers(RawServer, lambda: Console(), family=family)
    with raw(server) as t:
        assert t.write(b"abc\r") == 4
        assert t.write(b"x") == 1
        assert t.bytes_written == 5
    finished = server.finished()
    assert finished.received == b"abc\rx"


@pytest.mark.parametrize("data", [b"", "text\r", bytearray(b"\r"), None])
def test_a_write_that_is_not_bytes_is_refused_and_sends_nothing(servers, data):
    server = servers(RawServer, lambda: Console())
    with raw(server) as t:
        with pytest.raises(ValueError, match="a console write is bytes"):
            t.write(data)
        assert t.bytes_written == 0
    finished = server.finished()
    assert finished.received == b""


def test_a_read_gives_at_most_max_bytes(servers):
    server = servers(RawServer, lambda: Console(greeting=b"0123456789"))
    with raw(server) as t:
        first = t.read(4, 2.0)
        assert first == b"0123"


def test_a_closed_far_end_is_said_so(servers):
    server = servers(RawServer, lambda: Console(greeting=b"bye"))
    with raw(server) as t:
        assert t.read(10, 2.0) == b"bye"
        server.clients[0].shutdown(socket.SHUT_RDWR)
        with pytest.raises(T.ConsoleClosed, match=f"console-server port {PORT_ID} "
                                                  r"\(127.0.0.1 port \d+\) closed the console"):
            for _ in range(50):
                t.read(10, 0.1)


# ── The bounds ───────────────────────────────────────────────────────────────────────────

def test_a_quiet_console_read_returns_nothing_within_its_wait(servers):
    server = servers(RawServer, lambda: Console())
    with raw(server) as t:
        began = time.monotonic()
        assert t.read(10, 0.3) == b""
        took = time.monotonic() - began
    assert 0.25 <= took < 2.0, took


def test_an_ssh_server_that_never_answers_is_bounded(servers, client_key):
    silent = servers(Silent)
    began = time.monotonic()
    # paramiko 2.12 says the banner never came as "No existing session" when its wait ends.
    with pytest.raises(paramiko.SSHException, match="banner|No existing session"):
        bridge(silent, connect_timeout=1).open()
    took = time.monotonic() - began
    assert 0.9 <= took < 6.0, took                  # the 1 s bound, not the 35 s default
    assert lock_free()


def test_the_default_connect_bound_is_the_device_connect_bound():
    from modules import connection
    assert T.connect_bound() == connection.CONNECT_TIMEOUT_S == 35


def test_the_default_connect_bound_is_used_when_none_is_given(servers, monkeypatch):
    server = servers(RawServer, console)
    seen = []
    real = socket.create_connection

    def recording(address, timeout=None, *a, **k):
        seen.append(timeout)
        return real(address, timeout, *a, **k)

    monkeypatch.setattr(T.socket, "create_connection", recording)
    with raw(server, connect_timeout=None):
        pass
    with raw(server, connect_timeout=2.5):
        pass
    assert seen == [35, 2.5]


# ── Hosts ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("host,canonical", [
    ("192.0.2.10", "192.0.2.10"), ("2001:db8::1", "2001:db8::1"),
    ("[2001:db8::1]", "2001:db8::1"), ("2001:DB8:0:0::1", "2001:db8::1"),
    ("::1", "::1"), ("fe80::1%eth0", "fe80::1%eth0"),
    ("Console-1.Example.NET", "console-1.example.net"), ("console.example.", "console.example"),
])
def test_a_host_is_keyed_canonical(host, canonical):
    assert T.canonical_host(host) == canonical


@pytest.mark.parametrize("host", ["", None, "[192.0.2.1]", "1.2.3", "300.1.1.1", "a b",
                                  "-bad.example", "x" * 254, "bad_.example", "[nope]",
                                  "2001:db8::zz", "a..b"])
def test_a_host_that_is_neither_is_refused(host):
    with pytest.raises(T.ConsoleRefused, match="is not an IPv4 or IPv6 address or a hostname"):
        T.canonical_host(host)


@pytest.mark.parametrize("port", [0, 65536, -1, "22", True, None, 2.0])
def test_a_port_number_out_of_range_is_refused(port):
    with pytest.raises(T.ConsoleRefused, match="is not a port number"):
        T.check_tcp_port("the port", port)
    assert T.check_tcp_port("the port", 65535) == 65535 and T.check_tcp_port("p", 1) == 1


def test_a_bad_console_port_is_refused_before_holding(servers):
    with pytest.raises(T.ConsoleRefused, match="the console's TCP port 0"):
        T.RawTcp(PORT_ID, host="::1", tcp_port=0).open()
    with pytest.raises(T.ConsoleRefused, match="the jump host's SSH port 70000"):
        T.RawTcp(PORT_ID, host="::1", tcp_port=5000, jump_host="::1", ssh_port=70000,
                 credential_ref=REF).open()
    with pytest.raises(T.ConsoleRefused, match="the console server's SSH port 0"):
        T.CommandBridge(PORT_ID, host="::1", container=NAME, credential_ref=REF,
                        ssh_port=0).open()
    assert lock_free()


def test_the_descriptions_name_the_port_and_the_path():
    assert T.RawTcp(7, host="192.0.2.1", tcp_port=5000).describe() == \
        "console-server port 7 (192.0.2.1 port 5000)"
    assert T.RawTcp(7, host="192.0.2.1", tcp_port=5000, jump_host="2001:db8::2",
                    ssh_port=2222, credential_ref=REF).describe() == \
        "console-server port 7 (192.0.2.1 port 5000 via 2001:db8::2 port 2222)"
    assert T.CommandBridge(7, host="2001:db8::2", container=NAME,
                           credential_ref=REF).describe() == \
        "console-server port 7 ('s5' on 2001:db8::2 port 22)"
    assert T.ConsoleTransport(7).owner == "an unnamed caller"


def test_the_interface_leaves_the_connection_to_its_drivers():
    """The base class holds the port, counts and moves bytes; connecting, the pipe, closing
    and the description are each driver's, and the base refuses to stand in for one."""
    base = T.ConsoleTransport(7)
    assert base._check() is None
    for member, args in (("_connect", (1.0,)), ("_pipe", ()), ("_disconnect", ()),
                         ("describe", ())):
        with pytest.raises(NotImplementedError):
            getattr(base, member)(*args)


def test_the_lowest_netbox_id_is_a_port():
    assert T.PortLock(1, "test").port_id == 1


@pytest.mark.parametrize("host", ["[2001:db8::1", "2001:db8::1]", "x" * 253 + "."])
def test_a_host_half_bracketed_or_too_long_is_refused(host):
    with pytest.raises(T.ConsoleRefused, match="is not an IPv4 or IPv6 address or a hostname"):
        T.canonical_host(host)


@pytest.mark.parametrize("host,canonical", [
    ("a." * 126 + "b", "a." * 126 + "b"),                  # 253 characters, the longest
    ("console.example..", None),                            # two dots: an empty label
    ("a." * 126 + "bc", None),                              # 254 characters
    ("X.", "x"),
])
def test_a_hostnames_length_and_trailing_dot(host, canonical):
    if canonical is None:
        with pytest.raises(T.ConsoleRefused):
            T.canonical_host(host)
    else:
        assert T.canonical_host(host) == canonical


# ── A closed bridge says what the console host said ─────────────────────────────────────

class _Chan:
    """An SSH channel at its end: its stderr in chunks, its exit status (or none yet), and
    every read and wait asked of it."""

    def __init__(self, stderr=(), status=None):
        self.chunks = [bytes(c) for c in stderr]
        self.status = status
        self.asked, self.waited = [], []
        self.status_event = self

    def wait(self, seconds):
        self.waited.append(seconds)

    def recv_stderr_ready(self):
        return bool(self.chunks)

    def recv_stderr(self, n):
        self.asked.append(n)
        chunk, rest = self.chunks[0][:n], self.chunks[0][n:]
        self.chunks[0:1] = [rest] if rest else []
        return chunk

    def exit_status_ready(self):
        return self.status is not None

    def recv_exit_status(self):
        assert self.status is not None, "an exit status read before it arrived would block"
        return self.status


def closed(chan) -> str:
    t = T.CommandBridge(7, host="192.0.2.1", container=NAME, credential_ref=REF)
    t._chan = chan
    return str(t._closed())


def test_a_bridge_closed_with_nothing_said_says_only_that():
    chan = _Chan()
    assert closed(chan) == "console-server port 7 ('s5' on 192.0.2.1 port 22) closed the bridge"
    assert chan.waited == [T.EXIT_WAIT_S] and chan.asked == []


def test_a_bridge_closed_with_its_status_and_words_names_both():
    chan = _Chan([b"nmas-console-bridge: refused: ", b"'s9' is not on the allowlist\n"], 2)
    assert closed(chan) == ("console-server port 7 ('s5' on 192.0.2.1 port 22) closed the "
                            "bridge (exit 2): nmas-console-bridge: refused: 's9' is not on the "
                            "allowlist")


def test_a_bridge_status_of_zero_is_named():
    assert closed(_Chan(status=0)).endswith("closed the bridge (exit 0)")


def test_the_stderr_read_stops_at_its_limit():
    chan = _Chan([b"a" * 600, b"b" * 600, b"c" * 10], 1)
    words = closed(chan)
    assert chan.asked == [T.STDERR_MAX, T.STDERR_MAX - 600] == [1000, 400]
    assert words.endswith(": " + "a" * 600 + "b" * 400)


def test_stderr_that_is_not_utf8_is_still_said():
    assert closed(_Chan([b"refused \xff here"], 2)).endswith(": refused � here")
