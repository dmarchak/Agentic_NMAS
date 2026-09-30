"""The PreToolUse hook that refuses a heredoc fed into an interpreter
(scripts/hooks/claude-no-heredoc-interpreter), driven exactly as Claude Code
drives it: the tool call as JSON on stdin, exit 2 and a message on stderr to
refuse, exit 0 to let it run.

The refused cases are the agent's own slips (a document edit sent to
`python3 - <<'EOF'`) and the shapes that carry the same text another way; the
allowed cases are the heredocs this project uses legitimately (a commit
message, a file written by `cat`) and an interpreter reading a file, which is
the remedy the refusal names."""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "scripts", "hooks", "claude-no-heredoc-interpreter")
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")


def run(command, tool="Bash", raw=None):
    payload = raw if raw is not None else json.dumps(
        {"tool_name": tool, "tool_input": {"command": command}, "hook_event_name": "PreToolUse"})
    return subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                          text=True, timeout=20)


REFUSED = {
    "the slip itself": "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('docs/X.md')\nEOF",
    "unquoted delimiter": "python3 <<EOF\nprint(1)\nEOF",
    "a dash heredoc": "cd /tmp && python3 - <<-END\n\tprint(1)\n\tEND",
    "piped from cat": "cat <<'EOF' | python3 -\nprint(1)\nEOF",
    "a remote interpreter": "scripts/nmas-host nmas -- bash -c 'cd x && python3 -' <<'EOF'\nprint(1)\nEOF",
    "a here-string": "node <<< 'console.log(1)'",
    "behind sudo and an env": "sudo -u nmas env A=1 /usr/bin/python3.12 - <<EOF\nx\nEOF",
    "a shell fed a script": "bash <<'EOF'\necho hi\nEOF",
    "after a separator": "git status && python3 - <<'EOF'\nprint(1)\nEOF",
}

ALLOWED = {
    "a commit message": "git commit -q -F /tmp/msg.txt",
    "a commit message built by cat": (
        "git commit -m \"$(cat <<'EOF'\nFix the python3 heredoc hook\n\nbash <<EOF\nEOF\n)\""),
    "a file written by cat": "cat > /tmp/probe.py <<'EOF'\nimport json\nprint(json)\nEOF",
    "an interpreter reading a file": "python3 /tmp/probe.py",
    "an interpreter fed a file": "bash -c 'cd x && python3 -' < /tmp/probe.py",
    "no heredoc at all": "grep -n '<<' scripts/x | head",
    "a heredoc into grep, then python on its own line": "grep x <<EOF\nabc\nEOF\npython3 /tmp/a.py",
}


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_refused(name):
    r = run(REFUSED[name])
    assert r.returncode == 2, (name, r.returncode, r.stderr)
    assert "Refused by the project's PreToolUse hook" in r.stderr
    assert "Write tool" in r.stderr


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_allowed(name):
    r = run(ALLOWED[name])
    assert r.returncode == 0, (name, r.returncode, r.stderr)
    assert r.stderr == ""


def test_the_refusal_names_the_interpreter():
    r = run(REFUSED["piped from cat"])
    assert "(python3)" in r.stderr


def test_another_tool_is_not_its_business():
    assert run("python3 - <<EOF\nx\nEOF", tool="Write").returncode == 0


def test_unreadable_input_is_a_visible_hook_error_not_a_silent_pass():
    r = run(None, raw="not json")
    assert r.returncode == 1 and "was NOT checked" in r.stderr


def test_the_settings_wire_it_to_every_bash_call():
    """The hook is only a hook if Claude Code runs it: the committed project
    settings name it for the Bash tool, and the file exists and is executable."""
    with open(SETTINGS, encoding="utf-8") as fh:
        settings = json.load(fh)
    entries = settings["hooks"]["PreToolUse"]
    wired = [h["command"] for e in entries if e.get("matcher") == "Bash" for h in e["hooks"]]
    assert any(c.endswith("/scripts/hooks/claude-no-heredoc-interpreter") for c in wired), wired
    assert os.access(HOOK, os.X_OK)
