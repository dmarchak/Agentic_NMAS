"""A deploy batch's running row says what its device's pipeline is doing NOW (`deploy_job.state`,
`_doing`; C2650).

C2650: CI's coverage ratchet failed now and then on `modules/deploy_job.py` (#1505, #1520),
one of its eight functions read as covered by no unit test. The function was `_doing`
(measured 2026-11-07 from #1520's and #1519's coverage reports: `_doing` unit 0 in the red
run, 1 in the green). It runs only when a batch's state is read while a device is running,
which the unit suite reached only by the timing of tests that poll a live job. This file reaches
it deterministically, and holds what the running row says.
"""

import time

import pytest

from modules import deploy_job, pipeline


@pytest.fixture
def running(monkeypatch):
    """A batch of two devices, the first running, the second not reached yet."""
    job = "job-c2650"
    monkeypatch.setattr("modules.nsot.capture_job.get",
                        lambda job_id: {"state": "running", "list": "Default"}
                        if job_id == job else None)
    monkeypatch.setitem(deploy_job._progress, job, {
        "order": ["edge1", "edge2"], "done": {}, "current": "edge1",
        "started": {"edge1": time.time() - 5}, "scope": ""})
    return job


def _a_stage_with_words():
    """A stage the pipeline names, with the words its running row says (read from the
    pipeline's own table, never typed here)."""
    for name in pipeline.STAGE_NAMES:
        if pipeline.stage_doing(name):
            return name, pipeline.stage_doing(name)
    raise AssertionError("no pipeline stage has running words")


def test_the_running_row_says_what_its_pipeline_is_doing(running, monkeypatch):
    step, words = _a_stage_with_words()
    monkeypatch.setattr("modules.nsot.device_ops.holder",
                        lambda list_name, host: {"progress": {"step": step}}
                        if (list_name, host) == ("Default", "edge1") else None)
    steps = deploy_job.state(running)["steps"]
    assert steps[0]["state"] == "running" and steps[0]["doing"] == words != ""
    assert steps[1] == {"device": "edge2", "state": "pending"}


def test_a_hold_with_no_stage_noted_yet_says_nothing(running, monkeypatch):
    monkeypatch.setattr("modules.nsot.device_ops.holder", lambda list_name, host: {})
    assert deploy_job.state(running)["steps"][0]["doing"] == ""


def test_a_hold_that_cannot_be_read_says_nothing_never_raises(running, monkeypatch):
    def unreadable(list_name, host):
        raise OSError("the hold store is unreadable")

    monkeypatch.setattr("modules.nsot.device_ops.holder", unreadable)
    assert deploy_job.state(running)["steps"][0]["doing"] == ""
