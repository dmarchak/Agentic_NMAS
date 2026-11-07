"""One Python floor, stated alike everywhere (C2634; the operator, 2026-11-06: "raise the
documented floor to 3.12", and "make every other statement of the floor match").

- app.py's first statements import only `sys` and refuse an interpreter below `PYTHON_FLOOR`,
  before any other import (an older Python would otherwise die on a SyntaxError deep in an
  import, naming nothing).
- Every statement of Mercury's floor in the documents that state one (CLAUDE.md, README.md,
  docs/ARCHITECTURE.md, docs/DEPLOY_LINUX.md), found by its shape ("Python 3.N+", "Python 3.N
  or later"), names the same version as app.py; at least four are found (a floor), and a
  planted older statement is caught.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ("CLAUDE.md", "README.md", "docs/ARCHITECTURE.md", "docs/DEPLOY_LINUX.md")
#: A floor's shape. "a Python 3.13+ shim" (CLAUDE.md, telnetlib.py) names where a shim starts
#: to be needed, not the floor, and is left out by its own word.
STATEMENT = re.compile(r"Python (3\.\d+)(?:\+| or later)(?! shim)")


def _floor():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PYTHON_FLOOR"
                                                for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("app.py declares no PYTHON_FLOOR")


def statements(text):
    return STATEMENT.findall(text)


def test_app_refuses_an_older_interpreter_before_any_other_import():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    body = tree.body
    imports = [i for i, n in enumerate(body)
               if isinstance(n, (ast.Import, ast.ImportFrom, ast.Try))]
    check = next(i for i, n in enumerate(body) if isinstance(n, ast.If)
                 and "PYTHON_FLOOR" in ast.unparse(n.test)
                 and "version_info" in ast.unparse(n.test))
    assert ast.unparse(body[imports[0]]) == "import sys as _sys", ast.unparse(body[imports[0]])
    assert all(i > check for i in imports[1:]), "an import runs before the floor's check"
    assert "exit" in ast.unparse(body[check].body[0])
    assert _floor() == (3, 12)


def test_every_documented_floor_names_the_same_version():
    want = ".".join(map(str, _floor()))
    found = {d: statements((ROOT / d).read_text(encoding="utf-8")) for d in DOCS}
    assert sum(len(v) for v in found.values()) >= 4, found
    wrong = {d: v for d, v in found.items() if any(s != want for s in v)}
    assert not wrong, f"floor statements that are not {want}: {wrong}"


def test_a_planted_older_statement_is_found():
    assert statements("Needs Python 3.10 or later, and Python 3.12+ is tested.") == \
        ["3.10", "3.12"]
    assert statements("telnetlib.py is a Python 3.13+ shim") == []
