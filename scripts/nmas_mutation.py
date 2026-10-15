"""The nightly mutation run's logic (docs/TESTING.md, "Mutation testing"; the workflow is
.github/workflows/mutation-nightly.yml, the CLI scripts/nmas-mutation).

Coverage says a test ran a line; mutation testing says whether a test would notice the line being
wrong. Each night this mutates ONLY the automation functions changed since the commit the last
night covered, and the functions the record keeps (one unfinished, or one with an open
survivor), at most a cap of them, the oldest first; runs against each mutant the tests measured
to execute its function (the tests that import its module where nothing has measured it yet:
"The tests that reach a function"), and reports the
survivors that are not in the hand-kept list of equivalent mutants
(tests/mutation_equivalent.py). A canary (tests/mutation_canary.py) runs first and must be
killed, or no result stands. It never runs on the NMAS host, the gate or a push.
"""
import glob
import hashlib
import importlib.util
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pydefs = _load("pydefs", os.path.join(ROOT, "scripts", "pydefs.py"))

#: The canary: every one of these functions' mutants must be KILLED each night, one reached in
#: the test's process and one only through a child process (tests/mutation_canary.py).
CANARY_FILE = "tests/mutation_canary.py"
CANARY_IN_PROCESS = (CANARY_FILE, "in_process")
CANARY_IN_CHILD = (CANARY_FILE, "in_child")
CANARY_TESTS = "tests/test_mutation_canary.py"

#: A mutant no test failed on. "no tests" is mutmut's name for one no test even reached: it
#: survives just the same, and is never left to read as anything else.
SURVIVING = ("survived", "no tests")


# ── What changed ──────────────────────────────────────────────────────────────────────────────

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.M)


def changed_lines(diff: str) -> dict:
    """`{path: {line, ...}}` of the lines a `git diff -U0` adds or changes, by the new file's
    numbering (a pure deletion marks the line it happened before, so the function holding it
    still counts as changed)."""
    out, path = {}, None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
            continue
        m = _HUNK.match(line)
        if m and path:
            start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            out.setdefault(path, set()).update(range(start, start + max(count, 1)))
    return out


def changed_functions(lines_by_path: dict, read, classify) -> list:
    """`[(path, qualname)]` of the counted automation functions whose definition holds a changed
    line. *read(path)* returns a file's source (None when it is gone); *classify(path)* is the
    coverage tool's scope (tests/coverage_scope.py): only `automation` is mutated."""
    out = []
    for path, lines in sorted(lines_by_path.items()):
        if not path.endswith(".py"):
            continue
        placed = classify(path)
        if not placed or placed[0] != "automation":
            continue
        source = read(path)
        if source is None:
            continue
        for d in pydefs.definitions(source):
            if d.counted and lines & set(range(d.lineno, d.end_lineno + 1)):
                out.append((path, d.qualname))
    return out


def function_hash(source, qualname: str) -> str:
    """A hash of the function's own text (its lines, its nested functions within), or "" when
    *source* holds no such counted function. mutmut numbers a function's mutants from its text
    alone (mutmut pinned), so an unchanged hash means the same mutants, numbered the same, and
    the results the record keeps for them still stand."""
    if not source:
        return ""
    lines = source.splitlines()
    for d in pydefs.definitions(source):
        if d.qualname == qualname and d.counted:
            text = "\n".join(lines[d.lineno - 1:d.end_lineno])
            return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ""


def failing_tests(text: str) -> list:
    """The test ids a pytest run's short summary names as FAILED or ERROR, in its order, each
    once (the reason after " - " left off)."""
    out = []
    for raw in re.split(r"[\r\n]+", _ANSI.sub("", text or "")):
        m = re.match(r"^(?:FAILED|ERROR) (.+?)(?: - .*)?$", raw.strip())
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def with_deselected(cfg: str, ids: list) -> str:
    """mutmut's setup.cfg with `--deselect <id>` for each of *ids* among its pytest arguments
    (one argument a line, as mutmut reads them)."""
    head = "pytest_add_cli_args =\n"
    if head not in cfg:
        raise ValueError("no pytest_add_cli_args in mutmut's setup.cfg")
    added = "".join(f"    --deselect\n    {i}\n" for i in ids)
    return cfg.replace(head, head + added, 1)


#: mutmut 3.8's own pragma: on a `def` or `class` header line it skips the whole node, which is
#: then written into mutmut's copy as it is, with no trampoline (mutmut/mutation/pragma_handling.py).
FENCE = "# pragma: no mutate block"


def _header_lines(source: str) -> dict:
    """`{def or class line: the line its header's colon ends on}` for every function and class,
    by the source's tokens (a signature can span lines)."""
    import io
    import tokenize

    out, start, depth = {}, None, 0
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.NAME and tok.string in ("def", "class") and start is None:
            start, depth = tok.start[0], 0
        elif start is not None and tok.type == tokenize.OP:
            if tok.string in "([{":
                depth += 1
            elif tok.string in ")]}":
                depth -= 1
            elif tok.string == ":" and depth == 0:
                out[start] = tok.start[0]
                start = None
    return out


def fence(source: str, planned: set) -> str:
    """*source* with every function and class it holds fenced off from mutmut (`FENCE` appended
    to its header line) except the *planned* qualnames and the classes that hold one, whose other
    methods are fenced in turn. mutmut mutates every function of a file it is given: one changed
    line in modules/pipeline.py planned every function of it, a copy of tens of megabytes that
    every test's process compiled, a clean run of 2,315 s for 407 tests, and a source scan of an
    unplanned function failing on mutmut's rewriting of it (the second GitHub night, 2026-10-14).
    Only comments are added, so every line keeps its number."""
    import ast

    headers = _header_lines(source)
    lines = source.splitlines(keepends=True)
    marks = set()

    def visit(body, prefix):
        for node in body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            q = prefix + node.name
            if q in planned:
                continue
            if isinstance(node, ast.ClassDef) and any(p.startswith(q + ".") for p in planned):
                visit(node.body, q + ".")
                continue
            line = headers.get(node.lineno)
            first = node.body[0].lineno
            if line is not None and line < first:          # a one-line body is left as it is
                marks.add(line)

    lines_before = len(lines)
    visit(ast.parse(source).body, "")
    for line in marks:
        text = lines[line - 1]
        end = text[len(text.rstrip("\r\n")):]
        lines[line - 1] = text.rstrip("\r\n") + "  " + FENCE + end
    assert len(lines) == lines_before
    return "".join(lines)


def mangled(path: str, qualname: str) -> str:
    """mutmut 3's name for a function: `module.x_func`, or for a method `module.xǁClassǁmethod`
    (its statistics key, and its mutants' names less `__mutmut_<n>`)."""
    module = path[:-3].replace("/", ".")
    if "." in qualname:
        cls, func = qualname.rsplit(".", 1)
        return f"{module}.xǁ{cls.replace('.', 'ǁ')}ǁ{func}"
    return f"{module}.x_{qualname}"


def mutant_pattern(path: str, qualname: str) -> str:
    """mutmut 3's name pattern for one function's mutants: `module.x_func__mutmut_*`, or for a
    method `module.xǁClassǁmethod__mutmut_*`."""
    return mangled(path, qualname) + "__mutmut_*"


def function_of(mutant: str) -> str:
    """The `module.function` (or `module.Class.method`) a mutmut name belongs to."""
    base = mutant.rsplit("__mutmut_", 1)[0]
    module, _, name = base.rpartition(".")
    if name.startswith("xǁ"):
        parts = name[2:].split("ǁ")
        return f"{module}.{'.'.join(parts)}"
    return f"{module}.{name[2:] if name.startswith('x_') else name}"


def dotted(planned_function) -> str:
    """`(path, qualname)` as mutmut's `module.function` (the form `function_of` returns)."""
    path, qualname = planned_function
    return path[:-3].replace("/", ".") + "." + qualname


def key(planned_function) -> str:
    """The record's key for a function: `path::qualname`."""
    return f"{planned_function[0]}::{planned_function[1]}"


def imported_modules(source: str) -> set:
    """Every module a source's import statements name, parsed (never a text search, which
    matched an import written inside a test's string data, 2026-10-14): `import a.b` gives
    `a.b`; `from a import b` gives `a` and `a.b` (b may be a module)."""
    import ast
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.add(node.module)
            out.update(f"{node.module}.{alias.name}" for alias in node.names)
    return out


def tests_for(paths: list, test_sources: dict) -> list:
    """The test files that import any of *paths*' modules (by its dotted name, or `from package
    import module`, at any depth in the file): the tests a night runs against those mutants."""
    wanted = {path[:-3].replace("/", ".") for path in paths}
    return sorted(f for f, text in test_sources.items() if imported_modules(text) & wanted)


# ── The tests that reach a function: measured (C796, C834; the operator, 2026-10-15) ─────────
#
# "Test selection by MEASURED reach: the coverage nightly's per-test contexts say which tests
# execute each function, and a mutant runs only those." Three measurements, none an import:
# (1) the night's TESTS: for a function whose text is unchanged since the coverage nightly's
# commit, the tests its per-test contexts saw execute it (`load_reach`, `choose_tests`); for
# one changed since, or new, the test files importing its module, as before, until a coverage
# night has measured it; (2) per MUTANT, mutmut's own statistics run, which records the tests
# that call each function in the test's process; (3) a test's CHILD processes, which neither
# sees (the contexts record nothing a child runs: measured 2026-10-15 on the canary with CI's
# coverage command), measured each night by running the tests that start a child of ours once,
# with coverage in their children (`child_rc`, `child_reach`): a test joins only the functions
# its children were measured to run, and one whose children could not all be measured joins
# every function, as before.

def load_tier_records(folder: str) -> dict:
    """`{test node id: {"tier", "children"}}` from the tier records tests/conftest.py writes
    (`NMAS_TEST_TIERS`, one JSON line per test); `children` is None in a record that predates
    the count (the coverage nightly's before 2026-10-15)."""
    out = {}
    for path in sorted(glob.glob(os.path.join(folder, "*.jsonl"))):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rec = json.loads(line)
                    out[rec["test"]] = {"tier": rec["tier"], "children": rec.get("children")}
    return out


def child_starting(records: dict) -> list:
    """The tests that started a process running this checkout's code, by their tier records:
    a counted child (`children` > 0); in a record without the count, any test not `unit` (its
    tier then is the only word: `spawns`, or `browser`, which may have)."""
    return sorted(t for t, r in records.items()
                  if (r.get("children") or 0) > 0
                  or (r.get("children") is None and r.get("tier") != "unit"))


def add_tests(stats: dict, functions: list, tests: list) -> int:
    """Add *tests* to each of *functions*' (mangled names) tests in mutmut's statistics
    (`mutants/mutmut-stats.json`, as loaded): `tests_by_mangled_function_name`. Returns how many
    associations were new."""
    return add_tests_by(stats, {f: tests for f in functions})


def add_tests_by(stats: dict, tests_by_function: dict) -> int:
    """Add each function's own tests (`{mangled name: [test]}`) to mutmut's statistics; returns
    how many associations were new."""
    by = stats.setdefault("tests_by_mangled_function_name", {})
    added = 0
    for f, tests in tests_by_function.items():
        have = set(by.get(f, []))
        new = [t for t in tests if t not in have]
        by[f] = sorted(have | set(new))
        added += len(new)
    return added


def function_level(nodeid: str) -> str:
    """A test's id without its parameters (`tests/a.py::T::test_x[1-2]` → `tests/a.py::T::test_x`):
    the night selects the test function, so a parameter id that moved since the coverage night
    measured it still selects, and no id carries a character mutmut's configuration file reads
    as its own (`%`)."""
    return nodeid.split("[", 1)[0]


def load_reach(folder: str):
    """The coverage nightly's drill-down (its `coverage-drilldown` artifact, unpacked in
    *folder*): `{"functions": {path::qualname: [test]}, "tiers": {test: record}}`, each
    function's tests those its per-test contexts saw execute a line of its body (in the test's
    own process: scripts/nmas_coverage.py, `module_report`); None when there is no drill-down."""
    path = os.path.join(folder or "", "coverage.json")
    if not folder or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        report = json.load(fh)
    functions = {}
    for mpath, mod in (report.get("modules") or {}).items():
        for f in mod.get("function_list") or []:
            functions[f"{mpath}::{f['name']}"] = sorted(set(f.get("unit_tests") or [])
                                                        | set(f.get("other_tests") or []))
    return {"functions": functions, "tiers": load_tier_records(os.path.join(folder, "tiers"))}


def reach_fresh(planned: list, hashes: dict, reach, reach_commit: str, head: str,
                root: str = ROOT) -> dict:
    """Which planned functions the drill-down measured as they are tonight: `{"fresh": [key],
    "stale": {key: why}, "changed_tests": [test file], "unusable": why or ""}`. A function is
    fresh when the drill-down names it and its text at the drill-down's commit is its text at
    *head* (`function_hash`); the test files changed since that commit are named, so their new
    tests are run whole."""
    out = {"fresh": [], "stale": {}, "changed_tests": [], "unusable": ""}
    if reach is None:
        out["unusable"] = "no coverage drill-down was found"
    elif not reach_commit:
        out["unusable"] = "the drill-down's commit is not known"
    elif not reach["tiers"]:
        out["unusable"] = ("the drill-down holds no test tiers, so the tests that start a child "
                           "cannot be found in it")
    else:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q",
                            f"{reach_commit}^{{commit}}"], capture_output=True, text=True)
        if r.returncode != 0:
            out["unusable"] = f"the drill-down's commit {reach_commit[:9]} is not in this history"
    if out["unusable"]:
        out["stale"] = {key(f): out["unusable"] for f in planned}
        return out
    out["changed_tests"] = sorted(git("diff", "--name-only", f"{reach_commit}..{head}", "--",
                                      "tests", root=root).split())
    for f in planned:
        k = key(f)
        r = subprocess.run(["git", "-C", root, "show", f"{reach_commit}:{f[0]}"],
                           capture_output=True, text=True)
        then = function_hash(r.stdout if r.returncode == 0 else None, f[1])
        if k not in reach["functions"]:
            out["stale"][k] = f"not in the drill-down of {reach_commit[:9]} (new since)"
        elif not then or then != hashes.get(k):
            out["stale"][k] = f"its text changed since {reach_commit[:9]}"
        else:
            out["fresh"].append(k)
    return out


def choose_tests(planned: list, test_sources: dict, reach=None, fresh=(),
                 changed_tests=()) -> dict:
    """The night's tests, each function's by what is measured of it: for a *fresh* one (its text
    unchanged since the drill-down), the tests the drill-down saw execute it, the tests of its
    module's importing files that start a child (their children are measured tonight), and its
    importing files changed since the drill-down, whole (their tests are newer than it); for any
    other, its module's importing test files whole, as before. `{"tests": files then ids,
    "how": {key: "measured" | "by import"}}`; an id inside a file run whole is dropped."""
    files, ids, how = set(), set(), {}
    starters = set(child_starting(reach["tiers"])) if reach else set()
    for f in planned:
        k = key(tuple(f))
        importing = tests_for([f[0]], test_sources)
        if reach is not None and k in fresh:
            how[k] = "measured"
            ids.update(function_level(t) for t in reach["functions"].get(k, []))
            ids.update(function_level(t) for t in starters if t.split("::")[0] in importing)
            files.update(t for t in importing if t in set(changed_tests))
        else:
            how[k] = "by import"
            files.update(importing)
    ids = {i for i in ids if i.split("::")[0] not in files}
    return {"tests": sorted(files) + sorted(ids), "how": how}


def valid_ids(ids: list, collected: set) -> tuple:
    """`(kept, not found)`: each selected function-level id that names a test collected at head
    (exactly, or with parameters), so a test the drill-down measured and head no longer has
    never fails the night's collection (pytest refuses a run naming one)."""
    bases = {function_level(c) for c in collected}
    kept, gone = [], []
    for i in ids:
        (kept if i in bases else gone).append(i)
    return kept, gone


#: What a measured child writes its coverage under: the test that started it, from the
#: environment the spawn guard gives every child (tests/network_guard.py, NODE_ENV).
CHILD_CONTEXT_ENV = "NMAS_TEST_NODEID"


def child_rc(paths: list, data_dir: str) -> str:
    """coverage.py's configuration for the children of the night's child-starting tests
    (`COVERAGE_PROCESS_START`, set on each child by the spawn guard when
    `NMAS_CHILD_COVERAGE` names this file): each child writes its own data file in *data_dir*,
    under the context of the test that started it, measuring *paths* (the planned modules and
    the canary, wherever the child runs them from) and the spawn guard's sitecustomize, which
    every Python child runs: a child that wrote a context was measured, even when it ran none of
    the planned code."""
    include = [f"*/{p}" for p in paths] + ["*/sitecustomize.py"]
    return ("[run]\n"
            f"data_file = {os.path.join(data_dir, '.coverage')}\n"
            "parallel = True\n"
            f"context = ${{{CHILD_CONTEXT_ENV}}}\n"
            "sigterm = True\n"
            "patch = _exit\n"
            "disable_warnings = no-data-collected, module-not-measured, module-not-imported, "
            "module-not-python, couldnt-parse, no-ctracer\n"
            "include =\n" + "".join(f"    {i}\n" for i in include))


def child_reach(functions: dict, measured: dict, records: dict, population: list,
                failed=()) -> dict:
    """Which functions each child-starting test's children ran, and which tests could not be
    measured. *functions*: `{mangled name: (path, {body line})}`; *measured*: `{test: {"files":
    data files with its context, "lines": {path: {line}}}}` from the measurement run;
    *records*: that run's tier records (`children`, counted by the spawn guard); *population*:
    the tests measured. A test is measured when that run recorded it, it passed, and at least as
    many of its children wrote data as it started; otherwise it is `unmeasured` and joins every
    function, as before (never fewer tests than could kill a mutant). Returns `{"by_function":
    {mangled: [test]}, "reached": {test: [mangled]}, "unmeasured": [test]}`."""
    by = {f: [] for f in functions}
    reached, unmeasured = {}, []
    for t in sorted(population):
        rec, got = records.get(t), measured.get(t) or {}
        if rec is None or t in failed or got.get("files", 0) < (rec.get("children") or 0) \
                or not got.get("files"):
            unmeasured.append(t)
            continue
        lines = got.get("lines") or {}
        reached[t] = sorted(f for f, (path, body) in functions.items()
                            if lines.get(path, set()) & set(body))
        for f in reached[t]:
            by[f].append(t)
    for f in by:
        by[f] = sorted(set(by[f]) | set(unmeasured))
    return {"by_function": by, "reached": reached, "unmeasured": unmeasured}


def body_lines(source: str, qualname: str) -> tuple:
    """A counted function's body lines in *source* (pydefs: after the docstring, nested
    functions within), () when there is none."""
    for d in pydefs.definitions(source):
        if d.qualname == qualname and d.counted:
            return tuple(d.body_lines)
    return ()


def planned_path_of(measured_file: str, paths: list) -> str:
    """The planned path a measured file is (by its path's ending: a child may run the program
    from a copy of the checkout), or ""."""
    norm = measured_file.replace(os.sep, "/")
    for p in sorted(paths, key=len, reverse=True):
        if norm == p or norm.endswith("/" + p):
            return p
    return ""


def read_child_data(data_dir: str, paths: list) -> dict:
    """`{test: {"files": n, "lines": {path: {line}}}}` from the children's coverage data files
    in *data_dir* (`child_rc`): each file is one child process, its one context the test that
    started it (read by the coverage tool, scripts/nmas_coverage.py, `process_files`)."""
    coverage_tool = _load("nmas_coverage", os.path.join(ROOT, "scripts", "nmas_coverage.py"))
    out = {}
    for proc in coverage_tool.process_files(data_dir):
        for ctx in proc["contexts"]:
            rec = out.setdefault(ctx, {"files": 0, "lines": {}})
            rec["files"] += 1
            for mf, lines in proc["lines"][ctx].items():
                p = planned_path_of(mf, paths)
                if p:
                    rec["lines"].setdefault(p, set()).update(lines)
    return out


# ── What a mutant changes: logging, MESSAGE or VERDICT ───────────────────────────────────────
# The operator's rule (2026-10-14), so the night's red means something: a mutant inside a
# logging call's arguments is never run (PIT's default); a survivor is MESSAGE when it changes
# only the words of text a person reads, and VERDICT otherwise (pass or fail, a check's level,
# which device or file is blamed, whether a secret or an unsendable line is caught). Decided
# from the mutation itself, by parsing; whatever the rule cannot decide is VERDICT.

#: The loggers a module writes to by name, and their methods.
LOGGERS = ("log", "logger", "logging", "LOG", "_log")
LOG_METHODS = ("debug", "info", "warning", "warn", "error", "exception", "critical", "log")


def mutated_functions(mutated_source: str) -> dict:
    """`{name: source}` of every function in mutmut's copy of a module whose name ends
    `__mutmut_<n>` or `__mutmut_orig` (methods included, at any depth), each dedented."""
    import ast
    import textwrap
    out = {}
    lines = mutated_source.splitlines()
    for node in ast.walk(ast.parse(mutated_source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "__mutmut_" in node.name:
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            out[node.name] = textwrap.dedent("\n".join(lines[start - 1:node.end_lineno]))
    return out


def _log_lines(source: str) -> set:
    """Line indexes (0-based) of *source* inside the argument list of a logging call."""
    import ast
    out = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in LOG_METHODS and isinstance(node.func.value, ast.Name) \
                and node.func.value.id in LOGGERS:
            out.update(range(node.lineno - 1, node.end_lineno))
    return out


def _changed(orig: list, mutant: list) -> tuple:
    """`(orig line indexes changed, [(orig line, mutant line)] when one line became one)`."""
    import difflib
    changed, pairs = set(), []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=orig, b=mutant,
                                                       autojunk=False).get_opcodes():
        if op == "equal":
            continue
        changed.update(range(i1, max(i2, i1 + 1)))
        if op == "replace" and i2 - i1 == 1 and j2 - j1 == 1:
            pairs.append((orig[i1], mutant[j1]))
    return changed, pairs


def _string_spans(line: str) -> list:
    """`[(start, end, text)]` of the string literals (and f-strings' text parts) on one line."""
    import io
    import tokenize
    spans = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(line + "\n").readline):
            if tok.type == tokenize.STRING or tok.type in (
                    getattr(tokenize, "FSTRING_MIDDLE", -1),):
                spans.append((tok.start[1], tok.end[1], tok.string))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass                                     # a line of a longer statement: try harder
    if not spans:
        for m in re.finditer(r'(?<![\w])[rbfuRBFU]{0,2}("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')',
                             line):
            spans.append((m.start(), m.end(), m.group(0)))
    return spans


def compared_strings(module_source: str) -> set:
    """The string literals a module COMPARES with (`==`, `!=`, `in`, `.startswith()`,
    `.endswith()`, a dict or set of them): a message holding one of them can decide a result
    (`startswith("no golden")` in config_check), so its words are never MESSAGE."""
    import ast
    out = set()
    for node in ast.walk(ast.parse(module_source)):
        targets = []
        if isinstance(node, ast.Compare):
            targets = [node.left, *node.comparators]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("startswith", "endswith", "find", "index", "count"):
            targets = list(node.args)
        for t in targets:
            for sub in ast.walk(t):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub.value:
                    out.add(sub.value)
    return out


def _body_start(lines: list) -> int:
    """The index of the first line after a function's `def ...:` line(s)."""
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("def ", "async def ")):
            for j in range(i, len(lines)):
                if lines[j].rstrip().endswith(":"):
                    return j + 1
    return 0


def classify(orig: str, mutant: str, compared: set = frozenset()) -> str:
    """"logging", "message" or "verdict" for one mutant (*orig* and *mutant*: the whole
    function's source before and after, `def` included, whose names differ and nothing else
    does; *compared*: `compared_strings` of its module)."""
    full_a, full_b = orig.splitlines(), mutant.splitlines()
    ia, ib = _body_start(full_a), _body_start(full_b)
    a, b = full_a[ia:], full_b[ib:]
    changed, pairs = _changed(a, b)
    if not changed:
        return "verdict"
    if changed <= {i - ia for i in _log_lines(orig)}:
        return "logging"
    if len(pairs) != 1 or len(changed) != 1:
        return "verdict"
    was, now = pairs[0]
    import difflib
    sm = difflib.SequenceMatcher(a=was, b=now, autojunk=False)
    edits = [(i1, i2, j1, j2) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
    spans_was, spans_now = _string_spans(was), _string_spans(now)

    def inside(spans, lo, hi):
        return any(s <= lo and hi <= e for s, e, _t in spans)

    hit = set()
    for i1, i2, j1, j2 in edits:
        if not (inside(spans_was, i1, max(i2, i1)) and inside(spans_now, j1, max(j2, j1))):
            return "verdict"
        hit.update(t for s, e, t in spans_was if s <= i1 and max(i2, i1) <= e)
    for text in hit:
        body = text.strip("rbfuRBFU").strip("'\"")
        if not re.search(r"\s", body):
            return "verdict"                      # an identifier, a status, a key, a path
        if any(_holds(body, c) for c in compared):
            return "verdict"                      # holds a string the module compares with
    return "message"


def _holds(body: str, compared: str) -> bool:
    """Whether a message *body* holds *compared* as words (three characters or more, a letter
    among them, at word boundaries): `"no golden"` in "no golden: nothing captured"; never a
    lone ":" or "/", which every sentence holds and nothing decides by."""
    if len(compared) < 3 or not re.search(r"[A-Za-z]", compared):
        return False
    return re.search(rf"(?<!\w){re.escape(compared)}(?!\w)", body) is not None


def classify_file(mutated_source: str, module_source: str) -> dict:
    """`{mutant: kind}` for every mutant in mutmut's copy of one module (*module_source*: the
    module itself, for `compared_strings`). Mutant names are mutmut's (`module.x_f__mutmut_3`
    without the module: the caller adds it)."""
    funcs = mutated_functions(mutated_source)
    compared = compared_strings(module_source)
    out = {}
    for name, src in funcs.items():
        if name.endswith("__mutmut_orig"):
            continue
        orig = funcs.get(name.rsplit("__mutmut_", 1)[0] + "__mutmut_orig")
        if orig is None:
            out[name] = "verdict"
            continue
        out[name] = classify(orig, src, compared)
    return out


# ── What survived ─────────────────────────────────────────────────────────────────────────────

_RESULT = re.compile(r"^\s*([\w.ǁ]+__mutmut_\d+): (\w[\w ]*)$")


def parse_results(text: str) -> dict:
    """`{mutant: status}` from `mutmut results --all true` (`name: killed`, `name: survived`,
    ...)."""
    out = {}
    for line in text.splitlines():
        m = _RESULT.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def diff_lines(show: str) -> tuple:
    """The (was, now) lines of a `mutmut show` diff, each stripped (the first changed pair)."""
    was = [l[1:].strip() for l in show.splitlines() if l.startswith("-") and not l.startswith("---")]
    now = [l[1:].strip() for l in show.splitlines() if l.startswith("+") and not l.startswith("+++")]
    return (was[0] if was else "", now[0] if now else "")


# ── The debt: known open VERDICT survivors (the operator, 2026-10-14) ──────────────────────────
#
# Code that was only moved (C781: the AI family's shared pieces, never tested directly) arrives
# with hundreds of survivors at once, and a night red for weeks says nothing new. Like the
# coverage ratchet's baseline, the debt is a committed list: each known open VERDICT survivor,
# by function and the two lines, with the reason it was accepted. It grows only by
# `nmas-mutation debt add` with a reason, never by a night; killing survivors shrinks it. A night
# is red on a survivor NOT on it, on the list having grown since the last night, or on a broken
# measurement; the debt it met is reported every night.

DEBT_FILE = os.path.join(ROOT, "tests", "mutation_debt.json")


def unmangle(function: str) -> tuple:
    """`(path, qualname)` of mutmut's name for a function (`mangled`'s inverse)."""
    module, _, name = function.rpartition(".")
    if name.startswith("xǁ"):
        qualname = ".".join(name[2:].split("ǁ"))
    elif name.startswith("x_"):
        qualname = name[2:]
    else:
        raise ValueError(f"{function!r} is not mutmut's name for a function")
    return module.replace(".", "/") + ".py", qualname


def load_debt(path: str = None) -> dict:
    """The debt list (`{"functions": {dotted: {path, qualname, hash, survivors}}}`, from *path*,
    by default DEBT_FILE as it is when called); empty when there is no file."""
    path = path or DEBT_FILE
    if not os.path.exists(path):
        return {"functions": {}}
    with open(path, encoding="utf-8") as fh:
        debt = json.load(fh)
    debt.setdefault("functions", {})
    return debt


#: The baseline sweep (the operator, 2026-10-14): night #4's 20 left-over functions, each at its
#: text hash, whose survivors are added to the debt list with this reason by the deliberate
#: `debt add` as the sweep finishes them, never failing a night. Only for that sweep: a function
#: whose text changes leaves it, and once its functions are finished it holds nothing.
SWEEP_FILE = os.path.join(ROOT, "tests", "mutation_sweep.json")
SWEEP_REASON = "baseline sweep of moved code"


def load_sweep(path: str = None) -> dict:
    """`{dotted: hash}` of the baseline sweep's functions; empty when there is no file."""
    path = path or SWEEP_FILE
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return {name: f["hash"] for name, f in json.load(fh).get("functions", {}).items()}


def debt_entries(debt: dict, counted: bool = False) -> int:
    """How many survivors the list holds; *counted*: only those whose growth turns a night red,
    every one but the baseline sweep's (SWEEP_REASON, the operator's approval)."""
    return sum(1 for f in debt.get("functions", {}).values() for s in f.get("survivors", [])
               if not (counted and (s.get("reason") or "").strip() == SWEEP_REASON))


def on_debt(debt: dict, function: str, was: str, now: str, function_hash_: str = "") -> bool:
    """Whether the survivor (*function*, *was*, *now*) is on the list: under the function's own
    name, or, when it moved (its text unchanged), under the name the same hash was listed by.
    Given the function's text hash, an entry counts only at that hash (the operator,
    2026-10-14): code changed after it was listed makes its survivors NEW, not known."""
    entries = []
    funcs = debt.get("functions", {})
    if function in funcs and (not function_hash_ or not funcs[function].get("hash")
                              or funcs[function]["hash"] == function_hash_):
        entries.append(funcs[function])
    if function_hash_:
        entries += [f for name, f in funcs.items()
                    if name != function and f.get("hash") == function_hash_]
    return any(s["was"].strip() == was and s["now"].strip() == now
               for f in entries for s in f.get("survivors", []))


def debt_unchanged(debt: dict, function: str, function_hash_: str) -> bool:
    """Whether *function* holds known debt at its current text (*function_hash_*): its open
    survivors are then not run again (the operator, 2026-10-14); a changed text runs them."""
    f = debt.get("functions", {}).get(function)
    return bool(f and f.get("survivors") and function_hash_ and f.get("hash") == function_hash_)


def tally_line(v: dict, known: int = None) -> str:
    """The night's headline: the known debt (*known*: the list's size, run tonight or not;
    else the debt met tonight), and the new survivors, the ones that fail it."""
    sweep = len(v.get("sweep", []))
    known = len(v.get("debt", [])) if known is None else known
    return (f"**{known} known, {len(v.get('new', []))} new**"
            + (f", {sweep} found finishing the baseline sweep (to be added to the debt list, "
               "the operator's approval)" if sweep else "") + ".")


def add_to_debt(debt: dict, survivors: list, reason: str, hash_of) -> int:
    """Add each open VERDICT survivor (`{"mutant", "function", "was", "now"}`, as a night's
    report holds them) not already listed, with *reason*, under its function's dotted name;
    *hash_of(path, qualname)* gives a function's text hash. Returns how many were added.
    Refused without a reason: the list grows only on purpose."""
    if not (reason or "").strip():
        raise ValueError("the debt list grows only with a reason (--reason)")
    added = 0
    for s in survivors:
        fn = s["function"]
        if on_debt(debt, fn, s["was"], s["now"]):
            continue
        path, qualname = unmangle(s["mutant"].rsplit("__mutmut_", 1)[0])
        entry = debt["functions"].setdefault(fn, {"path": path, "qualname": qualname,
                                                  "hash": hash_of(path, qualname),
                                                  "survivors": []})
        entry["survivors"].append({"was": s["was"], "now": s["now"], "reason": reason.strip()})
        added += 1
    for entry in debt["functions"].values():
        entry["survivors"].sort(key=lambda s: (s["was"], s["now"]))
    debt["functions"] = dict(sorted(debt["functions"].items()))
    return added


def debt_problems(debt: dict, root: str = ROOT) -> list:
    """What is wrong with a debt list: an entry for a function that no longer exists at *root*
    (the operator's rule: a deleted or renamed function's survivors leave with it), a name that
    is not its path and qualname's, and a survivor without both lines or a reason."""
    problems = []
    for name, f in debt.get("functions", {}).items():
        try:
            with open(os.path.join(root, f["path"]), encoding="utf-8") as fh:
                source = fh.read()
        except OSError:
            source = ""
        if not function_hash(source, f.get("qualname", "")):
            problems.append(f"{name}: no function {f.get('qualname')!r} in {f.get('path')}")
        elif dotted((f["path"], f["qualname"])) != name:
            problems.append(f"{name}: its path and qualname name "
                            f"{dotted((f['path'], f['qualname']))}")
        for s in f.get("survivors", []):
            if not (s.get("was") and s.get("now") and (s.get("reason") or "").strip()):
                problems.append(f"{name}: a survivor without both lines or a reason: {s}")
    return problems


def debt_lines(matched: list, debt: dict, previous: int = None, top: int = 5) -> list:
    """The summary's debt section: what the list holds, its change since the last night, the
    survivors it met tonight, and the functions holding the most."""
    now = debt_entries(debt)
    change = ("first counted tonight" if previous is None else
              "unchanged since the last night" if previous == now else
              f"{now - previous:+d} since the last night ({previous})")
    per = {}
    for name, f in debt.get("functions", {}).items():
        per[name] = len(f.get("survivors", []))
    biggest = sorted(per.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    lines = [f"Known debt: {now} open VERDICT survivor(s) in {len(per)} function(s) on the "
             f"list (tests/mutation_debt.json), {change}; {len(matched)} met tonight.", ""]
    if biggest:
        lines += ["| function | known survivors |", "|---|---|"]
        lines += [f"| `{n}` | {c} |" for n, c in biggest]
        lines += [""]
    return lines


def is_equivalent(function: str, was: str, now: str, equivalent: list) -> str:
    """The reason when (*function*, *was*, *now*) is in the hand-kept list, else ""."""
    for e in equivalent:
        if e["function"] == function and e["was"].strip() == was and e["now"].strip() == now:
            return e["why"]
    return ""


def verdict(results: dict, shows: dict, equivalent: list, kinds: dict = None,
            debt: dict = None, hash_of_function: dict = None, sweep: dict = None) -> dict:
    """Per function: mutants, killed, survived (no test failed: `SURVIVING`); the survivors
    split into known equivalents (listed apart, with their reason) and OPEN ones, each VERDICT
    or MESSAGE by *kinds* (`{mutant: kind}`, `classify_file`; a mutant it does not name is
    VERDICT). An open VERDICT survivor on the *debt* list (`on_debt`, followed through a move
    by *hash_of_function*, `{dotted: hash}`) is `debt`; only the rest (`new`) fail the night;
    MESSAGE ones are `message`. *shows*: `{mutant: mutmut show text}` for the survivors.
    *sweep*: the baseline sweep (`load_sweep`, `{dotted: hash}`): an open VERDICT survivor off
    the list in one of its functions, still at that hash, is `sweep` (found finishing #4's
    sweep, added by the deliberate `debt add`; never failing the night)."""
    per, new, message, known, owed, swept = {}, [], [], [], [], []
    debt = debt or {"functions": {}}
    hash_of_function = hash_of_function or {}
    sweep = sweep or {}
    for mutant, status in sorted(results.items()):
        fn = function_of(mutant)
        p = per.setdefault(fn, {"mutants": 0, "killed": 0, "survived": 0, "equivalent": 0,
                                "verdict": 0, "message": 0, "other": 0, "debt": 0})
        p["mutants"] += 1
        if status == "killed":
            p["killed"] += 1
        elif status in SURVIVING:
            p["survived"] += 1
            was, now = diff_lines(shows.get(mutant, ""))
            why = is_equivalent(fn, was, now, equivalent)
            entry = {"mutant": mutant, "function": fn, "was": was, "now": now, "why": why,
                     "status": status}
            if why:
                p["equivalent"] += 1
                known.append(entry)
            elif (kinds or {}).get(mutant) == "message":
                p["message"] += 1
                message.append(entry)
            elif on_debt(debt, fn, was, now, hash_of_function.get(fn, "")):
                p["debt"] += 1
                owed.append(entry)
            elif fn in sweep and sweep[fn] == hash_of_function.get(fn):
                p["sweep"] = p.get("sweep", 0) + 1
                swept.append(entry)
            else:
                p["verdict"] += 1
                new.append(entry)
        else:
            p["other"] += 1
    return {"functions": per, "new": new, "message": message, "known": known, "debt": owed,
            "sweep": swept}


def only_functions(results: dict, functions: list) -> dict:
    """*results* restricted to *functions*' mutants: `mutmut results` lists every mutant of a
    mutated FILE, the unplanned functions' as "not checked"."""
    wanted = {dotted(f) for f in functions}
    return {m: s for m, s in results.items() if function_of(m) in wanted}


def fresh_workspace(root: str = ROOT) -> bool:
    """Remove mutmut's working copy (`mutants/`, gitignored scratch) before a night, so every
    result read afterwards is TONIGHT's: a copy kept from an earlier run carries its results,
    which read as tonight's to the scope check, and could pass the canary on old kills (found
    walking two nights in one copy, 2026-10-14; GitHub's runner starts empty). True when
    there was one to remove."""
    import shutil
    path = os.path.join(root, "mutants")
    if not os.path.isdir(path):
        return False
    shutil.rmtree(path)
    return True


def canary_error(results: dict) -> str:
    """"" when every canary mutant was killed; otherwise the measurement is broken, and why."""
    canary = only_functions(results, [CANARY_IN_PROCESS, CANARY_IN_CHILD])
    if not canary:
        return "the canary made no mutant (tests/mutation_canary.py was not mutated)"
    alive = {m: s for m, s in canary.items() if s != "killed"}
    for f in (CANARY_IN_PROCESS, CANARY_IN_CHILD):
        if not only_functions(canary, [f]):
            alive[f"{dotted(f)} (no mutant made)"] = "missing"
    if alive:
        return ("MEASUREMENT BROKEN: the canary's mutants must all be killed, and "
                + ", ".join(f"{m} was {s}" for m, s in sorted(alive.items()))
                + " (tests/mutation_canary.py says what each proves)")
    return ""


def scope_error(results: dict, allowed: list) -> str:
    """"" when every mutant that RAN belongs to a planned function or the canary."""
    wanted = {dotted(f) for f in allowed}
    stray = sorted(m for m, s in results.items()
                   if s != "not checked" and function_of(m) not in wanted)
    if stray:
        return (f"SCOPE BROKEN: {len(stray)} mutant(s) of functions not planned ran, "
                f"for example {stray[0]}")
    return ""


def merge(kept: dict, tonight: dict) -> dict:
    """A function's results: those the record kept, each replaced where it ran tonight."""
    out = dict(kept)
    for m, s in tonight.items():
        if s != "not checked" or m not in out:
            out[m] = s
    return out


#: The run's exit when it finished; `timeout`'s when the budget ran out. mutmut exits 1 when its
#: own setup failed (the stats run, or the tests failing on the UNMUTATED code), and a crash is
#: anything else: either way nothing it reports can be trusted as a verdict.
FINISHED, OUT_OF_TIME = 0, 124
#: `nmas-mutation run`'s exit when the canary survived: it stopped before the night's mutants.
CANARY_BROKEN = 3


def outcome(planned: list, results: dict, mutmut_exit: int) -> dict:
    """Which planned functions are finished (`done`) and which are not (`left`), and the run's
    `error` ("" when its results stand). A function is done when it has no mutant left "not
    checked"; when the budget ran out, a function with NO result was never reached (a finished
    run gives a function that has no mutants no result either, and it is done)."""
    if mutmut_exit not in (FINISHED, OUT_OF_TIME):
        return {"done": [], "left": list(planned), "empty": [],
                "error": f"mutmut exited {mutmut_exit}, not {FINISHED} (finished) or "
                         f"{OUT_OF_TIME} (the budget ran out): its setup or clean run failed, so "
                         "no result stands"}
    seen, unchecked = set(), set()
    for m, s in results.items():
        seen.add(function_of(m))
        if s == "not checked":
            unchecked.add(function_of(m))
    done = [f for f in planned if dotted(f) not in unchecked
            and (mutmut_exit == FINISHED or dotted(f) in seen)]
    # Done with no mutant at all: nothing in it was tested tonight, which the summary says
    # rather than letting it read as passed.
    empty = [f for f in done if dotted(f) not in seen]
    return {"done": done, "left": [f for f in planned if f not in done], "empty": empty,
            "error": ""}


# ── The record a night leaves for the next ────────────────────────────────────────────────────

def next_state(head: str, planned: list, results: dict, open_mutants: list,
               hashes: dict, finished_before: dict = None, debt_count: int = None,
               deferred: dict = None, since: dict = None) -> dict:
    """What the next night starts from: this run's HEAD, and per function still unfinished or
    holding an open survivor (the debt's included, so a test that kills one is seen), its hash
    and every result so far (C769: a large function is finished across nights, never
    restarted; an open survivor is run again each night until a test kills it or a person lists
    it as equivalent). `finished`: the hash of every function finished with nothing open, this
    night's and earlier ones' still at that hash, so a function MOVED with its text unchanged
    is known as done (the operator, 2026-10-14). `debt_entries`: the debt list's size tonight,
    against which the next night sees it grow. *deferred*: the functions the night's cap left
    (`plan`), carried as they were; *since*: `{key: commit}`, when each planned function entered
    the record (the cap's order), kept on each one still unfinished. Both fields are additions:
    a record without them loads as the oldest."""
    open_by = {}
    for m in open_mutants:
        open_by.setdefault(function_of(m), []).append(m)
    functions, finished = {}, dict(finished_before or {})
    for f in planned:
        res = only_functions(results, [f])
        if any(s == "not checked" for s in res.values()) or dotted(f) in open_by:
            functions[key(f)] = {"hash": hashes.get(key(f), ""), "results": res,
                                 "open": sorted(open_by.get(dotted(f), []))}
            if (since or {}).get(key(f)):
                functions[key(f)]["since"] = since[key(f)]
            finished.pop(key(f), None)
        elif hashes.get(key(f)):
            finished[key(f)] = {"hash": hashes[key(f)]}
    for k, rec in (deferred or {}).items():
        functions.setdefault(k, rec)
        finished.pop(k, None)
    state = {"commit": head, "functions": functions, "finished": dict(sorted(finished.items()))}
    if debt_count is not None:
        state["debt_entries"] = debt_count
    return state


def renamed(names, old: tuple, new: tuple):
    """mutmut's mutant names of function *old* as function *new*'s (its text unchanged, so the
    same mutants, numbered the same: `function_hash`)."""
    a, b = mangled(*old) + "__mutmut_", mangled(*new) + "__mutmut_"
    if isinstance(names, dict):
        return {(b + m[len(a):] if m.startswith(a) else m): s for m, s in names.items()}
    return [b + m[len(a):] if m.startswith(a) else m for m in names]


#: The lines of a failed mutmut run that say why: pytest's failures and their assertion lines,
#: its short summary, mutmut's own refusal, and an exception's last line.
_CAUSE = re.compile(r"^(FAILED |ERROR |E {2,}\S|=+ short test summary info =+$|"
                    r"failed to collect stats|.*runner returned \d|nmas-test: REFUSED|"
                    r"!+ stopping after|\d+ (failed|errors?)\b.* in [\d.]+s|"
                    r"[A-Za-z_.]*(Error|Exception)(: .*)?$)")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def failure_excerpt(text: str, limit: int = 30) -> list:
    """What a failed mutmut run said about why, in its order, each line once, at most *limit*
    lines (the summary quotes them; the whole output is kept beside it): never "the log above
    says why" (the operator, 2026-10-14: the first GitHub night's summary named no cause)."""
    out = []
    for raw in re.split(r"[\r\n]+", _ANSI.sub("", text or "")):
        line = raw.rstrip()
        if line and _CAUSE.match(line) and line not in out:
            out.append(line)
    return out[:limit]


def summary(base: str, head: str, planned: list, verdict_: dict, left: list,
            budget_minutes: int, error: str = "", empty: list = (), extra: list = (),
            cause: list = (), moved: dict = None, known: int = None) -> str:
    """The job summary (Markdown). *extra*: lines said first (the canary, the scope, what the
    record carried in). *cause*: a failed run's own lines (`failure_excerpt`). *moved*:
    `{path::qualname: where it was}` for planned functions only moved, their text unchanged."""
    lines = [f"## Mutation testing: functions changed {base[:9]}..{head[:9]}", ""]
    if not planned:
        return "\n".join(lines + [tally_line({}, known), "",
                                  "Nothing to mutate: no automation function changed, and the "
                                  "record holds none unfinished (known debt at its listed text "
                                  "is not run again).", ""])
    if not error:
        lines += [tally_line(verdict_, known), ""]
    lines += list(extra)
    moved = moved or {}

    def planned_line(p, q):
        was = moved.get(key((p, q)))
        return f"- `{p}` {q}" + (f" (moved from `{was}`, its text unchanged)" if was else "")

    if moved:
        lines += [f"Moved, their text unchanged ({len(moved)} of {len(planned)}): mutated in "
                  "full, because the record keys a function by its path and name and the "
                  "tests that reach it moved with it.", ""]
    if error:
        lines += [f"**The run failed:** {error}.", ""]
        if cause:
            lines += ["What it said (its whole output is in the report's artifact):", "",
                      "```", *cause, "```", ""]
        lines += [f"Planned ({len(planned)}); the record is left as it was:", ""]
        return "\n".join(lines + [planned_line(p, q) for p, q in planned]) + "\n"
    lines += ["Logging calls' arguments are never mutated. A survivor is VERDICT when its change "
              "can decide pass or fail, a check's level, whom a result blames, or whether a "
              "secret or an unsendable line is caught; MESSAGE when it changes only the words "
              "a person reads (anything undecided is VERDICT). Score: killed over the mutants "
              "a test could kill (all, less known equivalents); VERDICT score: killed over "
              "killed and VERDICT survivors.", "",
              "| function | mutants | killed | survived: VERDICT | of which on the debt list "
              "| survived: MESSAGE | known equivalent | score | VERDICT score |",
              "|---|---|---|---|---|---|---|---|---|"]
    for fn, p in sorted(verdict_["functions"].items()):
        killable = p["mutants"] - p["equivalent"]
        score = f"{100.0 * p['killed'] / killable:.1f}%" if killable else "—"
        owed = p.get("debt", 0)
        open_verdict = p.get("verdict", p["survived"] - p["equivalent"]) + owed \
            + p.get("sweep", 0)
        at_stake = p["killed"] + open_verdict
        vscore = f"{100.0 * p['killed'] / at_stake:.1f}%" if at_stake else "—"
        lines.append(f"| `{fn}` | {p['mutants']} | {p['killed']} | {open_verdict} | {owed} "
                     f"| {p.get('message', 0)} | {p['equivalent']} | {score} | {vscore} |")

    def item(s):
        return (f"- `{s['mutant']}`" + (" (no test reached it)" if s.get("status") == "no tests"
                                        else "") + f": `{s['was']}` → `{s['now']}`")
    lines += ["", f"### New open VERDICT survivors ({len(verdict_['new'])}), not on the debt list: "
              "the night fails until each is killed by a test, listed as equivalent, or "
              "accepted onto the debt list on purpose", ""]
    lines += [item(s) for s in verdict_["new"]] \
        or ["- none: every mutant that can change a verdict was killed, is a known equivalent, "
            "or is known debt"]
    swept = verdict_.get("sweep", [])
    if swept:
        lines += ["", f"### Found finishing the baseline sweep ({len(swept)}): in night #4's "
                  "left-over functions at their text then; added to the debt list with the "
                  f"reason \"{SWEEP_REASON}\" (`nmas-mutation debt add`, the operator's approval "
                  "for this sweep only), never failing the night", ""]
        lines += [item(s) for s in swept]
    owed = verdict_.get("debt", [])
    lines += ["", f"### Known debt met tonight ({len(owed)}): open, in functions with unchecked "
              "mutants left, never failing the night (tests/mutation_debt.json)", ""]
    lines += [item(s) for s in owed] or ["- none"]
    lines += ["", f"### Open MESSAGE survivors ({len(verdict_.get('message', []))}): words only; "
              "listed and kept open, never failing the night", ""]
    lines += [item(s) for s in verdict_.get("message", [])] or ["- none"]
    lines += ["", f"### Known equivalent mutants ({len(verdict_['known'])})", ""]
    lines += [f"- `{s['mutant']}`: {s['why']}" for s in verdict_["known"]] or ["- none"]
    if empty:
        lines += ["", f"### Changed, but mutmut made no mutant of it ({len(empty)}): nothing "
                  "in it was tested tonight", ""]
        lines += [f"- `{p}` {q}" for p, q in empty]
    if left:
        lines += ["", f"### Left over ({len(left)}): the {budget_minutes}-minute budget ran out; "
                  "their results so far are kept, and the next night runs only the rest", ""]
        lines += [f"- `{p}` {q}" for p, q in left]
    return "\n".join(lines) + "\n"


def git(*args, root: str = ROOT) -> str:
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                          check=True).stdout


#: The nightly's own workflow: the commit that added it is where nights begin.
WORKFLOW_REL = ".github/workflows/mutation-nightly.yml"


def first_base(head: str, root: str = ROOT) -> str:
    """Where a night with no record starts: the commit that added the nightly workflow, so the
    first night covers everything changed since nights began; head's parent where that commit
    is not head's ancestor (a repository without the workflow, or head itself adding it)."""
    added = git("log", "--diff-filter=A", "--format=%H", head, "--", WORKFLOW_REL,
                root=root).split()
    if added and added[-1] != head:
        return added[-1]
    return git("rev-parse", f"{head}~1", root=root).strip()


def plan(state: dict, head: str, root: str = ROOT, also: list = (), debt: dict = None,
         cap: int = None) -> dict:
    """The night's plan: the base commit (the last covered, or on the first night the commit
    that added the nightly workflow, `first_base`) and the functions to mutate, each read at
    head: those the record keeps whose hash is
    unchanged (only their mutants not yet checked and their open survivors run: `names`), then
    the counted automation functions the diff touches (all their mutants). A kept function whose
    text changed is planned afresh, its old results dropped. A function MOVED, its text hash one
    the record holds under another name, is kept with those results renamed (`carried`); one
    the record finished, or the *debt* list holds, is not mutated again (`skipped_moved`).
    *also*: functions (`path::qualname`) a person names to mutate whole tonight, changed or
    not. The scope is *root*'s tests/coverage_scope.py, the coverage tool's. *cap*: at most
    that many functions tonight, the oldest unfinished first (`since`); the rest are
    `deferred`, carried by the record as they were (one not started as `whole`)."""
    scope = _load("coverage_scope", os.path.join(root, "tests", "coverage_scope.py"))
    # The record names a COMMIT: a name like HEAD would move under it (a laptop run stored
    # "HEAD" itself, 2026-10-14).
    head = git("rev-parse", "--verify", f"{head}^{{commit}}", root=root).strip()
    base = state.get("commit") or first_base(head, root)
    diff = git("diff", "-U0", f"{base}..{head}", "--", "modules", root=root)

    def read(path):
        """The file AT head (the diff's line numbers are head's), None when head has none."""
        r = subprocess.run(["git", "-C", root, "show", f"{head}:{path}"], capture_output=True,
                           text=True)
        return r.stdout if r.returncode == 0 else None

    kept, names, not_rerun, waiting = {}, {}, [], []
    since = {k: rec.get("since", "") for k, rec in (state.get("functions") or {}).items()}
    for k, rec in (state.get("functions") or {}).items():
        path, _, qualname = k.partition("::")
        if rec.get("whole") and rec.get("hash") \
                and function_hash(read(path), qualname) == rec["hash"]:
            # Left over by an earlier night's cap before any of it ran: mutated whole, in its
            # turn (its place in line is its `since`).
            waiting.append((path, qualname))
            continue
        if rec.get("hash") and function_hash(read(path), qualname) == rec["hash"]:
            # Known debt at the text it was listed at is NOT run again (the operator,
            # 2026-10-14): only the function's unchecked mutants are; one with none left is
            # not planned at all, its survivors held by the debt list.
            again = not debt_unchanged(debt or {}, dotted((path, qualname)), rec["hash"])
            left = sorted(m for m, s in rec["results"].items()
                          if s == "not checked" or (again and m in rec.get("open", [])))
            if not left:
                not_rerun.append(k)
                continue
            kept[k] = rec
            names[k] = left
    fresh = changed_functions(changed_lines(diff), read, scope.classify)
    # MOVED, not changed (the operator, 2026-10-14): a fresh function whose text hash the
    # record or the debt list already holds under another name. The record's results for it
    # are carried over, renamed (the same text makes the same mutants, numbered the same), and
    # only what is left or open runs; one finished before, or one on the debt list, is not
    # mutated again at all.
    record_by_hash = {rec["hash"]: k for k, rec in (state.get("functions") or {}).items()
                      if rec.get("hash") and k not in kept and not rec.get("whole")}
    finished_by_hash = {v["hash"]: k for k, v in (state.get("finished") or {}).items()
                        if v.get("hash")}
    debt_by_hash = {f["hash"]: f"{f['path']}::{f['qualname']}"
                    for f in (debt or {}).get("functions", {}).values() if f.get("hash")}
    carried, skipped, still_fresh = {}, {}, []
    for f in fresh:
        h = function_hash(read(f[0]), f[1])
        old = record_by_hash.get(h)
        if key(f) not in kept and old and old != key(f):
            o, rec = tuple(old.split("::", 1)), state["functions"][old]
            moved = {"hash": h, "results": renamed(rec["results"], o, f),
                     "open": renamed(rec.get("open", []), o, f)}
            kept[key(f)] = moved
            names[key(f)] = sorted(m for m, s in moved["results"].items()
                                   if s == "not checked" or m in moved["open"])
            carried[key(f)] = old
            since[key(f)] = since.get(old, "")
            continue
        was = finished_by_hash.get(h) or debt_by_hash.get(h)
        if key(f) not in kept and was and was != key(f):
            skipped[key(f)] = was
            continue
        still_fresh.append(f)
    fresh = still_fresh + [f for f in waiting if f not in still_fresh]
    named = []
    for k in also:
        f = tuple(k.split("::", 1))
        if not function_hash(read(f[0]), f[1]):
            raise ValueError(f"{k}: no counted function of that name at {head[:9]}")
        if f not in fresh:
            fresh.append(f)
        named.append(f)
        kept.pop(k, None)
        names.pop(k, None)
        carried.pop(k, None)
        skipped.pop(k, None)
    candidates = [tuple(k.split("::", 1)) for k in kept]
    candidates += [f for f in fresh if key(f) not in kept]
    # THE CAP (C834): the oldest unfinished first, by when each entered the record (`since`, the
    # night's head commit then; a record from before the field is older than any), a function a
    # person named tonight before all; what does not fit waits in the record, in its place.
    for f in candidates:
        if key(f) not in since:
            since[key(f)] = head
    when = _commit_times({since[key(f)] for f in candidates}, root)
    order = sorted(range(len(candidates)),
                   key=lambda i: (candidates[i] not in named,
                                  when.get(since[key(candidates[i])], 0), i))
    ordered = [candidates[i] for i in order]
    planned = ordered if not cap else ordered[:cap]
    hashes_all = {key(f): function_hash(read(f[0]), f[1]) for f in ordered}
    deferred = {}
    for f in ordered[len(planned):]:
        k = key(f)
        deferred[k] = (dict(kept[k], since=since[k]) if k in kept else
                       {"hash": hashes_all[k], "results": {}, "open": [], "since": since[k],
                        "whole": True})
    hashes = {key(f): hashes_all[key(f)] for f in planned}
    kept = {k: v for k, v in kept.items() if k not in deferred}
    names = {k: v for k, v in names.items() if k not in deferred}
    carried = {k: v for k, v in carried.items() if k not in deferred}
    # GONE: a function the record names (unfinished, or finished) that no longer exists at head,
    # deleted rather than changed (the AI family's removal, D15). Dropped from the record and
    # said in the night's summary, never an error (the operator, 2026-10-14).
    recorded = sorted(set(state.get("functions") or {}) | set(state.get("finished") or {}))
    gone = [k for k in recorded
            if not function_hash(read(k.partition("::")[0]), k.partition("::")[2])]
    finished_before = {k: v for k, v in (state.get("finished") or {}).items() if k not in gone}
    waiting_keys = {key(f) for f in waiting}
    return {"base": base, "head": head, "planned": planned, "names": names, "kept": kept,
            "hashes": hashes, "moved": moved_from([f for f in planned if key(f) not in kept],
                                                  hashes, base, root),
            "carried": carried, "skipped_moved": skipped,
            "finished_before": finished_before,
            "previous_debt_entries": state.get("debt_entries"),
            "gone": gone, "debt_not_rerun": sorted(not_rerun),
            "cap": cap, "deferred": deferred,
            "since": {key(f): since[key(f)] for f in planned},
            "dropped": sorted(k for k in (state.get("functions") or {})
                              if k not in kept and k not in gone and k not in not_rerun
                              and k not in deferred and k not in waiting_keys)}


def _commit_times(commits, root: str = ROOT) -> dict:
    """`{commit: committer time}` for the commits git knows (an unknown one is left out, and
    sorts as the oldest)."""
    out = {}
    for c in sorted(c for c in commits if c):
        r = subprocess.run(["git", "-C", root, "show", "-s", "--format=%ct", c],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip().isdigit():
            out[c] = int(r.stdout.strip())
    return out


def selection_lines(p: dict, ran: dict = None) -> list:
    """The summary's lines for how the night chose its tests (`plan`'s `selection`, and the run's
    measurement of the children): by measured reach, or by import and why, per function."""
    sel = p.get("selection")
    if not sel:
        return []
    how = sel.get("how") or {}
    measured = sorted(k for k, h in how.items() if h == "measured")
    by_import = sorted(k for k, h in how.items() if h != "measured")
    lines = [f"Tests: {sel.get('ids', 0)} test function(s) by measured reach and "
             f"{sel.get('files', 0)} test file(s) whole. "
             + (f"The coverage drill-down of {sel['reach_commit'][:9]} measured "
                f"{len(measured)} of the {len(how)} function(s) as they are tonight; "
                if not sel.get("unusable") else
                f"No measured reach tonight ({sel['unusable']}); ")
             + f"{len(by_import)} ran their modules' importing test files, as before:", ""]
    lines += [f"- `{k}`: by import" + (f" ({sel['stale'][k]})" if k in (sel.get("stale") or {})
                                         and not sel.get("unusable") else "")
              for k in by_import]
    if by_import:
        lines += [""]
    if sel.get("not_found"):
        lines += [f"Measured by the drill-down but not collected at head, so not run "
                  f"({len(sel['not_found'])}): " + ", ".join(f"`{t}`" for t in sel["not_found"]),
                  ""]
    ran = ran or {}
    if "children_reached" in ran:
        reached, unmeasured = ran.get("children_reached") or {}, ran.get("children_unmeasured") or []
        lines += [f"Children: {len(ran.get('spawning_tests') or [])} test(s) start a child of "
                  f"ours; {len(reached)} measured (each joins only the functions its children "
                  f"ran: {sum(1 for f in reached.values() if f)} reached one), "
                  f"{len(unmeasured)} not measured, so added to every function as before"
                  + (": " + ", ".join(f"`{t}`" for t in unmeasured) if unmeasured else "")
                  + f"; {ran.get('associations_added', 0)} association(s) added.", ""]
    return lines


def deferred_lines(p: dict) -> list:
    """The summary's lines for the functions the night's cap left for the next nights (`plan`'s
    `deferred`), oldest first, each kept in the record in its place."""
    left = p.get("deferred") or {}
    if not left:
        return []
    return [f"Capped: {len(p['planned'])} function(s) tonight, the oldest unfinished first (the "
            f"cap is {p.get('cap')}); {len(left)} wait in the record for the next nights, "
            "their results so far kept:", "",
            *[f"- `{k}`" + (" (not started)" if r.get("whole") else
                            f" ({sum(1 for s in r.get('results', {}).values() if s == 'not checked')}"
                            " not checked)")
              for k, r in left.items()], ""]


def not_rerun_lines(p: dict) -> list:
    """The summary's lines for the functions the plan did not run because all they hold is known
    debt at the text it was listed at (`plan`'s `debt_not_rerun`): the budget goes to what is
    unchecked or changed."""
    held = p.get("debt_not_rerun") or []
    if not held:
        return []
    return [f"Known debt not run again ({len(held)} function(s)): their text is the one their "
            "survivors were listed at, and nothing in them is unchecked:", "",
            *[f"- `{k}`" for k in held], ""]


def gone_lines(p: dict) -> list:
    """The summary's lines for the record's functions that no longer exist (`plan`'s `gone`):
    dropped from the record, named, never a failure."""
    gone = p.get("gone") or []
    if not gone:
        return []
    return [f"Gone since the record ({len(gone)}): these functions no longer exist at "
            f"{p['head'][:9]}, so the record drops them (a removal, not a failure):", "",
            *[f"- `{k}`" for k in gone], ""]


def moved_from(planned: list, hashes: dict, base: str, root: str = ROOT) -> dict:
    """`{path::qualname: where it was at base}` for each planned function whose text, hash for
    hash, was another module's function of the same name at *base*: moved, not changed (the
    operator, 2026-10-14: the AI family's shared pieces moved out). Said, not skipped: the
    record keys a function by path and name, and the tests that reach it moved with it."""
    out = {}
    for f in planned:
        leaf = f[1].rsplit(".", 1)[-1]
        r = subprocess.run(["git", "-C", root, "grep", "-l", "-F", "-e", f"def {leaf}(", base,
                            "--", "*.py"], capture_output=True, text=True)
        for hit in r.stdout.split("\n"):
            path = hit.split(":", 1)[1] if ":" in hit else ""
            if not path or path == f[0]:
                continue
            was = subprocess.run(["git", "-C", root, "show", f"{base}:{path}"],
                                 capture_output=True, text=True).stdout
            if hashes.get(key(f)) and function_hash(was, f[1]) == hashes[key(f)]:
                out[key(f)] = f"{path}::{f[1]}"
                break
    return out


def patterns(p: dict) -> list:
    """mutmut's names for the night: a kept function's own names (what is left, and its open
    survivors), a fresh function's whole pattern."""
    out = []
    for f in p["planned"]:
        k = key(tuple(f))
        out += p["names"][k] if k in p["names"] else [mutant_pattern(*f)]
    return out


def save(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
