"""tests/test_pipeline.py

Verifies the pipeline stage order enforcement contract defined in
modules/pipeline.py.  Every test here runs without network access, without
Flask, and without any real device connections — all stage *logic* is
exercised through the PipelineRunner interface only.

Run with:  python -m pytest tests/test_pipeline.py -v
"""

import threading
import pytest

from modules.pipeline import (
    PipelineContext,
    PipelineRunner,
    PipelineOrderError,
    PipelineStageError,
    STAGE_NAMES,
    _STAGE_TABLE,
    DIFF_LINE_THRESHOLD,
    _NEIGHBOR_DROP_TOLERANCE,
    _ROUTE_RETENTION_MIN,
    _INTERFACE_DOWN_TOLERANCE,
    _DANGEROUS_PATTERNS,
    _detect_routing_neighbors,
    _capture_operational_snapshot,
    _config_template_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ctx(**overrides) -> PipelineContext:
    """Return a minimal PipelineContext suitable for unit tests.

    ``settle_sleep`` is a no-op here. Phase 3c gave the verify stage real
    settle windows — up to 90 seconds for RIP — and a unit test has no device
    to converge, so without this the suite would spend its time asleep.
    """
    defaults = dict(
        config_type      = "interface",
        device_ips       = ["10.0.0.1"],
        params           = {"interface": "GigabitEthernet0/0"},
        ip_params_map    = {},
        selected_devices = [{"ip": "10.0.0.1", "hostname": "R1"}],
        check_devices    = [{"ip": "10.0.0.1", "hostname": "R1",
                             "username": "admin", "password": "cisco"}],
        connections_pool = {},
        pool_lock        = threading.Lock(),
        config_id        = "test-cfg-001",
        settle_sleep     = lambda _seconds: None,
    )
    defaults.update(overrides)
    return PipelineContext(**defaults)


# ---------------------------------------------------------------------------
# 1. Stage order enforcement
# ---------------------------------------------------------------------------

class TestPipelineOrderEnforcement:
    """PipelineRunner._assert_order must raise PipelineOrderError for out-of-sequence calls."""

    def test_stage_0_is_valid_first_call(self):
        runner = PipelineRunner(_ctx())
        runner._assert_order(0)   # must not raise

    def test_cannot_skip_to_stage_2_before_stage_0(self):
        runner = PipelineRunner(_ctx())
        with pytest.raises(PipelineOrderError):
            runner._assert_order(2)

    def test_cannot_skip_to_deploy_stage(self):
        runner = PipelineRunner(_ctx())
        deploy_idx = STAGE_NAMES.index("deploy")
        with pytest.raises(PipelineOrderError):
            runner._assert_order(deploy_idx)

    def test_cannot_skip_to_verify_stage(self):
        runner = PipelineRunner(_ctx())
        verify_idx = STAGE_NAMES.index("verify")
        with pytest.raises(PipelineOrderError):
            runner._assert_order(verify_idx)

    def test_cannot_repeat_a_completed_stage(self):
        runner = PipelineRunner(_ctx())
        runner._assert_order(0)
        runner._next_expected = 1
        with pytest.raises(PipelineOrderError):
            runner._assert_order(0)  # already completed

    def test_correct_full_sequence_never_raises(self):
        runner = PipelineRunner(_ctx())
        for idx in range(len(STAGE_NAMES)):
            runner._assert_order(idx)
            runner._next_expected = idx + 1

    def test_error_message_names_the_attempted_stage(self):
        runner = PipelineRunner(_ctx())
        with pytest.raises(PipelineOrderError, match="ci_gate"):
            runner._assert_order(STAGE_NAMES.index("ci_gate"))

    def test_error_message_names_the_expected_stage(self):
        runner = PipelineRunner(_ctx())
        with pytest.raises(PipelineOrderError, match="netbox_query"):
            runner._assert_order(STAGE_NAMES.index("ci_gate"))

    def test_error_message_contains_stage_numbers(self):
        runner = PipelineRunner(_ctx())
        with pytest.raises(PipelineOrderError) as exc_info:
            runner._assert_order(STAGE_NAMES.index("deploy"))
        msg = str(exc_info.value)
        assert "#" in msg  # should include "#N/9" formatting

    def test_mid_sequence_skip_raises(self):
        """After completing stages 0 and 1, jumping to stage 3 must fail."""
        runner = PipelineRunner(_ctx())
        runner._assert_order(0)
        runner._next_expected = 1
        runner._assert_order(1)
        runner._next_expected = 2
        with pytest.raises(PipelineOrderError):
            runner._assert_order(3)


# ---------------------------------------------------------------------------
# 2. Stage table contract
# ---------------------------------------------------------------------------

class TestStageTableContract:
    """The stage table must contain the required stages in the required order.

    Phase 3c added ``save_golden`` between verify and audit_log: recording what
    was actually pushed is part of the flow, not a callback afterwards, because
    containerlab nodes are ephemeral and the golden commit is the only durable
    record. The count changed; every ordering and failure-mode invariant below
    did not.
    """

    def test_stage_count(self):
        assert len(_STAGE_TABLE) == 10

    def test_stage_names_cover_all_required_stages(self):
        required = {
            "netbox_query", "template_render", "ci_gate",
            "pre_snapshot", "config_diff", "deploy",
            "post_snapshot", "verify", "save_golden", "audit_log",
        }
        assert set(STAGE_NAMES) == required

    def test_stage_order_matches_spec(self):
        assert STAGE_NAMES[0] == "netbox_query"
        assert STAGE_NAMES[1] == "template_render"
        assert STAGE_NAMES[2] == "ci_gate"
        assert STAGE_NAMES[3] == "pre_snapshot"
        assert STAGE_NAMES[4] == "config_diff"
        assert STAGE_NAMES[5] == "deploy"
        assert STAGE_NAMES[6] == "post_snapshot"
        assert STAGE_NAMES[7] == "verify"
        assert STAGE_NAMES[8] == "save_golden"
        assert STAGE_NAMES[9] == "audit_log"

    def test_audit_log_is_last(self):
        assert STAGE_NAMES[-1] == "audit_log"

    def test_rollback_stages_are_deploy_post_verify(self):
        rollback = {name for name, failure in _STAGE_TABLE if failure == "rollback"}
        assert rollback == {"deploy", "post_snapshot", "verify"}

    def test_pre_deploy_stages_are_abort_not_rollback(self):
        for stage in ("netbox_query", "template_render", "ci_gate", "pre_snapshot", "config_diff"):
            on_failure = next(f for n, f in _STAGE_TABLE if n == stage)
            assert on_failure == "abort", f"{stage} should be 'abort', got '{on_failure}'"

    def test_stage_table_length_matches_stage_names(self):
        assert len(_STAGE_TABLE) == len(STAGE_NAMES)

    def test_golden_save_follows_verify(self):
        """It must never record config that is about to be rolled back."""
        assert STAGE_NAMES.index("save_golden") > STAGE_NAMES.index("verify")

    def test_golden_save_does_not_roll_back(self):
        """The config is on the device either way.

        Failing to *record* a successful deploy is worth reporting; it is not
        worth rolling that deploy back over.
        """
        on_failure = next(f for n, f in _STAGE_TABLE if n == "save_golden")
        assert on_failure == "continue"


# ---------------------------------------------------------------------------
# 3. CI gate invariant — no SSH before stage 3
# ---------------------------------------------------------------------------

class TestCIGateInvariant:
    """SSH connections (Stage 4+) must be unreachable before ci_gate completes."""

    def test_ci_gate_precedes_pre_snapshot(self):
        ci_idx   = STAGE_NAMES.index("ci_gate")
        snap_idx = STAGE_NAMES.index("pre_snapshot")
        assert ci_idx < snap_idx

    def test_pre_snapshot_precedes_deploy(self):
        snap_idx   = STAGE_NAMES.index("pre_snapshot")
        deploy_idx = STAGE_NAMES.index("deploy")
        assert snap_idx < deploy_idx

    def test_cannot_jump_to_pre_snapshot_skipping_ci_gate(self):
        """Advance past netbox_query and template_render but NOT ci_gate, then try pre_snapshot."""
        runner = PipelineRunner(_ctx())
        runner._next_expected = STAGE_NAMES.index("ci_gate")   # simulating: 0+1 done
        with pytest.raises(PipelineOrderError, match="ci_gate"):
            runner._assert_order(STAGE_NAMES.index("pre_snapshot"))

    def test_cannot_deploy_without_pre_snapshot(self):
        """Advance through ci_gate but NOT pre_snapshot, then try deploy."""
        runner = PipelineRunner(_ctx())
        runner._next_expected = STAGE_NAMES.index("pre_snapshot")
        with pytest.raises(PipelineOrderError, match="pre_snapshot"):
            runner._assert_order(STAGE_NAMES.index("deploy"))


class TestCIGateJenkinsBlock:
    """
    CI gate reads last stored pipeline status — fast, no blocking.
    Blocks only when a pipeline is actively FAILING.  Never triggers builds.
    """

    def _run_ci_gate(self, monkeypatch,
                     rows: list[dict],
                     jenkins_url: str = "http://jenkins:8080"):
        """Patch jenkins_runner.get_current_list_pipeline_status and run the gate."""
        from modules.pipeline import _stage_ci_gate
        import sys, types

        fake_jr = types.ModuleType("modules.jenkins_runner")
        fake_jr.load_config = lambda: {"jenkins_url": jenkins_url}
        fake_jr.get_current_list_pipeline_status = lambda _cfg: {
            "registered": rows, "list_name": "testlist"
        }
        sys.modules["modules.jenkins_runner"] = fake_jr

        fake_cr = types.ModuleType("modules.check_runner")
        fake_cr.CHECKS = {"interface": lambda c, d: None}
        sys.modules["modules.check_runner"] = fake_cr

        ctx = _ctx()
        ctx.rendered_commands = {"10.0.0.1": ["interface GigabitEthernet0/0"]}
        try:
            _stage_ci_gate(ctx)
            return ctx
        finally:
            sys.modules.pop("modules.jenkins_runner", None)
            sys.modules.pop("modules.check_runner", None)

    # ── Core behaviour ───────────────────────────────────────────────────

    def test_failing_pipeline_blocks_deploy(self, monkeypatch):
        from modules.pipeline import PipelineStageError
        rows = [{"job_name": "nmas-list-ospf", "last_result": "FAILURE",
                 "exists_on_server": True}]
        with pytest.raises(PipelineStageError, match="FAILING"):
            self._run_ci_gate(monkeypatch, rows)

    def test_failing_pipeline_names_the_job(self, monkeypatch):
        from modules.pipeline import PipelineStageError
        rows = [{"job_name": "nmas-list-bgp", "last_result": "FAILURE",
                 "exists_on_server": True}]
        with pytest.raises(PipelineStageError, match="nmas-list-bgp"):
            self._run_ci_gate(monkeypatch, rows)

    def test_multiple_failing_pipelines_all_named(self, monkeypatch):
        from modules.pipeline import PipelineStageError
        rows = [
            {"job_name": "nmas-list-ospf", "last_result": "FAILURE", "exists_on_server": True},
            {"job_name": "nmas-list-bgp",  "last_result": "FAILURE", "exists_on_server": True},
        ]
        with pytest.raises(PipelineStageError) as exc_info:
            self._run_ci_gate(monkeypatch, rows)
        msg = str(exc_info.value)
        assert "nmas-list-ospf" in msg
        assert "nmas-list-bgp" in msg

    def test_all_passing_allows_deploy(self, monkeypatch):
        rows = [{"job_name": "nmas-list-ospf", "last_result": "SUCCESS",
                 "exists_on_server": True}]
        ctx = self._run_ci_gate(monkeypatch, rows)
        assert ctx.ci_passed is True

    def test_no_pipelines_registered_passes(self, monkeypatch):
        ctx = self._run_ci_gate(monkeypatch, rows=[])
        assert ctx.ci_passed is True

    def test_jenkins_not_configured_passes(self, monkeypatch):
        ctx = self._run_ci_gate(monkeypatch, rows=[], jenkins_url="")
        assert ctx.ci_passed is True

    def test_failed_job_not_on_server_not_blocking(self, monkeypatch):
        """Job registered locally but missing from Jenkins server is not a blocker."""
        rows = [{"job_name": "nmas-list-ospf", "last_result": "FAILURE",
                 "exists_on_server": False}]
        ctx = self._run_ci_gate(monkeypatch, rows)
        assert ctx.ci_passed is True

    def test_gate_does_not_call_run_checks(self, monkeypatch):
        """Gate must read status only — never trigger builds."""
        from modules.pipeline import _stage_ci_gate
        import sys, types

        triggered = []
        fake_jr = types.ModuleType("modules.jenkins_runner")
        fake_jr.load_config = lambda: {"jenkins_url": "http://j:8080"}
        fake_jr.get_current_list_pipeline_status = lambda _cfg: {"registered": []}
        fake_jr.run_checks = lambda: triggered.append("BAD") or {}
        sys.modules["modules.jenkins_runner"] = fake_jr
        fake_cr = types.ModuleType("modules.check_runner")
        fake_cr.CHECKS = {}
        sys.modules["modules.check_runner"] = fake_cr

        ctx = _ctx()
        ctx.rendered_commands = {"10.0.0.1": ["interface GigabitEthernet0/0"]}
        try:
            _stage_ci_gate(ctx)
        finally:
            sys.modules.pop("modules.jenkins_runner", None)
            sys.modules.pop("modules.check_runner", None)

        assert not triggered, "run_checks() must NOT be called in the CI gate"


# ---------------------------------------------------------------------------
# 4. Rollback contract
# ---------------------------------------------------------------------------

class TestRollbackContract:
    """Stages 6-8 must trigger rollback; stages 1-5 must not."""

    def test_deploy_on_failure_is_rollback(self):
        assert _STAGE_TABLE[STAGE_NAMES.index("deploy")][1] == "rollback"

    def test_post_snapshot_on_failure_is_rollback(self):
        assert _STAGE_TABLE[STAGE_NAMES.index("post_snapshot")][1] == "rollback"

    def test_verify_on_failure_is_rollback(self):
        assert _STAGE_TABLE[STAGE_NAMES.index("verify")][1] == "rollback"

    def test_pre_snapshot_on_failure_is_abort(self):
        assert _STAGE_TABLE[STAGE_NAMES.index("pre_snapshot")][1] == "abort"

    def test_ci_gate_on_failure_is_abort(self):
        assert _STAGE_TABLE[STAGE_NAMES.index("ci_gate")][1] == "abort"

    def test_config_diff_on_failure_is_abort(self):
        assert _STAGE_TABLE[STAGE_NAMES.index("config_diff")][1] == "abort"


# ---------------------------------------------------------------------------
# 5. PipelineContext state tracking
# ---------------------------------------------------------------------------

class TestPipelineContextState:

    def test_default_final_status_is_pending(self):
        assert _ctx().final_status == "pending"

    def test_canary_ip_returns_first_device(self):
        ctx = _ctx(device_ips=["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        assert ctx.canary_ip() == "10.0.0.1"

    def test_fleet_ips_excludes_canary(self):
        ctx = _ctx(device_ips=["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        assert ctx.fleet_ips() == ["10.0.0.2", "10.0.0.3"]

    def test_canary_is_none_when_no_devices(self):
        assert _ctx(device_ips=[]).canary_ip() is None

    def test_fleet_is_empty_with_single_device(self):
        assert _ctx(device_ips=["10.0.0.1"]).fleet_ips() == []

    def test_stages_completed_and_failed_are_disjoint(self):
        ctx = _ctx()
        ctx.stages_completed.append("netbox_query")
        ctx.stages_failed.append("template_render")
        assert set(ctx.stages_completed).isdisjoint(set(ctx.stages_failed))

    def test_device_params_falls_back_to_shared_params(self):
        ctx = _ctx(params={"shared": True}, ip_params_map={})
        assert ctx.device_params("10.0.0.1") == {"shared": True}

    def test_device_params_uses_per_device_override(self):
        ctx = _ctx(
            params         = {"shared": True},
            ip_params_map  = {"10.0.0.1": {"per_device": True}},
        )
        assert ctx.device_params("10.0.0.1") == {"per_device": True}
        assert ctx.device_params("10.0.0.99") == {"shared": True}


# ---------------------------------------------------------------------------
# 6. Safety constants
# ---------------------------------------------------------------------------

class TestSafetyConstants:
    """Key safety constants must be set to meaningful values."""

    def test_diff_threshold_is_positive(self):
        assert DIFF_LINE_THRESHOLD > 0

    def test_neighbor_drop_tolerance_is_non_negative(self):
        assert _NEIGHBOR_DROP_TOLERANCE >= 0

    def test_interface_down_tolerance_is_non_negative(self):
        assert _INTERFACE_DOWN_TOLERANCE >= 0

    def test_route_retention_min_is_fraction(self):
        assert 0.0 < _ROUTE_RETENTION_MIN <= 1.0

    def test_dangerous_patterns_list_is_non_empty(self):
        assert len(_DANGEROUS_PATTERNS) > 0

    def test_shutdown_is_dangerous(self):
        assert any(p.search(" shutdown") for p in _DANGEROUS_PATTERNS)

    def test_reload_is_dangerous(self):
        assert any(p.search(" reload") for p in _DANGEROUS_PATTERNS)

    def test_no_router_ospf_is_dangerous(self):
        assert any(p.search("no router ospf 1") for p in _DANGEROUS_PATTERNS)

    def test_ordinary_interface_command_is_not_dangerous(self):
        cmd = "interface GigabitEthernet0/0"
        assert not any(p.search(cmd) for p in _DANGEROUS_PATTERNS)

    def test_ip_address_command_is_not_dangerous(self):
        cmd = " ip address 10.0.0.1 255.255.255.0"
        assert not any(p.search(cmd) for p in _DANGEROUS_PATTERNS)


# ---------------------------------------------------------------------------
# 7. Audit log — always-runs guarantee
# ---------------------------------------------------------------------------

class TestAuditLogGuarantee:
    """audit_log must be the last stage and must always appear in the sequence."""

    def test_audit_log_is_always_the_final_stage(self):
        """The invariant is that audit runs last, not that it sits at index 8.

        Pinning the index made this test fail when save_golden was inserted
        before it, even though the guarantee it exists to protect was untouched.
        """
        assert STAGE_NAMES[-1] == "audit_log"
        assert STAGE_NAMES.index("audit_log") == len(STAGE_NAMES) - 1

    def test_all_other_stages_precede_audit_log(self):
        audit_idx = STAGE_NAMES.index("audit_log")
        for name in STAGE_NAMES:
            if name != "audit_log":
                assert STAGE_NAMES.index(name) < audit_idx


# ---------------------------------------------------------------------------
# 8. No-op and threshold abort conditions
# ---------------------------------------------------------------------------

class TestDiffAbortConditions:
    """_stage_config_diff must abort correctly for no-op and threshold-exceeded cases."""

    def _make_ctx_with_pre_snapshot(self, cmds: list[str], running_cfg: str) -> PipelineContext:
        ctx = _ctx()
        ctx.rendered_commands = {"10.0.0.1": cmds}
        ctx.pre_snapshots     = {"10.0.0.1": {"running_config": running_cfg}}
        return ctx

    def test_all_commands_already_present_raises(self):
        from modules.pipeline import _stage_config_diff
        running = "interface GigabitEthernet0/0\n ip address 10.0.0.1 255.255.255.0\n"
        cmds    = ["interface GigabitEthernet0/0", " ip address 10.0.0.1 255.255.255.0"]
        ctx     = self._make_ctx_with_pre_snapshot(cmds, running)
        with pytest.raises(PipelineStageError, match="no-op"):
            _stage_config_diff(ctx)

    def test_exceeding_threshold_raises(self):
        from modules.pipeline import _stage_config_diff
        # Generate commands that are NOT in the running config, exceeding the threshold.
        cmds    = [f"ip route 192.168.{i}.0 255.255.255.0 10.0.0.1"
                   for i in range(DIFF_LINE_THRESHOLD + 5)]
        ctx     = self._make_ctx_with_pre_snapshot(cmds, "! empty config\n")
        with pytest.raises(PipelineStageError, match="threshold"):
            _stage_config_diff(ctx)

    def test_new_commands_within_threshold_passes(self):
        from modules.pipeline import _stage_config_diff
        cmds    = ["ip route 192.168.0.0 255.255.255.0 10.0.0.1"]
        ctx     = self._make_ctx_with_pre_snapshot(cmds, "! empty config\n")
        _stage_config_diff(ctx)   # must not raise
        assert ctx.diff_summary["10.0.0.1"]["new_cmds"] == 1
        assert ctx.diff_summary["10.0.0.1"]["no_op"] is False

    def test_missing_running_config_skips_diff(self):
        from modules.pipeline import _stage_config_diff
        ctx = _ctx()
        ctx.rendered_commands = {"10.0.0.1": ["interface GigabitEthernet0/0"]}
        ctx.pre_snapshots     = {"10.0.0.1": {}}  # no running_config key
        _stage_config_diff(ctx)  # must not raise
        assert ctx.diff_summary["10.0.0.1"].get("skipped") is True


# ---------------------------------------------------------------------------
# 9. Template path helper
# ---------------------------------------------------------------------------

class TestProtocolAgnosticVerify:
    """_stage_verify must work correctly regardless of routing protocol."""

    def _make_snap(self, protocol: str, neighbors: int, routes: int, intf_up: int) -> dict:
        return {
            "routing_neighbors": {"protocol": protocol, "count": neighbors},
            "routes":            {"total_count": routes},
            "interfaces":        {"up_count": intf_up, "down_count": 0},
        }

    def _run_verify(self, pre_snap: dict, post_snap: dict):
        from modules.pipeline import _stage_verify
        ctx = _ctx()
        ctx.pre_snapshots  = {"10.0.0.1": pre_snap}
        ctx.post_snapshots = {"10.0.0.1": post_snap}
        _stage_verify(ctx)
        return ctx.verify_result["10.0.0.1"]

    def test_ospf_neighbor_loss_fails(self):
        from modules.pipeline import _stage_verify
        ctx = _ctx()
        ctx.pre_snapshots  = {"10.0.0.1": self._make_snap("ospf", 4, 100, 5)}
        ctx.post_snapshots = {"10.0.0.1": self._make_snap("ospf", 1, 100, 5)}
        with pytest.raises(PipelineStageError, match="ospf"):
            _stage_verify(ctx)

    def test_eigrp_neighbor_loss_fails(self):
        from modules.pipeline import _stage_verify
        ctx = _ctx()
        ctx.pre_snapshots  = {"10.0.0.1": self._make_snap("eigrp", 3, 50, 4)}
        ctx.post_snapshots = {"10.0.0.1": self._make_snap("eigrp", 0, 50, 4)}
        with pytest.raises(PipelineStageError, match="eigrp"):
            _stage_verify(ctx)

    def test_bgp_neighbor_loss_fails(self):
        from modules.pipeline import _stage_verify
        ctx = _ctx()
        ctx.pre_snapshots  = {"10.0.0.1": self._make_snap("bgp", 2, 200, 3)}
        ctx.post_snapshots = {"10.0.0.1": self._make_snap("bgp", 0, 200, 3)}
        with pytest.raises(PipelineStageError, match="bgp"):
            _stage_verify(ctx)

    def test_no_routing_protocol_skips_neighbor_check(self):
        """A pure L2 switch or static-only router (count=-1) should not fail verify."""
        result = self._run_verify(
            self._make_snap("none", -1, 5, 6),
            self._make_snap("none", -1, 5, 6),
        )
        assert result["ok"] is True

    def test_interface_going_down_fails(self):
        from modules.pipeline import _stage_verify
        ctx = _ctx()
        ctx.pre_snapshots  = {"10.0.0.1": self._make_snap("ospf", 2, 50, 5)}
        ctx.post_snapshots = {"10.0.0.1": self._make_snap("ospf", 2, 50, 3)}
        with pytest.raises(PipelineStageError, match="[Ii]nterface"):
            _stage_verify(ctx)

    def test_route_table_shrink_fails(self):
        from modules.pipeline import _stage_verify
        ctx = _ctx()
        ctx.pre_snapshots  = {"10.0.0.1": self._make_snap("ospf", 2, 100, 5)}
        ctx.post_snapshots = {"10.0.0.1": self._make_snap("ospf", 2,  50, 5)}
        with pytest.raises(PipelineStageError, match="[Rr]oute"):
            _stage_verify(ctx)

    def test_stable_network_passes_all_checks(self):
        result = self._run_verify(
            self._make_snap("ospf", 4, 150, 6),
            self._make_snap("ospf", 4, 152, 6),
        )
        assert result["ok"] is True
        assert result["issues"] == []

    def test_verify_result_records_protocol_name(self):
        result = self._run_verify(
            self._make_snap("isis", 2, 80, 4),
            self._make_snap("isis", 2, 80, 4),
        )
        assert result["pre"]["routing_protocol"] == "isis"
        assert result["post"]["routing_protocol"] == "isis"

    def test_unknown_baseline_skips_neighbor_check(self):
        """If pre-snapshot count is -1 (protocol not detected), neighbor check is skipped."""
        result = self._run_verify(
            self._make_snap("none", -1, 100, 5),
            self._make_snap("ospf",  3, 100, 5),
        )
        # No neighbor issue — the pre-baseline was unknown so we can't penalise
        neighbor_issues = [i for i in result["issues"] if "neighbor" in i.lower()]
        assert neighbor_issues == []

    def test_route_check_skipped_for_ospf_config_type(self):
        """Adding OSPF may temporarily shrink the route table as adjacencies form —
        the retention check must not trigger a false rollback."""
        from modules.pipeline import _stage_verify
        ctx = _ctx(config_type="ospf")
        # Route table appears to halve during OSPF convergence
        ctx.pre_snapshots  = {"10.0.0.1": self._make_snap("ospf", 4, 100, 5)}
        ctx.post_snapshots = {"10.0.0.1": self._make_snap("ospf", 4,  40, 5)}
        _stage_verify(ctx)   # must not raise
        route_issues = [i for i in ctx.verify_result["10.0.0.1"]["issues"]
                        if "route" in i.lower()]
        assert route_issues == []

    def test_route_check_skipped_for_bgp_config_type(self):
        from modules.pipeline import _stage_verify
        ctx = _ctx(config_type="bgp")
        ctx.pre_snapshots  = {"10.0.0.1": self._make_snap("bgp", 2, 200, 4)}
        ctx.post_snapshots = {"10.0.0.1": self._make_snap("bgp", 2,  80, 4)}
        _stage_verify(ctx)  # must not raise

    def test_route_check_skipped_via_param_flag(self):
        """params['skip_route_check'] = True bypasses retention check for any config type."""
        from modules.pipeline import _stage_verify
        ctx = _ctx(config_type="interface", params={"skip_route_check": True})
        ctx.pre_snapshots  = {"10.0.0.1": self._make_snap("none", -1, 200, 4)}
        ctx.post_snapshots = {"10.0.0.1": self._make_snap("none", -1,  10, 4)}
        _stage_verify(ctx)  # must not raise

    def test_route_check_still_fires_for_interface_config_type(self):
        """Configuring an interface should not install routes, so retention is still checked."""
        from modules.pipeline import _stage_verify
        ctx = _ctx(config_type="interface")
        ctx.pre_snapshots  = {"10.0.0.1": self._make_snap("none", -1, 100, 5)}
        ctx.post_snapshots = {"10.0.0.1": self._make_snap("none", -1,  50, 5)}
        with pytest.raises(PipelineStageError, match="[Rr]oute"):
            _stage_verify(ctx)


class TestTemplatePath:

    def test_returns_string_path(self):
        path = _config_template_path("interface")
        assert isinstance(path, str)
        assert path.endswith("interface.j2")

    def test_path_ends_in_config_templates_dir(self):
        path = _config_template_path("bgp")
        assert "config_templates" in path.replace("\\", "/")


class TestPreRenderedCommandsAreNotOverwritten:
    """The NSoT deploy path decides its own command list, outside the pipeline.

    It has to: the operator confirmed that exact list, and it is the only thing
    that may be sent. Stage 2 overwrote ``ctx.rendered_commands``
    unconditionally, so a caller that populated it beforehand had its work
    discarded — and then failed on ``Unknown config type: 'template'``.

    Re-rendering would break the confirm guarantee even if it succeeded: the
    pipeline would decide what to send after the operator approved something
    else.
    """

    def _ctx(self, **kw):
        import threading
        from modules.pipeline import PipelineContext
        base = dict(config_type="template", device_ips=["203.0.113.24"],
                    params={}, ip_params_map={},
                    selected_devices=[{"ip": "203.0.113.24", "hostname": "s4"}],
                    check_devices=[], connections_pool={},
                    pool_lock=threading.Lock(), config_id="tpl-s4")
        base.update(kw)
        return PipelineContext(**base)

    def test_pre_rendered_commands_survive_stage_two(self):
        from modules.pipeline import _stage_template_render

        commands = ["interface GigabitEthernet0/1", " description x", "exit"]
        ctx = self._ctx()
        ctx.confirmed_commands = {"203.0.113.24": commands}

        _stage_template_render(ctx)
        assert ctx.rendered_commands == {"203.0.113.24": commands}

    def test_an_unknown_config_type_no_longer_matters(self):
        """It was fatal only because the stage insisted on rendering."""
        from modules.pipeline import _stage_template_render

        ctx = self._ctx(config_type="not-a-real-generator")
        ctx.confirmed_commands = {"203.0.113.24": ["hostname s4"]}
        _stage_template_render(ctx)
        assert ctx.rendered_commands == {"203.0.113.24": ["hostname s4"]}

    def test_pre_rendered_with_no_commands_is_refused(self):
        """Never quietly render a substitute for a confirmed list."""
        from modules.pipeline import PipelineStageError, _stage_template_render

        ctx = self._ctx()
        ctx.confirmed_commands = {}
        with pytest.raises(PipelineStageError) as exc:
            _stage_template_render(ctx)
        assert "operator confirmed" in str(exc.value)

    def test_the_normal_path_still_renders(self):
        """confirmed_commands defaults to None; existing callers are untouched."""
        ctx = self._ctx()
        assert ctx.confirmed_commands is None
        ctx.rendered_commands = {"203.0.113.24": ["hostname s4"]}
        assert ctx.rendered_commands == {"203.0.113.24": ["hostname s4"]}

    def test_assigning_over_a_confirmed_list_raises(self):
        """The reason this is derived rather than a pass-through flag: a flag
        is a convention, and the convention is what failed twice."""
        from modules.pipeline import ConfirmedCommandsOverwritten

        ctx = self._ctx()
        ctx.confirmed_commands = {"203.0.113.24": ["interface Gi0/1"]}
        with pytest.raises(ConfirmedCommandsOverwritten):
            ctx.rendered_commands = {"203.0.113.24": ["something else"]}
        assert ctx.rendered_commands == {"203.0.113.24": ["interface Gi0/1"]}


class TestRollbackFiresOnAMidPushFailure:
    """The net itself, which did not fire when it was needed.

    Two independent bugs, both of which excluded exactly the case rollback
    exists for:

    * the trigger required ``"deploy" in stages_completed`` — false precisely
      when the *deploy stage* is the thing that failed
    * the target list was ``push_results`` filtered to ``ok`` — so a device
      whose push died mid-stream was excluded, though a partial push is the
      state most in need of restoring
    """

    def _ctx_with_push(self, ok, skipped=False):
        ctx = _ctx()
        ctx.push_results = {"10.0.0.1": {"ok": ok, "skipped": skipped}}
        return ctx

    def test_a_failed_push_is_a_rollback_target(self):
        """And it is sent the INVERSE of what was pushed, not a replay."""
        from modules.pipeline import _stage_rollback

        ctx = self._ctx_with_push(ok=False)
        ctx.confirmed_commands = {"10.0.0.1": ["interface GigabitEthernet0/0",
                                               " shutdown", "exit"]}
        sent = []
        import modules.ai_assistant as A
        import modules.connection as C
        import modules.pipeline as P

        original, orig_load, orig_conn = (P._restore_config,
                                          A._load_pre_change_file,
                                          C.get_persistent_connection)
        P._restore_config = lambda conn, cmds: sent.extend(cmds)
        A._load_pre_change_file = lambda ip: (
            "interface GigabitEthernet0/0\n description core\n")
        C.get_persistent_connection = lambda dev, pool, lock: object()
        try:
            _stage_rollback(ctx)
        finally:
            P._restore_config = original
            A._load_pre_change_file = orig_load
            C.get_persistent_connection = orig_conn

        assert sent == ["interface GigabitEthernet0/0", " no shutdown", "exit"], (
            f"a replay cannot undo a shutdown; got {sent}")
        assert ctx.rollback_performed is True
        assert ctx.rolled_back_ips == ["10.0.0.1"]
        assert ctx.rollback_commands["10.0.0.1"] == sent

    def test_a_skipped_device_is_not_a_rollback_target(self):
        from modules.pipeline import _stage_rollback

        ctx = self._ctx_with_push(ok=True, skipped=True)
        import modules.pipeline as P
        restored = []
        original = P._restore_config
        P._restore_config = lambda conn, cfg: restored.append(cfg)
        try:
            _stage_rollback(ctx)
        finally:
            P._restore_config = original
        assert restored == []

    def test_the_trigger_no_longer_requires_a_completed_deploy(self):
        """The condition that made a mid-push failure roll back nothing."""
        import inspect
        from modules.pipeline import PipelineRunner

        source = inspect.getsource(PipelineRunner.run)
        assert 'on_failure == "rollback" and "deploy" in self.ctx.stages_completed' \
            not in source
        assert "attempted" in source


class TestFailureStateIsCaptured:
    """"The push failed" and "the device is unchanged" are different claims.

    ``send_config_set`` raising means something was already sent. The first
    real deploy left ``description NSoT-managed b`` on a device and reported
    only a Netmiko pattern timeout; a human found the corruption by going and
    looking, with the pipeline's own connection still open.
    """

    def _run_capture(self, running_after, pre="hostname R1\n"):
        """Captures over a FRESH connection, never the pooled one."""
        from modules.pipeline import _capture_failure_state
        import modules.ai_assistant as A
        import modules.connection as C

        ctx = _ctx()
        ctx.push_results = {"10.0.0.1": {"ok": False, "error": "boom"}}

        class _Conn:
            def send_command(self, _cmd):
                return running_after

        orig_load = A._load_pre_change_file
        orig_temp = C.with_temp_connection
        A._load_pre_change_file = lambda ip: pre
        C.with_temp_connection = lambda dev, func: func(_Conn())
        try:
            _capture_failure_state(ctx)
        finally:
            A._load_pre_change_file = orig_load
            C.with_temp_connection = orig_temp
        return ctx.failure_state["10.0.0.1"]

    def test_it_does_not_use_the_pooled_connection(self):
        """The pooled session is the one that just failed."""
        from modules.pipeline import _capture_failure_state
        import modules.ai_assistant as A
        import modules.connection as C

        ctx = _ctx()
        ctx.push_results = {"10.0.0.1": {"ok": False}}
        used_pool = []

        class _Conn:
            def send_command(self, _cmd):
                return "hostname R1\n"

        orig = (A._load_pre_change_file, C.with_temp_connection,
                C.get_persistent_connection)
        A._load_pre_change_file = lambda ip: "hostname R1\n"
        C.with_temp_connection = lambda dev, func: func(_Conn())
        C.get_persistent_connection = lambda *a: used_pool.append(1)
        try:
            _capture_failure_state(ctx)
        finally:
            (A._load_pre_change_file, C.with_temp_connection,
             C.get_persistent_connection) = orig

        assert used_pool == [], "the capture reused the failed pooled session"

    def test_a_failed_capture_drops_the_pooled_connection(self):
        """A fresh connection could not read it, so the pooled one is no
        better — and the rollback is the next thing to use it."""
        from modules.pipeline import _capture_failure_state
        import modules.connection as C

        ctx = _ctx()
        ctx.push_results = {"10.0.0.1": {"ok": False}}
        closed = []

        def _boom(dev, func):
            raise OSError("Pattern not detected")

        orig = (C.with_temp_connection, C.close_persistent_connection)
        C.with_temp_connection = _boom
        C.close_persistent_connection = lambda ip, pool, lock: closed.append(ip)
        try:
            _capture_failure_state(ctx)
        finally:
            (C.with_temp_connection, C.close_persistent_connection) = orig

        assert closed == ["10.0.0.1"]
        assert ctx.failure_state["10.0.0.1"]["device_changed"] is None

    def test_a_partial_write_is_reported_as_a_change(self):
        entry = self._run_capture("hostname R1\n description NSoT-managed b\n")
        assert entry["device_changed"] is True
        assert entry["landed"] == [" description NSoT-managed b"]
        assert entry["push_ok"] is False

    def test_an_untouched_device_is_reported_as_unchanged(self):
        entry = self._run_capture("hostname R1\n")
        assert entry["device_changed"] is False
        assert entry["landed"] == []

    def test_a_removed_line_is_reported_too(self):
        entry = self._run_capture("", pre="hostname R1\nip routing\n")
        assert sorted(entry["lost"]) == ["hostname R1", "ip routing"]

    def test_an_unreadable_device_says_so_rather_than_unchanged(self):
        from modules.pipeline import _capture_failure_state
        import modules.connection as C

        ctx = _ctx()
        ctx.push_results = {"10.0.0.1": {"ok": False}}
        orig = (C.with_temp_connection, C.close_persistent_connection)

        def _boom(dev, func):
            raise OSError("unreachable")

        C.with_temp_connection = _boom
        C.close_persistent_connection = lambda *a: None
        try:
            _capture_failure_state(ctx)
        finally:
            (C.with_temp_connection, C.close_persistent_connection) = orig

        entry = ctx.failure_state["10.0.0.1"]
        assert entry["device_changed"] is None, "unknown must not read as unchanged"
        assert "unreachable" in entry["error"]

    def test_capture_runs_before_rollback(self):
        """Or the repair destroys the evidence."""
        import inspect
        from modules.pipeline import PipelineRunner

        source = inspect.getsource(PipelineRunner.run)
        assert source.index("_capture_failure_state") < source.index("_stage_rollback")


class TestGoldenIsNeverSavedForARolledBackChange:
    """A rolled-back device must not have the rolled-back config committed.

    Two independent mechanisms have to hold: stage 8.5 must not RUN when a
    rollback-class stage failed, and if it did run it must skip the devices
    that were rolled back. Either alone would be a single point of failure for
    "the repo records what the device actually has".
    """

    def test_a_failed_rollback_stage_breaks_out_before_save_golden(self):
        """run() breaks on a non-continue failure; 8.5 is after 8."""
        from modules.pipeline import _STAGE_TABLE

        names = [name for name, _on_failure in _STAGE_TABLE]
        assert names.index("verify") < names.index("save_golden")
        assert dict(_STAGE_TABLE)["verify"] == "rollback"
        assert dict(_STAGE_TABLE)["save_golden"] == "continue"

    def test_save_golden_skips_a_rolled_back_device(self):
        from modules.pipeline import _stage_save_golden

        ctx = _ctx()
        ctx.rolled_back_ips = ["10.0.0.1"]
        ctx.post_snapshots = {"10.0.0.1": {"running_config": "hostname R1\n"}}
        _stage_save_golden(ctx)

        assert ctx.golden_result["commit"] == ""
        assert [s["hostname"] for s in ctx.golden_skipped] == ["R1"]
        assert "not deployed successfully" in ctx.golden_skipped[0]["reason"]

    def test_save_golden_skips_a_failed_device(self):
        from modules.pipeline import _stage_save_golden

        ctx = _ctx()
        ctx.deploy_failures = [{"ip": "10.0.0.1", "reason": "boom"}]
        ctx.post_snapshots = {"10.0.0.1": {"running_config": "hostname R1\n"}}
        _stage_save_golden(ctx)

        assert ctx.golden_result["commit"] == ""
        assert ctx.golden_skipped[0]["reason"] == "not deployed successfully"

    def test_save_golden_refuses_without_a_post_deploy_capture(self):
        """Never commit the pre-deploy config and claim it is what is there."""
        from modules.pipeline import _stage_save_golden

        ctx = _ctx()
        ctx.post_snapshots = {}
        _stage_save_golden(ctx)
        assert ctx.golden_skipped[0]["reason"] == "no post-deploy config captured"

    def test_a_verify_failure_never_reaches_save_golden(self):
        """End to end through the runner, with a spy on the golden stage."""
        import modules.pipeline as P
        from modules.pipeline import PipelineRunner, PipelineStageError

        ran = []
        originals = {name: getattr(P, f"_stage_{name}") for name in
                     ("netbox_query", "template_render", "ci_gate",
                      "pre_snapshot", "config_diff", "deploy", "post_snapshot",
                      "verify", "save_golden", "rollback")}
        for name in ("netbox_query", "template_render", "ci_gate",
                     "pre_snapshot", "config_diff", "deploy", "post_snapshot"):
            setattr(P, f"_stage_{name}", lambda ctx: None)
        setattr(P, "_stage_verify",
                lambda ctx: (_ for _ in ()).throw(PipelineStageError("verify failed")))
        setattr(P, "_stage_save_golden", lambda ctx: ran.append("save_golden"))
        setattr(P, "_stage_rollback", lambda ctx: ran.append("rollback"))
        try:
            ctx = _ctx()
            ctx.push_results = {"10.0.0.1": {"ok": True}}
            result = PipelineRunner(ctx).run()
        finally:
            for name, fn in originals.items():
                setattr(P, f"_stage_{name}", fn)

        assert "rollback" in ran, "rollback did not fire on a verify failure"
        assert "save_golden" not in ran, "a rolled-back change reached golden"
        assert result.final_status == "failed"
