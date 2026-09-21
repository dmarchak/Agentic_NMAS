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

    def test_build_targets_reads_through_a_scoped_source(self, lab):
        """The bound is the object, not the author's care.

        A docstring and an AST scan guard one function. A second restore path
        would read whatever it liked and inherit nothing — and item 2's intent
        restore is already scheduled.
        """
        import inspect
        from modules.nsot import restore

        source = inspect.getsource(restore.build_targets)
        assert "RefSource(" in source
        assert "golden_at(" not in source, "bypasses the scoped source"
        assert "devices_at(" not in source, "bypasses the scoped source"

    def test_the_scoped_source_refuses_tooling_paths(self):
        from modules.nsot.repo import RefSource, ScopeRefused

        src = RefSource("/nonexistent", "HEAD")
        for path in ("templates/cisco_ios/base.j2", "templates/bindings.yml",
                     "templates/.approvals.json", ".nsot/manifest.json"):
            with pytest.raises(ScopeRefused):
                src.read(path)

    def test_it_refuses_paths_that_escape_the_repo(self):
        from modules.nsot.repo import RefSource, ScopeRefused
        with pytest.raises(ScopeRefused):
            RefSource("/nonexistent", "HEAD").read("../../etc/passwd")

    def test_the_refusal_says_how_to_widen_it_deliberately(self):
        from modules.nsot.repo import RefSource, ScopeRefused
        with pytest.raises(ScopeRefused) as exc:
            RefSource("/nonexistent", "HEAD").read("host_vars/s4.yml")
        assert "Widen `allow` at the call site" in str(exc.value)

    def test_a_wider_scope_is_declared_at_construction(self):
        """What item 2 will do, and it has to say so."""
        from modules.nsot.repo import RefSource
        src = RefSource("/nonexistent", "HEAD", allow=("golden/", "host_vars/"))
        assert src._check("host_vars/s4.yml") == "host_vars/s4.yml"
        assert src._check("golden/s4.cfg") == "golden/s4.cfg"

    def test_widening_does_not_admit_templates(self):
        from modules.nsot.repo import RefSource, ScopeRefused
        src = RefSource("/nonexistent", "HEAD", allow=("golden/", "host_vars/"))
        with pytest.raises(ScopeRefused):
            src.read("templates/cisco_ios/base.j2")

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


class TestIntentIsRestoredWithTheDevice:
    """Item 2: device and committed intent are one unit per device.

    Restoring only the configuration leaves the device at the ref while
    ``host_vars`` still describes something else, so the very next plan offers
    to undo the restore. The device fights its own source of truth, and the
    operator sees a "drift" they created by pressing restore.
    """

    def _with_intent(self, lab, host, text):
        from modules.nsot import hostvars
        hostvars.write_committed_text(lab["repo"], host, text)
        R.git(lab["repo"], "add", "-A", "host_vars")
        R.git(lab["repo"], "commit", "-m", f"intent: {host}")
        _rc, sha, _err = R.git(lab["repo"], "rev-parse", "HEAD")
        return sha.strip()

    def test_ref_intent_is_carried_verbatim(self, lab, monkeypatch):
        """The ref's own bytes, not a re-serialisation of the parsed dict."""
        text = "device: R1\nplatform: cisco_ios\nhostname: R1\n# a human note\n"
        ref = self._with_intent(lab, "R1", text)

        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
        monkeypatch.setattr("modules.nsot.restore.validate_restored_intent",
                            lambda *a, **k: [])
        monkeypatch.setattr("routes.deploy._captured_config", lambda r, h: "")
        targets, _skipped = restore.build_targets("Lab", ref, ["R1"])

        target = next(t for t in targets if t.device == "R1")
        assert target.ref_intent_text == text, (
            "the comment survives only if the ref's bytes are carried")
        assert target.ref_intent["device"] == "R1"

    def test_device_with_no_intent_at_the_ref_is_skipped_not_un_onboarded(
            self, lab, monkeypatch):
        """The default outcome is SKIP, never a silent deletion of intent."""
        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
        monkeypatch.setattr("routes.deploy._captured_config", lambda r, h: "")

        targets, skipped = restore.build_targets("Lab", lab["baseline"], ["R1"])
        assert targets == []
        entry = next(s for s in skipped if s["hostname"] == "R1")
        assert entry["un_onboardable"] is True
        assert "un-onboard" in entry["detail"]
        assert "recoverable from git history" in entry["detail"]

    def test_un_onboarding_is_opt_in_per_device(self, lab, monkeypatch):
        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
        monkeypatch.setattr("routes.deploy._captured_config", lambda r, h: "")

        targets, skipped = restore.build_targets(
            "Lab", lab["baseline"], ["R1", "R2"], un_onboard=["R1"])
        assert [t.device for t in targets] == ["R1"]
        assert targets[0].un_onboard is True
        assert [s["hostname"] for s in skipped] == ["R2"]

    def test_intent_is_written_only_for_devices_that_reached_the_ref(
            self, lab, monkeypatch):
        """A failed device keeps today's intent. Half a unit is the bug."""
        from modules.nsot import hostvars
        from routes.deploy import _write_restored_intent

        hostvars.write_committed_text(lab["repo"], "R1", "device: R1\nold: yes\n")
        hostvars.write_committed_text(lab["repo"], "R2", "device: R2\nold: yes\n")

        report = {"results": [
            {"device": "R1", "outcome": "deployed",
             "ref_intent_text": "device: R1\nnew: yes\n"},
            {"device": "R2", "outcome": "failed",
             "ref_intent_text": "device: R2\nnew: yes\n"},
        ]}
        out = _write_restored_intent("Lab", report, "some-ref")

        assert out["restored"] == ["R1"]
        assert [s["device"] for s in out["skipped"]] == ["R2"]
        assert "new: yes" in open(hostvars.committed_path(lab["repo"], "R1")).read()
        assert "old: yes" in open(hostvars.committed_path(lab["repo"], "R2")).read()

    def test_restored_intent_is_staged_across_the_crash_window(
            self, lab, monkeypatch):
        """Between the push landing and the commit, the pairing is at risk."""
        from routes.deploy import _write_restored_intent

        report = {"results": [{"device": "R1", "outcome": "deployed",
                               "ref_intent_text": "device: R1\nnew: yes\n"}]}
        _write_restored_intent("Lab", report, "some-ref")
        assert R.staged_restored_intent(lab["repo"]) == {
            "R1": "device: R1\nnew: yes\n"}

    def test_un_onboard_removes_the_file_by_a_forward_commit(self, lab):
        from modules.nsot import hostvars
        from routes.deploy import _write_restored_intent

        hostvars.write_committed_text(lab["repo"], "R1", "device: R1\n")
        R.git(lab["repo"], "add", "-A", "host_vars")
        R.git(lab["repo"], "commit", "-m", "intent: R1")

        report = {"results": [{"device": "R1", "outcome": "deployed",
                               "un_onboard": True, "ref_intent_text": ""}]}
        out = _write_restored_intent("Lab", report, "some-ref")

        assert out["un_onboarded"] == ["R1"]
        assert not os.path.exists(hostvars.committed_path(lab["repo"], "R1"))
        # The previous commit is untouched, so the intent is still reachable.
        _rc, out_log, _e = R.git(lab["repo"], "log", "--oneline", "--", "host_vars")
        assert "intent: R1" in out_log


class TestIntentCommitsWithTheDevice:
    """``host_vars`` reaches a commit only when a caller asks for it."""

    def test_a_template_deploy_never_carries_intent(self, lab):
        """``extra_paths`` omitted: staged intent stays out of the commit."""
        from modules.nsot import hostvars

        hostvars.write_committed_text(lab["repo"], "R1", "device: R1\nx: 1\n")
        items = [R.GoldenItem("R1", "hostname R1\nnew line\n", "203.0.113.1",
                              netbox_id=1)]
        result = R.save_golden("Lab", items, source="pipeline")

        _rc, files, _e = R.git(lab["repo"], "show", "--name-only",
                               "--format=", result["commit"])
        assert "host_vars" not in files

    def test_a_restore_carries_intent_in_the_same_commit(self, lab):
        from modules.nsot import hostvars

        hostvars.write_committed_text(lab["repo"], "R1", "device: R1\nx: 1\n")
        items = [R.GoldenItem("R1", "hostname R1\nnew line\n", "203.0.113.1",
                              netbox_id=1)]
        result = R.save_golden("Lab", items, source="pipeline",
                               extra_paths=["host_vars"])

        _rc, files, _e = R.git(lab["repo"], "show", "--name-only",
                               "--format=", result["commit"])
        assert "host_vars/R1.yml" in files
        assert "golden/R1.cfg" in files

    def test_intent_alone_still_produces_a_commit(self, lab):
        """A device already at the ref changes no golden — the intent still moved.

        The empty-commit guard asked only about ``golden/``. A restore to a ref
        a device already matches would have written the intent and returned
        "no commit created", leaving it uncommitted in the working tree.
        """
        from modules.nsot import hostvars

        hostvars.write_committed_text(lab["repo"], "R1", "device: R1\nx: 1\n")
        items = [R.GoldenItem("R1", "hostname R1\n", "203.0.113.1", netbox_id=1)]
        result = R.save_golden("Lab", items, source="pipeline",
                               extra_paths=["host_vars"])

        assert result["changed"] == []
        assert result["commit"], "intent moved, so there is something to record"
        _rc, files, _e = R.git(lab["repo"], "show", "--name-only",
                               "--format=", result["commit"])
        assert "host_vars/R1.yml" in files

    def test_nothing_at_all_still_creates_no_commit(self, lab):
        """The guard must not have been traded away for the case above."""
        before = R.git(lab["repo"], "rev-parse", "HEAD")[1].strip()
        items = [R.GoldenItem("R1", "hostname R1\n", "203.0.113.1", netbox_id=1)]
        result = R.save_golden("Lab", items, source="pipeline",
                               extra_paths=["host_vars"])

        assert result["commit"] == ""
        assert R.git(lab["repo"], "rev-parse", "HEAD")[1].strip() == before


class TestRestoreUsesTheListItWasGiven:
    """Audit finding C: repo from the argument, inventory from a global.

    ``plan_restore()`` and ``build_targets()`` both take ``list_name``, used it
    to resolve the repo, then read the devices from
    ``get_current_device_list()``. Pass a list that is not the active one — which
    the signature invites, since why else take the parameter — and you get list
    A's stored configs matched against list B's device rows: B's management
    addresses, B's credentials, B's platform mapping.

    Latent, because every caller happened to pass the active list. The more
    dangerous of the two shapes, because nothing looks wrong at the call site.
    """

    def test_devices_come_from_the_named_list_not_the_active_one(
            self, lab, monkeypatch, tmp_path):
        from modules.nsot import restore

        other = tmp_path / "other_list"
        (other / "config_repo").mkdir(parents=True)
        (other / "devices.csv").write_text(
            "hostname,ip,device_type,username,password,secret\n"
            "R1,198.51.100.99,cisco_ios,u,p,s\n", encoding="utf-8")

        # The ACTIVE list is the other one; the caller asks for "Lab".
        monkeypatch.setattr("modules.device.get_current_device_list",
                            lambda: ("Other", str(other / "devices.csv")))
        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)

        result = restore.plan_restore("Lab", lab["baseline"])

        addresses = {entry["ip"] for entry in result["restorable"]}
        assert "198.51.100.99" not in addresses, (
            "restore resolved device addresses from the ACTIVE list instead of "
            f"the list it was given: {addresses}")
        assert addresses <= {"203.0.113.1", "203.0.113.2", "203.0.113.7"}

    def test_build_targets_uses_the_named_list(self, lab, monkeypatch, tmp_path):
        from modules.nsot import restore

        other = tmp_path / "other_list2"
        (other / "config_repo").mkdir(parents=True)
        (other / "devices.csv").write_text(
            "hostname,ip,device_type,username,password,secret\n"
            "R1,198.51.100.99,cisco_ios,u,p,s\n", encoding="utf-8")
        monkeypatch.setattr("modules.device.get_current_device_list",
                            lambda: ("Other", str(other / "devices.csv")))
        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
        monkeypatch.setattr("routes.deploy._captured_config", lambda r, h: "")

        targets, skipped = restore.build_targets("Lab", lab["baseline"],
                                                 un_onboard=["R1", "R2", "R7"])
        addresses = {t.device_row.get("ip") for t in targets}
        assert "198.51.100.99" not in addresses, addresses

    def test_the_module_does_not_consult_the_active_list(self):
        import inspect
        from modules.nsot import restore

        source = inspect.getsource(restore)
        offending = [l.strip() for l in source.splitlines()
                     if "get_current_device_list" in l
                     and not l.strip().startswith(("#", "devices from"))]
        assert offending == [], offending


class TestRevertHandsOffToTheConfirmedPath:
    """`revert_to_golden` pushed a stored diff straight at a device.

    Every `-` line applied verbatim, every `+` line turned into `no <command>` —
    unbounded negation, with no confirm hash, no `assert_no_mask()`, no
    sendability check, no failure capture and no rollback.
    `invalidate_queued_restores()` already rejected these items *from the
    Baselines panel*, which left the other direction open: approving one
    through the normal queue UI still reached the executor.
    """

    ENTRY = {"id": "abc123", "action_type": "revert_to_golden",
             "device_ip": "203.0.113.1", "device_hostname": "R1",
             "diff": "--- golden\n+++ running\n-ip route 0.0.0.0 0.0.0.0 1.1.1.1\n"
                     "+ip route 0.0.0.0 0.0.0.0 2.2.2.2\n"}

    def test_it_hands_off_instead_of_pushing(self):
        from modules import approval_queue

        result = approval_queue._exec_revert_golden(dict(self.ENTRY))
        assert result["needs_confirmation"] is True
        assert "error" not in result

    def test_it_points_at_this_device_at_HEAD(self):
        """A single-device revert IS a Mode A re-apply of its HEAD golden."""
        from modules import approval_queue

        result = approval_queue._exec_revert_golden(dict(self.ENTRY))
        assert result["restore"] == {"ref": "HEAD", "devices": ["R1"],
                                     "approval_id": "abc123"}
        assert "R1" in result["message"]

    def test_it_opens_no_connection(self, monkeypatch):
        """The decisive property: nothing reaches a device."""
        from modules import approval_queue

        def _boom(*a, **k):
            raise AssertionError("the retired executor opened a connection")
        monkeypatch.setattr("modules.connection.get_persistent_connection", _boom)
        monkeypatch.setattr("modules.connection.with_temp_connection", _boom)

        approval_queue._exec_revert_golden(dict(self.ENTRY))

    def test_no_negation_is_generated_anywhere_in_the_module(self):
        """The `no <line>` construction is gone, not merely unreached."""
        import inspect

        from modules import approval_queue

        source = inspect.getsource(approval_queue)
        assert 'f"no {' not in source, (
            "approval_queue still builds a negation; the one place this tool "
            "may generate 'no' is deploy.rollback_commands(), bounded by "
            "assert_rollback_provenance()")

    def test_the_other_action_type_still_works(self, monkeypatch):
        """Only the pushing path is retired. Promoting a capture is fine."""
        from modules import approval_queue

        called = {}
        monkeypatch.setattr("modules.ai_assistant._get_running_config_for_golden",
                            lambda ip, host: "hostname R1\n")
        monkeypatch.setattr("modules.ai_assistant._save_golden_config_file",
                            lambda ip, host, text: called.setdefault("saved", host))
        monkeypatch.setattr("modules.ai_assistant._safe_device_name", lambda h: h)
        monkeypatch.setattr("modules.ai_assistant._get_golden_configs_dir",
                            lambda: "/tmp")

        result = approval_queue._exec_update_golden(
            {"device_ip": "203.0.113.1", "device_hostname": "R1"})
        assert called.get("saved") == "R1"
        assert "error" not in result


class TestApproveAllSkipsConfirmEndingItems:
    """Bulk approval must not auto-confirm a program nobody was shown.

    Approve-all exists to clear a queue of decided outcomes. A confirm-ending
    item — one whose approval opens a preview the operator confirms per device
    — has no decided outcome yet. Looping it would either auto-confirm (exactly
    what the confirm hash prevents) or stack N modals on one click.
    """

    def test_a_confirm_ending_action_is_identified(self):
        from modules import approval_queue

        assert approval_queue.is_confirm_ending(
            {"action_type": "revert_to_golden"}) is True
        assert approval_queue.is_confirm_ending(
            {"action_type": "update_golden_config"}) is False

    def test_approve_all_skips_it_and_says_why(self, monkeypatch):
        import flask

        import app as app_module
        from modules import approval_queue

        pending = [
            {"id": "a1", "action_type": "update_golden_config",
             "device_ip": "203.0.113.1", "device_hostname": "r1"},
            {"id": "b2", "action_type": "revert_to_golden",
             "device_ip": "203.0.113.2", "device_hostname": "r2"},
        ]
        resolved = []
        monkeypatch.setattr(approval_queue, "get_pending", lambda: pending)
        monkeypatch.setattr(approval_queue, "resolve",
                            lambda i, a: resolved.append(i) or {"ok": True})

        with app_module.app.test_request_context(json={}):
            response = app_module.ai_approval_approve_all()
        body = response.get_json() if hasattr(response, "get_json") else response[0]

        assert resolved == ["a1"], "a confirm-ending item was bulk-approved"
        assert body["skipped_count"] == 1
        assert body["skipped"][0]["device"] == "r2"
        assert body["skipped"][0]["reason"] == "requires individual review"
        assert "individual review" in body["message"]


class TestTheQueuedDiffNeverReachesADevice:
    """D2 part 1: approving opens the preview; the program is computed fresh.

    The queued diff was computed when the drift was noticed, which is not when
    the operator is looking. A program the approver never read is exactly what
    the confirm hash exists to prevent — so the stored diff is advisory context
    ("what the agent saw") beside a program computed now, from the device as it
    is now.
    """

    ENTRY = {"id": "q1", "action_type": "revert_to_golden", "status": "pending",
             "resolved_at": None,
             "device_ip": "203.0.113.1", "device_hostname": "R1",
             "diff": "--- golden\n+++ running\n-ip route 0.0.0.0 0.0.0.0 1.1.1.1\n"
                     "+ip route 0.0.0.0 0.0.0.0 2.2.2.2\n"}

    @pytest.fixture
    def queue(self, tmp_path, monkeypatch):
        from modules import approval_queue

        path = tmp_path / "approval_queue.json"
        monkeypatch.setattr(approval_queue, "_queue_path", lambda: str(path))
        monkeypatch.setattr(approval_queue, "_load_queue",
                            lambda: [dict(self.ENTRY)])
        saved = {}
        monkeypatch.setattr(approval_queue, "_save_queue",
                            lambda entries: saved.update({"entries": entries}))
        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
        return approval_queue, saved

    def test_the_advisory_diff_is_carried_but_labelled(self):
        from modules import approval_queue

        result = approval_queue._exec_revert_golden(dict(self.ENTRY))
        assert result["advisory_diff"] == self.ENTRY["diff"]
        assert "computed fresh" in result["advisory_note"]
        assert "may differ" in result["advisory_note"]

    def test_approving_does_not_mark_the_item_done(self, queue):
        """The work has not happened — it is awaiting a confirmation."""
        approval_queue, saved = queue

        result = approval_queue.resolve("q1", "approve")

        assert result["needs_confirmation"] is True
        assert result["entry"]["status"] == "pending"
        assert result["entry"]["resolved_at"] is None
        assert "Awaiting confirmation" in result["entry"]["context"]

    def test_approving_opens_no_connection(self, queue, monkeypatch):
        approval_queue, _saved = queue

        def _boom(*a, **k):
            raise AssertionError("approving opened a connection")
        monkeypatch.setattr("modules.connection.get_persistent_connection", _boom)
        monkeypatch.setattr("modules.connection.with_temp_connection", _boom)

        approval_queue.resolve("q1", "approve")

    def test_mark_done_closes_it(self, queue):
        approval_queue, _saved = queue

        result = approval_queue.mark_done("q1", "Re-applied HEAD to R1")
        assert result["ok"] is True
        assert result["entry"]["status"] == "approved"
        assert result["entry"]["resolved_at"]
        assert "Re-applied" in result["entry"]["context"]

    def test_mark_done_refuses_an_already_resolved_item(self, queue,
                                                         monkeypatch):
        approval_queue, _saved = queue
        monkeypatch.setattr(approval_queue, "_load_queue",
                            lambda: [dict(self.ENTRY, status="approved")])
        assert approval_queue.mark_done("q1")["ok"] is False

    def test_the_restore_closes_the_item_only_on_success(self, monkeypatch):
        """An item closed on a failed push is the queue claiming work that
        did not happen."""
        import flask

        import routes.golden as golden
        from modules.nsot.deploy import DEPLOYED

        closed = {}

        def _mark_done(entry_id, note=""):
            closed["id"] = entry_id
            return {"ok": True}
        monkeypatch.setattr("modules.approval_queue.mark_done", _mark_done)
        monkeypatch.setattr(golden, "_active_list", lambda data=None: "Lab")
        monkeypatch.setattr("modules.nsot.restore.invalidate_queued_restores",
                            lambda: {"rejected": []})
        monkeypatch.setattr("modules.nsot.restore.build_targets",
                            lambda *a, **k: ([object()], []))

        app = flask.Flask(__name__)
        app.register_blueprint(golden.bp)

        # Failure first: nothing may be closed.
        monkeypatch.setattr("routes.deploy.run_targets",
                            lambda *a, **k: {"results": [
                                {"device": "R1", "outcome": "failed"}]})
        body = app.test_client().post("/golden/restore/apply", json={
            "ref": "HEAD", "confirmations": {"R1": "h"},
            "approval_id": "q1"}).get_json()
        assert body["approval_closed"] is False
        assert "no device completed" in body["approval_note"]
        assert closed == {}

        # Then success.
        monkeypatch.setattr("routes.deploy.run_targets",
                            lambda *a, **k: {"results": [
                                {"device": "R1", "outcome": DEPLOYED}]})
        body = app.test_client().post("/golden/restore/apply", json={
            "ref": "HEAD", "confirmations": {"R1": "h"},
            "approval_id": "q1"}).get_json()
        assert body["approval_closed"] is True
        assert closed["id"] == "q1"

    def test_no_approval_id_means_no_queue_interaction(self, monkeypatch):
        """An ordinary restore must not touch the queue."""
        import flask

        import routes.golden as golden
        from modules.nsot.deploy import DEPLOYED

        def _boom(*a, **k):
            raise AssertionError("mark_done called without an approval_id")
        monkeypatch.setattr("modules.approval_queue.mark_done", _boom)
        monkeypatch.setattr(golden, "_active_list", lambda data=None: "Lab")
        monkeypatch.setattr("modules.nsot.restore.invalidate_queued_restores",
                            lambda: {"rejected": []})
        monkeypatch.setattr("modules.nsot.restore.build_targets",
                            lambda *a, **k: ([object()], []))
        monkeypatch.setattr("routes.deploy.run_targets",
                            lambda *a, **k: {"results": [
                                {"device": "R1", "outcome": DEPLOYED}]})

        app = flask.Flask(__name__)
        app.register_blueprint(golden.bp)
        body = app.test_client().post("/golden/restore/apply", json={
            "ref": "HEAD", "confirmations": {"R1": "h"}}).get_json()
        assert "approval_closed" not in body


class TestTheHandoffScopesToOneDevice:
    """Approving one device's item must not preview a fleet-wide re-apply."""

    def test_the_preview_honours_the_devices_list(self, monkeypatch):
        import flask

        import routes.golden as golden

        seen = {}

        def _build(list_name, ref, devices=None, un_onboard=None):
            seen["ref"] = ref
            seen["devices"] = devices
            return [], []

        monkeypatch.setattr(golden, "_active_list", lambda data=None: "Lab")
        monkeypatch.setattr("modules.nsot.restore.build_targets", _build)

        app = flask.Flask(__name__)
        app.register_blueprint(golden.bp)
        body = app.test_client().post("/golden/restore/preview", json={
            "ref": "HEAD", "devices": ["R1"],
            "advisory_diff": "--- golden\n+++ running\n-a\n+b\n",
            "approval_id": "q1"}).get_json()

        assert seen["ref"] == "HEAD"
        assert seen["devices"] == ["R1"]
        # Echoed for the confirm dialog, never an input to anything.
        assert body["advisory_diff"].startswith("--- golden")
        assert body["approval_id"] == "q1"

    def test_the_advisory_diff_is_not_used_to_build_anything(self, monkeypatch):
        """It is displayed. It is not parsed, rendered, or sent."""
        import inspect

        import routes.golden as golden

        source = inspect.getsource(golden.restore_preview)
        # The only thing done with it is echoing it back.
        uses = [l.strip() for l in source.splitlines() if "advisory_diff" in l]
        assert uses == ['"advisory_diff": (data.get("advisory_diff") or ""),'], uses

class TestBaselineCredentialGaps:
    """Which devices' credentials a baseline predates, stated before the click.

    A restore point normally goes stale by being behind. A rotation makes it
    stale in a second direction: the ref names a secret the device has been
    deliberately moved away from, so re-applying it would re-publish a secret
    that exists in history precisely because rotation was meant to kill it.

    `validate_restored_intent()` already refuses such a device at plan time,
    so this is not a new guard — it is the same question asked early enough to
    print beside the button rather than after the operator has committed.
    """

    def _repo(self, tmp_path, intents):
        """A repo with one commit holding the given host_vars."""
        import subprocess

        import yaml

        repo = tmp_path / "config_repo"
        (repo / "host_vars").mkdir(parents=True)
        for host, data in intents.items():
            (repo / "host_vars" / f"{host}.yml").write_text(
                yaml.safe_dump(data), encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A"]):
            subprocess.run(["git", "-C", str(repo), *args], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                        "-c", "user.name=t", "commit", "-q", "-m", "seed"],
                       check=True)
        return str(repo)

    def test_a_rotated_device_is_reported_as_stale(self, tmp_path, monkeypatch):
        from modules.nsot.restore import baseline_credential_gaps

        repo = self._repo(tmp_path, {
            "r1": {"secret_refs": ["user_admin_password", "snmp_community_ro"]},
            "r9": {"secret_refs": ["user_admin_secret"]},
        })
        # The store holds only what survives today's rotation.
        monkeypatch.setattr(
            "modules.credentials.get_template_secret",
            lambda key: "value" if key.endswith("user_admin_secret")
            or key.endswith("snmp_community_ro") else "")

        out = baseline_credential_gaps(repo, "HEAD", "Lab", ["r1", "r9"])
        assert out["stale"] == {"r1": ["user_admin_password"]}
        assert out["no_intent"] == []
        assert out["checked"] == 2

    def test_a_device_with_no_intent_is_not_reported_as_safe(
            self, tmp_path, monkeypatch):
        """A ref predating onboarding is a different thing from a valid one."""
        from modules.nsot.restore import baseline_credential_gaps

        repo = self._repo(tmp_path, {"r1": {"secret_refs": ["user_admin_secret"]}})
        monkeypatch.setattr("modules.credentials.get_template_secret",
                            lambda key: "value")

        out = baseline_credential_gaps(repo, "HEAD", "Lab", ["r1", "r_absent"])
        assert out["stale"] == {}
        assert out["no_intent"] == ["r_absent"]

    def test_an_intent_with_no_secret_refs_counts_as_no_intent(
            self, tmp_path, monkeypatch):
        """The migrated baseline's shape: committed, but nothing to check."""
        from modules.nsot.restore import baseline_credential_gaps

        repo = self._repo(tmp_path, {"r1": {"users": [{"name": "admin"}]}})
        monkeypatch.setattr("modules.credentials.get_template_secret",
                            lambda key: "value")

        out = baseline_credential_gaps(repo, "HEAD", "Lab", ["r1"])
        assert out["no_intent"] == ["r1"]
        assert out["stale"] == {}

    def test_everything_current_reports_nothing(self, tmp_path, monkeypatch):
        from modules.nsot.restore import baseline_credential_gaps

        repo = self._repo(tmp_path, {"r1": {"secret_refs": ["user_admin_secret"]}})
        monkeypatch.setattr("modules.credentials.get_template_secret",
                            lambda key: "value")

        out = baseline_credential_gaps(repo, "HEAD", "Lab", ["r1"])
        assert out == {"stale": {}, "no_intent": [], "checked": 1}

    def test_malformed_intent_is_not_silently_treated_as_current(
            self, tmp_path, monkeypatch):
        from modules.nsot.restore import baseline_credential_gaps

        repo = tmp_path / "config_repo"
        (repo / "host_vars").mkdir(parents=True)
        (repo / "host_vars" / "r1.yml").write_text("{[not yaml", encoding="utf-8")
        import subprocess
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                        "-c", "user.name=t", "commit", "-q", "-m", "seed"],
                       check=True)
        monkeypatch.setattr("modules.credentials.get_template_secret",
                            lambda key: "value")

        out = baseline_credential_gaps(str(repo), "HEAD", "Lab", ["r1"])
        assert out["no_intent"] == ["r1"], "unreadable is not current"

