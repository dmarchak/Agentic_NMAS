"""The suite's bound, and what it says when it fires (the operator, 2026-09-28).

A timeout chosen "to be safe" converts every hang into its full length, and a
bare "timed out" names nothing. So `scripts/nmas-test` bounds the run from a
MEASUREMENT (300 s, 2.5x the 121 s serial run on the laptop) and, when the
bound fires, prints the test each process was running and every thread's
stack. The per-test bound is pytest.ini's `faulthandler_timeout` (45 s, 2.5x
the slowest single item, a 17.3 s module setup), which dumps and does not stop.

This drives the REAL runner over a test that hangs, with a short bound, and
reads what it prints: the hanging test and its line named, a test that had
finished not named. The conftest's hooks are loaded as the plugin they are
(`-p tests.conftest`), because the probe lives in a temporary directory, not
in the checkout.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _runner(tmp_path, body, bound="5"):
    probe = tmp_path / "test_probe_bound.py"
    probe.write_text(body)
    env = dict(os.environ, NMAS_TEST_TIMEOUT=bound, PYTHON=sys.executable)
    env.pop("PYTEST_XDIST_WORKER", None)
    env.pop("NMAS_TEST_INFLIGHT", None)
    return subprocess.run(
        [os.path.join(ROOT, "scripts", "nmas-test"), "--allow-unconfined", "-q",
         "-p", "no:randomly", "-p", "no:cacheprovider", "-p", "tests.conftest",
         "--rootdir", ROOT, "-c", os.path.join(ROOT, "pytest.ini"), str(probe)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)


HANG = ("import time\n\n"
        "def test_finished_first():\n    pass\n\n"
        "def test_hangs_here():\n    time.sleep(600)\n")


def test_a_hang_is_named_with_its_line(tmp_path):
    out = _runner(tmp_path, HANG)
    assert out.returncode == 124, (out.returncode, out.stderr[-800:])
    err = out.stderr
    assert "TIMED OUT after 5 s" in err
    assert "test_probe_bound.py::test_hangs_here" in err, err[-800:]
    assert "test_probe_bound.py\", line 7 in test_hangs_here" in err, "no stack for the hang"
    assert "test_finished_first" not in err, "a test that finished is not what was running"


def test_a_run_that_finishes_is_never_reported_as_a_timeout(tmp_path):
    """The control: the report fires on the bound, not on every run."""
    out = _runner(tmp_path, "def test_ok():\n    pass\n")
    assert out.returncode == 0, out.stderr[-800:]
    assert "TIMED OUT" not in out.stderr + out.stdout
