"""The existing-test audit's tool (a), the deletion test (docs/TEST_AUDIT.md;
`scripts/nmas-test-audit-deletion`), run on its committed canary
(`docs/test_audit/canary/deletion/`, its files stored as `<name>.txt` so pytest never collects
them, copied here into a temporary folder under their real names, given an index so the tool's
copy reads it through `tests.source_index.tracked()`).

- **Every plant gets its own result and nothing else does:** a test asserting a function's
  result fails with it stubbed (and a method, stubbed by its qualname); a test calling it and
  asserting nothing, and one catching the stub's exception broadly, still pass and are listed;
  a test reaching a function whose text moved since the map is stale and is not run; a
  function defined twice makes its test not stubbable; a test the map names that no longer
  collects is said so, its file there or gone; a test whose own module calls the function at
  its import fails in collection, and says so.
- **The harness** (a function every test in the map reaches, here through the canary's
  conftest) is named and not stubbed; stubbing it fails every test that runs.
- **Why there are two stubs:** the raising stub alone fails the test that asserts nothing.
- **The stub** replaces only the body after the docstring, keeping the signature and the
  decorators, at the byte offsets `ast` gives (a non-ASCII line before it included).
"""
import ast
import importlib.machinery
import importlib.util
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANARY = os.path.join(ROOT, "docs", "test_audit", "canary", "deletion")
SCOPE = ("canarypkg/calc.py",)

T = "tests/test_calc.py"
EXPECTED_DELETION_RESULTS = {
    f"{T}::test_plant_double_value_fails_when_stubbed": "fails",
    f"{T}::TestPlantCounter::test_plant_bump_value_fails_when_stubbed": "fails",
    f"{T}::test_plant_double_asserts_nothing_still_passes": "still passes",
    f"{T}::test_plant_double_caught_broadly_still_passes": "still passes",
    f"{T}::test_plant_label_value_is_stale": "stale",
    f"{T}::test_plant_pick_is_not_stubbable": "not stubbable",
    f"{T}::test_plant_removed_since_the_map": "not collected",
    "tests/test_plant_file_removed.py::test_plant_in_a_file_removed_since_the_map":
        "not collected",
    "tests/test_plant_import_time.py::test_plant_fails_in_collection_when_stubbed": "fails",
}


def _tool():
    path = os.path.join(ROOT, "scripts", "nmas-test-audit-deletion")
    loader = importlib.machinery.SourceFileLoader("nmas_test_audit_deletion", path)
    mod = importlib.util.module_from_spec(
        importlib.util.spec_from_loader("nmas_test_audit_deletion", loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tool():
    return _tool()


@pytest.fixture
def canary(tmp_path):
    """The committed canary under its real names, in a folder with an index of its own."""
    from tests.source_index import track_all, tracked
    root = tmp_path / "ta-a-canary"
    copied = 0
    for src in tracked(CANARY):
        f = os.path.basename(src)
        assert f.endswith(".txt"), f"every canary file is stored as .txt: {f}"
        dst = root / os.path.relpath(src, CANARY)[: -len(".txt")]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied += 1
    assert copied >= 8, "floor: the canary's eight files are committed"
    return track_all(root)


def _run(tool, canary, tmp_path, **kw):
    return tool.audit(canary, os.path.join(canary, "reach"),
                      then=os.path.join(canary, "reach", "then"), scope=SCOPE,
                      python=sys.executable, jobs=2, workdir=str(tmp_path), **kw)


def test_every_plant_gets_its_own_result_and_the_harness_is_named(tool, canary, tmp_path):
    out = _run(tool, canary, tmp_path)
    got = {r[0]: r[3] for r in out["rows"]}
    assert got == EXPECTED_DELETION_RESULTS, (
        f"differs: {sorted(set(got.items()) ^ set(EXPECTED_DELETION_RESULTS.items()))}")
    assert out["errors"] == []
    why = {r[0]: r[4] for r in out["rows"] if r[3] == "not collected"}
    assert "its file is not in the copy" in why[
        "tests/test_plant_file_removed.py::test_plant_in_a_file_removed_since_the_map"]
    assert "the copy's collection does not list it" in why[
        f"{T}::test_plant_removed_since_the_map"]
    assert out["plan"]["harness"] == ["canarypkg/calc.py::harness"]
    assert sorted(out["plan"]["stale"]) == ["canarypkg/calc.py::label"]
    collecting = {r[0]: r[4] for r in out["rows"]}[
        "tests/test_plant_import_time.py::test_plant_fails_in_collection_when_stubbed"]
    assert "raise: error (1 error) in collection" in collecting, collecting
    listed = {r[0]: r for r in out["rows"] if r[3] == "still passes"}
    assert listed[f"{T}::test_plant_double_asserts_nothing_still_passes"][4].count("none: passed")
    assert listed[f"{T}::test_plant_double_caught_broadly_still_passes"][4].count("raise: passed")
    assert os.listdir(tmp_path) == ["ta-a-canary"], "the tool's copies are removed"


def test_the_raising_stub_alone_fails_the_test_that_asserts_nothing(tool, canary, tmp_path):
    out = _run(tool, canary, tmp_path, stubs=("raise",))
    got = {r[0]: r[3] for r in out["rows"]}
    assert got[f"{T}::test_plant_double_asserts_nothing_still_passes"] == "fails"
    assert got[f"{T}::test_plant_double_caught_broadly_still_passes"] == "still passes"


def test_stubbing_the_harness_fails_every_test_that_runs(tool, canary, tmp_path):
    out = _run(tool, canary, tmp_path, stub_harness=True)
    ran = {r[0]: r for r in out["rows"]
           if r[3] not in ("stale", "not collected", "not stubbable")}
    assert len(ran) == 5
    assert {r[3] for r in ran.values()} == {"fails"}
    # Under the raising stub the import-time plant's file does not collect before any fixture
    # runs; every other test errors in its setup, at the conftest's call of the harness.
    raising = {t: next(x for x in r[4].split("; ") if x.startswith("raise: "))
               for t, r in ran.items()}
    imported = "tests/test_plant_import_time.py::test_plant_fails_in_collection_when_stubbed"
    assert raising.pop(imported).startswith("raise: error (1 error) in collection")
    assert all(x.startswith("raise: error (1 error) in setup") for x in raising.values()), raising


SOURCE = '''"""Ünïcode before the functions moves byte offsets past character ones."""
import functools


def plain(a, b=2, *args, **kw):
    """Its docstring stays."""
    x = a + b
    return x


def one_line(a): return a


def install(app):
    """Its first statement is decorated: the `@` line comes before the statement's own line."""

    @app.after_request
    def _inner(response):
        return response
    return app


class Holder:
    @functools.lru_cache(maxsize=None)
    def cached(self, n):  # a comment on the def line
        return {"ü": n}
'''


def test_the_stub_keeps_signature_decorators_and_docstring(tool):
    new, refused = tool.stub_source(SOURCE, {"plain", "one_line", "install", "Holder.cached"})
    assert refused == {}
    tree = ast.parse(new)
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert set(funcs) == {"plain", "one_line", "install", "cached"}, "the nested one is gone"
    assert "@app.after_request" not in new
    assert ast.get_docstring(funcs["plain"]) == "Its docstring stays."
    assert [a.arg for a in funcs["plain"].args.args] == ["a", "b"]
    assert funcs["plain"].args.vararg.arg == "args" and funcs["plain"].args.kwarg.arg == "kw"
    assert ast.unparse(funcs["cached"].decorator_list[0]) == "functools.lru_cache(maxsize=None)"
    for name, node in funcs.items():
        body = node.body[1:] if ast.get_docstring(node) else node.body
        assert [ast.unparse(s) for s in body] == ["raise NotImplementedError('deletion audit')"], name
    assert "Ünïcode" in new and "# a comment on the def line" in new
    none, _ = tool.stub_source(SOURCE, {"plain"}, stub=tool.STUBS["none"])
    assert "    return None\n" in none and "x = a + b" not in none


def test_a_name_defined_nowhere_or_twice_is_refused_by_name(tool):
    src = "import sys\nif sys:\n    def f():\n        return 1\nelse:\n    def f():\n        return 2\n"
    new, refused = tool.stub_source(src, {"f", "g"})
    assert new is None
    assert refused == {"f": "defined 2 times in the module",
                       "g": "no counted definition of it in the module"}
