"""C178: verify reads BGP once more, no earlier than the hold time after the push.

`convergence.wait_for` returns at its FIRST passing read (10 s in), and verify
did not wait at all when the first post-push count matched the pre count.
IOS holds a BGP session up until its hold timer expires (180 s by default),
so a change that breaks BGP without resetting the TCP session at once (a
filter on TCP 179, a lost route to a multihop peer) read Established, passed,
and rolled back nothing. A reading taken before the session COULD have shown
the failure is not evidence that there was none.

From r3's REAL captures: its fleet config (two peers, IPv4 and IPv6, no
timers: IOS's 180 s) and its real `show bgp all summary`. The break is a
minimal edit of that real output (the IPv4 row's state field set to Idle, as
`test_pipeline_reads_real_output` does for C64). The hold time here is the
CONFIGURED one, an upper bound on the negotiated one: reading each peer's
negotiated hold time needs a real `show bgp all neighbors` capture, which is
the operator's (device access), and C117's real-device measurement stays
with its loop.
"""

import os

import pytest

from modules import pipeline
from modules.nsot.convergence import IOS_BGP_DEFAULT_HOLD, bgp_hold_times
from tests.test_pipeline_reads_real_output import capture, device

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R3 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r3.cfg"),
          encoding="utf-8").read()


def _summary(state_of_ipv4=None):
    """r3's real `show bgp all summary`, the IPv4 session's last field (its
    prefix count while Established) replaced by *state_of_ipv4*."""
    text = capture("r3", "show_bgp_all_summary")
    if state_of_ipv4 is None:
        return text
    out = []
    for line in text.splitlines():
        if line.startswith("198.51.100.1 "):
            fields = line.split()
            fields[-1] = state_of_ipv4
            line = " ".join(fields)
        out.append(line)
    return "\n".join(out) + "\n"


def _snap(monkeypatch, summary):
    real = device("r3")

    def reply(conn, command, **kw):
        if command == "show bgp all summary":
            return summary
        return real(conn, command, **kw)

    monkeypatch.setattr("modules.commands.run_device_command", reply)
    return pipeline._detect_routing_neighbors(None)


class Clock:
    """A clock that advances only when verify sleeps."""

    def __init__(self, now):
        self.now, self.slept = now, []

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.now += s


@pytest.fixture
def world(monkeypatch):
    def build(after_summary, *, pushed_at=1000.0, now=1010.0, config=R3):
        healthy = _snap(monkeypatch, _summary())
        assert pipeline._protocol_counts(healthy)["bgp"] == 2    # the fixture can reach it
        later = _snap(monkeypatch, after_summary)
        clock = Clock(now)
        ctx = pipeline.PipelineContext(
            config_type="template", device_ips=["x"], params={}, ip_params_map={},
            selected_devices=[{"ip": "x", "hostname": "r3"}], connections_pool={},
            pool_lock=None, config_id="t", settle_sleep=clock.sleep, settle_clock=clock)
        ctx.pre_snapshots = {"x": {"routing_neighbors": healthy}}
        ctx.post_snapshots = {"x": {"routing_neighbors": healthy, "running_config": config}}
        if pushed_at is not None:
            ctx.pushed_at = {"x": pushed_at}
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda *a, **k: None)
        # The read verify takes AFTER waiting: the device as it is by then.
        monkeypatch.setattr(pipeline, "_detect_routing_neighbors", lambda _c: later)
        return ctx, clock
    return build


class TestTheHoldTime:
    def test_r3s_real_config_is_the_ios_default_on_both_peers(self):
        h = bgp_hold_times(R3)
        assert set(h["peers"]) == {"198.51.100.1", "2001:DB8:51::2"}
        assert h["max"] == IOS_BGP_DEFAULT_HOLD == 180
        assert "IOS default" in h["basis"]

    def test_precedence_neighbor_then_group_then_process(self):
        cfg = ("router bgp 65001\n timers bgp 20 60\n neighbor G peer-group\n"
               " neighbor G timers 5 15\n neighbor 192.0.2.1 remote-as 65002\n"
               " neighbor 192.0.2.1 timers 3 9\n neighbor 192.0.2.2 peer-group G\n"
               " neighbor 192.0.2.3 remote-as 65003\n")
        h = bgp_hold_times(cfg)
        assert h["peers"] == {"192.0.2.1": {"hold": 9, "basis": "neighbor 192.0.2.1 timers"},
                              "192.0.2.2": {"hold": 15, "basis": "peer-group G timers"},
                              "192.0.2.3": {"hold": 60, "basis": "timers bgp"}}
        assert h["max"] == 60 and "G" not in h["peers"]

    def test_no_bgp_is_no_peer(self):
        assert bgp_hold_times("hostname r1\nrouter ospf 1\n network 10.0.0.0 0.0.0.255 area 0\n"
                              )["peers"] == {}


class TestVerifyWatchesToTheHoldTime:
    def test_a_session_gone_by_hold_expiry_FAILS_verify_and_rolls_back(self, world):
        ctx, clock = world(_summary("Idle"))
        with pytest.raises(pipeline.PipelineStageError) as exc:
            pipeline._stage_verify(ctx)
        assert "did not survive to its hold expiry" in str(exc.value)
        assert clock.slept == [170.0], "waited until 180 s after the push, not from now"
        w = ctx.verify_result["x"]["bgp_watch"]
        assert (w["state"], w["watched_s"], w["hold_s"], w["before"], w["after"]) == (
            "failed", 180, 180, 2, 1)

    def test_a_session_that_holds_passes_and_says_how_long_it_was_watched(self, world):
        ctx, clock = world(_summary())
        pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert v["ok"] is True and v["issues"] == []
        assert (v["bgp_watch"]["state"], v["bgp_watch"]["watched_s"]) == ("converged", 180)
        assert "IOS default" in v["bgp_watch"]["basis"]

    def test_a_configured_hold_time_is_what_is_waited(self, world):
        cfg = R3.replace("router bgp 65001\n", "router bgp 65001\n timers bgp 10 30\n")
        ctx, clock = world(_summary(), config=cfg)
        pipeline._stage_verify(ctx)
        assert clock.slept == [20.0] and ctx.verify_result["x"]["bgp_watch"]["hold_s"] == 30

    def test_past_the_hold_already_it_reads_at_once(self, world):
        ctx, clock = world(_summary(), now=1500.0)
        pipeline._stage_verify(ctx)
        assert clock.slept == [] and ctx.verify_result["x"]["bgp_watch"]["watched_s"] == 500

    def test_no_recorded_push_time_waits_the_whole_hold_from_now(self, world):
        ctx, clock = world(_summary(), pushed_at=None)
        pipeline._stage_verify(ctx)
        w = ctx.verify_result["x"]["bgp_watch"]
        assert clock.slept == [180.0] and "no push time was recorded" in w["since"]

    def test_an_unreadable_session_table_fails_it_never_passes(self, world, monkeypatch):
        ctx, _clock = world(_summary())

        def broken(_c):
            raise OSError("Socket is closed")

        monkeypatch.setattr(pipeline, "_detect_routing_neighbors", broken)
        with pytest.raises(pipeline.PipelineStageError) as exc:
            pipeline._stage_verify(ctx)
        assert "whether the sessions survived to hold expiry is unknown" in str(exc.value)

    def test_a_device_without_bgp_waits_for_nothing(self, world, monkeypatch):
        ospf_only = "hostname r1\nrouter ospf 1\n network 10.0.0.0 0.0.0.255 area 0\n"
        ctx, clock = world(_summary(), config=ospf_only)
        pipeline._stage_verify(ctx)
        assert clock.slept == []
        assert ctx.verify_result["x"]["bgp_watch"]["state"] == "skipped"


class TestThePushTimeIsRecorded:
    def test_the_deploy_stage_stamps_each_pushed_device(self, monkeypatch):
        clock = Clock(4242.0)
        ctx = pipeline.PipelineContext(
            config_type="template", device_ips=["x"], params={}, ip_params_map={},
            selected_devices=[{"ip": "x", "hostname": "r3"}], connections_pool={},
            pool_lock=None, config_id="t", settle_clock=clock)
        ctx.confirmed_commands = {"x": ["interface Loopback9", " description t", "exit"]}
        monkeypatch.setattr(pipeline, "_push_config", lambda *a, **k: "ok")
        monkeypatch.setattr(pipeline, "_canary_sanity_check", lambda *a, **k: True,
                            raising=False)
        pipeline._stage_deploy(ctx)
        assert ctx.pushed_at == {"x": 4242.0}


def test_the_receipt_keeps_the_watch_and_the_result_draws_it():
    from modules.nsot import receipts
    from modules.preview_confirm import operation_result
    from tests.payload_render import render_result

    watch = {"state": "converged", "hold_s": 180, "basis": "IOS default 180 s (no timers "
             "configured)", "since": "the push", "watched_s": 180, "before": 2, "after": 2}
    rows = receipts.rows_for({"results": [{
        "device": "r3", "outcome": "deployed", "commands": ["x"], "authorised": [],
        "verify": {"ok": True, "issues": [], "checked_protocols": ["bgp"], "pre": {},
                   "post": {}, "bgp_watch": watch}}]},
        list_name="Lab", action="deploy", actor="op", actor_kind="person")
    assert rows[0]["checks"]["bgp_watch"] == watch
    html = render_result(operation_result(rows, {"results": []}, {"ok": True, "path": "x"},
                                          "deploy"))
    assert "bgp read 180 s after the push (hold 180 s, IOS default" in html
