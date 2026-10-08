"""C78 (2026-10-07): the device is compared at apply with the capture its program was computed
against, and a device changed since is skipped as drifted with nothing sent.

The apply's "fresh" capture was the STORED one the preview used, so its hash check caught a
golden that moved and nothing else, and the screens had to say "the DEVICE is not compared". A
device changed by hand since its capture got a program computed against a stale capture
(merge-only could omit a line the device had lost; a restore at HEAD sent nothing by
construction). Now stage 4, which already reads the running config before anything is sent,
compares it with that capture by `roundtrip.stored_is_device`, the freshness check's own
comparison (measured on the host 2026-10-07 before this was built: all nine devices' Oxidized
copies read equivalent to their goldens, so the gate refuses no device today). A device with
nothing to send is compared on the read it already makes.

The configs are the real r1 capture (tests/fixtures/configs/r1_c8000v.cfg, its self-signed
certificate included); each case is one edit to it.
"""

import os
import re
import threading

import pytest

import modules.pipeline as P
from modules.nsot import roundtrip
from modules.nsot.deploy import (DEPLOYED, FAILED, SKIPPED_DRIFTED, CircuitBreaker,
                                 DeviceMoved, device_moved_reason)
from tests.test_coverage_deploy import _plan, r6_probe_unsent  # noqa: F401 (the fixture)
from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R1 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "r1_c8000v.cfg"),
          encoding="utf-8").read()
IP = "192.0.2.31"

#: The golden's own header, as `save_golden` writes it, and the device's banner lines.
GOLDEN = "! Golden config — r1 (192.0.2.31)\n! Saved: 2026-10-07 18:00:00\n" + R1
DEVICE = "Building configuration...\n\nCurrent configuration : 9001 bytes\n" + R1


def _without_first_description(text: str) -> tuple:
    line = next(ln for ln in text.splitlines() if ln.startswith(" description "))
    return text.replace(line + "\n", "", 1), line


class TestTheComparison:
    def test_a_device_read_is_its_golden_whatever_each_side_stamps(self):
        """The golden's header and the device's banner are not configuration."""
        assert roundtrip.stored_is_device(GOLDEN, DEVICE)["equal"] is True

    def test_a_line_the_device_lost_is_on_the_capture_side(self):
        device, lost = _without_first_description(DEVICE)
        got = roundtrip.stored_is_device(GOLDEN, device)
        assert got["equal"] is False
        assert [x.split(" :: ")[-1] for x in got["only_left"]] == [lost.strip()]
        assert got["only_right"] == []


class TestTheReason:
    def test_nothing_when_the_device_is_the_capture(self):
        assert device_moved_reason(GOLDEN, DEVICE) == ""

    def test_both_sides_named_and_a_secret_masked(self):
        secret = "$9$Zq3kVbT2mN8pQ4wXy7"
        device = DEVICE.replace("\nend", f"\nusername breakin privilege 15 secret 9 {secret}\nend")
        device, lost = _without_first_description(device)
        reason = device_moved_reason(GOLDEN, device)
        assert reason.startswith("the device is not the capture this program was computed "
                                 "against: lines only in the capture 1 (")
        assert lost.strip() in reason
        assert "only on the device 1 (username breakin" in reason
        assert secret not in reason
        assert "Nothing was sent. Capture the device" in reason


class _Session:
    def __init__(self, running):
        self.running = running


@pytest.fixture
def stage_four(tmp_path, monkeypatch):
    """The real stage 4 against a device answering *running*; its other reads are empty."""
    from tests.test_pipeline import _ctx

    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path))
    monkeypatch.setattr(P, "_capture_operational_snapshot", lambda *a, **k: {})

    def run(running, capture):
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda dev, pool, lock: _Session(running))
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, cmd, **k: conn.running)
        ctx = _ctx(list_name="Lab", device_ips=[IP],
                   selected_devices=[{"ip": IP, "hostname": "r1"}])
        ctx.confirmed_capture = None if capture is None else {IP: capture}
        try:
            P._stage_pre_snapshot(ctx)
            return ctx, None
        except P.PipelineStageError as exc:
            return ctx, str(exc)
    return run


class TestStageFour:
    def test_the_device_as_captured_goes_on(self, stage_four):
        ctx, error = stage_four(DEVICE, GOLDEN)
        assert error is None and ctx.drifted == {}
        assert P._pre_change(ctx, IP) == DEVICE

    def test_a_device_changed_since_its_capture_stops_before_anything_is_sent(self, stage_four):
        device, _lost = _without_first_description(DEVICE)
        ctx, error = stage_four(device, GOLDEN)
        assert set(ctx.drifted) == {IP}
        assert ctx.drifted[IP].startswith("the device is not the capture")
        assert error and ctx.drifted[IP] in error
        assert IP not in ctx.pre_snapshots

    def test_an_unreadable_running_config_is_not_a_match(self, stage_four):
        ctx, error = stage_four("", GOLDEN)
        assert ctx.drifted == {}
        assert error and "could not be compared with the capture" in error

    def test_a_run_with_no_capture_compares_nothing(self, stage_four):
        """Callers that computed against nothing stored (rotation, adoption) are unchanged."""
        device, _lost = _without_first_description(DEVICE)
        ctx, error = stage_four(device, None)
        assert error is None and ctx.drifted == {}

    def test_the_whole_run_sends_nothing_to_a_drifted_device(self, stage_four, monkeypatch):
        """The runner's own abort, with the real stage 4: the transport is never reached."""
        from tests.test_pipeline import _ctx
        sent = []
        monkeypatch.setattr(P, "_push_config", lambda dev, cmds, pool, lock: sent.append(cmds))
        for name in ("_stage_netbox_query", "_stage_ci_gate", "_stage_config_diff",
                     "_stage_post_snapshot", "_stage_verify", "_stage_save_golden",
                     "_stage_audit_log"):
            monkeypatch.setattr(P, name, lambda ctx: None)
        device, _lost = _without_first_description(DEVICE)
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda dev, pool, lock: _Session(device))
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, cmd, **k: conn.running)
        ctx = _ctx(list_name="Lab", device_ips=[IP],
                   selected_devices=[{"ip": IP, "hostname": "r1"}])
        ctx.confirmed_commands = {IP: ["interface GigabitEthernet1", " description x", "exit"]}
        ctx.confirmed_capture = {IP: GOLDEN}
        result = P.PipelineRunner(ctx).run()
        assert sent == [] and result.final_status == "failed"
        assert result.stages_failed == ["pre_snapshot"] and set(result.drifted) == {IP}


class TestADeviceWithNothingToSend:
    def _device(self):
        return {"ip": IP, "hostname": "r1", "device_type": "cisco_xe"}

    @pytest.fixture
    def repo(self, tmp_path, monkeypatch):
        from modules.nsot import repo as R
        R.init_repo(str(tmp_path / "config_repo"))
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path))
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: default)
        return str(tmp_path / "config_repo")

    def test_a_read_that_is_not_the_capture_raises_and_stages_nothing(self, repo, monkeypatch):
        import routes.deploy as RD
        from modules.nsot import repo as R
        device, _lost = _without_first_description(DEVICE)
        monkeypatch.setattr("modules.connection.with_temp_connection", lambda dev, fn: device)
        with pytest.raises(DeviceMoved, match="^the device is not the capture"):
            RD._measure_unchanged("Lab", self._device(), "r1", R1, capture=GOLDEN)
        assert "r1" not in R.staged_post_deploy(repo)

    def test_the_capture_read_back_is_measured_as_before(self, repo, monkeypatch):
        import routes.deploy as RD
        from modules.nsot import repo as R
        monkeypatch.setattr("modules.connection.with_temp_connection", lambda dev, fn: DEVICE)
        out = RD._measure_unchanged("Lab", self._device(), "r1", R1, capture=GOLDEN)
        assert out and out[0]["config_text"] == DEVICE and out[0]["sent_nothing"] is True
        assert R.staged_post_deploy(repo)["r1"] == DEVICE


class TestTheBreakerLeavesDriftAlone:
    def test_a_device_found_drifted_at_apply_does_not_count(self):
        """Someone touched a box, and nothing was sent (C10 counts every failure else)."""
        b = CircuitBreaker(limit=1)
        assert not b.counts({"device": "r1", "outcome": SKIPPED_DRIFTED})
        assert b.counts({"device": "r1", "outcome": FAILED, "stage": "pre_snapshot"})
        assert not b.counts({"device": "r1", "outcome": DEPLOYED, "verify": {"ok": True}})


class TestTheApply:
    """The route: the stored capture reaches the pipeline, and a drifted device is reported
    as drifted, not failed. r6 on test_profile_apply's lab; the pipeline is a fake."""

    def _apply(self, lab, monkeypatch, runner):
        import routes.deploy as rd
        monkeypatch.setattr("modules.pipeline.PipelineRunner", runner)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        monkeypatch.setattr(rd, "_write_receipts", lambda *a, **k: {})
        (d,) = _plan(lab, "profile")["devices"]
        return lab["client"].post("/deploy/apply", json={
            "confirmations": {"r6": d["capture_hash"]},
            "command_hashes": {"r6": d["command_hash"]},
            "list_name": "Lab", "scope": "profile"}).get_json()

    def test_the_pipeline_is_handed_the_capture_the_program_came_from(
            self, lab, monkeypatch, r6_probe_unsent):  # noqa: F811
        caught = []

        class Runner:
            def __init__(self, ctx):
                caught.append(ctx)

            def run(self):
                raise RuntimeError("stopped here: the test reads the context only")
        self._apply(lab, monkeypatch, Runner)
        ((ip, capture),) = caught[-1].confirmed_capture.items()
        assert ip == caught[-1].selected_devices[0]["ip"]
        assert roundtrip.stored_is_device(r6_probe_unsent, capture)["equal"] is True

    def test_a_drifted_device_is_reported_drifted_with_nothing_sent(
            self, lab, monkeypatch, r6_probe_unsent):  # noqa: F811
        class Runner:
            def __init__(self, ctx):
                self.ctx = ctx

            def run(self):
                ip = self.ctx.selected_devices[0]["ip"]
                self.ctx.drifted = {ip: "the device is not the capture (test)"}
                self.ctx.stages_failed = ["pre_snapshot"]
                self.ctx.final_status = "failed"
                return self.ctx
        body = self._apply(lab, monkeypatch, Runner)
        (row,) = [r for r in body["results"] if r["device"] == "r6"]
        assert row["outcome"] == SKIPPED_DRIFTED, row
        assert row["reason"] == "the device is not the capture (test)"
        assert body["breaker_tripped"] is False


class TestTheScreensSayItIsCompared:
    def test_the_gate_names_the_device_and_the_capture(self):
        from modules.preview_confirm import CAPTURE_GATE, CAPTURE_GATE_DETAIL
        assert CAPTURE_GATE == "device and capture unchanged since this preview"
        assert "is compared with that capture" in CAPTURE_GATE_DETAIL
        assert "not compared" not in CAPTURE_GATE_DETAIL

    def test_the_wizard_no_longer_says_a_device_change_is_not_detected(self):
        js = open(os.path.join(ROOT, "static", "js", "gen", "partials__deploy_wizard.1.js"),
                  encoding="utf-8").read()
        assert "NOT detected" not in js and not re.search(r"save its golden first", js)
        assert "compared with that capture before anything is sent" in js
