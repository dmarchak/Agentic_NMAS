"""The nightly mutation run (scripts/nmas_mutation.py, CLI scripts/nmas-mutation, workflow
.github/workflows/mutation-nightly.yml; docs/TESTING.md, "Mutation testing"), tested without
mutmut: what a night plans from a real git history and the record, how it reads mutmut's real
output (captured 2026-10-14 in tests/fixtures/mutation/), when the measurement is broken, when
the night fails, and what it leaves for the next night. mutmut itself is dev-only and never
installed here; the workflow is checked as a file."""
import fnmatch
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "mutation")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load("nmas_mutation_under_test", "scripts/nmas_mutation.py")
EQ = _load("mutation_equivalent_under_test", "tests/mutation_equivalent.py")


def _fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


PROBE = ("modules/readers/reachability.py", "probe")
TCP = ("modules/integrations/monitoring_profile.py", "tcp_accepts")
CANARY_KILLED = {f"tests.mutation_canary.x_in_process__mutmut_{n}": "killed" for n in (1, 2)}
CANARY_KILLED.update({f"tests.mutation_canary.x_in_child__mutmut_{n}": "killed" for n in (1, 2)})


# ── What a night plans ────────────────────────────────────────────────────────────────────────

class TestWhatChanged:
    def test_the_lines_a_real_diff_changes(self):
        """`git diff -U0` of the two Lab 7 seam commits (f40c9da6~1..1dc672ea): each hunk's
        new lines, a pure addition (`+85`, no count) as its one line."""
        assert M.changed_lines(_fixture("seams.diff")) == {
            "modules/integrations/monitoring_profile.py": {51, 52, 53, 54, 55, 56, 59},
            "modules/readers/reachability.py": {71, 72, 73, 74, 75, 77, 78, 85, 87},
        }

    def test_a_pure_deletion_still_marks_its_function(self):
        diff = ("+++ b/modules/x.py\n"
                "@@ -5,2 +4,0 @@ def f():\n")
        assert M.changed_lines(diff) == {"modules/x.py": {4}}


V1 = '''\
def changed(x):
    def helper(y):
        return y + 1
    return helper(x)


def untouched(x):
    return x


class Box:
    @property
    def size(self):
        return 1

    def fill(self, n):
        return n * 2
'''

V2 = V1.replace("return y + 1", "return y + 2").replace("return 1\n", "return 3\n") \
    .replace("return n * 2", "return n * 4")


@pytest.fixture
def history(tmp_path):
    """A real git repository: this checkout's scope, an automation module whose nested helper,
    a property and a method change, a support route that changes, and a module deleted."""
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    os.makedirs(tmp_path / "tests")
    shutil.copy(os.path.join(ROOT, "tests", "coverage_scope.py"), tmp_path / "tests")
    for rel, text in (("modules/net.py", V1), ("modules/gone.py", "def x():\n    return 1\n"),
                      ("routes/page.py", "def view():\n    return 1\n")):
        os.makedirs(os.path.dirname(tmp_path / rel), exist_ok=True)
        (tmp_path / rel).write_text(text)
    git("init", "-q", "-b", "main")
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "one")
    (tmp_path / "modules/net.py").write_text(V2)
    (tmp_path / "routes/page.py").write_text("def view():\n    return 2\n")
    os.remove(tmp_path / "modules/gone.py")
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "two")
    head = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    return str(tmp_path), head


def _record(results, text=V2, qualname="untouched", open_=()):
    return {"hash": M.function_hash(text, qualname), "results": results, "open": list(open_)}


class TestThePlan:
    def test_the_first_night_mutates_the_counted_automation_functions_head_changed(self, history):
        """Against head's parent: the function holding the changed nested helper, and the
        method; never the property (not counted), the untouched function, the support route,
        or the deleted module; each whole."""
        root, head = history
        p = M.plan({}, head, root=root)
        assert p["planned"] == [("modules/net.py", "changed"), ("modules/net.py", "Box.fill")]
        assert p["base"] == M.git("rev-parse", f"{head}~1", root=root).strip()
        assert M.patterns(p) == ["modules.net.x_changed__mutmut_*",
                                 "modules.net.xǁBoxǁfill__mutmut_*"]

    def test_a_kept_function_runs_only_what_is_left_and_its_open_survivors(self, history):
        """C769: the record's results stand while the function's text is unchanged; only its
        mutants not yet checked, and its open survivors, run again, by name."""
        root, head = history
        rec = _record({"modules.net.x_untouched__mutmut_1": "killed",
                       "modules.net.x_untouched__mutmut_2": "survived",
                       "modules.net.x_untouched__mutmut_3": "not checked"},
                      open_=["modules.net.x_untouched__mutmut_2"])
        p = M.plan({"commit": head, "functions": {"modules/net.py::untouched": rec}}, head,
                   root=root)
        assert p["planned"] == [("modules/net.py", "untouched")] and p["dropped"] == []
        assert M.patterns(p) == ["modules.net.x_untouched__mutmut_2",
                                 "modules.net.x_untouched__mutmut_3"]

    def test_a_kept_function_whose_text_changed_starts_afresh(self, history):
        root, head = history
        base = M.git("rev-parse", f"{head}~1", root=root).strip()
        rec = _record({"modules.net.x_changed__mutmut_1": "not checked"}, text=V1,
                      qualname="changed")
        p = M.plan({"commit": base, "functions": {"modules/net.py::changed": rec,
                                                  "modules/gone.py::x": rec}}, head, root=root)
        assert p["dropped"] == ["modules/net.py::changed"]
        assert p["gone"] == ["modules/gone.py::x"], "deleted, not changed: said apart (D15)"
        assert ("modules/net.py", "changed") in p["planned"] and p["kept"] == {}
        assert "modules.net.x_changed__mutmut_*" in M.patterns(p)

    def test_known_debt_at_its_listed_text_is_not_run_again(self, history):
        """The operator, 2026-10-14: an open survivor on the debt list, its function's text the
        one it was listed at, is NOT run again; only unchecked mutants are, and a function with
        none is not planned at all. The control: the same record, the debt listed at another
        text, runs the open survivor again."""
        root, head = history
        m = "modules.net.x_untouched__mutmut_"
        h = M.function_hash(V2, "untouched")
        rec = _record({m + "1": "killed", m + "2": "survived", m + "3": "not checked"},
                      open_=[m + "2"])
        debt = {"functions": {"modules.net.untouched": {
            "path": "modules/net.py", "qualname": "untouched", "hash": h,
            "survivors": [{"was": "a", "now": "b", "reason": "r"}]}}}
        state = {"commit": head, "functions": {"modules/net.py::untouched": rec}}
        p = M.plan(state, head, root=root, debt=debt)
        assert M.patterns(p) == [m + "3"], "only the unchecked mutant runs"
        done = dict(rec, results={m + "1": "killed", m + "2": "survived"})
        q = M.plan({"commit": head, "functions": {"modules/net.py::untouched": done}}, head,
                   root=root, debt=debt)
        assert q["planned"] == [] and q["debt_not_rerun"] == ["modules/net.py::untouched"]
        assert "Known debt not run again (1 function(s))" in "\n".join(M.not_rerun_lines(q))
        moved_on = {"functions": {"modules.net.untouched": dict(
            debt["functions"]["modules.net.untouched"], hash="the text it was listed at")}}
        r = M.plan({"commit": head, "functions": {"modules/net.py::untouched": done}}, head,
                   root=root, debt=moved_on)
        assert M.patterns(r) == [m + "2"], "listed at another text: run again"

    def test_a_function_a_person_names_is_mutated_whole(self, history):
        root, head = history
        p = M.plan({"commit": head}, head, root=root, also=["modules/net.py::untouched"])
        assert M.patterns(p) == ["modules.net.x_untouched__mutmut_*"]
        with pytest.raises(ValueError, match="no counted function"):
            M.plan({"commit": head}, head, root=root, also=["modules/net.py::size"])

    def test_a_first_night_begins_where_the_nightly_was_added(self, history):
        """No record yet: everything since the commit that added the nightly workflow (so the
        first night is not an empty one), else head's parent."""
        root, head = history
        wf = os.path.join(root, ".github", "workflows")
        os.makedirs(wf)
        with open(os.path.join(wf, "mutation-nightly.yml"), "w", encoding="utf-8") as fh:
            fh.write("name: mutation-nightly\n")
        for args in (("add", "-A"), ("commit", "-qm", "the nightly")):
            subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c",
                            "user.email=t@example.invalid", *args], check=True,
                           capture_output=True)
        added = M.git("rev-parse", "HEAD", root=root).strip()
        assert M.first_base(added, root) == head, "head itself added it: its parent"
        for rel, text in (("modules/net.py", "\n\ndef later(x):\n    return x\n"),
                          ("routes/page.py", "\n# a route's comment, the night after\n")):
            with open(os.path.join(root, rel), "a", encoding="utf-8") as fh:
                fh.write(text)
            for args in (("add", "-A"), ("commit", "-qm", rel)):
                subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c",
                                "user.email=t@example.invalid", *args], check=True,
                               capture_output=True)
        p = M.plan({}, "HEAD", root=root)
        assert p["base"] == added, "not head's parent: two commits came after the nightly"
        assert p["planned"] == [("modules/net.py", "later")]

    def test_the_record_names_a_commit_never_a_moving_name(self, history):
        root, head = history
        assert M.plan({"commit": head}, "HEAD", root=root)["head"] == head
        assert M.plan({}, "main", root=root)["head"] == head

    def test_nothing_changed_and_nothing_kept_is_nothing_to_mutate(self, history):
        root, head = history
        p = M.plan({"commit": head}, head, root=root)
        assert p["planned"] == []
        assert "Nothing to mutate" in M.summary(p["base"], head, [], {}, [], 120)


class TestTheFunctionHash:
    def test_it_follows_the_functions_own_text(self):
        assert M.function_hash(V1, "untouched") == M.function_hash(V2, "untouched")
        assert M.function_hash(V1, "changed") != M.function_hash(V2, "changed")
        assert M.function_hash(V1, "Box.fill") != M.function_hash(V2, "Box.fill")
        assert M.function_hash(V1, "Box.size") == "", "a property is not counted"
        assert M.function_hash(None, "changed") == ""


class TestTheTestsANightRuns:
    @pytest.mark.parametrize("source, picked", [
        ("from modules.readers import reachability as RE\n", True),
        ("import modules.readers.reachability\n", True),
        ("from modules.readers.reachability import probe\n", True),
        ("from modules.readers import job_health, reachability\n", True),
        ("def test_x():\n    from modules.readers import reachability\n", True),
        ("from modules.readers import reachability_other\n", False),
        ("from modules import readers\n", False),
        ('CASES = ["from modules.readers import reachability as RE\\n"]\n', False),
    ])
    def test_a_test_file_is_run_when_its_code_imports_the_module(self, source, picked):
        """Parsed, never searched: an import written inside a test's string data selected
        test_nmas_mutation.py itself (2026-10-14)."""
        got = M.tests_for(["modules/readers/reachability.py"], {"tests/test_x.py": source})
        assert got == (["tests/test_x.py"] if picked else [])


class TestMutmutsNames:
    """mutmut 3's names, from its real `results` output: a function's mutants are
    `module.x_<name>__mutmut_<n>`, a method's `module.xǁ<Class>ǁ<name>__mutmut_<n>`."""

    def names(self):
        return list(M.parse_results(_fixture("results-2026-10-14.txt")))

    @pytest.mark.parametrize("planned, count", [
        (PROBE, 35), (TCP, 21),
        (("modules/integrations/monitoring_profile.py", "MonitoringProfileIntegration.checks"), 3),
        (("modules/readers/reachability.py", "miss_threshold"), 3),
    ])
    def test_a_pattern_selects_exactly_its_functions_mutants(self, planned, count):
        pattern = M.mutant_pattern(*planned)
        hits = [n for n in self.names() if fnmatch.fnmatchcase(n, pattern)]
        assert len(hits) == count
        assert {M.function_of(n) for n in hits} == {M.dotted(planned)}
        assert {n.rsplit("__mutmut_", 1)[0] for n in hits} == {M.mangled(*planned)}


# ── The tests a child reaches ─────────────────────────────────────────────────────────────────

class TestATestsChild:
    def test_the_tests_that_start_a_child_join_each_planned_functions_tests(self):
        """A child records nothing in mutmut's statistics, so a test reaching a function only
        through one would never be chosen: every test that started one (its tier) is added."""
        tiers = {"tests/test_a.py::test_unit": "unit", "tests/test_a.py::test_spawn": "spawns",
                 "tests/test_b.py::test_page": "browser"}
        spawning = M.spawning_tests(tiers)
        assert spawning == ["tests/test_a.py::test_spawn", "tests/test_b.py::test_page"]
        stats = {"tests_by_mangled_function_name": {"m.x_f": ["tests/test_a.py::test_unit",
                                                             "tests/test_a.py::test_spawn"]}}
        assert M.add_tests(stats, ["m.x_f", "m.x_g"], spawning) == 3
        assert stats["tests_by_mangled_function_name"] == {
            "m.x_f": ["tests/test_a.py::test_spawn", "tests/test_a.py::test_unit",
                      "tests/test_b.py::test_page"],
            "m.x_g": ["tests/test_a.py::test_spawn", "tests/test_b.py::test_page"]}

    def test_only_the_statistics_run_turns_a_childs_recording_off(self):
        """Recording needs mutmut's configuration, which only the run's folder holds
        (FileNotFoundError, measured 2026-10-14): under the statistics run a child records
        nothing; under a mutant's run, and outside mutmut, its environment is left alone, so
        it runs the mutant."""
        from tests.network_guard import spawn_guard
        guard = spawn_guard()
        assert guard.child_env({"MUTANT_UNDER_TEST": "stats"})["MUTMUT_DEPENDENCY_DEPTH"] == "0"
        mutant = "modules.readers.reachability.x_probe__mutmut_31"
        assert "MUTMUT_DEPENDENCY_DEPTH" not in guard.child_env({"MUTANT_UNDER_TEST": mutant})
        assert "MUTMUT_DEPENDENCY_DEPTH" not in guard.child_env({})


# ── What a night reports ──────────────────────────────────────────────────────────────────────

class TestTheVerdict:
    def results(self):
        return M.parse_results(_fixture("results-2026-10-14.txt"))

    def test_mutmuts_results_read_in_full(self):
        statuses = list(self.results().values())
        assert len(statuses) == 62
        assert {s: statuses.count(s) for s in set(statuses)} == {
            "killed": 48, "survived": 8, "not checked": 6}

    def test_only_the_planned_functions_are_reported(self):
        """mutmut lists every mutant of a mutated FILE; the unplanned functions' are dropped."""
        got = M.only_functions(self.results(), [PROBE, TCP])
        assert len(got) == 56 and "not checked" not in got.values()

    def test_a_survivors_lines_come_from_its_real_diff(self):
        assert M.diff_lines(_fixture("show-probe-31.txt")) == (
            "with connect((ip, 22), timeout=2):", "with connect((ip, 22), ):")

    def test_a_listed_equivalent_is_known_and_any_other_survivor_is_open(self):
        """Mutant 12 is in tests/mutation_equivalent.py (matched by function and lines, never
        number); mutant 31 is not, and is the night's failure (VERDICT: no kind given); a
        mutant no test reached survives just the same, and says so; a MESSAGE survivor is
        listed apart and never fails the night."""
        results = {"modules.readers.reachability.x_probe__mutmut_12": "survived",
                   "modules.readers.reachability.x_probe__mutmut_31": "survived",
                   "modules.readers.reachability.x_probe__mutmut_40": "no tests",
                   "modules.readers.reachability.x_probe__mutmut_50": "survived",
                   "modules.readers.reachability.x_probe__mutmut_1": "killed"}
        shows = {"modules.readers.reachability.x_probe__mutmut_12": _fixture("show-probe-12.txt"),
                 "modules.readers.reachability.x_probe__mutmut_31": _fixture("show-probe-31.txt")}
        kinds = {"modules.readers.reachability.x_probe__mutmut_50": "message"}
        v = M.verdict(results, shows, EQ.EQUIVALENT, kinds)
        assert [s["mutant"].rsplit("_", 1)[1] for s in v["new"]] == ["31", "40"]
        assert [s["mutant"].rsplit("_", 1)[1] for s in v["message"]] == ["50"]
        assert [s["mutant"] for s in v["known"]] == ["modules.readers.reachability.x_probe__mutmut_12"]
        assert v["functions"]["modules.readers.reachability.probe"] == {
            "mutants": 5, "killed": 1, "survived": 4, "equivalent": 1, "verdict": 2,
            "message": 1, "other": 0, "debt": 0}
        text = M.summary("a" * 40, "b" * 40, [PROBE], v, [], 120)
        assert "| `modules.readers.reachability.probe` | 5 | 1 | 2 | 0 | 1 | 1 | 25.0% | 33.3% |" \
            in text
        assert "### New open VERDICT survivors (2)" in text and "with connect((ip, 22), ):" in text
        assert "### Open MESSAGE survivors (1): words only" in text
        assert "x_probe__mutmut_40` (no test reached it)" in text

    def test_the_same_lines_under_another_function_are_not_its_equivalent(self):
        results = {"modules.readers.other.x_probe__mutmut_12": "survived"}
        v = M.verdict(results, {"modules.readers.other.x_probe__mutmut_12":
                                _fixture("show-probe-12.txt")}, EQ.EQUIVALENT)
        assert len(v["new"]) == 1 and not v["known"]


class TestWhatAMutantChanges:
    """The operator's rule (2026-10-14): a logging call's arguments are never mutated; a
    survivor is MESSAGE when it changes only the words a person reads, VERDICT otherwise, and
    whatever the rule cannot decide is VERDICT. On real mutants of config_check._check_device
    (tests/fixtures/mutation/check_device_mutants.txt, cut verbatim from mutmut's copy)."""

    def kinds(self):
        with open(os.path.join(ROOT, "modules", "nsot", "config_check.py"),
                  encoding="utf-8") as fh:
            module = fh.read()
        return M.classify_file(_fixture("check_device_mutants.txt"), module)

    @pytest.mark.parametrize("n, kind, what", [
        (81, "logging", "log.debug's format replaced by None"),
        (18, "message", "the bootstrap note's sentence wrapped in XX"),
        (19, "message", "the bootstrap note's sentence upper-cased"),
        (16, "verdict", '"note", a level, wrapped in XX'),
        (11, "verdict", "the note's message argument dropped"),
        (374, "verdict", '"no golden: ..." wrapped: the module compares with "no golden"'),
    ])
    def test_a_real_mutant_is_classified_by_its_effect(self, n, kind, what):
        assert self.kinds()[f"x__check_device__mutmut_{n}"] == kind, what

    def test_a_logging_calls_continuation_line_is_logging(self):
        orig = 'def f(x):\n    log.warning("a %s"\n                "b", x)\n    return x\n'
        mutant = 'def g(x):\n    log.warning("a %s"\n                "b", None)\n    return x\n'
        assert M.classify(orig, mutant) == "logging"
        assert M.classify(orig, orig.replace("return x", "return None")) == "verdict"

    def test_a_word_compared_elsewhere_keeps_a_sentence_verdict_and_punctuation_does_not(self):
        orig = 'def f():\n    return add("no golden: nothing to compare")\n'
        mutant = 'def g():\n    return add("XXno golden: nothing to compareXX")\n'
        assert M.classify(orig, mutant, {":", "/"}) == "message"
        assert M.classify(orig, mutant, {"no golden"}) == "verdict"
        assert M.classify(orig, mutant.replace('"XXno golden: nothing to compareXX"', "None"),
                          set()) == "verdict", "a type change is undecided: VERDICT"

    def test_a_string_with_no_space_is_an_identifier_status_or_key_so_verdict(self):
        """Even when nothing in the module compares with it: `"render"`, a check's name."""
        orig = 'def f():\n    return add("render", "a sentence of words")\n'
        assert M.classify(orig, orig.replace('"render"', '"XXrenderXX"'), set()) == "verdict"
        assert M.classify(orig, orig.replace('"a sentence of words"',
                                             '"A SENTENCE OF WORDS"'), set()) == "message"


class TestTheMeasurementIsChecked:
    """The canary (tests/mutation_canary.py) must be killed whole, and only planned functions
    may run: otherwise no result stands, the night fails, and the record is left as it was."""

    def test_a_canary_all_killed_is_a_working_measurement(self):
        assert M.canary_error(CANARY_KILLED) == ""

    @pytest.mark.parametrize("mutant, status", [
        ("tests.mutation_canary.x_in_child__mutmut_2", "survived"),
        ("tests.mutation_canary.x_in_child__mutmut_2", "no tests"),
        ("tests.mutation_canary.x_in_process__mutmut_1", "not checked"),
    ])
    def test_a_canary_mutant_alive_is_a_broken_measurement(self, mutant, status):
        err = M.canary_error({**CANARY_KILLED, mutant: status})
        assert err.startswith("MEASUREMENT BROKEN") and f"{mutant} was {status}" in err

    def test_a_canary_function_with_no_mutant_is_a_broken_measurement(self):
        only_in_process = {m: s for m, s in CANARY_KILLED.items() if "in_process" in m}
        assert "in_child (no mutant made) was missing" in M.canary_error(only_in_process)
        assert "made no mutant" in M.canary_error({})

    def test_a_mutant_of_an_unplanned_function_that_ran_breaks_the_scope(self):
        results = {"modules.readers.reachability.x_probe__mutmut_1": "killed",
                   "modules.readers.reachability.x_miss_threshold__mutmut_1": "not checked"}
        assert M.scope_error(results, [PROBE]) == ""
        ran = {**results, "modules.readers.reachability.x_miss_threshold__mutmut_2": "killed"}
        assert M.scope_error(ran, [PROBE]).startswith("SCOPE BROKEN: 1 mutant")


class TestTheNightsOutcome:
    """mutmut exits 0 when it finished (survivors or not) and 1 when its own setup failed (its
    stats run, or the tests failing on the unmutated code: measured 2026-10-14, a loopback that
    was down); `timeout` exits 124 when the budget ran out."""

    def test_a_failed_mutmut_run_fails_the_night(self):
        out = M.outcome([PROBE, TCP], {}, 1)
        assert out["done"] == [] and out["left"] == [PROBE, TCP] and "mutmut exited 1" in out["error"]
        text = M.summary("a" * 40, "b" * 40, [PROBE, TCP], M.verdict({}, {}, []), out["left"],
                         120, out["error"])
        assert text.count("**The run failed:**") == 1 and "record is left as it was" in text

    def test_out_of_time_leaves_what_was_not_reached_or_not_finished(self):
        results = {"modules.readers.reachability.x_probe__mutmut_1": "killed",
                   "modules.readers.reachability.x_probe__mutmut_2": "not checked"}
        unreached = ("modules/readers/reachability.py", "population")
        out = M.outcome([PROBE, TCP, unreached], {**results,
                        "modules.integrations.monitoring_profile.x_tcp_accepts__mutmut_1":
                        "killed"}, 124)
        assert out["done"] == [TCP] and out["left"] == [PROBE, unreached] and not out["error"]
        text = M.summary("a" * 40, "b" * 40, [PROBE, TCP, unreached],
                         M.verdict(results, {}, []), out["left"], 120)
        assert "### Left over (2): the 120-minute budget ran out; their results so far are kept" \
            in text

    def test_a_finished_night_names_a_function_mutmut_made_nothing_of(self):
        """Done, but nothing in it was tested: said, never left to read as passed."""
        out = M.outcome([PROBE, TCP], {"modules.readers.reachability.x_probe__mutmut_1":
                                       "killed"}, 0)
        assert out["done"] == [PROBE, TCP] and out["empty"] == [TCP] and out["left"] == []
        text = M.summary("a" * 40, "b" * 40, [PROBE, TCP],
                         M.verdict({"modules.readers.reachability.x_probe__mutmut_1": "killed"},
                                   {}, []), [], 120, "", out["empty"])
        assert "made no mutant of it (1)" in text and "tcp_accepts" in text.split("made no")[1]


class TestTheRecord:
    """C769: what a night keeps for the next, so a large function is finished across nights and
    an open survivor is run again each night until it is killed or listed as equivalent."""

    def test_tonights_results_replace_what_was_kept_where_they_ran(self):
        kept = {"m.x_f__mutmut_1": "killed", "m.x_f__mutmut_2": "not checked",
                "m.x_f__mutmut_3": "survived"}
        tonight = {"m.x_f__mutmut_1": "not checked", "m.x_f__mutmut_2": "killed",
                   "m.x_f__mutmut_3": "killed"}
        assert M.merge(kept, tonight) == {"m.x_f__mutmut_1": "killed",
                                          "m.x_f__mutmut_2": "killed",
                                          "m.x_f__mutmut_3": "killed"}

    def test_it_keeps_the_unfinished_and_the_open_and_drops_the_rest(self):
        results = {"modules.readers.reachability.x_probe__mutmut_1": "killed",
                   "modules.readers.reachability.x_probe__mutmut_2": "not checked",
                   "modules.integrations.monitoring_profile.x_tcp_accepts__mutmut_1": "survived",
                   "modules.readers.reachability.x_population__mutmut_1": "killed"}
        population = ("modules/readers/reachability.py", "population")
        hashes = {M.key(PROBE): "h1", M.key(TCP): "h2", M.key(population): "h3"}
        state = M.next_state("c" * 40, [PROBE, TCP, population], results,
                             ["modules.integrations.monitoring_profile.x_tcp_accepts__mutmut_1"],
                             hashes)
        assert state["commit"] == "c" * 40
        assert set(state["functions"]) == {M.key(PROBE), M.key(TCP)}
        assert state["functions"][M.key(PROBE)] == {
            "hash": "h1", "open": [],
            "results": {"modules.readers.reachability.x_probe__mutmut_1": "killed",
                        "modules.readers.reachability.x_probe__mutmut_2": "not checked"}}
        assert state["functions"][M.key(TCP)]["open"] == [
            "modules.integrations.monitoring_profile.x_tcp_accepts__mutmut_1"]


class TestEveryNightStartsEmpty:
    def test_an_earlier_runs_copy_is_removed_before_the_night(self, tmp_path):
        """Its results would read as tonight's: a scope broken by a function that did not run,
        a canary passed on old kills (two nights walked in one copy, 2026-10-14)."""
        old = tmp_path / "mutants" / "modules"
        old.mkdir(parents=True)
        (old / "x.py.meta").write_text('{"exit_code_by_key": {"m.x_f__mutmut_1": 1}}')
        assert M.fresh_workspace(str(tmp_path)) is True
        assert not (tmp_path / "mutants").exists()
        assert M.fresh_workspace(str(tmp_path)) is False, "nothing to remove"
        cli = open(os.path.join(ROOT, "scripts", "nmas-mutation"), encoding="utf-8").read()
        run = cli[cli.index("def cmd_run"):cli.index("def cmd_report")]
        first_mutmut = run.index("_mutmut_run(")
        assert -1 < run.index("M.fresh_workspace()") < first_mutmut, "before mutmut runs"


class TestTheEquivalentList:
    def test_every_entry_names_a_function_both_lines_and_a_reason(self):
        assert len(EQ.EQUIVALENT) >= 20, "the population: the first pass's and the first night's"
        for e in EQ.EQUIVALENT:
            assert set(e) == {"function", "was", "now", "why"}, e
            assert e["function"].startswith("modules.") and e["was"] and e["why"], e
            assert e["was"] != e["now"], e

    def test_no_mutant_is_listed_twice(self):
        keys = [(e["function"], e["was"], e["now"]) for e in EQ.EQUIVALENT]
        assert len(keys) == len(set(keys))


class TestTheCanary:
    def test_it_is_planned_beside_the_night_and_its_tests_selected(self):
        """Every night mutates the canary's file beside the planned ones, and runs its tests."""
        assert M.CANARY_IN_PROCESS[0] == M.CANARY_IN_CHILD[0] == "tests/mutation_canary.py"
        assert os.path.exists(os.path.join(ROOT, M.CANARY_TESTS))
        cli = open(os.path.join(ROOT, "scripts", "nmas-mutation"), encoding="utf-8").read()
        assert "files + [M.CANARY_FILE]" in cli and "tests + [M.CANARY_TESTS]" in cli


# ── The workflow and its place: nightly, dev-only ────────────────────────────────────────────

WORKFLOW = os.path.join(ROOT, ".github", "workflows", "mutation-nightly.yml")


class TestTheWorkflow:
    def doc(self):
        with open(WORKFLOW, encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def text(self):
        with open(WORKFLOW, encoding="utf-8") as fh:
            return fh.read()

    def test_it_runs_nightly_and_by_hand_never_on_a_push(self):
        on = self.doc()[True]                    # YAML reads the bare key `on` as True
        assert set(on) == {"schedule", "workflow_dispatch"}
        assert on["schedule"] == [{"cron": "17 8 * * *"}]
        cron_at = self.text().index('cron: "17 8 * * *"')
        assert "America/Denver" in self.text()[cron_at - 160:cron_at]

    def test_a_dispatchs_functions_reach_the_plan_through_the_environment(self):
        """Never `${{ inputs... }}` pasted into a script (an input is text a person typed)."""
        doc = self.doc()
        assert set(doc[True]["workflow_dispatch"]["inputs"]) == {"functions"}
        plan = next(s for s in doc["jobs"]["mutate"]["steps"] if s.get("id") == "plan")
        assert plan["env"] == {"ALSO_FUNCTIONS": "${{ inputs.functions }}"}
        assert "${{" not in plan["run"] and '--also "$f"' in plan["run"]

    def test_its_one_setting_is_the_budget_and_it_bounds_the_run(self):
        doc = self.doc()
        assert doc["env"] == {"MUTATION_BUDGET_MINUTES": "120"}
        run = next(s["run"] for s in doc["jobs"]["mutate"]["steps"] if s.get("id") == "mutate")
        assert 'timeout "${MUTATION_BUDGET_MINUTES}m" unshare -rn' in run
        assert "ip link set lo up" in run and "scripts/nmas-mutation run --out mutation-out" in run
        # Confined as the suite is (C46): a loopback-only namespace the tests require.
        assert "NMAS_REQUIRE_NETWORK_CONFINEMENT=1" in run
        # Bytecode written: a child recompiling the mutated module cost 7.7 s per spawn.
        assert "PYTHONDONTWRITEBYTECODE" not in run

    def test_mutmut_runs_one_mutant_at_a_time(self):
        cli = open(os.path.join(ROOT, "scripts", "nmas-mutation"), encoding="utf-8").read()
        assert '"run", "--max-children", "1"' in cli

    def test_the_record_is_kept_after_every_night_whose_results_stand(self):
        steps = self.doc()["jobs"]["mutate"]["steps"]
        save = [s for s in steps if str(s.get("uses", "")).startswith("actions/cache/save")]
        assert len(save) == 1
        assert save[0]["if"] == "always() && hashFiles('.mutation-state/state.json') != ''"
        report = next(s for s in steps if s.get("name") == "The report")
        assert '--mutmut-exit "$MUTMUT_EXIT"' in report["run"]
        assert report["env"] == {"MUTMUT_EXIT": "${{ steps.mutate.outputs.exit }}"}

    def test_each_summary_reaches_the_jobs_log_and_the_runs_page_and_the_report_decides(self):
        """The API returns no job summary, so the night's summary is printed in the log too;
        the report step's result is the report's own exit, never the printing's."""
        steps = {s.get("name"): s for s in self.doc()["jobs"]["mutate"]["steps"]}
        plan, report = steps["Plan the night"]["run"], steps["The report"]["run"]
        assert "--summary mutation-out/summary.md" in plan
        assert "--summary mutation-out/summary.md" in report
        for run in (plan, report):
            assert "cat mutation-out/summary.md\n" in run
            assert 'cat mutation-out/summary.md >> "$GITHUB_STEP_SUMMARY"' in run
        assert report.rstrip().endswith("exit $code") and "code=$?" in report

    def test_mutmut_is_never_the_hosts_the_gates_or_a_pushs(self):
        for rel in ("requirements.txt", "requirements.lock", "requirements-ci.txt",
                    "requirements-test.txt", ".github/workflows/ci.yml", "scripts/hooks/pre-commit",
                    "scripts/nmas-gate"):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                assert "mutmut" not in fh.read().lower(), rel

    def test_its_requirements_are_pinned_exactly(self):
        with open(os.path.join(ROOT, "requirements-mutation.txt"), encoding="utf-8") as fh:
            pins = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
        assert "mutmut==3.8.0" in pins
        assert all("==" in p and p.count("==") == 1 for p in pins), pins


# ── The first GitHub night (2026-10-14): what it lacked, and what its summary did not say ────

CI_WORKFLOW = os.path.join(ROOT, ".github", "workflows", "ci.yml")

#: ci.yml's test-job setup the night does not repeat, each with why (anything else must have a
#: twin in the night, its `run` word for word).
NOT_FOR_THE_NIGHT = {
    "A folder for each test's tier": "the coverage measurement's; nmas-mutation run makes its own",
}
#: The variables ci.yml's tests step sets that the night does not, each with why.
NOT_THE_NIGHTS_ENV = {
    "COVERAGE_CORE": "coverage's tracer; the night measures no coverage",
    "COVERAGE_FILE": "coverage's data file",
    "NMAS_TEST_TIERS": "set by nmas-mutation run itself, for its first mutmut run",
    "NMAS_COVERAGE_TIERS": "a push's coverage measured by tier (C773); the night measures none",
    "NMAS_TEST_TIMEOUT": "nmas-test's bound; the night is bounded by its budget",
}


def setup_gaps(ci: dict, night: dict) -> list:
    """What ci.yml's tests stand on that the night lacks: each setup step of the test job (every
    step before its tests step) with no twin in the night's job (the same `run`, the same
    action), the install's commands not all in the night's install, a different interpreter,
    and each variable of the tests step not on the mutate step."""
    steps = ci["jobs"]["test"]["steps"]
    tests_at = next(i for i, s in enumerate(steps) if str(s.get("name", "")).startswith("Tests"))
    mine = night["jobs"]["mutate"]["steps"]
    runs = {s["run"] for s in mine if "run" in s}
    uses = {s["uses"] for s in mine if "uses" in s}
    install = "\n".join(s["run"] for s in mine if str(s.get("name", "")).startswith("Install"))
    gaps = []
    for s in steps[:tests_at]:
        name = s.get("name") or s.get("uses")
        if name in NOT_FOR_THE_NIGHT:
            continue
        if "uses" in s:
            if s["uses"] not in uses:
                gaps.append(f"{name}: no step uses {s['uses']}")
            want = (s.get("with") or {}).get("python-version")
            have = [(t.get("with") or {}).get("python-version") for t in mine
                    if t.get("uses") == s["uses"]]
            if want and want not in have:
                gaps.append(f"{name}: python-version {want}, the night's {have}")
        elif str(name).startswith("Install"):
            lost = [ln for ln in s["run"].splitlines() if ln.strip() and ln.strip() not in install]
            if lost:
                gaps.append(f"{name}: the night does not run {lost}")
        elif s["run"] not in runs:
            gaps.append(f"{name}: no step of the night runs it")
    mutate_env = next(s for s in mine if s.get("id") == "mutate").get("env") or {}
    for k, v in (steps[tests_at].get("env") or {}).items():
        if k not in NOT_THE_NIGHTS_ENV and str(mutate_env.get(k)) != str(v):
            gaps.append(f"{k}={v} on ci.yml's tests step; the mutate step has {mutate_env.get(k)}")
    return gaps


class TestTheNightStandsOnCIsSetup:
    """The first GitHub night ran its tests without PostgreSQL, promtool or NMAS_REQUIRE_PG,
    which ci.yml's tests stand on: a test skipped for want of one kills no mutant (the operator,
    2026-10-14: the two workflows had drifted). Now each setup step of ci.yml's test job needs a
    twin in the night."""

    def docs(self):
        with open(CI_WORKFLOW, encoding="utf-8") as a, open(WORKFLOW, encoding="utf-8") as b:
            return yaml.safe_load(a), yaml.safe_load(b)

    def test_every_setup_step_cis_tests_stand_on_is_the_nights_too(self):
        ci, night = self.docs()
        steps = ci["jobs"]["test"]["steps"]
        assert len([s for s in steps if "run" in s]) >= 8                      # the floor
        assert setup_gaps(ci, night) == []

    def test_each_exception_names_a_step_or_variable_ci_has(self):
        ci, _night = self.docs()
        steps = ci["jobs"]["test"]["steps"]
        assert set(NOT_FOR_THE_NIGHT) <= {s.get("name") for s in steps}
        env = next(s for s in steps if str(s.get("name", "")).startswith("Tests"))["env"]
        assert set(NOT_THE_NIGHTS_ENV) <= set(env)

    def test_a_planted_setup_step_and_variable_are_found(self):
        """Controls: a step ci.yml gains, the night's PostgreSQL step lost, and the variable the
        tests require taken off the mutate step: each named."""
        ci, night = self.docs()
        tests_at = next(i for i, s in enumerate(ci["jobs"]["test"]["steps"])
                        if str(s.get("name", "")).startswith("Tests"))
        ci["jobs"]["test"]["steps"].insert(tests_at, {"name": "A new tool", "run": "install x"})
        night["jobs"]["mutate"]["steps"] = [s for s in night["jobs"]["mutate"]["steps"]
                                            if not str(s.get("name", "")).startswith("PostgreSQL")]
        next(s for s in night["jobs"]["mutate"]["steps"] if s.get("id") == "mutate")["env"] = {}
        gaps = setup_gaps(ci, night)
        assert any(g.startswith("A new tool:") for g in gaps), gaps
        assert any(g.startswith("PostgreSQL 18") for g in gaps), gaps
        assert any(g.startswith("NMAS_REQUIRE_PG=1") for g in gaps), gaps


class TestAFailedRunSaysWhy:
    """The first GitHub night's summary said only "the log above it says why" (the operator,
    2026-10-14). Its real output (tests/fixtures/mutation/night-2026-10-14-clean-run-failed.txt,
    the runner's timestamps stripped) holds the cause, and the summary now quotes it."""

    def test_the_excerpt_is_the_failing_test_and_mutmuts_refusal(self):
        got = M.failure_excerpt(_fixture("night-2026-10-14-clean-run-failed.txt"))
        assert ("FAILED tests/test_config_read.py::TestTheJudgement::"
                "test_every_real_config_is_one_configuration - assert 0 >= 9") in got
        assert "failed to collect stats. runner returned 1" in got
        assert "1 failed, 92 passed in 742.06s (0:12:22)" in got
        assert not any(l.startswith(".....") or "Running stats" in l for l in got), got
        assert len(got) <= 30

    def test_the_summary_quotes_it_and_never_points_elsewhere(self):
        cause = M.failure_excerpt(_fixture("night-2026-10-14-clean-run-failed.txt"))
        out = M.outcome([PROBE], {}, 1)
        text = M.summary("a" * 40, "b" * 40, [PROBE], M.verdict({}, {}, []), out["left"], 120,
                         out["error"], cause=cause)
        assert "What it said" in text and "```\n" in text
        assert "test_every_real_config_is_one_configuration - assert 0 >= 9" in text
        assert "log above" not in text

    def test_the_run_keeps_mutmuts_output_and_names_the_copys_checkout(self, tmp_path,
                                                                       monkeypatch):
        """Each mutmut run's output is written whole to its log as it comes, and the tests in
        mutmut's copy are told the checkout it copies (NMAS_COPY_OF)."""
        loader = importlib.machinery.SourceFileLoader(
            "nmas_mutation_cli_under_test", os.path.join(ROOT, "scripts", "nmas-mutation"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cli = importlib.util.module_from_spec(spec)
        loader.exec_module(cli)
        seen = {}

        class FakeMutmut:
            def __init__(self, argv, cwd, env, **kw):
                seen.update(argv=argv, env=env)
                self.stdout = iter(["FAILED tests/test_x.py::test_y - assert 0\n",
                                    "failed to collect stats. runner returned 1\n"])

            def wait(self):
                return 1

        monkeypatch.setattr(cli.subprocess, "Popen", FakeMutmut)
        log = tmp_path / "mutmut-run-1.log"
        assert cli._mutmut_run(["x"], str(log), env={"KEEP": "1"}) == 1
        assert seen["env"]["NMAS_COPY_OF"] == cli.M.ROOT and seen["env"]["KEEP"] == "1"
        assert "--max-children" in seen["argv"]
        assert M.failure_excerpt(log.read_text()) == [
            "FAILED tests/test_x.py::test_y - assert 0",
            "failed to collect stats. runner returned 1"]


FENCE_SOURCE = '''import os


@decorated
def planned(x):
    return x + 1


def unplanned(a,
              b: int = 1) -> dict:  # its own comment
    return {"a": a}


async def also_unplanned():
    return 1


def one_line(): return 2


class Holder:
    def kept(self):
        return 1

    def other(self):
        return 2


class Untouched:
    def method(self):
        return 3
'''


class TestTheFence:
    """The second GitHub night (2026-10-14): two changed functions of modules/pipeline.py made
    mutmut mutate all 56 (5,030 mutants, a 50.78 MB copy) and rewrite the unplanned ones a source
    scan reads. Fenced, mutmut 3.8 made 77 mutants of the two planned, 0.24 MB, and wrote every
    other function as it is (measured with mutmut's own mutate_file_contents; mutmut is dev-only,
    so here the fence is checked as text)."""

    def test_only_what_is_not_planned_is_fenced(self):
        out = M.fence(FENCE_SOURCE, {"planned", "Holder.kept"})
        lines = out.splitlines()
        marked = [l for l in lines if l.endswith(M.FENCE)]
        assert len(marked) == 4, marked
        assert any(l.startswith("              b: int = 1) -> dict:") for l in marked), \
            "a signature over two lines: its colon's line"
        assert any(l.startswith("async def also_unplanned():") for l in marked)
        assert any(l.startswith("    def other(self):") for l in marked)
        assert any(l.startswith("class Untouched:") for l in marked)
        assert not any(l.startswith(("def planned", "class Holder", "    def kept",
                                     "def one_line")) and l.endswith(M.FENCE) for l in lines)

    def test_only_comments_are_added(self):
        out = M.fence(FENCE_SOURCE, {"planned"})
        assert len(out.splitlines()) == len(FENCE_SOURCE.splitlines())
        assert [l.replace("  " + M.FENCE, "") for l in out.splitlines()] == \
            FENCE_SOURCE.splitlines()
        import ast
        assert ast.dump(ast.parse(out)) == ast.dump(ast.parse(FENCE_SOURCE))

    def test_mutmuts_own_pragma_reading_takes_it_as_a_block(self):
        """mutmut 3.8 reads `# pragma: … no mutate <token>` from a comment and acts on `block`
        (mutmut/mutation/pragma_handling.py's _parse_pragma_token): the token after "no mutate"
        is "block", here and after a comment of the line's own."""
        line = "def f():  # its own comment  " + M.FENCE
        tail = line.partition("no mutate")[-1].strip()
        assert "# pragma:" in line and tail.lstrip(": ").split(",", 1)[0].split()[0] == "block"

    def test_the_workflow_fences(self):
        wf = open(WORKFLOW, encoding="utf-8").read()
        plan = next(s["run"] for s in yaml.safe_load(wf)["jobs"]["mutate"]["steps"]
                    if s.get("id") == "plan")
        assert " --fence " in plan.replace("\\\n", " ")

    def test_the_cli_fences_in_place_and_refuses_a_module_with_changes_of_its_own(
            self, history, monkeypatch, tmp_path):
        """Through the real CLI over a planted repository: a clean planned module is fenced;
        one with uncommitted changes is refused (exit 2) and left as it was."""
        root, head = history
        loader = importlib.machinery.SourceFileLoader(
            "nmas_mutation_cli_fence", os.path.join(ROOT, "scripts", "nmas-mutation"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cli = importlib.util.module_from_spec(spec)
        loader.exec_module(cli)
        monkeypatch.setattr(cli.M, "ROOT", root)
        monkeypatch.setattr(cli.M, "git", lambda *a, root=root: M.git(*a, root=root))
        monkeypatch.setattr(cli.M, "plan", lambda state, h, also=(), debt=None: M.plan(
            state, h, root=root, also=also, debt=debt))
        os.makedirs(os.path.join(root, "tests"), exist_ok=True)
        args = ["plan", "--head", head, "--out", str(tmp_path / "out"), "--fence"]
        net = os.path.join(root, "modules", "net.py")
        (open(net, "a", encoding="utf-8")).write("# a change of its own\n")
        before = open(net, encoding="utf-8").read()
        assert cli.main(args) == 2
        assert open(net, encoding="utf-8").read() == before, "a refused fence wrote nothing"
        subprocess.run(["git", "-C", root, "checkout", "--", "modules/net.py"], check=True)
        assert cli.main(args) == 0
        text = open(net, encoding="utf-8").read()
        assert "def untouched(x):  " + M.FENCE in text
        assert "def changed(x):\n" in text, "a planned function is left as it is"


class TestTestsThatFailInTheCopy:
    """C778's walk (2026-10-14): with the fence, the night's tests ran in mutmut's copy and 2 of
    2,725 failed there with no mutant active, each a scan of a planned module's definitions
    meeting mutmut's generated copies of its functions. They are measured each night, deselected
    for mutmut and named in the summary (tests/fixtures/mutation/copy-prepass-2026-10-14.txt is
    that run's short summary)."""

    def test_the_failing_ids_are_read_from_a_real_run(self):
        assert M.failing_tests(_fixture("copy-prepass-2026-10-14.txt")) == [
            "tests/test_other_readers_real_output.py::TestOneBgpReader::test_no_third_reader",
            "tests/test_readers_use_what_is_committed.py::TestThePopulation::"
            "test_no_function_resolving_a_golden_opens_a_file"]
        assert M.failing_tests(_fixture("night-2026-10-14-clean-run-failed.txt")) == [
            "tests/test_config_read.py::TestTheJudgement::"
            "test_every_real_config_is_one_configuration"]

    def test_an_id_with_spaces_and_a_reason_and_an_error(self):
        text = ("FAILED tests/test_a.py::test_x[a b] - AssertionError: no\n"
                "ERROR tests/test_b.py::test_y\nFAILED tests/test_a.py::test_x[a b]\n")
        assert M.failing_tests(text) == ["tests/test_a.py::test_x[a b]", "tests/test_b.py::test_y"]

    def test_each_is_deselected_among_mutmuts_pytest_arguments(self):
        cfg = ("[mutmut]\nsource_paths =\n    modules/x.py\npytest_add_cli_args =\n    -p\n"
               "    no:cacheprovider\npytest_add_cli_args_test_selection =\n    tests/test_x.py\n")
        out = M.with_deselected(cfg, ["tests/test_x.py::test_a", "tests/test_x.py::test_b[1 2]"])
        import configparser
        c = configparser.ConfigParser()
        c.read_string(out)
        args = [l for l in c["mutmut"]["pytest_add_cli_args"].splitlines() if l]
        assert args == ["--deselect", "tests/test_x.py::test_a", "--deselect",
                        "tests/test_x.py::test_b[1 2]", "-p", "no:cacheprovider"]
        assert c["mutmut"]["pytest_add_cli_args_test_selection"].split() == ["tests/test_x.py"]

    def test_a_copy_run_past_its_bound_is_said_not_a_crash(self, tmp_path, monkeypatch):
        """C832, night #11: the copy's run passed its bound and the harness died adding a str
        to the partial output, which CPython's TimeoutExpired carries as BYTES even with
        text=True. The bound's firing is written to copy-run.log and nothing is deselected."""
        import subprocess as sp

        cli = _cli()
        root, out = tmp_path / "root", tmp_path / "out"
        (root / "mutants").mkdir(parents=True)
        out.mkdir()
        monkeypatch.setattr(cli.M, "ROOT", str(root))

        def past_the_bound(cmd, **kw):
            raise sp.TimeoutExpired(cmd, kw.get("timeout"), output=b"....F partial \xff run\n")
        monkeypatch.setattr(cli.subprocess, "run", past_the_bound)
        try:
            got = cli._fails_in_the_copy({"tests": ["tests/test_x.py"]}, str(out))
        except TypeError as exc:
            pytest.fail(f"the bound's firing crashed the harness: {exc}")
        assert got == []
        log = (out / "copy-run.log").read_text(encoding="utf-8")
        assert log.startswith("....F partial � run\n")
        assert f"the copy's run passed its {cli.COPY_RUN_TIMEOUT_S} s bound" in log

    def test_the_copy_runs_bound_is_about_two_and_a_half_times_the_runner_s(self):
        """The bound is read against the runner's measured copy runs (299 s and 340 s, nights #9
        and #10), never a laptop's: about 2.5 times the larger."""
        cli = _cli()
        assert 2.2 * 340 <= cli.COPY_RUN_TIMEOUT_S <= 2.8 * 340

    def test_the_run_measures_the_copy_deselects_and_tries_again(self, tmp_path, monkeypatch):
        """Through the real CLI's run step with mutmut stood in: the first mutmut run fails, the
        copy's run names a test, which is deselected and recorded, and mutmut runs again (here
        failing again, so the night stops there with its own cause)."""
        import json
        loader = importlib.machinery.SourceFileLoader(
            "nmas_mutation_cli_copy", os.path.join(ROOT, "scripts", "nmas-mutation"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cli = importlib.util.module_from_spec(spec)
        loader.exec_module(cli)
        root, out = tmp_path / "root", tmp_path / "out"
        root.mkdir()
        out.mkdir()
        (root / "setup.cfg").write_text("[mutmut]\npytest_add_cli_args =\n    -p\n"
                                        "    no:cacheprovider\n")
        (out / "plan.json").write_text(json.dumps({"tests": ["tests/test_x.py"],
                                                   "planned": []}))
        monkeypatch.setattr(cli.M, "ROOT", str(root))
        monkeypatch.setattr(cli.M, "fresh_workspace", lambda root=None: False)
        runs = []

        def fake_run(names, log, env=None):
            runs.append(names)
            with open(log, "w", encoding="utf-8") as fh:
                fh.write(f"FAILED tests/test_y.py::test_{len(runs)} - no\n")
            return 1
        monkeypatch.setattr(cli, "_mutmut_run", fake_run)
        monkeypatch.setattr(cli, "_fails_in_the_copy", lambda p, o: ["tests/test_x.py::test_scan"])

        class A:
            pass
        a = A()
        a.out = str(out)
        assert cli.cmd_run(a) == 1
        assert len(runs) == 2 and runs[0] == runs[1], "tried again, the same canary"
        assert "--deselect\n    tests/test_x.py::test_scan\n" in (root / "setup.cfg").read_text()
        record = json.loads((out / "run.json").read_text())
        assert record["not_run_fail_in_the_copy"] == ["tests/test_x.py::test_scan"]
        assert [r["log"] for r in record["runs"]] == ["mutmut-run-1.log", "mutmut-run-2.log"]
        assert record["failure"] == ["FAILED tests/test_y.py::test_2 - no"], "the retry's cause"


PROBE_FN = "modules.readers.reachability.probe"          # a function's dotted name
PROBE_MUT = "modules.readers.reachability.x_probe"      # mutmut's, before `__mutmut_<n>`
SURVIVOR_12 = ("if response and response > 0:", "if response or response > 0:")
SURVIVOR_31 = ("with connect((ip, 22), timeout=2):", "with connect((ip, 22), ):")


def _cli():
    """scripts/nmas-mutation as a module."""
    loader = importlib.machinery.SourceFileLoader(
        "nmas_mutation_cli_debt", os.path.join(ROOT, "scripts", "nmas-mutation"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    cli = importlib.util.module_from_spec(spec)
    loader.exec_module(cli)
    return cli


def _debt(*survivors, fn=PROBE_FN, h="h1"):
    return {"functions": {fn: {"path": "modules/readers/reachability.py", "qualname": "probe",
                               "hash": h, "survivors": [{"was": w, "now": n, "reason": "r"}
                                                        for w, n in survivors]}}}


class TestTheDebt:
    """Known open VERDICT survivors (the operator, 2026-10-14): code that was only moved (C781)
    arrived with hundreds at once. The debt list is a committed baseline like the coverage
    ratchet's: a night is red on a survivor not on it, or when it grows; it is reported every
    night; it grows only on purpose."""

    def test_mutmuts_names_are_read_back_to_a_path_and_a_qualname(self):
        for f in (PROBE, ("modules/nsot/x.py", "Box.fill"), ("modules/a.py", "Outer.Inner.m")):
            assert M.unmangle(M.mangled(*f)) == f
        with pytest.raises(ValueError):
            M.unmangle("modules.a.not_mangled")

    def test_a_survivor_is_on_the_list_by_its_function_and_two_lines_or_by_its_hash_moved(self):
        debt = _debt(SURVIVOR_12)
        assert M.on_debt(debt, PROBE_FN, *SURVIVOR_12)
        assert not M.on_debt(debt, PROBE_FN, *SURVIVOR_31), "another line of the same function"
        moved = "modules.readers.elsewhere.probe"
        assert not M.on_debt(debt, moved, *SURVIVOR_12)
        assert M.on_debt(debt, moved, *SURVIVOR_12, "h1"), "moved, its text unchanged"
        assert not M.on_debt(debt, moved, *SURVIVOR_12, "h2"), "moved and changed: not known"

    def test_the_verdict_parts_known_debt_from_new(self):
        results = {f"{PROBE_MUT}__mutmut_12": "survived", f"{PROBE_MUT}__mutmut_31": "survived",
                   f"{PROBE_MUT}__mutmut_1": "killed"}
        shows = {f"{PROBE_MUT}__mutmut_12": _fixture("show-probe-12.txt"),
                 f"{PROBE_MUT}__mutmut_31": _fixture("show-probe-31.txt")}
        v = M.verdict(results, shows, [], {}, _debt(SURVIVOR_12))
        assert [s["mutant"] for s in v["debt"]] == [f"{PROBE_MUT}__mutmut_12"]
        assert [s["mutant"] for s in v["new"]] == [f"{PROBE_MUT}__mutmut_31"]
        per = v["functions"]["modules.readers.reachability.probe"]
        assert (per["debt"], per["verdict"], per["killed"]) == (1, 1, 1)
        text = M.summary("a" * 40, "b" * 40, [PROBE], v, [], 120)
        assert "| `modules.readers.reachability.probe` | 3 | 1 | 2 | 1 | 0 | 0 |" in text, \
            "both open VERDICT survivors counted, one of them on the debt list"
        assert "### New open VERDICT survivors (1)" in text
        assert "### Known debt met tonight (1)" in text

    def test_code_changed_after_it_was_listed_makes_its_survivors_new(self):
        """The operator, 2026-10-14: "new" means a survivor in code changed after the debt was
        listed. Given the function's text hash, an entry counts only at that hash."""
        debt = _debt(SURVIVOR_12, h="h1")
        assert M.on_debt(debt, PROBE_FN, *SURVIVOR_12, "h1"), "the text it was listed at"
        assert not M.on_debt(debt, PROBE_FN, *SURVIVOR_12, "h2"), "changed since: new"
        assert M.debt_unchanged(debt, PROBE_FN, "h1") and not M.debt_unchanged(debt, PROBE_FN,
                                                                                "h2")

    def test_the_baseline_sweep_never_fails_a_night_and_only_at_its_text(self):
        """The operator's approval (2026-10-14), for night #4's sweep only: a survivor off the
        list in a sweep function still at its listed text is `sweep`, never `new`; the same
        survivor once the text changed is new (the rule hardens)."""
        results = {f"{PROBE_MUT}__mutmut_31": "survived"}
        shows = {f"{PROBE_MUT}__mutmut_31": _fixture("show-probe-31.txt")}
        sweep = {PROBE_FN: "h1"}
        at = M.verdict(results, shows, [], {}, {"functions": {}}, {PROBE_FN: "h1"}, sweep)
        assert [s["mutant"] for s in at["sweep"]] == [f"{PROBE_MUT}__mutmut_31"]
        assert at["new"] == []
        moved_on = M.verdict(results, shows, [], {}, {"functions": {}}, {PROBE_FN: "h2"}, sweep)
        assert moved_on["sweep"] == [] and len(moved_on["new"]) == 1
        text = M.summary("a" * 40, "b" * 40, [PROBE], at, [], 120, known=196)
        assert "**196 known, 0 new**, 1 found finishing the baseline sweep" in text
        assert "### Found finishing the baseline sweep (1)" in text
        assert "| `modules.readers.reachability.probe` | 1 | 0 | 1 |" in text

    def test_the_sweeps_additions_are_not_growth_and_only_its_reason_adds_them(self, tmp_path):
        """Entries with the sweep's reason never turn a night red as growth; `debt add` with
        that reason adds only the sweep's survivors, and any other reason only new ones."""
        debt = _debt(SURVIVOR_12)
        debt["functions"][PROBE_FN]["survivors"].append(
            {"was": SURVIVOR_31[0], "now": SURVIVOR_31[1], "reason": M.SWEEP_REASON})
        assert (M.debt_entries(debt), M.debt_entries(debt, counted=True)) == (2, 1)
        cli = _cli()
        swept = {"mutant": f"{PROBE_MUT}__mutmut_31", "function": PROBE_FN,
                 "was": SURVIVOR_31[0], "now": SURVIVOR_31[1]}
        new = {"mutant": f"{PROBE_MUT}__mutmut_12", "function": PROBE_FN,
               "was": SURVIVOR_12[0], "now": SURVIVOR_12[1]}
        report = tmp_path / "report.json"
        report.write_text(json.dumps({"plan": {"head": "HEAD"}, "error": "",
                                      "verdict": {"new": [new], "sweep": [swept]}}))
        listed = tmp_path / "debt.json"
        listed.write_text(json.dumps({"functions": {}}))
        args = ["debt", "add", "--from-report", str(report), "--file", str(listed)]
        assert cli.main(args + ["--reason", M.SWEEP_REASON]) == 0
        got = json.loads(listed.read_text())["functions"][PROBE_FN]["survivors"]
        assert [(s["was"], s["reason"]) for s in got] == [(SURVIVOR_31[0], M.SWEEP_REASON)]
        assert cli.main(args + ["--reason", "accepted on purpose"]) == 0
        got = json.loads(listed.read_text())["functions"][PROBE_FN]["survivors"]
        assert sorted(s["was"] for s in got) == sorted([SURVIVOR_12[0], SURVIVOR_31[0]])

    def test_the_sweep_file_names_real_functions(self):
        """Night #4's 20 left-over functions, each named by its path and qualname and a counted
        function at HEAD (a deleted one would be a stale approval)."""
        with open(M.SWEEP_FILE, encoding="utf-8") as fh:
            funcs = json.load(fh)["functions"]
        assert len(funcs) == 20 and set(M.load_sweep()) == set(funcs)
        for name, f in funcs.items():
            assert M.dotted((f["path"], f["qualname"])) == name
            with open(os.path.join(ROOT, f["path"]), encoding="utf-8") as fh:
                assert M.function_hash(fh.read(), f["qualname"]), name

    def test_the_list_grows_only_with_a_reason_and_never_twice_for_one_survivor(self):
        debt = {"functions": {}}
        new = [{"mutant": f"{PROBE_MUT}__mutmut_12", "function": PROBE_FN,
                "was": SURVIVOR_12[0], "now": SURVIVOR_12[1]},
               {"mutant": f"{PROBE_MUT}__mutmut_31", "function": PROBE_FN,
                "was": SURVIVOR_31[0], "now": SURVIVOR_31[1]}]
        with pytest.raises(ValueError, match="reason"):
            M.add_to_debt(debt, new, "  ", lambda p, q: "h")
        assert M.add_to_debt(debt, new, "moved, C781", lambda p, q: f"hash of {p}::{q}") == 2
        assert M.add_to_debt(debt, new, "again", lambda p, q: "h") == 0
        entry = debt["functions"][PROBE_FN]
        assert (entry["path"], entry["qualname"]) == PROBE
        assert entry["hash"] == "hash of modules/readers/reachability.py::probe"
        assert [s["reason"] for s in entry["survivors"]] == ["moved, C781", "moved, C781"]
        assert M.debt_entries(debt) == 2

    def test_the_debt_is_reported_with_its_change_and_its_biggest_functions(self):
        debt = _debt(SURVIVOR_12, SURVIVOR_31)
        first = M.debt_lines([], debt, None)
        assert first[0].startswith("Known debt: 2 open VERDICT survivor(s) in 1 function(s)")
        assert "first counted tonight" in first[0]
        assert "unchanged since the last night" in M.debt_lines([], debt, 2)[0]
        assert "+1 since the last night (1)" in M.debt_lines([{}], debt, 1)[0]
        assert "1 met tonight" in M.debt_lines([{}], debt, 1)[0]
        assert f"| `{PROBE_FN}` | 2 |" in M.debt_lines([], debt, 2)

    def test_the_record_keeps_open_debt_finished_hashes_and_the_lists_size(self):
        tcp = ("modules/integrations/monitoring_profile.py", "tcp_accepts")
        results = {f"{PROBE_MUT}__mutmut_12": "survived",
                   "modules.integrations.monitoring_profile.x_tcp_accepts__mutmut_1": "killed"}
        state = M.next_state("c" * 40, [PROBE, tcp], results, [f"{PROBE_MUT}__mutmut_12"],
                             {M.key(PROBE): "hp", M.key(tcp): "ht"},
                             finished_before={"modules/old.py::gone": {"hash": "hg"}},
                             debt_count=441)
        assert list(state["functions"]) == [M.key(PROBE)], "the debt survivor runs again"
        assert state["finished"] == {M.key(tcp): {"hash": "ht"},
                                     "modules/old.py::gone": {"hash": "hg"}}
        assert state["debt_entries"] == 441

    @staticmethod
    def _cli(name):
        loader = importlib.machinery.SourceFileLoader(
            name, os.path.join(ROOT, "scripts", "nmas-mutation"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cli = importlib.util.module_from_spec(spec)
        loader.exec_module(cli)
        return cli

    def _night(self, tmp_path, monkeypatch, listed, previous):
        """The real report step over a night with two open VERDICT survivors of probe (12, 31)
        and one kill, *listed* of them on the debt list, the last night's list *previous*."""
        import json
        cli = self._cli("nmas_mutation_cli_debt_report")
        out = tmp_path / "out"
        out.mkdir()
        (out / "plan.json").write_text(json.dumps({
            "base": "a" * 40, "head": "b" * 40, "planned": [list(PROBE)], "kept": {},
            "hashes": {M.key(PROBE): "h1"}, "moved": {}, "previous_debt_entries": previous}))
        (out / "run.json").write_text(json.dumps({"kinds": {}}))
        debt_file = tmp_path / "debt.json"
        debt_file.write_text(json.dumps(_debt(*listed)))
        monkeypatch.setattr(cli.M, "DEBT_FILE", str(debt_file))
        results = "\n".join(f"    {m}: {s}" for m, s in {
            **CANARY_KILLED, f"{PROBE_MUT}__mutmut_1": "killed",
            f"{PROBE_MUT}__mutmut_12": "survived", f"{PROBE_MUT}__mutmut_31": "survived"}.items())
        shows = {f"{PROBE_MUT}__mutmut_12": _fixture("show-probe-12.txt"),
                 f"{PROBE_MUT}__mutmut_31": _fixture("show-probe-31.txt")}
        monkeypatch.setattr(cli, "_mutmut", lambda *a: results if a[0] == "results"
                            else shows.get(a[1], ""))

        class A:
            plan, summary = str(out / "plan.json"), str(tmp_path / "summary.md")
            state_out, budget, mutmut_exit = str(tmp_path / "next.json"), 120, 0
        code = cli.cmd_report(A())
        return code, (tmp_path / "summary.md").read_text(), json.loads(
            (tmp_path / "next.json").read_text())

    def test_a_night_whose_open_survivors_are_all_known_is_green_and_says_so(
            self, tmp_path, monkeypatch):
        # Survivor 12 is a known EQUIVALENT (tests/mutation_equivalent.py), judged before the
        # debt is asked; 31 is the debt met tonight.
        code, text, state = self._night(tmp_path, monkeypatch, [SURVIVOR_12, SURVIVOR_31], 2)
        assert code == 0
        assert "Known debt: 2 open VERDICT survivor(s) in 1 function(s)" in text
        assert "unchanged since the last night; 1 met tonight" in text
        assert "### New open VERDICT survivors (0)" in text
        assert "### Known debt met tonight (1)" in text
        assert state["debt_entries"] == 2
        assert state["functions"][M.key(PROBE)]["open"] == [f"{PROBE_MUT}__mutmut_31"], \
            "the debt runs again each night"

    def test_a_survivor_off_the_list_turns_the_night_red(self, tmp_path, monkeypatch):
        code, text, _state = self._night(tmp_path, monkeypatch, [SURVIVOR_12], 1)  # 31 is new
        assert code == 1 and "### New open VERDICT survivors (1)" in text

    def test_the_list_grown_since_the_last_night_turns_it_red_once(self, tmp_path, monkeypatch):
        code, text, state = self._night(tmp_path, monkeypatch, [SURVIVOR_12, SURVIVOR_31], 1)
        assert code == 1 and "**The debt list grew** from 1 to 2" in text
        assert state["debt_entries"] == 2, "the next night measures from here"

    def test_debt_add_takes_a_nights_new_survivors_with_a_reason(self, tmp_path, capsys):
        import json
        cli = self._cli("nmas_mutation_cli_debt_add")
        head = M.git("rev-parse", "HEAD").strip()
        report = tmp_path / "report.json"
        new = [{"mutant": f"{PROBE_MUT}__mutmut_12", "function": PROBE_FN,
                "was": SURVIVOR_12[0], "now": SURVIVOR_12[1]}]
        report.write_text(json.dumps({"error": "", "plan": {"head": head},
                                      "verdict": {"new": new}}))
        debt_file = tmp_path / "debt.json"
        args = ["debt", "add", "--from-report", str(report), "--file", str(debt_file)]
        assert cli.main(args + ["--reason", " "]) == 2 and not debt_file.exists()
        assert cli.main(args + ["--reason", "moved, C781"]) == 0
        saved = json.loads(debt_file.read_text())
        entry = saved["functions"][PROBE_FN]
        source = M.git("show", f"{head}:modules/readers/reachability.py")
        assert entry["hash"] == M.function_hash(source, "probe") and entry["hash"]
        assert entry["survivors"] == [{"was": SURVIVOR_12[0], "now": SURVIVOR_12[1],
                                       "reason": "moved, C781"}]
        assert "the list grows only" not in capsys.readouterr().out
        failed = tmp_path / "failed.json"
        failed.write_text(json.dumps({"error": "mutmut exited 1", "plan": {"head": head},
                                      "verdict": {"new": new}}))
        assert cli.main(["debt", "add", "--from-report", str(failed), "--file",
                         str(tmp_path / "other.json"), "--reason", "r"]) == 2

    def test_every_function_on_the_committed_list_exists_and_every_entry_has_a_reason(self):
        """The operator's rule: an entry for a function that no longer exists is refused (a
        killed, renamed or deleted function's survivors leave the list with it)."""
        assert os.path.exists(M.DEBT_FILE), "tests/mutation_debt.json is committed"
        assert M.debt_problems(M.load_debt()) == []

    def test_a_listed_function_that_is_gone_a_wrong_name_and_no_reason_are_each_named(self):
        """The check above, on planted entries: its control."""
        planted = {"functions": {
            "modules.goldens.no_such": {"path": "modules/goldens.py", "qualname": "no_such",
                                        "hash": "h", "survivors": []},
            "modules.goldens.wrong_name": {"path": "modules/goldens.py",
                                           "qualname": "_identity_for_ip", "hash": "h",
                                           "survivors": []},
            "modules.goldens._nsot_repo_dir": {"path": "modules/goldens.py",
                                               "qualname": "_nsot_repo_dir", "hash": "h",
                                               "survivors": [{"was": "a", "now": "b",
                                                              "reason": " "}]}}}
        problems = M.debt_problems(planted)
        assert len(problems) == 3, problems
        assert any("goldens.no_such: no function 'no_such'" in p for p in problems)
        assert any("goldens.wrong_name: its path and qualname name" in p for p in problems)
        assert any("without both lines or a reason" in p for p in problems)


@pytest.fixture
def moved(tmp_path):
    """A real history: `kept` moves to another module unchanged, `edited` moves and changes."""
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t",
                        "-c", "user.email=t@example.invalid", *args],
                       check=True, capture_output=True)
    os.makedirs(tmp_path / "tests")
    shutil.copy(os.path.join(ROOT, "tests", "coverage_scope.py"), tmp_path / "tests")
    os.makedirs(tmp_path / "modules")
    body = "def kept(x):\n    return x + 1\n\n\ndef edited(x):\n    return x * 2\n"
    (tmp_path / "modules/old.py").write_text(body + "\n\ndef stays():\n    return 0\n")
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-qm", "one")
    (tmp_path / "modules/old.py").write_text("def stays():\n    return 0\n")
    (tmp_path / "modules/new.py").write_text(body.replace("x * 2", "x * 3"))
    git("add", "-A")
    git("commit", "-qm", "two")
    head = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    return str(tmp_path), head


class TestAMovedFunctionIsSaid:
    """Tonight's shared pieces moved module, their text unchanged (the operator, 2026-10-14).
    The record keys a function by path and name, so a moved one is mutated in full, and the
    plan and the summary say it moved rather than call it changed."""

    def test_a_function_moved_unchanged_is_named_with_where_it_was(self, moved):
        root, head = moved
        p = M.plan({}, head, root=root)
        assert set(p["planned"]) == {("modules/new.py", "kept"), ("modules/new.py", "edited")}
        assert p["moved"] == {"modules/new.py::kept": "modules/old.py::kept"}

    def _base(self, root, head):
        return M.git("rev-parse", f"{head}~1", root=root).strip()

    def _kept_hash(self, root, head):
        return M.function_hash(M.git("show", f"{head}:modules/new.py", root=root), "kept")

    def test_a_move_the_record_knows_carries_its_results_renamed(self, moved):
        """The operator, 2026-10-14: a function whose text hash the record holds under another
        name is MOVED; its results carry over and only what was left or open runs."""
        root, head = moved
        old = "modules.old.x_kept__mutmut_"
        state = {"commit": self._base(root, head), "functions": {"modules/old.py::kept": {
            "hash": self._kept_hash(root, head),
            "results": {old + "1": "killed", old + "2": "not checked", old + "3": "survived"},
            "open": [old + "3"]}}}
        p = M.plan(state, head, root=root)
        assert p["carried"] == {"modules/new.py::kept": "modules/old.py::kept"}
        new = "modules.new.x_kept__mutmut_"
        assert p["kept"]["modules/new.py::kept"]["results"] == {
            new + "1": "killed", new + "2": "not checked", new + "3": "survived"}
        assert p["names"]["modules/new.py::kept"] == [new + "2", new + "3"]
        assert ("modules/new.py", "edited") in p["planned"], "moved and changed: afresh"
        assert M.patterns(p) == [new + "2", new + "3", "modules.new.x_edited__mutmut_*"]

    def test_a_move_finished_before_or_on_the_debt_list_is_not_mutated_again(self, moved):
        root, head = moved
        base, h = self._base(root, head), self._kept_hash(root, head)
        finished = M.plan({"commit": base, "functions": {},
                           "finished": {"modules/old.py::kept": {"hash": h}}}, head, root=root)
        assert finished["skipped_moved"] == {"modules/new.py::kept": "modules/old.py::kept"}
        assert ("modules/new.py", "kept") not in finished["planned"]
        debt = {"functions": {"modules.old.kept": {"path": "modules/old.py", "qualname": "kept",
                                                   "hash": h, "survivors": []}}}
        owed = M.plan({"commit": base, "functions": {}}, head, root=root, debt=debt)
        assert owed["skipped_moved"] == {"modules/new.py::kept": "modules/old.py::kept"}
        assert ("modules/new.py", "kept") not in owed["planned"]
        forced = M.plan({"commit": base, "functions": {},
                         "finished": {"modules/old.py::kept": {"hash": h}}}, head, root=root,
                        also=["modules/new.py::kept"])
        assert ("modules/new.py", "kept") in forced["planned"] and not forced["skipped_moved"]

    def test_a_recorded_function_that_no_longer_exists_is_dropped_and_said(self, moved):
        """The AI family's removal (D15, 2026-10-14): a function the record names, unfinished or
        finished, that is gone at head is dropped from the record and named in the summary,
        never an error. The control: one whose text only changed is dropped as changed, not
        called gone."""
        root, head = moved
        base = self._base(root, head)
        stays = M.function_hash(M.git("show", f"{head}:modules/old.py", root=root), "stays")
        state = {"commit": base,
                 "functions": {"modules/old.py::edited": {"hash": "an old hash", "results": {},
                                                          "open": []},
                               "modules/old.py::stays": {"hash": "not its hash now",
                                                         "results": {}, "open": []}},
                 "finished": {"modules/gone.py::f": {"hash": "x"},
                              "modules/old.py::stays": {"hash": stays}}}
        p = M.plan(state, head, root=root)
        assert p["gone"] == ["modules/gone.py::f", "modules/old.py::edited"]
        assert p["dropped"] == ["modules/old.py::stays"], "changed, not gone"
        assert p["finished_before"] == {"modules/old.py::stays": {"hash": stays}}
        nxt = M.next_state(head, [], {}, [], {}, finished_before=p["finished_before"])
        assert "modules/gone.py::f" not in nxt["finished"]
        text = "\n".join(M.gone_lines(p))
        assert "Gone since the record (2)" in text and "a removal, not a failure" in text
        assert "- `modules/gone.py::f`" in text and "- `modules/old.py::edited`" in text
        assert M.gone_lines({"gone": [], "head": head}) == []

    def test_the_summary_says_which_moved(self, moved):
        root, head = moved
        p = M.plan({}, head, root=root)
        planned = [tuple(f) for f in p["planned"]]
        text = M.summary(p["base"], p["head"], planned, M.verdict({}, {}, []), [], 120,
                         "mutmut exited 1", moved=p["moved"])
        assert "Moved, their text unchanged (1 of 2)" in text
        assert "`modules/new.py` kept (moved from `modules/old.py::kept`" in text
        assert "`modules/new.py` edited\n" in text + "\n"
