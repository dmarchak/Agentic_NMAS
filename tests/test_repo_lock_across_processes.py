"""The list repository's lock holds across PROCESSES (CONCURRENCY_AUDIT R1, R24, R25).

`repo_lock()` was a `threading.Lock` per repository, so a host CLI committing (`nmas-retire`,
the rotation, `nmas-golden-state`, the repair scripts) beside the app was serialised by
nothing: another process's staged file rode into this commit, or `stage_exactly` refused
naming it. The only two-writer test used threads. Here a REAL second process holds the
lock with a file staged:

- the app's commit waits for it, and each commit carries only its own file;
- the holder is recorded beside the repository, and a long wait is logged naming it;
- a holder that dies releases it (the kernel drops the `flock`);
- staging and committing are refused outside the lock;
- a save compares what is COMMITTED, never the working file (R25);
- a reader takes no optional git lock, and a tag that fails is reported, never dropped (R24).
"""

import logging
import os
import subprocess
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git is not available")

#: The other process: holds the lock with its file STAGED, says so, waits, then commits
#: (or dies holding it).
CHILD = '''
import os, sys, time
sys.path.insert(0, {root!r})
from modules.nsot import repo as R
repo, marker, mode = sys.argv[1:4]
with R.repo_lock(repo):
    with open(os.path.join(repo, "host_vars", "a.yml"), "w") as fh:
        fh.write("hostname: a\\n")
    R.git(repo, "add", "--", "host_vars/a.yml")
    with open(marker, "w") as fh:
        fh.write(str(os.getpid()))
    time.sleep(1.5)
    if mode == "die":
        os._exit(3)
    rc, sha, err = R.commit(repo, "a\\n\\nSource: test\\nActor: t\\n", publish_now=False)
    sys.exit(rc)
'''


@pytest.fixture
def repo(tmp_path, monkeypatch):
    from modules.nsot import repo as R
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    path = str(tmp_path / "lab" / "config_repo")
    R.init_repo(path)
    return path


def _child(tmp_path, repo, mode="commit"):
    script = tmp_path / "child.py"
    script.write_text(CHILD.format(root=ROOT))
    marker = str(tmp_path / "staged")
    proc = subprocess.Popen([sys.executable, str(script), repo, marker, mode],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.time() + 30
    while not os.path.exists(marker) or not open(marker).read():
        assert time.time() < deadline, proc.communicate(timeout=5)
        assert proc.poll() is None, proc.communicate()
        time.sleep(0.05)
    return proc, int(open(marker).read())


def _files_of(repo, rev):
    out = subprocess.run(["git", "-C", repo, "show", "--name-only", "--format=", rev],
                         capture_output=True, text=True).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


class TestTwoProcesses:
    def test_a_commit_waits_for_the_other_process_and_carries_only_its_own(
            self, repo, tmp_path, monkeypatch, caplog):
        from modules.nsot import repo as R
        monkeypatch.setattr(R, "REPO_LOCK_WAIT_LOG_SECONDS", 0.3)
        proc, pid = _child(tmp_path, repo)
        holder = open(R.RepoLock(repo).holder_path).read()
        assert f"pid {pid} " in holder, holder
        with caplog.at_level(logging.WARNING, logger="modules.nsot.repo"):
            with R.repo_lock(repo):
                with open(os.path.join(repo, "host_vars", "b.yml"), "w") as fh:
                    fh.write("hostname: b\n")
                R.stage_exactly(repo, ["host_vars/b.yml"])
                rc, _sha, err = R.commit(repo, "b\n\nSource: test\nActor: t\n",
                                         publish_now=False)
        assert proc.wait(timeout=30) == 0, proc.communicate()
        assert rc == 0, err
        assert _files_of(repo, "HEAD~1") == ["host_vars/a.yml"]
        assert _files_of(repo, "HEAD") == ["host_vars/b.yml"]
        assert any(f"held by pid {pid} " in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]
        assert not os.path.exists(R.RepoLock(repo).holder_path), "released, holder cleared"

    def test_a_holder_that_dies_releases_it(self, repo, tmp_path):
        from modules.nsot import repo as R
        proc, _pid = _child(tmp_path, repo, mode="die")
        got = []

        def take():
            with R.repo_lock(repo):
                got.append(True)

        t = threading.Thread(target=take, daemon=True)
        t.start()
        t.join(timeout=20)
        assert got, "the lock was not released when its holder died"
        assert proc.wait(timeout=10) == 3


class TestOutsideTheLock:
    def test_staging_and_committing_are_refused(self, repo):
        from modules.nsot import repo as R
        with pytest.raises(R.LockNotHeld, match="staging outside the repository lock"):
            R.stage_exactly(repo, ["host_vars/x.yml"])
        with pytest.raises(R.LockNotHeld, match="a commit outside the repository lock"):
            R.commit(repo, "x")

    def test_the_lock_is_re_entrant_in_its_thread(self, repo):
        from modules.nsot import repo as R
        with R.repo_lock(repo):
            with R.repo_lock(repo):
                assert R.RepoLock(repo).held()
            assert R.RepoLock(repo).held()
        assert not R.RepoLock(repo).held()


class TestWhatIsCommitted:
    def test_a_save_compares_head_not_the_working_file(self, repo, monkeypatch,
                                                      intent_matches):
        """R25: a working file already holding the new capture (another writer's, or a
        hand edit) made the save say "unchanged" while HEAD held the old golden."""
        from modules.nsot import repo as R
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: os.path.dirname(repo))
        item = R.GoldenItem("r1", "hostname r1\n", "203.0.113.1", netbox_id=1, platform="cisco_ios")
        assert R.save_golden("Lab", [item], allow_new=True)["ok"]
        new = R.GoldenItem("r1", "hostname r1\nntp server 192.0.2.1\n", "203.0.113.1",
                           netbox_id=1, platform="cisco_ios")
        with open(os.path.join(repo, "golden", "r1.cfg"), "w", newline="\n") as fh:
            fh.write(R.golden_body("r1", "203.0.113.1", new.config_text))
        got = R.save_golden("Lab", [new])
        assert got["ok"] and got["changed"] == ["r1"], got
        shown = subprocess.run(["git", "-C", repo, "show", "HEAD:golden/r1.cfg"],
                               capture_output=True, text=True).stdout
        assert "ntp server 192.0.2.1" in shown


class TestReadersAndTags:
    def test_a_reader_takes_no_optional_lock(self):
        from modules.nsot import repo as R
        assert R._git_env()["GIT_OPTIONAL_LOCKS"] == "0"

    def test_a_tag_that_fails_is_reported(self, repo, monkeypatch, intent_matches):
        from modules.nsot import repo as R
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: os.path.dirname(repo))
        real = R.git

        def refuse_tags(r, *args):
            if args[:2] == ("tag", "-a"):
                return 128, "", "fatal: cannot lock ref"
            return real(r, *args)

        monkeypatch.setattr(R, "git", refuse_tags)
        got = R.save_golden("Lab", [R.GoldenItem("r1", "hostname r1\n", "203.0.113.1",
                                                 netbox_id=1, platform="cisco_ios")], allow_new=True)
        assert got["ok"] and got["tags"] == []
        assert got["tag_failures"] and "cannot lock ref" in got["tag_failures"][0]


class TestACommitNamesItsPaths:
    def test_a_file_staged_by_a_bypass_is_not_carried(self, repo, monkeypatch):
        """R1 (3): a person's `git add` on the host takes no lock. A file it stages between
        this commit's staging and its commit stays staged and is NOT in this commit."""
        from modules.nsot import repo as R
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: os.path.dirname(repo))
        for name in ("mine", "theirs"):
            with open(os.path.join(repo, "host_vars", f"{name}.yml"), "w") as fh:
                fh.write(f"hostname: {name}\n")
        real = R.stage_exactly

        def stage_then_bypass(r, paths):
            got = real(r, paths)
            subprocess.run(["git", "-C", r, "add", "--", "host_vars/theirs.yml"], check=True)
            return got

        monkeypatch.setattr(R, "stage_exactly", stage_then_bypass)
        got = R._commit_paths("Lab", ["host_vars/mine.yml"], "intent: mine", [], "test")
        assert got["ok"], got
        assert _files_of(repo, "HEAD") == ["host_vars/mine.yml"]
        staged = subprocess.run(["git", "-C", repo, "diff", "--cached", "--name-only"],
                                capture_output=True, text=True).stdout.split()
        assert staged == ["host_vars/theirs.yml"]
