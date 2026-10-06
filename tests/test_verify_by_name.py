"""C506 phase 1 (board approved 2026-10-06): verify judges interfaces BY NAME against what the
program intends, and fails AT ONCE on an unexpected hard failure.

Before: verify COUNTED interfaces up before and after, after waiting out every routing
protocol's window and BGP's hold time. So a program's own `shutdown` was a loss, tw-ztp-a
stayed broken 4 min 40 s over an interface loss visible at the first read, and a cable move
(one interface down, another up) netted to zero and would hide a third lost at the same time.

Now: the program's expected effects are derived (an interface it shuts goes down, one it brings
up comes up); an interface up before and down after that the program did not shut is
unexpected, given the short "unexpected" settle (10 s, the installation's default) and then a
failure at once, the slow waits skipped; one the program brings up must be up; a read that
named no interface falls back to counting, and the result says which comparison ran.

On r3's real interfaces (tests/fixtures/operational) and test_bgp_hold_watch's world (r3's real
config and BGP table, a fake clock).
"""

import os

import pytest

from modules import pipeline
from modules.nsot import expected_effects as fx
from tests.test_bgp_hold_watch import _summary, world  # noqa: F401 (the fixture)

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "operational")
R3_INTERFACES = open(os.path.join(
    FIX, "r3__show_interfaces_include_line_protocol_internet_address.txt"),
    encoding="utf-8").read()
R3_STATES = fx.interface_states(R3_INTERFACES)


def _text(states):
    words = {"up": "up, line protocol is up", "down": "down, line protocol is down",
             "admin_down": "administratively down, line protocol is down"}
    return "\n".join(f"{n} is {words[s]} " for n, s in states.items())


class TestTheParts:
    def test_r3s_real_read_names_every_interface(self):
        assert R3_STATES == {"GigabitEthernet1": "up", "GigabitEthernet2": "up",
                             "GigabitEthernet3": "up", "GigabitEthernet4": "up",
                             "Loopback0": "up"}

    def test_states_by_line_protocol_and_admin(self):
        got = fx.interface_states(
            "GigabitEthernet3 is administratively down, line protocol is down \n"
            "GigabitEthernet4 is up, line protocol is down \n"
            "Loopback1 is up, line protocol is up \n  Internet address is 192.0.2.1/32")
        assert got == {"GigabitEthernet3": "admin_down", "GigabitEthernet4": "down",
                       "Loopback1": "up"}

    @pytest.mark.parametrize("short, full", [("Gi3", "GigabitEthernet3"),
                                             ("gi0/1", "GigabitEthernet0/1"),
                                             ("Lo1", "Loopback1"), ("Vlan10", "Vlan10"),
                                             ("Po2", "Port-channel2")])
    def test_names_as_the_device_prints_them(self, short, full):
        assert fx.canonical(short) == full

    def test_the_program_s_own_effects(self):
        assert fx.derive(["interface Loopback1", " shutdown", "exit"]) == {
            "down": ["Loopback1"], "up": []}
        assert fx.derive(["interface Gi3", " shutdown", "exit", "interface Gi4",
                          " no shutdown", " shutdown", " no shutdown", "exit",
                          "router ospf 1", " shutdown"]) == {
            "down": ["GigabitEthernet3"], "up": ["GigabitEthernet4"]}

    def test_a_cable_move_cannot_hide_a_third_loss(self):
        """Gi3 shut and Gi4 and a new Gi5 brought up: the up COUNT is the same before and
        after, and Loopback0, which nothing touched, is lost."""
        before = dict(R3_STATES, GigabitEthernet5="admin_down")
        before["GigabitEthernet4"] = "admin_down"
        after = dict(before, GigabitEthernet3="admin_down", GigabitEthernet4="up",
                     GigabitEthernet5="up", Loopback0="down")
        assert sum(s == "up" for s in before.values()) == sum(s == "up" for s in after.values())
        got = fx.judge({"down": ["GigabitEthernet3"], "up": ["GigabitEthernet4",
                                                            "GigabitEthernet5"]}, before, after)
        assert got["lost_expected"] == ["GigabitEthernet3"]
        assert got["lost_unexpected"] == ["Loopback0"] and got["not_up"] == []


@pytest.fixture
def run(world, monkeypatch):  # noqa: F811
    """r3 with its interfaces: *before* and *after* (the read after the push), and *later*, the
    reads the settle makes, in order (the last repeats)."""
    def build(program, before, after, later=None):
        ctx, clock = world(_summary())
        ctx.rendered_commands = {"x": program}
        ctx.pre_snapshots["x"]["interfaces"] = {"states": before,
                                                "up_count": list(before.values()).count("up")}
        ctx.post_snapshots["x"]["interfaces"] = {"states": after,
                                                 "up_count": list(after.values()).count("up")}
        reads = list(later or [after])
        calls = []

        def read(_conn, command):
            calls.append(command)
            return _text(reads.pop(0) if len(reads) > 1 else reads[0])
        monkeypatch.setattr("modules.commands.run_device_command", read)
        return ctx, clock, calls
    return build


class TestVerify:
    def test_the_program_s_own_shutdown_is_its_effect_never_a_loss(self, run):
        ctx, clock, _calls = run(["interface GigabitEthernet3", " shutdown", "exit"], R3_STATES,
                                 dict(R3_STATES, GigabitEthernet3="admin_down"))
        pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert v["ok"] is True and v["issues"] == []
        assert v["interfaces"]["compared_by"] == "name"
        assert v["interfaces"]["lost_expected"] == ["GigabitEthernet3"]
        assert v["failed_at_once"] is False and v["bgp_watch"]["state"] == "converged"

    def test_an_untouched_interface_lost_fails_at_once_without_the_hold_time(self, run):
        lost = dict(R3_STATES, GigabitEthernet4="down")
        ctx, clock, calls = run(["interface Loopback9", " description x", "exit"], R3_STATES,
                                lost)
        with pytest.raises(pipeline.PipelineStageError):
            pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert v["failed_at_once"] is True and v["bgp_watch"] is None
        assert any("GigabitEthernet4" in i and "did not touch" in i for i in v["issues"])
        assert v["unexpected_settle"]["seconds"] == 10, "the settle it used is named"
        assert sum(clock.slept) <= 12, f"waited {clock.slept}: the hold time was waited out"
        assert calls, "the interfaces were read again within the settle"

    def test_an_untouched_interface_that_comes_back_within_the_settle_is_not_a_failure(self,
                                                                                       run):
        flap = dict(R3_STATES, GigabitEthernet4="down")
        ctx, clock, _calls = run(["interface Loopback9", " description x", "exit"], R3_STATES,
                                 flap, later=[R3_STATES])
        pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert v["ok"] is True and v["failed_at_once"] is False
        assert v["interfaces"]["lost_unexpected"] == []
        assert v["bgp_watch"]["state"] == "converged", "the ordinary checks then run"

    def test_an_interface_the_program_brings_up_must_be_up(self, run):
        before = dict(R3_STATES, GigabitEthernet4="admin_down")
        ctx, clock, _calls = run(["interface GigabitEthernet4", " no shutdown", "exit"],
                                 before, before)
        with pytest.raises(pipeline.PipelineStageError):
            pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert v["interfaces"]["not_up"] == ["GigabitEthernet4"]
        assert any("brings up GigabitEthernet4" in i for i in v["issues"])

    def test_a_read_that_named_no_interface_falls_back_to_counting_and_says_so(self, run):
        ctx, clock, _calls = run(["interface Loopback9", " description x", "exit"], {}, {})
        ctx.pre_snapshots["x"]["interfaces"] = {"up_count": 5}
        ctx.post_snapshots["x"]["interfaces"] = {"up_count": 4}
        with pytest.raises(pipeline.PipelineStageError):
            pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert v["interfaces"]["compared_by"] == "count"
        assert any("5 up before → 4 up after" in i for i in v["issues"])


def test_the_snapshot_keeps_the_names_from_the_whole_read(monkeypatch):
    """The display copy is cut at 3000 characters; the names are parsed from the whole read."""
    many = "\n".join(f"GigabitEthernet0/{n} is up, line protocol is up " for n in range(120))
    monkeypatch.setattr("modules.commands.run_device_command", lambda c, cmd: many)
    monkeypatch.setattr(pipeline, "_detect_routing_neighbors", lambda c: {})
    snap = pipeline._capture_operational_snapshot(None, "x", "s9")
    assert len(snap["interfaces"]["output"]) <= 3000 < len(many)
    assert len(snap["interfaces"]["states"]) == 120
