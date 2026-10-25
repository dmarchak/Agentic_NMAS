"""The doc set (tests/doc_tests.py; the operator, 2026-10-25): what a commit whose every path is
under docs/ runs, in the gate and in CI's doc job.

- docs-only is every path under docs/: an empty change, CLAUDE.md, or any path elsewhere runs
  everything;
- the set holds every measured reader that still exists, and every test file whose own source
  reads a document (a planted reader joins it; a planted file that only mentions docs/ in
  words does not);
- `nmas-shards docs` prints exactly the set, and its matrix is the doc job alone only for a
  docs-only change.
"""

import importlib.machinery
import importlib.util
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import doc_tests  # noqa: E402


@pytest.mark.parametrize("paths,docs", [
    (["docs/OPEN_FINDINGS.md"], True),
    (["docs/manual/screens/history.md", "docs/TESTING.md"], True),
    (["docs/a.md", "CLAUDE.md"], False),
    (["CLAUDE.md"], False),
    (["docs/a.md", "modules/redact.py"], False),
    ([], False),
    (["documents.md"], False),
], ids=["register", "two-docs", "with-claude-md", "claude-md", "with-code", "empty",
        "not-the-folder"])
def test_docs_only_is_every_path_under_docs(paths, docs):
    assert doc_tests.docs_only(paths) is docs


def test_the_set_holds_every_measured_reader_that_exists():
    got = set(doc_tests.doc_set())
    measured = {f"tests/{n}" for n in doc_tests.MEASURED
                if os.path.exists(os.path.join(ROOT, "tests", n))}
    assert len(measured) >= 45, "floor: the measurement's readers are still here"
    assert measured <= got, sorted(measured - got)


def test_a_test_written_later_that_reads_a_document_joins_the_set(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_reads.py").write_text(
        'def test_x():\n    open(os.path.join(ROOT, "docs", "TESTING.md")).read()\n')
    (tests / "test_mentions.py").write_text(
        '"""See docs/TESTING.md for why."""\ndef test_y():\n    assert True\n')
    (tests / "test_claude.py").write_text('P = "CLAUDE.md"\n')
    (tests / "test_tracked.py").write_text('git = ["git", "ls-files", "-z"]\n')
    got = doc_tests.doc_set(str(tmp_path))
    assert got == ["tests/test_claude.py", "tests/test_reads.py", "tests/test_tracked.py"], got


def _shards():
    path = os.path.join(ROOT, "scripts", "nmas-shards")
    loader = importlib.machinery.SourceFileLoader("nmas_shards_for_doc_tests", path)
    spec = importlib.util.spec_from_loader("nmas_shards_for_doc_tests", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_the_doc_job_runs_exactly_the_set():
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "nmas-shards"), "docs"],
                         capture_output=True, text=True, check=True).stdout.split()
    assert out == doc_tests.doc_set() and len(out) >= 50


@pytest.mark.parametrize("paths,expect", [
    (["docs/OPEN_FINDINGS.md"], ["docs"]),
    (["docs/OPEN_FINDINGS.md", "scripts/nmas-gate"], "five"),
    (["CLAUDE.md"], "five"),
    (None, "five"),
], ids=["docs", "docs-and-code", "claude-md", "unreadable-range"])
def test_the_matrix_is_the_doc_job_only_for_a_docs_only_change(paths, expect):
    shards = _shards()
    assert shards.matrix(paths) == (list(shards.SHARDS) if expect == "five" else expect)


def test_a_new_branch_or_an_unknown_range_runs_everything():
    shards = _shards()
    assert shards.changed_paths("0" * 40, "HEAD") is None
    assert shards.changed_paths("", "HEAD") is None
    assert shards.changed_paths("not-a-sha", "HEAD") is None
