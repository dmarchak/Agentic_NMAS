"""C326 (2026-10-02): an approved revert ended REJECTED, with no person and no reason.

Approving a queued revert hands it to the confirmed restore (`_exec_revert_golden`), and the
restore's apply then called `invalidate_queued_restores()`, which rejected every pending revert
on the list: the one being acted on (so `mark_done` failed, "already rejected") and every
other device's. Written when the old executor pushed whole-config text; that executor is gone,
so the rejection only destroyed records. The route tests stubbed it out, which is why nothing
saw it.

Through the REAL queue and the REAL /golden/restore/apply route, as the harness's verified
person; only the device work (`build_targets`, `run_targets`) is stubbed, as a success.
"""

import pytest

from tests.test_approval_responses_masked import queue  # noqa: F401 (the fixture)


@pytest.fixture
def restored(queue, monkeypatch):
    from modules.nsot.deploy import DEPLOYED

    monkeypatch.setattr("modules.nsot.restore.build_targets", lambda *a, **k: ([object()], []))
    monkeypatch.setattr("routes.deploy.run_targets", lambda *a, **k: {
        "results": [{"device": "r2", "outcome": DEPLOYED}]})
    return queue


def _entry(entry_id):
    from modules.approval_queue import get_all
    return next(e for e in get_all(200) if e["id"] == entry_id)


class TestTheApprovedRevertCloses:
    def test_approve_then_restore_closes_it_as_approved_by_the_person(self, restored):
        from tests.conftest import TEST_PERSON

        entry_id = restored["add"]("revert_to_golden")
        r = restored["client"].post(f"/ai/approvals/{entry_id}/approve")
        assert r.status_code == 200 and r.get_json()["execution"]["restore"]["approval_id"] == entry_id
        assert _entry(entry_id)["status"] == "pending"          # awaiting the confirm
        out = restored["client"].post("/golden/restore/apply", json={
            "ref": "HEAD", "confirmations": {"r2": "h"}, "approval_id": entry_id}).get_json()
        assert out["approval_closed"] is True, out
        e = _entry(entry_id)
        assert e["status"] == "approved", e
        assert e["resolved_by"] == TEST_PERSON, e
        assert "Re-applied HEAD to r2" in e["context"]

    def test_a_restore_leaves_another_devices_pending_revert_alone(self, restored, monkeypatch):
        from modules import approval_queue

        other = approval_queue.add_approval("revert_to_golden", "drift on s4", "203.0.113.24",
                                            "s4", "", {}, "test")
        other = other["id"] if isinstance(other, dict) else other
        restored["client"].post("/golden/restore/apply", json={
            "ref": "HEAD", "confirmations": {"r2": "h"}})
        assert _entry(other)["status"] == "pending", _entry(other)
