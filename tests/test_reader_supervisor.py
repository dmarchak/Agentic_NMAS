"""C3330: a reader thread that STOPS is started again by Mercury itself (modules/reader_job.py,
the supervisor), and is a person's row only when it keeps stopping.

A read that keeps failing is a live thread, already its job-health row (`failing`); a thread
that dies (anything `_loop` does not catch: here a BaseException raised in a read) was a
`stale` row until a person restarted the app. Held here, on planted readers whose threads
really die, counted, never timed:

- a dead thread is started again at the supervisor's next look, recorded with who ("Mercury's
  self-healing"), the reader, why and the exception's type, and History draws each restart;
- the next restart waits out its backoff; a row only from `RESTARTS_BEFORE_ROW` restarts within
  `RESTART_WINDOW_SECONDS`, and none once the window has passed;
- only this process's own reader threads are touched: no process is signalled or started, and a
  thread that was never started, or is alive, is left alone.
"""

import os
import threading
import types

import pytest

from modules import history_sources as HS
from modules import reader_job as R


class Die(BaseException):
    """What `_loop`'s `except Exception` does not catch: the thread ends."""


@pytest.fixture
def sup(tmp_path, monkeypatch):
    """A supervisor of this test's own: its store, its threads, its stop event; any other
    supervisor a test started is stopped first, so none looks at these threads."""
    R._stop.set()                                       # noqa: SLF001 (ends other supervisors)
    monkeypatch.setattr(R, "_stop", threading.Event())
    monkeypatch.setattr(R, "_threads", {})
    monkeypatch.setattr(R, "_DEATHS", {}, raising=False)  # this change adds it
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr(R, "store_path", lambda name: str(tmp_path / "readers" / f"{name}.json"))
    reads = []

    def read():
        reads.append(1)
        raise Die("a read that ends its thread")
    reader = R.Reader(name="t-dies", what="a test's reader whose thread dies",
                      endpoints=("a test",), interval_seconds=5, interval_basis="a test",
                      read=read, invalidates=("logs",))
    R.register(reader)
    monkeypatch.setattr(R, "readers", lambda: [reader])

    def no_process(*a, **kw):
        raise AssertionError("the supervisor touched a process")
    monkeypatch.setattr(os, "kill", no_process)
    monkeypatch.setattr("subprocess.Popen", no_process)
    try:
        yield types.SimpleNamespace(reader=reader, reads=reads)
    finally:
        R.unregister("t-dies")
        R._stop.set()                                   # noqa: SLF001
        for t in list(R._threads.values()):             # noqa: SLF001
            if getattr(t, "ident", None) is not None:   # a thread never started is not joined
                t.join(5)


def _dead(reader):
    t = R._spawn(reader, None)                          # noqa: SLF001 (the real start)
    t.join(5)
    assert not t.is_alive()


class TestTheSupervisor:
    def test_a_dead_thread_is_started_again_and_recorded(self, sup):
        _dead(sup.reader)
        assert R._DEATHS["t-dies"]["type"] == "Die"     # noqa: SLF001
        now = 1_800_000_000.0
        assert R.supervise_once(now=now) == ["t-dies"]
        R._threads["t-dies"].join(5)                    # noqa: SLF001 (it dies again)
        assert len(sup.reads) == 2, "the restarted thread ran its read"
        (row,) = R.restarts()["rows"]
        assert (row["reader"], row["who"], row["type"], row["attempt"]) == (
            "t-dies", "Mercury's self-healing", "Die", 1)
        assert "its thread stopped: Die: a read that ends its thread" == row["why"]

    def test_history_draws_each_restart(self, sup):
        _dead(sup.reader)
        R.supervise_once(now=1_800_000_000.0)
        ctx = {"ref": types.SimpleNamespace(name="Lab"), "device": "", "limit": 50,
               "since": None, "members": set(), "until": None, "call": ""}
        (ev,) = HS.reader_restarts(ctx)["events"]
        assert ev["kind"] == "reader_restart" and ev["who"] == "Mercury's self-healing"
        assert ev["what"].startswith("Reader t-dies started again: its thread stopped: Die")
        assert ("Exception", "Die") in ev["record"]
        assert "reader_restart" in HS.KIND_FILTERS["reader_restarts"]
        assert HS.reader_restarts(dict(ctx, device="edge1"))["events"] == []

    def test_the_next_restart_waits_its_backoff_and_a_row_only_past_the_threshold(self, sup):
        now = 1_800_000_000.0
        restarted = []
        for step in range(0, 400, 5):                   # the supervisor's looks, 5 s apart
            t = R._threads.get("t-dies")                # noqa: SLF001
            if t is None:
                _dead(sup.reader)
            else:
                t.join(5)
            got = R.supervise_once(now=now + step)
            restarted += [now + step] * len(got)
            row = R.restart_row(sup.reader, now + step)
            n = len(restarted)
            assert (row is not None) == (n >= R.RESTARTS_BEFORE_ROW), (step, n, row)
        gaps = [b - a for a, b in zip(restarted, restarted[1:])]
        # At once, then 15 s, 30 s, 60 s, 120 s: rule 14's backoff, never a loop.
        assert gaps[:4] == [15, 30, 60, 120], gaps
        row = R.restart_row(sup.reader, now + 400)
        assert row["state"] == "restarting" and "Mercury started it again" in row["detail"]
        assert row["action"]["href"] == "/v2/history?kind=reader_restarts"
        # An hour on, with no restart since, the row is gone (it clears by time).
        assert R.restart_row(sup.reader, restarted[-1] + R.RESTART_WINDOW_SECONDS + 1) is None

    def test_health_rows_draws_it_as_the_readers_row(self, sup):
        now = 1_800_000_000.0
        for i in range(R.RESTARTS_BEFORE_ROW):
            R._record_restart({"at": R._iso(now + i), "at_ts": now + i,   # noqa: SLF001
                               "reader": "t-dies", "why": "planted", "type": "Die",
                               "who": R.RESTART_DOER, "attempt": i + 1})
        (row,) = R.health_rows(now=now + 10, population=[sup.reader])
        assert (row["unit"], row["state"]) == ("reader:t-dies", "restarting")
        from modules import attention as A
        assert A._JOB_STATES["restarting"][1] == "warning"  # noqa: SLF001

    def test_a_live_thread_or_one_never_started_is_left_alone(self, sup):
        never = threading.Thread(target=lambda: None)
        R._threads["t-dies"] = never                    # noqa: SLF001
        assert R.supervise_once(now=1_800_000_000.0) == []
        gate = threading.Event()
        alive = threading.Thread(target=gate.wait, daemon=True)
        alive.start()
        R._threads["t-dies"] = alive                    # noqa: SLF001
        try:
            assert R.supervise_once(now=1_800_000_000.0) == []
        finally:
            gate.set()
            alive.join(5)
        assert R.restarts()["rows"] == []

    def test_a_stopped_app_restarts_nothing(self, sup):
        _dead(sup.reader)
        R._stop.set()                                   # noqa: SLF001
        assert R.supervise_once(now=1_800_000_000.0) == []
