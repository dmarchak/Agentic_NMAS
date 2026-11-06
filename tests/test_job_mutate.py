"""Mercury's own mutation engine (the SDN platform design rev. 6, section 11a, item 2, step 5;
decision 27; T23's bound case): `modules/jobs/mutate.py`.

Planted here: a function offering every one of rev. 6's nine operators, each of which must make a
mutant (the expected changes written out by hand, not derived from the engine's tables); a
docstring and a `return None` that must make none; two mutations giving one identical
program, counted once; the tests, never mutated; the plain words a survivor is described in;
the budget's numbers; and a mutant whose loop never ends, stopped at its bound and named."""

import ast
import os
import time

import pytest

from modules.jobs import mutate as M
from modules.jobs import runner as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "tests", "fixtures", "jobs")

EVERY = '''"""A planted module offering each operator."""


def every_operator(xs, limit, flag=True):
    """A docstring: never a constant site."""
    out = []
    total = 0
    for x in xs:
        if x == limit:
            continue
        if x > limit and flag:
            break
        total += x * 2
        out.append(x)
    if not out:
        return "none"
    return total
'''

#: Each change the planted function must offer, by operator, written out by hand.
EXPECTED = {
    ("comparison", "`==` became `!=`"), ("comparison", "`>` became `<=`"),
    ("boundary", "`>` became `>=`"),
    ("boolean", "`and` became `or`"), ("boolean", "`not out` became `out`"),
    ("condition", "condition `x == limit` became `not (x == limit)`"),
    ("condition", "condition `x > limit and flag` became `not (x > limit and flag)`"),
    ("condition", "condition `not out` became `not (not out)`"),
    ("constant", "`True` became `False`"), ("constant", "`0` became `1`"),
    ("constant", "`2` became `3`"), ("constant", "string `'none'` became `''`"),
    ("arithmetic", "`+` became `-`"), ("arithmetic", "`*` became `/`"),
    ("return", "`return \"none\"` became `return None`"),
    ("return", "`return total` became `return None`"),
    ("statement", "call `out.append(x)` was removed"),
    ("early exit", "`continue` became `break`"), ("early exit", "`break` became `continue`"),
}

COUNT_UP = '''def count_up(n):
    i = 0
    while i < n:
        i += 1
    return i
'''


def prepared(tmp_path, job: str, tests: dict = None):
    folder = tmp_path / "job"
    folder.mkdir(parents=True)
    (folder / "job.py").write_text(job)
    for name, text in (tests or {}).items():
        (folder / name).write_text(text)
    return R.prepare(R.load_sources(folder))


def line_of(text: str, fragment: str) -> int:
    return next(i for i, line in enumerate(text.splitlines(), 1) if fragment in line)


# ── the operators ────────────────────────────────────────────────────────────────────────────

def test_each_operator_makes_its_mutants_on_the_planted_function(tmp_path):
    got = M.generate(prepared(tmp_path, EVERY))
    assert {(m.operator, m.change) for m in got.mutants} == EXPECTED
    assert len(got.mutants) == len(EXPECTED)
    assert all(got.by_operator[op] >= 1 for op in M.OPERATORS)
    assert set(got.by_operator) == set(M.OPERATORS) and len(M.OPERATORS) == 9


def test_each_mutant_is_compiled_and_differs_from_the_original(tmp_path):
    p = prepared(tmp_path, EVERY)
    original = p.job_codes["job"]
    for mutant in M.generate(p).mutants:
        assert type(mutant.code) is type(original)
        assert mutant.code.co_consts != original.co_consts or \
            mutant.code.co_code != original.co_code


def test_a_docstring_and_a_return_of_none_make_no_mutant(tmp_path):
    job = ('"""Module docstring."""\n\n\ndef f():\n    """Function docstring."""\n'
           '    return None\n\n\ndef g():\n    return\n')
    got = M.generate(prepared(tmp_path, job))
    assert got.mutants == [] and got.uncounted == 0


def test_an_identical_mutant_is_not_counted(tmp_path):
    got = M.generate(prepared(tmp_path, "def f(y):\n    return not not y\n"))
    changes = [m.change for m in got.mutants]
    # The outer and the inner `not` each unwrap to `return not y`: one program, counted once.
    assert changes == ["`return not not y` became `return None`",
                       "`not not y` became `not y`"] or changes == [
        "`not not y` became `not y`", "`return not not y` became `return None`"]
    assert got.uncounted == 1


def test_the_tests_and_the_conftest_are_never_mutated(tmp_path):
    p = prepared(tmp_path, COUNT_UP, {"test_a.py": "def test_x():\n    assert 1 < 2 and True\n",
                                      "conftest.py": "X = 1 + 2\n"})
    assert {m.file for m in M.generate(p).mutants} == {"job.py"}


def test_the_survivors_words_name_the_line_and_the_change(tmp_path):
    p = prepared(tmp_path, EVERY)
    boundary = next(m for m in M.generate(p).mutants if m.operator == "boundary")
    line = line_of(EVERY, "x > limit and flag")
    assert boundary.words == f"your tests didn't notice when line {line}'s `>` became `>=`"
    assert boundary.where == f"job.py line {line}: if x > limit and flag:"


def test_a_key_is_stable_and_any_edit_to_the_module_retires_it(tmp_path):
    first = [m.key for m in M.generate(prepared(tmp_path / "a", EVERY)).mutants]
    again = [m.key for m in M.generate(prepared(tmp_path / "b", EVERY)).mutants]
    edited = [m.key for m in M.generate(prepared(tmp_path / "c", EVERY + "\n# edited\n")).mutants]
    assert first == again and len(set(first)) == len(first)
    assert not set(first) & set(edited)


def test_changed_lines_come_first(tmp_path):
    p = prepared(tmp_path, EVERY)
    line = line_of(EVERY, "out.append(x)")
    got = M.generate(p, changed_lines={"job": {line}})
    assert got.mutants[0].line == line
    assert sorted(m.line for m in got.mutants[1:]) == [m.line for m in got.mutants[1:]]


# ── the run and its budget ───────────────────────────────────────────────────────────────────

def test_the_budget_is_two_and_a_half_times_the_unmutated_run():
    assert M.mutant_bound(1.0) == 2.5
    assert M.mutant_bound(0.001) == M.MIN_BOUND_SECONDS == 0.5
    assert M.mutant_bound(0.001, min_bound=0.0) == pytest.approx(0.0025)


def test_the_tautology_fixture_is_run_within_its_budget():
    p = R.prepare(R.load_sources(os.path.join(JOBS, "tautology")))
    base = R.run(p)
    report = M.run_mutants(p, base.seconds)
    assert report.mutant_bound == M.mutant_bound(base.seconds)
    assert report.step_bound == pytest.approx(report.mutant_bound * len(report.results))
    assert report.complete and report.counts()["survived"] == 3
    assert report.seconds < report.step_bound


def test_past_the_ceiling_the_rest_are_named_not_run():
    p = R.prepare(R.load_sources(os.path.join(JOBS, "tautology")))
    report = M.run_mutants(p, 0.01, ceiling=3)
    made = len(M.generate(p).mutants)
    assert len(report.results) == made
    assert [r.outcome for r in report.results[3:]] == ["not run"] * (made - 3)
    assert report.results[3].message == f"past the ceiling of 3 mutants ({made} made)"
    assert not report.complete
    assert report.step_bound == pytest.approx(report.mutant_bound * 3)


def test_a_mutant_past_its_bound_is_stopped_and_named(tmp_path):
    p = prepared(tmp_path, COUNT_UP, {"test_a.py": (
        "from job import count_up\n\n\ndef test_three():\n    assert count_up(3) == 3\n")})
    base = R.run(p)
    assert base.passed
    report = M.run_mutants(p, base.seconds, min_bound=0.1)
    stopped = report.of("stopped")
    assert [r.mutant.change for r in stopped] == ["`+` became `-`"]
    line = line_of(COUNT_UP, "i += 1")
    message = stopped[0].message
    assert message.startswith(f"mutant {stopped[0].mutant.key} (job.py line {line}: i += 1; "
                              "`+` became `-`) stopped at the bound of ")
    bound = report.mutant_bound
    assert f"of {bound:.3f} s, after " in message
    assert stopped[0].seconds >= bound
    assert report.complete and not report.of("not run")
    # the constant 0 -> 1 survives (count_up(3) is still 3); the rest are killed
    assert [m.change for m in report.survivors] == ["`0` became `1`"]


def test_the_steps_bound_stops_the_rest_and_names_itself(tmp_path, monkeypatch):
    """A run that overruns its own bound (a single C-level operation the watch cannot stop)
    is caught by the step's bound, which leaves the rest not run, naming it."""
    p = prepared(tmp_path, COUNT_UP, {"test_a.py": (
        "from job import count_up\n\n\ndef test_three():\n    assert count_up(3) == 3\n")})
    real = R.run

    def overrunning(prepared_, *, job_codes=None, bound, fail_fast=False):
        result = real(prepared_, job_codes=job_codes, bound=bound, fail_fast=fail_fast)
        time.sleep(2 * bound)
        return result
    monkeypatch.setattr(M.runner, "run", overrunning)
    report = M.run_mutants(p, 0.0, min_bound=0.05)
    cut = report.of("not run")
    assert cut and not report.complete
    assert report.step_fired.startswith(f"the step's bound of {report.step_bound:.3f} s "
                                        f"({len(report.results)} mutants x 0.050 s) fired after ")
    assert all(r.message == report.step_fired for r in cut)
