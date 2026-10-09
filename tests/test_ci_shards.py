"""The suite's three CI jobs (`scripts/nmas-shards`; the operator, 2026-10-03: a run took 6.5
to 9 minutes, 93% of it the tests).

- Every test file runs in exactly one job, found by its name (`tests/test_*.py`), so a new
  file runs the moment it exists; every file that starts a real browser is in the browser job.
- The jobs share the measured work (tests/shard_weights.json) within 15% of each other (the
  browser job heavier only when it holds nothing but its browser files, C614), and the
  weights know most of the files (a stale map is said, not silently unbalanced).
- The same input gives the same jobs.
"""

import importlib.machinery
import importlib.util
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _shards():
    path = os.path.join(ROOT, "scripts", "nmas-shards")
    loader = importlib.machinery.SourceFileLoader("nmas_shards", path)
    spec = importlib.util.spec_from_loader("nmas_shards", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_every_test_file_runs_in_exactly_one_job():
    m = _shards()
    got = m.assign()
    files = sorted(f"tests/{n}" for n in os.listdir(os.path.join(ROOT, "tests"))
                   if re.fullmatch(r"test_\w+\.py", n))
    assert len(files) >= 300
    every = [f for s in m.SHARDS for f in got[s]]
    assert sorted(every) == files, "every file once, none twice, none left out"


def test_every_browser_file_is_in_the_browser_job():
    m = _shards()
    users = [f for f in m.test_files() if m.uses_a_browser(f)]
    assert len(users) >= 8
    assert set(users) <= set(m.assign()["browser"])


def test_the_jobs_share_the_work_and_the_weights_are_current():
    m = _shards()
    w = m.weights()
    files = m.test_files()
    known = [f for f in files if f in w]
    assert len(known) >= 0.9 * len(files), (
        f"{len(files) - len(known)} test files have no measured weight: measure again "
        "(--durations=0) and rewrite tests/shard_weights.json")
    got = m.assign()
    loads = {s: sum(w.get(f, 0) for f in fs) for s, fs in got.items()}
    # a and b share the rest within 15%. The browser job may weigh more only when it holds its
    # browser files and nothing else: they cannot be split (the gate runs only that job
    # unconfined), and since 2026-10-09 they weigh 40% of the suite (C614), so the browser job
    # is the long pole by construction, not by the assignment.
    assert max(loads["a"], loads["b"]) <= 1.15 * min(loads["a"], loads["b"]), loads
    if loads["browser"] > 1.15 * min(loads["a"], loads["b"]):
        assert all(m.uses_a_browser(f) for f in got["browser"]), (
            "the browser job is heavier and still takes other files", loads)
    else:
        assert max(loads.values()) <= 1.15 * min(loads.values()), loads


def test_the_same_input_gives_the_same_jobs():
    m = _shards()
    assert m.assign() == m.assign()
