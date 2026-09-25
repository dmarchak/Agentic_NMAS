"""Every script's entry point can actually reach what it calls.

**Written because `--remove-excluded` crashed with
`NameError: name '_remove_excluded' is not defined` the first time anyone
ran it.** The function was in the file — at line 347, *below* the
`if __name__ == "__main__"` guard at line 343. Run as a script, `main()`
executes before Python reaches the definition. The mode had never run.

**Sixth instance in one session of the same family, and the purest.** Not a
wrong signature (`set_device_override`, `load_saved_devices`, `preflight`'s
lambda, `_commit`'s spy) and not an unreachable branch — a call to something
that is not there. The common cause every time: *the test names or
constructs its subject, so it cannot notice that the caller does not.*

There is a second cause here and it is worth naming separately, because it
defeats the obvious test. **Loading a script as a module cannot exhibit
this.** `SourceFileLoader(...).exec_module()` runs the whole file with
`__name__` set to the module's name, so the guard never fires, every
definition is reached, and `_remove_excluded` exists. A test that imported
the script and called the function would have **passed** — the same shape as
`FakeNetBox` being unable to cascade. The harness's import differs from the
real execution, so the check has to be about the *file*, not about the
loaded module.

`scripts/nmas-verify-runbook` does the equivalent for routes: it resolves
every documented URL against `app.url_map` rather than trusting that a
blueprint's path looks right. Scripts had no such check.
"""

import ast
import builtins
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")

#: Directories under scripts/ that are not scripts.
_SKIP_DIRS = {"__pycache__", "hooks"}


def _script_paths() -> list:
    out = []
    for name in sorted(os.listdir(SCRIPTS)):
        path = os.path.join(SCRIPTS, name)
        if not os.path.isfile(path) or name in _SKIP_DIRS:
            continue
        try:
            head = open(path, encoding="utf-8").read(200)
        except (UnicodeDecodeError, OSError):
            continue
        if name.endswith(".py") or head.startswith("#!") and "python" in head:
            out.append(path)
    return out


def _guard_line(tree: ast.Module):
    """Line of the `if __name__ == "__main__":` guard, or None."""
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"):
            return node.lineno
    return None


def definitions_below_the_guard(path: str) -> list:
    """Module-level definitions the entry point can never reach.

    **The defect, stated structurally.** A `def` below the guard is defined
    only when the file is imported; run as a script, `main()` has already
    executed and returned. It is not dead code — it is code that exists for
    every reader and every test and not for the program.
    """
    tree = ast.parse(open(path, encoding="utf-8").read())
    guard = _guard_line(tree)
    if guard is None:
        return []
    return [n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef))
            and n.lineno > guard]


def unresolved_calls(path: str) -> list:
    """Names called that nothing in the file or its imports binds.

    Deliberately conservative: a name counts as bound if **anything
    anywhere** in the module binds it. That cannot catch a scoping mistake,
    and it does catch the case this exists for — a call to a function that
    is simply not there.
    """
    tree = ast.parse(open(path, encoding="utf-8").read())
    bound = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            bound.add(node.name)
            for arg in getattr(node, "args", ast.arguments(
                    posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[],
                    defaults=[])).args if hasattr(node, "args") else []:
                bound.add(arg.arg)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.Global):
            bound.update(node.names)

    missing = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id not in bound):
            missing.append(f"{node.func.id} (line {node.lineno})")
    return missing


class TestNoScriptCallsWhatItCannotReach:
    def test_the_scan_finds_something(self):
        """**The floor.** Every assertion below is "no offenders", and a
        scan that read nothing is indistinguishable from a clean one."""
        paths = _script_paths()
        assert len(paths) >= 20, f"only {len(paths)} scripts found"
        total = sum(len(ast.parse(open(p, encoding="utf-8").read()).body)
                    for p in paths)
        assert total >= 200, f"only {total} top-level statements parsed"

    @pytest.mark.parametrize("path", _script_paths(),
                             ids=lambda p: os.path.basename(p))
    def test_nothing_is_defined_below_the_entry_point(self, path):
        stranded = definitions_below_the_guard(path)
        assert not stranded, (
            f"{os.path.basename(path)} defines {stranded} BELOW its "
            "`if __name__ == \"__main__\"` guard. Run as a script, main() "
            "executes before Python reaches them — importing the file hides "
            "this completely, which is why no test caught it.")

    @pytest.mark.parametrize("path", _script_paths(),
                             ids=lambda p: os.path.basename(p))
    def test_every_called_name_is_bound(self, path):
        missing = unresolved_calls(path)
        assert not missing, (
            f"{os.path.basename(path)} calls {missing}, which nothing in "
            "the file or its imports binds")

    def test_at_least_one_script_really_has_a_guard(self):
        """Otherwise the ordering check above passes by finding no guards."""
        with_guard = [p for p in _script_paths()
                      if _guard_line(ast.parse(
                          open(p, encoding="utf-8").read())) is not None]
        assert len(with_guard) >= 10, \
            f"only {len(with_guard)} scripts have a __main__ guard"


class TestTheCheckItselfCanSayNo:
    """Both detectors driven against files built to fail — otherwise the
    parametrised sweep above is a suite of "nothing is wrong" assertions
    with nothing proving it can find anything."""

    def test_a_definition_below_the_guard_is_caught(self, tmp_path):
        p = tmp_path / "bad.py"
        p.write_text(
            'def main():\n    return later()\n\n\n'
            'if __name__ == "__main__":\n    raise SystemExit(main())\n\n\n'
            'def later():\n    return 0\n', encoding="utf-8")

        assert definitions_below_the_guard(str(p)) == ["later"]

    def test_the_same_file_ABOVE_the_guard_is_clean(self, tmp_path):
        """The control on the control: it must not simply always fire."""
        p = tmp_path / "good.py"
        p.write_text(
            'def later():\n    return 0\n\n\n'
            'def main():\n    return later()\n\n\n'
            'if __name__ == "__main__":\n    raise SystemExit(main())\n',
            encoding="utf-8")

        assert definitions_below_the_guard(str(p)) == []
        assert unresolved_calls(str(p)) == []

    def test_a_call_to_nothing_is_caught(self, tmp_path):
        p = tmp_path / "missing.py"
        p.write_text('def main():\n    return _gone(1)\n', encoding="utf-8")

        assert any("_gone" in m for m in unresolved_calls(str(p)))

    def test_an_imported_name_is_not_reported_missing(self, tmp_path):
        p = tmp_path / "imports.py"
        p.write_text('from os.path import join\n\n\n'
                     'def main():\n    return join("a", "b")\n',
                     encoding="utf-8")

        assert unresolved_calls(str(p)) == []

    def test_a_file_with_no_guard_is_not_reported(self, tmp_path):
        p = tmp_path / "lib.py"
        p.write_text('def a():\n    return 1\n\n\ndef b():\n    return a()\n',
                     encoding="utf-8")

        assert definitions_below_the_guard(str(p)) == []


class TestTheRepairScriptSpecifically:
    """The one that crashed, pinned by name so the regression is legible."""

    PATH = os.path.join(SCRIPTS, "nmas-netbox-repair-addresses")

    def test_remove_excluded_is_reachable_from_main(self):
        assert "_remove_excluded" not in definitions_below_the_guard(self.PATH)

    def test_and_main_really_does_call_it(self):
        """Reachable and uncalled would satisfy the test above."""
        tree = ast.parse(open(self.PATH, encoding="utf-8").read())
        main = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        called = {n.func.id for n in ast.walk(main)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "_remove_excluded" in called


# ---------------------------------------------------------------------------
# Does it start at all when run the way the docs say to run it?
# ---------------------------------------------------------------------------

def _has_path_bootstrap(source: str) -> bool:
    """Does it put the repo root on `sys.path`? **Parsed, not matched.**

    There are two spellings in this repository and they are the same thing:

        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, ROOT)                       # nine scripts

        sys.path.insert(0, os.path.dirname(os.path.dirname(...)))   # five

    The first version of this check was the literal string
    `"sys.path.insert(0, ROOT)"` and reported the other five as broken — **a
    check matching one spelling of a construct**, which is the Gi1 link check
    blind to the extended format, one file over. Any `sys.path.insert` or
    `sys.path.append` counts; how the path is computed is not this check's
    business.

    A script importing `modules` without one works only with `PYTHONPATH`
    set — which is to say it works for whoever wrote it and for nobody
    following the documentation.
    """
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in ("insert", "append"):
            continue
        target = func.value
        if (isinstance(target, ast.Attribute) and target.attr == "path"
                and getattr(target.value, "id", "") == "sys"):
            return True
    return False


def _scripts():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    directory = os.path.join(root, "scripts")
    return [os.path.join(directory, n) for n in sorted(os.listdir(directory))
            if n.startswith("nmas-") and os.path.isfile(os.path.join(directory, n))]


def _imports_modules(source: str) -> bool:
    """Does it import from the `modules` package **anywhere**, including
    inside a function — which is where this project puts them."""
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "modules":
            return True
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == "modules" for a in node.names):
                return True
    return False


def test_the_bootstrap_scan_finds_something():
    """**The floor.** Both assertions below are set differences."""
    users = [p for p in _scripts()
             if _imports_modules(open(p, encoding="utf-8").read())]
    assert len(users) >= 10, (
        f"only {len(users)} scripts import `modules` — the scan is reading "
        "almost nothing")


def test_every_script_that_imports_modules_puts_the_root_on_sys_path():
    """The property that matters: *does this start when run the way the docs
    say to run it.*"""
    offenders = []
    for path in _scripts():
        source = open(path, encoding="utf-8").read()
        if _imports_modules(source) and not _has_path_bootstrap(source):
            offenders.append(os.path.basename(path))
    assert not offenders, (
        "these import `modules` and do not put the repo root on sys.path, so "
        f"they run only with PYTHONPATH set: {offenders}")


def test_a_script_that_imports_nothing_needs_no_bootstrap():
    """**The floor on the other side.** Requiring it everywhere would add two
    dead lines to `nmas-clab-targets`, which is deliberately dependency-free
    so the clab host can run it."""
    bare = [os.path.basename(p) for p in _scripts()
            if not _imports_modules(open(p, encoding="utf-8").read())]
    assert bare, "every script imports modules — this check proves nothing"


class TestHelpIsNotTheImportCheck:
    """**The proposed runnable check would not have caught it, measured.**

    `python3 scripts/<name> --help` passed on the broken script: argparse
    prints and exits **before** any function body runs, and this project
    imports `modules` *inside* functions to keep startup cheap. So `--help`
    proves the file parses and argparse is wired — and says nothing about
    whether the imports resolve.

    Worth pinning rather than dropping: `--help` catches other things, and the
    danger is somebody later reading it as the import check. Third time this
    session that a check could not exhibit the case it was written for.
    """

    def test_help_passes_on_a_script_with_no_bootstrap(self, tmp_path):
        import subprocess
        import sys

        script = tmp_path / "nmas-fake"
        script.write_text(
            "import argparse\n"
            "def main():\n"
            "    argparse.ArgumentParser().parse_args()\n"
            "    from modules import credentials\n"
            "    return 0\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        done = subprocess.run([sys.executable, str(script), "--help"],
                              capture_output=True, text=True, env=env,
                              cwd=str(tmp_path), timeout=30)
        assert done.returncode == 0
        assert "ModuleNotFoundError" not in done.stderr, (
            "--help reached the import after all — then it IS the check, and "
            "the static rule above can be reconsidered")

    def test_and_actually_running_it_does_catch_it(self, tmp_path):
        """The same script, invoked so the function body runs."""
        import subprocess
        import sys

        script = tmp_path / "nmas-fake"
        script.write_text(
            "def main():\n"
            "    from modules import credentials\n"
            "    return 0\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        done = subprocess.run([sys.executable, str(script)],
                              capture_output=True, text=True, env=env,
                              cwd=str(tmp_path), timeout=30)
        assert "ModuleNotFoundError" in done.stderr


def test_every_script_starts_when_run_bare():
    """Runnable, and kept for what it *does* catch: a syntax error, a broken
    argparse, a module-level statement that raises. Not the import check —
    see `TestHelpIsNotTheImportCheck`."""
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    broken = []
    for path in _scripts():
        try:
            done = subprocess.run([sys.executable, path, "--help"],
                                  capture_output=True, text=True, env=env,
                                  cwd=root, timeout=60)
        except subprocess.TimeoutExpired:
            broken.append(f"{os.path.basename(path)}: timed out on --help")
            continue
        if "Traceback" in done.stderr:
            first = next((l for l in done.stderr.splitlines() if "Error" in l),
                         done.stderr.splitlines()[-1] if done.stderr else "?")
            broken.append(f"{os.path.basename(path)}: {first.strip()}")
    assert not broken, "scripts that do not start: " + "; ".join(broken)


def test_the_bootstrap_check_accepts_BOTH_spellings():
    """The repository has two forms of one construct. A check that recognises
    one reports the other five scripts as broken — which the first version of
    this check did."""
    named = ("import os, sys\n"
             "ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
             "sys.path.insert(0, ROOT)\n")
    inline = ("import os, sys\n"
              "sys.path.insert(0, os.path.dirname(os.path.dirname("
              "os.path.abspath(__file__))))\n")
    assert _has_path_bootstrap(named)
    assert _has_path_bootstrap(inline)


def test_the_bootstrap_check_can_say_no():
    """**The floor.** A recogniser that accepted everything would make the
    rule above unfalsifiable."""
    assert not _has_path_bootstrap("import os, sys\nprint(sys.path)\n")
    assert not _has_path_bootstrap("from modules import credentials\n")
