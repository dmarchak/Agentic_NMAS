"""The job gate: ONE verdict on a job's folder, which `mercury job check` and Publish both call
(the SDN platform design rev. 6, section 11a, item 2; T24: the two cannot drift, because there is
one function). `check(folder, marks=...)` answers a `Verdict`: a list of checks, each passed
or failed, each with an action a person can take.

The checks, in order (a check whose input is refused says so, "not run", and names the check
to clear first; no code of the folder runs until the static check passes):
1. `spec`: the spec card (`modules/jobs/spec.py`), every field valid and no `ask:` left;
2. `static`: the AST allowlist over every module and test of the folder (`static_problems`),
   each refusal naming its file and line;
3. `tests`: the tests pass under Mercury's runner (`modules/jobs/runner.py`), timed;
4. `examples`: every acceptance example is `@covers`-ed by at least one test, and every
   `@covers` names an example; each one missing refused by name;
5. `asserts`: every test asserts something (`assertion_free`), refused by name;
6. `mutation`: the job's own code mutated (`modules/jobs/mutate.py`) and every mutant run
   within its budget, the unmutated run's time being the `tests` check's;
7. `survivors`: every mutant the tests did not notice is killed (a test added that fails for
   it) or marked equivalent by a PERSON with a reason (`record_equivalent`). A Draft shows its
   survivors here; Publish needs the check passed.

**An equivalence mark is a person's judgement, never an AI's:** `record_equivalent` refuses a
mark whose `trigger` is `ai` (an AI-gateway call or an assistant session), naming why. A mark
names a mutant by its key, which hashes its module's source, so any edit to the module retires
the marks made on it.

Each check's rule in words is `RULES[name]`, and the action it prints when it fails
`ACTIONS[name]`: one table, which the gate uses and the authoring guide quotes
(`modules/jobs/scaffold.py`). A controller app's verdict (`modules/apps/gate.py`) has the same
check names with two around them, its own allowlist, and runs no app code (C2635).

The verdict's `details` and `summary` hold no timings, so the same folder at the same revision
gives the same verdict, check by check, however loaded the host; the times are in `timings`.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import Optional

from modules.jobs import mutate, runner, spec as spec_card
from modules.jobs.base import ContractError

CHECKS = ("spec", "static", "tests", "examples", "asserts", "mutation", "survivors")
TRIGGERS = ("person", "ai")
REASON_MIN = 10
MUTANT_KEY = re.compile(r"^[0-9a-f]{16}$")
#: Dunder attributes a job may use: a class's own `__init__` (through `super()`) and a type's
#: `__name__`. Every other is how code walks to the interpreter's internals.
DUNDER_ALLOWED = frozenset({"__init__", "__name__"})
#: Attributes that reach a frame, a code object or a namespace without a dunder.
INTROSPECTION = frozenset({
    "ag_code", "ag_frame", "co_code", "co_consts", "cr_code", "cr_frame", "f_back",
    "f_builtins", "f_code", "f_globals", "f_locals", "func_code", "func_globals", "gi_code",
    "gi_frame", "mro", "tb_frame", "tb_next",
})
#: A format string reaching an attribute or an item of a dunder (`"{0.__class__}"`).
_FORMAT_DUNDER = re.compile(r"\{[^{}]*[.\[]__")
#: The calls that make a test assert: pytest's raises and the SDK's refused.
_EXPECTING = ("raises", "refused")

#: What each check holds, in words: one home for the authoring guide's list
#: (`modules/jobs/scaffold.gate_checks_markdown`, held to `CHECKS` by tests/test_mercury_cli.py).
RULES = {
    "spec": f"{spec_card.SPEC} is a valid spec card: the contract, two or more acceptance "
            "examples, and no `ask:` question left open.",
    "static": "Every module and test of the folder passes the AST allowlist: imports only of "
              "the folder's own modules, modules.jobs, modules.jobs.testing, pytest's raises "
              "(in tests) and the standard library's safe set; no open, exec, eval, getattr "
              "or other forbidden builtin; no dunder or frame attribute; no bare except.",
    "tests": "The tests pass under Mercury's runner, in one process, with no network; a "
             "failed assertion shows both sides.",
    "examples": "Every acceptance example is covered by at least one test marked "
                "`@covers(\"<example name>\")`, and every `@covers` names an example.",
    "asserts": "Every test asserts something: an assert, a pytest.raises or a refused() "
               "block, directly or through a helper.",
    "mutation": "The job's own code is mutated (comparisons, boundaries, booleans, "
                "conditions, constants, arithmetic, returns, call statements, break and "
                "continue) and every mutant runs within its budget.",
    "survivors": "Every mutant the tests did not notice is killed by a new test, or marked "
                 "equivalent by the reviewer, a person, with a reason.",
}
#: The action a failed check prints (the guide quotes each); `mutation`'s takes the ceiling.
ACTIONS = {
    "spec": f"Correct each field named in {spec_card.SPEC}, and answer each `ask:` question: "
            "the spec card is the decision a person confirms.",
    "static": "Remove each use named: a job reaches the world only through ctx, and imports "
              "only its own modules, modules.jobs and the standard library's safe set.",
    "tests": "Fix the code or the test named: each failed assertion shows both sides.",
    "examples": "Mark a test @covers(\"<example>\") for each example named, or correct the "
                "name that matches no example.",
    "asserts": "Give each test named an assert, a pytest.raises or a refused() block: a test "
               "that asserts nothing passes whatever the code does.",
    "mutation": "Make the tests faster (the step's bound), or split the job or name its "
                "changed lines (the ceiling of {ceiling} mutants): every mutant must run.",
    "survivors": "Add a test that fails for each change named, or have the reviewer (a "
                 "person, never an AI) mark it equivalent with a reason.",
}
#: The static check's action when a file itself is refused (a link, too large, not UTF-8, a
#: shadowing name, Python in a subfolder other than tests/), before any use is read.
FOLDER_ACTION = "Correct each file named."
#: A check whose input was refused: "not run", naming the check to clear first.
NOT_RUN_ACTION = "Clear the {first} check first."


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    summary: str
    action: str
    details: tuple = ()

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "summary": self.summary,
                "action": self.action, "details": list(self.details)}


@dataclass
class Verdict:
    """The gate's verdict: `checks` in `CHECKS` order; `passed` when every one passed (what
    Publish needs); `timings` (seconds: the unmutated run, each test, the mutation step and
    its bounds); `run` and `mutation`, the runner's and the engine's own results."""

    folder: str
    checks: list
    timings: dict = field(default_factory=dict)
    run: Optional[object] = None
    mutation: Optional[object] = None

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def check(self, name: str) -> Check:
        for c in self.checks:
            if c.name == name:
                return c
        raise KeyError(f"no check named {name!r}: the gate's checks are {', '.join(CHECKS)}")

    def outcome(self) -> dict:
        """`{check: passed}`, what T24 compares between `job check` and Publish."""
        return {c.name: c.passed for c in self.checks}

    def as_dict(self) -> dict:
        return {"folder": self.folder, "passed": self.passed,
                "checks": [c.as_dict() for c in self.checks], "timings": dict(self.timings)}


# ── survivors marked equivalent ──────────────────────────────────────────────────────────────

class MarkRefused(ContractError):
    """An equivalence mark refused, naming the field, the value and the rule."""


@dataclass(frozen=True)
class EquivalenceMark:
    """A person's judgement that a surviving mutant is equivalent (no test could tell it from
    the original), with the reason. Validated when it is made, however it is made."""

    mutant: str
    by: str
    reason: str
    trigger: str

    def __post_init__(self):
        problems = []
        if not isinstance(self.mutant, str) or not MUTANT_KEY.fullmatch(self.mutant):
            problems.append(f"mutant {self.mutant!r} is not a mutant's key "
                            f"({MUTANT_KEY.pattern})")
        if self.trigger not in TRIGGERS:
            problems.append(f"trigger {self.trigger!r} is not one of {', '.join(TRIGGERS)}")
        elif self.trigger == "ai":
            problems.append("trigger 'ai' (an AI-gateway call or an assistant session) is "
                            "refused: a survivor is marked equivalent by a person, the "
                            "reviewer, with a reason; an AI marking survivors would clear "
                            "tests that prove nothing (rev. 6, section 11a, step 5)")
        if not isinstance(self.by, str) or not self.by.strip():
            problems.append("by names the person marking it, not an empty value")
        if not isinstance(self.reason, str) or len(self.reason.strip()) < REASON_MIN:
            problems.append(f"reason says why no test could tell the mutant from the original, "
                            f"at least {REASON_MIN} characters, not {self.reason!r}")
        if problems:
            raise MarkRefused(f"the equivalence mark on {self.mutant!r}", problems)


def record_equivalent(mutant, *, by: str, reason: str, trigger: str) -> EquivalenceMark:
    """A survivor marked equivalent: *mutant* (a `Mutant` or its key), by the person *by*,
    with *reason*; *trigger* is `person` or `ai`, and `ai` is refused, naming why. P4 keeps
    the mark in the review's record; the gate is handed the marks it holds."""
    key = mutant.key if isinstance(mutant, mutate.Mutant) else mutant
    return EquivalenceMark(key, by, reason, trigger)


# ── 2. the static check ──────────────────────────────────────────────────────────────────────

def _exports(module: str) -> frozenset:
    import importlib

    return frozenset(getattr(importlib.import_module(module), "__all__", ()))


def _is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def _import_problems(node, file: str, own: set, is_test: bool) -> list:
    where = f"{file} line {node.lineno}"
    sdk = ", ".join(runner.SDK_MODULES)
    out = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            top = alias.name.partition(".")[0]
            if alias.name in own or top in runner.SAFE_STDLIB:
                continue
            if alias.name == runner.PYTEST and is_test:
                continue
            if top == "modules":
                out.append(f"{where}: `import {alias.name}`: write `from {alias.name} import "
                           f"<names>`, so only the SDK's published names are reached")
            else:
                out.append(f"{where}: `import {alias.name}` is not allowed: a job imports its "
                           f"own modules, {sdk} and the standard library's safe set "
                           f"({', '.join(sorted(runner.SAFE_STDLIB))})")
        return out
    module, names = node.module or "", [a.name for a in node.names]
    if node.level:
        return [f"{where}: a relative import; the folder's modules are imported by name "
                "(`from job import ...`)"]
    if "*" in names:
        return [f"{where}: `from {module} import *` hides what is imported; name each"]
    top = module.partition(".")[0]
    if module in own or top in runner.SAFE_STDLIB:
        return []
    if module == runner.PYTEST and is_test:
        extra = [n for n in names if n != "raises"]
        return [f"{where}: `from pytest import {', '.join(extra)}`: the runner's pytest "
                "offers raises alone"] if extra else []
    if module == "modules.jobs.testing" and not is_test:
        return [f"{where}: modules.jobs.testing is for the job's tests, not its code"]
    if module in runner.SDK_MODULES:
        extra = [n for n in names if n not in _exports(module)]
        return [f"{where}: `from {module} import {', '.join(extra)}`: not among {module}'s "
                f"published names ({', '.join(sorted(_exports(module)))})"] if extra else []
    return [f"{where}: `from {module} import ...` is not allowed: a job imports its own "
            f"modules, {sdk} and the standard library's safe set "
            f"({', '.join(sorted(runner.SAFE_STDLIB))})"]


#: Why a forbidden builtin is refused, in a job's words (an app's gate gives its own).
JOB_REACH = "a job reaches the world only through ctx, and runs no code it builds"


def _file_problems(tree, file: str, own: set, is_test: bool) -> list:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out.extend(_import_problems(node, file, own, is_test))
        else:
            out.extend(node_problems(node, f"{file} line {getattr(node, 'lineno', 0)}",
                                     JOB_REACH))
    return out


def node_problems(node, where: str, reach: str) -> list:
    """The allowlist's rules for one node that is not an import, shared by the job gate and
    the app gate's own allowlist (`modules/apps/allowlist.py`): no forbidden builtin (*reach*
    says why), no dunder or frame attribute, no bare except, no format string reaching a
    dunder."""
    out = []
    if isinstance(node, ast.Name):
        if node.id in runner.FORBIDDEN_BUILTINS:
            out.append(f"{where}: `{node.id}` is not allowed: {reach}")
        elif _is_dunder(node.id) and node.id != "__name__":
            out.append(f"{where}: `{node.id}` is not allowed: it reaches the interpreter's "
                       "internals")
    elif isinstance(node, ast.Attribute):
        if (_is_dunder(node.attr) and node.attr not in DUNDER_ALLOWED) \
                or node.attr in INTROSPECTION:
            out.append(f"{where}: the attribute `.{node.attr}` is not allowed: it reaches "
                       "the interpreter's internals")
        elif isinstance(node.value, ast.Name) and node.value.id == runner.PYTEST \
                and node.attr != "raises":
            out.append(f"{where}: `pytest.{node.attr}`: the runner's pytest offers raises "
                       "alone (fixtures are parameters; use plain functions)")
    elif isinstance(node, ast.ExceptHandler):
        caught = node.type
        names = [e.id for e in (caught.elts if isinstance(caught, ast.Tuple) else [caught])
                 if isinstance(e, ast.Name)] if caught is not None else []
        if caught is None or "BaseException" in names:
            out.append(f"{where}: `except{'' if caught is None else ' BaseException'}:` is "
                       "not allowed: catch Exception or narrower, so the runner's bound "
                       "can stop the code")
    elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
            and _FORMAT_DUNDER.search(node.value):
        out.append(f"{where}: a format string reaching a dunder attribute "
                   f"({node.value[:40]!r}) is not allowed")
    return out


def static_problems(sources: "runner.Sources") -> list:
    """One line per refusal of the AST allowlist over *sources*' modules and tests, each
    naming its file and line (see the module's docstring and `runner`'s lists)."""
    own = set(sources.job)
    out = []
    for module, text in sources.job.items():
        out.extend(_parsed_problems(text, sources.job_file(module), own, False))
    for name, text in sources.tests.items():
        out.extend(_parsed_problems(text, name, own, True))
    return out


def _parsed_problems(text: str, file: str, own: set, is_test: bool) -> list:
    try:
        tree = ast.parse(text, filename=file)
    except (SyntaxError, ValueError) as exc:
        return [f"{file}: does not parse ({exc})"]
    return _file_problems(tree, file, own, is_test)


# ── 5. the assertion check ───────────────────────────────────────────────────────────────────

def _called(node) -> set:
    names = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


def _asserts_directly(node) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Assert):
            return True
        if isinstance(n, ast.Raise) and n.exc is not None:
            exc = n.exc.func if isinstance(n.exc, ast.Call) else n.exc
            if isinstance(exc, ast.Name) and exc.id == "AssertionError":
                return True
    return bool(_called(node) & set(_EXPECTING))


def assertion_free(trees: dict) -> list:
    """The tests (`file::name`) of *trees* (`{file: tree}`, the folder's test modules) that
    assert nothing: no `assert`, no `raise AssertionError`, no `pytest.raises` or `refused()`,
    and no call to a helper function in the folder's tests that does, followed to any depth.

    The same logic as Mercury's own suite's check, `assertion_free` in scripts/nmas_coverage.py
    (reimplemented, not imported: that is a development script, absent from the sandbox, and
    its helpers are private), narrowed and widened for a job: `refused()` counts, and a mock's
    `assert_*` and `pytest.fail` do not, a job's tests having neither."""
    helpers = {}
    for tree in trees.values():
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                helpers.setdefault(n.name, []).append(n)
    asserting = {name for name, nodes in helpers.items()
                 if any(_asserts_directly(n) for n in nodes)}
    changed = True
    while changed:                          # a helper calling an asserting helper asserts
        changed = False
        for name, nodes in helpers.items():
            if name not in asserting and any(_called(n) & asserting for n in nodes):
                asserting.add(name)
                changed = True
    found = []
    for file, tree in trees.items():
        tests, _problems = runner.collect(tree, file)
        for test in tests:
            if not _asserts_directly(test.node) and not (_called(test.node) & asserting):
                found.append(test.id)
    return found


def parsed_tests(sources: "runner.Sources") -> dict:
    """`{file: tree}` of *sources*' test files that parse (one that does not is named by the
    static or the tests check)."""
    trees = {}
    for name, text in sources.tests.items():
        try:
            trees[name] = ast.parse(text, filename=name)
        except (SyntaxError, ValueError):
            continue
    return trees


def asserts_check(sources: "runner.Sources", count: int) -> Check:
    """The `asserts` check over *sources*' tests, read from the source (shared by the app
    gate); *count* is the number of tests the summary names."""
    empty = assertion_free(parsed_tests(sources))
    if empty:
        return Check("asserts", False, f"{len(empty)} tests assert nothing", ACTIONS["asserts"],
                     tuple(f"{t} asserts nothing" for t in empty))
    return Check("asserts", True, f"every one of {count} tests asserts", "")


# ── the gate ─────────────────────────────────────────────────────────────────────────────────

def not_run(name: str, why: str, first: str) -> Check:
    return Check(name, False, f"not run: {why}", NOT_RUN_ACTION.format(first=first))


def spec_check(folder):
    try:
        card = spec_card.load_spec(folder)
    except ContractError as exc:
        return None, Check("spec", False, f"{spec_card.SPEC} is refused", ACTIONS["spec"],
                           tuple(exc.problems))
    return card, Check("spec", True, f"{spec_card.SPEC}: {card.kind} {card.name}, "
                                     f"{len(card.examples)} examples", "")


def examples_check(card, tests) -> Check:
    """The `examples` check over *tests* (`runner.TestSpec`s, read from the source: nothing
    runs), shared by the app gate."""
    if card is None:
        return not_run("examples", "the spec card is refused, so its examples cannot be "
                                    "mapped", "spec")
    names = card.example_names()
    covering = {n: [] for n in names}
    unknown = []
    for test in tests:
        for name in test.covers:
            if name in covering:
                covering[name].append(test.id)
            else:
                unknown.append(f"{test.id} @covers {name!r}, which is not one of "
                               f"{spec_card.SPEC}'s examples")
    missing = [f"the example {n!r} is covered by no test" for n in names if not covering[n]]
    details = tuple(missing + unknown)
    if details:
        return Check("examples", False, f"{len(missing)} of {len(names)} examples uncovered, "
                                        f"{len(unknown)} @covers naming no example",
                     ACTIONS["examples"], details)
    return Check("examples", True, f"each of {len(names)} examples is covered", "",
                 tuple(f"{n!r}: {', '.join(covering[n])}" for n in names))


def _mutation_checks(prepared, run, marks, changed_lines, timings):
    if run is None or not run.passed:
        why = "the tests do not pass on the unmutated code" if run is not None else \
            "the tests were not run"
        return None, [not_run("mutation", why, "tests"), not_run("survivors", why, "tests")]
    report = mutate.run_mutants(prepared, run.seconds, changed_lines=changed_lines)
    timings.update({"mutation_seconds": report.seconds, "mutant_bound": report.mutant_bound,
                    "step_bound": report.step_bound})
    counts = report.counts()
    summary = (f"{len(report.results)} mutants: {counts['killed']} killed, "
               f"{counts['survived']} survived, {counts['stopped']} stopped at their bound, "
               f"{counts['not run']} not run; {report.uncounted} not counted")
    details = tuple(f"stopped: {r.mutant.words} ({r.mutant.where})" for r in
                    report.of("stopped"))
    if report.complete:
        mutation = Check("mutation", True, summary, "", details)
    else:
        why = report.step_fired or report.of("not run")[0].message
        mutation = Check("mutation", False, summary,
                         ACTIONS["mutation"].format(ceiling=report.ceiling),
                         details + (f"not run: {why}",))
    marked = {}
    for mark in marks:
        if not isinstance(mark, EquivalenceMark):
            raise MarkRefused("the gate's marks", [f"a mark is an EquivalenceMark, made by "
                                                   f"record_equivalent, not {mark!r}"])
        marked[mark.mutant] = mark
    open_, lines = [], []
    for mutant in report.survivors:
        mark = marked.get(mutant.key)
        if mark is None:
            open_.append(mutant)
            lines.append(f"{mutant.words} ({mutant.where}; mutant {mutant.key})")
        else:
            lines.append(f"marked equivalent by {mark.by}: {mark.reason} ({mutant.where}; "
                         f"mutant {mutant.key})")
    if open_:
        survivors = Check("survivors", False, f"{len(open_)} survivors unmarked of "
                                              f"{len(report.survivors)}",
                          ACTIONS["survivors"], tuple(lines))
    else:
        survivors = Check("survivors", True, f"{len(report.survivors)} survivors, each marked "
                                             "equivalent by a person" if report.survivors
                          else "no survivors", "", tuple(lines))
    return report, [mutation, survivors]


def check(folder, *, marks=(), changed_lines: dict = None) -> Verdict:
    """The gate's verdict on *folder* (see the module's docstring). *marks* are the
    `EquivalenceMark`s the review holds; *changed_lines* (`{module: {line, ...}}`) orders the
    mutants past the ceiling."""
    folder = str(folder)
    card, spec = spec_check(folder)
    checks, timings = [spec], {}
    try:
        sources = runner.load_sources(folder)
    except ContractError as exc:
        checks.append(Check("static", False, "the folder is refused", FOLDER_ACTION,
                            tuple(exc.problems)))
        why = "the folder's files are refused"
        checks.extend(not_run(n, why, "static") for n in CHECKS[2:])
        return Verdict(folder, checks, timings)
    problems = static_problems(sources)
    if problems:
        checks.append(Check("static", False, f"{len(problems)} uses refused",
                            ACTIONS["static"], tuple(problems)))
        why = "the static check refused the code, and no code runs until it passes"
        checks.extend(not_run(n, why, "static") for n in CHECKS[2:])
        return Verdict(folder, checks, timings)
    checks.append(Check("static", True, f"{len(sources.job)} modules and {len(sources.tests)} "
                                        "test files allowed", ""))
    prepared = runner.prepare(sources)
    run = runner.run(prepared)
    timings["run_seconds"] = run.seconds
    timings["run_bound"] = run.bound
    timings["tests"] = {t.id: t.seconds for t in run.tests}
    if run.passed:
        checks.append(Check("tests", True, f"{len(run.tests)} tests passed", ""))
    else:
        details = tuple(prepared.problems) + tuple(f"{t.id}: {t.outcome}"
                                                    + (f": {t.message}" if t.message else "")
                                                    for t in run.failures())
        if not run.tests:
            details += (f"the folder has no tests: a {runner.TEST_PREFIX}*.py file of "
                        f"test functions, at its root or in {runner.TESTS_FOLDER}/",)
        summary = (f"stopped: {run.stopped}" if run.stopped else
                   f"{len(run.failures())} of {len(run.tests)} tests did not pass")
        checks.append(Check("tests", False, summary, ACTIONS["tests"], details))
    checks.append(examples_check(card, prepared.tests))
    checks.append(asserts_check(sources, len(run.tests)))
    report, last = _mutation_checks(prepared, run, marks, changed_lines, timings)
    checks.extend(last)
    return Verdict(folder, checks, timings, run, report)
