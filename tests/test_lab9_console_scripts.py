"""C1545: the two Lab 9 scripts that talk to a device console, tested in the suite.

LAB TOOLING (`lab/lab9/`), run by hand on the lab host against s5's serial console (qemu's
telnet server). Their only tests lived in a scratchpad, which CI never runs:

- `console-reader.py` is strictly ONE-WAY: it connects, only receives, and appends what it
  receives to a file. A listener here counts every byte the reader sends; the count must be 0,
  whatever the console sends it (telnet negotiation a client would answer included), whether
  the console closes or the reader's bound ends the session.
- `s5-erase-session.py` sends only fixed inputs, each after the reply it expects: RETURN,
  `enable`, `dir nvram:`, and only when nvram's startup file is larger than 0 bytes
  `write erase`, its confirm, `reload`, `no` at the save question and the reload confirm. It
  STOPS, sending nothing more, on `Username:`, `Password:`, `--More--` or the setup dialog. A
  simulated console replies to each input and records every byte it receives; each case
  asserts the exact bytes sent.

The console's replies are what s5 really printed (tests/fixtures/console/, read 2026-10-22).
The 0-byte case replays the diagnostic session's own transcript, so what the session must send
there is read from that transcript (what the real session sent), not from the script under
test. The erase, reload and stop prompts were not printed in that session; their text is IOS's
own wording, each named where it is used.

Everything runs on loopback (the suite is confined to it), IPv4 and IPv6 side by side.
"""

import ast
import importlib.machinery
import importlib.util
import os
import re
import socket
import stat
import threading
import time
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READER = os.path.join(ROOT, "lab", "lab9", "console-reader.py")
SESSION = os.path.join(ROOT, "lab", "lab9", "s5-erase-session.py")
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "console")

#: Telnet negotiation a telnet CLIENT would answer: IAC WILL ECHO, IAC WILL SUPPRESS-GO-AHEAD,
#: IAC DO TERMINAL-TYPE (qemu's telnet server sends the first two).
NEGOTIATION = b"\xff\xfb\x01\xff\xfb\x03\xff\xfd\x18"


def _load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _fixture(name):
    with open(os.path.join(FIXTURES, name), "rb") as fh:
        return fh.read()


def _families():
    """Loopback in both families; IPv6 is skipped, by name, only where the host has no ::1."""
    out = [pytest.param("127.0.0.1", id="ipv4")]
    try:
        with socket.create_server(("::1", 0), family=socket.AF_INET6):
            out.append(pytest.param("::1", id="ipv6"))
    except OSError as exc:
        out.append(pytest.param("::1", id="ipv6", marks=pytest.mark.skip(
            reason=f"this host cannot bind ::1 ({exc})")))
    return out


class _NoStdin:
    """Standing in for stdin: any read is a failure (the reader must read nothing from it)."""

    def __getattr__(self, name):
        raise AssertionError(f"the script touched stdin ({name})")


class Listener:
    """A loopback console: runs *serve(conn, count)* on the one connection it accepts and
    counts every byte the client sends."""

    def __init__(self, host, serve):
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        self.srv = socket.create_server((host, 0), family=family)
        self.srv.settimeout(10)
        self.port = self.srv.getsockname()[1]
        self.received = bytearray()
        self.error = None
        self._serve = serve
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            conn, _ = self.srv.accept()
            with conn:
                self._serve(conn, self.received)
        except Exception as exc:              # surfaced by finish(), never swallowed
            self.error = exc

    def finish(self):
        self.thread.join(10)
        self.srv.close()
        assert not self.thread.is_alive(), "the listener never finished"
        assert self.error is None, self.error


def _read_until_eof(conn, received, seconds):
    conn.settimeout(0.05)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            data = conn.recv(4096)
        except socket.timeout:
            continue
        if not data:
            return
        received.extend(data)


# ── The one-way reader ────────────────────────────────────────────────────────────────────


class TestTheReaderIsOneWay:
    def test_the_floor_the_fixtures_are_what_s5_printed(self):
        assert b"Press RETURN to get started." in _fixture("s5-pnp-stopped.txt")
        assert b"Booted IOSv." in _fixture("s5-boot-to-release.txt")

    def test_by_parsing_its_socket_is_only_given_a_timeout_and_read(self):
        """Its docstring's claim: nothing calls send, sendall, write or makefile on the socket,
        and it never half-closes it. Read from its syntax tree, not its text (the docstring
        names every one of them)."""
        tree = ast.parse(open(READER, encoding="utf-8").read())
        on_sock = {n.func.attr for n in ast.walk(tree)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and isinstance(n.func.value, ast.Name) and n.func.value.id == "sock"}
        assert on_sock == {"settimeout", "recv"}, on_sock
        sending = {"send", "sendall", "sendto", "sendmsg", "sendfile", "makefile", "shutdown"}
        named = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not named & sending, named & sending
        assert "stdin" not in named

    @pytest.mark.parametrize("host", _families())
    def test_it_sends_nothing_and_logs_everything_the_console_sends(self, host, tmp_path,
                                                                   monkeypatch):
        reader = _load(READER, "console_reader")
        monkeypatch.setattr("sys.stdin", _NoStdin())
        sent = NEGOTIATION + _fixture("s5-boot-to-release.txt") + _fixture("s5-pnp-stopped.txt")

        def serve(conn, received):
            conn.sendall(sent)
            _read_until_eof(conn, received, 0.5)     # anything it answers arrives in this

        console = Listener(host, serve)
        log = tmp_path / "console.log"
        assert reader.main(["console-reader.py", host, str(console.port), str(log), "20"]) == 0
        console.finish()
        assert len(console.received) == 0, bytes(console.received)
        text = log.read_bytes()
        body = re.sub(rb"\n--- \d\d:\d\d:\d\dZ ---\n", b"", text)   # its own chunk stamps
        assert sent in body
        assert f"connected to {host}:{console.port}, receive only".encode() in text
        assert b"the console closed the connection" in text

    @pytest.mark.parametrize("host", _families())
    def test_at_its_bound_it_has_still_sent_nothing(self, host, tmp_path, monkeypatch):
        """The console stays open and keeps printing; the reader's bound ends the session, and
        the listener reads until the reader's socket is closed."""
        reader = _load(READER, "console_reader")
        monkeypatch.setattr("sys.stdin", _NoStdin())
        stop = threading.Event()

        def serve(conn, received):
            conn.settimeout(0.05)
            conn.sendall(NEGOTIATION)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    if not stop.is_set():
                        conn.sendall(b"%PNP-6-PNP_DISCOVERY_STARTED\r\n")
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    return
                if not data:
                    return
                received.extend(data)

        console = Listener(host, serve)
        log = tmp_path / "console.log"
        assert reader.main(["console-reader.py", host, str(console.port), str(log), "0.5"]) == 0
        stop.set()
        console.finish()
        assert len(console.received) == 0, bytes(console.received)
        text = log.read_bytes()
        assert b"bound reached" in text and b"%PNP-6-PNP_DISCOVERY_STARTED" in text


# ── The erase session ─────────────────────────────────────────────────────────────────────

#: IOS's wording for what the diagnostic session never reached (not printed on 2026-10-22).
ERASE_CONFIRM = (b"write erase\r\nErasing the nvram filesystem will remove all configuration "
                 b"files! Continue? [confirm]")
ERASED = b"[OK]\r\nErase of nvram: complete\r\nSwitch#"
SAVE_QUESTION = b"reload\r\n\r\nSystem configuration has been modified. Save? [yes/no]: "
PROCEED = b"no\r\nProceed with reload? [confirm]"
RELOADING = b"\r\n\r\n*Oct 22 06:20:00.000: %SYS-5-RELOAD: Reload requested by console.\r\n"


def _transcript():
    """The diagnostic session's transcript as ``[(sent, the console's answer)]``."""
    parts = re.split(rb"\n>>> send '([^']*)'\n", _fixture("s5-session-enable-dir-nvram.txt"))
    return [(sent.decode("unicode_escape").encode(), answer)
            for sent, answer in zip(parts[1::2], parts[2::2])]


def _with_startup_bytes(answer, size):
    """The real `dir nvram:` answer with the startup file's size edited (columns kept)."""
    edited = answer.replace(b"  254  -rw-           0 ", b"  254  -rw-" + f"{size:>12} ".encode())
    assert edited != answer and len(edited) == len(answer)       # the columns kept
    return edited


class Console:
    """A simulated IOS console: answers each input (a run of bytes ending in RETURN) with the
    next scripted reply when it is the input expected next, and records every byte."""

    def __init__(self, host, script):
        self.script = list(script)
        self.unexpected = []
        self.done = threading.Event()
        self.listener = Listener(host, self._serve)
        self.port = self.listener.port

    @property
    def received(self):
        return bytes(self.listener.received)

    def _serve(self, conn, received):
        conn.settimeout(0.05)
        pending = bytearray()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                if self.done.is_set():          # the session has ended and nothing is in flight
                    return
                continue
            except OSError:
                return
            if not data:
                return
            received.extend(data)
            pending.extend(data)
            while b"\r" in pending:
                cut = pending.index(b"\r") + 1
                said = bytes(pending[:cut])
                del pending[:cut]
                if self.script and self.script[0][0] == said:
                    conn.sendall(self.script.pop(0)[1])
                else:
                    self.unexpected.append(said)

    def finish(self):
        self.done.set()
        self.listener.finish()


@pytest.fixture
def session(monkeypatch):
    mod = _load(SESSION, "s5_erase_session")
    # Its one fixed pause (2 s after the reload confirm) is not waited out here; the clock it
    # bounds its waits with stays the real one.
    monkeypatch.setattr(mod, "time", types.SimpleNamespace(
        sleep=lambda s: None, monotonic=time.monotonic, strftime=time.strftime,
        gmtime=time.gmtime))
    return mod


def _run(session, console, transcript, *extra):
    argv = ["s5-erase-session.py", console.listener.srv.getsockname()[0], str(console.port),
            str(transcript), *extra]
    try:
        code = session.main(argv)
    except SystemExit as exc:
        code = exc.code
    console.finish()
    return code


class TestTheEraseSession:
    def test_the_floor_the_transcript_holds_three_sends_and_a_zero_byte_startup_file(self):
        t = _transcript()
        assert [s for s, _a in t] == [b"\r", b"enable\r", b"dir nvram:\r"]
        assert re.search(rb"-rw- +0 .*startup-config", t[2][1])
        assert t[0][1].rstrip().endswith(b"Switch>") and t[1][1].rstrip().endswith(b"Switch#")

    @pytest.mark.parametrize("host", _families())
    def test_a_zero_byte_startup_file_sends_return_enable_dir_and_nothing_else(
            self, host, session, tmp_path, capsys):
        t = _transcript()
        console = Console(host, t)
        transcript = tmp_path / "transcript.log"
        code = _run(session, console, transcript)
        out = capsys.readouterr().out
        # What the real session sent, read from its transcript, not from the script.
        assert console.received == b"".join(s for s, _a in t), console.received
        assert console.unexpected == [] and code == 3, (code, out)
        assert "startup file is 0 bytes" in out and "STOPPED, nothing more sent" in out
        assert stat.S_IMODE(os.stat(transcript).st_mode) == 0o600
        assert b"262144 bytes total (260044 bytes free)" in transcript.read_bytes()

    @pytest.mark.parametrize("host", _families())
    def test_a_startup_file_over_zero_bytes_sends_the_erase_and_reload_and_nothing_else(
            self, host, session, tmp_path, capsys):
        (ret, banner), (en, enabled), (dir_, listing) = _transcript()
        console = Console(host, [
            (ret, banner), (en, enabled), (dir_, _with_startup_bytes(listing, 1405)),
            (b"write erase\r", ERASE_CONFIRM), (b"\r", ERASED),
            (b"reload\r", SAVE_QUESTION), (b"no\r", PROCEED), (b"\r", RELOADING)])
        code = _run(session, console, tmp_path / "transcript.log")
        out = capsys.readouterr().out
        assert console.received == (b"\renable\rdir nvram:\rwrite erase\r\rreload\rno\r\r"), \
            console.received
        assert console.unexpected == [] and console.script == [] and code == 0, (code, out)
        assert "startup file of 1405 bytes: erasing" in out and "nvram erased" in out

    @pytest.mark.parametrize("host", _families())
    def test_never_saved_reloads_a_zero_byte_startup_without_an_erase(
            self, host, session, tmp_path, capsys):
        """C1572: the REAL 0-byte `dir nvram:` answer, with --never-saved: reload, `no` at the
        save question, RETURN at the confirm; no `write erase`."""
        (ret, banner), (en, enabled), (dir_, listing) = _transcript()
        console = Console(host, [(ret, banner), (en, enabled), (dir_, listing),
                                 (b"reload\r", SAVE_QUESTION), (b"no\r", PROCEED),
                                 (b"\r", RELOADING)])
        code = _run(session, console, tmp_path / "transcript.log", "--never-saved")
        out = capsys.readouterr().out
        assert console.received == b"\renable\rdir nvram:\rreload\rno\r\r", console.received
        assert console.unexpected == [] and console.script == [] and code == 0, (code, out)
        assert "reloading without an erase" in out and "write erase" not in out

    def test_never_saved_still_erases_a_startup_file_over_zero_bytes(self, session, tmp_path):
        (ret, banner), (en, enabled), (dir_, listing) = _transcript()
        console = Console("127.0.0.1", [
            (ret, banner), (en, enabled), (dir_, _with_startup_bytes(listing, 1405)),
            (b"write erase\r", ERASE_CONFIRM), (b"\r", ERASED),
            (b"reload\r", SAVE_QUESTION), (b"no\r", PROCEED), (b"\r", RELOADING)])
        code = _run(session, console, tmp_path / "transcript.log", "--never-saved")
        assert console.received == b"\renable\rdir nvram:\rwrite erase\r\rreload\rno\r\r"
        assert console.unexpected == [] and code == 0

    def test_an_unknown_argument_is_refused_before_anything_is_sent(self, session, tmp_path,
                                                                     capsys, monkeypatch):
        """Refused before a connection is even opened, so no byte can reach the console."""
        opened = []
        monkeypatch.setattr(session, "Session", lambda *a: opened.append(a))
        with pytest.raises(SystemExit) as exc:
            session.main(["s5-erase-session.py", "192.0.2.1", "5000",
                          str(tmp_path / "transcript.log"), "--erase-anyway"])
        assert (exc.value.code, opened) == (2, []), (exc.value.code, opened)
        assert "unknown arguments" in capsys.readouterr().out

    def test_a_reload_that_asks_no_save_question_is_confirmed_without_a_no(
            self, session, tmp_path):
        (ret, banner), (en, enabled), (dir_, listing) = _transcript()
        console = Console("127.0.0.1", [
            (ret, banner), (en, enabled), (dir_, _with_startup_bytes(listing, 1405)),
            (b"write erase\r", ERASE_CONFIRM), (b"\r", ERASED),
            (b"reload\r", b"reload\r\nProceed with reload? [confirm]"), (b"\r", RELOADING)])
        code = _run(session, console, tmp_path / "transcript.log")
        assert console.received == b"\renable\rdir nvram:\rwrite erase\r\rreload\r\r"
        assert console.unexpected == [] and code == 0

    @pytest.mark.parametrize("case, replies, sent", [
        # enable answered with a password prompt: the image's configuration sets one.
        ("Password:", lambda t: [t[0], (t[1][0], b"enable\r\nPassword: ")],
         b"\renable\r"),
        # The console asks for a login (IOS's wording for `login local` on the line).
        ("Username:", lambda t: [(t[0][0], t[0][1].rsplit(b"Switch>", 1)[0]
                                 + b"\r\n\r\nUser Access Verification\r\n\r\nUsername: ")],
         b"\r"),
        # `dir nvram:` paged: the listing cut after its first entry and IOS's pager prompt.
        ("--More--", lambda t: [t[0], t[1], (t[2][0], t[2][1].split(b"private-config")[0]
                                         + b"\r\n --More-- ")],
         b"\renable\rdir nvram:\r"),
        # The setup dialog (IOS's wording) instead of a prompt.
        ("initial configuration dialog",
         lambda t: [(t[0][0], b"\r\n\r\n         --- System Configuration Dialog ---\r\n\r\n"
                              b"Would you like to enter the initial configuration dialog? "
                              b"[yes/no]: ")],
         b"\r"),
    ])
    @pytest.mark.parametrize("host", _families())
    def test_it_stops_sending_on_a_prompt_it_must_not_answer(self, host, case, replies, sent,
                                                             session, tmp_path, capsys):
        console = Console(host, replies(_transcript()))
        code = _run(session, console, tmp_path / "transcript.log")
        out = capsys.readouterr().out
        assert console.received == sent, (case, console.received)
        assert console.unexpected == [] and code == 2, (case, code, out)
        # It stopped on the word itself, at once, never on a wait that ran out later.
        assert "STOPPED, nothing more sent" in out and repr(case) in out, out


# ── The SVI MAC read (console-show-mac.py) ────────────────────────────────────────────────

SHOW_MAC = os.path.join(ROOT, "lab", "lab9", "console-show-mac.py")


def _svi_text():
    """s1's REAL `show interfaces Vlan10` (Mercury's Show commands, 2026-10-23), as IOS sends it."""
    return _fixture("vios_l2_show_interfaces_vlan10.txt").replace(b"\n", b"\r\n")


@pytest.fixture
def show_mac(monkeypatch):
    mod = _load(SHOW_MAC, "console_show_mac")
    monkeypatch.setattr(mod, "time", types.SimpleNamespace(
        sleep=lambda s: None, monotonic=time.monotonic, strftime=time.strftime,
        gmtime=time.gmtime))
    return mod


def _show(mod, console, transcript, *extra):
    argv = ["console-show-mac.py", console.listener.srv.getsockname()[0], str(console.port),
            str(transcript), *extra]
    try:
        code = mod.main(argv)
    except SystemExit as exc:
        code = exc.code
    console.finish()
    return code


class TestTheSviMacRead:
    @pytest.mark.parametrize("host", _families())
    def test_it_reads_the_svi_mac_and_sends_only_its_three_inputs(self, host, show_mac,
                                                                  tmp_path, capsys):
        console = Console(host, [
            (b"\r", b"\r\nSwitch>"),
            (b"terminal length 0\r", b"terminal length 0\r\nSwitch>"),
            (b"show interfaces Vlan10\r", b"show interfaces Vlan10\r\n" + _svi_text()
             + b"\r\nSwitch>")])
        code = _show(show_mac, console, tmp_path / "t.log", "Vlan10")
        out = capsys.readouterr().out
        assert console.received == b"\rterminal length 0\rshow interfaces Vlan10\r"
        assert console.unexpected == [] and code == 0, (code, out)
        assert "Vlan10 MAC: 0c00.6ce9.800a" in out
        assert "state: Vlan10 is up, line protocol is up" in out
        # Nothing else the console showed is printed (its address line stays in the transcript).
        assert "10.10.10.2" not in out
        assert stat.S_IMODE(os.stat(tmp_path / "t.log").st_mode) == 0o600

    def test_no_address_line_says_the_mac_is_unknown(self, show_mac, tmp_path, capsys):
        console = Console("127.0.0.1", [
            (b"\r", b"\r\nSwitch>"), (b"terminal length 0\r", b"terminal length 0\r\nSwitch>"),
            (b"show interfaces Vlan1\r", b"show interfaces Vlan1\r\n                       ^\r\n"
                                         b"% Invalid input detected at '^' marker.\r\nSwitch>")])
        code = _show(show_mac, console, tmp_path / "t.log")
        assert code == 3 and "the MAC is unknown" in capsys.readouterr().out

    @pytest.mark.parametrize("reply, word", [
        (b"\r\n\r\nUser Access Verification\r\n\r\nUsername: ", "Username:"),
        (b"\r\nWould you like to enter the initial configuration dialog? [yes/no]: ",
         "initial configuration dialog")])
    def test_it_stops_on_a_prompt_it_must_not_answer(self, show_mac, tmp_path, capsys, reply,
                                                     word):
        console = Console("127.0.0.1", [(b"\r", reply)])
        code = _show(show_mac, console, tmp_path / "t.log")
        out = capsys.readouterr().out
        assert (code, console.received) == (2, b"\r"), (code, console.received)
        assert "STOPPED, nothing more sent" in out and repr(word) in out

    def test_a_paged_answer_stops_at_the_pager(self, show_mac, tmp_path, capsys):
        console = Console("127.0.0.1", [
            (b"\r", b"\r\nSwitch>"), (b"terminal length 0\r", b"terminal length 0\r\nSwitch>"),
            (b"show interfaces Vlan1\r", _svi_text().split(b"  MTU")[0] + b"\r\n --More-- ")])
        code = _show(show_mac, console, tmp_path / "t.log")
        assert (code, console.received) == (2, b"\rterminal length 0\rshow interfaces Vlan1\r")

    @pytest.mark.parametrize("host", _families())
    def test_stp_reads_the_bridge_address_and_says_its_prediction_is_one(self, host, show_mac,
                                                                         tmp_path, capsys):
        """s1's REAL `show spanning-tree vlan 1`: its bridge 0c00.6ce9.b700, whose first four
        bytes are its SVIs' (Vlan10 0c00.6ce9.800a, measured), so Vlan1 is predicted ....8001."""
        stp = _fixture("vios_l2_show_spanning_tree_vlan1.txt").replace(b"\n", b"\r\n")
        console = Console(host, [
            (b"\r", b"\r\nSwitch>"), (b"terminal length 0\r", b"terminal length 0\r\nSwitch>"),
            (b"show spanning-tree vlan 1\r", b"show spanning-tree vlan 1\r\n" + stp
             + b"\r\nSwitch>")])
        code = _show(show_mac, console, tmp_path / "t.log", "--stp")
        out = capsys.readouterr().out
        assert console.received == b"\rterminal length 0\rshow spanning-tree vlan 1\r"
        assert console.unexpected == [] and code == 0, (code, out)
        assert "bridge address: 0c00.6ce9.b700" in out
        assert "0c00.6ce9.8001" in out and "not on this one" in out

    def test_stp_reads_this_bridge_not_the_root(self, show_mac, tmp_path, capsys):
        """A planted case (a minimal edit of the real output): another switch is the root, as on
        s2's VLAN 10, so the Root ID's address differs and only the Bridge ID's is this switch."""
        stp = _fixture("vios_l2_show_spanning_tree_vlan1.txt").replace(b"\n", b"\r\n")
        stp = stp.replace(b"0c00.6ce9.b700", b"0c00.6f31.0c00", 1)      # the root's line only
        assert stp.count(b"0c00.6ce9.b700") == 1
        console = Console("127.0.0.1", [
            (b"\r", b"\r\nSwitch>"), (b"terminal length 0\r", b"terminal length 0\r\nSwitch>"),
            (b"show spanning-tree vlan 1\r", b"show spanning-tree vlan 1\r\n" + stp
             + b"\r\nSwitch>")])
        assert _show(show_mac, console, tmp_path / "t.log", "--stp") == 0
        out = capsys.readouterr().out
        assert "bridge address: 0c00.6ce9.b700" in out and "0c00.6ce9.8001" in out, out

    def test_a_malformed_interface_is_refused_before_a_connection(self, show_mac, tmp_path,
                                                                  monkeypatch):
        opened = []
        monkeypatch.setattr(show_mac, "Session", lambda *a: opened.append(a))
        with pytest.raises(SystemExit) as exc:
            show_mac.main(["console-show-mac.py", "192.0.2.1", "5000", str(tmp_path / "t"),
                           "Vlan1; reload"])
        assert (exc.value.code, opened) == (2, [])
