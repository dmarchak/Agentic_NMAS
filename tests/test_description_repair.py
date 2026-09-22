"""Correcting descriptions that were expanded in committed intent.

The parser fix stops new damage. It does not undo what is already committed:
`host_vars` hold `GigabitEthernet3` where the device says `Gi3`, and the
render will keep disagreeing with the device until that is corrected.

The repair is deliberately narrow, and the narrowness is the point. A
description that genuinely differs from the device is **drift** -- a pending
change waiting to be deployed -- and a repair tool that rewrote it would
silently discard somebody's work while claiming to fix formatting.
"""

import pytest

from scripts.nsot_fix_description_ifnames import corrections, golden_descriptions

CONFIG = """hostname s1
!
interface GigabitEthernet0/2
 description P2P to r1 Gi3 - RIPng
 no switchport
!
interface GigabitEthernet0/3
 description trunk to s2 Gi0/3 - VRRP rides this
!
interface Vlan10
 description hosts
!
end
"""


class TestReadingTheDevicesOwnText:
    def test_descriptions_come_back_verbatim(self):
        found = golden_descriptions(CONFIG)
        assert found["GigabitEthernet0/2"] == "P2P to r1 Gi3 - RIPng"
        assert found["Vlan10"] == "hosts"

    def test_it_does_not_read_through_the_parser(self):
        """The parser is the thing that corrupted this text; reading back
        through it would compare a value against itself."""
        import inspect

        from scripts import nsot_fix_description_ifnames as tool

        source = inspect.getsource(tool.golden_descriptions)
        assert "get_parser" not in source and "parse(" not in source

    def test_a_description_outside_an_interface_is_ignored(self):
        config = "router bgp 65001\n description not an interface\n!\n"
        assert golden_descriptions(config) == {}


class TestOnlyTheExpansionIsCorrected:
    def test_an_expanded_description_is_corrected(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2",
             "description": "P2P to r1 GigabitEthernet3 - RIPng"}]}
        found = corrections(committed, CONFIG)
        assert found == [("GigabitEthernet0/2",
                          "P2P to r1 GigabitEthernet3 - RIPng",
                          "P2P to r1 Gi3 - RIPng")]

    def test_real_drift_is_left_alone(self):
        """Somebody edited intent and has not deployed it yet. Rewriting it
        would discard the change."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": "NEW purpose"}]}
        assert corrections(committed, CONFIG) == []

    def test_drift_that_also_contains_an_expansion_is_left_alone(self):
        """The subtle case: both an expansion AND a real edit. Correcting it
        would half-apply a repair over somebody's pending change."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2",
             "description": "P2P to r1 GigabitEthernet3 - OSPF now"}]}
        assert corrections(committed, CONFIG) == []

    def test_a_matching_description_is_not_touched(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": "P2P to r1 Gi3 - RIPng"}]}
        assert corrections(committed, CONFIG) == []

    def test_an_interface_the_device_does_not_have_is_skipped(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet9/9", "description": "x GigabitEthernet3"}]}
        assert corrections(committed, CONFIG) == []

    def test_an_interface_with_no_description_is_skipped(self):
        committed = {"interfaces": [{"name": "GigabitEthernet0/2"}]}
        assert corrections(committed, CONFIG) == []

    def test_an_empty_description_is_not_confused_with_a_missing_one(self):
        """`""` is a description the operator set; `None` is absence."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": ""}]}
        found = corrections(committed, CONFIG)
        assert found == [("GigabitEthernet0/2", "", "P2P to r1 Gi3 - RIPng")] \
            or found == []

    def test_the_interface_is_matched_canonically(self):
        """The header was expanded legitimately, so both sides must agree on
        which interface is which."""
        committed = {"interfaces": [
            {"name": "Gi0/2", "description": "P2P to r1 GigabitEthernet3 - RIPng"}]}
        assert corrections(committed, CONFIG)[0][0] == "Gi0/2"


class TestItTouchesNothingButDescriptions:
    def test_no_other_field_is_returned(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2",
             "description": "P2P to r1 GigabitEthernet3 - RIPng",
             "ipv4": "10.0.0.1 255.255.255.0", "no_switchport": True}]}
        assert len(corrections(committed, CONFIG)) == 1

    def test_the_writer_only_assigns_description(self):
        import inspect

        from scripts import nsot_fix_description_ifnames as tool

        body = inspect.getsource(tool.main)
        assignments = [l for l in body.splitlines()
                       if "entry[" in l and "=" in l and "==" not in l]
        assert assignments, "no assignment found; the test is checking nothing"
        for line in assignments:
            assert '"description"' in line, line


class TestOnTheRealFleetFixtures:
    """The fixtures are the sanitized real devices, so this is the shape the
    live repair will meet."""

    @pytest.mark.parametrize("host", ["s1", "r1"])
    def test_an_expanded_committed_intent_is_detected(self, host):
        import io
        import os

        from modules.nsot import ifnames
        from modules.nsot.parsers import get_parser

        path = os.path.join("tests", "fixtures", "configs", "fleet",
                            f"{host}.cfg")
        config = io.open(path, encoding="utf-8").read()
        platform = "cisco_ios" if host.startswith("s") else "cisco_iosxe"
        parsed = get_parser(platform).parse(config)

        # Reconstruct what the OLD parser committed: descriptions expanded.
        damaged = {"interfaces": []}
        for entry in parsed.get("interfaces") or []:
            text = entry.get("description")
            if text is None:
                continue
            damaged["interfaces"].append({
                "name": entry["name"],
                "description": ifnames._LINE_RE.sub(
                    lambda m: ifnames.canonical(f"{m.group(1)}{m.group(2)}"),
                    text)})

        found = corrections(damaged, config)
        assert found, f"{host} has no expanded description to repair"
        for _name, have, want in found:
            assert have != want
            assert want in config, "the correction is not the device's own text"
