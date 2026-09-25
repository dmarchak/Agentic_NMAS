"""OPEN_FINDINGS C6: which networks run a stale seed of a shipped template.

Four answers -- current, stale, edited, edited_and_stale -- from git history
alone, with real repositories: an "application" whose shipped templates have
history, and a "network" config repo seeded from it at some point.
"""

import os
import subprocess

import pytest

from modules.nsot import templates_repo as T


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True,
                   capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t",
                        "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t"})


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


@pytest.fixture
def world(tmp_path):
    """An app with shipped `_common.j2` v1 → v2 → v3 and `x/base.j2` v1;
    a network repo whose copies are set per test."""
    app = tmp_path / "app"
    builtin = app / "templates"
    _git(tmp_path, "init", "-q", str(app))
    net = tmp_path / "net"
    _git(tmp_path, "init", "-q", str(net))

    def ship(rel, text):
        _write(builtin / rel, text)
        _git(app, "add", "-A")
        _git(app, "commit", "-q", "-m", f"ship {rel}")

    def place(rel, text):
        _write(net / "templates" / rel, text)
        _git(net, "add", "-A")
        _git(net, "commit", "-q", "-m", f"network {rel}")

    ship("_common.j2", "v1\n")
    ship("x/base.j2", "base v1\n")
    return app, builtin, net, ship, place


def _state(report, rel):
    for e in report["files"] + report["unclassified"]:
        if e["path"] == rel:
            return e["state"]
    raise AssertionError(f"{rel} not reported")


class TestTheFourStates:
    def test_current(self, world):
        app, builtin, net, ship, place = world
        place("_common.j2", "v1\n")
        assert _state(T.seed_status(str(net), str(builtin)), "_common.j2") \
            == "current"

    def test_stale_when_the_shipped_file_moved_and_this_did_not(self, world):
        app, builtin, net, ship, place = world
        place("_common.j2", "v1\n")
        ship("_common.j2", "v2\n")
        r = T.seed_status(str(net), str(builtin))
        assert _state(r, "_common.j2") == "stale"

    def test_edited_is_not_a_defect(self, world):
        app, builtin, net, ship, place = world
        place("_common.j2", "v1\n")
        place("_common.j2", "v1 + a local change\n")
        r = T.seed_status(str(net), str(builtin))
        assert _state(r, "_common.j2") == "edited"
        detail = next(e["detail"] for e in r["files"]
                      if e["path"] == "_common.j2")
        assert "nothing to do" in detail

    def test_edited_and_stale_when_both_moved(self, world):
        app, builtin, net, ship, place = world
        place("_common.j2", "v1\n")
        place("_common.j2", "v1 + a local change\n")
        ship("_common.j2", "v2\n")
        assert _state(T.seed_status(str(net), str(builtin)), "_common.j2") \
            == "edited_and_stale"

    def test_a_hand_carried_shipped_change_is_stale_not_edited(self, world):
        """The measured shape on `default`: the network's copy equals an
        older SHIPPED version it was brought up to by hand. It was never
        edited locally."""
        app, builtin, net, ship, place = world
        place("_common.j2", "v1\n")
        ship("_common.j2", "v2\n")
        place("_common.j2", "v2\n")        # carried in by hand
        ship("_common.j2", "v3\n")
        assert _state(T.seed_status(str(net), str(builtin)), "_common.j2") \
            == "stale"

    def test_every_file_is_reported_in_exactly_one_state(self, world):
        app, builtin, net, ship, place = world
        place("_common.j2", "v1\n")
        place("x/base.j2", "base v1\n")
        r = T.seed_status(str(net), str(builtin))
        paths = [e["path"] for e in r["files"] + r["unclassified"]]
        assert sorted(paths) == sorted(["_common.j2", "x/base.j2",
                                        T.BINDINGS_FILE])
        assert all(e["state"] in T.SEED_STATES for e in r["files"])
        assert all(e["state"] in T.SEED_UNCLASSIFIED and e["reason"]
                   for e in r["unclassified"])


class TestRelativePaths:
    """Measured live: every test above passed absolute tmp paths, and the
    deployed call passes a RELATIVE repo path -- which made every file read
    `edited_and_stale`. The fixture could not exhibit the case."""

    def test_a_relative_repo_path_classifies_the_same(self, world,
                                                      monkeypatch):
        app, builtin, net, ship, place = world
        place("_common.j2", "v1\n")
        ship("_common.j2", "v2\n")
        place("x/base.j2", "base v1\n")
        monkeypatch.chdir(net.parent)
        r = T.seed_status(os.path.relpath(net), os.path.relpath(builtin))
        assert _state(r, "_common.j2") == "stale"
        assert _state(r, "x/base.j2") == "current"


class TestWhenHistoryCannotAnswer:
    def test_absent_is_named(self, world):
        app, builtin, net, ship, place = world
        place("_common.j2", "v1\n")
        assert _state(T.seed_status(str(net), str(builtin)), "x/base.j2") \
            == "absent"

    def test_no_common_base_is_not_guessed(self, world):
        app, builtin, net, ship, place = world
        place("_common.j2", "something never shipped\n")
        assert _state(T.seed_status(str(net), str(builtin)), "_common.j2") \
            == "no_common_base"

    def test_an_app_that_is_not_a_checkout_says_so(self, world, tmp_path):
        app, builtin, net, ship, place = world
        loose = tmp_path / "loose"
        _write(loose / "_common.j2", "v9\n")
        place("_common.j2", "v1\n")
        r = T.seed_status(str(net), str(loose))
        assert r["ok"] is False and "not a git checkout" in r["reason"]
        assert _state(r, "_common.j2") == "no_shipped_history"


def test_the_classifier_never_writes_to_either_repository(world):
    app, builtin, net, ship, place = world
    place("_common.j2", "v1\n")
    ship("_common.j2", "v2\n")
    before = [subprocess.run(["git", "-C", str(r), "status", "--porcelain"],
                             capture_output=True, text=True).stdout
              for r in (app, net)]
    T.seed_status(str(net), str(builtin))
    after = [subprocess.run(["git", "-C", str(r), "status", "--porcelain"],
                            capture_output=True, text=True).stdout
             for r in (app, net)]
    assert before == after
