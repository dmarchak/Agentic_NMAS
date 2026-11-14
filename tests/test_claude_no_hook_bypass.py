"""The PreToolUse hook that refuses a git hook bypass (scripts/hooks/claude-no-hook-bypass; the
operator, 2026-11-13), driven exactly as Claude Code drives it: the tool call as JSON on stdin,
exit 2 and a message on stderr to refuse, exit 0 to let it run.

What each test holds: every bypass the operator named is refused (`--no-verify` on a commit, a
push or any git subcommand, with git's accepted abbreviations; `-n` on a commit, alone or in a
cluster of short options; core.hooksPath set by `-c`, by `--config-env`, by `git config` in any
place, or through the environment, in any case), including inside `bash -c` and `eval`, and
after `sudo` or `env`; what this project runs every day is let through (a commit by message
file, `-m` messages naming the flag, a push's `-n` dry run, a read of core.hooksPath, a search
for the words, a hook installed by `ln -sf`, a heredoc's body); an unreadable input is a hook
error, never silently allowed; and the committed settings wire the hook to every Bash call.
"""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "scripts", "hooks", "claude-no-hook-bypass")
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")


def run(command, tool="Bash", raw=None):
    payload = raw if raw is not None else json.dumps(
        {"tool_name": tool, "tool_input": {"command": command}, "hook_event_name": "PreToolUse"})
    return subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                          text=True, timeout=20)


REFUSED = {
    "a commit's --no-verify": "git commit --no-verify -F /tmp/msg",
    "a commit's abbreviation": "git commit --no-veri -m x",
    "a commit's -n": "git commit -n -m x",
    "a commit's -n in a cluster": "git commit -anm 'a message'",
    "a commit's -n after -q": "git commit -qn -F /tmp/msg",
    "a push's --no-verify": "git push --no-verify origin ci/x",
    "a push's --no-verify after the refspec": "git push -q origin HEAD:refs/heads/ci/x --no-verify",
    "a merge's --no-verify": "git merge --no-verify topic",
    "-c core.hooksPath": "git -c core.hooksPath=/dev/null commit -F /tmp/msg",
    "-c with another case": "git -c CORE.HOOKSPATH=/tmp/none push origin ci/x",
    "--config-env": "git --config-env=core.hooksPath=EMPTY push origin ci/x",
    "git config, local": "git config core.hooksPath /tmp/none",
    "git config, global": "git config --global core.hooksPath /tmp/none",
    "git config, a file": "git config --file .git/config core.hooksPath /tmp/none",
    "git config, unset": "git config --unset core.hooksPath",
    "the environment": "GIT_CONFIG_PARAMETERS=\"'core.hooksPath'='/tmp/none'\" git push origin ci/x",
    "the environment's numbered keys": (
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/tmp/none "
        "git commit -F /tmp/msg"),
    "an export": "export GIT_CONFIG_KEY_0=core.hooksPath",
    "behind sudo": "sudo -u someone git push --no-verify",
    "behind env": "env -i HOME=/tmp git commit --no-verify -F /tmp/msg",
    "after a separator": "git add -A && git commit --no-verify -F /tmp/msg",
    "on the next line": "cd /tmp/x\ngit push --no-verify origin ci/x",
    "inside bash -c": "bash -c 'cd /tmp/x && git push --no-verify origin ci/x'",
    "inside eval": "eval git commit -n -m x",
    "a git by path": "/usr/bin/git -C /tmp/x commit --no-verify -m x",
}

ALLOWED = {
    "a commit by message file": "git commit -q -F /tmp/msg.txt",
    "a message naming the flag": "git commit -m 'never use --no-verify'",
    "a message across lines naming it": "git commit -m 'one\ngit push --no-verify was refused'",
    "a message value that is the flag": "git commit -m --no-verify",
    "a -F cluster whose value is n": "git commit -Fn",
    "a push's dry run": "git push -n origin ci/x",
    "a push": "git push -q origin HEAD:refs/heads/ci/x",
    "a read of core.hooksPath": "git config --get core.hooksPath",
    "a bare read of core.hooksPath": "git config core.hooksPath",
    "another key": "git config user.name t",
    "a search for the flag": "grep -rn -- --no-verify scripts/ tests/",
    "a search for the key": "grep -rn hooksPath .git/config",
    "installing a hook": "ln -sf ../../scripts/hooks/pre-push .git/hooks/pre-push",
    "a heredoc's body": "cat > /tmp/note <<'EOF'\ngit push --no-verify\nEOF",
    "a log": "git log -30 --format=%B | grep -n '^Bypass:'",
    "a verbose commit": "git commit -v -F /tmp/msg",
}


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_refused(name):
    r = run(REFUSED[name])
    assert r.returncode == 2, (name, r.returncode, r.stderr)
    assert "Refused by the project's PreToolUse hook (scripts/hooks/claude-no-hook-bypass)" \
        in r.stderr
    assert "No hook is bypassed" in r.stderr


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_allowed(name):
    r = run(ALLOWED[name])
    assert r.returncode == 0, (name, r.returncode, r.stderr)
    assert r.stderr == ""


def test_another_tool_is_not_judged():
    assert run("git push --no-verify", tool="Read").returncode == 0


def test_an_unreadable_input_is_a_hook_error_never_allowed_silently():
    r = run(None, raw="not json")
    assert r.returncode == 1 and "was NOT checked" in r.stderr


def test_the_settings_wire_it_to_every_bash_call():
    """The hook is only a hook if Claude Code runs it: the committed project settings name it
    for the Bash tool, and the file exists and is executable."""
    with open(SETTINGS, encoding="utf-8") as fh:
        settings = json.load(fh)
    entries = settings["hooks"]["PreToolUse"]
    wired = [h["command"] for e in entries if e.get("matcher") == "Bash" for h in e["hooks"]]
    assert any(c.endswith("/scripts/hooks/claude-no-hook-bypass") for c in wired), wired
    assert os.access(HOOK, os.X_OK)
