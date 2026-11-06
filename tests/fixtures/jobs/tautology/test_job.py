"""One tautological test: the job's current answer for one input."""

from job import Tautology, label
from modules.jobs import covers
from modules.jobs.testing import plan_run


@covers("a busy switch is busy", "a quiet switch is ok")
def test_label():
    assert label(5, 3) == "busy"


def test_the_job_runs(ryu):
    ctx = plan_run(Tautology, {"count": 5}, controller=ryu.driver())
    assert ctx.output.lines == ["busy"]
