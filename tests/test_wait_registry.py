"""The wait registry (modules/waits.py; the operator's standing rule R3, 2026-11-14: "Every sleep,
settle, grace or timeout in the code declares what it waits for and why. A test fails on an
undeclared one").

**The population, by property** (`sites`): every place in the product's Python (`SCANNED`:
app.py, modules/, routes/, and the scripts and helpers under scripts/ and deploy/ whose first
line runs Python; tracked files only, `tests.source_index.tracked`) that blocks for a time or
sets the time a loop ends:
- a call to a sleep: a callee named ``sleep`` or ending ``_sleep`` (``time.sleep``, an injected
  ``src.sleep``, ``ctx.settle_sleep``), also as one side of an ``or``
  (``(ctx.settle_sleep or time.sleep)(remaining)``);
- a timed wait: ``X.wait(t)`` (one argument, or ``timeout=``) whose ``X`` is not a module the
  file imports (``Q.wait(Q.limits(...))`` is a module's function that computes a timeout, not
  a wait), and ``X.join(timeout=...)``;
- a deadline: an assignment to a name or attribute whose name holds ``deadline``.

**What the scan assumes stays true**: a sleep is called under a name ending ``sleep``; a timed
wait is a method named ``wait``; a deadline is named so. A bound on one call
(``subprocess.run(timeout=)``, an HTTP client's ``timeout``) is not in this population: it
bounds a call that ends when it answers, and is its own row (the registry's docstring says
so). Shell scripts are not parsed here.

Each site is keyed ``<path>::<function's qualified name>`` (``<module>`` at module level); one
entry declares every wait in that function. The registry may not hold an entry no site has
(a stale entry would declare a wait that is gone).
"""

import ast
import os
import re

import pytest

from tests.source_index import ROOT, track_all, tracked

#: The product's folders and files the scan reads.
SCANNED = ("app.py", "modules", "routes", "scripts", "deploy")
#: The fewest sites the scan must find in the checkout (106 in 79 functions on 2026-11-14, when
#: the registry was built): a scan that found far fewer has stopped reading a folder.
FEWEST_SITES = 95
#: A "measured" entry names its date.
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")


def is_python(path) -> bool:
    if str(path).endswith(".py"):
        return True
    try:
        with open(path, "rb") as fh:
            first = fh.readline()
    except OSError:
        return False
    return first.startswith(b"#!") and b"python" in first


def _callee(func) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _is_sleep(func) -> bool:
    if isinstance(func, ast.BoolOp):
        return any(_is_sleep(v) for v in func.values)
    name = _callee(func)
    return name == "sleep" or name.endswith("_sleep")


def _imported(tree) -> set:
    """Every name an import binds anywhere in the module (a function's own import too)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.update(a.asname or a.name for a in node.names)
    return out


def _names(node) -> list:
    """The upper-case names (constants) an expression refers to."""
    out = []
    # A module or object an attribute is read from (`D` of `D.DELTA_SECONDS`) is not a constant.
    owners = {id(n.value) for n in ast.walk(node) if isinstance(n, ast.Attribute)}
    for n in ast.walk(node):
        if id(n) in owners:
            continue
        name = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else ""
        if name and name.upper() == name and any(c.isalpha() for c in name):
            out.append(name)
    return out


def sites(source: str) -> list:
    """``[{"where", "line", "kind", "names"}]``: each wait in *source* (the module's text),
    *where* its function's qualified name."""
    tree = ast.parse(source)
    modules = _imported(tree)
    out = []

    def add(kind, where, node, expr):
        out.append({"where": where or "<module>", "line": node.lineno, "kind": kind,
                    "names": _names(expr) if expr is not None else []})

    def walk(node, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                walk(child, stack + [child.name])
                continue
            where = ".".join(stack)
            if isinstance(child, ast.Call):
                f = child.func
                if _is_sleep(f):
                    add("sleep", where, child, child.args[0] if child.args else None)
                elif isinstance(f, ast.Attribute) and f.attr == "wait":
                    recv = f.value
                    timed = (len(child.args) == 1 and not child.keywords) or any(
                        k.arg == "timeout" for k in child.keywords)
                    if timed and not (isinstance(recv, ast.Name) and recv.id in modules):
                        add("wait", where, child, child.args[0] if child.args else
                            next(k.value for k in child.keywords if k.arg == "timeout"))
                elif isinstance(f, ast.Attribute) and f.attr == "join" and any(
                        k.arg == "timeout" for k in child.keywords):
                    add("wait", where, child,
                        next(k.value for k in child.keywords if k.arg == "timeout"))
            if isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for t in targets:
                    name = (t.id if isinstance(t, ast.Name) else
                            t.attr if isinstance(t, ast.Attribute) else "")
                    if "deadline" in name.lower():
                        add("deadline", where, child, child.value)
            walk(child, stack)

    walk(tree, [])
    return out


def scan(root=None) -> dict:
    """``{key: [site, ...]}`` over the tracked product files under *root* (the checkout)."""
    base = str(root or ROOT)
    out = {}
    for path in tracked(*SCANNED, root=root):
        if not is_python(path):
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        rel = os.path.relpath(path, base).replace(os.sep, "/")
        for s in sites(text):
            out.setdefault(f"{rel}::{s['where']}", []).append(s)
    return out


@pytest.fixture(scope="module")
def found():
    return scan()


def _shown(key, ss):
    return f"{key} (line{'s' if len(ss) > 1 else ''} {', '.join(str(s['line']) for s in ss)})"


class TestEveryWaitIsDeclared:
    def test_the_scan_reads_the_whole_product(self, found):
        n = sum(len(v) for v in found.values())
        assert n >= FEWEST_SITES, f"the scan found {n} waits, fewer than {FEWEST_SITES}"
        folders = {k.split("/", 1)[0] for k in found}
        assert {"modules", "scripts", "deploy"} <= folders, folders

    def test_every_wait_is_declared(self, found):
        from modules.waits import WAITS
        missing = [_shown(k, v) for k, v in sorted(found.items()) if k not in WAITS]
        assert not missing, (
            "a wait the registry does not declare (modules/waits.py, R3: every sleep, settle, "
            "grace or timeout declares what it waits for and why):\n  " + "\n  ".join(missing))

    def test_no_entry_declares_a_wait_that_is_gone(self, found):
        from modules.waits import WAITS
        stale = sorted(k for k in WAITS if k not in found)
        assert not stale, f"entries with no wait at that place any more: {stale}"

    def test_each_entry_says_what_why_how_and_whether_it_ends_early(self):
        from modules.waits import BASES, WAITS
        for key, w in WAITS.items():
            assert set(w) == {"waits_for", "why", "basis", "early", "constants"}, key
            assert w["waits_for"].strip() and w["why"].strip(), key
            assert w["basis"] in BASES, (key, w["basis"])
            assert isinstance(w["early"], bool), key
            if w["basis"] == "measured":
                assert DATE.search(w["why"]), f"{key}: a measurement names its date"
            if w["basis"] == "unclassified":
                assert "the full wait, safe by default" in w["why"], key

    def test_each_constant_a_wait_is_named_by_is_declared_with_it(self, found):
        from modules.waits import WAITS
        wrong = []
        for key, ss in sorted(found.items()):
            if key not in WAITS:
                continue
            named = {n for s in ss for n in s["names"]}
            left = sorted(named - set(WAITS[key]["constants"]))
            if left:
                wrong.append(f"{key}: {left}")
        assert not wrong, "constants a wait's length is named by, not declared:\n  " + \
            "\n  ".join(wrong)


PLANTED = '''\
import threading
import time
from modules import history_logq as Q

STEP_S = 3


def polls(clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + 60
    while clock() < deadline:
        sleep(STEP_S)


class Keeper:
    def run(self, ctx):
        (ctx.settle_sleep or time.sleep)(1)
        self._done.wait(timeout=5)
        self._thread.join(timeout=2)

    def words(self, items):
        return ", ".join(items), Q.wait(Q.limits("n")), self._done.wait()
'''


class TestThePlantedWaits:
    def test_the_scan_finds_each_planted_wait_and_nothing_else(self, tmp_path):
        """A planted module's every kind of wait is found where it is, by kind, with the
        constant it names; a string join, a module's own `wait` function and a wait with no
        time are not waits."""
        (tmp_path / "modules").mkdir()
        (tmp_path / "modules" / "planted.py").write_text(PLANTED, encoding="utf-8")
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "nmas-planted").write_text(
            "#!/usr/bin/env python3\nimport time\n\n\ndef main():\n    time.sleep(2)\n",
            encoding="utf-8")
        (tmp_path / "scripts" / "nmas-shell").write_text("#!/bin/sh\nsleep 5\n",
                                                         encoding="utf-8")
        got = scan(track_all(tmp_path))
        assert {k: [(s["kind"], s["names"]) for s in v] for k, v in got.items()} == {
            "modules/planted.py::polls": [("deadline", []), ("sleep", ["STEP_S"])],
            "modules/planted.py::Keeper.run": [("sleep", []), ("wait", []), ("wait", [])],
            "scripts/nmas-planted::main": [("sleep", [])],
        }

    def test_an_undeclared_planted_wait_is_named_by_the_check(self, tmp_path):
        from modules.waits import WAITS
        (tmp_path / "modules").mkdir()
        (tmp_path / "modules" / "planted.py").write_text(PLANTED, encoding="utf-8")
        got = scan(track_all(tmp_path))
        missing = [_shown(k, v) for k, v in sorted(got.items()) if k not in WAITS]
        assert missing == ["modules/planted.py::Keeper.run (lines 16, 17, 18)",
                           "modules/planted.py::polls (lines 9, 11)"]


class TestR3sWaits:
    """The waits the verify-speed work changed say so in their declarations."""

    def test_the_bgp_hold_is_the_devices_timer_and_skipped_for_what_cannot_reach_it(self):
        from modules.waits import WAITS
        w = WAITS["modules/pipeline.py::_watch_bgp_hold"]
        assert w["basis"] == "device timer" and "bgp_reach" in w["why"]

    def test_the_resubscribe_verify_ends_early_on_its_direct_checks(self):
        from modules.waits import WAITS
        w = WAITS["modules/heal/resubscribe.py::verify"]
        assert w["early"] is True and "DIRECT_POLL_S" in w["constants"]

    def test_a_cosmetic_heal_does_not_wait_on_its_symptom(self):
        from modules.waits import WAITS
        assert "readback_only" in WAITS["modules/heal/act.py::read_symptom"]["why"]
