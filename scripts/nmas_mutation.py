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


def verdict(results: dict, shows: dict, equivalent: list) -> dict:
    """Per function: mutants, killed, survived (no test failed: `SURVIVING`); the survivors
    split into NEW (open: a failure) and known equivalents (listed apart, with their reason).
    *shows*: `{mutant: mutmut show text}` for the survivors."""
    per, new, known = {}, [], []
    for mutant, status in sorted(results.items()):
        fn = function_of(mutant)
        p = per.setdefault(fn, {"mutants": 0, "killed": 0, "survived": 0, "equivalent": 0,
                                "other": 0})
        p["mutants"] += 1
        if status == "killed":
            p["killed"] += 1
        elif status in SURVIVING:
            p["survived"] += 1
            was, now = diff_lines(shows.get(mutant, ""))
            why = is_equivalent(fn, was, now, equivalent)
            p["equivalent"] += bool(why)
            (known if why else new).append({"mutant": mutant, "function": fn, "was": was,
                                            "now": now, "why": why, "status": status})
        else:
            p["other"] += 1
    return {"functions": per, "new": new, "known": known}


def only_functions(results: dict, functions: list) -> dict:
    """*results* restricted to *functions*' mutants: `mutmut results` lists every mutant of a
    mutated FILE, the unplanned functions' as "not checked"."""
    wanted = {dotted(f) for f in functions}
    return {m: s for m, s in results.items() if function_of(m) in wanted}


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
                         "no result stands; the log above it says why"}
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


def summary(base: str, head: str, planned: list, verdict_: dict, left: list,
            budget_minutes: int, error: str = "", empty: list = (), extra: list = ()) -> str:
    """The job summary (Markdown). *extra*: lines said first (the canary, the scope, what the
    record carried in)."""
    lines = [f"## Mutation testing: functions changed {base[:9]}..{head[:9]}", ""]
    if not planned:
        return "\n".join(lines + ["Nothing to mutate: no automation function changed, and "
                                  "the record holds none unfinished or with an open survivor.",
                                  ""])
    lines += list(extra)
    if error:
        lines += [f"**The run failed:** {error}.", "",
                  f"Planned ({len(planned)}); the record is left as it was:", ""]
        return "\n".join(lines + [f"- `{p}` {q}" for p, q in planned]) + "\n"
    lines += ["The score is killed over the mutants a test could kill (all, less the known "
              "equivalents).", "",
              "| function | mutants | killed | survived | of them known equivalent | score |",
              "|---|---|---|---|---|---|"]
    for fn, p in sorted(verdict_["functions"].items()):
        killable = p["mutants"] - p["equivalent"]
        score = f"{100.0 * p['killed'] / killable:.1f}%" if killable else "—"
        lines.append(f"| `{fn}` | {p['mutants']} | {p['killed']} | {p['survived']} "
                     f"| {p['equivalent']} | {score} |")
    lines += ["", f"### Open survivors ({len(verdict_['new'])}): the night fails until each is "
              "killed by a test or listed as equivalent", ""]
    lines += [f"- `{s['mutant']}`" + (" (no test reached it)" if s.get("status") == "no tests"
                                      else "") + f": `{s['was']}` → `{s['now']}`"
              for s in verdict_["new"]] \
        or ["- none: every mutant was killed, or is a known equivalent"]
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


def plan(state: dict, head: str, root: str = ROOT, also: list = ()) -> dict:
    """The night's plan: the base commit (the last covered, or head's parent on the first
    night) and the functions to mutate, each read at head: those the record keeps whose hash is
    unchanged (only their mutants not yet checked and their open survivors run: `names`), then
    the counted automation functions the diff touches (all their mutants). A kept function whose
    text changed is planned afresh, its old results dropped. *also*: functions (`path::qualname`)
    a person names to mutate whole tonight, changed or not. The scope is *root*'s
    tests/coverage_scope.py, the coverage tool's."""
    scope = _load("coverage_scope", os.path.join(root, "tests", "coverage_scope.py"))
    base = state.get("commit") or git("rev-parse", f"{head}~1", root=root).strip()
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
            "hashes": hashes,
            "dropped": sorted(k for k in (state.get("functions") or {}) if k not in kept)}


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
