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
        edit = lambda cmd, t: t.replace("4d13h           3", "never    Idle") \
            if cmd == "show ip bgp summary" else t
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
    item = R.GoldenItem(name, f"hostname {name}\n", "203.0.113.1", netbox_id=42)
    return R.save_golden("Lab", [item], source="save_all", allow_new=True,
                         operational=operational)


WORKING_SNAP = {"taken_at": "t", "claim": gs.WORKING, "working": True,
                "devices": {"R1": {"working": True, "declared": ["ospf"],
                                   "why": ["ospf: 5 neighbour(s), all FULL or 2WAY"],
                                   "interfaces_up": 4, "routes": 13}},
                "unread": [], "not_working": [], "not_read": list(gs.NOT_READ)}


@pytestmark_git
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
        # reader is patched ONCE, before main, and answers for whichever
        # device is connected.
        current = {"host": None}
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, cmd, **kw: read_from_captures(current["host"])(conn, cmd))

        def connect(dev, work):
            if dev["hostname"] in unreachable:
                raise OSError("timed out")
            current["host"] = dev["hostname"]
            return work(None)
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
