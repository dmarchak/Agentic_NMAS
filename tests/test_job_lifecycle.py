"""The lifecycle shared by jobs and controller apps (the SDN platform design r4, sections 11 and
12; phase P1): `modules/jobs/lifecycle.py`. The folder's content hash, as git holds it at a
revision (C2616: what is not committed never enters it, so running a folder's tests never moves
it; a link, a submodule or a path outside the repository refused by name), Draft to Published
only by a reviewer other than the author (or recorded self-review under a single-user policy),
any committed edit returning Published to Draft, Retired kept, and who may run a Draft and
which app version may deploy. Every refusal planted."""

import hashlib
import os
import subprocess

import pytest

from modules.jobs import lifecycle as L

AUTHOR, REVIEWER = "author@example.invalid", "reviewer@example.invalid"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          env=dict(os.environ, **GIT_ENV)).stdout


def commit(folder, message="a change"):
    """Commit everything under *folder*'s repository (its parent)."""
    git(folder.parent, "add", "-A")
    git(folder.parent, "commit", "-q", "--allow-empty", "-m", message)


def make_folder(root, files: dict):
    """*files* written under *root*, a folder of a git repository (its parent), committed."""
    repo = root.parent
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        git(repo, "init", "-q", "-b", "main")
    for rel, data in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    commit(root, "the folder")
    return root


def H(folder, rev="HEAD"):
    """The content hash of *folder*, a folder of its parent repository."""
    return L.content_hash(folder.parent, folder.name, rev)


FILES = {"manifest.yml": b"name: dns_blacklist\n", "app/__init__.py": b"",
         "app/logic.py": b"def verdict(name):\n    return 'allow'\n"}


# ── the content hash ─────────────────────────────────────────────────────────────────────────

def test_the_hash_is_the_documented_framing_over_git_s_own_listing(tmp_path):
    """Computed independently: from git's blob ids (`git hash-object`) and modes, not from
    `ls-tree`, which the code reads."""
    folder = make_folder(tmp_path / "app", {"b.txt": b"two", "a/c.txt": b"one"})
    digest = hashlib.sha256(b"mercury-git-folder-sha256-v2\0")
    for rel, data in ((b"a/c.txt", b"one"), (b"b.txt", b"two")):
        blob = subprocess.run(["git", "hash-object", "--stdin"], input=data, check=True,
                              capture_output=True).stdout.strip()
        digest.update(len(rel).to_bytes(8, "big") + rel + b"100644 " +
                      len(blob).to_bytes(1, "big") + blob)
    assert H(folder) == digest.hexdigest()


def test_the_hash_ignores_the_order_written_and_the_times(tmp_path):
    one = make_folder(tmp_path / "one" / "app", FILES)
    two = make_folder(tmp_path / "two" / "app", dict(reversed(list(FILES.items()))))
    os.utime(two / "app" / "logic.py", (1, 1))
    assert H(one) == H(two)


@pytest.mark.parametrize("residue", [
    lambda f: (f / "__pycache__").mkdir() or (f / "__pycache__" / "x.pyc").write_bytes(b"\0"),
    lambda f: (f / "app" / "untracked.py").write_bytes(b"x = 1\n"),
    lambda f: (f / "app" / "logic.py").write_bytes(b"edited, not committed\n"),
    lambda f: (f / "empty").mkdir(),
], ids=["bytecode", "untracked", "uncommitted-edit", "empty-folder"])
def test_what_is_not_committed_never_moves_it(tmp_path, residue):
    """C2616: running a folder's tests writes bytecode into it; that, an untracked file and an
    uncommitted edit never move the hash, so they never return a job to Draft."""
    folder = make_folder(tmp_path / "app", FILES)
    before = H(folder)
    residue(folder)
    assert H(folder) == before


@pytest.mark.parametrize("edit", [
    lambda f: (f / "app" / "logic.py").write_bytes(b"def verdict(name):\n    return 'block'\n"),
    lambda f: (f / "app" / "logic.py").rename(f / "app" / "rules.py"),
    lambda f: (f / "app" / "new.py").write_bytes(b""),
    lambda f: (f / "app" / "__init__.py").unlink(),
    lambda f: os.chmod(f / "app" / "logic.py", 0o755),
], ids=["bytes", "rename", "new-empty-file", "removed", "executable"])
def test_any_committed_edit_moves_the_hash(tmp_path, edit):
    folder = make_folder(tmp_path / "app", FILES)
    before = H(folder)
    edit(folder)
    commit(folder)
    assert H(folder) != before
    assert H(folder, "HEAD~1") == before, "an earlier revision keeps its own hash"


def test_a_committed_link_in_the_folder_is_refused_naming_it(tmp_path):
    folder = make_folder(tmp_path / "app", FILES)
    (folder / "app" / "linked.py").symlink_to("../manifest.yml")
    commit(folder)
    with pytest.raises(L.LifecycleError, match="app/linked.py is a symbolic link"):
        H(folder)


@pytest.mark.parametrize("path,said", [
    ("..", "is not a folder inside the repository"),
    ("../elsewhere", "is not a folder inside the repository"),
    ("/etc", "is not a folder inside the repository"),
    ("", "is not a folder inside the repository"),
    ("absent", "git holds no file there"),
], ids=["parent", "escape", "absolute", "empty", "absent"])
def test_a_path_that_is_not_a_held_folder_is_refused(tmp_path, path, said):
    folder = make_folder(tmp_path / "app", FILES)
    with pytest.raises(L.LifecycleError, match=said):
        L.content_hash(folder.parent, path)


def test_a_folder_in_no_repository_and_an_unknown_revision_are_refused(tmp_path):
    (tmp_path / "plain" / "app").mkdir(parents=True)
    with pytest.raises(L.LifecycleError, match="is not a git repository"):
        L.content_hash(tmp_path / "plain", "app")
    folder = make_folder(tmp_path / "repo" / "app", FILES)
    with pytest.raises(L.LifecycleError, match="git ls-tree refused it"):
        H(folder, "no-such-revision")


# ── the record ───────────────────────────────────────────────────────────────────────────────

def drafted(tmp_path, kind="job", name="trace-path"):
    folder = make_folder(tmp_path / name, FILES)
    return L.draft(kind, name, "1.0.0", AUTHOR, folder.parent, folder.name), folder


@pytest.mark.parametrize("kind,name,said", [
    ("job", "trace_path", "a job's name 'trace_path' does not match ^[a-z][a-z0-9-]{0,40}$"),
    ("app", "dns-blacklist", "an app's name 'dns-blacklist' does not match"),
    ("model", "x", "kind: 'model' refused"),
])
def test_names_follow_their_kinds_rule(kind, name, said):
    with pytest.raises(L.ContractError) as got:
        L.Version(kind=kind, name=name, version="1.0.0", author=AUTHOR, content_sha256="0" * 64)
    assert said in str(got.value)


@pytest.mark.parametrize("fields,said", [
    ({"content_sha256": "abc"}, "a content hash is 64 lower-case hex digits"),
    ({"version": "1.0"}, "version: '1.0' refused"),
    ({"author": " "}, "an author is a non-empty identity"),
    ({"state": "published"}, "a Published version names its reviewer"),
    ({"state": "draft", "standard_change": True}, "only a Published version is a standard"),
    ({"reviewer": REVIEWER, "self_review": True}, "self_review is set, but the reviewer"),
], ids=["hash", "version", "author", "unreviewed", "standard-draft", "self-review"])
def test_an_inconsistent_record_is_refused(fields, said):
    base = dict(kind="job", name="trace-path", version="1.0.0", author=AUTHOR,
                content_sha256="0" * 64)
    with pytest.raises(L.ContractError) as got:
        L.Version(**dict(base, **fields))
    assert said in str(got.value)


def test_a_new_version_is_a_draft_pinned_by_its_folder(tmp_path):
    v, folder = drafted(tmp_path)
    assert (v.state, v.content_sha256, v.reviewer) == (L.DRAFT, H(folder), "")


# ── publishing ───────────────────────────────────────────────────────────────────────────────

def test_a_reviewer_other_than_the_author_publishes_it(tmp_path):
    v, folder = drafted(tmp_path)
    got = L.publish(v, H(folder), reviewer=REVIEWER, harness_passed=True)
    assert (got.state, got.reviewer, got.self_review) == (L.PUBLISHED, REVIEWER, False)


@pytest.mark.parametrize("reviewer", [AUTHOR, " Author@Example.Invalid "], ids=["same", "case"])
def test_the_author_cannot_review_their_own_work(tmp_path, reviewer):
    v, folder = drafted(tmp_path)
    with pytest.raises(L.LifecycleError) as got:
        L.publish(v, H(folder), reviewer=reviewer, harness_passed=True)
    assert (f"the reviewer {reviewer!r} is the author {AUTHOR!r}, and the installation's policy "
            "is not single-user") in str(got.value)


def test_a_single_user_installation_records_self_review(tmp_path):
    v, folder = drafted(tmp_path)
    got = L.publish(v, H(folder), reviewer=AUTHOR, harness_passed=True,
                    single_user=True)
    assert (got.state, got.self_review) == (L.PUBLISHED, True)
    other = L.publish(v, H(folder), reviewer=REVIEWER, harness_passed=True,
                      single_user=True)
    assert other.self_review is False


@pytest.mark.parametrize("change,said", [
    (lambda f: {"harness_passed": False},
     "its harness tests have not passed (harness_passed is False)"),
    (lambda f: {"harness_passed": "yes"}, "harness_passed is 'yes'"),
    (lambda f: {"reviewer": ""}, "no reviewer is named"),
], ids=["harness", "harness-not-bool", "no-reviewer"])
def test_publishing_without_its_conditions_is_refused(tmp_path, change, said):
    v, folder = drafted(tmp_path)
    kwargs = dict({"reviewer": REVIEWER, "harness_passed": True}, **change(folder))
    with pytest.raises(L.LifecycleError) as got:
        L.publish(v, H(folder), **kwargs)
    assert said in str(got.value)


def test_publishing_a_folder_that_moved_since_it_was_drafted_names_both_hashes(tmp_path):
    v, folder = drafted(tmp_path)
    (folder / "app" / "logic.py").write_bytes(b"edited\n")
    commit(folder)
    moved = H(folder)
    with pytest.raises(L.LifecycleError) as got:
        L.publish(v, moved, reviewer=REVIEWER, harness_passed=True)
    assert f"the folder's hash {moved} is not the Draft's pinned {v.content_sha256}" \
        in str(got.value)


def test_only_a_draft_is_published(tmp_path):
    v, folder = drafted(tmp_path)
    published = L.publish(v, H(folder), reviewer=REVIEWER, harness_passed=True)
    with pytest.raises(L.LifecycleError, match="only a Draft is published; this version is "
                                               "published"):
        L.publish(published, H(folder), reviewer=REVIEWER, harness_passed=True)


# ── an edit, and retirement ──────────────────────────────────────────────────────────────────

def test_an_edit_returns_a_published_version_to_draft(tmp_path):
    v, folder = drafted(tmp_path)
    published = L.publish(v, H(folder), reviewer=REVIEWER, harness_passed=True)
    assert L.observe(published, H(folder)) is published
    (folder / "app" / "logic.py").write_bytes(b"edited\n")
    commit(folder)
    got = L.observe(published, H(folder))
    assert (got.state, got.reviewer, got.content_sha256) == (L.DRAFT, "",
                                                            H(folder))


def test_a_draft_takes_its_new_hash_and_a_retired_version_keeps_its_own(tmp_path):
    v, folder = drafted(tmp_path)
    assert L.observe(v, "1" * 64).content_sha256 == "1" * 64
    retired = L.retire(v)
    assert L.observe(retired, "1" * 64) is retired


def test_retirement_is_kept_and_happens_once(tmp_path):
    v, _folder = drafted(tmp_path)
    retired = L.retire(v)
    assert (retired.state, retired.content_sha256) == (L.RETIRED, v.content_sha256)
    with pytest.raises(L.LifecycleError, match="it is already retired"):
        L.retire(retired)


# ── who runs, what deploys ───────────────────────────────────────────────────────────────────

def test_a_draft_runs_for_its_author_in_plan_mode_only(tmp_path):
    v, folder = drafted(tmp_path)
    assert L.run_refusal(v, "plan", AUTHOR) == ""
    assert "only its author" in L.run_refusal(v, "plan", REVIEWER)
    assert "it runs in plan mode only, not commit" in L.run_refusal(v, "commit", AUTHOR)
    published = L.publish(v, H(folder), reviewer=REVIEWER, harness_passed=True)
    assert L.run_refusal(published, "commit", REVIEWER) == ""
    assert "is retired" in L.run_refusal(L.retire(published), "plan", AUTHOR)
    assert "mode 'apply' is not plan or commit" in L.run_refusal(published, "apply", AUTHOR)


def test_only_a_published_app_deploys_and_only_byte_for_byte(tmp_path):
    v, folder = drafted(tmp_path, kind="app", name="dns_blacklist")
    pinned = H(folder)
    said = L.deploy_refusal(v, pinned)
    assert "is draft: only a Published version deploys" in said and pinned[:12] in said
    published = L.publish(v, pinned, reviewer=REVIEWER, harness_passed=True)
    assert L.deploy_refusal(published, pinned) == ""
    assert (f"the staged folder's hash {'2' * 64} is not the Published {pinned}"
            == L.deploy_refusal(published, "2" * 64))


def test_a_job_is_run_and_an_app_deployed(tmp_path):
    job, _f = drafted(tmp_path)
    app, _g = drafted(tmp_path, kind="app", name="dns_blacklist")
    assert "a job is run, not deployed" in L.deploy_refusal(job, job.content_sha256)
    assert "an app is deployed, not run" in L.run_refusal(app, "plan", AUTHOR)
