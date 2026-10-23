"""A switchport's mode renders AFTER its access VLAN and its trunk's allowed VLANs and
encapsulation (C1586, 2026-10-23: the shipped `interface` macro wrote `switchport mode` first, so a
deploy program, which sends lines in render order (`deploy.merge_commands`), would send
`switchport mode trunk` to a port whose trunk encapsulation is still "auto", and an IOS switch
refuses it: "Command rejected: An interface whose trunk encapsulation is "Auto" can not be
configured to "trunk" mode". The switch's form of C1478).

The order is the one IOS prints. On a REAL vIOS-L2 capture (tests/fixtures/configs/fleet/s1.cfg,
whose Gi0/3 trunk prints `switchport trunk allowed vlan`, `switchport trunk encapsulation dot1q`,
`switchport mode trunk`): (a) the render of the capture's own trunk keeps that order; (b) a bare
port made a trunk renders and deploys encapsulation before mode; (c) a bare port made an access
port renders and deploys its access VLAN before its mode; (d) both read back as the same intent."""

import copy
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "s1.cfg")
PLATFORM = "cisco_ios"
TRUNK = "GigabitEthernet0/3"     # a trunk in the capture
BARE = "GigabitEthernet0/1"      # a port with no switchport lines in the capture


def _capture():
    with open(CAPTURE, encoding="utf-8") as fh:
        return fh.read()


def _parse(text):
    from modules.nsot.parsers import get_parser
    return get_parser(PLATFORM).parse(text)


def _block(lines, name):
    """The body lines of interface *name* in *lines* (a render's lines or a program)."""
    start = lines.index(f"interface {name}") + 1
    body = []
    for line in lines[start:]:
        if not line.startswith(" "):
            break
        body.append(line)
    return body


def _with_port(hv, **keys):
    want = copy.deepcopy(hv)
    port = next(i for i in want["interfaces"] if i["name"] == BARE)
    port.update(keys)
    return want


AS_TRUNK = {"switchport_mode": "trunk", "switchport_trunk_encapsulation": "dot1q",
            "switchport_trunk_vlans": ["1,10"]}
AS_ACCESS = {"switchport_mode": "access", "switchport_access_vlan": "10"}


def _render(hv):
    from modules.nsot import roundtrip
    return roundtrip.render(hv, PLATFORM)


def test_the_capture_s_own_trunk_renders_in_the_order_ios_prints_it():
    capture = _capture()
    printed = [ln for ln in _block(capture.splitlines(), TRUNK) if ln.startswith(" switchport")]
    assert printed == [" switchport trunk allowed vlan 10,20,30",
                       " switchport trunk encapsulation dot1q", " switchport mode trunk"], printed
    rendered = [ln for ln in _block(_render(_parse(capture)).splitlines(), TRUNK)
                if ln.startswith(" switchport")]
    assert rendered == printed, rendered


def test_a_new_trunk_renders_and_deploys_encapsulation_before_mode():
    from modules.nsot import deploy
    capture = _capture()
    assert " switchport" not in "\n".join(_block(capture.splitlines(), BARE)), "floor: bare port"
    rendered = _render(_with_port(_parse(capture), **AS_TRUNK))
    body = _block(rendered.splitlines(), BARE)
    enc, mode = body.index(" switchport trunk encapsulation dot1q"), body.index(" switchport mode trunk")
    assert enc < mode, body
    program = deploy.merge_commands(rendered, capture)
    sent = _block(program, BARE)
    assert sent == [" switchport trunk allowed vlan 1,10", " switchport trunk encapsulation dot1q",
                    " switchport mode trunk"], program


def test_a_new_access_port_renders_and_deploys_its_vlan_before_its_mode():
    from modules.nsot import deploy
    capture = _capture()
    rendered = _render(_with_port(_parse(capture), **AS_ACCESS))
    program = deploy.merge_commands(rendered, capture)
    assert _block(program, BARE) == [" switchport access vlan 10", " switchport mode access"], \
        program


def test_both_read_back_as_the_same_intent():
    capture = _capture()
    for keys in (AS_TRUNK, AS_ACCESS):
        port = next(i for i in _parse(_render(_with_port(_parse(capture), **keys)))["interfaces"]
                    if i["name"] == BARE)
        assert {k: port[k] for k in keys} == keys, port
