"""A description is prose, not configuration this tool may rewrite.

`canonicalise_line()` expands every interface reference in a line, which is
right for `passive-interface Gi0/2` and `ip route ... Gi0/0`, and wrong inside
a `description`: `link to Gi0/1 spare` is what an operator chose to write, and
rewriting it to `GigabitEthernet0/1` changes what the device was configured to
say.

**It hid itself.** Both sides of every comparison go through this function, so
the expanded text matched the expanded text and the diff came back clean while
`host_vars` and the device disagreed. Measured on the live fleet: s1's
committed intent holds `GigabitEthernet3` where the device says `Gi3`.

That is the same shape as the flattened BGP address-families -- parse and
render were symmetric, so both sides agreed with each other while both
disagreed with the device.
"""

import pytest

from modules.nsot.ifnames import FREE_FORM_COMMANDS, canonicalise_line


class TestFreeFormArgumentsAreLeftAlone:
    @pytest.mark.parametrize("line", [
        " description link to Gi0/1 spare",
        " description Gi3",
        " description uplink Te1/1/1 to core",
        " remark permit from Gi0/1",
        " name Gi3-vlan",
        " banner motd ^ do not touch Gi0/0 ^",
    ])
    def test_it_is_returned_verbatim(self, line):
        assert canonicalise_line(line) == line

    def test_a_negated_free_form_line_too(self):
        assert canonicalise_line(" no description Gi3") == " no description Gi3"

    def test_leading_indentation_is_preserved(self):
        """These lines live inside an interface block; losing the indent
        would change which section they belong to."""
        assert canonicalise_line("  description Gi3").startswith("  ")

    def test_the_exempt_list_is_the_one_deploy_uses(self):
        """One list, not two. `deploy` needs it to decide whether a broad
        command key may match a prior value; this module needs it to know
        whose argument not to rewrite. Two copies of a rule that has already
        been wrong in both directions would drift."""
        from modules.nsot.deploy import FREE_FORM_COMMANDS as from_deploy

        assert from_deploy is FREE_FORM_COMMANDS


class TestEverythingElseStillExpands:
    """The exemption must not become a hole."""

    @pytest.mark.parametrize("line,expected", [
        ("interface Gi3", "interface GigabitEthernet3"),
        (" passive-interface Gi0/2", " passive-interface GigabitEthernet0/2"),
        (" ip route 0.0.0.0 0.0.0.0 Gi0/0",
         " ip route 0.0.0.0 0.0.0.0 GigabitEthernet0/0"),
        (" track 1 interface Gi0/2 line-protocol",
         " track 1 interface GigabitEthernet0/2 line-protocol"),
        (" snmp-server trap-source Gi0/0",
         " snmp-server trap-source GigabitEthernet0/0"),
    ])
    def test_references_are_canonicalised(self, line, expected):
        assert canonicalise_line(line) == expected

    def test_a_word_merely_starting_with_a_keyword_is_not_exempt(self):
        """`descriptions` is not `description`, and a prefix match would
        exempt commands nobody meant to exempt."""
        assert canonicalise_line("descriptionx Gi3") != "descriptionx Gi3"

    def test_an_empty_line_survives(self):
        assert canonicalise_line("") == ""
        assert canonicalise_line(None) is None


class TestTheDefectIsVisibleAgain:
    """The point of the fix: the two sides must now disagree when they do."""

    def test_an_abbreviated_description_no_longer_matches_an_expanded_one(self):
        device = " description link to Gi3"
        committed = " description link to GigabitEthernet3"
        assert canonicalise_line(device) != canonicalise_line(committed), (
            "both sides expanded to the same text, which is how the damage "
            "stayed invisible in every diff")

    def test_before_the_fix_they_would_have_matched(self):
        """Pins what was wrong, so the test explains itself in a year.

        This reconstructs the OLD behaviour -- unconditional expansion -- and
        shows it erasing the difference.
        """
        import re

        from modules.nsot import ifnames

        old = lambda line: ifnames._LINE_RE.sub(
            lambda m: ifnames.canonical(f"{m.group(1)}{m.group(2)}"), line)
        assert old(" description link to Gi3") == old(
            " description link to GigabitEthernet3")


class TestRoundTripSeesItToo:
    """`roundtrip` normalises through the same function, so the comparison
    that reports fidelity inherits the fix."""

    def test_a_description_difference_is_no_longer_normalised_away(self):
        from modules.nsot import roundtrip

        left = roundtrip._norm(" description link to Gi3")
        right = roundtrip._norm(" description link to GigabitEthernet3")
        assert left != right
