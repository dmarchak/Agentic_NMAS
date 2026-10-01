"""The tests THIS process ran, most recent last (not a test module).

Filled by conftest's `pytest_runtest_logstart`, in every process: under xdist
each worker keeps its own, which is the point. A fixture whose state another
test broke can name what ran before it on ITS worker, and that is the one
order nobody can reconstruct after the run (the operator, 2026-10-01: CI's
POST sweep failed twice on gw1, passed in 28 simulated schedules here, and
the public API serves no log saying what gw1 had run).

Kept in its own module because importing `tests.conftest` for it would run
conftest a second time (CLAUDE.md, "an instrument that re-executes its setup
can move what it measures")."""

import collections
import os
import threading

#: Enough to reach back past the module before the one failing.
KEPT = 60

RAN = collections.deque(maxlen=KEPT)


def record(nodeid: str) -> None:
    RAN.append(nodeid)


def worker() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER", "the only process")


def last_line(limit: int = 8) -> str:
    """The last *limit* tests on ONE line: CI's failure annotation carries only
    an assertion's first line (measured on run #245's)."""
    recent = list(RAN)[-limit:]
    return (f"before it, worker {worker()} ran: "
            + (", ".join(recent) if recent else "nothing recorded"))


def describe(limit: int = 25) -> str:
    """The last *limit* tests this process ran, and every other live thread,
    as lines a failure message can carry."""
    recent = list(RAN)[-limit:]
    threads = [f"{t.name} (daemon={t.daemon})" for t in threading.enumerate()
               if t is not threading.current_thread()]
    return (f"worker {worker()} ran these last ({len(recent)} of {len(RAN)} kept):\n  "
            + "\n  ".join(recent or ["(nothing recorded)"])
            + f"\nother threads alive now ({len(threads)}):\n  "
            + "\n  ".join(threads or ["(none)"]))
