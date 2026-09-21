"""Restore to a baseline.

Restore never pushes directly — it queues per-device approvals. Stale devices
(gone from a NetBox-sourced list) are skipped and **named**: a partial restore
the operator did not know about is worse than a refused one.
"""

import json
import os
import subprocess

import pytest

from modules.nsot import repo as R
from modules.nsot import restore

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git is not available",
)

DEVICES = [
    {"hostname": "R1", "ip": "203.0.113.1", "device_type": "cisco_ios",
     "username": "u", "password": "p", "secret": "s", "role": "router"},
    {"hostname": "R2", "ip": "203.0.113.2", "device_type": "cisco_ios",
     "username": "u", "password": "p", "secret": "s", "role": "router"},
    {"hostname": "R7", "ip": "203.0.113.7", "device_type": "cisco_ios",
     "username": "u", "password": "p", "secret": "s", "role": "router"},
]


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost",
                            "nsot_device_tag_retention": 50,
                        }.get(key, default))
    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.device.get_current_device_list",
                        lambda: ("Lab", str(list_dir / "devices.csv")))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda p=None: DEVICES)

    items = [R.GoldenItem(d["hostname"], f"hostname {d['hostname']}\n", d["ip"],
                          netbox_id=i) for i, d in enumerate(DEVICES, start=1)]
    result = R.save_golden("Lab", items, source="save_all")
    baseline = next(t for t in result["tags"] if t.startswith("baseline/"))
    return {"dir": list_dir, "repo": str(list_dir / "config_repo"),
            "baseline": baseline}


def _mark_stale(lab, ips):
    (lab["dir"] / "source.json").write_text(
        json.dumps({"source": "netbox"}), encoding="utf-8")
    (lab["dir"] / "stale_devices.json").write_text(
        json.dumps({ip: {"hostname": f"dev-{ip}", "reason": "gone"} for ip in ips}),
        encoding="utf-8")


class TestPlanRestore:
    def test_all_devices_restorable_when_none_are_stale(self, lab, monkeypatch):
        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
        plan = restore.plan_restore("Lab", lab["baseline"])
        assert plan["ok"]
        assert {d["hostname"] for d in plan["restorable"]} == {"R1", "R2", "R7"}
        assert plan["skipped"] == []

    def test_stale_devices_are_skipped_and_named(self, lab, monkeypatch):
        monkeypatch.setattr("modules.inventory.is_stale",
                            lambda ip, ln="": ip == "203.0.113.7")
        monkeypatch.setattr("modules.inventory.stale_message",
                            lambda ip, ln="": "R7 is no longer in NetBox")
        plan = restore.plan_restore("Lab", lab["baseline"])
        assert {d["hostname"] for d in plan["restorable"]} == {"R1", "R2"}
        assert [s["hostname"] for s in plan["skipped"]] == ["R7"]
        assert "no longer in NetBox" in plan["skipped"][0]["reason"]

    def test_summary_names_the_skipped_devices(self, lab, monkeypatch):
        """No silent partial restore: the count and the names are both shown."""
        monkeypatch.setattr("modules.inventory.is_stale",
                            lambda ip, ln="": ip in ("203.0.113.7", "203.0.113.2"))
        monkeypatch.setattr("modules.inventory.stale_message", lambda ip, ln="": "gone")
        summary = restore.plan_restore("Lab", lab["baseline"])["summary"]
        assert "Restoring 1 of 3" in summary
        assert "R2" in summary and "R7" in summary

    def test_device_not_in_list_is_skipped(self, lab, monkeypatch):
        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
        monkeypatch.setattr("modules.device.load_saved_devices", lambda p=None: DEVICES[:1])
        plan = restore.plan_restore("Lab", lab["baseline"])
        assert {s["hostname"] for s in plan["skipped"]} == {"R2", "R7"}
        assert all("not in the current device list" in s["reason"]
                   for s in plan["skipped"])

    def test_subset_restore(self, lab, monkeypatch):
        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
        plan = restore.plan_restore("Lab", lab["baseline"], devices=["R1"])
        assert [d["hostname"] for d in plan["restorable"]] == ["R1"]

    def test_unknown_ref_fails_cleanly(self, lab, monkeypatch):
        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
        plan = restore.plan_restore("Lab", "baseline/does-not-exist")
        assert plan["ok"] is False and "No golden configs" in plan["error"]


class TestRestoreGoesThroughTheConfirmedPath:
    """Restore no longer queues whole-config approvals.

    The old path handed the approval executor the entire stored config and let
    it push directly — no confirm hash, no ASCII guard, no provenance, no
    ``error_pattern``, no failure capture, no rollback. It is the one button
    whose label promised the most and whose mechanism had the least behind it.
    """

    def test_execute_restore_is_gone(self):
        """The unguarded entry point must not still be callable."""
        from modules.nsot import restore
        assert not hasattr(restore, "execute_restore")

    def test_build_targets_reads_only_golden_at_the_ref(self, lab):
        """Scope: never templates, bindings or approvals.

        Templates are code. Rolling them back to restore a network would
        silently revert template fixes — including the ones made this week.
        """
        import ast
        import inspect
        import textwrap

        from modules.nsot import restore

        # Code only: the docstring names what must not be touched, and would
        # otherwise trip its own guard.
        tree = ast.parse(textwrap.dedent(inspect.getsource(restore.build_targets)))
        function = tree.body[0]
        if (function.body and isinstance(function.body[0], ast.Expr)
                and isinstance(function.body[0].value, ast.Constant)):
            function.body = function.body[1:]
        code = ast.unparse(function)

        for forbidden in ("templates/", "bindings.yml", ".approvals.json",
                          "templates_repo", "approval"):
            assert forbidden not in code, f"restore must not touch {forbidden}"
        assert "golden_at" in code

    def test_queued_restore_items_are_rejected_not_executed(self, monkeypatch):
        from modules.nsot import restore

        pending = [{"id": "a1", "action_type": "revert_to_golden",
                    "device_hostname": "s4"},
                   {"id": "b2", "action_type": "update_golden_config",
                    "device_hostname": "s3"}]
        resolved = []
        import modules.approval_queue as Q
        monkeypatch.setattr(Q, "get_pending", lambda: pending)
        monkeypatch.setattr(Q, "resolve",
                            lambda entry_id, action: resolved.append((entry_id, action)))

        outcome = restore.invalidate_queued_restores()

        assert resolved == [("a1", "reject")], (
            "only queued restores are rejected, and they are rejected not run")
        assert [r["hostname"] for r in outcome["rejected"]] == ["s4"]
        assert "superseded" in outcome["reason"]

    def test_the_reason_tells_the_operator_what_to_do(self, monkeypatch):
        from modules.nsot import restore
        import modules.approval_queue as Q
        monkeypatch.setattr(Q, "get_pending", lambda: [
            {"id": "a1", "action_type": "revert_to_golden", "device_hostname": "s4"}])
        monkeypatch.setattr(Q, "resolve", lambda entry_id, action: None)
        assert "Baselines panel" in restore.invalidate_queued_restores()["reason"]


class TestBaselineCoverage:
    def test_baseline_tree_contains_every_device(self, lab):
        """Baselines cover everything inherently — the tagged tree has them all."""
        assert set(R.devices_at(lab["repo"], lab["baseline"])) == {"R1", "R2", "R7"}

    def test_stale_device_config_remains_downloadable(self, lab, monkeypatch):
        """Skipping a stale device from restore must not hide its config."""
        monkeypatch.setattr("modules.inventory.is_stale",
                            lambda ip, ln="": ip == "203.0.113.7")
        monkeypatch.setattr("modules.inventory.stale_message", lambda ip, ln="": "gone")
        restore.plan_restore("Lab", lab["baseline"])
        assert R.golden_at(lab["repo"], "R7", lab["baseline"]) is not None
