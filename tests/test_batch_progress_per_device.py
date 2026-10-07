"""Each device of a batch shows its OWN state (C446; the operator, 2026-10-04).

s3 and s4, deployed as one batch, both read "for 2 min; now: reading the device after the
change (26 s)" while the batch ran them one at a time. A batch holds every device from the
start, and `device_ops.note(step)` wrote each step to every device the thread held. Now a
device waits its turn, shows its own steps while it runs, and is done with its outcome;
the others are untouched by its steps. Driven through the real holds and `run_batch`, with
`deploy_one` noting the pipeline's own steps, sequentially and on worker threads.
"""

from types import SimpleNamespace

import pytest

from modules import config
from modules.nsot import deploy as DEP
from modules.nsot import device_ops as D

LIST = "Default"


@pytest.fixture
def held(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(D, "_announce_progress", lambda: None)
    monkeypatch.setattr(D, "_announce_released", lambda: None)
    got, busy = D.acquire_many(LIST, ["s4", "s3"], "deploy", "op@example.invalid")
    assert got == ["s4", "s3"] and busy == []
    yield
    D.release_many(LIST, ["s4", "s3"])


def _steps():
    return {r["device"]: r["step"] for r in D.in_flight(LIST)}


def _plan(*devices):
    return {"to_deploy": [{"artifact": SimpleNamespace(device=d)} for d in devices],
            "skipped": []}


def test_each_device_shows_its_own_state_in_turn(held):
    seen = []

    def deploy_one(entry):
        device = entry["artifact"].device
        D.note("post_snapshot")                     # as the pipeline notes its stage
        seen.append((device, _steps()))
        return {"device": device, "outcome": DEP.DEPLOYED, "verified": True}

    DEP.run_batch(_plan("s4", "s3"), deploy_one, sequential=True, list_name="Lab")
    assert seen == [("s4", {"s4": "post_snapshot", "s3": D.WAITING}),
                    ("s3", {"s4": "done: deployed", "s3": "post_snapshot"})], seen
    assert _steps() == {"s4": "done: deployed", "s3": "done: deployed"}


def test_a_device_the_breaker_stopped_says_so(held, monkeypatch):
    def deploy_one(entry):
        return {"device": entry["artifact"].device, "outcome": DEP.FAILED,
                "verified": False}

    breaker = DEP.CircuitBreaker(list_name="Lab")
    monkeypatch.setattr(breaker, "counts", lambda outcome: True)
    monkeypatch.setattr(breaker, "record_failure", lambda device: None)
    monkeypatch.setattr(type(breaker), "is_tripped", property(lambda self: True))
    DEP.run_batch(_plan("s4", "s3"), deploy_one, breaker=breaker, sequential=True,
                  list_name="Lab")
    assert all(s.startswith("not attempted") for s in _steps().values()), _steps()


def test_on_worker_threads_each_step_reaches_its_own_device(held, monkeypatch):
    monkeypatch.setattr(DEP, "max_workers", lambda list_name: 2)
    seen = {}

    def deploy_one(entry):
        device = entry["artifact"].device
        D.note(f"deploy-{device}")
        seen[device] = _steps()[device]
        return {"device": device, "outcome": DEP.DEPLOYED, "verified": True}

    DEP.run_batch(_plan("s4", "s3"), deploy_one, list_name="Lab")
    assert seen == {"s4": "deploy-s4", "s3": "deploy-s3"}, seen


def test_a_single_device_operation_still_notes_without_naming_it(held):
    D.release_many(LIST, ["s3"])
    D.note("verify")
    assert _steps() == {"s4": "verify"}
    D.acquire(LIST, "s3", "deploy", "op@example.invalid")
