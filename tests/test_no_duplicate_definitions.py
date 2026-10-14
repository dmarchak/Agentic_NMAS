"""No module or class defines the same name twice (C90's sibling).

A second `def` of a name silently replaces the first, as a repeated dict key
keeps the later value. Found adding the suite's timeout report (2026-09-28):
a second `pytest_sessionstart` in tests/conftest.py would have replaced the
first, and with it the check that stops an unconfined run (C46). Nothing
errors, the source reads correctly, and the suite passes, which is why only a
scan finds it. Inside a test class it silently drops the earlier TEST.

Scanned: every function and class defined directly in a module body or a
class body, in the program, its scripts and its tests. A property's
`@<name>.setter` / `.getter` / `.deleter` is the one legitimate repeat.

The definitions come from `scripts/pydefs.py`, the one walker the coverage tool
(scripts/nmas_coverage.py) counts functions with: one answer to "what does this
module define".
"""

import importlib.util
import os

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location("pydefs", os.path.join(ROOT, "scripts",
                                                                      "pydefs.py"))
pydefs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pydefs)


def duplicates(source: str, label: str = "") -> list:
    """The shared walker's answer (`scripts/pydefs.duplicates`)."""
    return pydefs.duplicates(source, label)


def _files():
    out = [f for f in tracked(suffix=".py")
           if "node_modules" not in f and os.sep + "." not in f[len(ROOT):]]
    for f in tracked("scripts", recursive=False):
        if os.path.isfile(f) and not f.endswith(".py"):
            with open(f, encoding="utf-8", errors="ignore") as fh:
                first = fh.readline()
            if first.startswith("#!") and "python" in first:
                out.append(f)
    return out



def test_no_name_is_defined_twice():
    files, found = _files(), []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            try:
                found += duplicates(fh.read(), os.path.relpath(f, ROOT))
            except SyntaxError:
                continue
    assert len(files) >= 300, f"only {len(files)} files scanned: the listing found too little"
    assert found == [], found


def test_the_scan_finds_the_shape():
    """The control: the exact near-miss, and a dropped test method."""
    src = ("def pytest_sessionstart(s):\n    pass\n\n"
           "def pytest_sessionstart(s):\n    pass\n\n"
           "class TestX:\n    def test_a(self): pass\n    def test_a(self): pass\n")
    assert duplicates(src) == [":pytest_sessionstart: lines 1 and 4",
                               ":TestX.test_a: lines 8 and 9"]


def test_a_property_setter_is_not_a_duplicate():
    """The floor on the exemption: the real case in modules/pipeline.py."""
    src = ("class C:\n    @property\n    def x(self): return 1\n"
           "    @x.setter\n    def x(self, v): pass\n")
    assert duplicates(src) == []
    with open(os.path.join(ROOT, "modules", "pipeline.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert "@rendered_commands.setter" in text, "the anchor for the exemption moved"
