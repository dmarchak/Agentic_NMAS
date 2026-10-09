"""The suite's four CI jobs (`scripts/nmas-shards`; the operator, 2026-10-03: a run took 6.5
to 9 minutes, 93% of it the tests; two of them browser jobs since C614).

- Every test file runs in exactly one job, found by its name (`tests/test_*.py`), so a new
  file runs the moment it exists; every file that starts a real browser is in a browser job,
  and both browser jobs hold some.
- The jobs share the measured work (tests/shard_weights.json) within 15% of each other, and
  the weights know most of the files (a stale map is said, not silently unbalanced).
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


def test_every_browser_file_is_in_a_browser_job_and_both_hold_some():
    m = _shards()
    users = [f for f in m.test_files() if m.uses_a_browser(f)]
    assert len(users) >= 8
    got = m.assign()
    assert set(users) <= {f for s in m.BROWSER_SHARDS for f in got[s]}
    assert all(set(users) & set(got[s]) for s in m.BROWSER_SHARDS), "both browser jobs"


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
    # Since C614 the browser files (40% of the suite, 2026-10-09) go to two jobs, so all four
    # can share the work within 15% again.
    assert max(loads.values()) <= 1.15 * min(loads.values()), loads


def test_the_same_input_gives_the_same_jobs():
    m = _shards()
    assert m.assign() == m.assign()
