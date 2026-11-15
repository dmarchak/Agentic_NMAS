"""The AI uses Mercury itself (C3718; the operator's principle, 2026-11-14): every AI tool is a
Mercury feature a person can also use, the AI calling the same code, declared in
tests/ai_tool_homes.py, or it is a finding named there by its row.

- **Every tool is declared:** each tool the code declares (`ai_tool_homes.tools`: the command
  families, Mercury's own reads, the host reads, the plan engine's step kinds and the catalog's
  operations) is in `HOMES` or `MISSING`, never both; a planted undeclared tool is found.
- **Every home is real:** its endpoint is one of the app's v2 routes, and the module it names is
  imported on the person's side (the endpoint's own module, or the one its *where* names), so
  the person's control and the AI reach one piece of code; a planted home naming no route is
  found, as is one whose person's side does not import its module.
- **Every gap names its row:** each `MISSING` entry names a C-row of the register.

No device, no network, no AI call.
"""
import ast
import importlib
import inspect
import pathlib
import re

import pytest

from tests import ai_tool_homes as H

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _app():
    import app as APP

    return APP.app


def _imports(module_name: str) -> set:
    """Every module *module_name*'s source imports, anywhere in it, by its full dotted name
    (``from modules import x`` gives ``modules.x``; ``from modules.x import y`` gives both)."""
    mod = importlib.import_module(module_name)
    tree = ast.parse(pathlib.Path(inspect.getsourcefile(mod)).read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
    return out


def faults(homes: dict) -> list:
    """What is wrong with each home of *homes*: an endpoint that is not one of the app's routes
    or not under /v2/, a module that is not importable, and a person's side that does not
    import it."""
    rules = {}
    for rule in _app().url_map.iter_rules():
        rules.setdefault(rule.endpoint, []).append(rule.rule)
    out = []
    for tool, home in sorted(homes.items()):
        ep, via = home.get("endpoint") or "", home.get("via") or ""
        if ep not in rules:
            out.append((tool, f"{ep!r} is no route of the app"))
            continue
        if not all(r.startswith("/v2/") for r in rules[ep]):
            out.append((tool, f"{ep!r} is not a v2 route ({rules[ep]})"))
        try:
            importlib.import_module(via)
        except ImportError:
            out.append((tool, f"{via!r} is not a module"))
            continue
        where = home.get("where") or _app().view_functions[ep].__module__
        if via not in _imports(where):
            out.append((tool, f"{where} does not import {via}"))
    return out


class TestEveryToolIsDeclared:
    def test_every_tool_is_in_homes_or_missing(self):
        found = H.tools()
        assert len(found) >= 20, found                # the floor: the five families today
        assert H.undeclared() == [], H.undeclared()

    def test_none_is_in_both(self):
        assert set(H.HOMES) & set(H.MISSING) == set()

    def test_every_declared_tool_is_one_the_code_declares(self):
        """A home or a gap for a tool the code no longer has is a stale line."""
        found = set(H.tools())
        assert sorted(set(H.HOMES) - found) == [] and sorted(set(H.MISSING) - found) == []

    def test_a_planted_undeclared_tool_is_found(self, monkeypatch):
        from modules.ai import fixit_reads

        monkeypatch.setattr(fixit_reads, "OWN", fixit_reads.OWN + (
            ("planted", "a read only the AI has", None),))
        assert H.undeclared() == [("own", "planted")]


class TestEveryHomeIsReal:
    def test_each_home_is_a_v2_route_on_the_same_code(self):
        assert faults(H.HOMES) == []

    def test_a_planted_home_naming_no_route_is_found(self):
        planted = {("own", "planted"): {"endpoint": "v2.no_such_page",
                                        "via": "modules.neighbours"}}
        assert faults(planted) == [(("own", "planted"), "'v2.no_such_page' is no route of the app")]

    def test_a_planted_home_on_other_code_is_found(self):
        """Show commands' route does not import the neighbours reader, so it is no home of a
        read by it."""
        planted = {("own", "planted"): {"endpoint": "reads_v2.show_commands_run",
                                        "via": "modules.neighbours"}}
        assert faults(planted) == [(("own", "planted"),
                                    "routes.reads_v2 does not import modules.neighbours")]


class TestEveryGapNamesItsRow:
    def test_each_missing_names_a_register_row(self):
        register = (ROOT / "docs" / "OPEN_FINDINGS.md").read_text()
        for tool, why in H.MISSING.items():
            m = re.match(r"(C\d+): \S", why)
            assert m, (tool, why)
            assert re.search(rf"^\| {m.group(1)} \|", register, re.M), (tool, m.group(1))
