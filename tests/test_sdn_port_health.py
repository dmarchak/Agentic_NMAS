"""T9 (the SDN platform design revision 6, section 15; P2a; C2602): the Ryu driver's `port_desc`
on recorded answers, health read from LINK_DOWN and never from LIVE.

The recordings: the masked bring-up capture (tests/fixtures/lab9_captures/2026-11-06/
ryu-rest.txt: two Aristas on EOS 4.17 reporting every working port with state 0, a ProCurve and
two Open vSwitch hosts reporting LIVE, one OVS port unconnected at state 1, and each OVS
bridge's own port administratively down), and the container harness's (real Ryu 4.34 and real
Open vSwitch, tests/fixtures/sdn/harness/), both served by the recorded Ryu
(tests/fixtures/sdn/ryu_recorded.py) through Mercury's real driver.

The fault: a health read built on LIVE would call every working Arista port down; one that
ignored LINK_DOWN would call the unconnected port up. Each case below is held to the capture's
own raw bits, read back independently of the driver.
"""

import json

import pytest

from modules.sdn.drivers import base as B
from modules.sdn.drivers.base import Connection, SpecError
from modules.sdn.drivers.ryu import RyuDriver
from tests.fixtures.sdn import ryu_recorded as R
from tests.sdn_fakes import Clock, Response, Session

#: The OpenFlow 1.3 specification's own bits (`ofp_port_config`: OFPPC_PORT_DOWN = 1 << 0;
#: `ofp_port_state`: OFPPS_LINK_DOWN = 1 << 0, OFPPS_BLOCKED = 1 << 1, OFPPS_LIVE = 1 << 2),
#: written here from the specification, never read from the code under test.
PORT_DOWN, LINK_DOWN, LIVE = 1 << 0, 1 << 0, 1 << 2

#: The capture's switches by what their description says (desc's mfr_desc), read in the test
#: from the capture itself so a changed capture changes the expectation.
CAPTURE = R.RecordedRyu()


def _by_maker(maker: str) -> list:
    return [d for d in CAPTURE.dpids()
            if CAPTURE.get(f"/stats/desc/{d}")[str(d)]["mfr_desc"] == maker]


def _raw(dpid: int) -> dict:
    """The capture's own port bits, `{port_no: (config, state)}`, not through the driver."""
    return {p["port_no"]: (p["config"], p["state"])
            for p in CAPTURE.get(f"/stats/portdesc/{dpid}")[str(dpid)]}


def test_the_capture_holds_the_cases_this_file_tests():
    """A floor: two Aristas, a ProCurve, two OVS hosts, an unconnected port at state 1."""
    assert len(_by_maker("Arista Networks")) == 2
    assert len(_by_maker("HP")) == 1
    assert len(_by_maker("Nicira, Inc.")) == 2
    states = [s for d in CAPTURE.dpids() for (_c, s) in _raw(d).values()]
    assert states.count(0) >= 4 and LINK_DOWN in states and LIVE in states


def test_the_driver_s_bits_are_the_specification_s():
    """The driver's named bits are the OpenFlow specification's, so a health read on them reads
    the bit the switch set."""
    assert (B.OFPPC_PORT_DOWN, B.OFPPS_LINK_DOWN, B.OFPPS_LIVE) == (PORT_DOWN, LINK_DOWN, LIVE)


@pytest.mark.parametrize("dpid", _by_maker("Arista Networks"))
def test_a_working_arista_port_reads_up_though_it_reports_no_live_bit(dpid):
    got = CAPTURE.driver().port_desc(dpid)
    assert got["ok"], got
    assert got["health_from"] == B.HEALTH_FROM
    assert got["ports"] and all(_raw(dpid)[p["port_no"]] == (0, 0) for p in got["ports"])
    assert [p["link_up"] for p in got["ports"]] == [True] * len(got["ports"])
    # What a LIVE-based read would have said: every one of them down (C2602).
    assert [p["live"] for p in got["ports"]] == [False] * len(got["ports"])


def test_every_recorded_port_reads_down_exactly_when_its_state_carries_link_down():
    seen_down = 0
    for dpid in CAPTURE.dpids():
        got = CAPTURE.driver().port_desc(dpid)
        assert got["ok"], (dpid, got)
        raw = _raw(dpid)
        assert {p["port_no"] for p in got["ports"]} == set(raw)
        for port in got["ports"]:
            config, state = raw[port["port_no"]]
            assert port["link_up"] is (state & LINK_DOWN == 0), (dpid, port)
            assert port["admin_up"] is (config & PORT_DOWN == 0), (dpid, port)
            assert (port["config"], port["state"]) == (config, state)
            seen_down += not port["link_up"]
    assert seen_down >= 3          # the unconnected eno4 and both bridges' own port


def test_the_unconnected_ovs_port_reads_down_and_admin_up():
    ovs = [d for d in _by_maker("Nicira, Inc.") if (0, LINK_DOWN) in _raw(d).values()]
    assert len(ovs) == 1
    port = [p for p in CAPTURE.driver().port_desc(ovs[0])["ports"] if p["name"] == "eno4"][0]
    assert (port["link_up"], port["admin_up"], port["port_no"]) == (False, True, 3)


def test_the_harness_recording_reads_the_same_way():
    """Real Ryu on real OVS: the port held down (config PORT_DOWN, state LINK_DOWN) reads down
    and administratively down; the others up, with the numbers the bridge gave them."""
    harness = R.RecordedRyu(R.HARNESS)
    got = harness.driver().port_desc(4)
    assert got["ok"], got
    ports = {p["port_no"]: (p["name"], p["link_up"], p["admin_up"]) for p in got["ports"]}
    assert ports == {"LOCAL": ("br4", True, True), 1: ("s4-eth1", True, True),
                     2: ("s4-eth2", True, True), 3: ("s4-eth3", False, False)}


@pytest.mark.parametrize("config, state, want", [
    (0, 0, (True, True, False)),                       # an Arista's working port
    (0, LIVE, (True, True, True)),               # OVS's and the ProCurve's
    (0, LINK_DOWN, (False, True, False)),        # unconnected
    (PORT_DOWN, LINK_DOWN, (False, False, False)),   # held down
    (0, 2, (True, True, False)),                       # BLOCKED: not a link state
    (PORT_DOWN, LIVE, (True, False, True)),
])
def test_the_derived_values_come_from_the_bits_alone(config, state, want):
    port = B.port_desc_from_bits(1, 7, config=config, state=state)
    assert (port.link_up, port.admin_up, port.live) == want


@pytest.mark.parametrize("config, state", [(True, 0), (0, None), (-1, 0), (0, "4")])
def test_bits_that_are_not_whole_numbers_are_refused(config, state):
    with pytest.raises(SpecError, match="whole number of OpenFlow bits"):
        B.port_desc_from_bits(1, 1, config=config, state=state)


def test_a_reserved_port_keeps_its_name_and_a_bad_number_is_refused():
    assert B.port_desc_from_bits(1, "LOCAL").port_no == "LOCAL"
    with pytest.raises(SpecError, match="not a port number"):
        B.port_desc_from_bits(1, "eth0")


def _driver(*answers):
    return RyuDriver(Connection("http://127.0.0.1:8080"), session=Session(*answers),
                     clock=Clock(), sleep=lambda s: None)


def test_a_switch_the_controller_does_not_have_is_named():
    got = _driver(Response(404, "")).port_desc(9)
    assert not got["ok"] and got["no_switch"] and "no switch 9" in got["error"]


def test_an_answer_that_is_not_a_list_of_ports_is_refused():
    got = _driver(Response(200, json.dumps({"9": {"port_no": 1}}))).port_desc(9)
    assert not got["ok"] and "not a list of ports" in got["error"]


def test_a_port_with_bits_that_are_not_numbers_is_refused_not_read_as_up():
    body = json.dumps({"9": [{"port_no": 1, "name": "p1", "config": 0, "state": "LIVE"}]})
    got = _driver(Response(200, body)).port_desc(9)
    assert not got["ok"] and "whole number of OpenFlow bits" in got["error"]
