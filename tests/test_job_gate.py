"""The job gate (the SDN platform design rev. 6, section 11a, item 2; T23 and T24's one verdict):
`modules/jobs/gate.py`, the one verdict `job check` and Publish call.

T23, each rule planted: a tautological test passes the run but the mutation step names the
surviving mutant in plain words; an example no test covers is refused by name; a test with no
assert is refused; a spec card holding `ask:` is refused; a survivor marked equivalent by an
AI-triggered call is refused, and a person's mark accepted with its reason; the static
allowlist refuses each planted use, naming its line, and no code runs while it does. (A mutant
past its bound: tests/test_job_mutate.py.) T24's one verdict: the same folder gives the same
verdict, check by check, every time."""

import os
import shutil

import pytest

from modules.jobs import gate as G
from modules.jobs import mutate as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "tests", "fixtures", "jobs")


def copy(tmp_path, name: str) -> str:
    target = tmp_path / name
    shutil.copytree(os.path.join(JOBS, name), target)
    return str(target)


def line_of(path: str, fragment: str) -> int:
    with open(path, encoding="utf-8") as fh:
        return next(i for i, line in enumerate(fh, 1) if fragment in line)


def edit(folder: str, file: str, old: str, new: str) -> None:
    path = os.path.join(folder, file)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert old in text, f"{old!r} is not in {file}"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace(old, new, 1))


# ── the passing case, and T24's one verdict ──────────────────────────────────────────────────

def test_a_job_whose_tests_kill_every_mutant_passes_every_check():
    verdict = G.check(os.path.join(JOBS, "switch-links"))
    assert [c.name for c in verdict.checks] == list(G.CHECKS)
    assert verdict.passed, [(c.name, c.summary, c.details) for c in verdict.checks
                            if not c.passed]
    assert verdict.check("survivors").summary == "no survivors"
    assert all(c.action == "" for c in verdict.checks)


def test_the_same_folder_gets_the_same_verdict_check_by_check():
    folder = os.path.join(JOBS, "tautology")
    first, second = G.check(folder), G.check(folder)
    strip = [{k: v for k, v in c.items()} for c in first.as_dict()["checks"]]
    assert strip == second.as_dict()["checks"]
    assert first.outcome() == second.outcome()
    assert "timings" in first.as_dict() and "run_seconds" in first.timings


def test_every_failed_check_names_an_action():
    verdict = G.check(os.path.join(JOBS, "tautology"))
    failed = [c for c in verdict.checks if not c.passed]
    assert failed and all(c.action for c in failed)


# ── T23: a tautological test ─────────────────────────────────────────────────────────────────

def test_a_tautological_test_passes_but_its_survivor_is_named_in_plain_words():
    folder = os.path.join(JOBS, "tautology")
    verdict = G.check(folder)
    assert verdict.check("tests").passed and verdict.check("examples").passed
    assert verdict.check("asserts").passed and verdict.check("mutation").passed
    survivors = verdict.check("survivors")
    assert not survivors.passed and not verdict.passed
    line = line_of(os.path.join(folder, "job.py"), "count > busy")
    words = (f"your tests didn't notice when line {line}'s `>` became `>=` (job.py line "
             f"{line}: return \"busy\" if count > busy else \"ok\"; mutant ")
    assert any(d.startswith(words) for d in survivors.details), survivors.details
    assert survivors.summary == "3 survivors unmarked of 3"


# ── T23: the examples, the assertions, the spec card ─────────────────────────────────────────

def test_an_example_no_test_covers_is_refused_by_name(tmp_path):
    folder = copy(tmp_path, "switch-links")
    edit(folder, "test_job.py", '@covers("a switch past the threshold is busy")\n', "")
    check = G.check(folder).check("examples")
    assert not check.passed
    assert check.details == ("the example 'a switch past the threshold is busy' is covered by "
                             "no test",)


def test_a_covers_naming_no_example_is_refused_by_name(tmp_path):
    folder = copy(tmp_path, "switch-links")
    edit(folder, "test_job.py", '@covers("a switch past the threshold is busy")',
         '@covers("a switch past the threshold is busy", "a typo of an example")')
    check = G.check(folder).check("examples")
    assert not check.passed
    assert check.details == ("test_job.py::test_a_switch_past_the_threshold_is_busy @covers "
                             "'a typo of an example', which is not one of spec.yml's examples",)


def test_a_test_with_no_assert_is_refused_by_name(tmp_path):
    folder = copy(tmp_path, "switch-links")
    with open(os.path.join(folder, "test_extra.py"), "w", encoding="utf-8") as fh:
        fh.write("from job import label\n\n\ndef test_runs():\n    label(3, 2)\n\n\n"
                 "def checks(v):\n    assert v == 'busy'\n\n\n"
                 "def test_through_a_helper():\n    checks(label(3, 2))\n\n\n"
                 "def test_by_refusal():\n    from modules.jobs import refused\n"
                 "    with refused():\n        label(3, 2)\n")
    verdict = G.check(folder)
    check = verdict.check("asserts")
    assert not check.passed
    assert check.details == ("test_extra.py::test_runs asserts nothing",)
    assert verdict.check("tests").passed is False      # the refused() block raised nothing


def test_a_spec_card_holding_ask_is_refused_and_its_examples_not_mapped(tmp_path):
    folder = copy(tmp_path, "switch-links")
    edit(folder, "spec.yml", "permission: read", "permission: {ask: 'read or write?'}")
    verdict = G.check(folder)
    spec = verdict.check("spec")
    assert not spec.passed
    assert spec.details == ("permission: an open question, 'read or write?': answer it before "
                            "the card is checked",)
    assert verdict.check("examples").summary.startswith("not run: the spec card is refused")
    assert verdict.check("tests").passed            # the code's checks still run


def test_a_failing_test_names_both_operands_and_mutation_waits(tmp_path):
    folder = copy(tmp_path, "switch-links")
    edit(folder, "test_job.py", 'assert label(2, 2) == "ok"', 'assert label(2, 2) == "busy"')
    verdict = G.check(folder)
    tests = verdict.check("tests")
    assert not tests.passed
    assert ("test_job.py::test_a_switch_past_the_threshold_is_busy: failed: assert label(2, 2) "
            "== \"busy\": left 'ok', right 'busy' (==)") in tests.details[0]
    assert verdict.check("mutation").summary == ("not run: the tests do not pass on the "
                                                 "unmutated code")
    assert verdict.check("survivors").action == "Clear the tests check first."


# ── T23: survivors marked equivalent ─────────────────────────────────────────────────────────

def survivor(name: str = "arp-guard") -> M.Mutant:
    verdict = G.check(os.path.join(JOBS, name))
    return verdict.mutation.survivors[0]


def test_an_ai_triggered_equivalence_mark_is_refused_naming_why():
    mutant = survivor()
    with pytest.raises(G.MarkRefused) as exc:
        G.record_equivalent(mutant, by="assistant", reason="break and continue end the same "
                                                           "way here", trigger="ai")
    assert any(p.startswith("trigger 'ai' (an AI-gateway call or an assistant session) is "
                            "refused: a survivor is marked equivalent by a person")
               for p in exc.value.problems)


def test_a_mark_built_directly_is_refused_the_same_way():
    with pytest.raises(G.MarkRefused):
        G.EquivalenceMark(survivor().key, "assistant", "the loop ends either way", "ai")


@pytest.mark.parametrize("by, reason, trigger, words", [
    ("", "the loop ends either way", "person", "by names the person"),
    ("reviewer@example.invalid", "same", "person", "at least 10 characters"),
    ("reviewer@example.invalid", "the loop ends either way", "robot",
     "trigger 'robot' is not one of person, ai"),
])
def test_a_malformed_mark_is_refused_by_name(by, reason, trigger, words):
    with pytest.raises(G.MarkRefused) as exc:
        G.record_equivalent(survivor(), by=by, reason=reason, trigger=trigger)
    assert any(words in p for p in exc.value.problems), exc.value.problems


def test_a_persons_mark_clears_the_survivor_with_its_reason():
    folder = os.path.join(JOBS, "arp-guard")
    before = G.check(folder)
    assert [m.change for m in before.mutation.survivors] == ["`break` became `continue`"]
    assert not before.passed
    mark = G.record_equivalent(before.mutation.survivors[0], by="reviewer@example.invalid",
                               reason="past the limit every later switch is skipped either "
                                      "way, and nothing follows the loop's body",
                               trigger="person")
    after = G.check(folder, marks=[mark])
    assert after.passed, [(c.name, c.details) for c in after.checks if not c.passed]
    assert after.check("survivors").details[0].startswith(
        "marked equivalent by reviewer@example.invalid: past the limit every later switch")


def test_a_mark_for_another_mutant_clears_nothing():
    folder = os.path.join(JOBS, "tautology")
    other = G.record_equivalent("0123456789abcdef", by="reviewer@example.invalid",
                                reason="a mark made for some other mutant", trigger="person")
    assert not G.check(folder, marks=[other]).check("survivors").passed


def test_a_mark_that_is_not_a_mark_is_refused():
    with pytest.raises(G.MarkRefused):
        G.check(os.path.join(JOBS, "arp-guard"), marks=[{"mutant": "x", "trigger": "person"}])


# ── the static check ─────────────────────────────────────────────────────────────────────────

PLANTED_USES = [
    ("import os", "`import os` is not allowed"),
    ("import subprocess", "`import subprocess` is not allowed"),
    ("from socket import socket", "`from socket import ...` is not allowed"),
    ("import modules.jobs", "`import modules.jobs`: write `from modules.jobs import <names>`"),
    ("from modules.jobs import lifecycle", "not among modules.jobs's published names"),
    ("from modules.jobs.testing import ctx", "modules.jobs.testing is for the job's tests"),
    ("from modules.config import load", "`from modules.config import ...` is not allowed"),
    ("from . import helper", "a relative import"),
    ("from json import *", "`from json import *` hides what is imported"),
    ("X = open('f')", "`open` is not allowed"),
    ("X = eval('1')", "`eval` is not allowed"),
    ("exec('x = 1')", "`exec` is not allowed"),
    ("X = __import__('os')", "`__import__` is not allowed"),
    ("X = getattr(int, 'real')", "`getattr` is not allowed"),
    ("X = __builtins__", "`__builtins__` is not allowed"),
    ("X = ().__class__.__bases__", "the attribute `.__bases__` is not allowed"),
    ("X = (lambda: 0).__globals__", "the attribute `.__globals__` is not allowed"),
    ("X = int.mro", "the attribute `.mro` is not allowed"),
    ("X = '{0.__class__}'.format(1)", "a format string reaching a dunder attribute"),
    ("try:\n    pass\nexcept:\n    pass", "`except:` is not allowed"),
    ("try:\n    pass\nexcept BaseException:\n    pass", "`except BaseException:` is not "
                                                         "allowed"),
]


@pytest.mark.parametrize("use, words", PLANTED_USES)
def test_each_planted_use_is_refused_naming_its_line(tmp_path, use, words):
    folder = copy(tmp_path, "switch-links")
    path = os.path.join(folder, "job.py")
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    lines[4:4] = use.splitlines()           # after the imports, at line 5
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    check = G.check(folder).check("static")
    assert not check.passed
    assert any(d.startswith("job.py line ") and words in d for d in check.details), \
        check.details
    assert all(d.split(":")[0].startswith("job.py line 5") or
               d.split(":")[0].startswith("job.py line 6") or
               d.split(":")[0].startswith("job.py line 7") for d in check.details), \
        check.details


def test_the_tests_may_use_pytest_raises_and_nothing_else_of_it(tmp_path):
    folder = copy(tmp_path, "arp-guard")
    assert G.check(folder).check("static").passed
    edit(folder, "test_job.py", "import pytest\n", "import pytest\n\nMARK = pytest.mark\n")
    check = G.check(folder).check("static")
    assert check.details == ("test_job.py line 6: `pytest.mark`: the runner's pytest offers "
                             "raises alone (fixtures are parameters; use plain functions)",)


def test_no_code_of_the_folder_runs_while_the_static_check_refuses_it(tmp_path, monkeypatch):
    monkeypatch.delenv("NMAS_JOB_GATE_PLANTED_RAN", raising=False)
    folder = copy(tmp_path, "switch-links")
    edit(folder, "job.py", "from modules.jobs import",
         "import os\nos.environ['NMAS_JOB_GATE_PLANTED_RAN'] = '1'\nfrom modules.jobs import")
    verdict = G.check(folder)
    assert not verdict.check("static").passed
    assert "NMAS_JOB_GATE_PLANTED_RAN" not in os.environ
    assert [verdict.check(n).summary for n in G.CHECKS[2:]] == [
        "not run: the static check refused the code, and no code runs until it passes"] * 5


def test_a_folder_file_refused_stops_the_code_checks(tmp_path):
    folder = copy(tmp_path, "switch-links")
    os.symlink(os.path.join(folder, "job.py"), os.path.join(folder, "other.py"))
    verdict = G.check(folder)
    assert verdict.check("static").details == ("other.py: is a symbolic link; a job's file is "
                                               "a regular file",)
    assert not verdict.check("tests").passed


def test_an_unknown_check_name_is_refused_naming_the_checks():
    verdict = G.check(os.path.join(JOBS, "switch-links"))
    with pytest.raises(KeyError) as exc:
        verdict.check("lint")
    assert "spec, static, tests, examples, asserts, mutation, survivors" in str(exc.value)
