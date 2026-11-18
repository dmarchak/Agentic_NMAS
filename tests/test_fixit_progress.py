"""The incident card's live stepper never says "Fixed" over a run that did not pass (the
correctness review's G6 M6, 2026-11-18; `modules/fixit/progress.py` `lines`).

A command plan's run declares ``... verify, rollback, record``. The rollback is bookkeeping
(`progress.HIDDEN`) until it fails, so once verify recorded ``fail`` the next declared step
drawn was ``record``, whose words are "Fixed": "Fixed" with a spinner for the whole rollback,
then "✓ Fixed" once the record step was written, until the job ended. The steps are planted as
a run records them (`command_plan_run._step`: ``{"step", "result", "at"}``), the declared
steps the runner's own (`command_plan_run.STEPS`).
"""
import time

import pytest

from modules.fixit import progress
from modules.nsot import command_plan_run as CR

T = 1794776570


def at(n: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T + n))


#: A run on s5 whose verify failed at its sixth step (12:00:10 in the review's scenario).
FAILED_VERIFY = [{"step": "approve", "result": "ok", "at": at(0)},
                 {"step": "hold", "result": "ok", "at": at(1)},
                 {"step": "read_before", "result": "ok", "at": at(3)},
                 {"step": "preconditions", "result": "ok", "at": at(5)},
                 {"step": "send", "result": "ok", "at": at(7)},
                 {"step": "verify", "result": "fail", "at": at(10)}]


@pytest.mark.parametrize("recorded", [
    FAILED_VERIFY,
    FAILED_VERIFY + [{"step": "rollback", "result": "ok", "at": at(30)}],
    FAILED_VERIFY + [{"step": "rollback", "result": "ok", "at": at(30)},
                     {"step": "record", "result": "ok", "at": at(31)}]],
    ids=["rolling-back", "rolled-back", "recorded"])
def test_a_run_whose_verify_failed_never_shows_fixed(recorded):
    got, _n = progress.lines(CR.STEPS, recorded, device="s5", start=T, ended=False,
                             passed=False)
    assert [s for s in got if s["words"] == "Fixed"] == [], got
    running = [s["key"] for s in got if s["state"] == "running"]
    assert "record" not in running, got


def test_while_it_rolls_back_the_rollback_is_the_running_step():
    got, _n = progress.lines(CR.STEPS, FAILED_VERIFY, device="s5", start=T, ended=False)
    assert [s["key"] for s in got if s["state"] == "running"] == ["rollback"], got


def test_a_run_that_verified_still_shows_fixed():
    passed = [dict(s, result="ok") for s in FAILED_VERIFY]
    got, _n = progress.lines(CR.STEPS, passed, device="s5", start=T, ended=False)
    assert [s["state"] for s in got if s["words"] == "Fixed"] == ["running"], got
