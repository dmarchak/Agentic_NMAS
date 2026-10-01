"""Every read on a tool session waits for the DEVICE, never for Netmiko's fixed
bounds, and a show command ends on the device's own prompt after its echo.

The hourly startup check, 2026-10-01 06:03 on the host: 7 of 9 devices
UNKNOWN, each a Netmiko `ReadTimeout`, at four different places:
  r1 to r4  "Pattern not detected: 'show\\ running\\-config\\ \\|\\ include\\ \\^username'"
            (the command's ECHO, which Netmiko waits a fixed 10 s for);
  s1        "Pattern not detected: '(\\#|>)'" (the login prompt, 10 s);
  s3        "Pattern not detected: 'terminal width 511'" (session preparation, 10 s);
  s4        "Pattern not detected: 'terminal\\ length\\ 0'" (session preparation, 20 s).
None of those bounds is one a caller passes, and the same failures were in the
00:06, 03:02 and 04:02 runs, before C272 was deployed. Measured the same
morning (all nine at once, then one at a time): an echo up to 5.9 s, a vIOS
`show running-config | include ^username` 31.6 s alone, a login 46 s.

The fixtures are REAL channel transcripts, r1 (IOS-XE) and s1 (vIOS), read
through the tool's own open_ssh on the host (tests/fixtures/transcripts/,
README there). They are replayed through REAL Netmiko on a simulated clock, so
the delays are the device's and the code reading them is the code that runs.
"""
import re
import time as _real_time
from pathlib import Path

import netmiko
import pytest
from netmiko.exceptions import ReadTimeout

from modules import connection

FIX = Path(__file__).parent / "fixtures" / "transcripts"

COMMANDS = {
    "show_startup-config": "show startup-config",
    "show_running-config_include_username": "show running-config | include ^username",
    "show_running-config_section_router": "show running-config | section router",
    "show_ip_interface_brief": "show ip interface brief",
    "show_ip_ospf_neighbor": "show ip ospf neighbor",
    "show_ip_protocols_include_routing_protocol": "show ip protocols | include Routing Protocol",
    "show_running-config": "show running-config",
}
PROMPTS = {"r1": "r1#", "s1": "s1#"}
CASES = sorted((dev, name) for dev in PROMPTS for name in COMMANDS)


def transcript(device, name):
    return (FIX / device / f"{name}.txt").read_text()


class Clock:
    """Netmiko's clock, simulated: sleeping advances it."""

    def __init__(self):
        self.t = 1_000_000.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += max(float(s), 0.001)

    def __getattr__(self, name):
        return getattr(_real_time, name)


class Device:
    """The device end of a session. What was in the channel before a command
    (prompts left over from logging in) is there at once; a command's reply,
    from its echo on, arrives `delay` seconds after it is written, in chunks
    of `chunk` characters `gap` seconds apart, as a real channel delivers it."""

    def __init__(self, clock, prompt, replies, delay=0.0, chunk=4096, gap=0.05):
        self.clock, self.prompt, self.replies = clock, prompt, replies
        self.delay, self.chunk, self.gap = delay, chunk, gap
        self.pending = []
        self.written = []

    def preload(self, text):
        self.pending.append((self.clock.t, text))

    def write(self, data):
        self.written.append(data)
        for line in data.split("\n")[:-1]:              # each line ENTERED
            line = line.strip()
            reply = ("\n" + self.prompt) if not line else self.replies.get(
                line, f"{line}\n{self.prompt}")
            at = self.clock.t + self.delay
            for i in range(0, len(reply), self.chunk):
                self.pending.append((at, reply[i:i + self.chunk]))
                at += self.gap

    def write_channel(self, data):
        self.write(data)

    def read_channel(self):
        return self.read()

    def read(self):
        now = self.clock.t
        ready = [p for p in self.pending if p[0] <= now]
        self.pending = [p for p in self.pending if p[0] > now]
        return "".join(t for _, t in ready)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(netmiko.base_connection, "time", c)
    return c


def session(device_obj, base_prompt):
    """A REAL Netmiko Cisco IOS connection whose channel is *device_obj*."""
    conn = netmiko.ConnectHandler(device_type="cisco_ios", host="192.0.2.1",
                                  username="u", password="p", auto_connect=False)
    conn.channel = device_obj          # Netmiko's own read_channel and buffer run
    conn.base_prompt = base_prompt
    return conn


def split(text, cmd):
    """(what sat in the channel before the echo, the reply from the echo on),
    and the command's output as the transcript holds it: after the echo line,
    before the closing prompt line. Computed from the text alone, never by the
    reader under test."""
    at = text.index(cmd)
    before, reply = text[:at], text[at:]
    body = reply[len(cmd):].split("\n", 1)[1] if "\n" in reply[len(cmd):] else ""
    body = body.rsplit("\n", 1)[0] if "\n" in body else ""
    return before, reply, body


def test_the_fixtures_are_the_real_transcripts():
    """Floor: every case has its transcript, each ends at the device's prompt
    and holds its command's echo, and the startup reads carry the prompts
    logging in left before the echo (what makes a prompt-only read wrong)."""
    assert len(CASES) == 14
    for dev, name in CASES:
        text = transcript(dev, name)
        assert text.endswith(PROMPTS[dev]), (dev, name)
        assert COMMANDS[name] in text, (dev, name)
    for dev in PROMPTS:
        before, _r, _b = split(transcript(dev, "show_startup-config"), "show startup-config")
        assert before.count(PROMPTS[dev]) >= 4, before


@pytest.mark.parametrize("dev,name", CASES)
def test_every_real_transcript_reads_its_own_output(clock, dev, name):
    cmd = COMMANDS[name]
    before, reply, body = split(transcript(dev, name), cmd)
    d = Device(clock, PROMPTS[dev], {cmd: reply}, delay=0.3, chunk=700)
    d.preload(before)
    conn = session(d, dev)
    connection.floor_reads(conn, floor=120)
    out = conn.send_command(cmd, read_timeout=120)
    assert out.strip() == body.strip()
    assert d.written == [cmd + "\n"]                       # sent ONCE


@pytest.mark.parametrize("dev", sorted(PROMPTS))
def test_the_0603_failure_is_the_echo_bound_and_the_floor_waits_it_out(clock, dev):
    """The device echoes 12 s after the command, as r1 to r4 did at 06:03.
    Netmiko as it ships raises at its fixed 10 s whatever read_timeout the
    caller gave (the control, the host's exact message); the tool's session
    waits and reads the output."""
    name = "show_running-config_include_username"
    cmd = COMMANDS[name]
    _b, reply, body = split(transcript(dev, name), cmd)

    plain = session(Device(clock, PROMPTS[dev], {cmd: reply}, delay=12), dev)
    with pytest.raises(ReadTimeout) as exc:
        plain.send_command(cmd, read_timeout=120)
    # The host's exact message: the escaped command, i.e. the ECHO.
    assert f"Pattern not detected: {re.escape(cmd)!r}" in str(exc.value)

    floored = session(Device(clock, PROMPTS[dev], {cmd: reply}, delay=12), dev)
    connection.floor_reads(floored, floor=120)
    assert floored.send_command(cmd, read_timeout=120).strip() == body.strip()


@pytest.mark.parametrize("dev", sorted(PROMPTS))
def test_a_prompt_left_from_logging_in_never_answers_the_command(clock, dev):
    """The real startup reads: four prompts sit in the channel before the echo.
    Ending on the prompt alone returns one of THEM as the answer (the danger,
    shown); the tool's session reads past them to the echo and returns the
    startup configuration."""
    name, cmd = "show_startup-config", "show startup-config"
    before, reply, body = split(transcript(dev, name), cmd)
    pattern = connection.prompt_terminator(dev)

    d = Device(clock, PROMPTS[dev], {cmd: reply}, delay=0.5)
    d.preload(before)
    prompt_only = session(d, dev)
    early = prompt_only.send_command(cmd, read_timeout=120, cmd_verify=False,
                                     expect_string=pattern)
    assert "Using " not in early and "end" not in early.split()

    d = Device(clock, PROMPTS[dev], {cmd: reply}, delay=0.5)
    d.preload(before)
    conn = session(d, dev)
    connection.floor_reads(conn, floor=120)
    out = conn.send_command(cmd, read_timeout=120)
    assert out.strip() == body.strip()
    assert out.rstrip().endswith("end")


@pytest.mark.parametrize("dev", sorted(PROMPTS))
def test_the_hostname_inside_a_configuration_never_ends_the_read(clock, dev):
    """`hostname r1` arrives long before the prompt. Netmiko's bare base
    prompt (its pattern with no prompt probe) ends the read there (the
    control); the anchored terminator reads to `end`."""
    name, cmd = "show_running-config", "show running-config"
    _b, reply, body = split(transcript(dev, name), cmd)
    assert f"hostname {dev}" in body

    bare = session(Device(clock, PROMPTS[dev], {cmd: reply}, chunk=256), dev)
    cut = bare.send_command(cmd, read_timeout=120, expect_string=re.escape(dev))
    assert not cut.rstrip().endswith("end")

    conn = session(Device(clock, PROMPTS[dev], {cmd: reply}, chunk=256), dev)
    connection.floor_reads(conn, floor=120)
    assert conn.send_command(cmd, read_timeout=120).strip() == body.strip()


def test_logging_in_waits_for_a_slow_switch(clock):
    """s3 and s4 at 06:03: `terminal width 511` and `terminal length 0` not
    echoed in Netmiko's 10 s and 20 s; s1: no prompt in 10 s. A switch that
    answers everything 25 s late fails Netmiko's own session preparation (the
    control) and completes the tool's, with the prompt read."""
    plain = session(Device(clock, "s1#", {}, delay=25), "")
    with pytest.raises(ReadTimeout):
        plain.session_preparation()

    conn = session(Device(clock, "s1#", {}, delay=25), "")
    connection.floor_reads(conn, floor=120)
    conn.session_preparation()
    assert conn.base_prompt == "s1"


def test_a_callers_longer_bound_is_kept_and_a_shorter_one_raised():
    seen = []

    class Raw:
        base_prompt = "r1"

        def send_command(self, *a, **kw):
            seen.append(kw)
            return ""

        def read_until_pattern(self, *a, **kw):
            seen.append(("until", a, kw))
            return ""

    conn = Raw()
    connection.floor_reads(conn, floor=120)
    conn.send_command("show clock", read_timeout=300)
    conn.send_command("show clock", read_timeout=30)
    conn.send_command("show clock")
    conn.send_command("show clock", expect_string="mine")
    conn.read_until_pattern(pattern="x")
    conn.read_until_pattern("x", 20)
    conn.read_until_pattern(pattern="x", read_timeout=500)
    assert [k["read_timeout"] for k in seen[:4]] == [300, 120, 120, 120]
    assert seen[0]["expect_string"] == connection.prompt_terminator("r1")
    assert seen[3]["expect_string"] == "mine"
    assert seen[4][2]["read_timeout"] == 120
    assert seen[5][1] == ("x", 120)
    assert seen[6][2]["read_timeout"] == 500


def test_the_terminator_is_the_prompt_on_a_line_of_its_own_at_the_end():
    p = connection.prompt_terminator("r1")
    for text in ("show clock\n*12:00:00 UTC\nr1#", "x\nr1>", "x\nr1(config)#",
                 "x\nr1# ", "x\nr1-core.lab#"):
        assert re.search(p, text), text
    for text in ("hostname r1\n", "x\nr1#\nmore", "description to r1#\n x",
                 "x\nar1#", "x\nr1"):
        assert not re.search(p, text), text
    assert re.search(connection.prompt_terminator("verylonghostname"),
                     "x\nverylonghostname-12#")
    for bad in ("", None, "^@", "\x00", "r1#x y"):
        assert connection.prompt_terminator(bad) is None


def test_open_ssh_floors_every_read_before_the_session_logs_in(monkeypatch):
    """The login is where s1, s3 and s4 failed, so the floor must be in place
    BEFORE it: open_ssh asks Netmiko not to connect, floors, then logs in. A
    login that raises closes what it opened and leaves no counted session."""
    import netmiko as nm

    made = []

    class Fake:
        fail = False

        def __init__(self, **kw):
            self.kw = kw
            self.base_prompt = ""
            self.floored_at_login = None
            self.closed = False
            made.append(self)

        def read_until_pattern(self, *a, **kw):
            return ""

        def send_command(self, *a, **kw):
            return ""

        def _open(self):
            self.floored_at_login = getattr(self, "_nmas_read_floor", None)
            if Fake.fail:
                raise ReadTimeout("Pattern not detected: 'terminal width 511'")

        def disconnect(self):
            self.closed = True

    monkeypatch.setattr(nm, "ConnectHandler", Fake)
    monkeypatch.setattr(connection, "vty_lines", lambda ip: (5, "test"))
    params = {"device_type": "cisco_ios", "ip": "192.0.2.7", "username": "u",
              "password": "p"}
    conn = connection.open_ssh(params, owner="test")
    assert made[0].kw["auto_connect"] is False
    assert made[0].floored_at_login == connection.read_floor() >= 120
    conn.disconnect()

    Fake.fail = True
    with pytest.raises(ReadTimeout):
        connection.open_ssh(params, owner="test")
    assert made[1].closed
    assert "192.0.2.7" not in connection.held_sessions() or \
        not connection.held_sessions()["192.0.2.7"]
