"""The PreToolUse hook's working-tree half (scripts/hooks/claude-no-shell-prose-edits; the
operator, 2026-10-26: "mechanise the rest rather than soften it"): inside the checkout, a
command that writes over the working tree is refused, so control, canary and mutation runs go
through scripts/nmas-control and edits through the Edit tool.

Driven exactly as Claude Code drives it: the tool call as JSON on stdin, with the session's
working directory; exit 2 and a message on stderr to refuse, exit 0 to let it run. One case per
refused form and per allowed form, against this checkout's own tracked files (the hook only
reads; nothing here runs the command)."""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "scripts", "hooks", "claude-no-shell-prose-edits")
TRACKED = "modules/endpoints.py"                    # a tracked file of this checkout


def run(command, cwd=ROOT, tool="Bash"):
    payload = json.dumps({"tool_name": tool, "tool_input": {"command": command}, "cwd": cwd,
                          "hook_event_name": "PreToolUse"})
    return subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                          text=True, timeout=20)


REFUSED = {
    "git checkout -- <path>": f"git checkout -- {TRACKED}",
    "git checkout <ref> -- <path>": f"git checkout HEAD~1 -- {TRACKED}",
    "git restore": f"git restore {TRACKED}",
    "git restore --staged --worktree": "git restore --staged --worktree .",
    "git reset --hard": "git reset --hard HEAD",
    "git clean": "git clean -fd",
    "git stash pop": "git stash pop",
    "git stash apply": "git stash apply stash@{0}",
    "git -C <checkout> restore, from elsewhere": f"git -C {ROOT} restore {TRACKED}",
    "cd <checkout> && git restore": f"cd {ROOT} && git restore {TRACKED}",
    "cp onto a tracked file": f"cp /tmp/x.py {TRACKED}",
    "cp into a folder over a tracked file": "cp /tmp/endpoints.py modules/",
    "cp -t <folder>": "cp -t modules /tmp/endpoints.py",
    "mv onto a tracked file": f"mv /tmp/x.py {TRACKED}",
    "rsync onto tracked files": "rsync -a /tmp/backup/ modules/",
    "install onto a tracked file": f"install -m 644 /tmp/x.py {TRACKED}",
    "cp with the command's own variable": f"D={ROOT}; cp /tmp/x.py $D/{TRACKED}",
    "behind sudo": f"sudo cp /tmp/x.py {TRACKED}",
    "git update-index --skip-worktree": "git update-index --skip-worktree CLAUDE.md",
    "git update-index --assume-unchanged": f"git update-index --assume-unchanged {TRACKED}",
}

ALLOWED = {
    "git stash create": "git stash create",
    "nmas-control": "scripts/nmas-control -- bash -c 'git restore modules/endpoints.py'",
    "git status and diff": "git status --short && git diff --stat",
    "git checkout -b (no --)": "git checkout -b scratch-branch",
    "git stash list": "git stash list",
    "cp onto a new, untracked file": "cp /tmp/x.py modules/brand_new_untracked_name.py",
    "cp out of the checkout": f"cp {TRACKED} /tmp/endpoints.copy.py",
    "rsync out of the checkout": "rsync -a modules/ /tmp/modules-copy/",
    "an unresolved variable": "cp /tmp/x.py $SOMEWHERE/x.py",
    "clearing skip-worktree": "git update-index --no-skip-worktree CLAUDE.md",
    "clearing assume-unchanged": f"git update-index --no-assume-unchanged {TRACKED}",
    "update-index --refresh": "git update-index -q --refresh",
}


@pytest.mark.parametrize("label", sorted(REFUSED))
def test_a_write_over_the_working_tree_is_refused(label):
    r = run(REFUSED[label])
    assert r.returncode == 2, (label, r.stdout, r.stderr)
    if "update-index" in label:
        assert "nmas-gate --only" in r.stderr, r.stderr
    else:
        assert "scripts/nmas-control" in r.stderr and "Edit tool" in r.stderr, r.stderr


@pytest.mark.parametrize("label", sorted(ALLOWED))
def test_an_allowed_form_runs(label):
    r = run(ALLOWED[label])
    assert r.returncode == 0, (label, r.stderr)


def test_the_edit_tool_is_not_this_hook_s(tmp_path):
    r = run(f"irrelevant", tool="Edit")
    assert r.returncode == 0


def test_the_same_commands_elsewhere_run(tmp_path):
    """Another repository (a test's, a scratch one) is not the checkout."""
    for command in ("git restore x.py", "git reset --hard", "git clean -fd", "cp /tmp/a b.py"):
        assert run(command, cwd=str(tmp_path)).returncode == 0, command


def test_an_agent_s_worktree_inside_the_checkout_is_not_the_checkout():
    wt = os.path.join(ROOT, ".claude", "worktrees", "agent-x")
    assert run("git restore modules/endpoints.py", cwd=wt).returncode == 0
