"""The action remediations' declarations (`modules/heal/actions.py`, `modules/heal/flaps.py`,
`diagnose.ACTIONS`; board H's amendment item 2, part H19; docs/HEAL_TO_INTENT.md 19.4), no
network, no device, a fake clock.

- **The four kinds are rows of the tier table,** a session clear Auto only on a network marked
  lab; **every kind is refused by name until its part builds it** ("not built yet: H20"),
  before any guard runs, and no policy may allow one.
- **An action is chosen only from the diagnosis's first, complete hypothesis** by `ACTIONS`:
  a port down while administratively up with its far end up is the bounce's; a far end not
  read, both ends down, or a decisive MTU mismatch above it chooses none.
- **Guards 13a to 13e, in order,** each naming both operands, each failing closed: the
  precondition read again (a port that came back by itself is left alone), the far end up and
  not held nor worked on, never the interface carrying Mercury's address (IPv4 and IPv6; the
  CEF and only-path parts H20's, so the guard still applies), once (a second need within the
  repeat window is the dampening proposal; a session cleared once an incident), and a flap
  measured.
- **The flap record** is the `logs-tail` reader's after-store step: UPDOWN lines recorded at
  their receive time, never the device's clock; a link and its line protocol one transition;
  a person's shutdown no flap; each line once; nothing where healing is off; a window longer
  than the record keeps, or an unreadable record, is unreadable, never quiet.
- **The new settings leave a policy confirmed before them in force,** and setting one is a
  change a person confirms.
"""
import json
import os
import time

import pytest

from tests.test_heal_diagnose import _FLEET_DEVICES, SHOW_IF, diagnose, healthy, with_answer
from tests.test_heal_policy import T0, confirm
from tests.test_heal_triggers import world  # noqa: F401 (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)


@pytest.fixture
def diag_world(networks, monkeypatch):  # noqa: F811 (the fixture)
    """tests/test_heal_diagnose.py's world: its fleet, each read answered by its captures."""
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in _FLEET_DEVICES])
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, c, read_timeout=None: conn.answer(c))
    return networks


def A():
    from modules.heal import actions
    return actions


def F():
    from modules.heal import flaps
    return flaps


def raw(dev, iface, state, proto=False, devclock="Jan  1 00:03:17.371 UTC"):
    """A syslog line as the lab's Loki holds it (tests/fixtures/loki/lines_r4.json's shape),
    its message IOS's own UPDOWN text (tests/fixtures/console/s5-kickstart-take-syslog.txt),
    the device's clock wrong (a slow vIOS clock)."""
    msg = (f"%LINEPROTO-5-UPDOWN: Line protocol on Interface {iface}, changed state to {state}"
           if proto else f"%LINK-3-UPDOWN: Interface {iface}, changed state to {state}")
    return f"Oct 10 21:19:18 {dev} 4290: {dev}: {devclock}: {msg}"


def line(ts, state, proto=False, dev="core-b", iface="GigabitEthernet2"):
    from modules.readers.logs_tail import line_of
    return line_of(str(int(ts * 1e9)), raw(dev, iface, state, proto))


def flap_lines(start, n, dev="core-b", iface="GigabitEthernet2"):
    """*n* transitions, each its link and line protocol lines, 20 s apart."""
    out = []
    for i in range(n):
        state = "down" if i % 2 == 0 else "up"
        out += [line(start + 20 * i, state, dev=dev, iface=iface),
                line(start + 20 * i + 1, state, proto=True, dev=dev, iface=iface)]
    return out


# ── The kinds, and nothing unbuilt runs ─────────────────────────────────────────────────────

class TestTheKinds:
    def test_the_four_kinds_are_rows_of_the_tier_table(self):
        from modules.heal.kinds import KIND_WORDS, TIER
        assert {k: TIER[k] for k in A().KINDS} == {"port_bounce": 1, "session_clear": 1,
                                                   "ospf_reset": 1, "dampening_proposal": 2}
        assert all("action" in KIND_WORDS[k] or "intent" in KIND_WORDS[k] for k in A().KINDS)

    def test_a_session_clear_is_auto_only_on_a_network_marked_lab(self):
        assert (A().tier_of("session_clear", True), A().tier_of("session_clear", False)) == (1, 2)
        assert A().tier_of("port_bounce", False) == 1

    def test_every_kind_is_refused_by_name_before_any_guard(self, monkeypatch):
        # H20 built the bounce and the OSPF reset through it, H21 the session clear, H22 the
        # dampening proposal: every kind is built. A kind whose part has not landed is still
        # refused by name before any guard reads, shown on a stand-in part.
        assert A().BUILT == A().KINDS and A().NOT_BUILT == {}
        monkeypatch.setitem(A().NOT_BUILT, "dampening_proposal", ("H99", "a stand-in part"))
        got = A().judge("dampening_proposal", {}, built=("port_bounce",))
        assert got["outcome"] == "cant_fix" and "not built yet: H99" in got["words"]
        assert [s["step"] for s in got["steps"]] == ["built"], got
        got = A().judge("port_bounce", {})
        assert [s["step"] for s in got["steps"]] == ["built", "13a"], got

    def test_no_policy_may_allow_an_unbuilt_action(self, networks, monkeypatch):
        from modules.heal import policy as H
        monkeypatch.setitem(A().NOT_BUILT, "dampening_proposal", ("H99", "a stand-in part"))
        for key, kind, part in ((H.KINDS_PROPOSE_KEY, "dampening_proposal", "H99"),):
            with pytest.raises(H.PolicyRefused) as e:
                H.plan("Default", {"heal_mode": "dry_run", key: [kind]}, T0)
            assert f"{kind} ({A().KIND_WORDS[kind]}): not built yet: {part}" in str(e.value)
        monkeypatch.delitem(A().NOT_BUILT, "dampening_proposal")
        # H22 built the dampening proposal: Propose only (Tier 2), never Auto, none by default.
        got = H.plan("Default", {"heal_mode": "dry_run",
                                 H.KINDS_PROPOSE_KEY: ["dampening_proposal"]}, T0)
        assert "dampening_proposal" in got["after"][H.KINDS_PROPOSE_KEY], got
        with pytest.raises(H.PolicyRefused):
            H.plan("Default", {"heal_mode": "dry_run",
                               H.KINDS_AUTO_KEY: ["dampening_proposal"]}, T0)
        # H21 built the session clear: a policy may name it in either list (Tier 1 on a lab
        # network, a proposal elsewhere), and none does by default.
        for key in (H.KINDS_AUTO_KEY, H.KINDS_PROPOSE_KEY):
            got = H.plan("Default", {"heal_mode": "dry_run", key: ["session_clear"]}, T0)
            assert "session_clear" in got["after"][key], got

    def test_the_action_guards_settings_are_guard_13s(self):
        from modules.heal import policy as H
        thirteen = next(keys for n, _w, keys in H.GUARDS if n == 13)
        assert {k for _g, _n, keys, _k in A().GUARDS for k in keys} - \
            {"heal_repeat_halts_hours"} <= set(thirteen)
        assert [g for g, *_ in A().GUARDS] == ["13a", "13b", "13c", "13d", "13e"]


# ── The choice from the diagnosis (`diagnose.ACTIONS`) ──────────────────────────────────────

def down(host):
    return SHOW_IF.replace("GigabitEthernet4 is up, line protocol is up",
                           "GigabitEthernet4 is down, line protocol is down")


class TestTheChoice:
    def test_every_rule_actions_names_is_a_runbooks_or_named_unbuilt(self):
        from modules.heal import diagnose as D
        built = {r.name for r in D.RULES}
        for a in D.ACTIONS:
            assert a["kind"] in A().KINDS
            assert (a["rule"] in built) != (a["rule"] in D.ACTION_RULES_NOT_BUILT), a

    def test_a_port_down_with_its_far_end_up_is_the_bounces(self, diag_world):
        from modules.heal import diagnose as D
        got, _ = diagnose(with_answer("r4", "show interfaces GigabitEthernet4", down("r4")))
        act = D.action_for(got)
        assert (act["state"], act["kind"], act["rule"]) == ("chosen", "port_bounce",
                                                           "down_admin_up")
        assert act["at"] == {"host": "r4", "interface": "GigabitEthernet4", "far_host": "r3",
                             "far_interface": "GigabitEthernet4"}

    def test_a_far_end_not_read_chooses_none(self, diag_world):
        from modules.heal import diagnose as D
        from modules.nsot import device_ops
        answers = with_answer("r3", "show interfaces GigabitEthernet4", down("r3"))
        with device_ops.hold("Default", "r4", "deploy", "someone@example.invalid"):
            got, _ = diagnose(answers)
        act = D.action_for(got)
        assert act["state"] == "none" and "lacks evidence" in act["words"], act

    def test_both_ends_down_chooses_none(self, diag_world):
        from modules.heal import diagnose as D
        answers = dict(healthy())
        for h in ("r3", "r4"):
            answers[(h, "show interfaces GigabitEthernet4")] = down(h)
        got, _ = diagnose(answers)
        assert got["hypotheses"][0]["rule"] == "down_admin_up"
        assert D.action_for(got)["state"] == "none"

    def test_a_decisive_finding_above_it_chooses_none(self):
        from modules.heal import diagnose as D
        mtu = {"rule": "mtu", "strength": "decisive", "incomplete": [], "claim": "MTU",
               "id": "diag:1"}
        bounce = {"rule": "down_admin_up", "case": "far_end_up", "strength": "decisive",
                  "incomplete": [], "claim": "down", "id": "diag:2"}
        got = D.action_for({"hypotheses": [mtu, bounce]})
        assert got["state"] == "none" and "is no action's rule" in got["words"]
        assert D.action_for({"hypotheses": [bounce]})["kind"] == "port_bounce"
        assert D.action_for({"hypotheses": []})["state"] == "none"
        lacking = dict(bounce, incomplete=["`show interfaces GigabitEthernet4` on r3: held"])
        assert D.action_for({"hypotheses": [lacking]})["state"] == "none"


# ── The guards ──────────────────────────────────────────────────────────────────────────────

class TestG13aFresh:
    def test_a_port_that_came_back_by_itself_is_left_alone(self):
        then = A().precondition("port_bounce", {"name": "Gi2", "state": "down"})
        again = A().precondition("port_bounce", {"name": "Gi2", "state": "up"})
        g = A().g13a_fresh("port_bounce", then, again)
        assert g["outcome"] == "nothing" and "the port came back by itself" in g["words"]
        assert g["operands"] == {"decided": "Gi2 is down", "again": "Gi2 is up"}
        assert A().g13a_fresh("port_bounce", then, then) is None

    def test_a_read_again_that_failed_sends_nothing(self):
        then = A().precondition("port_bounce", {"name": "Gi2", "state": "down"})
        g = A().g13a_fresh("port_bounce", then, A().precondition("port_bounce", None))
        assert g["outcome"] == "cant_fix" and "could not be read again" in g["words"]

    @pytest.mark.parametrize("kind,facts,holds", [
        ("ospf_reset", {"neighbours": [{"state": "EXSTART"}]}, True),
        ("ospf_reset", {"neighbours": [{"state": "EXSTART"}, {"state": "FULL"}]}, False),
        ("session_clear", {"established": False, "state": "Active"}, True),
        ("session_clear", {"established": True, "state": "Established"}, False),
        ("session_clear", {"established": True, "variant": "soft"}, True),
        ("dampening_proposal", {"flapping": True}, True),
    ])
    def test_each_kinds_precondition(self, kind, facts, holds):
        assert A().precondition(kind, facts)["holds"] is holds


class TestG13bFarEnd:
    FAR = {"device": "edge-a", "interface": "GigabitEthernet2", "managed": True, "state": "up"}

    def g(self, far, **kw):
        kw.setdefault("holder", lambda n, d: None)
        kw.setdefault("working", lambda n, d, now, m: [])
        return A().g13b_far_end("Default", far, T0, changes=3, minutes=10, **kw)

    def test_up_and_not_held_passes(self):
        assert self.g(self.FAR) is None

    def test_an_unmanaged_far_end_is_no_action(self):
        got = self.g(dict(self.FAR, managed=False))
        assert got["outcome"] == "cant_fix" and "cannot be read" in got["words"]

    def test_a_far_end_down_is_the_link(self):
        got = self.g(dict(self.FAR, state="down"))
        assert got["tier"] == 3 and "edge-a GigabitEthernet2 is down, not up" in got["words"]

    def test_a_far_end_held_by_an_operation_holds_it(self, networks):
        from modules.nsot import device_ops
        with device_ops.hold("Default", "edge-a", "deploy", "op@example.com"):
            got = A().g13b_far_end("Default", self.FAR, T0, changes=3, minutes=10,
                                   working=lambda n, d, now, m: [])
        assert got["outcome"] == "held" and "op@example.com" in got["words"]

    def test_a_person_working_on_the_far_end_holds_it(self):
        got = self.g(self.FAR, working=lambda n, d, now, m: [T0 - 60, T0 - 30, T0 - 5])
        assert got["outcome"] == "held" and "a person appears to be working on edge-a" in \
            got["words"] and got["until"] == T0 - 5 + 600

    def test_what_holds_it_unreadable_holds(self):
        def boom(n, d):
            raise OSError("no")
        assert self.g(self.FAR, holder=boom)["outcome"] == "held"


class TestG13cPath:
    INTENT = {"interfaces": [
        {"name": "GigabitEthernet1", "ipv4": "192.0.2.6 255.255.255.252"},
        {"name": "GigabitEthernet3", "ipv6": ["2001:db8:0:7::1/64", "fe80::1/64"]},
        {"name": "GigabitEthernet2", "ipv4": "192.0.2.9 255.255.255.252",
         "ipv6": ["2001:db8:0:9::1/64"]}]}

    @pytest.mark.parametrize("iface,mgmt", [("GigabitEthernet1", "192.0.2.6"),
                                            ("GigabitEthernet3", "2001:db8:0:7::1")])
    def test_the_interface_carrying_mercurys_address_is_never_bounced(self, iface, mgmt):
        got = A().g13c_path("core-b", iface, mgmt_ip=mgmt, intent=self.INTENT)
        assert got["tier"] == 4 and f"{iface} carries {mgmt}, the address Mercury reaches " \
            "core-b on" in got["words"]

    @pytest.mark.parametrize("mgmt", ["192.0.2.6", "2001:db8:0:7::1"])
    def test_its_cef_and_only_path_parts_are_h20s_so_it_still_applies(self, mgmt):
        # H20 builds both parts (tests/test_heal_bounce.py); a part not read still applies.
        got = A().g13c_path("core-b", "GigabitEthernet2", mgmt_ip=mgmt, intent=self.INTENT)
        assert got["tier"] == 4 and "route to Mercury was not read" in got["words"]
        cef = {"manager": "192.0.2.250", "command": "show ip cef 192.0.2.250",
               "answer": "0.0.0.0/0\n  nexthop 192.0.2.5 GigabitEthernet1"}
        got = A().g13c_path("core-b", "GigabitEthernet2", mgmt_ip=mgmt, intent=self.INTENT,
                            cef=cef)
        assert got["tier"] == 4 and "blast radius" in got["words"]

    def test_an_interface_intent_lacks_or_no_address_applies(self):
        assert "holds no GigabitEthernet9" in A().g13c_path(
            "core-b", "GigabitEthernet9", mgmt_ip="192.0.2.6", intent=self.INTENT)["words"]
        assert "is not known" in A().g13c_path(
            "core-b", "GigabitEthernet2", mgmt_ip="", intent=self.INTENT)["words"]


def row(kind="port_bounce", device="core-b", interface="GigabitEthernet2", peer="", epoch=T0,
        incident="inc-1"):
    return {"id": f"dc-{int(epoch)}", "kind": kind, "device": device, "interface": interface,
            "peer": peer, "incident": incident, "epoch": epoch, "at": "earlier"}


class TestG13dOnce:
    TARGET = {"device": "core-b", "interface": "GigabitEthernet2", "incident": "inc-2"}

    def g(self, kind, rows, now=T0 + 600, per_hour=1, target=None):
        return A().g13d_once(kind, rows, target or self.TARGET, now, per_hour=per_hour,
                             repeat_hours=24)

    def test_a_second_need_within_24_h_is_the_dampening_proposal(self):
        got = self.g("port_bounce", [row(epoch=T0 - 20 * 3600)])
        assert (got["outcome"], got["instead"]) == ("instead", "dampening_proposal")
        assert "a second need is the dampening proposal, never a second bounce" in got["words"]

    def test_an_ospf_reset_is_a_bounce_of_its_port(self):
        assert self.g("port_bounce", [row(kind="ospf_reset")])["instead"] == \
            "dampening_proposal"

    def test_a_bounce_older_than_the_window_or_of_another_port_is_none(self):
        assert self.g("port_bounce", [row(epoch=T0 - 25 * 3600),
                                      row(interface="GigabitEthernet1")]) is None

    def test_none_an_hour_bounces_none(self):
        assert self.g("port_bounce", [], per_hour=0)["outcome"] == "cant_fix"

    def test_a_session_is_cleared_once_an_incident(self):
        target = {"device": "core-b", "peer": "2001:db8::2", "incident": "inc-1"}
        got = self.g("session_clear", [row(kind="session_clear", peer="2001:db8::2")],
                     target=target)
        assert got["tier"] == 3 and "a second need is can't fix" in got["words"]
        assert self.g("session_clear", [row(kind="session_clear", peer="2001:db8::2",
                                            incident="inc-0")], target=target) is None


class TestG13eFlap:
    def test_an_unreadable_record_fails_closed(self):
        got = A().g13e_flap("port_bounce", {"state": "unreadable", "words": "torn"})
        assert got["outcome"] == "cant_fix" and "torn" in got["words"]

    def test_dampening_needs_a_measured_flap(self):
        quiet = {"state": "read", "flapping": False, "words": "1 transition"}
        assert A().g13e_flap("dampening_proposal", quiet)["outcome"] == "nothing"
        assert A().g13e_flap("port_bounce", quiet) is None
        assert A().g13e_flap("dampening_proposal", dict(quiet, flapping=True)) is None


class TestTheJudgement:
    def test_the_guards_run_in_order_and_the_first_hit_ends(self):
        hit13b = A().hit("13b", "held", "far end held", {"far_device": "edge-a"}, until=T0)
        got = A().judge("port_bounce", {"13a": None, "13b": hit13b, "13c": None},
                        built=("port_bounce",))
        assert got["outcome"] == "held" and got["guard"]["guard"] == "13b"
        assert [s["step"] for s in got["steps"]] == ["built", "13a", "13b"]

    def test_a_guard_not_judged_applies(self):
        got = A().judge("port_bounce", {"13a": None}, built=("port_bounce",))
        assert got["guard"]["guard"] == "13b" and "was not judged" in got["words"]

    def test_every_guard_passed_and_only_those_that_apply(self):
        got = A().judge("dampening_proposal", {"13a": None, "13e": None},
                        built=("dampening_proposal",))
        assert got["outcome"] == "pass"
        assert [s["step"] for s in got["steps"]] == ["built", "13a", "13e"]

    def test_13d_sends_a_second_bounce_to_the_dampening_proposal(self):
        d = A().g13d_once("port_bounce", [row()], {"device": "core-b",
                                                   "interface": "GigabitEthernet2"}, T0 + 60,
                          per_hour=1, repeat_hours=24)
        got = A().judge("port_bounce", {"13a": None, "13b": None, "13c": None, "13d": d},
                        built=("port_bounce",))
        assert (got["outcome"], got["instead"]) == ("instead", "dampening_proposal")

    def test_history_reads_the_action_rows_the_decisions_store_holds(self, networks,
                                                                    monkeypatch):
        from modules.heal import decisions
        rows = [{"id": "dc-1", "outcome": "heal", "epoch": T0, "at": "x", "incident": "i",
                 "action": {"kind": "port_bounce", "device": "core-b",
                            "interface": "GigabitEthernet2"}},
                {"id": "dc-2", "outcome": "heal", "epoch": T0, "units": []},
                {"id": "dc-3", "outcome": "would_heal", "epoch": T0,
                 "action": {"kind": "port_bounce", "device": "core-b"}}]
        monkeypatch.setattr(decisions, "decisions", lambda network: rows)
        assert [r["id"] for r in A().history("Default", "heal")] == ["dc-1"]


# ── The flap record (13e) ───────────────────────────────────────────────────────────────────

def record():
    from modules import config
    with open(os.path.join(config.DATA_DIR, "heal", "flaps.json"), encoding="utf-8") as fh:
        return json.load(fh)


class TestTheFlapRecord:
    def test_a_link_and_its_line_protocol_are_one_transition_at_the_receive_time(self, world):
        got = F().from_logs_tail("logs-tail", {"lines": flap_lines(T0, 3)}, now=T0 + 120)
        assert got["recorded"] == 3
        t = F().transitions("Default", "core-b", "GigabitEthernet2", T0 - 1, T0 + 120)
        # The collector's receive time, never the device's clock (Jan 1, a slow vIOS clock).
        assert [(x["epoch"], x["state"]) for x in t["transitions"]] == [
            (T0, "down"), (T0 + 20, "up"), (T0 + 40, "down")]

    def test_three_in_ten_minutes_is_a_flap_two_is_not(self, world):
        F().from_logs_tail("logs-tail", {"lines": flap_lines(T0, 3)}, now=T0 + 120)
        got = F().flapping("Default", "core-b", "GigabitEthernet2", T0 + 120, at_least=3,
                           minutes=10)
        assert got["flapping"] and got["transitions"] == 3 and "a flap" in got["words"]
        assert not F().flapping("Default", "core-b", "GigabitEthernet2", T0 + 120,
                                at_least=4, minutes=10)["flapping"]
        late = F().flapping("Default", "core-b", "GigabitEthernet2", T0 + 610, at_least=3,
                            minutes=10)
        assert late["transitions"] == 2 and not late["flapping"]

    def test_a_shutdown_is_no_flap(self, world):
        from modules.readers.logs_tail import line_of
        shut = line_of(str(int(T0 * 1e9)), "Oct 10 21:19:18 core-b 4290: core-b: Jan  1 "
                       "00:03:17.371 UTC: %LINK-5-CHANGED: Interface GigabitEthernet2, changed "
                       "state to administratively down")
        assert F().from_logs_tail("logs-tail", {"lines": [shut]}, now=T0)["recorded"] == 0

    def test_each_line_once(self, world):
        lines = flap_lines(T0, 2)
        F().from_logs_tail("logs-tail", {"lines": lines}, now=T0 + 60)
        again = F().from_logs_tail("logs-tail", {"lines": lines + flap_lines(T0 + 100, 1)},
                                   now=T0 + 160)
        assert again["recorded"] == 1
        assert len(F().transitions("Default", "core-b", "GigabitEthernet2", T0 - 1,
                                   T0 + 160)["transitions"]) == 3

    def test_nothing_where_healing_is_off_but_the_lines_are_consumed(self, world, monkeypatch):
        from modules import attention as AT
        monkeypatch.setattr(AT, "_device_networks", lambda: {"core-b": ["Branch"]})
        got = F().from_logs_tail("logs-tail", {"lines": flap_lines(T0, 3)}, now=T0 + 60)
        assert (got["recorded"], got["off"]) == (0, 6)
        doc = record()
        assert doc["cursors"]["logs-tail"] == T0 + 41 and "Branch" not in doc.get("networks", {})

    def test_an_ipv6_only_device_is_placed_like_any(self, world):
        got = F().from_logs_tail("logs-tail", {"lines": flap_lines(T0, 1, dev="v6-d",
                                                                   iface="GigabitEthernet1")},
                                 now=T0 + 10)
        assert got["recorded"] == 1

    def test_the_record_keeps_an_hour_and_a_longer_window_is_unreadable(self, world):
        F().from_logs_tail("logs-tail", {"lines": flap_lines(T0, 1)}, now=T0 + 10)
        # Up an hour later: a transition (a second "down" would be none: the state is known).
        F().from_logs_tail("logs-tail", {"lines": [line(T0 + 3700, "up")]}, now=T0 + 3710)
        assert F().transitions("Default", "core-b", "GigabitEthernet2", T0 + 200,
                               T0 + 3710)["transitions"][0]["epoch"] == T0 + 3700
        assert "core-b" in record()["networks"]["default"]
        assert len(record()["networks"]["default"]["core-b"]["gigabitethernet2"][
            "transitions"]) == 1
        got = F().transitions("Default", "core-b", "GigabitEthernet2", T0, T0 + 3710)
        assert got["state"] == "unreadable" and "longer than the flap record keeps" in \
            got["words"]

    def test_an_unreadable_record_is_never_quiet(self, world):
        from modules import config
        os.makedirs(os.path.join(config.DATA_DIR, "heal"), exist_ok=True)
        with open(os.path.join(config.DATA_DIR, "heal", "flaps.json"), "w",
                  encoding="utf-8") as fh:
            fh.write("{torn")
        got = F().flapping("Default", "core-b", "GigabitEthernet2", T0, at_least=3, minutes=10)
        assert got["state"] == "unreadable" and not got["flapping"]
        assert A().g13e_flap("port_bounce", got)["outcome"] == "cant_fix"


class TestTheStep:
    def test_start_installs_it(self, monkeypatch, world):
        from modules import reader_job as RJ
        monkeypatch.setattr(RJ, "readers", lambda: [])
        F().uninstall()
        RJ.start()
        try:
            assert F()._after_store in RJ._AFTER_ANY_STORE
        finally:
            F().uninstall()

    def test_a_logs_tail_store_runs_it_and_another_readers_does_not(self, world):
        from modules import reader_job as RJ
        now = time.time()
        lines = flap_lines(now - 60, 1)
        for name, n in (("adjacencies@t9", 0), ("logs-tail@t9", 1)):
            reader = RJ.Reader(name=name, what="a test's reader", endpoints=("a test",),
                               interval_seconds=5, interval_basis="a test",
                               invalidates=("logs",),
                               read=lambda: {"configured": True, "lines": lines})
            F().install()
            try:
                RJ.run_once(reader, clock=lambda: now)
            finally:
                F().uninstall()
            got = F().transitions("Default", "core-b", "GigabitEthernet2", now - 120, now)
            assert len(got["transitions"]) == n, name

    def test_a_step_that_fails_never_stops_the_reader(self, world, monkeypatch):
        from modules import reader_job as RJ

        def boom(store, value):
            raise RuntimeError("no")
        monkeypatch.setattr(F(), "from_logs_tail", boom)
        reader = RJ.Reader(name="logs-tail@t8", what="a test's tail", endpoints=("a test",),
                           interval_seconds=5, interval_basis="a test", invalidates=("logs",),
                           read=lambda: {"configured": True, "lines": []})
        F().install()
        try:
            doc = RJ.run_once(reader, clock=time.time)
        finally:
            F().uninstall()
        assert doc["last_attempt"]["ok"] is True


# ── The settings and the fingerprint ────────────────────────────────────────────────────────

class TestTheSettings:
    def test_a_policy_confirmed_before_them_keeps_its_fingerprint(self):
        from modules.heal import policy as H
        from modules.settings_schema import DEFAULTS
        before = {k: DEFAULTS[k] for k in H.POLICY_KEYS if k not in H.ACTION_GUARD_KEYS}
        at_default = dict(before, **{k: DEFAULTS[k] for k in H.ACTION_GUARD_KEYS})
        assert H.policy_fingerprint(before) == H.policy_fingerprint(at_default)
        assert H.policy_fingerprint(dict(at_default, heal_flap_transitions=4)) != \
            H.policy_fingerprint(at_default)

    def test_setting_one_is_confirmed_by_a_person_and_in_force(self, networks):
        from modules.heal import policy as H
        confirm("Default", heal_mode="dry_run")
        confirm("Default", heal_flap_transitions=5, heal_flap_minutes=15)
        got = H.current("Default", T0)
        assert got["mode"] == "dry_run"
        assert (got["guards"]["heal_flap_transitions"]["value"],
                got["guards"]["heal_flap_minutes"]["value"]) == (5, 15)

    @pytest.mark.parametrize("key,value", [("heal_flap_minutes", 61),
                                           ("heal_bounce_per_port_hour", 2),
                                           ("heal_flap_transitions", 1)])
    def test_the_schema_holds_their_ceilings(self, networks, key, value):
        from modules.heal import policy as H
        with pytest.raises(H.PolicyRefused) as e:
            H.plan("Default", {"heal_mode": "dry_run", key: value}, T0)
        # The schema's refusal, never "not part of a heal policy" (a key it does not hold).
        assert str(e.value).startswith("not a heal policy: "), str(e.value)
