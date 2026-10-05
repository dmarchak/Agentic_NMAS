"""scripts/hooks/claude-no-claude-md-edits: CLAUDE.md is the operator's to change, so the
agent's tools are refused on it (the operator, 2026-10-05, after an agent edit met no guard).

Driven the way Claude Code drives it: the tool call as JSON on stdin, exit 2 and a message on
stderr to refuse, 0 to allow, 1 (a visible hook error) for input it cannot read."""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "scripts", "hooks", "claude-no-claude-md-edits")


def run(tool, tool_input=None, raw=None):
    payload = raw if raw is not None else json.dumps({"tool_name": tool, "tool_input": tool_input})
    return subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                          text=True, timeout=20)


REFUSED_FILE = [
    ("Edit", {"file_path": f"{ROOT}/CLAUDE.md", "old_string": "a", "new_string": "b"}),
    ("Write", {"file_path": f"{ROOT}/CLAUDE.md", "content": "x"}),
    ("MultiEdit", {"file_path": f"{ROOT}/sub/CLAUDE.md", "edits": []}),
    ("Write", {"file_path": "CLAUDE.md", "content": "x"}),
]
ALLOWED_FILE = [
    ("Edit", {"file_path": f"{ROOT}/docs/LESSONS.md", "old_string": "a", "new_string": "b"}),
    ("Write", {"file_path": f"{ROOT}/CLAUDE.md.bak", "content": "x"}),
    ("Read", {"file_path": f"{ROOT}/CLAUDE.md"}),
]
REFUSED_BASH = [
    "echo x >> CLAUDE.md",
    "printf 'x' > ./CLAUDE.md",
    "sed -i 's/a/b/' CLAUDE.md",
    "sed -i.bak -e 's/a/b/' CLAUDE.md",
    "cd /repo && sed -i '234s/x/y/' CLAUDE.md && git add -A",
    "perl -pi -e 's/a/b/' CLAUDE.md",
    "echo x | tee -a CLAUDE.md",
    "cp /tmp/new.md CLAUDE.md",
    "mv CLAUDE.md /tmp/old.md",
    "rm CLAUDE.md",
    "git checkout HEAD~1 -- CLAUDE.md",
    "git restore CLAUDE.md",
    "python3 /tmp/edit.py CLAUDE.md",
    "python3 -c \"p='CLAUDE.md'; open(p,'w').write('x')\"",
    "python3 -c \"import pathlib; pathlib.Path('CLAUDE.md').write_text('x')\"",
]
ALLOWED_BASH = [
    "cat CLAUDE.md",
    "grep -n 'terminal' CLAUDE.md",
    "sed -n '230,240p' CLAUDE.md",
    "head -40 CLAUDE.md | tail -5",
    "git diff CLAUDE.md",
    "git show HEAD:CLAUDE.md | head",
    "git log --oneline -- CLAUDE.md",
    "git add -A && git commit -F /tmp/msg",
    "python3 -c \"print(open('CLAUDE.md').read()[:100])\"",
    "sed -i 's/a/b/' docs/OPEN_FINDINGS.md",
    "echo 'see CLAUDE.md' > /tmp/note.txt",
]


@pytest.mark.parametrize("tool, tool_input", REFUSED_FILE)
def test_a_file_tool_on_claude_md_is_refused(tool, tool_input):
    out = run(tool, tool_input)
    assert out.returncode == 2, (tool, tool_input, out.stderr)
    assert "the operator's to change" in out.stderr and "exact lines to paste" in out.stderr


@pytest.mark.parametrize("tool, tool_input", ALLOWED_FILE)
def test_other_files_and_reads_are_allowed(tool, tool_input):
    assert run(tool, tool_input).returncode == 0


@pytest.mark.parametrize("command", REFUSED_BASH)
def test_a_bash_write_is_refused(command):
    out = run("Bash", {"command": command})
    assert out.returncode == 2, (command, out.stderr)


@pytest.mark.parametrize("command", ALLOWED_BASH)
def test_a_bash_read_is_allowed(command):
    out = run("Bash", {"command": command})
    assert out.returncode == 0, (command, out.stderr)


def test_unreadable_input_is_a_visible_hook_error():
    assert run(None, raw="not json").returncode == 1


def test_the_settings_wire_it_to_the_file_tools_and_bash():
    with open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8") as fh:
        hooks = json.load(fh)["hooks"]["PreToolUse"]
    wired = {}
    for entry in hooks:
        for h in entry["hooks"]:
            if h["command"].endswith("claude-no-claude-md-edits"):
                for tool in entry["matcher"].split("|"):
                    wired[tool] = True
    for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"):
        assert wired.get(tool), f"the hook is not wired to {tool}"
