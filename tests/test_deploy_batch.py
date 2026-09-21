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


class TestEveryPushedLineIsAttributed:
    """Merge-only pushes every line the render has and the device lacks.

    Not only the line the operator changed. If anyone touched the device since
    the capture, or an earlier intent edit was never deployed, those lines ride
    along in the same push. Merge-only is the right safety property; this is
    its cost, and the cost has to be visible *before* the confirm, not
    discovered in the pushed-command list afterwards.
    """

    @pytest.fixture
    def lab(self, tmp_path, monkeypatch):
        from modules.nsot import hostvars, repo as R
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "nmas@localhost",
                                "nsot_device_tag_retention": 50,
                            }.get(key, default))
        list_dir = tmp_path / "lab"
        list_dir.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(list_dir))
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
        repo = str(list_dir / "config_repo")
        R.init_repo(repo)
        return repo, hostvars, R

    def _commit(self, R, repo, hostvars, doc, subject):
        hostvars.write_committed_text(repo, "s1", doc)
        R.save_host_vars("Lab", ["s1"], message=f"host_vars: s1 {subject}")

    def test_the_previous_intent_is_recoverable(self, lab):
        repo, hostvars, R = lab
        self._commit(R, repo, hostvars, "hostname: s1\nmtu: 1500\n", "initial")
        self._commit(R, repo, hostvars, "hostname: s1\nmtu: 9000\n", "jumbo frames")

        change = hostvars.intent_change(repo, "s1")
        assert change["subject"] == "host_vars: s1 jumbo frames"
        assert change["previous_sha"]
        assert "9000" in change["diff"] and "1500" in change["diff"]

        previous = hostvars.committed_at(repo, "s1", change["previous_sha"])
        assert previous["mtu"] == 1500

    def test_intent_commits_are_listed_newest_first(self, lab):
        repo, hostvars, R = lab
        self._commit(R, repo, hostvars, "hostname: s1\nmtu: 1500\n", "initial")
        self._commit(R, repo, hostvars, "hostname: s1\nmtu: 9000\n", "jumbo frames")

        commits = hostvars.intent_commits(repo, "s1")
        assert [c["subject"] for c in commits] == [
            "host_vars: s1 jumbo frames", "host_vars: s1 initial"]

    def test_a_device_with_no_intent_has_no_history(self, lab):
        repo, hostvars, _R = lab
        assert hostvars.intent_commits(repo, "nosuchdevice") == []
        assert hostvars.intent_change(repo, "nosuchdevice")["sha"] == ""

    def test_the_first_intent_commit_claims_no_attribution(self, lab):
        """Nothing to compare against, so nothing may be called the operator's."""
        from routes.deploy import _attribute_additions

        repo, hostvars, R = lab
        self._commit(R, repo, hostvars, "hostname: s1\nmtu: 1500\n", "initial")

        class _Art:
            platform = "cisco_ios"
            template = "cisco_ios/base.j2"

        result = _attribute_additions(repo, "s1", _Art(), "hostname s1\n",
                                      [" mtu 1500"])
        assert result["from_this_edit"] == []
        assert result["pre_existing"] == [" mtu 1500"]
        assert result["attributable"] is False
        assert "no earlier render" in result["note"]

    def test_an_unreadable_previous_intent_is_reported_not_assumed(self, lab):
        from routes.deploy import _attribute_additions

        repo, hostvars, R = lab
        self._commit(R, repo, hostvars, "hostname: s1\nmtu: 1500\n", "initial")
        self._commit(R, repo, hostvars, "hostname: s1\nmtu: 9000\n", "jumbo")

        class _Art:
            platform = "cisco_ios"
            template = "cisco_ios/nonexistent-template.j2"

        result = _attribute_additions(repo, "s1", _Art(), "hostname s1\n",
                                      [" mtu 9000"])
        assert result["attributable"] is False
        assert result["note"]


class TestApplyRefusesAChangedProgram:
    """Recomputed at apply, compared, refused on mismatch.

    The check lives at apply because that is where it can still prevent
    something. A hash the client sends back proves only what the client saw;
    the server recomputes from current state and compares.
    """

    def test_a_matching_program_is_not_refused(self):
        from modules.nsot.deploy import command_fingerprint, merge_commands
        intended = "interface GigabitEthernet0/1\n description x\n"
        running = "interface GigabitEthernet0/1\n"
        confirmed = command_fingerprint(merge_commands(intended, running))
        now = command_fingerprint(merge_commands(intended, running))
        assert now == confirmed

    def test_an_intent_change_between_confirm_and_apply_is_caught(self):
        from modules.nsot.deploy import command_fingerprint, merge_commands
        running = "interface GigabitEthernet0/1\n"
        confirmed = command_fingerprint(
            merge_commands("interface GigabitEthernet0/1\n description x\n", running))
        now = command_fingerprint(
            merge_commands("interface GigabitEthernet0/1\n description y\n", running))
        assert now != confirmed

    def test_a_device_change_between_confirm_and_apply_is_caught(self):
        """Someone configures the device after the preview and before the push."""
        from modules.nsot.deploy import command_fingerprint, merge_commands
        intended = ("interface GigabitEthernet0/1\n description x\n mtu 9000\n")
        confirmed = command_fingerprint(
            merge_commands(intended, "interface GigabitEthernet0/1\n"))
        now = command_fingerprint(
            merge_commands(intended,
                           "interface GigabitEthernet0/1\n description x\n"))
        assert now != confirmed


class TestRolledBackIntentBlocksAReplan:
    """Rollback restores the device. It says nothing about the intent.

    Without a note, the intent still asserts the change should be there, so the
    next plan computes the same diff and offers to push exactly what just
    failed verification. The tool would loop, confidently, and every attempt
    would look like a fresh proposal rather than a repeat.
    """

    @pytest.fixture
    def lab(self, tmp_path, monkeypatch):
        from modules.nsot import hostvars, repo as R
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "nmas@localhost",
                                "nsot_device_tag_retention": 50,
                            }.get(key, default))
        list_dir = tmp_path / "lab"
        list_dir.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
        repo = str(list_dir / "config_repo")
        R.init_repo(repo)
        hostvars.write_committed_text(repo, "s4", "hostname: s4\nmtu: 1500\n")
        R.save_host_vars("Lab", ["s4"], message="host_vars: s4 initial")
        hostvars.write_committed_text(repo, "s4", "hostname: s4\nmtu: 9000\n")
        R.save_host_vars("Lab", ["s4"], message="host_vars: s4 jumbo")
        return repo, hostvars

    def test_a_note_is_recorded_against_the_current_intent(self, lab):
        repo, hv = lab
        current = hv.intent_commits(repo, "s4")[0]["sha"]
        hv.record_rolled_back(repo, "s4", current, reason="verify failed")

        note = hv.rolled_back_note(repo, "s4")
        assert note["intent_commit"] == current
        assert note["reason"] == "verify failed"

    def test_the_note_blocks_deployability(self, lab):
        from modules.nsot.render_artifact import build_artifact
        repo, hv = lab
        current = hv.intent_commits(repo, "s4")[0]["sha"]
        note = hv.record_rolled_back(repo, "s4", current, reason="verify failed")

        art = build_artifact("s1", _config_text(), "cisco_ios",
                             template="cisco_ios/base.j2",
                             template_approved=True, rolled_back=note)
        assert art.deployable is False
        assert any("rolled back" in r for r in art.blocking_reasons)

    def test_the_reason_says_what_to_do(self, lab):
        from modules.nsot.render_artifact import build_artifact
        repo, hv = lab
        note = hv.record_rolled_back(repo, "s4", "abc123", reason="verify failed")
        art = build_artifact("s1", _config_text(), "cisco_ios",
                             template="cisco_ios/base.j2",
                             template_approved=True, rolled_back=note)
        reason = next(r for r in art.blocking_reasons if "rolled back" in r)
        assert "revert the intent" in reason

    def test_a_different_program_expires_the_note(self, lab):
        """Self-expiring on the PROGRAM, not on an edit.

        This test asserted the opposite until the program key replaced the
        commit-sha key: editing the intent used to clear the block, which is
        wrong whenever the edit leaves the failing change in place.
        """
        repo, hv = lab
        current = hv.intent_commits(repo, "s4")[0]["sha"]
        pushed = ["interface GigabitEthernet0/1", " shutdown", "exit"]
        hv.record_rolled_back(repo, "s4", current, reason="verify failed",
                              commands=pushed)

        assert hv.rolled_back_note(repo, "s4", pushed) is not None

        from modules.nsot import repo as R
        hv.write_committed_text(repo, "s4", "hostname: s4\nmtu: 1600\n")
        R.save_host_vars("Lab", ["s4"], message="host_vars: s4 try again")

        # An edit alone changes nothing; a different program does.
        assert hv.rolled_back_note(repo, "s4", pushed) is not None
        assert hv.rolled_back_note(repo, "s4", []) is None


class TestTheBlockIsContainmentNotEquality:
    """Three keys were tried, and each lifts the block while the failing change
    is still in intent:

    * intent **commit sha** — any later commit clears it
    * **content hash** of the host_vars document — any edit clears it
    * program **equality** — an edit that adds its own sent line makes the
      program different, so the failed ``shutdown`` goes out bundled with it

    The third is the subtle one, and the test that should have caught it passed
    for the wrong reason: it supplied the failed program by hand instead of
    deriving it, so the program never grew.

    Containment is the answer: block while the failed lines are still among the
    lines that would be sent.
    """

    FAILED = ["interface GigabitEthernet0/1", " shutdown", "exit"]
    BUNDLED = ["interface GigabitEthernet0/1", " shutdown", "exit",
               "interface GigabitEthernet0/2", " description uplink", "exit"]
    OTHER_ONLY = ["interface GigabitEthernet0/2", " description uplink", "exit"]

    @pytest.fixture
    def lab(self, tmp_path, monkeypatch):
        from modules.nsot import hostvars, repo as R
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "nmas@localhost",
                                "nsot_device_tag_retention": 50,
                            }.get(key, default))
        list_dir = tmp_path / "lab"
        list_dir.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
        repo = str(list_dir / "config_repo")
        R.init_repo(repo)
        hostvars.write_committed_text(repo, "s4", "hostname: s4\n")
        R.save_host_vars("Lab", ["s4"], message="host_vars: s4 shut Gi0/1")
        note = hostvars.record_rolled_back(
            repo, "s4", hostvars.intent_commits(repo, "s4")[0]["sha"],
            reason="verify failed: intf_up 7->6", commands=self.FAILED)
        return repo, hostvars, R, note

    # (a) ------------------------------------------------------------------
    def test_an_unrelated_edit_that_adds_a_sent_line_stays_blocked(self, lab):
        """The bundled case: a DIFFERENT program that still sends the failure."""
        repo, hv, _R, _note = lab
        assert hv.rolled_back_note(repo, "s4", self.BUNDLED) is not None, (
            "an unrelated edit bundled the rolled-back change back out")

    def test_the_bundled_program_really_is_different(self, lab):
        """Guards the test above from passing for the reason the old one did."""
        from modules.nsot.deploy import command_fingerprint
        assert command_fingerprint(self.BUNDLED) != command_fingerprint(self.FAILED)

    # (b) ------------------------------------------------------------------
    def test_removing_the_failed_line_lifts_it_even_with_other_edits(self, lab):
        repo, hv, _R, _note = lab
        assert hv.rolled_back_note(repo, "s4", self.OTHER_ONLY) is None

    def test_an_empty_program_lifts_it(self, lab):
        repo, hv, _R, _note = lab
        assert hv.rolled_back_note(repo, "s4", []) is None

    def test_the_same_program_stays_blocked(self, lab):
        repo, hv, _R, _note = lab
        assert hv.rolled_back_note(repo, "s4", self.FAILED) is not None

    def test_reordering_does_not_lift_it(self, lab):
        """Order-insensitive: the same lines under the same headers."""
        repo, hv, _R, _note = lab
        reordered = ["interface GigabitEthernet0/2", " description uplink", "exit",
                     "interface GigabitEthernet0/1", " shutdown", "exit"]
        assert hv.rolled_back_note(repo, "s4", reordered) is not None

    def test_the_same_text_under_a_different_header_is_not_the_same_line(self, lab):
        """`shutdown` on Gi0/2 is not the `shutdown` that failed on Gi0/1."""
        repo, hv, _R, _note = lab
        elsewhere = ["interface GigabitEthernet0/2", " shutdown", "exit"]
        assert hv.rolled_back_note(repo, "s4", elsewhere) is None

    # (c) ------------------------------------------------------------------
    def test_an_explicit_retry_lifts_the_block(self, lab):
        repo, hv, _R, _note = lab
        result = hv.authorise_retry(repo, "s4", actor="dustin",
                                    reason="link confirmed unused")
        assert result["ok"] is True
        assert hv.rolled_back_note(repo, "s4", self.FAILED) is None

    def test_the_retry_is_recorded(self, lab):
        repo, hv, _R, _note = lab
        hv.authorise_retry(repo, "s4", actor="dustin", reason="link confirmed unused")
        entries = hv.retry_log(repo)
        assert len(entries) == 1
        assert entries[0]["device"] == "s4"
        assert entries[0]["actor"] == "dustin"
        assert entries[0]["reason"] == "link confirmed unused"
        assert entries[0]["note"]["commands"] == self.FAILED

    def test_a_retry_route_requires_a_reason(self):
        import flask
        from routes.templatize import retry_rolled_back

        app = flask.Flask(__name__)
        with app.test_request_context(json={}):
            _body, status = retry_rolled_back("s4")
        assert status == 400

    def test_retrying_a_device_with_no_note_is_refused(self, lab):
        repo, hv, _R, _note = lab
        assert hv.authorise_retry(repo, "s9", reason="x")["ok"] is False

    def test_a_legacy_note_without_a_program_falls_back_to_the_sha(self, lab):
        import json
        repo, hv, R, _note = lab

        path = hv._rolled_back_path(repo)
        data = json.load(open(path, encoding="utf-8"))
        data["s4"].pop("commands")
        json.dump(data, open(path, "w", encoding="utf-8"), indent=2)

        assert hv.rolled_back_note(repo, "s4", self.FAILED) is not None
        hv.write_committed_text(repo, "s4", "hostname: s4\nmtu: 9000\n")
        R.save_host_vars("Lab", ["s4"], message="host_vars: s4 edit")
        assert hv.rolled_back_note(repo, "s4", self.FAILED) is None


class TestRevertUndoesOneCommitNotASnapshot:
    """Restoring the previous snapshot is the obvious implementation, and it is
    wrong as soon as the commit to undo is not at HEAD.

    With ``A`` shutdown Gi0/1 (rolled back) then ``B`` describe Gi0/2
    (unrelated), "restore the previous committed intent" either restores ``A``
    — which still contains the shutdown — or walks back past it and silently
    discards ``B``. Neither is a revert of ``A``.

    Every revert test written before this had the rolled-back commit at HEAD,
    so none of them could see it.
    """

    @pytest.fixture
    def lab(self, tmp_path, monkeypatch):
        from modules.nsot import hostvars, repo as R
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "nmas@localhost",
                                "nsot_device_tag_retention": 50,
                            }.get(key, default))
        list_dir = tmp_path / "lab"
        list_dir.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
        repo = str(list_dir / "config_repo")
        R.init_repo(repo)
        return repo, hostvars, R

    def _doc(self, gi01_shutdown=False, gi02_description=""):
        import yaml
        return yaml.safe_dump({
            "hostname": "s4",
            "interfaces": [
                {"name": "GigabitEthernet0/1", "shutdown": gi01_shutdown},
                {"name": "GigabitEthernet0/2", "description": gi02_description},
            ],
        }, sort_keys=True)

    def _commit(self, repo, hv, R, doc, subject):
        hv.write_committed_text(repo, "s4", doc)
        R.save_host_vars("Lab", ["s4"], message=f"host_vars: s4 {subject}")

    # (a) ------------------------------------------------------------------
    def test_the_rolled_back_commit_at_head_is_reverted(self, lab):
        repo, hv, R = lab
        self._commit(repo, hv, R, self._doc(), "baseline")
        self._commit(repo, hv, R, self._doc(gi01_shutdown=True), "shut Gi0/1")

        outcome = hv.revert_intent_change(repo, "s4")
        assert outcome["ok"] is True

        current = hv.read_committed(repo, "s4")
        gi01 = next(i for i in current["interfaces"] if i["name"].endswith("0/1"))
        assert gi01["shutdown"] is False

    # (b) ------------------------------------------------------------------
    def test_an_unrelated_commit_on_top_is_kept(self, lab):
        """A undone, B kept — the case a snapshot restore cannot express."""
        repo, hv, R = lab
        self._commit(repo, hv, R, self._doc(), "baseline")
        self._commit(repo, hv, R, self._doc(gi01_shutdown=True), "shut Gi0/1")
        a_sha = hv.intent_commits(repo, "s4")[0]["sha"]
        self._commit(repo, hv, R,
                     self._doc(gi01_shutdown=True, gi02_description="uplink"),
                     "describe Gi0/2")

        outcome = hv.revert_intent_change(repo, "s4", sha=a_sha)
        assert outcome["ok"] is True

        current = hv.read_committed(repo, "s4")
        gi01 = next(i for i in current["interfaces"] if i["name"].endswith("0/1"))
        gi02 = next(i for i in current["interfaces"] if i["name"].endswith("0/2"))
        assert gi01["shutdown"] is False, "the rolled-back change was not undone"
        assert gi02["description"] == "uplink", "the unrelated edit was discarded"

    def test_it_names_what_it_reverted(self, lab):
        repo, hv, R = lab
        self._commit(repo, hv, R, self._doc(), "baseline")
        self._commit(repo, hv, R, self._doc(gi01_shutdown=True), "shut Gi0/1")
        a_sha = hv.intent_commits(repo, "s4")[0]["sha"]
        self._commit(repo, hv, R,
                     self._doc(gi01_shutdown=True, gi02_description="uplink"),
                     "describe Gi0/2")

        outcome = hv.revert_intent_change(repo, "s4", sha=a_sha)
        assert outcome["reverted_paths"] == [
            "interfaces.GigabitEthernet0/1.shutdown"]
        assert len(outcome["kept_later_commits"]) == 1

    # (c) ------------------------------------------------------------------
    def test_a_conflicting_later_edit_is_refused(self, lab):
        repo, hv, R = lab
        self._commit(repo, hv, R, self._doc(), "baseline")
        self._commit(repo, hv, R, self._doc(gi01_shutdown=True), "shut Gi0/1")
        a_sha = hv.intent_commits(repo, "s4")[0]["sha"]
        self._commit(repo, hv, R, self._doc(gi01_shutdown=False), "unshut by hand")

        with pytest.raises(hv.RevertConflict) as exc:
            hv.revert_intent_change(repo, "s4", sha=a_sha)
        assert "GigabitEthernet0/1.shutdown" in str(exc.value)

    def test_the_conflict_says_what_to_do(self, lab):
        repo, hv, R = lab
        self._commit(repo, hv, R, self._doc(), "baseline")
        self._commit(repo, hv, R, self._doc(gi01_shutdown=True), "shut Gi0/1")
        a_sha = hv.intent_commits(repo, "s4")[0]["sha"]
        self._commit(repo, hv, R, self._doc(gi01_shutdown=False), "unshut")

        with pytest.raises(hv.RevertConflict) as exc:
            hv.revert_intent_change(repo, "s4", sha=a_sha)
        assert "make that edit explicitly" in str(exc.value)

    def test_a_conflict_writes_nothing(self, lab):
        repo, hv, R = lab
        self._commit(repo, hv, R, self._doc(), "baseline")
        self._commit(repo, hv, R, self._doc(gi01_shutdown=True), "shut")
        a_sha = hv.intent_commits(repo, "s4")[0]["sha"]
        self._commit(repo, hv, R, self._doc(gi01_shutdown=False), "unshut")
        before = hv.read_committed(repo, "s4")

        with pytest.raises(hv.RevertConflict):
            hv.revert_intent_change(repo, "s4", sha=a_sha)
        assert hv.read_committed(repo, "s4") == before

    def test_the_first_intent_commit_cannot_be_reverted(self, lab):
        repo, hv, R = lab
        self._commit(repo, hv, R, self._doc(), "baseline")
        outcome = hv.revert_intent_change(repo, "s4")
        assert outcome["ok"] is False
        assert "first intent commit" in outcome["error"]

    def test_the_revert_is_a_forward_commit(self, lab):
        from modules.nsot import repo as R2
        repo, hv, R = lab
        self._commit(repo, hv, R, self._doc(), "baseline")
        self._commit(repo, hv, R, self._doc(gi01_shutdown=True), "shut Gi0/1")

        hv.revert_intent_change(repo, "s4")
        R.save_host_vars("Lab", ["s4"], message="host_vars: s4 revert")

        assert len(hv.intent_commits(repo, "s4")) == 3


def _config_text():
    """A real fleet config, for artifacts that only need to render."""
    import os
    fleet = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")
    with open(os.path.join(fleet, "s1.cfg"), encoding="utf-8") as fh:
        return fh.read()


class TestARejectedCommandFailsCapturesAndRollsBack:
    """3B's premise, confirmed on a mocked transport before any device sees it.

    Netmiko does not treat ``% Invalid input detected`` as an error by default,
    so before ``error_pattern`` a cleanly rejected line returned normally: the
    push logged success, verify passed because nothing had changed and
    therefore nothing had broken, and stage 8.5 committed a golden that
    correctly recorded a device which was never configured.

    This asserts the whole chain for each pattern — detection, failure-state
    capture, and rollback — rather than only that the exception is raised.
    """

    REJECTIONS = [
        "% Invalid input detected at '^' marker.",
        "% Incomplete command.",
        '% Ambiguous command: "des"',
        "% Unrecognized host or address.",
    ]

    PUSHED = ["interface GigabitEthernet0/1", " description x", "exit"]

    def _ctx(self):
        import threading
        from modules.pipeline import PipelineContext

        ctx = PipelineContext(
            config_type="template", device_ips=["10.0.0.1"],
            params={}, ip_params_map={},
            selected_devices=[{"ip": "10.0.0.1", "hostname": "s4"}],
            check_devices=[], connections_pool={},
            pool_lock=threading.Lock(), config_id="tpl-s4",
            settle_sleep=lambda _s: None)
        ctx.confirmed_commands = {"10.0.0.1": list(self.PUSHED)}
        return ctx

    @pytest.mark.parametrize("rejection", REJECTIONS)
    def test_the_push_raises_on_each_pattern(self, rejection):
        import re
        from modules.pipeline import IOS_ERROR_PATTERN
        assert re.search(IOS_ERROR_PATTERN, rejection), (
            f"{rejection!r} would be pushed and reported as success")

    @pytest.mark.parametrize("rejection", REJECTIONS)
    def test_capture_then_rollback_run_for_each_pattern(self, rejection):
        """A rejected push must still be read back and undone."""
        import modules.ai_assistant as A
        import modules.connection as C
        import modules.pipeline as P
        from modules.pipeline import _capture_failure_state, _stage_rollback

        ctx = self._ctx()
        # The push failed partway; something may already be on the device.
        ctx.push_results = {"10.0.0.1": {"ok": False, "error": rejection}}
        sent = []

        class _Fresh:
            def send_command(self, _cmd, read_timeout=None):
                # The device kept the interface line, rejected the description.
                return "hostname s4\ninterface GigabitEthernet0/1\n"

        orig = (A._load_pre_change_file, C.with_temp_connection,
                C.get_persistent_connection, P._restore_config)
        A._load_pre_change_file = lambda ip: "hostname s4\n"
        C.with_temp_connection = lambda dev, func: func(_Fresh())
        C.get_persistent_connection = lambda dev, pool, lock: object()
        P._restore_config = lambda conn, cmds: sent.extend(cmds)
        try:
            _capture_failure_state(ctx)
            _stage_rollback(ctx)
        finally:
            (A._load_pre_change_file, C.with_temp_connection,
             C.get_persistent_connection, P._restore_config) = orig

        state = ctx.failure_state["10.0.0.1"]
        assert state["push_ok"] is False
        assert state["device_changed"] is True, (
            "a partially applied push must be reported as a change")
        assert "interface GigabitEthernet0/1" in state["landed"]

        # The description was REJECTED — it is not in what landed — so there is
        # nothing to undo and it is reported instead. Undoing a line the device
        # refused would send a command answering something that never happened,
        # and with error_pattern live that command could itself be refused and
        # take the repair down.
        assert ctx.rollback_not_undone["10.0.0.1"] == [" description x"]
        assert sent == [], sent

    @pytest.mark.parametrize("rejection", REJECTIONS)
    def test_a_line_that_DID_land_is_undone(self, rejection):
        """The other half: a partial push undoes the part that applied."""
        import modules.ai_assistant as A
        import modules.connection as C
        import modules.pipeline as P
        from modules.pipeline import _capture_failure_state, _stage_rollback

        ctx = self._ctx()
        ctx.push_results = {"10.0.0.1": {"ok": False, "error": rejection}}
        sent = []

        class _Fresh:
            def send_command(self, _cmd, read_timeout=None):
                # This time the description landed; something later was refused.
                return ("hostname s4\ninterface GigabitEthernet0/1\n"
                        " description x\n")

        orig = (A._load_pre_change_file, C.with_temp_connection,
                C.get_persistent_connection, P._restore_config)
        A._load_pre_change_file = lambda ip: "hostname s4\n"
        C.with_temp_connection = lambda dev, func: func(_Fresh())
        C.get_persistent_connection = lambda dev, pool, lock: object()
        P._restore_config = lambda conn, cmds: sent.extend(cmds)
        try:
            _capture_failure_state(ctx)
            _stage_rollback(ctx)
        finally:
            (A._load_pre_change_file, C.with_temp_connection,
             C.get_persistent_connection, P._restore_config) = orig

        assert ctx.rollback_performed is True
        assert ctx.rolled_back_ips == ["10.0.0.1"]
        assert sent == ["interface GigabitEthernet0/1",
                        " no description x", "exit"], sent
        assert ctx.rollback_not_undone.get("10.0.0.1") is None

    def test_an_unreadable_capture_undoes_everything_pushed(self):
        """Conservative when you do not know what landed."""
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(self.PUSHED, "hostname s4\n", landed=None)
        assert undo == ["interface GigabitEthernet0/1",
                        " no description x", "exit"]

    def test_a_rejected_push_is_a_rollback_target(self):
        """The filter that once excluded exactly this device."""
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(self.PUSHED, "hostname s4\n")
        assert undo == ["interface GigabitEthernet0/1",
                        " no description x", "exit"]


class TestTheNotesListingEvaluatesApplicability:
    """The listing reported every stored record, not the ones that block.

    ``rolled_back_note()`` without a program returns the raw note — correct for
    reading one, wrong for answering "what is blocked". After 3B the listing
    said s4 was rolled back while the plan said s4 was deployable, because the
    intent had since been reverted and the failing program was no longer what
    would be sent. Two answers to one question, and the operator reads the
    wrong one first.
    """

    FAILED = ["interface Loopback0", " description 3B test", "exit"]

    @pytest.fixture
    def lab(self, tmp_path, monkeypatch):
        from modules.nsot import hostvars, repo as R
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "nmas@localhost",
                            }.get(key, default))
        list_dir = tmp_path / "lab"
        list_dir.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
        repo = str(list_dir / "config_repo")
        R.init_repo(repo)
        hostvars.write_committed_text(repo, "s4", "hostname: s4\n")
        R.save_host_vars("Lab", ["s4"], message="host_vars: s4 initial")
        hostvars.record_rolled_back(
            repo, "s4", hostvars.intent_commits(repo, "s4")[0]["sha"],
            reason="verify failed", commands=self.FAILED)
        return repo, hostvars

    def _listing(self, monkeypatch, program):
        import flask
        import routes.deploy as D
        import routes.templatize as T

        monkeypatch.setattr(D, "_artifact_for", lambda *a: (("art", "cap"), ""))
        monkeypatch.setattr(D, "_current_program", lambda art, cap: program)
        app = flask.Flask(__name__)
        with app.test_request_context(json={}):
            return T.rolled_back().get_json()

    def test_a_note_whose_program_still_applies_is_listed_as_blocking(
            self, lab, monkeypatch):
        body = self._listing(monkeypatch, self.FAILED)
        assert "s4" in body["rolled_back"]
        assert body["rolled_back"]["s4"]["applicability"] == "blocking"
        assert body["blocking_count"] == 1

    def test_a_note_that_no_longer_applies_is_not_listed_as_blocking(
            self, lab, monkeypatch):
        """The 3B case: intent reverted, nothing would be sent."""
        body = self._listing(monkeypatch, [])
        assert body["rolled_back"] == {}
        assert body["blocking_count"] == 0
        assert body["stale"]["s4"]["applicability"] == "no longer applies"

    def test_the_record_is_kept_not_deleted(self, lab, monkeypatch):
        """It is real history, and the retry log refers to it."""
        body = self._listing(monkeypatch, [])
        assert body["stale"]["s4"]["commands"] == self.FAILED
        assert body["stale"]["s4"]["reason"] == "verify failed"

    def test_an_uncomputable_program_is_reported_as_standing(
            self, lab, monkeypatch):
        """Unknown must not read as cleared — the same rule as the capture."""
        import routes.deploy as D
        import routes.templatize as T

        def _boom(*a):
            raise RuntimeError("cannot render")

        monkeypatch.setattr(D, "_artifact_for", lambda *a: (("art", "cap"), ""))
        monkeypatch.setattr(D, "_current_program", _boom)
        import flask
        app = flask.Flask(__name__)
        with app.test_request_context(json={}):
            body = T.rolled_back().get_json()

        assert body["rolled_back"]["s4"]["applicability"] == "unknown"
        assert body["blocking_count"] == 1
