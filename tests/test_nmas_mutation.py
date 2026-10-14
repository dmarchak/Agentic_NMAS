"""The nightly mutation run (scripts/nmas_mutation.py, CLI scripts/nmas-mutation, workflow
.github/workflows/mutation-nightly.yml; docs/TESTING.md, "Mutation testing"), tested without
mutmut: what a night plans from a real git history and the record, how it reads mutmut's real
output (captured 2026-10-14 in tests/fixtures/mutation/), when the measurement is broken, when
the night fails, and what it leaves for the next night. mutmut itself is dev-only and never
installed here; the workflow is checked as a file."""
import fnmatch
import importlib.machinery
import importlib.util
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
        assert p["dropped"] == ["modules/gone.py::x", "modules/net.py::changed"]
        assert ("modules/net.py", "changed") in p["planned"] and p["kept"] == {}
        assert "modules.net.x_changed__mutmut_*" in M.patterns(p)

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
            "message": 1, "other": 0}
        text = M.summary("a" * 40, "b" * 40, [PROBE], v, [], 120)
        assert "| `modules.readers.reachability.probe` | 5 | 1 | 2 | 1 | 1 | 25.0% | 33.3% |" \
            in text
        assert "### Open VERDICT survivors (2)" in text and "with connect((ip, 22), ):" in text
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
        monkeypatch.setattr(cli.M, "plan", lambda state, h, also=(): M.plan(state, h, root=root,
                                                                            also=also))
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

    def test_the_summary_says_which_moved(self, moved):
        root, head = moved
        p = M.plan({}, head, root=root)
        planned = [tuple(f) for f in p["planned"]]
        text = M.summary(p["base"], p["head"], planned, M.verdict({}, {}, []), [], 120,
                         "mutmut exited 1", moved=p["moved"])
        assert "Moved, their text unchanged (1 of 2)" in text
        assert "`modules/new.py` kept (moved from `modules/old.py::kept`" in text
        assert "`modules/new.py` edited\n" in text + "\n"
