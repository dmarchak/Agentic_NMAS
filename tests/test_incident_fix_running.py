"""A batch's claim is a running heal only while its batch runs (the correctness review's G6 M5,
2026-11-18; `modules/incident_page.py` `fix_running`, `modules/heal/batch.py`
`claimed_by_batch`).

A batch marks each restore's incident ``batch_claim`` when it starts, and only the batch takes
the mark off (the device's outcome recorded, or the batch refused). A batch whose process died
mid-run (a restart, an OOM) left the mark, and `fix_running` read it as a running heal for up
to `batch.UNTAKEN_S` (34 minutes): "Self-healing: restoring <device>", step "starting", the
incident out of Needs attention's people-needed set, with nothing running. The claim counts
only while a batch job of the incident's network runs (`capture_job`, the registry the batch's
own strip reads, `control_strip.newest_batch_job`).

No device, no network: the incident is planted as `fix_running` is handed it.
"""
import threading
import time

from modules import incident_page as IP
from modules.heal import batch as HB
from modules.nsot import capture_job

NET = "fix-running-test"


def found(now: float) -> dict:
    """An open standing incident on r2 that a batch claimed a minute ago, no decision taken."""
    return {"incident": {"id": "hi-0000000000m5", "device": "r2", "state": "standing",
                         "batch_claim": {"at": "", "epoch": now - 60, "by": "Fix all"}},
            "entry": {}, "decisions": []}


def test_a_batch_claim_with_no_live_batch_job_is_not_running():
    now = time.time()
    assert not [j for j in capture_job.card_jobs(now)
                if j["kind"] == HB.KIND and j["list"] == NET and j["state"] == "running"]
    assert HB.claimed_by_batch(found(now)["incident"], now), "the planted claim is a claim"
    assert IP.fix_running(NET, found(now), now) == {}


def test_a_batch_claim_while_its_batch_runs_is_running():
    gate = threading.Event()
    job = capture_job.start(NET, "a batch for the test", "test", lambda _j: gate.wait(30) and {},
                            kind=HB.KIND, page="/v2/?batch={job}#control-strip")
    try:
        now = time.time()
        got = IP.fix_running(NET, found(now), now)
        assert got.get("words") == IP.RESTORING.format(device="r2"), got
    finally:
        gate.set()
        capture_job.wait(job, 30)
