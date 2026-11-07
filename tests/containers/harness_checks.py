"""The container harness's checks (T8's base; the SDN platform design revision 6, section 15):
Mercury's own Ryu driver against real Ryu 4.34 and real Open vSwitch on its userspace datapath.

Run only by `scripts/nmas-harness check`, inside the harness's runner container on the
harness's internal network (tests/containers/compose.yml), never by the suite: the file is not
named test_*.py, so the suite does not collect it, and every check here needs the harness's
containers. NMAS_HARNESS_REST is the controller's REST inside that network.

What each check catches:
- every bridge reaching the controller with its datapath id: a DPID format or controller target
  wrong (the bridges are tests/containers/ovs/bridges.conf);
- `port_desc` against a real switch: the port numbers the bridge was given (ofport_request), and
  health from LINK_DOWN (a port held down reads down, the others up);
- `table_features` against a real switch: the driver reads a real pipeline's answer, every
  instruction and action by name, none left as UNKNOWN;
- the links Ryu discovers over the bridges' cable: a topology read that misses a real link;
- no route off the network: the harness's network is internal (the operator's condition 1),
  measured from inside it.
"""

import os
import time

import pytest

from modules.sdn.drivers.base import Connection
from modules.sdn.drivers.ryu import RyuDriver

REST = os.environ.get("NMAS_HARNESS_REST", "")
HERE = os.path.dirname(os.path.abspath(__file__))
#: Ryu's link discovery sends LLDP out of each port in turn (ryu/topology/switches.py, Ryu 4.34).
#: Not measured on its own yet: the runs of 2026-11-07 found both directions on their first read,
#: about 3 s after the switches connected (the checks before this one take that long); 8 s is
#: 2.5x that.
LINKS_BOUND_S = 8.0

if not REST:
    raise RuntimeError("harness_checks.py runs only in the harness (scripts/nmas-harness "
                       "check), which sets NMAS_HARNESS_REST")


def bridges() -> dict:
    """bridges.conf read: {dpid: {"ports": {ofport: (name, up)}}}, patches as up ports."""
    out, names = {}, {}
    with open(os.path.join(HERE, "ovs", "bridges.conf"), encoding="utf-8") as fh:
        for line in fh:
            words = line.split()
            if not words or words[0].startswith("#"):
                continue
            if words[0] == "bridge":
                names[words[1]] = int(words[2], 16)
                out[names[words[1]]] = {}
            elif words[0] == "port":
                out[names[words[1]]][int(words[3])] = (words[2], words[4] == "up")
            elif words[0] == "patch":
                out[names[words[1]]][int(words[3])] = (words[2], True)
                out[names[words[4]]][int(words[6])] = (words[5], True)
    return out


@pytest.fixture(scope="module")
def driver():
    return RyuDriver(Connection(REST, timeout=5.0))


def test_every_bridge_reaches_the_controller_with_its_datapath_id(driver):
    got = driver.switches()
    assert got["ok"], got
    assert [s["dpid"] for s in got["switches"]] == sorted(bridges())


@pytest.mark.parametrize("dpid", sorted(bridges()))
def test_port_desc_reads_each_port_by_its_number_and_health_by_link_down(driver, dpid):
    got = driver.port_desc(dpid)
    assert got["ok"], got
    assert "LINK_DOWN" in got["health_from"]
    ports = {p["port_no"]: p for p in got["ports"] if p["port_no"] != "LOCAL"}
    want = bridges()[dpid]
    assert {n: ports[n]["name"] for n in ports} == {n: name for n, (name, _up) in want.items()}
    assert {n: ports[n]["link_up"] for n in ports} == {n: up for n, (_name, up) in want.items()}
    for number, (_name, up) in want.items():
        # A port held down: config PORT_DOWN and state LINK_DOWN, as OVS reports it.
        assert ports[number]["admin_up"] is up
        assert bool(ports[number]["state"] & 1) is (not up)


@pytest.mark.parametrize("dpid", sorted(bridges()))
def test_table_features_reads_a_real_pipeline_by_name(driver, dpid):
    got = driver.table_features(dpid)
    assert got["ok"], got
    tables = got["tables"]
    assert tables and tables[0]["table_id"] == 0
    first = tables[0]
    assert {"in_port", "eth_type", "eth_src", "ipv4_src", "tcp_dst"} <= set(first["match"])
    assert {"GOTO_TABLE", "APPLY_ACTIONS", "METER"} <= set(first["instructions"])
    assert "OUTPUT" in first["apply_actions"]
    names = [n for t in tables for key in ("instructions", "apply_actions", "write_actions")
             for n in t[key]]
    assert names and not [n for n in names if n.startswith("UNKNOWN(")]
    assert all(t["unknown_properties"] == [] for t in tables)


def test_the_controller_discovers_the_cable_between_the_bridges(driver):
    deadline, got = time.monotonic() + LINKS_BOUND_S, None
    while time.monotonic() < deadline:
        got = driver.links()
        if got["ok"] and len(got["links"]) >= 2:
            break
        time.sleep(0.5)
    assert got["ok"], got
    ends = {((l["src"]["dpid"], l["src"]["port_no"]), (l["dst"]["dpid"], l["dst"]["port_no"]))
            for l in got["links"]}
    assert ends == {((3, 2), (4, 2)), ((4, 2), (3, 2))}, (ends, LINKS_BOUND_S)


def test_the_network_has_no_route_off_it():
    """The operator's condition 1, measured where the checks run: no default route, IPv4 or
    IPv6 (an internal Docker network gives its containers no gateway)."""
    with open("/proc/net/route", encoding="ascii") as fh:
        rows = [line.split() for line in fh.readlines()[1:]]
    assert rows, "no IPv4 route at all: the runner is not on the harness network"
    assert not [r for r in rows if r[1] == "00000000"], rows
    if os.path.exists("/proc/net/ipv6_route"):
        with open("/proc/net/ipv6_route", encoding="ascii") as fh:
            six = [line.split() for line in fh]
        assert not [r for r in six if r[0] == "0" * 32 and r[1] == "00" and r[9] != "lo"], six
