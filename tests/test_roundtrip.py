"""Round-trip validation against real sanitized configs.

Built against `tests/fixtures/configs/`, not only synthetic snippets: a parser
that handles configs I wrote is not evidence of much.

Central properties:

* **Fidelity** — render(extract(config)) reproduces the config.
* **Fixed point** — extract → render → extract again produces byte-identical
  YAML. This catches parser/template asymmetries that comparison normalisation
  would otherwise hide, e.g. a parser that accepts two spellings and a template
  that only emits one.
* **Ordering policy** — a reordered ACL fails; reordered BGP neighbors pass.
"""

import os

import pytest

from modules.nsot import hostvars, roundtrip
from modules.nsot.parsers import get_parser

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "configs")

DEVICES = [
    ("s1_vios_l2.cfg", "cisco_ios", "s1"),
    ("r1_c8000v.cfg", "cisco_xe", "r1"),
]


def _config(filename):
    with open(os.path.join(FIXTURES, filename), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(params=DEVICES, ids=[d[2] for d in DEVICES])
def device(request):
    filename, platform, hostname = request.param
    return {"config": _config(filename), "platform": platform, "hostname": hostname}


class TestRoundTripFidelity:
    def test_renders_without_error(self, device):
        report = roundtrip.validate_device(device["config"], device["platform"])
        assert not report.get("error"), report.get("error")

    def test_nothing_missing_from_render(self, device):
        report = roundtrip.validate_device(device["config"], device["platform"])
        missing = report["details"]["missing"]
        assert missing == [], f"{len(missing)} line(s) not reproduced: " + \
            "; ".join(m["line"][:60] for m in missing[:5])

    def test_nothing_extra_in_render(self, device):
        report = roundtrip.validate_device(device["config"], device["platform"])
        extra = report["details"]["extra"]
        assert extra == [], f"{len(extra)} invented line(s): " + \
            "; ".join(e["line"][:60] for e in extra[:5])

    def test_full_fidelity(self, device):
        report = roundtrip.validate_device(device["config"], device["platform"])
        assert report["round_trip_fidelity"] == 100.0
        assert report["ok"] is True

    def test_modeled_coverage_meets_threshold(self, device):
        """The agreed bar: under 80% means extend 3a rather than narrow 3b."""
        report = roundtrip.validate_device(device["config"], device["platform"])
        assert report["modeled_coverage"] >= 80.0, (
            f"{device['hostname']} modelled only {report['modeled_coverage']}%")

    def test_hostname_extracted(self, device):
        report = roundtrip.validate_device(device["config"], device["platform"])
        assert report["hostname"] == device["hostname"]


class TestFixedPoint:
    """extract → render → extract again must be byte-identical."""

    def test_yaml_is_a_fixed_point(self, device):
        parser = get_parser(device["platform"])

        first = parser.parse(device["config"])
        rendered = roundtrip.render(first, first["platform"])
        second = parser.parse(rendered)

        yaml_one = hostvars.to_yaml(first)
        yaml_two = hostvars.to_yaml(second)
        assert yaml_one == yaml_two, (
            "extract→render→extract changed the YAML — the parser and template "
            "disagree about some construct")

    def test_to_yaml_is_a_fixed_point_at_its_own_boundary(self, device):
        """The serialiser, tested where the stores actually cross it.

        The test above feeds the **parser's** output in twice, and the parser
        always produces a ``secrets`` key — so ``to_yaml`` was only ever
        exercised on input it had not itself produced. Both host_vars stores
        round-trip through ``from_yaml``/``to_yaml``, and on that path the key
        is gone, which is where it silently emptied ``secret_refs``.

        Any serialiser two stores round-trip through needs this asserted
        directly, not inferred from a test of the thing that feeds it.
        """
        parser = get_parser(device["platform"])
        once = hostvars.to_yaml(parser.parse(device["config"]))
        twice = hostvars.to_yaml(hostvars.from_yaml(once))
        assert twice == once, (
            f"{device['hostname']}: to_yaml(from_yaml(to_yaml(x))) != to_yaml(x) "
            "— the serialiser loses information about its own output")

    def test_to_yaml_is_stable_under_repeated_passes(self, device):
        parser = get_parser(device["platform"])
        text = hostvars.to_yaml(parser.parse(device["config"]))
        for _ in range(3):
            text = hostvars.to_yaml(hostvars.from_yaml(text))
        assert text == hostvars.to_yaml(
            hostvars.from_yaml(hostvars.to_yaml(parser.parse(device["config"]))))

    def test_secret_refs_survive_the_serialiser_boundary(self, device):
        """Named separately because this is the field that was lost."""
        parser = get_parser(device["platform"])
        parsed = parser.parse(device["config"])
        expected = sorted((parsed.get("secrets") or {}).keys())

        twice = hostvars.from_yaml(
            hostvars.to_yaml(hostvars.from_yaml(hostvars.to_yaml(parsed))))
        assert twice["secret_refs"] == expected, (
            f"{device['hostname']}: expected {expected}, "
            f"got {twice['secret_refs']}")

    def test_second_render_is_identical(self, device):
        parser = get_parser(device["platform"])
        first = parser.parse(device["config"])
        render_one = roundtrip.render(first, first["platform"])
        render_two = roundtrip.render(parser.parse(render_one), first["platform"])
        assert render_one == render_two

    def test_secrets_survive_the_round_trip(self, device):
        """A hash must come back byte-identical: it cannot be regenerated."""
        parser = get_parser(device["platform"])
        first = parser.parse(device["config"])
        rendered = roundtrip.render(first, first["platform"])
        second = parser.parse(rendered)
        assert first["secrets"] == second["secrets"]
        for value in first["secrets"].values():
            assert value in rendered, f"secret {value[:12]}… not emitted verbatim"


class TestOrderingPolicy:
    """Ordered by default; unordered only where the device treats it as a set."""

    ACL_CONFIG = """hostname R9
ip access-list standard BLOCKLIST
 10 permit 203.0.113.1
 20 deny   203.0.113.2
 30 permit any
"""

    BGP_CONFIG = """hostname R9
router bgp 65001
 neighbor 203.0.113.1 remote-as 65002
 neighbor 203.0.113.2 remote-as 65003
 neighbor 203.0.113.3 remote-as 65004
"""

    def test_acl_is_order_significant(self):
        assert not roundtrip.section_is_unordered("ip access-list standard BLOCKLIST")

    def test_reordered_acl_is_reported(self):
        """A reordered ACL is a traffic-behaviour change, not an equivalence."""
        reordered = self.ACL_CONFIG.replace(
            " 10 permit 203.0.113.1\n 20 deny   203.0.113.2\n",
            " 20 deny   203.0.113.2\n 10 permit 203.0.113.1\n")
        report = roundtrip.compare(self.ACL_CONFIG, reordered)
        assert report["reordered_sections"] == 1
        assert report["ok"] is False

    def test_bgp_neighbors_are_order_insensitive(self):
        assert roundtrip.section_is_unordered("router bgp 65001")

    def test_reordered_bgp_neighbors_pass(self):
        reordered = self.BGP_CONFIG.replace(
            " neighbor 203.0.113.1 remote-as 65002\n neighbor 203.0.113.2 remote-as 65003\n",
            " neighbor 203.0.113.2 remote-as 65003\n neighbor 203.0.113.1 remote-as 65002\n")
        report = roundtrip.compare(self.BGP_CONFIG, reordered)
        assert report["ok"] is True
        assert report["reordered_sections"] == 0

    def test_prefix_lists_and_route_maps_are_ordered(self):
        for section in ("ip prefix-list PL-IN", "route-map RM-OUT permit 10",
                        "policy-map PM", "class-map CM", "ip sla 1"):
            assert not roundtrip.section_is_unordered(section), section

    def test_interface_bodies_are_unordered(self):
        """IOS reorders interface sub-commands itself, so their order is not ours."""
        assert roundtrip.section_is_unordered("interface GigabitEthernet0/1")

    def test_missing_acl_entry_is_not_hidden_by_reorder_logic(self):
        shorter = self.ACL_CONFIG.replace(" 20 deny   203.0.113.2\n", "")
        report = roundtrip.compare(self.ACL_CONFIG, shorter)
        assert report["missing_from_render"] == 1
        assert report["reordered_sections"] == 0


class TestCoverageAccounting:
    def test_unmodeled_counts_against_modeled_coverage(self):
        """A line parked in a pass-through block round-trips but is not modelled."""
        report = roundtrip.compare(
            "hostname R9\nfoo bar\n", "hostname R9\nfoo bar\n",
            host_vars={"unmodeled": [{"line": "foo bar", "children": []}],
                       "interfaces": []})
        assert report["unmodeled"] == 1
        assert report["round_trip_fidelity"] == 100.0
        assert report["modeled_coverage"] < 100.0

    def test_fidelity_and_coverage_answer_different_questions(self, device):
        report = roundtrip.validate_device(device["config"], device["platform"])
        assert report["round_trip_fidelity"] >= report["modeled_coverage"]

    def test_ranked_unmodeled_lists_devices(self):
        reports = [roundtrip.validate_device(_config(f), p) for f, p, _ in DEVICES]
        ranked = roundtrip.rank_unmodeled(reports)
        assert all("construct" in r and "devices" in r for r in ranked)
        assert ranked == sorted(ranked, key=lambda r: -r["occurrences"])


class TestInterfaceNameNormalisation:
    def test_abbreviated_and_full_names_compare_equal(self):
        short = "interface Gi0/1\n description uplink\n"
        long = "interface GigabitEthernet0/1\n description uplink\n"
        assert roundtrip.compare(short, long)["ok"] is True

    def test_references_inside_lines_are_normalised(self):
        a = "router rip\n passive-interface Gi0/2\n"
        b = "router rip\n passive-interface GigabitEthernet0/2\n"
        assert roundtrip.compare(a, b)["ok"] is True


class TestRealNmasGoldenShape:
    """A golden file as NMAS actually writes it, not as the device prints it.

    Every fixture in this repo was built from raw device output. A golden file
    on a real NMAS has three extra header lines NMAS adds itself, plus the two
    lines IOS prints above `show running-config`:

        ! Golden config — s4 (203.0.113.24)
        ! Saved: 2026-09-15 22:36:40
        ! Source: show startup-config
        Building configuration...
        Current configuration : 4240 bytes

    None of those can be rendered from a template, and `strip_for_roundtrip`
    was not removing them — so the first run against the real fleet reported
    exactly five unreproducible lines on all nine devices. The fixtures could
    not have caught it, because the fixtures were the wrong shape.
    """

    NMAS_HEADER = (
        "! Golden config — s4 (203.0.113.24)\n"
        "! Saved: 2026-09-15 22:36:40\n"
        "! Source: show startup-config\n"
        "!\n"
        "Building configuration...\n"
        "\n"
        "Current configuration : 4240 bytes\n"
    )

    def _as_nmas_golden(self, raw: str) -> str:
        """Wrap raw device output the way NMAS stores it."""
        return self.NMAS_HEADER + raw

    @pytest.mark.parametrize("filename,platform,hostname", DEVICES,
                             ids=[d[2] for d in DEVICES])
    def test_round_trips_with_the_nmas_header(self, filename, platform, hostname):
        wrapped = self._as_nmas_golden(_config(filename))
        report = roundtrip.validate_device(wrapped, platform)
        assert report["missing_from_render"] == 0, (
            "lines NMAS adds to a golden file were treated as config: "
            + "; ".join(m["line"] for m in report["details"]["missing"][:5]))
        assert report["extra_in_render"] == 0

    @pytest.mark.parametrize("filename,platform,hostname", DEVICES,
                             ids=[d[2] for d in DEVICES])
    def test_header_does_not_change_the_verdict(self, filename, platform, hostname):
        """Wrapping a config must not alter what the validator concludes."""
        raw = _config(filename)
        bare = roundtrip.validate_device(raw, platform)
        wrapped = roundtrip.validate_device(self._as_nmas_golden(raw), platform)
        assert wrapped["round_trip_fidelity"] == bare["round_trip_fidelity"]
        assert wrapped["modeled_coverage"] == bare["modeled_coverage"]

    def test_each_header_line_is_stripped(self):
        from modules.nsot.normalize import strip_for_roundtrip

        out = strip_for_roundtrip(self._as_nmas_golden("hostname s4\n"))
        joined = "\n".join(out)
        for line in ("! Golden config", "! Saved:", "! Source:",
                     "Building configuration", "Current configuration"):
            assert line not in joined, f"{line!r} survived stripping"
        assert "hostname s4" in joined

    def test_byte_count_line_is_not_mistaken_for_config(self):
        """`Current configuration : N bytes` varies with the config itself."""
        from modules.nsot.normalize import strip_for_roundtrip

        for size in (4240, 8905, 1):
            out = strip_for_roundtrip(f"Current configuration : {size} bytes\nhostname x\n")
            assert out == ["hostname x"]
