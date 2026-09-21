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
"""

import logging

log = logging.getLogger(__name__)

#: Platforms whose startup config is TYPED into a console rather than loaded
#: as a file. On these, every line is a round trip and a resync risk, so the
#: output carries no commentary.
CONSOLE_REPLAYED = {"cisco_ios"}

#: Platforms where vrnetlab injects its own ``username ... password ...``
#: before the startup config. A ``secret`` line for that user arrives second
#: and is refused, so these must use the password form and rotate afterwards.
#: Measured in the patched launch script; confirmed on the probe.
VRNETLAB_INJECTS_USER = {"cisco_iosxe"}


class UnsupportedPlatform(Exception):
    """No bootstrap shape is known for this platform."""


def secret_clause(platform: str, value: str) -> str:
    """``password 0 x`` or ``secret 0 x``, per what the platform will accept.

    Not a style choice. On a platform where vrnetlab injects a password line
    first, a secret line for the same user is refused — the device keeps
    vrnetlab's credential and the startup file describes one it does not have.
    """
    if platform in VRNETLAB_INJECTS_USER:
        return f"password 0 {value}"
    return f"secret 0 {value}"


def render_bootstrap(platform: str, *, hostname: str, username: str,
                     secret: str, domain: str = "rcn.lab",
                     mgmt_interface: str = "") -> str:
    """The minimal management-plane config for a device joining the lab.

    Derived from ``r1.cfg`` and ``s1.cfg`` with everything else removed: no
    loopback, no addressed data interface, no routing process. What remains is
    what makes the device reachable and nothing more.

    The asymmetry between the platforms is real and load-bearing. The C8000v's
    management interface is owned by vrnetlab and is absent here; the vIOS's
    is configured explicitly, because with ``CLAB_MGMT_PASSTHROUGH=false``
    nothing else gives it an address. A generator that treated both alike
    would produce an unreachable switch.
    """
    from modules.nsot.deploy import assert_sendable

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
            f"ip domain-name {domain}",
            "!",
            "line vty 0 4",
            " logging synchronous",
            " login local",
            " transport input all",
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
            f"ip domain-name {domain}",
            "!",
            f"interface {interface}",
            " description clab-mgmt",
            " no switchport",
            " ip address dhcp",
            " negotiation auto",
            " no shutdown",
            "!",
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
