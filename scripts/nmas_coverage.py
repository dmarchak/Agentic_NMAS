"""Which of Mercury's automation code the tests reach, function by function (Lab 7, Objective 2;
docs/TESTING.md, "The coverage tool"). The CLI is `scripts/nmas-coverage`.

**The question it answers:** for every automation module (tests/coverage_scope.py), does any
unit test reach it at all, and how many of its functions? A function counts as covered when at
least one line of its BODY ran while a unit test ran. "Ran" is measured by coverage.py with a
context per test, never inferred from a test mentioning the function's name: name-matching
counts a function covered when a test only imports it, or names it in a string, or tests a
different function of the same name, and misses one reached through its caller.

**Tiers** (tests/conftest.py records each test's, by what it did): `unit`, in-process and
offline (the Flask-client tests among them: they call the app in the same process, with no
socket); `spawns`, it started a process; `browser`, it drove a browser. The headline is the
unit tier; a second column counts every offline tier, and where the two differ the gap is the
finding: those functions are reached only through a process or a browser.

**Beside the function figure:** line coverage (unit tier) and branch coverage (every tier), so
a function "covered" by one line is visibly unlike one exercised through; and the tests that
assert nothing.

**The gate** is a ratchet against a committed baseline (tests/coverage_baseline.json), per
module: a drop in an automation module's unit function coverage, a new automation module with
none, or a new test that asserts nothing, fails. No absolute threshold. The baseline moves only
by `nmas-coverage baseline`, never by itself.
"""
import ast
import glob
import html
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "tests", "coverage_baseline.json")
#: The packages coverage measures (the CI command's --cov arguments).
MEASURED = ("modules", "routes", "app.py")
TIERS = ("unit", "spawns", "browser")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pydefs = _load("pydefs", os.path.join(ROOT, "scripts", "pydefs.py"))


def load_scope(root: str = ROOT):
    """The scope module (tests/coverage_scope.py) of *root*."""
    return _load("coverage_scope", os.path.join(root, "tests", "coverage_scope.py"))


# ── Scope ─────────────────────────────────────────────────────────────────────────────────────

def measured_files(root: str = ROOT, tracked=None) -> list:
    """The repository-relative Python files under MEASURED, from git's index (*tracked* when
    given), so an untracked copy never joins the report."""
    if tracked is None:
        import subprocess
        out = subprocess.run(["git", "-C", root, "ls-files", "--", *MEASURED],
                             capture_output=True, text=True, check=True).stdout
        tracked = out.split()
    return sorted(p for p in tracked if p.endswith(".py"))


def classify_all(files: list, scope) -> dict:
    """`{"files": {path: (category, why)}, "unclassified": [...], "stale": [...]}`: every
    file placed by the scope's rules or exceptions; a file nothing places, and an exception
    naming a file that is not there, are the scope's failures."""
    placed, unclassified = {}, []
    for path in files:
        got = scope.classify(path)
        if got is None:
            unclassified.append(path)
        else:
            placed[path] = tuple(got)
    stale = sorted(p for p in scope.EXCEPTIONS if p not in files)
    return {"files": placed, "unclassified": unclassified, "stale": stale}


# ── Assertions ────────────────────────────────────────────────────────────────────────────────

_ASSERT_CALLS = re.compile(r"^(assert\w*|fail\w*|raises|warns|deprecated_call|approx)$")


def _calls(node) -> set:
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
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) \
                else ""
            if _ASSERT_CALLS.match(name):
                return True
    return False


def assertion_free(test_files: list, root: str = ROOT, helper_files=None) -> list:
    """The tests (`file::Class::test`) that assert nothing: no `assert`, no `raise
    AssertionError`, no `pytest.raises` / `pytest.fail` / a mock's `assert_*`, and no call to a
    helper that does (any function in *helper_files*, by default every Python file in tests/,
    as `browser.wait_for`), followed to any depth. Such a test can only show that nothing
    raised, so it can execute every line and check none."""
    trees, helpers = {}, {}
    if helper_files is None:
        helper_files = sorted(os.path.relpath(p, root) for p in
                              glob.glob(os.path.join(root, "tests", "*.py")))
    for path in sorted(set(test_files) | set(helper_files)):
        with open(os.path.join(root, path), encoding="utf-8") as fh:
            try:
                tree = ast.parse(fh.read())
            except SyntaxError:
                continue
        if path in test_files:
            trees[path] = tree
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                helpers.setdefault(n.name, []).append(n)
    asserting = {name for name, nodes in helpers.items()
                 if any(_asserts_directly(n) for n in nodes)}
    changed = True
    while changed:                       # a helper that calls an asserting helper asserts
        changed = False
        for name, nodes in helpers.items():
            if name not in asserting and any(_calls(n) & asserting for n in nodes):
                asserting.add(name)
                changed = True
    found = []
    for path, tree in sorted(trees.items()):
        def scan(body, prefix):
            for n in body:
                if isinstance(n, ast.ClassDef) and n.name.startswith("Test"):
                    scan(n.body, f"{prefix}{n.name}::")
                elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and n.name.startswith("test"):
                    if not _asserts_directly(n) and not (_calls(n) & asserting):
                        found.append(f"{path}::{prefix}{n.name}")
        scan(tree.body, "")
    return found


# ── Measurement ───────────────────────────────────────────────────────────────────────────────

def load_tiers(folder: str) -> dict:
    """`{test node id: tier}` from the coverage run's records (tests/conftest.py writes one
    JSON line per test into `NMAS_TEST_TIERS`)."""
    tiers = {}
    for path in glob.glob(os.path.join(folder, "tiers-*.jsonl")):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rec = json.loads(line)
                    tiers[rec["test"]] = rec["tier"]
    return tiers


def _test_of(context: str) -> str:
    """The test a coverage context names (pytest-cov: `<node id>|run`), or "" for code that ran
    outside any test's run phase (a fixture's setup, a child process)."""
    nodeid, _, phase = context.rpartition("|")
    return nodeid if phase == "run" else ""


def module_report(path: str, source: str, by_line: dict, tiers: dict, statements: set,
                  numbers: dict) -> dict:
    """One module's figures. *by_line*: `{line: [contexts]}` from the coverage data;
    *statements*: its executable lines; *numbers*: coverage's own summary for it (lines and
    branches over every context)."""
    defs = pydefs.definitions(source)
    functions, excluded = [], []
    for d in defs:
        if d.kind == "class":
            continue
        if d.excluded:
            excluded.append({"name": d.qualname, "line": d.lineno,
                             "why": pydefs.WHY[d.excluded]})
            continue
        tests = set()
        for line in d.body_lines:
            for ctx in by_line.get(line, ()):
                t = _test_of(ctx)
                if t:
                    tests.add(t)
        child = any(ctx == "" for line in d.body_lines for ctx in by_line.get(line, ()))
        unit = sorted(t for t in tests if tiers.get(t, "unit") == "unit")
        functions.append({"name": d.qualname, "line": d.lineno, "unit_tests": unit,
                          "other_tests": sorted(t for t in tests if t not in unit),
                          "covered_unit": bool(unit), "covered_any": bool(tests) or child})
    unit_lines = {line for line, ctxs in by_line.items()
                  if any(_test_of(c) and tiers.get(_test_of(c), "unit") == "unit" for c in ctxs)}
    total = len(functions)
    cu = sum(f["covered_unit"] for f in functions)
    ca = sum(f["covered_any"] for f in functions)
    return {
        "path": path, "functions": total, "covered_unit": cu, "covered_any": ca,
        "function_pct_unit": round(100.0 * cu / total, 1) if total else None,
        "function_pct_any": round(100.0 * ca / total, 1) if total else None,
        "line_pct_unit": (round(100.0 * len(unit_lines & statements) / len(statements), 1)
                          if statements else None),
        "line_pct_any": numbers.get("percent_statements_covered"),
        "branch_pct_any": (round(100.0 * numbers["covered_branches"] / numbers["num_branches"], 1)
                           if numbers.get("num_branches") else None),
        "function_list": functions, "excluded": excluded,
    }


def measure(data_file: str, tiers_dir: str, root: str = ROOT, files=None, scope=None) -> dict:
    """The whole report from a combined coverage data file with per-test contexts."""
    import coverage

    scope = scope or load_scope(root)
    files = measured_files(root) if files is None else files
    placed = classify_all(files, scope)
    tiers = load_tiers(tiers_dir)
    cov = coverage.Coverage(data_file=data_file)
    cov.load()
    data = cov.get_data()
    json_path = data_file + ".summary.json"
    in_data = {os.path.relpath(f, root): f for f in data.measured_files()}
    cov.json_report(outfile=json_path, morfs=list(in_data.values()), ignore_errors=True)
    with open(json_path, encoding="utf-8") as fh:
        summary = {os.path.relpath(k, root) if os.path.isabs(k) else k: v["summary"]
                   for k, v in json.load(fh)["files"].items()}
    modules = {}
    for path, (category, why) in placed["files"].items():
        if category == "excluded":
            continue
        with open(os.path.join(root, path), encoding="utf-8") as fh:
            source = fh.read()
        abs_path = in_data.get(path)
        by_line = data.contexts_by_lineno(abs_path) if abs_path else {}
        statements = set()
        if abs_path:
            _f, stmts, _x, _m, _s = cov.analysis2(abs_path)
            statements = set(stmts)
        rep = module_report(path, source, by_line, tiers, statements, summary.get(path, {}))
        rep.update(category=category, why=why, measured=bool(abs_path))
        modules[path] = rep
    tests = sorted(p for p in (scope_tests(root)))
    return {"modules": modules, "unclassified": placed["unclassified"],
            "stale_exceptions": placed["stale"], "tiers": _tier_counts(tiers),
            "assertion_free": assertion_free(tests, root)}


def scope_tests(root: str = ROOT) -> list:
    """The test files, repository-relative."""
    return sorted(os.path.relpath(p, root) for p in glob.glob(os.path.join(root, "tests",
                                                                           "test_*.py")))


def _tier_counts(tiers: dict) -> dict:
    return {t: sum(1 for v in tiers.values() if v == t) for t in TIERS}


def totals(report: dict, category: str = "automation") -> dict:
    """The top line over every module of *category*."""
    mods = [m for m in report["modules"].values() if m["category"] == category]
    fn = sum(m["functions"] for m in mods)
    cu = sum(m["covered_unit"] for m in mods)
    ca = sum(m["covered_any"] for m in mods)
    return {"modules": len(mods), "functions": fn, "covered_unit": cu, "covered_any": ca,
            "function_pct_unit": round(100.0 * cu / fn, 1) if fn else None,
            "function_pct_any": round(100.0 * ca / fn, 1) if fn else None,
            "untested_modules": sorted(m["path"] for m in mods
                                       if m["functions"] and not m["covered_unit"])}


# ── The ratchet ───────────────────────────────────────────────────────────────────────────────

def baseline_of(report: dict) -> dict:
    """What `nmas-coverage baseline` writes: each automation module's unit function figure,
    and the tests that assert nothing today."""
    return {"modules": {p: {"functions": m["functions"], "covered_unit": m["covered_unit"]}
                        for p, m in sorted(report["modules"].items())
                        if m["category"] == "automation"},
            "assertion_free": sorted(report["assertion_free"])}


def ratchet(report: dict, baseline: dict) -> list:
    """The ratchet's failures, each naming the module or test and both figures: an automation
    module's unit function coverage below its baseline; a new automation module (not in the
    baseline) with functions and none covered; a test that asserts nothing and is not in the
    baseline."""
    failures = []
    base_mods = baseline.get("modules", {})
    for path, m in sorted(report["modules"].items()):
        if m["category"] != "automation" or not m["functions"]:
            continue
        b = base_mods.get(path)
        now = m["covered_unit"] / m["functions"]
        if b is None:
            if not m["covered_unit"]:
                failures.append(f"{path}: a new automation module with no unit test "
                                f"(0 of {m['functions']} functions)")
        elif b["functions"] and now < b["covered_unit"] / b["functions"]:
            failures.append(
                f"{path}: unit function coverage fell from {b['covered_unit']} of "
                f"{b['functions']} ({100.0 * b['covered_unit'] / b['functions']:.1f}%) to "
                f"{m['covered_unit']} of {m['functions']} ({100.0 * now:.1f}%)")
    known = set(baseline.get("assertion_free", []))
    for t in report["assertion_free"]:
        if t not in known:
            failures.append(f"{t}: a new test that asserts nothing")
    return failures


# ── Output ────────────────────────────────────────────────────────────────────────────────────

def _pct(v) -> str:
    return "—" if v is None else f"{v:.1f}%"


def table(report: dict) -> str:
    """The terminal table: the top line, the modules with no unit test, then every automation
    module, lowest first."""
    t = totals(report)
    out = [f"Automation code: {t['modules']} modules, {t['functions']} functions. Unit tests reach "
           f"{t['covered_unit']} ({_pct(t['function_pct_unit'])}); every offline tier "
           f"{t['covered_any']} ({_pct(t['function_pct_any'])}).",
           f"Tests by tier: " + ", ".join(f"{k} {v}" for k, v in report["tiers"].items()),
           f"Modules with no unit test: {len(t['untested_modules'])}"]
    out += [f"  {p}" for p in t["untested_modules"]]
    out.append("")
    out.append(f"{'module':58} {'functions':>9} {'unit':>7} {'all':>7} {'lines':>7} {'branches':>8}")
    mods = sorted((m for m in report["modules"].values() if m["category"] == "automation"
                   and m["functions"]), key=lambda m: (m["function_pct_unit"], m["path"]))
    for m in mods:
        out.append(f"{m['path']:58} {m['covered_unit']:>4}/{m['functions']:<4} "
                   f"{_pct(m['function_pct_unit']):>7} {_pct(m['function_pct_any']):>7} "
                   f"{_pct(m['line_pct_unit']):>7} {_pct(m['branch_pct_any']):>8}")
    retiring = [m for m in report["modules"].values() if m["category"] == "retiring"]
    if retiring:
        out.append("")
        out.append("Retiring (not in the totals): " + ", ".join(
            f"{m['path']} {_pct(m['function_pct_unit'])}" for m in
            sorted(retiring, key=lambda m: m["path"])))
    out.append(f"Tests that assert nothing: {len(report['assertion_free'])}")
    return "\n".join(out)


def summary_markdown(report: dict, failures: list) -> str:
    """The Actions job summary (GITHUB_STEP_SUMMARY)."""
    t = totals(report)
    lines = ["## Function coverage of the automation code",
             f"**{t['covered_unit']} of {t['functions']} functions ({_pct(t['function_pct_unit'])})**"
             f" are reached by a unit test; {t['covered_any']} ({_pct(t['function_pct_any'])}) by "
             f"any offline tier, across {t['modules']} modules.", ""]
    if failures:
        lines += ["### The ratchet failed", ""] + [f"- {f}" for f in failures] + [""]
    else:
        lines += ["The ratchet holds: no module fell, no new module is untested, no new test "
                  "asserts nothing.", ""]
    lines += [f"### Modules with no unit test ({len(t['untested_modules'])})", ""]
    lines += [f"- `{p}`" for p in t["untested_modules"]] or ["- none"]
    mods = sorted((m for m in report["modules"].values() if m["category"] == "automation"
                   and m["functions"]), key=lambda m: (m["function_pct_unit"], m["path"]))[:15]
    lines += ["", "### The lowest fifteen", "",
              "| module | functions (unit) | unit | all tiers | lines (unit) | branches |",
              "|---|---|---|---|---|---|"]
    lines += [f"| `{m['path']}` | {m['covered_unit']}/{m['functions']} | "
              f"{_pct(m['function_pct_unit'])} | {_pct(m['function_pct_any'])} | "
              f"{_pct(m['line_pct_unit'])} | {_pct(m['branch_pct_any'])} |" for m in mods]
    lines += ["", f"Tests that assert nothing: {len(report['assertion_free'])} "
              "(baselined; a new one fails)."]
    return "\n".join(lines) + "\n"


def html_report(report: dict, failures: list) -> str:
    """One static page: the top line, the ratchet, every module, and per module each function
    with the tests that reach it."""
    e = html.escape
    t = totals(report)
    rows = []
    for m in sorted(report["modules"].values(), key=lambda m: (
            {"automation": 0, "support": 1, "retiring": 2}.get(m["category"], 3),
            m["function_pct_unit"] if m["function_pct_unit"] is not None else 101, m["path"])):
        fns = "".join(
            f"<tr class='{'ok' if f['covered_unit'] else ('other' if f['covered_any'] else 'no')}'>"
            f"<td>{e(f['name'])}</td><td>{f['line']}</td>"
            f"<td>{'unit' if f['covered_unit'] else ('other tier only' if f['covered_any'] else 'not reached')}</td>"
            f"<td>{e(', '.join(f['unit_tests'][:5]))}{' …' if len(f['unit_tests']) > 5 else ''}</td></tr>"
            for f in m["function_list"])
        excl = "".join(f"<li>{e(x['name'])} (line {x['line']}): {e(x['why'])}</li>"
                       for x in m["excluded"])
        rows.append(
            f"<details><summary><span class='cat {e(m['category'])}'>{e(m['category'])}</span> "
            f"<code>{e(m['path'])}</code> — {m['covered_unit']}/{m['functions']} functions "
            f"({_pct(m['function_pct_unit'])} unit, {_pct(m['function_pct_any'])} all tiers), "
            f"lines {_pct(m['line_pct_unit'])}, branches {_pct(m['branch_pct_any'])}</summary>"
            f"<table><tr><th>function</th><th>line</th><th>reached by</th><th>unit tests</th></tr>"
            f"{fns}</table>{'<p>Not counted:</p><ul>' + excl + '</ul>' if excl else ''}</details>")
    fails = ("".join(f"<li>{e(f)}</li>" for f in failures) or "<li>none: the ratchet holds</li>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mercury function coverage</title><style>
body{{font:14px/1.4 system-ui,sans-serif;margin:16px;max-width:1100px}}
summary{{cursor:pointer;padding:3px 0}} table{{border-collapse:collapse;margin:6px 0 12px 18px}}
td,th{{padding:2px 8px;text-align:left;border-bottom:1px solid #ddd}}
tr.no td:nth-child(3){{color:#b00}} tr.other td:nth-child(3){{color:#a60}}
.cat{{font-size:11px;padding:1px 6px;border-radius:8px;background:#eee}}
.cat.automation{{background:#dfe}} .cat.retiring{{background:#fed}}
</style></head><body>
<h1>Function coverage of Mercury's automation code</h1>
<p><b>{t['covered_unit']} of {t['functions']} functions ({_pct(t['function_pct_unit'])})</b> are
reached by a unit test; {t['covered_any']} ({_pct(t['function_pct_any'])}) by any offline tier, across
{t['modules']} automation modules. Tests by tier: {e(', '.join(f'{k} {v}' for k, v in report['tiers'].items()))}.</p>
<h2>The ratchet</h2><ul>{fails}</ul>
<h2>Modules with no unit test ({len(t['untested_modules'])})</h2>
<ul>{''.join(f'<li><code>{e(p)}</code></li>' for p in t['untested_modules']) or '<li>none</li>'}</ul>
<h2>Every module</h2>{''.join(rows)}
<h2>Tests that assert nothing ({len(report['assertion_free'])})</h2>
<ul>{''.join(f'<li><code>{e(x)}</code></li>' for x in report['assertion_free'])}</ul>
</body></html>"""
