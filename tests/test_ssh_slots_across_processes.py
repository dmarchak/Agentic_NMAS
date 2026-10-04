"""The SSH session budget holds ACROSS PROCESSES (CONCURRENCY_AUDIT R11, 2026-10-04).

R11: the budget (a device's vty lines minus one kept for a person) counted one process, while
host CLIs (`nmas-startup-check`, `nmas-golden-state`, `nmas-capture-output`) open their own
sessions; together with the app they could take every vty line, the person's included. Now each
session takes a slot: a `flock` on ``<store>/ssh_slots/<ip>/<n>.lock``. A process holding the
whole budget refuses another process's session, naming the holder and its pid; a holder that
dies frees its slots (the kernel releases the lock); a slot this process holds for a session it
no longer counts is released before the next is taken.

Driven with a real child process holding sessions through `open_ssh`, Netmiko faked at its
boundary in both processes (no device is reached), on the test's own store.
"""

import os
import signal
import subprocess
import sys
import time

import pytest

from modules import connection as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IP = "192.0.2.31"

CHILD = '''
import os, sys, time
sys.path.insert(0, {root!r})
import netmiko

class Fake:
    def __init__(self, **kw):
        pass
    def disconnect(self):
        pass

netmiko.ConnectHandler = Fake
from modules import connection as C
C.vty_lines = lambda ip: (5, "the test's device")
held = [C.open_ssh({{"ip": sys.argv[1], "device_type": "cisco_ios"}}, owner="child:holder")
        for _ in range(int(sys.argv[2]))]
open(sys.argv[3], "w").write(str(os.getpid()))
while not os.path.exists(sys.argv[4]):
    time.sleep(0.05)
for c in held:
    c.disconnect()
'''


class Fake:
    def __init__(self, **kw):
        self.kw = kw

    def disconnect(self):
        pass


@pytest.fixture
def parent(monkeypatch):
    import netmiko
    monkeypatch.setattr(netmiko, "ConnectHandler", Fake)
    monkeypatch.setattr(C, "vty_lines", lambda ip: (5, "the test's device"))
    C._sessions.clear()
    yield
    C._sessions.clear()


def _child(tmp_path, n):
    script = tmp_path / "child.py"
    script.write_text(CHILD.format(root=ROOT))
    ready, done = tmp_path / "ready", tmp_path / "done"
    proc = subprocess.Popen([sys.executable, str(script), IP, str(n), str(ready), str(done)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 30
    while not ready.exists():
        assert proc.poll() is None, proc.communicate()
        assert time.time() < deadline, "the child never took its sessions"
        time.sleep(0.05)
    return proc, done


def _open():
    return C.open_ssh({"ip": IP, "device_type": "cisco_ios"}, owner="parent:asker")


def test_another_processes_sessions_count_against_the_budget(tmp_path, parent):
    proc, done = _child(tmp_path, 4)                       # the whole budget: 5 lines, 1 kept
    try:
        with pytest.raises(C.SessionBudgetExceeded) as got:
            _open()
        said = str(got.value)
        assert "every one of its 4 session slot(s) is held" in said
        assert f"child:holder (pid {proc.pid})" in said
        assert IP not in C._sessions or not C._sessions[IP]
    finally:
        done.write_text("")
        proc.communicate(timeout=30)
    conn = _open()                                         # released: the parent may open
    conn.disconnect()


def test_the_budget_is_shared_not_doubled(tmp_path, parent):
    proc, done = _child(tmp_path, 2)
    try:
        first, second = _open(), _open()
        with pytest.raises(C.SessionBudgetExceeded):
            _open()
        first.disconnect()
        third = _open()                                    # a slot freed by a close is free
        second.disconnect()
        third.disconnect()
    finally:
        done.write_text("")
        proc.communicate(timeout=30)


def test_a_close_frees_its_slot_for_another_process(tmp_path, parent):
    for conn in [_open() for _ in range(4)]:
        conn.disconnect()
    proc, done = _child(tmp_path, 4)                       # the child takes the whole budget
    done.write_text("")
    proc.communicate(timeout=30)
    assert proc.returncode == 0


def test_a_holder_that_dies_frees_its_slots(tmp_path, parent):
    proc, _done = _child(tmp_path, 4)
    os.kill(proc.pid, signal.SIGKILL)
    proc.communicate(timeout=30)
    conn = _open()
    conn.disconnect()


def test_a_session_this_process_stopped_counting_releases_its_slot(parent):
    held = [_open() for _ in range(4)]
    C._sessions.clear()                                    # the count lost, the slots not closed
    conn = _open()
    conn.disconnect()
    assert len(held) == 4
