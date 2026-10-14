"""C773: a push measures each test's run phase by tier (tests/coverage_tiers.py), and the coverage
tool reads that data (scripts/nmas_coverage.py's `_tier_of`, `data_kind`, `data_line`).

Measured on the same tree (2026-10-14), the whole suite both ways: the per-test contexts and
this gave the same figure, unit and every tier, for every one of 4,263 functions (C782 is the
one function whose unit reach can move with xdist's order), and the tests step went from about
10 minutes a shard to about 5 on CI's runners. Here a nested pytest run, with
sys.monitoring and the plugin, over a planted module: what a unit test's run phase reached is
`unit|run`; what only a fixture reached is no test's; what a test that starts a process reached
is `other|run`.
"""
import os
import subprocess
import sys

import coverage
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import nmas_coverage as C  # noqa: E402

PLANTED = '''def unit_only():
    return 1


def fixture_only():
    return 2


def other_only():
    return 3


def teardown_only():
    return 4
'''

PROBE = '''import subprocess
import sys

import pytest

import planted


@pytest.fixture
def warmed():
    planted.fixture_only()
    return True


def test_a_unit_test():
    assert planted.unit_only() == 1


def test_one_with_a_fixture(warmed):
    assert warmed


@pytest.fixture
def closing():
    yield
    planted.teardown_only()


def test_one_that_starts_a_process(closing):
    assert planted.other_only() == 3
    subprocess.run([sys.executable, "-c", "pass"], check=True)
'''


def _lines(source, name):
    import ast
    fn = next(n for n in ast.parse(source).body if getattr(n, "name", "") == name)
    return set(range(fn.body[0].lineno, fn.end_lineno + 1))


@pytest.fixture
def measured(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "planted.py").write_text(PLANTED)
    probe = tmp_path / "test_probe_tiers.py"
    probe.write_text(PROBE)
    env = dict(os.environ, NMAS_PROBE_RUN="1", COVERAGE_CORE="sysmon", NMAS_COVERAGE_TIERS="1",
               COVERAGE_FILE=str(tmp_path / ".coverage"),
               PYTHONPATH=os.pathsep.join([str(pkg), os.environ.get("PYTHONPATH", "")]))
    env.pop("PYTEST_XDIST_WORKER", None)
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:cacheprovider",
         "-p", "tests.conftest", "--rootdir", ROOT, "-c", os.path.join(ROOT, "pytest.ini"),
         f"--cov={pkg}", "--cov-report=", str(probe)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout[-1500:] + out.stderr[-800:]
    files = [str(p) for p in tmp_path.iterdir() if p.name.startswith(".coverage")]
    data = coverage.CoverageData(str(tmp_path / "combined"))
    for f in files:
        part = coverage.CoverageData(f)
        part.read()
        data.update(part)
    planted = next(f for f in data.measured_files() if f.endswith("planted.py"))
    return data, data.contexts_by_lineno(planted)


class TestEachRunPhaseIsMeasuredByTier:
    def test_a_unit_test_s_run_phase_is_unit(self, measured):
        _data, by_line = measured
        assert all("unit|run" in by_line.get(l, []) for l in _lines(PLANTED, "unit_only"))

    def test_what_only_a_fixture_reached_is_no_test_s(self, measured):
        _data, by_line = measured
        ctxs = {c for l in _lines(PLANTED, "fixture_only") for c in by_line.get(l, [])}
        assert not ctxs & {"unit|run", "other|run"}, ctxs

    def test_what_only_the_last_teardown_reached_is_not_counted_at_all(self, measured):
        """pytest-cov saves its own data at the session's end before this plugin's hook runs,
        so the last test's teardown once reached it as "" (measured 2026-10-14: an autouse
        fixture's `redact.reset_health` counted as covered by every tier)."""
        _data, by_line = measured
        ctxs = {c for l in _lines(PLANTED, "teardown_only") for c in by_line.get(l, [])}
        assert ctxs == set(), ctxs

    def test_a_test_that_starts_a_process_is_other(self, measured):
        _data, by_line = measured
        ctxs = {c for l in _lines(PLANTED, "other_only") for c in by_line.get(l, [])}
        assert "other|run" in ctxs and "unit|run" not in ctxs, ctxs

    def test_the_tool_reads_it_as_tier_labelled(self, measured):
        data, _by_line = measured
        assert C.data_kind(data.measured_contexts()) == "by tier"
        assert C.data_kind(["tests/test_x.py::test_y|run", ""]) == "per test"


class TestTheToolSaysWhichDataItUsed:
    def test_a_label_is_its_own_tier_and_a_test_its_record(self):
        assert C._tier_of("unit", {}) == "unit" and C._tier_of("other", {}) == "other"
        assert C._tier_of("tests/test_x.py::t", {"tests/test_x.py::t": "browser"}) == "browser"

    def test_a_push_names_the_drilldown_and_its_date_and_says_when_there_is_none(self):
        line = C.data_line({"data": "by tier"}, "2026-10-15T03:47:00Z, https://example.invalid/1")
        assert "by tier" in line and "2026-10-15T03:47:00Z" in line
        assert "(none found)" in C.data_line({"data": "by tier"}, "")
        assert "a context per test, with branches" in C.data_line({"data": "per test"})

    def test_a_push_s_page_says_the_tests_by_name_are_the_night_s(self):
        fn = {"name": "f", "line": 1, "unit_tests": ["unit"], "other_tests": [],
              "covered_unit": True, "covered_any": True}
        mod = {"path": "modules/x.py", "category": "automation", "functions": 1,
               "covered_unit": 1, "covered_any": 1, "function_pct_unit": 100.0,
               "function_pct_any": 100.0, "line_pct_unit": 100.0, "branch_pct_any": None,
               "function_list": [fn], "excluded": []}
        report = {"modules": {"modules/x.py": mod}, "tiers": {}, "assertion_free": [],
                  "data": "by tier"}
        page = C.html_report(report, [], "2026-10-15T03:47:00Z, https://example.invalid/1")
        assert "the tests by name: the nightly coverage run" in page
        assert "2026-10-15T03:47:00Z" in page
