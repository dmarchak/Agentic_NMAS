"""Stage 4C.5 — the RW community goes, and the nine RO communities stay.

vrnetlab nodes arrive with a read-**write** `public` community. It is removed
as part of onboarding rather than after, because a device that has been in
the inventory for a week with a writable community is a device that was
writable for a week.

**The risk is over-broadening, not under-matching.** A pattern matching any
`snmp-server community` would propose removing all nine of the fleet's
read-only communities and take Prometheus, the SNMP collector and the trap
receiver with them. So the access mode is required in the match, and the
fleet fixtures are the test: every one of the nine carries
`snmp-server community public RO`, and not one of them may be proposed for
removal.
"""

import glob
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")


@pytest.fixture(scope="module")
def fleet():
    paths = sorted(glob.glob(os.path.join(FLEET, "*.cfg")))
    # Not vacuous: nine devices, measured. An empty glob would make every
    # "nothing was touched" assertion below trivially true -- the
    # set-difference rule, applied to a directory listing.
    assert len(paths) == 9, f"expected the nine reference devices, got {len(paths)}"
    return {os.path.basename(p): open(p, encoding="utf-8").read() for p in paths}


class TestTheNineAreUntouched:
    """The acceptance that matters. Over-broadening is the version that costs
    you monitoring."""

    def test_every_fixture_has_an_ro_community(self, fleet):
        """The premise. If they did not, the tests below would pass by
        having nothing to protect."""
        from modules.nsot.onboard import ro_communities

        for name, text in fleet.items():
            assert ro_communities(text), name

    def test_not_one_ro_community_is_proposed_for_removal(self, fleet):
        from modules.nsot.onboard import rw_removal_plan

        for name, text in fleet.items():
            plan = rw_removal_plan(text)
            assert plan["remove"] == [], (name, plan["remove"])

    def test_the_ro_communities_are_reported_as_KEPT(self, fleet):
        """Shown next to what is removed: an operator reading "1 removed" on
        a device with two communities needs to know which."""
        from modules.nsot.onboard import rw_removal_plan

        for name, text in fleet.items():
            assert rw_removal_plan(text)["keep"], name

    def test_a_device_with_both_keeps_the_ro_and_removes_the_rw(self, fleet):
        text = fleet["r1.cfg"] + "\nsnmp-server community secretwrite RW\n"
        from modules.nsot.onboard import rw_removal_plan

        plan = rw_removal_plan(text)
        assert plan["remove"] == ["no snmp-server community secretwrite RW"]
        assert any("RO" in line for line in plan["keep"])


class TestTheMatchRequiresTheAccessMode:

    def test_rw_matches(self):
        from modules.nsot.onboard import rw_communities

        assert rw_communities("snmp-server community public RW") == [
            "snmp-server community public RW"]

    def test_ro_does_not(self):
        from modules.nsot.onboard import rw_communities

        assert rw_communities("snmp-server community public RO") == []

    def test_a_community_with_no_mode_does_not_match(self):
        """IOS defaults it to RO. Removing a line on the strength of an
        assumption about a default is not a removal anybody reviewed."""
        from modules.nsot.onboard import rw_communities

        assert rw_communities("snmp-server community public") == []

    def test_a_name_containing_rw_does_not_match(self):
        """`\\b` on the mode, not a substring of the community name."""
        from modules.nsot.onboard import rw_communities

        assert rw_communities("snmp-server community RWTEAM RO") == []

    def test_an_unrelated_snmp_line_does_not_match(self):
        from modules.nsot.onboard import rw_communities

        assert rw_communities("snmp-server host 10.0.0.1 version 2c public") == []
        assert rw_communities("snmp-server location RW closet") == []

    def test_case_is_not_the_discriminator(self):
        from modules.nsot.onboard import rw_communities

        assert rw_communities("snmp-server community public rw") != []


class TestTheRemovalIsVerbatim:
    """A reconstructed line can differ from the device's own in the ACL, the
    view or the spacing, and `no snmp-server community public RW` against a
    device whose line reads `… RW 99` is a command that does not match."""

    def test_an_acl_is_carried_through(self):
        from modules.nsot.onboard import rw_removal_plan

        plan = rw_removal_plan("snmp-server community public RW 99")
        assert plan["remove"] == ["no snmp-server community public RW 99"]

    def test_a_view_is_carried_through(self):
        from modules.nsot.onboard import rw_removal_plan

        plan = rw_removal_plan("snmp-server community sec RW ipv6 acl6")
        assert plan["remove"] == ["no snmp-server community sec RW ipv6 acl6"]

    def test_leading_whitespace_is_stripped_from_the_command(self):
        from modules.nsot.onboard import rw_removal_plan

        assert rw_removal_plan("  snmp-server community public RW")["remove"] == [
            "no snmp-server community public RW"]

    def test_the_removal_is_not_rebuilt_from_the_name(self):
        """If it were, the ACL would be dropped and the command would not
        match the device's line."""
        import inspect

        from modules.nsot import onboard

        src = inspect.getsource(onboard.rw_removal_plan)
        assert "group('name')" not in src and "groupdict" not in src


class TestMultipleAndNone:

    def test_two_rw_communities_are_both_removed(self):
        from modules.nsot.onboard import rw_removal_plan

        plan = rw_removal_plan("snmp-server community a RW\n"
                               "snmp-server community b RW\n")
        assert len(plan["remove"]) == 2

    def test_a_clean_device_proposes_nothing(self):
        from modules.nsot.onboard import rw_removal_plan

        assert rw_removal_plan("hostname r6\n!\nend\n")["remove"] == []

    def test_an_empty_capture_proposes_nothing(self):
        from modules.nsot.onboard import rw_removal_plan

        assert rw_removal_plan("")["remove"] == []
        assert rw_removal_plan(None)["remove"] == []
