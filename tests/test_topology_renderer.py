"""The topology service's renderer (C256, 2026-09-30): versioned in the
repository, names from the scrape targets' `device` label, and every device
with no LLDP link to the rest of the network drawn as an ISLAND with its reason.

The inputs are the host's REAL Prometheus answers (tests/fixtures/topology/,
read-only, 2026-09-30): eight polled devices, eighteen LLDP rows, and r5 seen
only as a neighbour. Each case that adds r6 is a minimal edit of those: r6's
`up` series in its platform's job, in the same shape as r1's.
"""
import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "topology" / "rcn-topology.py"
FIX = ROOT / "tests" / "fixtures" / "topology"


@pytest.fixture(scope="module")
def topo():
    spec = importlib.util.spec_from_file_location("rcn_topology", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _real():
    return {name: json.loads((FIX / f"{name}.json").read_text())["data"]["result"]
            for name in ("up", "sysName", "lldpRemEntry", "lldpRemPortId")}


def _query(answers):
    def q(expr):
        if expr.startswith("up{"):
            return answers["up"]
        return answers[expr]
    return q


def _with_r6(answers, *, lldp_scraped=True, up="1"):
    """r6 polled in r1's job, in r1's exact series shape."""
    a = copy.deepcopy(answers)
    for s in list(a["up"]):
        m = s["metric"]
        if m["device"] != "r1":
            continue
        if m["job"] == "lldp" and not lldp_scraped:
            continue
        r6 = copy.deepcopy(s)
        r6["metric"].update(device="r6", instance="10.255.0.32")
        r6["value"] = [r6["value"][0], up if m["job"] != "lldp" else "1"]
        a["up"].append(r6)
    return a


def _render(topo, nodes, edges, meta, monkeypatch):
    # networkx is the host's; the main component's layout is replaced by a ring.
    monkeypatch.setattr(topo, "_layout_main", lambda names, edges: {
        n: (i, i % 3) for i, n in enumerate(names)})
    return topo.render(nodes, edges, meta)


class TestTheRealFleet:
    def test_the_fleet_is_one_network_with_no_island(self, topo):
        nodes, edges, meta = topo.collect(_query(_real()))
        assert {n for n, d in nodes.items() if d["polled"]} == {
            "r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4"}
        assert len(edges) >= 10
        assert meta["islands"] == 0
        assert not any(d["island"] for d in nodes.values())

    def test_a_retired_neighbour_is_drawn_unpolled(self, topo):
        nodes, _e, _m = topo.collect(_query(_real()))
        assert nodes["r5"]["polled"] is False and nodes["r5"]["state"] == "unknown"

    def test_names_come_from_the_targets_device_label(self, topo):
        assert "STATIC_NAMES" not in SCRIPT.read_text()
        a = _real()
        a["sysName"] = []          # no sysName: the label alone names them
        nodes, _e, _m = topo.collect(_query(a))
        assert nodes["r1"]["ip"] == "10.255.1.11"
        assert not any(n.startswith("dev-") for n in nodes)


class TestAnIsland:
    def test_r6_polled_with_its_lldp_table_read_and_empty(self, topo, monkeypatch):
        nodes, edges, meta = topo.collect(_query(_with_r6(_real())))
        r6 = nodes["r6"]
        assert r6["polled"] and r6["island"]
        assert r6["island_reason"] == topo.REASON_NO_NEIGHBOURS
        assert "not directly connected to any other managed device" in r6["island_reason"]
        assert meta["islands"] == 1
        assert not nodes["r1"]["island"]
        svg = _render(topo, nodes, edges, meta, monkeypatch)
        assert "no LLDP neighbours" in svg and "Islands:" in svg
        assert "1 island(s)" in svg

    def test_an_island_is_drawn_in_the_band_below(self, topo, monkeypatch):
        nodes, edges, _m = topo.collect(_query(_with_r6(_real())))
        monkeypatch.setattr(topo, "_layout_main", lambda names, e: {
            n: (i, i % 3) for i, n in enumerate(names)})
        pos = topo.layout(nodes, edges)
        band = topo.H - topo.ISLAND_H
        assert pos["r6"][1] > band
        assert all(y < band for n, (x, y) in pos.items() if n != "r6")

    def test_an_lldp_table_nobody_reads_is_not_no_neighbours(self, topo):
        nodes, _e, _m = topo.collect(_query(_with_r6(_real(), lldp_scraped=False)))
        assert nodes["r6"]["island"]
        assert nodes["r6"]["island_reason"] == topo.REASON_NOT_READ

    def test_a_down_device_is_not_called_unconnected(self, topo):
        nodes, _e, _m = topo.collect(_query(_with_r6(_real(), up="0")))
        assert nodes["r6"]["state"] == "down"
        assert nodes["r6"]["island_reason"] == topo.REASON_DOWN

    def test_a_cut_off_pair_is_an_island_of_its_own(self, topo):
        # s1 and s2's only link to the rest is r1-s1 and r2-s2: remove them.
        a = _real()
        cut = {("r1", "s1.rcn.lab"), ("r2", "s2.rcn.lab")}
        # (s1 and s2 report only each other in the capture.)
        a["lldpRemEntry"] = [s for s in a["lldpRemEntry"]
                             if (s["metric"]["device"], s["metric"]["lldpRemEntry"]) not in cut]
        nodes, _e, meta = topo.collect(_query(a))
        assert meta["islands"] == 1
        assert nodes["s1"]["island"] and nodes["s2"]["island"]
        assert nodes["s1"]["island_reason"] == topo.REASON_APART


class TestTheDrawing:
    def test_a_name_from_a_device_is_escaped(self, topo, monkeypatch):
        a = _with_r6(_real())
        for s in a["up"]:
            if s["metric"]["device"] == "r6":
                s["metric"]["device"] = "<script>x"
        nodes, edges, meta = topo.collect(_query(a))
        svg = _render(topo, nodes, edges, meta, monkeypatch)
        assert "<script>" not in svg and "&lt;script&gt;" in svg

    def test_no_island_draws_no_band(self, topo, monkeypatch):
        nodes, edges, meta = topo.collect(_query(_real()))
        svg = _render(topo, nodes, edges, meta, monkeypatch)
        assert "Islands:" not in svg and "island(s)" not in svg

    def test_the_script_holds_no_address_literal(self):
        src = SCRIPT.read_text()
        found = set(re.findall(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", src))
        assert found == {"0.0.0.0"}       # the bind address, and nothing else
