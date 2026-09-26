"""P.4 step 4: nmas-deploy moves the host only to a commit CI passed.

Driven through `main()` against a real bare "origin" and a clone, with the
GitHub API, the restart and the health check injected. HEAD is asserted
UNMOVED on every refusal: a refusal that had already fast-forwarded would be
the defect it exists to prevent.
"""

import importlib.machinery
import importlib.util
import json
import os
import stat
import subprocess
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CI_YML = textwrap.dedent("""\
    name: ci
    on:
      push:
        paths-ignore: ["docs/**", "**/*.md"]
    jobs: {}
    """)


def _script():
    path = os.path.join(ROOT, "scripts", "nmas-deploy")
    loader = importlib.machinery.SourceFileLoader("nmas_deploy", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


def _commit(repo, files, message):
    for rel, text in files.items():
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def world(tmp_path):
    """origin (bare) <- dev (pushes) ; host (the deployed clone)."""
    origin, dev, host = (str(tmp_path / n) for n in ("origin.git", "dev", "host"))
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True)
    subprocess.run(["git", "clone", "-q", origin, dev], check=True, capture_output=True)
    _git(dev, "checkout", "-q", "-b", "main")
    base = _commit(dev, {".github/workflows/ci.yml": CI_YML, "app.py": "v = 1\n"}, "base")
    _git(dev, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", "-b", "main", origin, host], check=True, capture_output=True)
    _git(host, "remote", "set-url", "origin", "github-nmas:owner/repo.git")
    _git(host, "config", "remote.origin.pushurl", origin)
    os.makedirs(os.path.join(host, "data"))

    class W:
        pass
    w = W()
    w.origin, w.dev, w.host, w.base = origin, dev, host, base

    def advance(files, message="change"):
        sha = _commit(dev, files, message)
        _git(dev, "push", "-q", "origin", "main")
        return sha
    w.advance = advance
    return w


def _fetch_from_real_origin(world):
    """The host's origin URL is a GitHub-shaped alias (for the slug); fetch
    through the real bare repository the test built."""
    _git(world.host, "config", "remote.origin.url", world.origin)


def _run(world, runs_by_sha, passed=(), offline=False, suite_rc=0, health="200", reachable=True):
    mod = _script()
    calls = []

    def get(path):
        calls.append(path)
        if not reachable:
            return 0, None, "URLError: timed out"
        if "head_sha=" in path:
            sha = path.split("head_sha=")[1].split("&")[0]
            return 200, {"workflow_runs": runs_by_sha.get(sha, [])}, ""
        return 200, {"workflow_runs": [{"head_sha": s, "path": ".github/workflows/ci.yml",
                                        "status": "completed", "conclusion": "success"}
                                       for s in passed]}, ""

    # slug_of reads the URL; the fetch needs the real path. Give git both.
    real_remote = mod.git

    def git(repo, *args, check=True):
        if args[:2] == ("remote", "get-url"):
            return "github-nmas:owner/repo.git"
        return real_remote(repo, *args, check=check)
    mod.git = git
    _fetch_from_real_origin(world)

    class Out:
        returncode = suite_rc
        stdout = "3942 passed" if suite_rc == 0 else "1 failed, 3941 passed"
    restarted = []
    code = mod.main(["--repo", world.host] + (["--offline"] if offline else []),
                    get=get, run=lambda *a, **k: Out(), restart=lambda: restarted.append(1),
                    health=lambda: health)
    return code, restarted, calls


def _run_entry(sha, conclusion="success", status="completed"):
    return [{"head_sha": sha, "path": ".github/workflows/ci.yml", "status": status,
             "conclusion": conclusion, "created_at": "2026-09-26T00:00:00Z",
             "html_url": f"https://github.com/owner/repo/actions/runs/{sha[:6]}"}]


def _head(world):
    return _git(world.host, "rev-parse", "HEAD")


class TestTheGate:
    def test_a_passing_run_deploys(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, restarted, _ = _run(world, {sha: _run_entry(sha)})
        assert code == 0 and _head(world) == sha and restarted

    def test_a_failed_run_refuses_and_names_it(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, restarted, _ = _run(world, {sha: _run_entry(sha, "failure")})
        err = capsys.readouterr().err
        assert code == 1 and _head(world) == world.base and not restarted
        assert sha[:10] in err and "failure" in err and "actions/runs" in err

    def test_a_running_run_refuses(self, world):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha, None, "in_progress")})
        assert code == 1 and _head(world) == world.base

    def test_a_cancelled_run_is_not_a_pass(self, world):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha, "cancelled")})
        assert code == 1 and _head(world) == world.base

    def test_github_unreachable_is_could_not_ask_and_refuses(self, world, capsys):
        world.advance({"app.py": "v = 2\n"})
        code, restarted, _ = _run(world, {}, reachable=False)
        assert code == 2 and _head(world) == world.base and not restarted
        assert "--offline" in capsys.readouterr().err


class TestNoRunFound:
    """Exit 2, never a pass: the old Jenkins ci_gate's shape, refused."""

    def test_no_run_and_code_changed_is_refused(self, world, capsys):
        world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {}, passed=[world.base])
        assert code == 2 and _head(world) == world.base
        assert "app.py" in capsys.readouterr().err

    def test_no_run_and_no_passing_ancestor_is_refused(self, world):
        world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {}, passed=[])
        assert code == 2 and _head(world) == world.base

    def test_a_docs_only_push_passes_on_its_ancestors_run(self, world, capsys):
        sha = world.advance({"docs/NOTE.md": "x\n", "README.md": "y\n"})
        code, _, _ = _run(world, {}, passed=[world.base])
        assert code == 0 and _head(world) == sha
        assert "paths-ignore" in capsys.readouterr().out


class TestOffline:
    def test_a_failing_suite_here_refuses(self, world, capsys):
        world.advance({"app.py": "v = 2\n"})
        code, _, calls = _run(world, {}, offline=True, suite_rc=1)
        assert code == 3 and _head(world) == world.base and calls == []

    def test_a_passing_suite_here_deploys_without_asking_github(self, world):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, calls = _run(world, {}, offline=True, suite_rc=0)
        assert code == 0 and _head(world) == sha and calls == []


class TestLocalState:
    def test_local_edits_refuse_before_anything(self, world):
        world.advance({"app.py": "v = 2\n"})
        with open(os.path.join(world.host, "app.py"), "w") as fh:
            fh.write("edited\n")
        code, _, calls = _run(world, {})
        assert code == 4 and calls == []

    def test_a_diverged_host_is_not_forced(self, world):
        _commit(world.host, {"local.txt": "x\n"}, "local commit")
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)})
        assert code == 4


class TestAfterTheRestart:
    def test_no_answer_is_exit_5(self, world):
        sha = world.advance({"app.py": "v = 2\n"})
        code, _, _ = _run(world, {sha: _run_entry(sha)}, health="000")
        assert code == 5 and _head(world) == sha


class TestTheRecord:
    def test_every_run_is_one_row_and_owner_only(self, world):
        sha = world.advance({"app.py": "v = 2\n"})
        _run(world, {sha: _run_entry(sha, "failure")})
        _run(world, {sha: _run_entry(sha)})
        path = os.path.join(world.host, "data", "deploy_audit.jsonl")
        rows = [json.loads(l) for l in open(path)]
        assert [r["exit"] for r in rows] == [1, 0]
        assert rows[0]["to"] == sha and rows[0]["gate"] == "ci" and rows[0]["user"]
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


class TestIgnoredPaths:
    @pytest.mark.parametrize("path,ignored", [
        ("README.md", True), ("docs/NSOT_PLAN.md", True), ("docs/a/b/c.txt", True),
        ("app.py", False), ("modules/x.md.py", False), ("scripts/nmas-deploy", False)])
    def test_the_workflow_globs(self, path, ignored):
        assert _script().only_ignored([path], ["docs/**", "**/*.md"]) is ignored

    def test_nothing_changed_is_not_only_ignored(self):
        assert _script().only_ignored([], ["docs/**"]) is False

    def test_the_patterns_are_read_from_the_workflow_not_copied(self):
        src = open(os.path.join(ROOT, "scripts", "nmas-deploy")).read()
        assert "ignored_patterns(repo, target)" in src
        assert '"docs/**"' not in src
