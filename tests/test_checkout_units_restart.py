"""C1404: a deploy or an update restarts every long-running unit that runs the checkout's code,
not only the app, and confirms each by identity.

0d's run 2 (2026-10-19): the ZTP responder had started 21 hours before, and ran the code it
started with through a deploy of 0e's responder change; probe-zr6's relayed request was refused
by the old code ("10.255.96.2 holds no reservation the tool wrote") while the same functions in
a fresh process served it. The app said it was deployed. Now:

- the population, by the property: every unit template (deploy/systemd/*.service) that is not a
  oneshot and whose ExecStart runs the checkout's code is in `nmas-deploy`'s CHECKOUT_UNITS, and
  nothing else is (a oneshot starts fresh each run); a planted template is found;
- `restart_checkout_units`: a running unit is restarted and confirmed by its new MainPID; one
  installed and not running is left (its next start loads the checkout); one not installed is
  said; a failed restart, or a MainPID that does not move within the bound, is not ok and names
  the command that fixes it;
- `nmas-deploy` restarts them once the app runs the target, and a unit left on old code is
  UNHEALTHY, never a plain success;
- the Update button's updater does the same through the gate's function, and ends
  `updated_partly` (drawn as a warning) when a unit is not restarted or its installed gate
  predates this.
"""

import os
import re

import pytest

from tests import test_nmas_deploy as ND
from tests import test_update_button as UB
from tests.source_index import tracked
from tests.test_nmas_deploy import world  # noqa: F401 (the fixture)
from tests.test_update_button import repos  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESPONDER = "nmas-ztp-responder.service"


def long_running_checkout_units(paths) -> set:
    """Every template among *paths* that is not a oneshot and runs the checkout's code."""
    out = set()
    for path in paths:
        text = open(path, encoding="utf-8").read()
        kind = re.search(r"^Type=(\S+)", text, re.M)
        if (kind and kind.group(1) == "oneshot") or "@NMAS_CHECKOUT@" not in \
                "".join(re.findall(r"^ExecStart=.*$", text, re.M)):
            continue
        out.add(os.path.basename(path))
    return out


class TestThePopulation:
    def test_checkout_units_are_exactly_the_long_running_checkout_templates(self):
        found = long_running_checkout_units(
            os.path.join(ROOT, p) for p in tracked("deploy/systemd", suffix=".service"))
        assert found, "the scan found no unit: it can no longer see one"
        assert set(ND._script().CHECKOUT_UNITS) == found

    def test_a_planted_template_is_found(self, tmp_path):
        for name, body in (("planted.service", "[Service]\nExecStart=@NMAS_CHECKOUT@/x\n"),
                           ("once.service", "[Service]\nType=oneshot\n"
                                            "ExecStart=@NMAS_CHECKOUT@/y\n"),
                           ("other.service", "[Service]\nExecStart=/usr/bin/z\n")):
            (tmp_path / name).write_text(body)
        assert long_running_checkout_units(
            str(tmp_path / n) for n in ("planted.service", "once.service",
                                        "other.service")) == {"planted.service"}


class _Units:
    """systemd for the checkout's units: each a MainPID, a restart that gives it a new one."""

    def __init__(self, pids, load=None, fail=(), stuck=()):
        self.pids, self.load = dict(pids), dict(load or {})
        self.fail, self.stuck, self.restarted = set(fail), set(stuck), []

    def restart(self, u):
        import subprocess
        if u in self.fail:
            raise subprocess.CalledProcessError(1, "systemctl", stderr="Access denied")
        self.restarted.append(u)
        if u not in self.stuck:
            self.pids[u] += 1000

    def state(self, u):
        return {"MainPID": self.pids.get(u, 0), "start": "",
                "load": self.load.get(u, "loaded" if u in self.pids else "not-found")}


def _clock():
    now = [0.0]

    def clock():
        return now[0]

    def sleep(s):
        now[0] += s
    return clock, sleep


class TestTheRestart:
    def _go(self, units, names=(RESPONDER,)):
        clock, sleep = _clock()
        return ND._script().restart_checkout_units(units.restart, units.state, clock, sleep,
                                                   units=names)

    def test_a_running_unit_is_restarted_and_confirmed_by_its_new_pid(self):
        u = _Units({RESPONDER: 4242})
        ok, words = self._go(u)
        assert ok and u.restarted == [RESPONDER]
        assert words == [f"{RESPONDER}: restarted, pid 4242 -> 5242"]

    def test_one_not_running_is_left_for_its_next_start(self):
        u = _Units({RESPONDER: 0})
        ok, words = self._go(u)
        assert ok and u.restarted == []
        assert "not running, so not restarted; its next start loads this checkout" in words[0]

    def test_one_not_installed_is_said(self):
        u = _Units({})
        ok, words = self._go(u)
        assert ok and u.restarted == [] and "not installed here (not-found)" in words[0]

    def test_a_failed_restart_is_not_ok_and_names_the_fix(self):
        u = _Units({RESPONDER: 4242}, fail={RESPONDER})
        ok, words = self._go(u)
        assert not ok and "NOT restarted (Access denied)" in words[0]
        assert f"run `sudo systemctl restart {RESPONDER}`" in words[0]

    def test_a_pid_that_never_moves_is_not_confirmed(self):
        u = _Units({RESPONDER: 4242}, stuck={RESPONDER})
        ok, words = self._go(u)
        assert not ok and "MainPID is 4242 after 30 s (it was 4242)" in words[0]


class TestTheDeploy:
    def test_the_responder_is_restarted_once_the_app_runs_the_target(self, world, capsys):  # noqa: F811
        sha = world.advance({"app.py": "v = 2\n"})
        u = _Units({RESPONDER: 4242})
        code, restarted, _ = ND._run(world, {sha: ND._run_entry(sha)},
                                     units=(u.restart, u.state))
        out = capsys.readouterr().out
        assert code == 0 and restarted and u.restarted == [RESPONDER]
        assert f"{RESPONDER}: restarted, pid 4242 -> 5242" in out

    def test_a_responder_left_on_old_code_is_unhealthy_not_success(self, world, capsys):  # noqa: F811
        sha = world.advance({"app.py": "v = 2\n"})
        u = _Units({RESPONDER: 4242}, fail={RESPONDER})
        code, restarted, _ = ND._run(world, {sha: ND._run_entry(sha)},
                                     units=(u.restart, u.state))
        out = capsys.readouterr()
        assert code == 5 and restarted
        assert "not every unit that runs the checkout was" in out.out + out.err
        assert f"{RESPONDER}: NOT restarted" in out.out + out.err


class TestTheUpdater:
    def _update(self, repos, gate, units):  # noqa: F811
        U = UB._updater()
        return U.update(UB._request(repos), repo=str(repos["work"]), gate=gate,
                        git=UB._local_git, restart=lambda: None, unit=lambda: {"MainPID": 100},
                        health=lambda: (200, {}), sleep=lambda s: None,
                        restart_unit=units.restart, unit_of=units.state)

    def _gate(self):
        g = UB._gate()
        g.restart_checkout_units = ND._script().restart_checkout_units
        return g

    def test_it_restarts_the_responder_through_the_gate(self, repos):  # noqa: F811
        u = _Units({RESPONDER: 4242})
        rec = self._update(repos, self._gate(), u)
        assert rec["outcome"] == "updated" and u.restarted == [RESPONDER]
        assert f"{RESPONDER}: restarted, pid 4242 -> 5242" in rec["reason"]

    def test_a_responder_not_restarted_is_updated_partly(self, repos):  # noqa: F811
        u = _Units({RESPONDER: 4242}, fail={RESPONDER})
        rec = self._update(repos, self._gate(), u)
        assert rec["outcome"] == "updated_partly"
        assert f"{RESPONDER}: NOT restarted" in rec["reason"]

    def test_a_gate_that_predates_this_is_updated_partly_naming_the_reinstall(self,
                                                                              repos):  # noqa: F811
        u = _Units({RESPONDER: 4242})
        rec = self._update(repos, UB._gate(), u)
        assert rec["outcome"] == "updated_partly" and u.restarted == []
        assert "predates C1404" in rec["reason"] and "re-install it" in rec["reason"]

    def test_the_app_draws_updated_partly_as_a_warning_with_its_words(self):
        from modules import update_op
        assert "updated_partly" in update_op.FINISHED
        assert "C1404" in update_op.OUTCOME_WORDS["updated_partly"]
        text = open(os.path.join(ROOT, "templates", "v2", "_update.html"), encoding="utf-8").read()
        assert "'updated_partly': 'warn'" in text


@pytest.mark.parametrize("outcome", ["updated_partly"])
def test_the_page_never_draws_it_as_a_plain_updated(outcome):
    """The update page's script (stepStates, run in duktape as tests/test_update_button.py runs
    it): the app runs the target, and the updater says a unit did not restart."""
    import dukpy
    target = "t" * 40
    src = open(os.path.join(ROOT, "static", "js", "nmas_update.js"), encoding="utf-8").read()
    status = {"outcome": {"state": "ok", "value": {
        "id": "r1", "outcome": outcome, "step": "wait", "reason": f"{RESPONDER}: NOT restarted"}},
        "outcome_words": {outcome: "updated, but not every unit"}, "pending": []}
    got = dukpy.evaljs([src, "NMAS_UPDATE.stepStates(dukpy.k, dukpy.t, dukpy.i, dukpy.h, "
                             "dukpy.s, dukpy.e, dukpy.o)"],
                       k=UB.KEYS, t=target, i="r1", h={"commit": target}, s=status, e=5, o=900)
    assert got["steps"]["running"]["state"] == "done", "the app does run the target"
    assert got["failed"] is True and got["reload"] is False
    assert "NOT restarted" in got["words"] and not got["words"].startswith("Updated")
