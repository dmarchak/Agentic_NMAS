"""`collect_threat_data(network)` (`modules/sdn/closed_loop.py`, PHASE8_PLAN 17.1 S4), against
Ryu 4.34's captured answers (tests/fixtures/sdn/ryu/rest_with_peer.json) through the real
connection and driver, a fake clock and no sleep.

The second port sample is the captured one with minimal edits (the capture has one read): port
1 received 500 more packets and 40,000 more bytes, port 2 sent 500 more packets, ports 3 and
LOCAL did not move. Every expected value below is read off the fixture by hand: nine flows, one
of them a drop (Mercury's /24, an empty action list); granularity L4 (three flows match
`tp_dst`, TCP's and UDP's alike), with two L3 flows, three L2 and the match-all.

- **What it answers:** per connection and switch, the flows, the active count, the drop flows,
  port rates over the stated interval (the elapsed time measured by the clock), and coverage;
  a plain JSON-serialisable dict; 1 + 3N controller calls for N switches.
- **Coverage:** L4, L3 (IPv4 and IPv6 alike) and L2 told apart, and L2 and L3 said unable to
  show a per-port scan.
- **Failure:** a controller that fails is in the answer, unreadable with why, beside the one
  that answered; a switch whose flows fail is partial; no connection is `none`, an unreadable
  store `unreadable`; a counter that fell is a reset, never a negative rate.
- **Bounds:** the wait is the injected sleep, once, for the interval asked; an interval out of
  bounds is refused; an IPv6 controller URL reads alike.
"""
import copy
import json

import pytest
import requests

from modules.sdn import closed_loop as CL
from modules.sdn import connections as C
from tests.sdn_fakes import Clock, Response, Routes, fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

BASE = "http://192.0.2.10:8080"
BASE6 = "http://[2001:db8::10]:8080"
WITH_PEER = fixture("rest_with_peer.json")
PORT_PATH = "/stats/port/1"


def second_ports(edit=None) -> str:
    """The captured port read with the second sample's edits (the module docstring's)."""
    entry = next(e for e in WITH_PEER if e["path"] == PORT_PATH)
    body = json.loads(entry["body"])
    ports = {p["port_no"]: p for p in body["1"]}
    ports[1]["rx_packets"] += 500
    ports[1]["rx_bytes"] += 40000
    ports[2]["tx_packets"] += 500
    if edit:
        edit(ports)
    return json.dumps(body)


class Sampled(Routes):
    """The captured answers, the port read answering the second sample the second time."""

    def __init__(self, base, second=None, flows=None):
        super().__init__(WITH_PEER, base)
        self.second = second if second is not None else second_ports()
        self.flows = flows
        self.port_reads = 0

    def request(self, method, url, **kwargs):
        path = url[len(self.base):]
        if path == PORT_PATH:
            self.port_reads += 1
            if self.port_reads == 2:
                self.sent.append(dict(kwargs, method=method, url=url))
                return Response(200, self.second)
        if path == "/stats/flow/1" and self.flows is not None:
            self.sent.append(dict(kwargs, method=method, url=url))
            return self.flows if isinstance(self.flows, Response) else \
                Response(200, json.dumps({"1": self.flows}))
        return super().request(method, url, **kwargs)


def captured_flows():
    entry = next(e for e in WITH_PEER if e["path"] == "/stats/flow/1")
    return json.loads(entry["body"])["1"]


def run(network="Default", sessions=None, interval=5.0):
    clock = Clock()
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        clock.now += seconds

    sessions = sessions or {}

    def driver(net, name):
        return C.driver_for(net, name, session=sessions[name])

    got = CL.collect_threat_data(network, interval, sleep=sleep, clock=clock,
                                 now=lambda: 1_790_000_000.0, driver=driver)
    return got, slept


def save(name="ctl-1", url=BASE, network="Default"):
    C.save_connection(network, {"name": name, "kind": "ryu", "url": url}, actor="op")


@pytest.mark.usefixtures("networks")
class TestTheAnswer:
    def test_the_capture_read_whole(self):
        save()
        got, slept = run(sessions={"ctl-1": Sampled(BASE)})
        assert slept == [5.0], "one wait, the interval asked, never a real sleep"
        assert got["state"] == "ok" and got["calls"] == 4, "1 + 3N for one switch"
        (ctl,) = got["controllers"]
        assert (ctl["connection"], ctl["state"], ctl["own_cookies"]) == ("ctl-1", "ok", [0])
        (sw,) = ctl["switches"]
        assert sw["dpid"] == 1 and sw["dpid_hex"] == "0000000000000001"
        assert sw["active_flows"] == 9 and len(sw["flows"]) == 9
        assert [f["cookie"] for f in sw["drop_flows"]] == [0x4D45524300000001]
        assert sw["coverage"] == {"granularity": "L4", "scan_by_ports": True,
                                  "by_granularity": {"L4": 3, "L3": 2, "L2": 3, "none": 1},
                                  "words": CL.COVERAGE_WORDS["L4"]}
        assert sw["sample"] == {"interval_s": 5.0, "elapsed_s": 5.0}
        ports = {p["port_no"]: p for p in sw["ports"]}
        assert set(ports) == {1, 2, 3, "LOCAL"}
        assert (ports[1]["rx_pps"], ports[1]["rx_bytes_per_s"], ports[1]["tx_pps"]) == \
            (100.0, 8000.0, 0.0)
        assert ports[2]["tx_packets_delta"] == 500 and ports[2]["tx_pps"] == 100.0
        assert ports[3]["rx_pps"] == 0.0 and ports["LOCAL"]["rx_pps"] == 0.0
        assert got["summary"] == {"controllers": 1, "unreadable": 0, "partial": 0,
                                  "switches": 1, "flows": 9, "drop_flows": 1,
                                  "scan_by_ports": 1}

    def test_it_is_a_plain_json_value(self):
        save()
        got, _ = run(sessions={"ctl-1": Sampled(BASE)})
        assert json.loads(json.dumps(got)) == got

    def test_an_ipv6_controller_reads_alike(self):
        save(url=BASE6)
        got, _ = run(sessions={"ctl-1": Sampled(BASE6)})
        assert got["state"] == "ok"
        assert got["controllers"][0]["switches"][0]["active_flows"] == 9

    def test_each_connection_of_the_network(self):
        save()
        save(name="ctl-2", url=BASE6)
        got, slept = run(sessions={"ctl-1": Sampled(BASE), "ctl-2": Sampled(BASE6)})
        assert [c["connection"] for c in got["controllers"]] == ["ctl-1", "ctl-2"]
        assert slept == [5.0] and got["calls"] == 8, "one wait for the network"

    def test_the_interval_is_bounded(self):
        save()
        for bad in (0.5, 61, True, "5"):
            got, slept = run(sessions={"ctl-1": Sampled(BASE)}, interval=bad)
            assert got["state"] == "unreadable" and "interval" in got["error"] and not slept


@pytest.mark.usefixtures("networks")
class TestCoverage:
    def _coverage(self, flows):
        save()
        got, _ = run(sessions={"ctl-1": Sampled(BASE, flows=flows)})
        return got["controllers"][0]["switches"][0]["coverage"]

    def test_l2_only_flows_say_they_cannot_show_a_per_port_scan(self):
        flows = [f for f in captured_flows() if "nw_src" not in f["match"]
                 and "ipv6_src" not in f["match"]]
        cov = self._coverage(flows)
        assert cov["granularity"] == "L2" and not cov["scan_by_ports"]
        assert "cannot show a per-port scan" in cov["words"]

    def test_l3_ipv4_flows_cannot_show_one_either(self):
        flows = [f for f in captured_flows() if "tp_dst" not in f["match"]]
        cov = self._coverage(flows)
        assert cov["granularity"] == "L3" and not cov["scan_by_ports"]
        assert "cannot show a per-port scan" in cov["words"]

    def test_l3_ipv6_flows_are_l3(self):
        v6 = next(f for f in captured_flows() if "ipv6_src" in f["match"])
        v6 = copy.deepcopy(v6)
        del v6["match"]["tp_dst"]                     # the minimal edit: no transport port
        assert self._coverage([v6])["granularity"] == "L3"

    def test_an_ipv6_l4_flow_is_l4(self):
        v6 = next(f for f in captured_flows() if "ipv6_src" in f["match"])
        assert self._coverage([v6])["granularity"] == "L4"

    def test_the_match_all_alone_is_none(self):
        miss = [f for f in captured_flows() if not f["match"]]
        cov = self._coverage(miss)
        assert cov["granularity"] == "none" and cov["by_granularity"]["none"] == 1

    @pytest.mark.parametrize("match,expected", [
        ({"tcp_dst": 22}, "L4"), ({"udp_dst": 53, "ipv4_src": "192.0.2.1"}, "L4"),
        ({"tcp_src": 22, "ipv4_src": "192.0.2.1"}, "L3"), ({"ipv6_dst": "2001:db8::1"}, "L3"),
        ({"in_port": 1, "eth_src": "00:00:00:00:00:01"}, "L2"), ({"vlan_vid": 10}, "L2"),
        ({}, "none")])
    def test_one_flow_s_granularity(self, match, expected):
        assert CL.granularity(match) == expected


@pytest.mark.usefixtures("networks")
class TestFailures:
    def test_a_controller_that_fails_is_said_never_dropped(self):
        save()
        save(name="ctl-2", url=BASE6)
        down = Routes([], BASE6)
        down.request = lambda *a, **k: (_ for _ in ()).throw(
            requests.exceptions.ConnectionError("refused"))
        got, _ = run(sessions={"ctl-1": Sampled(BASE), "ctl-2": down})
        ctl = {c["connection"]: c for c in got["controllers"]}
        assert set(ctl) == {"ctl-1", "ctl-2"}
        assert ctl["ctl-1"]["state"] == "ok"
        assert ctl["ctl-2"]["state"] == "unreadable"
        assert "could not connect" in ctl["ctl-2"]["error"]
        assert got["state"] == "partial" and got["summary"]["unreadable"] == 1
        assert "ctl-2" in got["error"]

    def test_a_switch_whose_flows_fail_is_partial_naming_the_read(self):
        save()
        got, _ = run(sessions={"ctl-1": Sampled(BASE, flows=Response(500, "Traceback\nboom"))})
        sw = got["controllers"][0]["switches"][0]
        assert sw["state"] == "partial" and sw["error"].startswith("flows: HTTP 500")
        assert sw["active_flows"] is None and sw["ports"], "the ports still read"
        assert got["controllers"][0]["state"] == "partial", "its only switch read in part"
        assert got["state"] == "partial"

    def test_a_switch_with_nothing_read_is_unreadable_and_so_its_controller(self):
        save()
        sess = Sampled(BASE, flows=Response(500, ""))
        real = sess.request

        def no_ports(method, url, **kwargs):
            if url.endswith(PORT_PATH):
                raise requests.exceptions.ConnectionError("gone")
            return real(method, url, **kwargs)
        sess.request = no_ports
        got, _ = run(sessions={"ctl-1": sess})
        sw = got["controllers"][0]["switches"][0]
        assert sw["state"] == "unreadable" and "first port read" in sw["error"]
        assert got["controllers"][0]["state"] == "unreadable" and got["state"] == "unreadable"

    def test_a_counter_that_fell_is_a_reset_never_a_negative_rate(self):
        save()

        def reset(ports):
            ports[3]["rx_packets"] = 1
        got, _ = run(sessions={"ctl-1": Sampled(BASE, second=second_ports(reset))})
        ports = {p["port_no"]: p for p in got["controllers"][0]["switches"][0]["ports"]}
        assert "a reset" in ports[3]["note"] and "rx_pps" not in ports[3]

    def test_no_connection_is_none(self):
        got, slept = run()
        assert got["state"] == "none" and got["controllers"] == [] and not slept
        assert got["words"] == "Default has no SDN controller connection"

    def test_an_unreadable_store_is_unreadable(self, networks):
        (networks / "lists" / "branch").mkdir(parents=True)
        (networks / "lists" / "branch" / "settings.json").write_text("{torn")
        got, _ = run("Branch")
        assert got["state"] == "unreadable" and "could not be read" in got["error"]

    def test_a_driver_that_raises_is_that_controller_s_failure(self):
        save()

        def boom(net, name):
            raise RuntimeError("no driver today")
        got = CL.collect_threat_data("Default", 5.0, sleep=lambda s: None, clock=Clock(),
                                     driver=boom)
        (ctl,) = got["controllers"]
        assert ctl["state"] == "unreadable" and "no driver today" in ctl["error"]
