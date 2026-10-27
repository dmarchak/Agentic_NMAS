"""The Ryu driver (`modules/sdn/drivers/ryu.py`, PHASE8_PLAN 17.1 S1) against Ryu 4.34's own
answers (tests/fixtures/sdn/ryu/, README.md there says how each was made), no network.

- **Reads:** each call's answer translated whole into the one shape. Every expected value here
  is read off the fixture's text by hand, a path independent of the translation: Ryu's
  OpenFlow 1.0 match keys as OXM names (`tp_dst` as `tcp_dst` or `udp_dst` by `ip_proto`, a
  VLAN's decimal string as a number, an IPv6 flow beside the IPv4 ones), its action strings
  as normalised actions (an empty list a drop, `OUTPUT:CONTROLLER`, `METER:1`,
  `WRITE_ACTIONS`, `GOTO_TABLE`, `SET_FIELD` with a MAC's colons), meters' configuration and
  counters joined, `LOCAL` kept as a name; and the empty answers.
- **Failures in words:** a switch that is not there, a malformed request, a call the
  controller does not serve (topology, captured), a 500's traceback by its last line, an
  answer for another switch, a 200 that is not JSON.
- **Writes:** each render is exactly the body Ryu accepted in the capture, and what reached
  the switch on the wire for it (peer_log.json, decoded by Ryu's parser) is the message the
  spec meant: the match whole (an IPv6 one too), the meter instruction, DELETE_STRICT with
  the whole cookie masked, meter flags 13. A write's 200 says sent, not installed.
- **Ryu's parser:** a body carrying JSON's `true` fails it (captured: a 500), so no render
  can carry one; every rendered body reads the same to `ast.literal_eval` as to JSON.
- **Round trip:** every flow read back that the driver could translate renders again with
  its match and actions unchanged; one it could not (`UNPARSED`) is refused, naming Ryu's
  text.
"""
import ast
import json
from types import SimpleNamespace

import pytest

from modules.sdn.drivers import ryu as R
from modules.sdn.drivers.base import UINT64_MAX, Connection
from tests.sdn_fakes import Response, Routes, Session, captured, fixture

BASE = "http://127.0.0.1:8080"
WITH_PEER = fixture("rest_with_peer.json")
NO_SWITCH = fixture("rest_no_switch.json")
PEER_LOG = fixture("peer_log.json")
MERCURY_1, MERCURY_2, MERCURY_3 = 0x4D45524300000001, 0x4D45524300000002, 0x4D45524300000003

#: The specs the capture's writes were made from (the same as the capture run's).
DROP = {"priority": 100, "cookie": MERCURY_1, "hard_timeout": 300,
        "match": {"eth_type": 2048, "ipv4_src": "192.0.2.0/255.255.255.0"}, "actions": []}
LIMIT = {"priority": 90, "cookie": MERCURY_2, "hard_timeout": 300,
         "match": {"in_port": 3, "eth_type": 2048, "ipv4_src": "192.0.2.3"},
         "actions": [{"type": "METER", "meter_id": 1}, {"type": "OUTPUT", "port": 2}]}
V6_DROP = {"priority": 100, "cookie": MERCURY_3, "hard_timeout": 300,
           "match": {"eth_type": 0x86DD, "ipv6_src": "2001:db8::1", "ip_proto": 6,
                     "tcp_dst": 22}, "actions": []}
METER = {"meter_id": 1, "flags": ["KBPS", "BURST", "STATS"],
         "bands": [{"type": "DROP", "rate": 1000, "burst_size": 100}]}


def driver(session=None, url=BASE):
    return R.RyuDriver(Connection(url), session=session or Routes(WITH_PEER, url))


def one(entries, method, path, body=None):
    (entry,) = [e for e in entries if (e["method"], e["path"]) == (method, path)
                and (body is None or e["request_body"] == body)]
    return entry


def flow(**kw):
    out = {"dpid": 1, "table_id": 0, "priority": 0, "cookie": 0, "match": {}, "actions": [],
           "idle_timeout": 0, "hard_timeout": 0}
    out.update(kw)
    return out


# ───────────────────────────────────────────────────────────────────────────── reads

def test_test_says_it_answers_and_that_ofctl_rest_reports_no_version():
    assert driver().test() == {"ok": True, "error": "", "answers": True, "version": None,
                               "version_note": "Ryu's ofctl_rest reports no version",
                               "switch_count": 1}


def test_switches_with_one_connected_and_with_none():
    assert driver().switches() == {"ok": True, "error": "", "switches": [
        {"dpid": 1, "dpid_hex": "0000000000000001"}]}
    empty = one(NO_SWITCH, "GET", "/stats/switches")
    assert driver(Session(captured(empty))).switches() == {"ok": True, "error": "",
                                                           "switches": []}


def test_a_switch_describes_itself():
    assert driver().switch_desc(1) == {"ok": True, "error": "", "dpid": 1, "desc": {
        "mfr_desc": "Example Manufacturer", "hw_desc": "Example Switch", "sw_desc": "0.0.0",
        "serial_num": "None", "dp_desc": "s1"}}


def test_the_flow_table_in_the_one_shape():
    out = driver().flows(1)
    assert out["ok"] and out["dpid"] == 1
    assert out["flows"] == [
        flow(actions=[{"type": "OUTPUT", "port": "CONTROLLER"}],
             packet_count=41, byte_count=4466, duration_sec=912),
        flow(priority=1, match={"in_port": 1, "eth_dst": "00:00:00:00:00:02",
                                "eth_src": "00:00:00:00:00:01"},
             actions=[{"type": "OUTPUT", "port": 2}],
             packet_count=12, byte_count=1036, duration_sec=874),
        flow(priority=2, idle_timeout=30,
             match={"in_port": 1, "eth_type": 2048, "ip_proto": 6, "ipv4_src": "192.0.2.1",
                    "ipv4_dst": "192.0.2.2", "tcp_dst": 22},
             actions=[{"type": "OUTPUT", "port": 2}],
             packet_count=2, byte_count=132, duration_sec=3),
        flow(priority=2, idle_timeout=30,
             match={"in_port": 2, "eth_type": 2048, "ip_proto": 17, "ipv4_src": "192.0.2.2",
                    "ipv4_dst": "192.0.2.3", "udp_dst": 53},
             actions=[{"type": "OUTPUT", "port": 3}],
             packet_count=1, byte_count=74, duration_sec=5),
        flow(priority=2, idle_timeout=30,
             match={"in_port": 1, "eth_type": 34525, "ip_proto": 6, "tcp_dst": 443,
                    "ipv6_src": "2001:db8::1", "ipv6_dst": "2001:db8::2"},
             actions=[{"type": "OUTPUT", "port": 3}],
             packet_count=3, byte_count=258, duration_sec=7),
        flow(priority=100, cookie=MERCURY_1, hard_timeout=300,
             match={"eth_type": 2048, "ipv4_src": "192.0.2.0/255.255.255.0"}, actions=[],
             packet_count=980, byte_count=58800, duration_sec=40),
        flow(priority=90, cookie=MERCURY_2, hard_timeout=300,
             match={"in_port": 3, "eth_type": 2048, "ipv4_src": "192.0.2.3"},
             actions=[{"type": "METER", "meter_id": 1}, {"type": "OUTPUT", "port": 2}],
             packet_count=5000, byte_count=7500000, duration_sec=12),
        flow(priority=5, match={"in_port": 3, "eth_type": 2054},
             actions=[{"type": "WRITE_ACTIONS", "actions": [{"type": "OUTPUT", "port": 1}]},
                      {"type": "GOTO_TABLE", "table_id": 1}],
             packet_count=0, byte_count=0, duration_sec=60),
        flow(table_id=1, priority=1, match={"vlan_vid": 10},
             actions=[{"type": "SET_FIELD", "field": "eth_dst", "value": "00:00:00:00:00:03"},
                      {"type": "OUTPUT", "port": 3}],
             packet_count=0, byte_count=0, duration_sec=60),
    ]


def test_an_empty_flow_table():
    out = driver(Session(captured(fixture("flow_stats_empty.json")))).flows(1)
    assert out == {"ok": True, "error": "", "dpid": 1, "flows": []}


def test_no_meters_is_an_empty_list():
    session = Session(captured(fixture("meter_config_empty.json")),
                      captured(fixture("meter_stats_empty.json")))
    assert driver(session).meters(1) == {"ok": True, "error": "", "dpid": 1, "meters": []}


def test_port_counters_in_the_one_shape():
    out = driver().port_stats(1)
    counters = ("rx_packets", "tx_packets", "rx_bytes", "tx_bytes", "rx_dropped",
                "tx_dropped", "rx_errors", "tx_errors", "duration_sec")

    def port(no, *values):
        return dict(zip(("dpid", "port_no") + counters, (1, no) + values))
    assert out == {"ok": True, "error": "", "dpid": 1, "ports": [
        port(1, 120, 118, 9480, 9310, 0, 0, 0, 0, 912),
        port(2, 118, 121, 9320, 9500, 0, 0, 0, 0, 912),
        port(3, 40, 38, 3200, 3100, 0, 3, 0, 0, 912),
        port("LOCAL", 0, 0, 0, 0, 0, 0, 0, 0, 912)]}


def test_a_meter_joins_its_configuration_and_its_counters():
    assert driver().meters(1) == {"ok": True, "error": "", "dpid": 1, "meters": [{
        "dpid": 1, "meter_id": 1, "flags": ["KBPS", "BURST", "STATS"],
        "bands": [{"type": "DROP", "rate": 1000, "burst_size": 100, "prec_level": None,
                   "packet_band_count": 1200, "byte_band_count": 1800000}],
        "flow_count": 1, "packet_in_count": 5000, "byte_in_count": 7500000,
        "duration_sec": 12}]}


def test_a_meter_counted_but_not_configured_is_kept():
    config = Response(200, json.dumps({"1": []}))
    stats = Response(200, json.dumps({"1": [{"meter_id": 7, "flow_count": 0,
                                             "packet_in_count": 1, "byte_in_count": 2,
                                             "duration_sec": 3, "band_stats": []}]}))
    out = driver(Session(config, stats)).meters(1)
    assert out["meters"] == [{"dpid": 1, "meter_id": 7, "flags": [], "bands": [],
                              "flow_count": 0, "packet_in_count": 1, "byte_in_count": 2,
                              "duration_sec": 3}]


def test_meter_features():
    assert driver().meter_features(1) == {"ok": True, "error": "", "dpid": 1, "features": {
        "dpid": 1, "max_meter": 200, "band_types": ["DROP", "DSCP_REMARK"],
        "capabilities": ["KBPS", "PKTPS", "BURST", "STATS"], "max_bands": 1, "max_color": 0}}
    none = Response(200, json.dumps({"1": []}))
    assert driver(Session(none)).meter_features(1)["features"] is None


@pytest.mark.parametrize("url,sent", [
    ("http://192.0.2.10:8080", "http://192.0.2.10:8080/stats/flow/1"),
    ("http://[2001:db8::10]:8080", "http://[2001:db8::10]:8080/stats/flow/1"),
])
def test_an_ipv4_and_an_ipv6_controller_are_read_alike(url, sent):
    session = Routes(WITH_PEER, url)
    out = driver(session, url=url).flows(1)
    assert out["ok"] and len(out["flows"]) == 9 and session.sent[0]["url"] == sent


# ───────────────────────────────────────────────────────────────────────────── failures

def test_a_switch_that_is_not_there_is_named():
    entry = one(NO_SWITCH, "GET", "/stats/flow/1")
    out = driver(Session(captured(entry))).flows(1)
    assert out == {"ok": False, "status": 404, "no_switch": True,
                   "error": "HTTP 404: the controller has no switch 1 (0000000000000001)"}


def test_a_malformed_request_is_said():
    entry = one(NO_SWITCH, "GET", "/stats/flow/abc")
    out = driver(Session(captured(entry))).port_stats(1)
    assert out == {"ok": False, "status": 400,
                   "error": "HTTP 400: the controller refused the request as malformed"}


def test_topology_is_not_served_by_ofctl_rest():
    """The capture: `GET /v1.0/topology/links` is Ryu's HTML 404 without rest_topology, so
    the driver declares no read_topology; and a call the controller does not serve is named."""
    entry = one(NO_SWITCH, "GET", "/v1.0/topology/links")
    assert entry["status"] == 404 and "<html>" in entry["body"]
    out = driver(Session(captured(entry))).switches()
    assert out == {"ok": False, "status": 404, "error": (
        "HTTP 404: the controller has no call /stats/switches (is the application serving "
        "it loaded?)")}


def test_a_500_says_the_tracebacks_last_line():
    entry = one(WITH_PEER, "POST", "/stats/flowentry/add",
                '{"dpid": 1, "priority": 1, "match": {}, "actions": [], "x": true}')
    out = driver(Session(captured(entry))).flows(1)
    assert out["ok"] is False and out["status"] == 500 and out["error"] == "HTTP 500"
    assert out["detail"].startswith("ValueError: malformed node or string: <ast.Name object")


def test_an_answer_for_another_switch_is_refused():
    out = driver(Session(Response(200, json.dumps({"2": []})))).flows(1)
    assert out == {"ok": False, "error": "the controller answered /stats/flow/1 for ['2'], "
                                         "not switch 1"}


def test_a_200_that_is_not_json_is_said():
    out = driver(Session(Response(200, "<html>proxy</html>", "text/html"))).flows(1)
    assert out == {"ok": False, "status": 200,
                   "error": "HTTP 200 from /stats/flow/1 with a body that is not JSON"}


def test_a_switch_list_that_is_not_one_is_said():
    out = driver(Session(Response(200, json.dumps({"1": "x"})))).switches()
    assert out["error"] == "the controller's switch list is not a list of datapath ids"


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_credential_is_named_as_such(status):
    out = driver(Session(Response(status, ""))).flows(1)
    assert out == {"ok": False, "status": status, "refused": True,
                   "error": f"HTTP {status}: the controller refused the tool's credential"}


def test_an_unsupported_openflow_request_is_said():
    out = driver(Session(Response(501, "", "text/html"))).meters(1)
    assert out["error"] == ("HTTP 501: the switch's OpenFlow version does not support this "
                            "request")


# ───────────────────────────────────────────────────────────────────────────── writes

WRITES = [  # (call, spec, path, the peer log's message index)
    ("add_meter", METER, R.METER_ADD, 1),
    ("add_flow", DROP, R.FLOW_ADD, 2),
    ("add_flow", LIMIT, R.FLOW_ADD, 3),
    ("add_flow", V6_DROP, R.FLOW_ADD, 4),
    ("delete_flow_strict", DROP, R.FLOW_DELETE_STRICT, 5),
    ("delete_meter", {"meter_id": 1}, R.METER_DELETE, 6),
]


@pytest.mark.parametrize("call,spec,path,_index", WRITES)
def test_each_render_is_the_body_ryu_accepted(call, spec, path, _index):
    rendered = getattr(driver(Session()), f"render_{call}")(1, spec)
    assert rendered["ok"] and (rendered["method"], rendered["path"]) == ("POST", path)
    entry = one(WITH_PEER, "POST", path, rendered["body"])
    assert entry["status"] == 200 and entry["body"] == ""


def _oxm(message):
    return {f["OXMTlv"]["field"]: (f["OXMTlv"]["value"] if f["OXMTlv"]["mask"] is None
                                   else (f["OXMTlv"]["value"], f["OXMTlv"]["mask"]))
            for f in message["match"]["OFPMatch"]["oxm_fields"]}


def test_what_reached_the_switch_is_what_each_spec_meant():
    """peer_log.json: index 0 is the application's own table-miss on connect."""
    meter_add, drop, limit, v6, delete, meter_delete = [m for m in PEER_LOG[1:]]
    assert meter_add == {"OFPMeterMod": {"command": 0, "flags": 13, "meter_id": 1,
                                         "bands": [{"type": 1, "rate": 1000,
                                                    "burst_size": 100}]}}
    drop = drop["OFPFlowMod"]
    assert (drop["command"], drop["priority"], drop["cookie"], drop["hard_timeout"],
            drop["instructions"]) == (0, 100, MERCURY_1, 300, [])
    assert _oxm(drop) == {"eth_type": 2048, "ipv4_src": ("192.0.2.0", "255.255.255.0")}
    limit = limit["OFPFlowMod"]
    assert _oxm(limit) == {"in_port": 3, "eth_type": 2048, "ipv4_src": "192.0.2.3"}
    assert limit["instructions"][0] == {"OFPInstructionMeter": {"len": 8, "meter_id": 1,
                                                                "type": 6}}
    assert limit["instructions"][1]["OFPInstructionActions"]["actions"][0][
        "OFPActionOutput"]["port"] == 2
    v6 = v6["OFPFlowMod"]
    assert _oxm(v6) == {"eth_type": 0x86DD, "ip_proto": 6, "tcp_dst": 22,
                        "ipv6_src": "2001:db8::1"}
    assert v6["instructions"] == [] and v6["cookie"] == MERCURY_3
    delete = delete["OFPFlowMod"]
    assert (delete["command"], delete["priority"], delete["cookie"],
            delete["cookie_mask"]) == (4, 100, MERCURY_1, UINT64_MAX)
    assert _oxm(delete) == _oxm(drop)
    assert meter_delete == {"OFPMeterMod": {"command": 2, "flags": 0, "meter_id": 1,
                                            "bands": []}}


@pytest.mark.parametrize("call,spec,path,_index", WRITES)
def test_a_write_says_sent_not_installed(call, spec, path, _index):
    out = getattr(driver(), call)(1, spec)
    assert out["ok"] and out["sent"] is True and out["status"] == 200
    assert out["note"] == R.SENT_NOTE and "read the table back to verify" in out["note"]


def test_a_write_to_a_switch_that_is_not_there_names_it():
    out = driver().add_flow(99, DROP)
    assert out["ok"] is False and out["no_switch"] is True
    assert out["error"] == "HTTP 404: the controller has no switch 99 (0000000000000063)"


def test_json_true_fails_ryus_parser_so_no_render_carries_one():
    entry = one(NO_SWITCH, "POST", "/stats/flowentry/add", '{"dpid": 1, "x": true}')
    assert entry["status"] == 500 and "ast.literal_eval" in entry["body"]
    for call, spec, _path, _i in WRITES:
        body = getattr(driver(Session()), f"render_{call}")(1, spec)["body"]
        assert ast.literal_eval(body) == json.loads(body)
        assert not {"true", "false", "null"} & set(body.replace('"', " ").split())
    refused = driver(Session()).render_add_flow(1, dict(DROP, match={"in_port": True}))
    assert refused["ok"] is False


def test_a_body_that_would_read_differently_to_ryu_is_refused(monkeypatch):
    planted = SimpleNamespace(dumps=lambda value, **kw: '{"dpid": 1, "x": true}',
                              loads=json.loads)
    monkeypatch.setattr(R, "json", planted)
    out = driver(Session()).render_add_flow(1, DROP)
    assert out == {"ok": False, "error": "the request would not read the same to Ryu's parser"}


def test_a_dscp_remark_band_carries_its_level():
    spec = {"meter_id": 2, "flags": ["PKTPS"],
            "bands": [{"type": "DSCP_REMARK", "rate": 100, "prec_level": 1}]}
    body = json.loads(driver(Session()).render_add_meter(1, spec)["body"])
    assert body == {"dpid": 1, "meter_id": 2, "flags": ["PKTPS"], "bands": [
        {"type": "DSCP_REMARK", "rate": 100, "burst_size": 0, "prec_level": 1}]}


# ───────────────────────────────────────────────────────────────────────────── round trip

def test_every_flow_read_renders_back_unchanged():
    flows = driver().flows(1)["flows"]
    for read in flows:
        spec = {k: read[k] for k in ("table_id", "priority", "cookie", "match", "actions",
                                     "idle_timeout", "hard_timeout")}
        body = json.loads(driver(Session()).render_add_flow(1, spec)["body"])
        assert (body["match"], body["actions"]) == (read["match"], read["actions"])


@pytest.mark.parametrize("text,action", [
    ("OUTPUT:2", {"type": "OUTPUT", "port": 2}),
    ("OUTPUT:CONTROLLER", {"type": "OUTPUT", "port": "CONTROLLER"}),
    ("DROP", None),
    ("CLEAR_ACTIONS", {"type": "CLEAR_ACTIONS"}),
    ("POP_VLAN", {"type": "POP_VLAN"}),
    ("PUSH_VLAN:33024", {"type": "PUSH_VLAN", "ethertype": 33024}),
    ("SET_QUEUE:3", {"type": "SET_QUEUE", "queue_id": 3}),
    ("GROUP:4", {"type": "GROUP", "group_id": 4}),
    ("WRITE_METADATA:0x1/0xff", {"type": "WRITE_METADATA", "metadata": 1,
                                 "metadata_mask": 255}),
    ("WRITE_METADATA:0x5", {"type": "WRITE_METADATA", "metadata": 5, "metadata_mask": 0}),
    ("SET_FIELD: {vlan_vid:4106}", {"type": "SET_FIELD", "field": "vlan_vid",
                                    "value": 4106}),
    ("SET_FIELD: {ipv6_dst:2001:db8::2}", {"type": "SET_FIELD", "field": "ipv6_dst",
                                           "value": "2001:db8::2"}),
    ("EXPERIMENTER: {experimenter:8992, data:AA==}",
     {"type": "UNPARSED", "text": "EXPERIMENTER: {experimenter:8992, data:AA==}"}),
    ("UNKNOWN", {"type": "UNPARSED", "text": "UNKNOWN"}),
    ("OUTPUT:", {"type": "UNPARSED", "text": "OUTPUT:"}),
    ({"APPLY": []}, {"type": "UNPARSED", "text": '{"APPLY": []}'}),
])
def test_each_of_ryus_action_strings(text, action):
    assert R.action_from_ryu(text) == action


def test_a_flow_with_an_unparsed_action_is_read_but_never_sent():
    answer = Response(200, json.dumps({"1": [{"priority": 1, "cookie": 0, "table_id": 0,
                                              "idle_timeout": 0, "hard_timeout": 0,
                                              "packet_count": 0, "byte_count": 0,
                                              "duration_sec": 0, "match": {"tp_dst": 9},
                                              "actions": ["UNKNOWN"]}]}))
    (read,) = driver(Session(answer)).flows(1)["flows"]
    assert read["match"] == {"tp_dst": 9}
    assert read["actions"] == [{"type": "UNPARSED", "text": "UNKNOWN"}]
    spec = {k: read[k] for k in ("priority", "match", "actions")}
    out = driver(Session()).render_add_flow(1, spec)
    assert out["ok"] is False
    assert "'tp_dst' is not an OpenFlow 1.3 OXM field name" in out["error"]
    assert "(read back as the controller's 'UNKNOWN')" in out["error"]
