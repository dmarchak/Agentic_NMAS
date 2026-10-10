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
        res, up = _capture()
        intents = {h: hv for h, hv in _intents().items() if h != "r5"}
        g = T.network_graph(MANAGED, {}, intents, res, up)
        bgp = g["layers"]["bgp"]
        assert bgp and all(l["external"] for l in bgp)
        for l in bgp:
            assert g["nodes"][l["external"]] == dict(g["nodes"][l["external"]], managed=False,
                                                     external=True)

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


class TestTheRead:
    def test_not_configured_says_so(self):
        got = T.read(source=lambda: (False, {}, {}), population=lambda: [])
        assert got == {"configured": False, "networks": {}, "errors": []}

    def test_a_network_per_list(self):
        from types import SimpleNamespace
        res, up = _capture()
        ref = SimpleNamespace(repo_dir=os.path.join(ROOT, "no-such-repo"))
        got = T.read(source=lambda: (True, res, up),
                     population=lambda: [("Lab", ref, MANAGED)], clock=lambda: 0)
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
