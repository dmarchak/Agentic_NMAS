"""Add an app as a Draft: Mercury's one write path to a network's code repository
(`modules/apps/draft_write.py`; the operator's decision of 2026-11-10, "a write path that can
ONLY create Drafts in the code repository (preview, confirm, recorded); Publish stays the
gate"), its routes on SDN › Apps and the picker's script (static/js/nmas_draft.js).

Every case runs on real repositories made here with git (local, no network): a bare code
repository holding one app (`of_versions`, from tests/test_coderepo.py's world), or an empty one,
and Default's Mercury data under tmp_path.

- **The preview** is the exact program (the location, the branch, the base commit read now, the
  folder, each file's path, size and sha256, the message, the author) and a hash over it, and
  writes nothing: not the repository, not Mercury's copy or its record.
- **Each refusal** names its comparison and both operands: an https location, a folder already
  at the base, a name that is not an app's, no manifest or one naming another app, a path that
  is absolute, holds ``..``, ``.git``, a character that is not printable or lies outside the
  folder, each cap, a file that is not UTF-8, an empty branch on an empty repository, a branch
  that does not exist in a repository holding others.
- **The apply** pushes exactly one commit adding only ``apps/<name>/`` on top of the base, as
  the person; a base that moved since the preview, or files that changed, are refused naming
  which; a non-fast-forward is refused by git and reported; the fetch registers the Draft; the
  write is recorded; the throwaway repository is removed every time.
- **The routes:** a caller with no verified identity is refused before anything is read; the
  folder's relative paths come through the multipart filenames; the preview, its confirm and the
  answer are drawn in the card's place, and the code repository's keys are announced.

No address is parsed or drawn by the draft writer (the location is `coderepo.location`'s, whose
IPv4 and IPv6 cases are tests/test_coderepo.py's), so there is no IPv6 case here.
"""

import hashlib
import json
import os
import re
import subprocess
from html import unescape

import pytest

from modules import coderepo as R
from modules.apps import draft_write as D
from tests.test_coderepo import ACTOR, GIT_ENV, NET, VERIFIED, code, git, lab  # noqa: F401
from tests.test_coderepo import manifest, set_to

NAME, VERSION = "dhcp_watch", "0.1.0"
LOGIC = b"def busy(ports, limit=20):\n    return sorted(p for p, n in ports.items() if n > limit)\n"
TEST = b"from dhcp_watch import busy\n\n\ndef test_busy():\n    assert busy({1: 30}) == [1]\n"


def draft(name=NAME, version=VERSION, **extra):
    files = {"manifest.yml": manifest(name, version).encode(), f"{name}.py": LOGIC,
             "tests/test_watch.py": TEST}
    files.update(extra)
    return {k: v for k, v in files.items() if v is not None}


@pytest.fixture
def bare(tmp_path, code):  # noqa: F811
    """The code repository, bare (a push lands only in a repository with no checked-out
    branch), holding of_versions 1.0.0 on main, set as Default's."""
    repo = tmp_path / "code.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(code), str(repo)], check=True,
                   capture_output=True, env=dict(os.environ, **GIT_ENV))
    return repo


@pytest.fixture
def world(lab, bare):  # noqa: F811
    set_to(bare, "main")
    return bare


@pytest.fixture
def empty(lab, tmp_path):  # noqa: F811
    repo = tmp_path / "empty.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(repo))
    return repo


def head(repo, branch="main"):
    proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
                           f"refs/heads/{branch}"], capture_output=True, text=True)
    return proc.stdout.strip()


def preview(files=None, name=NAME, actor=ACTOR):
    return D.preview(NET, name, draft() if files is None else files, actor=actor,
                     actor_verified=VERIFIED)


def add(p, files=None, name=NAME, **kw):
    return D.apply(NET, name, draft() if files is None else files, p["hash"], actor=ACTOR,
                   actor_verified=VERIFIED, then_base=p["base"], then_files=p["files_sha"],
                   **kw)


def leftovers():
    folder = os.path.dirname(R.copy_dir(NET))
    return sorted(n for n in os.listdir(folder) if n.startswith(".draft-")) \
        if os.path.isdir(folder) else []


def push_other(repo, tmp_path, path="notes.md"):
    """Someone else's commit on main, pushed to the bare repository."""
    work = tmp_path / f"other-{path.replace('/', '-')}"
    subprocess.run(["git", "clone", "-q", str(repo), str(work)], check=True,
                   capture_output=True, env=dict(os.environ, **GIT_ENV))
    (work / path).write_text("another person's commit\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "elsewhere")
    git(work, "push", "-q", "origin", "HEAD:main")
    return git(work, "rev-parse", "HEAD")


# ── the preview ──────────────────────────────────────────────────────────────────────────────

def test_the_preview_is_the_exact_program_and_writes_nothing(world):
    base = head(world)
    p = preview()
    assert p["ok"], p["error"]
    assert (p["location"], p["branch"], p["branch_from"]) == (str(world), "main", "setting")
    assert p["base"] == base and p["folder"] == "apps/dhcp_watch/" and p["version"] == VERSION
    files = draft()
    assert p["files"] == [{"rel": rel, "path": f"apps/dhcp_watch/{rel}", "size": len(files[rel]),
                           "sha256": hashlib.sha256(files[rel]).hexdigest()}
                          for rel in sorted(files)]
    assert p["author"] == ACTOR and p["message"].startswith("Add dhcp_watch 0.1.0 as a Draft\n")
    assert f"\nActor: {ACTOR}\nActor-Verified: {VERIFIED}\n" in p["message"]
    assert re.fullmatch(r"[0-9a-f]{64}", p["hash"]) and preview()["hash"] == p["hash"]
    # Nothing written: the repository, Mercury's copy and its record, and no throwaway left.
    assert head(world) == base and R.read_record(NET)["state"] == "absent"
    assert not os.path.exists(R.copy_dir(NET)) and leftovers() == []


@pytest.mark.parametrize("change", ["a byte of a file", "another person", "a moved base"])
def test_the_hash_binds_every_part_of_the_program(world, tmp_path, change):
    before = preview()["hash"]
    if change == "a byte of a file":
        after = preview(draft(**{"dhcp_watch.py": LOGIC + b"#\n"}))["hash"]
    elif change == "another person":
        after = preview(actor="another@example.invalid")["hash"]
    else:
        push_other(world, tmp_path)
        after = preview()["hash"]
    assert after != before


def test_an_empty_repository_with_its_branch_named_takes_the_first_commit(empty):
    set_to(empty, "main")
    p = preview()
    assert p["ok"], p["error"]
    assert p["base"] == "" and p["branch"] == "main"


# ── the refusals ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("files, name, words", [
    (None, "of_versions", None),                                           # set below
    (None, "Dhcp-Watch", "'Dhcp-Watch' is not an app's name"),
    ({"dhcp_watch.py": LOGIC}, NAME, "holds no manifest.yml at its top"),
    (draft(**{"manifest.yml": manifest("other", "0.1.0").encode()}), NAME,
     "dhcp_watch/manifest.yml names the app 'other', and its folder is 'dhcp_watch'"),
    (draft(**{"/etc/passwd": b"x"}), NAME, "'/etc/passwd' is absolute"),
    (draft(**{"../escape.py": b"x"}), NAME, "holds '..': a path never leaves the app's folder"),
    (draft(**{"tests/../../x.py": b"x"}), NAME, "holds '..'"),
    (draft(**{".git/config": b"x"}), NAME, "holds .git"),
    (draft(**{"a\x01.py": b"x"}), NAME, "not printable ASCII"),
    (draft(**{"a b.py": b"x"}), NAME, "not printable ASCII (or a space)"),
    (draft(**{"bad.bin": b"\xff\xfe\x00"}), NAME, "bad.bin is not UTF-8 text (byte 0 is not)"),
    (draft(**{"nul.txt": b"a\x00b"}), NAME, "nul.txt holds a NUL byte"),
    (draft(**{f"f{i}.py": b"x" for i in range(D.MAX_FILES)}), NAME,
     f"the folder holds {D.MAX_FILES + 3} files, over a Draft's {D.MAX_FILES}"),
    (draft(**{"big.py": b"x" * (D.MAX_FILE_BYTES + 1)}), NAME,
     f"big.py is at least {D.MAX_FILE_BYTES + 1} bytes, over a file's {D.MAX_FILE_BYTES}"),
    (draft(**{f"part{i}.py": b"x" * D.MAX_FILE_BYTES for i in range(4)}), NAME,
     f"over a Draft's {D.MAX_TOTAL_BYTES}"),
])
def test_each_refusal_names_its_comparison(world, files, name, words):
    if name == "of_versions":
        files = draft("of_versions", "2.0.0")
        words = (f"apps/of_versions/ already exists at {head(world)[:12]} on main (a tree): a "
                 "Draft is a new app folder only, never a change to one already there")
    p = preview(files, name=name)
    assert p["ok"] is False and words in p["error"], p["error"]
    assert leftovers() == []


def test_an_https_location_is_refused_naming_the_credential(lab):  # noqa: F811
    set_to("https://code.example.invalid/lab9.git", "main")
    p = preview()
    assert p["ok"] is False
    assert "https://code.example.invalid/lab9.git, an https location" in p["error"]
    assert "a push credential Mercury does not hold, so it is refused" in p["error"]
    c = D.control(NET, "form")
    assert c["may"] is False and c["state"] == "rest" and "push credential" in c["why"]


def test_no_location_is_refused_naming_the_card(lab):  # noqa: F811
    assert "set its location on Settings › Default › Network › Code repository" in \
        preview()["error"]
    assert D.control(NET)["may"] is False


def test_an_empty_branch_on_an_empty_repository_names_the_card(empty):
    """git's ls-remote names no HEAD for an empty repository (measured with git 2.53.0: no
    line, exit 0), so there is no default branch to take."""
    set_to(empty, "")
    p = preview()
    assert p["ok"] is False and "has no default branch yet" in p["error"]
    assert "name the branch on Settings › Default › Network › Code repository" in p["error"]


def test_an_empty_branch_on_a_repository_takes_its_default_branch(lab, bare):  # noqa: F811
    set_to(bare, "")
    p = preview()
    assert p["ok"] and p["branch"] == "main" and p["branch_from"] == "default"


def test_a_branch_missing_from_a_repository_holding_others_is_refused(lab, bare):  # noqa: F811
    set_to(bare, "drafts")
    p = preview()
    assert p["ok"] is False and "the branch drafts does not exist in" in p["error"]
    assert "which holds 1 other refs" in p["error"]


def test_only_a_verified_person_adds_a_draft(world):
    p = D.preview(NET, NAME, draft(), actor=ACTOR, actor_verified="none")
    assert p["ok"] is False and "added by a verified person" in p["error"]


# ── the apply ────────────────────────────────────────────────────────────────────────────────

def test_the_apply_pushes_one_commit_adding_only_the_folder(world):
    base = head(world)
    p = preview()
    done = add(p)
    assert done["outcome"] == "added", done["error"]
    new = head(world)
    assert new == done["commit"] != base
    assert git(world, "rev-parse", f"{new}^") == base, "exactly one commit, on the base"
    status = git(world, "diff-tree", "-r", "--no-commit-id", "--name-status", base, new)
    assert status.splitlines() == [f"A\tapps/dhcp_watch/{rel}" for rel in sorted(draft())]
    for rel, data in draft().items():
        shown = subprocess.run(["git", "-C", str(world), "show", f"{new}:apps/dhcp_watch/{rel}"],
                               capture_output=True, check=True).stdout
        assert shown == data
    assert git(world, "log", "-1", "--format=%ae %ce", new) == f"{ACTOR} {ACTOR}"
    assert git(world, "log", "-1", "--format=%B", new) == p["message"].strip()
    assert leftovers() == []


def test_the_first_commit_of_an_empty_repository(empty):
    set_to(empty, "main")
    p = preview()
    done = add(p)
    assert done["outcome"] == "added", done["error"]
    assert git(empty, "rev-list", "--count", "main") == "1"
    assert git(empty, "ls-tree", "-r", "--name-only", "main").splitlines() == \
        [f"apps/dhcp_watch/{rel}" for rel in sorted(draft())]


def test_the_fetch_registers_the_draft_in_the_same_operation(world):
    done = add(preview())
    assert done["registered"] is True and done["register_error"] == ""
    reg = R.registered(NET)
    app = next(a for a in reg["apps"] if a["name"] == NAME)
    (entry,) = app["versions"]
    assert entry["version"].state == "draft" and entry["commit"] == done["commit"]
    assert entry["version"].author == ACTOR


def test_the_write_is_recorded(world):
    p = preview()
    done = add(p)
    (row,) = R.read_record(NET)["record"]["drafts"]
    assert (row["by"], row["actor_verified"], row["ok"]) == (ACTOR, VERIFIED, True)
    assert (row["location"], row["branch"], row["base"], row["commit"], row["folder"]) == \
        (str(world), "main", p["base"], done["commit"], "apps/dhcp_watch/")
    assert row["files"] == [{k: f[k] for k in ("path", "size", "sha256")} for f in p["files"]]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", row["at"])


def test_a_base_moved_since_the_preview_is_refused_naming_both(world, tmp_path):
    p = preview()
    other = push_other(world, tmp_path)
    done = add(p)
    assert done["outcome"] == "refused" and done["moved"] is True
    assert (f"the base commit moved since the preview (previewed {p['base'][:12]}, now "
            f"{other[:12]} on main)") in done["error"]
    assert head(world) == other and leftovers() == []
    assert "drafts" not in R.read_record(NET)["record"], "nothing was tried, nothing recorded"


def test_files_changed_since_the_preview_are_refused_naming_it(world):
    p = preview()
    done = add(p, files=draft(**{"dhcp_watch.py": LOGIC + b"# changed\n"}))
    assert done["outcome"] == "refused" and "the files changed since the preview" in \
        done["error"]
    assert head(world) == p["base"]


def test_a_non_fast_forward_is_refused_by_git_and_recorded(world, tmp_path, monkeypatch):
    """Someone pushes between the build and the push: git itself refuses ours."""
    p = preview()
    real = D.build

    def build_then_race(tmp, program):
        commit = real(tmp, program)
        state["other"] = push_other(world, tmp_path, "race.md")
        return commit
    state = {}
    monkeypatch.setattr(D, "build", build_then_race)
    done = add(p)
    assert done["outcome"] == "refused" and "was refused by git" in done["error"]
    assert re.search(r"rejected|non-fast-forward|fetch first", done["error"]), done["error"]
    assert head(world) == state["other"], "the other person's commit stands"
    (row,) = R.read_record(NET)["record"]["drafts"]
    assert row["ok"] is False and "was refused by git" in row["error"] and row["commit"] == ""
    assert leftovers() == []


def test_the_throwaway_is_removed_and_mercurys_copy_is_never_built_in(world, monkeypatch):
    made = []
    real = D.tempfile.mkdtemp

    def mkdtemp(**kw):
        made.append(real(**kw))
        return made[-1]
    monkeypatch.setattr(D.tempfile, "mkdtemp", mkdtemp)
    add(preview())
    assert len(made) == 2 and not any(os.path.exists(m) for m in made)
    assert all(os.path.dirname(m) == os.path.dirname(R.copy_dir(NET)) for m in made)
    refs = git(R.copy_dir(NET), "for-each-ref", "--format=%(refname)").splitlines()
    assert refs == [R.FETCHED_REF], "the copy holds the fetch only, never a draft's base"


def test_an_unreadable_record_refuses_before_anything_is_pushed(world):
    p = preview()
    os.makedirs(os.path.dirname(R._record_path(NET)), exist_ok=True)
    with open(R._record_path(NET), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    done = add(p)
    assert done["outcome"] == "refused" and "can't be read" in done["error"]
    assert head(world) == p["base"]


def test_the_carried_files_come_back_as_they_went():
    files = draft()
    checked = D.check_files(NAME, files)
    back, why = D.files_from_form([c["rel"] for c in D.carried(checked)],
                                  [c["b64"] for c in D.carried(checked)])
    assert why == "" and back == files
    assert D.files_from_form(["a"], [])[1] == ("the form carries 1 paths and 0 files: they come "
                                               "in pairs")
    assert "is not base64" in D.files_from_form(["a"], ["@@"])[1]


def test_a_folder_at_its_cap_fits_the_confirm_under_flasks_form_limit():
    """The cap's own claim (draft_write's caps): a folder of `MAX_TOTAL_BYTES`, carried back by
    the confirm as base64 and URL-encoded, stays under the 500,000 bytes Flask 3.1 takes."""
    from urllib.parse import urlencode

    text = bytes(range(32, 127)) * (D.MAX_TOTAL_BYTES // 95 + 1)
    files = draft(**{"a.py": text[:D.MAX_FILE_BYTES]})
    files["b.py"] = text[:D.MAX_TOTAL_BYTES - sum(len(v) for v in files.values())]
    checked = D.check_files(NAME, files)
    assert sum(f["size"] for f in checked) == D.MAX_TOTAL_BYTES
    body = urlencode([("list", "Default"), ("name", NAME), ("hash", "a" * 64), ("base", "b" * 40),
                      ("files_sha", "c" * 64)]
                     + [kv for c in D.carried(checked)
                        for kv in (("path", c["rel"]), ("content", c["b64"]))])
    assert len(body) < 500_000, len(body)


@pytest.mark.parametrize("uploads, words", [
    ([("manifest.yml", b"x")], "came with no folder path"),
    ([("a/manifest.yml", b"x"), ("b/x.py", b"x")], "more than one folder (a, b)"),
    ([], "no folder was chosen"),
])
def test_a_folder_upload_is_one_folder_with_its_paths(uploads, words):
    assert words in D.files_from_upload(uploads)[2]


# ── the routes ───────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(world, monkeypatch):
    import app as A

    heard = []
    monkeypatch.setattr("modules.invalidation.announce",
                        lambda keys, by, ok=True: heard.append((tuple(keys), by)))
    c = A.app.test_client()
    c.heard = heard
    return c


def upload(c, files=None, top=NAME):
    from io import BytesIO

    files = draft() if files is None else files
    return c.post("/v2/sdn/apps/draft/preview", content_type="multipart/form-data", data={
        "list": NET, "file": [(BytesIO(data), f"{top}/{rel}") for rel, data in files.items()]})


def hidden(html):
    out = {}
    for m in re.finditer(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"', html):
        out.setdefault(m.group(1), []).append(unescape(m.group(2)))
    return out


def test_the_folder_upload_keeps_each_files_path_and_confirms(client, world):
    # The control at rest opens the picker, whose form the script sends with each file's path.
    html = client.get(f"/v2/sdn/apps?list={NET}").get_data(as_text=True)
    assert "Add an app as a Draft…" in html and f"/v2/sdn/apps/draft?list={NET}&amp;open=form" \
        in html
    form = client.get(f"/v2/sdn/apps/draft?list={NET}&open=form").get_data(as_text=True)
    assert "webkitdirectory" in form and "data-draft-folder" in form
    assert 'hx-encoding="multipart/form-data"' in form
    r = upload(client)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Add dhcp_watch 0.1.0 as a Draft" in html, html
    assert "apps/dhcp_watch/tests/test_watch.py" in html, "the relative path came through"
    f = hidden(html)
    assert f["path"] == sorted(draft()) and f["name"] == [NAME]
    form = {"list": NET, "name": NAME, "hash": f["hash"][0], "base": f["base"][0],
            "files_sha": f["files_sha"][0], "path": f["path"], "content": f["content"]}
    r = client.post("/v2/sdn/apps/draft/confirm", data=form)
    done = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and "dhcp_watch 0.1.0 added as a Draft" in done, done
    assert "Fetched and registered as a Draft" in done and "Open dhcp_watch's page" in done
    # The verified person is the suite's own, never the form's.
    assert git(world, "log", "-1", "--format=%ae", "main") == "test-person@example.invalid"
    assert (R.ANNOUNCE_KEYS, R.ANNOUNCER) in client.heard


def test_a_refused_upload_is_drawn_in_place_with_no_confirm(client, world):
    r = upload(client, top="Bad-Name")
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 409 and "Not added:" in html and "is not an app's name" in html
    assert "draft/confirm" not in html and client.heard == []


def test_an_upload_over_a_cap_is_refused_and_adds_nothing(client, world):
    base = head(world)
    r = upload(client, draft(**{"big.py": b"x" * (D.MAX_FILE_BYTES * 3)}))
    assert r.status_code == 409 and (f"big.py is at least {D.MAX_FILE_BYTES + 1} bytes, over a "
                                     f"file's {D.MAX_FILE_BYTES}") in unescape(r.get_data(True))
    r = upload(client, {f"f{i}.py": b"x" for i in range(D.MAX_FILES + 1)})
    assert r.status_code == 400 and (f"the folder holds {D.MAX_FILES + 1} files, over a "
                                     f"Draft's {D.MAX_FILES}") in unescape(r.get_data(True))
    assert head(world) == base and client.heard == []


def test_a_confirm_with_no_hash_or_a_stale_one_adds_nothing(client, world):
    f = hidden(upload(client).get_data(as_text=True))
    form = {"list": NET, "name": NAME, "path": f["path"], "content": f["content"]}
    r = client.post("/v2/sdn/apps/draft/confirm", data=form)
    assert r.status_code == 400 and "carries no preview hash" in unescape(r.get_data(as_text=True))
    r = client.post("/v2/sdn/apps/draft/confirm", data=dict(form, hash="a" * 64))
    assert r.status_code == 409 and "moved since the preview" in unescape(r.get_data(as_text=True))
    assert head(world) == f["base"][0]


@pytest.mark.real_identity
def test_a_caller_with_no_verified_identity_is_refused(world):
    import app as A

    base = head(world)
    r = A.app.test_client().post("/v2/sdn/apps/draft/confirm", data={"list": NET})
    assert r.status_code == 403 and (r.get_json() or {}).get("requires_identity") is True
    assert head(world) == base


# ── the picker's script ──────────────────────────────────────────────────────────────────────

def test_the_script_sends_each_file_by_its_path_in_the_folder():
    import dukpy

    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "static", "js", "nmas_draft.js"), encoding="utf-8") as fh:
        src = fh.read()
    got = dukpy.evaljs("var window = {};\n" + src + """
        var sent = [], fd = {'delete': function (k) { sent.push(['delete', k]); },
                             append: function (k, f, n) { sent.push([k, f.id, n]); }};
        var n = window.NMAS_DRAFT.rewrite(fd, [
            {id: 1, name: 'manifest.yml', webkitRelativePath: 'dhcp_watch/manifest.yml'},
            {id: 2, name: 'test_watch.py', webkitRelativePath: 'dhcp_watch/tests/test_watch.py'},
            {id: 3, name: 'loose.py', webkitRelativePath: ''}]);
        [n, sent];""")
    assert got == [3, [["delete", "file"], ["file", 1, "dhcp_watch/manifest.yml"],
                       ["file", 2, "dhcp_watch/tests/test_watch.py"], ["file", 3, "loose.py"]]]
    assert json.dumps(got)
