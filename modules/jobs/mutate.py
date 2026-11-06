"""Mercury's own mutation engine for a job's code (the SDN platform design rev. 6, section 11a, item
2, step 5; decision 27): the standard library's `ast`, each mutant compiled in memory and the
folder's tests run against it in the same process (`modules/jobs/runner.py`), so the sandbox's
no-fork rule holds. A test suite that passes whatever the code does is found here: a mutant
the tests still pass is a SURVIVOR, described in plain words with its line quoted.

**The operators** (rev. 6's table), each applied once per site, to the job's own modules only
(never its tests, `spec.yml` or `conftest.py`, which the runner never counts as job code):

| # | Operator | Mutation |
|---|---|---|
| 1 | comparison | `==`/`!=`, `<`/`>=`, `>`/`<=`, `is`/`is not`, `in`/`not in` |
| 2 | boundary | `<`/`<=`, `>`/`>=` |
| 3 | boolean | `and`/`or`, `not x` to `x` |
| 4 | condition | an `if`'s, `while`'s or ternary's test `c` to `not c` |
| 5 | constant | an integer `n` to `n+1`; `True`/`False`; a non-empty string to `""` |
| 6 | arithmetic | `+`/`-`, `*`/`/` (in an expression or an augmented assignment) |
| 7 | return | `return x` to `return None` (never a `return` already giving None) |
| 8 | statement | a call statement removed (an expression statement such as `out.append(x)`) |
| 9 | early exit | `break`/`continue` |

A docstring is not a constant site (changing one changes nothing a test could see). **A mutant
that does not compile, or whose program is identical to the original or to an earlier
mutant's, is not counted** (`Generated.uncounted` says how many).

**The budget** (rev. 6; CLAUDE.md: bounds are about 2.5x a measured time):
- the unmutated run is timed first, by the gate, in the same process (`baseline`);
- each mutant is bounded at `BOUND_FACTOR` (2.5) times it, never less than
  `MIN_BOUND_SECONDS`;
- the whole step at that bound multiplied by the mutant count;
- at most `CEILING` (200) mutants: with *changed_lines*, those lines' mutants first; the rest
  are reported `not run`, never silently dropped.

`MIN_BOUND_SECONDS` is 0.5 s, the one figure here not 2.5x a measurement, and why: the
fixture jobs' unmutated runs measure 1.4 ms to 3.6 ms once the SDK is imported
(tests/fixtures/jobs, 2026-11-06, CI's Python 3.12.3 on the laptop), and 2.5x that is inside
one scheduler slice or garbage collection on a loaded host. A mutant stopped by the host's
noise would read as stopped, not survived, so noise would hide survivors. The floor is about
7.5x the slowest fixture run measured, 67 ms (the first run in a process, which imports the
SDK and parses the recorded Ryu).

**A firing bound names the mutant and the time it ran:** a mutant whose run passes its bound
is `stopped` ("stopped at its bound of 0.500 s, after 0.501 s"), which is not a survivor (the
tests did not pass); the step's bound firing leaves the rest `not run`, naming it.
"""

import ast
import copy
import hashlib
import time
from dataclasses import dataclass, field
from functools import partial
from typing import Optional

from modules.jobs import runner

BOUND_FACTOR = 2.5
MIN_BOUND_SECONDS = 0.5
CEILING = 200
OPERATORS = ("comparison", "boundary", "boolean", "condition", "constant", "arithmetic",
             "return", "statement", "early exit")
_COMPARISON = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt,
               ast.Gt: ast.LtE, ast.LtE: ast.Gt, ast.Is: ast.IsNot, ast.IsNot: ast.Is,
               ast.In: ast.NotIn, ast.NotIn: ast.In}
_BOUNDARY = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt}
_ARITHMETIC = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}
_OPS = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
        ast.Is: "is", ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in", ast.Add: "+",
        ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.And: "and", ast.Or: "or"}
SEGMENT_MAX = 60


@dataclass(frozen=True)
class Mutant:
    """One mutant: where (module, file, line, column), which operator, the change in words,
    the original line quoted, its stable `key` (what an equivalence mark names) and its code.
    The key hashes the module's source with the site, so any edit to the module retires every
    mark made on it."""

    key: str
    module: str
    file: str
    line: int
    column: int
    operator: str
    change: str
    quoted: str
    code: object = field(compare=False, repr=False)

    @property
    def words(self) -> str:
        """The survivor's sentence: "your tests didn't notice when line 14's `>` became
        `>=`"."""
        return f"your tests didn't notice when line {self.line}'s {self.change}"

    @property
    def where(self) -> str:
        return f"{self.file} line {self.line}: {self.quoted}"


@dataclass
class Generated:
    """The mutants of a folder's job modules, in source order, and how many sites made a
    mutant that was not counted (not compiling, or identical to the original or an earlier
    mutant)."""

    mutants: list
    uncounted: int
    by_operator: dict


def _segment(text: str, node) -> str:
    got = ast.get_source_segment(text, node) or ast.unparse(node)
    got = " ".join(got.split())
    return got if len(got) <= SEGMENT_MAX else got[:SEGMENT_MAX - 3] + "..."


def _docstrings(tree) -> set:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                found.add(id(body[0].value))
                found.add(id(body[0]))
    return found


def _replace(tree, target, new) -> None:
    """Put *new* where *target* sits in *tree*."""
    for parent in ast.walk(tree):
        for name, value in ast.iter_fields(parent):
            if value is target:
                setattr(parent, name, new)
                return
            if isinstance(value, list):
                for i, item in enumerate(value):
                    if item is target:
                        value[i] = new
                        return
    raise LookupError("the mutation's site is not in its tree")


# Each mutation, made on the copy of its node (`n`) inside a copy of the tree.

def _set_compare(n, _tree, i, new):
    n.ops[i] = new()


def _set_op(n, _tree, new):
    n.op = new()


def _unwrap_not(n, tree):
    _replace(tree, n, n.operand)


def _negate_test(n, _tree):
    n.test = ast.UnaryOp(ast.Not(), n.test)


def _set_value(n, _tree, value):
    n.value = value


def _return_none(n, _tree):
    n.value = ast.Constant(None)


def _put(n, tree, new):
    _replace(tree, n, new())


def _shown(value) -> str:
    text = repr(value)
    return text if len(text) <= SEGMENT_MAX else text[:SEGMENT_MAX - 3] + "..."


def _sites(node, text: str, docstrings: set):
    """`(operator, change, apply)` for each mutation *node* offers; `apply(copy, tree)` makes
    it on the copy of *node* inside a copy of the tree."""
    if isinstance(node, ast.Compare):
        for i, op in enumerate(node.ops):
            for operator, table in (("comparison", _COMPARISON), ("boundary", _BOUNDARY)):
                new = table.get(type(op))
                if new is not None:
                    yield (operator, f"`{_OPS[type(op)]}` became `{_OPS[new]}`",
                           partial(_set_compare, i=i, new=new))
    elif isinstance(node, ast.BoolOp):
        new = ast.Or if isinstance(node.op, ast.And) else ast.And
        yield ("boolean", f"`{_OPS[type(node.op)]}` became `{_OPS[new]}`",
               partial(_set_op, new=new))
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        yield ("boolean", f"`{_segment(text, node)}` became `{_segment(text, node.operand)}`",
               _unwrap_not)
    elif isinstance(node, (ast.If, ast.While, ast.IfExp)):
        test = _segment(text, node.test)
        yield "condition", f"condition `{test}` became `not ({test})`", _negate_test
    elif isinstance(node, ast.Constant) and id(node) not in docstrings:
        value = node.value
        if isinstance(value, bool):
            yield ("constant", f"`{value}` became `{not value}`",
                   partial(_set_value, value=not value))
        elif isinstance(value, int):
            yield ("constant", f"`{value}` became `{value + 1}`",
                   partial(_set_value, value=value + 1))
        elif isinstance(value, str) and value:
            yield ("constant", f"string `{_shown(value)}` became `''`",
                   partial(_set_value, value=""))
    elif isinstance(node, (ast.BinOp, ast.AugAssign)) and type(node.op) in _ARITHMETIC:
        new = _ARITHMETIC[type(node.op)]
        yield ("arithmetic", f"`{_OPS[type(node.op)]}` became `{_OPS[new]}`",
               partial(_set_op, new=new))
    elif isinstance(node, ast.Return) and node.value is not None and not (
            isinstance(node.value, ast.Constant) and node.value.value is None):
        yield "return", f"`{_segment(text, node)}` became `return None`", _return_none
    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) \
            and id(node) not in docstrings:
        yield ("statement", f"call `{_segment(text, node.value)}` was removed",
               partial(_put, new=ast.Pass))
    elif isinstance(node, (ast.Break, ast.Continue)):
        old, new = (("break", ast.Continue) if isinstance(node, ast.Break)
                    else ("continue", ast.Break))
        said = "continue" if old == "break" else "break"
        yield "early exit", f"`{old}` became `{said}`", partial(_put, new=new)


def generate(prepared: "runner.Prepared", changed_lines: dict = None) -> Generated:
    """Every counted mutant of *prepared*'s job modules (see the module's docstring). With
    *changed_lines* (`{module: {line, ...}}`), those lines' mutants come first."""
    mutants, uncounted = [], 0
    by_operator = {op: 0 for op in OPERATORS}
    for module, tree in prepared.trees.items():
        text = prepared.sources.job[module]
        name = prepared.sources.job_file(module)
        lines = text.splitlines()
        original = ast.dump(tree)
        seen = {original}
        docstrings = _docstrings(tree)
        nodes = list(ast.walk(tree))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        for index, node in enumerate(nodes):
            for count, (operator, change, apply) in enumerate(_sites(node, text, docstrings)):
                mutated = copy.deepcopy(tree)
                target = list(ast.walk(mutated))[index]
                apply(target, mutated)
                ast.fix_missing_locations(mutated)
                dumped = ast.dump(mutated)
                if dumped in seen:
                    uncounted += 1
                    continue
                try:
                    code = compile(mutated, name, "exec")
                except (SyntaxError, ValueError, TypeError):
                    uncounted += 1
                    continue
                seen.add(dumped)
                line = getattr(node, "lineno", 0)
                column = getattr(node, "col_offset", 0)
                key = hashlib.sha256(f"{digest}\0{index}\0{count}\0{operator}\0{change}"
                                     .encode("utf-8")).hexdigest()[:16]
                quoted = lines[line - 1].strip() if 0 < line <= len(lines) else ""
                mutants.append(Mutant(key, module, name, line, column, operator, change,
                                      quoted, code))
                by_operator[operator] += 1
    mutants.sort(key=lambda m: (m.module, m.line, m.column))
    if changed_lines:
        mutants.sort(key=lambda m: m.line not in changed_lines.get(m.module, ()))
    return Generated(mutants, uncounted, by_operator)


@dataclass
class MutantResult:
    """One mutant's outcome: `killed` (a test failed: `by` names it), `survived` (every test
    passed), `stopped` (its bound fired: `message` names the bound and the time it ran) or
    `not run` (past the ceiling, or the step's bound fired first: `message` says which)."""

    mutant: Mutant
    outcome: str
    seconds: float = 0.0
    by: str = ""
    message: str = ""


@dataclass
class Report:
    """The mutation step: each mutant's result, and the budget it ran under."""

    results: list
    baseline: float
    mutant_bound: float
    step_bound: float
    seconds: float
    uncounted: int
    by_operator: dict
    ceiling: int = CEILING
    step_fired: Optional[str] = None

    def of(self, outcome: str) -> list:
        return [r for r in self.results if r.outcome == outcome]

    @property
    def survivors(self) -> list:
        return [r.mutant for r in self.of("survived")]

    @property
    def complete(self) -> bool:
        """Every mutant ran to an outcome: none past the ceiling, none cut by the step's
        bound."""
        return not self.of("not run")

    def counts(self) -> dict:
        return {o: len(self.of(o)) for o in ("killed", "survived", "stopped", "not run")}


def mutant_bound(baseline: float, min_bound: float = MIN_BOUND_SECONDS) -> float:
    """A mutant's bound: 2.5x the unmutated run's measured *baseline*, at least *min_bound*."""
    return max(BOUND_FACTOR * baseline, min_bound)


def run_mutants(prepared: "runner.Prepared", baseline: float, *, ceiling: int = CEILING,
                changed_lines: dict = None, min_bound: float = MIN_BOUND_SECONDS,
                generated: Generated = None) -> Report:
    """Run *prepared*'s tests against each mutant of its job modules, within the budget (see
    the module's docstring), *baseline* being the unmutated run's measured seconds."""
    generated = generated or generate(prepared, changed_lines)
    chosen, past = generated.mutants[:ceiling], generated.mutants[ceiling:]
    bound = mutant_bound(baseline, min_bound)
    step_bound = bound * len(chosen)
    results, fired = [], None
    started = time.perf_counter()
    step_deadline = started + step_bound
    for mutant in chosen:
        remaining = step_deadline - time.perf_counter()
        if fired or remaining <= 0:
            fired = fired or (f"the step's bound of {step_bound:.3f} s ({len(chosen)} mutants "
                              f"x {bound:.3f} s) fired after "
                              f"{time.perf_counter() - started:.3f} s")
            results.append(MutantResult(mutant, "not run", message=fired))
            continue
        this_bound = min(bound, remaining)
        codes = dict(prepared.job_codes)
        codes[mutant.module] = mutant.code
        run = runner.run(prepared, job_codes=codes, bound=this_bound, fail_fast=True)
        if run.stopped:
            results.append(MutantResult(mutant, "stopped", run.seconds,
                                        message=f"mutant {mutant.key} ({mutant.where}; "
                                                f"{mutant.change}) {run.stopped}"))
        elif run.passed:
            results.append(MutantResult(mutant, "survived", run.seconds))
        else:
            first = run.failures()[0]
            results.append(MutantResult(mutant, "killed", run.seconds, by=first.id,
                                        message=first.message))
    for mutant in past:
        results.append(MutantResult(mutant, "not run", message=(
            f"past the ceiling of {ceiling} mutants ({len(generated.mutants)} made)")))
    return Report(results, baseline, bound, step_bound, time.perf_counter() - started,
                  generated.uncounted, generated.by_operator, ceiling, fired)
