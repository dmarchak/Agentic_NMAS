"""The coverage tool (scripts/nmas_coverage.py, CLI scripts/nmas-coverage; docs/TESTING.md, "The
coverage tool"), tested on fixtures whose answers are known, and on this repository's scope.

The lab's own example is the first: a module of six functions, three of them reached by a
test, reads 50%; a module no test reaches is named; a module no rule places fails the tool."""
import importlib.util
import json
import os
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load("nmas_coverage_under_test", "scripts/nmas_coverage.py")
pydefs = C.pydefs

IP_CONNECTIVITY = '''
def parse_target(text):
    """Three of these six are tested: 50%, the lab's example."""
    return text.strip()


def ping(host):
    return host != "unreachable"


def tcp_check(host, port):
    return port == 22


def traceroute(host):
    hops = [host]
    return hops


def mtu_probe(host, size):
    return size <= 1500


def summary(results):
    return {k: v for k, v in results.items()}
'''

BGP_CFG = '''
def render_neighbor(asn, peer):
    return f"neighbor {peer} remote-as {asn}"


def render_network(prefix):
    return f"network {prefix}"
'''

SCOPE = '''
AUTOMATION, SUPPORT, RETIRING, EXCLUDED = "automation", "support", "retiring", "excluded"
RULES = (("modules/", AUTOMATION, "the fixture's automation"),)
EXCEPTIONS = {"modules/gone.py": (RETIRING, "a stale exception")}


def classify(path):
    if path in EXCEPTIONS:
        return EXCEPTIONS[path]
    for prefix, category, why in RULES:
        if path.startswith(prefix):
            return (category, why)
    return None
'''


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A repository with two automation modules and one file no rule places, and a coverage
    run in which three unit tests reach three of ip_connectivity's six functions."""
    import coverage

    # The gate's and CI's COVERAGE_CORE=sysmon cannot measure branches on Python 3.12, and
    # coverage warns when it falls back: this run is the fixture's own, on the default core.
    monkeypatch.delenv("COVERAGE_CORE", raising=False)
    (tmp_path / "modules").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "other").mkdir()
    (tmp_path / "modules" / "ip_connectivity.py").write_text(IP_CONNECTIVITY)
    (tmp_path / "modules" / "bgp_cfg.py").write_text(BGP_CFG)
    (tmp_path / "other" / "loose.py").write_text("def x():\n    return 1\n")
    (tmp_path / "tests" / "coverage_scope.py").write_text(SCOPE)
    data = str(tmp_path / ".coverage")
    cov = coverage.Coverage(data_file=data, branch=True)
    cov.start()
    try:
        # Imported INSIDE the first test, as a lazy import is: every `def` line runs under that
        # test's context, so a rule that counted def lines would call all six covered.
        cov.switch_context("tests/test_ip.py::test_parse_target|run")
        spec = importlib.util.spec_from_file_location(
            "ip_connectivity_fixture", str(tmp_path / "modules" / "ip_connectivity.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for test, call in (("tests/test_ip.py::test_parse_target", lambda: mod.parse_target(" a ")),
                           ("tests/test_ip.py::test_ping", lambda: mod.ping("r1")),
                           ("tests/test_ip.py::test_tcp_check", lambda: mod.tcp_check("r1", 22))):
            cov.switch_context(f"{test}|run")
            call()
    finally:
        cov.stop()
        cov.save()
    tiers = tmp_path / "tiers"
    tiers.mkdir()
    (tiers / "tiers-gw0-1.jsonl").write_text("".join(
        json.dumps({"test": f"tests/test_ip.py::{t}", "tier": "unit"}) + "\n"
        for t in ("test_parse_target", "test_ping", "test_tcp_check")))
    files = ["modules/bgp_cfg.py", "modules/ip_connectivity.py", "other/loose.py"]
    scope = C.load_scope(str(tmp_path))
    return C.measure(data, str(tiers), root=str(tmp_path), files=files, scope=scope)


class TestTheLabsExample:
    def test_three_of_six_functions_tested_is_fifty_percent(self, lab):
        m = lab["modules"]["modules/ip_connectivity.py"]
        assert (m["covered_unit"], m["functions"], m["function_pct_unit"]) == (3, 6, 50.0)
        covered = {f["name"] for f in m["function_list"] if f["covered_unit"]}
        assert covered == {"parse_target", "ping", "tcp_check"}
        reached = {f["name"]: f["unit_tests"] for f in m["function_list"]}
        assert reached["ping"] == ["tests/test_ip.py::test_ping"], "the drill-down names the test"

    def test_a_module_no_test_reaches_is_named(self, lab):
        assert C.totals(lab)["untested_modules"] == ["modules/bgp_cfg.py"]
        assert lab["modules"]["modules/bgp_cfg.py"]["function_pct_unit"] == 0.0

    def test_a_module_no_rule_places_fails_the_tool(self, lab):
        assert lab["unclassified"] == ["other/loose.py"]
        assert lab["stale_exceptions"] == ["modules/gone.py"]

    def test_line_and_branch_figures_stand_beside_the_function_figure(self, lab):
        m = lab["modules"]["modules/ip_connectivity.py"]
        assert 0 < m["line_pct_unit"] < 100 and m["line_pct_any"] is not None

    def test_the_outputs_carry_the_figures(self, lab):
        assert "3 of 8 functions" not in C.table(lab)
        assert "modules/ip_connectivity.py" in C.table(lab) and "50.0%" in C.table(lab)
        md = C.summary_markdown(lab, [])
        assert "**3 of 8 functions (37.5%)**" in md and "`modules/bgp_cfg.py`" in md
        page = C.html_report(lab, [])
        assert "<code>modules/ip_connectivity.py</code>" in page and "50.0% unit" in page


class TestTheTiers:
    def test_a_function_reached_only_by_another_tier_is_shown_apart(self, tmp_path, lab):
        """The headline counts the unit tier; a function reached only by a spawns or browser
        test counts in the all-tiers column, and the gap between them is the finding."""
        tiers = {"tests/test_ip.py::test_ping": "spawns"}
        m = lab["modules"]["modules/ip_connectivity.py"]
        ping = next(f for f in m["function_list"] if f["name"] == "ping")
        assert ping["covered_unit"]
        source = IP_CONNECTIVITY
        by_line = {line: ["tests/test_ip.py::test_ping|run"]
                   for line in next(d for d in pydefs.definitions(source)
                                    if d.name == "ping").body_lines}
        rep = C.module_report("m.py", source, by_line, tiers, set(), {})
        assert (rep["covered_unit"], rep["covered_any"]) == (0, 1)

    def test_each_module_names_its_test_files_by_any_phase(self):
        """C1640: the index a stale map's refresh is scoped by. A test reaching the module only
        in a fixture's setup is in it (the run-phase function lists lack it: run #41's
        whole-suite refresh chose such a file); a push's tier labels name no file."""
        source = IP_CONNECTIVITY
        body = next(d for d in pydefs.definitions(source) if d.name == "ping").body_lines
        by_line = {body[0]: ["tests/test_ip.py::test_ping|run",
                             "tests/test_pages.py::TestAll::test_x|setup", "unit|run", "",
                             "tests/test_down.py::test_other|teardown"]}
        rep = C.module_report("m.py", source, by_line, {}, set(), {})
        assert rep["test_files"] == ["tests/test_down.py", "tests/test_ip.py",
                                     "tests/test_pages.py"]
        ping = next(f for f in rep["function_list"] if f["name"] == "ping")
        assert "tests/test_ip.py::test_ping" in ping["unit_tests"]
        assert not any("test_pages" in t or "test_down" in t for t in ping["unit_tests"]), \
            "the function lists keep the run phase alone"
        assert C.module_report("m.py", source, {}, {}, set(), {})["test_files"] == []


class TestWhatMakesATestSpawns:
    """The spawns tier is a test that ran OUR code in another process, whose lines coverage
    cannot credit to the test: a Python interpreter, or a program of this checkout. A local
    tool the code under test calls (Mercury commits through `git`) leaves the test in unit."""

    @pytest.mark.parametrize("args, ours", [
        (["git", "-C", "/tmp/x", "commit", "-m", "m"], False),
        ("openssl rand -hex 4", False),
        ([os.sys.executable, "-c", "0"], True),
        (["python3", "-m", "pytest"], True),
        ("bash scripts/host-steps/lib.sh", True),
        (["env", "PYTHONDONTWRITEBYTECODE=1", "scripts/nmas-config-check", "--help"], True),
        ([os.path.join(ROOT, "scripts", "nmas-coverage"), "scope"], True),
        (["/usr/bin/true"], False),
    ])
    def test_ours_or_a_tool(self, args, ours):
        from tests import network_guard
        assert network_guard.runs_our_code(args) is ours


class TestTheCountingRules:
    SOURCE = textwrap.dedent('''
        from typing import TYPE_CHECKING, Protocol, overload
        from abc import abstractmethod

        if TYPE_CHECKING:
            def only_for_types(): return 1

        def outer():
            def inner():
                return 2
            return inner()

        square = lambda x: x * x

        class Device:
            @property
            def name(self): return self._n
            @name.setter
            def name(self, v): self._n = v
            @overload
            def get(self, k: int) -> int: ...
            def get(self, k):
                return k
            @abstractmethod
            def save(self): raise NotImplementedError
            def stub(self):
                """Only a docstring."""

        class Reader(Protocol):
            def read(self) -> str: return ""

        if __name__ == "__main__":
            def cli(): return 0
    ''')

    def test_what_is_counted_and_why_the_rest_is_not(self):
        defs = [d for d in pydefs.definitions(self.SOURCE) if d.kind != "class"]
        counted = [d.qualname for d in defs if d.counted]
        assert counted == ["outer", "Device.get"], "inner and the lambda are not listed apart"
        why = {d.qualname: d.excluded for d in defs if not d.counted}
        assert why == {"only_for_types": "type_checking", "Device.name": "property",
                       "Device.get": "overload", "Device.save": "abstract",
                       "Device.stub": "stub", "Reader.read": "protocol", "cli": "main"}

    def test_a_nested_functions_lines_are_its_enclosers(self):
        outer = next(d for d in pydefs.definitions(self.SOURCE) if d.name == "outer")
        inner_return = self.SOURCE.splitlines().index("        return 2") + 1
        assert inner_return in outer.body_lines

    def test_the_duplicate_check_shares_the_walker(self):
        """tests/test_no_duplicate_definitions.py uses this walker: a property's setter is the
        one repeat it allows, a second plain def is not."""
        assert pydefs.duplicates(self.SOURCE) == []
        assert pydefs.duplicates("def a(): pass\ndef a(): pass\n") == [":a: lines 1 and 2"]


class TestTheRatchet:
    REPORT = {"modules": {
        "modules/a.py": {"category": "automation", "functions": 6, "covered_unit": 3},
        "modules/new.py": {"category": "automation", "functions": 2, "covered_unit": 0},
        "routes/x.py": {"category": "support", "functions": 4, "covered_unit": 0}},
        "assertion_free": ["tests/test_a.py::test_old", "tests/test_a.py::test_new"]}

    def test_a_lost_test_a_new_untested_module_and_a_new_assertion_free_test_fail(self):
        baseline = {"modules": {"modules/a.py": {"functions": 6, "covered_unit": 4}},
                    "assertion_free": ["tests/test_a.py::test_old"]}
        assert C.ratchet(self.REPORT, baseline) == [
            "modules/a.py: uncovered functions rose from 2 (4 of 6 covered) to 3 (3 of 6 covered)",
            "modules/new.py: a new automation module with no unit test (0 of 2 functions)",
            "tests/test_a.py::test_new: a new test that asserts nothing"]

    def test_holding_or_rising_passes_and_support_is_never_gated(self):
        baseline = C.baseline_of(self.REPORT)
        assert "routes/x.py" not in baseline["modules"]
        assert C.ratchet(self.REPORT, baseline) == []

    # C808 (the operator's decision, 2026-10-15): the UNCOVERED count, never the percentage.

    @staticmethod
    def _module(covered, uncovered=()):
        """A report's automation module from the names of its covered and uncovered
        functions."""
        fl = ([{"name": n, "covered_unit": True} for n in covered]
              + [{"name": n, "covered_unit": False} for n in uncovered])
        return {"modules": {"modules/drift_check.py": {
            "category": "automation", "functions": len(fl),
            "covered_unit": len(covered), "function_list": fl}}, "assertion_free": []}

    def test_ci_812_removing_a_covered_function_passes(self):
        """CI #812 on 48301a0a, the real case: the Drift tab's removal took `network_for`, a
        covered function, out of modules/drift_check.py; 31 of 35 became 30 of 34, the
        percentage fell (88.6% to 88.2%) and the old ratchet failed; nothing lost its test."""
        baseline = {"modules": {"modules/drift_check.py": {"functions": 35,
                                                           "covered_unit": 31}}}
        report = {"modules": {"modules/drift_check.py": {
            "category": "automation", "functions": 34, "covered_unit": 30}},
            "assertion_free": []}
        assert C.ratchet(report, baseline) == []

    def test_ci_812_with_named_functions_passes_too(self):
        """The same removal against a baseline that names its covered functions: the removed
        one is gone from the module, so its absence from the covered set is no loss."""
        covered = [f"f{i}" for i in range(30)]
        uncovered = [f"u{i}" for i in range(4)]
        baseline = C.baseline_of(self._module(covered + ["network_for"], uncovered))
        assert (baseline["modules"]["modules/drift_check.py"]["functions"],
                baseline["modules"]["modules/drift_check.py"]["covered_unit"]) == (35, 31)
        assert C.ratchet(self._module(covered, uncovered), baseline) == []

    def test_adding_an_untested_function_fails(self):
        baseline = C.baseline_of(self._module(["a", "b"], ["c"]))
        assert C.ratchet(self._module(["a", "b"], ["c", "d"]), baseline) == [
            "modules/drift_check.py: uncovered functions rose from 1 (2 of 3 covered) to "
            "2 (2 of 4 covered)"]

    def test_a_covered_function_losing_its_test_fails_by_name_while_the_count_holds(self):
        """The planted loss: `b` loses its test while `c` gains one, so the uncovered count
        holds at 1 (and the percentage too); only the names can see it."""
        baseline = C.baseline_of(self._module(["a", "b"], ["c"]))
        assert baseline["modules"]["modules/drift_check.py"].get("covered") == ["a", "b"]
        assert C.ratchet(self._module(["a", "c"], ["b"]), baseline) == [
            "modules/drift_check.py: covered in the baseline, not covered now: b (the module: "
            "1 (2 of 3 covered) then, 1 (2 of 3 covered) now)"]

    def test_a_baseline_without_names_is_read_as_counts(self):
        """The format before C808 (counts only) is still read: the count rule applies, and the
        swap above, invisible to counts, passes there; the next `nmas-coverage baseline` adds
        the names."""
        old = {"modules": {"modules/drift_check.py": {"functions": 3, "covered_unit": 2}}}
        assert C.ratchet(self._module(["a", "c"], ["b"]), old) == []
        assert C.ratchet(self._module(["a"], ["b", "c"]), old) == [
            "modules/drift_check.py: uncovered functions rose from 1 (2 of 3 covered) to "
            "2 (1 of 3 covered)"]

    def test_a_new_module_with_some_covered_passes(self):
        assert C.ratchet(self._module(["a"], ["b", "c"]), {"modules": {}}) == []


class TestTheAssertionCheck:
    def test_it_finds_a_test_that_checks_nothing_and_follows_helpers(self, tmp_path):
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "helpers.py").write_text(
            "def wait_for(x):\n    if not x:\n        raise AssertionError('never')\n")
        (tmp_path / "tests" / "test_x.py").write_text(textwrap.dedent('''
            from tests.helpers import wait_for

            def test_runs_only():
                print(1 + 1)

            def test_asserts():
                assert 1 + 1 == 2

            def test_through_a_helper():
                wait_for(True)

            class TestRaises:
                def test_raises(self):
                    import pytest
                    with pytest.raises(ValueError):
                        int("x")
        '''))
        found = C.assertion_free(["tests/test_x.py"], str(tmp_path))
        assert found == ["tests/test_x.py::test_runs_only"]


class TestThisRepository:
    def test_every_measured_module_is_placed_and_no_exception_is_stale(self):
        """The guarantee the scope file gives: a new module can never drop out of the report
        unseen, and the exceptions cannot rot."""
        placed = C.classify_all(C.measured_files(), C.load_scope())
        assert len(placed["files"]) >= 250, "the population: modules, routes and app.py"
        assert placed["unclassified"] == [] and placed["stale"] == []

    def test_no_test_asserts_nothing_beyond_the_baseline(self):
        """The gate's half of the assertion rule (the ratchet runs it again on the coverage
        run): a new test that only shows nothing raised fails here, by name."""
        baseline = {}
        if os.path.exists(C.BASELINE):
            with open(C.BASELINE, encoding="utf-8") as fh:
                baseline = json.load(fh)
        new = sorted(set(C.assertion_free(C.scope_tests())) -
                     set(baseline.get("assertion_free", [])))
        assert new == []
