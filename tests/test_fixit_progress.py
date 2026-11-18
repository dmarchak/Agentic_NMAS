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


# ── The investigation's steps and a plan's numbered words (bad52d54 and 00c70e0f; the debt
# pass, 2026-11-18, docs/FAST_LANE_DEBT.md's rows for them) ───────────────────────────────

def test_an_investigation_is_its_trail_done_the_newest_running_and_the_rest_waiting(
        monkeypatch):
    """bad52d54: the running investigation's steps from its own trail
    (`troubleshoot_job.trail`): each said step done with its seconds to the next, its done
    words where it said them; the newest running since it was said; then each of `AI_NEXT`
    not yet reached, waiting. No trail, no steps."""
    from modules import troubleshoot_job as TJ

    trail = [{"doing": "Reading s5…", "done": "Read s5: show interfaces status", "at": T},
             {"doing": "Asking the AI…", "done": "", "at": T + 4},
             {"doing": "Checking the plan is safe to run…", "done": "", "at": T + 19}]
    monkeypatch.setattr(TJ, "trail", lambda network, iid: list(trail))
    got = progress.investigation("Default", "hi-1")
    assert [(s["words"], s["state"], s["took_s"]) for s in got] == [
        ("Read s5: show interfaces status", "done", 4),
        ("Asking the AI", "done", 15),
        ("Checking the plan is safe to run", "running", None),
        ("Plan ready for your approval", "waiting", None)], got
    assert got[2]["since"] == at(19)
    monkeypatch.setattr(TJ, "trail", lambda network, iid: [])
    assert progress.investigation("Default", "hi-1") == []


@pytest.mark.parametrize("label,n,total,key,device,want", [
    ("Sending", 1, 1, "send", "s5", "Sending"),
    ("Sending", 1, 2, "send", "access1", "Sending: step 1 of 2, on access1"),
    ("Closing the session", 2, 2, "close", "r7", "Closing the session: step 2 of 2"),
    ("Sending", 3, 3, "send", "", "Sending: step 3 of 3")])
def test_a_plans_step_is_numbered_only_in_a_plan_of_more_than_one(label, n, total, key,
                                                                  device, want):
    """00c70e0f (the operator, 2026-11-16: never "1. Sending" beside the unnumbered Holding
    and Checks): a plan of one step is not numbered; of more, "<label>: step n of N", its
    device named on the send."""
    assert progress.numbered(label, n, total, key=key, device=device) == want


def test_a_plan_counts_one_step_per_system_it_changes():
    """`systems`: a change on one system is one step, its reads and waits not counted, so a
    host's close then the device's send is two, and two device steps in a row are one."""
    assert progress.systems([("hold",), ("close",), ("send",), ("verify",)]) == 2
    assert progress.systems([("remove",), ("re-add",), ("verify",)]) == 1
    assert progress.systems([("hold",), ("verify",)]) == 0
