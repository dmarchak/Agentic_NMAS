"""C119, found by its own annotation: `if not os.path.exists(d): os.mkdir(d)`
in app.py raced when two parallel workers imported the app on a fresh
checkout, and ten rotation tests failed with FileExistsError on some CI runs
and not others. An old race the parallel scheduler exposed, not a new order
dependence. The shape is refused across the program and its scripts: create
with exist_ok, never check first."""

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sources():
    for top in ("modules", "routes", "scripts"):
        for d, _dirs, files in os.walk(os.path.join(ROOT, top)):
            for f in files:
                if f.endswith(".py") or (top == "scripts" and "." not in f):
                    yield os.path.join(d, f)
    yield os.path.join(ROOT, "app.py")


def check_then_create(src: str) -> list:
    """Line numbers of `if not <path>.exists/isdir(...)` whose body creates a
    directory without exist_ok."""
    out = []
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp)
                and isinstance(node.test.op, ast.Not)
                and isinstance(node.test.operand, ast.Call)
                and getattr(node.test.operand.func, "attr", "") in ("exists", "isdir")):
            continue
        for stmt in node.body:
            for c in ast.walk(stmt):
                if (isinstance(c, ast.Call) and getattr(c.func, "attr", "") in ("mkdir", "makedirs")
                        and not any(k.arg == "exist_ok" for k in c.keywords)):
                    out.append(node.lineno)
    return out


def test_no_directory_is_created_after_a_check():
    found, scanned = {}, 0
    for path in _sources():
        try:
            src = open(path, encoding="utf-8").read()
            lines = check_then_create(src)
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
        scanned += 1
        if lines:
            found[os.path.relpath(path, ROOT)] = lines
    assert scanned >= 150, scanned
    assert found == {}, found


def test_the_scan_sees_the_shape_it_refuses():
    assert check_then_create("import os\nif not os.path.exists(d):\n    os.mkdir(d)\n") == [2]
    assert check_then_create("import os\nos.makedirs(d, exist_ok=True)\n") == []
