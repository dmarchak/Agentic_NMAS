"""C1383 (the operator, 2026-10-19): the capture guard's narrow NEW-HARDWARE exception.

The lab's redeploy gave two C8000v routers (IOS-XE 17.06.01a) a new NIC each: r2 gained
GigabitEthernet4, r4 GigabitEthernet5. Each device then printed that interface's bare default
block, and each golden lacked the interface. r2's deploy of committed intent for Gi4 (shutdown,
a description) was confirmed by hash and refused before anything was sent by C78's guard: "the
device is not the capture this program was computed against: lines only in the capture 0, only
on the device 1 (interface GigabitEthernet4)". Capturing would bake the drift into the golden.

The operator's conditions, any one failing still refusing with today's words:
1. the interface is ABSENT from the golden entirely (an interface the golden has, now at its
   defaults, is someone defaulting it: drift);
2. the device-only lines are that platform's MEASURED default block exactly, per dialect (one
   extra line refuses; an unmeasured platform refuses);
3. the confirmed program configures that same interface;
4. the receipt records the accepted lines, and the deploy's record clears the drift item and row.

The golden is the real r2 capture (tests/fixtures/configs/fleet/r2.cfg); the device is that
capture plus the measured block after GigabitEthernet3's, a minimal edit; the measured blocks
are tests/fixtures/operational/interface_defaults/c8000v_17.06_new_nic.txt, read independently
of the product's data file.
"""

import json
import os
import re
import time

import pytest

import modules.pipeline as P
from modules.nsot import interface_defaults, receipts
from modules.nsot.deploy import (device_against_capture, device_moved_reason,
                                 merge_commands)
from tests.test_coverage_deploy import _plan, r6_probe_unsent  # noqa: F401 (the fixture)
from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r2.cfg"),
          encoding="utf-8").read()
MEASURED = os.path.join(ROOT, "tests", "fixtures", "operational", "interface_defaults",
                        "c8000v_17.06_new_nic.txt")
IOSXE, IOS = "cisco_iosxe", "cisco_ios"
IP = "192.0.2.12"

#: Where the new NIC's block sits in r2's running config: after GigabitEthernet3's block.
ANCHOR = " no mop sysid\n!\nrouter ospf 1"


def _measured_blocks() -> dict:
    """``{interface: [child lines]}`` from the fixture, parsed here (not by the product)."""
    blocks, current = {}, None
    for line in open(MEASURED, encoding="utf-8").read().splitlines():
        if line.startswith("interface "):
            current = blocks.setdefault(line.split(" ", 1)[1], [])
        elif line.startswith(" ") and current is not None:
            current.append(line)
        else:
            current = None
    return blocks


BLOCKS = _measured_blocks()


def _block(interface: str, children=None) -> str:
    children = BLOCKS[interface] if children is None else children
    return "\n".join([f"interface {interface}"] + list(children)) + "\n"


def _with(config: str, block: str) -> str:
    """*config* with *block* inserted after GigabitEthernet3's block."""
    assert config.count(ANCHOR) == 1
    return config.replace(ANCHOR, " no mop sysid\n!\n" + block + "!\nrouter ospf 1")


#: The golden as `save_golden` writes it, and the device as it reads (its banner).
GOLDEN = "! Golden config — edge2 (192.0.2.12)\n! Saved: 2026-10-19 18:00:00\n" + R2


def _device(interface="GigabitEthernet4", children=None, base=R2) -> str:
    return ("Building configuration...\n\nCurrent configuration : 9001 bytes\n"
            + _with(base, _block(interface, children)))


def _program(interface="GigabitEthernet4") -> list:
    """The confirmed program for intent configuring *interface* (shutdown, a description), as
    the deploy computes it: `merge_commands` of that intent against the capture."""
    intended = _with(R2, f"interface {interface}\n description to edge8 (planned)\n"
                         " no ip address\n shutdown\n")
    program = merge_commands(intended, R2)
    assert program[0] == f"interface {interface}", program
    return program


TODAYS_WORDS = ("the device is not the capture this program was computed against: lines only "
                "in the capture 0, only on the device 1 (interface GigabitEthernet4). Nothing "
                "was sent. Capture the device (its golden becomes what it runs now), then "
                "preview again")


class TestTheMeasurement:
    """Condition 2's data: the platform's measured default block, per dialect."""

    def test_the_fixture_holds_both_real_blocks_and_they_agree(self):
        assert set(BLOCKS) == {"GigabitEthernet4", "GigabitEthernet5"}
        assert BLOCKS["GigabitEthernet4"] == BLOCKS["GigabitEthernet5"]
        assert len(BLOCKS["GigabitEthernet4"]) == 5

    def test_the_products_data_is_the_measurement_exactly(self):
        """The product's row equals the fixture's blocks, read by a path that is not its own."""
        doc = json.load(open(interface_defaults.MEASURED_FILE, encoding="utf-8"))
        row = doc["by_dialect"][IOSXE]["GigabitEthernet"]
        assert row["lines"] == BLOCKS["GigabitEthernet4"]
        assert row["fixture"] == os.path.relpath(MEASURED, ROOT)
        assert set(doc["by_dialect"]) == {IOSXE}, "only IOS-XE is measured"

    @pytest.mark.parametrize("interface", ["GigabitEthernet4", "GigabitEthernet5"])
    def test_each_measured_block_is_the_default(self, interface):
        assert interface_defaults.unconfigured_interface_default(
            IOSXE, interface, BLOCKS[interface]) is True

    @pytest.mark.parametrize("children", [
        BLOCKS["GigabitEthernet4"] + [" description someone"],
        BLOCKS["GigabitEthernet4"][:-1],
        list(reversed(BLOCKS["GigabitEthernet4"])),
        [], ], ids=["one-extra", "one-fewer", "reordered", "empty"])
    def test_anything_else_is_not(self, children):
        assert interface_defaults.unconfigured_interface_default(
            IOSXE, "GigabitEthernet4", children) is False

    @pytest.mark.parametrize("dialect,interface", [
        (IOS, "GigabitEthernet4"), ("", "GigabitEthernet4"), ("eos", "GigabitEthernet4"),
        (IOSXE, "Loopback4"), (IOSXE, "GigabitEthernet")])
    def test_an_unmeasured_platform_or_interface_type_is_not(self, dialect, interface):
        assert interface_defaults.unconfigured_interface_default(
            dialect, interface, BLOCKS["GigabitEthernet4"]) is False

    def test_an_unreadable_measurement_accepts_nothing(self, tmp_path, monkeypatch):
        bad = tmp_path / "interface_defaults.json"
        bad.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(interface_defaults, "MEASURED_FILE", str(bad))
        assert interface_defaults.measured()["state"] == "unreadable"
        assert interface_defaults.unconfigured_interface_default(
            IOSXE, "GigabitEthernet4", BLOCKS["GigabitEthernet4"]) is False


class TestTheGuard:
    """`deploy.device_against_capture`: the operator's four cases, and the rest."""

    def test_the_new_nic_is_accepted_and_named(self):
        """The case itself: r2's Gi4, absent from the golden, at the measured default, which
        the confirmed program configures."""
        got = device_against_capture(GOLDEN, _device(), _program(), IOSXE)
        assert got == {"reason": "", "new_hardware": [
            {"interface": "GigabitEthernet4",
             "lines": ["interface GigabitEthernet4"] + BLOCKS["GigabitEthernet4"]}]}

    def test_the_second_routers_nic_is_accepted_too(self):
        got = device_against_capture(GOLDEN, _device("GigabitEthernet5"),
                                     _program("GigabitEthernet5"), IOSXE)
        assert got["reason"] == ""
        assert [n["interface"] for n in got["new_hardware"]] == ["GigabitEthernet5"]

    @pytest.mark.parametrize("golden_children", [
        [" description to edge8", " ip address 192.0.2.9 255.255.255.252", " negotiation auto",
         " no mop enabled", " no mop sysid"],
        # Only lines of the default block: nothing is only in the capture, so condition 1
        # (the interface is in the golden) is all that stops it.
        [" no ip address", " shutdown", " negotiation auto"],
    ], ids=["configured", "partly-defaults"])
    def test_a_configured_interface_now_at_its_defaults_is_refused(self, golden_children):
        """Condition 1: an interface the golden HAS, now printing the default block, is someone
        defaulting it: real drift, refused with today's words."""
        golden = GOLDEN.replace(R2, _with(R2, _block("GigabitEthernet4", golden_children)))
        device = _device()
        got = device_against_capture(golden, device, _program(), IOSXE)
        assert got["new_hardware"] == []
        assert got["reason"] == device_moved_reason(golden, device) != ""

    def test_a_default_block_plus_one_extra_line_is_refused(self):
        """Condition 2: one line more than the measured block."""
        device = _device(children=BLOCKS["GigabitEthernet4"] + [" description someone"])
        got = device_against_capture(GOLDEN, device, _program(), IOSXE)
        assert got == {"reason": TODAYS_WORDS, "new_hardware": []}

    def test_a_default_block_on_an_interface_the_program_does_not_touch_is_refused(self):
        """Condition 3: the program configures GigabitEthernet3, not the new NIC."""
        program = ["interface GigabitEthernet3", " description P2P (renamed)", "exit"]
        got = device_against_capture(GOLDEN, _device(), program, IOSXE)
        assert got == {"reason": TODAYS_WORDS, "new_hardware": []}

    def test_an_ios_device_with_the_same_block_is_refused(self):
        """Condition 2, per dialect: IOS has no measurement, so nothing is accepted."""
        got = device_against_capture(GOLDEN, _device(), _program(), IOS)
        assert got == {"reason": TODAYS_WORDS, "new_hardware": []}

    def test_no_program_is_todays_refusal(self):
        """A device with nothing to send (`_measure_unchanged`) configures no interface."""
        assert device_moved_reason(GOLDEN, _device()) == TODAYS_WORDS
        assert device_against_capture(GOLDEN, _device())["reason"] == TODAYS_WORDS

    def test_a_line_lost_from_the_capture_beside_the_new_nic_is_refused(self):
        device = _device().replace(" ip ospf priority 100\n", "", 1)
        got = device_against_capture(GOLDEN, device, _program(), IOSXE)
        assert got["new_hardware"] == [] and "lines only in the capture 1 (" in got["reason"]

    def test_a_second_device_only_change_beside_the_new_nic_is_refused(self):
        device = _device().replace("lldp run\n", "lldp run\nip domain lookup\n", 1)
        got = device_against_capture(GOLDEN, device, _program(), IOSXE)
        assert got["new_hardware"] == [] and "only on the device 2 (" in got["reason"]

    def test_an_interface_opened_twice_is_refused(self):
        """Condition 2 reads THE interface's block: a second block for it, carrying a line the
        first lacks, is merged by the comparison and must not hide behind the first."""
        device = _device().replace(
            "\nrouter ospf 1", "\ninterface GigabitEthernet4\n description someone\n!"
                               "\nrouter ospf 1", 1)
        got = device_against_capture(GOLDEN, device, _program(), IOSXE)
        assert got == {"reason": TODAYS_WORDS, "new_hardware": []}

    def test_only_an_interface_section_is_new_hardware(self):
        """Condition 0: the measurement is keyed by an interface's type, and a section that is
        not opened by `interface` is never read as one, however its name and lines look. The
        comparison is handed in directly: no IOS section looks like this, so the property is
        pinned on the guard itself."""
        from modules.nsot.deploy import _new_hardware
        lookalike = "GigabitEthernet4\n" + "\n".join(BLOCKS["GigabitEthernet4"]) + "\n"
        compared = {"equal": False, "only_left": [], "only_right": ["GigabitEthernet4"]}
        assert _new_hardware(R2, R2 + lookalike, compared,
                             ["GigabitEthernet4", " shutdown", "exit"], IOSXE) is None
        # The same shape opened by `interface` is accepted: the keyword is what differs.
        real = "interface " + lookalike
        compared = {"equal": False, "only_left": [], "only_right": ["interface GigabitEthernet4"]}
        assert _new_hardware(R2, R2 + real, compared,
                             ["interface GigabitEthernet4", " shutdown", "exit"], IOSXE)

    def test_the_device_as_captured_is_still_nothing(self):
        device = "Building configuration...\n\n" + R2
        assert device_against_capture(GOLDEN, device, _program(), IOSXE) == {
            "reason": "", "new_hardware": []}


class _Session:
    def __init__(self, running):
        self.running = running


@pytest.fixture
def stage_four(tmp_path, monkeypatch):
    """The real stage 4 against a device answering *running*, handed the confirmed program and
    the dialect as `_deploy_one` hands them."""
    from tests.test_pipeline import _ctx

    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path))
    monkeypatch.setattr(P, "_capture_operational_snapshot", lambda *a, **k: {})

    def run(running, program, dialect):
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda dev, pool, lock: _Session(running))
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, cmd, **k: conn.running)
        ctx = _ctx(list_name="Lab", device_ips=[IP],
                   selected_devices=[{"ip": IP, "hostname": "edge2"}])
        ctx.confirmed_commands = {IP: program}
        ctx.confirmed_capture = {IP: GOLDEN}
        ctx.capture_dialect = {IP: dialect}
        try:
            P._stage_pre_snapshot(ctx)
            return ctx, None
        except P.PipelineStageError as exc:
            return ctx, str(exc)
    return run


class TestStageFour:
    def test_the_new_nic_goes_on_and_is_kept_for_the_receipt(self, stage_four):
        ctx, error = stage_four(_device(), _program(), IOSXE)
        assert error is None and ctx.drifted == {}
        assert IP in ctx.pre_snapshots
        assert ctx.new_hardware == {IP: [
            {"interface": "GigabitEthernet4",
             "lines": ["interface GigabitEthernet4"] + BLOCKS["GigabitEthernet4"]}]}

    def test_an_ios_device_stops_before_anything_is_sent(self, stage_four):
        ctx, error = stage_four(_device(), _program(), IOS)
        assert ctx.drifted == {IP: TODAYS_WORDS} and TODAYS_WORDS in error
        assert ctx.new_hardware == {} and IP not in ctx.pre_snapshots

    def test_a_program_that_does_not_touch_it_stops_too(self, stage_four):
        ctx, error = stage_four(_device(), ["interface GigabitEthernet3",
                                            " description x", "exit"], IOSXE)
        assert ctx.drifted == {IP: TODAYS_WORDS} and error
        assert ctx.new_hardware == {}


class TestTheReceipt:
    """Condition 4, first half: the receipt names the device, the interface and the lines."""

    def test_the_row_carries_the_accepted_lines_masked(self):
        accepted = [{"interface": "GigabitEthernet4",
                     "lines": ["interface GigabitEthernet4"] + BLOCKS["GigabitEthernet4"]}]
        result = {"device": "edge2", "outcome": "deployed", "commands": _program(),
                  "new_hardware": accepted}
        (row,) = receipts.rows_for({"results": [result], "golden": {}}, list_name="Lab",
                                   action="deploy", actor="person@example.com",
                                   actor_kind="person")
        assert row["device"] == "edge2"
        assert row["new_hardware"] == accepted

    def test_a_secret_in_an_accepted_line_is_masked(self):
        secret = "$9$Zq3kVbT2mN8pQ4wXy7"
        result = {"device": "edge2", "outcome": "deployed", "new_hardware": [
            {"interface": "GigabitEthernet4",
             "lines": ["interface GigabitEthernet4", f" username x secret 9 {secret}"]}]}
        (row,) = receipts.rows_for({"results": [result], "golden": {}}, list_name="Lab",
                                   action="deploy", actor="a", actor_kind="person")
        assert secret not in json.dumps(row)

    def test_a_row_with_nothing_accepted_says_so(self):
        (row,) = receipts.rows_for({"results": [{"device": "edge2", "outcome": "deployed"}],
                                    "golden": {}}, list_name="Lab", action="deploy",
                                   actor="a", actor_kind="person")
        assert row["new_hardware"] == []


class TestTheApplyCarriesIt:
    """The route: the dialect reaches stage 4, and what stage 4 accepted reaches the receipt.
    r6 on test_profile_apply's lab; the pipeline is a fake."""

    def test_dialect_in_and_accepted_lines_out_to_the_receipt(self, lab, monkeypatch,  # noqa: F811
                                                              r6_probe_unsent):  # noqa: F811
        import routes.deploy as rd
        from tests import deploy_core

        seen, rows = [], []
        accepted = [{"interface": "GigabitEthernet4",
                     "lines": ["interface GigabitEthernet4"] + BLOCKS["GigabitEthernet4"]}]

        class Runner:
            def __init__(self, ctx):
                self.ctx = ctx
                seen.append(ctx)

            def run(self):
                ip = self.ctx.selected_devices[0]["ip"]
                self.ctx.new_hardware = {ip: accepted}
                self.ctx.final_status = "success"
                return self.ctx

        def write(list_name, report, action, confirmations, command_hashes, **kw):
            rows.extend(receipts.rows_for(report, list_name=list_name, action=action,
                                          actor="a", actor_kind="person"))
            return {"ok": True}
        monkeypatch.setattr("modules.pipeline.PipelineRunner", Runner)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        monkeypatch.setattr(rd, "_write_receipts", write)
        (d,) = _plan(lab, "profile")["devices"]
        deploy_core.post_apply(json={
            "confirmations": {"r6": d["capture_hash"]},
            "command_hashes": {"r6": d["command_hash"]},
            "list_name": "Lab", "scope": "profile"})
        (ctx,) = seen
        assert ctx.capture_dialect == {ctx.selected_devices[0]["ip"]: IOSXE}
        (row,) = [r for r in rows if r["device"] == "r6"]
        assert row["new_hardware"] == accepted


class TestTheDriftClears:
    """Condition 4, second half: after the deploy, r2's pending drift item is withdrawn and its
    drift row answered. Nothing new does it: the deploy's batch commit records the post-deploy
    capture through `save_golden`, whose `_supersede_drift_items` withdraws older drift items
    for the devices it recorded (`approval_queue.supersede_drift`) and answers the stored drift
    run's rows (`drift_check.answer_by_golden`). The capture the deploy records holds the new
    interface as configured, so the next drift run measures the device at its golden."""

    @pytest.fixture
    def cap(self, tmp_path, monkeypatch):
        from tests.test_capture import build_capture_lab
        return build_capture_lab(monkeypatch, tmp_path)

    def test_the_deploys_record_withdraws_the_item_and_answers_the_row(self, cap):
        import routes.deploy as rd
        from modules import approval_queue as Q
        from modules import drift_check as D
        from modules.nsot import roundtrip
        from tests.test_drift_items_withdrawn import _item, _status

        item = _item("r2", list_name="Lab")
        D._save_state({"last_check_ts": time.time() - 720, "last_result": {
            "ok": True, "inventory": 1, "checked": 1, "drifted": 1, "clean": 0,
            "drifted_devices": [{"hostname": "r2", "diff_lines": 6}],
            "skipped": [], "errors": [], "summary": "Drift detected on 1 device(s).",
            "timestamp": "2026-10-19 18:00:00", "triggered_by": "scheduled"}}, "Lab")
        # The device after the deploy: the new NIC at its defaults, with the program's lines.
        after = _with(cap["captured"], "interface GigabitEthernet4\n"
                                       " description to edge8 (planned)\n"
                                       + "\n".join(BLOCKS["GigabitEthernet4"]) + "\n")
        report = {"batch_id": "c1383", "results": [{
            "device": "r2", "outcome": "deployed", "program_hash": "0" * 16,
            "golden_pending": [{"hostname": "r2", "config_text": after,
                                "mgmt_ip": "203.0.113.12", "netbox_id": None,
                                "device_uid": "", "target_config": after}]}]}
        out = rd._commit_batch_golden("Lab", report, actor="person@example.com")
        assert out["ok"] and out["commit"], out
        e = _status(item, "Lab")
        assert e["status"] == "withdrawn", e
        assert e["withdrawn_reason"].startswith("superseded by commit ")
        last = D._load_state("Lab")["last_result"]
        assert last["drifted_devices"] == [] and last["answered"][0]["hostname"] == "r2"
        # And the golden is now the device: the next run finds nothing.
        from modules.nsot.manifest import find_by_name
        from modules.nsot.repo import committed_golden_for
        _identity, entry = find_by_name(cap["repo"], "r2")
        golden = committed_golden_for(cap["repo"], entry)["text"]
        assert roundtrip.stored_is_device(golden, after)["equal"] is True
        assert Q.DRIFT_ACTION == e["action_type"]
        assert re.search(r"^interface GigabitEthernet4$", golden, re.M)
