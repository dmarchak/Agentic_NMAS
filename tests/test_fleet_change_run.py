"""Board FC phase 2 (d), PHASE8_PLAN 22.2 (3) and (4): a layer change's approval and its run
(`fleet_change.approve`, `batches_of`, `run_batches`, `run_start`), on r2's real config and
committed intent (`tests.test_capture.build_capture_lab`), r2's row tagged. THE apply
(`routes.deploy.apply_batch`) is replaced by a recorder here: no test reaches a device.

- **The approval** recomputes the plan under the lock: the confirmed hash commits the layer's
  file as ONE commit (`Source: fleet-change`, the actor, the plan's hash); another hash, or no
  summary or reason, commits nothing.
- **The run's order** is the canary alone, then batches of the size asked.
- **The first failed device stops the run**, the rest unattempted, naming it; a device whose
  program is not the one approved stops the run before anything is sent to it.
- **Pause after the canary** ends the job paused at the next batch; Go on runs the rest.
"""

import os
import subprocess

import pytest

from modules.nsot import capture_job
from modules.nsot import fleet_change as F
from tests.test_fleet_change_plan import NTP, _head, lab, r2  # noqa: F401 (the fixtures)


def _approve(**kw):
    plan = F.plan_layer("Lab", "tag-blind-lab", NTP)
    assert plan["ok"], plan["error"]
    args = dict(summary="Lab NTP server", reason="the lab's time source",
                actor="op@example.com")
    args.update(kw)
    return plan, F.approve("Lab", "tag-blind-lab", NTP, kw.pop("hash", plan["hash"]),
                           **{k: v for k, v in args.items() if k != "hash"})


class TestTheApproval:
    def test_the_confirmed_hash_commits_the_layer_once(self, r2):  # noqa: F811
        head = _head(r2["repo"])
        plan, got = _approve()
        assert got["ok"], got["error"]
        log = subprocess.run(["git", "-C", r2["repo"], "log", "--format=%B", f"{head}..HEAD"],
                             capture_output=True, text=True, check=True).stdout
        assert log.count("Lab NTP server") == 1, "one commit"
        assert "Source: fleet-change" in log and "op@example.com" in log
        assert plan["hash"] in log
        shown = subprocess.run(["git", "-C", r2["repo"], "show", "HEAD:layers/tag-blind-lab.yml"],
                               capture_output=True, text=True, check=True).stdout
        assert "192.0.2.123" in shown

    def test_another_hash_commits_nothing(self, r2):  # noqa: F811
        head = _head(r2["repo"])
        _plan, got = _approve(hash="0" * 64)
        assert not got["ok"] and "the plan moved since you read it" in got["error"], got
        assert _head(r2["repo"]) == head
        assert not os.path.exists(os.path.join(r2["repo"], "layers", "tag-blind-lab.yml"))

    @pytest.mark.parametrize("field", ["summary", "reason"])
    def test_no_summary_or_reason_commits_nothing(self, r2, field):  # noqa: F811
        head = _head(r2["repo"])
        _plan, got = _approve(**{field: " "})
        assert not got["ok"] and field in got["error"] and _head(r2["repo"]) == head


def test_the_order_is_the_canary_then_batches():
    assert F.batches_of(["r2", "r3", "r4", "r6"], "r3", 2) == [["r3"], ["r2", "r4"], ["r6"]]
    assert F.batches_of(["r2", "r3"], "r2", 0) == [["r2"], ["r3"]]


@pytest.fixture
def sent(monkeypatch):
    """`apply_batch` recorded: each call's devices; a device in `fail` does not verify."""
    import routes.deploy as rd
    from modules.nsot.deploy import DEPLOYED
    got = {"calls": [], "fail": set(), "stop_at_first": []}

    def apply_batch(list_name, confirmations, command_hashes, **kw):
        got["calls"].append(list(confirmations))
        got["stop_at_first"].append(kw.get("stop_at_first"))
        return {"results": [{"device": d, "outcome": "failed" if d in got["fail"] else DEPLOYED,
                             "verify": {"ok": d not in got["fail"]}} for d in confirmations]}
    monkeypatch.setattr(rd, "apply_batch", apply_batch)
    return got


def _plan_of(hosts, monkeypatch, moved=()):
    """A plan of *hosts* whose programs `plan_devices` gives as approved (or not, *moved*)."""
    import routes.deploy as rd
    monkeypatch.setattr(rd, "plan_devices", lambda ln, batch: [
        {"device": d, "capture_hash": f"c-{d}",
         "command_hash": ("moved" if d in moved else f"h-{d}")} for d in batch])
    return {"layer": {"label": "tag blind-lab"},
            "devices": [{"device": d, "command_hash": f"h-{d}"} for d in hosts]}


class TestTheRun:
    def test_the_first_failed_device_stops_it(self, sent, monkeypatch):
        plan = _plan_of(["r2", "r3", "r4"], monkeypatch)
        sent["fail"] = {"r3"}
        got = F.run_batches("Lab", plan, [["r2"], ["r3"], ["r4"]], actor="op",
                            actor_kind="person")
        assert sent["calls"] == [["r2"], ["r3"]], "r4 is never sent"
        assert all(sent["stop_at_first"]), "every batch stops at its first failure"
        assert got["stopped"] == "r3 did not deploy and verify"
        assert [r["outcome"] for r in got["results"]][-1] == "unattempted"

    def test_a_program_not_the_approved_one_stops_it_before_sending(self, sent, monkeypatch):
        plan = _plan_of(["r2", "r3"], monkeypatch, moved=("r3",))
        got = F.run_batches("Lab", plan, [["r2"], ["r3"]], actor="op", actor_kind="person")
        assert sent["calls"] == [["r2"]], "r3's moved program is never sent"
        assert "r3's program is not the one approved" in got["stopped"]

    def test_pause_after_the_canary_then_go_on(self, sent, monkeypatch):
        plan = _plan_of(["r2", "r3", "r4"], monkeypatch)
        batches = [["r2"], ["r3"], ["r4"]]
        job = F.run_start("Lab", plan, "abc", batches, after_canary="pause", actor="op",
                          actor_kind="person")
        assert capture_job.wait(job, 10)
        first = capture_job.get(job)["payload"]
        assert first["state"] == "paused" and first["next"] == 1 and sent["calls"] == [["r2"]]
        job = F.run_start("Lab", plan, "abc", batches, after_canary="pause", actor="op",
                          actor_kind="person", start_at=first["next"])
        assert capture_job.wait(job, 10)
        rest = capture_job.get(job)["payload"]
        assert rest["state"] == "done" and sent["calls"] == [["r2"], ["r3"], ["r4"]]

    def test_go_runs_every_batch_after_the_canary(self, sent, monkeypatch):
        plan = _plan_of(["r2", "r3"], monkeypatch)
        job = F.run_start("Lab", plan, "abc", [["r2"], ["r3"]], after_canary="go", actor="op",
                          actor_kind="person")
        assert capture_job.wait(job, 10)
        assert capture_job.get(job)["payload"]["state"] == "done"
        assert sent["calls"] == [["r2"], ["r3"]]
