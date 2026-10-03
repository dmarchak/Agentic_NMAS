"""One run per reader at a time, and never an older value over a newer one
(CONCURRENCY_AUDIT R28).

The scheduled loop, a run on request and the post-commit refresh could all run one reader
at once. Each read happened before the store's lock, so a slower run that started first
stored LAST and replaced a fresher value; two `app-pushed` runs could `git fetch` one
checkout at once. Measured here:

- two runs of one reader in one process never read at once, and a run that starts while a
  slow one reads stores the NEWER value last;
- a run waits while another PROCESS holds the reader's run, and proceeds when it ends;
- a value read later than this run began is never replaced by this run's older one, and the
  attempt is still recorded.
"""

import os
import subprocess
import sys
import threading
import time

import pytest

from modules import config
from modules import reader_job as R
from tests.test_reader_job import make, store  # noqa: F401  (the store fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestOneRunAtATime:
    def test_two_runs_never_read_at_once_and_the_newer_value_is_stored_last(self):
        state = {"in": 0, "max": 0, "n": 0}
        mu = threading.Lock()
        first_reading = threading.Event()

        def read():
            with mu:
                state["n"] += 1
                me = state["n"]
                state["in"] += 1
                state["max"] = max(state["max"], state["in"])
            if me == 1:
                first_reading.set()
                time.sleep(0.5)          # the slow, OLDER read
            with mu:
                state["in"] -= 1
            return {"read": me}

        reader = make(read)
        a = threading.Thread(target=R.run_once, args=(reader,))
        a.start()
        assert first_reading.wait(5)
        b = threading.Thread(target=R.run_once, args=(reader,))
        b.start()                        # starts while the first is still reading
        a.join(10)
        b.join(10)
        assert state["max"] == 1, "two runs of one reader read at the same time"
        stored = R.read_cached("t-reader")["doc"]["last_good"]["value"]
        assert stored == {"read": 2}, f"the older value was stored last: {stored}"

    def test_a_run_waits_while_another_process_holds_the_reader(self, tmp_path):
        reader = make(lambda: {"ok": 1})
        script = tmp_path / "hold.py"
        script.write_text(
            "import sys, time\n"
            f"sys.path.insert(0, {ROOT!r})\n"
            "import modules.config as C\n"
            "C.DATA_DIR = sys.argv[1]\n"
            "from modules import filestore, reader_job as R\n"
            "with filestore.PathLock(R.store_path('t-reader') + '.run'):\n"
            "    print('held', flush=True)\n"
            "    time.sleep(30)\n", encoding="utf-8")
        child = subprocess.Popen([sys.executable, str(script), config.DATA_DIR],
                                 stdout=subprocess.PIPE, text=True)
        done = threading.Event()
        try:
            assert child.stdout.readline().strip() == "held"
            t = threading.Thread(target=lambda: (R.run_once(reader), done.set()))
            t.start()
            assert not done.wait(0.6), "the run did not wait for the other process"
            assert R.read_cached("t-reader")["state"] != "ok"
        finally:
            child.kill()
            child.wait(10)
        assert done.wait(10)
        assert R.read_cached("t-reader")["doc"]["last_good"]["value"] == {"ok": 1}


class TestNeverAnOlderValue:
    def test_a_value_read_later_is_kept_and_the_attempt_recorded(self):
        reader = make(lambda: {"v": "older"})
        R.run_once(make(lambda: {"v": "newer"}), clock=lambda: 2_000_000_000.0)
        R.run_once(reader, clock=lambda: 1_000_000_000.0)       # began before that read
        doc = R.read_cached("t-reader")["doc"]
        assert doc["last_good"]["value"] == {"v": "newer"}
        assert len(doc["runs"]) == 2 and doc["last_attempt"]["ok"] is True

    def test_a_later_read_replaces_an_earlier_one(self):
        R.run_once(make(lambda: {"v": 1}), clock=lambda: 1_000_000_000.0)
        R.run_once(make(lambda: {"v": 2}), clock=lambda: 2_000_000_000.0)
        assert R.read_cached("t-reader")["doc"]["last_good"]["value"] == {"v": 2}
