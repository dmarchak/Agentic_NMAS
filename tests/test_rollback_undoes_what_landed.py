"""C501 (the operator, 2026-10-05, the throwaway session's Part 5.3, C117's loop: the rollback's
first real run). A deploy to tw-ztp-a sent `interface Loopback1 / shutdown / exit`; the device
took all three lines; verify failed correctly at 181 s (BGP dropped past its hold). Then:

1. the rollback said "nothing of the push landed" and filed ` shutdown` as "rejected by the
   device, never applied", and sent nothing: `landed` was whole-line text new since the
   snapshot, and ` shutdown` was not new text (another interface printed it);
2. the push had already written startup (`write memory` two seconds after it, before verify),
   so the change was saved whatever the rollback did;
3. the card said "received 3 lines; matches the program" and "nothing to undo" together.

The device here has the shape that hid it: GigabitEthernet4 already shut down. Fake
connections stand in for the device; the pipeline's own functions run.
"""

import threading

import pytest

PUSHED = ["interface Loopback1", " shutdown", "exit"]
PRE = ("hostname tw-a\n"
       "interface Loopback1\n ip address 192.0.2.81 255.255.255.255\n"
       "interface GigabitEthernet4\n no ip address\n shutdown\n")
POST = ("hostname tw-a\n"
        "interface Loopback1\n ip address 192.0.2.81 255.255.255.255\n shutdown\n"
        "interface GigabitEthernet4\n no ip address\n shutdown\n")
IP = "192.0.2.81"


def _token():
    """A stored credential as a row holds it (B14: always a token, an empty value too)."""
    from modules.device import fernet
    return fernet.encrypt(b"").decode()


def _ctx():
    from modules.pipeline import PipelineContext

    ctx = PipelineContext(
        config_type="template", device_ips=[IP], params={}, ip_params_map={},
        selected_devices=[{"ip": IP, "hostname": "tw-a", "username": "u",
                           "device_type": "cisco_xe", "password": _token(), "secret": _token()}],
        connections_pool={},
        pool_lock=threading.Lock(), config_id="tpl-tw-a", settle_sleep=lambda _s: None)
    ctx.rendered_commands = {IP: list(PUSHED)}
    return ctx


class _Device:
    """The device's running config: POST until an undo is sent, then the undo applied."""

    def __init__(self):
        self.running = POST
        self.sent = []

    def fresh(self, _dev, func):
        dev = self

        class _Conn:
            def send_command(self, _cmd, read_timeout=None):
                return dev.running
        return func(_Conn())

    def restore(self, _conn, cmds):
        self.sent.extend(cmds)
        if cmds == ["interface Loopback1", " no shutdown", "exit"]:
            self.running = PRE


@pytest.fixture
def device(monkeypatch):
    import modules.connection as C
    import modules.pipeline as P

    d = _Device()
    monkeypatch.setattr(P, "_pre_change", lambda _ctx, ip: PRE)
    monkeypatch.setattr(C, "with_temp_connection", d.fresh)
    monkeypatch.setattr(C, "get_persistent_connection", lambda dev, pool, lock: object())
    monkeypatch.setattr(P, "_restore_config", d.restore)
    monkeypatch.setattr(P, "_note_rolled_back_intent", lambda ctx: None)
    monkeypatch.setattr("modules.list_settings.value", lambda _l, _k, d=None: d)
    return d


class TestTheRunThatFailed:
    def test_a_completed_push_that_failed_verify_is_undone(self, device):
        from modules.pipeline import _capture_failure_state, _stage_rollback

        ctx = _ctx()
        ctx.push_results = {IP: {"ok": True, "output": ""}}
        _capture_failure_state(ctx)
        _stage_rollback(ctx)
        assert device.sent == ["interface Loopback1", " no shutdown", "exit"]
        assert ctx.rollback_outcome[IP]["state"] == "restored", ctx.rollback_outcome[IP]
        assert not ctx.rollback_not_undone.get(IP), "nothing was rejected: the push completed"
        assert ctx.final_status == "rolled_back"

    def test_the_capture_records_the_line_under_its_interface(self, device):
        from modules.pipeline import _capture_failure_state

        ctx = _ctx()
        ctx.push_results = {IP: {"ok": True, "output": ""}}
        _capture_failure_state(ctx)
        assert ctx.failure_state[IP]["landed"] == [[["interface Loopback1"], "shutdown"]]


class TestNothingToUndoIsReadBack:
    def test_an_empty_undo_over_a_device_that_holds_the_push_is_not_nothing_to_undo(
            self, device, monkeypatch):
        """However the undo came out empty, "nothing to undo" is read back before it is
        said; the device still holding the push makes it incomplete, naming what remains."""
        import modules.nsot.deploy as D
        from modules.pipeline import _capture_failure_state, _stage_rollback

        real, calls = D.rollback_commands, []

        def first_empty(*a, **k):
            calls.append(1)
            return [] if len(calls) == 1 else real(*a, **k)
        monkeypatch.setattr(D, "rollback_commands", first_empty)
        ctx = _ctx()
        ctx.push_results = {IP: {"ok": True, "output": ""}}
        _capture_failure_state(ctx)
        _stage_rollback(ctx)
        out = ctx.rollback_outcome[IP]
        assert out["state"] == "incomplete" and " no shutdown" in out["remaining"], out
        assert ctx.final_status == "rollback_failed"

    def test_a_push_the_device_already_held_is_nothing_to_undo_read_back(self, device):
        from modules.pipeline import _capture_failure_state, _stage_rollback

        device.running = PRE
        ctx = _ctx()
        ctx.rendered_commands = {IP: ["interface GigabitEthernet4", " shutdown", "exit"]}
        ctx.push_results = {IP: {"ok": True, "output": ""}}
        _capture_failure_state(ctx)
        _stage_rollback(ctx)
        assert device.sent == [] and ctx.rollback_outcome[IP]["state"] == "nothing_to_undo"


class TestAChangeIsSavedOnlyOnceItPasses:
    def test_the_push_does_not_save(self, monkeypatch):
        import modules.connection as C
        import modules.pipeline as P

        calls = []

        class _Conn:
            def enable(self):
                calls.append("enable")

            def send_config_set(self, cmds, **_k):
                calls.append("send")
                return ""

            def save_config(self):
                calls.append("save")
        monkeypatch.setattr(C, "get_persistent_connection", lambda d, p, l: _Conn())
        P._push_via_netmiko({"ip": IP}, PUSHED, {}, threading.Lock())
        assert calls == ["enable", "send"], calls

    @pytest.mark.parametrize("verify_passes", [True, False])
    def test_save_startup_runs_after_verify_and_only_when_it_passed(self, monkeypatch,
                                                                     verify_passes):
        import modules.pipeline as P
        from modules.pipeline import STAGE_NAMES, PipelineRunner, PipelineStageError

        order = []
        for name in STAGE_NAMES:
            if name == "audit_log":
                monkeypatch.setattr(P, "_stage_audit_log", lambda ctx: order.append("audit_log"))
                continue

            def stage(ctx, _n=name):
                order.append(_n)
                if _n == "deploy":
                    ctx.push_results = {IP: {"ok": True, "output": ""}}
                if _n == "verify" and not verify_passes:
                    raise PipelineStageError("bgp established 1 -> 0")
            if name != "save_startup":
                monkeypatch.setattr(P, f"_stage_{name}", stage)
        saved = []
        monkeypatch.setattr("modules.nsot.onboard.persist_on_device",
                            lambda ip, *a, **k: (saved.append(ip), order.append("save"),
                                                 {"ok": True})[2])
        monkeypatch.setattr(P, "_capture_failure_state", lambda ctx: None)
        monkeypatch.setattr(P, "_stage_rollback", lambda ctx: order.append("rollback"))
        PipelineRunner(_ctx()).run()
        if verify_passes:
            assert order.index("save") == order.index("verify") + 1, order
            assert saved == [IP]
        else:
            assert "save" not in order and saved == [], (order, saved)
            assert order[-2:] == ["rollback", "audit_log"]

    def test_a_failed_save_is_reported_never_rolled_back(self, monkeypatch):
        import modules.pipeline as P
        from modules.pipeline import PipelineStageError

        def boom(ip, *a, **k):
            raise OSError("timed out")
        monkeypatch.setattr("modules.nsot.onboard.persist_on_device", boom)
        ctx = _ctx()
        ctx.push_results = {IP: {"ok": True}}
        with pytest.raises(PipelineStageError, match="NOT saved to startup"):
            P._stage_save_startup(ctx)
        assert ctx.saved_startup[IP]["ok"] is False
        assert dict(P._STAGE_TABLE)["save_startup"] == "continue"


class TestTheCardNeverSaysRejectedForACompletedPush:
    def _rows(self, stage):
        return [{"device": "tw-a", "outcome": "failed", "stage": stage, "sent": True,
                 "program": PUSHED, "rollback": {"performed": True, "state": "nothing_to_undo",
                                                 "not_undone": [" shutdown"]}}]

    def test_after_a_completed_push_it_says_the_device_may_hold_them(self):
        from modules.preview_confirm import operation_result
        out = operation_result(self._rows("verify"), {}, {"ok": True}, "deploy")
        kinds = {d["kind"]: d["text"] for d in out["did_not"]["items"]}
        assert "not_undone" not in kinds and "may still hold them" in kinds["not_restored"]

    def test_a_push_that_stopped_part_way_still_names_its_rejected_lines(self):
        from modules.preview_confirm import operation_result
        out = operation_result(self._rows("deploy"), {}, {"ok": True}, "deploy")
        assert any(d["kind"] == "not_undone" and "never applied" in d["text"]
                   for d in out["did_not"]["items"])
