"""lab/claude-md-c663-nmas-host.py, the operator's script for C663's three CLAUDE.md lines, run on
a COPY of CLAUDE.md (the script finds CLAUDE.md beside its own folder, so a copy of it in a
temporary tree edits only that tree's): it changes exactly the three lines, refuses a second
run as a duplicate, and refuses when an anchor is not found once."""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "lab", "claude-md-c663-nmas-host.py")


def _tree(tmp_path, text=None):
    (tmp_path / "lab").mkdir()
    shutil.copy(SCRIPT, tmp_path / "lab" / "s.py")
    with open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8") as fh:
        original = fh.read()
    (tmp_path / "CLAUDE.md").write_text(text if text is not None else original)
    return original


def _run(tmp_path):
    return subprocess.run([sys.executable, str(tmp_path / "lab" / "s.py")], capture_output=True,
                          text=True, timeout=30)


def test_the_listed_lines_change_and_nothing_else(tmp_path):
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("c663", SCRIPT)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    original = _tree(tmp_path)
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout
    after = (tmp_path / "CLAUDE.md").read_text()
    changed = [(a, b) for a, b in zip(original.split("\n"), after.split("\n")) if a != b]
    assert len(after.split("\n")) == len(original.split("\n"))
    assert changed == [(line, new) for _b, line, _a, new in mod.CHANGES]
    assert sum("lab/nmas-host" in b for _a, b in changed) == 3
    assert "claude-no-shell-prose-edits" in changed[2][1]


def test_a_second_run_is_refused_as_a_duplicate(tmp_path):
    _tree(tmp_path)
    assert _run(tmp_path).returncode == 0
    before = (tmp_path / "CLAUDE.md").read_text()
    r = _run(tmp_path)
    assert r.returncode == 1 and "already there (refusing a duplicate)" in r.stdout
    assert (tmp_path / "CLAUDE.md").read_text() == before


def test_an_anchor_not_found_once_refuses_and_writes_nothing(tmp_path):
    with open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8") as fh:
        text = fh.read().replace("local file (`data/` is gitignored), because the repository "
                                 "is public", "local file, moved")
    _tree(tmp_path, text)
    r = _run(tmp_path)
    assert r.returncode == 1 and "anchor found 0 times" in r.stdout
    assert (tmp_path / "CLAUDE.md").read_text() == text
