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
    assert all(set(users) & set(got[s]) for s in m.BROWSER_SHARDS), "every browser job"


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


def _weights_tool():
    path = os.path.join(ROOT, "scripts", "nmas-shard-weights")
    loader = importlib.machinery.SourceFileLoader("nmas_shard_weights", path)
    spec = importlib.util.spec_from_loader("nmas_shard_weights", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _junit(path, cases):
    body = "".join(f'<testcase classname="{c}" name="t{i}" time="{t}"/>'
                   for i, (c, t) in enumerate(cases))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<?xml version="1.0"?><testsuites><testsuite name="pytest">{body}'
                    "</testsuite></testsuites>", encoding="utf-8")


def test_the_weights_tool_sums_each_file_and_takes_the_median_over_runs(tmp_path):
    """C1637: a file's seconds are its cases' sum in one run (a class's cases and a module's
    count alike, across a run's shards), its weight the median over the runs that ran it."""
    t = _weights_tool()
    assert t.test_file("tests.test_x.TestY") == "tests/test_x.py"
    assert t.test_file("tests.test_x") == "tests/test_x.py" and t.test_file("conftest") == ""
    _junit(tmp_path / "r1" / "coverage-a" / "junit-a.xml",
           [("tests.test_x.TestY", 1.5), ("tests.test_x", 0.5), ("tests.test_z", 9)])
    _junit(tmp_path / "r1" / "coverage-b" / "junit-b.xml", [("tests.test_w", 4)])
    _junit(tmp_path / "r2" / "junit-a.xml", [("tests.test_x.TestY", 6), ("tests.test_w", 2)])
    _junit(tmp_path / "r3" / "junit-a.xml", [("tests.test_x", 3), ("tests.test_w", 5)])
    (tmp_path / "r3" / "other.xml").write_text("<not-junit/>", encoding="utf-8")
    got = t.measured([str(tmp_path / r) for r in ("r1", "r2", "r3")])
    assert got == {"tests/test_x.py": 3.0, "tests/test_w.py": 4.0, "tests/test_z.py": 9.0}


def test_today_s_placement_is_read_in_the_runner_s_seconds():
    """The imbalance a push meets: the files placed by today's weights, each shard's load in
    the runner's seconds (a placement read in its own weights is balanced by construction)."""
    t = _weights_tool()
    m = _shards()
    files = m.test_files()
    old = {f: 1.0 for f in files}
    runner = {f: (10.0 if f == files[0] else 1.0) for f in files}
    today = t.loads(m, old, runner)
    assert max(today.values()) - min(today.values()) >= 9.0, today
    assert t.loads(m, old) != today, "read in its own weights it hides the heavy file"


def test_a_file_no_run_measured_keeps_its_weight_scaled_to_the_runner():
    """The files both know say the runner is twice the weights; a file only the weights know
    doubles, one only the runner knows is its seconds, one neither knows has none."""
    t = _weights_tool()
    out, scaled = t.merged({"a": 10, "b": 20, "old": 5}, {"a": 20, "b": 40, "new": 7},
                           ["a", "b", "old", "new", "unknown"])
    assert out == {"a": 20, "b": 40, "old": 10.0, "new": 7} and scaled == 1


def test_the_weights_tool_names_both_loads_and_refuses_an_empty_measurement(tmp_path, capsys):
    t = _weights_tool()
    m = _shards()
    files = m.test_files()
    _junit(tmp_path / "r1" / "junit-a.xml",
           [(f[:-3].replace("/", "."), 1.0) for f in files])
    assert t.main([str(tmp_path / "r1")]) == 0
    said = capsys.readouterr().out
    assert said.startswith("placed today ") and "\nplaced measured " in said, said
    assert said.count("runner seconds") == 2, said
    assert f"files measured {len(files)}, kept and scaled 0, of {len(files)}" in said, said
    assert t.main([str(tmp_path / "nothing")]) == 1
    assert "no JUnit test case" in capsys.readouterr().err
