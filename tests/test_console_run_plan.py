"""The console driver loop (modules/nsot/console_transport.run_plan; docs/LAB9_PLAN.md section 8,
O2): it reads, feeds the session, ticks it when nothing arrives, and writes EXACTLY the bytes
the session decides, nothing else, stopping on done, abort, the far end closing, or its bound.

Driven by the real console text (tests/fixtures/console/, README.md there) through a scripted
in-memory console and a clock the console advances, so every case is exact and instant. The
transports themselves, over real sockets, are tests/test_console_transport.py."""

import pytest

from modules.nsot import console_profiles as P
from modules.nsot import console_session as S
from modules.nsot import console_transport as T
from tests.test_console_session import BOOT, PNP, SURVEY, plan, session_fixture

SWITCH = P.load("cisco_ios_switch")
NO_VALUES = {}
#: A run bound none of these cases reaches unless it says so.
BOUND = 600.0
#: Telnet negotiation a raw console server may open with: IAC DO ECHO, IAC WILL ECHO, IAC WILL
#: SUPPRESS-GO-AHEAD, IAC DO NAWS, and a subnegotiation. None of it is ever answered.
NEGOTIATE = b"\xff\xfd\x01\xff\xfb\x01\xff\xfb\x03\xff\xfd\x1f\xff\xfa\x18\x01\xff\xf0"
#: The device every run here sends for, which each test's thread holds (C1559: a console write
#: needs its device held; the guard's own cases are at the end).
DEVICE = ("console-run-plan", "edge1")


@pytest.fixture(autouse=True)
def held(tmp_path, monkeypatch):
    from modules.nsot import device_ops

    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    with device_ops.hold(*DEVICE, "console survey", "test@example.invalid"):
        yield


def run_held(*args, **kw):
    """`run_plan` for the device this test's thread holds."""
    return T.run_plan(*args, device=DEVICE, **kw)


class Clock:
    def __init__(self, now: float = 100.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


class Scripted:
    """An in-memory console behind the transport interface: it prints *greeting* in chunks,
    then for each CR written its next answer; a read with nothing to give waits its *timeout*
    on the clock and returns ``b""``. Every write is recorded, with the read count at which it
    came (`writes`)."""

    def __init__(self, clock, greeting=(), answers=(), close_after=None, fail_write=None):
        self.clock = clock
        self.pending = list(greeting)
        self.answers = list(answers)
        self.close_after = close_after         # reads after which the far end closes
        self.fail_write = fail_write           # an exception the first write raises
        self.writes = []
        self.reads = 0
        self.bytes_written = 0

    def describe(self):
        return "a scripted console"

    def read(self, max_bytes, timeout):
        self.reads += 1
        if self.close_after is not None and self.reads > self.close_after:
            raise T.ConsoleClosed("the scripted console closed (Hunter2-Secret-Value)")
        if self.pending:
            data = self.pending.pop(0)
            self.clock.now += 0.01
            if len(data) > max_bytes:
                self.pending.insert(0, data[max_bytes:])
                data = data[:max_bytes]
            return data
        self.clock.now += timeout
        return b""

    def write(self, data):
        if self.fail_write is not None:
            raise self.fail_write
        self.writes.append((self.reads, data))
        self.bytes_written += len(data)
        for _ in range(data.count(b"\r")):
            if self.answers:
                self.pending.append(self.answers.pop(0))
        return len(data)

    def written(self) -> bytes:
        return b"".join(d for _r, d in self.writes)


def session(the_plan, clock, settle=0.5, quiet=5.0, timeout=60.0, values=NO_VALUES):
    return S.ConsoleSession(SWITCH, the_plan, start=clock(), settle_s=settle, quiet_s=quiet,
                            step_timeout_s=timeout, values=values)


def surveyed(clock, **over):
    sends, answers = session_fixture()
    console = Scripted(clock, greeting=[PNP], answers=answers, **over)
    return sends, console, session(SURVEY, clock)


# ── The real text, exactly the plan's bytes ──────────────────────────────────────────────

def test_the_real_session_runs_to_done_writing_exactly_the_plans_bytes():
    clock = Clock()
    sends, console, s = surveyed(clock)
    result = run_held(console, s, clock, bound_s=BOUND)
    assert (result.outcome, result.reason, result.state) == ("done", "ended in priv_exec",
                                                            S.DONE)
    assert [d for _r, d in console.writes] == sends == [b"\r", b"enable\r", b"dir nvram:\r"]
    assert result.sent == console.written() == b"\renable\rdir nvram:\r"
    assert result.bytes_written == 19
    assert result.attach_state == P.PRESS_RETURN
    assert ">>> sent 'enable\\r'" in result.transcript
    assert "startup-config" in result.transcript


def test_the_boot_text_in_small_chunks_ends_with_nothing_written():
    clock = Clock()
    text = BOOT + PNP
    console = Scripted(clock, greeting=[text[i:i + 7] for i in range(0, len(text), 7)])
    result = run_held(console, session(plan(final=(P.PRESS_RETURN,)), clock), clock,
                        bound_s=BOUND)
    assert (result.outcome, result.bytes_written, console.writes) == ("done", 0, [])


def test_telnet_negotiation_is_never_answered():
    clock = Clock()
    sends, console, s = surveyed(clock)
    console.pending = [NEGOTIATE, PNP]
    result = run_held(console, s, clock, bound_s=BOUND)
    assert result.outcome == "done"
    assert console.written() == b"".join(sends)


def test_a_prompt_is_answered_only_by_a_tick_after_it_settled():
    """The prompt arrives in one read and decides nothing yet (it has not settled); the send
    comes after an empty read's tick, with the settle interval passed."""
    clock = Clock()
    console = Scripted(clock, greeting=[b"\r\nSwitch#"])
    s = session(plan((P.PRIV_EXEC, b"show version\r")), clock)
    run_held(console, s, clock, bound_s=5.0)
    (first_read, data), = console.writes[:1]
    assert data == b"show version\r"
    # Read 1 brought the prompt (0.01 s); reads 2, 3 and 4 were quiet, 0.2 s each, and the
    # fourth's tick (0.61 s) is the first past the 0.5 s settle interval: the write follows it.
    assert first_read == 4


def test_nothing_is_written_after_done_whatever_arrives():
    clock = Clock()
    sends, console, s = surveyed(clock)
    console.answers.append(b"\r\nSwitch#")             # more than the plan asks for
    result = run_held(console, s, clock, bound_s=BOUND)
    assert result.outcome == "done" and console.written() == b"".join(sends)
    reads = console.reads
    assert run_held(console, s, clock, bound_s=BOUND).outcome == "done"
    assert console.reads == reads and console.written() == b"".join(sends)


# ── Every way it stops ───────────────────────────────────────────────────────────────────

def test_a_password_prompt_aborts_and_nothing_is_written_after_it():
    clock = Clock()
    console = Scripted(clock, greeting=[PNP], answers=[b"\r\nPassword: "])
    result = run_held(console, session(SURVEY, clock), clock, bound_s=BOUND)
    assert result.outcome == "aborted"
    assert "found login_password" in result.reason
    assert console.written() == b"\r"
    assert result.bytes_written == 1


def test_the_far_end_closing_ends_the_run_with_its_words_masked():
    clock = Clock()
    sends, console, s = surveyed(clock, close_after=1)
    s.values = {"Hunter2-Secret-Value": "device-password"}
    result = run_held(console, s, clock, bound_s=BOUND)
    assert result.outcome == "closed"
    assert "Hunter2-Secret-Value" not in result.reason
    assert "the scripted console closed (<redacted:device-password>)" == result.reason
    assert console.written() == b"\r"                 # the greeting's line was answered


def test_a_failed_write_ends_the_run_saying_how_many_bytes():
    clock = Clock()
    sends, console, s = surveyed(clock, fail_write=BrokenPipeError("pipe gone"))
    result = run_held(console, s, clock, bound_s=BOUND)
    assert result.outcome == "closed"
    assert result.reason == "writing the plan's 1 bytes failed: pipe gone"
    assert result.bytes_written == 0


def test_a_closed_transport_raised_on_write_is_closed_too():
    clock = Clock()
    _sends, console, s = surveyed(clock, fail_write=T.ConsoleClosed("gone"))
    assert run_held(console, s, clock, bound_s=BOUND).outcome == "closed"


def test_the_bound_stops_a_console_that_keeps_talking():
    """Complete lines forever never decide a state and never abort before the step bound;
    the run's own bound stops it, named."""
    clock = Clock()
    console = Scripted(clock, greeting=[b"syslog line\r\n"] * 10000)
    s = session(plan((P.PRIV_EXEC, b"\r")), clock, timeout=600.0)
    result = run_held(console, s, clock, bound_s=3.0)
    assert result.outcome == "bound"
    assert result.reason == ("the run's bound of 3 s passed in state output, waiting for "
                             "priv_exec (step 1 of 1)")
    assert console.writes == []


def test_the_bound_counts_from_the_runs_start_on_its_clock():
    clock = Clock(1000.0)
    console = Scripted(clock, greeting=[b"syslog line\r\n"] * 10000)
    s = session(plan((P.PRIV_EXEC, b"\r")), clock, timeout=600.0)
    run_held(console, s, clock, bound_s=3.0)
    assert 1003.0 <= clock.now < 1003.1


def test_the_bound_is_reached_exactly_at_its_value():
    """Quiet reads of exactly 0.25 s each (binary-exact): the fourth brings the clock to the
    bound exactly, and the run stops there, before a fifth read (the mutation run of
    2026-10-22: `>=` made `>` survived)."""
    clock = Clock(0.0)
    console = Scripted(clock)
    s = session(plan((P.PRIV_EXEC, b"\r")), clock, timeout=600.0)
    result = run_held(console, s, clock, bound_s=1.0, poll_s=0.25)
    assert (result.outcome, console.reads, clock.now) == ("bound", 4, 1.0)


def test_the_bound_is_required_and_above_zero():
    clock = Clock()
    console = Scripted(clock)
    with pytest.raises(TypeError):
        run_held(console, session(SURVEY, clock), clock)   # pylint: disable=missing-kwoa
    for bound in (0, -1.0):
        with pytest.raises(ValueError, match=f"bound_s {bound} must be above 0"):
            run_held(console, session(SURVEY, clock), clock, bound_s=bound)
    assert console.reads == 0


def test_a_plan_whose_every_step_is_answered_late_completes_inside_its_bound():
    """Each step's answer comes just inside the step bound: the plan completes (about 38 s),
    and the same run with a bound under that ends at the bound."""
    clock = Clock()
    s = session(SURVEY, clock, timeout=10.0)
    _sends, answers = session_fixture()

    class Slow(Scripted):
        """Every answer, the first prompt included, comes after 9 s of silence: inside the
        10 s step bound, and about 38 s in all, over 3 steps' 30."""

        def read(self, max_bytes, timeout):
            if self.reads == 0:
                self.clock.now += 9.0
            return super().read(max_bytes, timeout)

        def write(self, data):
            n = super().write(data)
            self.clock.now += 9.0
            return n

    console = Slow(clock, greeting=[PNP], answers=answers)
    start = clock()
    result = run_held(console, s, clock, bound_s=40.0)
    assert result.outcome == "done", result.reason
    assert 36.0 < clock.now - start < 40.0
    clock = Clock()
    s = session(SURVEY, clock, timeout=10.0)
    console = Slow(clock, greeting=[PNP], answers=session_fixture()[1])
    assert run_held(console, s, clock, bound_s=30.0).outcome == "bound"


def test_a_stalled_step_is_ended_by_the_sessions_own_bound_first():
    clock = Clock()
    console = Scripted(clock, greeting=[b"syslog line\r\n"] * 100000)
    s = session(SURVEY, clock, quiet=2.0, timeout=4.0)
    result = run_held(console, s, clock, bound_s=BOUND)
    assert result.outcome == "aborted" and "within 4 s" in result.reason


@pytest.mark.parametrize("poll", [0.5, 0.6, 0.0, -0.1])
def test_a_poll_that_could_miss_the_settle_interval_is_refused(poll):
    clock = Clock()
    console = Scripted(clock)
    with pytest.raises(ValueError, match="under the session's settle_s"):
        run_held(console, session(SURVEY, clock), clock, poll_s=poll, bound_s=BOUND)
    assert console.reads == 0


def test_the_bytes_written_are_this_runs_only():
    clock = Clock()
    sends, console, s = surveyed(clock)
    console.bytes_written = 5
    assert run_held(console, s, clock, bound_s=BOUND).bytes_written == 19


def test_each_read_asks_for_at_most_the_chunk():
    clock = Clock()
    seen = []

    class Sized(Scripted):
        def read(self, max_bytes, timeout):
            seen.append((max_bytes, timeout))
            return super().read(max_bytes, timeout)

    console = Sized(clock, greeting=[PNP])
    run_held(console, session(plan(final=(P.PRESS_RETURN,)), clock), clock, chunk=64,
               bound_s=BOUND, poll_s=0.1)
    assert seen and set(seen) == {(64, 0.1)}
    assert len(seen) > len(PNP) // 64       # the greeting came in 64-byte reads


def test_the_defaults_are_the_modules():
    clock = Clock()
    seen = []

    class Sized(Scripted):
        def read(self, max_bytes, timeout):
            seen.append((max_bytes, timeout))
            return super().read(max_bytes, timeout)

    run_held(Sized(clock, greeting=[PNP]), session(plan(final=(P.PRESS_RETURN,)), clock),
               clock, bound_s=BOUND)
    assert set(seen) == {(T.CHUNK, T.POLL_S)} and (T.CHUNK, T.POLL_S) == (4096, 0.2)


def test_the_result_is_logged_without_the_transcript(caplog):
    clock = Clock()
    _sends, console, s = surveyed(clock)
    with caplog.at_level("INFO", logger="modules.nsot.console_transport"):
        run_held(console, s, clock, bound_s=BOUND)
    assert "a scripted console ended done after 19 bytes written (ended in priv_exec)" in \
        caplog.text
    assert "startup-config" not in caplog.text


# ── A send needs its device held (C1559) ─────────────────────────────────────────────────

def test_a_send_for_a_device_this_thread_does_not_hold_writes_nothing():
    """The fixture holds DEVICE; another device of the same network is not held, so the
    survey's first CR is refused and nothing reaches the console."""
    clock = Clock()
    _sends, console, s = surveyed(clock)
    result = T.run_plan(console, s, clock, bound_s=BOUND, device=(DEVICE[0], "edge2"))
    assert (result.outcome, console.writes, result.bytes_written) == ("refused", [], 0)
    assert result.reason == (f"this thread does not hold edge2 in {DEVICE[0]}, and a console "
                             "write needs the device held by its operation (C1559): nothing "
                             "was written")


@pytest.mark.parametrize("device", [None, (), ("console-run-plan",), ("", "edge1"),
                                    ("console-run-plan", ""), ["console-run-plan", "edge1"]])
def test_a_send_naming_no_device_writes_nothing(device):
    clock = Clock()
    _sends, console, s = surveyed(clock)
    result = T.run_plan(console, s, clock, bound_s=BOUND, device=device)
    assert (result.outcome, console.writes) == ("refused", [])
    assert result.reason == (f"a console write names the device it is for, as (network, "
                             f"hostname), and {device!r} was given: nothing was written")


def test_a_device_held_by_another_thread_is_not_held_here():
    """The hold is this thread's: a second thread running the plan for the held device is
    refused (device_ops' re-entrance is per thread)."""
    import threading

    clock = Clock()
    _sends, console, s = surveyed(clock)
    got = []
    worker = threading.Thread(target=lambda: got.append(
        T.run_plan(console, s, clock, bound_s=BOUND, device=DEVICE)))
    worker.start()
    worker.join(10)
    assert got[0].outcome == "refused" and console.writes == []


def test_a_plan_that_sends_nothing_needs_no_device():
    clock = Clock()
    console = Scripted(clock, greeting=[PNP])
    result = T.run_plan(console, session(plan(final=(P.PRESS_RETURN,)), clock), clock,
                        bound_s=BOUND)
    assert (result.outcome, console.writes) == ("done", [])


def test_a_hold_released_before_a_later_send_refuses_that_send():
    """The check is at each send, not once: the device released after the first phase, the
    next phase's first send is refused."""
    from modules.nsot import device_ops

    clock = Clock()
    sends, answers = session_fixture()
    console = Scripted(clock, greeting=[PNP], answers=answers)
    s = session(plan((P.PRESS_RETURN, b"\r"), final=(P.USER_EXEC,)), clock)
    assert run_held(console, s, clock, bound_s=BOUND).outcome == "done"
    device_ops.release(*DEVICE)
    then = plan((P.USER_EXEC, b"enable\r"), final=(P.PRIV_EXEC,))
    result = T.run_plan(console, s, clock, bound_s=BOUND, device=DEVICE, plan=then)
    assert result.outcome == "refused"
    assert console.written() == sends[0]
    device_ops.acquire(*DEVICE, "console survey", "test@example.invalid")


def test_a_continued_plan_sends_its_first_step_from_the_prompt_the_last_ended_on():
    """`plan=`: the session's next plan begins at the prompt its last plan ended on, and that
    first send is written by the loop (checked like every other)."""
    clock = Clock()
    sends, answers = session_fixture()
    console = Scripted(clock, greeting=[PNP], answers=answers)
    s = session(plan((P.PRESS_RETURN, b"\r"), final=(P.USER_EXEC,)), clock)
    first = run_held(console, s, clock, bound_s=BOUND)
    assert (first.outcome, console.written()) == ("done", b"\r")
    then = plan((P.USER_EXEC, b"enable\r"), (P.PRIV_EXEC, b"dir nvram:\r"))
    second = run_held(console, s, clock, bound_s=BOUND, plan=then)
    assert (second.outcome, second.reason) == ("done", "ended in priv_exec")
    assert console.written() == b"".join(sends)
    assert second.bytes_written == len(b"enable\rdir nvram:\r")
    assert "startup-config" in s.received_since_send()
