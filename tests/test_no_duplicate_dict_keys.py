"""A dict literal with a duplicate key keeps the LATER value, silently.

Found 2026-09-27 building 7.1 step 2 (C85): a new `RENDERS` entry for
`GET /netbox/status` was dropped without a word by an older entry further
down the same literal. The payload check then examined the old entry, whose
fixture could not reach a stored import, and 22 tests passed about a route
they did not look at; a planted key proved it. The same shape in
`route_gates.GATES` would silently drop a gate, and in an allowlist would
silently drop an exemption's reason. So: no dict literal with constant keys
may repeat one, anywhere in the program or its tests.
"""

import ast
import collections
import os

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _python_files():
    out = [os.path.join(ROOT, "app.py")]
    out += tracked("modules", "routes", "tests", suffix=".py")
    for f in tracked("scripts", recursive=False):
        if os.path.isfile(f):
            with open(f, encoding="utf-8", errors="ignore") as fh:
                first = fh.readline()
            if first.startswith("#!") and "python" in first:
                out.append(f)
    return out


def duplicates(source: str) -> list:
    """``[(line, [repeated keys])]`` for every dict literal in *source*."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            keys = [repr(k.value) for k in node.keys if isinstance(k, ast.Constant)]
            dup = sorted(k for k, n in collections.Counter(keys).items() if n > 1)
            if dup:
                out.append((node.lineno, dup))
    return out


def test_no_dict_literal_repeats_a_key():
    found, scanned = [], 0
    for path in _python_files():
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        scanned += sum(1 for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Dict))
        found += [(os.path.relpath(path, ROOT), line, dup) for line, dup in duplicates(src)]
    assert scanned >= 4000, scanned            # measured 4,530 with constant keys
    assert found == [], found


def test_the_scanner_finds_one():
    """Control: the exact shape that hid the NetBox entry."""
    src = 'RENDERS = {"GET /netbox/status": 1, "GET /x": 2, "GET /netbox/status": 3}\n'
    assert duplicates(src) == [(1, ["'GET /netbox/status'"])]
