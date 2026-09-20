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

    def test_editing_the_intent_expires_the_note(self, lab):
        """Self-expiring: what failed is no longer what would be sent."""
        repo, hv = lab
        current = hv.intent_commits(repo, "s4")[0]["sha"]
        hv.record_rolled_back(repo, "s4", current, reason="verify failed")
        assert hv.rolled_back_note(repo, "s4") is not None

        from modules.nsot import repo as R
        hv.write_committed_text(repo, "s4", "hostname: s4\nmtu: 1600\n")
        R.save_host_vars("Lab", ["s4"], message="host_vars: s4 try again")

        assert hv.rolled_back_note(repo, "s4") is None

    def test_reverting_restores_the_previous_intent(self, lab):
        from routes.templatize import revert_committed
        repo, hv = lab
        assert hv.read_committed(repo, "s4")["mtu"] == 9000

        import flask
        app = flask.Flask(__name__)
        with app.test_request_context(json={}):
            response = revert_committed("s4")
        body = response[0].get_json() if isinstance(response, tuple) else response.get_json()

        assert body["ok"] is True
        assert hv.read_committed(repo, "s4")["mtu"] == 1500

    def test_reverting_clears_the_note(self, lab):
        from routes.templatize import revert_committed
        repo, hv = lab
        current = hv.intent_commits(repo, "s4")[0]["sha"]
        hv.record_rolled_back(repo, "s4", current, reason="verify failed")

        import flask
        app = flask.Flask(__name__)
        with app.test_request_context(json={}):
            revert_committed("s4")

        assert hv.rolled_back_note(repo, "s4") is None

    def test_the_revert_is_a_forward_commit(self, lab):
        from modules.nsot import repo as R
        from routes.templatize import revert_committed
        repo, hv = lab

        import flask
        app = flask.Flask(__name__)
        with app.test_request_context(json={}):
            revert_committed("s4")

        rc, subject, _ = R.git(repo, "log", "-1", "--format=%s")
        assert subject.startswith("host_vars: s4 revert to ")
        assert len(hv.intent_commits(repo, "s4")) == 3

    def test_a_single_intent_commit_cannot_be_reverted(self, tmp_path, monkeypatch):
        from modules.nsot import hostvars, repo as R
        from routes.templatize import revert_committed

        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "nmas@localhost",
                            }.get(key, default))
        list_dir = tmp_path / "solo"
        list_dir.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Solo")
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
        repo = str(list_dir / "config_repo")
        R.init_repo(repo)
        hostvars.write_committed_text(repo, "s4", "hostname: s4\n")
        R.save_host_vars("Solo", ["s4"], message="host_vars: s4 initial")

        import flask
        app = flask.Flask(__name__)
        with app.test_request_context(json={}):
            response = revert_committed("s4")
        body, status = response
        assert status == 409
        assert "no previous state" in body.get_json()["error"]


def _config_text():
    import os
    fleet = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")
    with open(os.path.join(fleet, "s1.cfg"), encoding="utf-8") as fh:
        return fh.read()
