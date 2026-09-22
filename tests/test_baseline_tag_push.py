"""A baseline earned with nothing to commit must still reach the remote.

`save_golden()` can earn a `baseline/<ts>` tag with **no commit**: every
device's capture was verified equal to HEAD, so there is nothing to write and
an empty commit would be a false record of a change. The tag goes on the
existing HEAD.

That path then **returned without calling `run_post_commit` at all**, so the
push hook never fired. The restore point existed on one host and nowhere else
-- which is the single property an off-host archive exists to provide.

**What the fix does NOT rest on.** The first diagnosis said `--follow-tags`
was a second, independent cause: with no new commit there is nothing to carry
the tag. Measured against real repositories, that is **wrong** -- git pushes
annotated tags reachable from the pushed ref whether or not the ref advanced,
and the tag goes out fine.

The measurement found something else instead. `--follow-tags` published an
**unrelated older tag** in the same breath, because it carries every reachable
annotated tag the remote lacks. Publishing is irreversible, so what goes out
is now *named by the caller* rather than computed from reachability. That is a
narrower rule than the one it replaces, and it is the reason for the explicit
refspec -- not the reason originally written down.
"""

import os
import subprocess

import pytest


def _git(repo, *args):
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                         text=True, env=dict(
                             os.environ,
                             GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@l",
                             GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@l"))
    assert out.returncode == 0, f"git {args}: {out.stderr}"
    return out.stdout.strip()


def _remote_refs(bare):
    out = subprocess.run(["git", "ls-remote", bare], capture_output=True,
                         text=True)
    return {line.split()[1] for line in out.stdout.splitlines()
            if len(line.split()) > 1}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A repo with one commit, a bare remote holding it, and auto-push on."""
    from modules.nsot import archive

    local = str(tmp_path / "config_repo")
    os.makedirs(local)
    _git(local, "init", "-q", "-b", "main")
    with open(os.path.join(local, "golden.cfg"), "w") as handle:
        handle.write("hostname s1\n")
    _git(local, "add", "-A")
    _git(local, "commit", "-m", "first")

    bare = str(tmp_path / "remote.git")
    subprocess.run(["git", "init", "-q", "-b", "main", "--bare", bare],
                   check=True)
    _git(local, "push", "-q", bare, "main")

    monkeypatch.setattr("modules.nsot.remote.load_remote",
                        lambda name: {"owner": "o", "repo": "r",
                                      "auto_push": True, "branch": "main"})
    monkeypatch.setattr("modules.nsot.remote.remote_url", lambda config: bare)
    monkeypatch.setattr("modules.nsot.remote.auto_push_decision",
                        lambda name, repo: {"push": True, "reason": "ok"})
    return {"local": local, "bare": bare, "archive": archive}


class TestTheHookFiresOnTheNoCommitPath:
    """The cause that was real, and sufficient on its own."""

    def test_save_golden_calls_the_hook_when_a_baseline_is_earned(
            self, tmp_path, monkeypatch):
        """TWO calls: the first save commits, the second earns a tag only.

        The first version of this test asserted on `calls[-1]` and passed
        with the fix reverted -- the FIRST save's hook call already carries a
        baseline tag, so the assertion was satisfied by the call that was
        never in question. It could not fail, which is the defect class this
        whole plan is organised around.
        """
        from modules.nsot import repo as _repo

        calls = []
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit",
                            lambda ctx: calls.append(ctx))
        out = self._save_unchanged_twice(tmp_path, monkeypatch, _repo)

        assert out["commit"] == "", "the second save was not the no-commit path"
        assert out["baseline"], "the second save earned no baseline to publish"
        assert len(calls) == 2, (
            f"the no-commit path did not call the hook ({len(calls)} call(s))")

        second = calls[1]
        assert second["tags"] == [out["baseline"]]
        assert second["devices"] == [], "nothing changed, so no device did"
        assert second["sha"], "the hook needs the HEAD the tag sits on"

    def test_it_does_not_fire_when_nothing_was_earned(self, tmp_path,
                                                      monkeypatch):
        """A no-op save that earns no baseline has nothing to publish, and
        waking the push path to do nothing would put every unchanged Save All
        on the network."""
        from modules.nsot import repo as _repo

        calls = []
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit",
                            lambda ctx: calls.append(ctx))
        self._save_unchanged_twice(tmp_path, monkeypatch, _repo,
                                   baseline=False)
        assert len(calls) == 1, (
            "only the first save committed; the second earned nothing and "
            "must not call the hook")

    def _save_unchanged_twice(self, tmp_path, monkeypatch, _repo,
                              baseline=True):
        list_dir = tmp_path / "lab"
        list_dir.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(list_dir))
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "n@l",
                                "nsot_device_tag_retention": 50}.get(key, default))
        text = "hostname s1\n!\nend\n"
        kwargs = dict(source="save_all", actor="test", allow_new=True,
                      inventory_size=1)
        if not baseline:
            kwargs["baseline"] = False
        _repo.save_golden("lab", [_repo.GoldenItem("s1", text, "10.0.0.21")],
                          **kwargs)
        return _repo.save_golden(
            "lab", [_repo.GoldenItem("s1", text, "10.0.0.21")], **kwargs)


class TestExactlyTheNamedTagIsPublished:
    def test_the_new_baseline_reaches_the_remote(self, world):
        tag = "baseline/20260922T101500Z"
        _git(world["local"], "tag", "-a", tag, "-m", "network baseline")

        out = world["archive"].push_hook({"list_name": "lab",
                                          "repo": world["local"],
                                          "tags": [tag]})
        assert out["ok"] is True, out
        assert f"refs/tags/{tag}" in _remote_refs(world["bare"])

    def test_an_unrelated_local_tag_is_not_published(self, world):
        """The property the explicit refspec exists for.

        `--follow-tags` publishes every reachable annotated tag the remote
        lacks, so this one rode along -- measured, not assumed.
        """
        wanted = "baseline/20260922T101500Z"
        other = "golden/r1/20260101T000000Z"
        for tag in (wanted, other):
            _git(world["local"], "tag", "-a", tag, "-m", tag)

        world["archive"].push_hook({"list_name": "lab", "repo": world["local"],
                                    "tags": [wanted]})
        refs = _remote_refs(world["bare"])
        assert f"refs/tags/{wanted}" in refs
        assert f"refs/tags/{other}" not in refs, (
            "a tag nobody named was published")

    def test_several_named_tags_all_go(self, world):
        """A golden commit creates one tag per device plus a baseline."""
        tags = ["golden/s1/20260922T101500Z", "golden/s2/20260922T101500Z",
                "baseline/20260922T101500Z"]
        for tag in tags:
            _git(world["local"], "tag", "-a", tag, "-m", tag)

        out = world["archive"].push_hook({"list_name": "lab",
                                          "repo": world["local"], "tags": tags})
        refs = _remote_refs(world["bare"])
        assert sorted(out["tags_pushed"]) == sorted(tags)
        for tag in tags:
            assert f"refs/tags/{tag}" in refs, tag

    def test_no_tags_named_means_no_tags_published(self, world):
        _git(world["local"], "tag", "-a", "golden/r1/2026", "-m", "x")
        world["archive"].push_hook({"list_name": "lab", "repo": world["local"],
                                    "tags": []})
        assert not [r for r in _remote_refs(world["bare"])
                    if r.startswith("refs/tags/")]

    def test_one_bad_tag_does_not_take_the_others_with_it(self, world):
        good = "baseline/20260922T101500Z"
        _git(world["local"], "tag", "-a", good, "-m", good)
        out = world["archive"].push_hook({
            "list_name": "lab", "repo": world["local"],
            "tags": ["golden/does-not-exist/2026", good]})
        assert out["ok"] is True
        assert out["tags_pushed"] == [good]
        assert f"refs/tags/{good}" in _remote_refs(world["bare"])


class TestTheBroadFormsAreNotUsed:
    """Pinned by name, because either would satisfy "the tag is on the
    remote" while changing what publishing means."""

    def _source(self):
        import inspect

        from modules.nsot import archive

        return inspect.getsource(archive.push_hook)

    def _code(self):
        """The code, not the comment explaining why they are absent."""
        import ast
        import inspect
        import textwrap

        from modules.nsot import archive

        tree = ast.parse(textwrap.dedent(inspect.getsource(archive.push_hook)))
        body = tree.body[0].body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)):
            body = body[1:]
        return "\n".join(ast.dump(node) for node in body)

    def test_it_never_uses_push_all_tags(self):
        assert "'--tags'" not in self._code()
        assert '"--tags"' not in self._code()

    def test_it_no_longer_uses_follow_tags(self):
        assert "follow-tags" not in self._code()

    def test_it_uses_no_wildcard_tag_refspec(self):
        assert "refs/tags/*" not in self._code()

    def test_the_refspec_is_built_from_the_named_tag(self):
        assert "refs/tags/{tag}:refs/tags/{tag}" in self._source()


class TestTheAcknowledgementGateStillApplies:
    """A tag-only push must not be a way around the history scan."""

    def test_a_held_decision_publishes_nothing(self, world, monkeypatch):
        monkeypatch.setattr("modules.nsot.remote.auto_push_decision",
                            lambda name, repo: {
                                "push": False, "held": True,
                                "reason": "a new SNMP community appeared"})
        tag = "baseline/20260922T101500Z"
        _git(world["local"], "tag", "-a", tag, "-m", tag)

        out = world["archive"].push_hook({"list_name": "lab",
                                          "repo": world["local"],
                                          "tags": [tag]})
        assert out["ok"] is False and out["held"] is True
        assert f"refs/tags/{tag}" not in _remote_refs(world["bare"])

    def test_a_held_decision_runs_no_git_at_all(self, world, monkeypatch):
        """Stronger than "the tag is absent": nothing is attempted.

        A push that ran and failed would leave the same remote state as one
        that never ran, so the absence of the tag alone cannot tell them
        apart -- and only one of the two respects the gate.
        """
        monkeypatch.setattr("modules.nsot.remote.auto_push_decision",
                            lambda name, repo: {
                                "push": False, "held": True,
                                "reason": "a new SNMP community appeared"})
        calls = []
        monkeypatch.setattr("modules.nsot.repo.git",
                            lambda repo, *a, **k: calls.append(a) or (0, "", ""))

        _git(world["local"], "tag", "-a", "baseline/x", "-m", "x")
        world["archive"].push_hook({"list_name": "lab", "repo": world["local"],
                                    "tags": ["baseline/x"]})
        assert calls == [], calls


class TestEverySuccessfulPushIsRecorded:
    """The Remote card showed a push from the day before.

    Measured on the deployed instance: a baseline tag was published at
    ~17:24Z and "last push" still read `2026-09-21T19:57:47Z`. The card was
    not stale -- it was answering a narrower question than it appeared to.
    `remote.push()` (the button) recorded `last_push`; `archive.push_hook()`
    (auto-push) pushed without ever writing it, so the field meant "when
    somebody last clicked", which reads as "nothing has been published since".
    """

    def test_a_tag_only_auto_push_advances_last_push(self, world, monkeypatch):
        from modules.nsot import remote as R

        saved = {}
        monkeypatch.setattr(R, "save_remote",
                            lambda name, config: saved.update(config))
        monkeypatch.setattr(R, "load_remote",
                            lambda name: dict(saved) or {
                                "owner": "o", "repo": "r", "auto_push": True,
                                "branch": "main",
                                "last_push": {"at": "2026-09-21T19:57:47Z",
                                              "by": "person"}})
        tag = "baseline/20260922T172405Z"
        _git(world["local"], "tag", "-a", tag, "-m", tag)

        world["archive"].push_hook({"list_name": "lab", "repo": world["local"],
                                    "tags": [tag], "devices": []})
        assert saved["last_push"]["at"] != "2026-09-21T19:57:47Z"
        assert saved["last_push"]["by"] == "auto-push"

    def test_it_names_the_tag_that_went_out(self, world, monkeypatch):
        from modules.nsot import remote as R

        saved = {}
        monkeypatch.setattr(R, "save_remote",
                            lambda name, config: saved.update(config))
        monkeypatch.setattr(R, "load_remote", lambda name: dict(saved) or {
            "owner": "o", "repo": "r", "auto_push": True, "branch": "main"})
        tag = "baseline/20260922T172405Z"
        _git(world["local"], "tag", "-a", tag, "-m", tag)

        world["archive"].push_hook({"list_name": "lab", "repo": world["local"],
                                    "tags": [tag], "devices": []})
        assert saved["last_push"]["tags"] == [tag]

    def test_a_tag_only_push_is_recorded_as_such(self, world, monkeypatch):
        """"Pushed" is not one event. With no new commit the branch push is a
        no-op and the tag is the entire publication."""
        from modules.nsot import remote as R

        saved = {}
        monkeypatch.setattr(R, "save_remote",
                            lambda name, config: saved.update(config))
        monkeypatch.setattr(R, "load_remote", lambda name: dict(saved) or {
            "owner": "o", "repo": "r", "auto_push": True, "branch": "main"})
        _git(world["local"], "tag", "-a", "baseline/x", "-m", "x")

        world["archive"].push_hook({"list_name": "lab", "repo": world["local"],
                                    "tags": ["baseline/x"], "devices": []})
        assert saved["last_push"]["kind"] == "tags"

    def test_a_commit_push_is_recorded_as_a_commit(self, world, monkeypatch):
        from modules.nsot import remote as R

        saved = {}
        monkeypatch.setattr(R, "save_remote",
                            lambda name, config: saved.update(config))
        monkeypatch.setattr(R, "load_remote", lambda name: dict(saved) or {
            "owner": "o", "repo": "r", "auto_push": True, "branch": "main"})
        with open(os.path.join(world["local"], "golden.cfg"), "w") as handle:
            handle.write("hostname s1\n!\n")
        _git(world["local"], "add", "-A")
        _git(world["local"], "commit", "-m", "change")

        world["archive"].push_hook({"list_name": "lab", "repo": world["local"],
                                    "tags": [], "devices": ["s1"]})
        assert saved["last_push"]["kind"] == "commit"
        assert saved["last_push"]["commit"]


class TestAFailedPushRecordsTheFailureNotATimestamp:
    """A timestamp on a push that did not happen reads as durability that
    does not exist."""

    def test_last_push_is_not_advanced(self, world, monkeypatch):
        from modules.nsot import remote as R

        saved = {"last_push": {"at": "2026-09-21T19:57:47Z", "by": "person"}}
        monkeypatch.setattr(R, "save_remote",
                            lambda name, config: saved.update(config))
        monkeypatch.setattr(R, "load_remote", lambda name: dict(
            saved, owner="o", repo="r", auto_push=True, branch="main"))
        # A remote that rejects: push to a path that is not a repository.
        monkeypatch.setattr(R, "remote_url", lambda config: "/nonexistent.git")

        out = world["archive"].push_hook({"list_name": "lab",
                                          "repo": world["local"],
                                          "tags": [], "devices": ["s1"]})
        assert out["ok"] is False
        assert saved["last_push"]["at"] == "2026-09-21T19:57:47Z"

    def test_the_failure_is_recorded_with_its_reason(self, world, monkeypatch):
        from modules.nsot import remote as R

        saved = {}
        monkeypatch.setattr(R, "save_remote",
                            lambda name, config: saved.update(config))
        monkeypatch.setattr(R, "load_remote", lambda name: dict(
            saved, owner="o", repo="r", auto_push=True, branch="main"))
        monkeypatch.setattr(R, "remote_url", lambda config: "/nonexistent.git")

        world["archive"].push_hook({"list_name": "lab", "repo": world["local"],
                                    "tags": [], "devices": ["s1"]})
        assert saved["last_push_failure"]["at"]
        assert saved["last_push_failure"]["reason"]

    def test_a_later_success_clears_the_failure(self, world, monkeypatch):
        """Otherwise the card reports a problem that has since been fixed."""
        from modules.nsot import remote as R

        saved = {"last_push_failure": {"at": "2026-09-22T00:00:00Z",
                                       "reason": "it broke"}}
        monkeypatch.setattr(R, "save_remote",
                            lambda name, config: saved.clear() or
                            saved.update(config))
        monkeypatch.setattr(R, "load_remote", lambda name: dict(
            saved, owner="o", repo="r", auto_push=True, branch="main"))
        _git(world["local"], "tag", "-a", "baseline/y", "-m", "y")

        world["archive"].push_hook({"list_name": "lab", "repo": world["local"],
                                    "tags": ["baseline/y"], "devices": []})
        assert "last_push_failure" not in saved


class TestThereIsOneProducer:
    def test_push_does_not_write_last_push_itself(self):
        """Two writers of one field is how the two paths diverged."""
        import ast
        import inspect
        import textwrap

        from modules.nsot import remote as R

        tree = ast.parse(textwrap.dedent(inspect.getsource(R.push)))
        assert "last_push" not in ast.dump(tree).replace("record_push", ""), (
            "push() assigns last_push directly instead of calling record_push")

    def test_both_paths_call_the_recorder(self):
        import inspect

        from modules.nsot import archive, remote

        assert "record_push(" in inspect.getsource(remote.push)
        assert "record_push(" in inspect.getsource(archive.push_hook)
