"""Topology's Path… (board D, C693 and C694): the path packets take, read hop by hop from each
device's own forwarding table (modules/path_trace.py).

The answers are real: `show ip cef` for r5's two peering addresses and two loopbacks, asked of
every managed device but s3 through Mercury's reads engine on 2026-10-12
(tests/fixtures/path/cef_fleet.json). The network is the topology tests' (the real reader over
the real captures). A case the lab does not hold (a loop, a hop that cannot be read, a next hop
no device holds) is the captured answers with one minimal edit, named where it is made.
"""

import json
import os

import pytest

from modules import path_trace as P

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "path", "cef_fleet.json")


def _fx():
    with open(FIX, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def net():
    from tests.test_topology_v2 import _value
    return _value()["networks"]["Lab"]


def _reader(dest, answers=None, unread=()):
    answers = answers or _fx()["answers"]
    asked = []

    def read(devices):
        asked.append(list(devices))
        return {d: ({"ok": False, "why": "held by a deploy (test)"} if d in unread else
                    {"ok": True, "answer": answers[d][f"show ip cef {dest}"]}
                    if d in answers else {"ok": False, "why": "not in the capture"})
                for d in devices}
    read.asked = asked
    return read


def _trace(net, src, dest, **kw):
    owners = kw.pop("owners", None) or P.owners(net["nodes"], net["layers"]["bgp"])
    managed = {n for n, v in net["nodes"].items() if v.get("managed")}
    read = _reader(dest, **kw)
    return P.trace(src, dest, owners, read, managed), read


def _paths(result):
    return sorted((b["end"], tuple(h["device"] for h in b["hops"])) for b in result["branches"])


# --------------------------------------------------------------------------- parsing

class TestParse:
    def test_every_captured_answer_is_understood(self):
        states = {}
        for dev, answers in _fx()["answers"].items():
            for cmd, text in answers.items():
                got = P.parse_cef(text)
                assert got["state"] != "unknown", (dev, cmd, got)
                states[got["state"]] = states.get(got["state"], 0) + 1
        # The floor: the capture holds each form the lab produces.
        assert set(states) == {"next", "attached", "receive", "no_route"}, states
        assert sum(states.values()) == 32

    def test_equal_cost_next_hops_are_each_kept(self):
        got = P.parse_cef(_fx()["answers"]["r1"]["show ip cef 198.51.100.1"])
        assert got["prefix"] == "0.0.0.0/0"
        assert got["hops"] == [{"address": "10.255.3.13", "iface": "GigabitEthernet2"},
                               {"address": "10.255.3.14", "iface": "GigabitEthernet2"}]

    def test_an_svi_egress_and_a_receive(self):
        s4 = P.parse_cef(_fx()["answers"]["s4"]["show ip cef 10.255.1.14"])
        assert s4["hops"] == [{"address": "10.255.3.14", "iface": "Vlan100"}]
        r4 = P.parse_cef(_fx()["answers"]["r4"]["show ip cef 10.255.1.14"])
        assert r4["state"] == "receive" and r4["iface"] == "loopback0"

    @pytest.mark.parametrize("text", ["", "% Invalid input detected at '^' marker.",
                                      "something else entirely"])
    def test_what_is_not_an_answer_says_so(self, text):
        got = P.parse_cef(text)
        assert got["state"] == "unknown" and got["why"]


# --------------------------------------------------------------------------- the network

class TestNetwork:
    def test_an_address_two_devices_hold_names_neither(self, net):
        owners = P.owners(net["nodes"], net["layers"]["bgp"])
        held = [a for n in net["nodes"].values() for _i, a in n.get("addresses") or []]
        shared = {a for a in held if held.count(a) > 1 and ":" not in a}
        assert shared, "the floor: the lab's shared management address"
        assert not shared & set(owners)
        assert owners["10.255.3.13"] == "r3" and owners["198.51.100.1"] == "r5"

    def test_r5_is_offered_by_each_peering_address(self, net):
        to = P.destinations(net["nodes"], net["layers"]["bgp"])
        words = [d["words"] for d in to if d["device"] == "r5"]
        assert words == ["r5 (outside, AS 65002): 198.51.100.1, r3's peering",
                         "r5 (outside, AS 65002): 198.51.100.3, r4's peering"]
        assert {"value": "10.255.1.14", "device": "r4",
                "words": "r4 (its loopback 10.255.1.14)"} in to
        assert all(":" not in d["value"] for d in to)

    def test_from_is_the_routing_devices(self, net):
        assert P.sources(net["nodes"]) == ["r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4"]

    def test_layer_2_crosses_switches_never_a_router(self, net):
        phys, sw = net["layers"]["physical"], P.switches(net["nodes"])
        # r1 leaves on Gi2 for r4: across s3 and s4; never through r3, which is as near.
        assert P.l2_path(phys, "r1", "GigabitEthernet2", "r4", sw) == [
            ("r1", "s3"), ("r4", "s4"), ("s3", "s4")]
        # r3 reaches r4 two ways: its own cable (Gi4) and the shared segment (Gi3).
        assert P.l2_path(phys, "r3", "GigabitEthernet4", "r4", sw) == [("r3", "r4")]
        assert P.l2_path(phys, "r3", "GigabitEthernet3", "r4", sw) == [
            ("r3", "s3"), ("r4", "s4"), ("s3", "s4")]
        # An SVI's egress is no cabled port: the switches' shortest path.
        assert P.l2_path(phys, "s4", "Vlan100", "r1", sw) == [("r1", "s3"), ("s3", "s4")]


# --------------------------------------------------------------------------- the trace

class TestTrace:
    def test_r1_to_r5_one_branch_delivers_and_one_drops(self, net):
        got, read = _trace(net, "r1", "198.51.100.1")
        assert _paths(got) == [("delivered", ("r1", "r3")), ("dropped", ("r1", "r4"))]
        assert read.asked == [["r1"], ["r3", "r4"]]
        delivered, dropped = got["branches"]
        assert delivered["words"] == "delivered to r5"
        assert dropped["words"] == "dropped at r4: no route to 198.51.100.1"
        assert got["delivered"] == 1

    def test_r2_to_r4_s_peering_mirrors_it(self, net):
        got, _ = _trace(net, "r2", "198.51.100.3")
        assert _paths(got) == [("delivered", ("r2", "r4")), ("dropped", ("r2", "r3"))]

    def test_three_hops_from_a_switch(self, net):
        got, read = _trace(net, "s1", "198.51.100.1")
        assert _paths(got) == [("delivered", ("s1", "r1", "r3")),
                               ("dropped", ("s1", "r1", "r4"))]
        assert read.asked == [["s1"], ["r1"], ["r3", "r4"]]

    def test_the_destination_s_own_device_and_its_next_hop(self, net):
        own, _ = _trace(net, "r4", "10.255.1.14")
        assert _paths(own) == [("delivered", ("r4",))]
        # r3 holds two equal-cost next hops to r4: both deliver.
        two, _ = _trace(net, "r3", "10.255.1.14")
        assert _paths(two) == [("delivered", ("r3",)), ("delivered", ("r3",))]
        assert {h["iface"] for b in two["branches"] for h in b["hops"]} == {
            "GigabitEthernet3", "GigabitEthernet4"}

    def test_a_hop_that_cannot_be_read_stops_the_branch(self, net):
        got, _ = _trace(net, "r1", "198.51.100.1", unread=("r3",))
        ends = dict((p, e) for e, p in _paths(got))
        assert ends[("r1", "r3")] == "unread"
        b = next(b for b in got["branches"] if b["end"] == "unread")
        assert "not read (held by a deploy (test))" in b["words"]
        assert "what follows is not known" in b["words"]

    def test_a_loop_is_named(self, net):
        # One edit: r4 sends 198.51.100.1 back to r1's address on the shared segment.
        answers = _fx()["answers"]
        answers["r4"]["show ip cef 198.51.100.1"] = \
            "0.0.0.0/0\n  nexthop 10.255.3.11 GigabitEthernet3"
        got, _ = _trace(net, "r1", "198.51.100.1", answers=answers)
        b = next(b for b in got["branches"] if b["end"] == "loop")
        assert b["words"] == "r4 sends it back to r1: a forwarding loop"

    def test_a_next_hop_no_device_holds_leaves_the_network(self, net):
        # One edit: the owner map without r3's segment address.
        owners = P.owners(net["nodes"], net["layers"]["bgp"])
        del owners["10.255.3.13"]
        got, _ = _trace(net, "r1", "198.51.100.1", owners=owners)
        b = next(b for b in got["branches"] if b["end"] == "edge")
        assert "leaves the network at r1 toward 10.255.3.13" in b["words"]

    def test_past_the_branch_bound_it_says_so(self, net, monkeypatch):
        monkeypatch.setattr(P, "MAX_BRANCHES", 1)
        got, _ = _trace(net, "r1", "198.51.100.1")
        assert [b["end"] for b in got["branches"]].count("bounded") == 1
        assert "more than 1 equal-cost branches" in next(
            b["words"] for b in got["branches"] if b["end"] == "bounded")

    def test_a_delivered_branch_wins_a_shared_link_and_layer_2_is_marked(self, net):
        got, _ = _trace(net, "r1", "198.51.100.1")
        lit = P.drawn(got, net["layers"]["physical"], net["nodes"])
        assert lit["edges"] == {"r1|s3": {"cls": "on", "l2": True},
                                "r3|s3": {"cls": "on", "l2": True},
                                "r3|r5": {"cls": "on", "l2": False},
                                "r4|s4": {"cls": "drop", "l2": True},
                                "s3|s4": {"cls": "drop", "l2": True}}
        assert lit["nodes"] == {"r1": "on", "r3": "on", "r5": "on", "r4": "drop"}


# --------------------------------------------------------------------------- the record

class TestRecord:
    def test_a_refusal_names_both_sides_and_asks_nothing(self, net, tmp_path, monkeypatch):
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        got = P.start("Lab", "r9", "198.51.100.1", "", "p", nodes=net["nodes"],
                      bgp=net["layers"]["bgp"], run_reads=lambda d, c: 1 / 0)
        assert got["refused"].startswith("From is 'r9', which is not one of this network's "
                                         "routing devices (r1, r2,")
        assert "an IPv6 address" in P.refusal("r1", "2001:db8::1", ["r1"])
        assert "not an address" in P.refusal("r1", "r5; reload", ["r1"])
        assert not (tmp_path / "paths").exists()

    def test_the_job_writes_its_record_and_announces(self, net, tmp_path, monkeypatch):
        from modules.nsot import capture_job
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        heard = []
        monkeypatch.setattr("modules.invalidation.announce",
                            lambda keys, by="", ok=True: heard.append((tuple(keys), by)))
        answers = _fx()["answers"]
        sent = []

        def run_reads(devices, command):
            sent.append((list(devices), command))
            return {d: {"ok": True, "answer": answers[d][command]} for d in devices}

        got = P.start("Lab", "r1", "198.51.100.1", "r5 (outside)", "test-person",
                      nodes=net["nodes"], bgp=net["layers"]["bgp"], run_reads=run_reads)
        assert capture_job.wait(got["job"], 10)
        rec = P.get("Lab", got["trace"])
        assert rec["state"] == "done" and rec["actor"] == "test-person"
        assert rec["read"] == ["r1", "r3", "r4"] and rec["reading"] == []
        assert [b["end"] for b in rec["branches"]] == ["delivered", "dropped"]
        assert sent == [(["r1"], "show ip cef 198.51.100.1"),
                        (["r3", "r4"], "show ip cef 198.51.100.1")]
        assert (("path_trace",), "path-trace") in heard

    def test_absent_and_unreadable_are_different(self, tmp_path, monkeypatch):
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        assert P.get("Lab", "0" * 32) is None
        (tmp_path / "paths").mkdir()
        (tmp_path / "paths" / ("1" * 32 + ".json")).write_text("{not json")
        assert "unreadable" in P.get("Lab", "1" * 32)
        with pytest.raises(ValueError):
            P.get("Lab", "../../etc/passwd")

    def test_only_the_latest_are_kept(self, tmp_path, monkeypatch):
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        monkeypatch.setattr(P, "KEEP", 3)
        for i in range(5):
            P._write("Lab", {"id": f"{i:032x}"})
            os.utime(tmp_path / "paths" / f"{i:032x}.json", (1000 + i, 1000 + i))
        P._prune("Lab")
        assert sorted(os.listdir(tmp_path / "paths")) == [f"{i:032x}.json" for i in (2, 3, 4)]
