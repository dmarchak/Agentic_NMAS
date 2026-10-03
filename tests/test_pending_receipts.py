"""Per-device receipts, commit pending (CONCURRENCY_AUDIT R5's open half; the operator,
2026-10-02).

A batch's receipts were written after its golden commit, and the commit after the whole
batch, so a process that ended in between left every device already pushed with no receipt
at all. Now each device's row is written the moment it finishes, marked commit PENDING, and
a completion line fills in the commit after; the file stays append-only.

Measured here:

- a batch whose commit never comes (the process ends, or the commit raises) leaves a
  receipt for each device that finished, pending, with its program; on both apply paths;
- a batch that commits leaves ONE row per device, its id the pending row's, committed;
  a device refused before it started gets its whole row, in the same run;
- every reader draws a pending row as PENDING, never done or green: the result component
  (History's read-back, the Changes tab), the device page's History, the landing's recent
  changes, the in-flight panel;
- Needs attention: a pending receipt whose batch still runs, or whose process ended (the
  interrupted-operation row names it), is no second row; one held by nothing and named by
  nothing is a row of its own; the interrupted row names each pending receipt.
"""

import json
import types

import pytest

from modules.nsot import receipts
from tests.test_deploy_receipts import _sent

LIST = "R5lab"


def _pending(device="r1", run_id="run-1", **over):
    return receipts.pending_row(_sent(device=device, **over), list_name=LIST, action="deploy",
                                actor="person@example.invalid", actor_kind="person",
                                run_id=run_id)


class TestTheFileMergesCompletions:
    def test_a_completion_fills_in_its_row_and_leaves_one_row(self):
        row = _pending()
        receipts.write(LIST, [row])
        got = receipts.read(LIST)["rows"]
        assert [(r["device"], r["commit_state"], r["golden_commit"]) for r in got] == \
            [("r1", "pending", "")]
        final = dict(row, golden_commit="c0ffee", batch_id="batch-9",
                     commit_state=receipts.COMMITTED)
        receipts.write(LIST, [receipts.completion(final, row["id"])])
        (one,) = receipts.read(LIST)["rows"]
        assert (one["id"], one["commit_state"], one["golden_commit"], one["batch_id"]) == \
            (row["id"], "committed", "c0ffee", "batch-9")
        assert one["program"] == row["program"] and one["completed_at"]

    def test_a_row_written_before_commit_states_is_final(self):
        old = {k: v for k, v in _pending().items() if k not in ("commit_state", "run_id")}
        receipts.write(LIST, [dict(old, golden_commit="abc"), dict(old, id="x2",
                                                                    golden_commit="")])
        states = [r["commit_state"] for r in receipts.read(LIST)["rows"]]
        assert states == ["no_golden", "committed"]

    def test_a_completion_naming_no_row_adds_nothing(self, caplog):
        receipts.write(LIST, [_pending(), {"completes": "nosuchrow", "commit_state": "committed",
                                           "golden_commit": "c", "at": "x", "batch_id": ""}])
        rows = receipts.read(LIST)["rows"]
        assert len(rows) == 1 and receipts.is_pending(rows[0])
        assert "nosuchrow" in caplog.text


class _Apply:
    """`/deploy/apply` for s4, through the real route, with the device and the commit faked."""

    @staticmethod
    def run(mp, deploy_one, commit):
        from tests.test_deploy_receipts import TestTheApplyWritesIt

        return TestTheApplyWritesIt()._apply(mp, deploy_one, commit=commit)


def _deployed(entry, list_name, device_rows, authorise=None, source_ref="", **_kw):
    return _sent(device=entry["artifact"].device)


class TestTheApplyWritesEachDeviceAsItFinishes:
    def test_a_commit_that_never_comes_leaves_the_pushed_device_pending(self, monkeypatch):
        def commit(*_a, **_k):
            raise RuntimeError("the process ended here")

        _plan, out = _Apply.run(monkeypatch, _deployed, commit)
        assert out["ok"] is False, out          # the route answers the error, after the push
        rows = receipts.read("Default")["rows"]
        assert [(r["device"], r["commit_state"], r["sent"]) for r in rows] == \
            [("s4", "pending", True)], "the device was pushed and its receipt must say so"
        assert rows[0]["program_lines"] == len(_sent()["commands"]) and rows[0]["run_id"]

    def test_a_batch_that_commits_leaves_one_committed_row_per_device(self, monkeypatch):
        written = []
        real = receipts.write
        monkeypatch.setattr(receipts, "write",
                            lambda lst, rows: written.append([dict(r) for r in rows])
                            or real(lst, rows))
        _plan, out = _Apply.run(monkeypatch, _deployed,
                                lambda *a, **k: {"commit": "c0ffee", "batch_id": "batch-9",
                                                 "devices": ["s4"]})
        assert [len(w) for w in written] == [1, 1], "the row as it finished, then its completion"
        assert written[0][0]["commit_state"] == "pending"
        assert written[1][0]["completes"] == written[0][0]["id"]
        (row,) = receipts.read(out["list"])["rows"]
        assert (row["id"], row["commit_state"], row["golden_commit"]) == \
            (written[0][0]["id"], "committed", "c0ffee")
        # The result is drawn from the final rows: committed, so never pending.
        (target,) = out["result"]["happened"]["targets"]
        assert "PENDING" not in target["words"]
        assert out["result"]["happened"]["summary"].startswith("1 of 1")

    def test_the_restore_path_writes_each_device_as_it_finishes(self, monkeypatch):
        import app as A
        import routes.deploy as rd
        from modules.nsot import deploy as D

        target = types.SimpleNamespace(device="s4", captured="", device_row={})
        monkeypatch.setattr(D, "plan_batch", lambda accepted, *_a: {
            "to_deploy": [{"artifact": t} for t in accepted], "skipped": []})
        monkeypatch.setattr(rd, "_deploy_one", _deployed)

        def commit(*_a, **_k):
            raise RuntimeError("the process ended here")

        monkeypatch.setattr(rd, "_commit_batch_golden", commit)
        with A.app.test_request_context("/golden/reapply", method="POST"):
            with pytest.raises(RuntimeError):
                rd.run_targets("Default", [target], {"confirmations": {"s4": "h"}},
                               source_ref="golden/s4/1")
        (row,) = receipts.read("Default")["rows"]
        assert (row["device"], row["action"], row["commit_state"]) == ("s4", "restore", "pending")

    def test_a_refusal_shares_the_run_of_the_devices_that_finished(self, monkeypatch):
        import routes.deploy as rd

        record, pending = rd._pending_receipts("Default", "deploy", {}, {},
                                               actor="p@example.invalid", actor_kind="person")
        record(_sent(device="r1"))
        report = {"results": [_sent(device="r1"),
                              {"device": "r2", "outcome": "refused", "reason": "busy"}],
                  "golden": {}}
        rd._write_receipts("Default", report, "deploy", {}, {}, actor="p@example.invalid",
                           actor_kind="person", pending=pending)
        rows = receipts.read("Default")["rows"]
        assert {r["device"]: r["run_id"] for r in rows} == {"r1": pending["run_id"],
                                                          "r2": pending["run_id"]}
        assert {r["device"]: r["commit_state"] for r in rows} == {"r1": "no_golden",
                                                                "r2": "no_golden"}
        from modules.preview_confirm import receipt_history
        assert len(receipt_history(rows)) == 1, "one batch, though it committed nothing"
        # Each row keeps the time its own device finished; the run still groups them.
        apart = [dict(rows[0], at="2026-10-02T10:00:00Z"), dict(rows[1], at="2026-10-02T10:05:00Z")]
        assert len(receipt_history(apart)) == 1

    def test_the_running_stepper_says_the_record_is_not_committed_yet(self, monkeypatch):
        from modules import deploy_job
        from modules.nsot import capture_job

        state = {"state": "running"}
        monkeypatch.setattr(capture_job, "get", lambda _j: dict(state))
        monkeypatch.setitem(deploy_job._progress, "j1", {
            "order": ["r1"], "done": {"r1": {"outcome": "deployed", "reason": "", "took_s": 1}},
            "current": "", "started": {}})
        (step,) = deploy_job.state("j1")["steps"]
        assert step["words"] == "done; its record is committed when the batch ends"
        state["state"] = "done"
        assert deploy_job.state("j1")["steps"][0]["words"] == "done"


class TestEveryReaderDrawsPending:
    def test_the_result_component_never_says_done(self):
        from modules.nsot.deploy import command_fingerprint
        from modules.preview_confirm import operation_result, result_level
        from tests.test_deploy_receipts import AUTHORISED, PROGRAM

        row = receipts.pending_row(_sent(device="r1"), list_name=LIST, action="deploy",
                                   actor="person@example.invalid", actor_kind="person",
                                   command_hashes={"r1": command_fingerprint(PROGRAM, AUTHORISED)},
                                   run_id="run-1")
        # The same row, its commit recorded, is clean: only the pending state separates them.
        assert result_level([dict(row, commit_state="committed")], receipt_ok=True) == "success"
        assert result_level([row], receipt_ok=True) == "partial"
        res = operation_result([row], {"golden": {}}, {"ok": True, "written": 1}, "deploy")
        (target,) = res["happened"]["targets"]
        assert target["words"].startswith("sent; commit PENDING"), target["words"]
        assert "done" not in target["words"]
        assert any(d["kind"] == "commit_pending" for d in res["did_not"]["items"])
        assert res["happened"]["summary"].startswith("0 of 1")

    def test_the_device_history_draws_it_pending_and_never_green(self, monkeypatch):
        from modules import device_page

        receipts.write("Default", [dict(_pending(device="s4"), list="Default")])
        ref = types.SimpleNamespace(name="Default", repo_dir="/nonexistent")
        h = device_page.history(ref, {"hostname": "s4"})
        (e,) = [e for e in h["events"] if e["kind"] == "receipt"]
        assert e["pending"] is True and "commit PENDING" in e["what"]

        from flask import render_template

        import app as A
        with A.app.test_request_context("/"):
            html = render_template("v2/_history.html", h=h,
                                   device={"hostname": "s4"})
        line = html[html.index("tl-line"):html.index("commit PENDING")]
        assert "badge-warn" in line and "badge-ok" not in line

    def test_the_landing_marks_it(self, monkeypatch):
        from tests import payload_providers as P

        receipts.write("Default", [_pending(device="s4")])
        html = P._client().get("/v2/").get_data(as_text=True)
        recent = html[html.index("Recent changes"):]
        assert "commit pending" in recent and "badge-warn" in recent

    def test_the_in_flight_panel_carries_and_draws_it(self):
        import dukpy

        from tests import payload_providers as P
        from tests.payload_render import shipped

        receipts.write("Default", [_pending(device="s4")])
        d = P._client().get("/operations/in_flight?list_name=Default").get_json()
        (r,) = d["recent"]
        assert r["commit_state"] == "pending"
        html = dukpy.evaljs("var window = {}; var document = {addEventListener: function () {},"
                            " getElementById: function () { return null; }};\n"
                            + shipped("nmas_in_flight.js")
                            + f"\nwindow.inFlightPanelHtml({json.dumps(d)}, {{}})")
        assert 'data-commit-state="pending"' in html


@pytest.fixture
def ops():
    from modules.nsot import device_ops as D
    yield D
    for host in ("r1", "r2", "r3"):
        while D.holder(LIST, host) and D._held.get((LIST.lower(), host)):
            D.release(LIST, host)


@pytest.fixture
def own_store(tmp_path, monkeypatch):
    """A data directory of this test's own. The process's store is shared by every test it
    runs, and test_interrupted_operations leaves dead holds on r1 and r2 of the same list:
    after it, "named by nothing" was false (CI #333, reproduced in one process)."""
    from modules import config
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))


@pytest.mark.usefixtures("own_store")
class TestNeedsAttention:
    def _deploys(self, monkeypatch):
        from modules import attention

        monkeypatch.setattr("modules.config.get_current_list_name", lambda: LIST)
        return attention.deploy_source()

    def test_pending_while_its_batch_runs_is_no_row_and_not_clean(self, monkeypatch, ops):
        receipts.write(LIST, [_pending(device="r1")])
        ops.acquire(LIST, "r1", "deploy", "person@example.invalid")
        try:
            got = self._deploys(monkeypatch)
        finally:
            ops.release(LIST, "r1")
        assert got["rows"] == []
        assert "0 clean, 1 commit PENDING" in got["checked"], got["checked"]

    def test_pending_named_by_nothing_is_a_row(self, monkeypatch):
        receipts.write(LIST, [_pending(device="r1")])
        (row,) = self._deploys(monkeypatch)["rows"]
        assert "commit PENDING" in row["what"] and "never completed" in row["cause"]
        assert row["level"] == "danger", "a program was sent"

    def test_the_interrupted_row_names_the_pending_receipts(self, monkeypatch, tmp_path, ops):
        from modules import attention
        from tests.test_interrupted_operations import _die_holding

        pid = _die_holding(tmp_path, ["r1", "r2"], step="push")
        receipts.write(LIST, [_pending(device="r1")])
        (row,) = [r for r in attention.interrupted_source()["rows"] if f"|{pid}|" in r["id"]]
        assert row["operands"]["pending_receipts"] == ["r1"]
        assert "r1 finished before it ended" in row["cause"]
        assert "What reached r2" in row["cause"] and "What reached r1" not in row["cause"]
        assert self._deploys(monkeypatch)["rows"] == [], "named once, by the interrupted row"
