"""C1864: no test leaves a planned-restart window, a window's end or a restart in the session's
store.

The session's data directory lives for the whole run, and a window is read by everything after
it: Needs attention quiets an alert on a device a window covers, and a device's History draws
the window. `test_history_one_timeline`'s `planted` (used by `test_history_paging`) declared
two windows over the list Lab there, and `test_reload_v2`'s run declared and ended one for r2
in Lab; `test_evidence_pack`'s lab, its list also named Lab, then drew two windows in r1's
History and lost r2's alert row, only when one of those ran first in the same process (each
file passed alone and in the other order).

Each leaker's fixture now keeps the record in its test's own folder (`restarts._data`), and
tests/conftest.py's `_no_test_leaves_a_restart_record` (and its module twin) puts back each of
the record's files a test changed and fails that test naming them: a silent reset would hide
the next leaker (C1522's rule for the reader stores).

Both checks run in a child pytest under this suite's own conftest, in one process and in the
order that failed.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The leakers first, then the two cases that lost to them, in one process (C1864's order).
ORDER = ["tests/test_history_paging.py::TestTheRealSources",
         "tests/test_reload_v2.py::TestTheRun",
         "tests/test_evidence_pack.py::TestThePackFromTheCaptures"
         "::test_an_ipv6_device_by_its_polled_address",
         "tests/test_evidence_pack.py::TestTheTab::test_a_needs_attention_alert_row_opens_its_card"]

LEAKER = '''
import os
import time


def _record():
    from modules import config
    path = os.path.join(config.DATA_DIR, "planned_restarts.jsonl")
    return open(path, "rb").read() if os.path.exists(path) else None


BEFORE = []


def test_keeps_the_record_as_it_starts():
    BEFORE.append(_record())


def test_declares_a_window_and_leaves_it():
    from modules import restarts
    now = time.time()
    assert restarts.record_planned(["r2"], now, now + 600, "ana@example.invalid",
                                   "a leaking test", "test", list_name="Lab")["ok"]


def test_the_next_test_finds_the_record_as_it_was():
    assert _record() == BEFORE[0]


def test_one_that_keeps_the_record_in_its_own_folder_passes(tmp_path, monkeypatch):
    from modules import restarts
    monkeypatch.setattr(restarts, "_data", lambda name: str(tmp_path / name))
    now = time.time()
    assert restarts.record_planned(["r2"], now, now + 600, "ana@example.invalid",
                                   "its own record", "test", list_name="Lab")["ok"]
    assert (tmp_path / "planned_restarts.jsonl").exists()
'''


def _child(args, timeout):
    env = {k: v for k, v in os.environ.items() if k != "NMAS_DATA_DIR"}
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly",
         *args],
        cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
    return out.returncode, out.stdout + out.stderr


def test_the_leakers_then_the_evidence_pack_in_one_process_pass():
    """C1864's order in one process: every leaker's case, then r1's History and r2's alert
    row. Measured 2026-10-26: 6.9 s on the laptop, the child's start included; 2.5 times it is
    17 s, and the bound is 60 s because CI's runner, slower and unmeasured for this child,
    runs it beside another worker."""
    code, text = _child(ORDER, timeout=60)
    assert code == 0, text
    assert " failed" not in text and " error" not in text, text


def test_a_leaking_test_fails_naming_itself_and_the_record(tmp_path):
    """The guard, run for real: the leaking test fails naming itself and the file, and the test
    after it finds the record as it was. Measured 2026-10-26: 1.8 s; bounded as C1522's twin
    is."""
    leaker = tmp_path / "test_c1864_leaker.py"
    leaker.write_text(LEAKER, encoding="utf-8")
    code, text = _child(["-p", "tests.conftest", "--rootdir", ROOT, str(leaker)], timeout=180)
    assert code != 0, text
    assert ("test_declares_a_window_and_leaves_it left the restart record changed in the "
            "session's store: planned_restarts.jsonl. It is put back" in text), text
    assert "4 passed, 1 error" in text, text
