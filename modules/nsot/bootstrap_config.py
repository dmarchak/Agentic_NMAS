"""nsot/bootstrap_config.py — the minimal config a new device boots with.

Two callers, by design: the throwaway probe that measures the bootstrap
profile, and the Phase 4 wizard that onboards a real device. Designing it once
is the point — the probe measures what the wizard will produce.

**Everything this module emits is checked with ``assert_sendable``, comments
included.** That is not belt-and-braces; it is the rule the em dash has now
broken twice:

* a pushed command, where three UTF-8 bytes made IOS lose sync mid-line and
  surface as a Netmiko echo timeout;
* a *comment* in a vIOS startup config, where vrnetlab types the file into the
  console line by line and waits for a prompt after each one. It stopped on a
  line beginning ``!`` and hung the boot.

The C8000v booted with the same character in the same position, because it
loads its startup config as a file rather than typing it. Identical content,
harmless on one platform and fatal on the other — so the rule cannot be
"ASCII on the deploy path". It has to be ASCII on anything that reaches a CLI,
and the safe way to say that is: anything this module produces.

On vIOS the module emits **no prose comments at all**. Every line costs a
console round trip and is a chance to desync, and a comment buys nothing on a
device. Explanations live in ``docs/bootstrap-probe/README.md``.

TWO MANAGEMENT INTERFACES, AND THEY ARE NOT THE SAME ONE
--------------------------------------------------------

The word "management" names two different things here, on two different
networks, and conflating them is what made this module emit a config that
could not reach the manager (4C.8):

``mgmt_interface``
    The **containerlab-facing** interface. On a vIOS it is configured here
    (``ip address dhcp``); on a C8000v vrnetlab owns it and this module emits
    nothing for it. It lands on the docker management network, in the
    ``clab-mgmt`` VRF on a real lab device. **Nothing outside the
    containerlab host has a path to it.**

``manager_interface`` / ``manager_address``
    The **manager-facing** interface: a data interface, in the global table,
    carrying a static address on a segment the NMAS can reach. This is the
    one that makes the device onboardable, and until 4C.8 it did not exist.

Measured 2026-09-23: the manager has an interface on one lab segment and
reaches every device through a switch SVI on it, while each device's "mgmt
identity" address is a ``/32`` loopback advertised into the IGP. So the
previous docstring claim -- "no loopback, no addressed data interface, no
routing process; what remains is what makes the device reachable" -- was
false in its last clause. What remained made the device **boot**. Nothing
made it **reachable**.

The measured addresses are in ``docs/NSOT_STAGE4C_PLAN.md`` §8.2 and not
here: an address in this package is somebody's lab leaking into the tool,
which ``tests/test_no_ip_literals.py`` exists to refuse. It caught this
docstring.
"""

import logging
import re as _re

log = logging.getLogger(__name__)

#: Platforms whose startup config is TYPED into a console rather than loaded
#: as a file. On these, every line is a round trip and a resync risk, so the
#: output carries no commentary.
CONSOLE_REPLAYED = {"cisco_ios"}

#: Platforms where vrnetlab injects its own ``username ... password ...``
#: before the startup config. A ``secret`` line for that user arrives second
#: and is refused, so these must use the password form and rotate afterwards
#: -- unless the launch script carries the stage-C user skip.
#:
#: Read in the patched launch script, CONFIRMED on hardware in stage B
#: (`%CVAC-4-CLI_FAILURE ... was rejected`, node came up on admin/admin), and
#: the skip PROVEN in stage C.
VRNETLAB_INJECTS_USER = {"cisco_iosxe"}

#: The keyword for the DNS domain, which differs between the two platforms and
#: is not a style choice.
#:
#: Measured in stage C: `%CVAC-4-CLI_FAILURE: 'ip domain-name rcn.lab' was
#: rejected` on IOS-XE 17.6, which spells it `ip domain name`. Classic IOS
#: (vIOS-L2 15.x) spells it `ip domain-name` and rejects the other. There is
#: no spelling that works on both, so the generator must know the platform.
#:
#: This one failed SILENTLY in the sense that mattered: the node booted, was
#: healthy, answered SSH -- and had no domain name, so any later
#: `crypto key generate rsa` would have failed too.
DOMAIN_KEYWORD = {
    "cisco_iosxe": "ip domain name",
    "cisco_ios": "ip domain-name",
}

#: Platforms whose SSH server this file must start itself.
#:
#: Measured across the probe runs rather than assumed. The C8000v carried no
#: `ip ssh` line and no key generation, and answered SSH in stages A, B and C
#: -- vrnetlab's own bootstrap config sets it up. The vIOS carried
#: `ip ssh version 2` with no key, and its capture had to be taken over the
#: SERIAL CONSOLE because SSH never came up: IOS will not start an SSH server
#: without an RSA keypair, and says nothing about it.
#:
#: Key generation needs a hostname and a domain name already set, so it is
#: emitted after both and before `ip ssh version 2`.
GENERATES_SSH_KEY = {"cisco_ios"}

#: The helper name the stage-C launch patch defines.
#:
#: Two readers: `docs/bootstrap-probe/patches/patch-skip-injected-user.py`,
#: which writes it, and `credential_rotation.verify_startup_applies()`, which
#: greps the clab host's launch script for it to decide whether a `secret`
#: line in a startup file can apply. A test asserts the patcher still emits
#: exactly this name -- the check silently degrades to "always refuses" if the
#: two drift apart, which reads as a safe failure and is actually a check that
#: has stopped measuring anything.
LAUNCH_SKIP_MARKER = "_skip_users_defined_in_startup"

#: Modulus for the generated keypair. 2048 is the floor worth shipping.
#:
#: UNMEASURED on a console-replayed platform: key generation takes real time
#: and vrnetlab waits for a prompt after each line it types. See
#: `docs/bootstrap-probe/README.md` stage D.
SSH_KEY_MODULUS = 2048


#: Interfaces the manager-facing address must NEVER be put on, and why.
#:
#: **This is enforced.** Its predecessor, `VRNETLAB_OWNS_FIRST_INTERFACE`,
#: was a set named for a reservation and used only to pick a stanza *shape* --
#: so `render_bootstrap(..., manager_interface="GigabitEthernet1")` on a
#: C8000v emitted the address on vrnetlab's own interface without complaint.
#: Measured, after "the rule now holds from both ends" had been asserted and
#: agreed: it held at one end. `test_probe_topologies.py` refused a topology
#: that cabled Gi1 and nothing refused the config that addressed it.
#:
#: **A constant whose name states a rule it does not enforce** is the same
#: family as a docstring that teaches what the code does not do.
#:
#: The failure it prevents is the stage-B shape: a node that boots, reports
#: healthy, answers its console and cannot be reached -- reproduced inside
#: the tool built to prevent it.
#:
#: The two interfaces coexist happily when they are *different* ones: r1-r5
#: run Gi1 in `vrf forwarding clab-mgmt` and their data interfaces in the
#: global table at once.
RESERVED_INTERFACES = {
    "cisco_iosxe": {
        "GigabitEthernet1":
            "vrnetlab owns Gi1 on this platform and configures it as the "
            "containerlab management interface. Data interfaces start at "
            "Gi2.",
    },
    "cisco_ios": {
        "GigabitEthernet0/0":
            "this is the containerlab management interface on this "
            "platform, and the bootstrap config already gives it "
            "`ip address dhcp`. Two stanzas for one interface is not a "
            "configuration, it is a race.",
    },
}

#: Platforms whose ports are switchports unless told otherwise, so a routed
#: management interface needs `no switchport`.
#:
#: **Keyed on what it actually decides.** The stanza shape was previously
#: selected with `VRNETLAB_OWNS_FIRST_INTERFACE`, which happened to contain
#: the right platform for an unrelated reason -- two facts that coincide on
#: a two-platform fleet and diverge on the third.
LAYER2_PLATFORMS = {"cisco_ios"}


class UnsupportedPlatform(Exception):
    """No bootstrap shape is known for this platform."""


def _is_known_interface_spelling(name: str) -> bool:
    """Does *name* use a prefix `ifnames` recognises, followed by a slot?

    **Derived from `INTERFACE_PREFIXES`, not from a second regex.** That
    table already owns interface spelling for the whole program, and a
    parallel pattern here would be a second answer to one question -- the
    thing `ifnames` was created to stop, since two display maps had already
    drifted apart before it existed.

    This is a SPELLING check and nothing more. `GigabitEthernet02` passes:
    it is well-formed, and whether the device has such a port cannot be
    known without an inventory of that model's interfaces. That limit is
    deliberate and is stated in the wizard's help text rather than implied
    away -- an operator who believes a field is validated stops checking it
    themselves, which would make this check worse than none.
    """
    from modules.nsot.ifnames import INTERFACE_PREFIXES

    for prefix, _abbrevs in INTERFACE_PREFIXES:
        if name.startswith(prefix):
            slot = name[len(prefix):]
            return bool(slot) and _SLOT.match(slot) is not None
    return False


#: What may follow a canonical prefix: 2, 0/0, 1/0/1, 0/0.100.
_SLOT = _re.compile(r"^\d+(/\d+)*(\.\d+)?$")


class ManagementInterfaceRefused(Exception):
    """Base: the manager-facing interface stanza will not be emitted."""


class ManagementAddressRequired(ManagementInterfaceRefused):
    """A bootstrap config with no manager-reachable address is unreachable.

    Raised rather than emitted, because the failure it prevents is silent:
    the device boots, reports healthy, answers its console, and cannot be
    onboarded by anything.
    """


class ReservedInterface(ManagementInterfaceRefused):
    """The chosen interface belongs to something else on this platform."""


def manager_interface_lines(platform: str, *, interface: str, address: str,
                            mask: str, gateway: str = "",
                            clab_interface: str = "") -> list:
    """The one stanza that makes the device reachable by the manager.

    **Why there is no default gateway unless one is given.** The NMAS sits on
    the same ``/24`` as this address and always initiates the connection, so
    the device needs no route to answer it -- the reply goes out the same
    interface the request arrived on, to a neighbour it already has.

    That is a *conditional*, not a property of bootstrap configs, and it is
    the same conditional as choosing this segment at all: **it holds because
    the manager shares the segment, and fails in a network where it does
    not.** Both are written here rather than in a design document, because
    the next person adding a platform reads this function and not the
    document.

    A gateway written when nothing needs one would be a routing statement in
    a config whose entire point is to have none -- see ``§8.3`` of
    ``docs/NSOT_STAGE4C_PLAN.md``: in an in-band-managed network there is no
    config that is both minimal and sufficient, and this segment is what buys
    the way out of that.
    """
    # DHCP IS A STATED SOURCE, NOT AN ABSENT ADDRESS. The sentinel is
    # explicit and arrives from `OnboardPlan.address_source`, so "the operator
    # chose DHCP" can never be reached by leaving the field blank -- which is
    # what an "address optional" flag would have made indistinguishable from
    # "the operator forgot". The refusals below are untouched for `static`.
    dhcp = (address or "").strip().lower() == "dhcp"
    if not dhcp:
        if not address:
            raise ManagementAddressRequired(
                "a bootstrap config needs an address the manager can reach: "
                "without one the device boots healthy and is onboardable by "
                "nothing")
        if not mask:
            raise ManagementAddressRequired(
                f"no mask given for {address}. A /24 assumption is how a tool "
                f"works in exactly one lab")
    if not interface:
        raise ManagementAddressRequired(
            "no interface given for the management address. On a platform "
            "where vrnetlab owns the first interface this must be chosen, "
            "never defaulted")

    # CANONICALISED BEFORE ANYTHING COMPARES IT. `Gi2`, `gi2` and
    # `GigabitEthernet2` are one interface, and a reserved-interface check
    # that matched only the long spelling would refuse `GigabitEthernet1`
    # and wave `Gi1` through -- a gate that the shorter, likelier spelling
    # walks past.
    #
    # **The limit is real and is stated rather than hidden**: `canonical()`
    # returns an unrecognised name unchanged, so `GE2` and `Gig2` are
    # refused below, while `GigabitEthernet02` is well-formed and cannot be
    # told from a real interface without an inventory of the device's
    # actual ports. See docs/NSOT_STAGE4C_PLAN.md 8.10.
    from modules.nsot.ifnames import canonical

    interface = canonical(interface.strip())
    if not _is_known_interface_spelling(interface):
        raise ReservedInterface(
            f"'{interface}' is not a recognised interface name. Use the full "
            f"form or a standard abbreviation -- GigabitEthernet2 or Gi2, "
            f"not GE2 or Gig2.")

    reserved = RESERVED_INTERFACES.get(platform, {})
    if interface in reserved:
        raise ReservedInterface(
            f"'{interface}' cannot carry the management address: "
            + reserved[interface])

    # The same conflict, arrived at dynamically: whatever this render is
    # already configuring as the containerlab interface cannot also be the
    # manager-facing one, whichever platform it is and whatever it is called.
    if clab_interface and canonical(clab_interface.strip()) == interface:
        raise ReservedInterface(
            f"'{interface}' is already being configured as the containerlab "
            f"management interface in this same config. One interface cannot "
            f"hold two addresses, whatever their source.")

    if platform not in LAYER2_PLATFORMS:
        body = [
            f"interface {interface}",
            " description NMAS management - manager is on this subnet",
            (" ip address dhcp" if dhcp else f" ip address {address} {mask}"),
            " negotiation auto",
            " no shutdown",
            "!",
        ]
    else:
        # UNMEASURED on a real vIOS. `cisco_ios` is in
        # BLOCKED_PENDING_MEASUREMENT for onboarding anyway, so this shape
        # ships refused rather than ships unproven. A vIOS-L2 may well need
        # an SVI (s3 reaches the NMAS segment on `interface Vlan99`) rather
        # than a routed port; that is a stage-D question and is not answered
        # by writing the answer down here.
        body = [
            f"interface {interface}",
            " description NMAS management - manager is on this subnet",
            " no switchport",
            (" ip address dhcp" if dhcp else f" ip address {address} {mask}"),
            " no shutdown",
            "!",
        ]

    if gateway:
        # Only reached when the caller says the manager is elsewhere. Kept
        # out of the interface block because it is a different kind of claim.
        body += [f"ip route 0.0.0.0 0.0.0.0 {gateway}", "!"]
    return body


def secret_clause(platform: str, value: str) -> str:
    """``password 0 x`` or ``secret 0 x``, per what the platform will accept.

    Not a style choice. On a platform where vrnetlab injects a password line
    first, a secret line for the same user is refused — the device keeps
    vrnetlab's credential and the startup file describes one it does not have.
    """
    if platform in VRNETLAB_INJECTS_USER:
        return f"password 0 {value}"
    return f"secret 0 {value}"


def domain_line(platform: str, domain: str) -> str:
    """``ip domain name`` or ``ip domain-name``, per platform.

    IOS-XE 17.6 rejects the hyphenated form and classic IOS rejects the
    spaced one. A generator emitting one spelling is wrong on one platform.
    """
    keyword = DOMAIN_KEYWORD.get(platform)
    if not keyword:
        raise UnsupportedPlatform(
            f"no domain-name spelling is known for '{platform}'")
    return f"{keyword} {domain}"


def ssh_key_lines(platform: str) -> list:
    """Key generation, on the platforms that need it and nowhere else.

    Emitting it where vrnetlab already does the work would regenerate a key
    the device is mid-way through using.
    """
    if platform not in GENERATES_SSH_KEY:
        return []
    return [f"crypto key generate rsa modulus {SSH_KEY_MODULUS}"]


def render_bootstrap(platform: str, *, hostname: str, username: str,
                     secret: str, domain: str = "rcn.lab",
                     mgmt_interface: str = "",
                     manager_interface: str = "", manager_address: str = "",
                     manager_mask: str = "", manager_gateway: str = "") -> str:
    """The minimal management-plane config for a device joining the lab.

    Derived from ``r1.cfg`` and ``s1.cfg`` with everything else removed: no
    loopback, no routing process, no data interface beyond the one the
    manager reaches the device on. What remains is what makes the device
    reachable and nothing more.

    The asymmetry between the platforms is real and load-bearing. The C8000v's
    *containerlab* management interface is owned by vrnetlab and is absent
    here; the vIOS's is configured explicitly, because with
    ``CLAB_MGMT_PASSTHROUGH=false`` nothing else gives it an address. A
    generator that treated both alike would produce an unreachable switch.

    **``manager_address`` is what makes the device onboardable** -- see the
    module docstring for why it is not the same interface as
    ``mgmt_interface``. It is optional here **only** so the probe fixtures
    and the platform-shape tests can render without one; `build_plan()`
    makes its absence a blocking reason, so no config an operator can
    actually download is missing it.
    """
    from modules.nsot.deploy import assert_sendable

    # Computed before the branches: both platforms need it, and two call
    # sites would be two chances for one of them to forget. Empty when no
    # address is supplied, which is how the shape tests and the probe
    # fixtures render a config with no manager segment to sit on.
    manager_lines = []
    if manager_address or manager_interface or manager_mask:
        manager_lines = manager_interface_lines(
            platform, interface=manager_interface, address=manager_address,
            mask=manager_mask, gateway=manager_gateway,
            clab_interface=mgmt_interface)

    lines = []
    if platform == "cisco_iosxe":
        lines = [
            "! minimal bootstrap - management plane only",
            f"hostname {hostname}",
            "!",
            "no aaa new-model",
            "!",
            f"username {username} privilege 15 {secret_clause(platform, secret)}",
            "!",
            domain_line(platform, domain),
            "!",
        ] + manager_lines + [
            "line vty 0 4",
            " logging synchronous",
            " login local",
            # SSH ONLY, ON BOTH PLATFORMS. Decided 2026-09-23.
            #
            # r1-r3 carry `transport input all`, and this branch reproduced
            # it. The standing rule -- a new default reproduces the behaviour
            # that predates it -- does NOT apply here, and the exception is
            # worth stating because the rule is otherwise near-absolute: it
            # exists to stop a setting silently changing something that
            # already works, and **a bootstrap config is written for a device
            # that does not exist yet.** There is no behaviour to preserve.
            #
            # Reproducing `all` inherits an accident of how those five
            # routers were first built, not a decision anyone made. And `all`
            # includes telnet, which puts the credential on the wire in clear
            # text -- on the device's very first configuration, which is
            # exactly when the credential is the bootstrap one being rotated.
            #
            # Nothing in NMAS needs telnet: both Netmiko drivers in
            # `platform_map` are SSH (`cisco_xe`, `cisco_ios`, not the
            # `_telnet` variants), and vrnetlab reaches the device over the
            # serial console, not the vty lines. The root `telnetlib.py` shim
            # exists because Netmiko IMPORTS the module, not because anything
            # here telnets.
            #
            # r1-r5 still carry `transport input all` in their own configs.
            # Tightening them is an intent edit through the normal loop and
            # is recorded as its own item in NSOT_PLAN.md -- not done here,
            # because changing five live routers is not a side effect of
            # fixing a generator.
            " transport input ssh",
            "!",
            "end",
        ]
    elif platform == "cisco_ios":
        interface = mgmt_interface or "GigabitEthernet0/0"
        lines = [
            f"hostname {hostname}",
            "!",
            "no aaa new-model",
            "no logging console",
            "!",
            f"username {username} privilege 15 {secret_clause(platform, secret)}",
            "!",
            domain_line(platform, domain),
            "!",
            f"interface {interface}",
            " description clab-mgmt",
            " no switchport",
            " ip address dhcp",
            " negotiation auto",
            " no shutdown",
            "!",
        ] + manager_lines + ssh_key_lines(platform) + [
            "ip ssh version 2",
            "!",
            "line vty 0 4",
            " logging synchronous",
            " login local",
            " transport input ssh",
            "!",
            "end",
        ]
    else:
        raise UnsupportedPlatform(
            f"no bootstrap shape is known for '{platform}'. Adding one means "
            f"measuring a fresh node of that platform, not writing a guess "
            f"(see docs/bootstrap-probe/).")

    if platform in CONSOLE_REPLAYED:
        # Every line is typed and waited on. A comment costs a round trip and
        # risks a desync, and buys nothing on the device.
        lines = [l for l in lines if not l.startswith("! ")]

    text = "\n".join(lines) + "\n"

    # The whole artefact, comments and all. A comment is not exempt: the line
    # that hung a vIOS boot began with "!".
    assert_sendable(text.splitlines())
    return text


def generated_secret(length: int = 24) -> str:
    """A one-time bootstrap credential. Never a fixed word.

    It lands in the startup file, in the clab repository's history, and in the
    first golden capture, and it stays there after the device is rotated. A
    predictable value there is a predictable value in a published history.
    """
    from modules.nsot.credential_rotation import generate_password

    return generate_password("bootstrap", length)
