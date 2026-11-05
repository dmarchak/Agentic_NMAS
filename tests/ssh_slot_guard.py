"""No SSH session slot lock outlives the test that took it (the operator, 2026-11-05).

`modules.connection` takes one cross-process slot per session, a `flock` on
``<store>/ssh_slots/<ip>/<n>.lock``, kept in the process-wide `connection._slots`. A test that
left a session open, or cleared the session count without closing it, left its lock held by the
worker. The next test whose child process opened sessions on the same address found the
device's budget full, and failed far from the cause: the laptop kit's gate failed twice,
2026-11-05, on tests/test_ssh_slots_across_processes.py, for locks that
tests/test_discovery_reads.py had leaked.

So every test's teardown checks for held locks. One still held fails THAT test, by name, and is
released, so no later test inherits it. Imported into tests/conftest.py, autouse; a child pytest
loads it alone with ``-p tests.ssh_slot_guard`` (tests/test_ssh_slot_guard.py).
"""
import os
import sys

import pytest


def held() -> list:
    """Each slot lock this process holds, ``"<ip> slot <n>"``; [] when the connection module was
    never imported (nothing could have been taken)."""
    conn = sys.modules.get("modules.connection")
    if conn is None:
        return []
    return sorted(f"{ip} slot {n}" for ip, n in list(conn._slots))


def release() -> None:
    """Close and forget every slot lock this process holds."""
    conn = sys.modules.get("modules.connection")
    if conn is None:
        return
    with conn._sessions_mu:
        for key, (fd, _sid) in list(conn._slots.items()):
            conn._slots.pop(key, None)
            try:
                os.close(fd)
            except OSError:
                pass


@pytest.fixture(autouse=True)
def _no_ssh_slot_lock_outlives_its_test(request):
    yield
    leaked = held()
    if leaked:
        release()
        pytest.fail(f"{request.node.nodeid} left SSH session slot lock(s) held at its teardown: "
                    f"{', '.join(leaked)}. A session it opened was never disconnected, or its "
                    "count was cleared without closing it (`connection._slots`). Released now, "
                    "so no later test inherits them", pytrace=False)
