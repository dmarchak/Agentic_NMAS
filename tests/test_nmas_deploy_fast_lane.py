"""The fast lane (the operator, 2026-11-15, temporary until the operator ends it): "run the tests
for the touched files plus the smoke check, then deploy via nmas-deploy with a --fast-lane flag
that skips the pre-gate and the CI-green requirement. Keep the 02:30-03:30 backup window rule,
the preflight, and 'never on a red smoke' ... Every fast-lane deploy is logged (sha, files, the
tests run), and a one-command revert to the previous deployed sha exists and is tested once."

- **It deploys without asking any verdict**, recording the sha, the files it changed and the
  tests the deploy names, in the deploy record (data/deploy_audit.jsonl).
- **It refuses** with too few words for its tests, and inside the nightly backup window.
- **A red smoke reverts it** to the release it replaced, restarted, said; a green one stands.
- **`--revert` puts back the previous deployed commit**, from the deploy record, asking no
  verdict; with no such deploy recorded it refuses, and it too refuses in the backup window.

Through tests/test_nmas_deploy.py's world: a bare origin, a dev clone and the deployed clone; no
network, no service.
"""
import json
import os

import pytest

from tests.test_nmas_deploy import _git, _run, world  # noqa: F401 (the fixture)

TESTS = "pytest 3 files for the touched modules: 42 passed"
#: The operator's mode file, turned on until far ahead (docs/FASTLANE.md, "Turning it on").
ON = {"by": "the operator", "at": "2026-11-15T00:00:00Z", "until": "2099-01-01T00:00:00Z",
      "why": "a supervised lab window"}


@pytest.fixture(autouse=True)
def mode(tmp_path, monkeypatch):
    """The fast lane on for this file's tests (off by default since 2026-11-18): its mode file
    in the test's own folder, never the person's home (`NMAS_FAST_LANE_FILE`)."""
    path = tmp_path / "fast-lane.json"
    path.write_text(json.dumps(ON), encoding="utf-8")
    monkeypatch.setenv("NMAS_FAST_LANE_FILE", str(path))
    return path


def _record(world):
    with open(os.path.join(world.host, "data", "deploy_audit.jsonl"), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _green(repo, target):
    return True, "SMOKE OK"


def test_it_deploys_with_no_verdict_asked_and_records_the_files_and_the_tests(world, capsys):
    target = world.advance({"app.py": "v = 2\n", "modules/x.py": "y = 1\n"})
    code, restarted, calls = _run(world, {}, extra=("--fast-lane", TESTS), smoke=_green)
    assert code == 0, capsys.readouterr()
    assert not [c for c in calls if "head_sha=" in c], "no CI verdict was asked"
    assert _git(world.host, "rev-parse", "HEAD") == target and restarted
    row = _record(world)[-1]
    assert row["gate"] == "fast-lane" and row["to"] == target and row["from"] == world.base
    assert sorted(row["fast_lane"]["files"]) == ["app.py", "modules/x.py"]
    assert row["fast_lane"]["tests"] == TESTS and row["smoke"]["ok"] is True
    assert "FAST LANE" in capsys.readouterr().out


def test_too_few_words_for_its_tests_is_refused_and_nothing_moves(world, capsys):
    world.advance({"app.py": "v = 2\n"})
    code, restarted, _calls = _run(world, {}, extra=("--fast-lane", "tests passed"),
                                   smoke=_green)
    assert code == 4 and not restarted
    assert _git(world.host, "rev-parse", "HEAD") == world.base
    assert "at least 4 words" in capsys.readouterr().err


def test_inside_the_backup_window_it_is_refused_and_nothing_moves(world, capsys):
    world.advance({"app.py": "v = 2\n"})

    def inside(mod):
        mod.in_backup_window = lambda now: True
        mod.backup_window_words = lambda now: "02:30 to 03:30 America/Denver"
    code, restarted, _calls = _run(world, {}, extra=("--fast-lane", TESTS), smoke=_green,
                                   setup=inside)
    assert code == 4 and not restarted
    assert _git(world.host, "rev-parse", "HEAD") == world.base
    assert "inside the hypervisor's nightly backup window" in capsys.readouterr().err


def test_a_red_smoke_puts_the_previous_release_back(world, capsys):
    world.advance({"app.py": "v = 2\n"})
    code, restarted, _calls = _run(world, {}, extra=("--fast-lane", TESTS),
                                   smoke=lambda repo, target: (False, "SMOKE FAILED: /v2/ 500"))
    assert code == 5, capsys.readouterr()
    assert _git(world.host, "rev-parse", "HEAD") == world.base, "put back"
    assert len(restarted) == 2, "restarted on the new release, then on the one put back"
    row = _record(world)[-1]
    assert row["smoke"]["ok"] is False and row["reverted"]["to"] == world.base
    assert "the smoke check was RED, so it was reverted" in capsys.readouterr().err


def test_a_red_smoke_with_a_swapped_venv_puts_the_venv_and_the_units_back(world, capsys):
    """The correctness review's G7-D4 (2026-11-18): a red smoke's revert reset the checkout
    and restarted the app, but left the venv link on the new release's venv and the ZTP
    responder running the new release's code, and said "reverted … (running again)": a mixed
    version drawn as a rollback done. The revert puts back what the deploy moved: the venv
    link, the app, and each unit that runs the checkout."""
    world.advance({"app.py": "v = 2\n"})
    plan = {"state": "swap", "from": "aaa", "to": "bbb"}
    moved = []

    def venv(mod):
        mod.venv_plan = lambda *a, **k: dict(plan)
        mod.swap_venv = lambda p, *a, **k: moved.append(("swap", p["to"]))
        mod.unswap_venv = lambda p, *a, **k: moved.append(("unswap", p["from"]))
        mod.prune_venvs = lambda keep, *a, **k: ([], [])
    pid = {"n": 300}

    def restart_unit(u):
        moved.append(("restart", u))
        pid["n"] += 1

    def unit_of(u):
        return {"MainPID": pid["n"], "start": "", "load": "loaded"}
    code, restarted, _calls = _run(world, {}, extra=("--fast-lane", TESTS), setup=venv,
                                   units=(restart_unit, unit_of),
                                   smoke=lambda repo, target: (False, "SMOKE FAILED: /v2/ 500"))
    err = capsys.readouterr().err
    assert code == 5, err
    assert _git(world.host, "rev-parse", "HEAD") == world.base, "put back"
    assert moved == [("swap", "bbb"), ("restart", "nmas-ztp-responder.service"),
                     ("unswap", "aaa"), ("restart", "nmas-ztp-responder.service")], moved
    row = _record(world)[-1]
    assert row["reverted"]["venv"] == "aaa", row["reverted"]
    assert any("nmas-ztp-responder.service: restarted" in w
               for w in row["reverted"]["checkout_units"]), row["reverted"]


def test_revert_puts_back_the_previous_deployed_commit_with_no_verdict(world, capsys):
    target = world.advance({"app.py": "v = 2\n"})
    assert _run(world, {}, extra=("--fast-lane", TESTS), smoke=_green)[0] == 0
    assert _git(world.host, "rev-parse", "HEAD") == target
    code, restarted, calls = _run(world, {}, extra=("--revert",))
    assert code == 0, capsys.readouterr()
    assert _git(world.host, "rev-parse", "HEAD") == world.base and restarted
    assert not [c for c in calls if "head_sha=" in c]
    row = _record(world)[-1]
    assert row["gate"] == "revert" and row["from"] == target and row["to"] == world.base


def test_revert_with_no_deploy_recorded_is_refused(world, capsys):
    code, restarted, _calls = _run(world, {}, extra=("--revert",))
    assert code == 4 and not restarted
    assert "nothing to put it back to" in capsys.readouterr().err


class TestOffByDefault:
    """The operator, 2026-11-18: "Turn fastlane off and restore full CI gating" (docs/FASTLANE.md):
    `--fast-lane` deploys only while the operator's mode file says it is on; otherwise it is
    refused before anything moves, naming the file and why. `--revert` is recovery and asks no
    mode. The deploy record carries the mode's words."""

    def _refused(self, world, capsys, why):
        world.advance({"app.py": "v = 2\n"})
        code, restarted, calls = _run(world, {}, extra=("--fast-lane", TESTS), smoke=_green)
        err = capsys.readouterr().err
        assert code == 4 and not restarted, err
        assert _git(world.host, "rev-parse", "HEAD") == world.base
        assert not calls, "refused before asking anything"
        assert "--fast-lane refused: the fast lane is off" in err and why in err, err
        return err

    def test_no_mode_file_is_off(self, world, capsys, mode):
        mode.unlink()
        err = self._refused(world, capsys, "does not exist")
        assert str(mode) in err and "docs/FASTLANE.md" in err

    def test_a_mode_past_its_until_is_off(self, world, capsys, mode):
        mode.write_text(json.dumps(dict(ON, until="2026-11-17T00:00:00Z")), encoding="utf-8")
        self._refused(world, capsys, "it ended at 2026-11-17T00:00:00Z")

    def test_a_mode_naming_no_person_or_reason_is_off(self, world, capsys, mode):
        mode.write_text(json.dumps(dict(ON, by="", why=" ")), encoding="utf-8")
        self._refused(world, capsys, "names no by, why")

    def test_an_unreadable_mode_is_off(self, world, capsys, mode):
        mode.write_text("{not json", encoding="utf-8")
        self._refused(world, capsys, "cannot be read (JSONDecodeError)")

    def test_revert_asks_no_mode(self, world, capsys, mode):
        target = world.advance({"app.py": "v = 2\n"})
        assert _run(world, {}, extra=("--fast-lane", TESTS), smoke=_green)[0] == 0
        mode.unlink()
        code, restarted, _calls = _run(world, {}, extra=("--revert",))
        assert code == 0 and restarted, capsys.readouterr()
        assert _git(world.host, "rev-parse", "HEAD") == world.base != target

    def test_the_record_carries_the_modes_words(self, world, capsys):
        world.advance({"app.py": "v = 2\n"})
        assert _run(world, {}, extra=("--fast-lane", TESTS), smoke=_green)[0] == 0
        assert _record(world)[-1]["fast_lane"]["mode"] == (
            "the fast lane is on until 2099-01-01T00:00:00Z, by the operator: a supervised "
            "lab window")
