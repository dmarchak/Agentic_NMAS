"""Mercury's own test runner for a job's folder (the SDN platform design rev. 6, section 11a, item
2; decisions 27 and 28): the standard library only, in ONE process (no fork, no subprocess,
no thread: the sandbox's `TasksMax=1`), and it never imports pytest.

**The format stays pytest's**, so the same folder runs unchanged under pytest (T24 holds the
two agree, test by test):
- the tests are the module-level functions whose names start `test` in the folder's
  `test_*.py` files (pytest's default `python_functions`), run in file order, then line
  order; a `Test*` class or an `async` test is refused by name (the runner does not run
  them, and a test the runner skips silently would look like a test that passed);
- a test's parameters are fixtures, each given by `modules.jobs.testing.fixture(name, job)`
  (`ctx`, `ryu`, `netbox`); a parameter with a default is not one, as under pytest;
- `import pytest` gets a shim offering `raises` alone (`modules.jobs.authoring.raises`), and
  `refused` (from `modules.jobs`) works the same; the folder's `conftest.py` is ignored here
  (it maps the same names for pytest);
- the folder's other modules (`job.py`, any helper beside it) are imported by their names,
  from the sources held in memory, possibly mutated (`modules/jobs/mutate.py`): nothing is
  written, and `sys.modules` and `sys.path` are never touched.

**A failed assertion names its operands**, as pytest's does: each test module's `assert` is
rewritten at import (`rewrite_asserts`, an `ast` transform). A comparison's two sides are each
evaluated ONCE, into a temporary, and a failure reads `assert 3 == 4: left 3, right 4 (==)`;
a chain (`a < b < c`) is checked pair by pair, short-circuiting as Python does; a bare
`assert x` reads `assert x: <x's value>`. An assertion's own message follows, after `; `.

**What a run may import, at run time as well as in the gate's static check** (one list,
here): the folder's own modules, `modules.jobs` and `modules.jobs.testing`, pytest's shim,
and the standard library's `SAFE_STDLIB`; `FORBIDDEN_BUILTINS` are removed from the
builtins the folder's code sees. The OS sandbox is the boundary (P4); this is the check a
person can read.

**The bound.** Every code object compiled from the folder (the job's and the tests') is
watched through `sys.monitoring` (a tool id of its own, `TOOL_IDS`; coverage.py's id is left
alone) on each line and each jump, so a loop that never ends is stopped at the run's
deadline wherever it spins in the folder's code: `BoundFired` (a `BaseException`, so a job's
`except Exception` cannot keep it) is raised in that code at once and again on every line
after, and the run reports `stopped`, naming the bound and the time it ran. A single
C-level operation (a huge power, say) is not interruptible this way; the sandbox's own limits
cover it. Python 3.12 or later is required (`sys.monitoring`), refused by name otherwise.

**The unmutated run's bound, `FIRST_RUN_SECONDS`:** there is no measured job yet (rev. 6 says so
of the mutation ceiling too). It is PROVISIONAL, a ceiling to re-derive as 2.5x
`dns_blacklist`'s first measured run; the fixture jobs' unmutated runs measured 62 ms to
67 ms for the first in a process (importing the SDK) and 1.4 ms to 3.6 ms after it
(tests/fixtures/jobs, 2026-11-06, the laptop, CI's Python 3.12.3), so it binds nothing they
do. Every later bound derives from the unmutated run's own measured time: the
mutation step's (`modules/jobs/mutate.py`) are 2.5x it.
"""

import ast
import builtins
import os
import sys
import threading
import time
import types
from dataclasses import dataclass, field
from typing import Optional

from modules.jobs.base import ContractError

#: See the module's docstring. Provisional until dns_blacklist's first run is measured.
FIRST_RUN_SECONDS = 60.0
#: A job folder's file, at most (a job's whole source is a few hundred lines).
MAX_FILE_BYTES = 256 * 1024
TEST_PREFIX = "test_"
TEST_FUNCTION_PREFIX = "test"
CONFTEST = "conftest.py"
#: The standard library a job and its tests may import: pure computation, no I/O, no process,
#: no introspection of the interpreter.
SAFE_STDLIB = frozenset({
    "abc", "base64", "bisect", "collections", "copy", "dataclasses", "datetime", "decimal",
    "difflib", "enum", "fractions", "functools", "hashlib", "heapq", "ipaddress", "itertools",
    "json", "math", "numbers", "operator", "re", "statistics", "string", "textwrap", "typing",
})
#: The SDK modules a job's folder may import (by `from <module> import <name>`).
SDK_MODULES = ("modules.jobs", "modules.jobs.testing")
PYTEST = "pytest"
#: Builtins the folder's code never gets: I/O, dynamic code, and the dynamic attribute access
#: that would walk around the static check's attribute rules.
FORBIDDEN_BUILTINS = frozenset({
    "open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr",
    "setattr", "delattr", "breakpoint", "input", "help", "exit", "quit", "memoryview",
})
#: sys.monitoring's ids not reserved for a debugger (0), coverage (1), a profiler (2) or an
#: optimizer (5).
TOOL_IDS = (3, 4)
REPR_MAX = 240
_SYMBOLS = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">",
            ast.GtE: ">=", ast.Is: "is", ast.IsNot: "is not", ast.In: "in",
            ast.NotIn: "not in"}
_LOCK = threading.Lock()


class SourceError(ContractError):
    """A job folder the runner will not read, naming each file and why."""


class RunnerError(RuntimeError):
    """The runner cannot run here (its interpreter, or no free monitoring id), naming why."""


class BoundFired(BaseException):
    """The run's deadline passed, raised inside the folder's code."""

    def __init__(self, bound: float, ran: float):
        self.bound, self.ran = bound, ran
        super().__init__(f"stopped at the bound of {bound:.3f} s, after {ran:.3f} s")


# ── the folder ───────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Sources:
    """A job folder held in memory: `job` (`{module name: source}`: every top-level `.py`
    file but the tests and `conftest.py`) and `tests` (`{file name: source}`)."""

    folder: str
    job: dict
    tests: dict

    def job_file(self, module: str) -> str:
        return f"{module}.py"


def load_sources(folder) -> Sources:
    """*folder*'s Python files, read once (see `Sources`); refused, naming each file, when one
    is a link, larger than `MAX_FILE_BYTES`, not UTF-8, a module whose name is not an
    identifier or would shadow one the folder may import, or when Python sits in a
    subfolder (the gate checks a folder's top level only)."""
    folder = os.fspath(folder)
    if not os.path.isdir(folder):
        raise SourceError(folder, ["is not a folder"])
    problems, job, tests = [], {}, {}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if os.path.isdir(path) and not os.path.islink(path):
            if name != "__pycache__" and any(f.endswith(".py") for _d, _s, fs in os.walk(path)
                                             for f in fs):
                problems.append(f"{name}/: holds Python, and a job's modules sit in its "
                                "folder's top level")
            continue
        if not name.endswith(".py") or name == CONFTEST:
            continue
        if os.path.islink(path):
            problems.append(f"{name}: is a symbolic link; a job's file is a regular file")
            continue
        size = os.path.getsize(path)
        if size > MAX_FILE_BYTES:
            problems.append(f"{name}: is {size} bytes, more than the {MAX_FILE_BYTES} a job's "
                            "file may be")
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except UnicodeDecodeError as exc:
            problems.append(f"{name}: is not UTF-8 ({exc.reason} at byte {exc.start})")
            continue
        stem = name[:-3]
        if name.startswith(TEST_PREFIX):
            tests[name] = text
        elif not stem.isidentifier() or stem in SAFE_STDLIB or stem in (PYTEST, "modules"):
            problems.append(f"{name}: a job's module is named by an identifier that shadows "
                            f"nothing it may import, not {stem!r}")
        else:
            job[stem] = text
    if problems:
        raise SourceError(folder, problems)
    return Sources(folder=folder, job=job, tests=tests)


# ── the tests, as collected from their source ───────────────────────────────────────────────

@dataclass(frozen=True)
class TestSpec:
    """One test: its file, its name, its line and the examples it `@covers`."""

    __test__ = False                        # pytest: not a test class

    file: str
    name: str
    line: int
    covers: tuple
    node: object = field(compare=False, repr=False)

    @property
    def id(self) -> str:
        return f"{self.file}::{self.name}"


def covers_of(node) -> tuple:
    """The examples *node*'s `@covers(...)` decorators name, as `(names, problems)`; a name
    not written as a string literal is a problem (the gate reads names from the source)."""
    names, problems = [], []
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        f = dec.func
        called = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) \
            else None
        if called != "covers":
            continue
        for arg in dec.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.strip():
                names.append(arg.value)
            else:
                problems.append(f"line {dec.lineno}: @covers names an example as a string "
                                f"literal, not {ast.unparse(arg)}")
    return tuple(names), problems


def collect(tree, file: str):
    """`(tests, problems)`: the module-level `test*` functions of *tree* in line order (a
    name defined twice keeps the last definition, as Python does, at its first line), and
    each `Test*` class, `async` test or malformed `@covers` refused by name."""
    tests, problems, seen = [], [], {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            problems.append(f"{file}::{node.name} (line {node.lineno}): a test class; the "
                            "runner runs module-level test functions, so write each as one")
        elif isinstance(node, ast.AsyncFunctionDef) and node.name.startswith(
                TEST_FUNCTION_PREFIX):
            problems.append(f"{file}::{node.name} (line {node.lineno}): an async test; a "
                            "job's tests are plain functions")
        elif isinstance(node, ast.FunctionDef) and node.name.startswith(TEST_FUNCTION_PREFIX):
            names, bad = covers_of(node)
            problems.extend(f"{file}::{node.name}: {p}" for p in bad)
            spec = TestSpec(file, node.name, node.lineno, names, node)
            if node.name in seen:
                tests[seen[node.name]] = TestSpec(file, node.name, tests[seen[node.name]].line,
                                                  names, node)
            else:
                seen[node.name] = len(tests)
                tests.append(spec)
    return tests, problems


# ── the assertion rewrite ────────────────────────────────────────────────────────────────────

def _short(value) -> str:
    try:
        text = repr(value)
    except Exception as exc:                # a repr that raises still names the value's type
        text = f"<{type(value).__name__}, whose repr raised {type(exc).__name__}>"
    return text if len(text) <= REPR_MAX else text[:REPR_MAX - 3] + "..."


def assert_compare(source, left, right, op, message) -> str:
    """A failed comparison's words: `assert <source>: left <l>, right <r> (<op>)`."""
    text = f"assert {source}: left {_short(left)}, right {_short(right)} ({op})"
    return text if message is None else f"{text}; {message}"


def assert_value(source, value, message) -> str:
    """A failed bare assertion's words: `assert <source>: <value>`."""
    text = f"assert {source}: {_short(value)}"
    return text if message is None else f"{text}; {message}"


#: The names the rewritten asserts call, put in each test module's namespace.
_HELPERS = {"_nmas_assert_compare": assert_compare, "_nmas_assert_value": assert_value}


class _Rewrite(ast.NodeTransformer):
    def __init__(self, source: str):
        self.source, self.count = source, 0

    def _tmp(self) -> str:
        self.count += 1
        return f"_nmas_operand_{self.count}"

    @staticmethod
    def _fail(helper: str, args, message):
        msg = ast.Constant(None) if message is None else _copy(message)
        call = ast.Call(func=ast.Name("AssertionError", ast.Load()),
                        args=[ast.Call(func=ast.Name(helper, ast.Load()), args=[*args, msg],
                                       keywords=[])], keywords=[])
        return ast.Raise(exc=call, cause=None)

    def visit_Assert(self, node):
        source = ast.get_source_segment(self.source, node.test) or ast.unparse(node.test)
        text = ast.Constant(" ".join(source.split()))
        out, test = [], node.test
        if isinstance(test, ast.Compare):
            left = self._tmp()
            out.append(ast.Assign(targets=[ast.Name(left, ast.Store())], value=test.left))
            for op, comparator in zip(test.ops, test.comparators):
                right = self._tmp()
                out.append(ast.Assign(targets=[ast.Name(right, ast.Store())], value=comparator))
                holds = ast.Compare(left=ast.Name(left, ast.Load()), ops=[op],
                                    comparators=[ast.Name(right, ast.Load())])
                fail = self._fail("_nmas_assert_compare",
                                  [text, ast.Name(left, ast.Load()), ast.Name(right, ast.Load()),
                                   ast.Constant(_SYMBOLS[type(op)])], node.msg)
                out.append(ast.If(test=ast.UnaryOp(ast.Not(), holds), body=[fail], orelse=[]))
                left = right
        else:
            value = self._tmp()
            out.append(ast.Assign(targets=[ast.Name(value, ast.Store())], value=test))
            fail = self._fail("_nmas_assert_value", [text, ast.Name(value, ast.Load())],
                              node.msg)
            out.append(ast.If(test=ast.UnaryOp(ast.Not(), ast.Name(value, ast.Load())),
                              body=[fail], orelse=[]))
        for stmt in out:
            ast.copy_location(stmt, node)
        return out


def _copy(node):
    import copy
    return copy.deepcopy(node)


def rewrite_asserts(tree, source: str):
    """*tree* (a test module's) with every `assert` rewritten to name its operands (see the
    module's docstring); the tree is changed in place and returned."""
    tree = _Rewrite(source).visit(tree)
    return ast.fix_missing_locations(tree)


# ── a prepared folder ────────────────────────────────────────────────────────────────────────

@dataclass
class Prepared:
    """A folder parsed and compiled once: `trees` and `job_codes` for the job's modules,
    `test_codes` (asserts rewritten) and `tests` (`TestSpec`s) for its test files, and
    `problems` (a file that does not parse, a refused test shape)."""

    sources: Sources
    trees: dict
    job_codes: dict
    test_codes: dict
    tests: list
    problems: list


def prepare(sources: Sources) -> Prepared:
    trees, job_codes, test_codes, tests, problems = {}, {}, {}, [], []
    for module, text in sources.job.items():
        name = sources.job_file(module)
        try:
            tree = ast.parse(text, filename=name)
            trees[module] = tree
            job_codes[module] = compile(tree, name, "exec")
        except (SyntaxError, ValueError) as exc:
            problems.append(f"{name}: does not parse ({exc})")
    for name, text in sources.tests.items():
        try:
            tree = ast.parse(text, filename=name)
        except (SyntaxError, ValueError) as exc:
            problems.append(f"{name}: does not parse ({exc})")
            continue
        found, bad = collect(tree, name)
        tests.extend(found)
        problems.extend(bad)
        test_codes[name] = compile(rewrite_asserts(tree, text), name, "exec")
    return Prepared(sources, trees, job_codes, test_codes, tests, problems)


# ── a run ────────────────────────────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    """One test's outcome: `passed`, `failed` (its assertion or its code raised), `error`
    (its fixtures could not be given, or its module would not import), `stopped` (the run's
    bound fired in it) or `not run` (the run stopped before it, or stopped at its first
    failure); its words, and the seconds it took."""

    __test__ = False                        # pytest: not a test class

    id: str
    outcome: str
    message: str = ""
    seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return self.outcome == "passed"


@dataclass
class RunResult:
    """A run: each test's result in order, the whole run's seconds, the bound it ran under,
    and `stopped` (the bound's words) when it fired."""

    tests: list
    seconds: float
    bound: float
    stopped: Optional[str] = None
    problems: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (not self.stopped and not self.problems and bool(self.tests)
                and all(t.passed for t in self.tests))

    def outcomes(self) -> dict:
        """`{test id: passed}`, the comparison T24 makes with pytest's."""
        return {t.id: t.passed for t in self.tests}

    def failures(self) -> list:
        return [t for t in self.tests if not t.passed]


def _code_objects(codes) -> list:
    out, todo = [], list(codes)
    while todo:
        code = todo.pop()
        out.append(code)
        todo.extend(c for c in code.co_consts if isinstance(c, types.CodeType))
    return out


class _Watch:
    """Watches *codes* through sys.monitoring until the deadline (see the module's
    docstring)."""

    def __init__(self, codes, bound: float):
        self.codes, self.bound = _code_objects(codes), bound
        self.tool = None

    def _tick(self, *_args):
        now = time.perf_counter()
        if now > self.deadline:
            raise BoundFired(self.bound, now - self.started)

    def __enter__(self):
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            raise RunnerError(f"the runner bounds a job's code through sys.monitoring, Python "
                              f"3.12 or later; this interpreter is {sys.version.split()[0]}")
        _LOCK.acquire()
        self.started = time.perf_counter()
        self.deadline = self.started + self.bound
        try:
            for tool in TOOL_IDS:
                if monitoring.get_tool(tool) is None:
                    monitoring.use_tool_id(tool, "mercury-job-runner")
                    self.tool = tool
                    break
            else:
                raise RunnerError(f"sys.monitoring's ids {TOOL_IDS} are all in use, by "
                                  f"{[monitoring.get_tool(t) for t in TOOL_IDS]}")
            events = monitoring.events
            monitoring.register_callback(self.tool, events.LINE, self._tick)
            monitoring.register_callback(self.tool, events.JUMP, self._tick)
            for code in self.codes:
                monitoring.set_local_events(self.tool, code, events.LINE | events.JUMP)
        except BaseException:
            self._release()
            raise
        return self

    def _release(self):
        monitoring = sys.monitoring
        try:
            if self.tool is not None:
                for code in self.codes:
                    monitoring.set_local_events(self.tool, code, 0)
                monitoring.register_callback(self.tool, monitoring.events.LINE, None)
                monitoring.register_callback(self.tool, monitoring.events.JUMP, None)
                monitoring.free_tool_id(self.tool)
        finally:
            self.tool = None
            _LOCK.release()

    def __exit__(self, *_exc):
        self._release()
        return False


def _pytest_shim():
    from modules.jobs.authoring import raises

    shim = types.ModuleType(PYTEST, "Mercury's runner's pytest: raises() alone")
    shim.raises = raises

    def missing(name):
        raise AttributeError(f"the runner's pytest offers raises() alone, not pytest.{name}: "
                             "a job's tests use plain functions, fixtures by name, and "
                             "pytest.raises or refused()")
    shim.__getattr__ = missing
    return shim


class _Imports:
    """The folder's imports for one run: its own modules (from *codes*), pytest's shim, and
    the allowed rest through Python's own import."""

    def __init__(self, codes: dict, builtins_: dict):
        self.codes, self.builtins = codes, builtins_
        self.modules, self.shim = {}, None

    def module(self, name: str):
        if name not in self.modules:
            mod = types.ModuleType(name)
            mod.__dict__["__builtins__"] = self.builtins
            mod.__dict__["__file__"] = f"{name}.py"
            self.modules[name] = mod
            try:
                exec(self.codes[name], mod.__dict__)    # noqa: S102 - the folder's own code
            except BaseException:
                del self.modules[name]          # as Python's import: no half-run module kept
                raise
        return self.modules[name]

    def __call__(self, name, globals=None, locals=None, fromlist=(), level=0):
        if level:
            raise ImportError(f"a relative import (from {'.' * level}{name} ...): the "
                              "folder's modules are imported by name, as `import job`")
        if name in self.codes:
            return self.module(name)
        if name == PYTEST:
            self.shim = self.shim or _pytest_shim()
            return self.shim
        top = name.partition(".")[0]
        if top in SAFE_STDLIB or name in SDK_MODULES:
            return builtins.__import__(name, globals, locals, fromlist, level)
        raise ImportError(f"{name!r} is not a module a job's folder may import: its own "
                          f"modules, {', '.join(SDK_MODULES)}, pytest (raises) and the "
                          f"standard library's {', '.join(sorted(SAFE_STDLIB))}")


def _where(tb, files) -> str:
    """`file:line` of the deepest frame of *tb* in the folder's own files."""
    found = ""
    while tb is not None:
        name = tb.tb_frame.f_code.co_filename
        if name in files:
            found = f"{name}:{tb.tb_lineno}"
        tb = tb.tb_next
    return found


def run(prepared: Prepared, *, job_codes: dict = None, bound: float = FIRST_RUN_SECONDS,
        fail_fast: bool = False) -> RunResult:
    """Run *prepared*'s tests once, in this process, against its job modules (or *job_codes*,
    a mutant's), within *bound* seconds; with *fail_fast*, the first test that does not pass
    ends the run (the mutation step's: one failure kills a mutant)."""
    from modules.jobs.testing import fixture_for

    codes = dict(prepared.job_codes if job_codes is None else job_codes)
    files = set(prepared.sources.job_file(m) for m in codes) | set(prepared.test_codes)
    allowed = {k: v for k, v in vars(builtins).items() if k not in FORBIDDEN_BUILTINS}
    imports = _Imports(codes, allowed)
    allowed["__import__"] = imports
    results, stopped = [], None
    by_file = {}
    for spec in prepared.tests:
        by_file.setdefault(spec.file, []).append(spec)
    started = time.perf_counter()
    with _Watch(list(codes.values()) + list(prepared.test_codes.values()), bound):
        for file, code in prepared.test_codes.items():
            specs = by_file.get(file, [])
            if stopped or (fail_fast and any(not r.passed for r in results)):
                results.extend(TestResult(s.id, "not run") for s in specs)
                continue
            namespace = {"__builtins__": allowed, "__name__": file[:-3], "__file__": file,
                         **_HELPERS}
            try:
                exec(code, namespace)                   # noqa: S102 - the folder's tests
            except BoundFired as exc:
                stopped = str(exc)
                results.extend(TestResult(s.id, "stopped" if i == 0 else "not run",
                                          f"importing {file}: {exc}")
                               for i, s in enumerate(specs))
                continue
            except Exception as exc:
                where = _where(exc.__traceback__, files)
                results.extend(TestResult(s.id, "error", f"{file} would not import: "
                                          f"{type(exc).__name__}: {exc}"
                                          + (f" (at {where})" if where else ""))
                               for s in specs)
                continue
            for spec in specs:
                if stopped or (fail_fast and any(not r.passed for r in results)):
                    results.append(TestResult(spec.id, "not run"))
                    continue
                results.append(_one(spec, namespace, imports, files, fixture_for))
                if results[-1].outcome == "stopped":
                    stopped = results[-1].message
    return RunResult(results, time.perf_counter() - started, bound, stopped,
                     list(prepared.problems))


def _one(spec, namespace, imports, files, fixture_for) -> TestResult:
    import inspect

    began = time.perf_counter()
    test = namespace.get(spec.name)
    if not callable(test):
        return TestResult(spec.id, "error", f"{spec.name} is not a function once its module "
                                            "ran")
    try:
        params = [p.name for p in inspect.signature(test).parameters.values()
                  if p.default is inspect.Parameter.empty
                  and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        # Every module of the folder, imported if the test's own module did not: the job
        # class is found among them all, as the fixed conftest.py finds it under pytest.
        own = [imports.module(name) for name in imports.codes] if params else []
        given = {name: fixture_for(name, own) for name in params}
    except BoundFired as exc:
        return TestResult(spec.id, "stopped", str(exc), time.perf_counter() - began)
    except Exception as exc:
        return TestResult(spec.id, "error", f"its fixtures: {type(exc).__name__}: {exc}",
                          time.perf_counter() - began)
    try:
        test(**given)
    except BoundFired as exc:
        return TestResult(spec.id, "stopped", str(exc), time.perf_counter() - began)
    except AssertionError as exc:
        where = _where(exc.__traceback__, files)
        return TestResult(spec.id, "failed", str(exc) + (f" (at {where})" if where else ""),
                          time.perf_counter() - began)
    except (Exception, SystemExit) as exc:
        where = _where(exc.__traceback__, files)
        return TestResult(spec.id, "failed", f"{type(exc).__name__}: {exc}"
                          + (f" (at {where})" if where else ""), time.perf_counter() - began)
    return TestResult(spec.id, "passed", "", time.perf_counter() - began)


def run_folder(folder, *, bound: float = FIRST_RUN_SECONDS) -> RunResult:
    """Load, prepare and run *folder* once (the convenience `job check` and the tests use)."""
    return run(prepare(load_sources(folder)), bound=bound)
