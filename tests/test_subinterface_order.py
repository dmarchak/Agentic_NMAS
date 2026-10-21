"""A subinterface's `encapsulation` renders before every address line (C1478, 2026-10-21: the
program built for a new dot1Q subinterface sent `ip address` and `ip helper-address` ahead of
`encapsulation dot1Q`, and IOS refuses an address on a LAN subinterface that has no
encapsulation yet: "% Configuring IP routing on a LAN subinterface is only allowed if that
subinterface is already configured as part of an IEEE 802.10, IEEE 802.1Q, or ISL vLAN").

The shipped `interface` macro (`modules/nsot/templates/_common.j2`) now writes `encapsulation`
right after `description`, where the device prints it, so a deploy program, which sends lines in
render order (`deploy.merge_commands`), configures the encapsulation first.

On a REAL C8000v capture (tests/fixtures/configs/fleet/r2.cfg), with a subinterface added on
documentation addresses (192.0.2.0/24, 2001:db8::/32): (a) the render puts `encapsulation`
before `vrf forwarding`, every `ip address` and `ipv6 address`, and `ip helper-address`; (b) a
deploy adding the subinterface to that capture sends `interface <name>`, then `encapsulation`,
then the address lines."""

import copy
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r2.cfg")
PLATFORM = "cisco_iosxe"
PARENT = "GigabitEthernet3"
SUB = "GigabitEthernet3.10"


def _capture():
    with open(CAPTURE, encoding="utf-8") as fh:
        return fh.read()


def _parse(text):
    from modules.nsot.parsers import get_parser
    return get_parser(PLATFORM).parse(text)


def _with_subinterface(hv):
    """*hv* with a dot1Q subinterface after its parent, built from the parent's parsed entry so
    it carries every key the parser gives an interface, each emptied but those set here."""
    parent = next(i for i in hv["interfaces"] if i["name"] == PARENT)
    sub = {k: type(v)() if isinstance(v, (str, list, dict, bool)) else None
           for k, v in parent.items()}
    sub.update(name=SUB, description="Subinterface VLAN 10", encapsulation="dot1Q 10",
               vrf="BRANCH", ipv4="192.0.2.1 255.255.255.0",
               helper_addresses=["192.0.2.250"], ipv6=["2001:DB8:10::1/64"])
    want = copy.deepcopy(hv)
    at = next(n for n, i in enumerate(want["interfaces"]) if i["name"] == PARENT)
    want["interfaces"].insert(at + 1, sub)
    return want


def _block(rendered, name):
    """The body lines of interface *name* in *rendered*."""
    lines = rendered.splitlines()
    start = lines.index(f"interface {name}") + 1
    body = []
    for line in lines[start:]:
        if not line.startswith(" "):
            break
        body.append(line)
    return body


def _first(body, prefix):
    return next(n for n, line in enumerate(body) if line.startswith(prefix))


def _address_lines(body):
    """Every line that configures an address or a relay on the interface: IPv4 and IPv6."""
    return [n for n, line in enumerate(body)
            if line.startswith((" vrf forwarding ", " ip address ", " ip helper-address ",
                                " ipv6 address "))]


def test_the_render_puts_encapsulation_before_vrf_and_every_address_line():
    from modules.nsot import roundtrip
    body = _block(roundtrip.render(_with_subinterface(_parse(_capture())), PLATFORM), SUB)
    encap = _first(body, " encapsulation dot1Q 10")
    # Floor: every line the check orders is in the render, IPv4 and IPv6 alike.
    for prefix in (" vrf forwarding BRANCH", " ip address 192.0.2.1 255.255.255.0",
                   " ip helper-address 192.0.2.250", " ipv6 address 2001:DB8:10::1/64"):
        assert any(line == prefix for line in body), (prefix, body)
    assert len(_address_lines(body)) == 4, body
    late = [body[n] for n in _address_lines(body) if n < encap]
    assert not late, f"rendered before `encapsulation dot1Q 10`: {late}; the block: {body}"
    # Where the device prints it: straight after the description.
    assert body[:2] == [" description Subinterface VLAN 10", " encapsulation dot1Q 10"], body


def test_the_rendered_subinterface_reads_back_as_the_same_intent():
    from modules.nsot import roundtrip
    rendered = roundtrip.render(_with_subinterface(_parse(_capture())), PLATFORM)
    sub = next(i for i in _parse(rendered)["interfaces"] if i["name"] == SUB)
    assert (sub["encapsulation"], sub["vrf"], sub["ipv4"], sub["helper_addresses"],
            sub["ipv6"]) == ("dot1Q 10", "BRANCH", "192.0.2.1 255.255.255.0",
                             ["192.0.2.250"], ["2001:DB8:10::1/64"]), sub


def test_a_deploy_of_a_new_subinterface_sends_encapsulation_before_any_address():
    from modules.nsot import deploy, roundtrip
    capture = _capture()
    assert f"interface {SUB}" not in capture, "floor: the capture has no such subinterface"
    # Against the capture itself, as the device printed it.
    program = deploy.merge_commands(
        roundtrip.render(_with_subinterface(_parse(capture)), PLATFORM), capture)
    assert f"interface {SUB}" in program, program
    head = program.index(f"interface {SUB}")
    sub = []
    for line in program[head + 1:]:
        if not line.startswith(" "):
            break
        sub.append(line)
    encap = _first(sub, " encapsulation dot1Q 10")
    addresses = _address_lines(sub)
    assert len(addresses) == 4, sub
    assert encap < min(addresses), (
        f"the program sends {[sub[n] for n in addresses if n < encap]} before "
        f"`encapsulation dot1Q 10`; IOS refuses an address on a LAN subinterface without it: "
        f"{program}")
    # And nothing else: the new subinterface, merge-only, in the order the device needs.
    assert program == [f"interface {SUB}", " description Subinterface VLAN 10",
                       " encapsulation dot1Q 10", " vrf forwarding BRANCH",
                       " ip address 192.0.2.1 255.255.255.0", " ip helper-address 192.0.2.250",
                       " ipv6 address 2001:DB8:10::1/64", "exit"], program
