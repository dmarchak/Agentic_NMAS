"""C1401 (0d, 2026-10-19; re-ranked B by the operator: Lab 8's step 4 brings interfaces up).

An interface's intent changed from `shutdown: true` to `no_shutdown: true` was deployed
(`interface GigabitEthernet3` / ` no shutdown` / `exit`), verified and captured, and the next
plan still sent ` no shutdown`: IOS never prints `no shutdown` in its running config, only a
shut interface's `shutdown`, so the captured golden never held the line intent renders, and an
intent bringing an interface up never converged.

The model (`modules/nsot/platform_defaults.py`, the one table of lines a device holds without
printing): an interface's `no shutdown` is satisfied by a device that holds the interface and
prints no `shutdown` under it. The renderer still states it, because merge-only expresses the
transition only by sending it: a captured `shutdown` is its counterpart, so the plan sends
` no shutdown` exactly while the device is shut. An interface the device does not hold yet is
created with it.

The captures are real, with minimal edits: IOS-XE is r2's capture
(tests/fixtures/configs/fleet/r2.cfg) with the default block measured on its new NIC
(tests/fixtures/operational/interface_defaults/c8000v_17.06_new_nic.txt: ` no ip address`,
` shutdown`, ...) placed after GigabitEthernet3's, as the device printed it; up again it is the
same text without ` shutdown`. IOS is s1's capture (vIOS-L2, fleet/s1.cfg), whose
GigabitEthernet0/1 holds only ` negotiation auto`; shut, it gains ` shutdown` before that line,
the position the IOS-XE measurement shows (IOS's own is assumed the same).
"""

import copy
import os

import pytest

from modules.nsot import platform_defaults, roundtrip
from modules.nsot.deploy import classify_diff, merge_commands, merge_diff
from modules.nsot.parsers import get_parser
from modules.nsot.render_artifact import build_artifact

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
MEASURED = os.path.join(ROOT, "tests", "fixtures", "operational", "interface_defaults",
                        "c8000v_17.06_new_nic.txt")

R2 = open(os.path.join(FLEET, "r2.cfg"), encoding="utf-8").read()
S1 = open(os.path.join(FLEET, "s1.cfg"), encoding="utf-8").read()

#: Where the new NIC's block sits in r2's running config: after GigabitEthernet3's block.
R2_ANCHOR = " no mop sysid\n!\nrouter ospf 1"
#: s1's unused port, up: the whole block as captured.
S1_UP = "interface GigabitEthernet0/1\n negotiation auto\n!\n"


def _measured_r2_block() -> str:
    """r2's new-NIC block from the measurement, as the device printed it."""
    text = open(MEASURED, encoding="utf-8").read()
    block = text.split("! r2\n", 1)[1].split("!\n", 1)[0]
    assert block.startswith("interface GigabitEthernet4\n") and " shutdown\n" in block
    return block


def _r2_shut() -> str:
    assert R2.count(R2_ANCHOR) == 1
    return R2.replace(R2_ANCHOR, " no mop sysid\n!\n" + _measured_r2_block() + "!\nrouter ospf 1")


def _s1_shut() -> str:
    assert S1.count(S1_UP) == 1
    return S1.replace(S1_UP, "interface GigabitEthernet0/1\n shutdown\n negotiation auto\n!\n")


#: ``(platform, interface, shut capture, the same capture brought up)``.
CASES = {
    "iosxe": ("cisco_iosxe", "GigabitEthernet4", _r2_shut,
              lambda: _r2_shut().replace(" no ip address\n shutdown\n", " no ip address\n")),
    "ios": ("cisco_ios", "GigabitEthernet0/1", _s1_shut, lambda: S1),
}


def _seed(platform: str, capture: str) -> dict:
    """Intent as the seed makes it: the capture's own parse."""
    return get_parser(platform).parse(capture)


def _iface(host_vars: dict, name: str) -> dict:
    return next(i for i in host_vars["interfaces"] if i["name"] == name)


def _brought_up(host_vars: dict, name: str) -> dict:
    """The intent edit 0d made: `shutdown: true` to `shutdown: false`, `no_shutdown: true`."""
    edited = copy.deepcopy(host_vars)
    iface = _iface(edited, name)
    iface["shutdown"], iface["no_shutdown"] = False, True
    return edited


def _render(host_vars: dict, platform: str) -> str:
    return roundtrip.render(host_vars, host_vars.get("platform", platform))


def _for(program: list, name: str) -> list:
    """The program's lines for one interface, its header included."""
    out, inside = [], False
    for line in program:
        if not line.startswith(" ") and line != "exit":
            inside = line == f"interface {name}"
        if inside and line != "exit":
            out.append(line)
    return out


@pytest.mark.parametrize("dialect", sorted(CASES))
class TestAnInterfaceBroughtUpConverges:

    def test_the_fixture_can_exhibit_the_case(self, dialect):
        platform, name, shut, up = CASES[dialect]
        assert _iface(_seed(platform, shut()), name)["shutdown"] is True
        assert _iface(_seed(platform, up()), name)["shutdown"] is False
        # Neither capture, nor any up interface in them, prints `no shutdown`.
        assert " no shutdown" not in shut() + up()
        # The seed's `no_shutdown: false` on every interface is the schema default (a key
        # every template may name), not a reading: the parser sets it only from the line.
        assert all(i["no_shutdown"] is False for i in _seed(platform, up())["interfaces"])

    def test_the_seed_s_own_plan_is_empty(self, dialect):
        platform, _name, shut, _up = CASES[dialect]
        intent = _seed(platform, shut())
        assert merge_commands(_render(intent, platform), shut()) == []

    def test_the_first_plan_sends_no_shutdown(self, dialect):
        platform, name, shut, _up = CASES[dialect]
        intent = _brought_up(_seed(platform, shut()), name)
        rendered = _render(intent, platform)
        assert f"interface {name}\n" in rendered and " no shutdown\n" in rendered
        program = merge_commands(rendered, shut())
        assert program == [f"interface {name}", " no shutdown", "exit"], program
        # The preview's answer is the program's: a replacement of the captured `shutdown`.
        assert classify_diff(rendered, shut())["replace"] == [
            {"line": " no shutdown", "old": " shutdown", "new": " no shutdown"}]

    def test_after_the_new_capture_the_next_plan_sends_nothing(self, dialect):
        platform, name, shut, up = CASES[dialect]
        intent = _brought_up(_seed(platform, shut()), name)
        rendered = _render(intent, platform)
        assert merge_commands(rendered, up()) == []
        diff = merge_diff(rendered, up())
        assert diff["to_add"] == [] and diff["add"] == [] and diff["replace"] == []
        assert diff["residue"] == []

    def test_the_round_trip_and_intent_match_say_converged(self, dialect):
        platform, name, shut, up = CASES[dialect]
        intent = _brought_up(_seed(platform, shut()), name)
        rendered = _render(intent, platform)
        report = roundtrip.compare(up(), rendered, intent)
        assert report["ok"], report["details"]
        rows = roundtrip.change_rows(up(), rendered)
        assert rows["added"] == [] and rows["removed"] == []
        artifact = build_artifact(intent["hostname"], up(), platform, host_vars=intent)
        assert artifact.intent_drift["differs"] is False, artifact.intent_drift

    def test_while_the_device_is_still_shut_intent_match_says_it_differs(self, dialect):
        """The control the convergence is read against: the shut capture still differs."""
        platform, name, shut, _up = CASES[dialect]
        intent = _brought_up(_seed(platform, shut()), name)
        artifact = build_artifact(intent["hostname"], shut(), platform, host_vars=intent)
        assert artifact.intent_drift["differs"] is True
        assert artifact.intent_drift["removes"] == 1          # the device's ` shutdown`


@pytest.mark.parametrize("dialect", sorted(CASES))
class TestAnInterfaceIntendedShutStaysShut:

    def test_shut_intent_on_a_shut_device_sends_nothing(self, dialect):
        platform, _name, shut, _up = CASES[dialect]
        assert merge_commands(_render(_seed(platform, shut()), platform), shut()) == []

    def test_shut_intent_on_an_up_device_sends_shutdown(self, dialect):
        platform, name, shut, up = CASES[dialect]
        rendered = _render(_seed(platform, shut()), platform)
        assert _for(merge_commands(rendered, up()), name) == [f"interface {name}", " shutdown"]

    def test_intent_naming_neither_never_brings_a_shut_interface_up(self, dialect):
        """Merge-only: an interface whose intent says nothing either way is left as it is."""
        platform, name, shut, _up = CASES[dialect]
        intent = copy.deepcopy(_seed(platform, shut()))
        _iface(intent, name)["shutdown"] = False
        assert _for(merge_commands(_render(intent, platform), shut()), name) == []


class TestOnlyWhereTheDeviceHoldsTheInterface:

    def test_a_new_interface_is_created_with_its_no_shutdown(self):
        """No `shutdown` printed under an interface the device does not hold says nothing:
        the line is part of creating it."""
        intent = _seed("cisco_iosxe", R2)
        intent["interfaces"].append({**_iface(intent, "Loopback0"), "name": "Loopback9",
                                     "description": "", "ipv4": "192.0.2.9 255.255.255.255",
                                     "ipv6": ["2001:DB8:9::9/128"], "ospfv3_interface": {},
                                     "ospfv3": [], "no_shutdown": True})
        program = merge_commands(_render(intent, "cisco_iosxe"), R2)
        assert _for(program, "Loopback9") == [
            "interface Loopback9", " ip address 192.0.2.9 255.255.255.255",
            " ipv6 address 2001:DB8:9::9/128", " no shutdown"], program

    def test_only_a_direct_child_of_an_interface(self):
        assert platform_defaults.hidden(["interface GigabitEthernet4"], " no shutdown")
        assert not platform_defaults.hidden(
            ["interface Vlan10", " vrrp 10 address-family ipv4"], "  no shutdown")
        assert not platform_defaults.hidden(["router bgp 65001"], " no shutdown")
        assert not platform_defaults.hidden([], "no shutdown")
        assert not platform_defaults.hidden(["interface GigabitEthernet4"], " shutdown")


def test_compare_asks_the_one_table():
    """By parsing, as tests/test_platform_defaults.py does for the other four: the render
    report Intent-Match reads (`roundtrip.compare`) asks `platform_defaults`."""
    import ast
    tree = ast.parse(open(os.path.join(ROOT, "modules", "nsot", "roundtrip.py"),
                          encoding="utf-8").read())
    node = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "compare")
    names = {getattr(n, "id", getattr(n, "attr", "")) for n in ast.walk(node)}
    assert "platform_defaults" in names
