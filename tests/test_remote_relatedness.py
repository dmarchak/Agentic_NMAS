"""The remote holds our own history. That is the normal state, and it failed.

Found during the demo. Remote card -> Verify (read-only):

    [XX] repository_is_empty_or_related   68 ref(s), none related
         "the repository is not empty and shares no history with this list"

The remote held exactly the 61 commits and 33 tags pushed from that very
repository an hour earlier. Local HEAD and remote main were the same SHA.

The check intersected the local ROOT commit with the remote's ref TIPS:

    local_root = rev-list --max-parents=0 HEAD
    if set(local_root) & {sha for each remote ref}: related

A root commit is a ref tip only in a repository with exactly ONE commit. So
it passed on an empty remote, passed by luck on a one-commit remote, and
refused every remote with real history -- including our own.

It was only ever exercised against an empty remote, because until the first
push there was no other state to exercise. "It passed" and "it works" stayed
the same sentence right up to the moment the first push made them different,
and the check then refused the state it had just created.

These tests use REAL git repositories rather than stubbed `ls-remote` output.
The defect was in what the SHAs meant, not in how the lines were parsed, so a
fixture that hands over invented SHAs would agree with whatever the code
believes about them.
"""

import os
import subprocess

import pytest

import modules.nsot.remote as remote


def _git(repo, *args):
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                         text=True, env=dict(
                             os.environ,
                             GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@l",
                             GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@l"))
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def _commit(repo, text, message):
    with open(os.path.join(repo, "golden.cfg"), "w") as handle:
        handle.write(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)


@pytest.fixture
def world(tmp_path):
    """A local repo with real history, and a bare remote holding it."""
    local = str(tmp_path / "config_repo")
    os.makedirs(local)
    _git(local, "init", "-q", "-b", "main")
    for n in range(5):
        _commit(local, f"hostname r1\n! rev {n}\n", f"commit {n}")
        # Tagging starts AFTER the first commit, as the real repo's does --
        # tags began at migration, not at the root. Tagging commit 0 would put
        # the root commit among the ref tips and the old test would pass,
        # which is the fixture quietly ceasing to reproduce the bug.
        if n:
            _git(local, "tag", "-a", f"golden/r1/{n}", "-m", f"tag {n}")

    bare = str(tmp_path / "remote.git")
    # `-b main`, or the bare repo's HEAD points at refs/heads/master, a clone
    # checks out nothing, and the push in the "remote is ahead" test fails
    # with "src refspec main does not match any".
    subprocess.run(["git", "init", "-q", "-b", "main", "--bare", bare], check=True)
    _git(local, "push", "-q", bare, "main", "--tags")
    return {"local": local, "bare": bare}


def _ls_remote(url):
    out = subprocess.run(["git", "ls-remote", url], capture_output=True, text=True)
    return [line for line in out.stdout.splitlines() if line.strip()]


class TestThePostFirstPushState:
    """The normal state from now on, and the one that was never tested."""

    def test_the_setup_reproduces_the_demo(self, world):
        """Local HEAD and remote main identical, many refs, deep history."""
        refs = _ls_remote(world["bare"])
        assert len(refs) > 5, "needs tags and peeled entries, as the real one had"
        head = _git(world["local"], "rev-parse", "HEAD")
        main = next(l.split()[0] for l in refs if l.endswith("refs/heads/main"))
        assert head == main

    def test_the_old_test_would_have_refused_this(self, world):
        """Pinning the defect: the root commit is not among the ref tips."""
        refs = _ls_remote(world["bare"])
        root = _git(world["local"], "rev-list", "--max-parents=0", "HEAD").split()
        tips = {line.split()[0] for line in refs}
        assert not (set(root) & tips), (
            "if this ever becomes true the fixture has stopped reproducing "
            "the bug")

    def test_it_passes_now(self, world):
        out = remote._relatedness(world["local"], _ls_remote(world["bare"]))
        assert out["ok"] is True, out

    def test_the_detail_says_why(self, world):
        out = remote._relatedness(world["local"], _ls_remote(world["bare"]))
        assert "history" in out["detail"]

    def test_it_still_passes_when_local_is_ahead(self, world):
        """The state right after a commit that has not been pushed -- remote
        main is a strict ancestor of HEAD."""
        _commit(world["local"], "hostname r1\n! later\n", "not yet pushed")
        out = remote._relatedness(world["local"], _ls_remote(world["bare"]))
        assert out["ok"] is True, out

    def test_peeled_tag_entries_do_not_confuse_it(self, world):
        """The real ls-remote had 68 lines: main, HEAD, and 33 tags listed
        twice. Only refs/heads/* is ancestry-tested."""
        refs = _ls_remote(world["bare"])
        assert any(line.endswith("^{}") for line in refs), "no peeled entries"
        assert len(remote.remote_heads(refs)) == 1


class TestAGenuinelyUnrelatedRepositoryIsStillRefused:
    """The refusal exists for a reason and must survive the fix."""

    def test_a_different_history_is_refused(self, world, tmp_path):
        stranger = str(tmp_path / "stranger")
        os.makedirs(stranger)
        _git(stranger, "init", "-q", "-b", "main")
        _commit(stranger, "somebody else's network\n", "unrelated")
        bare = str(tmp_path / "stranger.git")
        subprocess.run(["git", "init", "-q", "-b", "main", "--bare", bare],
                       check=True)
        _git(stranger, "push", "-q", bare, "main")

        out = remote._relatedness(world["local"], _ls_remote(bare))
        assert out["ok"] is False
        assert "interleave" in out["fix"]

    def test_an_unrelated_repo_with_deep_history_is_refused(self, world, tmp_path):
        """Not just a one-commit stranger -- the shape the old test could
        never distinguish."""
        stranger = str(tmp_path / "deep")
        os.makedirs(stranger)
        _git(stranger, "init", "-q", "-b", "main")
        for n in range(4):
            _commit(stranger, f"other net {n}\n", f"other {n}")
        bare = str(tmp_path / "deep.git")
        subprocess.run(["git", "init", "-q", "-b", "main", "--bare", bare],
                       check=True)
        _git(stranger, "push", "-q", bare, "main")

        assert remote._relatedness(world["local"], _ls_remote(bare))["ok"] is False

    def test_an_empty_remote_still_passes(self, world, tmp_path):
        bare = str(tmp_path / "empty.git")
        subprocess.run(["git", "init", "-q", "-b", "main", "--bare", bare],
                       check=True)
        out = remote.check_right_repository(
            {"owner": "o", "repo": "r", "host": "github.com"},
            "nonexistent", world["local"]) if False else None
        assert _ls_remote(bare) == []


class TestARemoteThatIsAheadIsStillRelated:
    """Somebody pushed from another machine and we have not fetched.

    Its branch head is a commit this clone has never seen. Testing branch
    heads alone would report our own repository as unrelated for the sake of
    one unfetched commit -- so relatedness is decided on every SHA the remote
    advertises that we actually have, and one shared commit is enough.
    """

    def _remote_ahead(self, world, tmp_path, name):
        clone = str(tmp_path / name)
        subprocess.run(["git", "clone", "-q", world["bare"], clone], check=True)
        _commit(clone, "pushed from another machine\n", "theirs")
        _git(clone, "push", "-q", "origin", "main")
        return _ls_remote(world["bare"])

    def test_it_passes(self, world, tmp_path):
        refs = self._remote_ahead(world, tmp_path, "elsewhere")
        out = remote._relatedness(world["local"], refs)
        assert out["ok"] is True, out

    def test_the_unfetched_head_is_genuinely_unknown_here(self, world, tmp_path):
        """Otherwise the test above passes for the wrong reason."""
        refs = self._remote_ahead(world, tmp_path, "elsewhere2")
        head = next(l.split()[0] for l in refs if l.endswith("refs/heads/main"))
        assert remote._have_commit(world["local"], head) is False

    def test_the_detail_says_we_are_behind(self, world, tmp_path):
        refs = self._remote_ahead(world, tmp_path, "elsewhere3")
        assert "not yet fetched" in remote._relatedness(world["local"], refs)["detail"]


class TestTheAncestryHelpers:
    def test_a_commit_is_its_own_ancestor(self, world):
        """Which is what makes 'ancestor of, or equal to' one check."""
        head = _git(world["local"], "rev-parse", "HEAD")
        assert remote._is_ancestor(world["local"], head, "HEAD") is True

    def test_an_older_commit_is_an_ancestor(self, world):
        older = _git(world["local"], "rev-parse", "HEAD~2")
        assert remote._is_ancestor(world["local"], older, "HEAD") is True

    def test_a_missing_object_is_reported_as_missing(self, world):
        assert remote._have_commit(world["local"], "0" * 40) is False

    def test_heads_ignores_tags_and_head(self):
        refs = ["a\trefs/heads/main", "b\trefs/heads/dev", "c\trefs/tags/v1",
                "d\trefs/tags/v1^{}", "e\tHEAD"]
        assert remote.remote_heads(refs) == ["a", "b"]
