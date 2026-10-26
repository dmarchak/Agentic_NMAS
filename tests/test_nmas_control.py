"""`scripts/nmas-control` (the operator, 2026-10-26): a control, canary or mutation run in a
throwaway worktree made from a snapshot of the current state, never in the working tree.

In real temporary repositories: an uncommitted edit, a staged one and an untracked file are all
present in the worktree, an ignored file is not; the command's own edits stay there; the working
tree's bytes and `git status` are identical before and after, and no worktree is left behind;
an argument naming the working tree is refused before anything runs; a working tree that changes
during the run is said and exits 3.
"""
import hashlib
import importlib.machinery
import importlib.util
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-control")


def _load():
    loader = importlib.machinery.SourceFileLoader("nmas_control", SCRIPT)
    spec = importlib.util.spec_from_loader("nmas_control", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


C = _load()


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "checkout"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "t")
    (r / ".gitignore").write_text("ignored.txt\n")
    (r / "a.py").write_text("committed\n")
    (r / "b.py").write_text("committed b\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "one")
    (r / "a.py").write_text("edited, not committed\n")          # an uncommitted edit
    (r / "b.py").write_text("staged b\n")
    git(r, "add", "b.py")                                        # a staged one
    (r / "new.py").write_text("untracked\n")                     # an untracked file
    (r / "ignored.txt").write_text("ignored\n")                  # an ignored one
    return r


def _state(r):
    files = {}
    for p in sorted(r.rglob("*")):
        if ".git" in p.relative_to(r).parts or not p.is_file():
            continue
        files[str(p.relative_to(r))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return files, git(r, "status", "--porcelain=v1", "--untracked-files=all")


CHECK = ("import os, sys; "
         "assert open('a.py').read() == 'edited, not committed\\n', 'the edit'; "
         "assert open('b.py').read() == 'staged b\\n', 'the staged edit'; "
         "assert open('new.py').read() == 'untracked\\n', 'the untracked file'; "
         "assert not os.path.exists('ignored.txt'), 'an ignored file'; "
         "open('a.py', 'w').write('the control broke it\\n'); "
         "os.remove('new.py')")


def test_the_current_state_is_in_the_worktree_and_the_working_tree_is_untouched(repo):
    before = _state(repo)
    worktrees = git(repo, "worktree", "list")
    assert C.run([sys.executable, "-c", CHECK], root=str(repo)) == 0
    assert _state(repo) == before, "the working tree's bytes and git status, unchanged"
    assert git(repo, "worktree", "list") == worktrees, "no worktree left behind"
    assert git(repo, "stash", "list") == "", "no stash entry recorded"


def test_the_command_s_exit_code_is_returned(repo):
    assert C.run([sys.executable, "-c", "raise SystemExit(7)"], root=str(repo)) == 7


def test_an_argument_naming_the_working_tree_is_refused_before_anything_runs(repo, capsys):
    before = _state(repo)
    target = os.path.join(str(repo), "a.py")
    got = C.run([sys.executable, "-c", f"open({target!r}, 'w').write('x')"], root=str(repo))
    assert got == 2 and "names the working tree" in capsys.readouterr().err
    assert _state(repo) == before


def test_a_working_tree_changed_during_the_run_is_said(repo, capsys, monkeypatch):
    """A write the argument check cannot see (its path in the environment) is caught after."""
    monkeypatch.setenv("TARGET", os.path.join(str(repo), "a.py"))
    code = "import os; open(os.environ['TARGET'], 'w').write('changed')"
    assert C.run([sys.executable, "-c", code], root=str(repo)) == 3
    assert "THE WORKING TREE CHANGED during the run: ['a.py'" in capsys.readouterr().err


def test_no_command_is_refused(repo):
    assert C.run([], root=str(repo)) == 2
