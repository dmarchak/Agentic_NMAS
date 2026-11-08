"""The BGP session clear (`modules/heal/session_clear.py`, `privileged.SESSION_CLEARS`; board H's
amendment, item 2, part H21; docs/HEAL_TO_INTENT.md 19.4 and N16). No network and no device:
the neighbour's reads are r4's real captures of 2026-11-07 (tests/fixtures/tier2/r4__*, taken
through the reads engine, masked), with the minimal edits each case names (its state, its
counters, its last reset); the device is faked at the act's session seam.

- **The command policy** (`clear_plan`): never ``*`` or anything but one address; the peer is
  intent's; a hard clear only of a session not Established in two reads in a row, a soft clear
  only of an Established one; no clear for Idle (Admin), a shut neighbour or a bad peer AS; the
  clear measured on the platform or refused by name (the shipped record: the soft clear
  measured on IOS-XE, the hard clear not), its verify bound 2.5 times the measured settle; the
  IPv6 forms.
- **The session read** (`bgp_session`): the real captures, IPv4 and IPv6; an answer of another
  shape decides nothing.
- **The send** (`send_clear`): the session read again and kept; a hard clear never sent to a
  session Established at the send; the measured prompt alone answered; a device refusal; a
  session not back within the bound; a soft clear that reset its session.
- **The decision** (`consider`): no clear chosen records nothing; dry run on a lab network
  records "would have cleared" and sends nothing; AUTO with the kind allowed clears; off a lab
  network it is a proposal, or can't fix when the policy does not propose it; 13a (it came back
  by itself), 13c (Mercury's route learned from that neighbour, IPv4 and IPv6), 13d (once per
  incident), the plan's refusal (not measured).
- **The act** (`apply`, `apply_approved`): the planned window recorded BEFORE the clear and
  naming the neighbour's interface, or nothing sent; the stops and the hash again; the session
  read again at the send; cleared, not back, reset (a halt); the records (the Tier 2 record
  History shows, the decisions store, the step log); the device held throughout; the person's
  act as the person.
- **The wiring**: the taker, the approval and the notice's consideration each reach it.
"""

import json
import os

import pytest

from tests.test_nmas_revert_probe import T0, Clock
from tests.test_nmas_revert_probe import no_hold_survives_a_test  # noqa: F401 (autouse)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NET = "Default"
PEER = "198.51.100.3"
PEER6 = "2001:DB8:51:1::2"
MANAGER = "192.0.2.250"
MANAGER6 = "2001:db8:ffff::250"
DEV = {"hostname": "r4", "ip": "192.0.2.14", "device_type": "cisco_xe"}


def P():
    from modules.nsot import privileged
    return privileged


def S():
    from modules.heal import session_clear
    return session_clear


def fixture(name):
    with open(os.path.join(ROOT, "tests", "fixtures", "tier2", name), encoding="utf-8") as fh:
        return fh.read()


ESTABLISHED = fixture("r4__show_ip_bgp_neighbors_established_before_soft.txt")
REFRESHED = fixture("r4__show_ip_bgp_neighbors_established_after_soft.txt")
ESTABLISHED6 = fixture("r4__show_bgp_ipv6_unicast_neighbors_established.txt")
ROUTE_BY_OSPF = fixture("r4__show_ip_route_manager_by_ospf.txt")
ROUTE_BY_BGP = fixture("r4__show_ip_route_by_bgp.txt")


def down(text=ESTABLISHED, state="Active", reset="due to BGP Notification received, hold time "
                                                   "expired", dropped=1):
    """The real capture with the session not Established: its state, its drop count and its
    last reset edited (the minimal edits)."""
    return (text.replace("BGP state = Established, up for 2w2d", f"BGP state = {state}")
            .replace("Connections established 1; dropped 0",
                     f"Connections established 1; dropped {dropped}")
            .replace("Last reset never", f"Last reset 00:02:10, {reset}"))


def back(text=ESTABLISHED, dropped=1):
    """The capture as it reads once a reset session formed again."""
    return (text.replace("up for 2w2d", "up for 00:00:07")
            .replace("Connections established 1; dropped 0",
                     f"Connections established 2; dropped {dropped}"))


def record(rows):
    return {"by_dialect": {"cisco_iosxe": rows}, "unmeasured": {}}


MEASURED = record({
    "clear-bgp-peer": {"prompt": None, "answer": "", "settle_s": 20, "device": "the test",
                       "at": "2026-11-07T00:00:00Z"},
    "clear-bgp-peer-ipv6": {"prompt": None, "answer": "", "settle_s": 20, "device": "the test",
                            "at": "2026-11-07T00:00:00Z"},
    "clear-bgp-soft": {"prompt": None, "answer": "", "settle_s": 2.4, "device": "the test",
                       "at": "2026-11-07T00:00:00Z"}})


@pytest.fixture
def measured(tmp_path, monkeypatch):
    """A record measuring the hard clear too (the shipped one does not yet), named as a test's."""
    path = tmp_path / "measured.json"
    path.write_text(json.dumps(MEASURED))
    monkeypatch.setattr(P(), "RESET_MEASURED_FILE", str(path))
    return path


def session(text):
    return P().bgp_session(text)


def two_down():
    return [session(down()), session(down())]


def intent_peers(*extra):
    return [PEER, PEER6.lower(), *extra]


# ── The command policy ──────────────────────────────────────────────────────────────────────

class TestThePlan:
    def plan(self, key="clear-bgp-peer", peer=PEER, sessions=None, peers=None, **kw):
        return P().clear_plan(key, peer, dialect=kw.pop("dialect", "cisco_iosxe"), device="r4",
                              sessions=two_down() if sessions is None else sessions,
                              intent_peers=intent_peers() if peers is None else peers)

    @pytest.mark.parametrize("peer", ["*", "all", "198.51.100.*"])
    def test_every_neighbour_at_once_is_never(self, measured, peer):
        p = self.plan(peer=peer)
        assert not p["ok"] and "Mercury never sends `clear ip bgp *`" in p["refused"], p
        assert p["refused"].endswith("Nothing was sent")

    @pytest.mark.parametrize("peer", ["", "r5", "198.51.100.3 soft", "198.51.100.3;reload"])
    def test_anything_but_one_address_is_refused(self, measured, peer):
        p = self.plan(peer=peer)
        assert not p["ok"] and "is not one neighbour address" in p["refused"], p

    def test_the_peer_is_intents_never_typed(self, measured):
        p = self.plan(peer="192.0.2.99")
        assert not p["ok"] and "is not a BGP neighbour of r4 in its committed intent" \
            in p["refused"]
        p = P().clear_plan("clear-bgp-peer", PEER, dialect="cisco_iosxe", device="r4",
                           sessions=two_down(), intent_peers=None)
        assert not p["ok"] and "committed intent could not be read" in p["refused"]

    def test_a_hard_clear_needs_two_reads_not_established(self, measured):
        assert self.plan()["ok"]
        one = self.plan(sessions=[session(down())])
        assert not one["ok"] and "read twice in a row" in one["refused"], one
        for pair in ([session(ESTABLISHED), session(down())],
                     [session(down()), session(ESTABLISHED)]):
            p = self.plan(sessions=pair)
            assert not p["ok"] and "Established (Established, up for 2w2d) in 1 of the last " \
                "two reads" in p["refused"], p
            assert "an Established one gets a soft clear (N16)" in p["refused"]

    def test_a_soft_clear_needs_an_established_session(self, measured):
        assert self.plan("clear-bgp-soft", sessions=[session(ESTABLISHED)])["ok"]
        p = self.plan("clear-bgp-soft", sessions=[session(down())])
        assert not p["ok"] and "is Active, not Established" in p["refused"]

    @pytest.mark.parametrize("text, words", [
        (down(state="Idle (Admin)"), "shut by configuration, so no clear would bring it up"),
        (down(state="Idle") + "\n  Administratively shut down\n", "shut by configuration"),
        (down(state="Idle", reset="due to BGP Notification sent, peer in wrong AS"),
         "names a configuration mismatch"),
        (down(state="Idle", reset="due to BGP Notification received, bad peer AS"),
         "names a configuration mismatch")],
        ids=["idle-admin", "shut-down", "peer-in-wrong-as", "bad-peer-as"])
    def test_no_clear_at_all_for_a_cause_a_clear_cannot_fix(self, measured, text, words):
        p = self.plan(sessions=[session(text), session(text)])
        assert not p["ok"] and words in p["refused"] and "N16" in p["refused"], p

    def test_a_session_not_read_decides_nothing(self, measured):
        p = self.plan(sessions=[session(down()), session("% BGP not active")])
        assert not p["ok"] and "was not read as one neighbour's session" in p["refused"]

    def test_the_shipped_record_measures_every_clear_on_iosxe_and_none_on_ios(self):
        # r4, 2026-11-07: the IPv4 soft clear at 19:44:58, the hard clear and both IPv6 clears
        # from 22:26 UTC, each run by scripts/nmas-tier2-probe, the hard ones in a window first.
        rec = P().reset_measured()
        assert rec["state"] == "ok"
        xe = rec["by_dialect"]["cisco_iosxe"]
        got = {k: (xe[k]["prompt"], xe[k]["settle_s"], xe[k]["reset"]) for k in xe}
        assert got == {"clear-bgp-soft": (None, 2.4, False), "clear-bgp-peer": (None, 3.5, True),
                       "clear-bgp-soft-ipv6": (None, 4.7, False),
                       "clear-bgp-peer-ipv6": (None, 5.0, True),
                       # C2374, 2026-11-08: the OSPF process reset, its prompt answered.
                       "clear-ospf-process": ("Reset OSPF process 1? [no]:", 6.0, True)}, got
        assert xe["clear-bgp-soft"]["at"] == "2026-11-07T19:44:58Z"
        assert self.plan("clear-bgp-soft", sessions=[session(ESTABLISHED)])["bound_s"] == 6
        assert self.plan()["bound_s"] == 9                  # 2.5 x 3.5 s, rounded up
        for key in ("clear-bgp-peer", "clear-bgp-peer-ipv6", "clear-bgp-soft",
                    "clear-bgp-soft-ipv6"):
            assert key not in rec["unmeasured"]["cisco_iosxe"], key
            assert rec["unmeasured"]["cisco_ios"][key], key
        ios = self.plan("clear-bgp-soft", sessions=[session(ESTABLISHED)], dialect="cisco_ios")
        assert not ios["ok"] and "is not measured on cisco_ios" in ios["refused"]
        hard = self.plan(dialect="cisco_ios")
        assert not hard["ok"] and "is not measured on cisco_ios" in hard["refused"]
        assert "bgp-hard" in hard["refused"] and "clear-bgp-peer" in hard["refused"]
        assert hard["command"] == f"clear ip bgp {PEER}", "the refusal still names the command"

    def test_the_bound_is_two_and_a_half_times_the_measured_settle(self, measured):
        assert self.plan()["bound_s"] == 50 and self.plan()["settle_s"] == 20

    def test_absent_and_unreadable_records_refuse_differently(self, tmp_path, monkeypatch):
        monkeypatch.setattr(P(), "RESET_MEASURED_FILE", str(tmp_path / "none.json"))
        absent = self.plan()
        (tmp_path / "bad.json").write_text("{not json")
        monkeypatch.setattr(P(), "RESET_MEASURED_FILE", str(tmp_path / "bad.json"))
        bad = self.plan()
        assert "is absent" in absent["refused"] and "is unreadable" in bad["refused"]

    def test_the_ipv6_forms(self, measured):
        s6 = session(down(ESTABLISHED6))
        p = self.plan(peer=PEER6, sessions=[s6, s6])
        assert p["ok"] and p["family"] == "ipv6", p
        assert p["command"] == f"clear bgp ipv6 unicast {PEER6}"
        assert p["read"] == f"show bgp ipv6 unicast neighbors {PEER6}"
        soft = self.plan("clear-bgp-soft", peer=PEER6, sessions=[session(ESTABLISHED6)])
        assert soft["command"] == f"clear bgp ipv6 unicast {PEER6} soft"
        assert P().clear_plan("clear-bgp-peer", PEER, dialect="cisco_iosxe")["command"] == \
            f"clear ip bgp {PEER}"

    def test_the_reads_are_reads_and_the_clears_are_not(self):
        from modules.readonly_commands import refusal
        for spec in P().SESSION_CLEARS.values():
            for fam, peer in (("ipv4", PEER), ("ipv6", PEER6)):
                assert refusal(spec["read"][fam].format(peer=peer)) == ""
                assert refusal(spec["command"][fam].format(peer=peer)), "a clear is no read"
        assert not set(P().SESSION_CLEARS) & set(P().COMMANDS), "never on the Actions menu"


# ── The session read ────────────────────────────────────────────────────────────────────────

class TestTheSessionRead:
    def test_the_real_captures(self):
        s = session(ESTABLISHED)
        assert (s["read"], s["peer"], s["remote_as"], s["state"], s["established"]) == (
            True, PEER, "65002", "Established", True)
        assert (s["up_for"], s["connections"], s["dropped"], s["received"],
                s["refresh_sent"], s["interface"], s["last_reset"], s["admin"],
                s["bad_peer_as"]) == ("2w2d", 1, 0, 3, 0, "GigabitEthernet2", "never", False,
                                      False)
        assert session(REFRESHED)["refresh_sent"] == 1, "the soft clear's refresh, measured"
        s6 = session(ESTABLISHED6)
        assert (s6["peer"], s6["established"], s6["received"], s6["interface"]) == (
            PEER6, True, 3, "GigabitEthernet2")

    def test_an_answer_of_another_shape_decides_nothing(self):
        for text in ("% BGP not active", "", "r4#"):
            assert session(text)["read"] is False

    def test_a_session_down(self):
        s = session(down())
        assert (s["state"], s["established"], s["dropped"], s["up_for"]) == (
            "Active", False, 1, "")


# ── The send ────────────────────────────────────────────────────────────────────────────────

class Device:
    """One router's BGP neighbour at the send's seam: each read of the neighbour answers the
    next text of *reads* (the last repeating); each send is kept and answered from *sends*."""

    def __init__(self, reads, sends=None):
        self.reads, self.sends, self.sent, self.n = list(reads), dict(sends or {}), [], 0

    def read(self, cmd):
        self.n += 1
        return self.reads[min(self.n, len(self.reads)) - 1]

    def send(self, text):
        self.sent.append(text)
        return self.sends.get(text, "r4#")


def planned(key="clear-bgp-peer", sessions=None, **kw):
    return P().clear_plan(key, PEER, dialect="cisco_iosxe", device="r4",
                          sessions=two_down() if sessions is None else sessions,
                          intent_peers=intent_peers(), **kw)


class TestTheSend:
    def send(self, plan, dev, clock=None):
        clock = clock or Clock()
        return P().send_clear(plan, read=dev.read, send=dev.send, clock=clock.time,
                              sleep=clock.sleep)

    def test_a_hard_clear_verified_back_established_its_before_kept(self, measured):
        dev = Device([down(), down(state="Connect"), back()])
        got = self.send(planned(), dev)
        assert got["state"] == "done" and dev.sent == [f"clear ip bgp {PEER}"], got
        assert got["before"] == down(), "the session before is kept (T2-4)"
        assert got["session_before"]["last_reset"].startswith("00:02:10, due to BGP")
        assert "Established, up for 00:00:07" in got["verify"]["words"]

    def test_a_hard_clear_is_never_sent_to_a_session_established_at_the_send(self, measured):
        dev = Device([ESTABLISHED])
        got = self.send(planned(), dev)
        assert got["state"] == "refused" and dev.sent == [], got
        assert "a hard clear is never sent to an Established session" in got["why"]

    def test_only_the_measured_prompt_is_answered(self, measured, tmp_path, monkeypatch):
        rows = json.loads(json.dumps(MEASURED))
        rows["by_dialect"]["cisco_iosxe"]["clear-bgp-peer"].update(prompt="Reset? [confirm]",
                                                                   answer="\n")
        (tmp_path / "p.json").write_text(json.dumps(rows))
        monkeypatch.setattr(P(), "RESET_MEASURED_FILE", str(tmp_path / "p.json"))
        dev = Device([down(), back()], {f"clear ip bgp {PEER}": "Reset? [confirm]"})
        assert self.send(planned(), dev)["state"] == "done" and dev.sent[-1] == "\n"
        other = Device([down()], {f"clear ip bgp {PEER}": "Proceed? [yes/no]:"})
        got = self.send(planned(), other)
        assert got["state"] == "refused" and other.sent == [f"clear ip bgp {PEER}"], got
        assert "not the measured prompt" in got["why"]

    def test_a_question_the_measurement_does_not_record_is_never_answered(self, measured):
        dev = Device([down()], {f"clear ip bgp {PEER}": "Are you sure? [y/n]"})
        got = self.send(planned(), dev)
        assert got["state"] == "refused" and "\n" not in dev.sent

    def test_the_device_refusing_it_is_rejected(self, measured):
        dev = Device([down()], {f"clear ip bgp {PEER}": "% Invalid input detected\nr4#"})
        got = self.send(planned(), dev)
        assert got["state"] == "rejected" and got["why"].startswith("% Invalid input")

    def test_a_session_not_back_within_the_bound_is_said(self, measured):
        clock = Clock()
        dev = Device([down()])
        got = self.send(planned(), dev, clock)
        assert got["state"] == "not_back" and got["waited_s"] >= 50, got
        assert clock.now - T0 < 60, "it waits the bound, not more"

    def test_a_soft_clear_resets_nothing_and_a_reset_is_said(self, measured):
        ok = self.send(planned("clear-bgp-soft", [session(ESTABLISHED)]),
                       Device([ESTABLISHED, REFRESHED]))
        assert ok["state"] == "done", ok
        assert "route refreshes sent 0 then 1" in ok["verify"]["words"]
        assert "connections dropped 0 then 0" in ok["verify"]["words"]
        reset = self.send(planned("clear-bgp-soft", [session(ESTABLISHED)]),
                          Device([ESTABLISHED, back(REFRESHED)]))
        assert reset["state"] == "reset" and reset["verify"]["reset"], reset

    def test_a_soft_clear_of_a_session_down_at_the_send_sends_nothing(self, measured):
        dev = Device([down()])
        got = self.send(planned("clear-bgp-soft", [session(ESTABLISHED)]), dev)
        assert got["state"] == "refused" and dev.sent == []


# ── The decision ────────────────────────────────────────────────────────────────────────────

def mode(m="dry_run", kinds=(), propose=(), stage="lab"):
    values = {"heal_bounce_per_port_hour": 1, "heal_repeat_halts_hours": 24,
              "heal_max_per_device_hour": 3, "heal_max_per_network_hour": 10}
    return {"network": NET, "mode": m, "set": m, "state": "ok", "words": f"{m} for the test",
            "fingerprint": "fp-1", "kinds_auto": list(kinds), "kinds_propose": list(propose),
            "confirmed": {"by": "op@example.invalid", "reason": "the clear under test",
                          "fingerprint": "fp-1"},
            "guards": {k: {"value": v} for k, v in values.items()},
            "stage": {"stage": stage}, "stopped": {"stopped": False}}


def hv():
    return {"platform": "cisco_iosxe", "routing": {"bgp": {"neighbors": [
        f"neighbor {PEER} remote-as 65002", f"neighbor {PEER6} remote-as 65002"]}}}


def diagnosis(peer=PEER, rule="bgp_not_established"):
    return {"hypotheses": [{
        "rule": rule, "case": "", "strength": "strong", "incomplete": [],
        "claim": f"r4's BGP session to {peer} is Active, with no configuration cause",
        "id": "diag:1", "at": {"host": "r4", "peer": peer}}]}


class Src:
    """The clear's sources, faked: the policy, the stores and each read as the test sets it;
    the act's session on a `Device` whose reads answer by command."""

    def __init__(self, *, m=None, answers=None, rows=(), planned=None, manager=(MANAGER, ""),
                 dev=None, clock=None, window=None, intents_=None):
        self.clock_ = clock or Clock()
        self.clock, self.sleep = self.clock_.time, self.clock_.sleep
        self._mode, self._rows, self._planned = m or mode(), list(rows), planned
        self._manager, self.dev, self._window = manager, dev, window
        self._intents = {"r4": hv()} if intents_ is None else intents_
        self.answers = {f"show ip bgp neighbors {PEER}": down(),
                        f"show ip route {MANAGER}": ROUTE_BY_OSPF,
                        f"show bgp ipv6 unicast neighbors {PEER6}": down(ESTABLISHED6),
                        f"show ipv6 route {MANAGER6}": ROUTE_BY_OSPF}
        self.answers.update(answers or {})
        self.reads, self.windows, self.held_during = [], [], []

    def mode(self, now):
        return self._mode

    def halted(self):
        return {}

    def planned(self, device, now):
        return self._planned

    def decisions(self):
        return list(self._rows)

    def device(self, host):
        return dict(DEV) if host == "r4" else {}

    def intents(self):
        return self._intents, ""

    def manager_toward(self, address):
        return self._manager

    def read(self, host, commands):
        self.reads.append((host, list(commands)))
        got = {c: self.answers[c] for c in commands if c in self.answers}
        return got or {"_why": "not answered"}

    def session(self, dev, work):
        from modules.nsot import device_ops
        self.held_during.append(device_ops.holder(NET, dev["hostname"]))
        return work(self.dev)

    def values(self):
        return {}

    def window(self, network, device, interface, now, seconds, *, by, why, far_ends=()):
        self.windows.append({"device": device, "interface": interface, "seconds": seconds,
                             "sent_before": list(self.dev.sent) if self.dev else []})
        self.far_ends = getattr(self, "far_ends", []) + [list(far_ends)]
        if self._window is not None:
            return self._window
        return {"ok": True, "record": {"from": "a", "until": "b", "via": S().VIA,
                                       "interfaces": [interface]}}


class Conn:
    """The act's session: `run_device_command` answers by command (the neighbour from *reads*,
    one after another), `send_command_timing` keeps each send."""

    def __init__(self, reads, sends=None, route=ROUTE_BY_OSPF):
        self.dev = Device(reads, sends)
        self.route = route

    @property
    def sent(self):
        return self.dev.sent

    def answer(self, cmd):
        if cmd.startswith("show ip route") or cmd.startswith("show ipv6 route"):
            return self.route
        return self.dev.read(cmd)

    def send_command_timing(self, text, **kw):
        return self.dev.send(text)


@pytest.fixture
def stores(networks, monkeypatch):  # noqa: F811 (the fixture)
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, cmd, **kw: conn.answer(cmd))
    return networks


def consider(src, diag=None):
    from modules.heal import decisions
    got = S().consider(NET, "hi-1", diag or diagnosis(), now=T0, sources=src)
    return got, decisions.decisions(NET)


class TestTheDecision:
    def test_no_clear_chosen_records_nothing(self, stores, measured):
        bounce = {"hypotheses": [dict(diagnosis()["hypotheses"][0], rule="down_admin_up",
                                      case="far_end_up")]}
        got, rows = consider(Src(), bounce)
        assert got["state"] == "none" and rows == []

    def test_dry_run_on_a_lab_network_records_would_have_cleared_and_sends_nothing(
            self, stores, measured):
        src = Src()
        got, rows = consider(src)
        d = rows[-1]
        assert d["outcome"] == "would_heal" and d["tier"] == 1, d
        assert d["words"].startswith(f"would have cleared r4's BGP neighbour {PEER} "
                                     f"(clear ip bgp {PEER}, command ")
        assert "the mode is dry run. Nothing was sent" in d["words"]
        assert d["program"] == [f"clear ip bgp {PEER}"] and d["program_hash"]
        assert d["action"] == {"kind": "session_clear", "device": "r4", "interface": "",
                               "peer": PEER, "variant": "hard", "rule": "bgp_not_established",
                               "hypothesis": "diag:1"}
        assert d["clear"]["interface"] == "GigabitEthernet2" and d["clear"]["bound_s"] == 50
        assert all(c.startswith("show ") for _h, cmds in src.reads for c in cmds)

    def test_auto_with_the_kind_allowed_on_a_lab_network_clears(self, stores, measured):
        d = consider(Src(m=mode("auto", kinds=["session_clear"])))[1][-1]
        assert d["outcome"] == "heal" and d["words"].startswith("clear now:"), d["words"]
        d = consider(Src(m=mode("auto", kinds=["port_bounce"])))[1][-1]
        assert d["outcome"] == "would_heal" and "session_clear is not allowed AUTO" in d["words"]

    def test_off_a_lab_network_it_is_a_proposal_or_cant_fix(self, stores, measured):
        d = consider(Src(m=mode("auto", kinds=["session_clear"], propose=["session_clear"],
                                stage="production")))[1][-1]
        assert (d["outcome"], d["tier"]) == ("propose", 2), d
        assert "Tier 2 on a network not marked lab, N16" in d["words"]
        d = consider(Src(m=mode("dry_run", stage="production")))[1][-1]
        assert d["outcome"] == "cant_fix" and "the policy does not propose" in d["words"]

    def test_a_session_that_came_back_by_itself_is_left_alone(self, stores, measured):
        d = consider(Src(answers={f"show ip bgp neighbors {PEER}": ESTABLISHED}))[1][-1]
        assert d["outcome"] == "nothing" and "it resolved by itself" in d["words"], d

    @pytest.mark.parametrize("manager, cmd", [(MANAGER, f"show ip route {MANAGER}"),
                                              (MANAGER6, f"show ipv6 route {MANAGER6}")])
    def test_mercurys_route_learned_from_that_neighbour_is_never(self, stores, measured,
                                                                   manager, cmd):
        text = ROUTE_BY_BGP.replace("10.255.1.15/32", "192.0.2.0/24")
        d = consider(Src(manager=(manager, ""), answers={cmd: text}))[1][-1]
        assert d["outcome"] == "cant_fix" and d["tier"] == 4 and d["guard"]["guard"] == "13c"
        assert f"by a route learned by BGP from {PEER} (`{cmd}` on r4)" in d["words"], d

    def test_a_bgp_route_from_another_neighbour_passes_and_one_unnamed_does_not(
            self, stores, measured):
        other = ROUTE_BY_BGP.replace(PEER, "192.0.2.77")
        assert consider(Src(answers={f"show ip route {MANAGER}": other}))[1][-1]["outcome"] \
            == "would_heal"
        unnamed = 'Routing entry for 192.0.2.0/24\n  Known via "bgp 65001", distance 20\n'
        d = consider(Src(answers={f"show ip route {MANAGER}": unnamed}))[1][-1]
        assert d["guard"]["guard"] == "13c" and "whose source the answer does not name" \
            in d["words"]

    def test_a_route_not_read_or_no_manager_is_never(self, stores, measured):
        d = consider(Src(manager=("", "no route to it")))[1][-1]
        assert d["guard"]["guard"] == "13c" and d["tier"] == 4
        src = Src()
        del src.answers[f"show ip route {MANAGER}"]
        d = consider(src)[1][-1]
        assert d["guard"]["guard"] == "13c" and "was not read" in d["words"]

    def test_once_per_neighbour_per_incident(self, stores, measured):
        prior = {"id": "hd-1", "outcome": "would_heal", "incident": "hi-1", "epoch": T0 - 60,
                 "at": "earlier", "action": {"kind": "session_clear", "device": "r4",
                                             "peer": PEER}}
        d = consider(Src(rows=[prior]))[1][-1]
        assert d["outcome"] == "cant_fix" and d["guard"]["guard"] == "13d", d
        assert "was cleared once in this incident" in d["words"]

    def test_a_clear_not_measured_on_the_platform_is_refused_by_name(self, stores, tmp_path,
                                                                     monkeypatch):
        # The shipped record with its IOS-XE hard clear taken back out (measured on r4,
        # 2026-11-07), so the platform's clear is unmeasured again.
        rec = json.loads(open(P().RESET_MEASURED_FILE, encoding="utf-8").read())
        del rec["by_dialect"]["cisco_iosxe"]["clear-bgp-peer"]
        rec["unmeasured"]["cisco_iosxe"]["clear-bgp-peer"] = "not run yet: a test's record"
        path = tmp_path / "unmeasured.json"
        path.write_text(json.dumps(rec))
        monkeypatch.setattr(P(), "RESET_MEASURED_FILE", str(path))
        d = consider(Src())[1][-1]
        assert d["outcome"] == "cant_fix" and d["tier"] == 3, d
        assert d["guard"]["guard"] == "clear" and "is not measured on cisco_iosxe" in d["words"]

    def test_an_ipv6_neighbour(self, stores, measured):
        src = Src(manager=(MANAGER6, ""))
        d = consider(src, diagnosis(PEER6))[1][-1]
        assert d["outcome"] == "would_heal", d["words"]
        assert d["program"] == [f"clear bgp ipv6 unicast {PEER6}"]
        assert src.reads[-1] == ("r4", [f"show bgp ipv6 unicast neighbors {PEER6}",
                                        f"show ipv6 route {MANAGER6}"])


# ── The act ─────────────────────────────────────────────────────────────────────────────────

def taken(src, diag=None):
    from modules.heal import decisions
    got = S().consider(NET, "hi-1", diag or diagnosis(), now=T0, sources=src)
    assert got["decision"]["outcome"] in ("heal", "propose"), got["decision"]["words"]
    return decisions.take(NET, got["decision"]["id"], by="the test", now=T0)


def auto(dev, **kw):
    kw.setdefault("m", mode("auto", kinds=["session_clear"]))
    return Src(dev=dev, **kw)


class TestTheAct:
    @pytest.mark.parametrize("peer_if", [
        {"name": "GigabitEthernet1", "ipv4": f"{PEER} 255.255.255.252"},
        {"name": "GigabitEthernet1", "ipv6": [f"{PEER6}/64"]}], ids=["ipv4", "ipv6"])
    def test_a_hard_clears_window_names_the_neighbours_device(self, stores, measured, peer_if):
        # C2749: a hard clear drops the session at the neighbour too; committed intent holding
        # the peer's address names its device in the window (an outside peer names none).
        conn = Conn([down(), down(state="Connect"), back()])
        src = auto(conn, intents_={"r4": hv(), "r3": {"interfaces": [peer_if]}})
        S().apply(NET, taken(src), sources=src)
        family_peer = PEER if "ipv4" in peer_if else PEER6
        if family_peer == PEER:
            assert src.far_ends == [[("r3", "")]], src.far_ends
        else:                                         # the IPv4 clear's peer: r3 holds none
            assert src.far_ends == [[]], src.far_ends

    def test_a_hard_clear_whose_intent_cannot_be_read_records_no_window_and_sends_nothing(
            self, stores, measured):
        # C2795: committed intent that cannot be read is not intent naming no neighbour; the
        # act's own plan reads the device's intent first, so it refuses there, before a window.
        conn = Conn([down(), down(state="Connect"), back()])
        src = auto(conn)
        d = taken(src)
        src.intents = lambda: (None, "the committed intent could not be listed (boom)")
        out = S().apply(NET, d, sources=src)
        assert out["outcome"] != "cleared" and conn.sent == [], out["steps"]
        assert getattr(src, "windows", []) == [], "no window recorded"
        assert "r4's committed intent could not be read" in str(out["steps"]), out["steps"]

    def test_cleared_its_window_before_the_send_and_its_records(self, stores, measured):
        from modules.heal import decisions, steplog
        conn = Conn([down(), down(state="Connect"), back()])
        src = auto(conn)
        d = taken(src)
        out = S().apply(NET, d, sources=src)
        assert out["outcome"] == "cleared", out["steps"]
        assert conn.sent == [f"clear ip bgp {PEER}"], "one clear, nothing else"
        assert src.windows == [{"device": "r4", "interface": "GigabitEthernet2",
                                "seconds": 50 + S().WINDOW_MARGIN_S, "sent_before": []}]
        steps = [s["step"] for s in out["steps"]]
        assert steps == ["take", "stops", "plan", "hold", "route", "window", "send", "verify",
                         "record"], steps
        assert src.held_during[0]["operation"] == S().OPERATION, "held throughout"
        assert decisions.find(NET, d["id"])["applied"]["outcome"] == "cleared"
        rows = [r["row"] for r in steplog.read(NET)["rows"]]
        assert rows.count("started") == 1 and rows.count("act") == 1
        run = P().get(NET, out["records"]["privileged"])
        assert (run["state"], run["command"], run["variant"], run["peer"]) == (
            "done", f"clear ip bgp {PEER}", "hard", PEER)
        assert run["actor"] == "op@example.invalid" and "under the policy fp-1" in run["reason"]
        assert run["before"] == down(), "the session before kept in the record"

    def test_a_window_that_cannot_be_recorded_sends_nothing(self, stores, measured):
        conn = Conn([down()])
        src = auto(conn, window={"ok": False, "error": "the store is unreadable"})
        out = S().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "refused" and conn.sent == [], out
        assert "the planned window for the clear could not be recorded" in out["words"]
        assert out["words"].endswith("Nothing was sent")

    def test_the_stops_again_at_the_act(self, stores, measured):
        conn = Conn([down()])
        src = auto(conn)
        d = taken(src)
        src._mode = mode("dry_run", kinds=["session_clear"])
        out = S().apply(NET, d, sources=src)
        assert out["outcome"] == "refused" and "only AUTO sends a heal" in out["words"]
        assert conn.sent == [] and src.windows == []

    def test_a_hash_that_moved_is_refused(self, stores, measured):
        conn = Conn([down()])
        src = auto(conn)
        d = dict(taken(src), program_hash="0000")
        out = S().apply(NET, d, sources=src)
        assert out["outcome"] == "refused" and "the clear's hash moved" in out["words"]
        assert conn.sent == []

    def test_a_session_established_again_at_the_send_is_left_alone(self, stores, measured):
        conn = Conn([ESTABLISHED])
        src = auto(conn)
        out = S().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "refused" and conn.sent == [], out
        assert "a hard clear is never sent to an Established session" in out["words"]

    def test_mercurys_route_on_the_held_session_refuses(self, stores, measured):
        conn = Conn([down()], route=ROUTE_BY_BGP.replace("10.255.1.15/32", "192.0.2.0/24"))
        src = auto(conn)
        out = S().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "refused" and conn.sent == [] and src.windows == []
        assert "13c: Not cleared" in out["words"]

    def test_a_device_held_by_another_operation_sends_nothing(self, stores, measured,
                                                               monkeypatch):
        import contextlib
        from modules.nsot import device_ops
        conn = Conn([down()])
        src = auto(conn)
        d = taken(src)

        @contextlib.contextmanager
        def busy(*a, **k):
            raise device_ops.DeviceBusy({"operation": "deploy",
                                         "actor": "someone@example.invalid"})
            yield
        monkeypatch.setattr(device_ops, "hold", busy)
        out = S().apply(NET, d, sources=src)
        assert out["outcome"] == "refused" and conn.sent == [] and src.windows == []
        assert [s["step"] for s in out["steps"]][-2] == "hold", out["steps"]

    def test_a_session_lost_after_the_send_is_never_nothing_sent(self, stores, measured):
        conn = Conn([down()])
        src = auto(conn)
        d = taken(src)

        def lost(text, **kw):
            conn.dev.sent.append(text)
            raise OSError("Socket is closed")
        conn.send_command_timing = lost
        out = S().apply(NET, d, sources=src)
        assert out["sent"] and out["outcome"] == "unverified", out
        assert "the session failed after the clear was sent" in out["words"]
        assert "Nothing was sent" not in out["words"]

    def test_not_back_within_its_bound(self, stores, measured):
        from modules.heal import decisions
        conn = Conn([down()])
        src = auto(conn)
        d = taken(src)
        out = S().apply(NET, d, sources=src)
        assert out["outcome"] == "not_back" and conn.sent == [f"clear ip bgp {PEER}"]
        assert "not Established within 50 s" in out["words"]
        assert not decisions.halted(NET).get("id"), "a session that was down had nothing to lose"

    def test_a_soft_clear_that_reset_its_session_halts(self, stores, measured):
        from modules.heal import decisions
        conn = Conn([ESTABLISHED, back(REFRESHED)])
        src = auto(conn, answers={f"show ip bgp neighbors {PEER}": ESTABLISHED})
        d = taken(src, diagnosis(rule="bgp_fewer_routes"))
        out = S().apply(NET, d, sources=src)
        assert out["outcome"] == "reset" and conn.sent == [f"clear ip bgp {PEER} soft"], out
        assert decisions.halted(NET)["guard"] == 14

    def test_a_soft_clear_resets_nothing(self, stores, measured):
        conn = Conn([ESTABLISHED, REFRESHED])
        src = auto(conn, answers={f"show ip bgp neighbors {PEER}": ESTABLISHED})
        out = S().apply(NET, taken(src, diagnosis(rule="bgp_fewer_routes")), sources=src)
        assert out["outcome"] == "cleared", out["steps"]
        assert "a soft clear withdraws nothing" in [s["words"] for s in out["steps"]
                                                    if s["step"] == "route"][0]

    def test_the_approved_proposal_runs_as_the_person(self, stores, measured):
        conn = Conn([down(), back()])
        src = Src(dev=conn, m=mode("dry_run", propose=["session_clear"], stage="production"))
        d = taken(src)
        out = S().apply_approved(NET, d, {"by": "person@example.invalid",
                                          "reason": "the peer is stuck after the fibre cut",
                                          "hash": "h-1"}, sources=src)
        assert out["outcome"] == "cleared", out["steps"]
        run = P().get(NET, out["records"]["privileged"])
        assert run["actor"] == "person@example.invalid"
        assert run["reason"] == "the peer is stuck after the fibre cut"
        assert src.held_during[0]["actor"] == "person@example.invalid"

    def test_an_approved_proposal_the_policy_no_longer_proposes_sends_nothing(
            self, stores, measured):
        conn = Conn([down()])
        src = Src(dev=conn, m=mode("dry_run", propose=["session_clear"], stage="production"))
        d = taken(src)
        src._mode = mode("dry_run", stage="production")
        out = S().apply_approved(NET, d, {"by": "p@example.invalid", "reason": "r r r",
                                          "hash": "h"}, sources=src)
        assert out["outcome"] == "refused" and "no longer proposed" in out["words"]
        assert conn.sent == []


# ── The records (H23: History, the change record) ──────────────────────────────────────────

FAR_WINDOW = {"ok": True, "record": {"from": "2026-11-08T06:00:00Z",
                                     "until": "2026-11-08T06:01:50Z", "via": "heal-clear",
                                     "interfaces": ["GigabitEthernet2"],
                                     "expected": {"far_ends": [{"device": "r3",
                                                                "interface": ""}]}}}


def history(device):
    import types
    from modules import history_sources as HS
    return HS.heal({"ref": types.SimpleNamespace(name=NET), "device": device, "limit": 50,
                    "members": None, "since": None, "until": None})["events"]


class TestTheRecords:
    def test_a_clear_keeps_its_far_end_rollback_and_change_record(self, stores, measured):
        conn = Conn([down(), down(state="Connect"), back()])
        src = auto(conn, window=FAR_WINDOW)
        out = S().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "cleared", out["steps"]
        rec = out["records"]
        assert rec["window"]["far_ends"] == [{"device": "r3", "interface": ""}]
        assert rec["rollback"].startswith("does not apply: a session that was not Established")
        cr = rec["change_record"]
        assert cr["state"] == "made" and cr["risk"] == "low", cr
        assert f"# Change record: r4's BGP neighbour {PEER}, a BGP neighbour cleared" \
            in cr["markdown"]
        assert f"clear ip bgp {PEER}" in cr["markdown"] and "its far end: r3" in cr["markdown"]
        assert f"The privileged command's record: {rec['privileged']}" in cr["markdown"]
        assert "The standing policy fp-1" in cr["markdown"]

    def test_history_names_the_neighbour_and_the_far_end_draws_it(self, stores, measured):
        conn = Conn([down()])
        src = auto(conn, window=FAR_WINDOW)
        out = S().apply(NET, taken(src), sources=src)
        assert out["outcome"] == "not_back", out["steps"]
        (e,) = history("r4")
        assert e["what"] == (f"Self-healing (AUTO): r4's BGP neighbour {PEER} cleared, session "
                             "not back"), e["what"]
        rec = dict(e["record"])
        assert rec["Far end"] == "r3" and rec["Privileged command run"] == \
            out["records"]["privileged"]
        assert rec["Rollback"].startswith("does not apply")
        assert "verify: failed" in rec["Verify"]
        assert [x["what"] for x in history("r3")] == [e["what"]]

    def test_an_unverified_clear_is_never_marked_bounced(self, stores, measured):
        from modules.heal import steplog
        assert steplog.mark("unverified", "session_clear") == "cleared, not verified"
        assert steplog.mark("would_heal", "session_clear") == "would clear"

    def test_an_approved_clears_record_names_the_person(self, stores, measured):
        conn = Conn([down(), back()])
        src = Src(dev=conn, m=mode("dry_run", propose=["session_clear"], stage="production"))
        d = taken(src)
        out = S().apply_approved(NET, d, {"by": "person@example.invalid", "verified": "access",
                                          "reason": "the peer is stuck after the fibre cut",
                                          "hash": "h-1", "at": "2026-11-08T06:00:00Z"},
                                 sources=src)
        text = out["records"]["change_record"]["markdown"]
        assert "Approved by person@example.invalid (verified: access)" in text
        assert "sent as person@example.invalid, who approved it" in text


# ── The wiring ──────────────────────────────────────────────────────────────────────────────

class TestTheWiring:
    def test_the_taker_reaches_the_clear(self, monkeypatch):
        from modules.heal import act
        seen = []
        monkeypatch.setattr(S(), "apply", lambda n, d, **k: seen.append(d["id"]) or {"ok": 1})
        act._apply_for(NET, {"id": "hd-x", "action": {"kind": "session_clear"}})
        assert seen == ["hd-x"]

    def test_an_approval_reaches_the_clear(self, monkeypatch):
        from modules.heal import propose
        seen = []
        monkeypatch.setattr(S(), "apply_approved",
                            lambda n, d, a, **k: seen.append((d["id"], a["by"])) or {})
        propose._approved_for(NET, {"id": "hd-y", "action": {"kind": "session_clear"}},
                              {"by": "p@example.invalid"})
        assert seen == [("hd-y", "p@example.invalid")]
        assert propose._steps_of({"action": {"kind": "session_clear"}}) == S().STEPS

    def test_the_notice_considers_the_clear_its_diagnosis_chooses(self, monkeypatch):
        import modules.heal_notice as N
        from modules.heal import bounce
        seen = []
        monkeypatch.setattr(S(), "consider", lambda n, i, d: seen.append("clear") or {})
        monkeypatch.setattr(bounce, "consider", lambda n, i, d: seen.append("bounce") or {})
        N._action_consider(NET, "hi-1", diagnosis())
        N._action_consider(NET, "hi-1", {"hypotheses": [dict(
            diagnosis()["hypotheses"][0], rule="down_admin_up", case="far_end_up")]})
        assert seen == ["clear", "bounce"]

    def test_the_kind_is_built_and_named_in_both_tiers_lists(self):
        from modules.heal import actions, policy
        assert "session_clear" in actions.BUILT and not actions.not_built("session_clear")
        assert "session_clear" in policy.TIER1_KINDS and "session_clear" in policy.TIER2_KINDS
        assert [g for g, _n, _k, kinds in actions.GUARDS if "session_clear" in kinds] == [
            "13a", "13c", "13d"]
