"""Mercury's own test runner for a job's folder (the SDN platform design rev. 6, section 11a,
item 2; decisions 27 and 28; T24): `modules/jobs/runner.py`, the standard library in one
process.

Planted here: pytest's format run without pytest (plain functions, fixtures by name, the
`pytest.raises` shim, the SDK's `refused()`); a failed assertion naming both operands, each
evaluated once; the folder's imports and files refused by name; a loop that never ends stopped
at the run's bound and named; nothing forked, nothing left in `sys.modules`. And T24's
condition: the same folder, unmutated, gets the same pass or fail per test from real pytest
(run as a subprocess from THIS test; the no-fork rule binds the runner) as from the runner."""

import ast
import os
import shutil
import subprocess
import sys
import threading
import types
import xml.etree.ElementTree as ET

import pytest

from modules.jobs import runner as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "tests", "fixtures", "jobs")
FOLDERS = ("switch-links", "arp-guard", "tautology")
CONFTEST = os.path.join(JOBS, "switch-links", "conftest.py")

JOB = '''"""A planted job."""
from modules.jobs import Job, JobInputs, JobMeta, Scope


def double(n):
    return n * 2


class Doubler(Job):
    meta = JobMeta(name="doubler", version="1.0.0", summary="Doubles a number.",
                   permission="read", scope=Scope(object_types=["dcim.device"]))

    class Inputs(JobInputs):
        n: int = 1

    def run(self, ctx, inputs):
        ctx.output.log(str(double(inputs.n)))
'''

#: A test module whose tests pass and fail in every way the runner tells apart: the T24 case.
MIXED = '''import pytest

from job import double
from modules.jobs import refused


def test_passes():
    assert double(2) == 4


def test_fails_a_comparison():
    assert double(2) == 5


def test_fails_a_bare_assert():
    assert double(0)


def test_raises_passes():
    with pytest.raises(TypeError):
        double(None)


def test_raises_not_raised():
    with pytest.raises(ValueError):
        double(1)


def test_raises_another_exception():
    with pytest.raises(ValueError):
        double(None)


def test_raises_as_a_call():
    pytest.raises(TypeError, double, None)


def test_raises_match_differs():
    with pytest.raises(TypeError, match="^nothing like it$"):
        double(None)


def test_refused_passes(ctx):
    with refused("permission is 'read'"):
        ctx.changes.flow(1, "add_flow", flow={"priority": 1})


def test_refused_not_raised(ctx):
    with refused():
        ctx.output.log("nothing refused")


def test_an_exception_fails():
    assert {}["missing"]


def test_the_recorded_ryu(ryu):
    assert len(ryu.dpids()) == len(ryu.get("/stats/switches"))


def test_an_unknown_fixture(database):
    assert database


def test_a_default_is_not_a_fixture(n=3):
    assert n == 3


def helper_not_a_test():
    assert False
'''


def plant(tmp_path, tests: dict, job: str = JOB, name: str = "job") -> str:
    """A job folder under *tmp_path*: `job.py` and the test files given."""
    folder = tmp_path / name
    folder.mkdir()
    if job is not None:
        (folder / "job.py").write_text(job)
    for file, text in tests.items():
        (folder / file).parent.mkdir(parents=True, exist_ok=True)
        (folder / file).write_text(text)
    return str(folder)


def run(tmp_path, tests: dict, **kw) -> R.RunResult:
    return R.run_folder(plant(tmp_path, tests, **{k: v for k, v in kw.items() if k == "job"}),
                        **{k: v for k, v in kw.items() if k == "bound"})


def outcome(result, name) -> R.TestResult:
    return next(t for t in result.tests if t.id.endswith(f"::{name}"))


# ── a failed assertion names its operands ────────────────────────────────────────────────────

def test_a_failing_comparison_names_both_operands(tmp_path):
    got = run(tmp_path, {"test_a.py": "def test_x():\n    assert 3 == 4\n"})
    assert got.tests[0].outcome == "failed"
    assert got.tests[0].message == "assert 3 == 4: left 3, right 4 (==) (at test_a.py:2)"


def test_each_side_is_evaluated_once(tmp_path):
    got = run(tmp_path, {"test_a.py": (
        "calls = []\n\n\ndef side(v):\n    calls.append(v)\n    return v\n\n\n"
        "def test_once():\n    assert side(3) == side(4)\n\n\n"
        "def test_counted():\n    assert calls == [3, 4]\n")})
    assert outcome(got, "test_once").message.startswith(
        "assert side(3) == side(4): left 3, right 4 (==)")
    assert outcome(got, "test_counted").passed


def test_a_chain_is_checked_pair_by_pair_and_short_circuits(tmp_path):
    got = run(tmp_path, {"test_a.py": (
        "def boom():\n    raise RuntimeError('evaluated')\n\n\n"
        "def test_first_pair():\n    assert 1 < 0 < boom()\n\n\n"
        "def test_second_pair():\n    assert 0 < 1 < 1\n")})
    assert outcome(got, "test_first_pair").message.startswith(
        "assert 1 < 0 < boom(): left 1, right 0 (<)")
    assert outcome(got, "test_second_pair").message.startswith(
        "assert 0 < 1 < 1: left 1, right 1 (<)")


@pytest.mark.parametrize("line, words", [
    ("assert []", "assert []: []"),
    ("x = 0\n    assert x, 'the count'", "assert x: 0; the count"),
    ("assert 1 in [2]", "assert 1 in [2]: left 1, right [2] (in)"),
    ("assert None is not None", "assert None is not None: left None, right None (is not)"),
    ("assert 'a' * 300 == 'b'", "right 'b' (==)"),
])
def test_each_assertion_form_names_its_values(tmp_path, line, words):
    got = run(tmp_path, {"test_a.py": f"def test_x():\n    {line}\n"})
    assert words in got.tests[0].message, got.tests[0].message


def test_a_long_value_is_cut_to_its_limit():
    assert len(R.assert_value("x", "a" * 1000, None)) < R.REPR_MAX + 20
    assert R.assert_value("x", "a" * 1000, None).endswith("...")


# ── pytest's format without pytest ───────────────────────────────────────────────────────────

def test_the_runner_and_the_sdk_never_import_pytest_or_start_a_process():
    banned = {"pytest", "subprocess", "multiprocessing", "concurrent", "signal"}
    found = []
    for name in ("runner", "mutate", "gate", "authoring", "spec"):
        path = os.path.join(ROOT, "modules", "jobs", f"{name}.py")
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found += [(name, a.name) for a in node.names if a.name.split(".")[0] in banned]
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in banned:
                found.append((name, node.module))
            elif isinstance(node, ast.Attribute) and node.attr in ("fork", "Thread", "system",
                                                                   "popen", "spawnv"):
                found.append((name, node.attr))
    assert found == []


def test_a_run_forks_nothing_and_starts_no_thread(tmp_path, monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("the runner started a process or a thread")
    monkeypatch.setattr(os, "fork", refuse, raising=False)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(threading.Thread, "start", refuse)
    got = R.run_folder(os.path.join(JOBS, "switch-links"))
    assert got.passed, [t.message for t in got.failures()]


def test_the_pytest_a_test_gets_is_the_runners_shim(tmp_path):
    got = run(tmp_path, {"test_a.py": (
        "import pytest\n\n\ndef test_shim():\n    assert not hasattr(pytest, 'mark')\n"
        "    assert pytest.raises is not None\n")})
    assert got.passed, [t.message for t in got.failures()]


def test_pytest_beyond_raises_is_refused_by_name(tmp_path):
    got = run(tmp_path, {"test_a.py": (
        "import pytest\n\n\n"
        "@pytest.fixture\ndef thing():\n    return 1\n\n\n"
        "def test_x(thing):\n    assert thing\n")})
    assert got.tests[0].outcome == "error"
    assert "the runner's pytest offers raises() alone, not pytest.fixture" in got.tests[0].message


def test_the_mixed_folder_tells_each_outcome_apart(tmp_path):
    got = run(tmp_path, {"test_mixed.py": MIXED})
    passed = {t.id.split("::")[1] for t in got.tests if t.passed}
    assert passed == {"test_passes", "test_raises_passes", "test_raises_as_a_call",
                      "test_refused_passes", "test_the_recorded_ryu",
                      "test_a_default_is_not_a_fixture"}
    assert "helper_not_a_test" not in {t.id.split("::")[1] for t in got.tests}
    assert outcome(got, "test_fails_a_bare_assert").message.startswith(
        "assert double(0): 0")
    assert outcome(got, "test_raises_not_raised").message.startswith(
        "DID NOT RAISE ValueError")
    assert outcome(got, "test_raises_another_exception").message.startswith("TypeError: ")
    assert "does not match '^nothing like it$'" in outcome(
        got, "test_raises_match_differs").message
    assert outcome(got, "test_refused_not_raised").message.startswith(
        "DID NOT RAISE ContractError: refused() expected")
    assert outcome(got, "test_an_exception_fails").message.startswith("KeyError: 'missing'")
    unknown = outcome(got, "test_an_unknown_fixture")
    assert unknown.outcome == "error"
    assert "no fixture named 'database': a job's test may ask for ctx, netbox, ryu" in \
        unknown.message


def test_netbox_without_objects_names_the_export_it_waits_for(tmp_path):
    got = run(tmp_path, {"test_a.py": "def test_x(netbox):\n    assert netbox\n"})
    assert got.tests[0].outcome == "error"
    assert "tests/fixtures/lab9_netbox/" in got.tests[0].message


def test_ctx_needs_exactly_one_job_class(tmp_path):
    got = run(tmp_path, {"test_a.py": "def test_x(ctx):\n    assert ctx\n"},
              job="def helper():\n    return 1\n")
    assert got.tests[0].outcome == "error"
    assert "exactly one Job class" in got.tests[0].message and "found 0" in got.tests[0].message


def test_ctx_is_the_folders_job_with_the_recorded_controller(tmp_path):
    got = run(tmp_path, {"test_a.py": (
        "def test_x(ctx, ryu):\n    assert ctx.meta.name == 'doubler'\n"
        "    assert len(ctx.controller.switches()['switches']) == len(ryu.dpids())\n")})
    assert got.passed, [t.message for t in got.failures()]


# ── what the folder may import, and its files ────────────────────────────────────────────────

def test_an_import_off_the_list_is_refused_at_run_time(tmp_path):
    got = run(tmp_path, {"test_a.py": "import os\n\n\ndef test_x():\n    assert os\n"})
    assert got.tests[0].outcome == "error"
    assert "'os' is not a module a job's folder may import" in got.tests[0].message


def test_a_forbidden_builtin_is_not_there(tmp_path):
    got = run(tmp_path, {"test_a.py": "def test_x():\n    assert open('x')\n"})
    assert got.tests[0].outcome == "failed"
    assert got.tests[0].message.startswith("NameError: name 'open' is not defined")


def test_a_relative_import_is_refused(tmp_path):
    got = run(tmp_path, {"test_a.py": "from . import job\n\n\ndef test_x():\n    assert job\n"})
    assert "a relative import" in got.tests[0].message


def test_a_job_module_that_raises_on_import_is_not_kept(tmp_path):
    job = "raise RuntimeError('broken')\n"
    got = run(tmp_path, {"test_a.py": "import job\n\n\ndef test_x():\n    assert job\n",
                         "test_b.py": "import job\n\n\ndef test_y():\n    assert job\n"}, job=job)
    assert [t.outcome for t in got.tests] == ["error", "error"]
    assert all("RuntimeError: broken" in t.message for t in got.tests)


@pytest.mark.parametrize("make, words", [
    (lambda f: (f / "json.py").write_text("x = 1\n"), "json.py: a job's module is named"),
    (lambda f: (f / "my-job.py").write_text("x = 1\n"), "my-job.py: a job's module is named"),
    (lambda f: ((f / "pkg").mkdir(), (f / "pkg" / "x.py").write_text("x = 1\n")),
     "pkg/: holds Python"),
    (lambda f: (f / "bad.py").write_bytes(b"x = '\xff'\n"), "bad.py: is not UTF-8"),
    (lambda f: (f / "big.py").write_text("#" * (R.MAX_FILE_BYTES + 1)), "big.py: is "),
    (lambda f: (f / "link.py").symlink_to(f / "job.py"), "link.py: is a symbolic link"),
])
def test_a_folder_file_the_runner_will_not_read_is_named(tmp_path, make, words):
    folder = plant(tmp_path, {"test_a.py": "def test_x():\n    assert 1\n"})
    make(__import__("pathlib").Path(folder))
    with pytest.raises(R.SourceError) as exc:
        R.load_sources(folder)
    assert any(p.startswith(words) for p in exc.value.problems), exc.value.problems


def test_the_conftest_is_ignored_and_pycache_is_no_subfolder(tmp_path):
    folder = plant(tmp_path, {"test_a.py": "def test_x():\n    assert 1\n",
                              "conftest.py": "raise RuntimeError('read by the runner')\n"})
    os.mkdir(os.path.join(folder, "__pycache__"))
    got = R.run_folder(folder)
    assert got.passed


PASSING = "from job import double\n\n\ndef test_x():\n    assert double(2) == 4\n"


def test_tests_at_the_root_and_in_a_tests_subfolder_are_both_found_and_run(tmp_path):
    """C2636: the conventional tests/ subfolder, and the folder's root, and nowhere else."""
    got = run(tmp_path, {"test_root.py": PASSING, "tests/test_sub.py": PASSING,
                         "tests/conftest.py": "raise RuntimeError('read by the runner')\n"})
    assert got.passed
    assert [t.id for t in got.tests] == ["test_root.py::test_x", "tests/test_sub.py::test_x"]


def test_a_failure_in_the_tests_subfolder_names_its_file_and_line(tmp_path):
    got = run(tmp_path, {"tests/test_sub.py": "def test_x():\n    assert 1 == 2\n"})
    assert got.tests[0].message == "assert 1 == 2: left 1, right 2 (==) (at tests/test_sub.py:2)"


@pytest.mark.parametrize("files, words", [
    ({"tests/helpers.py": "x = 1\n"}, "tests/helpers.py: tests/ holds test_*.py files (and a "
                                      "conftest.py) only"),
    ({"tests/unit/test_deep.py": PASSING}, "tests/unit/: holds Python, and a folder's tests "
                                           "sit at its root or in tests/ itself"),
    ({"checks/test_elsewhere.py": PASSING}, "checks/: holds Python, and a job's modules sit in "
                                            "its folder's top level, its tests there or in "
                                            "tests/"),
    ({"tests/test_root.py": PASSING}, "tests/test_root.py: a test file of the same name is at "
                                      "the folder's root"),
])
def test_a_test_anywhere_else_is_refused_by_name(tmp_path, files, words):
    folder = plant(tmp_path, {"test_root.py": PASSING, **files})
    with pytest.raises(R.SourceError) as exc:
        R.load_sources(folder)
    assert exc.value.problems == [words] or any(p.startswith(words)
                                                for p in exc.value.problems), exc.value.problems


@pytest.mark.parametrize("path, ok", [
    ("test_a.py", True), ("tests/test_a.py", True), ("a_test.py", False),
    ("tests/helpers.py", False), ("tests/unit/test_a.py", False), ("lib/test_a.py", False),
    ("test_a.txt", False)])
def test_the_one_layout_rule(path, ok):
    assert (R.test_location_problem(path) == "") is ok


def test_a_test_class_and_an_async_test_are_refused_by_name(tmp_path):
    got = run(tmp_path, {"test_a.py": (
        "class TestThings:\n    def test_x(self):\n        assert 1\n\n\n"
        "async def test_y():\n    assert 1\n\n\ndef test_z():\n    assert 1\n")})
    assert not got.passed
    assert [t.id for t in got.tests] == ["test_a.py::test_z"]
    assert any("test_a.py::TestThings (line 1): a test class" in p for p in got.problems)
    assert any("test_a.py::test_y (line 6): an async test" in p for p in got.problems)


def test_a_folder_without_tests_does_not_pass(tmp_path):
    got = run(tmp_path, {})
    assert got.tests == [] and not got.passed


# ── the bound ────────────────────────────────────────────────────────────────────────────────

SPIN = '''def spin():
    while True:
        try:
            pass
        except Exception:
            pass
'''


def test_a_loop_that_never_ends_is_stopped_at_the_bound_and_named(tmp_path):
    got = run(tmp_path, {"test_a.py": (
        "from job import spin\n\n\ndef test_spins():\n    assert spin()\n\n\n"
        "def test_after():\n    assert 1\n")}, job=SPIN, bound=0.2)
    first, after = got.tests
    assert first.outcome == "stopped"
    assert first.message.startswith("stopped at the bound of 0.200 s, after 0.2")
    assert after.outcome == "not run"
    assert got.stopped == first.message and not got.passed
    assert 0.2 <= got.seconds < 0.2 + 2.0


def test_a_loop_at_import_is_stopped_too(tmp_path):
    got = run(tmp_path, {"test_a.py": "import job\n\n\ndef test_x():\n    assert job\n"},
              job="while True:\n    pass\n", bound=0.2)
    assert got.tests[0].outcome == "stopped"
    assert "importing test_a.py: stopped at the bound of 0.200 s" in got.tests[0].message


def test_the_monitoring_id_is_given_back(tmp_path):
    before = [sys.monitoring.get_tool(t) for t in R.TOOL_IDS]
    run(tmp_path, {"test_a.py": "def test_x():\n    assert 1\n"})
    assert [sys.monitoring.get_tool(t) for t in R.TOOL_IDS] == before


def test_an_interpreter_without_monitoring_is_refused_naming_its_version(monkeypatch, tmp_path):
    folder = plant(tmp_path, {"test_a.py": "def test_x():\n    assert 1\n"})
    monkeypatch.setattr(R, "sys", types.SimpleNamespace(version="3.11.9 (main)"))
    with pytest.raises(R.RunnerError) as exc:
        R.run_folder(folder)
    assert "Python 3.12 or later; this interpreter is 3.11.9" in str(exc.value)


def test_each_test_is_timed_within_the_run(tmp_path):
    got = R.run_folder(os.path.join(JOBS, "arp-guard"))
    assert got.passed
    assert all(t.seconds >= 0 for t in got.tests)
    assert got.seconds >= sum(t.seconds for t in got.tests)
    assert got.bound == R.FIRST_RUN_SECONDS


def test_fail_fast_stops_at_the_first_failure(tmp_path):
    folder = plant(tmp_path, {"test_mixed.py": MIXED})
    got = R.run(R.prepare(R.load_sources(folder)), fail_fast=True)
    outcomes = [t.outcome for t in got.tests]
    assert outcomes[:2] == ["passed", "failed"]
    assert set(outcomes[2:]) == {"not run"}


def test_a_run_leaves_the_interpreter_as_it_found_it(tmp_path):
    folder = os.path.join(JOBS, "switch-links")
    R.run_folder(folder)                    # the SDK's own modules imported once
    modules, path, meta_path = set(sys.modules), list(sys.path), list(sys.meta_path)
    R.run_folder(folder)
    assert set(sys.modules) == modules and "job" not in sys.modules
    assert sys.path == path and sys.meta_path == meta_path


# ── T24: pytest agrees, test by test ─────────────────────────────────────────────────────────

#: The pytest run's bound. Measured 2026-11-06 on the laptop, CI's Python 3.12.3, coverage on
#: and off: 0.22 s to 0.30 s per folder. 2.5x that (0.75 s) is inside what a loaded CI
#: runner's scheduling alone can add, so this is PROVISIONAL at 10 s until the CI log's
#: --durations line measures the run there (a finding to register).
PYTEST_BOUND_SECONDS = 10


def pytest_outcomes(folder: str, tmp_path) -> dict:
    """`{test id: passed}` from real pytest over a copy of *folder* (its fixed conftest.py
    giving the fixtures), read from its JUnit XML."""
    root = tmp_path / "pytest-root"
    copy = root / "job"
    shutil.copytree(folder, copy)
    if not (copy / "conftest.py").exists():
        shutil.copy(CONFTEST, copy / "conftest.py")
    (root / "pytest.ini").write_text("[pytest]\n")
    xml = root / "results.xml"
    env = dict(os.environ, PYTHONPATH=ROOT, PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTEST_XDIST_WORKER", None)
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:cacheprovider",
         "-c", str(root / "pytest.ini"), "--rootdir", str(root), f"--junitxml={xml}",
         str(copy)], cwd=str(root), env=env, capture_output=True, text=True,
        timeout=PYTEST_BOUND_SECONDS)
    assert xml.exists(), out.stdout[-1500:] + out.stderr[-800:]
    got = {}
    for case in ET.parse(xml).getroot().iter("testcase"):
        # `job.test_x` at the folder's root, `job.tests.test_x` in its tests/ subfolder
        module = case.get("classname").split(".", 1)[1].replace(".", "/")
        bad = [c for c in case if c.tag in ("failure", "error", "skipped")]
        got[f"{module}.py::{case.get('name')}"] = not bad
    return got


@pytest.mark.parametrize("name", FOLDERS)
def test_pytest_and_the_runner_agree_on_each_fixture_job(name, tmp_path):
    folder = os.path.join(JOBS, name)
    ours = R.run_folder(folder).outcomes()
    assert ours and all(ours.values())
    assert pytest_outcomes(folder, tmp_path) == ours


def test_pytest_and_the_runner_agree_on_tests_in_a_tests_subfolder(tmp_path):
    """C2636: the same ids and outcomes from pytest's discovery of tests/ as from the
    runner's, a passing and a failing test in each place."""
    folder = plant(tmp_path, {"test_root.py": PASSING, "tests/test_sub.py": PASSING
                              + "\n\ndef test_y():\n    assert double(2) == 5\n"})
    ours = R.run_folder(folder).outcomes()
    assert ours == {"test_root.py::test_x": True, "tests/test_sub.py::test_x": True,
                    "tests/test_sub.py::test_y": False}
    assert pytest_outcomes(folder, tmp_path) == ours


def test_pytest_and_the_runner_agree_on_every_kind_of_failure(tmp_path):
    folder = plant(tmp_path, {"test_mixed.py": MIXED})
    ours = R.run_folder(folder).outcomes()
    assert sorted(set(ours.values())) == [False, True]
    assert pytest_outcomes(folder, tmp_path) == ours
