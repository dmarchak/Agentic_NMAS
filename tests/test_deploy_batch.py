"""Batch orchestration: drift, the circuit breaker, and full accounting.

Design point 5 requires that a multi-device deploy "never leaves a partial
batch unreported". A partial batch is acceptable *if* every device is accounted
for — which is also why mid-batch drift skips rather than aborts: aborting at
device four leaves three deployed and six untouched, exactly as mixed a state
as skipping one. Abort prevents further change; it restores nothing.

No test here opens a socket: ``deploy_one`` is injected.
"""

import hashlib

import pytest

from modules.nsot import deploy
from modules.nsot.deploy import (
    DEPLOYED, FAILED, REFUSED, SKIPPED_DRIFTED, SKIPPED_NOT_SELECTED, UNATTEMPTED,
    CircuitBreaker, plan_batch, run_batch,
)


class FakeArtifact:
    """Stands in for a RenderArtifact without building a real one."""

    def __init__(self, device, deployable=True, reasons=None):
        self.device = device
        self._deployable = deployable
        self.blocking_reasons = reasons or ([] if deployable else ["unmodelled lines"])

    @property
    def deployable(self):
        return self._deployable


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@pytest.fixture(autouse=True)
def sequential(monkeypatch):
    monkeypatch.setattr(deploy, "max_workers", lambda: 1)


class TestPlanning:
    def test_matching_capture_is_planned(self):
        config = "hostname R1\n"
        plan = plan_batch([FakeArtifact("R1")], {"R1": _hash(config)}, {"R1": config})
        assert [e["artifact"].device for e in plan["to_deploy"]] == ["R1"]
        assert plan["skipped"] == []

    def test_drifted_device_is_skipped_not_aborted(self):
        plan = plan_batch([FakeArtifact("R1"), FakeArtifact("R2")],
                          {"R1": _hash("a"), "R2": _hash("b")},
                          {"R1": "a", "R2": "CHANGED"})
        assert [e["artifact"].device for e in plan["to_deploy"]] == ["R1"]
        drifted = plan["skipped"][0]
        assert drifted["device"] == "R2"
        assert drifted["outcome"] == SKIPPED_DRIFTED

    def test_drift_skip_carries_the_fresh_capture(self):
        """So the operator gets one-click re-preview without another read."""
        plan = plan_batch([FakeArtifact("R2")], {"R2": _hash("b")},
                          {"R2": "CHANGED"})
        assert plan["skipped"][0]["fresh_capture"] == "CHANGED"

    def test_non_deployable_is_refused(self):
        plan = plan_batch([FakeArtifact("R3", deployable=False)],
                          {"R3": _hash("c")}, {"R3": "c"})
        assert plan["to_deploy"] == []
        assert plan["skipped"][0]["outcome"] == REFUSED

    def test_unselected_device_is_recorded(self):
        plan = plan_batch([FakeArtifact("R4")], {}, {"R4": "d"})
        assert plan["skipped"][0]["outcome"] == SKIPPED_NOT_SELECTED

    def test_missing_fresh_capture_fails(self):
        plan = plan_batch([FakeArtifact("R5")], {"R5": _hash("e")}, {})
        assert plan["skipped"][0]["outcome"] == FAILED


class TestFullAccounting:
    def _plan(self, n=9, drifted=(), refused=()):
        artifacts, confirmed, fresh = [], {}, {}
        for i in range(1, n + 1):
            name = f"R{i}"
            artifacts.append(FakeArtifact(name, deployable=name not in refused))
            confirmed[name] = _hash(name)
            fresh[name] = "DRIFTED" if name in drifted else name
        return plan_batch(artifacts, confirmed, fresh)

    def test_every_device_appears_exactly_once(self):
        plan = self._plan(9, drifted={"R4"}, refused={"R7"})
        report = run_batch(plan, lambda e: {"device": e["artifact"].device,
                                            "outcome": DEPLOYED})
        devices = [r["device"] for r in report["results"]]
        assert sorted(devices) == sorted(f"R{i}" for i in range(1, 10))
        assert len(devices) == len(set(devices)), "a device appeared twice"

    def test_totals_add_up(self):
        plan = self._plan(9, drifted={"R4"}, refused={"R7"})
        report = run_batch(plan, lambda e: {"device": e["artifact"].device,
                                            "outcome": DEPLOYED})
        assert report["total"] == 9
        assert len(report["deployed"]) == 7
        assert report["by_outcome"][SKIPPED_DRIFTED] == ["R4"]
        assert report["by_outcome"][REFUSED] == ["R7"]

    def test_partial_batch_is_fully_reported(self):
        plan = self._plan(5)
        def _deploy(entry):
            device = entry["artifact"].device
            if device == "R3":
                return {"device": device, "outcome": FAILED, "stage": "deploy",
                        "reason": "push failed"}
            return {"device": device, "outcome": DEPLOYED}
        report = run_batch(plan, _deploy)
        assert len(report["results"]) == 5
        assert report["by_outcome"][FAILED] == ["R3"]
        assert len(report["deployed"]) == 4

    def test_results_are_sorted_for_stable_display(self):
        report = run_batch(self._plan(3),
                           lambda e: {"device": e["artifact"].device,
                                      "outcome": DEPLOYED})
        assert [r["device"] for r in report["results"]] == ["R1", "R2", "R3"]


class TestCircuitBreakerInBatch:
    def _plan(self, n):
        artifacts, confirmed, fresh = [], {}, {}
        for i in range(1, n + 1):
            artifacts.append(FakeArtifact(f"R{i}"))
            confirmed[f"R{i}"] = _hash(f"R{i}")
            fresh[f"R{i}"] = f"R{i}"
        return plan_batch(artifacts, confirmed, fresh)

    def test_verify_failures_trip_the_breaker(self):
        plan = self._plan(9)
        def _deploy(entry):
            return {"device": entry["artifact"].device, "outcome": FAILED,
                    "stage": "verify", "reason": "neighbours lost"}
        report = run_batch(plan, _deploy, CircuitBreaker(limit=2))
        assert report["breaker_tripped"] is True
        assert len(report["by_outcome"][FAILED]) == 2
        assert len(report["by_outcome"][UNATTEMPTED]) == 7

    def test_unattempted_devices_say_why(self):
        report = run_batch(self._plan(5),
                           lambda e: {"device": e["artifact"].device,
                                      "outcome": FAILED, "stage": "verify"},
                           CircuitBreaker(limit=1))
        unattempted = [r for r in report["results"] if r["outcome"] == UNATTEMPTED]
        assert unattempted
        assert all("verify failure" in r["reason"] for r in unattempted)

    def test_deploy_failures_do_not_trip_it(self):
        """The breaker counts VERIFY failures. A push failure is not systemic."""
        report = run_batch(self._plan(5),
                           lambda e: {"device": e["artifact"].device,
                                      "outcome": FAILED, "stage": "deploy"},
                           CircuitBreaker(limit=2))
        assert report["breaker_tripped"] is False
        assert len(report["by_outcome"][FAILED]) == 5

    def test_drift_does_not_trip_it(self):
        """One drifted device means someone touched a box, not a systemic fault."""
        artifacts, confirmed, fresh = [], {}, {}
        for i in range(1, 6):
            artifacts.append(FakeArtifact(f"R{i}"))
            confirmed[f"R{i}"] = _hash(f"R{i}")
            fresh[f"R{i}"] = "DRIFTED"
        plan = plan_batch(artifacts, confirmed, fresh)
        report = run_batch(plan, lambda e: {"device": e["artifact"].device,
                                            "outcome": DEPLOYED},
                           CircuitBreaker(limit=2))
        assert report["breaker_tripped"] is False
        assert len(report["by_outcome"][SKIPPED_DRIFTED]) == 5

    def test_devices_before_the_trip_still_deploy(self):
        plan = self._plan(6)
        calls = []
        def _deploy(entry):
            device = entry["artifact"].device
            calls.append(device)
            if device in ("R1", "R2"):
                return {"device": device, "outcome": FAILED, "stage": "verify"}
            return {"device": device, "outcome": DEPLOYED}
        report = run_batch(plan, _deploy, CircuitBreaker(limit=2))
        assert calls == ["R1", "R2"], "devices were attempted after the breaker tripped"
        assert len(report["by_outcome"][UNATTEMPTED]) == 4


class TestConcurrency:
    def test_sequential_by_default(self, monkeypatch):
        monkeypatch.setattr(deploy, "max_workers", lambda: 1)
        order = []
        artifacts = [FakeArtifact(f"R{i}") for i in range(1, 4)]
        confirmed = {a.device: _hash(a.device) for a in artifacts}
        fresh = {a.device: a.device for a in artifacts}
        plan = plan_batch(artifacts, confirmed, fresh)
        run_batch(plan, lambda e: order.append(e["artifact"].device) or
                  {"device": e["artifact"].device, "outcome": DEPLOYED})
        assert order == ["R1", "R2", "R3"]

    def test_parallel_still_accounts_for_everyone(self, monkeypatch):
        monkeypatch.setattr(deploy, "max_workers", lambda: 4)
        artifacts = [FakeArtifact(f"R{i}") for i in range(1, 10)]
        confirmed = {a.device: _hash(a.device) for a in artifacts}
        fresh = {a.device: a.device for a in artifacts}
        plan = plan_batch(artifacts, confirmed, fresh)
        report = run_batch(plan, lambda e: {"device": e["artifact"].device,
                                            "outcome": DEPLOYED})
        assert report["total"] == 9
        assert report["workers"] == 4
