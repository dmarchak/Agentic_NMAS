"""The nightly mutation run's logic (docs/TESTING.md, "Mutation testing"; the workflow is
.github/workflows/mutation-nightly.yml, the CLI scripts/nmas-mutation).

Coverage says a test ran a line; mutation testing says whether a test would notice the line being
wrong. Each night this mutates ONLY the automation functions changed since the commit the last
night covered, and the functions the record keeps (one unfinished, or one with an open
survivor), runs the tests that import their modules against each mutant, and reports the
survivors that are not in the hand-kept list of equivalent mutants
(tests/mutation_equivalent.py). A canary (tests/mutation_canary.py) runs first and must be
killed, or no result stands. It never runs on the NMAS host, the gate or a push.
"""
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


# ── The tests a child reaches ─────────────────────────────────────────────────────────────────

def spawning_tests(tiers: dict) -> list:
    """The tests that started a process running this checkout's code (the tier records
    tests/conftest.py writes: `spawns`, and `browser`, whose app runs apart too). Such a test can
    reach any function in its child, and a child records nothing in mutmut's statistics, so
    mutmut alone would never choose it to run against a mutant."""
    return sorted(t for t, tier in tiers.items() if tier != "unit")


def add_tests(stats: dict, functions: list, tests: list) -> int:
    """Add *tests* to each of *functions*' (mangled names) tests in mutmut's statistics
    (`mutants/mutmut-stats.json`, as loaded): `tests_by_mangled_function_name`. Returns how many
    associations were new."""
    by = stats.setdefault("tests_by_mangled_function_name", {})
    added = 0
    for f in functions:
        have = set(by.get(f, []))
        new = [t for t in tests if t not in have]
        by[f] = sorted(have | set(new))
        added += len(new)
    return added


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


def is_equivalent(function: str, was: str, now: str, equivalent: list) -> str:
    """The reason when (*function*, *was*, *now*) is in the hand-kept list, else ""."""
    for e in equivalent:
        if e["function"] == function and e["was"].strip() == was and e["now"].strip() == now:
            return e["why"]
    return ""


def verdict(results: dict, shows: dict, equivalent: list, kinds: dict = None) -> dict:
    """Per function: mutants, killed, survived (no test failed: `SURVIVING`); the survivors
    split into known equivalents (listed apart, with their reason) and OPEN ones, each VERDICT
    or MESSAGE by *kinds* (`{mutant: kind}`, `classify_file`; a mutant it does not name is
    VERDICT). Only open VERDICT survivors (`new`) fail the night; MESSAGE ones are `message`.
    *shows*: `{mutant: mutmut show text}` for the survivors."""
    per, new, message, known = {}, [], [], []
    for mutant, status in sorted(results.items()):
        fn = function_of(mutant)
        p = per.setdefault(fn, {"mutants": 0, "killed": 0, "survived": 0, "equivalent": 0,
                                "verdict": 0, "message": 0, "other": 0})
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
            else:
                p["verdict"] += 1
                new.append(entry)
        else:
            p["other"] += 1
    return {"functions": per, "new": new, "message": message, "known": known}


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
               hashes: dict) -> dict:
    """What the next night starts from: this run's HEAD, and per function still unfinished or
    holding an open survivor, its hash and every result so far (C769: a large function is
    finished across nights, never restarted; an open survivor is run again each night until a
    test kills it or a person lists it as equivalent)."""
    open_by = {}
    for m in open_mutants:
        open_by.setdefault(function_of(m), []).append(m)
    functions = {}
    for f in planned:
        res = only_functions(results, [f])
        if any(s == "not checked" for s in res.values()) or dotted(f) in open_by:
            functions[key(f)] = {"hash": hashes.get(key(f), ""), "results": res,
                                 "open": sorted(open_by.get(dotted(f), []))}
    return {"commit": head, "functions": functions}


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
            cause: list = (), moved: dict = None) -> str:
    """The job summary (Markdown). *extra*: lines said first (the canary, the scope, what the
    record carried in). *cause*: a failed run's own lines (`failure_excerpt`). *moved*:
    `{path::qualname: where it was}` for planned functions only moved, their text unchanged."""
    lines = [f"## Mutation testing: functions changed {base[:9]}..{head[:9]}", ""]
    if not planned:
        return "\n".join(lines + ["Nothing to mutate: no automation function changed, and "
                                  "the record holds none unfinished or with an open survivor.",
                                  ""])
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
              "| function | mutants | killed | survived: VERDICT | survived: MESSAGE "
              "| known equivalent | score | VERDICT score |",
              "|---|---|---|---|---|---|---|---|"]
    for fn, p in sorted(verdict_["functions"].items()):
        killable = p["mutants"] - p["equivalent"]
        score = f"{100.0 * p['killed'] / killable:.1f}%" if killable else "—"
        at_stake = p["killed"] + p.get("verdict", p["survived"] - p["equivalent"])
        vscore = f"{100.0 * p['killed'] / at_stake:.1f}%" if at_stake else "—"
        lines.append(f"| `{fn}` | {p['mutants']} | {p['killed']} "
                     f"| {p.get('verdict', p['survived'] - p['equivalent'])} "
                     f"| {p.get('message', 0)} | {p['equivalent']} | {score} | {vscore} |")

    def item(s):
        return (f"- `{s['mutant']}`" + (" (no test reached it)" if s.get("status") == "no tests"
                                        else "") + f": `{s['was']}` → `{s['now']}`")
    lines += ["", f"### Open VERDICT survivors ({len(verdict_['new'])}): the night fails until "
              "each is killed by a test or listed as equivalent", ""]
    lines += [item(s) for s in verdict_["new"]] \
        or ["- none: every mutant that can change a verdict was killed, or is a known equivalent"]
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


def plan(state: dict, head: str, root: str = ROOT, also: list = ()) -> dict:
    """The night's plan: the base commit (the last covered, or on the first night the commit
    that added the nightly workflow, `first_base`) and the functions to mutate, each read at
    head: those the record keeps whose hash is
    unchanged (only their mutants not yet checked and their open survivors run: `names`), then
    the counted automation functions the diff touches (all their mutants). A kept function whose
    text changed is planned afresh, its old results dropped. *also*: functions (`path::qualname`)
    a person names to mutate whole tonight, changed or not. The scope is *root*'s
    tests/coverage_scope.py, the coverage tool's."""
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

    kept, names = {}, {}
    for k, rec in (state.get("functions") or {}).items():
        path, _, qualname = k.partition("::")
        if rec.get("hash") and function_hash(read(path), qualname) == rec["hash"]:
            kept[k] = rec
            names[k] = sorted(m for m, s in rec["results"].items()
                              if s == "not checked" or m in rec.get("open", []))
    fresh = changed_functions(changed_lines(diff), read, scope.classify)
    for k in also:
        f = tuple(k.split("::", 1))
        if not function_hash(read(f[0]), f[1]):
            raise ValueError(f"{k}: no counted function of that name at {head[:9]}")
        if f not in fresh:
            fresh.append(f)
        kept.pop(k, None)
        names.pop(k, None)
    planned = [tuple(k.split("::", 1)) for k in kept]
    planned += [f for f in fresh if key(f) not in kept]
    hashes = {key(f): function_hash(read(f[0]), f[1]) for f in planned}
    return {"base": base, "head": head, "planned": planned, "names": names, "kept": kept,
            "hashes": hashes, "moved": moved_from([f for f in planned if key(f) not in kept],
                                                  hashes, base, root),
            "dropped": sorted(k for k in (state.get("functions") or {}) if k not in kept)}


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
