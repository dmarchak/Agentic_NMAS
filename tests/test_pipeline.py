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
    """Return a minimal PipelineContext suitable for unit tests."""
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
    """The stage table must contain exactly 9 entries in the required order."""

    def test_exactly_nine_stages(self):
        assert len(_STAGE_TABLE) == 9

    def test_stage_names_cover_all_required_stages(self):
        required = {
            "netbox_query", "template_render", "ci_gate",
            "pre_snapshot", "config_diff", "deploy",
            "post_snapshot", "verify", "audit_log",
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
        assert STAGE_NAMES[8] == "audit_log"

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

    def test_audit_log_is_index_8(self):
        assert STAGE_NAMES.index("audit_log") == 8

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
