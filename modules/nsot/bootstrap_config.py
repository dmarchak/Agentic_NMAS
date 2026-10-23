"""nsot/bootstrap_config.py — the minimal config a new device boots with.

Two callers, by design: the throwaway probe that measures the bootstrap
profile, and the Phase 4 wizard that onboards a real device. Designing it once
is the point — the probe measures what the wizard will produce.

**Everything this module emits is checked with ``assert_sendable``, comments
included.** That is not belt-and-braces; it is the rule the em dash has now
broken twice:

* a pushed command, where three UTF-8 bytes made IOS lose sync mid-line and
  surface as a Netmiko echo timeout;
* a *comment* in a vIOS startup config, where an emulator typed the file into
  the console line by line and waited for a prompt after each one. It stopped
  on a line beginning ``!`` and hung the boot.

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
    The **platform's own** management port, where it has one apart from the
    manager's: on a vIOS it is configured here (``ip address dhcp``) when one
    is named; on a C8000v it is its environment's and this module emits
    nothing for it. In an emulator it is the emulator's own management
    network, which nothing outside the emulator's host can reach. Which
    interfaces those are is NetBox's (`mgmt_only`, `device_environment`).

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

#: Whether something injects its own ``username ... password ...`` ahead of
#: the startup config is a fact about the device's ENVIRONMENT, never its
#: platform (C663 step 3): read from NetBox per device
#: (`device_environment`, a `username` line among its environment-owned
#: lines). Where one is injected, a ``secret`` line for that user arrives
#: second and is refused (measured on an emulated C8000v in stage B:
#: `%CVAC-4-CLI_FAILURE ... was rejected`), so the password form is used and
#: rotated afterwards. A device with no such environment takes the stronger
#: form.

#: The keyword for the DNS domain, which differs between the two platforms and
#: is not a style choice.
#:
#: Measured in stage C: `%CVAC-4-CLI_FAILURE: 'ip domain-name <domain>' was
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

#: Platforms whose SSH server this file must start itself, whatever their
#: environment.
#:
#: Measured across the probe runs rather than assumed. The vIOS carried
#: `ip ssh version 2` with no key, and its capture had to be taken over the
#: SERIAL CONSOLE because SSH never came up: IOS will not start an SSH server
#: without an RSA keypair, and says nothing about it. Any other platform
#: generates one too unless its ENVIRONMENT brings SSH up (an `ip ssh` or
#: `crypto key` line among its environment-owned lines, C663 step 3): the
#: emulated C8000v carried no key generation and answered SSH in stages A to
#: C because its emulator's own bootstrap set it up, which a real C8000v's
#: does not.
#:
#: Key generation needs a hostname and a domain name already set, so it is
#: emitted after both and before `ip ssh version 2`.
GENERATES_SSH_KEY = {"cisco_ios"}

#: Modulus for the generated keypair. 2048 is the floor worth shipping.
#:
#: UNMEASURED on a console-replayed platform: key generation takes real time
#: and a console replay waits for a prompt after each line it types. See
#: `docs/bootstrap-probe/README.md` stage D.
SSH_KEY_MODULUS = 2048


#: Interfaces the manager-facing address must NEVER be put on are the
#: environment's own management interfaces: the device's interfaces NetBox
#: marks management-only (`device_environment`, C663 step 3). They were a
#: per-PLATFORM table naming the emulator's ports until then, which a real
#: device does not have.
#:
#: **This is enforced** (`manager_interface_lines`). The failure it prevents
#: is the stage-B shape: a node that boots, reports healthy, answers its
#: console and cannot be reached -- the address put on a port something else
#: owns. The two interfaces coexist happily when they are *different* ones:
#: an environment's management port in its own VRF and the data interfaces in
#: the global table at once.

#: Platforms whose ports are switchports unless told otherwise, so a routed
#: management interface needs `no switchport`.
#:
#: **Keyed on what it actually decides.** The stanza shape was previously
#: selected with a set naming the emulator's first interface, which happened to contain
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
                            platform_mgmt_interface: str = "",
                            reserved: dict = None, gateway_route: bool = True) -> list:
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
            "no interface given for the management address. It must be "
            "chosen, never defaulted: the first interface may be one the "
            "device's environment owns")

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

    reserved = {canonical(k): v for k, v in (reserved or {}).items()}
    if interface in reserved:
        raise ReservedInterface(
            f"'{interface}' cannot carry the management address: "
            + reserved[interface])

    # The same conflict, arrived at dynamically: whatever this render is
    # already configuring as the platform's own management interface cannot
    # also be the manager-facing one, whatever it is called.
    if platform_mgmt_interface and canonical(platform_mgmt_interface.strip()) == interface:
        raise ReservedInterface(
            f"'{interface}' is already being configured as the platform's own "
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
        # A layer-2 platform's ports are switchports, so a routed port needs `no switchport`.
        # An SVI is not a port: `no switchport` under `interface Vlan1` is an invalid line
        # (C1349: a switch whose uplink also carries its hosts' VLAN is managed on an SVI).
        # A fetched configuration with a refused line still applies the rest, but the file
        # Mercury served would then hold a line the device never took.
        body = [
            f"interface {interface}",
            " description NMAS management - manager is on this subnet",
        ] + ([] if interface.startswith("Vlan") else [" no switchport"]) + [
            (" ip address dhcp" if dhcp else f" ip address {address} {mask}"),
            " no shutdown",
            "!",
        ]

    if gateway:
        # Only reached when the caller says the manager is elsewhere. Kept
        # out of the interface block because it is a different kind of claim.
        # *gateway_route* False (out-of-band ZTP's static switch, the operator 2026-10-23): a
        # layer-2 switch with routing off reaches the manager by its default gateway alone, the
        # line the console kick-start typed and read back; no static route is rendered.
        if gateway_route or platform not in LAYER2_PLATFORMS:
            body += [f"ip route 0.0.0.0 0.0.0.0 {gateway}"]
        if platform in LAYER2_PLATFORMS:
            # A switch with `ip routing` off ignores a static route and uses its default
            # gateway; with routing on (the vIOS-L2 image's default, read from a running
            # switch's golden: RIP on SVIs, no `ip routing` line shown) the gateway is
            # ignored. Both, so the manager is reachable whichever the switch runs (C1349).
            body += [f"ip default-gateway {gateway}"]
        body += ["!"]
    return body


def secret_clause(platform: str, value: str, injects_user: bool = False) -> str:
    """``password 0 x`` or ``secret 0 x``, per what the device will accept.

    Not a style choice. Where the device's environment injects a password line
    for the user first, a secret line for the same user is refused: the device
    keeps the injected credential and the startup file describes one it does
    not have. *injects_user* is that environment's fact (`device_environment`);
    *platform* stays in the signature because the clause is per platform's
    syntax, which both platforms here share.
    """
    if injects_user:
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


def ssh_key_lines(platform: str, force: bool = False) -> list:
    """Key generation, on the platforms that always need it, and wherever
    *force* says nothing else will.

    Emitting it where the environment already does the work would regenerate
    a key the device is mid-way through using.

    *force*: nothing else will generate one. P.6 M4 found the case: a ZTP
    C8000v boots the pristine base with its emulator's day-0 config REMOVED,
    so "the emulator sets it up" (the reason the C8000v is not in
    `GENERATES_SSH_KEY`) was no longer true. The device fetched and applied
    its config, had no key, and refused TCP 22 (measured in 3 ms). The
    platform was standing in for the environment, which is why the render now
    forces it unless the device's environment says it brings SSH up (C663).
    """
    if platform not in GENERATES_SSH_KEY and not force:
        return []
    return [f"crypto key generate rsa modulus {SSH_KEY_MODULUS}"]


def render_bootstrap(platform: str, *, hostname: str, username: str,
                     secret: str, domain: str = "example.net",
                     mgmt_interface: str = "",
                     manager_interface: str = "", manager_address: str = "",
                     manager_mask: str = "", manager_gateway: str = "",
                     generate_ssh_key: bool = False,
                     injects_user: bool = None, environment=None,
                     gateway_route: bool = True) -> str:
    """The minimal management-plane config for a device joining the network.

    *environment*: what the device's environment owns, read from NetBox
    (`device_environment.read`, C663 step 3); None is no environment, and a
    device with none has none. From it: the interfaces the manager's address
    may not go on, whether an injected account forces the password form
    (*injects_user* overrides it: a ZTP device boots with nothing injected),
    and whether the environment brings SSH up. Where it does not, the C8000v
    generates its own key too.

    *generate_ssh_key*: generate the key whatever the environment says,
    because nothing else will (a ZTP device, P.6 M4).

    Derived from ``r1.cfg`` and ``s1.cfg`` with everything else removed: no
    loopback, no routing process, no data interface beyond the one the
    manager reaches the device on. What remains is what makes the device
    reachable and nothing more.

    The asymmetry between the platforms is real and load-bearing. A vIOS's
    own management port (*mgmt_interface*, or the one interface its
    environment marks management-only) is configured here with
    ``ip address dhcp``, because nothing else gives it an address; a C8000v's
    is its environment's to configure and is absent here. A generator that
    treated both alike would produce an unreachable switch.

    **``manager_address`` is what makes the device onboardable** -- see the
    module docstring for why it is not the same interface as
    ``mgmt_interface``. It is optional here **only** so the probe fixtures
    and the platform-shape tests can render without one; `build_plan()`
    makes its absence a blocking reason, so no config an operator can
    actually download is missing it.
    """
    from modules.nsot.deploy import assert_sendable
    from modules.nsot.device_environment import NONE

    env = environment or NONE
    injects = env.injects_user if injects_user is None else injects_user
    own_mgmt = mgmt_interface or (env.management_interfaces[0]
                                  if len(env.management_interfaces) == 1 else "")

    # Computed before the branches: both platforms need it, and two call
    # sites would be two chances for one of them to forget. Empty when no
    # address is supplied, which is how the shape tests and the probe
    # fixtures render a config with no manager segment to sit on.
    manager_lines = []
    if manager_address or manager_interface or manager_mask:
        manager_lines = manager_interface_lines(
            platform, interface=manager_interface, address=manager_address,
            mask=manager_mask, gateway=manager_gateway,
            platform_mgmt_interface=own_mgmt, reserved=env.reserved,
            gateway_route=gateway_route)

    lines = []
    if platform == "cisco_iosxe":
        lines = [
            "! minimal bootstrap - management plane only",
            f"hostname {hostname}",
            "!",
            "no aaa new-model",
            "!",
            f"username {username} privilege 15 {secret_clause(platform, secret, injects)}",
            "!",
            domain_line(platform, domain),
            "!",
        ] + manager_lines + ((ssh_key_lines(platform, force=True)
                              + ["ip ssh version 2", "!"])
                             if generate_ssh_key or not env.owns_ssh else []) + [
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
            # `_telnet` variants), and an emulator reaches the device over the
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
        # The platform's own management port, only where one is named (the form's
        # Platform management port, or the one interface the environment marks
        # management-only). It was always Gi0/0 until C663: one emulator's port.
        own_lines = ([f"interface {own_mgmt}",
                      " description platform management",
                      " no switchport",
                      " ip address dhcp",
                      " negotiation auto",
                      " no shutdown",
                      "!"] if own_mgmt else [])
        lines = [
            f"hostname {hostname}",
            "!",
            "no aaa new-model",
            "no logging console",
            "!",
            f"username {username} privilege 15 {secret_clause(platform, secret, injects)}",
            "!",
            domain_line(platform, domain),
            "!",
        ] + own_lines + manager_lines + [
            "line vty 0 4",
            " logging synchronous",
            " login local",
            " transport input ssh",
            "!",
            # LAST, after everything SSH needs but the key (stage D, 2026-10-12): an emulator
            # TYPES this file into a console, and key generation takes real time. Before, the
            # key line came before `ip ssh version 2` and the whole vty block, so a replay
            # stalled there would have left a switch that answers ping and not SSH. Now a
            # stall can cost only the line after it; `ip ssh version 2` must follow the key
            # (IOS refuses it with no keypair).
        ] + ssh_key_lines(platform) + [
            "ip ssh version 2",
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

    It lands in the startup file, in any repository that keeps it, and in the
    first golden capture, and it stays there after the device is rotated. A
    predictable value there is a predictable value in a published history.
    """
    from modules.nsot.credential_rotation import generate_password

    return generate_password("bootstrap", length)
