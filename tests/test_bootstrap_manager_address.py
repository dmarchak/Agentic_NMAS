"""The bootstrap config must reach the manager, and stay a bootstrap config.

4C.8. Found by running the probe on hardware: every unit passed, and the
artefact they all agreed about could not be reached by anything.

Measured 2026-09-23 -- the NMAS is on `enp6s19` at 10.255.0.10/24, s3's
`Vlan99` is the gateway at 10.255.0.1, and every device's 10.255.1.x is a
/32 loopback advertised into OSPF. So reproducing how r1-r5 are reached
would put a Loopback0, a core-segment address and `router ospf 1` into a
config whose whole point is to have no routing.

**Both properties are asserted here, because they pull against each other.**
The config must carry enough to be reachable (an address) and no more (no
IGP, no loopback, no route). A test for either one alone is satisfied by a
generator that fails the other.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules.nsot.bootstrap_config import (  # noqa: E402
    ManagementAddressRequired, ManagementInterfaceRefused,
    ReservedInterface, render_bootstrap)

#: The verified-free probe address. Confirmed three ways on 2026-09-23:
#: NetBox held exactly one address in 10.255.0.0/24 (s3's Vlan99), .31/.32/.33
#: were silent to ping, and the neighbour table on enp6s19 showed them
#: INCOMPLETE with s3 the only REACHABLE entry.
ADDRESS = "10.255.0.31"
MASK = "255.255.255.0"

#: Gi2, not Gi1. On a C8000v vrnetlab owns Gi1.
IOSXE_IF = "GigabitEthernet2"


def _render(platform="cisco_iosxe", **over):
    args = dict(hostname="bp-onboard-c", username="admin", secret="abc12345",
                manager_interface=IOSXE_IF, manager_address=ADDRESS,
                manager_mask=MASK)
    args.update(over)
    return render_bootstrap(platform, **args)


def _lines(text):
    return [ln.strip() for ln in text.splitlines()]


class TestItCarriesEnoughToBeReached:

    def test_the_address_is_emitted_on_the_named_interface(self):
        out = _render()
        lines = _lines(out)
        assert f"interface {IOSXE_IF}" in lines
        assert f"ip address {ADDRESS} {MASK}" in lines

    def test_the_interface_is_brought_up(self):
        """An addressed interface that is down is the same as no address,
        and is the version that looks correct in a diff."""
        out = _render()
        body = out.split(f"interface {IOSXE_IF}")[1].split("!")[0]
        assert "no shutdown" in body, body

    def test_both_platforms_emit_it(self):
        """A generator that treated only one platform would produce an
        unreachable device on the other -- the same asymmetry that made the
        vIOS's clab interface explicit and the C8000v's absent."""
        for platform, iface in (("cisco_iosxe", IOSXE_IF),
                                ("cisco_ios", "GigabitEthernet0/1")):
            out = _render(platform, manager_interface=iface)
            assert f"ip address {ADDRESS} {MASK}" in _lines(out), platform

    def test_a_vios_manager_port_is_routed(self):
        """`no switchport` on an L2 platform, or the address is refused by
        the device rather than by this generator."""
        out = _render("cisco_ios", manager_interface="GigabitEthernet0/1")
        body = out.split("interface GigabitEthernet0/1")[1].split("!")[0]
        assert "no switchport" in body, body


class TestItStaysABootstrapConfig:
    """The other half. See the module docstring: these pull against each
    other, and a generator can satisfy either one alone."""

    def test_no_routing_protocol(self):
        for platform, iface in (("cisco_iosxe", IOSXE_IF),
                                ("cisco_ios", "GigabitEthernet0/1")):
            out = _render(platform, manager_interface=iface)
            assert "router ospf" not in out, platform
            assert "router bgp" not in out, platform
            assert "router rip" not in out, platform

    def test_no_loopback(self):
        """10.255.1.x is a loopback range reachable only through OSPF.
        Emitting one here would be the IGP-participation version of this
        step, which §8.3 rejected."""
        for platform, iface in (("cisco_iosxe", IOSXE_IF),
                                ("cisco_ios", "GigabitEthernet0/1")):
            assert "Loopback" not in _render(platform,
                                             manager_interface=iface), platform

    def test_no_route_when_no_gateway_is_given(self):
        """The manager is on this subnet and always initiates, so the device
        needs no route to answer it. A default gateway written when nothing
        needs one is a routing statement in a config whose point is to have
        none."""
        for platform, iface in (("cisco_iosxe", IOSXE_IF),
                                ("cisco_ios", "GigabitEthernet0/1")):
            out = _render(platform, manager_interface=iface)
            assert "ip route" not in out, platform

    def test_a_gateway_IS_emitted_when_one_is_given(self):
        """The positive control for the test above.

        Without it, `no "ip route" in out` would pass just as happily against
        a generator that had no gateway support at all -- a "nothing is
        wrong" assertion with nothing to distinguish it from absence.
        """
        out = _render(manager_gateway="10.255.0.1")
        assert "ip route 0.0.0.0 0.0.0.0 10.255.0.1" in _lines(out)


class TestItRefusesRatherThanGuesses:

    def test_no_interface_is_refused_not_defaulted(self):
        """A C8000v whose management address landed on Gi1 -- vrnetlab's --
        is the failure this step exists to prevent. A default is how a guess
        becomes a silent one."""
        with pytest.raises(ManagementAddressRequired) as excinfo:
            _render(manager_interface="")
        assert "interface" in str(excinfo.value)

    def test_no_mask_is_refused(self):
        with pytest.raises(ManagementAddressRequired) as excinfo:
            _render(manager_mask="")
        assert "mask" in str(excinfo.value)

    def test_an_interface_without_an_address_is_refused(self):
        """The half-supplied case. Emitting a bare `interface Gi2` stanza
        would be a config that looks configured and carries nothing."""
        with pytest.raises(ManagementAddressRequired):
            _render(manager_address="")


class TestTheGuardStillCoversEverything:

    def test_the_new_lines_are_ascii(self):
        """`assert_sendable` runs over the whole render, so this passes by
        construction -- and is asserted anyway, because the em dash has
        broken this rule twice and the description is prose."""
        out = _render()
        offenders = [ln for ln in out.splitlines()
                     if any(ord(c) > 126 for c in ln)]
        assert not offenders, offenders

    def test_a_config_with_no_manager_address_still_renders(self):
        """The probe fixtures and the platform-shape tests render without
        one, so this must stay legal at the generator. `build_plan` is where
        it becomes a blocking reason -- the gate belongs where an operator
        can be told about it, not where a fixture would trip over it."""
        out = render_bootstrap("cisco_iosxe", hostname="r6",
                               username="admin", secret="abc12345")
        assert "ip address" not in out
        assert out.rstrip().endswith("end")


# ---------------------------------------------------------------------------
# The interface belongs to something else, or is not a name at all
# ---------------------------------------------------------------------------

class TestTheReservedInterfaceIsRefused:
    """`VRNETLAB_OWNS_FIRST_INTERFACE` was a set named for a reservation and
    used only to pick a stanza SHAPE. Nothing consulted it as a rule, so

        render_bootstrap("cisco_iosxe", manager_interface="GigabitEthernet1")

    emitted the management address on vrnetlab's own interface. That is the
    stage-B shape reproduced inside the tool built to prevent it: the node
    boots, reports healthy, answers its console, and is unreachable.

    *"The rule now holds from both ends"* had been asserted and agreed. It
    held at one end — `test_probe_topologies.py` refused a topology that
    **cabled** Gi1, and nothing refused a config that **addressed** it.
    """

    def test_the_platforms_own_interface_is_refused(self):
        with pytest.raises(ReservedInterface) as excinfo:
            _render(manager_interface="GigabitEthernet1")
        assert "vrnetlab owns Gi1" in str(excinfo.value)

    def test_the_short_spelling_is_refused_too(self):
        """Canonicalised BEFORE comparison. A check that knew only the long
        form would refuse `GigabitEthernet1` and wave `Gi1` through — the
        shorter, likelier spelling walking past the gate."""
        with pytest.raises(ReservedInterface):
            _render(manager_interface="Gi1")
        with pytest.raises(ReservedInterface):
            _render(manager_interface="gi1")

    def test_the_vios_clab_interface_is_refused(self):
        """Its bootstrap already gives Gi0/0 `ip address dhcp`. Two stanzas
        for one interface is not a configuration, it is a race."""
        with pytest.raises(ReservedInterface):
            _render("cisco_ios", manager_interface="GigabitEthernet0/0")

    def test_the_conflict_is_also_caught_dynamically(self):
        """Whatever THIS render is configuring as the containerlab
        interface, whatever it is called and on whichever platform."""
        with pytest.raises(ReservedInterface) as excinfo:
            _render("cisco_ios", manager_interface="Gi0/2",
                    mgmt_interface="GigabitEthernet0/2")
        assert "already being configured" in str(excinfo.value)

    def test_a_permitted_interface_still_renders(self):
        """The control. A refusal that refused everything would pass every
        test above and ship a generator that emits nothing."""
        out = _render(manager_interface="GigabitEthernet2")
        assert f"ip address {ADDRESS} {MASK}" in _lines(out)
        out = _render("cisco_ios", manager_interface="Gi0/1")
        assert "interface GigabitEthernet0/1" in _lines(out)


class TestTheSpellingIsCheckedAgainstTheSharedTable:
    """Validated against `ifnames.INTERFACE_PREFIXES`, not a second regex.

    That table already owns interface spelling for the whole program, and
    `ifnames` exists because two display maps had drifted apart. A parallel
    pattern here would be a third.
    """

    def test_abbreviations_are_accepted_and_expanded(self):
        for given in ("Gi2", "gi2", "GigabitEthernet2"):
            assert "interface GigabitEthernet2" in _lines(
                _render(manager_interface=given)), given

    def test_slots_and_subinterfaces_survive(self):
        for given, want in (("Gi0/0/1", "GigabitEthernet0/0/1"),
                            ("Gi2.100", "GigabitEthernet2.100"),
                            ("Te1/1", "TenGigabitEthernet1/1")):
            assert f"interface {want}" in _lines(
                _render(manager_interface=given)), given

    def test_invented_abbreviations_are_refused(self):
        """`GE2` and `Gig2` look plausible and are not names `ifnames`
        knows, so they would reach the device verbatim."""
        for given in ("GE2", "Gig2", "banana", "2", "Gi", ""):
            with pytest.raises(ManagementInterfaceRefused):
                _render(manager_interface=given)

    def test_a_well_formed_name_for_a_missing_port_is_ACCEPTED(self):
        """**The limit, pinned as a test so it cannot be quietly forgotten.**

        `GigabitEthernet02` is well-formed. Whether the device has such a
        port is unknowable without an inventory of that model's interfaces,
        which is a device-TYPE fact and deliberately not built (§8.10).

        This asserts the gap rather than hiding it. The wizard's help text
        says the field is checked for spelling and **not** against the
        device, because an operator who believes a field is validated stops
        checking it themselves — which would make a partial check worse than
        no check.
        """
        out = _render(manager_interface="GigabitEthernet02")
        assert "interface GigabitEthernet02" in _lines(out)
