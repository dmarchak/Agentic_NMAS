"""No tracked file holds a merge-conflict marker (the operator, 2026-10-23: a `>>>>>>> theirs`
showed in a diff during a three-way merge of agents' worktrees).

The stage guard refuses one in a staged file (scripts/nmas-stage-guard, `CONFLICT_MARKER`);
this scan is the same rule over every tracked text file, so CI refuses a marker a laptop's hooks
let through. The markers are built here, never written whole: a literal one would be the thing
refused."""

import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER = re.compile("^(?:" + "<" * 7 + " |" + ">" * 7 + " |" + "=" * 7 + "$)", re.M)


def _tracked():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"], capture_output=True,
                         check=True).stdout.decode("utf-8", "replace")
    return [p for p in out.split("\0") if p]


def markers_in(text: str) -> list:
    """``[(line number, the line)]`` for each conflict-marker line in *text*."""
    return [(text.count("\n", 0, m.start()) + 1, text[m.start():].split("\n", 1)[0].strip())
            for m in MARKER.finditer(text)]


def test_no_tracked_file_holds_a_conflict_marker():
    files = _tracked()
    assert len(files) >= 1000, len(files)          # the floor: about 1,900 tracked files
    found = []
    for rel in files:
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as fh:
            blob = fh.read()
        if b"\0" in blob[:8192]:                   # binary: not text a merge writes into
            continue
        found += [(rel, line, mark) for line, mark in markers_in(blob.decode("latin-1"))]
    assert found == [], f"merge-conflict markers left in tracked files: {found}"


@pytest.mark.parametrize("marker", ["<" * 7 + " ours", "=" * 7, ">" * 7 + " theirs"])
def test_the_scan_finds_each_planted_marker_and_names_its_line(marker):
    assert markers_in(f"a\nb\n{marker}\nc\n") == [(3, marker)]


def test_the_scan_passes_a_markdown_rule_and_a_quoted_marker():
    assert markers_in("Title\n" + "=" * 8 + "\nsee `" + ">" * 7 + " theirs` here\n") == []
