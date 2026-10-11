"""The PreToolUse hook that refuses an in-place shell edit of prose
(scripts/hooks/claude-no-shell-prose-edits; the operator, 2026-10-11: "the prose slips keep
recurring"), driven exactly as Claude Code drives it: the tool call as JSON on stdin, exit 2 and
a message on stderr to refuse, exit 0 to let it run.

The refused cases include the overnight run's own slips (`sed -i` on docs/CONSOLE_DRILL.md and
docs/TESTING.md); the allowed ones are what the agent does legitimately (an in-place edit of
code, reading prose with sed or python, a script file run)."""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "scripts", "hooks", "claude-no-shell-prose-edits")
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")


def run(command, tool="Bash", raw=None):
    payload = raw if raw is not None else json.dumps(
        {"tool_name": tool, "tool_input": {"command": command}, "hook_event_name": "PreToolUse"})
    return subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                          text=True, timeout=20)


REFUSED = {
    "the slip on CONSOLE_DRILL": "sed -i 's/old/new/' docs/CONSOLE_DRILL.md",
    "the slip on TESTING, by line": "cd /x && sed -i '670s/a/b/' docs/TESTING.md",
    "an -i with a suffix": "sed -i.bak -e 's/a/b/' README.md",
    "an -Ei": "sed -Ei 's/(a)/b/' docs/manual/screens/dhcp.md",
    "--in-place": "sed --in-place 's/a/b/' CHANGELOG.md",
    "behind sudo": "sudo sed -i 's/a/b/' /srv/x/docs/notes.txt",
    "perl -pi": "perl -pi -e 's/a/b/' docs/LESSONS.md",
    "python -c writing": ("python3 -c \"import pathlib; p=pathlib.Path('docs/X.md'); "
                          "p.write_text(p.read_text().replace('a','b'))\""),
    "python -I -c with open w": "python3 -I -c \"open('docs/a.md','w').write('x')\"",
    "after a pipe": "git status | cat && sed -i 's/a/b/' docs/OPEN_FINDINGS.md",
}

ALLOWED = {
    "sed -i on code": "sed -i 's/a/b/' modules/x.py tests/test_x.py",
    "a script naming .md, on code": "sed -i 's/README.md/X.md/' scripts/build.py",
    "reading prose with sed": "sed -n 1,40p docs/TESTING.md",
    "reading prose with python": "python3 -c \"print(open('docs/TESTING.md').read()[:10])\"",
    "a script file run": "python3 scripts/nmas-manual-diagrams",
    "grep": "grep -n 'sed -i' docs/LESSONS.md",
    "perl reading": "perl -ne 'print if /x/' docs/a.md",
}


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_refused(name):
    r = run(REFUSED[name])
    assert r.returncode == 2, (name, r.returncode, r.stderr)
    assert "Refused by the project's PreToolUse hook" in r.stderr and "Edit and Write" in r.stderr


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_allowed(name):
    r = run(ALLOWED[name])
    assert r.returncode == 0, (name, r.returncode, r.stderr)


def test_the_refusal_names_the_file():
    assert "docs/CONSOLE_DRILL.md" in run(REFUSED["the slip on CONSOLE_DRILL"]).stderr


def test_another_tool_is_not_its_business():
    assert run("sed -i 's/a/b/' docs/X.md", tool="Write").returncode == 0


def test_unreadable_input_is_a_visible_hook_error_not_a_silent_pass():
    r = run(None, raw="not json")
    assert r.returncode == 1 and "was NOT checked" in r.stderr


def test_the_settings_wire_it_to_every_bash_call():
    with open(SETTINGS, encoding="utf-8") as fh:
        settings = json.load(fh)
    wired = [h["command"] for e in settings["hooks"]["PreToolUse"]
             if e.get("matcher") == "Bash" for h in e["hooks"]]
    assert any(c.endswith("/scripts/hooks/claude-no-shell-prose-edits") for c in wired), wired
    assert os.access(HOOK, os.X_OK)
