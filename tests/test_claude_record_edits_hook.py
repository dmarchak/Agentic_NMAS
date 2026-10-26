"""The PostToolUse hook that records each file the Edit and Write tools change, in the ledger
`scripts/nmas-gate` reads to name a swept-in file nobody edited through them
(scripts/hooks/claude-record-edits; the operator, 2026-10-26).

`record` against a temporary checkout: a file inside is appended relative to it; a file outside,
or in an agent's worktree under .claude/worktrees/, is not; the hook itself never refuses, even
on input it cannot read; and it is wired after the edit tools in .claude/settings.json."""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "scripts", "hooks", "claude-record-edits")


def _load():
    loader = importlib.machinery.SourceFileLoader("claude_record_edits", HOOK)
    spec = importlib.util.spec_from_loader("claude_record_edits", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


H = _load()


def test_a_file_inside_is_recorded_relative_to_the_checkout(tmp_path):
    root = tmp_path / "checkout"
    (root / ".git").mkdir(parents=True)
    (root / "modules").mkdir()
    assert H.record(str(root / "modules" / "x.py"), root=str(root)) == "modules/x.py"
    assert H.record(str(root / "README.md"), root=str(root)) == "README.md"
    assert (root / ".git" / "nmas-edited-paths").read_text() == "modules/x.py\nREADME.md\n"


def test_outside_and_in_an_agent_s_worktree_nothing_is_recorded(tmp_path):
    root = tmp_path / "checkout"
    (root / ".git").mkdir(parents=True)
    assert H.record(str(tmp_path / "elsewhere.py"), root=str(root)) == ""
    assert H.record(str(root / ".claude" / "worktrees" / "agent-x" / "a.py"),
                    root=str(root)) == ""
    assert not (root / ".git" / "nmas-edited-paths").exists()


def test_the_hook_never_refuses():
    for payload in ("not json", json.dumps({"tool_name": "Edit", "tool_input": {}})):
        r = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                           text=True, timeout=20)
        assert r.returncode == 0, r.stderr


def test_it_is_wired_after_the_edit_tools():
    with open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8") as fh:
        hooks = json.load(fh)["hooks"]["PostToolUse"]
    (entry,) = [h for h in hooks if "claude-record-edits" in json.dumps(h)]
    assert entry["matcher"] == "Edit|Write|MultiEdit|NotebookEdit"
