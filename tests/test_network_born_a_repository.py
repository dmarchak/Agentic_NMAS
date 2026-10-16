"""C931: a network's repository exists from the moment the network does, and Seed says what
it did, through the real app, on a store inside a planted parent repository (on the host the
store, `data/`, sits inside the application's checkout and is ignored there).

Found 2026-10-16 writing walk W2: Templates › "Seed the library…" on a network created on v2
committed nothing and said the network had every shipped file. Create made the folder and no
repository, so Seed's `git status` climbed to the repository holding the store, read it clean,
and the four copied files sat uncommitted under a card saying "unchanged".

What is held:

- a network created on v2 (preview, then Create) has a `config_repo` that is a repository with
  a first commit, its own top level; the parent repository is untouched;
- Seed on it commits the shipped files as the person, and History shows the commit with no
  uncommitted path;
- a network made before this (a folder with no `.git`): History says it has no repository yet
  and that its first commit makes it (C945; never "clean"), and its first Seed makes the
  repository (the one init, as every write path does) and commits; nothing reaches the parent;
  a repository git cannot read is said as "could not be read", with git's error (C945);
  its timeline, on the page and a device's tab, says the same once, naming the records the
  repository will hold, never "could not be read" (C957);
- Seed's failed commit, and a status it could not read, are said as failed (a danger card
  naming the git error, HTTP 500), never "Nothing was added".
"""

import json
import os
import re
import subprocess

import pytest


def _sh(cwd, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def _flat(r):
    return re.sub(r"\s+", " ", r.get_data(as_text=True))


@pytest.fixture
def store(tmp_path, monkeypatch):
    """The settings store inside a parent repository that ignores it, holding Default."""
    from modules import config, device

    parent = tmp_path / "checkout"
    data = parent / "store"
    (data / "lists" / "default").mkdir(parents=True)
    _sh(parent, "init", "-q", "-b", "main")
    (parent / ".gitignore").write_text("store/\n")
    (parent / "README").write_text("the application\n")
    _sh(parent, "add", ".gitignore", "README")
    _sh(parent, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "app")

    monkeypatch.setattr(config, "DATA_DIR", str(data))
    monkeypatch.setattr(config, "LISTS_DIR", str(data / "lists"))
    settings = data / "user_settings.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(settings))
    registry = data / "device_lists.json"
    registry.write_text(json.dumps({"current_list": "Default", "lists": {"Default": "default"}}),
                        encoding="utf-8")
    monkeypatch.setattr(device, "DEVICE_LISTS_CONFIG", str(registry))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)

    def state():
        return {"head": _sh(parent, "rev-parse", "HEAD")[1],
                "log": _sh(parent, "log", "--oneline", "--all")[1],
                "index": _sh(parent, "ls-files", "--stage")[1],
                "status": _sh(parent, "status", "--porcelain")[1],
                "tags": _sh(parent, "tag", "-l")[1]}
    import app as A
    return {"client": A.app.test_client(), "data": data, "registry": registry,
            "state": state, "before": state()}


def _create(store, name):
    c = store["client"]
    pv = _flat(c.post("/v2/settings/networks/new/preview", data={"name": name},
                      headers={"HX-Request": "true"}))
    fp = re.search(r'name="fingerprint" value="([0-9a-f]+)"', pv).group(1)
    r = c.post("/v2/settings/networks/new", data={"name": name, "fingerprint": fp},
               headers={"HX-Request": "true"})
    assert r.status_code == 200 and f"Created {name}" in _flat(r), _flat(r)[:600]


def _seed(store, name):
    c = store["client"]
    html = c.get(f"/v2/templates/seed?list={name}").get_data(as_text=True)
    sig = re.search(r'name="signature" value="([^"]*)"', html).group(1)
    return c.post("/v2/templates/seed", data={"list": name, "signature": sig})


def _card(r):
    m = re.search(r'<section class="op-card[^"]*" id="tpl-card".*?</section>', _flat(r))
    assert m, _flat(r)[:600]
    return m.group(0)


def _header(r):
    """History's header, the remote card (`templates/v2/_history_remote.html`)."""
    m = re.search(r'<section class="card hist-remote" id="hist-remote".*?</section>', _flat(r))
    assert m, _flat(r)[:600]
    return m.group(0)


class TestANetworkIsBornARepository:
    def test_create_makes_its_repository(self, store):
        _create(store, "Site East")
        repo = store["data"] / "lists" / "site_east" / "config_repo"
        assert (repo / ".git").is_dir(), "a network created on v2 has no repository"
        rc, top, _e = _sh(repo, "rev-parse", "--show-toplevel")
        assert rc == 0 and os.path.realpath(top) == os.path.realpath(repo)
        assert _sh(repo, "rev-parse", "--verify", "HEAD")[0] == 0, "no first commit"
        assert store["state"]() == store["before"], "the parent repository was written"

    def test_a_repository_git_could_not_make_refuses_the_network(self, store, monkeypatch):
        """No network without its repository: the folder this call made is removed (so the
        name stays free, C639) and nothing is registered."""
        monkeypatch.setattr("modules.nsot.repo.init_repo", lambda repo: True)
        c = store["client"]
        pv = _flat(c.post("/v2/settings/networks/new/preview", data={"name": "Site East"},
                          headers={"HX-Request": "true"}))
        fp = re.search(r'name="fingerprint" value="([0-9a-f]+)"', pv).group(1)
        r = c.post("/v2/settings/networks/new", data={"name": "Site East", "fingerprint": fp},
                   headers={"HX-Request": "true"})
        assert r.status_code == 409
        assert "git could not make lists/site_east/config_repo a repository" in _flat(r)
        assert not (store["data"] / "lists" / "site_east").exists()
        assert "Site East" not in json.loads(store["registry"].read_text())["lists"]

    def test_seed_commits_the_library_and_history_shows_it(self, store):
        from modules.nsot import approve_op, templates_repo
        _create(store, "Site East")
        repo = str(store["data"] / "lists" / "site_east" / "config_repo")
        r = _seed(store, "Site East")
        card = _card(r)
        assert r.status_code == 200 and "seeded" in card, card
        assert "Nothing was added" not in card
        msg = _sh(repo, "log", "-1", "--format=%B")[1]
        assert msg.startswith("template: seed library (")
        assert "Actor: test-person@example.invalid" in msg
        assert set(approve_op.committed_templates(repo)) == \
            {p for p in templates_repo.seed_paths() if p.endswith(".j2")}
        assert _sh(repo, "status", "--porcelain")[1] == "", "seeded files left uncommitted"
        history = _flat(store["client"].get("/v2/history?list=Site%20East"))
        assert "template: seed library (" in history
        assert "could not be read" not in history and "are not committed" not in history
        assert "No repository yet" not in history
        assert store["state"]() == store["before"]


@pytest.fixture
def old(store):
    """A network made before networks were born with a repository: registered, its folder
    holding a `config_repo` with no `.git` (the copied library, never committed)."""
    folder = store["data"] / "lists" / "old"
    (folder / "config_repo").mkdir(parents=True)
    (folder / "devices.csv").write_text("hostname,ip\n", encoding="utf-8")
    reg = json.loads(store["registry"].read_text())
    reg["lists"]["Old"] = "old"
    store["registry"].write_text(json.dumps(reg), encoding="utf-8")
    return dict(store, repo=folder / "config_repo")


class TestANetworkWithNoRepository:
    def test_history_says_it_has_no_repository_yet_and_what_makes_one(self, old):
        """C945: the header said "The working tree could not be read." with no cause; a folder
        with no `.git` is a network whose first commit makes its repository, and says so."""
        r = old["client"].get("/v2/history?list=Old")
        assert r.status_code == 200
        history = _header(r)
        assert "No repository yet: the network's first commit makes it." in history, \
            "a folder with no .git did not say it has no repository yet"
        assert "could not be read" not in history and "Everything is committed" not in history
        assert not (old["repo"] / ".git").exists(), "a read made the repository"
        assert old["state"]() == old["before"]

    def test_an_unreadable_repository_says_could_not_be_read_with_git_s_error(self, old):
        """C945: any failure other than a missing `.git` keeps "could not be read", naming
        git's error. Planted: a `.git` file pointing at a repository that is not there."""
        (old["repo"] / ".git").write_text("gitdir: ../planted-for-c945\n", encoding="utf-8")
        r = old["client"].get("/v2/history?list=Old")
        assert r.status_code == 200
        history = _header(r)
        assert "The working tree could not be read: " in history, history
        # The expectation comes from git itself, by a path independent of the code under test:
        # the same `git status` in the same folder, its own words (CI #853: the runner's git
        # words it otherwise than the laptop's 2.53, so a hard-coded phrase failed there).
        import html
        from modules.redact import redact_text
        own = subprocess.run(["git", "status", "--porcelain"], cwd=str(old["repo"]),
                             capture_output=True, text=True,
                             env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(old["repo"].parent)))
        assert own.returncode != 0 and own.stderr.strip(), "git read the planted .git file"
        said = html.escape(redact_text(own.stderr.strip().splitlines()[0]), quote=False)
        assert said in history, \
            f"the header did not carry git's error ({said!r})"
        assert "No repository yet" not in history and "Everything is committed" not in history
        assert old["state"]() == old["before"]

    def test_its_first_seed_makes_the_repository_and_commits(self, old):
        r = _seed(old, "Old")
        card = _card(r)
        assert r.status_code == 200 and "seeded" in card and "Nothing was added" not in card
        assert (old["repo"] / ".git").is_dir()
        assert _sh(old["repo"], "log", "-1", "--format=%s")[1].startswith(
            "template: seed library (")
        assert _sh(old["repo"], "status", "--porcelain")[1] == ""
        assert old["state"]() == old["before"], "the parent repository was written"


def _timeline_card(r):
    """History's timeline card (`templates/v2/_history_timeline.html`)."""
    m = re.search(r'<section class="card hist-timeline" id="hist-timeline".*?</section>', _flat(r))
    assert m, _flat(r)[:600]
    return m.group(0)


def _tab(r):
    """A device's History tab (`templates/v2/_history.html`)."""
    m = re.search(r'<section class="card history" id="history".*?</section>', _flat(r))
    assert m, _flat(r)[:600]
    return m.group(0)


#: Every timeline source that reads the network's repository, in `SOURCES`' order: the fleet's
#: view reads all five; a device's view reads the first three (the other commits and the
#: baseline decisions are about no one device).
FLEET_UNBORN = ("the golden history, the intent history, the saves that measured devices, "
                "the repository&#39;s other commits and the baseline decisions")
DEVICE_UNBORN = "the golden history, the intent history and the saves that measured devices"


@pytest.fixture
def old_r1(old):
    (old["data"] / "lists" / "old" / "devices.csv").write_text("hostname,ip\nr1,192.0.2.1\n",
                                                                encoding="utf-8")
    return old


class TestTheTimelineWithNoRepository:
    """C957: the timeline said "the golden history could not be read: … is not a git
    repository (it has no .git)" (and the same for the intent history, the measured saves, the
    other commits and the baseline decisions) for a network whose first commit has not made its
    repository yet. Decided by `repo.has_repository`, the header's test (C945)."""

    def test_history_says_no_repository_yet_once_naming_what_it_holds(self, old_r1):
        r = old_r1["client"].get("/v2/history?list=Old")
        assert r.status_code == 200
        card = _timeline_card(r)
        assert ("No repository yet: the network's first commit makes it. Until then "
                f"{FLEET_UNBORN} have nothing to show.") in card, card[-1200:]
        assert card.count("No repository yet") == 1
        assert "could not be read" not in card and "has no .git" not in card, card[-1200:]
        assert not (old_r1["repo"] / ".git").exists(), "a read made the repository"
        assert old_r1["state"]() == old_r1["before"]

    def test_the_timeline_redrawn_alone_says_the_same(self, old_r1):
        """The card's own route, which a landed record redraws it by."""
        old_r1["client"].get("/v2/history?list=Old")       # makes Old the active network
        card = _timeline_card(old_r1["client"].get("/v2/history/timeline?list=Old"))
        assert f"Until then {FLEET_UNBORN} have nothing to show." in card, card[-1200:]
        assert "could not be read" not in card

    def test_a_device_s_history_tab_says_it_naming_its_own_records(self, old_r1):
        r = old_r1["client"].get("/v2/device/r1?list=Old&tab=history")
        assert r.status_code == 200
        tab = _tab(r)
        assert ("No repository yet: the network's first commit makes it. Until then "
                f"{DEVICE_UNBORN} have nothing to show.") in tab, tab[-1200:]
        assert "could not be read" not in tab and "has no .git" not in tab, tab[-1200:]

    def test_an_unreadable_repository_keeps_its_errors(self, old_r1):
        """The control: a `.git` that git cannot read is not "no repository yet"; each source
        that reads it keeps "could not be read" with git's own error."""
        (old_r1["repo"] / ".git").write_text("gitdir: ../planted-for-c957\n", encoding="utf-8")
        own = subprocess.run(["git", "log", "-1"], cwd=str(old_r1["repo"]),
                             capture_output=True, text=True,
                             env=dict(os.environ,
                                      GIT_CEILING_DIRECTORIES=str(old_r1["repo"].parent)))
        assert own.returncode != 0 and own.stderr.strip(), "git read the planted .git file"
        import html
        from modules.redact import redact_text
        said = html.escape(redact_text(own.stderr.strip().splitlines()[0]), quote=False)
        card = _timeline_card(old_r1["client"].get("/v2/history?list=Old"))
        assert "No repository yet" not in card, card[-1200:]
        for words in ("the golden history could not be read: ",
                      "the intent history could not be read: ",
                      "the saves that measured devices could not be read: ",
                      "the repository&#39;s other commits could not be read: ",
                      "the baseline decisions could not be read: "):
            assert words in card, f"{words!r} not said: {card[-1500:]}"
        assert said in card, f"git's error ({said!r}) not carried"
        tab = _tab(old_r1["client"].get("/v2/device/r1?list=Old&tab=history"))
        assert "No repository yet" not in tab
        assert "the golden history could not be read: " in tab and said in tab
        assert old_r1["state"]() == old_r1["before"]


class TestAFailedSeedIsSaid:
    def test_a_failed_commit_is_said_naming_the_error(self, store, monkeypatch):
        _create(store, "Site East")
        monkeypatch.setattr("modules.nsot.repo.save_templates", lambda *a, **k: {
            "ok": False, "error": "commit failed: fatal: planted for C931"})
        r = _seed(store, "Site East")
        card = _card(r)
        assert r.status_code == 500 and "op-danger" in card, card
        assert "Not done" in card
        assert ("Seeding Site East&#39;s library failed: nothing was committed: commit failed: "
                "fatal: planted for C931") in card
        assert "Nothing was added" not in card and "unchanged" not in card

    def test_an_unreadable_status_is_said_naming_the_error(self, store, monkeypatch):
        from modules.nsot import repo as R
        _create(store, "Site East")
        real = R.git

        def git(repo, *args):
            if args[:1] == ("status",):
                return 128, "", "fatal: status planted for C931"
            return real(repo, *args)
        monkeypatch.setattr(R, "git", git)
        r = _seed(store, "Site East")
        card = _card(r)
        assert r.status_code == 500 and "op-danger" in card, card
        assert "the repository&#39;s status could not be read (fatal: status planted for C931)" \
            in card
        assert "Nothing was added" not in card
