"""A commit that changes a file a person installs on the host says what the
host needs (the operator, 2026-09-30): `Host-Step:` or `Host-Step-None:`,
refused by the commit-msg hook and by CI over the pushed range.

Driven against REAL git repositories. The rule's first run, over the
operator's range af8630a..e7b80c7, named 7551c2a (scripts/nmas-deploy changed,
no step said): the case it exists for.
"""
import importlib.machinery
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "nmas-host-step-check"


@pytest.fixture(scope="module")
def hs():
    loader = importlib.machinery.SourceFileLoader("nmas_host_step_check", str(SCRIPT))
    spec = importlib.util.spec_from_loader("nmas_host_step_check", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "README").write_text("x\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "start")
    return tmp_path


def _commit(repo, path, message):
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(p.read_text() + "y\n" if p.exists() else "y\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _run(repo, *args):
    return subprocess.run(["python3", str(SCRIPT), *args], cwd=repo,
                          capture_output=True, text=True)


class TestTheRange:
    def test_a_host_file_with_nothing_said_is_refused_by_name(self, repo):
        sha = _commit(repo, "scripts/nmas-deploy", "change the gate")
        p = _run(repo, "--range", "HEAD~1..HEAD")
        assert p.returncode == 1
        assert sha[:12] in p.stderr and "scripts/nmas-deploy" in p.stderr
        assert "Host-Step-None" in p.stderr

    @pytest.mark.parametrize("path", ["deploy/update/nmas-update", "deploy/systemd/x.service",
                                      "deploy/topology/rcn-topology.py", "scripts/nmas-deploy"])
    def test_a_step_said_passes(self, repo, path):
        _commit(repo, path, "change\n\nHost-Step: re-install it as root")
        assert _run(repo, "--range", "HEAD~1..HEAD").returncode == 0

    def test_none_with_its_reason_passes(self, repo):
        _commit(repo, "deploy/update/nmas-update", "a comment\n\nHost-Step-None: a comment only")
        assert _run(repo, "--range", "HEAD~1..HEAD").returncode == 0

    def test_an_empty_trailer_is_not_a_statement(self, repo):
        _commit(repo, "deploy/update/nmas-update", "change\n\nHost-Step:")
        assert _run(repo, "--range", "HEAD~1..HEAD").returncode == 1

    def test_a_file_not_installed_on_the_host_needs_nothing(self, repo):
        _commit(repo, "modules/x.py", "change")
        _commit(repo, "scripts/nmas-deploy-notes", "a sibling name, not the gate")
        assert _run(repo, "--range", "HEAD~2..HEAD").returncode == 0

    def test_every_commit_in_the_range_is_asked(self, repo):
        bad = _commit(repo, "deploy/systemd/a.timer", "first")
        _commit(repo, "deploy/systemd/b.timer", "second\n\nHost-Step: install b")
        p = _run(repo, "--range", "HEAD~2..HEAD")
        assert p.returncode == 1 and bad[:12] in p.stderr and p.stderr.count("REFUSED") == 1

    def test_a_range_git_cannot_read_is_not_a_pass(self, repo):
        p = _run(repo, "--range", "nosuch..HEAD")
        assert p.returncode == 2 and "COULD NOT ASK" in p.stderr


class TestTheCommitBeingMade:
    def test_the_staged_files_and_the_message_are_read(self, repo, tmp_path_factory):
        (repo / "deploy" / "update").mkdir(parents=True)
        (repo / "deploy" / "update" / "nmas-update").write_text("z\n")
        _git(repo, "add", "-A")
        msg = tmp_path_factory.mktemp("m") / "MSG"
        msg.write_text("change\n\n# Host-Step: in git's comment template, not said\n")
        assert _run(repo, "--message", str(msg)).returncode == 1
        msg.write_text("change\n\nHost-Step: re-install the updater\n")
        assert _run(repo, "--message", str(msg)).returncode == 0

    def test_the_hook_runs_the_check(self):
        hook = (ROOT / "scripts" / "hooks" / "commit-msg").read_text()
        assert 'nmas-host-step-check" --message "$1"' in hook
        assert os.access(ROOT / "scripts" / "hooks" / "commit-msg", os.X_OK)


class TestOneList:
    def test_every_updater_source_needs_a_word_about_the_host(self, hs):
        from modules.readers.app_pushed import UPDATER_SOURCES
        assert len(UPDATER_SOURCES) >= 4
        assert hs.host_paths(UPDATER_SOURCES) == list(UPDATER_SOURCES)

    def test_none_is_never_listed_as_a_step_to_do(self):
        from modules.readers.app_pushed import HOST_STEP
        assert HOST_STEP.findall("x\n\nHost-Step-None: a comment only\n") == []
        assert HOST_STEP.findall("x\n\nHost-Step: do it\n") == ["do it"]

    def test_ci_runs_it_over_the_pushed_range(self):
        doc = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
        runs = [s.get("run", "") for s in doc["jobs"]["test"]["steps"]]
        assert any('nmas-host-step-check --range "$RANGE"' in r for r in runs)
