"""Canonical interface names.

`Gi0/0` and `GigabitEthernet0/0` are the same interface. A comparison that
treats them as different lines reports false drift on every abbreviated
reference — and abbreviations are what CDP/LLDP output and operators use.
"""

import pytest

from modules.nsot import ifnames


class TestCanonical:
    @pytest.mark.parametrize("short,full", [
        ("Gi0/0", "GigabitEthernet0/0"),
        ("Gi1", "GigabitEthernet1"),
        ("Te1/1/1", "TenGigabitEthernet1/1/1"),
        ("Fa0/1", "FastEthernet0/1"),
        ("Lo0", "Loopback0"),
        ("Po1", "Port-channel1"),
        ("Vl99", "Vlan99"),
        ("Tu0", "Tunnel0"),
        ("Se0/0/0", "Serial0/0/0"),
    ])
    def test_expands(self, short, full):
        assert ifnames.canonical(short) == full

    def test_already_canonical_is_unchanged(self):
        assert ifnames.canonical("GigabitEthernet0/0") == "GigabitEthernet0/0"

    def test_tengig_is_not_swallowed_by_te(self):
        """Longest-first matching: 'TenGig' must not resolve via 'Te'."""
        assert ifnames.canonical("TenGig1/1") == "TenGigabitEthernet1/1"

    def test_unknown_prefix_is_not_guessed(self):
        """A wrong expansion is worse than none."""
        assert ifnames.canonical("Xyzzy9/9") == "Xyzzy9/9"

    def test_empty_input(self):
        assert ifnames.canonical("") == ""
        assert ifnames.canonical(None) == ""


class TestRoundTrip:
    @pytest.mark.parametrize("name", [
        "GigabitEthernet0/0", "TenGigabitEthernet1/1/1", "Loopback0",
        "Port-channel1", "Vlan99", "FastEthernet0/1",
    ])
    def test_abbreviate_then_canonical_is_identity(self, name):
        assert ifnames.canonical(ifnames.abbreviate(name)) == name

    def test_same_interface(self):
        assert ifnames.same_interface("Gi0/2", "GigabitEthernet0/2")
        assert ifnames.same_interface("gi0/2", "GigabitEthernet0/2")
        assert not ifnames.same_interface("Gi0/2", "Gi0/3")


class TestLineCanonicalisation:
    @pytest.mark.parametrize("line,expected", [
        (" passive-interface Gi0/2", " passive-interface GigabitEthernet0/2"),
        ("track 1 interface Gi0/2 line-protocol",
         "track 1 interface GigabitEthernet0/2 line-protocol"),
        ("logging source-interface Lo0", "logging source-interface Loopback0"),
        (" no passive-interface Gi3", " no passive-interface GigabitEthernet3"),
    ])
    def test_expands_references_inside_lines(self, line, expected):
        assert ifnames.canonicalise_line(line) == expected

    def test_leaves_unrelated_text_alone(self):
        line = "snmp-server location Cloud Environment"
        assert ifnames.canonicalise_line(line) == line

    def test_does_not_mangle_ip_addresses(self):
        line = " ip address 10.255.1.21 255.255.255.255"
        assert ifnames.canonicalise_line(line) == line


class TestSharedTable:
    def test_both_directions_derive_from_one_table(self):
        """The two pre-existing maps in this codebase could drift apart."""
        for canonical, abbrevs in ifnames.INTERFACE_PREFIXES:
            for abbrev in abbrevs:
                assert ifnames.canonical(f"{abbrev}0") == f"{canonical}0"
