"""Lab 9 A4: the DHCP server pack, a Cisco router's own DHCPv4 pools in its intent
(`dhcp_server`; `modules/nsot/features/dhcp.py`; docs/FEATURE_PACKS.md, "DHCP server";
docs/LAB_READINESS.md, "A4: the router's pool").

No capture in the lab holds an `ip dhcp` line (the fleet's DHCP is Kea's), so the configs here
are the lab's real captures (tests/fixtures/configs/fleet/r1.cfg, a C8000v on IOS-XE 17.6, and
s1.cfg, a vIOS-L2 on IOS 15.2) with ONE edit: the lines below inserted before their
`ip forward-protocol nd`. Those lines are the shape of Cisco's own example ("Example:
Configuring DHCP Address Pools", in "Configuring the Cisco IOS DHCP Server", IP Addressing:
DHCP Configuration Guide, Cisco IOS Release 15M&T,
https://www.cisco.com/c/en/us/td/docs/ios-xml/ios/ipaddr_dhcp/configuration/15-mt/dhcp-15-mt-book/config-dhcp-server.html,
read 2026-11-05): two excluded ranges, a network pool with a domain name and name servers, two
subnet pools each with routers and a 30-day lease; its addresses moved to 192.0.2.0/24. Beside
them, the shapes the pack leaves as lines: an option (ZTP's TFTP server, option 150), a network
entered as a prefix length, a VRF's excluded range, a secondary subnet's submode, and IOS's
DHCPv6 pool (the IPv6 case). The network is written in mask form, the form the guide's own
example shows; how a lab device prints it is unmeasured (docs/FEATURE_PACKS.md).

What is held:

1. every capture without a DHCP line parses as it did (no `dhcp_server` key), and the edited
   captures round-trip, their parse a fixed point that passes every check;
2. the parse holds in the fields exactly what the lines say, and every shape it does not model
   stays verbatim (in a pool's `raw`, or whole in `unmodeled`), the IPv6 pool among them;
3. authored intent renders the exact lines for both Cisco dialects, and the preview's program
   against the real capture is exactly those lines under their pools, merge-only, its undo
   the two negations, its verify FULL;
4. each refusal names the field, its value and the rule, beside a control that passes, the
   IPv6 case beside the IPv4 one, by the editor's check and by the render;
5. a library from before the pack (the shipped templates at its parent commit) is handed the
   pack's fields as lines, so the same lines render through it.
"""

import copy
import os
import subprocess

import pytest

from modules.nsot import deploy, features, hostvars, roundtrip, verify_scope
from modules.nsot.features import dhcp
from modules.nsot.parsers import get_parser
from modules.nsot.parsers.base import split_blocks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
#: The commit before the pack: its shipped templates are "a library from before it".
BEFORE_DHCP = "af98e563"
ANCHOR = "ip forward-protocol nd\n"

#: The guide's example's shape (see the module docstring), in 192.0.2.0/24.
GUIDE = """\
ip dhcp excluded-address 192.0.2.1 192.0.2.10
ip dhcp excluded-address 192.0.2.129 192.0.2.138
ip dhcp pool 0
 network 192.0.2.0 255.255.255.0
 domain-name lab.example
 dns-server 192.0.2.53 192.0.2.54
ip dhcp pool 1
 network 192.0.2.0 255.255.255.128
 default-router 192.0.2.1 192.0.2.2
 lease 30
ip dhcp pool 2
 network 192.0.2.128 255.255.255.128
 default-router 192.0.2.129 192.0.2.130
 lease 30
"""
#: The shapes left as lines.
LEFT = """\
ip dhcp excluded-address vrf CUSTOMER 192.0.2.200 192.0.2.210
ip dhcp pool ZTP
 network 192.0.2.192 255.255.255.224
 default-router 192.0.2.193
 option 150 ip 192.0.2.5
 lease 0 8
ip dhcp pool TYPED
 network 192.0.2.224 /27
ip dhcp pool TWO-SUBNETS
 network 192.0.2.240 255.255.255.248
 network 192.0.2.248 255.255.255.248 secondary
  override default-router 192.0.2.249
ipv6 dhcp pool V6
 address prefix 2001:DB8:0:10::/64
 dns-server 2001:DB8::53
"""

CAPTURES = (("r1.cfg", "cisco_iosxe"), ("s1.cfg", "cisco_ios"))


def _capture(name):
    with open(os.path.join(FLEET, name), encoding="utf-8") as fh:
        return fh.read()


def _edited(name, lines=GUIDE + LEFT):
    text = _capture(name)
    assert text.count(ANCHOR) == 1, f"{name}: the anchor line is not there once"
    return text.replace(ANCHOR, lines + ANCHOR)


def _secret(_name):
    return "x"


def _blocks(text, head):
    return [(b.stripped, [c.strip() for c in b.children])
            for b in split_blocks(text) if b.stripped.startswith(head)]


#: Authored intent: what a person types for a router's two LANs.
AUTHORED = {
    "excluded": [{"low": "192.0.2.1", "high": "192.0.2.10"}, {"low": "192.0.2.129"}],
    "pools": [
        {"name": "LAN10", "network": "192.0.2.0/25", "default_router": ["192.0.2.1"],
         "dns_servers": ["192.0.2.53", "192.0.2.54"], "domain_name": "lab.example",
         "lease": {"days": 0, "hours": 8}},
        {"name": "LAN20", "network": "192.0.2.128/25", "default_router": ["192.0.2.129"],
         "lease": {"infinite": True}, "raw": ["option 150 ip 192.0.2.5"]},
    ],
}
#: Those fields in IOS's words, typed from the guide's syntax (an independent path).
AUTHORED_LINES = [
    "ip dhcp excluded-address 192.0.2.1 192.0.2.10",
    "ip dhcp excluded-address 192.0.2.129",
    "ip dhcp pool LAN10",
    " network 192.0.2.0 255.255.255.128",
    " default-router 192.0.2.1",
    " dns-server 192.0.2.53 192.0.2.54",
    " domain-name lab.example",
    " lease 0 8",
    "ip dhcp pool LAN20",
    " network 192.0.2.128 255.255.255.128",
    " default-router 192.0.2.129",
    " lease infinite",
    " option 150 ip 192.0.2.5",
]


def _dhcp_lines(text):
    lines, inside = [], False
    for line in text.splitlines():
        if line.startswith("ip dhcp "):
            lines.append(line)
            inside = line.startswith("ip dhcp pool ")
        elif inside and line.startswith(" "):
            lines.append(line)
        else:
            inside = False
    return lines


def _authored(name, platform):
    hv = get_parser(platform).parse(_capture(name))
    hv["dhcp_server"] = copy.deepcopy(AUTHORED)
    return hv


def test_the_population():
    """A floor: every capture in the fleet folder is read, none holds a DHCP server line (so
    the edited ones are the only population of the pack), and the planted text holds the six
    pools and three excluded ranges the tests below count on."""
    names = sorted(n for n in os.listdir(FLEET) if n.endswith(".cfg"))
    assert len(names) >= 9, names
    for n in names:
        assert "ip dhcp " not in _capture(n), n
    planted = GUIDE + LEFT
    assert len(_blocks(planted, "ip dhcp pool ")) == 6
    assert len(_blocks(planted, "ip dhcp excluded-address ")) == 3


# ── 1. the round trip ────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(n for n in os.listdir(FLEET) if n.endswith(".cfg")))
def test_a_capture_without_a_dhcp_line_gains_no_key(name):
    platform = "cisco_iosxe" if name.startswith("r") else "cisco_ios"
    hv = get_parser(platform).parse(_capture(name))
    assert "dhcp_server" not in hv


@pytest.mark.parametrize("name, platform", CAPTURES)
def test_the_edited_capture_round_trips_as_a_fixed_point(name, platform):
    text = _edited(name)
    hv = get_parser(platform).parse(text)
    assert features.problems(hv) == []
    rendered = roundtrip.render(hv, platform)
    report = roundtrip.compare(text, rendered, hv)
    assert report["ok"], report["details"]
    again = get_parser(platform).parse(rendered)
    assert hostvars.to_yaml(again) == hostvars.to_yaml(hv)


def test_a_pool_is_compared_as_a_set_and_an_access_list_still_in_order():
    """IOS prints a pool's lines in its own order (each sets one of the pool's parameters), so
    the round trip compares a pool as a set; the order-significant sections stay ordered."""
    assert roundtrip.section_is_unordered("ip dhcp pool LAN10")
    assert not roundtrip.section_is_unordered("ip access-list extended EDGE")


# ── 2. parse → fields ────────────────────────────────────────────────────────

@pytest.mark.parametrize("name, platform", CAPTURES)
def test_the_parse_holds_what_the_guide_s_lines_say(name, platform):
    hv = get_parser(platform).parse(_edited(name))
    server = hv["dhcp_server"]
    assert server["excluded"] == [{"low": "192.0.2.1", "high": "192.0.2.10"},
                                  {"low": "192.0.2.129", "high": "192.0.2.138"}]
    pools = {p["name"]: p for p in server["pools"]}
    assert pools["0"] == {"name": "0", "network": "192.0.2.0/24",
                          "dns_servers": ["192.0.2.53", "192.0.2.54"],
                          "domain_name": "lab.example", "raw": []}
    assert pools["1"] == {"name": "1", "network": "192.0.2.0/25",
                          "default_router": ["192.0.2.1", "192.0.2.2"],
                          "lease": {"days": "30"}, "raw": []}
    assert pools["2"]["network"] == "192.0.2.128/25"


@pytest.mark.parametrize("name, platform", CAPTURES)
def test_every_shape_the_pack_does_not_model_stays_verbatim(name, platform):
    """An option stays in its pool's `raw`; a network typed as a prefix length (a form the
    partial does not write) stays a raw line; a VRF's range, a pool with a secondary subnet's
    submode and IOS's DHCPv6 pool stay in `unmodeled`, whole."""
    hv = get_parser(platform).parse(_edited(name))
    pools = {p["name"]: p for p in hv["dhcp_server"]["pools"]}
    assert pools["ZTP"]["raw"] == ["option 150 ip 192.0.2.5"]
    assert pools["ZTP"]["lease"] == {"days": "0", "hours": "8"}
    assert pools["TYPED"] == {"name": "TYPED", "raw": ["network 192.0.2.224 /27"]}
    assert "TWO-SUBNETS" not in pools
    unmodeled = {u["line"]: [c.strip() for c in u["children"]] for u in hv["unmodeled"]}
    assert unmodeled["ip dhcp excluded-address vrf CUSTOMER 192.0.2.200 192.0.2.210"] == []
    assert unmodeled["ip dhcp pool TWO-SUBNETS"] == [
        "network 192.0.2.240 255.255.255.248",
        "network 192.0.2.248 255.255.255.248 secondary",
        "override default-router 192.0.2.249"]
    assert unmodeled["ipv6 dhcp pool V6"] == ["address prefix 2001:DB8:0:10::/64",
                                              "dns-server 2001:DB8::53"]


def test_a_pool_whose_router_is_off_its_subnet_is_kept_as_lines():
    """Each line passes alone, the pair breaks RFC 2132's rule: the pool's lines stay raw, so
    the parse renders and the device's own lines go back as they were."""
    text = _edited("r1.cfg", "ip dhcp pool ODD\n network 192.0.2.0 255.255.255.128\n"
                             " default-router 192.0.2.200\n")
    hv = get_parser("cisco_iosxe").parse(text)
    assert hv["dhcp_server"]["pools"] == [{"name": "ODD", "raw": [
        "network 192.0.2.0 255.255.255.128", "default-router 192.0.2.200"]}]
    assert features.problems(hv) == []
    assert roundtrip.compare(text, roundtrip.render(hv, "cisco_iosxe"), hv)["ok"]


# ── 3. authored intent → lines → the preview's program ───────────────────────

@pytest.mark.parametrize("name, platform", CAPTURES)
def test_authored_intent_renders_the_exact_lines(name, platform):
    rendered = roundtrip.render(_authored(name, platform), platform, secret_lookup=_secret)
    assert _dhcp_lines(rendered) == AUTHORED_LINES


@pytest.mark.parametrize("name, platform", CAPTURES)
def test_what_it_renders_parses_back_to_the_same_fields(name, platform):
    rendered = roundtrip.render(_authored(name, platform), platform)
    back = get_parser(platform).parse(rendered)["dhcp_server"]
    assert back["excluded"] == AUTHORED["excluded"]
    lan10 = dict(AUTHORED["pools"][0], lease={"days": "0", "hours": "8"}, raw=[])
    assert back["pools"][0] == lan10
    assert back["pools"][1]["lease"] == {"infinite": True}


@pytest.mark.parametrize("name, platform", CAPTURES)
def test_the_preview_s_program_is_the_new_lines_under_their_pools(name, platform):
    """The program the preview shows and the deploy sends (`deploy.merge_commands`, the
    rendered intent against the device's running config): only the DHCP server's lines, each
    pool's under its header; merge-only; its undo removes exactly what it adds; its verify is
    FULL (a pool changes what clients are given, never management alone)."""
    running = _capture(name)
    # No secret lookup: the parse's own hashes render back, so the accounts are not a change.
    rendered = roundtrip.render(_authored(name, platform), platform)
    program = deploy.merge_commands(rendered, running)
    assert program == AUTHORED_LINES[:8] + ["exit"] + AUTHORED_LINES[8:] + ["exit"]
    deploy.assert_merge_only(program, rendered)
    assert deploy.rollback_commands(program, running) == [
        "no ip dhcp excluded-address 192.0.2.1 192.0.2.10",
        "no ip dhcp excluded-address 192.0.2.129",
        "no ip dhcp pool LAN10", "no ip dhcp pool LAN20"]
    assert verify_scope.classify(program)["scope"] == verify_scope.FULL


def test_a_changed_router_and_lease_replace_their_lines_and_roll_back_to_them():
    """A pool already on the device, its router and lease changed in intent: the preview names
    each line it replaces (`deploy.classify_diff`), the program sends only the two new lines
    under the pool, and the undo puts the device's own two lines back."""
    pool = ("ip dhcp pool LAN10\n network 192.0.2.0 255.255.255.128\n"
            " default-router 192.0.2.1\n lease 7\n")
    running = _edited("r1.cfg", pool)
    hv = get_parser("cisco_iosxe").parse(running)
    hv["dhcp_server"]["pools"][0].update(default_router=["192.0.2.2"], lease={"days": "1"})
    rendered = roundtrip.render(hv, "cisco_iosxe")
    program = deploy.merge_commands(rendered, running)
    assert program == ["ip dhcp pool LAN10", " default-router 192.0.2.2", " lease 1", "exit"]
    replaced = {(r["old"], r["new"]) for r in deploy.classify_diff(rendered, running)["replace"]}
    assert replaced == {(" default-router 192.0.2.1", " default-router 192.0.2.2"),
                        (" lease 7", " lease 1")}
    assert deploy.rollback_commands(program, running) == [
        "ip dhcp pool LAN10", " default-router 192.0.2.1", " lease 7", "exit"]


# ── 4. the refusals ──────────────────────────────────────────────────────────

def _pool(**fields):
    return {"dhcp_server": {"pools": [{"name": "LAN10", "network": "192.0.2.0/25",
                                       **fields}]}}


REFUSED = [
    # (the intent, the words its refusal must carry, the control that passes)
    (_pool(default_router=["198.51.100.1"]),
     ["dhcp_server.pools[0].default_router[0]", "'198.51.100.1'", "RFC 2132",
      "192.0.2.0/25"], _pool(default_router=["192.0.2.1"])),
    (_pool(default_router=["2001:db8::1"]),
     ["dhcp_server.pools[0].default_router[0]", "'2001:db8::1'", "DHCPv6",
      "not covered"], _pool(default_router=["192.0.2.1"])),
    (_pool(default_router=["192.0.2.0"]),
     ["default_router[0]", "own network address"], _pool(default_router=["192.0.2.126"])),
    (_pool(default_router=[f"192.0.2.{n}" for n in range(1, 10)]),
     ["dhcp_server.pools[0].default_router", "at most 8", "this is 9"],
     _pool(default_router=[f"192.0.2.{n}" for n in range(1, 9)])),
    (_pool(dns_servers=["2001:db8::53"]),
     ["dhcp_server.pools[0].dns_servers[0]", "DHCPv6"], _pool(dns_servers=["192.0.2.53"])),
    ({"dhcp_server": {"pools": [{"name": "V6", "network": "2001:db8:0:10::/64"}]}},
     ["dhcp_server.pools[0].network", "'2001:db8:0:10::/64'", "DHCPv6"],
     {"dhcp_server": {"pools": [{"name": "V6", "network": "192.0.2.0/24"}]}}),
    ({"dhcp_server": {"pools": [{"name": "A", "network": "192.0.2.0"}]}},
     ["dhcp_server.pools[0].network", "with its length"],
     {"dhcp_server": {"pools": [{"name": "A", "network": "192.0.2.0/24"}]}}),
    ({"dhcp_server": {"pools": [{"name": "A", "network": "192.0.2.5/24"}]}},
     ["dhcp_server.pools[0].network", "host bits", "192.0.2.0/24"],
     {"dhcp_server": {"pools": [{"name": "A", "network": "192.0.2.0/24"}]}}),
    (_pool(lease={"hours": 8}),
     ["dhcp_server.pools[0].lease.hours", "needs days"], _pool(lease={"days": 0, "hours": 8})),
    (_pool(lease={"hours": 25, "days": 0}),
     ["dhcp_server.pools[0].lease.hours", "from 0 to 23"], _pool(lease={"days": 1, "hours": 1})),
    (_pool(lease={"infinite": True, "days": 7}),
     ["dhcp_server.pools[0].lease.infinite", "no length"], _pool(lease={"infinite": True})),
    ({"dhcp_server": {"excluded": [{"low": "192.0.2.9", "high": "192.0.2.3"}]}},
     ["dhcp_server.excluded[0].high", "'192.0.2.3'", "low is '192.0.2.9'"],
     {"dhcp_server": {"excluded": [{"low": "192.0.2.3", "high": "192.0.2.9"}]}}),
    ({"dhcp_server": {"excluded": [{"low": "2001:db8::1"}]}},
     ["dhcp_server.excluded[0].low", "DHCPv6"],
     {"dhcp_server": {"excluded": [{"low": "192.0.2.1"}]}}),
    ({"dhcp_server": {"pools": [{"name": "A"}, {"name": "A"}]}},
     ["dhcp_server.pools[1].name", "named twice"],
     {"dhcp_server": {"pools": [{"name": "A"}, {"name": "B"}]}}),
    ({"dhcp_server": {"pools": [{"name": "two words"}]}},
     ["dhcp_server.pools[0].name", "one word"],
     {"dhcp_server": {"pools": [{"name": "two-words"}]}}),
]


@pytest.mark.parametrize("intent, words, control", REFUSED,
                         ids=[w[0] + " " + w[-1] for _i, w, _c in REFUSED])
def test_a_refused_field_is_named_with_its_value_and_its_rule(intent, words, control):
    assert features.problems(control) == []
    found = features.problems(intent)
    assert len(found) == 1, found
    message = found[0][2]
    for word in words:
        assert word in message, (word, message)


@pytest.mark.parametrize("name, platform", CAPTURES)
def test_the_render_refuses_what_the_editor_refuses(name, platform):
    hv = _authored(name, platform)
    roundtrip.render(hv, platform, secret_lookup=_secret)          # the control
    hv["dhcp_server"]["pools"][0]["default_router"] = ["198.51.100.1"]
    with pytest.raises(features.FeatureIntentInvalid, match="RFC 2132"):
        roundtrip.render(hv, platform, secret_lookup=_secret)


def test_a_misspelt_pool_key_is_unknown_and_the_right_one_is_not():
    """The schema's sections know the pack's keys (`hostvars.INTENT_SECTIONS`), so a typo in
    a pool is named where it was written."""
    good = {"dhcp_server": {"pools": [{"name": "A", "default_router": ["192.0.2.1"],
                                       "lease": {"days": 1}}]}}
    assert hostvars.unknown_keys(good) == []
    bad = {"dhcp_server": {"pools": [{"name": "A", "default_routers": ["192.0.2.1"],
                                      "lease": {"day": 1}}]}}
    unknown = {(path, key) for path, key, _where in hostvars.unknown_keys(bad)}
    assert unknown == {(("dhcp_server", "pools", 0), "default_routers"),
                       (("dhcp_server", "pools", 0, "lease"), "day")}


# ── 5. a library from before the pack ────────────────────────────────────────

def _old_library(tmp_path):
    """The shipped templates at BEFORE_DHCP, in a folder of their own."""
    root = tmp_path / "templates"
    for rel in ("_common.j2", "cisco_ios/base.j2", "cisco_iosxe/base.j2"):
        old = subprocess.run(["git", "-C", ROOT, "show",
                              f"{BEFORE_DHCP}:modules/nsot/templates/{rel}"],
                             capture_output=True, text=True, check=False)
        if old.returncode != 0:
            pytest.skip(f"no history for the shipped templates here: {old.stderr.strip()}")
        assert "dhcp_server" not in old.stdout, "not a library from before the pack"
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(old.stdout, encoding="utf-8")
    return str(root)


@pytest.mark.parametrize("name, platform", CAPTURES)
def test_a_library_from_before_the_pack_renders_its_fields_as_lines(tmp_path, name, platform):
    """The parent commit's library renders the routing packs and not this one: it is judged on
    the pack's own markers, handed the pool as lines (`dhcp.lines_view`), and the same lines
    reach the device, the edited capture still round-tripping through it."""
    root = _old_library(tmp_path)
    assert features.library_reads_packs(root, platform, "base.j2") is True
    assert features.library_reads_packs(root, platform, "base.j2", dhcp.MARKERS) is False
    assert features.library_reads_packs(roundtrip.TEMPLATE_ROOT, platform, "base.j2",
                                        dhcp.MARKERS) is True
    hv = _authored(name, platform)
    old = roundtrip.render(hv, platform, secret_lookup=_secret, template_root=root)
    assert _dhcp_lines(old) == AUTHORED_LINES
    text = _edited(name)
    parsed = get_parser(platform).parse(text)
    report = roundtrip.compare(text, roundtrip.render(parsed, platform, template_root=root),
                               parsed)
    assert report["ok"], report["details"]


@pytest.mark.parametrize("platform", ["cisco_ios", "cisco_iosxe"])
def test_a_line_the_template_would_write_differently_stays_verbatim(platform):
    """A pool line the parser understands but the template would not write back the same
    (here, `domain-name` with three spaces) is kept verbatim in `raw`, never modeled: a
    modeled field renders as the template writes it, which would change the device's line."""
    got = dhcp.claim_pool("LAB", [" network 192.0.2.0 255.255.255.0",
                                  " domain-name   example.org"], platform)
    assert got["raw"] == ["domain-name   example.org"], got
    assert not got.get("domain_name"), got
