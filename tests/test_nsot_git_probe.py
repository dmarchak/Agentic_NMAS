"""C171: the NSoT git probe asks about what the program USES. Each list's
repository is derived (`data/lists/<slug>/config_repo`) and each list's
remote is its own `remote.json`; the six `nsot_git_*` location settings
describe Phase 0's single global repository and nothing reads them. The probe
reported "not configured" while the repositories committed all evening: a
working integration reported unconfigured (C166's lesson in the status bar).

On real repositories, built with git in a temporary lists directory."""

import os
import subprocess

import pytest

from modules import config
from modules.integrations.nsot_git import NsotGitIntegration
from modules.nsot import remote as R


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))


@pytest.fixture
def lists(tmp_path, monkeypatch):
    """Three lists: one with a committed repository, one never committed, one
    whose directory is not a repository."""
    root = tmp_path / "lists"
    monkeypatch.setattr(config, "LISTS_DIR", str(root))
    good = root / "lab" / "config_repo"
    good.mkdir(parents=True)
    git(str(good), "init", "-q", "-b", "main")
    (good / "golden").mkdir()
    (good / "golden" / "r1.cfg").write_text("hostname r1\n")
    git(str(good), "add", "-A")
    git(str(good), "commit", "-q", "-m", "golden: r1")
    (root / "fresh").mkdir()
    (root / "broken" / "config_repo").mkdir(parents=True)
    entries = [{"name": "Lab", "filename": "lab"}, {"name": "Fresh", "filename": "fresh"}]
    from modules import device
    monkeypatch.setattr(device, "get_device_lists", lambda: list(entries))
    remotes = {}
    monkeypatch.setattr(R, "load_remote", lambda name: remotes.get(name))
    return entries, remotes


class TestTheProbe:
    def test_it_is_configured_by_derivation_never_not_configured(self, lists):
        st = NsotGitIntegration().status()
        assert st["state"] == "up", st
        assert "configured by derivation" in st["message"]
        assert "Lab: HEAD" in st["message"] and "no remote" in st["message"]
        assert "Fresh: no repository yet" in st["message"]

    def test_a_directory_that_is_not_a_repository_is_down_by_name(self, lists):
        entries, _ = lists
        entries.append({"name": "Broken", "filename": "broken"})
        st = NsotGitIntegration().status()
        assert st["state"] == "down" and "Broken:" in st["message"]
        assert "not a readable repository" in st["message"]

    def test_a_failed_last_push_is_down_naming_it(self, lists):
        _, remotes = lists
        remotes["Lab"] = {"owner": "o", "repo": "r", "last_push_failure": {
            "at": "2026-09-28T21:00:00Z", "reason": "Permission denied (publickey)"}}
        st = NsotGitIntegration().status()
        assert st["state"] == "down" and "last push FAILED" in st["message"]
        assert "Permission denied" in st["message"]

    def test_a_remote_with_a_last_push_names_it(self, lists):
        _, remotes = lists
        remotes["Lab"] = {"owner": "o", "repo": "r", "last_push": {"at": "2026-09-28T21:05:00Z"}}
        st = NsotGitIntegration().status()
        assert st["state"] == "up" and "remote o/r, last push 2026-09-28T21:05:00Z" in st["message"]

    def test_the_global_location_settings_are_read_by_nothing_but_the_form(self):
        """C171's other half (7.7): the six Phase 0 settings. A pin on the
        property this probe no longer depends on: it reads none of them."""
        src = open(NsotGitIntegration.__module__.replace(".", os.sep) + ".py").read()
        body = src[src.index("def test_connection"):]
        for key in ("nsot_git_repo_path", "nsot_git_remote_url", "nsot_git_branch"):
            assert key not in body, key
