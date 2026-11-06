"""A read job whose one test is tautological, a planted case of the job gate's tests
(tests/test_job_gate.py, T23): the test asserts the job's current answer for one input, so it
passes, and the mutation step finds what it never checked."""

from modules.jobs import Job, JobInputs, JobMeta, Scope


def label(count, busy):
    return "busy" if count > busy else "ok"


class Tautology(Job):
    meta = JobMeta(name="tautology", version="1.0.0",
                   summary="Whether a switch is busy.",
                   permission="read", scope=Scope(object_types=["dcim.device"]))

    class Inputs(JobInputs):
        count: int

    def run(self, ctx, inputs):
        ctx.output.log(label(inputs.count, 3))
