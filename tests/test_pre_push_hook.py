"""scripts/hooks/pre-push (C3421): a ci/ branch is pushed only with a passing pre-gate
verdict on its tree; every other ref untouched. Driven by real pushes from a temporary
repository to a bare one, the hook installed as git installs it, the real scripts/nmas-pregate
answering `--verdict`, each verdict written by the pre-gate's own `record_verdict`.

What each test holds: a ci/ branch whose tree has a recorded pass is pushed; one with no
verdict, a failed one, or one where something did not run is refused, naming the tree and the
command to run, and the remote does not move; a branch outside ci/ is pushed with no verdict at
all; deleting a ci/ branch is never asked about.
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "scripts", "hooks", "pre-push")
PREGATE = os.path.join(ROOT, "scripts", "nmas-pregate")
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@example.com")


def _git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=ENV, check=check)


def _pregate():
    loader = importlib.machinery.SourceFileLoader("nmas_pregate_for_hook", PREGATE)
    spec = importlib.util.spec_from_loader("nmas_pregate_for_hook", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _setup(tmp_path):
    """``(repo, bare)``: a checkout holding the pre-gate (and the one module it imports first)
    with the hook installed, and a bare remote it pushes to."""
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(bare))
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    (repo / "scripts").mkdir()
    (repo / "modules").mkdir()
    shutil.copy2(PREGATE, repo / "scripts" / "nmas-pregate")
    shutil.copy2(os.path.join(ROOT, "modules", "app_interpreter.py"),
                 repo / "modules" / "app_interpreter.py")
    (repo / "a.txt").write_text("a\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "remote", "add", "origin", str(bare))
    hooks = repo / ".git" / "hooks"
    shutil.copy2(HOOK, hooks / "pre-push")
    os.chmod(hooks / "pre-push", 0o755)
    return repo, bare


def _commit(repo, branch, text):
    _git(repo, "checkout", "-q", "-B", branch)
    (repo / "a.txt").write_text(text)
    _git(repo, "commit", "-q", "-am", text)
    return _git(repo, "rev-parse", "HEAD").stdout.strip(), \
        _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()


def _verdict(repo, tree, verdict):
    _pregate().record_verdict(str(repo), {
        "tree": tree, "verdict": verdict, "exit": {"pass": 0, "failed": 1}.get(verdict, 4),
        "change": "staged", "base": "", "at": "2026-11-13T00:00:00Z", "message": "not given",
        "files": {}, "notes": [], "working_tree_changed": []})


def _push(repo, *refs):
    return _git(repo, "push", "-q", "origin", *refs, check=False)


def _remote(bare, branch):
    r = _git(bare, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", check=False)
    return r.stdout.strip() or None


def test_a_ci_branch_with_a_passing_verdict_is_pushed(tmp_path):
    repo, bare = _setup(tmp_path)
    sha, tree = _commit(repo, "ci/x", "passed\n")
    _verdict(repo, tree, "pass")
    r = _push(repo, "ci/x")
    assert r.returncode == 0, r.stderr
    assert _remote(bare, "ci/x") == sha


def test_a_ci_branch_with_no_verdict_is_refused_naming_its_tree_and_the_command(tmp_path):
    repo, bare = _setup(tmp_path)
    sha, tree = _commit(repo, "ci/x", "never run\n")
    r = _push(repo, "ci/x")
    assert r.returncode != 0, r.stderr
    assert f"its tree {tree} has no passing pre-gate verdict" in r.stderr
    assert f"scripts/nmas-pregate --range {sha}^..{sha}" in r.stderr
    assert "NO VERDICT recorded" in r.stderr
    assert _remote(bare, "ci/x") is None


def test_a_ci_branch_whose_verdict_failed_or_did_not_finish_is_refused(tmp_path):
    repo, bare = _setup(tmp_path)
    for verdict in ("failed", "not run"):
        _sha, tree = _commit(repo, "ci/x", f"{verdict}\n")
        _verdict(repo, tree, verdict)
        r = _push(repo, "ci/x")
        assert r.returncode != 0, (verdict, r.stderr)
        assert f"its tree {tree} has no passing pre-gate verdict" in r.stderr, verdict
        assert _remote(bare, "ci/x") is None, verdict


def test_a_pass_for_another_tree_does_not_let_a_ci_branch_through(tmp_path):
    repo, bare = _setup(tmp_path)
    _sha, tree = _commit(repo, "ci/x", "one\n")
    _verdict(repo, tree, "pass")
    _commit(repo, "ci/x", "two\n")
    r = _push(repo, "ci/x")
    assert r.returncode != 0, r.stderr
    assert _remote(bare, "ci/x") is None


def test_a_branch_outside_ci_is_pushed_untouched(tmp_path):
    repo, bare = _setup(tmp_path)
    for branch in ("main", "feature", "cix", "lab/ci/x"):
        sha, _tree = _commit(repo, branch, f"{branch}\n")
        r = _push(repo, branch)
        assert r.returncode == 0, (branch, r.stderr)
        assert _remote(bare, branch) == sha, branch


def test_deleting_a_ci_branch_is_not_asked_about(tmp_path):
    repo, bare = _setup(tmp_path)
    _sha, tree = _commit(repo, "ci/x", "passed\n")
    _verdict(repo, tree, "pass")
    assert _push(repo, "ci/x").returncode == 0
    r = _push(repo, ":ci/x")
    assert r.returncode == 0, r.stderr
    assert _remote(bare, "ci/x") is None
