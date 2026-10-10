"""P.11's reader (`modules/readers/topology_graph.py`), on real captures: LLDP's neighbour
tables and `up` (tests/fixtures/topology/, 2026-09-30, the same 18 rows read again on
2026-10-10), the interfaces' `ifOperStatus` and `ifHighSpeed` (2026-10-10, `ifAlias` dropped),
the three routing tables (tests/fixtures/prometheus/neighbours.json) and the fleet's real configs
parsed as committed intent.

- **Accuracy (the brief's Q5):** the physical layer's device pairs are exactly the hand-kept
  cabling (tests/fixtures/topology/cabling.yml, read from the lab's containerlab definitions),
  an expectation independent of LLDP.
- A link is the union of both ends: reported by both, or one-sided and classified (r5 is cabled
  and not managed: its links are "far end not polled"; a polled, managed end that stops
  reporting is "one silent").
- Each end's ports are LLDP's own, and its state is that port's `ifOperStatus`: down at one end
  is down, naming the end; the speed is the slower end's `ifHighSpeed`.
- A managed device with no LLDP neighbour is an island with why; a device that is not managed is
  a node marked so.
- The analyses on a MultiGraph: a parallel link is never a bridge; an articulation point names
  what it would cut off; down links carry nothing.
- The routing layers are the Neighbours tab's comparison, adjacency by adjacency.
- The read: not configured says so; the change test ignores the read's own time.
"""

import json
import os

import pytest
import yaml

from modules.readers import topology_graph as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOPO = os.path.join(ROOT, "tests", "fixtures", "topology")
NEIGHBOURS = os.path.join(ROOT, "tests", "fixtures", "prometheus", "neighbours.json")
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
MANAGED = ["r1", "r2", "r3", "r4", "r6", "s1", "s2", "s3", "s4"]


def _rows(name):
    with open(os.path.join(TOPO, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)["data"]["result"]


def _capture():
    """``(results, up)`` as the reader's fetch builds them, from the captures."""
    results, up = {}, {}
    for metric in ("lldpRemEntry", "lldpRemPortId", "ifOperStatus", "ifHighSpeed"):
        for row in _rows(metric):
            results.setdefault(row["metric"]["device"], {}).setdefault(metric, []).append(row)
    with open(NEIGHBOURS, encoding="utf-8") as fh:
        n = json.load(fh)
    for metric in ("ospfNbrState", "ospfv3NbrState", "cbgpPeer2State"):
        for row in n[metric]["data"]["result"]:
            results.setdefault(row["metric"]["device"], {}).setdefault(metric, []).append(row)
    for row in _rows("up") + n['up{job=~"ospf|ospfv3|bgp"}']["data"]["result"]:
        m = row["metric"]
        up.setdefault(m.get("device", ""), {})[m["job"]] = int(row["value"][1])
    # r6 joined the polled fleet after the 2026-09-30 capture (read 2026-10-10: its lldp target
    # up, no LLDP neighbour): planted as measured.
    up.setdefault("r6", {})["lldp"] = 1
    return results, up


def _intents():
    from modules.nsot.parsers import get_parser
    out = {}
    for f in sorted(os.listdir(FLEET)):
        host = f[:-4]
        with open(os.path.join(FLEET, f), encoding="utf-8") as fh:
            out[host] = get_parser("cisco_iosxe" if host.startswith("r") else "cisco_ios") \
                .parse(fh.read())
    return out


def _graph(results=None, up=None, hosts=MANAGED):
    res, u = _capture()
    return T.network_graph(hosts, {}, _intents(), results or res, up or u)


def _r5_retired(**kw):
    """The graph as the host reads it: r5 has no committed intent there (it is retired)."""
    res, up = _capture()
    intents = {h: hv for h, hv in _intents().items() if h != "r5"}
    return T.network_graph(MANAGED, {}, intents, res, up, **kw)


def _link(g, a, b):
    return [l for l in g["layers"]["physical"] if {l["a"], l["b"]} == {a, b}]


class TestThePhysicalLayer:
    def test_its_pairs_are_the_real_cabling(self):
        with open(os.path.join(TOPO, "cabling.yml"), encoding="utf-8") as fh:
            cabling = {tuple(sorted(p)) for p in yaml.safe_load(fh)["links"]}
        assert len(cabling) >= 10
        got = {(l["a"], l["b"]) for l in _graph()["layers"]["physical"]}
        assert got == cabling

    def test_both_ends_one_link_and_its_ports(self):
        g = _graph()
        (l,) = _link(g, "r1", "s3")
        assert l["kind"] == "both" and l["reported_by"] == ["r1", "s3"]
        ports = {l["a"]: l["port_a"], l["b"]: l["port_b"]}
        assert ports == {"r1": "Gi2", "s3": "Gi1/0"}
        assert l["state"] == "up" and l["speed"] == 1000

    def test_the_lab_s_one_sided_links_are_the_measured_four(self):
        """The research (1.4) measured 4 of 11 links one-sided, two between polled devices:
        s1 and s2 report only each other, and r5 is not managed."""
        kinds = {}
        for l in _graph()["layers"]["physical"]:
            kinds.setdefault(l["kind"], set()).add((l["a"], l["b"]))
        assert kinds["one_silent"] == {("r1", "s1"), ("r2", "s2")}
        assert kinds["far_not_polled"] == {("r3", "r5"), ("r4", "r5")}
        assert len(kinds["both"]) == 7

    def test_a_far_end_not_managed_is_classified_not_flagged(self):
        g = _graph()
        (l,) = _link(g, "r3", "r5")
        assert l["kind"] == "far_not_polled" and l["reported_by"] == ["r3"]
        assert g["nodes"]["r5"]["managed"] is False

    def test_a_polled_end_that_stops_reporting_is_one_silent(self):
        res, up = _capture()
        (before,) = _link(_graph(res, up), "s3", "s4")
        assert before["kind"] == "both"
        res["s4"]["lldpRemEntry"] = [r for r in res["s4"]["lldpRemEntry"]
                                     if not r["metric"]["lldpRemEntry"].startswith("s3")]
        (l,) = _link(_graph(res, up), "s3", "s4")
        assert l["kind"] == "one_silent" and l["reported_by"] == ["s3"]

    def test_down_at_one_end_is_down_naming_it(self):
        res, up = _capture()
        for row in res["r1"]["ifOperStatus"]:
            if row["metric"]["ifName"] == "Gi2":
                row["value"] = [row["value"][0], "2"]
        (l,) = _link(_graph(res, up), "r1", "s3")
        assert l["state"] == "down" and l["down_at"] == ["r1"]
        assert l["ends"] == {"r1": "down", "s3": "up"}

    def test_a_managed_device_with_no_neighbour_is_an_island_with_why(self):
        a = _graph()["analysis"]["physical"]
        assert a["islands"] == [["r6"]]
        assert a["island_why"]["r6"] == "no LLDP neighbour among the managed devices"
        assert "r5" in a["main"]
        assert a["island_state"]["r6"] == {"expected": None, "since": "", "became": False,
                                           "warn": True}


class TestIslandsExpectedAndBecoming:
    """The operator, 2026-10-10: r6 is an island by design (its own containerlab lab); mark an
    expected island with its reason, and keep the warning for a device that BECOMES one."""

    DECL = {"reason": "its own containerlab lab, cabled apart", "by": "p@example.invalid",
            "at": "2026-10-10T19:00:00Z"}

    def test_a_declared_island_is_expected_with_its_reason_and_warns_nothing(self):
        a = _r5_retired(expected={"r6": self.DECL}, now="T1")["analysis"]["physical"]
        assert a["island_state"]["r6"]["expected"] == self.DECL
        assert a["island_state"]["r6"]["warn"] is False

    def test_a_device_that_becomes_an_island_is_new_and_warned(self):
        a = _r5_retired(previous={"physical": {}}, now="T1")["analysis"]["physical"]
        assert a["island_state"]["r6"] == {"expected": None, "since": "T1", "became": True,
                                           "warn": True}

    def test_one_that_was_already_an_island_carries_its_since(self):
        a = _r5_retired(previous={"physical": {"r6": {"since": "T0"}}},
                        now="T1")["analysis"]["physical"]
        assert a["island_state"]["r6"]["since"] == "T0"
        assert a["island_state"]["r6"]["became"] is False

    def test_the_declaration_is_the_physical_layer_s_only(self):
        g = _r5_retired(expected={"s1": self.DECL})
        assert all(st["expected"] is None for layer, a in g["analysis"].items()
                   if layer != "physical" for st in a["island_state"].values())

    def test_device_names_are_shortened_never_trusted_whole(self):
        assert T.short("s3.example.invalid") == "s3" and T.short("") == ""


class TestTheAnalyses:
    def test_a_parallel_link_is_never_a_bridge(self):
        links = [{"a": "a", "b": "b", "state": "up"}, {"a": "a", "b": "b", "state": "up"},
                 {"a": "b", "b": "c", "state": "up"}]
        got = T.analyse(["a", "b", "c"], links)
        assert [(x["a"], x["b"]) for x in got["bridges"]] == [("b", "c")]
        assert got["bridges"][0]["cuts_off"] == ["c"]

    def test_an_articulation_point_names_what_it_cuts_off(self):
        links = [{"a": "core", "b": x, "state": "up"} for x in ("e1", "e2")] + \
                [{"a": "e1", "b": "e2", "state": "up"}, {"a": "e2", "b": "leaf", "state": "up"}]
        got = T.analyse(["core", "e1", "e2", "leaf"], links)
        assert got["spof"] == [{"device": "e2", "cuts_off": ["leaf"]}]
        assert got["critical"][0]["device"] == "e2"

    def test_a_down_link_carries_nothing(self):
        links = [{"a": "a", "b": "b", "state": "down"}]
        got = T.analyse(["a", "b"], links)
        assert got["components"] == 2 and got["islands"] == [["b"]]

    def test_the_lab_has_no_physical_single_point_of_failure(self):
        a = _graph()["analysis"]["physical"]
        assert a["spof"] == [] and a["bridges"] == []


class TestTheRoutingLayers:
    def test_a_peer_outside_management_is_a_node_named_by_its_address(self):
        """C648: the lab's eBGP sessions are to r5, which is not managed; the first host run
        dropped them and drew an empty BGP layer. r5 has no committed intent on the host (it is
        retired), so its address names no device, as there."""
        g = _r5_retired()
        bgp = g["layers"]["bgp"]
        assert bgp
        # ... named through the LLDP neighbour on the interface whose subnet holds the address
        # (the operator, 2026-10-10: r5 drawn as an outside peer), its address kept.
        assert {l["external"] for l in bgp} == {"r5"}
        assert all(l["address"] and "r5" in (l["a"], l["b"]) for l in bgp)
        assert {l["a"] if l["b"] == "r5" else l["b"] for l in bgp} == {"r3", "r4"}
        # ... and never a node of the physical layer (the fix's first host run put them there).
        phys = g["analysis"]["physical"]
        assert phys["islands"] == [["r6"]]
        assert not any(":" in n or n[0].isdigit() for n in g["nodes"])

    def test_an_outside_peer_is_one_node_never_a_fleet_node_or_an_island(self):
        g = _r5_retired()
        r5 = g["nodes"]["r5"]
        assert r5["managed"] is False and r5["outside"] is True
        assert r5["seen_by"] == ["r3", "r4"]
        for layer, a in g["analysis"].items():
            assert not any("r5" in i for i in a["islands"]), layer

    def test_a_layer_s_islands_are_among_the_devices_taking_part(self):
        """C648: a switch that runs no OSPF is not an island of the OSPF layer."""
        g = _graph()
        ospf_devices = {e for l in g["layers"]["ospf"] for e in (l["a"], l["b"])}
        assert ospf_devices and not {"s1", "s2"} & ospf_devices
        islands = {d for i in g["analysis"]["ospf"]["islands"] for d in i}
        assert islands <= ospf_devices

    def test_each_adjacency_is_the_neighbours_comparison(self):
        g = _graph()
        ospf = g["layers"]["ospf"]
        assert len(ospf) >= 8
        assert all(l["a"] < l["b"] for l in ospf)
        assert {l["state"] for l in ospf} <= {"up", "down", "not_seen"}
        assert any(l["state"] == "up" and l["intended"] for l in ospf)


def _here(intents):
    """Mercury's host on s3 Vlan99's subnet, as on the lab's, derived from the captured config."""
    import ipaddress
    svi = next(i for i in intents["s3"]["interfaces"] if i["name"] == "Vlan99")
    net = ipaddress.ip_interface("/".join(svi["ipv4"].split())).network
    return [("eth1", f"{net.network_address + 250}/{net.prefixlen}")]


def _labelled(**kw):
    """The graph as the host reads it, with Mercury's host where the lab's attaches."""
    res, up = _capture()
    intents = {h: hv for h, hv in _intents().items() if h != "r5"}
    roles = {h: "router" if h.startswith("r") else "switch" for h in MANAGED}
    return T.network_graph(MANAGED, roles, intents, res, up, now="2026-10-10T19:00:00Z",
                           at_here=_here(intents), **kw)


class TestWhatEachLinkCarries:
    """The operator, 2026-10-10: each link labelled with its ports and each neighbourship's
    state and key facts (OSPF and OSPFv3 area, BGP peer AS)."""

    def _adj(self, g, a, b):
        link = _link(g, a, b)[0]
        return [dict(g["layers"][r["layer"]][r["i"]], layer=r["layer"], at=r["at"])
                for r in link["adj"]]

    def test_a_point_to_point_link_carries_its_adjacency_from_both_ends(self):
        adj = self._adj(_labelled(), "r3", "r4")
        assert sorted((x["layer"], x["area"], x["words"], tuple(x["at"])) for x in adj) == [
            ("ospf", "0", "full", ("r3", "r4")), ("ospfv3", "0", "full", ("r3", "r4"))]

    def test_a_shared_segment_s_port_carries_every_adjacency_leaving_it(self):
        """r1 Gi2 is on VLAN 100 with r2, r3, r4, s3 and s4: its link to s3 carries all five
        OSPF and three OSPFv3 neighbourships, and s3's own (through its Vlan100 interface, on a
        port carrying VLAN 100 to r1)."""
        adj = self._adj(_labelled(), "r1", "s3")
        ospf = {(x["a"], x["b"]) for x in adj if x["layer"] == "ospf"}
        assert ospf == {("r1", p) for p in ("r2", "r3", "r4", "s3", "s4")}
        assert {x["words"] for x in adj if x["layer"] == "ospf"} == {"full", "2-way"}
        assert len([x for x in adj if x["layer"] == "ospfv3"]) == 3
        assert next(x for x in adj if x["b"] == "s3" and x["layer"] == "ospf")["at"] == \
            ["r1", "s3"]

    def test_an_svi_adjacency_rides_the_trunk_to_its_peer(self):
        adj = self._adj(_labelled(), "s3", "s4")
        assert [(x["layer"], x["words"], x["at"]) for x in adj] == [("ospf", "2-way",
                                                                     ["s3", "s4"])]

    def test_ebgp_to_the_outside_peer_names_both_ases_on_its_link(self):
        adj = self._adj(_labelled(), "r3", "r5")
        assert {x["layer"] for x in adj} == {"bgp"} and len(adj) == 2      # IPv4 and IPv6
        for x in adj:
            assert x["asn"]["r5"] != x["asn"]["r3"] and x["state"] == "up"

    def test_every_adjacency_of_the_lab_is_on_a_link(self):
        g = _labelled()
        assert all(a["on_link"] for layer in ("ospf", "ospfv3", "bgp")
                   for a in g["layers"][layer])

    def test_ripng_configured_is_said_not_read(self):
        assert _link(_labelled(), "r1", "s1")[0]["unread"] == {"r1": ["RIPng"], "s1": ["RIPng"]}
        assert _link(_labelled(), "r3", "r4")[0]["unread"] == {}


class TestWhereMercuryAttaches:
    def test_measured_by_address_to_the_one_port_carrying_its_vlan(self):
        g = _labelled()
        mgr = [l for l in g["layers"]["physical"] if l.get("manager")]
        assert [(l["a"], l["port_a"], l["b"], l["port_b"], l["via"], l["vlan"]) for l in mgr] \
            == [(T.MANAGER, "eth1", "s3", "Gi1/1", "Vl99", "99")]
        assert g["nodes"][T.MANAGER]["manager"] and not g["nodes"][T.MANAGER]["managed"]

    def test_its_only_way_in_is_said_and_mercury_is_no_device_s_path(self):
        """The board's s3 SPOF, now measured: Mercury reaches every device but the island r6
        through s3 alone. The host forwards nothing, so it is never a weak point itself."""
        a = _labelled()["analysis"]["physical"]
        assert a["attached"] == ["s3"]
        assert a["only_way_in"] == [{"device": "s3", "port": "Gi1/1", "vlan": "99",
                                     "reaches": ["r1", "r2", "r3", "r4", "s1", "s2", "s4"]}]
        assert a["spof"] == [] and a["bridges"] == []

    def test_an_address_two_devices_hold_attaches_nothing(self):
        """Measured on the host, 2026-10-10: every containerlab router holds the same
        management-VRF address, in a subnet overlapping the host's LAN; each had been drawn
        attached to Mercury."""
        import ipaddress
        res, up = _capture()
        intents = {h: hv for h, hv in _intents().items() if h != "r5"}
        gi1 = next(i for i in intents["r1"]["interfaces"] if i["name"] == "GigabitEthernet1")
        assert any(i.get("ipv4") == gi1["ipv4"] for i in intents["r4"]["interfaces"])
        net = ipaddress.ip_interface("/".join(gi1["ipv4"].split())).network
        g = T.network_graph(MANAGED, {}, intents, res, up,
                            at_here=[("eth0", f"{net.network_address + 250}/{net.prefixlen}")])
        assert T.MANAGER not in g["nodes"]

    def test_a_device_mercury_reaches_directly_stays_an_island_and_says_so(self):
        """r6 on the host: its own lab, its Gi2 on Mercury's management segment, no LLDP link
        to the fleet. Attached directly, it is still the devices' island, never joined to s3
        through Mercury, and Mercury's way into the rest is still s3 alone."""
        import ipaddress
        res, up = _capture()
        intents = {h: hv for h, hv in _intents().items() if h != "r5"}
        here = _here(intents)
        net = ipaddress.ip_interface(here[0][1]).network
        intents["r6"] = {"interfaces": [{"name": "GigabitEthernet2",
                                         "ipv4": f"{net.network_address + 6} {net.netmask}"}]}
        roles = {h: "router" if h.startswith("r") else "switch" for h in MANAGED}
        g = T.network_graph(MANAGED, roles, intents, res, up, at_here=here)
        a = g["analysis"]["physical"]
        assert a["attached"] == ["r6", "s3"] and a["islands"] == [["r6"]]
        assert "reaches it directly" in a["island_why"]["r6"]
        assert [o["device"] for o in a["only_way_in"]] == ["s3"] and a["spof"] == []

    def test_c651_a_cut_names_only_its_own_component(self):
        links = [{"a": "a", "b": "b", "state": "up"}, {"a": "b", "b": "c", "state": "up"}]
        got = T.analyse(["a", "b", "c", "island"], links)
        assert got["spof"] == [{"device": "b", "cuts_off": ["a"]}]

    def test_an_address_in_no_device_s_subnet_draws_nothing(self):
        res, up = _capture()
        g = T.network_graph(MANAGED, {}, _intents(), res, up, at_here=[("eth0", "192.0.2.9/24")])
        assert T.MANAGER not in g["nodes"]

    def test_here_reads_this_host_s_own_addresses_without_loopback(self):
        import ipaddress
        for name, iface in T.here():
            ip = ipaddress.ip_interface(iface).ip
            assert name and not ip.is_loopback and not ip.is_link_local


class TestSinceAndLayout:
    def test_a_state_held_carries_its_since_and_a_change_is_seen(self):
        g1 = _labelled()
        link = _link(g1, "r3", "r4")[0]
        assert link["since"] == "2026-10-10T19:00:00Z" and link["since_seen"] is False
        before = {layer: {T._link_key(layer, l): {"state": l["state"], "since": l["since"],
                                                  "since_seen": l["since_seen"]}
                          for l in links} for layer, links in g1["layers"].items()}
        res, up = _capture()
        for row in res["r3"]["ifOperStatus"]:
            if row["metric"]["ifName"] == "Gi4":
                row["value"] = [row["value"][0], "2"]
        intents = {h: hv for h, hv in _intents().items() if h != "r5"}
        g2 = T.network_graph(MANAGED, {}, intents, res, up, now="2026-10-10T19:05:00Z",
                             at_here=_here(intents), before_links=before)
        down = _link(g2, "r3", "r4")[0]
        assert down["state"] == "down" and down["since"] == "2026-10-10T19:05:00Z"
        assert down["since_seen"] is True
        held = _link(g2, "r1", "s3")[0]
        assert held["since"] == "2026-10-10T19:00:00Z"

    def test_the_map_is_laid_out_once_with_the_graph(self):
        g = _labelled()
        pos = g["layout"]["positions"]
        assert set(pos) == set(g["nodes"])
        assert pos == _labelled()["layout"]["positions"]        # the same graph, the same map
        # Bands by class: routers above switches, Mercury's host at the bottom.
        assert pos["r1"][1] < pos["s3"][1] < pos[T.MANAGER][1]


class TestTheRead:
    def test_not_configured_says_so(self):
        got = T.read(source=lambda: (False, {}, {}), population=lambda: [])
        assert got == {"configured": False, "networks": {}, "errors": []}

    def test_a_network_per_list(self):
        from types import SimpleNamespace
        res, up = _capture()
        ref = SimpleNamespace(repo_dir=os.path.join(ROOT, "no-such-repo"))
        got = T.read(source=lambda: (True, res, up),
                     population=lambda: [("Lab", ref, MANAGED)], clock=lambda: 0,
                     expected=lambda name: {"state": "absent", "islands": {}, "error": ""},
                     at_here=[])
        assert got["configured"] and set(got["networks"]) == {"Lab"}
        assert got["read_at"] == "1970-01-01T00:00:00Z"
        assert got["networks"]["Lab"]["nodes"]["r1"]["role"] == "router"

    def test_the_change_test_ignores_the_read_time(self):
        a = {"configured": True, "networks": {"x": 1}, "read_at": "t1"}
        assert not T.changed(a, dict(a, read_at="t2"))
        assert T.changed(a, dict(a, networks={"x": 2}))


@pytest.fixture(autouse=True)
def _no_mutation():
    """The captures are read fresh in each test; nothing above may change them on disk."""
    before = {f: os.path.getmtime(os.path.join(TOPO, f)) for f in os.listdir(TOPO)}
    yield
    assert before == {f: os.path.getmtime(os.path.join(TOPO, f)) for f in os.listdir(TOPO)}
