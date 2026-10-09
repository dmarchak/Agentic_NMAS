"""Phase 4 section 8.4 (signed off by the operator, 2026-10-09): a release whose venv identity
differs from the running venv's moves the link /opt/mercury-venv in the SAME restart; a release
whose venv is not built and proved is refused before anything moves; a rollback puts the link
back with the commit; after a good deploy only the current and previous venvs are kept.

The functions live in scripts/nmas-deploy, whose root copy the updater loads (root never
imports the user-writable checkout). They run here against real links in a temporary folder,
with no sudo: the same commands, the same renames.
"""

import os
import subprocess
import types

import pytest

from modules import app_interpreter
from tests.test_nmas_deploy import _head, _run, _run_entry, _script, world  # noqa: F401
from tests.test_update_button import _g, _local_git, _request, _updater, repos  # noqa: F401

NO_SUDO = {"sudo": (), "ln": "ln", "mv": "mv", "rm": "rm", "grep": "grep"}


@pytest.fixture
def opt(tmp_path):
    """A stand-in /opt: the link, the previous link, and venvs aaaa… (running) and bbbb…."""
    base = tmp_path / "opt"
    base.mkdir()
    for vid in ("a" * 12, "b" * 12):
        (base / f"mercury-venv-{vid}").mkdir()
        (base / f"mercury-venv-{vid}" / ".mercury-proved").write_text(f"id {vid}\ncommit x\n")
    os.symlink(f"mercury-venv-{'a' * 12}", base / "mercury-venv")
    return types.SimpleNamespace(base=base, link=str(base / "mercury-venv"),
                                 previous=str(base / "mercury-venv.previous"),
                                 prefix=str(base / "mercury-venv-"))


def _point(D, opt):
    D.VENV_LINK, D.VENV_PREVIOUS, D.VENV_PREFIX = opt.link, opt.previous, opt.prefix
    D.VENV_BINS = NO_SUDO


# --- the identity ---------------------------------------------------------------------------

def test_the_identity_from_git_bytes_equals_the_host_steps_one(tmp_path):
    """Two computations of one fact (root cannot import the checkout's): held equal, on files
    ending in a newline, which a text read that strips would lose."""
    D = _script()
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "requirements.lock").write_text("a==1 \\\n    --hash=sha256:00\n")
    (repo / "requirements-test.txt").write_text("b==2\n\n")
    _g(repo, "add", "-A")
    _g(repo, "commit", "-q", "-m", "x")
    sha = _g(repo, "rev-parse", "HEAD")
    assert D.venv_id_from(D.git_show_bytes(str(repo), sha)) == app_interpreter.venv_id(str(repo))
    assert D.VENV_INPUTS == app_interpreter.VENV_INPUTS


# --- the plan -------------------------------------------------------------------------------

def test_no_link_is_before_the_first_switch_and_reads_nothing(tmp_path):
    D = _script()
    plan = D.venv_plan(lambda: pytest.fail("read the release's files"), link=str(tmp_path / "x"))
    assert plan == {"state": "none", "from": None, "to": None}


def test_the_same_identity_moves_nothing(opt):
    D = _script()
    assert D.venv_plan("a" * 12, opt.link, opt.prefix)["state"] == "same"


def test_a_proved_other_venv_is_swapped_and_an_unproved_one_refused(opt):
    D = _script()
    plan = D.venv_plan("b" * 12, opt.link, opt.prefix)
    assert plan == {"state": "swap", "from": "a" * 12, "to": "b" * 12}
    (opt.base / f"mercury-venv-{'b' * 12}" / ".mercury-proved").unlink()
    assert D.venv_plan("b" * 12, opt.link, opt.prefix)["state"] == "unbuilt"
    assert D.venv_plan("c" * 12, opt.link, opt.prefix)["state"] == "unbuilt"
    # A mark naming another identity is not this venv's proof.
    (opt.base / f"mercury-venv-{'b' * 12}" / ".mercury-proved").write_text(f"id {'c' * 12}\n")
    assert D.venv_plan("b" * 12, opt.link, opt.prefix)["state"] == "unbuilt"


def test_the_refusal_names_both_identities_and_a_build_from_a_clone(opt):
    D = _script()
    words = D.venv_refusal({"state": "unbuilt", "from": "a" * 12, "to": "c" * 12},
                           "f" * 40, "/srv/checkout")
    assert "a" * 12 in words and "c" * 12 in words and "venv-1-build.sh" in words
    assert "git clone -q --shared /srv/checkout" in words and "<" not in words


# --- the swap, its undo and the pruning -----------------------------------------------------

def test_the_swap_records_the_previous_and_moves_the_link_relative(opt):
    D = _script()
    plan = {"state": "swap", "from": "a" * 12, "to": "b" * 12}
    D.swap_venv(plan, bins=NO_SUDO, link=opt.link, previous=opt.previous)
    assert os.readlink(opt.link) == f"mercury-venv-{'b' * 12}"
    assert os.readlink(opt.previous) == f"mercury-venv-{'a' * 12}"
    D.unswap_venv(plan, bins=NO_SUDO, link=opt.link)
    assert os.readlink(opt.link) == f"mercury-venv-{'a' * 12}"
    assert not os.path.exists(opt.link + ".new")


def test_pruning_keeps_current_previous_unproved_and_loaded(opt, tmp_path):
    D = _script()
    for vid, proved in (("c" * 12, True), ("d" * 12, True), ("e" * 12, False)):
        (opt.base / f"mercury-venv-{vid}").mkdir()
        if proved:
            (opt.base / f"mercury-venv-{vid}" / ".mercury-proved").write_text(f"id {vid}\n")
    maps = tmp_path / "maps"           # a process's maps naming dddd's folder
    maps.write_text(f"7f00 r-xp 0 08:01 1 {opt.prefix}{'d' * 12}/lib/x.so\n")
    removed, held = D.prune_venvs({"a" * 12, "b" * 12}, bins=NO_SUDO, prefix=opt.prefix,
                                  maps=[str(maps)])
    assert [os.path.basename(p) for p in removed] == [f"mercury-venv-{'c' * 12}"]
    assert [os.path.basename(p) for p in held] == [f"mercury-venv-{'d' * 12}"]
    left = sorted(p.name for p in opt.base.iterdir() if p.name.startswith("mercury-venv-"))
    assert left == [f"mercury-venv-{v * 12}" for v in "abde"], "unproved eeee is left"


# --- nmas-deploy, end to end ----------------------------------------------------------------

def _release(world, opt, lock="x==2\n"):
    """A release whose lock differs; returns (sha, its venv identity)."""
    sha = world.advance({"requirements.lock": lock, "requirements-test.txt": "t==1\n",
                         "app.py": "v = 2\n"})
    D = _script()
    return sha, D.venv_id_from(D.git_show_bytes(world.origin, sha))


def test_a_release_whose_venv_is_not_built_is_refused_and_nothing_moves(world, opt, capsys):
    sha, vid = _release(world, opt)
    code, restarted, _ = _run(world, {sha: _run_entry(sha)}, setup=lambda D: _point(D, opt))
    err = capsys.readouterr().err
    assert code != 0 and not restarted and _head(world) == world.base
    assert vid in err and "a" * 12 in err and "venv-1-build.sh" in err
    assert os.readlink(opt.link) == f"mercury-venv-{'a' * 12}"


def test_a_built_venv_moves_with_the_release_in_the_same_restart(world, opt, capsys):
    sha, vid = _release(world, opt)
    (opt.base / f"mercury-venv-{vid}").mkdir()
    (opt.base / f"mercury-venv-{vid}" / ".mercury-proved").write_text(f"id {vid}\n")
    code, restarted, _ = _run(world, {sha: _run_entry(sha)}, setup=lambda D: _point(D, opt))
    out = capsys.readouterr().out
    assert code == 0 and restarted and _head(world) == sha
    assert os.readlink(opt.link) == f"mercury-venv-{vid}"
    assert os.readlink(opt.previous) == f"mercury-venv-{'a' * 12}"
    # bbbb… was neither current nor previous, proved, and loaded by nothing here.
    assert not (opt.base / f"mercury-venv-{'b' * 12}").exists()
    assert vid in out


def test_before_the_first_switch_nothing_is_compared(world, tmp_path, capsys):
    sha = world.advance({"app.py": "v = 2\n"})        # no lock in this release at all
    nolink = types.SimpleNamespace(link=str(tmp_path / "none"), previous=str(tmp_path / "p"),
                                   prefix=str(tmp_path / "none-"))
    code, restarted, _ = _run(world, {sha: _run_entry(sha)}, setup=lambda D: _point(D, nolink))
    assert code == 0 and restarted and _head(world) == sha


# --- the updater ----------------------------------------------------------------------------

class FakeVenv:
    """The updater's Venv, recording what it was asked, in order."""

    def __init__(self, state, calls, swap_fails=False):
        self.state, self.calls, self.swap_fails = state, calls, swap_fails

    def plan(self, target):
        return {"state": self.state, "from": "a" * 12, "to": "b" * 12}

    def refusal(self, plan, target):
        return f"needs the venv {plan['to']}, not built"

    def swap(self, plan):
        self.calls.append("swap")
        if self.swap_fails:
            raise subprocess.CalledProcessError(1, "mv")

    def unswap(self, plan):
        self.calls.append("unswap")

    def prune(self, plan):
        self.calls.append("prune")
        return [], []


def _update(repos, venv, gate, calls, U=None):
    U = U or _updater()
    rec = U.update(_request(repos), repo=str(repos["work"]), gate=gate, git=_local_git,
                   restart=lambda: calls.append("restart"), unit=lambda: {"MainPID": 100},
                   health=lambda: (200, {}), sleep=lambda s: None, venv=venv)
    return U, rec


def _up(ok=True):
    def wait_for_running(target, pid_before, health, unit, clock, sleep, timeout=90):
        return ok, {"unit": {"MainPID": 200}}, ("" if ok else "the running process loaded another commit")
    return types.SimpleNamespace(OK=0, ci_verdict=lambda repo, target: (0, "CI passed"),
                                 wait_for_running=wait_for_running)


def test_the_updater_refuses_an_unbuilt_venv_before_the_move(repos):
    calls = []
    U = _updater()
    with pytest.raises(U.Refused, match="not built"):
        _update(repos, FakeVenv("unbuilt", calls), _up(), calls, U)
    assert calls == [] and _g(repos["work"], "rev-parse", "HEAD") == repos["shas"][0]


def test_the_updater_swaps_after_the_move_before_the_restart_and_prunes(repos):
    calls = []
    _U, rec = _update(repos, FakeVenv("swap", calls), _up(), calls)
    assert rec["outcome"] == "updated" and calls == ["swap", "restart", "prune"]
    assert "b" * 12 in rec["reason"]


def test_a_rollback_puts_the_link_back_with_the_commit(repos):
    calls = []
    _U, rec = _update(repos, FakeVenv("swap", calls), _up(ok=False), calls)
    assert rec["outcome"] in ("rolled_back", "rollback_failed")
    assert calls[:3] == ["swap", "restart", "unswap"] and "prune" not in calls
    assert _g(repos["work"], "rev-parse", "HEAD") == repos["shas"][0]


def test_a_link_that_cannot_move_puts_the_checkout_back_unrestarted(repos):
    calls = []
    U = _updater()
    with pytest.raises(U.Refused, match="could not be moved"):
        _update(repos, FakeVenv("swap", calls, swap_fails=True), _up(), calls, U)
    assert calls == ["swap"] and _g(repos["work"], "rev-parse", "HEAD") == repos["shas"][0]


def test_the_updaters_venv_runs_as_root_by_absolute_path():
    U = _updater()
    v = U.Venv(types.SimpleNamespace(), "/srv/checkout", "svc")
    assert v.bins["sudo"] == () and all(os.path.isabs(v.bins[k]) for k in ("ln", "mv", "rm", "grep"))
