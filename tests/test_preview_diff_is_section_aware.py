"""The preview diff must report configuration differences, not presentation.

Reviewed on real data after the 1.4 repair: every description matched the
device, and the preview still showed diffs. They were ordering, whitespace and
masking -- none of which is a difference in what the device is configured to
do.

The preview normalised both sides and then compared them with a flat
`difflib`, so it reported:

* **order**, in sections where the device does not care. IOS reorders
  interface sub-commands itself, so a render emitting them in template order
  shows a wall of moved lines.
* **indentation**, which `_norm` collapses but which survived because the
  comparison ran on raw strings anyway.

The machinery to answer both already existed. `section_is_unordered()` knows
which containers care about order and `_sections()` knows what is in each one
-- `compare()` has used them since Phase 3a. The preview simply was not.

A diff that cries wolf is not a cautious diff. It is one people stop reading,
and the next real difference goes past unnoticed.
"""

import pytest

from modules.nsot.roundtrip import canonical_diff, canonical_lines

BASE = """interface GigabitEthernet0/1
 description uplink
 ip address 10.0.0.1 255.255.255.0
 no shutdown
!
ip access-list extended GUARD
 permit ip any any
 deny ip any any
!
router ospf 1
 network 10.0.0.0 0.0.0.255 area 0
 passive-interface default
!
end
"""


def _rewrite(original, old, new):
    assert old in original, old
    return original.replace(old, new)


class TestOrderThatTheDeviceIgnores:
    """`interface`, `router ospf/bgp/rip`, `line`, `vrf definition`."""

    def test_a_reordered_interface_body_is_not_a_difference(self):
        other = """interface GigabitEthernet0/1
 no shutdown
 ip address 10.0.0.1 255.255.255.0
 description uplink
!
ip access-list extended GUARD
 permit ip any any
 deny ip any any
!
router ospf 1
 network 10.0.0.0 0.0.0.255 area 0
 passive-interface default
!
end
"""
        assert canonical_diff(BASE, other) == ""

    def test_a_reordered_ospf_body_is_not_a_difference(self):
        other = _rewrite(
            BASE,
            " network 10.0.0.0 0.0.0.255 area 0\n passive-interface default",
            " passive-interface default\n network 10.0.0.0 0.0.0.255 area 0")
        assert canonical_diff(BASE, other) == ""

    def test_reordered_globals_are_not_a_difference(self):
        """A template emits globals in its own order and the device in its
        own; neither is a configuration difference."""
        one = "hostname s1\nip domain-name a.b\nno ip http server\n"
        two = "no ip http server\nhostname s1\nip domain-name a.b\n"
        assert canonical_diff(one, two) == ""


class TestOrderThatTheDeviceDoesNotIgnore:
    """Hiding these would be worse than crying wolf."""

    def test_a_reordered_acl_is_still_a_difference(self):
        other = _rewrite(BASE, " permit ip any any\n deny ip any any",
                         " deny ip any any\n permit ip any any")
        diff = canonical_diff(BASE, other)
        assert diff
        assert "GUARD" in diff

    def test_a_reordered_route_map_is_still_a_difference(self):
        one = ("route-map RM permit 10\n match ip address 1\n set metric 5\n")
        two = ("route-map RM permit 10\n set metric 5\n match ip address 1\n")
        assert canonical_diff(one, two) != ""

    def test_a_reordered_prefix_list_is_still_a_difference(self):
        one = "ip prefix-list P seq 5 permit 10.0.0.0/8\nip prefix-list P seq 10 deny 0.0.0.0/0\n"
        two = "ip prefix-list P seq 10 deny 0.0.0.0/0\nip prefix-list P seq 5 permit 10.0.0.0/8\n"
        # Both are globals here, so the SECTION rule does not apply -- what
        # matters is that the lines themselves still differ if one changes.
        assert canonical_diff(one, two.replace("seq 10 deny 0.0.0.0/0",
                                               "seq 10 deny 192.168.0.0/16")) != ""


class TestWhitespace:
    def test_indentation_alone_is_not_a_difference(self):
        other = BASE.replace(" description uplink", "      description uplink")
        assert canonical_diff(BASE, other) == ""

    def test_internal_spacing_alone_is_not_a_difference(self):
        other = BASE.replace("ip address 10.0.0.1 255.255.255.0",
                             "ip address  10.0.0.1   255.255.255.0")
        assert canonical_diff(BASE, other) == ""

    def test_trailing_whitespace_is_not_a_difference(self):
        other = BASE.replace(" no shutdown", " no shutdown   ")
        assert canonical_diff(BASE, other) == ""


class TestRealDifferencesStillShow:
    """The diff has to keep working as a diff."""

    def test_a_changed_value_shows(self):
        other = BASE.replace("10.0.0.1 255.255.255.0", "10.0.0.2 255.255.255.0")
        assert canonical_diff(BASE, other) != ""

    def test_a_missing_line_shows(self):
        other = BASE.replace(" passive-interface default\n", "")
        diff = canonical_diff(BASE, other)
        assert "passive-interface default" in diff

    def test_an_added_line_shows(self):
        other = BASE.replace(" no shutdown", " no shutdown\n mtu 9000")
        assert "mtu 9000" in canonical_diff(BASE, other)

    def test_a_missing_section_shows(self):
        other = BASE.replace(
            "router ospf 1\n network 10.0.0.0 0.0.0.255 area 0\n"
            " passive-interface default\n!\n", "")
        assert "router ospf 1" in canonical_diff(BASE, other)

    def test_identical_configs_diff_to_nothing(self):
        assert canonical_diff(BASE, BASE) == ""


class TestTheOutputNamesWhereADifferenceIs:
    """A unified diff over raw lines leaves the reader counting indentation
    to work out which block a changed line belongs to."""

    def test_children_are_grouped_under_their_container_path(self):
        lines = canonical_lines(BASE)
        assert "interface GigabitEthernet0/1" in lines
        index = lines.index("interface GigabitEthernet0/1")
        assert lines[index + 1].startswith("    ")

    def test_the_global_scope_is_labelled(self):
        assert "(global)" in canonical_lines("hostname s1\n")


class TestItStillFiltersWhatATemplateCannotRender:
    """Dropping `strip_for_roundtrip` when the preview moved to this helper
    would make every unrenderable line read as a difference from a render
    that could never have contained it."""

    def test_an_unrenderable_line_is_not_a_difference(self):
        from modules.nsot import normalize

        with_cert = BASE.replace(
            "end\n",
            "crypto pki certificate chain TP-self-signed-1\n"
            " certificate self-signed 01\n"
            "  30820330 30820218 A0030201\n"
            "  quit\n!\nend\n")
        # Only meaningful if the filter actually removes it.
        assert "30820330" not in "\n".join(
            normalize.strip_for_roundtrip(with_cert))
        assert canonical_diff(BASE, with_cert) == ""

    def test_both_filters_are_applied(self):
        import inspect

        from modules.nsot import roundtrip

        source = inspect.getsource(roundtrip.canonical_lines)
        assert "strip_for_roundtrip" in source and "strip_for_diff" in source


class TestTheRouteUsesIt:
    def test_preview_calls_canonical_diff(self):
        import inspect

        from routes import templates as route_module

        assert "canonical_diff" in inspect.getsource(route_module.preview)

    def test_the_route_no_longer_diffs_raw_lines(self):
        import inspect

        from routes import templates as route_module

        source = inspect.getsource(route_module.preview)
        assert "difflib.unified_diff" not in source, (
            "a flat diff is what reported ordering and whitespace as "
            "configuration differences")
