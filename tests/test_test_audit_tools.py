"""The existing-test audit's tools (c) and (d) (docs/TEST_AUDIT.md), each run on the committed
canary (`docs/test_audit/canary/`, its files stored as `<name>.txt` so pytest never collects
them, copied here into a temporary folder under their real names).

- **Tool (c), `scripts/nmas-test-audit-static`:** every plant is listed with its own pattern
  (two tautologies, an assertion-free test, two mocks of the module the file is named for, a
  swallowed exception, two status-only tests), and nothing else is: the clean tests (a value
  checked, a collaborator patched through the subject's namespace, an asserting helper imported
  from `tests.`, `pytest.raises` with a content assert, a narrow handler and an HTTP client's
  `.patch`) are parsed and never listed.
- **Tool (d), `scripts/nmas-test-audit-dead`:** pytest's real collection of the canary against
  its definitions: every plant listed with its own pattern (three always skipped, one always
  xfail, one shadowed, three uncollected with their reasons, one conditionally skipped with its
  condition), and the clean tests are collected and never listed; its totals are pytest's own.
- **A file written after the collection began** is said to be newer than the collection, not
  uncollected for a reason of its own.
- **A collection that did not run is never read as an empty one:** output with no count line
  exits 1.
"""
import importlib.machinery
import importlib.util
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANARY = os.path.join(ROOT, "docs", "test_audit", "canary")

W = "tests/test_widget.py"
D = "tests/test_dead_plants.py"
B = "tests/test_plant_broken.py"

STATIC_PLANTS = {
    (f"{W}::test_plant_tautology_same_sides", "tautology"),
    (f"{W}::test_plant_tautology_constant", "tautology"),
    (f"{W}::test_plant_assertion_free", "assertion-free"),
    (f"{W}::test_plant_mock_of_subject_object", "mock-of-subject"),
    (f"{W}::test_plant_mock_of_subject_string", "mock-of-subject"),
    (f"{W}::test_plant_swallowed_exception", "swallowed-exception"),
    (f"{W}::test_plant_status_only_code", "status-only"),
    (f"{W}::test_plant_status_only_ok", "status-only"),
}
STATIC_CLEAN = {
    f"{W}::test_clean_compute_value",
    f"{W}::test_clean_patches_a_collaborator",
    f"{W}::test_clean_uses_an_asserting_helper",
    f"{W}::test_clean_narrow_handler_and_a_client_patch",
    f"{W}::TestCleanClass::test_clean_raises_and_reads_content",
}
DEAD_PLANTS = {
    (f"{D}::test_plant_skip_decorator", "always-skipped"),
    (f"{D}::test_plant_skipif_true", "always-skipped"),
    (f"{D}::test_plant_skip_first_statement", "always-skipped"),
    (f"{D}::test_plant_xfail_unconditional", "always-xfail"),
    (f"{D}::test_plant_shadowed", "shadowed"),
    (f"{D}::TestPlantHasInit::test_plant_class_with_init", "uncollected"),
    (f"{D}::PlantNotATestClass::test_plant_method_outside_a_test_class", "uncollected"),
    (f"{B}::test_plant_in_a_file_that_does_not_collect", "uncollected"),
    (f"{D}::test_plant_conditional_skip", "conditionally-skipped"),
}
DEAD_CLEAN = {
    f"{D}::test_clean_runs",
    f"{D}::test_clean_parametrized",
    f"{D}::TestCleanCollected::test_clean_method",
}


def _tool(name):
    path = os.path.join(ROOT, "scripts", name)
    mod_name = name.replace("-", "_")
    loader = importlib.machinery.SourceFileLoader(mod_name, path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(mod_name, loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture
def canary(tmp_path):
    """The committed canary under its real names, in a folder of its own."""
    from tests.source_index import tracked
    root = tmp_path / "ta-canary"
    copied = 0
    for src in tracked(CANARY):
        f = os.path.basename(src)
        assert f.endswith(".txt"), f"every canary file is stored as .txt: {f}"
        dst = root / os.path.relpath(src, CANARY)[: -len(".txt")]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied += 1
    assert copied >= 7, "floor: the canary's seven files are committed"
    return str(root)


def test_static_lists_every_plant_with_its_pattern_and_no_clean_test(canary):
    tool = _tool("nmas-test-audit-static")
    got = tool.audit(canary)
    flagged = {(r[0], r[2]) for r in got["rows"]}
    assert flagged == STATIC_PLANTS, (
        f"missed: {sorted(STATIC_PLANTS - flagged)}; unexpected: {sorted(flagged - STATIC_PLANTS)}")
    parsed = set()
    for path in tool.test_files(canary):
        rp = tool.rel(canary, path)
        for chain, _classes, fn in tool.iter_tests(tool.parse(path)):
            parsed.add("::".join([rp] + chain + [fn.name]))
    assert STATIC_CLEAN <= parsed, sorted(STATIC_CLEAN - parsed)
    assert got["tests"] == len(parsed) + 1, "the shadowed plant's two definitions both parsed"


def test_dead_lists_every_plant_with_its_pattern_and_no_clean_test(canary):
    tool = _tool("nmas-test-audit-dead")
    _cmd, text = tool.run_collection(canary, sys.executable)
    got = tool.audit(canary, text)
    flagged = {(r[0], r[2]) for r in got["rows"]}
    assert flagged == DEAD_PLANTS, (
        f"missed: {sorted(DEAD_PLANTS - flagged)}; unexpected: {sorted(flagged - DEAD_PLANTS)}")
    collected, _n, errors, _line = tool.parse_collection(text)
    assert DEAD_CLEAN <= collected, sorted(DEAD_CLEAN - collected)
    assert list(errors) == [B]
    why = {r[0].rsplit("::", 1)[-1]: r[4] for r in got["rows"] if r[2] == "uncollected"}
    assert "__init__" in why["test_plant_class_with_init"]
    assert "python_classes" in why["test_plant_method_outside_a_test_class"]
    assert "planted_module_that_does_not_exist" in why["test_plant_in_a_file_that_does_not_collect"]
    cond = [r[4] for r in got["rows"] if r[2] == "conditionally-skipped"]
    assert cond == ["skipif condition: sys.platform == 'planted-no-such-platform'"]


def test_dead_totals_are_pytest_s_own(canary):
    tool = _tool("nmas-test-audit-dead")
    _cmd, text = tool.run_collection(canary, sys.executable)
    got = tool.audit(canary, text)
    assert got["count_line"].startswith(f"{got['ids']} tests collected"), got["count_line"]
    assert got["ids"] == got["base_ids"] + 1, "the parametrized clean test's two cases"


def test_a_file_written_after_the_collection_began_is_said_to_be_newer(canary):
    """Another writer in the checkout (2026-11-03: a test file written during the repository's
    40 s collection was listed as uncollected for no reason of its own)."""
    tool = _tool("nmas-test-audit-dead")
    started = os.path.getmtime(os.path.join(canary, W)) + 1
    _cmd, text = tool.run_collection(canary, sys.executable)
    late = os.path.join(canary, "tests", "test_written_late.py")
    with open(late, "w", encoding="utf-8") as fh:
        fh.write("def test_late():\n    assert 1 + 1 == 2\n")
    os.utime(late, (started + 5, started + 5))
    got = tool.audit(canary, text, started)
    rows = [r for r in got["rows"] if r[0] == "tests/test_written_late.py::test_late"]
    assert [r[2] for r in rows] == ["uncollected"]
    assert "written after the collection started" in rows[0][4]


@pytest.mark.parametrize("name", ["nmas-test-audit-static", "nmas-test-audit-dead"])
def test_quoted_source_in_a_row_carries_no_address_or_email(name):
    """The output is committed without the test files' own excused-line exemptions (2026-11-03:
    a status-only detail quoted a test's address literal and the publication scan refused it)."""
    tool = _tool(name)
    row = ("tests/test_x.py::test_y", "tests/test_x.py", "status-only", 1,
           "ctx.verify_result['192.0.2.7']['ok'] is True; by t@example.com")
    args = ({"rows": [row], "files": 1, "unparsed": [], "tests": 1},) \
        if name.endswith("static") else \
        ({"rows": [row], "ids": 1, "base_ids": 1, "errors": {}, "count_line": "1 test collected",
          "defs": 1, "extra": []}, "x")
    out = "\n".join(tool.report(*args))
    assert "192.0.2.7" not in out and "t@example.com" not in out, out
    assert "ctx.verify_result['<address>']['ok'] is True; by <email>" in out


def test_a_collection_that_did_not_run_is_refused_not_read_as_empty(canary, tmp_path, capsys):
    tool = _tool("nmas-test-audit-dead")
    saved = tmp_path / "collection.txt"
    saved.write_text("ImportError while loading conftest\n", encoding="utf-8")
    assert tool.main(["--root", canary, "--collected", str(saved)]) == 1
    assert "no count line" in capsys.readouterr().err
