"""Heal to intent's decision (`modules/heal/kinds.py`, `guards.py`, `decide.py`,
`decisions.py`, and `attention.heal_source`; board H, part H3, docs/HEAL_TO_INTENT.md sections
2, 4 to 7 and 11, N4, N5, N9, N12 and N13), no network, no device, a fake clock.

- **The intersection rule:** a line is healed only if it departed from both the golden and
  intent; an intent edit not deployed, a golden behind, and a golden that departs from intent
  are each left out and counted.
- **Units (N13):** one feature on one section, by the parser's grouping (R3's two lines one
  unit); a departed stanza one unit; a single-valued setting changed one unit.
- **Kinds and tiers:** every row of section 5 with a planted case (N4: every ACL Tier 4; N9: a
  secret added back Tier 2, a routing key removed Tier 1, masked); the strictest unit's tier is
  the incident's; an unmeasured removal blocked naming the probe; IPv4 and IPv6 routes.
- **The guards, in order,** each shown applying with both operands; a halt in force; a halt
  only in AUTO; lifted only by a person with a reason.
- **The outcomes:** heal (AUTO, a kind allowed), would heal (dry run, or a kind not allowed),
  propose (Tier 2), can't fix (Tiers 3 and 4, blocked, a program that would cut Mercury's
  path), nothing to heal; the person named (N12).
- **The program, one computation,** its hash recomputable by H4 and moving with the device.
- **The record:** masked lines only, never a secret; Right / Wrong by a verified person, counted
  per kind; the seams H4 and H5 take, each once.
- **The drift row carries the dry-run record** (`attach_to`), keeping its own action.
"""
import json

import pytest

from tests.test_heal_policy import T0, auto, confirm, iso, mark
from tests.test_sdn_connections import networks  # the fixture, named by each test below
from tests.test_heal_triggers import _Lazy

K, GD, DC, DS, I = (_Lazy("kinds"), _Lazy("guards"), _Lazy("decide"), _Lazy("decisions"),
                    _Lazy("incidents"))
PLATFORM = "cisco_iosxe"
PERSON = {"by": "op@example.com", "actor_verified": "access", "person": True}

GOLDEN = """hostname edge-b
interface GigabitEthernet1
 description management
 ip address 192.0.2.6 255.255.255.252
interface GigabitEthernet2
 description to leaf
 ip address 192.0.2.13 255.255.255.252
interface GigabitEthernet4
 description to core
 ip address 192.0.2.9 255.255.255.252
 ip ospf cost 10
router ospf 1
 router-id 192.0.2.6
 network 192.0.2.8 0.0.0.3 area 0
event manager applet HB
 event timer watchdog time 60
 action 1 syslog msg heartbeat
logging host 192.0.2.50
"""


def changed(*pairs, base=GOLDEN):
    out = base
    for old, new in pairs:
        assert old in out, old
        out = out.replace(old, new)
    return out


ROUTE4 = "ip route 192.0.2.128 255.255.255.128 192.0.2.10\n"
ROUTE6 = "ipv6 route 2001:db8:9::/48 2001:db8:0:7::2\n"


def classify(running, golden=GOLDEN, intended=GOLDEN, **kw):
    return K.classify(golden, running, intended, platform=PLATFORM, mgmt_ip="192.0.2.6", **kw)


@pytest.fixture(autouse=True)
def no_host_addresses(monkeypatch):
    """This host's addresses, for the manager's routes: outside every test route."""
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])


# ── The intersection rule ───────────────────────────────────────────────────────────────────

class TestTheIntersection:
    def test_a_missing_line_both_hold_is_healed(self):
        got = classify(changed(("logging host 192.0.2.50\n", "")))
        (u,) = got["units"]
        assert (u["op"], u["kind"], u["tier"]) == ("add", "missing_line", 1)

    def test_an_intent_edit_not_deployed_is_never_healed(self):
        got = classify(GOLDEN, intended=GOLDEN + "ntp server 192.0.2.51\n")
        assert got["units"] == [] and got["left_out"]["intent_only"] == 1

    def test_a_line_the_device_and_intent_hold_and_the_golden_lacks_is_left(self):
        got = classify(GOLDEN + "ntp server 192.0.2.51\n",
                       intended=GOLDEN + "ntp server 192.0.2.51\n")
        assert got["units"] == [] and got["left_out"]["golden_behind"] == 1

    def test_a_line_the_golden_holds_and_intent_lacks_is_not_put_back(self):
        got = classify(changed(("logging host 192.0.2.50\n", "")),
                       intended=changed(("logging host 192.0.2.50\n", "")))
        assert got["units"] == [] and got["left_out"]["golden_not_intent"] == 1

    def test_a_raw_read_is_compared_in_the_golden_s_stored_form(self):
        raw = "! NVRAM config last updated at 10:00:00 UTC Mon Nov 2 2026\n" + GOLDEN
        assert classify(raw)["units"] == []


# ── Units (N13) ─────────────────────────────────────────────────────────────────────────────

class TestUnits:
    def test_the_parser_groups_one_feature_on_one_interface(self):
        """R3: the authentication mode and its key are one unit, removed together."""
        got = classify(changed((" ip ospf cost 10\n", " ip ospf cost 10\n ip ospf "
                                "authentication message-digest\n ip ospf message-digest-key 1 "
                                "md5 S3cretKey\n")))
        (u,) = got["units"]
        assert u["op"] == "remove" and len(u["remove"]) == 2
        assert u["kind"] == "added_line", "N9: a routing key removed returns to intent, Tier 1"

    def test_two_features_on_one_interface_are_two_units(self):
        got = classify(changed((" ip ospf cost 10\n", " ip ospf cost 10\n load-interval 30\n"
                                " ip ospf authentication message-digest\n")))
        assert len(got["units"]) == 2

    def test_outside_an_interface_each_multi_valued_line_is_its_own_unit(self):
        got = classify(GOLDEN + ROUTE4 + ROUTE6)
        assert len(got["units"]) == 2
        got = classify(changed((" network 192.0.2.8 0.0.0.3 area 0\n",
                                " network 192.0.2.8 0.0.0.3 area 0\n network 192.0.2.16 0.0.0.3 "
                                "area 0\n network 192.0.2.20 0.0.0.3 area 0\n")))
        assert len(got["units"]) == 2

    def test_a_departed_stanza_is_one_unit_with_its_lines(self):
        got = classify(changed(("event manager applet HB\n event timer watchdog time 60\n"
                                " action 1 syslog msg heartbeat\n", "")))
        (u,) = got["units"]
        assert u["stanza"] and u["op"] == "add" and len(u["add"]) == 3

    def test_a_single_valued_setting_changed_is_one_changed_unit(self):
        got = classify(changed((" ip ospf cost 10\n", " ip ospf cost 50\n")))
        (u,) = got["units"]
        assert (u["op"], u["kind"]) == ("change", "changed_line")
        assert [l for _c, l in u["add"]] == [" ip ospf cost 10"]

    def test_feature_of_reads_the_parse_not_the_text(self):
        a = K.feature_of(PLATFORM, ("interface GigabitEthernet4",),
                         " ip ospf authentication message-digest")
        b = K.feature_of(PLATFORM, ("interface GigabitEthernet4",),
                         " ip ospf message-digest-key 1 md5 x")
        c = K.feature_of(PLATFORM, ("interface GigabitEthernet4",), " description x")
        assert a["feature"] == b["feature"] and not a["single"]
        assert c["single"] and c["feature"] != a["feature"]


# ── Kinds and tiers (section 5) ─────────────────────────────────────────────────────────────

GI2 = " description to leaf\n ip address 192.0.2.13 255.255.255.252\n"


class TestKinds:
    @pytest.mark.parametrize("route", [ROUTE4, ROUTE6])
    def test_an_added_static_route_is_tier_1_and_its_measured_removal_named(self, route):
        got = classify(GOLDEN + route)
        (u,) = got["units"]
        assert (u["kind"], u["tier"], u["blocked"]) == ("added_line", 1, "")
        assert got["removal_ids"] == u["removal_ids"] != []

    def test_admin_down_where_intent_says_up(self):
        got = classify(changed((GI2, GI2 + " shutdown\n")))
        assert got["units"][0]["kind"] == "admin_down"

    @pytest.mark.parametrize("added", [
        "ip access-list extended EDGE\n 10 permit tcp any any\n",
        "access-list 101 permit ip any any\n"])
    def test_every_acl_is_tier_4_n4(self, added):
        got = classify(GOLDEN + added)
        assert (got["kind"], got["tier"]) == ("security_acl", 4)

    def test_an_acl_binding_is_tier_4(self):
        got = classify(changed((GI2, GI2 + " ip access-group 101 in\n")))
        assert got["kind"] == "security_acl"

    @pytest.mark.parametrize("added", ["username audit privilege 15 secret 9 $9$abc\n",
                                       "snmp-server community Pub1ic RO\n",
                                       "aaa new-model\n"])
    def test_credentials_and_aaa_are_tier_4(self, added):
        assert classify(GOLDEN + added)["kind"] == "credentials"

    def test_the_management_interface_is_tier_4(self):
        got = classify(changed((" description management\n", " description mgmt\n")))
        assert (got["kind"], got["tier"]) == ("management_path", 4)

    def test_a_route_that_may_be_the_managers_is_tier_4(self, monkeypatch):
        monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.130"])
        got = classify(GOLDEN + ROUTE4)
        assert got["kind"] == "management_path", got["units"]

    def test_a_qos_policy_is_tier_2(self):
        got = classify(changed((GI2, GI2 + " service-policy output SHAPE\n")))
        assert (got["kind"], got["tier"]) == ("qos_policy", 2)

    def test_a_router_id_changed_is_a_process_reset(self):
        got = classify(changed((" router-id 192.0.2.6\n", " router-id 192.0.2.99\n")))
        assert (got["kind"], got["tier"]) == ("process_reset", 2)

    def test_a_secret_added_back_is_tier_2_n9(self):
        golden = changed((" ip ospf cost 10\n", " ip ospf cost 10\n ip ospf message-digest-key "
                          "1 md5 S3cretKey\n"))
        got = classify(GOLDEN, golden=golden, intended=golden)
        assert (got["kind"], got["tier"]) == ("secret_added_back", 2)

    def test_a_cause_spanning_devices_is_tier_4(self):
        assert classify(GOLDEN + ROUTE4, related=True)["kind"] == "multi_device"

    def test_an_unmeasured_removal_is_blocked_naming_the_probe(self):
        # A line no measured shape covers (the OSPF authentication shapes, this test's example
        # until 2026-11-07, are measured exact now: C2373).
        got = classify(changed((" ip ospf cost 10\n", " ip ospf cost 10\n ip ospf "
                                "hello-interval 5\n")))
        assert "scripts/nmas-removal-probe" in got["blocked"]["why"]

    def test_the_strictest_unit_is_the_incidents_tier(self):
        got = classify(GOLDEN + ROUTE4 + "access-list 101 permit ip any any\n")
        assert (got["tier"], got["kind"]) == (4, "security_acl")

    def test_the_tiers_are_a_ceiling_in_code_matching_the_policy(self):
        from modules.heal.actions import NOT_BUILT
        from modules.heal.policy import TIER1_KINDS, TIER2_KINDS

        # An action kind (19.4, H19) is in the tier table before its operation is built, and
        # no policy may name it until then; once built it must be in the policy's lists.
        built = {k: t for k, t in K.TIER.items() if k not in NOT_BUILT}
        assert {k for k, t in built.items() if t == 1} == set(TIER1_KINDS)
        assert {k for k, t in built.items() if t == 2} == set(TIER2_KINDS)
        assert set(NOT_BUILT) <= set(K.TIER)
        assert not set(NOT_BUILT) & set(TIER1_KINDS + TIER2_KINDS)

    def test_a_record_holds_masked_lines_only(self):
        got = classify(changed((" ip ospf cost 10\n", " ip ospf cost 10\n ip ospf "
                                "authentication message-digest\n ip ospf message-digest-key 1 "
                                "md5 S3cretKey\n")))
        assert "S3cretKey" not in json.dumps([K.masked_unit(u) for u in got["units"]])


# ── The decision, through decide_one with its sources faked ────────────────────────────────

class Fake:
    """The decision's sources: the golden at intent, the device read as *running*."""

    def __init__(self, running, golden=GOLDEN, intended=GOLDEN, state="at_intent", held=None,
                 read_error=""):
        self.running, self.golden_text, self.intended_text = running, golden, intended
        self.state, self.held, self.read_error, self.reads = state, held, read_error, 0

    def device(self, device):
        return {"hostname": device, "ip": "192.0.2.6", "platform": PLATFORM}

    def golden(self, device, dev):
        return {"text": self.golden_text, "commit": "c0ffee", "state": self.state,
                "words": "at intent" if self.state == "at_intent" else "departs (+1)"}

    def intended(self, device, platform):
        return {"text": self.intended_text, "platform": platform, "why": ""}

    def platform(self, device, dev):
        return PLATFORM

    def read(self, dev):
        self.reads += 1
        return (None, self.read_error) if self.read_error else (self.running, "")

    def intents(self):
        return {}

    def host_networks(self):
        return ["192.0.2.4/30"]

    def topology(self, device, now):
        return self.held or {"held": False, "words": "not held"}


def settle(running, golden=GOLDEN, how="persisted", device="edge-b", triggers=None,
           network="Default", related=None, claim=True):
    """An incident for *device*, settled with *running*'s departure: claimed (as the decision
    takes it), or left ready (*claim* False) for the decision's job."""
    from modules.drift_check import departure, drift_diff

    t = triggers if triggers is not None else [{
        "kind": "config_change", "key": "cfg:1", "epoch": T0 - 1000, "at": iso(T0 - 1000),
        "attribution": {"by": "outside"},
        "person": {"user": "alice", "words": "the line names the account alice on vty0"},
        "words": "CONFIG_I"}]
    first = I.sight(network, device, t[0], now=T0 - 1000)
    for extra in t[1:]:
        I.sight(network, device, extra, now=T0 - 1000)
    inc_id = first["incident"]
    if related:
        def add(doc):
            next(i for i in doc["incidents"] if i["id"] == inc_id)["related"] = related
        I._mutate(network, add)
    dep = departure(drift_diff(golden, running, device))
    I.settle(network, inc_id, {"state": how, "words": "settled", "first": 0, "second": 1,
                               "operands": {"departure": dep}}, T0 - 10)
    if not claim:
        return I.ready(network)[-1]
    return I.claim(network, inc_id, by="test", now=T0 - 5)


@pytest.fixture
def lab(networks, monkeypatch):
    """Default marked lab, dry run; no planned work, hold or window."""
    monkeypatch.setattr("modules.restarts.explained_by", lambda d, n, now: None)
    monkeypatch.setattr("modules.nsot.device_ops.holder", lambda n, d: None)
    monkeypatch.setattr("modules.change_windows.holding", lambda now=None, given=None: None)
    monkeypatch.setattr("modules.heal.detect.wake", lambda: None)
    mark("Default")
    confirm("Default", heal_mode="dry_run")
    return networks


def one(running, src=None, **kw):
    inc = settle(running, **kw)
    return DC.decide_one("Default", inc, now=T0, sources=src or Fake(running))


class TestOutcomes:
    def test_dry_run_would_heal_with_its_program_and_hash(self, lab):
        d = one(GOLDEN + ROUTE4)
        assert d["outcome"] == "would_heal" and "the mode is dry run" in d["words"]
        assert d["program"] == ["no ip route 192.0.2.128 255.255.255.128 192.0.2.10"]
        assert len(d["program_hash"]) >= 16 and d["removal_ids"]

    def test_auto_heals_a_kind_it_allows(self, lab):
        auto("Default", now=T0 - 60, kinds=("added_line",))
        d = one(GOLDEN + ROUTE6)
        assert d["outcome"] == "heal", d["words"]
        assert d["program"] == ["no ipv6 route 2001:db8:9::/48 2001:db8:0:7::2"]

    def test_auto_keeps_a_kind_it_does_not_allow_in_dry_run(self, lab):
        auto("Default", now=T0 - 60, kinds=("added_line",))
        d = one(changed(("logging host 192.0.2.50\n", "")))
        assert d["outcome"] == "would_heal" and "missing_line is not allowed AUTO" in d["words"]

    def test_a_tier_2_kind_the_policy_proposes_is_proposed(self, lab):
        d = one(changed((" router-id 192.0.2.6\n", " router-id 192.0.2.99\n")))
        assert (d["outcome"], d["kind"]) == ("propose", "process_reset")

    def test_tier_4_is_never_automatic_n4(self, lab):
        d = one(GOLDEN + "access-list 101 permit ip any any\n")
        assert d["outcome"] == "cant_fix" and "never automatic" in d["words"]
        assert d["program"] == [], "nothing is computed for a fix that is never sent"

    def test_a_blocked_unit_cannot_be_fixed_yet(self, lab):
        # A line no measured shape covers (C2373 measured the OSPF authentication shapes).
        d = one(changed((" ip ospf cost 10\n", " ip ospf cost 10\n ip ospf hello-interval "
                         "5\n")))
        assert d["outcome"] == "cant_fix" and "nmas-removal-probe" in d["words"]

    def test_a_program_that_would_cut_mercurys_path_is_tier_4(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.expected_effects.for_device",
                            lambda *a, **k: {"reach_lost": {"state": "known",
                                                            "cut": ["leaf-c"]}})
        d = one(GOLDEN + ROUTE4)
        assert (d["outcome"], d["kind"]) == ("cant_fix", "management_path")
        assert "leaf-c" in d["words"]

    def test_the_person_is_named_n12(self, lab):
        d = one(GOLDEN + ROUTE4)
        assert "the account alice" in d["words"] and d["person"]["user"] == "alice"

    def test_at_its_golden_with_a_link_down_is_physical(self, lab):
        trig = [{"kind": "alert", "key": "alert:1", "epoch": T0 - 900, "at": iso(T0 - 900),
                 "interface": "GigabitEthernet4", "words": "Interface down"}]
        d = one(GOLDEN, how="at_golden", triggers=trig)
        assert (d["outcome"], d["kind"], d["tier"]) == ("cant_fix", "physical", 3)

    def test_at_its_golden_with_no_symptom_is_nothing_to_heal(self, lab):
        assert one(GOLDEN, how="at_golden")["outcome"] == "nothing"

    def test_only_an_intent_edit_is_nothing_to_heal(self, lab):
        src = Fake(GOLDEN, intended=GOLDEN + "ntp server 192.0.2.51\n")
        d = one(GOLDEN + "ntp server 192.0.2.52\n", src=Fake(
            GOLDEN + "ntp server 192.0.2.52\n", intended=GOLDEN + "ntp server 192.0.2.52\n"))
        assert d["outcome"] == "nothing" and src.reads == 0

    def test_a_device_moved_since_it_settled_is_checked_again(self, lab):
        inc = settle(GOLDEN + ROUTE4)
        d = DC.decide_one("Default", inc, now=T0, sources=Fake(GOLDEN + ROUTE6))
        assert d["outcome"] == "deferred" and "changed since its grace period" in d["words"]

    def test_a_read_that_fails_is_checked_again(self, lab):
        d = one(GOLDEN + ROUTE4, src=Fake(GOLDEN + ROUTE4, read_error="timed out"))
        assert d["outcome"] == "deferred" and "timed out" in d["words"]


# ── The guards, in order ────────────────────────────────────────────────────────────────────

class TestGuards:
    def test_1_the_kill_switch(self, lab):
        from modules.heal import policy

        policy.stop(actor="op@example.com", why="a drill")
        d = one(GOLDEN + ROUTE4)
        assert (d["outcome"], d["guard"]["guard"]) == ("off", 1)

    def test_2_the_mode_off(self, lab):
        from modules.heal import policy

        inc = settle(GOLDEN + ROUTE4)
        policy.turn_off("Default", actor="op@example.com")
        d = DC.decide_one("Default", inc, now=T0, sources=Fake(GOLDEN + ROUTE4))
        assert (d["outcome"], d["guard"]["guard"]) == ("off", 2)

    def test_2_a_halt_in_force_until_a_person_lifts_it(self, lab):
        h = DS.halt("Default", guard=10, name="rate: per network", words="six heals",
                    operands={})
        assert one(GOLDEN + ROUTE4)["outcome"] == "halted"
        with pytest.raises(DS.Refused):
            DS.lift("Default", h["id"], by="op@example.com", actor_verified="none",
                    person=False, reason="x")
        with pytest.raises(DS.Refused):
            DS.lift("Default", h["id"], reason=" ", **PERSON_LIFT)
        DS.lift("Default", h["id"], reason="the rollout ended", **PERSON_LIFT)
        assert DS.halted("Default") == {}

    def test_3_planned_work_is_held_until_its_end_and_settle(self, lab, monkeypatch):
        from modules import restarts

        monkeypatch.setattr("modules.restarts.explained_by", lambda d, n, now: {
            "end": T0 + 300, "words": "edge-b is restarting as planned"})
        d = one(GOLDEN + ROUTE4)
        assert (d["outcome"], d["guard"]["guard"]) == ("held", 3)
        assert d["until"] == T0 + 300 + restarts.SETTLE_SECONDS

    def test_3_another_operation_holding_the_device(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.device_ops.holder",
                            lambda n, d: {"operation": "deploy", "actor": "op@example.com"})
        assert one(GOLDEN + ROUTE4)["guard"]["guard"] == 3

    def test_4_a_golden_that_departs_from_intent_n5(self, lab):
        d = one(GOLDEN + ROUTE4, src=Fake(GOLDEN + ROUTE4, state="departs"))
        assert (d["outcome"], d["guard"]["guard"], d["until"]) == ("held", 4, None)
        assert d["guard"]["operands"]["intent_match"] == "departs"

    @pytest.mark.parametrize("mark,words", [
        ({"_management": "observe", "_management_from": "the device's local config context"},
         "mercury.management to observe (the device's local config context)"),
        ({"role": "host"}, "mercury_kind is host")], ids=("observe", "host"))
    def test_4_an_observe_device_or_a_host_has_no_state_to_heal_to(self, lab, mark, words):
        """C2606, C2608: held under guard 4 before its golden is read, naming the mark; the
        device is never read."""
        class Marked(Fake):
            def device(self, device):
                return dict(super().device(device), **mark)
        src = Marked(GOLDEN + ROUTE4)
        d = one(GOLDEN + ROUTE4, src=src)
        assert (d["outcome"], d["guard"]["guard"]) == ("held", 4)
        assert words in d["words"] and src.reads == 0

    def test_5_the_topology_hold(self, lab):
        held = {"held": True, "until": iso(T0 + 600), "words": "held until then",
                "minutes": 60, "changes": []}
        d = one(GOLDEN + ROUTE4, src=Fake(GOLDEN + ROUTE4, held=held))
        assert (d["guard"]["guard"], d["until"]) == (5, T0 + 600)

    def test_6_many_devices_at_once(self, lab):
        for n in ("a-1", "a-2", "a-3", "a-4"):
            I.sight("Default", n, {"kind": "drift", "key": f"d:{n}", "epoch": T0 - 30},
                    now=T0 - 30)
        d = one(GOLDEN + ROUTE4)
        assert (d["guard"] or {}).get("guard") == 6, d["words"]
        assert d["guard"]["operands"]["devices"] == 4, d["words"]
        assert d["guard"]["operands"]["heal_max_devices_drifting"] == 3

    def test_7_a_person_working(self, lab):
        trig = [{"kind": "config_change", "key": f"cfg:{n}", "epoch": T0 - 60 * n,
                 "at": iso(T0 - 60 * n), "attribution": {"by": "outside"},
                 "person": {"words": "the line names the account alice"}, "words": "x"}
                for n in (1, 2, 3)]
        d = one(GOLDEN + ROUTE4, triggers=trig)
        assert (d["guard"] or {}).get("guard") == 7, d["words"]
        assert "a person appears to be working" in d["words"]
        assert d["until"] == T0 - 60 + 600

    def test_8_a_device_that_could_not_be_judged(self, lab):
        d = one(GOLDEN + ROUTE4, how="unreadable")
        assert (d["outcome"], d["guard"]["guard"]) == ("cant_fix", 8)

    def _heals(self, n, device="edge-b", outcome="heal", departure="x"):
        for _ in range(n):
            DS.record("Default", {"outcome": outcome, "device": device, "departure": departure},
                      T0 - 100)

    def test_9_the_rate_per_device(self, lab):
        auto("Default", now=T0 - 60)
        self._heals(1)
        assert (one(GOLDEN + ROUTE4)["guard"] or {}).get("guard") == 9

    def test_10_the_rate_per_network_halts_in_auto_only(self, lab):
        auto("Default", now=T0 - 60)
        for n in range(6):
            self._heals(1, device=f"o-{n}")
        inc = settle(GOLDEN + ROUTE4)
        d = DS.record("Default", DC.decide_one("Default", inc, now=T0,
                                               sources=Fake(GOLDEN + ROUTE4)), T0)
        assert (d["outcome"], d["guard"]["guard"]) == ("halted", 10)
        DC._act("Default", inc, d, T0)
        assert DS.halted("Default")["guard"] == 10

    def test_10_in_dry_run_records_and_halts_nothing(self, lab):
        for n in range(6):
            self._heals(1, device=f"o-{n}", outcome="would_heal")
        inc = settle(GOLDEN + ROUTE4)
        d = DS.record("Default", DC.decide_one("Default", inc, now=T0,
                                               sources=Fake(GOLDEN + ROUTE4)), T0)
        DC._act("Default", inc, d, T0)
        assert d["outcome"] == "halted" and DS.halted("Default") == {}

    def test_11_the_same_deviation_twice(self, lab):
        from modules.drift_check import departure, drift_diff

        dep = departure(drift_diff(GOLDEN, GOLDEN + ROUTE4, "edge-b"))
        DS.record("Default", {"outcome": "would_heal", "device": "edge-b", "departure": dep},
                  T0 - 7200)
        d = one(GOLDEN + ROUTE4)
        assert d["guard"]["guard"] == 11 and dep in d["words"]

    def test_12_more_than_one_removal_unit(self, lab):
        d = one(GOLDEN + ROUTE4 + ROUTE6)
        assert d["guard"], d["words"]
        assert (d["outcome"], d["guard"]["guard"]) == ("cant_fix", 12)

    def test_14_a_rolled_back_heal_halts(self, lab):
        auto("Default", now=T0 - 60)
        rec = DS.record("Default", {"outcome": "heal", "device": "edge-b"}, T0 - 7200)
        DS.applied("Default", rec["id"], "rolled_back", by="the apply",
                   words="an adjacency dropped", now=T0 - 7000)
        assert DS.halted("Default")["guard"] == 14

    def test_the_first_that_applies_is_named(self, lab, monkeypatch):
        """3 before 4: planned work and a departing golden, and 3 is named."""
        monkeypatch.setattr("modules.restarts.explained_by", lambda d, n, now: {
            "end": T0 + 60, "words": "restarting"})
        d = one(GOLDEN + ROUTE4, src=Fake(GOLDEN + ROUTE4, state="departs"))
        assert d["guard"]["guard"] == 3


PERSON_LIFT = {"by": "op@example.com", "actor_verified": "access", "person": True}


# ── The program, one computation ────────────────────────────────────────────────────────────

class TestTheProgram:
    def units(self, running):
        c = classify(running)
        return c["units"], c["removal_ids"]

    def test_the_same_read_gives_the_same_hash_and_a_moved_one_another(self):
        running = changed(("logging host 192.0.2.50\n", "")) + ROUTE4
        units, ids = self.units(changed(("logging host 192.0.2.50\n", "")))
        a = DC.program(GOLDEN, changed(("logging host 192.0.2.50\n", "")), units, ids,
                       mgmt_ip="192.0.2.6", platform=PLATFORM)
        b = DC.program(GOLDEN, changed(("logging host 192.0.2.50\n", "")), units, ids,
                       mgmt_ip="192.0.2.6", platform=PLATFORM)
        assert a["hash"] == b["hash"] and a["commands"] == ["logging host 192.0.2.50"]
        # The device moved after the decision: the line is back, so H4's program differs.
        moved = DC.program(GOLDEN, GOLDEN, units, ids, mgmt_ip="192.0.2.6", platform=PLATFORM)
        assert moved["commands"] == [] and moved["hash"] != a["hash"]
        assert running != GOLDEN

    def test_a_missing_stanza_is_sent_from_the_golden_whole(self):
        running = changed(("event manager applet HB\n event timer watchdog time 60\n"
                           " action 1 syslog msg heartbeat\n", ""))
        units, ids = self.units(running)
        got = DC.program(GOLDEN, running, units, ids, mgmt_ip="192.0.2.6", platform=PLATFORM)
        assert got["commands"][:3] == ["event manager applet HB",
                                       " event timer watchdog time 60",
                                       " action 1 syslog msg heartbeat"]

    def test_an_intent_edit_is_never_in_the_program(self):
        running = changed(("logging host 192.0.2.50\n", ""))
        c = K.classify(GOLDEN, running, GOLDEN + "ntp server 192.0.2.51\n", platform=PLATFORM,
                       mgmt_ip="192.0.2.6")
        got = DC.program(GOLDEN, running, c["units"], c["removal_ids"], mgmt_ip="192.0.2.6",
                         platform=PLATFORM)
        assert not any("ntp" in x for x in got["commands"])


# ── The record and the seams ────────────────────────────────────────────────────────────────

class TestTheRecordAndTheSeams:
    def run(self, running, src=None):
        settle(running, claim=False)
        return DC.run("Default", now=T0, sources=src or Fake(running))

    def test_a_decision_is_recorded_and_its_incident_closed(self, lab):
        got = self.run(GOLDEN + ROUTE4)
        (d,) = got["decided"]
        assert d["outcome"] == "would_heal"
        (inc,) = I.read("Default")["incidents"]
        assert inc["state"] == "closed" and d["decision"] in inc["closed_why"]

    def test_a_heal_stays_claimed_for_h4_who_takes_it_once(self, lab):
        auto("Default", now=T0 - 60)
        self.run(GOLDEN + ROUTE4)
        (d,) = DS.to_apply("Default")
        assert I.read("Default")["incidents"][0]["state"] == "claimed"
        DS.take("Default", d["id"], by="the apply")
        with pytest.raises(DS.Refused):
            DS.take("Default", d["id"], by="the apply")
        assert DS.to_apply("Default") == []

    def test_a_proposal_is_h5s(self, lab):
        self.run(changed((" router-id 192.0.2.6\n", " router-id 192.0.2.99\n")))
        assert [d["kind"] for d in DS.proposals("Default")] == ["process_reset"]

    def test_held_with_a_time_sends_the_incident_back_to_watching(self, lab, monkeypatch):
        monkeypatch.setattr("modules.restarts.explained_by", lambda d, n, now: {
            "end": T0 + 60, "words": "restarting"})
        self.run(GOLDEN + ROUTE4)
        (inc,) = I.read("Default")["incidents"]
        assert inc["state"] == "watching" and inc["defer_until"] > T0

    def test_a_deferred_incident_is_not_read_before_its_time_and_restarts_after(self, lab,
                                                                                 monkeypatch):
        from modules.heal import detect

        monkeypatch.setattr("modules.restarts.explained_by", lambda d, n, now: {
            "end": T0 + 60, "words": "restarting"})
        self.run(GOLDEN + ROUTE4)
        (inc,) = I.read("Default")["incidents"]
        reads = []

        def check(network, device, by):
            reads.append(device)
            return {"state": "drifted", "departure": "d1", "changed_lines": 1,
                    "read_at": None, "skipped": False}

        early = detect.run("Default", now=inc["defer_until"] - 1, check=check,
                           clock=lambda: inc["defer_until"] - 1)
        assert reads == [] and early["waiting"][0]["state"] == "deferred"
        later = detect.run("Default", now=inc["defer_until"] + 1, check=check,
                           clock=lambda: inc["defer_until"] + 1)
        assert reads == ["edge-b"] and later["waiting"][0]["state"] == "waiting", \
            "its grace period restarts at the deferral's end: one read is not enough"

    def test_a_decision_that_fails_defers_its_incident(self, lab):
        class Broken(Fake):
            def golden(self, device, dev):
                raise RuntimeError("the repository is locked")

        got = self.run(GOLDEN + ROUTE4, src=Broken(GOLDEN + ROUTE4))
        assert "locked" in got["failed"][0]
        assert I.read("Default")["incidents"][0]["state"] == "watching"

    def test_a_pass_in_progress_refuses_a_second(self, lab):
        settle(GOLDEN + ROUTE4, claim=False)
        with I.HealLock("Default", actor="Mercury", trigger="a pass elsewhere"):
            got = DC.run("Default", now=T0, sources=Fake(GOLDEN + ROUTE4))
        assert "a pass elsewhere" in got["busy"]

    def test_no_secret_reaches_the_record(self, lab):
        running = changed((" ip ospf cost 10\n", " ip ospf cost 10\n ip ospf authentication "
                           "message-digest\n ip ospf message-digest-key 1 md5 S3cretKey\n"))
        self.run(running)
        with open(DS.path("Default"), encoding="utf-8") as fh:
            assert "S3cretKey" not in fh.read()


class TestRightOrWrong:
    def test_marked_by_a_verified_person_and_counted_per_kind(self, lab):
        a = DS.record("Default", {"outcome": "would_heal", "kind": "added_line"}, T0)
        b = DS.record("Default", {"outcome": "would_heal", "kind": "added_line"}, T0)
        DS.record("Default", {"outcome": "would_heal", "kind": "missing_line"}, T0)
        with pytest.raises(DS.Refused):
            DS.mark("Default", a["id"], True, by="svc", actor_verified="none", person=False)
        with pytest.raises(DS.Refused):
            DS.mark("Default", a["id"], False, **PERSON)
        DS.mark("Default", a["id"], True, **PERSON)
        DS.mark("Default", b["id"], False, why="the route was a planned change", **PERSON)
        got = DS.dry_run_counts("Default")
        assert got["added_line"] == {"records": 2, "right": 1, "wrong": 1, "unmarked": 0,
                                     "false_positive": 0.5}
        assert got["missing_line"]["false_positive"] is None

    def test_only_a_dry_run_record_is_marked(self, lab):
        h = DS.record("Default", {"outcome": "heal"}, T0)
        with pytest.raises(DS.Refused):
            DS.mark("Default", h["id"], True, **PERSON)


# ── The drift row carries the dry-run record ────────────────────────────────────────────────

class TestTheDriftRow:
    def rows(self, monkeypatch, now=T0):
        from modules import attention as A

        monkeypatch.setattr(A, "_page_network", lambda: "Default")
        return A.heal_source(now=now)["rows"]

    def test_a_dry_run_record_attaches_to_the_devices_drift_row(self, lab, monkeypatch):
        from modules import attention as A

        d = DS.record("Default", {"outcome": "would_heal", "device": "edge-b", "kind":
                                  "added_line", "words": "would heal", "program_hash": "abc",
                                  "units": [{"words": "an added line (Tier 1)"}]}, T0)
        (r,) = self.rows(monkeypatch)
        assert r["attach_to"] == "drift:Default:drifted:edge-b" and r["attach_action"] is False
        assert "dry run on Default" in r["what"] and r["operands"]["decision"] == d["id"]
        drift = A.row(source="drift", kind="drifted", key="Default:drifted:edge-b",
                      what="edge-b differs", cause="c", action={"label": "Capture or revert"},
                      level="warning")
        (kept,) = A._attach([drift, r])
        assert kept["action"]["label"] == "Capture or revert", "the drift row keeps its action"
        assert kept["attached"][0]["kind"] == "would_heal"

    def test_marked_or_old_it_goes(self, lab, monkeypatch):
        d = DS.record("Default", {"outcome": "would_heal", "device": "edge-b"}, T0)
        assert self.rows(monkeypatch, now=T0 + DS.MARK_DAYS * 86400 + 1) == []
        DS.mark("Default", d["id"], True, **PERSON)
        assert self.rows(monkeypatch) == []

    def test_an_unreadable_record_is_its_own_row(self, lab, monkeypatch):
        from modules import attention as A

        DS.record("Default", {"outcome": "would_heal", "device": "edge-b"}, T0)
        with open(DS.path("Default"), "a", encoding="utf-8") as fh:
            fh.write("{torn\n")
        monkeypatch.setattr(A, "_page_network", lambda: "Default")
        got = A.heal_source(now=T0)
        assert got["state"] == "unreadable" and "could not be read" in got["rows"][0]["cause"]


class TestNothingSends:
    def test_no_h3_module_sends_to_a_device(self):
        """H3 decides and records; H4 applies. Only the decision's read reaches a device."""
        import ast
        import inspect

        from modules.heal import decide, decisions, guards, kinds

        sent = {"send_config_set", "send_command", "apply_batch", "run_device_command",
                "PipelineRunner", "open_ssh", "ConnectHandler", "_deploy_one"}
        for mod in (decide, decisions, guards, kinds):
            names = {n.attr if isinstance(n, ast.Attribute) else n.id
                     for n in ast.walk(ast.parse(inspect.getsource(mod)))
                     if isinstance(n, (ast.Attribute, ast.Name))}
            assert not names & sent, (mod.__name__, names & sent)
