"""RIP verification.

`_detect_routing_neighbors` probed BGP → OSPF → EIGRP → IS-IS and never RIP.
S1 and S2 are the RIPv2 devices in the reference lab, so they matched nothing,
returned a neighbour count of -1, and the verify stage skipped the neighbour
check entirely — reporting "verified" having checked no neighbour state at all.

A verify that silently checks nothing produces false confidence in the one
phase where confidence matters, so these tests exist to make a vacuous pass
impossible.
"""

import pytest

from modules import pipeline
from modules.nsot import convergence

SHOW_IP_PROTOCOLS_RIP = """Routing Protocol is "rip"
  Outgoing update filter list for all interfaces is not set
  Sending updates every 30 seconds, next due in 12 seconds
  Default version control: send version 2, receive version 2
    Interface             Send  Recv  Triggered RIP  Key-chain
    GigabitEthernet0/2    2     2
  Automatic network summarization is not in effect
  Maximum path: 4
  Routing for Networks:
    10.0.0.0
  Routing Information Sources:
    Gateway         Distance      Last Update
    10.255.2.10          120      00:00:12
    10.255.2.14          120      00:00:04
  Distance: (default is 120)
"""

SHOW_IP_PROTOCOLS_RIP_SILENT = SHOW_IP_PROTOCOLS_RIP.replace(
    "    10.255.2.10          120      00:00:12\n"
    "    10.255.2.14          120      00:00:04\n", "")

SHOW_IP_PROTOCOLS_RIP_STALE = SHOW_IP_PROTOCOLS_RIP.replace(
    "00:00:12", "00:04:31").replace("00:00:04", "00:05:02")

SHOW_IP_PROTOCOLS_OSPF = """Routing Protocol is "ospf 1"
  Router ID 10.255.1.11
  Routing for Networks:
    10.255.3.0 0.0.0.255 area 0
"""


class TestRipSourceParsing:
    def test_parses_gateways(self):
        sources = pipeline._parse_rip_sources(SHOW_IP_PROTOCOLS_RIP)
        assert [s["gateway"] for s in sources] == ["10.255.2.10", "10.255.2.14"]

    def test_parses_distance_and_age(self):
        first = pipeline._parse_rip_sources(SHOW_IP_PROTOCOLS_RIP)[0]
        assert first["distance"] == 120
        assert first["last_update"] == "00:00:12"

    def test_stops_at_the_distance_line(self):
        """`Distance: (default is 120)` is not a gateway row."""
        sources = pipeline._parse_rip_sources(SHOW_IP_PROTOCOLS_RIP)
        assert all(s["gateway"] != "120" for s in sources)
        assert len(sources) == 2

    def test_absent_section_returns_none(self):
        assert pipeline._parse_rip_sources(SHOW_IP_PROTOCOLS_OSPF) is None

    def test_empty_section_is_a_real_answer_not_none(self):
        """RIP configured but hearing from nobody is a finding, not 'unknown'."""
        assert pipeline._parse_rip_sources(SHOW_IP_PROTOCOLS_RIP_SILENT) == []


class TestRipIsDetected:
    class _Conn:
        def __init__(self, protocols_output):
            self.protocols_output = protocols_output

        def send_command(self, cmd, **kwargs):
            if "ip protocols" in cmd:
                return self.protocols_output
            return ""                       # no BGP/OSPF/EIGRP/IS-IS

    @pytest.fixture(autouse=True)
    def _stub_command(self, monkeypatch):
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, cmd, **kw: conn.send_command(cmd))

    def test_rip_only_device_is_no_longer_invisible(self):
        """The regression: this used to return count -1 and be skipped."""
        result = pipeline._detect_routing_neighbors(
            self._Conn(SHOW_IP_PROTOCOLS_RIP))
        assert result["protocol"] == "rip"
        assert result["count"] == 2

    def test_rip_with_no_sources_reports_zero_not_minus_one(self):
        result = pipeline._detect_routing_neighbors(
            self._Conn(SHOW_IP_PROTOCOLS_RIP_SILENT))
        assert result["protocol"] == "rip"
        assert result["count"] == 0, "a silent RIP process must not look like 'no protocol'"

    def test_device_with_no_protocol_still_returns_minus_one(self):
        result = pipeline._detect_routing_neighbors(self._Conn("no protocols here"))
        assert result["count"] == -1

    def test_sources_are_carried_for_the_progress_check(self):
        result = pipeline._detect_routing_neighbors(
            self._Conn(SHOW_IP_PROTOCOLS_RIP))
        assert len(result["sources"]) == 2


class TestNoVacuousPass:
    """A device that checked nothing must not look like one that passed."""

    def test_skipped_is_recorded_distinctly(self):
        from modules.pipeline import PipelineContext

        ctx = PipelineContext(
            config_type="interface", device_ips=["203.0.113.1"], params={},
            ip_params_map={}, selected_devices=[{"ip": "203.0.113.1", "hostname": "S9"}],
            check_devices=[], connections_pool={}, pool_lock=None,
            config_id="t", settle_sleep=lambda _s: None)
        ctx.pre_snapshots = {"203.0.113.1": {"routing_neighbors": {"count": -1}}}
        ctx.post_snapshots = {"203.0.113.1": {"routing_neighbors": {"count": -1}}}

        pipeline._stage_verify(ctx)
        recorded = ctx.convergence["203.0.113.1"]["neighbors"]
        assert recorded["state"] == convergence.SKIPPED
        assert "no routing protocol" in recorded["reason"]


class TestRipUsesItsOwnSettleWindow:
    def test_rip_window_is_the_long_one(self):
        assert convergence.window_for("rip")["timeout"] >= 60

    def test_recent_update_counts_as_progress(self):
        """Updates still arriving means convergence in progress, not failure."""
        sources = pipeline._parse_rip_sources(SHOW_IP_PROTOCOLS_RIP)
        assert pipeline._protocol_shows_progress({"sources": sources}, 0) is True

    def test_stale_updates_are_not_progress(self):
        sources = pipeline._parse_rip_sources(SHOW_IP_PROTOCOLS_RIP_STALE)
        assert pipeline._protocol_shows_progress({"sources": sources}, 0) is False

    def test_partial_recovery_counts_as_progress(self):
        assert pipeline._protocol_shows_progress({}, 1) is True


class TestConvergenceOutcomes:
    """A RIP device must produce converged or not_yet_converged — never a
    vacuous pass, and never a spurious failure on the first poll."""

    def _await(self, counts, pre_count=2, sources=None):
        from modules.pipeline import PipelineContext

        ctx = PipelineContext(
            config_type="rip", device_ips=["203.0.113.21"], params={},
            ip_params_map={},
            selected_devices=[{"ip": "203.0.113.21", "hostname": "s1"}],
            check_devices=[], connections_pool={}, pool_lock=None,
            config_id="t", settle_sleep=lambda _s: None)

        iterator = iter(counts)
        def _detect(_conn):
            count = next(iterator, counts[-1])
            return {"protocol": "rip", "count": count,
                    "sources": sources if sources is not None else []}

        import modules.pipeline as P
        original_detect = P._detect_routing_neighbors
        original_conn = None
        try:
            import modules.connection as C
            original_conn = C.get_persistent_connection
            C.get_persistent_connection = lambda *a, **k: object()
            P._detect_routing_neighbors = _detect
            return P._await_neighbour_convergence(ctx, "203.0.113.21", "s1", "rip",
                                                  pre_count)
        finally:
            P._detect_routing_neighbors = original_detect
            if original_conn:
                C.get_persistent_connection = original_conn

    def test_recovery_within_the_window_converges(self):
        """Convergence is "within tolerance", not "fully restored".

        With a baseline of 2 and _NEIGHBOR_DROP_TOLERANCE of 1, a count of 1 is
        already acceptable — so polling stops there rather than waiting for 2.
        """
        result = self._await([0, 1, 2])
        assert result["state"] == convergence.CONVERGED
        assert result["count"] >= 2 - pipeline._NEIGHBOR_DROP_TOLERANCE

    def test_full_recovery_also_converges(self):
        result = self._await([0, 2], pre_count=2)
        assert result["state"] == convergence.CONVERGED

    def test_drop_beyond_tolerance_does_not_converge_early(self):
        """A baseline of 5 dropping to 1 is outside tolerance."""
        result = self._await([1, 1, 1], pre_count=5)
        assert result["state"] != convergence.CONVERGED

    def test_still_updating_is_not_yet_converged(self):
        fresh = [{"gateway": "10.255.2.10", "distance": 120, "last_update": "00:00:08"}]
        result = self._await([0, 0, 0], sources=fresh)
        assert result["state"] == convergence.NOT_YET, \
            "a RIP process still receiving updates was called a failure"

    def test_silent_protocol_is_a_failure(self):
        stale = [{"gateway": "10.255.2.10", "distance": 120, "last_update": "00:06:11"}]
        result = self._await([0, 0, 0], sources=stale)
        assert result["state"] == convergence.FAILED

    def test_result_is_never_vacuous(self):
        """Whatever happens, the outcome is one of the three real states."""
        for counts in ([0, 1, 2], [0, 0, 0], [2, 2, 2]):
            result = self._await(counts)
            assert result["state"] in (convergence.CONVERGED, convergence.NOT_YET,
                                       convergence.FAILED)
            assert "count" in result and "elapsed" in result
