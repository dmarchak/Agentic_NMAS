"""`scripts/nmas-rollback` (C1669; the operator, 2026-10-25): the application rolled back to an
earlier commit as one forward revert whose TREE is that commit's, checked by the tool. In real
temporary repositories:

- a rollback over a docs-only commit lands a commit whose tree is the target's, listing what it
  reverted, with `Host-Step-None`;
- a dirty working tree, a target that is not an earlier commit, and a reverted host-installed
  file with no `--host-step` each refuse, leaving HEAD and the tree as they were;
- with `--host-step`, the step is the commit's `Host-Step-After`;
- a test the revert removes is named in a `Test-Weakened` trailer under C1669, from the
  weakening check's own findings.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "scripts", "nmas-rollback")
ENV = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@example.com")


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=ENV, check=True).stdout.strip()


def _commit(repo, files, message):
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if text is None:
            path.unlink()
        else:
            path.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    _git(tmp_path, "init", "-q", "-b", "main", str(r))
    base = _commit(r, {"docs/a.md": "one\n", "app.py": "v = 1\n"}, "base")
    return r, base


def _roll(repo, to, *extra):
    return subprocess.run([sys.executable, TOOL, "--repo", str(repo), to, *extra],
                          capture_output=True, text=True, env=ENV)


def _tree(repo, sha):
    return _git(repo, "rev-parse", f"{sha}^{{tree}}")


def test_a_rollback_over_a_docs_commit_lands_the_targets_tree(repo):
    r, base = repo
    bad = _commit(r, {"docs/a.md": "two\n"}, "bad: a docs change")
    out = _roll(r, base)
    assert out.returncode == 0, out.stdout + out.stderr
    head = _git(r, "rev-parse", "HEAD")
    assert head != base and _git(r, "rev-parse", "HEAD~1") == bad, "a forward commit"
    assert _tree(r, head) == _tree(r, base)
    body = _git(r, "log", "-1", "--format=%B")
    assert body.startswith(f"Rollback to {base[:10]}: 1 commit(s) reverted")
    assert f"- {bad[:10]} bad: a docs change" in body
    assert "Host-Step-None: no host-installed file is reverted" in body
    assert f"its tree is {base[:10]}'s ({_tree(r, base)[:10]})" in out.stdout


def test_several_commits_are_reverted_in_one(repo):
    r, base = repo
    one = _commit(r, {"docs/a.md": "two\n"}, "one")
    two = _commit(r, {"app.py": "v = 2\n"}, "two")
    out = _roll(r, base)
    assert out.returncode == 0, out.stdout + out.stderr
    assert _tree(r, "HEAD") == _tree(r, base)
    body = _git(r, "log", "-1", "--format=%B")
    assert "2 commit(s) reverted" in body and two[:10] in body and one[:10] in body


@pytest.mark.parametrize("case", ["dirty", "not-earlier", "is-head"])
def test_a_refusal_changes_nothing(repo, case):
    r, base = repo
    bad = _commit(r, {"docs/a.md": "two\n"}, "bad")
    to = base
    if case == "dirty":
        (r / "docs" / "a.md").write_text("an edit in progress\n")
    elif case == "not-earlier":
        _git(r, "checkout", "-q", "-b", "side", base)
        to = _commit(r, {"docs/b.md": "side\n"}, "side")
        _git(r, "checkout", "-q", "main")
    else:
        to = bad
    out = _roll(r, to)
    assert out.returncode != 0 and "REFUSED" in out.stdout + out.stderr, out.stdout
    assert _git(r, "rev-parse", "HEAD") == bad
    assert _git(r, "status", "--porcelain") == ("M docs/a.md" if case == "dirty" else "")


def test_a_revert_whose_tree_differs_is_refused_and_undone(repo, monkeypatch):
    """The equality is the tool's own check: a revert landing on any other tree (here
    `write-tree` made to answer another hash) refuses, and HEAD and the tree are as before."""
    import importlib.machinery
    import importlib.util
    r, base = repo
    bad = _commit(r, {"docs/a.md": "two\n"}, "bad")
    loader = importlib.machinery.SourceFileLoader("nmas_rollback_t", TOOL)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    real = mod.git

    def git(repo_, *args, check=True):
        return "0" * 40 if args[:1] == ("write-tree",) else real(repo_, *args, check=check)
    monkeypatch.setattr(mod, "git", git)
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(SystemExit) as got:
        mod.main(["--repo", str(r), base])
    assert "is not" in str(got.value) and "nothing changed" in str(got.value)
    assert _git(r, "rev-parse", "HEAD") == bad and _git(r, "status", "--porcelain") == ""


def test_a_reverted_host_installed_file_needs_its_host_step(repo):
    r, base = repo
    bad = _commit(r, {"scripts/nmas-deploy": "#!/bin/sh\necho two\n"}, "bad: the deploy tool")
    out = _roll(r, base)
    assert out.returncode != 0 and "--host-step" in out.stdout + out.stderr
    assert "scripts/nmas-deploy" in out.stdout + out.stderr
    assert _git(r, "rev-parse", "HEAD") == bad and _git(r, "status", "--porcelain") == ""
    out = _roll(r, base, "--host-step", "re-install the updater's root-owned copies")
    assert out.returncode == 0, out.stdout + out.stderr
    assert ("Host-Step-After: re-install the updater's root-owned copies"
            in _git(r, "log", "-1", "--format=%B"))


def test_a_test_the_revert_removes_is_named_under_c1669(repo):
    r, base = repo
    _commit(r, {"tests/test_new.py": "def test_it():\n    assert 1 + 1 == 2\n"}, "bad: a test")
    out = _roll(r, base)
    assert out.returncode == 0, out.stdout + out.stderr
    body = _git(r, "log", "-1", "--format=%B")
    trailers = [ln for ln in body.splitlines() if ln.startswith("Test-Weakened:")]
    assert len(trailers) == 1 and "test_it" in trailers[0] and "— C1669:" in trailers[0], body
