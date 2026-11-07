"""scripts/nmas-fast-checks: the fast checks before every gate (the operator, 2026-11-03), driven
in real temporary repositories with stand-ins for `scripts/nmas-test` and the commit-msg hooks.

What each test holds: a new untracked file is staged, so a scan reading only what git tracks sees
it (H2 and H3's first gate, three whole-repo scans blind to three untracked modules); it is
named explicitly, never marked intent-to-add (C2348); the message is judged by the parent's
hooks and by this tree's own (C2396); and the outer run goes through nmas-control.
"""
import ast
import importlib.machinery
import importlib.util
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-fast-checks")
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@example.com")


def _load():
    loader = importlib.machinery.SourceFileLoader("nmas_fast_checks", SCRIPT)
    spec = importlib.util.spec_from_loader("nmas_fast_checks", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=ENV, check=True).stdout


def _exe(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


def _repo(tmp_path, hook_rc=0):
    """A repository whose committed hook exits *hook_rc*, with a stand-in suite that passes only
    when git tracks the new module (`git ls-files` names it)."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(tmp_path, "init", "-q", str(r))
    (r / "modules").mkdir()
    (r / "modules" / "old.py").write_text("X = 1\n")
    _exe(r / "scripts" / "hooks" / "commit-msg", f"exit {hook_rc}\n")
    _exe(r / "scripts" / "nmas-test",
         'git ls-files | grep -qx modules/new.py && echo "tracked" && exit 0\n'
         'echo "modules/new.py untracked"; exit 1\n')
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    (r / "modules" / "new.py").write_text("Y = 2\n")
    return r


def _inside(mod, repo, monkeypatch, files=(), message=None, base=None):
    monkeypatch.chdir(repo)
    monkeypatch.setattr(mod.os, "environ", dict(ENV))
    args = type("A", (), {"files": list(files), "message": message, "base": base})()
    return mod.inside(args)


def _throwaway(tmp_path, suite, local=()):
    """A checkout ignoring data/ and holding *local* there, and a worktree made from it, as
    nmas-control makes one; the worktree's stand-in suite is *suite*."""
    repo = _repo(tmp_path)
    (repo / ".gitignore").write_text("data/\n")
    _exe(repo / "scripts" / "nmas-test", suite)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "ignore data")
    for name in local:
        (repo / "data").mkdir(exist_ok=True)
        (repo / "data" / name).write_text("term\n")
    tree = tmp_path / "tree"
    _git(repo, "worktree", "add", "-q", "--detach", str(tree), "HEAD")
    return repo, tree


def test_the_operator_s_local_files_are_in_the_throwaway_for_the_run_only(tmp_path, monkeypatch,
                                                                         capfd):
    """C2452: nmas-control copies no ignored file, so the publication scan read no denylist in
    the throwaway. The checkout's local files (found from the worktree's common git directory)
    are copied in for the suite, which passes only when both are there and neither is staged,
    and are gone after it; the checkout's copies stay."""
    mod = _load()
    repo, tree = _throwaway(
        tmp_path, 'test -f data/publication_denylist.txt && test -f data/lab_hosts.json || exit 1\n'
                  'git ls-files --error-unmatch data/publication_denylist.txt 2>/dev/null && exit 1\n'
                  'exit 0\n', local=("publication_denylist.txt", "lab_hosts.json"))
    assert _inside(mod, tree, monkeypatch) == 0
    out = capfd.readouterr().out
    assert "local files for the run: data/publication_denylist.txt, data/lab_hosts.json" in out
    assert not (tree / "data" / "publication_denylist.txt").exists()
    assert not (tree / "data" / "lab_hosts.json").exists()
    assert (repo / "data" / "publication_denylist.txt").read_text() == "term\n"


def test_without_the_checkout_s_local_files_the_suite_runs_without_them(tmp_path, monkeypatch,
                                                                       capfd):
    """A checkout with neither file (CI, a fresh clone) copies none and says so."""
    mod = _load()
    _repo_, tree = _throwaway(tmp_path, "test -f data/publication_denylist.txt && exit 1\nexit 0\n")
    assert _inside(mod, tree, monkeypatch) == 0
    assert "local files for the run: none" in capfd.readouterr().out


def test_on_nmas_control_s_snapshot_the_commit_is_what_differs_from_the_base(tmp_path,
                                                                           monkeypatch, capfd):
    """nmas-control's worktree stands on a snapshot commit holding every edit: set back to the
    checkout's HEAD (the base), the new module is new again and staged, and the parent's hooks
    are the base's (a snapshot whose own hook refuses is not the judge)."""
    mod = _load()
    repo = _repo(tmp_path, hook_rc=0)
    base = _git(repo, "rev-parse", "HEAD").strip()
    _exe(repo / "scripts" / "hooks" / "commit-msg", "exit 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "snapshot")
    msg = tmp_path / "msg.txt"
    msg.write_text("A change\n")
    assert _inside(mod, repo, monkeypatch, message=str(msg), base=base) == 1
    out = capfd.readouterr().out
    assert "2 of them new" not in out and "tracked" in out
    assert "ok: the parent's commit-msg hooks" in out
    assert "REFUSED: this tree's commit-msg hooks" in out
    assert _git(repo, "rev-parse", "HEAD").strip() == base


def test_a_new_untracked_file_is_staged_so_a_tracked_file_scan_sees_it(tmp_path, monkeypatch,
                                                                        capfd):
    mod = _load()
    repo = _repo(tmp_path)
    assert _inside(mod, repo, monkeypatch) == 0
    out = capfd.readouterr().out
    assert "1 of them new" in out and "tracked" in out
    assert "ok: the tests and scans" in out


def test_a_new_file_named_by_the_gate_s_list_is_staged_too(tmp_path, monkeypatch, capfd):
    mod = _load()
    repo = _repo(tmp_path)
    assert _inside(mod, repo, monkeypatch, files=["modules/new.py"]) == 0
    assert "1 file(s), 1 of them new" in capfd.readouterr().out


def test_a_file_left_off_the_list_is_not_staged(tmp_path, monkeypatch, capfd):
    """The commit's files are the gate's `--only` list: one left off is not what the gate will
    test, so the scan does not see it."""
    mod = _load()
    repo = _repo(tmp_path)
    assert _inside(mod, repo, monkeypatch, files=["modules/old.py"]) == 1
    out = capfd.readouterr().out
    assert "modules/new.py untracked" in out and "REFUSED: the tests and scans" in out


def test_the_tests_run_on_exactly_the_commit_s_tree(tmp_path, monkeypatch, capfd):
    """An edit to a file the commit does not hold is set back, and a new file it does not hold
    is gone, before the tests run: the gate tests only the commit's tree."""
    mod = _load()
    repo = _repo(tmp_path)
    (repo / "modules" / "old.py").write_text("X = 99\n")
    (repo / "modules" / "stray.py").write_text("Z = 3\n")
    _exe(repo / "scripts" / "nmas-test",
         'grep -qx "X = 1" modules/old.py && [ ! -e modules/stray.py ] && '
         'git ls-files | grep -qx modules/new.py && echo "the commit\'s tree" && exit 0\n'
         'echo "not the commit\'s tree"; exit 1\n')
    _git(repo, "add", "scripts/nmas-test")
    _git(repo, "commit", "-q", "-m", "suite")
    assert _inside(mod, repo, monkeypatch, files=["modules/new.py"]) == 0
    assert "the commit's tree" in capfd.readouterr().out


def test_new_files_are_named_never_marked_intent_to_add():
    """C2348: an intent-to-add entry stops `git stash create`, and so nmas-control."""
    tree = ast.parse(open(SCRIPT, encoding="utf-8").read())
    calls = [[a.value for a in n.args if isinstance(a, ast.Constant)]
             for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "git"]
    adds = [c for c in calls if c[:1] == ["add"]]
    assert adds and all("-N" not in c and "--intent-to-add" not in c for c in adds), adds
    assert ["ls-files", "--others", "--exclude-standard", "-z"] in calls


def test_the_message_is_judged_by_the_parent_s_hooks_and_this_tree_s(tmp_path, monkeypatch,
                                                                     capfd):
    """C2396: the parent's hooks pass, this tree's tightened hook refuses, and the run says so."""
    mod = _load()
    repo = _repo(tmp_path, hook_rc=0)
    _exe(repo / "scripts" / "hooks" / "commit-msg", "exit 1\n")
    msg = tmp_path / "msg.txt"
    msg.write_text("A change\n")
    assert _inside(mod, repo, monkeypatch, message=str(msg)) == 1
    out = capfd.readouterr().out
    assert "ok: the parent's commit-msg hooks" in out
    assert "REFUSED: this tree's commit-msg hooks" in out
    assert "parent" not in _git(repo, "worktree", "list")


def test_the_parent_s_refusal_is_said_too(tmp_path, monkeypatch, capfd):
    mod = _load()
    repo = _repo(tmp_path, hook_rc=1)
    _exe(repo / "scripts" / "hooks" / "commit-msg", "exit 0\n")
    msg = tmp_path / "msg.txt"
    msg.write_text("A change\n")
    assert _inside(mod, repo, monkeypatch, message=str(msg)) == 1
    out = capfd.readouterr().out
    assert "REFUSED: the parent's commit-msg hooks" in out
    assert "ok: this tree's commit-msg hooks" in out


def test_the_changed_tests_run_then_the_scans_each_once(tmp_path):
    mod = _load()
    (tmp_path / "tests").mkdir()
    for name in ("test_a.py", "test_doc_tests.py"):
        (tmp_path / "tests" / name).write_text("")
    got = mod.tests_of(["tests/test_a.py", "tests/test_doc_tests.py", "tests/helper.py",
                        "modules/m.py"], str(tmp_path))
    assert got == ["tests/test_a.py", "tests/test_doc_tests.py"]


def test_a_changed_test_in_a_declared_data_folder_is_not_named_to_pytest(tmp_path):
    """pytest collects a file named on its command line even inside a `collect_ignore`d
    folder, so the selector leaves out tests/data_folders.py's folders itself (C2633: the job
    gate's fixture jobs hold planted failing tests; the first fast-checks run over them
    errored). An entry outside tests/fixtures/ declares nothing."""
    mod = _load()
    (tmp_path / "tests" / "fixtures" / "jobs" / "a").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "jobsy").mkdir(parents=True)
    decl = tmp_path / "tests" / "data_folders.py"
    decl.write_text('DATA_FOLDERS = ("tests/fixtures/jobs/",)\n')
    for name in ("tests/test_a.py", "tests/fixtures/jobs/a/test_job.py",
                 "tests/fixtures/jobsy/test_b.py"):
        (tmp_path / name).write_text("")
    got = mod.tests_of(["tests/test_a.py", "tests/fixtures/jobs/a/test_job.py",
                        "tests/fixtures/jobsy/test_b.py"], str(tmp_path))
    assert got == ["tests/test_a.py", "tests/fixtures/jobsy/test_b.py"]
    decl.write_text('DATA_FOLDERS = ("tests/",)\n')
    assert mod.tests_of(["tests/test_a.py"], str(tmp_path)) == ["tests/test_a.py"]
    decl.unlink()
    got = mod.tests_of(["tests/fixtures/jobs/a/test_job.py"], str(tmp_path))
    assert got == ["tests/fixtures/jobs/a/test_job.py"]


def test_the_outer_run_goes_through_nmas_control(monkeypatch):
    mod = _load()
    seen = {}

    def fake_run(cmd, cwd=None, **kw):
        if cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")
        seen.update(cmd=cmd, cwd=cwd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod.sys, "argv", ["nmas-fast-checks", "modules/a.py"])
    assert mod.main() == 0
    assert seen["cmd"][:2] == [os.path.join(ROOT, "scripts", "nmas-control"), "--"]
    assert seen["cmd"][-4:] == ["--inside", "--base", "abc123", "modules/a.py"]
    assert seen["cwd"] == ROOT
