"""DHCP steering on real Open vSwitch through real Ryu 4.34 (Lab 9 Objective 6, the REST path;
C2904): the recorded measurement tests/fixtures/sdn/harness/dhcp-steering-ovs-3.3.9-ryu-4.34-
py3.5.json (its README says when and how it was made: the harness up, the compiled flows sent
through Mercury's Ryu driver to ofctl_rest, `ovs-appctl ofproto/trace`, the harness down).

The suite cannot start a container, so the recording is held to the code instead:
- the requests recorded are exactly what `dhcp_steer.compile` and the Ryu driver render now
  for the harness's export (a change to either fails here until the proof is made again);
- every request was answered 200, and Mercury's own Verify (`flow_ops.verify_installed`)
  passes on the tables real Ryu read back (its dotted mask for the server's prefix among them);
- the DHCPDISCOVER entering the edge port left br3 with eth_dst rewritten to the server's MAC
  and br4 on the server's port; each server reply arriving on the edge port was dropped by a
  steering flow, and the server's own reply matched none.
"""

import importlib.util
import json
import os

import pytest

from modules.sdn import flow_intent as F
from modules.sdn import flow_ops as O

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "sdn", "harness")
RECORDING = os.path.join(HERE, "dhcp-steering-ovs-3.3.9-ryu-4.34-py3.5.json")
MAC = "00:00:5e:00:53:01"


def _proof():
    spec = importlib.util.spec_from_file_location("dhcp_steer_proof",
                                                  os.path.join(HERE, "dhcp_steer_proof.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rec():
    with open(RECORDING, encoding="utf-8") as fh:
        return json.load(fh)


def trace(rec, name):
    return next(t for t in rec["traces"] if t["name"] == name)["output"]


def cookie_of(rec, role, dpid=3, dst=None):
    for r in rec["requests"]:
        body = json.loads(r["request"]["body"])
        if r["role"] == role and r["dpid"] == dpid and (dst is None or
                                                       body["match"].get("ipv4_dst") == dst):
            return F.cookie_hex(body["cookie"])
    raise AssertionError(f"no recorded {role} on {dpid}")


def test_the_recorded_requests_are_what_the_code_renders_now(rec):
    assert _proof().rendered() == rec["requests"]
    assert [(r["dpid"], r["role"]) for r in rec["requests"]] == [
        (4, "transit"), (3, "request"), (3, "reply_drop"), (3, "reply_drop")]


def test_every_request_was_answered_and_verify_passes_on_what_ryu_read_back(rec):
    assert [s["answer"]["status"] for s in rec["sent"]] == [200] * len(rec["requests"])
    tables = rec["tables"]

    class Read:
        @staticmethod
        def flows(dpid):
            return {"ok": True, "flows": tables[str(dpid)]}

    for r in rec["requests"]:
        spec = json.loads(r["request"]["body"])
        dpid = spec.pop("dpid")
        got = O.verify_installed(Read(), dpid, [{"expect": {"present": spec},
                                                 "words": r["role"]}], sleep=lambda s: None)
        assert got["ok"], got["checks"]
    masked = [f for f in tables["3"] if "/" in str(f["match"].get("ipv4_dst"))]
    assert masked and masked[0]["match"]["ipv4_dst"] == "198.51.100.0/255.255.255.0", \
        "Ryu reads a prefix back as a dotted mask, and Verify reads it as the same"


def test_the_discover_leaves_rewritten_to_the_server_s_mac_on_the_server_s_port(rec):
    out = trace(rec, "request")
    br3, br4 = out.split('bridge("br4")')
    assert f"cookie {cookie_of(rec, 'request')}" in br3
    assert f"set_field:{MAC}->eth_dst" in br3 and "output:2" in br3
    assert f"cookie {cookie_of(rec, 'transit', dpid=4)}" in br4 and "output:1" in br4
    assert f"Datapath actions: set(eth(dst={MAC})),4" in out
    assert "s4-eth1 1/4: (dummy)" in rec["datapath_ports"], "datapath port 4 is br4's port 1"
    assert f"Final flow: udp,in_port=1,vlan_tci=0x0000,dl_src=aa:bb:cc:00:00:01,dl_dst={MAC}," \
        "nw_src=0.0.0.0,nw_dst=255.255.255.255" in out, "ipv4_dst is kept, never rewritten"


@pytest.mark.parametrize("name,dst", [("reply_broadcast_from_edge", "255.255.255.255"),
                                      ("reply_unicast_from_edge", "198.51.100.0/24")])
def test_a_server_reply_arriving_on_an_edge_port_is_dropped(rec, name, dst):
    out = trace(rec, name)
    assert f"cookie {cookie_of(rec, 'reply_drop', dst=dst)}" in out
    table = out.split("Final flow")[0]
    assert "    drop\n" in table and "output:" not in table


def test_the_server_s_own_reply_matches_no_steering_flow(rec):
    out = trace(rec, "reply_from_server_port")
    assert "0. No match." in out and "cookie 0x4d45" not in out
