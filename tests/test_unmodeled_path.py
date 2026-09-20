"""The `unmodeled` fallback path.

Every construct in the reference fleet is now modelled, which means this path —
the one that catches everything the parsers do not understand — is exercised by
nothing. It is also the only thing standing between an unfamiliar network and
silently dropped configuration, so it gets tested deliberately with constructs
the parsers have never seen.

The guarantee: a line the parser does not model is captured **whole**, including
nested children, round-trips **byte-exact**, and is **never silently dropped**.
"""

import pytest

from modules.nsot import hostvars, roundtrip
from modules.nsot.parsers import get_parser

BASE = """hostname R99
ip domain-name example.com
interface GigabitEthernet0/1
 description known construct
 ip address 203.0.113.1 255.255.255.0
!
"""

# Constructs no parser in this codebase models. Deliberately plausible-looking
# rather than nonsense: a real unfamiliar platform looks like this.
UNKNOWN_FLAT = "frobnicate widgets enable\n"

UNKNOWN_NESTED = """quantum-tunnel profile ALPHA
 entanglement-mode paired
 decoherence-threshold 42
 peer 203.0.113.9
!
"""

UNKNOWN_DEEP = """service-chain POLICY-X
 classifier match-any
  match protocol http
  match protocol https
 action redirect
  target 203.0.113.50
!
"""

UNKNOWN_IN_INTERFACE = """interface GigabitEthernet0/2
 description interface with an unknown child
 ip address 203.0.113.2 255.255.255.0
 flux-capacitor enable 1.21
!
"""


def _parse(config, platform="cisco_ios"):
    return get_parser(platform).parse(config)


def _unmodeled_lines(host_vars):
    lines = []
    for entry in host_vars["unmodeled"]:
        lines.append(entry["line"])
        lines.extend(entry["children"])
    for iface in host_vars["interfaces"]:
        lines.extend(iface["unmodeled"])
    return lines


class TestFlatUnknownConstruct:
    def test_lands_in_unmodeled(self):
        host_vars = _parse(BASE + UNKNOWN_FLAT)
        assert "frobnicate widgets enable" in [l.strip() for l in _unmodeled_lines(host_vars)]

    def test_is_not_silently_dropped(self):
        """The failure this guards against: the line vanishes without a trace."""
        host_vars = _parse(BASE + UNKNOWN_FLAT)
        rendered = roundtrip.render(host_vars, "cisco_ios")
        assert "frobnicate widgets enable" in rendered

    def test_known_constructs_still_parse_alongside_it(self):
        host_vars = _parse(BASE + UNKNOWN_FLAT)
        assert host_vars["hostname"] == "R99"
        assert host_vars["domain_name"] == "example.com"
        assert len(host_vars["interfaces"]) == 1


class TestNestedUnknownBlock:
    def test_parent_and_all_children_captured(self):
        host_vars = _parse(BASE + UNKNOWN_NESTED)
        entry = next(e for e in host_vars["unmodeled"]
                     if e["line"].startswith("quantum-tunnel"))
        assert entry["line"] == "quantum-tunnel profile ALPHA"
        assert [c.strip() for c in entry["children"]] == [
            "entanglement-mode paired", "decoherence-threshold 42", "peer 203.0.113.9"]

    def test_block_round_trips_byte_exact(self):
        host_vars = _parse(BASE + UNKNOWN_NESTED)
        rendered = roundtrip.render(host_vars, "cisco_ios")
        block = UNKNOWN_NESTED.rstrip("\n!\n").rstrip()
        assert block in rendered, "the nested block was not reproduced verbatim"

    def test_indentation_is_preserved(self):
        """Indentation is structural in IOS — losing it changes the config."""
        host_vars = _parse(BASE + UNKNOWN_NESTED)
        entry = next(e for e in host_vars["unmodeled"]
                     if e["line"].startswith("quantum-tunnel"))
        assert all(c.startswith(" ") for c in entry["children"])

    def test_full_round_trip_reports_no_loss(self):
        config = BASE + UNKNOWN_NESTED
        report = roundtrip.validate_device(config, "cisco_ios")
        assert report["missing_from_render"] == 0, \
            f"lost: {[m['line'] for m in report['details']['missing']]}"
        assert report["extra_in_render"] == 0


class TestDeeplyNestedUnknownBlock:
    """Two levels of nesting under an unknown parent — as `call-home` has."""

    def test_all_levels_captured(self):
        host_vars = _parse(BASE + UNKNOWN_DEEP)
        entry = next(e for e in host_vars["unmodeled"]
                     if e["line"].startswith("service-chain"))
        children = entry["children"]
        assert any(c == " classifier match-any" for c in children)
        assert any(c == "  match protocol http" for c in children)
        assert any(c == "  target 203.0.113.50" for c in children)

    def test_deep_block_round_trips(self):
        config = BASE + UNKNOWN_DEEP
        report = roundtrip.validate_device(config, "cisco_ios")
        assert report["missing_from_render"] == 0
        assert report["round_trip_fidelity"] == 100.0


class TestUnknownChildInsideKnownInterface:
    def test_lands_in_interface_unmodeled(self):
        host_vars = _parse(BASE + UNKNOWN_IN_INTERFACE)
        iface = next(i for i in host_vars["interfaces"]
                     if i["name"] == "GigabitEthernet0/2")
        assert iface["unmodeled"] == ["flux-capacitor enable 1.21"]

    def test_known_siblings_still_parse(self):
        host_vars = _parse(BASE + UNKNOWN_IN_INTERFACE)
        iface = next(i for i in host_vars["interfaces"]
                     if i["name"] == "GigabitEthernet0/2")
        assert iface["description"] == "interface with an unknown child"
        assert iface["ipv4"] == "203.0.113.2 255.255.255.0"

    def test_round_trips_inside_the_interface(self):
        config = BASE + UNKNOWN_IN_INTERFACE
        rendered = roundtrip.render(_parse(config), "cisco_ios")
        assert " flux-capacitor enable 1.21" in rendered
        report = roundtrip.validate_device(config, "cisco_ios")
        assert report["missing_from_render"] == 0


class TestCoverageAccounting:
    """Unmodeled content must lower modelled coverage, not hide inside it."""

    def test_unknown_constructs_reduce_modeled_coverage(self):
        clean = roundtrip.validate_device(BASE, "cisco_ios")
        dirty = roundtrip.validate_device(BASE + UNKNOWN_NESTED, "cisco_ios")
        assert dirty["modeled_coverage"] < clean["modeled_coverage"]

    def test_fidelity_stays_perfect(self):
        """Fidelity and coverage answer different questions — this is the proof."""
        dirty = roundtrip.validate_device(BASE + UNKNOWN_NESTED, "cisco_ios")
        assert dirty["round_trip_fidelity"] == 100.0
        assert dirty["modeled_coverage"] < 100.0

    def test_unmodeled_count_matches_the_lines(self):
        report = roundtrip.validate_device(BASE + UNKNOWN_NESTED, "cisco_ios")
        assert report["unmodeled"] == 4          # parent + three children

    def test_ranked_list_surfaces_the_unknown(self):
        report = roundtrip.validate_device(BASE + UNKNOWN_NESTED, "cisco_ios")
        ranked = roundtrip.rank_unmodeled([report])
        assert any(r["construct"].startswith("quantum-tunnel") for r in ranked)


class TestFixedPointWithUnknowns:
    def test_yaml_is_still_a_fixed_point(self):
        """An unfamiliar platform must not break extract→render→extract."""
        config = BASE + UNKNOWN_NESTED + UNKNOWN_DEEP + UNKNOWN_FLAT
        parser = get_parser("cisco_ios")
        first = parser.parse(config)
        second = parser.parse(roundtrip.render(first, "cisco_ios"))
        assert hostvars.to_yaml(first) == hostvars.to_yaml(second)

    def test_yaml_carries_the_unknown_content(self):
        text = hostvars.to_yaml(_parse(BASE + UNKNOWN_NESTED))
        assert "quantum-tunnel profile ALPHA" in text
        assert "entanglement-mode paired" in text


class TestWhollyUnknownConfig:
    """The worst case: a platform the parsers know nothing about."""

    ALIEN = """system identity name=alien-01
/interface bridge
 add name=bridge1 protocol-mode=rstp
/ip address
 add address=203.0.113.1/24 interface=bridge1
"""

    def test_nothing_is_lost(self):
        report = roundtrip.validate_device(self.ALIEN, "cisco_ios")
        assert report["missing_from_render"] == 0
        assert report["round_trip_fidelity"] == 100.0

    def test_coverage_is_honestly_zero(self):
        report = roundtrip.validate_device(self.ALIEN, "cisco_ios")
        assert report["modeled_coverage"] == 0.0

    def test_every_line_is_reproduced(self):
        rendered = roundtrip.render(_parse(self.ALIEN), "cisco_ios")
        for line in self.ALIEN.splitlines():
            assert line in rendered, f"lost: {line!r}"


class TestNoInventedLines:
    """A template must never emit config the device did not have.

    Regression: `control_plane` defaulted to `{"settings": []}`, which is
    truthy, so every rendered config gained a `control-plane` line — including
    devices that never had one. Every fixture in the fleet happens to have it,
    so only a minimal config exposed the bug. Inventing a line is arguably worse
    than dropping one: it would push configuration to a device on deploy.
    """

    MINIMAL = "hostname R99\n"

    def test_minimal_config_gains_nothing(self):
        report = roundtrip.validate_device(self.MINIMAL, "cisco_ios")
        assert report["extra_in_render"] == 0, \
            f"invented: {[e['line'] for e in report['details']['extra']]}"

    @pytest.mark.parametrize("absent", [
        "control-plane", "redundancy", "call-home", "vtp mode", "ip http",
        "spanning-tree", "snmp-server", "logging host", "ntp server",
    ])
    def test_absent_construct_is_not_invented(self, absent):
        rendered = roundtrip.render(_parse(self.MINIMAL), "cisco_ios")
        assert absent not in rendered, f"template invented {absent!r}"

    def test_empty_optional_blocks_render_nothing(self):
        """Every optional block defaults must be falsy-or-None, not empty-truthy."""
        host_vars = _parse(self.MINIMAL)
        for key in ("control_plane", "redundancy", "call_home"):
            assert host_vars[key] is None, (
                f"{key} defaults to a truthy empty container, which renders a "
                "header for a device that does not have one")

    def test_interface_only_config_invents_nothing(self):
        config = "hostname R99\ninterface GigabitEthernet0/1\n shutdown\n"
        report = roundtrip.validate_device(config, "cisco_ios")
        assert report["extra_in_render"] == 0
        assert report["round_trip_fidelity"] == 100.0
