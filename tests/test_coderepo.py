"""A network's code repository and the registry's read side (`modules/coderepo.py`; the SDN
platform design revision 7, 11c.2 and 11c.3; the operator's decision 8 of 2026-11-08).

Cases, each planted in a code repository made here:
- the setting: a local path, a file:// URL and an https:// URL (an IPv4 and an IPv6 literal
  host) are taken; ssh, scp's form, git://, http://, ext::, a user part, a query, a path inside
  Mercury's data and a space are refused, each naming why; set only by a verified person,
  recorded, refused when it moved since the card drew it, naming both;
- the fetch: Mercury's copy has no working tree (git's objects only), git's transports are
  limited to file and https with no prompt, the fetched commit is a ref of the copy, and the
  network's configuration repository is byte for byte the same afterwards; a failed fetch is
  recorded with why and keeps the commit the copy had; a record that cannot be read refuses it;
- registration: each ``apps/<name>/`` folder at the fetched commit is a Draft keyed by the
  location, the commit and its content hash (`lifecycle.content_hash` of the SOURCE at that
  commit), its manifest read from the blob; a folder with no manifest, or one naming another
  app, is a problem named, never a version; a version again with another hash is the Draft
  moved; an older version stays listed and stages from its own commit's blobs;
- the registry reads blobs, never a file: a file planted in the copy, or an uncommitted edit in
  the source, changes nothing; a location changed since the fetch lists nothing, naming both;
- `sources.Wired().registered` is this registry."""

import json
import os
import subprocess

import pytest

from modules import coderepo as R
from modules.apps import channel
from modules.apps import sources as S
from modules.jobs.lifecycle import DRAFT, content_hash

NET = "Default"
ACTOR, VERIFIED = "op@example.invalid", "access-assertion"
GIT_ENV = {"GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "author@example.invalid",
           "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "author@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          env=dict(os.environ, **GIT_ENV)).stdout.decode().strip()


def manifest(name, version):
    return (f"name: {name}\nversion: {version}\ncontrollers:\n  ryu: \">=4.34\"\n"
            "openflow_versions: [\"1.3\"]\nrequires: []\nconfig_schema: {type: object}\n"
            f"rest:\n  prefix: /{name}\n  endpoints:\n    - path: /health\n      methods: [GET]\n")


def commit_app(repo, name, version, body="x = 1\n", text=None):
    folder = repo / "apps" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.yml").write_text(text if text is not None else manifest(name, version))
    (folder / f"{name}.py").write_text(body)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"{name} {version}")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def code(tmp_path):
    repo = tmp_path / "code"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit_app(repo, "of_versions", "1.0.0")
    return repo


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """Mercury's data (its settings, its networks) under tmp_path/data, the code repository
    beside it: Default's folder, where the copy and its record land."""
    from tests.test_sdn_connections import make_networks

    data = tmp_path / "data"
    data.mkdir()
    make_networks(data, monkeypatch)
    folder = data / "lists" / "default"
    (folder / "config_repo").mkdir(parents=True)
    R._blob_read.cache_clear()
    return folder


def set_to(loc, branch=""):
    return R.set_location(NET, str(loc), branch, actor=ACTOR, actor_verified=VERIFIED)


def fetch():
    return R.fetch(NET, actor=ACTOR, actor_verified=VERIFIED)


# ── the setting ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, kind", [
    ("/srv/code/lab9.git", "path"), ("file:///srv/code/lab9.git", "path"),
    ("https://code.example.invalid/lab9.git", "https"),
    ("https://192.0.2.10/lab9.git", "https"), ("https://[2001:db8::10]:8443/lab9.git", "https"),
])
def test_a_local_path_or_an_https_url_is_a_location(text, kind):
    got = R.parse_location(text)
    assert got["ok"] and got["kind"] == kind, got


@pytest.mark.parametrize("text, words", [
    ("ssh://git@code.example.invalid/lab9.git", "'ssh' is neither"),
    ("git@code.example.invalid:lab9.git", "is neither"),
    ("git://code.example.invalid/lab9.git", "'git' is neither"),
    ("http://192.0.2.10/lab9.git", "'http' is neither"),
    ("ext::sh -c touch% /tmp/x", "printable ASCII with no space"),
    ("ext::sh", "'ext' is neither"),
    ("https://user:secret@code.example.invalid/x.git", "carries a user part"),
    ("https://[2001:db8::10]/x.git?a=1", "a query or a fragment"),
    ("https:///x.git", "names no host"),
    ("relative/path", "is neither"),
    ("", "no location was given"),
])
def test_anything_else_is_refused_naming_why(text, words):
    got = R.parse_location(text)
    assert not got["ok"] and words in got["error"], got


def test_a_path_inside_mercurys_data_is_refused():
    from modules import config

    got = R.parse_location(os.path.join(config.DATA_DIR, "lists", "default", "x"))
    assert not got["ok"] and "inside Mercury's own data" in got["error"]


@pytest.mark.parametrize("branch, ok", [("main", True), ("release/1.2", True), ("", True),
                                        ("-x", False), ("a..b", False), ("a.lock", False),
                                        ("a b", False), ("a//b", False)])
def test_a_branch_is_a_branchs_name(branch, ok):
    assert (R.branch_problem(branch) == "") is ok


def test_the_setting_is_set_by_a_verified_person_and_recorded(lab, code):
    from modules import list_settings as L

    with pytest.raises(R.Refused, match="verified person"):
        R.set_location(NET, str(code), "", actor=ACTOR, actor_verified="none")
    got = set_to(code, "main")
    assert got["ok"] and not got["unchanged"]
    assert R.location(NET)["location"] == str(code) and R.location(NET)["branch"] == "main"
    with open(lab / L.RECORD, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    [row] = [r for r in rows if r.get("kind") == "code_repository"]
    assert row["after"] == f"{code}\nmain" and row["before"] == "\n" and row["actor"] == ACTOR
    assert set_to(code, "main")["unchanged"]


def test_a_save_after_the_setting_moved_is_refused_naming_both(lab, code, tmp_path):
    set_to(code)
    with pytest.raises(R.Refused) as exc:
        R.set_location(NET, "/srv/other.git", "", actor=ACTOR, actor_verified=VERIFIED,
                       loaded="/srv/drawn.git\n")
    said = str(exc.value)
    assert "moved since the card drew it" in said and "/srv/drawn.git" in said \
        and str(code) in said
    assert R.location(NET)["location"] == str(code)


def test_another_network_never_inherits_defaults_code_repository(lab, code):
    """Each network's own (`settings_scope.OWN_ONLY`): Default's apps are never registered for
    a network that inherits Default's other settings."""
    set_to(code)
    assert R.location(NET)["location"] == str(code)
    branch = R.location("Branch")
    assert branch["state"] == "none" and branch["location"] == ""


def test_nothing_set_is_said_never_an_empty_registry(lab):
    got = R.registered(NET)
    assert got["state"] == "none" and got["apps"] == []
    assert "has no code repository set" in got["error"] and "Code repository" in got["error"]
    wired = S.Wired().registered(NET)
    assert wired["state"] == "none" and wired["error"] == got["error"]


# ── the fetch and registration ──────────────────────────────────────────────────────────────

def test_a_fetch_registers_each_app_folder_as_a_draft_pinned_by_commit_and_hash(lab, code):
    head = git(code, "rev-parse", "HEAD")
    set_to(code)
    got = fetch()
    assert got["ok"] and got["commit"] == head and got["changed"], got
    reg = R.registered(NET)
    assert reg["state"] == "ok", reg["error"]
    assert reg["repo"]["commit"] == head and reg["repo"]["path"] == str(code)
    [app] = reg["apps"]
    [entry] = app["versions"]
    v = entry["version"]
    assert (app["name"], v.version, v.state, v.kind) == ("of_versions", "1.0.0", DRAFT, "app")
    # Pinned by the folder's hash as the SOURCE holds it at that commit.
    assert v.content_sha256 == content_hash(code, "apps/of_versions", head)
    assert entry["commit"] == entry["rev"] == head and entry["path"] == "apps/of_versions"
    assert entry["manifest"].rest.prefix == "/of_versions" and entry["location"] == str(code)
    assert v.author == "author@example.invalid"


def test_the_copy_has_no_working_tree_and_the_configuration_repository_is_untouched(lab, code):
    cfg = lab / "config_repo"
    (cfg / "kept.txt").write_text("state\n")
    before = sorted((p.relative_to(cfg), p.read_bytes()) for p in cfg.rglob("*") if p.is_file())
    set_to(code)
    assert fetch()["ok"]
    copy = lab / R.COPY
    assert sorted(os.listdir(copy)) == [".git"]
    after = sorted((p.relative_to(cfg), p.read_bytes()) for p in cfg.rglob("*") if p.is_file())
    assert after == before


def test_the_copys_git_runs_only_the_file_and_https_transports_and_never_prompts(lab, code):
    """The environment the copy's git is run with names exactly file and https, and no prompt
    (in tests every child's git is held to file by tests/network_guard.py, so https cannot be
    shown by a fetch here); by its effect, git run so refuses a git:// remote before
    connecting, and a local fetch works."""
    env = R._git_env()
    assert env["GIT_ALLOW_PROTOCOL"] == "file:https" and env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_ASKPASS"] == "" and env["SSH_ASKPASS"] == ""
    set_to(code)
    assert fetch()["ok"]
    copy = str(lab / R.COPY)
    proc = R._git(copy, "ls-remote", "--", "git://127.0.0.1:9/x.git")
    assert proc.returncode != 0 and "transport 'git' not allowed" in proc.stderr, proc.stderr
    assert R.fetched_commit(copy) == git(code, "rev-parse", "HEAD")


def test_a_branch_is_fetched_by_its_name(lab, code):
    git(code, "checkout", "-q", "-b", "next")
    nxt = commit_app(code, "of_versions", "1.1.0")
    git(code, "checkout", "-q", "main")
    set_to(code, "next")
    assert fetch()["commit"] == nxt


def test_a_folder_with_no_manifest_or_another_apps_name_is_a_problem_never_a_version(lab, code):
    (code / "apps" / "loose").mkdir()
    (code / "apps" / "loose" / "x.py").write_text("x = 1\n")
    commit_app(code, "switch_quirks", "0.1.0", text=manifest("other_name", "0.1.0"))
    set_to(code)
    got = fetch()
    assert got["ok"]
    words = " ".join(got["problems"])
    assert "apps/loose/manifest.yml" in words and "no manifest" in words
    assert "names the app 'other_name', and its folder is 'switch_quirks'" in words
    reg = R.registered(NET)
    assert [a["name"] for a in reg["apps"]] == ["of_versions"]
    assert reg["problems"] == got["problems"]


def test_a_new_version_adds_and_the_old_one_stays_staged_from_its_own_blobs(lab, code, tmp_path):
    first = git(code, "rev-parse", "HEAD")
    set_to(code)
    fetch()
    second = commit_app(code, "of_versions", "1.1.0", body="x = 2\n")
    got = fetch()
    assert got["changed"] and any("1.1.0 registered" in w for w in got["registered"])
    reg = R.registered(NET)
    versions = {e["version"].version: e for e in reg["apps"][0]["versions"]}
    assert versions["1.0.0"]["commit"] == first and versions["1.1.0"]["commit"] == second
    old = versions["1.0.0"]
    staged = channel.stage(old["repo"], old["path"], old["rev"], str(tmp_path / "staged"))
    assert (tmp_path / "staged" / "of_versions.py").read_text() == "x = 1\n"
    assert {f["path"] for f in staged["files"]} == {"manifest.yml", "of_versions.py"}


def test_the_same_version_with_another_hash_is_the_draft_moved(lab, code):
    set_to(code)
    fetch()
    moved = commit_app(code, "of_versions", "1.0.0", body="x = 3\n")
    got = fetch()
    assert any("1.0.0 moved" in w for w in got["registered"]), got["registered"]
    [entry] = R.registered(NET)["apps"][0]["versions"]
    assert entry["commit"] == moved
    assert entry["version"].content_sha256 == content_hash(code, "apps/of_versions", moved)


def test_an_unchanged_fetch_registers_nothing_new(lab, code):
    set_to(code)
    fetch()
    again = fetch()
    assert again["ok"] and not again["changed"] and again["registered"] == []


def test_the_registry_reads_blobs_never_a_file(lab, code):
    set_to(code)
    fetch()
    # A file planted where a checkout would be, and an edit the source has not committed.
    planted = lab / R.COPY / "apps" / "of_versions"
    planted.mkdir(parents=True)
    (planted / "manifest.yml").write_text(manifest("of_versions", "9.9.9"))
    (code / "apps" / "of_versions" / "of_versions.py").write_text("x = 'uncommitted'\n")
    R._blob_read.cache_clear()
    [entry] = R.registered(NET)["apps"][0]["versions"]
    assert entry["version"].version == "1.0.0"
    assert entry["version"].content_sha256 == content_hash(code, "apps/of_versions",
                                                           git(code, "rev-parse", "HEAD"))


def test_a_version_whose_blobs_no_longer_hash_to_its_pin_is_a_problem_never_listed(lab, code):
    set_to(code)
    fetch()
    path = lab / R.RECORD
    rec = json.loads(path.read_text())
    rec["versions"][0]["content_sha256"] = "0" * 64
    path.write_text(json.dumps(rec))
    got = R.registered(NET)
    assert got["state"] == "ok" and got["apps"] == []
    assert any("registered with hash 000000000000" in p for p in got["problems"]), got


def test_a_location_changed_since_the_fetch_lists_nothing_naming_both(lab, code):
    set_to(code)
    fetch()
    set_to("/srv/elsewhere.git")
    got = R.registered(NET)
    assert got["state"] == "unreadable" and got["apps"] == []
    assert str(code) in got["error"] and "/srv/elsewhere.git" in got["error"]
    assert "Fetch again" in got["error"]


def test_not_fetched_yet_is_said_and_a_failed_fetch_is_recorded_with_why(lab, code, tmp_path):
    set_to(tmp_path / "missing.git")
    assert R.registered(NET)["state"] == "unfetched"
    got = fetch()
    assert not got["ok"] and "git fetch of" in got["error"]
    reg = R.registered(NET)
    assert reg["state"] == "unfetched" and "failed" in reg["error"]
    assert R.card(NET)["last"]["error"] == got["error"]
    # A later failure keeps the commit a good fetch made.
    set_to(code)
    good = fetch()["commit"]
    set_to(tmp_path / "missing.git")
    fetch()
    assert R.fetched_commit(str(lab / R.COPY)) == good


def test_an_unreadable_record_refuses_a_fetch_and_lists_nothing(lab, code):
    set_to(code)
    (lab / R.RECORD).write_text("{not json")
    with pytest.raises(R.Refused, match="nothing was fetched"):
        fetch()
    assert R.registered(NET)["state"] == "unreadable"
    assert (lab / R.RECORD).read_text() == "{not json"


def test_a_fetch_is_a_verified_persons_and_needs_a_location(lab):
    with pytest.raises(R.Refused, match="verified person"):
        R.fetch(NET, actor=ACTOR, actor_verified="")
    with pytest.raises(R.Refused, match="has no code repository set"):
        fetch()


def test_the_record_keeps_who_fetched_what_and_when(lab, code):
    set_to(code)
    fetch()
    rec = json.loads((lab / R.RECORD).read_text())
    [row] = rec["fetches"]
    assert row["by"] == ACTOR and row["actor_verified"] == VERIFIED and row["ok"]
    assert row["location"] == str(code) and row["at"].endswith("Z")
    assert isinstance(row["took_ms"], int) and 0 <= row["took_ms"] < R.FETCH_TIMEOUT * 1000
    [v] = rec["versions"]
    assert v["registered_by"] == ACTOR and v["location"] == str(code)
