"""The pipeline's readers against REAL device output (C62, C64 to C67).

Every regex in `modules/pipeline.py` that matches device text was written
against imagined output. Swept 2026-09-27 against captures from the live
fleet (`tests/fixtures/operational/`, read-only, see its README). Nothing in
the repository had ever fed the BGP or RIP branch a real capture.

- **Correct on real output, pinned here:** the error pattern, the interface
  up-count, the OSPF row count.
- **Wrong on real output: the acceptance for each finding is a STRICT
  expected failure.** It fails today for the recorded reason, and when the
  fix lands it passes, which strict mode turns into a failure until the
  marker is removed. So the fix and the retirement of the marker are one
  commit, and a finding cannot be closed without its real-output test
  passing.
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
    @pytest.mark.xfail(strict=True, reason="C64: the BGP pattern expects eight fields; "
                                           "a real row has ten, so it counts 0")
    def test_c64_the_established_bgp_session_on_r3_is_counted(self, on):
        on("r3")
        got = pipeline._detect_routing_neighbors(None)
        assert (got["protocol"], got["count"]) == ("bgp", 1)

    def test_c64_what_it_counts_today(self, on):
        """The measured defect, so its fix is seen to move it."""
        on("r3")
        got = pipeline._detect_routing_neighbors(None)
        assert (got["protocol"], got["count"]) == ("bgp", 0)

    @pytest.mark.xfail(strict=True, reason="C65: the parser reads the first 'Routing "
                                           "Information Sources' table, the "
                                           "'application' pseudo-protocol's, which is empty")
    def test_c65_s1_hears_its_rip_neighbour(self):
        sources = pipeline._parse_rip_sources(capture("s1", "show_ip_protocols"))
        assert [s["gateway"] for s in sources] == ["10.255.2.10"]

    def test_c65_what_it_reads_today(self):
        assert pipeline._parse_rip_sources(capture("s1", "show_ip_protocols")) == []

    @pytest.mark.xfail(strict=True, reason="C66: 'Total\\s+(\\d+)' captures the Networks "
                                           "column, not networks plus subnets")
    @pytest.mark.parametrize("host,routes", [("r3", 30), ("s1", 13)])
    def test_c66_the_route_count_is_the_route_count(self, on, host, routes):
        on(host)
        snap = pipeline._capture_operational_snapshot(None, "x", host)
        assert snap["routes"]["total_count"] == routes

    @pytest.mark.xfail(strict=True, reason="C67: the canary asks whether 'up' appears "
                                           "anywhere, and Loopback0 is always up")
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

    @pytest.mark.xfail(strict=True, reason="C62: the first protocol found is the only "
                                           "one read; r3 runs BGP and OSPF")
    def test_c62_r3s_ospf_is_read_as_well_as_its_bgp(self, on):
        on("r3")
        got = pipeline._detect_routing_neighbors(None)
        names = set(got.get("protocols") or [got["protocol"]])
        assert {"bgp", "ospf"} <= names


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
