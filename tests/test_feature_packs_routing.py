"""K7 (C764): the routing feature packs, OSPFv2, OSPFv3, RIPv2 and RIPng (docs/FEATURE_PACKS.md).

What is held here, each against the lab's real captures (tests/fixtures/configs/, the host's
committed goldens and intents in tests/fixtures/committed/):

1. every capture still round-trips, and its parse is a fixed point;
2. a capture's parse holds in the packs' fields exactly what its routing lines say;
3. structured intent (an ABR with areas 0, 10 and 20, RIPv2 and OSPF redistributing into each
   other, OSPFv3 and RIPng with IPv6 ranges and interfaces) renders the exact expected lines for
   BOTH Cisco dialects;
4. the render of a capture's parse gives back each routing block of the capture line for line,
   in the device's order (a block holding a line no pack models: the same lines, the unmodelled
   one after);
5. a field a pack refuses is refused naming the field, its value and what it was compared
   with, by the editor's check and by the render, the IPv6 case beside the IPv4 one;
6. an intent written before the packs (the host's committed r2 and s1) renders byte for byte as
   it did through the templates from before the packs, and structured intent rendered through
   those old templates still gives the device's lines (`features.for_library`).
"""

import copy
import os
import subprocess

import pytest
import yaml

from modules.nsot import features, hostvars, roundtrip
from modules.nsot.parsers import get_parser
from modules.nsot.parsers.base import split_blocks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
#: The last commit before the packs: its shipped templates are "a library from before them".
BEFORE_PACKS = "5666edb5"
PLATFORMS = ("cisco_ios", "cisco_iosxe")
ROUTING_HEADS = ("router ospf", "router rip", "ipv6 router ospf", "ipv6 router rip")


def _platform(name):
    return "cisco_iosxe" if os.path.basename(name).startswith("r") else "cisco_ios"


def _captures():
    """``[(label, platform, text)]``: every captured configuration the round-trip tests use, and
    the host's two committed goldens."""
    out = []
    for folder in ("configs/fleet", "configs", "committed"):
        for name in sorted(os.listdir(os.path.join(FIX, folder))):
            if name.endswith(".cfg"):
                with open(os.path.join(FIX, folder, name), encoding="utf-8") as fh:
                    out.append((f"{folder}/{name}", _platform(name), fh.read()))
    return out


CAPTURES = _captures()


def _parse(label):
    _l, platform, text = next(c for c in CAPTURES if c[0] == label)
    return get_parser(platform).parse(text)


def _blocks(text, heads=ROUTING_HEADS):
    """``{header: [child lines, stripped]}`` for the blocks of *text* starting with *heads*."""
    return {b.stripped: [c.strip() for c in b.children]
            for b in split_blocks(text) if b.stripped.startswith(heads)}


def _secret(_name):
    return "x"


def test_the_population():
    """A floor, so a fixture folder emptied by mistake cannot pass every test below."""
    assert len(CAPTURES) >= 13
    with_routing = [label for label, _p, text in CAPTURES if _blocks(text)]
    assert len(with_routing) >= 12, with_routing


# ── 1. the round trip ────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", [c[0] for c in CAPTURES])
def test_every_capture_still_round_trips(label):
    _l, platform, text = next(c for c in CAPTURES if c[0] == label)
    hv = get_parser(platform).parse(text)
    report = roundtrip.compare(text, roundtrip.render(hv, platform), hv)
    assert report["ok"], report["details"]


@pytest.mark.parametrize("label", [c[0] for c in CAPTURES])
def test_the_parse_is_a_fixed_point(label):
    """parse → render → parse gives the same document: what the packs model they render back
    as the lines they were parsed from."""
    _l, platform, text = next(c for c in CAPTURES if c[0] == label)
    first = get_parser(platform).parse(text)
    second = get_parser(platform).parse(roundtrip.render(first, platform))
    assert hostvars.to_yaml(second) == hostvars.to_yaml(first)


@pytest.mark.parametrize("label", [c[0] for c in CAPTURES])
def test_a_capture_s_parse_passes_every_pack_check(label):
    """A parse the render would refuse would block its own device: the parser models a line
    only when the result passes."""
    assert features.problems(_parse(label)) == []


# ── 2. parse → the packs' fields ─────────────────────────────────────────────

def _iface(hv, name):
    return next(i for i in hv["interfaces"] if i["name"] == name)


def _statements(label):
    """The capture's own RIP network statements' addresses, read from its text (a path
    independent of the parser)."""
    _l, _p, text = next(c for c in CAPTURES if c[0] == label)
    return [l.split()[1] for l in _blocks(text)["router rip"] if l.startswith("network ")]


class TestTheParseHoldsWhatTheConfigSays:
    def test_an_ios_xe_router_running_ospf_rip_and_their_ipv6_twins(self):
        """configs/fleet/r1.cfg: OSPF 1 redistributing RIP, RIPv2 passive by default, OSPFv3
        redistributing RIPng with connected routes, and every interface's own lines."""
        hv = _parse("configs/fleet/r1.cfg")
        (ospf,) = hv["routing"]["ospf"]
        assert ospf["process"] == "1" and ospf["router_id"] == "10.255.1.11"
        assert ospf["redistribute"] == [{"protocol": "rip"}]
        assert ospf["passive_interfaces"] == ["Loopback0"]
        assert ospf["areas"] == [{"id": "0", "networks": [
            {"address": "10.255.1.11", "wildcard": "0.0.0.0"},
            {"address": "10.255.3.0", "wildcard": "0.0.0.255"}]}]
        assert (ospf["settings"], ospf["networks"]) == ([], [])
        rip = hv["routing"]["rip"]
        assert (rip["version"], rip["passive_default"], rip["no_passive_interfaces"]) == (
            "2", True, ["GigabitEthernet3"])
        assert rip["classful_networks"] == _statements("configs/fleet/r1.cfg") and \
            len(rip["classful_networks"]) == 1
        assert rip["default_information"] == {"originate": True}
        assert rip["auto_summary"] is False
        assert (rip["settings"], rip["networks"]) == ([], [])
        (v3,) = hv["routing"]["ospfv3"]
        assert v3["router_id"] == "10.255.1.11" and v3["raw"] == []
        assert v3["redistribute"] == [{"protocol": "rip", "process": "RCN",
                                       "include_connected": True}]
        assert hv["routing"]["ripng"] == [{"name": "RCN", "redistribute": [], "raw": []}]
        assert _iface(hv, "Loopback0")["ospfv3_interface"] == {"process": "1", "area": "0"}
        gi2 = _iface(hv, "GigabitEthernet2")
        assert gi2["ospf_interface"] == {"priority": "100"}
        assert gi2["ospfv3_interface"] == {"process": "1", "area": "0"}
        assert (gi2["ospf"], gi2["ospfv3"]) == ([], [])
        gi3 = _iface(hv, "GigabitEthernet3")
        assert gi3["ripng_interface"] == [{"name": "RCN", "enable": True,
                                           "default_information": "originate"}]
        assert gi3["ripng"] == []

    def test_an_abr_s_neighbour_with_a_default_route_in_both_families(self):
        """configs/fleet/r3.cfg: three area-0 networks (a /31 among them), the default route
        always originated in OSPF and OSPFv3, OSPFv3 redistributing static."""
        hv = _parse("configs/fleet/r3.cfg")
        (ospf,) = hv["routing"]["ospf"]
        assert [n["wildcard"] for n in ospf["areas"][0]["networks"]] == [
            "0.0.0.0", "0.0.0.1", "0.0.0.255"]
        assert ospf["default_information"] == {"originate": True, "always": True}
        (v3,) = hv["routing"]["ospfv3"]
        assert v3["default_information"] == {"originate": True, "always": True}
        assert v3["redistribute"] == [{"protocol": "static"}]

    def test_an_ios_switch_redistributing_static_with_subnets(self):
        """configs/fleet/s3.cfg (IOS 15.2): `redistribute static subnets`, two passive
        interfaces, one /16 network, and a DROTHER's `ip ospf priority 0`."""
        hv = _parse("configs/fleet/s3.cfg")
        (ospf,) = hv["routing"]["ospf"]
        assert ospf["redistribute"] == [{"protocol": "static", "subnets": True}]
        assert ospf["passive_interfaces"] == ["Loopback0", "Vlan99"]
        assert ospf["areas"] == [{"id": "0", "networks": [
            {"address": "10.255.0.0", "wildcard": "0.0.255.255"}]}]
        assert [i["name"] for i in hv["interfaces"]
                if i["ospf_interface"] == {"priority": "0"}], "the priority-0 interface"

    def test_an_ios_switch_running_rip_and_ripng(self):
        """configs/fleet/s1.cfg (IOS 15.2): RIPv2 with three passive interfaces, RIPng enabled
        on four interfaces."""
        hv = _parse("configs/fleet/s1.cfg")
        rip = hv["routing"]["rip"]
        assert rip["passive_interfaces"] == ["Loopback0", "Vlan10", "Vlan20"]
        assert (rip["version"], rip["auto_summary"]) == ("2", False)
        assert rip["classful_networks"] == _statements("configs/fleet/s1.cfg")
        assert len(rip["classful_networks"]) == 1
        enabled = [i["name"] for i in hv["interfaces"] if i["ripng_interface"]]
        assert len(enabled) == 4
        for name in enabled:
            assert _iface(hv, name)["ripng_interface"] == [{"name": "RCN", "enable": True}]

    def test_a_line_the_pack_would_write_differently_stays_verbatim(self):
        """Planted (one line added to configs/fleet/r1.cfg's OSPF block): the pack reads
        `redistribute connected route-map RM metric 5` but writes `metric` before `route-map`,
        so the line is no field: it stays in `settings` as typed, and the round trip holds.
        Its control, the pack's order, is modelled in the same block."""
        _l, platform, text = next(c for c in CAPTURES if c[0] == "configs/fleet/r1.cfg")
        planted = text.replace(" redistribute rip\n",
                               " redistribute rip\n redistribute connected route-map RM metric 5\n"
                               " redistribute static metric 5 route-map RM\n", 1)
        assert planted != text
        hv = get_parser(platform).parse(planted)
        (ospf,) = hv["routing"]["ospf"]
        assert ospf["settings"] == ["redistribute connected route-map RM metric 5"]
        assert ospf["redistribute"] == [{"protocol": "rip"},
                                        {"protocol": "static", "metric": "5",
                                         "route_map": "RM"}]
        assert roundtrip.compare(planted, roundtrip.render(hv, platform), hv)["ok"]

    def test_an_interface_naming_a_process_routing_lacks_keeps_its_lines(self):
        """Planted (configs/fleet/r1.cfg with its `ipv6 router ospf 1` block written as IOS-XE's
        newer `router ospfv3 1`, which no pack parses): the interfaces' `ipv6 ospf 1 area 0`
        name a process `routing.ospfv3` does not hold, which the render would refuse, so the
        parse leaves those lines as they were (`features.settle`) and the round trip holds."""
        _l, platform, text = next(c for c in CAPTURES if c[0] == "configs/fleet/r1.cfg")
        planted = text.replace("\nipv6 router ospf 1\n", "\nrouter ospfv3 1\n", 1)
        assert planted != text
        hv = get_parser(platform).parse(planted)
        assert hv["routing"]["ospfv3"] == []
        assert features.problems(hv) == []
        loop = _iface(hv, "Loopback0")
        assert (loop["ospfv3_interface"], loop["ospfv3"]) == ({}, ["1 area 0"])
        assert _iface(hv, "GigabitEthernet2")["ospf_interface"] == {"priority": "100"}
        assert roundtrip.compare(planted, roundtrip.render(hv, platform), hv)["ok"]

    def test_a_line_no_pack_models_stays_verbatim_where_it_was(self):
        """committed/r2.cfg, the host's golden: `max-metric` is no pack's field, so it stays an
        unmodelled line, in OSPF's `settings` and OSPFv3's `raw`; everything else is modelled."""
        hv = _parse("committed/r2.cfg")
        (ospf,) = hv["routing"]["ospf"]
        assert ospf["settings"] == ["max-metric router-lsa external-lsa on-startup 5"]
        assert ospf["router_id"] == "10.255.1.12" and ospf["networks"] == []
        (v3,) = hv["routing"]["ospfv3"]
        assert v3["raw"] == ["max-metric router-lsa on-startup 5"]
        assert v3["redistribute"] == [{"protocol": "rip", "process": "RCN",
                                       "include_connected": True}]


# ── 3. structured intent → the exact lines, both dialects ───────────────────

#: An ABR (areas 0, 10 and 20; area 10 summarised, area 20 a totally stubby area), RIPv2 and
#: OSPF redistributing into each other with a metric, OSPFv3 summarising an IPv6 range, and
#: RIPng redistributing OSPFv3: the shape of Labs 8 and 9, in documentation addresses.
ROUTING = {
    "ospf": [{"process": 1, "router_id": "192.0.2.4",
              "areas": [{"id": 0, "networks": [{"prefix": "192.0.2.128/30"}]},
                        {"id": 10, "networks": [{"prefix": "192.0.2.0/26"},
                                                {"address": "192.0.2.64",
                                                 "wildcard": "0.0.0.63"}],
                         "ranges": [{"prefix": "192.0.2.0/25"}]},
                        {"id": 20, "type": "stub", "no_summary": True, "default_cost": 10,
                         "networks": [{"prefix": "192.0.2.192/27"}]}],
              "redistribute": [{"protocol": "rip", "subnets": True}],
              "passive_interfaces": ["Loopback0"],
              "default_information": {"originate": True}}],
    "rip": {"version": 2, "redistribute": [{"protocol": "ospf", "process": 1, "metric": 5}],
            "passive_default": True, "no_passive_interfaces": ["GigabitEthernet0/2"],
            "classful_networks": ["192.0.2.0"], "auto_summary": False},
    "ospfv3": [{"process": 1, "router_id": "192.0.2.4",
                "areas": [{"id": 10, "ranges": [{"prefix": "2001:DB8:10::/48"}]}],
                "redistribute": [{"protocol": "rip", "process": "EDGE",
                                  "include_connected": True}]}],
    "ripng": [{"name": "EDGE", "redistribute": [{"protocol": "ospf", "process": 1,
                                                 "metric": 3}]}],
    "bgp": None,
}
INTERFACES = [
    {"name": "Loopback0", "ipv4": "192.0.2.4 255.255.255.255"},
    {"name": "GigabitEthernet0/1", "ipv4": "192.0.2.129 255.255.255.252",
     "ipv6": ["2001:DB8:A::1/64"],
     "ospf_interface": {"process": 1, "area": 0, "network_type": "point-to-point",
                        "cost": 10},
     "ospfv3_interface": {"process": 1, "area": 10},
     "ripng_interface": [{"name": "EDGE", "enable": True}]},
    {"name": "GigabitEthernet0/2", "ipv4": "192.0.2.65 255.255.255.192",
     "ipv6": ["2001:DB8:B::1/64"],
     "ripng_interface": [{"name": "EDGE", "enable": True,
                          "default_information": "originate"}]},
]
EXPECTED = {
    "router ospf 1": [
        "router-id 192.0.2.4",
        "area 10 range 192.0.2.0 255.255.255.128",
        "area 20 stub no-summary",
        "area 20 default-cost 10",
        "redistribute rip subnets",
        "passive-interface Loopback0",
        "network 192.0.2.128 0.0.0.3 area 0",
        "network 192.0.2.0 0.0.0.63 area 10",
        "network 192.0.2.64 0.0.0.63 area 10",
        "network 192.0.2.192 0.0.0.31 area 20",
        "default-information originate"],
    "router rip": [
        "version 2",
        "redistribute ospf 1 metric 5",
        "passive-interface default",
        "no passive-interface GigabitEthernet0/2",
        "network 192.0.2.0",
        "no auto-summary"],
    "ipv6 router ospf 1": [
        "router-id 192.0.2.4",
        "area 10 range 2001:DB8:10::/48",
        "redistribute rip EDGE include-connected"],
    "ipv6 router rip EDGE": [
        "redistribute ospf 1 metric 3"],
}
EXPECTED_INTERFACES = {
    "interface GigabitEthernet0/1": [
        "ip address 192.0.2.129 255.255.255.252",
        "ip ospf network point-to-point",
        "ip ospf 1 area 0",
        "ip ospf cost 10",
        "ipv6 address 2001:DB8:A::1/64",
        "ipv6 ospf 1 area 10",
        "ipv6 rip EDGE enable"],
    "interface GigabitEthernet0/2": [
        "ip address 192.0.2.65 255.255.255.192",
        "ipv6 address 2001:DB8:B::1/64",
        "ipv6 rip EDGE enable",
        "ipv6 rip EDGE default-information originate"],
}


def _authored(platform, routing=None, interfaces=None):
    """A real capture's parse of *platform* (a vIOS-L2 switch, a C8000v router) with its routing
    and interfaces replaced by the authored ones: the document a person edits."""
    base = _parse("configs/fleet/s1.cfg" if platform == "cisco_ios" else "configs/fleet/r1.cfg")
    doc = copy.deepcopy(base)
    doc.update(hostname="edge1", routing=copy.deepcopy(routing or ROUTING),
               interfaces=copy.deepcopy(INTERFACES if interfaces is None else interfaces))
    return doc


@pytest.mark.parametrize("platform", PLATFORMS)
class TestStructuredIntentRendersTheExactLines:
    def test_the_routing_blocks(self, platform):
        rendered = roundtrip.render(_authored(platform), platform, secret_lookup=_secret)
        assert _blocks(rendered) == EXPECTED

    def test_the_interfaces_own_lines(self, platform):
        rendered = roundtrip.render(_authored(platform), platform, secret_lookup=_secret)
        got = _blocks(rendered, heads=tuple(EXPECTED_INTERFACES))
        assert got == EXPECTED_INTERFACES

    def test_what_it_renders_parses_back_to_the_same_fields(self, platform):
        """The authored intent → its lines → the dialect's parser: the same fields, the
        authored prefixes in IOS's notation (192.0.2.0/26 is 192.0.2.0 0.0.0.63)."""
        rendered = roundtrip.render(_authored(platform), platform, secret_lookup=_secret)
        back = get_parser(platform).parse(rendered)
        (ospf,) = back["routing"]["ospf"]
        assert [a["id"] for a in ospf["areas"]] == ["10", "20", "0"]   # first seen, IOS order
        area10 = ospf["areas"][0]
        assert area10["ranges"] == [{"address": "192.0.2.0", "mask": "255.255.255.128"}]
        assert area10["networks"] == [{"address": "192.0.2.0", "wildcard": "0.0.0.63"},
                                      {"address": "192.0.2.64", "wildcard": "0.0.0.63"}]
        assert ospf["areas"][1] == {"id": "20", "type": "stub", "no_summary": True,
                                    "default_cost": "10", "networks": [
                                        {"address": "192.0.2.192", "wildcard": "0.0.0.31"}]}
        assert back["routing"]["rip"]["redistribute"] == [
            {"protocol": "ospf", "process": "1", "metric": "5"}]
        (v3,) = back["routing"]["ospfv3"]
        assert v3["areas"] == [{"id": "10", "ranges": [{"prefix": "2001:DB8:10::/48"}]}]
        assert _iface(back, "GigabitEthernet0/1")["ospfv3_interface"] == {
            "process": "1", "area": "10"}
        for block in (ospf["settings"], ospf["networks"], v3["raw"],
                      back["routing"]["rip"]["settings"]):
            assert block == []

    def test_a_range_not_advertised_with_a_cost_in_both_families(self, platform):
        routing = copy.deepcopy(ROUTING)
        routing["ospf"][0]["areas"][1]["ranges"] = [
            {"address": "192.0.2.0", "mask": "255.255.255.128", "advertise": False},
            {"prefix": "192.0.2.0/26", "cost": 20}]
        routing["ospfv3"][0]["areas"][0]["ranges"] = [
            {"prefix": "2001:DB8:10::/48", "advertise": False},
            {"prefix": "2001:DB8:11::/48", "cost": 20}]
        rendered = roundtrip.render(_authored(platform, routing), platform,
                                    secret_lookup=_secret)
        blocks = _blocks(rendered)
        assert [l for l in blocks["router ospf 1"] if " range " in l] == [
            "area 10 range 192.0.2.0 255.255.255.128 not-advertise",
            "area 10 range 192.0.2.0 255.255.255.192 cost 20"]
        assert [l for l in blocks["ipv6 router ospf 1"] if " range " in l] == [
            "area 10 range 2001:DB8:10::/48 not-advertise",
            "area 10 range 2001:DB8:11::/48 cost 20"]


# ── 4. render(parse(capture)) gives back the capture's blocks ────────────────

@pytest.mark.parametrize("label", [c[0] for c in CAPTURES if _blocks(c[2])])
def test_each_routing_block_comes_back_line_for_line(label):
    """Every routing block of every capture: the render of its parse holds the same lines in
    the device's own order. Where a block holds a line no pack models (`max-metric`, on the
    host's r2), that line follows the modelled ones, so the block holds the same lines and the
    modelled ones keep the device's order."""
    _l, platform, text = next(c for c in CAPTURES if c[0] == label)
    hv = get_parser(platform).parse(text)
    rendered = _blocks(roundtrip.render(hv, platform, secret_lookup=_secret))
    captured = _blocks(text)
    assert set(rendered) == set(captured)
    for head, lines in captured.items():
        unmodelled = _unmodelled(hv, head)
        modelled = [l for l in lines if l not in unmodelled]
        assert rendered[head] == modelled + unmodelled, head


def _unmodelled(hv, head):
    routing = hv["routing"]
    words = head.split()
    if head.startswith("router ospf"):
        p = next(p for p in routing["ospf"] if p["process"] == words[2])
        return p["settings"] + p["networks"]
    if head == "router rip":
        return routing["rip"]["settings"] + routing["rip"]["networks"]
    if head.startswith("ipv6 router ospf"):
        return next(p for p in routing["ospfv3"] if p["process"] == words[3])["raw"]
    return next(p for p in routing["ripng"] if p["name"] == words[3])["raw"]


@pytest.mark.parametrize("label", [c[0] for c in CAPTURES if _blocks(c[2])])
def test_each_interface_s_routing_lines_come_back(label):
    """Every interface's `ip ospf`, `ipv6 ospf` and `ipv6 rip` lines, as a set (IOS orders an
    interface's lines itself)."""
    _l, platform, text = next(c for c in CAPTURES if c[0] == label)
    hv = get_parser(platform).parse(text)
    rendered = _blocks(roundtrip.render(hv, platform, secret_lookup=_secret), ("interface",))
    prefixes = ("ip ospf ", "ipv6 ospf ", "ipv6 rip ")
    for head, lines in _blocks(text, ("interface",)).items():
        mine = sorted(l for l in lines if l.startswith(prefixes))
        assert sorted(l for l in rendered[head] if l.startswith(prefixes)) == mine, head


# ── 5. refusals name the field, the value and what it was compared with ─────

def _routing_with(**changes):
    routing = copy.deepcopy(ROUTING)
    for path, value in changes.items():
        node = routing
        keys = path.split("__")
        for key in keys[:-1]:
            node = node[int(key)] if key.isdigit() else node[key]
        last = keys[-1]
        node[int(last) if last.isdigit() else last] = value
    return routing


REFUSALS = [
    # (what is wrong, the changed field, the words the refusal must hold)
    ("an area id that is not a number",
     {"ospf__0__areas__1__id": "ten"},
     ["routing.ospf[0].areas[1].id is 'ten'", "0 to 4294967295", "dotted quad"]),
    ("an area id past 32 bits",
     {"ospf__0__areas__1__id": "4294967296"},
     ["routing.ospf[0].areas[1].id is '4294967296'", "0 to 4294967295"]),
    ("one area written twice",
     {"ospf__0__areas__1__id": "0.0.0.0"},
     ["routing.ospf[0].areas[1].id is '0.0.0.0'", "routing.ospf[0].areas[0].id (0)"]),
    ("a network prefix with host bits (IPv4)",
     {"ospf__0__areas__0__networks__0__prefix": "192.0.2.129/30"},
     ["routing.ospf[0].areas[0].networks[0].prefix is '192.0.2.129/30'",
      "not an IPv4 network", "host bits"]),
    ("a range with host bits (IPv4)",
     {"ospf__0__areas__1__ranges__0__prefix": "192.0.2.1/25"},
     ["routing.ospf[0].areas[1].ranges[0].prefix is '192.0.2.1/25'", "host bits"]),
    ("a range with host bits (IPv6)",
     {"ospfv3__0__areas__0__ranges__0__prefix": "2001:DB8:10::1/48"},
     ["routing.ospfv3[0].areas[0].ranges[0].prefix is '2001:DB8:10::1/48'",
      "an OSPFv3 range is an IPv6 network", "host bits"]),
    ("an IPv4 range given to OSPFv3",
     {"ospfv3__0__areas__0__ranges__0__prefix": "192.0.2.0/25"},
     ["routing.ospfv3[0].areas[0].ranges[0].prefix is '192.0.2.0/25'",
      "an OSPFv3 range is an IPv6 network"]),
    ("a protocol OSPF does not redistribute here",
     {"ospf__0__redistribute__0__protocol": "isis"},
     ["routing.ospf[0].redistribute[0].protocol is 'isis'",
      "bgp, connected, eigrp, ospf, rip, static"]),
    ("a protocol RIPng does not redistribute here",
     {"ripng__0__redistribute__0__protocol": "isis"},
     ["routing.ripng[0].redistribute[0].protocol is 'isis'", "bgp, connected, ospf, static"]),
    ("OSPF redistributed without its process",
     {"rip__redistribute__0__process": ""},
     ["routing.rip.redistribute[0].process is ''", "redistributing ospf names its process"]),
    ("a RIP network that is not classful",
     {"rip__classful_networks__0": "192.0.2.64"},
     ["routing.rip.classful_networks[0] is '192.0.2.64'", "192.0.2.0/24", "write 192.0.2.0"]),
    ("no-summary on a normal area",
     {"ospf__0__areas__1__no_summary": True},
     ["routing.ospf[0].areas[1].no_summary is True", "type is 'normal'"]),
    ("a passive interface listed under passive-interface default",
     {"rip__passive_interfaces": ["Loopback0"]},
     ["routing.rip.passive_interfaces is ['Loopback0']", "passive_default is true"]),
    ("a router id that is not an address",
     {"ospfv3__0__router_id": "2001:DB8::4"},
     ["routing.ospfv3[0].router_id is '2001:DB8::4'", "an IPv4 address (OSPFv3's too)"]),
]


@pytest.mark.parametrize("why, change, words", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_a_refusal_names_the_field_its_value_and_the_rule(why, change, words):
    found = features.problems({"routing": _routing_with(**change), "interfaces": INTERFACES})
    text = "; ".join(m for _p, _k, m in found)
    assert found, why
    for w in words:
        assert w in text, (why, w, text)


INTERFACE_REFUSALS = [
    ("an interface naming an OSPF process routing does not hold (IPv4)",
     1, "ospf_interface", {"process": 2, "area": 0},
     ["interfaces[1].ospf_interface.process is 2", "process(es) ['1']"]),
    ("an interface naming an OSPFv3 process routing does not hold (IPv6)",
     1, "ospfv3_interface", {"process": 2, "area": 10},
     ["interfaces[1].ospfv3_interface.process is 2", "process(es) ['1']"]),
    ("an interface area that is no area (IPv4)",
     1, "ospf_interface", {"process": 1, "area": "backbone"},
     ["interfaces[1].ospf_interface.area is 'backbone'", "0 to 4294967295"]),
    ("an interface area that is no area (IPv6)",
     1, "ospfv3_interface", {"process": 1, "area": "backbone"},
     ["interfaces[1].ospfv3_interface.area is 'backbone'", "0 to 4294967295"]),
    ("a process without its area",
     1, "ospf_interface", {"process": 1},
     ["interfaces[1].ospf_interface.area is None", "process (1)", "given together"]),
    ("an interface naming a RIPng process routing does not hold",
     2, "ripng_interface", [{"name": "OTHER", "enable": True}],
     ["interfaces[2].ripng_interface[0].name is 'OTHER'", "RIPng process(es) ['EDGE']"]),
]


@pytest.mark.parametrize("why, index, key, value, words", INTERFACE_REFUSALS,
                         ids=[r[0] for r in INTERFACE_REFUSALS])
def test_an_interface_refusal_names_the_field_and_both_operands(why, index, key, value, words):
    interfaces = copy.deepcopy(INTERFACES)
    interfaces[index][key] = value
    text = "; ".join(m for _p, _k, m in features.problems(
        {"routing": copy.deepcopy(ROUTING), "interfaces": interfaces}))
    for w in words:
        assert w in text, (why, w, text)


def test_the_authored_intent_itself_passes():
    """The control for the refusals above: the document they each change by one field."""
    assert features.problems({"routing": copy.deepcopy(ROUTING), "interfaces": INTERFACES}) == []


def test_the_render_refuses_naming_the_field():
    doc = _authored("cisco_iosxe", _routing_with(ospf__0__areas__1__id="ten"))
    with pytest.raises(features.FeatureIntentInvalid) as exc:
        roundtrip.render(doc, "cisco_iosxe", secret_lookup=_secret)
    assert "routing.ospf[0].areas[1].id is 'ten'" in str(exc.value)


def test_the_editor_refuses_with_the_field_s_line():
    """The intent editor's own check (`intent_edit.validate`, run by its preview and its save):
    stage schema, the line of the refused key, and the words."""
    from modules.nsot import intent_edit
    doc = _authored("cisco_iosxe", _routing_with(**{"rip__classful_networks__0": "192.0.2.64"}))
    doc["logging"]["syslog"]["heartbeat"] = 300        # the editor's syslog rule (whole block)
    text = hostvars.to_yaml(doc)
    got = intent_edit.validate("edge1", text)
    assert got["ok"] is False and got["stage"] == "schema", got
    assert "routing.rip.classful_networks[0] is '192.0.2.64'" in got["error"]
    assert text.splitlines()[got["line"] - 1].strip() == "classful_networks:"


def test_the_editor_takes_the_authored_intent():
    """The control: the same document, unchanged, passes the editor."""
    from modules.nsot import intent_edit
    doc = _authored("cisco_iosxe")
    doc["logging"]["syslog"]["heartbeat"] = 300
    got = intent_edit.validate("edge1", hostvars.to_yaml(doc))
    assert got["ok"] is True, got


# ── 6. intent from before the packs, and libraries from before them ──────────

def _old_library(tmp_path):
    """The shipped templates as they were at BEFORE_PACKS, in a folder of their own."""
    root = tmp_path / "templates"
    for rel in ("_common.j2", "cisco_ios/base.j2", "cisco_iosxe/base.j2"):
        old = subprocess.run(["git", "-C", ROOT, "show",
                              f"{BEFORE_PACKS}:modules/nsot/templates/{rel}"],
                             capture_output=True, text=True)
        if old.returncode != 0:
            pytest.skip(f"no history for the shipped templates here: {old.stderr.strip()}")
        assert "ospf_interface" not in old.stdout, "not a library from before the packs"
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(old.stdout, encoding="utf-8")
    return str(root)


@pytest.mark.parametrize("name, platform", [("r2", "cisco_iosxe"), ("s1", "cisco_ios")])
def test_intent_from_before_the_packs_renders_byte_for_byte_as_it_did(tmp_path, name, platform):
    """The host's committed r2 and s1 (raw `settings`/`networks`/`raw` only), through today's
    shipped templates and through the templates from before the packs: the same bytes. The
    old library is the independent path: no pack macro is in it."""
    with open(os.path.join(FIX, "committed", f"{name}.yml"), encoding="utf-8") as fh:
        intent = yaml.safe_load(fh)
    assert not features.structured(intent), "the committed fixture holds lines only"
    now = roundtrip.render(intent, platform, secret_lookup=_secret)
    then = roundtrip.render(intent, platform, secret_lookup=_secret,
                            template_root=_old_library(tmp_path))
    assert now == then
    assert "router ospf 1" in now or "router rip" in now


@pytest.mark.parametrize("label", ["configs/fleet/r1.cfg", "configs/fleet/r3.cfg",
                                   "configs/fleet/s1.cfg", "configs/fleet/s3.cfg",
                                   "committed/r2.cfg"])
def test_a_library_from_before_the_packs_renders_their_fields_as_lines(tmp_path, label):
    """A network whose `_common.j2` predates the packs reads none of their fields; the render
    hands them over as the lines the shipped packs render (`features.for_library`), so a
    capture's structured parse still reproduces the capture through it."""
    _l, platform, text = next(c for c in CAPTURES if c[0] == label)
    hv = get_parser(platform).parse(text)
    assert features.structured(hv)
    root = _old_library(tmp_path)
    assert features.library_reads_packs(root, platform, "base.j2") is False
    assert features.library_reads_packs(roundtrip.TEMPLATE_ROOT, platform, "base.j2") is True
    rendered = roundtrip.render(hv, platform, template_root=root)
    report = roundtrip.compare(text, rendered, hv)
    assert report["ok"], report["details"]


def test_the_authored_intent_through_an_old_library_gives_the_same_lines(tmp_path):
    """Structured intent a person wrote, through a library from before the packs: every
    routing block holds the lines the shipped templates render (order inside a block is the
    device's to choose; the round trip compares a routing block as a set)."""
    doc = _authored("cisco_iosxe")
    new = roundtrip.render(doc, "cisco_iosxe", secret_lookup=_secret)
    old = roundtrip.render(doc, "cisco_iosxe", secret_lookup=_secret,
                           template_root=_old_library(tmp_path))
    assert {h: sorted(l) for h, l in _blocks(old).items()} == \
        {h: sorted(l) for h, l in _blocks(new).items()}
    heads = tuple(EXPECTED_INTERFACES)
    assert {h: sorted(l) for h, l in _blocks(old, heads).items()} == \
        {h: sorted(l) for h, l in _blocks(new, heads).items()}


class TestTheReadersReadEitherShape:
    """The adjacency readers judge from intent's lines; a pack's fields read as the lines they
    render (`features.raw_view`), so intent written either way implies the same adjacencies."""

    def test_neighbours_and_rip_read_the_same_from_both_shapes(self):
        from modules import neighbours
        from modules.readers import rip as rip_reader
        checked = 0
        for label in ("configs/fleet/r1.cfg", "configs/fleet/r3.cfg", "configs/fleet/s1.cfg",
                      "configs/fleet/s3.cfg"):
            hv = _parse(label)
            lines = features.raw_view(hv)
            assert not features.structured(lines) and features.structured(hv)
            assert neighbours.ospf_links(hv) == neighbours.ospf_links(lines)
            assert neighbours.ospfv3_links(hv) == neighbours.ospfv3_links(lines)
            assert neighbours.router_id(hv) == neighbours.router_id(lines)
            assert rip_reader.runs(hv) == rip_reader.runs(lines)
            assert rip_reader.rip_interfaces(hv) == rip_reader.rip_interfaces(lines)
            checked += 1
        assert checked == 4

    def test_the_lines_view_holds_the_capture_s_own_lines(self):
        """The view's lines are the capture's (r1: its OSPF settings and network statements,
        its interface's `ipv6 rip` lines), read from the capture itself, not from the code."""
        _l, _p, text = next(c for c in CAPTURES if c[0] == "configs/fleet/r1.cfg")
        lines = features.raw_view(_parse("configs/fleet/r1.cfg"))
        (ospf,) = lines["routing"]["ospf"]
        captured = _blocks(text)["router ospf 1"]
        assert ospf["networks"] == [l for l in captured if l.startswith("network ")]
        assert sorted(ospf["settings"]) == sorted(l for l in captured
                                                  if not l.startswith("network "))
        gi3 = _blocks(text, ("interface GigabitEthernet3",))["interface GigabitEthernet3"]
        assert ["ipv6 rip " + x for x in _iface(lines, "GigabitEthernet3")["ripng"]] == [
            l for l in gi3 if l.startswith("ipv6 rip ")]

    def test_a_platform_the_tool_does_not_know_is_never_rendered_as_another(self):
        """C452: the view is drawn through the device's own dialect or not at all. Unknown, a
        reader gets the intent as it is (never Cisco's lines guessed), and the strict caller is
        refused naming the device and the platforms the tool knows."""
        from modules.nsot.platform import UnknownPlatform
        hv = dict(_parse("configs/fleet/r1.cfg"), platform="junos")
        assert features.structured(hv)
        assert features.raw_view(hv) is hv
        with pytest.raises(UnknownPlatform, match="cisco_ios, cisco_iosxe"):
            features.raw_view(hv, strict=True)
        known = features.raw_view(dict(hv, platform="cisco_iosxe"))
        assert not features.structured(known)
