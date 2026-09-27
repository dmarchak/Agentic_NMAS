"""The pipeline's readers against REAL device output (C62, C64 to C67).

Every regex in `modules/pipeline.py` that matches device text was written
against imagined output. Swept 2026-09-27 against captures from the live
fleet (`tests/fixtures/operational/`, read-only, see its README). Nothing in
the repository had ever fed the BGP or RIP branch a real capture.

- **Correct on real output, pinned here:** the error pattern, the interface
  up-count, the OSPF row count.
- **Wrong on real output, and fixed:** each finding's acceptance was a
  STRICT expected failure built from a capture. The fixes made all six pass,
  strict mode then failed them, and the markers were removed in the same
  commit as the fixes, so no finding closed without its real-output test.
"""

import ast
import os
import re

import pytest

from modules import pipeline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "operational")


def capture(host, slug):
    with open(os.path.join(FIX, f"{host}__{slug}.txt"), encoding="utf-8") as fh:
        return fh.read()


def device(host):
    """`run_device_command` answered from the host's captures, by command."""
    def reply(_conn, command, **_kw):
        slug = re.sub(r"[^a-z0-9]+", "_", command.lower()).strip("_")
        path = os.path.join(FIX, f"{host}__{slug}.txt")
        if not os.path.exists(path):
            return ""   # a command this host was not captured for
        return open(path, encoding="utf-8").read()
    return reply


@pytest.fixture
def on(monkeypatch):
    def _use(host):
        monkeypatch.setattr("modules.commands.run_device_command", device(host))
    return _use


class TestTheCapturesAreReal:
    def test_the_directory_holds_what_the_tests_read(self):
        names = os.listdir(FIX)
        assert len([n for n in names if n.endswith(".txt")]) >= 20
        assert "r3__show_ip_bgp_summary.txt" in names
        assert "s1__show_ip_protocols.txt" in names

    def test_the_bgp_row_is_the_devices_ten_fields(self):
        """The row a hand-written sample gets wrong."""
        row = [l for l in capture("r3", "show_ip_bgp_summary").splitlines()
               if l.startswith("198.51.100.1")]
        assert len(row) == 1 and len(row[0].split()) == 10, row


class TestCorrectOnRealOutput:
    @pytest.mark.parametrize("host", ["r3", "s1"])
    def test_the_error_pattern_matches_the_devices_error(self, host):
        assert re.search(pipeline.IOS_ERROR_PATTERN, capture(host, "show_foobar"))

    def test_the_error_pattern_does_not_match_a_normal_read(self):
        """The control: it is not matching everything."""
        assert not re.search(pipeline.IOS_ERROR_PATTERN,
                             capture("r3", "show_ip_ospf_neighbor"))

    @pytest.mark.parametrize("host,up", [("r3", 5), ("s1", 10)])
    def test_the_interface_up_count(self, on, host, up):
        on(host)
        snap = pipeline._capture_operational_snapshot(None, "x", host)
        assert snap["interfaces"]["up_count"] == up

    @pytest.mark.parametrize("host,rows", [("s3", 5), ("r1", 5)])
    def test_the_ospf_row_count_on_an_ospf_first_device(self, on, host, rows):
        """Counts adjacencies in any state. On a broadcast segment 2WAY between
        DROTHERs is the steady state (r1 and s3 show three), so counting only
        FULL would be wrong; a neighbour stuck in INIT or EXSTART counts too,
        which C62 records."""
        on(host)
        got = pipeline._detect_routing_neighbors(None)
        assert (got["protocol"], got["count"]) == ("ospf", rows)


class TestTheFindings:
    def test_c64_the_established_bgp_session_on_r3_is_counted(self, on):
        on("r3")
        got = pipeline._detect_routing_neighbors(None)
        assert (got["protocol"], got["count"]) == ("bgp", 1)

    def test_c64_a_down_session_is_configured_not_established(self):
        """r3's real row, with its last field replaced by a state word, is the
        same ten-field row a down peer prints: configured, not established."""
        text = capture("r3", "show_ip_bgp_summary")
        down = text.replace("4d13h           3", "never       Idle")
        assert down != text, "the fixture must carry the row being edited"
        parsed = pipeline._parse_bgp_summary(down)
        assert (parsed["established"], parsed["configured"]) == (0, 1)

    def test_c65_s1_hears_its_rip_neighbour(self):
        sources = pipeline._parse_rip_sources(capture("s1", "show_ip_protocols"))
        assert [s["gateway"] for s in sources] == ["10.255.2.10"]

    def test_c65_r1_hears_rip_under_its_ospf(self):
        """r1 runs OSPF and RIP: its OSPF section has a sources table too, and
        the RIP one is read."""
        sources = pipeline._parse_rip_sources(capture("r1", "show_ip_protocols"))
        assert sources is not None and all(s["distance"] == 120 for s in sources)

    def test_c65_no_rip_section_is_none_even_with_other_tables(self):
        """r3 runs no RIP; its application and OSPF tables must not be read as RIP."""
        assert pipeline._parse_rip_sources(capture("r3", "show_ip_protocols")) is None

    @pytest.mark.parametrize("host,routes", [("r3", 30), ("s1", 13)])
    def test_c66_the_route_count_is_the_route_count(self, on, host, routes):
        on(host)
        snap = pipeline._capture_operational_snapshot(None, "x", host)
        assert snap["routes"]["total_count"] == routes

    def test_c67_the_canary_fails_when_only_the_loopback_is_up(self, monkeypatch):
        """Real lines only: r3's header and its Loopback0 line, with every
        physical interface removed. The canary should halt the fleet."""
        lines = capture("r3", "show_ip_interface_brief").splitlines()
        text = "\n".join([lines[0]] + [l for l in lines if l.startswith("Loopback0")])
        monkeypatch.setattr("modules.commands.run_device_command", lambda *a, **k: text)
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda *a, **k: None)
        ctx = type("Ctx", (), {"connections_pool": {}, "pool_lock": None})()
        with pytest.raises(pipeline.PipelineStageError):
            pipeline._canary_sanity_check({"ip": "x", "hostname": "r3"}, ctx)

    def test_c62_r3s_ospf_is_read_as_well_as_its_bgp(self, on):
        on("r3")
        got = pipeline._detect_routing_neighbors(None)
        names = set(got.get("protocols") or [got["protocol"]])
        assert {"bgp", "ospf"} <= names


class TestVerifyComparesEveryProtocol:
    """C62 at the verify stage, from r3's real captures: r3 runs BGP and OSPF,
    and a loss in OSPF must fail the deploy even though BGP, the protocol the
    old check chose, is untouched."""

    def _snap(self, monkeypatch, ospf_text):
        replies = {"show ip ospf neighbor": ospf_text}

        def reply(_conn, command, **_kw):
            if command in replies:
                return replies[command]
            return device("r3")(_conn, command)
        monkeypatch.setattr("modules.commands.run_device_command", reply)
        return pipeline._detect_routing_neighbors(None)

    def test_an_ospf_loss_on_a_bgp_router_fails_verify(self, monkeypatch):
        from modules.pipeline import PipelineContext

        full = capture("r3", "show_ip_ospf_neighbor")
        rows = full.splitlines()
        degraded = "\n".join(rows[:-3])            # three adjacencies gone
        assert len(rows) - 3 >= 3, "the capture must hold the adjacencies removed"
        pre = self._snap(monkeypatch, full)
        post = self._snap(monkeypatch, degraded)
        assert pre["protocol"] == "bgp", "the protocol the old check chose"
        ctx = PipelineContext(config_type="interface", device_ips=["x"], params={},
                              ip_params_map={}, selected_devices=[{"ip": "x", "hostname": "r3"}],
                              connections_pool={}, pool_lock=None, config_id="t",
                              settle_sleep=lambda _s: None)
        ctx.pre_snapshots = {"x": {"routing_neighbors": pre}}
        ctx.post_snapshots = {"x": {"routing_neighbors": post}}
        monkeypatch.setattr("modules.connection.get_persistent_connection", lambda *a, **k: None)
        with pytest.raises(pipeline.PipelineStageError, match="ospf neighbors dropped"):
            pipeline._stage_verify(ctx)
        assert ctx.verify_result["x"]["checked_protocols"] == ["bgp", "ospf", "ospfv3"]

    def test_unchanged_passes_and_names_both(self, monkeypatch):
        """The control: the same captures before and after pass."""
        from modules.pipeline import PipelineContext

        snap = self._snap(monkeypatch, capture("r3", "show_ip_ospf_neighbor"))
        ctx = PipelineContext(config_type="interface", device_ips=["x"], params={},
                              ip_params_map={}, selected_devices=[{"ip": "x", "hostname": "r3"}],
                              connections_pool={}, pool_lock=None, config_id="t",
                              settle_sleep=lambda _s: None)
        ctx.pre_snapshots = {"x": {"routing_neighbors": snap}}
        ctx.post_snapshots = {"x": {"routing_neighbors": snap}}
        pipeline._stage_verify(ctx)
        assert ctx.verify_result["x"]["ok"] is True
        # r3's real captures: BGP, OSPF and OSPFv3 (IPv6), each counted.
        assert ctx.verify_result["x"]["pre"]["routing_protocols"] == \
            {"bgp": 1, "ospf": 6, "ospfv3": 4}


class TestOneReader:
    def test_every_command_the_pipeline_reads_with_passes_the_allowlist(self):
        """8.6 reuses these reads through the shared allowlist, so each must
        pass it. The first C61 parse refused one of them."""
        from modules.readonly_commands import refusal

        tree = ast.parse(open(os.path.join(ROOT, "modules", "pipeline.py"),
                              encoding="utf-8").read())
        commands = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "run_device_command"
                    and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)):
                commands.append(node.args[1].value)
        assert len(commands) >= 8, commands
        assert [c for c in commands if refusal(c)] == [], commands


class TestTheIpv6ProtocolsOnRealOutput:
    def test_ospfv3_rows_and_states(self):
        rows = pipeline._parse_ospf_neighbor_rows(capture("r1", "show_ospfv3_neighbor"))
        assert [r["state"] for r in rows] == ["2WAY/DROTHER", "FULL/BDR", "FULL/DR"]

    def test_ripng_next_hops(self):
        hops = pipeline._parse_ripng_next_hops(capture("s1", "show_ipv6_rip_next_hops"))
        assert [(h["interface"], h["paths"]) for h in hops] == [
            ("Vlan10", 4), ("Vlan20", 4), ("Vlan30", 4), ("GigabitEthernet0/2", 2)]

    def test_r1_hears_ripng_though_it_installs_none(self):
        """The measurement that chose the evidence: r1's RIPng table has no
        installed route (OSPFv3 wins on distance) and one next hop."""
        route = capture("r1", "show_ipv6_route_rip")
        assert not [l for l in route.splitlines() if l.startswith("R ")]
        assert len(pipeline._parse_ripng_next_hops(capture("r1", "show_ipv6_rip_next_hops"))) == 1

    def test_a_device_not_running_ripng_has_none(self):
        assert pipeline._parse_ripng_next_hops(capture("r3", "show_ipv6_rip_next_hops")) == []
