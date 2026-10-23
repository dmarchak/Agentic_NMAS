"""C1414: `scripts/nmas-test` run from a terminal neither stops on the terminal nor ignores
Ctrl+C.

The operator, 2026-10-20: a run from an interactive terminal hung for ever (pytest in state T,
`do_signal_stop`) and Ctrl+C could not reach it. `timeout` without `--foreground` runs its
command in a process group of its own, a BACKGROUND group on the terminal: the first touch of
the terminal stops it (SIGTTOU), and the terminal's Ctrl+C goes to the foreground group it is
not in. The gate and CI run with no terminal and never met it.

Each case runs the real script under a real pseudo-terminal (it is the session's controlling
terminal, the script in its foreground group, as a person's shell runs it) on a planted test
file, with a bound of its own so a hang fails the test instead of hanging the suite:

- a planted test that sets the terminal's attributes (what stops a background group) passes;
- a planted test that sleeps is interrupted by Ctrl+C within seconds.
"""

import os
import pty
import select
import signal
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-test")

TOUCHES_THE_TERMINAL = '''
import os
import termios


def test_touches_the_terminal():
    """What a background process group is stopped for: setting the terminal's attributes."""
    fd = os.open("/dev/tty", os.O_RDWR)
    try:
        termios.tcsetattr(fd, termios.TCSANOW, termios.tcgetattr(fd))
    finally:
        os.close(fd)
'''

SLEEPS = '''
import time


def test_sleeps(tmp_path_factory):
    open(__file__ + ".started", "w").close()
    time.sleep(60)
'''


def _spawn(planted):
    """`nmas-test` on *planted* under a pseudo-terminal: ``(pid, master fd)``."""
    env = dict(os.environ, NMAS_TEST_TIMEOUT="90", PYTHON=sys.executable, TERM="dumb")
    env.pop("NMAS_TEST_INFLIGHT", None)
    env.pop("PYTEST_XDIST_WORKER", None)
    pid, fd = pty.fork()
    if pid == 0:                                                  # the child: the terminal's
        os.chdir(os.path.dirname(planted))                       # session, in its foreground
        os.execvpe("bash", ["bash", SCRIPT, "--allow-unconfined", "-q", "-p",
                            "no:cacheprovider", "-p", "no:randomly", planted], env)
    return pid, fd


def _read_until(fd, pid, deadline, want=None):
    """Read the terminal until the run ends (or *want* appears): ``(rc or None, text)``."""
    out = b""
    while time.time() < deadline:
        ready, _w, _x = select.select([fd], [], [], 0.5)
        if ready:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                chunk = b""
            out += chunk
        if want and want():
            return None, out.decode(errors="replace")
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            try:
                out += os.read(fd, 65536)
            except OSError:
                pass
            return os.waitstatus_to_exitcode(status), out.decode(errors="replace")
    return None, out.decode(errors="replace")


def _end(pid):
    try:
        os.killpg(pid, signal.SIGKILL)       # the session the test made: its own, by identity
    except ProcessLookupError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass


def test_a_run_that_touches_the_terminal_is_not_stopped(tmp_path):
    planted = tmp_path / "test_planted_terminal.py"
    planted.write_text(TOUCHES_THE_TERMINAL)
    pid, fd = _spawn(str(planted))
    try:
        rc, out = _read_until(fd, pid, time.time() + 60)
        assert rc is not None, f"the run did not end within 60 s (stopped on the terminal):\n{out}"
        assert rc == 0 and "1 passed" in out, out
    finally:
        _end(pid)
        os.close(fd)


def test_ctrl_c_reaches_the_run(tmp_path):
    planted = tmp_path / "test_planted_sleep.py"
    planted.write_text(SLEEPS)
    pid, fd = _spawn(str(planted))
    try:
        started = str(planted) + ".started"
        rc, out = _read_until(fd, pid, time.time() + 60, want=lambda: os.path.exists(started))
        assert rc is None and os.path.exists(started), f"the planted test never started:\n{out}"
        # Into the planted test's sleep, not the instant between its marker and the sleep: CI
        # #1090 (2026-10-23) sent it there and pytest's capture raised "was already stopped"
        # before printing KeyboardInterrupt (C1599). The marker is the test's first line, so
        # half a second puts the interrupt inside the 60 s sleep on any runner.
        time.sleep(0.5)
        os.write(fd, b"\x03")                                    # Ctrl+C, as the terminal sends it
        rc, more = _read_until(fd, pid, time.time() + 20)
        assert rc is not None, f"Ctrl+C did not end the run within 20 s:\n{out}{more}"
        assert rc != 0 and "KeyboardInterrupt" in out + more, out + more
    finally:
        _end(pid)
        os.close(fd)
