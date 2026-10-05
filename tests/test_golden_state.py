"""E7: a golden state is the network CONFIGURED as approved AND WORKING.

A baseline records configuration, so a broken moment and a good one read the
same. A baseline taken with the fleet's operational snapshot earns the claim
"configured and working" only when every routing protocol each device's
committed intent declares is up. The judgement runs here on REAL device
output (`tests/fixtures/operational/`) and real fleet configs.
"""

import json
import os
import re
import subprocess

import pytest

from modules import pipeline
from modules.nsot import golden_state as gs
from modules.nsot import repo as R
from modules.nsot.parsers import get_parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS = os.path.join(ROOT, "tests", "fixtures", "operational")
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
PLATFORM = {"r1": "cisco_iosxe", "r3": "cisco_iosxe", "s1": "cisco_ios", "s3": "cisco_ios"}


def intent(host):
    with open(os.path.join(FLEET, f"{host}.cfg"), encoding="utf-8") as fh:
        return get_parser(PLATFORM[host]).parse(fh.read())


def read_from_captures(host, edit=None):
    """`_capture_operational_snapshot` against the host's real captures;
    *edit* rewrites one command's output (a minimal edit of real text)."""
    def reply(_conn, command, **_kw):
        slug = re.sub(r"[^a-z0-9]+", "_", command.lower()).strip("_")
        path = os.path.join(OPS, f"{host}__{slug}.txt")
        text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        return edit(command, text) if edit else text
    return reply


def snapshot(monkeypatch, host, edit=None):
    monkeypatch.setattr("modules.commands.run_device_command", read_from_captures(host, edit))
    return pipeline._capture_operational_snapshot(None, "x", host)


class TestWhatIntentDeclares:
    def test_from_the_real_fleet(self):
        assert gs.declared_protocols(intent("r3")) == ["bgp", "ospf", "ospfv3"]
        assert gs.declared_protocols(intent("r1")) == ["ospf", "ospfv3", "rip", "ripng"]
        assert gs.declared_protocols(intent("s1")) == ["rip", "ripng"]
        assert gs.declared_protocols(intent("s3")) == ["ospf"]


class TestTheFleetIsWorkingOnRealOutput:
    @pytest.mark.parametrize("host", ["r3", "r1", "s1", "s3"])
    def test_every_declared_protocol_is_up(self, monkeypatch, host):
        judged = gs.judge_device(gs.declared_protocols(intent(host)),
                                 snapshot(monkeypatch, host))
        assert judged["working"] is True, judged


class TestAFailureIsNamed:
    """Minimal edits of real output: the same device, one thing broken."""

    def test_a_bgp_peer_down(self, monkeypatch):
        edit = lambda cmd, t: t.replace("0 4d14h           3", "0 never    Idle", 1) \
            if cmd == "show bgp all summary" else t
        judged = gs.judge_device(["bgp", "ospf", "ospfv3"], snapshot(monkeypatch, "r3", edit))
        assert judged["working"] is False
        assert any("198.51.100.1" in w for w in judged["why"])

    def test_an_ospf_neighbour_stuck(self, monkeypatch):
        edit = lambda cmd, t: t.replace("FULL/BDR", "EXSTART/BDR", 1) \
            if cmd == "show ip ospf neighbor" else t
        judged = gs.judge_device(["bgp", "ospf", "ospfv3"], snapshot(monkeypatch, "r3", edit))
        assert judged["working"] is False and "EXSTART/BDR" in judged["why"][0]

    def test_rip_hearing_nobody(self, monkeypatch):
        edit = lambda cmd, t: t.replace("    10.255.2.10          120      00:00:03\n", "") \
            if cmd == "show ip protocols" else t
        judged = gs.judge_device(["rip", "ripng"], snapshot(monkeypatch, "s1", edit))
        assert judged["working"] is False and "rip: no gateway heard" in judged["why"]

    def test_a_declared_protocol_the_device_does_not_run(self, monkeypatch):
        """s3's intent declaring BGP it does not run: reported, not skipped."""
        judged = gs.judge_device(["bgp", "ospf"], snapshot(monkeypatch, "s3"))
        assert judged["working"] is False
        assert "bgp is declared and the device reported none" in judged["why"]

    def test_a_protocol_this_tool_does_not_measure_fails_closed(self, monkeypatch):
        judged = gs.judge_device(["eigrp"], snapshot(monkeypatch, "s3"))
        assert judged["working"] is False and "does not measure" in judged["why"][0]

    def test_no_committed_intent_is_unknown_not_fine(self, monkeypatch):
        judged = gs.judge_device([], snapshot(monkeypatch, "s3"), intent_known=False)
        assert judged["working"] is False and "no committed intent" in judged["why"][0]

    def test_no_protocol_declared_is_a_real_state(self, monkeypatch):
        """r6: static only. Nothing to judge is working, and says why."""
        judged = gs.judge_device([], snapshot(monkeypatch, "s3"))
        assert judged["working"] is True and "no routing protocol declared" in judged["why"][0]


class TestTheFleetClaim:
    def _take(self, monkeypatch, fail=()):
        devices = [{"hostname": h} for h in ("r3", "r1", "s1", "s3")]

        def read(dev):
            if dev["hostname"] in fail:
                raise OSError("timed out")
            return snapshot(monkeypatch, dev["hostname"])
        return gs.take(devices, read, intent)

    def test_every_device_working_is_the_strong_claim(self, monkeypatch):
        snap = self._take(monkeypatch)
        assert snap["claim"] == gs.WORKING and snap["not_working"] == []
        assert any("heartbeats" in n for n in snap["not_read"]), "what it did not read, said"

    def test_one_device_not_read_is_the_weak_claim_and_names_it(self, monkeypatch):
        snap = self._take(monkeypatch, fail=("s1",))
        assert snap["claim"] == gs.CONFIGURED and snap["unread"] == ["s1"]
        assert "not read" in snap["devices"]["s1"]["why"][0]

    def test_an_empty_fleet_is_never_working(self):
        assert gs.take([], lambda d: {}, lambda h: {})["claim"] == gs.CONFIGURED


pytestmark_git = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git is not available")


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost",
                            "nsot_device_tag_retention": 50}.get(key, default))
    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    return str(list_dir / "config_repo")


def _save(operational, name="R1"):
    item = R.GoldenItem(name, f"hostname {name}\n", "203.0.113.1", netbox_id=42, platform="cisco_ios")
    # The test's fleet is this one device: coverage stated (C91).
    return R.save_golden("Lab", [item], source="save_all", allow_new=True,
                         operational=operational, inventory_size=1)


WORKING_SNAP = {"taken_at": "t", "claim": gs.WORKING, "working": True,
                "devices": {"R1": {"working": True, "declared": ["ospf"],
                                   "why": ["ospf: 5 neighbour(s), all FULL or 2WAY"],
                                   "interfaces_up": 4, "routes": 13}},
                "unread": [], "not_working": [], "not_read": list(gs.NOT_READ)}


@pytestmark_git
@pytest.mark.usefixtures("intent_matches")
class TestTheTagCarriesTheClaim:
    def test_working_earns_a_golden_state_tag_and_says_so(self, lab):
        result = _save(WORKING_SNAP)
        assert any(t.startswith("golden-state/") for t in result["tags"])
        listed = R.list_baselines(lab)[0]
        assert listed["claim"] == gs.WORKING

    def test_the_snapshot_is_in_the_tag(self, lab):
        result = _save(WORKING_SNAP)
        tag = next(t for t in result["tags"] if t.startswith("baseline/"))
        _rc, body, _ = R.git(lab, "tag", "-l", "--format=%(contents)", tag)
        operational = json.loads(body.split("Operational: ", 1)[1].strip())
        assert operational["devices"]["R1"]["working"] is True
        assert "Not read: heartbeats" in body

    def test_not_working_is_the_weak_claim_and_no_golden_state_tag(self, lab):
        snap = dict(WORKING_SNAP, claim=gs.CONFIGURED, working=False)
        result = _save(snap)
        assert not any(t.startswith("golden-state/") for t in result["tags"])
        assert R.list_baselines(lab)[0]["claim"] == gs.CONFIGURED

    def test_a_baseline_without_a_snapshot_says_configured(self, lab):
        _save(None)
        listed = R.list_baselines(lab)[0]
        assert listed["claim"] == gs.CONFIGURED
        assert "no operational snapshot" in listed["claim_detail"]

    def test_a_baseline_from_before_e7_reads_as_configured(self, lab):
        """The eleven on the host: a tag whose message has no Claim line."""
        _save(None)
        head = R.git(lab, "rev-parse", "HEAD")[1].strip()
        R.git(lab, "tag", "-a", "baseline/20260921T033554Z", "-m",
              "network baseline — 6 device(s) via save_all", head)
        old = next(b for b in R.list_baselines(lab) if b["tag"] == "baseline/20260921T033554Z")
        assert old["claim"] == gs.CONFIGURED and "before baselines recorded" in old["claim_detail"]


class TestTheBaselineRowDrawsTheClaim:
    def test_the_shipped_badge(self):
        import dukpy

        from tests.payload_render import lift, shipped

        src = shipped("partials__golden_repo.1.js")
        fn = lift(src, "_gEsc") + "\n" + lift(src, "_gBaselineClaim")
        strong = dukpy.evaljs(fn + "\n_gBaselineClaim(" + json.dumps(
            {"claim": gs.WORKING, "claim_detail": gs.WORKING}) + ")")
        weak = dukpy.evaljs(fn + "\n_gBaselineClaim(" + json.dumps(
            {"claim": gs.CONFIGURED, "claim_detail": "configuration only"}) + ")")
        assert 'data-baseline-claim="working"' in strong and "bg-success" in strong
        assert 'data-baseline-claim="configured"' in weak and "bg-success" not in weak


class TestTheCli:
    """`nmas-golden-state`: dry-run by default; one session per device; the
    snapshot reaches the commit. Devices answer from the real captures."""

    def _run(self, monkeypatch, argv, unreachable=()):
        import importlib.machinery
        import importlib.util

        path = os.path.join(ROOT, "scripts", "nmas-golden-state")
        loader = importlib.machinery.SourceFileLoader("nmas_golden_state", path)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(mod)

        devices = [{"hostname": h, "ip": f"203.0.113.{i}"} for i, h in
                   enumerate(("r3", "r1", "s1", "s3"), 1)]
        monkeypatch.setattr("modules.device.get_current_device_list",
                            lambda: ("Default", "/nonexistent/default/devices.csv"))
        monkeypatch.setattr("modules.device.load_saved_devices", lambda _p: devices)

        # The script binds `run_device_command` when it starts reading, so the
        # reader is patched ONCE, before main. Each connection answers for ITS
        # device, as a real session does: the devices are read at once (the
        # concurrency rule), and a fake holding one "current device" handed
        # each device another's captures.
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, cmd, **kw: read_from_captures(conn)(conn, cmd))

        def connect(dev, work):
            if dev["hostname"] in unreachable:
                raise OSError("timed out")
            return work(dev["hostname"])
        monkeypatch.setattr("modules.connection.with_temp_connection", connect)
        import yaml
        monkeypatch.setattr("modules.nsot.hostvars.committed_at_head",
                            lambda repo, host: (yaml.safe_dump(intent(host)), "committed"))
        saved = {}

        def save_golden(list_name, items, **kw):
            saved.update(kw, items=items)
            return {"ok": True, "commit": "c0ffee", "tags": ["baseline/x", "golden-state/x"]}
        monkeypatch.setattr("modules.nsot.repo.save_golden", save_golden)
        return mod.main(argv), saved

    def test_a_dry_run_commits_nothing_and_says_the_claim(self, monkeypatch, capsys):
        code, saved = self._run(monkeypatch, [])
        out = capsys.readouterr().out
        assert code == 0 and saved == {}
        assert "Claim: configured and working" in out and "nothing committed" in out

    def test_commit_carries_the_snapshot(self, monkeypatch):
        code, saved = self._run(monkeypatch, ["--commit"])
        assert code == 0 and saved["source"] == "golden_state" and saved["baseline"] is True
        assert saved["operational"]["claim"] == gs.WORKING
        assert "Tool: nmas-golden-state" in saved["extra_trailers"]
        assert len(saved["items"]) == 4

    def test_an_unread_device_is_exit_2_and_named(self, monkeypatch, capsys):
        code, saved = self._run(monkeypatch, [], unreachable=("s1",))
        out = capsys.readouterr().out
        assert code == 2 and "Claim: configured" in out and "s1: NOT working" in out


def _fleet_configs(hosts):
    return {h: open(os.path.join(FLEET, f"{h}.cfg"), encoding="utf-8").read() for h in hosts}


MANAGED = ("r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4")   # r5 retired


class TestBothBgpFamiliesOnRealOutput:
    def test_r3_and_r4_each_have_two_sessions_and_no_phantom(self):
        from modules.topology import parse_bgp_summary

        got = {h: [(p["neighbor"], p["address_family"], p["established"]) for p in
                   parse_bgp_summary(open(os.path.join(OPS, f"{h}__show_bgp_all_summary.txt"))
                                     .read())["peers"]] for h in ("r3", "r4")}
        assert got == {
            "r3": [("198.51.100.1", "IPv4 Unicast", True), ("2001:DB8:51::2", "IPv6 Unicast", True)],
            # r4's IPv6 peer is a REAL wrapped row: the address alone on its line.
            "r4": [("198.51.100.3", "IPv4 Unicast", True), ("2001:DB8:51:1::2", "IPv6 Unicast", True)]}


    def test_the_row_rule_rejects_a_non_peer_line_inside_a_table(self):
        """Real output cannot separate the parser's two guards (the per-family
        reset and the address-and-version row rule): measured, removing
        either alone left every real-capture test passing. So the row rule
        is tested where the reset cannot help: r3's own "0 BGP route-map
        cache entries using 0 bytes of memory" line (ten fields, a digit
        first), placed inside a table after a real row."""
        from modules.topology import parse_bgp_summary

        text = open(os.path.join(OPS, "r3__show_ip_bgp_summary.txt")).read()
        junk = "0 BGP route-map cache entries using 0 bytes of memory"
        assert junk in text, "the junk line is r3's own"
        inside = text.rstrip("\n") + "\n" + junk + "\n"
        assert [p["neighbor"] for p in parse_bgp_summary(inside)["peers"]] == ["198.51.100.1"]


class TestAPeerOutsideManagementIsNamed:
    """The operator's point (2026-09-27): r3's and r4's only BGP peer is r5,
    retired from management. "Established" is one side's report of a
    two-sided fact, so the claim names the dependency rather than hiding it."""

    def test_r3s_peers_are_named(self, monkeypatch):
        amap = gs.managed_addresses(_fleet_configs(MANAGED))
        per = snapshot(monkeypatch, "r3")["routing_neighbors"]["protocols"]
        outside, _ = gs.outside_management(per, amap)
        assert outside == ["bgp 198.51.100.1", "bgp 2001:DB8:51::2"], outside

    def test_the_control_managing_r5_removes_the_dependency(self, monkeypatch):
        amap = gs.managed_addresses(_fleet_configs(MANAGED + ("r5",)))
        per = snapshot(monkeypatch, "r3")["routing_neighbors"]["protocols"]
        assert gs.outside_management(per, amap)[0] == []

    def test_ospf_neighbours_are_named_by_router_id_and_inside(self, monkeypatch):
        """r3's OSPF neighbours are r1, r2, r4 by their loopbacks: inside."""
        amap = gs.managed_addresses(_fleet_configs(MANAGED))
        per = snapshot(monkeypatch, "r3")["routing_neighbors"]["protocols"]
        outside, _ = gs.outside_management(per, amap)
        assert not [o for o in outside if o.startswith("ospf")]

    def test_ripng_next_hops_are_unattributed_not_guessed(self, monkeypatch):
        amap = gs.managed_addresses(_fleet_configs(MANAGED))
        per = snapshot(monkeypatch, "s1")["routing_neighbors"]["protocols"]
        outside, unattributed = gs.outside_management(per, amap)
        assert outside == [] and "link-local" in unattributed[0]

    def test_the_claim_says_what_it_rests_on_and_its_limits(self, monkeypatch):
        amap = gs.managed_addresses(_fleet_configs(MANAGED))
        devices = [{"hostname": h} for h in ("r3", "s3")]
        snap = gs.take(devices, lambda d: snapshot(monkeypatch, d["hostname"]), intent,
                       address_map=amap)
        lines = gs.claim_lines(snap)
        assert snap["claim"] == gs.WORKING
        assert lines[0].startswith("Claim: configured and working, resting on 2 routing peer(s)")
        assert "Outside management: r3: bgp 198.51.100.1, bgp 2001:DB8:51::2" in lines
        assert lines[-1].startswith("Limits: the tool sees what the managed devices report")

    def test_no_snapshot_still_states_its_limits(self):
        assert gs.claim_lines(None)[-1].startswith("Limits:")

    def test_not_assessed_says_so(self, monkeypatch):
        snap = gs.take([{"hostname": "s3"}], lambda d: snapshot(monkeypatch, "s3"), intent)
        assert "Outside management: NOT assessed (no address map was supplied)" in \
            gs.claim_lines(snap)
