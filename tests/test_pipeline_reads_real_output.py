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
        """Both of r3's sessions, IPv4 and IPv6 (`show bgp all summary`)."""
        on("r3")
        got = pipeline._detect_routing_neighbors(None)
        assert (got["protocol"], got["count"]) == ("bgp", 2)

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
        ctx = type("Ctx", (), {"connections_pool": {}, "pool_lock": __import__("threading").Lock()})()
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
            {"bgp": 2, "ospf": 6, "ospfv3": 4}


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


class TestVerifyChecksWhatIntentDeclares:
    """The C70 re-run (the operator, 2026-09-27): a restore whose whole
    purpose was putting `ipv6 ospf 1 area 0` back reported "checked ospf,
    rip, ripng". Verify took its protocol list from the device's BEFORE
    state, so the protocol the operation existed to restore was the one it
    could not check. The list is now the before-state plus what the TARGET
    intent declares, carried in by the operation. From r1's real captures,
    with OSPFv3 absent before (the device answered nothing for it)."""

    def _snap(self, monkeypatch, ospfv3_text):
        def reply(_conn, command, **_kw):
            if command == "show ospfv3 neighbor":
                return ospfv3_text
            return device("r1")(_conn, command)
        monkeypatch.setattr("modules.commands.run_device_command", reply)
        return pipeline._detect_routing_neighbors(None)

    def _ctx(self, monkeypatch, pre, post, declared, settle=None):
        from modules.pipeline import PipelineContext

        ctx = PipelineContext(config_type="template", device_ips=["x"], params={},
                              ip_params_map={}, selected_devices=[{"ip": "x", "hostname": "r1"}],
                              connections_pool={}, pool_lock=None, config_id="t",
                              settle_sleep=lambda _s: None)
        ctx.pre_snapshots = {"x": {"routing_neighbors": pre}}
        ctx.post_snapshots = {"x": {"routing_neighbors": post}}
        ctx.declared_protocols = {"x": declared}
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda *a, **k: None)
        # The settle window re-reads the device: it answers as `settle` does.
        monkeypatch.setattr(pipeline, "_detect_routing_neighbors",
                            lambda _c: settle if settle is not None else post)
        return ctx

    def _declared(self):
        from modules.nsot.golden_state import declared_protocols
        from modules.nsot.parsers import get_parser

        intent = get_parser("cisco_iosxe").parse(
            open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r1.cfg"),
                 encoding="utf-8").read())
        declared = declared_protocols(intent)
        assert "ospfv3" in declared, declared      # the fixture can reach the case
        return declared

    def test_a_protocol_intent_declares_is_checked_though_absent_before(self, monkeypatch):
        pre = self._snap(monkeypatch, "")
        post = self._snap(monkeypatch, capture("r1", "show_ospfv3_neighbor"))
        assert "ospfv3" not in pipeline._protocol_counts(pre)   # the break
        ctx = self._ctx(monkeypatch, pre, post, self._declared())
        pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert "ospfv3" in v["checked_protocols"], v["checked_protocols"]
        assert v["from_intent"] == ["ospfv3"] and v["ok"] is True, v

    def test_still_absent_after_is_not_a_pass_and_not_a_rollback(self, monkeypatch):
        pre = self._snap(monkeypatch, "")
        ctx = self._ctx(monkeypatch, pre, pre, self._declared())
        pipeline._stage_verify(ctx)            # raises nothing: no rollback
        v = ctx.verify_result["x"]
        assert v["ok"] is False and v["issues"] == []
        assert len(v["intent_unmet"]) == 1 and v["intent_unmet"][0].startswith("ospfv3")

    def test_the_control_with_no_intent_known_checks_the_before_state_only(self, monkeypatch):
        pre = self._snap(monkeypatch, "")
        post = self._snap(monkeypatch, capture("r1", "show_ospfv3_neighbor"))
        ctx = self._ctx(monkeypatch, pre, post, None)
        pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert "ospfv3" not in v["checked_protocols"] and v["from_intent"] == []
        assert v["declared_protocols"] is None

    def test_the_receipt_and_the_screen_say_it(self, monkeypatch):
        import json

        import dukpy

        from modules.nsot import receipts

        pre = self._snap(monkeypatch, "")
        ctx = self._ctx(monkeypatch, pre, pre, self._declared())
        pipeline._stage_verify(ctx)
        checks = receipts._checks({"outcome": "deployed", "commands": ["x"],
                                   "verify": ctx.verify_result["x"]})
        assert checks["from_intent"] == ["ospfv3"] and checks["neighbours"]["ospfv3"][0] == 0
        src = open(os.path.join(ROOT, "static", "js", "nmas_preview_confirm.js")).read()
        result = {"parts": ["happened", "did_not", "sent", "checks", "record", "not_watched"],
                  "action": "restore", "level": "partial",
                  "happened": {"summary": "s", "targets": []}, "did_not": {"none": "n"},
                  "targets": [{"name": "r1", "sent": {"lines": [], "none": "x"},
                               "checks": checks}],
                  "record": {"statement": ""}, "not_watched": ""}
        html = dukpy.evaljs("var window = {};\n" + src
                            + f"\nwindow.previewConfirmResultHtml({json.dumps(result)}, {{}});")
        assert "declared by intent, not running before: ospfv3" in html
        assert "data-pr-intent-unmet" in html and "verify failed" in html


class TestTheOperationCarriesItsIntentIntoVerify:
    """The seam: `_deploy_one` hands verify the TARGET intent's protocols, the
    ref's for a restore and the committed intent's for a deploy."""

    def _run(self, monkeypatch, artifact):
        import routes.deploy as rd

        seen = {}
        monkeypatch.setattr("modules.nsot.deploy.prepare_for_deploy",
                            lambda a: {"config": "hostname r1\n"})
        monkeypatch.setattr("modules.nsot.deploy.merge_commands", lambda i, c: ["hostname r1"])
        monkeypatch.setattr("modules.nsot.deploy.assert_merge_only", lambda c, i: None)

        def run(self):
            seen["declared"] = self.ctx.declared_protocols
            self.ctx.final_status = "success"
            return self.ctx
        monkeypatch.setattr(pipeline.PipelineRunner, "run", run)
        rd._deploy_one({"artifact": artifact, "fresh": "hostname x\n"}, "Lab",
                       {"r1": {"ip": "203.0.113.11", "hostname": "r1"}})
        return seen["declared"]

    def test_a_restore_carries_the_refs_intent_and_a_deploy_its_own(self, monkeypatch):
        routing = {"routing": {"ospf": {"x": 1}, "ospfv3": {"x": 1}}}

        class Restore:
            device = "r1"
            ref_intent = routing

        class Deploy:
            device = "r1"
            host_vars = routing

        class Predates:
            device = "r1"
            ref_intent = None

        assert self._run(monkeypatch, Restore()) == {"203.0.113.11": ["ospf", "ospfv3"]}
        assert self._run(monkeypatch, Deploy()) == {"203.0.113.11": ["ospf", "ospfv3"]}
        assert self._run(monkeypatch, Predates()) == {"203.0.113.11": None}
