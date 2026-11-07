"""The diagnosis runbooks' parsers on H18's real captures (board H amendment item 1, part H18;
docs/HEAL_TO_INTENT.md 19.3; C2414, C2415, C2681; modules/heal/diagnose_parse.py and
`path_trace.parse_cef`'s IPv6 form).

Every answer here is a real one, captured read-only on 2026-11-07 through Mercury's reads
engine from r2 and r4 (IOS-XE) and s1 (IOS), masked (tests/fixtures/diagnose/README.md names
each one's device, command and UTC time). Each parser is held to the facts its capture prints,
and to the two states that must never be read as a fact: the device's "no such read" marker,
and an answer that is not the read's (unreadable, never "nothing there").
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAG = os.path.join(ROOT, "tests", "fixtures", "diagnose")


def diag(name: str) -> str:
    with open(os.path.join(DIAG, name), encoding="utf-8") as fh:
        return fh.read()


def parse(kind, name, interface="", dialect=""):
    from modules.heal.diagnose_parse import parse as p
    return p(kind, diag(name), interface, dialect)


def facts(kind, name, interface="", dialect=""):
    got = parse(kind, name, interface, dialect)
    assert got["state"] == "parsed", got
    return got["facts"]


class TestThePing:
    @pytest.mark.parametrize("name,expected", [
        ("r2__ping_10.255.1.14_source_Loopback0_repeat_5_timeout_2.txt",
         (5, 5, 100, "!!!!!", "10.255.1.12", True, True)),
        ("r2__ping_ipv6_2001_DB8_1_14_source_Loopback0_repeat_5_timeout_2.txt",
         (5, 5, 100, "!!!!!", "2001:db8:1::12", True, True)),
        ("r2__ping_10.255.3.99_repeat_5_timeout_2.txt", (5, 0, 0, ".....", "", False, False)),
        ("r2__ping_ipv6_2001_DB8_1_21_source_Loopback0_repeat_5_timeout_2.txt",
         (5, 0, 0, "XXXXX", "2001:db8:1::12", False, False)),
        ("r2__ping_ipv6_2001_DB8_3_99_repeat_5_timeout_2.txt",
         (5, 0, 0, ".H..H", "", False, False)),
        ("s1__ping_ipv6_2001_DB8_1_14_source_Loopback0_repeat_5_timeout_2.txt",
         (5, 0, 0, ".....", "2001:db8:1::21", False, False)),
        ("r2__ping_10.255.3.14_size_1500_df_bit_repeat_2_timeout_2.txt",
         (2, 2, 100, "!!", "", True, True))])
    def test_each_ping_s_probes(self, name, expected):
        f = facts("reach_ping", name)
        assert (f["sent"], f["received"], f["percent"], f["marks"], f["source"], f["reached"],
                f["all"]) == expected

    def test_an_answer_with_no_summary_is_unreadable_never_no_reply(self):
        from modules.heal.diagnose_parse import parse as p
        text = diag("r2__ping_10.255.3.99_repeat_5_timeout_2.txt")
        cut = text.split("Success rate")[0]                    # the answer cut before its end
        assert p("reach_ping", cut)["state"] == "unreadable"
        assert p("reach_ping", "")["state"] == "unreadable"


class TestTheRoute:
    @pytest.mark.parametrize("name,expected", [
        ("r2__show_ip_route_10.255.1.14.txt",
         ("10.255.1.14/32", "ospf 1", "ospf", "1", "intra area",
          [("10.255.3.14", "GigabitEthernet2")])),
        ("r2__show_ip_route_10.255.1.21.txt",
         ("10.255.1.21/32", "ospf 1", "ospf", "1", "extern 2",
          [("10.255.3.11", "GigabitEthernet2")])),
        ("r2__show_ip_route_10.255.3.14.txt",
         ("10.255.3.0/24", "connected", "connected", "", "", [("", "GigabitEthernet2")])),
        ("r2__show_ip_route_0.0.0.0.txt",
         ("0.0.0.0/0", "ospf 1", "ospf", "1", "",
          [("10.255.3.14", "GigabitEthernet2"), ("10.255.3.13", "GigabitEthernet2")])),
        ("s1__show_ip_route_0.0.0.0.txt",
         ("0.0.0.0/0", "rip", "rip", "", "", [("10.255.2.10", "GigabitEthernet0/2")])),
        ("s1__show_ip_route_10.10.10.3.txt",
         ("10.10.10.0/24", "connected", "connected", "", "", [("", "Vlan10")])),
        ("r2__show_ipv6_route_2001_DB8_1_14.txt",
         ("2001:db8:1::14/128", "ospf 1", "ospf", "1", "intra area",
          [("fe80::a8c1:abff:fe7b:a0db", "GigabitEthernet2")])),
        ("r2__show_ipv6_route_2001_DB8_3_14.txt",
         ("2001:db8:3::/64", "connected", "connected", "", "connected",
          [("", "GigabitEthernet2")])),
        ("r4__show_ipv6_route_2001_DB8_1_21.txt",
         ("2001:db8::/32", "static", "static", "", "", [("", "Null0")])),
        ("s1__show_ipv6_route_2001_DB8_1_14.txt",
         ("::/0", "rip RCN", "rip", "RCN", "", [("fe80::a8c1:abff:fe93:3623",
                                                  "GigabitEthernet0/2")])),
        ("r2__show_ipv6_route_unspecified.txt",
         ("::/127", "connected", "connected", "", "receive", [("", "Null0")]))])
    def test_each_route_s_entry(self, name, expected):
        f = facts("route", name)
        assert f["in_table"] is True
        assert (f["prefix"], f["source"], f["protocol"], f["process"], f["type"],
                [(x["next_hop"], x["interface"]) for x in f["paths"]]) == expected

    @pytest.mark.parametrize("name", ["r2__show_ip_route_198.51.100.1.txt",
                                      "s1__show_ip_route_10.255.1.14.txt"])
    def test_not_in_the_table_on_both_platforms(self, name):
        # Both forward these by their default route: IPv4's lookup by address never matches it.
        f = facts("route", name)
        assert f["in_table"] is False and f["paths"] == []

    def test_an_answer_that_is_not_a_route_is_unreadable(self):
        from modules.heal.diagnose_parse import parse as p
        assert p("route", diag("r2__show_ipv6_cef_2001_DB8_1_14.txt"))["state"] == "unreadable"


class TestTheTraceroute:
    def test_ios_xe_both_families(self):
        f = facts("traceroute", "r2__traceroute_10.255.1.21_numeric_timeout_2_probe_1_ttl_1_16.txt")
        assert f["dest"] == "10.255.1.21" and f["last"] == "10.255.2.11"
        assert [(h["n"], h["address"], h["marks"]) for h in f["hops"]] == [
            (1, "10.255.3.11", []), (2, "10.255.2.11", [])]
        f6 = facts("traceroute",
                   "r2__traceroute_ipv6_2001_DB8_1_21_numeric_timeout_2_probe_1_ttl_1_16.txt")
        assert [(h["n"], h["address"], h["marks"]) for h in f6["hops"]] == [
            (1, "2001:db8:3::14", []), (2, "2001:db8:3::14", ["!X"])]

    def test_ios_s_plain_form_and_its_timeouts(self):
        f = facts("traceroute", "s1__traceroute_10.255.1.14.txt")
        assert [(h["address"], h["timeouts"]) for h in f["hops"]] == [
            ("10.255.2.10", 0), ("10.255.3.14", 1)]

    @pytest.mark.parametrize("name", [
        "s1__traceroute_10.255.1.14_numeric_timeout_2_probe_1_ttl_1_16.txt",
        "s1__traceroute_10.255.1.14_timeout_2_probe_1_ttl_1_16.txt",
        "s1__traceroute_ipv6_2001_DB8_1_14_numeric_timeout_2_probe_1_ttl_1_16.txt",
        "s1__traceroute_ipv6_2001_DB8_1_14_timeout_2_probe_1_ttl_1_16.txt"])
    def test_ios_refuses_the_bounded_form(self, name):
        # C2681: vIOS-L2 has no option after a traceroute's address.
        got = parse("traceroute", name)
        assert got["state"] == "unsupported" and "no such read" in got["why"]


class TestTheAccessList:
    def test_each_list_s_entries(self):
        assert facts("acl_counters", "r2__show_ip_access_lists_meraki_fqdn_dns.txt") == {
            "name": "meraki-fqdn-dns", "family": 4, "entries": []}
        f = facts("acl_counters", "r4__show_ip_access_lists_NAT_PRIVATE.txt")
        assert f["name"] == "NAT-PRIVATE" and [e["seq"] for e in f["entries"]] == [10, 20, 30]
        f = facts("acl_counters", "s1__show_ip_access_lists_CISCO_CWA_URL_REDIRECT_ACL.txt")
        assert [e["seq"] for e in f["entries"]] == [100, 101, 102, 103, 104, 105]
        assert f["entries"][-1]["text"] == "permit tcp any any eq www"
        f = facts("acl_counters", "s1__show_ipv6_access_list_preauth_ipv6_acl.txt")
        assert (f["name"], f["family"], len(f["entries"])) == ("preauth_ipv6_acl", 6, 10)
        assert f["entries"][0] == {"seq": 10, "text": "permit udp any any eq domain"}

    def test_no_header_is_unreadable(self):
        from modules.heal.diagnose_parse import parse as p
        assert p("acl_counters", "")["state"] == "unreadable"


class TestTheIpv6Reads:
    def test_ipv6_interface_on_both_platforms(self):
        f = facts("ipv6_interface", "r2__show_ipv6_interface_GigabitEthernet2.txt",
                  "GigabitEthernet2")
        assert (f["state"], f["protocol"], f["link_local"], f["addresses"], f["ip_mtu"]) == (
            "up", "up", "fe80::a8c1:abff:feea:39ae", ["2001:db8:3::12/64"], 1500)
        f = facts("ipv6_interface", "s1__show_ipv6_interface_GigabitEthernet0_2.txt",
                  "GigabitEthernet0/2")
        assert f["addresses"] == ["2001:db8:2:a::2/64"]

    def test_neighbours_by_interface_and_by_address(self):
        f = facts("nd", "r2__show_ipv6_neighbors_GigabitEthernet2.txt")
        assert len(f["entries"]) == 4
        assert {"address": "fe80::a8c1:abff:fe7b:a0db", "mac": "aac1.ab7b.a0db",
                "state": "STALE", "interface": "Gi2"} in f["entries"]
        assert facts("nd", "r4__show_ipv6_neighbors_fe80_a8c1_abff_feea_39ae.txt")[
            "entries"] == [{"address": "fe80::a8c1:abff:feea:39ae", "mac": "aac1.abea.39ae",
                            "state": "STALE", "interface": "Gi3"}]
        assert facts("nd", "s1__show_ipv6_neighbors_GigabitEthernet0_2.txt")["entries"][0][
            "state"] == "REACH"

    def test_ios_refuses_the_address_form(self):
        # C2681: vIOS-L2 has no `show ipv6 neighbors <address>`.
        got = parse("nd", "s1__show_ipv6_neighbors_FE80_A8C1_ABFF_FE93_3623.txt")
        assert got["state"] == "unsupported"

    @pytest.mark.parametrize("name,state,prefix,hops", [
        ("r2__show_ipv6_cef_2001_DB8_1_14.txt", "next", "2001:db8:1::14/128",
         [("fe80::a8c1:abff:fe7b:a0db", "GigabitEthernet2")]),
        ("r2__show_ipv6_cef_2001_DB8_1_21.txt", "next", "2001:db8::/32",
         [("fe80::a8c1:abff:fe7b:a0db", "GigabitEthernet2"),
          ("fe80::a8c1:abff:feb2:a130", "GigabitEthernet2")]),
        ("r2__show_ipv6_cef_2001_DB8_1_12.txt", "receive", "2001:db8:1::12/128", []),
        ("r4__show_ipv6_cef_2001_DB8_1_21.txt", "drop", "2001:db8::/32", []),
        ("r4__show_ipv6_cef_2001_db8_1_12.txt", "next", "2001:db8:1::12/128",
         [("fe80::a8c1:abff:feea:39ae", "GigabitEthernet3")]),
        ("s1__show_ipv6_cef_2001_DB8_1_14.txt", "next", "::/0",
         [("fe80::a8c1:abff:fe93:3623", "GigabitEthernet0/2")])])
    def test_ipv6_cef_as_the_path_trace_reads_it(self, name, state, prefix, hops):
        from modules.path_trace import parse_cef
        got = parse_cef(diag(name), 6)
        assert (got["state"], got["prefix"], [(h["address"], h["iface"]) for h in got["hops"]]
                ) == (state, prefix, hops)

    def test_a_discard_route_is_dropped_in_either_family(self):
        # r4's real IPv6 answer; and the same line under an IPv4 prefix (edited), which the
        # IPv4 reader once took as "attached to Null0's segment".
        from modules.path_trace import parse_cef
        six = diag("r4__show_ipv6_cef_2001_DB8_1_21.txt")
        assert parse_cef(six, 6)["state"] == "drop"
        four = six.replace("2001:DB8::/32", "198.51.100.0/24")
        assert parse_cef(four)["state"] == "drop"
        assert parse_cef(diag("s1__show_ip_cef_10.10.10.3.txt"))["state"] == "attached"

    def test_an_ipv4_answer_is_not_read_as_ipv6(self):
        from modules.path_trace import parse_cef
        got = parse_cef(diag("s1__show_ip_cef_10.255.1.14.txt"), 6)
        assert got["state"] == "unknown" and "not an answer the trace reads" in got["why"]


class TestTheSwitch:
    def test_the_mac_table_and_spanning_tree(self):
        assert facts("mac", "s1__show_mac_address_table_address_0c00.6f31.800a.txt") == {
            "entries": [{"vlan": 10, "mac": "0c00.6f31.800a", "type": "DYNAMIC",
                         "port": "Gi0/3"}]}
        assert len(facts("mac", "s1__show_mac_address_table_dynamic.txt")["entries"]) == 5
        assert facts("stp", "s1__show_spanning_tree_interface_GigabitEthernet0_3.txt") == {
            "vlans": [{"vlan": v, "role": "Desg", "state": "FWD", "cost": 4}
                      for v in (10, 20, 30)]}

    @pytest.mark.parametrize("kind", ["mac", "stp", "nd"])
    def test_an_empty_answer_is_unreadable_never_empty(self, kind):
        from modules.heal.diagnose_parse import parse as p
        assert p(kind, "")["state"] == "unreadable"


class TestTheLoki:
    """C2695: a real interface UPDOWN line as the lab's Loki stores it (r4 Gi4, bounced
    18:05 to 18:08 UTC, read back through Mercury's own Loki selector)."""

    def test_the_updown_lines_parse_as_the_device_logs_reader_reads_them(self):
        import json

        from modules import device_logs
        with open(os.path.join(DIAG, "loki_updown_r4.json"), encoding="utf-8") as fh:
            got = json.load(fh)
        lines = [line for s in got["answer"]["data"]["result"] for _ns, line in s["values"]]
        parsed = [device_logs.parse(line, "r4") for line in lines]
        assert sorted(p["mnemonic"] for p in parsed) == (["%LINEPROTO-5-UPDOWN"] * 4
                                                         + ["%LINK-3-UPDOWN"] * 2)
        assert {p["text"] for p in parsed if p["mnemonic"] == "%LINEPROTO-5-UPDOWN"} == {
            "Line protocol on Interface GigabitEthernet4, changed state to down",
            "Line protocol on Interface GigabitEthernet4, changed state to up"}
