"""A real browser's session ends with the test process that started it, however that process
ends (C775).

tests/browser.py starts geckodriver in a process group of its own (C521: stopping the group
stops the Firefox geckodriver starts, which stopping geckodriver alone orphaned). But a test
process that ends WITHOUT running `Browser.__exit__` (nmas-test's bound's SIGTERM, a SIGKILL,
an xdist worker lost) signalled nothing in that group, and the browser ran on: measured
2026-10-14, each of those four ends left geckodriver and its Firefox (12 processes) running,
and two such trees had been running for 1.6 and 3.7 days (0.8 GB).

So `Browser` starts this program as the group's leader:

    browser_watch.py <test process pid> <session folder> <geckodriver argv...>

It holds a pidfd on the test process (its identity, never a pid that could be reused), starts
geckodriver as its child, and waits for either to end. Then it stops every other process in its
own group (TERM, then KILL; the group this module was made for, never a name) and, when the
test process is the one that ended, removes the session's folder. It ignores SIGTERM itself
once geckodriver has started, so a stop of the whole group (`Browser.__exit__`, `stop_group`)
reaches it as "geckodriver ended" and it sweeps the rest before it exits.
"""
import os
import select
import shutil
import signal
import subprocess
import sys
import time

#: The sweep's bound per signal: Firefox ends on SIGTERM within about a second (C521's
#: stop_group waits as long).
WAIT_S = 5.0


def others_in_my_group() -> list:
    """The live processes of this program's group, itself left out, read from /proc."""
    me, group = os.getpid(), os.getpgrp()
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == me:
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as fh:
                fields = fh.read().rsplit(")", 1)[1].split()
        except OSError:
            continue
        # After the command's closing parenthesis: state, ppid, pgrp.
        if fields[0] != "Z" and int(fields[2]) == group:
            found.append(int(name))
    return found


def sweep() -> list:
    """Stop the rest of the group: SIGTERM, then SIGKILL what is left after WAIT_S. Returns
    what was still alive after both (none, normally)."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        pids = others_in_my_group()
        if not pids:
            return []
        for pid in pids:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        deadline = time.time() + WAIT_S
        while time.time() < deadline and others_in_my_group():
            time.sleep(0.05)
    return others_in_my_group()


#: pidfd_open's system call number, the same in every Linux architecture's table since 5.3. The
#: python-build-standalone 3.12.3 the gate runs has no `os.pidfd_open` (measured 2026-10-14),
#: though the kernel does; the call is made directly there.
SYS_PIDFD_OPEN = 434


def pidfd_open(pid: int) -> int:
    """A file descriptor naming the process *pid* (readable once it has ended); raises
    ProcessLookupError when it is already gone."""
    if hasattr(os, "pidfd_open"):
        return os.pidfd_open(pid)
    import ctypes
    import errno

    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.syscall(SYS_PIDFD_OPEN, ctypes.c_int(pid), ctypes.c_uint(0))
    if fd < 0:
        err = ctypes.get_errno()
        if err == errno.ESRCH:
            raise ProcessLookupError(err, os.strerror(err))
        raise OSError(err, os.strerror(err))
    return fd


def main(argv) -> int:
    watched, folder, command = int(argv[1]), argv[2], argv[3:]
    try:
        test_process = pidfd_open(watched)
    except ProcessLookupError:
        return 0                                  # it ended before the browser could start
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    # After the start: a disposition set before it would be geckodriver's too (inherited).
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    poll = select.poll()
    poll.register(test_process, select.POLLIN)
    test_ended = False
    while child.poll() is None:
        if poll.poll(500):
            test_ended = True
            break
    sweep()
    child.wait()
    if test_ended:
        shutil.rmtree(folder, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
