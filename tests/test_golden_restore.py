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


def _seed(list_name, items, **kw):
    """Onboard devices into a fresh test repo.

    Named for what it does. These fixtures ARE onboarding — a new repo has an
    empty manifest — so they pass `allow_new=True` explicitly, and the flag
    lives in one place rather than being implied by a default. Tests that
    exercise resolution or refusal call `R.save_golden` directly.
    """
    kw.setdefault("allow_new", True)
    # A Save All here captures the test's whole fleet, which is the items it
    # passes: coverage is stated, because a Save All that committed without it
    # took a baseline with devices skipped (C91), and these tests had pinned it.
    if kw.get("source") == "save_all":
        kw.setdefault("inventory_size", len(items))
    return R.save_golden(list_name, items, **kw)

@pytest.fixture
def lab(tmp_path, monkeypatch, intent_matches):
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
    result = _seed("Lab", items, source="save_all")
    baseline = next(t for t in result["tags"] if t.startswith("baseline/"))
    return {"dir": list_dir, "repo": str(list_dir / "config_repo"),
            "baseline": baseline}


def _mark_stale(lab, ips):
    (lab["dir"] / "source.json").write_text(
        json.dumps({"source": "netbox"}), encoding="utf-8")
    (lab["dir"] / "stale_devices.json").write_text(
        json.dumps({ip: {"hostname": f"dev-{ip}", "reason": "gone"} for ip in ips}),
        encoding="utf-8")


R9 = {"hostname": "R9", "ip": "203.0.113.9", "device_type": "cisco_ios",
      "username": "u", "password": "p", "secret": "s", "role": "router"}


def _targets(lab, monkeypatch, devices=None, stale=(), inventory=None, ref=None):
    """build_targets() on the REAL repo. The lab commits goldens and no intent,
    so every device is passed as un-onboard to become a target; what is under
    test here is the POPULATION, not intent handling."""
    monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": ip in stale)
    monkeypatch.setattr("modules.inventory.stale_message", lambda ip, ln="": "R7 is no longer in NetBox")
    monkeypatch.setattr("routes.deploy._captured_config", lambda r, h: "")
    if inventory is not None:
        monkeypatch.setattr("modules.device.load_saved_devices", lambda p=None: inventory)
    return restore.build_targets("Lab", ref or lab["baseline"], devices,
                                 un_onboard=["R1", "R2", "R7", "R9"])


class TestBuildTargetsNamesEveryDevice:
    """Ported from `plan_restore()`, deleted by P.3 step 5 (register C23): the
    preview and the apply both call build_targets(), so that is where the
    population rules are tested."""

    def test_all_devices_are_targets_when_none_are_stale(self, lab, monkeypatch):
        targets, skipped = _targets(lab, monkeypatch)
        assert {t.device for t in targets} == {"R1", "R2", "R7"}
        assert skipped == []

    def test_stale_devices_are_skipped_and_named(self, lab, monkeypatch):
        targets, skipped = _targets(lab, monkeypatch, stale=("203.0.113.7",))
        assert {t.device for t in targets} == {"R1", "R2"}
        assert [s["hostname"] for s in skipped] == ["R7"]
        assert "no longer in NetBox" in skipped[0]["reason"]

    def test_device_not_in_list_is_skipped(self, lab, monkeypatch):
        _t, skipped = _targets(lab, monkeypatch, inventory=DEVICES[:1])
        assert {s["hostname"] for s in skipped} == {"R2", "R7"}
        assert all("not in the current device list" in s["reason"] for s in skipped)

    def test_subset_restore(self, lab, monkeypatch):
        targets, _s = _targets(lab, monkeypatch, devices=["R1"])
        assert [t.device for t in targets] == ["R1"]

    def test_unknown_ref_fails_cleanly(self, lab, monkeypatch):
        targets, skipped = _targets(lab, monkeypatch, ref="baseline/does-not-exist")
        assert targets == [] and "no golden configs" in skipped[0]["reason"]


class TestTheInventoryIsThePopulation:
    """Register C23. A device the ref PREDATES must be named, and the
    denominator is the inventory. The fix lived in `plan_restore()`, which no
    route called; the preview iterated the ref."""

    def test_a_device_the_ref_predates_is_named_with_what_will_happen(self, lab, monkeypatch):
        _t, skipped = _targets(lab, monkeypatch, inventory=DEVICES + [R9])
        row = next(s for s in skipped if s["hostname"] == "R9")
        assert row["reason"] == "not in this baseline" and row["not_at_ref"] is True
        assert "predates" in row["detail"] and "exactly as it is" in row["detail"]

    def test_the_denominator_is_the_inventory_and_the_ref_is_partial(self, lab, monkeypatch):
        _t, skipped = _targets(lab, monkeypatch, inventory=DEVICES + [R9])
        cov = restore.coverage("Lab", None, skipped)
        assert cov["denominator"] == 4 and cov["partial"] is True

    def test_a_ref_covering_the_whole_fleet_is_not_partial(self, lab, monkeypatch):
        """The floor: a preview that always said partial would pass the above."""
        _t, skipped = _targets(lab, monkeypatch)
        cov = restore.coverage("Lab", None, skipped)
        assert cov["partial"] is False and cov["denominator"] == 3
        assert not [s for s in skipped if s.get("not_at_ref")]

    def test_a_scoped_restore_names_a_requested_device_the_ref_lacks(self, lab, monkeypatch):
        """Asking for one device is not a claim about the fleet, but a device
        you ASKED for and the ref does not hold must not vanish either."""
        _t, skipped = _targets(lab, monkeypatch, devices=["R1", "R9"],
                               inventory=DEVICES + [R9])
        assert [s["hostname"] for s in skipped] == ["R9"]
        assert "no golden config at" in skipped[0]["reason"]
        cov = restore.coverage("Lab", ["R1", "R9"], skipped)
        assert cov["partial"] is False and cov["denominator"] == 2

    def test_the_plan_says_n_of_the_inventory_and_names_the_device(self, lab, monkeypatch):
        """What the operator READS. Control for C23: this is the sentence that
        read '3 of 3' while the inventory held 4. THE restore plan, which every preview
        runs (today's /golden/restore/preview did until it left at 7.8, 2026-10-17)."""
        import routes.golden as golden

        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
        monkeypatch.setattr("modules.device.load_saved_devices", lambda p=None: DEVICES + [R9])
        monkeypatch.setattr("routes.deploy._captured_config", lambda r, h: "hostname x\n")
        monkeypatch.setattr(golden, "_intent_preview", lambda ln, t: {"action": "none"})
        monkeypatch.setattr("modules.nsot.deploy.prepare_restore",
                            lambda target: {"config": target.target_config})
        body = golden.restore_plan("Lab", lab["baseline"], None,
                                   un_onboard=["R1", "R2", "R7"])
        assert body["ok"], body
        assert "of 4 device(s) in this list" in body["summary"], body["summary"]
        assert "PARTIAL" in body["summary"] and "R9" in body["summary"]
        assert body["inventory_size"] == 4 and body["partial"] is True


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

class TestBaselineCoverage:
    def test_baseline_tree_contains_every_device(self, lab):
        """Baselines cover everything inherently — the tagged tree has them all."""
        assert set(R.devices_at(lab["repo"], lab["baseline"])) == {"R1", "R2", "R7"}

    def test_stale_device_config_remains_downloadable(self, lab, monkeypatch):
        """Skipping a stale device from restore must not hide its config."""
        monkeypatch.setattr("modules.inventory.is_stale",
                            lambda ip, ln="": ip == "203.0.113.7")
        monkeypatch.setattr("modules.inventory.stale_message", lambda ip, ln="": "gone")
        monkeypatch.setattr("routes.deploy._captured_config", lambda r, h: "")
        restore.build_targets("Lab", lab["baseline"])
        assert R.golden_at(lab["repo"], "R7", lab["baseline"]) is not None


class TestIntentIsRestoredWithTheDevice:
    """Item 2: device and committed intent are one unit per device.

    Restoring only the configuration leaves the device at the ref while
    ``host_vars`` still describes something else, so the very next plan offers
    to undo the restore. The device fights its own source of truth, and the
    operator sees a "drift" they created by pressing restore.
    """

    def _with_intent(self, lab, host, text):
        """*text* committed as *host*'s intent byte for byte, as a ref from before C1693 holds
        it (every write path since commits Mercury's own formatting, so a comment reaches a
        ref only from before then; the restore still carries that ref's own bytes)."""
        from modules.nsot import hostvars
        path = hostvars.committed_path(lab["repo"], host)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
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
        # Read as documents: since C1693 a restore writes the ref's intent in Mercury's own
        # formatting (YAML's `yes` is written `true`), the same document.
        r1 = hostvars.from_yaml(open(hostvars.committed_path(lab["repo"], "R1")).read())
        r2 = hostvars.from_yaml(open(hostvars.committed_path(lab["repo"], "R2")).read())
        assert r1.get("new") is True and "old" not in r1
        assert r2.get("old") is True and "new" not in r2

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
        result = _seed("Lab", items, source="pipeline")

        _rc, files, _e = R.git(lab["repo"], "show", "--name-only",
                               "--format=", result["commit"])
        assert "host_vars" not in files

    def test_a_restore_carries_intent_in_the_same_commit(self, lab):
        from modules.nsot import hostvars

        hostvars.write_committed_text(lab["repo"], "R1", "device: R1\nx: 1\n")
        items = [R.GoldenItem("R1", "hostname R1\nnew line\n", "203.0.113.1",
                              netbox_id=1)]
        result = _seed("Lab", items, source="pipeline",
                               extra_paths=["host_vars/R1.yml"])

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
        result = _seed("Lab", items, source="pipeline",
                               extra_paths=["host_vars/R1.yml"])

        assert result["changed"] == []
        assert result["commit"], "intent moved, so there is something to record"
        _rc, files, _e = R.git(lab["repo"], "show", "--name-only",
                               "--format=", result["commit"])
        assert "host_vars/R1.yml" in files

    def test_nothing_at_all_still_creates_no_commit(self, lab):
        """The guard must not have been traded away for the case above."""
        before = R.git(lab["repo"], "rev-parse", "HEAD")[1].strip()
        items = [R.GoldenItem("R1", "hostname R1\n", "203.0.113.1", netbox_id=1)]
        result = _seed("Lab", items, source="pipeline",
                               extra_paths=["host_vars/R1.yml"])

        assert result["commit"] == ""
        assert R.git(lab["repo"], "rev-parse", "HEAD")[1].strip() == before


class TestRestoreUsesTheListItWasGiven:
    """Audit finding C: repo from the argument, inventory from a global.

    ``plan_restore()`` (since deleted, C23) and ``build_targets()`` both took ``list_name``, used it
    to resolve the repo, then read the devices from
    ``get_current_device_list()``. Pass a list that is not the active one — which
    the signature invites, since why else take the parameter — and you get list
    A's stored configs matched against list B's device rows: B's management
    addresses, B's credentials, B's platform mapping.

    Latent, because every caller happened to pass the active list. The more
    dangerous of the two shapes, because nothing looks wrong at the call site.
    """

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


class TestTheQueueBuildsNoProgram:
    """`revert_to_golden` once pushed a stored diff straight at a device: every `-` line
    verbatim, every `+` line as `no <command>`, with no confirm hash. Its executor became a
    hand-off to the restore path, and left entirely with the AI family (C783)."""

    def test_no_negation_is_generated_anywhere_in_the_module(self):
        """The `no <line>` construction is gone, not merely unreached."""
        import inspect

        from modules import approval_queue

        source = inspect.getsource(approval_queue)
        assert 'f"no {' not in source, (
            "approval_queue still builds a negation; the one place this tool "
            "may generate 'no' is deploy.rollback_commands(), bounded by "
            "assert_rollback_provenance()")


class TestTheQueuedDiffNeverReachesADevice:
    """D2 part 1: a queued item closes when its device is restored or captured through the
    confirmed path; the queued diff, computed when the drift was noticed, is never an input."""

    ENTRY = {"id": "q1", "action_type": "revert_to_golden", "status": "pending",
             "resolved_at": None,
             "device_ip": "203.0.113.1", "device_hostname": "R1",
             "diff": "--- golden\n+++ running\n-ip route 0.0.0.0 0.0.0.0 1.1.1.1\n"
                     "+ip route 0.0.0.0 0.0.0.0 2.2.2.2\n"}

    @pytest.fixture
    def queue(self, tmp_path, monkeypatch):
        from modules import approval_queue

        path = tmp_path / "approval_queue.json"
        monkeypatch.setattr(approval_queue, "_queue_path", lambda *a: str(path))
        saved = {}
        # A store that keeps what was saved, so a second read sees the first write.
        monkeypatch.setattr(approval_queue, "_load_queue",
                            lambda *a: [dict(e) for e in saved.get("entries",
                                                                   [dict(self.ENTRY)])])
        monkeypatch.setattr(approval_queue, "_save_queue",
                            lambda entries, *a: saved.update(
                                {"entries": [dict(e) for e in entries]}))
        monkeypatch.setattr("modules.inventory.is_stale", lambda ip, ln="": False)
        return approval_queue, saved

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
                            lambda *a: [dict(self.ENTRY, status="approved")])
        assert approval_queue.mark_done("q1")["ok"] is False

    # Today's re-apply route closed a handed-off item only on success (and touched no queue
    # without an approval id); the hand-off left with the AI family (D15) and the route at 7.8
    # (2026-10-17, P7-21). A capture still closes one (`golden._close_handed_off`).


class TestTheHandoffScopesToOneDevice:
    """Approving one device's item must not preview a fleet-wide re-apply."""

    def test_the_preview_honours_the_devices_list(self, monkeypatch):
        """THE restore plan, which every preview runs (today's /golden/restore/preview did until
        it left at 7.8, 2026-10-17)."""
        import routes.golden as golden

        seen = {}

        def _build(list_name, ref, devices=None, un_onboard=None, authorise=None):
            seen["ref"] = ref
            seen["devices"] = devices
            return [], []

        # build_targets is stubbed with a made-up list, so coverage() is too: it
        # reads that list's inventory, and resolving a list that does not exist
        # creates it (get_list_data_dir). Coverage is tested on a real repo in
        # TestTheInventoryIsThePopulation.
        monkeypatch.setattr("modules.nsot.restore.coverage",
                            lambda ln, devices=None, skipped=None: {
                                "inventory_size": 0, "partial": False,
                                "denominator": 0, "scope_words": "in this list"})
        monkeypatch.setattr("modules.nsot.restore.build_targets", _build)

        body = golden.restore_plan("Lab", "HEAD", ["R1"],
                                   advisory_diff="--- golden\n+++ running\n-a\n+b\n",
                                   approval_id="q1")

        assert seen["ref"] == "HEAD"
        assert seen["devices"] == ["R1"]
        # Echoed, never an input to anything.
        assert body["advisory_diff"].startswith("--- golden")
        assert body["approval_id"] == "q1"

    def test_the_advisory_diff_is_not_used_to_build_anything(self, monkeypatch):
        """It is displayed. It is not parsed, rendered, or sent."""
        import inspect

        import routes.golden as golden

        # THE restore plan (`restore_plan`, the v2 device page's and History's Re-apply's), and
        # the only thing done with it there is echoing it back.
        source = inspect.getsource(golden.restore_plan)
        uses = [l.strip() for l in source.splitlines() if "advisory_diff" in l]
        assert uses == ['authorise: dict = None, req=None, advisory_diff: str = "",',
                        '"advisory_diff": advisory_diff,'], uses

class TestBaselineCredentialGaps:
    """Measure whether re-applying would change the credential. Not the name.

    The first version asked whether the ref's secret_ref NAME still existed in
    the credential store. The routers' rotation renamed it
    (user_admin_password -> user_admin_secret) so the name vanished and the
    check fired. The switches' rotation kept user_admin_secret and changed
    only the VALUE — so the name was still there, and four baselines that
    predate all four switch rotations were badged "credentials current".

    That is the dangerous direction, not a cosmetic miss. A secret replaces a
    secret cleanly on those switches (measured), so re-applying such a
    baseline would push the old `secret 5` line, every switch would take it,
    and this tool — holding the new password — would lose SSH to all four. The
    intent-side guard stays silent because the name matches. And every future
    rotation would be invisible too, the routers now being on the same name.
    """

    SECRET5 = ("hostname {h}\n!\n"
               "username admin privilege 15 secret 5 $1$old$hash\n!\nend\n")
    SECRET9 = ("hostname {h}\n!\n"
               "username admin privilege 15 secret 9 $9$new$hash\n!\nend\n")
    PASSWORD = ("hostname {h}\n!\n"
                "username admin privilege 15 password 0 plain\n!\nend\n")

    def _repo(self, tmp_path, at_tag, at_head, intents=None):
        """A repo with a tagged commit and a later HEAD."""
        import subprocess

        import yaml

        repo = tmp_path / "config_repo"
        (repo / "golden").mkdir(parents=True)
        (repo / "host_vars").mkdir(parents=True)

        def commit(message):
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            # --allow-empty: a fixture where HEAD matches the tag is exactly
            # the "nothing changed" case these tests need to cover.
            subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                            "-c", "user.name=t", "commit", "-q",
                            "--allow-empty", "-m", message], check=True)

        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        for host, body in at_tag.items():
            (repo / "golden" / f"{host}.cfg").write_text(
                body.format(h=host), encoding="utf-8")
            (repo / "host_vars" / f"{host}.yml").write_text(
                yaml.safe_dump((intents or {}).get(
                    host, {"secret_refs": ["user_admin_secret"]})),
                encoding="utf-8")
        commit("at the baseline")
        subprocess.run(["git", "-C", str(repo), "tag", "baseline/x"], check=True)

        for host, body in at_head.items():
            (repo / "golden" / f"{host}.cfg").write_text(
                body.format(h=host), encoding="utf-8")
        commit("later")
        return str(repo)

    def test_a_rotation_that_keeps_the_ref_name_is_caught(self, tmp_path,
                                                          monkeypatch):
        """The exact switch case: secret 5 -> secret 9, same ref name."""
        from modules.nsot.restore import baseline_credential_gaps

        repo = self._repo(tmp_path,
                          at_tag={"s1": self.SECRET5, "s2": self.SECRET5},
                          at_head={"s1": self.SECRET9, "s2": self.SECRET9})
        # The name is still in the store — which is why the old check passed.
        monkeypatch.setattr("modules.credentials.get_template_secret",
                            lambda key: "still-here")

        out = baseline_credential_gaps(repo, "baseline/x", "Lab", ["s1", "s2"])
        assert sorted(out["stale"]) == ["s1", "s2"]
        assert out["stale"]["s1"] == {"at_ref": "secret 5", "at_head": "secret 9"}
        assert out["refused"] == [], "the name check finds nothing — that is the point"
        # Before C75 this was the lockout: stale, refused by nothing, and it
        # would land. Now the restore's own credential guard refuses both,
        # asked of a real RestoreTarget, so `silent` is empty.
        assert out["guarded"] == ["s1", "s2"]
        assert out["silent"] == [], "the credential guard refuses a rewrite of a held secret"

    def test_an_unchanged_device_is_not_flagged(self, tmp_path, monkeypatch):
        from modules.nsot.restore import baseline_credential_gaps

        repo = self._repo(tmp_path, at_tag={"s1": self.SECRET9},
                          at_head={"s1": self.SECRET9})
        monkeypatch.setattr("modules.credentials.get_template_secret",
                            lambda key: "v")

        out = baseline_credential_gaps(repo, "baseline/x", "Lab", ["s1"])
        assert out["stale"] == {}
        assert out["silent"] == []

    def test_the_router_case_is_still_caught_and_marked_refused(
            self, tmp_path, monkeypatch):
        """password -> secret, ref renamed: stale AND refused at plan time."""
        from modules.nsot.restore import baseline_credential_gaps

        repo = self._repo(
            tmp_path, at_tag={"r1": self.PASSWORD}, at_head={"r1": self.SECRET9},
            intents={"r1": {"secret_refs": ["user_admin_password"]}})
        monkeypatch.setattr(
            "modules.credentials.get_template_secret",
            lambda key: "" if key.endswith("user_admin_password") else "v")

        out = baseline_credential_gaps(repo, "baseline/x", "Lab", ["r1"])
        assert "r1" in out["stale"]
        assert out["refused"] == ["r1"]
        assert out["silent"] == [], "the guard covers this one"

    def test_a_device_with_no_golden_at_the_ref_is_not_called_safe(
            self, tmp_path, monkeypatch):
        from modules.nsot.restore import baseline_credential_gaps

        repo = self._repo(tmp_path, at_tag={"s1": self.SECRET9},
                          at_head={"s1": self.SECRET9})
        monkeypatch.setattr("modules.credentials.get_template_secret",
                            lambda key: "v")

        out = baseline_credential_gaps(repo, "baseline/x", "Lab",
                                       ["s1", "newcomer"])
        assert out["no_golden"] == ["newcomer"]
        assert "newcomer" not in out["stale"]

    def test_whitespace_alone_is_not_a_credential_change(self, tmp_path,
                                                         monkeypatch):
        from modules.nsot.restore import baseline_credential_gaps

        spaced = ("hostname {h}\n!\n"
                  "username  admin   privilege 15  secret 9   $9$new$hash\n!\nend\n")
        repo = self._repo(tmp_path, at_tag={"s1": self.SECRET9},
                          at_head={"s1": spaced})
        monkeypatch.setattr("modules.credentials.get_template_secret",
                            lambda key: "v")

        out = baseline_credential_gaps(repo, "baseline/x", "Lab", ["s1"])
        assert out["stale"] == {}, "rendering differences are not changes"

    def test_an_added_user_counts_as_a_credential_difference(self, tmp_path,
                                                             monkeypatch):
        """Not only the admin line: any username line."""
        from modules.nsot.restore import baseline_credential_gaps

        extra = self.SECRET9.replace(
            "!\nend\n", "username backup privilege 15 secret 9 $9$b$c\n!\nend\n")
        repo = self._repo(tmp_path, at_tag={"s1": self.SECRET9},
                          at_head={"s1": extra})
        monkeypatch.setattr("modules.credentials.get_template_secret",
                            lambda key: "v")

        out = baseline_credential_gaps(repo, "baseline/x", "Lab", ["s1"])
        assert "s1" in out["stale"]
        # The device holds an account the ref lacks: a re-apply never removes
        # it, and rewrites nothing the device holds, so the guard does not
        # refuse it. Stale, and correctly NOT a lockout.
        assert out["guarded"] == [] and out["silent"] == ["s1"]

    def test_golden_user_lines_distinguishes_absent_from_empty(self, tmp_path):
        from modules.nsot.restore import golden_user_lines

        repo = self._repo(tmp_path, at_tag={"s1": self.SECRET9},
                          at_head={"s1": self.SECRET9})
        assert golden_user_lines(repo, "HEAD", "s1") == [
            "username admin privilege 15 secret 9 $9$new$hash"]
        assert golden_user_lines(repo, "HEAD", "nope") is None

