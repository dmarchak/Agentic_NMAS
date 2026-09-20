"""Platform parsers, against the real sanitized fixtures.

Separate modules per platform is the multi-vendor story: a new vendor is a new
module plus a template directory, not a change to the extraction engine. These
tests pin the differences that justify the split.
"""

import os

import pytest

from modules.nsot.parsers import (
    REGISTRY, CiscoIosParser, CiscoIosXeParser, get_parser, split_blocks,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "configs")


def _config(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def s1():
    return get_parser("cisco_ios").parse(_config("s1_vios_l2.cfg"))


@pytest.fixture(scope="module")
def r1():
    return get_parser("cisco_xe").parse(_config("r1_c8000v.cfg"))


class TestRegistry:
    def test_platform_slugs_resolve(self):
        assert isinstance(get_parser("cisco_ios"), CiscoIosParser)
        assert isinstance(get_parser("cisco_xe"), CiscoIosXeParser)
        assert isinstance(get_parser("cisco-ios-xe"), CiscoIosXeParser)

    def test_unknown_platform_falls_back(self):
        assert get_parser("arista_eos") is not None

    def test_registry_covers_the_platform_map_defaults(self):
        for slug in ("cisco-ios-xe", "cisco-ios"):
            assert slug in REGISTRY


class TestBlockSplitting:
    def test_groups_indented_bodies(self):
        blocks = split_blocks("interface Gi0/1\n description x\n shutdown\nhostname R9\n")
        assert len(blocks) == 2
        assert blocks[0].children == [" description x", " shutdown"]

    def test_blank_lines_ignored(self):
        assert len(split_blocks("hostname R9\n\n\nvlan 10\n")) == 2


class TestSharedParsing:
    def test_hostname(self, s1, r1):
        assert s1["hostname"] == "s1"
        assert r1["hostname"] == "r1"

    def test_interfaces_are_canonical(self, s1):
        names = [i["name"] for i in s1["interfaces"]]
        assert "GigabitEthernet0/0" in names
        assert not any(n.startswith("Gi0") for n in names)

    def test_dual_stack_addressing(self, s1):
        vlan10 = next(i for i in s1["interfaces"] if i["name"] == "Vlan10")
        assert vlan10["ipv4"] == "10.10.10.2 255.255.255.0"
        assert "2001:DB8:10::2/64" in vlan10["ipv6"]

    def test_dhcp_relay_both_families(self, s1):
        vlan10 = next(i for i in s1["interfaces"] if i["name"] == "Vlan10")
        assert vlan10["helper_addresses"] == ["10.255.0.10"]
        assert vlan10["dhcpv6_relay"] == ["2001:DB8:255::10"]

    def test_rip_is_parsed_with_networks_split_out(self, s1):
        rip = s1["routing"]["rip"]
        assert "version 2" in rip["settings"]
        assert "no auto-summary" in rip["settings"]
        assert rip["networks"] == ["network 10.0.0.0"]

    def test_passive_interfaces_are_canonicalised(self, s1):
        rip = s1["routing"]["rip"]
        assert "passive-interface Loopback0" in rip["settings"]

    def test_logging_and_ntp(self, s1):
        assert s1["logging"]["hosts"] == ["10.255.1.10"]
        assert s1["ntp_servers"] == ["10.255.1.10"]

    def test_static_route_with_vrf(self, r1):
        assert any("vrf clab-mgmt" in r["spec"] for r in r1["static_routes"])


class TestIosSpecific:
    """vIOS-L2: VLANs, switchports, VRRP."""

    def test_vlans(self, s1):
        by_id = {v["id"]: v for v in s1["vlans"]}
        assert set(by_id) == {"10", "20", "30"}
        assert by_id["20"]["name"] == "USERS"
        assert by_id["10"]["name"] == ""

    def test_trunk_port(self, s1):
        gi03 = next(i for i in s1["interfaces"] if i["name"] == "GigabitEthernet0/3")
        assert gi03["switchport_mode"] == "trunk"
        assert gi03["switchport_trunk_vlans"] == ["10,20,30"]
        assert gi03["switchport_trunk_encapsulation"] == "dot1q"

    def test_access_port(self, s1):
        gi10 = next(i for i in s1["interfaces"] if i["name"] == "GigabitEthernet1/0")
        assert gi10["switchport_mode"] == "access"
        assert gi10["switchport_access_vlan"] == "10"

    def test_routed_port_on_a_switch(self, s1):
        gi02 = next(i for i in s1["interfaces"] if i["name"] == "GigabitEthernet0/2")
        assert gi02["no_switchport"] is True

    def test_vrrp_groups_are_structured(self, s1):
        """VRRP on S1/S2 SVIs is core to the lab, so it is modelled."""
        vlan10 = next(i for i in s1["interfaces"] if i["name"] == "Vlan10")
        groups = {g["family"]: g for g in vlan10["vrrp_groups"]}
        assert set(groups) == {"ipv4", "ipv6"}
        assert groups["ipv4"]["group"] == "10"
        assert "priority 110" in groups["ipv4"]["settings"]
        assert "address 10.10.10.1 primary" in groups["ipv4"]["settings"]
        assert groups["ipv4"]["terminator"] == "exit-vrrp"

    def test_svi_with_no_ipv4(self, s1):
        vlan30 = next(i for i in s1["interfaces"] if i["name"] == "Vlan30")
        assert vlan30["no_ip_address"] is True
        assert vlan30["ipv4"] == ""

    def test_track_object(self, s1):
        assert s1["tracks"][0]["id"] == 1
        assert "GigabitEthernet0/2" in s1["tracks"][0]["spec"]

    def test_no_telemetry_on_this_platform(self, s1):
        assert s1.get("telemetry", []) == []


class TestIosXeSpecific:
    """C8000v: VRF definitions, OSPF, telemetry, IP SLA, PKI."""

    def test_vrf_definition_with_address_families(self, r1):
        vrf = r1["vrfs"][0]
        assert vrf["name"] == "clab-mgmt"
        assert {af["family"] for af in vrf["address_families"]} == {"ipv4", "ipv6"}
        assert all(af["terminator"] == "exit-address-family"
                   for af in vrf["address_families"])

    def test_interface_vrf_binding(self, r1):
        gi1 = next(i for i in r1["interfaces"] if i["name"] == "GigabitEthernet1")
        assert gi1["vrf"] == "clab-mgmt"

    def test_ospf_networks_split_from_settings(self, r1):
        ospf = r1["routing"]["ospf"][0]
        assert ospf["process"] == "1"
        assert "router-id 10.255.1.11" in ospf["settings"]
        assert len(ospf["networks"]) == 2

    def test_ospfv3(self, r1):
        assert r1["routing"]["ospfv3"][0]["process"] == "1"

    def test_telemetry_subscriptions(self, r1):
        subs = {t["subscription"] for t in r1["telemetry"]}
        assert subs == {"101", "102"}
        assert any("receiver ip address" in s
                   for s in r1["telemetry"][0]["settings"])

    def test_netconf_and_restconf_flags(self, r1):
        assert r1["flags"].get("netconf-yang") is True
        assert r1["flags"].get("restconf") is True

    def test_ip_sla_entries_keep_order(self, r1):
        """Probe sub-commands nest: `frequency` sits under `icmp-echo`."""
        sla = r1["ip_sla"][0]
        assert sla["id"] == "1"
        assert "icmp-echo" in sla["settings"][0]

    def test_acl_entries_are_ordered(self, r1):
        acl = r1["acls"][0]
        assert acl["name"] == "PROMETHEUS_SERVER"
        assert acl["entries"] == ["10 permit 10.0.0.211"]

    def test_pki_trustpoints_kept_certificates_stripped(self, r1):
        """Trustpoint config is renderable; the certificate body is not."""
        assert {t["name"] for t in r1["pki_trustpoints"]} == {
            "TP-self-signed-2968666059", "SLA-TrustPoint"}
        assert not any("certificate chain" in u["line"] for u in r1["unmodeled"])


class TestDecisionRule:
    """Model what appears on 2+ devices; leave device-unique lines unmodeled."""

    def test_common_constructs_are_modelled(self, s1, r1):
        for parsed in (s1, r1):
            assert parsed["ssh"], "ip ssh appears on both devices"
            assert parsed["http"], "ip http appears on both devices"
            assert parsed["forward_protocol"]

    def test_fleet_run_promoted_shared_constructs(self, r1):
        """These were unmodeled until the fleet run showed them on 5 devices.

        The amended rule models any construct on 2+ devices, or any
        routing/redundancy protocol in the network design.
        """
        assert r1["subscriber"] == ["templating"]
        assert r1["multilink"] == ["bundle-name authenticated"]
        assert r1["redundancy"] is not None
        assert r1["call_home"] is not None
        assert r1["login"] == ["on-success log"]

    def test_call_home_keeps_its_full_nested_body(self, r1):
        """A truncated call-home block has silently eaten config before."""
        body = r1["call_home"]["body"]
        assert any("contact-email-addr" in l for l in body)
        assert any('profile "CiscoTAC-1"' in l for l in body)
        # Two levels deep: `profile` has its own children.
        assert any(l.startswith("  active") for l in body)
        assert any("destination transport-method http" in l for l in body)

    def test_switch_is_fully_modelled(self, s1):
        assert s1["unmodeled"] == []
        assert all(i["unmodeled"] == [] for i in s1["interfaces"])
