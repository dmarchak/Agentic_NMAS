"""The port bounce, and the OSPF adjacency reset through it (`modules/heal/bounce.py`; board H's
amendment, item 2, part H20; docs/HEAL_TO_INTENT.md 19.4, guards 13c and 13f; C2424, C2425,
C2694, C2702, C2704). No network and no device: the device is tests/test_nmas_revert_probe.py's
FakeIOS (its answers modelled on the command reference, the running configuration and the
brief real captures), extended here with a port down while administratively up and an OSPF
neighbour table; the decision's reads are faked at its `Sources`.

- **The program and its bounds**: one batch, its hash over the program and its authorised
  ``shutdown`` with the policy's reason; the settle bound 2.5 times the slowest measured settle,
  the planned window the timer, the watch past it and the settle bound (398 s).
- **The decision** (`consider`): no action chosen records nothing; **dry run records "would
  have bounced" and sends nothing**; AUTO with the kind allowed on a lab network is ``heal``;
  each guard's refusal by name: 13a (came back by itself), 13b (the far end held, with when it
  is checked again), 13c (the management address by intent, Mercury's route out of the
  interface by CEF, IPv4 and IPv6, an egress that cannot be read, the only path by the blast
  radius), 13d (a second bounce within the window is the dampening proposal), 13e (the flap
  record unreadable), 13f (no archive in intent: Never; a platform the trial did not measure).
- **The act** (`apply`): the window recorded BEFORE the batch and naming the port, or nothing
  sent; the hash recomputed; the port that came back by itself and 13c judged again on the held
  session; the confirm only once Mercury is back in and the post-check passes; the revert
  timer's revert when Mercury is not back; the repair, and NOT RESTORED; the stability window
  (stable, still flapping, unread); an OSPF reset's adjacency formed or not; never a save; the
  device held throughout; the records (the decisions store, a halt, the step log).
- **The flap record** leaves a planned window's transitions out of guard 13e's count (C2694).
- **Needs attention**: a held bounce and every end but bounced is one row; bounced is none.
"""

import ipaddress
import json
import time
import types

import pytest

from tests.test_nmas_revert_probe import (BRIEF, CEF_VIA_GI4, MANAGER, MANAGER_V6, MGMT_IF,
                                          MGMT_IP, SAVE, T0, Clock, FakeIOS)
from tests.test_nmas_revert_probe import no_hold_survives_a_test  # noqa: F401 (autouse)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)

NET = "Default"
NETWORK_MGMT = str(ipaddress.ip_interface(f"{MGMT_IP}/24").network)
R4_ON_MGMT = str(ipaddress.ip_interface(f"{MGMT_IP}/24").network.network_address + 20)
GI4 = "GigabitEthernet4"
DEV = {"hostname": "r3", "ip": MGMT_IP, "device_type": "cisco_xe"}
FAR = {"hostname": "r4", "ip": R4_ON_MGMT, "device_type": "cisco_xe"}


def B():
    from modules.heal import bounce
    return bounce


def intents(archive=True, r4_on_mgmt=True):
    """r3's management on Gi1 and its link to r4 on Gi4; r4 reaching Mercury's subnet by its own
    Gi2 unless *r4_on_mgmt* is False (then Gi4 is r3's only path to r4)."""
    r3 = {"platform": "cisco_iosxe", "interfaces": [
        {"name": "GigabitEthernet1", "ipv4": f"{MGMT_IP} 255.255.255.0"},
        {"name": GI4, "ipv4": "192.0.2.200 255.255.255.254", "ipv6": ["2001:db8:2:e::1/64"]}]}
    if archive:
        r3["archive"] = {"path": "bootflash:nmas-archive"}
    r4 = {"platform": "cisco_iosxe", "interfaces": [
        {"name": GI4, "ipv4": "192.0.2.201 255.255.255.254"}]}
    if r4_on_mgmt:
        r4["interfaces"].append({"name": "GigabitEthernet2", "ipv4": f"{R4_ON_MGMT} 255.255.255.0"})
    return {"r3": r3, "r4": r4}


def mode(m="dry_run", kinds=(), stage="lab", **guards):
    values = {"heal_person_working_changes": 3, "heal_person_working_minutes": 30,
              "heal_bounce_per_port_hour": 1, "heal_repeat_halts_hours": 24,
              "heal_flap_transitions": 3, "heal_flap_minutes": 10,
              "heal_max_per_device_hour": 3, "heal_max_per_network_hour": 10, **guards}
    return {"network": NET, "mode": m, "set": m, "state": "ok", "words": f"{m} for the test",
            "fingerprint": "fp-1", "kinds_auto": list(kinds),
            "confirmed": {"by": "op@example.invalid", "reason": "the bounce under test",
                          "fingerprint": "fp-1"},
            "guards": {k: {"value": v} for k, v in values.items()},
            "stage": {"stage": stage}, "stopped": {"stopped": False}}


def shown(state):
    return f"{GI4} is {state}, line protocol is {'up' if state == 'up' else 'down'} \n  MTU 1500"


PICK_DIAGNOSIS = {"hypotheses": [{
    "rule": "down_admin_up", "case": "far_end_up", "strength": "decisive", "incomplete": [],
    "claim": "r3 Gi4 is down while administratively up, and r4 Gi4 is up", "id": "diag:1",
    "at": {"host": "r3", "interface": GI4, "far_host": "r4", "far_interface": GI4}}]}
OSPF_DIAGNOSIS = {"hypotheses": [dict(PICK_DIAGNOSIS["hypotheses"][0],
                                      rule="ospf_not_full_one_neighbour", case="",
                                      strength="strong")]}


def ospf_detail(state):
    return (f" Neighbor 192.0.2.14, interface address 192.0.2.201, interface-id 10\n"
            f"    In the area 0 via interface {GI4}\n    Neighbor priority is 0, State is "
            f"{state}, 6 state changes\n")


class Src:
    """The bounce's sources, faked: the policy, the stores and each read as the test sets it;
    the act's session on a FakeIOS."""

    def __init__(self, *, m=None, answers=None, far="up", intents_=None, nets=None, flap=None,
                 rows=(), holder=None, planned=None, manager=(MANAGER, ""), dev=None,
                 clock=None, transitions=None):
        self.clock_ = clock or Clock()
        self.clock, self.sleep = self.clock_.time, self.clock_.sleep
        self._mode, self._rows, self._holder, self._planned = m or mode(), list(rows), holder, \
            planned
        self._intents = intents() if intents_ is None else intents_
        self._nets = [NETWORK_MGMT] if nets is None else nets
        self._manager, self.dev = manager, dev
        cef = f"0.0.0.0/0\n  nexthop 192.0.2.1 {MGMT_IF}"
        self.answers = {("r3", f"show interfaces {GI4}"): shown("down"),
                        ("r3", f"show ip cef {MANAGER}"): cef,
                        ("r3", f"show ipv6 cef {MANAGER_V6.lower()}"): cef,
                        ("r4", f"show interfaces {GI4}"): shown(far)}
        self.answers.update(answers or {})
        self._flap = flap or {"state": "read", "flapping": False, "transitions": 0,
                              "words": "0 UPDOWN transitions: not a flap"}
        self._transitions = transitions
        self.reads = []

    def mode(self, now):
        return self._mode

    def halted(self):
        return {}

    def planned(self, device, now):
        return self._planned

    def decisions(self):
        return list(self._rows)

    def device(self, host):
        return {"r3": dict(DEV), "r4": dict(FAR)}.get(host, {})

    def intents(self):
        return self._intents, ""

    def host_networks(self):
        return self._nets

    def manager_toward(self, address):
        return self._manager

    def read(self, host, commands):
        self.reads.append((host, list(commands)))
        got = {c: self.answers[(host, c)] for c in commands if (host, c) in self.answers}
        return got or {"_why": "not answered"}

    def flap(self, device, interface, now, at_least, minutes):
        return self._flap

    def transitions(self, device, interface, since, until):
        if self._transitions is not None:
            return self._transitions
        return {"state": "read", "transitions": [
            {"epoch": since + 12, "at": "", "state": "up"}], "words": "1 transition"}

    def holder(self, network, device):
        return self._holder

    def session(self, network, dev, interface, actor, values):
        return B().Session(network, dev, interface, actor, values, operation=B().OPERATION,
                           detail=f"port bounce of {interface}", label="port bounce",
                           opener=lambda d: self.dev.open(), clock=self.clock)

    def values(self):
        return {}


# ── The program and its bounds ──────────────────────────────────────────────────────────────

class TestTheProgramAndItsBounds:
    def test_one_batch_inside_the_revert_timer_its_hash_over_the_authorised_shutdown(self):
        prog = B().program(GI4, 2)
        assert prog == ["configure terminal revert timer 2", f"interface {GI4}", "shutdown",
                        "no shutdown", "end"]
        assert B().program_hash(prog, "one reason") != B().program_hash(prog, "another")
        assert B().program_hash(prog, "r") != B().program_hash(B().program(GI4, 3), "r")

    def test_the_settle_bound_and_the_window_are_derived_from_the_trial(self):
        import math
        slowest = max(max(m["settle_s"]) for m in B().MEASURED.values())
        assert slowest == 39 and B().SETTLE_BOUND_S == math.ceil(2.5 * slowest) == 98
        assert B().SETTLE_BOUND_S < B().TIMER_MINUTES * 60, "the confirm lands inside the timer"
        assert B().window_seconds() == 2 * 60 + B().WATCH_PAST_S + B().SETTLE_BOUND_S == 398
        assert set(B().MEASURED) == {"cisco_iosxe", "cisco_ios"}

    def test_a_save_is_refused_by_every_send(self):
        with pytest.raises(B().SaveRefused):
            B().assert_no_save(["end", "write memory"])


# ── The decision ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def stores(networks):  # noqa: F811 (the fixture)
    return networks


def decide(src, diagnosis=PICK_DIAGNOSIS):
    from modules.heal import decisions
    got = B().consider(NET, "hi-1", diagnosis, now=T0, sources=src)
    rows = decisions.decisions(NET)
    return got, rows


class TestTheDecision:
    def test_no_action_chosen_records_nothing(self, stores):
        got, rows = decide(Src(), {"hypotheses": []})
        assert got["state"] == "none" and rows == []

    def test_dry_run_records_would_have_bounced_and_sends_nothing(self, stores):
        from modules.heal import act
        dev = FakeIOS(Clock())
        src = Src(dev=dev)
        got, rows = decide(src)
        d = rows[-1]
        assert d["outcome"] == "would_heal" and d["mode"] == "dry_run", d
        assert d["words"].startswith(f"would have bounced r3 {GI4} (program ")
        assert "the mode is dry run. Nothing was sent" in d["words"]
        assert d["action"]["kind"] == "port_bounce" and d["program_hash"]
        assert d["program"] == B().program(GI4, 2)
        assert all(cmd.startswith("show ") for _h, cmds in src.reads for cmd in cmds)
        assert act.run(NET, now=T0, starter=lambda *a: pytest.fail("nothing is taken"))[
            "started"] == []
        assert dev.batches == [] and dev.opened == 0

    def test_auto_with_the_kind_allowed_on_a_lab_network_bounces(self, stores):
        got, rows = decide(Src(m=mode("auto", kinds=["port_bounce"])))
        assert rows[-1]["outcome"] == "heal", rows[-1]["words"]
        got, rows = decide(Src(m=mode("auto", kinds=["admin_down"])))
        assert rows[-1]["outcome"] == "would_heal"
        assert "port_bounce is not allowed AUTO" in rows[-1]["words"]

    def test_a_port_that_came_back_by_itself_is_left_alone(self, stores):
        src = Src(answers={("r3", f"show interfaces {GI4}"): shown("up")})
        d = decide(src)[1][-1]
        assert d["outcome"] == "nothing" and "the port came back by itself" in d["words"]

    def test_a_far_end_held_is_held_until_it_is_checked_again(self, stores):
        src = Src(holder={"operation": "deploy", "actor": "someone@example.invalid"})
        d = decide(src)[1][-1]
        assert d["outcome"] == "held" and d["guard"]["guard"] == "13b"
        assert d["until"] == T0 + 60

    def test_a_far_end_down_is_the_link_cant_fix(self, stores):
        d = decide(Src(far="down"))[1][-1]
        assert d["outcome"] == "cant_fix" and d["guard"]["guard"] == "13b"

    @pytest.mark.parametrize("manager,cmd", [(MANAGER, f"show ip cef {MANAGER}"),
                                             (MANAGER_V6.lower(),
                                              f"show ipv6 cef {MANAGER_V6.lower()}")])
    def test_mercurys_route_out_of_the_interface_is_never(self, stores, manager, cmd):
        src = Src(manager=(manager, ""),
                  answers={("r3", cmd): f"192.0.2.0/24\n  nexthop 192.0.2.41 {GI4}"})
        d = decide(src)[1][-1]
        assert (d["outcome"], d["tier"], d["guard"]["guard"]) == ("cant_fix", 4, "13c"), d
        assert f"r3 reaches Mercury ({manager}) out of {GI4} (`{cmd}` on r3" in d["words"]

    def test_an_egress_it_cannot_read_or_a_route_not_read_is_never(self, stores):
        src = Src(answers={("r3", f"show ip cef {MANAGER}"): "% Invalid input detected"})
        d = decide(src)[1][-1]
        assert d["tier"] == 4 and "names no egress Mercury can read" in d["words"]
        d = decide(Src(manager=("", "no route")))[1][-1]
        assert d["tier"] == 4 and "route to Mercury was not read" in d["words"]

    def test_the_management_interface_by_intent_is_never(self, stores):
        diag = {"hypotheses": [dict(PICK_DIAGNOSIS["hypotheses"][0], at={
            "host": "r3", "interface": "GigabitEthernet1", "far_host": "r4",
            "far_interface": GI4})]}
        src = Src(answers={("r3", "show interfaces GigabitEthernet1"):
                           shown("down").replace(GI4, "GigabitEthernet1")})
        d = decide(src, diag)[1][-1]
        assert d["tier"] == 4 and f"carries {MGMT_IP}, the address Mercury reaches r3" \
            in d["words"]

    def test_the_only_path_is_never(self, stores):
        d = decide(Src(intents_=intents(r4_on_mgmt=False)))[1][-1]
        assert d["tier"] == 4 and f"{GI4} is r3's only path: shutting it leaves r4 " \
            "unreachable" in d["words"]
        d = decide(Src(nets=["198.51.100.0/24"]))[1][-1]
        assert d["tier"] == 4 and "is not known" in d["words"]

    def test_a_second_bounce_within_the_window_is_the_dampening_proposal(self, stores):
        prior = {"id": "hd-1", "outcome": "would_heal", "epoch": T0 - 600, "at": "",
                 "action": {"kind": "port_bounce", "device": "r3", "interface": GI4}}
        got, rows = decide(Src(rows=[prior]))
        d = rows[-1]
        assert d["outcome"] == "cant_fix" and d["guard"]["guard"] == "13d"
        assert "dampening" in d["words"] and d["instead"] == "dampening_proposal"
        # H22: the dampening proposal follows a real bounce only; in dry run none was sent.
        assert got["dampening"]["state"] == "none" and "dry_run mode" in \
            got["dampening"]["words"], got["dampening"]

    def test_a_flap_record_that_cannot_be_read_holds_no_bounce(self, stores):
        d = decide(Src(flap={"state": "unreadable", "words": "the record is unreadable"}))[1][-1]
        assert d["outcome"] == "cant_fix" and d["guard"]["guard"] == "13e"

    def test_no_archive_in_intent_is_never_and_an_unmeasured_platform_cant_fix(
            self, stores, monkeypatch):
        d = decide(Src(intents_=intents(archive=False)))[1][-1]
        assert (d["outcome"], d["tier"]) == ("cant_fix", 4)
        assert "r3 has no configuration archive in its intent" in d["words"]
        # A dialect Mercury reads but the trial did not measure: the table refuses it.
        monkeypatch.setattr(B(), "MEASURED", {"cisco_ios": B().MEASURED["cisco_ios"]})
        d = decide(Src())[1][-1]
        assert (d["outcome"], d["tier"], d["guard"]["guard"]) == ("cant_fix", 3, "13f")
        assert "the revert timer is not measured on cisco_iosxe (r3)" in d["words"]
        other = intents()
        other["r3"]["platform"] = "cisco_nxos"
        d = decide(Src(intents_=other))[1][-1]
        assert d["guard"]["guard"] == "13f" and "an unknown platform" in d["words"]

    def test_an_ospf_reset_needs_its_one_neighbour_stuck(self, stores):
        answers = {("r3", f"show interfaces {GI4}"): shown("up"),
                   ("r3", f"show ip ospf neighbor {GI4} detail"): ospf_detail("EXSTART")}
        d = decide(Src(answers=answers), OSPF_DIAGNOSIS)[1][-1]
        assert d["outcome"] == "would_heal" and d["action"]["kind"] == "ospf_reset", d
        answers[("r3", f"show ip ospf neighbor {GI4} detail")] = ospf_detail("FULL")
        d = decide(Src(answers=answers), OSPF_DIAGNOSIS)[1][-1]
        assert d["outcome"] == "nothing" and "it resolved by itself" in d["words"]

    def test_the_decision_is_in_the_step_log(self, stores):
        from modules.heal import steplog
        decide(Src())
        rows = [r for r in steplog.read(NET)["rows"] if r.get("row") == "decision"]
        assert rows and [s["step"] for s in rows[-1]["steps"]][:5] == [
            "choose", "stops", "rates", "fresh", "guards"]


# ── The act ─────────────────────────────────────────────────────────────────────────────────

class FakeRouter(FakeIOS):
    """FakeIOS with a port down while administratively up (until a bounce brings it up) and an
    OSPF neighbour table (``ospf``: its state before the bounce, ``after``: after it)."""

    def __init__(self, clock, *, down=(GI4,), ospf=None, after="FULL", **kw):
        super().__init__(clock, cef=f"0.0.0.0/0\n  nexthop 192.0.2.1 {MGMT_IF}", **kw)
        self.down, self.ospf, self.after, self.bounced = set(down), ospf, after, False

    def show(self, cmd):
        if cmd == f"show ip ospf neighbor {GI4} detail" and self.ospf:
            return ospf_detail(self.after if self.bounced else self.ospf)
        got = super().show(cmd)
        name = cmd.split(None, 2)[2] if cmd.startswith("show interfaces ") else ""
        if name in self.down and name not in self.shut:
            return shown("down")
        return got

    def batch(self, text):
        try:
            return super().batch(text)
        finally:
            if "no shutdown" in [s.strip() for s in self.sent]:
                self.down.clear()
                self.bounced = True


@pytest.fixture
def act_world(stores, monkeypatch, tmp_path):
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, cmd, **kw: conn.device.show(cmd))
    monkeypatch.setattr("modules.restarts._data", lambda name: str(tmp_path / name))
    return stores


def taken(src, diagnosis=PICK_DIAGNOSIS):
    from modules.heal import decisions
    got = B().consider(NET, "hi-1", diagnosis, now=T0, sources=src)
    assert got["decision"]["outcome"] == "heal", got["decision"]["words"]
    return decisions.take(NET, got["decision"]["id"], by="the test", now=T0)


def auto_src(dev, clock, **kw):
    kw.setdefault("m", mode("auto", kinds=["port_bounce", "ospf_reset"]))
    return Src(dev=dev, clock=clock, **kw)


class TestTheAct:
    def test_bounced_confirmed_after_mercury_is_back_in_and_stable(self, act_world, monkeypatch):
        from modules import restarts
        from modules.heal import decisions, steplog
        clock = Clock()
        dev = FakeRouter(clock)
        calls = []
        real = restarts.record_planned

        def recorded(*a, **k):
            calls.append(len(dev.batches))
            return real(*a, **k)

        monkeypatch.setattr("modules.restarts.record_planned", recorded)
        src = auto_src(dev, clock)
        d = taken(src)
        out = B().apply(NET, d, sources=src)
        assert out["outcome"] == "bounced", out["steps"]
        assert calls == [0], "the window is recorded before the batch"
        assert dev.batches[0] == B().program(GI4, 2), "one batch"
        assert [b for b in dev.batches if b == ["configure confirm"]], "confirmed"
        w = restarts.planned_rows()[-1]
        assert (w["devices"], w["interfaces"], w["via"]) == (["r3"], [GI4], B().VIA)
        assert restarts._epoch(w["until"]) - restarts._epoch(w["from"]) == 398
        steps = [s["step"] for s in out["steps"]]
        assert steps.index("window") < steps.index("send") < steps.index("confirm") \
            < steps.index("verify") < steps.index("stable")
        assert decisions.find(NET, d["id"])["applied"]["outcome"] == "bounced"
        assert decisions.halted(NET) == {} or not decisions.halted(NET).get("id")
        rows = [r["row"] for r in steplog.read(NET)["rows"]]
        assert rows.count("started") == 1 and rows.count("act") == 1
        assert dev.saves == [] and not any(SAVE.match(x) for x in dev.sent)

    def test_a_window_that_cannot_be_recorded_sends_nothing(self, act_world, monkeypatch):
        clock = Clock()
        dev = FakeRouter(clock)
        monkeypatch.setattr("modules.restarts.record_planned",
                            lambda *a, **k: {"ok": False, "error": "the store is unreadable"})
        src = auto_src(dev, clock)
        out = B().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "refused" and dev.batches == []
        assert "planned window for the bounce could not be recorded (the store is " \
            "unreadable)" in out["words"]

    def test_a_hash_that_moved_sends_nothing(self, act_world):
        clock = Clock()
        dev = FakeRouter(clock)
        src = auto_src(dev, clock)
        d = dict(taken(src), program_hash="0" * 16)
        out = B().apply(NET, d, sources=src)
        assert out["outcome"] == "refused" and "hash moved" in out["words"]
        assert dev.opened == 0 and dev.batches == []

    def test_not_in_auto_at_apply_sends_nothing(self, act_world):
        clock = Clock()
        dev = FakeRouter(clock)
        src = auto_src(dev, clock)
        d = taken(src)
        src._mode = mode("dry_run")
        out = B().apply(NET, d, sources=src)
        assert out["outcome"] == "refused" and "only AUTO sends" in out["words"]
        assert dev.opened == 0

    def test_a_port_back_by_itself_on_the_held_session_is_left_alone(self, act_world):
        clock = Clock()
        dev = FakeRouter(clock, down=())
        src = auto_src(dev, clock)
        out = B().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "refused" and "the port came back by itself" in out["words"]
        assert dev.batches == []

    def test_13c_again_on_the_held_session_ipv4_and_ipv6(self, act_world):
        clock = Clock()
        dev = FakeRouter(clock)
        dev.cef = CEF_VIA_GI4
        src = auto_src(dev, clock)
        out = B().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "refused" and f"r3 reaches Mercury ({MANAGER}) out of {GI4}" \
            in out["words"] and dev.batches == []
        dev = FakeRouter(Clock(), manager=MANAGER_V6)
        dev.cef = f"2001:DB8:FFFF::/48\n  nexthop FE80::5054:FF:FE00:4 {GI4}"
        src = auto_src(dev, dev.clock)
        out = B().apply(NET, taken(src), sources=src)
        assert f"`show ipv6 cef {MANAGER_V6.lower()}` on r3" in out["words"]
        assert dev.batches == []

    def test_mercury_not_back_in_the_timer_reverts_it_and_the_network_halts(self, act_world):
        from modules.heal import decisions
        clock = Clock()
        dev = FakeRouter(clock, unreachable=((1, 125),))
        src = auto_src(dev, clock)
        d = taken(src)
        out = B().apply(NET, d, sources=src)
        assert out["outcome"] == "reverted", out["steps"]
        assert not [b for b in dev.batches if b == ["configure confirm"]], "never confirmed"
        assert clock.now >= T0 + 2 * 60 + B().WATCH_PAST_S, "watched past the timer"
        assert decisions.halted(NET)["guard"] == 14

    def test_a_configuration_that_moved_is_never_confirmed(self, act_world):
        """The post-check compares the running configuration with BEFORE, line for line: the
        port up/up and Mercury back in are not enough."""
        clock = Clock()
        dev = FakeRouter(clock)

        def moved():
            if dev.batches and "logging host 192.0.2.99" not in dev.config:
                dev.config += "logging host 192.0.2.99\n"

        dev.on_open = moved
        src = auto_src(dev, clock)
        out = B().apply(NET, taken(src), sources=src)
        assert not [b for b in dev.batches if b == ["configure confirm"]], "never confirmed"
        assert out["outcome"] in ("repaired", "failed"), out["steps"]

    def test_a_batch_cut_after_shutdown_is_reverted_by_the_timer(self, act_world):
        clock = Clock()
        dev = FakeRouter(clock, drop_after="shutdown")
        src = auto_src(dev, clock)
        out = B().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "reverted" and GI4 not in dev.shut

    def test_a_repair_that_cannot_unshut_is_not_restored(self, act_world):
        clock = Clock()
        dev = FakeRouter(clock, refuse={"no shutdown"})
        src = auto_src(dev, clock)
        out = B().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "failed" and out["words"].startswith("NOT RESTORED: r3")
        assert out["records"]["repair"]["restored"] is False

    def test_a_refused_line_once_is_repaired(self, act_world):
        clock = Clock()
        dev = FakeRouter(clock, refuse_once={"no shutdown"})
        src = auto_src(dev, clock)
        out = B().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "repaired" and GI4 not in dev.shut

    @pytest.mark.parametrize("seen,outcome", [
        ([("up", 12), ("down", 200), ("up", 230)], "still_flapping"),
        ([("down", 1), ("up", 12)], "bounced"),
        ([], "unverified")])
    def test_the_stability_window(self, act_world, seen, outcome):
        clock = Clock()
        dev = FakeRouter(clock)
        trans = {"state": "read", "words": "", "transitions": [
            {"epoch": T0 + t, "at": "", "state": s} for s, t in seen]}
        src = auto_src(dev, clock, transitions=trans)
        out = B().apply(NET, taken(src), sources=src)
        assert out["outcome"] == outcome, out["steps"]

    def test_a_stability_window_that_cannot_be_read_is_unverified(self, act_world):
        clock = Clock()
        dev = FakeRouter(clock)
        src = auto_src(dev, clock, transitions={"state": "unreadable", "transitions": [],
                                                "words": "the flap record cannot be read"})
        out = B().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "unverified"
        assert clock.now >= T0 + 10 * 60, "the stability window is waited out"

    @pytest.mark.parametrize("after,outcome", [("FULL", "bounced"), ("EXSTART", "not_formed")])
    def test_an_ospf_reset_verifies_its_adjacency(self, act_world, after, outcome):
        clock = Clock()
        dev = FakeRouter(clock, down=(), ospf="EXSTART", after=after)
        answers = {("r3", f"show interfaces {GI4}"): shown("up"),
                   ("r3", f"show ip ospf neighbor {GI4} detail"): ospf_detail("EXSTART")}
        src = auto_src(dev, clock, answers=answers)
        out = B().apply(NET, taken(src, OSPF_DIAGNOSIS), sources=src)
        assert out["outcome"] == outcome, out["steps"]

    def test_the_device_is_held_throughout(self, act_world):
        import threading
        from modules.nsot import device_ops as D
        clock = Clock()
        dev = FakeRouter(clock)
        refusals = []

        def other():
            try:
                D.acquire(NET, "r3", "deploy", "other@example.invalid")
                D.release(NET, "r3")
                refusals.append("")
            except D.DeviceBusy as exc:
                refusals.append(str(exc))

        def at_open():
            t = threading.Thread(target=other)
            t.start()
            t.join(5)

        dev.on_open = at_open
        src = auto_src(dev, clock)
        assert B().apply(NET, taken(src), sources=src)["outcome"] == "bounced"
        assert refusals and all("port bounced by self-healing" in r for r in refusals), refusals

    def test_a_device_held_by_another_operation_is_refused(self, act_world):
        from modules.nsot import device_ops as D
        clock = Clock()
        dev = FakeRouter(clock)
        src = auto_src(dev, clock)
        d = taken(src)
        import threading
        got = {}

        def hold_it():
            D.acquire(NET, "r3", "deploy", "other@example.invalid")
            got["ready"] = True
            time.sleep(0.5)
            D.release(NET, "r3")

        t = threading.Thread(target=hold_it)
        t.start()
        while not got.get("ready"):
            time.sleep(0.01)
        out = B().apply(NET, d, sources=src)
        t.join()
        assert out["outcome"] == "refused" and dev.batches == []

    def test_the_act_runner_takes_a_bounce_to_the_bounce(self, act_world, monkeypatch):
        from modules.heal import act
        seen = []
        monkeypatch.setattr("modules.heal.bounce.apply",
                            lambda network, decision, **kw: seen.append(decision["id"]) or {})
        monkeypatch.setattr("modules.heal.act.apply_decision",
                            lambda *a, **k: pytest.fail("a bounce is no heal"))
        clock = Clock()
        src = auto_src(FakeRouter(clock), clock)
        d = taken(src)
        act._apply_for(NET, d)
        assert seen == [d["id"]]


# ── The records (H23: History, the change record) ──────────────────────────────────────────

def history(device):
    from modules import history_sources as HS
    return HS.heal({"ref": types.SimpleNamespace(name=NET), "device": device, "limit": 50,
                    "members": None, "since": None, "until": None})["events"]


class TestTheRecords:
    def test_a_bounce_keeps_its_window_far_end_rollback_and_change_record(self, act_world):
        from modules.heal import steplog
        clock = Clock()
        src = auto_src(FakeRouter(clock), clock)
        out = B().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "bounced", out["steps"]
        rec = out["records"]
        assert rec["window"]["far_ends"] == [{"device": "r4", "interface": GI4}]
        assert rec["rollback"].startswith("not needed: confirmed on the device")
        cr = rec["change_record"]
        assert cr["state"] == "made" and cr["risk"] == "medium", cr
        text = cr["markdown"]
        heads = [x[3:] for x in text.splitlines() if x.startswith("## ")]
        from modules.heal import change_record
        assert heads == list(change_record.SECTIONS)
        assert f"# Change record: r3 {GI4}, a port bounced" in text
        assert "\n".join(B().program(GI4, 2)) in text, "the program, as sent"
        assert "its far end: r4 GigabitEthernet4" in text and "revert timer" in text
        (act_row,) = [r for r in steplog.read(NET)["rows"] if r["row"] == "act"]
        assert act_row["action"]["interface"] == GI4 and act_row["action"]["far_device"] == "r4"
        assert act_row["records"]["change_record"]["state"] == "made"

    def test_history_names_the_port_and_draws_it_on_the_far_end_too(self, act_world):
        clock = Clock()
        trans = {"state": "read", "words": "", "transitions": [
            {"epoch": T0 + t, "at": "", "state": s} for s, t in
            [("up", 12), ("down", 200), ("up", 230)]]}
        src = auto_src(FakeRouter(clock), clock, transitions=trans)
        out = B().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "still_flapping", out["steps"]
        (e,) = history("r3")
        assert e["what"] == f"Self-healing (AUTO): r3 {GI4} bounced, still flapping", e["what"]
        assert e["devices"] == ["r3", "r4"]
        rec = dict(e["record"])
        assert rec["Action"] == f"r3 {GI4}" and rec["Far end"] == f"r4 {GI4}"
        assert rec["Sent to the device"] == "yes: the program above, once"
        assert rec["Planned window"].endswith(f"naming {GI4} (by {B().VIA})")
        assert "stable: failed" in rec["Verify"] and "confirm: ok" in rec["Verify"]
        assert rec["Change record"].startswith("made:")
        assert "Dampening proposal" in rec
        assert [x["what"] for x in history("r4")] == [e["what"]], "the far end draws it"
        assert history("r9") == []

    @pytest.mark.parametrize("kw,outcome,said", [
        ({"refuse_once": {"no shutdown"}}, "repaired", "repaired: "),
        ({"refuse": {"no shutdown"}}, "failed", "NOT RESTORED: ")])
    def test_a_repair_is_the_rollback_history_draws(self, act_world, kw, outcome, said):
        clock = Clock()
        src = auto_src(FakeRouter(clock, **kw), clock)
        out = B().apply(NET, taken(src), sources=src)
        assert out["outcome"] == outcome, out["steps"]
        assert out["records"]["rollback"].startswith(said), out["records"]["rollback"]
        (e,) = history("r3")
        assert dict(e["record"])["Rollback"] == out["records"]["rollback"]
        mark = "repaired" if outcome == "repaired" else "bounced, NOT RESTORED"
        assert e["what"].endswith(f"r3 {GI4} {mark}"), e["what"]

    def test_a_dry_run_bounce_is_would_bounce_never_would_heal(self, stores):
        src = Src()
        got, _rows = decide(src)
        assert got["decision"]["outcome"] == "would_heal"
        (e,) = history("r3")
        assert e["what"] == f"Self-healing (dry run): r3 {GI4} would bounce", e["what"]
        assert dict(e["record"])["Far end"] == f"r4 {GI4}", "the decision's far end"
        assert "Sent to the device" not in dict(e["record"]), "nothing acted yet"


# ── The flap record leaves planned windows out (C2694) ─────────────────────────────────────

class TestTheFlapRecordAndPlannedWindows:
    def trans(self, *epochs):
        return {"state": "read", "words": "", "transitions": [
            {"epoch": e, "at": "", "state": "down" if i % 2 == 0 else "up"}
            for i, e in enumerate(epochs)]}

    def window(self, start, end, interfaces=None):
        w = {"devices": ["r3"], "list": NET, "from": B()._iso(start), "until": B()._iso(end)}
        if interfaces is not None:
            w["interfaces"] = interfaces
        return w

    def flapping(self, monkeypatch, got, planned):
        from modules.heal import flaps
        monkeypatch.setattr(flaps, "transitions", lambda *a, **k: got)
        return flaps.flapping(NET, "r3", GI4, T0 + 600, at_least=3, minutes=10, planned=planned)

    def test_the_bounces_own_transitions_are_no_flap(self, monkeypatch):
        got = self.trans(T0 + 10, T0 + 20, T0 + 30)
        assert self.flapping(monkeypatch, got, [])["flapping"] is True
        out = self.flapping(monkeypatch, got, [self.window(T0, T0 + 398, [GI4])])
        assert (out["flapping"], out["transitions"], out["planned"]) == (False, 0, 3)
        assert "3 more inside a planned window left out" in out["words"]

    def test_a_window_naming_another_port_leaves_these_in_and_a_whole_device_one_out(
            self, monkeypatch):
        got = self.trans(T0 + 10, T0 + 20, T0 + 30)
        assert self.flapping(monkeypatch, got, [self.window(T0, T0 + 398, ["Gi9"])])[
            "flapping"] is True
        assert self.flapping(monkeypatch, got, [self.window(T0, T0 + 398)])["flapping"] is False

    def test_transitions_after_the_window_still_count(self, monkeypatch):
        got = self.trans(T0 + 10, T0 + 450, T0 + 470, T0 + 490)
        out = self.flapping(monkeypatch, got, [self.window(T0, T0 + 398, [GI4])])
        assert (out["flapping"], out["transitions"], out["planned"]) == (True, 3, 1)

    def test_planned_windows_that_cannot_be_read_are_never_read_as_none(self, monkeypatch):
        from modules.heal import flaps

        def boom():
            raise RuntimeError("the planned-restart record could not be read")

        monkeypatch.setattr(flaps, "transitions", lambda *a, **k: self.trans(T0 + 10))
        monkeypatch.setattr("modules.restarts.planned_rows", boom)
        out = flaps.flapping(NET, "r3", GI4, T0 + 600, at_least=3, minutes=10)
        assert out["state"] == "unreadable" and "planned windows cannot be read" in out["words"]


# ── Needs attention ─────────────────────────────────────────────────────────────────────────

class TestNeedsAttention:
    def row(self, outcome="heal", applied=None, guard=None, epoch=T0, did="hd-1"):
        d = {"id": did, "device": "r3", "outcome": outcome, "epoch": epoch,
             "action": {"kind": "port_bounce", "device": "r3", "interface": GI4,
                        "far_device": "r4", "far_interface": GI4},
             "guard": guard or {}}
        if applied:
            d["applied"] = {"outcome": applied, "words": f"{applied} for the test"}
        return d

    def rows(self, decisions, now=T0 + 60):
        from modules import attention
        return attention._heal_bounce_rows(NET, decisions, now)

    @pytest.mark.parametrize("applied", ["reverted", "repaired", "failed", "still_flapping",
                                         "not_formed", "unverified", "refused"])
    def test_every_end_but_bounced_is_one_row(self, applied):
        got = self.rows([self.row(applied=applied)])
        assert len(got) == 1 and got[0]["kind"] == "bounce"
        assert got[0]["action"]["href"] == "/v2/device/r3?tab=history"

    def test_bounced_is_no_row_and_a_later_bounce_replaces_one(self):
        assert self.rows([self.row(applied="bounced")]) == []
        assert self.rows([self.row(applied="failed"),
                          self.row(applied="bounced", epoch=T0 + 30, did="hd-2")]) == []

    def test_a_held_bounce_is_a_row_saying_it_is_not_tried_again(self):
        got = self.rows([self.row("held", guard={"guard": "13b", "name": "the far end up",
                                                 "words": "r4 is held"})])
        assert len(got) == 1 and "not tried again by itself" in got[0]["cause"]

    def test_a_dry_run_record_is_no_bounce_row_and_an_old_one_has_gone(self):
        assert self.rows([self.row("would_heal")]) == []
        assert self.rows([self.row(applied="failed")], now=T0 + 8 * 86400) == []


# ── The OSPF reset's rule (`diagnose`) ──────────────────────────────────────────────────────

class TestTheOspfRule:
    @pytest.fixture
    def diag(self, networks, monkeypatch):  # noqa: F811 (the fixture)
        from tests.test_heal_diagnose import _FLEET_DEVICES
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path=None: [dict(d) for d in _FLEET_DEVICES])
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, c, read_timeout=None: conn.answer(c))

    def stuck(self, state):
        from tests.test_heal_diagnose import R3_OSPF, diagnose, with_answer
        cmd = f"show ip ospf neighbor {GI4} detail"
        full = f"via interface {GI4}\n    Neighbor priority is 1, State is FULL"
        assert R3_OSPF.count(full) == 1, "the capture's Gi4 neighbour, FULL"
        stuck = R3_OSPF.replace(full, full.replace("FULL", state))
        return diagnose(with_answer("r3", cmd, stuck))[0]

    def test_one_neighbour_stuck_with_the_link_up_is_the_ospf_reset(self, diag):
        from modules.heal import diagnose as D
        got = self.stuck("EXSTART")
        act = D.action_for(got)
        assert (act["state"], act["kind"]) == ("chosen", "ospf_reset"), (act, [
            (h["rule"], h["strength"]) for h in got["hypotheses"]])
        assert act["at"]["host"] == "r3" and act["at"]["interface"] == GI4

    @pytest.mark.parametrize("state", ["INIT", "DOWN"])
    def test_one_way_or_nothing_heard_is_no_reset(self, diag, state):
        from modules.heal import diagnose as D
        got = self.stuck(state)
        assert "ospf_not_full_one_neighbour" not in [h["rule"] for h in got["hypotheses"]]
        assert D.action_for(got).get("kind") != "ospf_reset"
