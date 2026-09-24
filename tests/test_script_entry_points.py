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
