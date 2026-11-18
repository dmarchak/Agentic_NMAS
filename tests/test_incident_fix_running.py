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


# ── fix_running's other states, and the grace's person (ee7682ba, C3862 and C3863; the debt
# pass, 2026-11-18, docs/FAST_LANE_DEBT.md's row for ee7682ba) ─────────────────────────────

def taken(did="hd-00000000a1") -> dict:
    """An open incident on r2 whose heal decision is taken and not yet applied."""
    return {"incident": {"id": "hi-0000000000a1", "device": "r2", "state": "standing"},
            "entry": {}, "decisions": [{"id": did, "outcome": "heal", "taken": {"by": "t"}}]}


def test_the_acts_mark_held_is_running_and_released_is_not(tmp_path, monkeypatch):
    """Its act's mark held (taken before the decision, in any process) is a running heal,
    "starting" until its job's step is known; the mark released, nothing runs."""
    from modules.heal import interrupted

    monkeypatch.setattr("modules.heal.incidents._dir", lambda network: str(tmp_path))
    f = taken()
    assert IP.fix_running(NET, f) == {}, "no mark: nothing runs"
    interrupted.hold(NET, "hd-00000000a1", "r2", "the test")
    try:
        got = IP.fix_running(NET, f)
        assert (got["words"], got["step"], got["decision"]) == (
            IP.RESTORING.format(device="r2"), IP.STARTING, "hd-00000000a1"), got
        applied = dict(f, decisions=[dict(f["decisions"][0], applied={"outcome": "healed"})])
        assert IP.fix_running(NET, applied) == {}, "an applied decision's mark is no act"
    finally:
        interrupted.release(NET, "hd-00000000a1")
    assert IP.fix_running(NET, f) == {}


def test_its_step_log_entry_applying_is_running_with_its_newest_step_even_closed():
    """An entry still applying (its act's rows, no ``record`` yet) is a running heal, its step
    the act's newest recorded one, whatever the incident's state; done, it is not."""
    from modules import run_stepper
    from modules.heal import act as A

    steps = [{"row": "started", "decision": "hd-00000000b2", "step": "take", "result": "ok"},
             {"row": "act", "decision": "hd-00000000b2", "step": "stops", "result": "ok"}]
    f = {"incident": {"id": "hi-0000000000b2", "device": "r2", "state": "closed"},
         "entry": {"state": "applying", "device": "r2", "steps": steps}, "decisions": []}
    got = IP.fix_running(NET, f)
    want = run_stepper.current_words(A.STEPS, steps,
                                     run_stepper.labels_for(A.STEP_LABELS, device="r2"))
    assert want and (got["step"], got["decision"]) == (want, "hd-00000000b2"), got
    done = dict(f, entry=dict(f["entry"], state="done"))
    assert IP.fix_running(NET, done) == {}


def test_the_grace_names_its_person_never_the_attributions_sentence():
    """C3863: a person said as a person, with where the line says they were; an old grace
    record's sentence read back; no account, nothing. IPv4, IPv6 and a console line."""
    from modules.heal.attribution import person_said

    assert person_said({"user": "lab", "line": "vty0", "address": "192.0.2.7"}) == \
        "lab (vty0, from 192.0.2.7)"
    assert person_said({"user": "lab", "line": "vty0", "address": "2001:db8::7"}) == \
        "lab (vty0, from 2001:db8::7)"
    assert person_said({"person": "the line names the account lab on vty0 from 2001:db8::7"}) \
        == "lab (vty0, from 2001:db8::7)"
    assert person_said({"words": "the line names the account alice on console"}) == \
        "alice (console)"
    assert person_said({"words": "made on the console, no account named"}) == ""
