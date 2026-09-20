"""Fleet-wide round-trip coverage across all nine reference devices.

Two fixtures proved the approach; nine prove the schema. R3/R4 add BGP
address-families, NAT and prefix-lists; R5 is the PE with no OSPF and no
telemetry; S3/S4 run OSPF rather than RIP/VRRP. Running the whole fleet is how
parser gaps surface before 3b builds a template library on the schema.
"""

import glob
import os

import pytest

from modules.nsot.roundtrip import rank_unmodeled, validate_device

FLEET = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")
DEVICES = sorted(os.path.basename(p)[:-4] for p in glob.glob(f"{FLEET}/*.cfg"))


def _platform(name):
    return "cisco_xe" if name.startswith("r") else "cisco_ios"


def _config(name):
    with open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def fleet():
    return [validate_device(_config(n), _platform(n)) for n in DEVICES]


def test_fleet_is_complete():
    assert DEVICES == ["r1", "r2", "r3", "r4", "r5", "s1", "s2", "s3", "s4"]


@pytest.mark.parametrize("name", DEVICES)
class TestPerDevice:
    def test_renders(self, name):
        assert not validate_device(_config(name), _platform(name)).get("error")

    def test_full_fidelity(self, name):
        report = validate_device(_config(name), _platform(name))
        assert report["round_trip_fidelity"] == 100.0
        assert report["missing_from_render"] == 0
        assert report["extra_in_render"] == 0

    def test_no_reordered_sections(self, name):
        assert validate_device(_config(name), _platform(name))["reordered_sections"] == 0

    def test_coverage_threshold(self, name):
        report = validate_device(_config(name), _platform(name))
        assert report["modeled_coverage"] >= 80.0, (
            f"{name} modelled {report['modeled_coverage']}%")


class TestFleetAggregate:
    def test_mean_coverage(self, fleet):
        mean = sum(r["modeled_coverage"] for r in fleet) / len(fleet)
        assert mean >= 95.0, f"fleet mean modelled coverage is {mean:.1f}%"

    def test_every_device_reproduces(self, fleet):
        assert all(r["ok"] for r in fleet)

    def test_ranked_unmodeled_is_ordered(self, fleet):
        ranked = rank_unmodeled(fleet)
        assert ranked == sorted(ranked, key=lambda r: -r["occurrences"])

    def test_no_construct_on_two_or_more_devices_is_unmodeled(self, fleet):
        """The decision rule, enforced.

        Model any construct on 2+ devices, or any routing/redundancy protocol
        in the network design. Anything left unmodeled must be device-unique.
        """
        shared = [u for u in rank_unmodeled(fleet) if u["device_count"] >= 2]
        assert shared == [], (
            "these appear on 2+ devices and should be modelled: "
            + ", ".join(f"{u['construct']} ({u['device_count']} devices)" for u in shared))


class TestPlatformSpecificFeatures:
    """Features only some devices have — the reason nine fixtures beat two."""

    def test_bgp_address_families_on_r3_r4_r5(self):
        for name in ("r3", "r4", "r5"):
            report = validate_device(_config(name), _platform(name))
            bgp = report["host_vars"]["routing"]["bgp"]
            assert bgp is not None, f"{name} has no BGP"
            assert any("address-family" in s for s in bgp["settings"]), name

    def test_r5_is_the_pe_no_ospf_no_telemetry(self):
        host_vars = validate_device(_config("r5"), "cisco_xe")["host_vars"]
        assert host_vars["routing"]["ospf"] == []
        assert host_vars["telemetry"] == []
        assert host_vars["routing"]["bgp"]["asn"] == "65002"

    def test_nat_and_prefix_lists_on_r3_r4(self):
        for name in ("r3", "r4"):
            host_vars = validate_device(_config(name), "cisco_xe")["host_vars"]
            assert host_vars["ip_nat"], name
            assert host_vars["prefix_lists"], name
            entries = host_vars["prefix_lists"][0]["entries"]
            assert entries == sorted(entries, key=lambda e: int(e.split()[1])), \
                "prefix-list entries must keep sequence order"

    def test_interface_level_nat(self):
        host_vars = validate_device(_config("r3"), "cisco_xe")["host_vars"]
        by_name = {i["name"]: i for i in host_vars["interfaces"]}
        assert by_name["GigabitEthernet2"]["ip_nat"] == ["outside"]
        assert by_name["GigabitEthernet3"]["ip_nat"] == ["inside"]

    def test_vrrp_only_on_s1_s2(self):
        for name in ("s1", "s2"):
            host_vars = validate_device(_config(name), "cisco_ios")["host_vars"]
            assert any(i["vrrp_groups"] for i in host_vars["interfaces"]), name
        for name in ("s3", "s4"):
            host_vars = validate_device(_config(name), "cisco_ios")["host_vars"]
            assert not any(i["vrrp_groups"] for i in host_vars["interfaces"]), name

    def test_s3_s4_run_ospf_not_rip(self):
        for name in ("s3", "s4"):
            host_vars = validate_device(_config(name), "cisco_ios")["host_vars"]
            assert host_vars["routing"]["ospf"], name
            assert host_vars["routing"]["rip"] is None, name

    def test_s1_s2_run_rip_not_ospf(self):
        for name in ("s1", "s2"):
            host_vars = validate_device(_config(name), "cisco_ios")["host_vars"]
            assert host_vars["routing"]["rip"] is not None, name
            assert host_vars["routing"]["ospf"] == [], name

    def test_ip_sla_parses_on_both_platforms(self):
        """It was IOS-XE-only until the fleet run found it on an IOS switch."""
        assert validate_device(_config("s3"), "cisco_ios")["host_vars"]["ip_sla"]
        assert validate_device(_config("r1"), "cisco_xe")["host_vars"]["ip_sla"]

    def test_telemetry_on_routers_that_have_it(self):
        for name in ("r1", "r2", "r3", "r4"):
            subs = validate_device(_config(name), "cisco_xe")["host_vars"]["telemetry"]
            assert {t["subscription"] for t in subs} == {"101", "102"}, name


class TestNestedBlockCapture:
    """Nested blocks must be captured whole, parents and all children."""

    def test_call_home_keeps_two_levels_of_nesting(self):
        for name in ("r1", "r3", "r5"):
            body = validate_device(_config(name), "cisco_xe")["host_vars"]["call_home"]["body"]
            assert any('profile "CiscoTAC-1"' in l for l in body), name
            assert any(l.startswith("  active") for l in body), name

    def test_call_home_survives_the_round_trip(self):
        report = validate_device(_config("r1"), "cisco_xe")
        rendered = report["rendered"]
        for line in ("call-home", "contact-email-addr", 'profile "CiscoTAC-1"',
                     "destination transport-method http"):
            assert line in rendered

    def test_vrf_address_families_keep_terminators(self):
        vrf = validate_device(_config("r1"), "cisco_xe")["host_vars"]["vrfs"][0]
        assert all(af["terminator"] == "exit-address-family"
                   for af in vrf["address_families"])
