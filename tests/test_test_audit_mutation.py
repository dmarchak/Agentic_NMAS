"""The existing-test audit's tool (b), mutation per test (docs/TEST_AUDIT.md;
`scripts/nmas-test-audit-mutation`), run on its committed canary
(`docs/test_audit/canary/mutation/`, its files stored as `<name>.txt` so pytest never collects
them, copied here into a temporary folder under their real names, given an index so the tool's
copy reads it through `tests.source_index.tracked()`).

- **Every test's kills, exactly, and the weak one listed:** `fee`'s four mutants (mutmut 3.8.0's,
  committed in the canary's `mutants.json`) run against all five of its covering tests in one
  pytest process each, every failure recorded: the test killing all four, the one killing one,
  the one reaching `fee` only in a child process (the mutant is in the copy's file), the one
  killed in its file's collection, and the planted weak test, which fails when `fee` raises and
  kills none of the four, the only one listed; the test failing unmutated is never judged.
- **The canaries come first:** a must-die canary that survives, or a null canary that is
  killed, stops the run before any audited mutant runs, and no result stands.
- **Nothing is run blind:** a function whose text moved since its mutants were made is stale; a
  mutant whose lines fall outside its function, or whose module does not parse, is refused.
- **The cost is said before a run:** `--estimate` prints mutants x covering tests x seconds,
  from the map and the mutants file, running nothing.
- **A selection of no function is refused** (a scan with nothing in it says nothing).
"""
import ast
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANARY = os.path.join(ROOT, "docs", "test_audit", "canary", "mutation")
SCOPE = ("canarypkg/fees.py",)
MUST_DIE = ("canarypkg/fees.py::must_die=tests/test_fees.py::test_plant_must_die",)
NULL = ("canarypkg/fees.py::untested=tests/test_fees.py",)
FEE = "canarypkg/fees.py::fee"

T = "tests/test_fees.py"
#: Each covering test of `fee`: its result, and the mutants it kills.
EXPECTED = {
    f"{T}::test_plant_fee_kills_all": ("kills some", f"{FEE}: 1, 2, 3, 4"),
    f"{T}::test_plant_fee_kills_one": ("kills some", f"{FEE}: 3"),
    f"{T}::test_plant_fee_in_a_child_kills_three": ("kills some", f"{FEE}: 1, 2, 4"),
    "tests/test_plant_import_time.py::test_plant_killed_in_collection":
        ("kills some", f"{FEE}: 1, 2, 4"),
    f"{T}::test_plant_fee_kills_none": ("kills none", ""),
    f"{T}::test_plant_fee_fails_unmutated": ("fails unmutated", ""),
}
CHILD = f"{T}::test_plant_fee_in_a_child_kills_three"
IMPORT = "tests/test_plant_import_time.py::test_plant_killed_in_collection"
#: Each mutant of `fee`: what it changes, and every test that kills it.
EXPECTED_MUTANTS = {
    "canarypkg.fees.x_fee__mutmut_1": ("if amount < 100:", "if amount <= 100:",
                                       [CHILD, f"{T}::test_plant_fee_kills_all", IMPORT]),
    "canarypkg.fees.x_fee__mutmut_2": ("if amount < 100:", "if amount < 101:",
                                       [CHILD, f"{T}::test_plant_fee_kills_all", IMPORT]),
    "canarypkg.fees.x_fee__mutmut_3": ("return 3", "return 4",
                                       [f"{T}::test_plant_fee_kills_all",
                                        f"{T}::test_plant_fee_kills_one"]),
    "canarypkg.fees.x_fee__mutmut_4": ("return 0", "return 1",
                                       [CHILD, f"{T}::test_plant_fee_kills_all", IMPORT]),
}


def _tool():
    path = os.path.join(ROOT, "scripts", "nmas-test-audit-mutation")
    loader = importlib.machinery.SourceFileLoader("nmas_test_audit_mutation", path)
    mod = importlib.util.module_from_spec(
        importlib.util.spec_from_loader("nmas_test_audit_mutation", loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tool():
    return _tool()


@pytest.fixture
def canary(tmp_path):
    """The committed canary under its real names, in a folder with an index of its own."""
    from tests.source_index import track_all, tracked
    root = tmp_path / "ta-b-canary"
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


def _fingerprint(root):
    out = {}
    for d, _sub, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            if "/.git/" not in p + "/":
                with open(p, "rb") as fh:
                    out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def _run(tool, canary, tmp_path, canaries=MUST_DIE, null=NULL, **kw):
    return tool.audit(canary, os.path.join(canary, "reach"), os.path.join(canary, "mutants.json"),
                      then=os.path.join(canary, "reach", "then"), scope=SCOPE,
                      canaries=canaries, null_canaries=null, python=sys.executable, jobs=2,
                      workdir=str(tmp_path), **kw)


def test_every_test_gets_its_exact_kills_and_only_the_weak_one_is_listed(tool, canary, tmp_path):
    before = _fingerprint(canary)
    out = _run(tool, canary, tmp_path)
    assert out["errors"] == [] and out["canary_broken"] == []
    got = {r[0]: (r[4], r[3]) for r in out["rows"]}
    assert got == EXPECTED, f"differs: {sorted(set(got.items()) ^ set(EXPECTED.items()))}"
    assert [r[0] for r in out["rows"] if r[4] == "kills none"] == [f"{T}::test_plant_fee_kills_none"]
    weak = {r[0]: r for r in out["rows"]}[f"{T}::test_plant_fee_kills_none"]
    assert weak[2] == "4", "the weak test was judged against all four mutants"
    assert "reach check failed it in 1 of 1 functions" in weak[5], (
        "it fails when fee raises: it reaches fee, and kills none of its mutants")
    mutants = {r[0]: (r[5], r[6], r[4].split(", ")) for r in out["mutant_rows"]}
    assert mutants == EXPECTED_MUTANTS
    assert {r[3] for r in out["mutant_rows"]} == {"killed"}
    assert [(k, w, n, bad) for k, w, n, _p, bad in out["canaries"]] == [
        ("canarypkg/fees.py::must_die", "killed", 2, []),
        ("canarypkg/fees.py::untested", "survived", 1, [])]
    assert _fingerprint(canary) == before, "the root is only read"
    assert os.listdir(tmp_path) == ["ta-b-canary"], "the tool's copies are removed"


def test_a_must_die_canary_that_survives_stops_the_run(tool, canary, tmp_path):
    out = _run(tool, canary, tmp_path,
               canaries=("canarypkg/fees.py::must_die=tests/test_fees.py::test_plant_fee_kills_all",))
    assert out["canary_broken"] == [
        "canarypkg/fees.py::must_die (every mutant to be killed): mutant 1 survived "
        "(return n + 1 -> return n - 1); mutant 2 survived (return n + 1 -> return n + 2)"]
    assert out["rows"] == [] and out["mutant_rows"] == [], "no result stands"


def test_a_null_canary_that_is_killed_stops_the_run(tool, canary, tmp_path):
    out = _run(tool, canary, tmp_path, canaries=(),
               null=("canarypkg/fees.py::must_die=tests/test_fees.py",))
    assert out["canary_broken"] == [
        "canarypkg/fees.py::must_die (every mutant to survive): mutant 1 was killed by "
        f"{T}::test_plant_must_die; mutant 2 was killed by {T}::test_plant_must_die"]
    assert out["rows"] == [] and out["mutant_rows"] == []


def test_a_function_whose_text_moved_since_its_mutants_is_stale(tool, canary, tmp_path):
    for rel in ("canarypkg/fees.py", "reach/then/canarypkg/fees.py"):
        path = os.path.join(canary, rel)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace("return 0\n", "return 0  # moved\n"))
    out = _run(tool, canary, tmp_path)
    assert out["stale"] == {FEE: "its text moved since its mutants were made"}
    assert {r[4] for r in out["rows"]} == {"stale"} and len(out["rows"]) == 6
    assert out["mutant_rows"] == []


def test_the_committed_mutants_are_current_and_each_stays_inside_its_function(tool):
    with open(os.path.join(CANARY, "mutants.json.txt"), encoding="utf-8") as fh:
        data = json.load(fh)
    with open(os.path.join(CANARY, "canarypkg", "fees.py.txt"), encoding="utf-8") as fh:
        source = fh.read()
    assert data["generator"] == "mutmut 3.8.0"
    assert sum(len(v["mutants"]) for v in data["functions"].values()) >= 7, "floor: 7 mutants"
    seen = {}
    for key, entry in data["functions"].items():
        qualname = key.split("::", 1)[1]
        assert entry["hash"] == tool.nm.function_hash(source, qualname), f"{key} moved"
        assert [m["n"] for m in entry["mutants"]] == list(range(1, len(entry["mutants"]) + 1))
        for m in entry["mutants"]:
            new, why = tool.mutant_source(source, qualname, m)
            assert why == "", (key, m["n"], why)
            _kind, was, now, _eq = tool.describe(source, key, new, set(), [])
            seen[tool.mutant_name(key, m["n"])] = (was, now)
    assert {k: v for k, v in seen.items() if "x_fee" in k} == {
        k: v[:2] for k, v in EXPECTED_MUTANTS.items()}


def test_a_mutant_outside_its_function_or_not_parsing_is_refused(tool):
    source = "def a(x):\n    return x + 1\n\n\ndef b(y):\n    return y\n"
    assert tool.mutant_source(source, "a", {"start": 6, "end": 6, "lines": ["    return 0\n"]}) \
        == (None, "its lines 6 to 6 are outside the function's 1 to 2")
    new, why = tool.mutant_source(source, "a", {"start": 2, "end": 2, "lines": ["    return (\n"]})
    assert new is None and why.startswith("the mutated module does not parse")
    new, why = tool.mutant_source(source, "a", {"start": 2, "end": 2, "lines": ["    return x - 1\n"]})
    assert why == "" and new.splitlines()[1] == "    return x - 1"
    hunk = tool.hunk_of(source, new)
    assert hunk == {"start": 2, "end": 2, "lines": ["    return x - 1\n"]}
    assert tool.apply_hunk(source, hunk) == new
    ast.parse(new)


def test_the_estimate_is_mutants_times_tests_times_seconds_and_runs_nothing(tool, canary,
                                                                             tmp_path):
    kw = dict(root=canary, scope=SCOPE, canaries=MUST_DIE, null_canaries=NULL)
    reach, mutants = os.path.join(canary, "reach"), os.path.join(canary, "mutants.json")
    e = tool.estimate(reach, mutants, seconds_per_test=1.0, startup=0.5, **kw)
    assert [r[:4] for r in e["rows"]] == [(FEE, 4, 6, 0)]
    # (4 mutants + the baseline + the reach check) runs x (0.5 s + 6 tests x 1.0 s).
    assert e["rows"][0][4] == pytest.approx(6 * (0.5 + 6 * 1.0))
    lines = tool.estimate_lines(e, SCOPE)
    assert "# pytest runs: 6 (each function's mutants, its baseline and its reach check), " \
           "the canaries' aside" in lines
    assert "# test executions: 36, 0 of them at a time from --times, the rest at 1.0 s each" \
        in lines
    junit = tmp_path / "junit.xml"
    junit.write_text('<testsuites><testsuite><testcase classname="tests.test_fees" '
                     'name="test_plant_fee_kills_all" time="2.0"/></testsuite></testsuites>',
                     encoding="utf-8")
    timed = tool.estimate(reach, mutants, seconds_per_test=1.0, startup=0.5,
                          times=tool.junit_times([str(junit)]), **kw)
    assert timed["rows"][0][3] == 1
    assert timed["rows"][0][4] == pytest.approx(6 * (0.5 + 2.0 + 5 * 1.0))
    assert sorted(os.listdir(tmp_path)) == ["junit.xml", "ta-b-canary"], "nothing ran"


def test_a_selection_of_no_function_is_refused(tool, canary, capsys):
    args = ["--reach", os.path.join(canary, "reach"), "--then",
            os.path.join(canary, "reach", "then"), "--root", canary, "--mutants",
            os.path.join(canary, "mutants.json"), "--scope", "canarypkg/nothing.py",
            "--canary", *MUST_DIE, "--null-canary", *NULL]
    assert tool.main(args) == 1
    assert tool.main([*args, "--estimate"]) == 1
    assert "the selection holds no function" in capsys.readouterr().err
