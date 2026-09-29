"""C223: every commit in a list's repository publishes, by construction.

Abandon committed through `git(repo, ..., "commit", ...)` directly and never
reached the post-commit push hook, so its commit stayed on the host while
onboarding's commit, one step earlier on the same list and remote, went out
(the operator's R10 demo, 2026-09-29: `7a72258` local, `cf4d96d` on GitHub).
The sweep found the same bypass at four more sites: the rename commit, both
migration commits and the list repository's first commit (`config_git`).

So pushing is a property of committing: `repo.commit()` commits and hands the
commit to the hooks. What is held here:

- no call in the program or its scripts names ``"commit"`` to git except the
  one inside `repo.commit()` (an AST scan, with a floor, and a subprocess
  argument list counts too);
- a caller that commits with ``publish_now=False`` (because it tags between
  committing and pushing) calls `repo.publish()` itself, except `init_repo`,
  whose two commits are carried by the write path that called it (declared);
- nothing outside `repo.publish()` calls `run_post_commit`;
- abandon, driven for real, hands its commit to the hooks.
"""

import ast
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The one function allowed to name "commit" to git.
CHOKEPOINT = ("modules/nsot/repo.py", "commit")
#: Callers that commit with publish_now=False and are NOT required to publish,
#: with the reason.
DEFERS_WITHOUT_PUBLISHING = {
    ("modules/nsot/repo.py", "init_repo"): (
        "its first commit and its .gitignore top-up run only on a write path, whose own "
        "commit follows and pushes the branch, carrying them"),
}


def _program_files():
    out = []
    for top in ("modules", "routes", "scripts"):
        for base, _dirs, files in os.walk(os.path.join(ROOT, top)):
            if "__pycache__" in base:
                continue
            for f in files:
                path = os.path.join(base, f)
                if f.endswith(".py"):
                    out.append(path)
                elif top == "scripts" and "." not in f:
                    with open(path, "rb") as fh:
                        if b"python" in fh.readline():
                            out.append(path)
    out.append(os.path.join(ROOT, "app.py"))
    return out


def _parse(path):
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=path)


def _functions(tree):
    """(qualified name, node) for every function, nested ones included."""
    out = []

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                out.append((name, child))
                walk(child, name + ".")
            elif isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
    walk(tree, "")
    return out


def _enclosing(tree, node):
    best = ""
    for name, fn in _functions(tree):
        if fn.lineno <= node.lineno <= (fn.end_lineno or fn.lineno):
            best = name          # nested functions come later, so the innermost wins
    return best


def _call_name(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def direct_git_commits(tree):
    """Nodes that name "commit" to git: a git()/_git()/git_raw() call with a
    "commit" argument, or a list/tuple holding both "git" and "commit"."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) in ("git", "_git", "git_raw"):
            if any(isinstance(a, ast.Constant) and a.value == "commit" for a in node.args):
                found.append(node)
        elif isinstance(node, (ast.List, ast.Tuple)):
            consts = {e.value for e in node.elts if isinstance(e, ast.Constant)}
            if {"git", "commit"} <= consts:
                found.append(node)
    return found


def deferred_commits(tree):
    """commit(..., publish_now=False) calls."""
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and _call_name(n) in ("commit", "_commit")
            and any(k.arg == "publish_now" and isinstance(k.value, ast.Constant)
                    and k.value.value is False for k in n.keywords)]


def _calls_in(fn, names):
    return any(isinstance(n, ast.Call) and _call_name(n) in names for n in ast.walk(fn))


def _rel(path):
    return os.path.relpath(path, ROOT)


@pytest.fixture(scope="module")
def program():
    trees = {_rel(p): _parse(p) for p in _program_files()}
    assert len(trees) >= 200 and "modules/nsot/repo.py" in trees
    return trees


class TestOneCommit:
    def test_nothing_but_the_chokepoint_names_commit_to_git(self, program):
        sites = [(p, _enclosing(t, n), n.lineno)
                 for p, t in program.items() for n in direct_git_commits(t)]
        # The floor: the scan must see the one it allows, or it sees nothing.
        assert [(p, f) for p, f, _ in sites if (p, f) == CHOKEPOINT], \
            "the scan did not find the chokepoint's own git commit: it is blind"
        stray = [f"{p}:{line} in {f or '<module>'}" for p, f, line in sites
                 if (p, f) != CHOKEPOINT]
        assert not stray, ("a commit outside repo.commit() never reaches the push hook "
                           "(C223): " + "; ".join(stray))

    def test_a_deferred_commit_is_published_by_its_caller(self, program):
        seen, missing = [], []
        for p, tree in program.items():
            fns = dict(_functions(tree))
            for call in deferred_commits(tree):
                where = _enclosing(tree, call)
                seen.append((p, where))
                if (p, where) in DEFERS_WITHOUT_PUBLISHING:
                    continue
                if not _calls_in(fns[where], ("publish",)):
                    missing.append(f"{p}:{call.lineno} in {where}")
        # Floor: save_golden (twice), _commit_paths and init_repo (twice) defer.
        assert len(seen) >= 5, seen
        assert not missing, "a commit deferred and never published: " + "; ".join(missing)

    def test_the_declared_exemptions_exist(self, program):
        present = {(p, _enclosing(t, c)) for p, t in program.items()
                   for c in deferred_commits(t)}
        assert set(DEFERS_WITHOUT_PUBLISHING) <= present, "a ghost exemption"

    def test_only_publish_calls_the_hooks(self, program):
        callers = [f"{p}:{n.lineno} in {_enclosing(t, n)}"
                   for p, t in program.items() for n in ast.walk(t)
                   if isinstance(n, ast.Call) and _call_name(n) == "run_post_commit"
                   and not (p == "modules/nsot/repo.py" and _enclosing(t, n) == "publish")]
        assert not callers, "the hooks are reached around repo.publish(): " + "; ".join(callers)


class TestTheScanCanFail:
    def test_a_planted_direct_commit_is_found(self):
        tree = ast.parse("def f(repo):\n    _repo.git(repo, '-c', 'a=b', 'commit', '-m', 'x')\n")
        assert len(direct_git_commits(tree)) == 1

    def test_a_planted_subprocess_commit_is_found(self):
        tree = ast.parse("import subprocess\nsubprocess.run(['git', '-C', r, 'commit', '-m', m])\n")
        assert len(direct_git_commits(tree)) == 1

    def test_a_read_is_not_a_commit(self):
        tree = ast.parse("git(repo, 'rev-parse', '--verify', 'HEAD^{commit}')\n")
        assert direct_git_commits(tree) == []

    def test_a_planted_deferred_commit_without_publish_is_found(self):
        tree = ast.parse("def f(repo):\n    commit(repo, 'm', publish_now=False)\n")
        (call,) = deferred_commits(tree)
        fn = dict(_functions(tree))["f"]
        assert not _calls_in(fn, ("publish",))


@pytest.fixture
def repo_dir(tmp_path, monkeypatch):
    from modules.nsot import repo as _repo

    list_dir = tmp_path / "probe"
    path = str(list_dir / "config_repo")
    os.makedirs(os.path.join(path, "host_vars"), exist_ok=True)
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
    monkeypatch.setattr("modules.device._load_device_lists_config",
                        lambda: {"lists": {"Probe": "probe"}})
    monkeypatch.setattr("modules.credentials._FILE", str(tmp_path / "creds.json"))
    fired = []
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", fired.append)
    _repo.init_repo(path)
    return path, fired


class TestItPublishesForReal:
    def test_commit_hands_its_sha_and_list_to_the_hooks(self, repo_dir):
        from modules.nsot import repo as _repo

        path, fired = repo_dir
        with open(os.path.join(path, "host_vars", "x.yml"), "w") as fh:
            fh.write("hostname: x\n")
        _repo.git(path, "add", "host_vars/x.yml")
        rc, sha, _ = _repo.commit(path, "x\n\nSource: test\nActor: t\n", source="test")
        head = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        assert rc == 0 and sha == head
        assert [(c["list_name"], c["sha"]) for c in fired] == [("Probe", head)], \
            "the list is resolved from the repository when the caller names none"

    def test_init_repo_commits_without_publishing(self, repo_dir):
        path, fired = repo_dir
        assert fired == [], "init_repo's commits are carried by the caller's"

    def test_a_failed_commit_publishes_nothing(self, repo_dir):
        from modules.nsot import repo as _repo

        path, fired = repo_dir
        rc, sha, _ = _repo.commit(path, "nothing staged")
        assert rc != 0 and sha == "" and fired == []

    def test_abandon_hands_its_commit_to_the_hooks(self, repo_dir):
        """The operator's R10 case, through the real abandon."""
        from tests.test_onboard_abandon import _onboard
        from modules.nsot.onboard import abandon_onboarding

        path, fired = repo_dir
        _onboard(path)
        fired.clear()
        out = abandon_onboarding(path, "bp1", "Probe", actor="t",
                                 remove_netbox=lambda l, h, dry_run=False, **k:
                                 {"ok": True, "deleted": [], "skipped": []})
        head = subprocess.run(["git", "-C", path, "log", "-1", "--format=%H %s"],
                              capture_output=True, text=True).stdout.strip()
        assert "abandon: bp1" in head, (out, head)
        assert [(c["list_name"], c["sha"]) for c in fired] == [("Probe", head.split()[0])]
