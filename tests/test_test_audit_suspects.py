"""The existing-test audit's combined suspects list (scripts/nmas-test-audit-suspects;
docs/TEST_AUDIT.md, "The output"): every test a tool flagged, and which tools, beside the
total collected. What each tool's rows count as: (c) every row; (d) only uncollected, shadowed,
always skipped or xfail, never a conditional skip; (a) only "still passes", never stale or not
collected; and the operator's named group. It classifies nothing."""
import importlib.machinery
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tool():
    path = os.path.join(ROOT, "scripts", "nmas-test-audit-suspects")
    loader = importlib.machinery.SourceFileLoader("nmas_test_audit_suspects", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


STATIC = [{"test_id": "t::a", "pattern": "tautology", "line": "3"},
          {"test_id": "t::b", "pattern": "status-only", "line": "9"}]
DEAD = [{"test_id": "t::c", "pattern": "shadowed"},
        {"test_id": "t::d", "pattern": "conditionally-skipped"}]
DELETION = [{"test_id": "t::a", "result": "still passes", "detail": "under none"},
            {"test_id": "t::e", "result": "stale", "detail": ""},
            {"test_id": "t::f", "result": "not collected", "detail": ""},
            {"test_id": "t::g", "result": "fails", "detail": ""}]


def test_each_tool_counts_only_what_it_flags():
    got = _tool().combine(STATIC, DEAD, DELETION, ["t::h"])
    assert sorted(got) == ["t::a", "t::b", "t::c", "t::h"]
    assert sorted(got["t::a"]) == ["deletion", "static"]
    assert "t::d" not in got, "a conditional skip is not dead"
    assert not {"t::e", "t::f", "t::g"} & set(got), "stale, not collected and fails are not listed"


def test_the_report_puts_the_most_flagged_first_and_counts_against_the_total():
    tool = _tool()
    lines = tool.report(tool.combine(STATIC, DEAD, DELETION, ["t::h"]), total=100)
    assert lines[0] == "test_id\ttools\thow many\tdetails"
    assert lines[1].startswith("t::a\tdeletion,static\t2\t")
    assert "# tests flagged: 4 of 100 collected" in lines
    assert "# by static: 2" in lines and "# by dead: 1" in lines
    assert "# by deletion: 1" in lines and "# by named: 1" in lines
    assert "# flagged by one tool: 3; by two or more: 1" in lines


def test_the_named_group_is_read_from_a_commit_s_trailers_by_their_reason(monkeypatch):
    tool = _tool()
    body = ("subject\n\n"
            "Test-Weakened: tests/test_x.py::test_one[case a] — C2313: A, re-recorded\n"
            "Test-Weakened: tests/test_x.py::test_two — C2313: B, edited\n"
            "Test-Weakened: tests/test_y.py::test_three — C2313: renamed\n")

    class R:
        stdout = body
    monkeypatch.setattr("modules.nsot.repo.run_git", lambda *a, **k: R)
    assert tool.named_tests("abc", r"^C2313: [AB],") == [
        "tests/test_x.py::test_one[case a]", "tests/test_x.py::test_two"]
    assert len(tool.named_tests("abc")) == 3
