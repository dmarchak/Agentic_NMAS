"""Self-healing's security tiers and dependents (C2839 and C2822, the operator, 2026-11-08 and
2026-11-09; docs/HEAL_TO_INTENT.md section 5 and N13), and the fold window against Grafana's
alert rules (the operator, 2026-11-08), no network, no device, a fake clock.

- **The platform pack** (`modules/nsot/platform_heal.json`): both dialects declare every class
  and every reference object, IOS-XE by ``same_as``; a planted line of each class is found; a
  platform with none declared fails closed (every removal a person's).
- **C2839:** a security control removed or changed outside intent is `security_control`, Tier
  2, always proposed (whatever the policy's propose list); any ACL is `security_acl`, Tier 2
  (was 4); a missing control added back stays Tier 1; accounts and the management path stay
  Tier 4; the proposal's card offers Remove it (back to intent) and Keep it: add it to intent;
  the per-network question defaults to no, and yes makes a one-sided change that broke an
  adjacency `security_revert`, Tier 1, only on an incident with an adjacency down and no other
  device. W6's case: OSPF authentication and its key added on one end of a link.
- **C2822:** a definition only one added unit uses is one unit with it (W7's ACL and its
  `ip access-group` on Gi2, and its IPv6 twin), transitively; a definition an unchanged line or
  two units use stays its own; missing dependents are re-applied together.
- **The fold window:** a rule past it, a rule unread, and none, each its own state; the reader
  stores each rule's group interval; the row names each rule, both numbers and the window.
"""
import copy
import json

import pytest

from tests.test_heal_decide import (GI2, GOLDEN, PLATFORM, Fake, changed, classify, lab,  # noqa: F401
                                    one, settle)
from tests.test_heal_policy import T0, confirm, iso
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture, named by `lab`)
from tests.test_heal_triggers import _Lazy

K, DC = _Lazy("kinds"), _Lazy("decide")

#: W6 (H11, 2026-11-08): OSPF authentication and its key added outside intent on one end.
W6_LINES = (" ip ospf authentication message-digest\n ip ospf message-digest-key 1 md5 "
            "S3cretKey\n")
W6 = changed((" ip ospf cost 10\n", " ip ospf cost 10\n" + W6_LINES))
#: W7 (H11, 2026-11-08): an inbound ACL with no OSPF permit, applied on Gi2.
W7_ACL = "ip access-list extended EDGE-IN\n 10 permit tcp any any\n 20 permit udp any any\n"
W7 = changed((GI2, GI2 + " ip access-group EDGE-IN in\n")) + W7_ACL
W7_V6_ACL = "ipv6 access-list EDGE6-IN\n permit tcp any any\n"
W7_V6 = changed((GI2, GI2 + " ipv6 traffic-filter EDGE6-IN in\n")) + W7_V6_ACL
ADJ = {"kind": "adjacency_log", "key": "adjlog:1", "epoch": T0 - 1000, "at": iso(T0 - 1000),
       "protocol": "OSPF", "words": "edge-b logged its OSPF adjacency to 192.0.2.10 down"}
CONFIG = {"kind": "config_change", "key": "cfg:1", "epoch": T0 - 1000, "at": iso(T0 - 1000),
          "attribution": {"by": "outside"}, "words": "CONFIG_I"}


@pytest.fixture(autouse=True)
def no_host_addresses(monkeypatch):
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])


def measured(monkeypatch, *keys):
    """The real removal record, with *keys* measured exact on the test's platform."""
    from modules.nsot import removal as RM

    real = RM.measured()
    rows = copy.deepcopy(real["by_dialect"])
    for k in keys:
        rows.setdefault(PLATFORM, {})[k] = {"result": "exact", "device": "probe",
                                            "at": "2026-11-09T00:00:00Z", "detail": ""}
    monkeypatch.setattr(RM, "measured", lambda: dict(real, by_dialect=rows))


W7_SHAPES = ("interface.ip-access-group", "interface.ipv6-traffic-filter", "global.named-acl")


# ── The platform pack ───────────────────────────────────────────────────────────────────────

CLASSES = ("routing_auth", "acl", "aaa", "crypto_ssh", "snmp_restriction", "copp",
           "port_security", "transport_input")
OBJECTS = ("acl", "ipv6-acl", "object-group", "prefix-list", "ipv6-prefix-list",
           "community-list", "as-path", "class-map", "policy-map", "key-chain", "track", "ip-sla")


class TestThePack:
    @pytest.mark.parametrize("dialect", ["cisco_ios", "cisco_iosxe"])
    def test_each_dialect_declares_every_class_and_object(self, dialect):
        p = K.pack(dialect)
        assert tuple(p["security"]) == CLASSES
        assert tuple(r["object"] for r in p["references"]) == OBJECTS

    def test_the_file_is_one_json_document_naming_its_sources(self):
        with open(K.PACK, encoding="utf-8") as fh:
            doc = json.load(fh)
        assert doc["what"] and doc["how"] and doc["dialects"]["cisco_iosxe"] == {
            "same_as": "cisco_ios"}

    @pytest.mark.parametrize("chain,line,cls", [
        (("interface GigabitEthernet4",), " ip ospf authentication message-digest", "routing_auth"),
        (("interface GigabitEthernet4",), " ipv6 ospf authentication ipsec spi 256 md5 0 K",
         "routing_auth"),
        (("interface GigabitEthernet4",), " ospfv3 1 authentication key-chain K", "routing_auth"),
        (("router bgp 65001",), " neighbor 2001:db8::2 password 7 K", "routing_auth"),
        (("router bgp 65001",), " neighbor 192.0.2.10 password 7 K", "routing_auth"),
        (("router ospf 1",), " area 0 authentication message-digest", "routing_auth"),
        (("interface GigabitEthernet2",), " ip access-group EDGE in", "acl"),
        (("interface GigabitEthernet2",), " ipv6 traffic-filter EDGE6 in", "acl"),
        ((), "ntp access-group peer 10", "acl"),
        ((), "aaa authentication login default local", "aaa"),
        (("line con 0",), " login authentication CON", "aaa"),
        ((), "ip ssh version 2", "crypto_ssh"),
        ((), "snmp-server view RESTRICT iso included", "snmp_restriction"),
        (("control-plane",), " service-policy input COPP", "copp"),
        (("interface GigabitEthernet0/1",), " switchport port-security maximum 2",
         "port_security"),
        (("interface GigabitEthernet0/1",), " authentication port-control auto",
         "port_security"),
        (("line con 0",), " transport input none", "transport_input")])
    def test_a_planted_line_of_each_class_is_found(self, chain, line, cls):
        u = {"add": [], "remove": [(chain, line)]}
        assert K.security_class(PLATFORM, u)[0] == cls

    def test_an_ordinary_line_is_in_no_class(self):
        u = {"add": [], "remove": [(("interface GigabitEthernet2",), " ip ospf cost 20")]}
        assert K.security_class(PLATFORM, u) == ("", "")

    def test_a_platform_with_none_declared_fails_closed(self):
        u = {"op": "remove", "chain": [], "add": [],
             "remove": [((), "ip route 192.0.2.128 255.255.255.128 192.0.2.10")]}
        cls, why = K.security_class("junos", u)
        assert cls == K.UNDECLARED and "junos" in why and "a person's" in why
        assert K.kind_of(u, mgmt_ifaces=set(), mgmt_routes={}, related=False,
                         platform="junos")[0] == "security_control"


# ── C2839: the security tiers ───────────────────────────────────────────────────────────────

class TestTheSecurityTiers:
    def test_w6_routing_authentication_added_is_a_tier_2_security_control(self):
        (u,) = classify(W6)["units"]
        assert (u["op"], u["kind"], u["tier"]) == ("remove", "security_control", 2)
        assert "C2839" in u["why"] and u["blocked"] == "", "both lines are measured shapes"

    @pytest.mark.parametrize("added", [
        changed((GI2, GI2 + " ipv6 ospf authentication ipsec spi 256 md5 0 K\n")),
        GOLDEN.replace("logging host 192.0.2.50\n",
                       "logging host 192.0.2.50\nline con 0\n transport input none\n"),
        GOLDEN + "control-plane\n service-policy input COPP\n",
        GOLDEN + "snmp-server view RESTRICT iso included\n"])
    def test_each_class_removed_is_tier_2(self, added):
        got = classify(added)
        assert {u["kind"] for u in got["units"]} == {"security_control"}, got["units"]
        assert got["tier"] == 2

    def test_a_missing_control_added_back_stays_tier_1(self):
        golden = W6.replace(" ip ospf message-digest-key 1 md5 S3cretKey\n", "")
        got = classify(changed((" ip ospf authentication message-digest\n", ""), base=golden),
                       golden=golden, intended=golden)
        (u,) = got["units"]
        assert (u["op"], u["kind"], u["tier"]) == ("add", "missing_line", 1)

    def test_a_routing_key_added_back_stays_a_secret_added_back(self):
        got = classify(GOLDEN, golden=W6, intended=W6)
        assert (got["kind"], got["tier"]) == ("secret_added_back", 2)

    @pytest.mark.parametrize("added,kind", [
        ("aaa new-model\n", "credentials"),
        ("username audit privilege 15 secret 9 $9$abc\n", "credentials"),
        ("key chain OSPF\n key 1\n  key-string 7 K\n", "credentials")])
    def test_tier_4_stays_where_it_was(self, added, kind):
        assert (classify(GOLDEN + added)["kind"], classify(GOLDEN + added)["tier"]) == (kind, 4)

    def test_transport_input_on_vty_is_still_the_management_path(self):
        got = classify(GOLDEN + "line vty 0 4\n transport input telnet ssh\n")
        assert (got["kind"], got["tier"]) == ("management_path", 4)

    def test_w6_is_proposed_whatever_the_propose_list_says(self, lab):
        confirm("Default", heal_mode="dry_run", heal_kinds_propose=[])
        d = one(W6, triggers=[CONFIG, ADJ])
        assert (d["outcome"], d["kind"], d["tier"]) == ("propose", "security_control", 2), d
        assert d["program"] == ["interface GigabitEthernet4",
                                " no ip ospf authentication message-digest",
                                " no ip ospf message-digest-key 1 md5 <redacted:ospf_key>",
                                "exit"], d["program"]
        assert "S3cretKey" not in json.dumps(d)

    def test_the_card_offers_remove_it_and_keep_it(self, lab):
        from modules.heal import decisions, propose
        d = decisions.record("Default", one(W6), T0)
        got = propose.security_choice(d)
        assert got["lines"] and "S3cretKey" not in json.dumps(got)
        assert got["remove_words"].startswith("Remove it (back to intent)")
        assert got["keep_words"].startswith("Keep it: add it to intent")
        assert propose.security_choice({"units": [{"kind": "process_reset"}]}) is None

    def test_its_approval_is_never_refused_as_a_kind_no_longer_proposed(self, lab):
        from modules.heal import decisions, propose
        confirm("Default", heal_mode="dry_run", heal_kinds_propose=[])
        d = decisions.record("Default", one(W6), T0)

        class Src(Fake):
            def mode(self, now):
                from modules.heal import policy
                return policy.current("Default", now)

            def planned(self, device, now):
                return None

        v = propose.view("Default", d["id"], now=T0, sources=Src(W6))
        assert v["refusals"] == [] and v["confirmable"], v["refusals"]
        assert v["security"]["lines"]

    def test_the_proposal_row_names_both_answers(self, lab):
        from modules import attention
        from modules.heal import decisions
        d = decisions.record("Default", one(W6), T0)
        (r,) = attention._heal_proposal_rows("Default", [d])
        assert "remove it (back to intent)" in r["action"]["label"]
        assert "keep it: add it to intent" in r["action"]["label"]


class TestThePerNetworkQuestion:
    def test_it_defaults_to_no_and_a_confirmed_policy_keeps_its_fingerprint(self):
        from modules.heal import policy as H
        from modules.settings_schema import DEFAULTS
        assert DEFAULTS[H.SECURITY_REVERT_KEY] is False
        before = {k: DEFAULTS[k] for k in H.POLICY_KEYS if k not in H.LATER_KEYS}
        assert H.policy_fingerprint(before) == H.policy_fingerprint(
            dict(before, **{H.SECURITY_REVERT_KEY: False}))
        assert H.policy_fingerprint(before) != H.policy_fingerprint(
            dict(before, **{H.SECURITY_REVERT_KEY: True}))

    def test_yes_makes_w6_with_an_adjacency_down_a_tier_1_revert(self, lab):
        confirm("Default", heal_mode="dry_run", heal_security_revert_adjacency=True)
        d = one(W6, triggers=[CONFIG, ADJ])
        assert (d["outcome"], d["kind"], d["tier"]) == ("would_heal", "security_revert", 1), d

    def test_yes_without_an_adjacency_down_is_still_a_proposal(self, lab):
        confirm("Default", heal_mode="dry_run", heal_security_revert_adjacency=True)
        d = one(W6, triggers=[CONFIG])
        assert (d["outcome"], d["kind"]) == ("propose", "security_control"), d

    def test_yes_on_a_change_spanning_devices_is_multi_device(self, lab):
        confirm("Default", heal_mode="dry_run", heal_security_revert_adjacency=True)
        d = one(W6, triggers=[CONFIG, ADJ], related=["edge-c"])
        assert (d["outcome"], d["kind"]) == ("cant_fix", "multi_device"), d

    def test_no_keeps_it_a_proposal_with_an_adjacency_down(self, lab):
        d = one(W6, triggers=[CONFIG, ADJ])
        assert (d["outcome"], d["kind"]) == ("propose", "security_control"), d

    def test_auto_heals_the_revert_only_where_the_kind_is_named(self, lab):
        confirm("Default", heal_mode="auto", heal_mode_until=iso(T0 + 3600),
                heal_kinds_auto=["added_line"], heal_security_revert_adjacency=True, now=T0 - 60)
        d = one(W6, triggers=[CONFIG, ADJ])
        assert d["outcome"] == "would_heal" and "security_revert" in d["words"], d
        confirm("Default", heal_mode="auto", heal_mode_until=iso(T0 + 3600),
                heal_kinds_auto=["added_line", "security_revert"],
                heal_security_revert_adjacency=True, now=T0 - 60)
        d = one(W6, triggers=[CONFIG, ADJ], device="edge-c")
        assert d["outcome"] == "heal", d


# ── C2822: dependents are one unit ──────────────────────────────────────────────────────────

class TestDependents:
    def test_w7_the_acl_and_its_access_group_are_one_unit(self):
        got = classify(W7)
        (u,) = got["units"]
        assert (u["op"], u["kind"], u["tier"]) == ("remove", "security_acl", 2)
        assert len(u["parts"]) == 2 and u["chain"] == ["interface GigabitEthernet2"]
        assert u["heads"] == [(("interface GigabitEthernet2",), " ip access-group EDGE-IN in"),
                              ((), "ip access-list extended EDGE-IN")]
        assert "1 definition(s) only it references" in K.unit_words(u)

    def test_w7_v6_the_acl_and_its_traffic_filter_are_one_unit(self):
        (u,) = classify(W7_V6)["units"]
        assert (u["kind"], len(u["parts"])) == ("security_acl", 2)

    def test_w7_unmeasured_is_blocked_naming_the_probe_and_the_shape(self, lab):
        d = one(W7)
        assert d["outcome"] == "cant_fix", d
        assert "interface.ip-access-group" in d["words"] and "nmas-removal-probe" in d["words"]

    @pytest.mark.parametrize("running,program", [
        (W7, [" no ip access-group EDGE-IN in", "no ip access-list extended EDGE-IN"]),
        (W7_V6, [" no ipv6 traffic-filter EDGE6-IN in", "no ipv6 access-list EDGE6-IN"])])
    def test_w7_measured_is_one_tier_2_proposal_removing_both(self, lab, monkeypatch, running,
                                                              program):
        measured(monkeypatch, *W7_SHAPES)
        d = one(running)
        assert (d["outcome"], d["kind"], d["tier"]) == ("propose", "security_acl", 2), d
        assert d["guard"] is None, "guard 12 counts one unit"
        # The use removed first, then the ACL it alone used.
        assert d["program"] == ["interface GigabitEthernet2", program[0], "exit", program[1]]

    def test_mode_b_still_refuses_a_definition_before_its_use(self, monkeypatch):
        """Mode B's own rule, kept: a definition still used when it is sent is refused; only a
        use the same program removes FIRST stops counting (`removal._references`)."""
        from modules.nsot import removal as RM
        measured(monkeypatch, *W7_SHAPES)
        use = {"chain": ["interface GigabitEthernet2"], "line": " ip access-group EDGE-IN in"}
        acl = {"chain": [], "line": "ip access-list extended EDGE-IN"}
        ok = RM.removal_program(W7, [use, acl], mgmt_ip="192.0.2.6", dialect=PLATFORM)
        assert ok["refused"] == [] and len(ok["removed"]) == 2
        bad = RM.removal_program(W7, [acl, use], mgmt_ip="192.0.2.6", dialect=PLATFORM)
        assert [r["line"] for r in bad["refused"]] == [acl["line"]]
        assert "still used by" in bad["refused"][0]["reason"]

    def test_a_definition_an_unchanged_line_uses_stays_its_own_unit(self):
        """Gi2's access-group is in the golden and intent (unchanged); Gi4's is added with the
        ACL: the ACL stays its own unit, never joined to Gi4's."""
        golden = changed((GI2, GI2 + " ip access-group EDGE-IN in\n"))
        intended = golden
        running = changed((" description to core\n",
                           " description to core\n ip access-group EDGE-IN in\n"),
                          base=golden) + W7_ACL
        got = classify(running, golden=golden, intended=intended)
        assert len(got["units"]) == 2, got["units"]
        assert not any(u.get("parts") for u in got["units"])

    def test_a_definition_two_units_use_stays_its_own_unit(self):
        running = changed((GI2, GI2 + " ip access-group EDGE-IN in\n"),
                          (" description to core\n",
                           " description to core\n ip access-group EDGE-IN in\n")) + W7_ACL
        got = classify(running)
        assert len(got["units"]) == 3 and not any(u.get("parts") for u in got["units"])

    def test_class_map_policy_map_and_service_policy_are_a_chain_of_three(self):
        running = changed((GI2, GI2 + " service-policy output SHAPE\n")) + (
            "class-map match-any VOICE\n match dscp ef\n"
            "policy-map SHAPE\n class VOICE\n  priority percent 10\n")
        (u,) = classify(running)["units"]
        assert (len(u["parts"]), u["kind"]) == (3, "qos_policy")

    def test_an_object_group_its_acl_and_its_application_are_one_unit(self):
        running = changed((GI2, GI2 + " ip access-group EDGE-IN in\n")) + (
            "object-group network SRC\n host 192.0.2.99\n"
            "ip access-list extended EDGE-IN\n 10 permit ip object-group SRC any\n")
        (u,) = classify(running)["units"]
        assert (len(u["parts"]), u["kind"]) == (3, "security_acl")

    def test_a_track_and_its_static_route_ipv4_and_ipv6(self):
        for route in ("ip route 192.0.2.128 255.255.255.128 192.0.2.10 track 5\n",
                      "ipv6 route 2001:db8:9::/48 2001:db8:0:7::2 track 5\n"):
            (u,) = classify(GOLDEN + "track 5 interface GigabitEthernet4 line-protocol\n"
                            + route)["units"]
            assert (len(u["parts"]), u["kind"]) == (2, "added_line"), u

    def test_an_ip_sla_its_schedule_and_its_track_are_one_unit(self):
        running = GOLDEN + ("ip sla 7\n icmp-echo 192.0.2.10\n"
                            "ip sla schedule 7 life forever start-time now\n"
                            "track 9 ip sla 7 reachability\n")
        (u,) = classify(running)["units"]
        assert len(u["parts"]) == 3, u

    def test_a_prefix_list_and_its_neighbor_use(self):
        golden = GOLDEN + "router bgp 65001\n neighbor 192.0.2.10 remote-as 65002\n"
        running = golden.replace(" neighbor 192.0.2.10 remote-as 65002\n",
                                 " neighbor 192.0.2.10 remote-as 65002\n"
                                 " neighbor 192.0.2.10 prefix-list IN in\n") + \
            "ip prefix-list IN seq 5 permit 192.0.2.0/24\n"
        got = classify(running, golden=golden, intended=golden)
        (u,) = got["units"]
        assert len(u["parts"]) == 2, got["units"]

    def test_a_key_chain_and_its_use_are_one_unit_and_stay_tier_4(self):
        running = changed((GI2, GI2 + " ip ospf authentication key-chain OSPFK\n")) + (
            "key chain OSPFK\n key 1\n  key-string 7 K\n")
        (u,) = classify(running)["units"]
        assert (len(u["parts"]), u["kind"], u["tier"]) == (2, "credentials", 4)

    def test_a_missing_acl_and_its_application_are_re_applied_together(self, lab):
        src = Fake(GOLDEN, golden=W7, intended=W7)
        inc = settle(GOLDEN, golden=W7, device="edge-c")
        d = DC.decide_one("Default", inc, now=T0, sources=src)
        assert (d["outcome"], d["kind"]) == ("propose", "security_acl"), d
        assert len(d["units"]) == 1 and d["units"][0]["joined"] == 2
        assert "ip access-list extended EDGE-IN" in d["program"]
        assert " ip access-group EDGE-IN in" in d["program"]


# ── The fold window ─────────────────────────────────────────────────────────────────────────

def rules(*pairs, configured=True):
    return {"rules": [{"uid": f"u{n}", "title": f"rule {n}", "group": "g", "for_seconds": f,
                       "interval_seconds": i, "configured": configured}
                      for n, (f, i) in enumerate(pairs)]}


class TestTheFoldWindow:
    def test_within_the_window_is_ok(self):
        assert FW().check(rules((60, 60), (0, 60), (190, 60)))["state"] == "ok"

    def test_past_the_window_names_each_rule_and_both_numbers(self):
        got = FW().check(rules((300, 60), (60, 60)))
        assert got["state"] == "past" and [i["title"] for i in got["past"]] == ["rule 0"]
        words = FW().words(got["past"][0], got["window"])
        assert "300 s" in words and "60 s" in words and "360 s" in words and "250 s" in words

    def test_a_rule_without_its_numbers_is_unread_never_fine(self):
        assert FW().check(rules((60, 0)))["state"] == "unread"
        assert FW().check(rules((60, 60), configured=False))["state"] == "unread"
        old = {"rules": [{"uid": "u", "title": "t", "for_seconds": 60}]}
        assert FW().check(old)["state"] == "unread", "a read stored before the interval was kept"

    def test_the_window_is_the_fold_window(self):
        from modules.heal.incidents import FOLD_STANDING_S
        assert FW().check(rules((int(FOLD_STANDING_S) - 60, 60)))["state"] == "ok"
        assert FW().check(rules((int(FOLD_STANDING_S) - 59, 60)))["state"] == "past"

    def test_the_reader_stores_each_rules_group_interval(self):
        from tests.test_grafana_reader import parse
        got = parse()["rules"]
        assert got and all(isinstance(r["interval_seconds"], int) and r["interval_seconds"] > 0
                           for r in got)

    def test_the_captured_rules_past_the_window_are_found(self):
        """The 2026-09-28 capture (tests/fixtures/grafana): two 1-minute interface rules pend
        for 300 s in a 60 s group, 360 s, past the window."""
        from tests.test_grafana_reader import parse
        got = FW().check(parse())
        assert sorted((i["title"], i["group"], i["total"]) for i in got["past"]) == [
            ("Interface error rate elevated", "1m", 360),
            ("Interface output discards", "1m", 360)]

    def test_the_row_while_healing_is_on_and_none_while_off(self):
        from modules import attention
        cached = {"state": "ok", "doc": {"last_good": {"value": rules((300, 60))}}}
        said = []
        (r,) = attention._heal_fold_rows("Default", said, cached=cached,
                                         mode={"mode": "dry_run"})
        assert (r["source"], r["kind"], r["level"]) == ("heal", "fold_window", "warning")
        assert "rule 0" in r["cause"] and "360 s" in r["cause"] and "250 s" in r["what"]
        assert r["operands"]["rules"] == [{"title": "rule 0", "for_s": 300, "interval_s": 60}]
        assert attention._heal_fold_rows("Default", said, cached=cached,
                                         mode={"mode": "off"}) == []
        assert "self-healing is off" in said[-1]

    def test_an_unread_cache_is_said_and_an_unread_rule_is_a_row(self):
        from modules import attention
        said = []
        assert attention._heal_fold_rows("Default", said, cached={"state": "absent",
                                                                  "why": "never run"},
                                         mode={"mode": "dry_run"}) == []
        assert "not read" in said[-1]
        cached = {"state": "ok", "doc": {"last_good": {"value": rules((60, 0))}}}
        (r,) = attention._heal_fold_rows("Default", said, cached=cached,
                                         mode={"mode": "auto"})
        assert "is not read" in r["what"] and "never read as fine" in r["cause"]


def FW():
    from modules.heal import fold_window
    return fold_window
