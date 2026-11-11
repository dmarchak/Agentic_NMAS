"""Topology from an SDN controller (PHASE8_PLAN 17.1 S14, C1910), no network.

The controller's answers are REAL: Ryu 4.34's topology REST on the NMAS host, read 2026-10-27
~09:35 UTC with a Mininet fabric attached (tests/fixtures/sdn/ryu/topology_rest.json: two
switches, their one link in both directions, six hosts, IPv4 and IPv6, two of them left from
earlier runs, as Ryu keeps them); the topology REST's 404 without the application
(rest_no_switch.json); and the LLDP frame Ryu's link discovery sends, rendered by Ryu's own code
(lldp_from_ryu.json). README.md beside them says how each was made. Every expected value below
is read off those files by hand, a path independent of the parse.

- **The driver:** Ryu declares read_topology; `topology()` parses switches, ports, links and
  hosts whole (the unspecified `::` dropped, IPv6 kept beside IPv4); a 404 is "the topology app
  is not running", never no links; every host answer carries what a listing means.
- **The SDN reader** keeps a topology that cannot be read as last read, with its time.
- **The layer:** switches keyed by DPID, "discovered via controller"; one link for the two
  directions, naming its source; the coverage words for read, couldn't read (with age) and an
  empty link list between switches; a store older than its promise is not read now.
- **Hybrid links:** a managed device's LLDP neighbour named by `dpid:<hex>` (Ryu's chassis id)
  is ONE link to that switch's port (Ryu's four-byte port id), both sources named; a MAC chassis
  id joins nothing; a DPID no controller reports is a node seen only by LLDP.
- **The network model:** the coverage header's controller layer, present, partial with why, not
  collected; the controller's links are cables naming their sources.
- **Endpoints:** the controller's hosts located on their switch port, found by IPv4, IPv6 or
  MAC; a device's MAC table, read now, wins; a host on a switch-to-switch port locates nothing.
- **The Topology view:** the SDN symbol and colour, each link's source on hover, in the lists
  and on the map, the strip naming each source, the legend; a network with no controller draws
  as before.
"""
import calendar
import os
import re
import time

import pytest

from modules import endpoints as E
from modules import network_model as NM
from modules.readers import sdn_controllers as R
from modules.readers import topology_graph as T
from modules.sdn import topology as SDN
from modules.sdn.drivers.base import Connection
from modules.sdn.drivers.ryu import NO_TOPOLOGY_APP, RyuDriver
from tests.sdn_fakes import Routes, Session, captured, fixture

BASE = "http://127.0.0.1:8080"
TOPO = fixture("topology_rest.json")
NO_APP = fixture("rest_no_switch.json")
LLDP = fixture("lldp_from_ryu.json")
READ_AT = "2026-10-27T09:35:49Z"
READ_EPOCH = float(calendar.timegm(time.strptime(READ_AT, "%Y-%m-%dT%H:%M:%SZ")))


def _driver(entries=TOPO):
    return RyuDriver(Connection(BASE), session=Routes(entries, BASE))


def _topology():
    got = _driver().topology()
    assert got["ok"], got
    return got


def _controller(state="read", topo=None, name="c1", read_at=READ_AT, why=""):
    t = topo or _topology()
    return {"name": name, "label": "Ryu", "state": state, "why": why, "read_at": read_at,
            "switches": t["switches"], "links": t["links"], "hosts": t["hosts"],
            "hosts_note": t["hosts_note"], "links_note": t.get("links_note", ""), "names": {}}


# ───────────────────────────────────────────────────────────────────────────── the driver

def test_ryu_declares_read_topology_now_that_the_lab_runs_the_app():
    assert "read_topology" in RyuDriver.capabilities and "read_topology" not in RyuDriver.absent


def test_the_captured_switches_and_their_ports():
    t = _topology()
    assert [s["dpid"] for s in t["switches"]] == [1, 2]
    s1 = t["switches"][0]
    assert s1["dpid_hex"] == "0000000000000001"
    assert [(p["port_no"], p["name"], p["hw_addr"]) for p in s1["ports"]] == [
        (1, "s1-eth1", "1e:8a:d1:09:f1:bd"), (2, "s1-eth2", "1e:e4:3a:59:67:11"),
        (3, "s1-eth3", "82:c3:07:17:32:b7")]


def test_the_captured_link_is_reported_in_both_directions():
    links = _topology()["links"]
    ends = [((l["src"]["dpid"], l["src"]["port_no"]), (l["dst"]["dpid"], l["dst"]["port_no"]))
            for l in links]
    assert ends == [((2, 3), (1, 3)), ((1, 3), (2, 3))]


def test_the_captured_hosts_with_ipv4_beside_ipv6_and_no_unspecified_address():
    hosts = {h["mac"]: h for h in _topology()["hosts"]}
    assert len(hosts) == 6
    h2 = hosts["00:00:00:00:00:02"]
    assert (h2["dpid"], h2["port_no"], h2["port_name"]) == (1, 2, "s1-eth2")
    assert h2["ipv4"] == ["192.0.2.2"]
    assert h2["ipv6"] == ["2001:db8:8::2", "fe80::200:ff:fe00:2"], "the '::' is dropped"
    left = hosts["12:da:aa:70:da:9f"]
    assert left["ipv4"] == [] and left["ipv6"] == ["fe80::10da:aaff:fe70:da9f"]
    assert all("::" not in h["ipv6"] and "0.0.0.0" not in h["ipv4"] for h in hosts.values())


def test_every_host_answer_says_what_a_listing_means():
    got = _driver().hosts()
    assert got["ok"] and "records no time" in got["hosts_note"]


def test_a_controller_without_the_topology_app_is_said_never_as_no_links():
    entry = next(e for e in NO_APP if e["path"] == "/v1.0/topology/links")
    assert entry["status"] == 404 and "<html>" in entry["body"]
    for call in ("links", "hosts", "topology"):
        drv = RyuDriver(Connection(BASE), session=Session(captured(entry)))
        out = getattr(drv, call)()
        assert out["ok"] is False and out.get("no_topology_app") is True, (call, out)
        assert NO_TOPOLOGY_APP in out["error"] and "links" not in out, out
    assert NO_TOPOLOGY_APP == ("the topology app is not running (start ryu-manager with "
                               "--observe-links and ryu.app.rest_topology)")


# ───────────────────────────────────────────────────────────────────────────── Ryu's own LLDP

def test_ryu_s_chassis_id_names_its_dpid_and_a_mac_names_none():
    for frame in LLDP["frames"]:
        assert frame["chassis_id_subtype"] == 7 and frame["tlv_types"] == [1, 2, 3, 0], \
            "locally assigned; no system name TLV, so a neighbour's table has no name for it"
        assert SDN.chassis_dpid(frame["chassis_id"]) == frame["dpid"]
    assert SDN.chassis_dpid("00:00:00:00:00:01") is None
    assert SDN.chassis_dpid("r2.example.com") is None
    # The prefix is the driver's declaration, never this module's: with none declared, none.
    assert RyuDriver.lldp_chassis_prefix == "dpid:"
    assert SDN.chassis_dpid(LLDP["frames"][0]["chassis_id"], prefixes=()) is None


def test_ryu_s_port_id_reads_as_its_port_number_in_every_form():
    for frame in LLDP["frames"]:
        raw = bytes.fromhex(frame["port_id_hex"]).decode("latin-1")
        assert frame["port_id_subtype"] == 2
        for form in (raw, frame["port_id_hex"], "0x" + frame["port_id_hex"],
                     " ".join(frame["port_id_hex"][i:i + 2] for i in range(0, 8, 2))):
            assert SDN.lldp_port_no(form) == frame["port_no"], form
    assert SDN.lldp_port_no("Gi1/0") is None
    assert SDN.lldp_port_no("00000010") == 16, "eight hex digits are the four bytes, never decimal"


# ───────────────────────────────────────────────────────────────────────────── the SDN reader

class _Drv:
    def __init__(self, answer):
        self.answer = answer

    def topology(self):
        return self.answer


def test_the_reader_stores_the_topology_with_its_time():
    got = R._topology(_Drv(_topology()), {"capabilities": ["read_topology"]}, {}, READ_AT)
    assert got["state"] == "read" and got["read_at"] == READ_AT
    assert len(got["switches"]) == 2 and len(got["hosts"]) == 6


def test_a_topology_that_cannot_be_read_keeps_its_last_read_with_that_read_s_time():
    before = R._topology(_Drv(_topology()), {"capabilities": ["read_topology"]}, {}, READ_AT)
    failed = {"ok": False, "error": f"HTTP 404 from /v1.0/topology/switches: {NO_TOPOLOGY_APP}"}
    got = R._topology(_Drv(failed), {"capabilities": ["read_topology"]}, before,
                      "2026-10-27T09:40:00Z")
    assert got["state"] == "could not read" and NO_TOPOLOGY_APP in got["error"]
    assert got["read_at"] == READ_AT and got["switches"] == before["switches"]
    assert got["links"] == before["links"] and got["hosts"] == before["hosts"]


def test_a_driver_without_read_topology_is_said_and_asked_nothing():
    got = R._topology(None, {"capabilities": ["read_flows"], "absent": {
        "read_topology": "no links call"}}, {}, READ_AT)
    assert got["state"] == "not_declared" and "no links call" in got["error"]


# ───────────────────────────────────────────────────────────────────────────── the stored read

def _cached(controllers, value_at=READ_AT):
    return {"state": "ok", "doc": {"last_good": {"value_at": value_at, "value": {
        "network": "Lab", "state": "ok", "controllers": controllers}}}}


def _stored_controller(topo_state="read", error=""):
    t = R._topology(_Drv(_topology()), {"capabilities": ["read_topology"]}, {}, READ_AT)
    if topo_state != "read":
        t = R._topology_kept(t, error)
    return {"name": "c1", "label": "Ryu", "state": "connected",
            "switches": [{"dpid": 1, "name": "edge-a"}, {"dpid": 2, "name": ""}],
            "topology": t}


def test_the_stored_read_is_the_reader_s_value_while_current():
    got = SDN.stored("Lab", now=READ_EPOCH + 30, cached=_cached([_stored_controller()]))
    (c,) = got["controllers"]
    assert got["state"] == "read" and c["state"] == "read" and c["names"] == {1: "edge-a"}


def test_a_stored_read_older_than_its_promise_is_not_read_now():
    from modules import reader_job
    promise = reader_job.page_promise(R.READER)
    got = SDN.stored("Lab", now=READ_EPOCH + promise + 1,
                     cached=_cached([_stored_controller()]))
    (c,) = got["controllers"]
    assert c["state"] == "could not read" and f"older than its promise of {promise} s" in c["why"]
    assert len(c["switches"]) == 2, "kept as last read"


def test_a_network_with_no_controller_is_none():
    got = SDN.stored("Lab", cached={"state": "not_configured", "why": "not configured"})
    assert got == {"state": "none", "why": "not configured", "controllers": []}


# ───────────────────────────────────────────────────────────────────────────── the layer

def test_switches_are_keyed_by_dpid_and_one_link_carries_both_directions():
    lay = SDN.layer([_controller()])
    assert sorted(lay["nodes"]) == ["of:0000000000000001", "of:0000000000000002"]
    node = lay["nodes"]["of:0000000000000001"]
    assert node["managed"] is False and node["sdn"]["controller"] == "c1"
    assert node["sdn"]["ports"] == 3
    (link,) = lay["links"]
    assert (link["a"], link["port_a"], link["b"], link["port_b"]) == (
        "of:0000000000000001", "port 3", "of:0000000000000002", "port 3")
    assert link["sources"] == ["controller (c1)"] and link["directions"] == 2
    assert link["state"] == "up"


def test_a_controller_not_read_now_keeps_its_links_as_unknown_never_up():
    lay = SDN.layer([_controller(state="could not read", why="no answer within 5 s")])
    (link,) = lay["links"]
    assert link["state"] == "unknown"
    assert all(not n["answering"] for n in lay["nodes"].values())


def test_the_coverage_words_for_read_couldn_t_read_and_no_links():
    (read,) = SDN.said([_controller()])
    assert SDN.words(read) == (f"controller (c1) · read {READ_AT} · 2 switches, 1 link, "
                               "6 hosts")
    (unread,) = SDN.said([_controller(state="could not read", why="no answer within 5 s")])
    said = SDN.words(unread, now=READ_EPOCH + 3 * 3600)
    assert said.startswith("controller (c1): couldn't read: no answer within 5 s; its "
                           f"switches as last read at {READ_AT} (3 h ago)")
    bare = dict(_topology(), links=[])
    (empty,) = SDN.said([_controller(topo=bare)])
    assert "no link reported between its 2 switches" in SDN.words(empty)
    assert "--observe-links" in SDN.words(empty)


# ───────────────────────────────────────────────────────────────────────────── hybrid links

def _r6_facing(chassis, port_id):
    """r6's LLDP rows as the Topology reader's fetch builds them: the shape of the captured
    lldpRemPortId row (tests/fixtures/topology/lldpRemPortId.json, r1's), on r6's Gi2, the
    chassis id and port id as Ryu's own frame carries them (lldp_from_ryu.json). The lab's
    LLDP module does not scrape lldpRemChassisId yet, so no capture of it exists."""
    labels = {"device": "r6", "instance": "192.0.2.16", "job": "lldp", "lldpLocPortNum": "2",
              "lldpRemIndex": "1", "lldpRemTimeMark": "0", "role": "router"}
    value = [1793093749.0, "1"]
    return {"lldpLocPortDesc": [{"metric": dict(labels, __name__="lldpLocPortDesc",
                                                lldpLocPortDesc="Gi2"), "value": value}],
            "lldpRemChassisId": [{"metric": dict(labels, __name__="lldpRemChassisId",
                                                 lldpRemChassisId=chassis), "value": value}],
            "lldpRemPortId": [{"metric": dict(labels, __name__="lldpRemPortId",
                                              lldpRemPortId=port_id), "value": value}]}


def _graph(sdn, extra=None):
    from tests.test_topology_graph import MANAGED, _capture, _intents
    res, up = _capture()
    for dev, metrics in (extra or {}).items():
        res.setdefault(dev, {}).update(metrics)
    return T.network_graph(MANAGED, {}, _intents(), res, up, sdn=sdn)


def test_a_router_s_lldp_neighbour_named_by_a_dpid_is_one_link_with_both_sources():
    frame = LLDP["frames"][0]                    # dpid 1, port 3, as Ryu sends it
    raw = bytes.fromhex(frame["port_id_hex"]).decode("latin-1")
    g = _graph({"state": "read", "controllers": [_controller()]},
               {"r6": _r6_facing(frame["chassis_id"], raw)})
    hybrid = [l for l in g["layers"]["physical"] if l.get("kind") == "hybrid"]
    (l,) = hybrid
    assert (l["a"], l["port_a"], l["b"], l["port_b"]) == ("of:0000000000000001", "port 3",
                                                          "r6", "Gi2")
    assert l["sources"] == ["LLDP (r6)", "controller (c1)"]
    assert l["chassis"] == "dpid:0000000000000001"


def test_a_mac_chassis_id_joins_nothing_and_an_unknown_dpid_is_seen_only_by_lldp():
    g = _graph({"state": "read", "controllers": [_controller()]},
               {"r6": _r6_facing("00:00:00:00:00:01", "Gi0/1")})
    assert not [l for l in g["layers"]["physical"] if l.get("kind") == "hybrid"]
    frame = LLDP["frames"][1]                    # a DPID no controller of this network reports
    g = _graph({"state": "read", "controllers": [_controller()]},
               {"r6": _r6_facing(frame["chassis_id"], frame["port_id_hex"])})
    (l,) = [l for l in g["layers"]["physical"] if l.get("kind") == "hybrid"]
    assert l["sources"] == ["LLDP (r6)"] and l["port_a"] == "port 65534"
    node = g["nodes"]["of:0123456789abcdef"]
    assert node["outside"] and "no controller of this network reports it" in node["sdn"]["why"]


def test_the_graph_holds_switches_hosts_and_the_controller_outside_every_analysis():
    g = _graph({"state": "read", "controllers": [_controller()]})
    nodes = g["nodes"]
    assert nodes["of:0000000000000002"]["sdn"]["dpid"] == 2
    assert nodes["ctl:c1"]["overlay"] and nodes["host:00:00:00:00:00:04@0000000000000002/2"]["overlay"]
    an = g["analysis"]["physical"]
    named = {d for i in an["islands"] for d in i} | {s["device"] for s in an["spof"]} | \
        set(an["main"])
    assert not any(n.startswith(("host:", "ctl:")) for n in named), named
    assert g["sdn"]["controllers"][0]["switches"] == 2 and g["sdn"]["hosts_drawn"]


def test_a_network_with_no_controller_graphs_as_before():
    from tests.test_topology_graph import _graph as plain
    assert _graph({"state": "none", "why": "", "controllers": []}) == plain()


def test_the_announcement_ignores_the_controller_s_read_time():
    a = {"networks": {"Lab": _graph({"state": "read", "controllers": [_controller()]})}}
    b = {"networks": {"Lab": _graph({"state": "read", "controllers": [
        _controller(read_at="2026-10-27T09:36:19Z")]})}}
    assert not T.changed(a, b)
    c = {"networks": {"Lab": _graph({"state": "read", "controllers": [
        _controller(state="could not read", why="no answer")]})}}
    assert T.changed(a, c)


# ───────────────────────────────────────────────────────────────────────────── the model

def test_the_coverage_header_lists_the_controller_layer():
    sdn = {"state": "read", "controllers": SDN.said([_controller()])}
    cov = NM.controller_coverage({"state": "read", "controllers": sdn})
    assert cov["state"] == "present" and cov["age"] == READ_AT
    assert cov["source"].startswith("controller (c1) · read") and cov["why"] == ""
    sdn = {"state": "read", "controllers": SDN.said(
        [_controller(), _controller(name="c2", state="could not read", why="HTTP 503")])}
    cov = NM.controller_coverage({"state": "read", "controllers": sdn})
    assert cov["state"] == "partial" and "controller (c2): couldn't read: HTTP 503" in cov["why"]
    assert NM.controller_coverage({"state": "read"})["why"] == \
        "this network has no SDN controller connection"
    assert NM.controller_coverage({"state": "could not read", "why": "absent"})["state"] == \
        "not_collected"
    assert "controller" in NM.LAYERS


# ───────────────────────────────────────────────────────────────────────────── endpoints

def test_controller_hosts_are_located_on_their_switch_port_and_found_by_any_address():
    hosts = SDN.endpoint_hosts([_controller()])
    located = E.locate({}, [], {}, now=READ_EPOCH, controller=hosts)["endpoints"]
    (h1,) = E.find(located, "192.0.2.1")
    assert (h1["device"], h1["interface"]) == ("of:0000000000000001", "port 1")
    assert h1["last_seen"] == READ_AT and h1["sources"] == ["controller (c1)'s host table"]
    assert E.find(located, "2001:db8:8::1") == [h1], "IPv6 beside IPv4"
    assert E.find(located, "00-00-00-00-00-01") == [h1]
    assert "as its controller lists it" in E.seen(h1, now=READ_EPOCH)["said"]


def test_a_device_s_mac_table_read_now_wins_over_a_controller_listing():
    hosts = SDN.endpoint_hosts([_controller()])
    reads = {"edge1": {"mac_table": [{"mac": "00:00:00:00:00:01", "port": "Gi1/0",
                                      "vlan": "10"}]}}
    (e,) = E.find(E.locate(reads, [], {}, now=READ_EPOCH + 60, controller=hosts)["endpoints"],
                  "00:00:00:00:00:01")
    assert e["device"] == "edge1" and "192.0.2.1" in e["addresses"]


def test_a_host_on_a_switch_to_switch_port_locates_nothing():
    t = _topology()
    t["hosts"] = t["hosts"] + [dict(t["hosts"][0], mac="02:00:00:00:00:99", port_no=3)]
    macs = {h["mac"] for h in SDN.endpoint_hosts([_controller(topo=t)])}
    assert "02:00:00:00:00:99" not in macs and "00:00:00:00:00:02" in macs


def test_a_switch_s_hosts_carry_forward_while_its_controller_reports_it():
    hosts = SDN.endpoint_hosts([_controller()])
    first = E.locate({}, [], {}, now=READ_EPOCH, controller=hosts)["endpoints"]
    later = E.locate({}, [], {}, previous=first, now=READ_EPOCH + 600,
                     controller=hosts[1:])["endpoints"]
    assert {e["mac"] for e in later} == {e["mac"] for e in first}


# ───────────────────────────────────────────────────────────────────────────── the view

@pytest.fixture
def web(tmp_path, monkeypatch):
    from tests.test_topology_v2 import _store, _value
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.topology_expected._path",
                        lambda name: str(tmp_path / "lab" / "topology_expected.json"))
    frame = LLDP["frames"][0]
    raw = bytes.fromhex(frame["port_id_hex"]).decode("latin-1")
    from tests.test_topology_graph import _capture
    res, up = _capture()
    res.setdefault("r6", {}).update(_r6_facing(frame["chassis_id"], raw))
    value = _value(results=res, up=up)
    from tests.test_topology_graph import MANAGED, _intents
    intents = {h: hv for h, hv in _intents().items() if h != "r5"}
    value["networks"]["Lab"] = T.network_graph(
        MANAGED, {h: ("router" if h.startswith("r") else "switch") for h in MANAGED}, intents,
        res, up, now="2026-10-10T19:00:00Z", at_here=[],
        sdn={"state": "read", "controllers": [_controller()]})
    _store(value)
    import app as A
    from modules import reader_job
    yield {"client": A.app.test_client()}
    os.remove(reader_job.store_path("topology-graph"))


def _map(web, query=""):
    return web["client"].get(f"/v2/topology/map?list=Lab{query}").get_data(as_text=True)


def test_the_view_draws_the_sdn_symbol_in_the_controller_s_colour(web):
    html = _map(web)
    assert '<symbol id="ti-sdn-switch"' in html and '<symbol id="ti-host"' in html
    assert html.count('href="#ti-sdn-switch"') >= 2
    assert re.search(r'class="topo-n topo-c-sdn[^"]*" data-node="of:0000000000000001"', html)
    assert re.search(r'<text class="topo-sdnline"[^>]*>of:…0001 · via controller</text>', html)
    assert "DPID 0000000000000001 · discovered via controller c1, read" in html


def test_each_link_says_its_source_on_hover_in_the_list_and_on_the_map(web):
    html = _map(web, "&labels=on")
    chips = re.findall(r'<text class="topo-st-t topo-st-src"[^>]*>([^<]*)</text>', html)
    assert "controller" in chips and "LLDP + controller" in chips and "LLDP" in chips
    assert re.search(r'class="topo-line topo-ok topo-src-ctl"', html)
    assert "one link, two sources: LLDP (r6) and controller (c1)" in html
    assert "<dt>Source</dt>" in html
    assert "port 3 to r6 up · LLDP + controller" in html or \
        re.search(r"to r6 [a-z]+ · LLDP \+ controller", html)


def test_the_strip_names_each_source_and_the_legend_both_symbols(web):
    html = _map(web)
    strip = re.search(r'<div class="topo-cov small".*?</div>', html, re.S).group(0)
    assert "LLDP · the Topology reader, read" in strip
    assert f"controller (c1) · read {READ_AT} · 2 switches, 1 link, 6 hosts" in strip
    legend = re.search(r'<div class="topo-legend small".*?</div>', html, re.S).group(0)
    assert "a switch a controller programs (OpenFlow)" in legend
    assert "a link the controller reports" in legend and "a host the controller learned" in legend


def test_a_network_with_no_controller_has_no_strip_and_no_source_chips(tmp_path, monkeypatch):
    from tests.test_topology_v2 import _store, _value
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.topology_expected._path",
                        lambda name: str(tmp_path / "lab" / "topology_expected.json"))
    _store(_value())
    import app as A
    from modules import reader_job
    try:
        html = A.app.test_client().get("/v2/topology/map?list=Lab&labels=on").get_data(
            as_text=True)
    finally:
        os.remove(reader_job.store_path("topology-graph"))
    assert 'class="topo-cov' not in html and "topo-st-src" not in html
    assert 'href="#ti-sdn-switch"' not in html and "<dt>Source</dt>" not in html


# ─────────────────────────────────────────────────────────── NetBox's names, one node a device
# C3010 and C1928 (the Lab 9 sitting, 2026-11-11): the captured fabric again (DPIDs 1 and 2,
# their link on port 3, h1 on DPID 1's port 1, h2 on its port 2, h3 and a host Ryu kept on
# DPID 2's port 1, h4 on its port 2), with NetBox's view of it in the committed export's own
# body shape (`modules/nsot/export.py`; a switch as tests/fixtures/nsot_export/lab9_records.json
# holds one: its custom field ``openflow_datapath_id``, each OpenFlow port tagged ``openflow``
# with its ``openflow_port``), read by the real `sdn.known.shaped`.

def _netbox(devices=("leaf-1", "leaf-2"), interfaces=(), hosts=(), cables=(), first=1):
    """NetBox's view: *devices* are switches, the first with datapath id *first*, the next
    one more."""
    from modules.sdn import known

    body = {"devices": [{"name": name, "id": n, "tags": [],
                         "custom_fields": {"openflow_datapath_id": f"{n:016x}"}}
                        for n, name in enumerate(devices, first)],
            "interfaces": [{"device": name, "name": f"Ethernet{p}", "tags": ["openflow"],
                            "custom_fields": {"openflow_port": p}, "ip_addresses": []}
                           for name in devices for p in (1, 2, 3)] + list(interfaces),
            "cables": list(cables), "hosts": list(hosts)}
    return known.shaped({"ok": True, "sha256": "ab" * 32, "error": "",
                         "export": {"sha256": "ab" * 32, "body": body}})


def _fabric(hosts, **kw):
    """The captured fabric's graph for a network managing *hosts*, nothing scraped."""
    return T.network_graph(list(hosts), {}, {}, {}, {},
                           sdn={"state": "read", "controllers": [_controller()]}, **kw)


def test_a_switch_netbox_names_is_its_managed_device_s_one_node():
    """The operator's kit: each switch is a managed NetBox device AND a DPID the controller
    reports. Matched by NetBox's ``openflow_datapath_id``, it is one node: the device's, with
    the switch's links, hosts and DPID; never a DPID node beside an "island"."""
    g = _fabric(["leaf-1", "leaf-2"], netbox=_netbox())
    nodes = g["nodes"]
    assert "of:0000000000000001" not in nodes and "of:0000000000000002" not in nodes
    one = nodes["leaf-1"]
    assert one["managed"] and one["sdn"]["dpid"] == 1 and one["sdn"]["controller"] == "c1"
    assert one["sdn"]["key"] == "of:0000000000000001" and one["answering"]
    (link,) = [l for l in g["layers"]["physical"] if l["kind"] == "controller"]
    assert {(link["a"], link["port_a"]), (link["b"], link["port_b"])} == {
        ("leaf-1", "port 3"), ("leaf-2", "port 3")}
    assert set(link["ends_detail"]) == {"leaf-1", "leaf-2"}
    assert sorted(l["b"] for l in g["layers"]["physical"] if l["kind"] == "control") == [
        "leaf-1", "leaf-2"]
    assert nodes["host:00:00:00:00:00:04@0000000000000002/2"]["host"]["switch"] == "leaf-2"
    assert {l["a"] for l in g["layers"]["physical"] if l["kind"] == "host"} == {"leaf-1",
                                                                                 "leaf-2"}
    an = g["analysis"]["physical"]
    assert an["islands"] == [] and an["not_scraped"] == [] and an["main"] == ["leaf-1", "leaf-2"]
    assert g["sdn"]["netbox"] == {"state": "read", "why": "", "sha": "abababababab",
                                  "merged": 2}
    # Without NetBox's view the two stay apart, as two nodes each; and a switch whose NetBox
    # device this network does not manage keeps its own node, named by NetBox.
    apart = _fabric(["leaf-1", "leaf-2"])
    assert {"of:0000000000000001", "leaf-1"} <= set(apart["nodes"])
    other = _fabric(["leaf-1"], netbox=_netbox())
    assert other["nodes"]["of:0000000000000002"]["sdn"]["label"] == "leaf-2"
    assert "leaf-2" not in other["nodes"] and other["sdn"]["netbox"]["merged"] == 1


def test_a_switch_is_drawn_by_its_netbox_name_and_never_by_a_placeholder():
    """DPID 1 describes itself as "None" (Open vSwitch's placeholder) and DPID 2 with a made-up
    label; NetBox names only DPID 2. The page draws DPID 2 by NetBox's name and DPID 1 by its
    DPID, never "None"."""
    from modules import topology_page as TP

    c = dict(_controller(), names={1: "None", 2: "made-up"})
    g = T.network_graph([], {}, {}, {}, {}, sdn={"state": "read", "controllers": [c]},
                        netbox=_netbox(devices=("leaf-2",), first=2))
    one, two = g["nodes"]["of:0000000000000001"], g["nodes"]["of:0000000000000002"]
    assert (one["sdn"]["label"], one["sdn"]["reported"], one["sdn"]["netbox"]) == ("", "None", "")
    assert (two["sdn"]["label"], two["sdn"]["reported"]) == ("leaf-2", "made-up")
    assert TP.label("of:0000000000000001", g["nodes"]) == "of:…0001"
    assert TP.label("of:0000000000000002", g["nodes"]) == "leaf-2"
    h4 = g["nodes"]["host:00:00:00:00:00:04@0000000000000002/2"]["host"]
    assert h4["switch_label"] == "leaf-2"
    # With no NetBox name, a description the switch does give is kept; "None" never is.
    plain = T.network_graph([], {}, {}, {}, {}, sdn={"state": "read", "controllers": [c]})
    assert plain["nodes"]["of:0000000000000002"]["sdn"]["label"] == "made-up"
    assert plain["nodes"]["of:0000000000000001"]["sdn"]["label"] == ""


def test_a_learnt_host_is_named_by_its_netbox_device():
    """h1's MAC is an end host's interface in NetBox; h4's port (leaf-2 Ethernet2) is where
    NetBox cables a device it records no MAC for, and h4 is the one host there; leaf-2
    Ethernet1 is cabled too, and holds two hosts, so its cable names neither."""
    view = _netbox(
        hosts=[{"name": "h1", "id": 9, "interfaces": [{
            "name": "eth0", "mac": "00:00:00:00:00:01",
            "ip_addresses": ["192.0.2.1/24", "2001:db8:8::1/64"], "attached": None}]}],
        cables=[{"a": [["leaf-2", "Ethernet2"]], "b": [["edge-rtr", "Gi0/0"]]},
                {"a": [["leaf-2", "Ethernet1"]], "b": [["other-rtr", "Gi0/1"]]}])
    nodes = _fabric([], netbox=view)["nodes"]

    def host(mac, at):
        return nodes[f"host:{mac}@{at}"]["host"]
    h1 = host("00:00:00:00:00:01", "0000000000000001/1")
    assert (h1["label"], h1["netbox"]) == ("h1", "h1 eth0, by its MAC")
    h4 = host("00:00:00:00:00:04", "0000000000000002/2")
    assert (h4["label"], h4["netbox"]) == (
        "edge-rtr", "edge-rtr Gi0/0, by its cable to leaf-2 Ethernet2")
    h3 = host("00:00:00:00:00:03", "0000000000000002/1")
    assert (h3["label"], h3["netbox"]) == ("192.0.2.3", ""), "two hosts on the port: no guess"
    h2 = host("00:00:00:00:00:02", "0000000000000001/2")
    assert (h2["label"], h2["netbox"]) == ("192.0.2.2", "")
    kept = host("12:da:aa:70:da:9f", "0000000000000001/1")
    assert kept["label"] == "host on leaf-1 port 1", "the switch by its NetBox name"
    from modules import topology_page as TP
    assert "NetBox: h1 eth0, by its MAC" in TP.host_lines(h1)


def test_a_device_no_target_scrapes_is_not_scraped_and_a_measured_island_stays_one():
    """The captured fleet (r6 measured apart: its LLDP is read and reaches nobody) and one more
    managed device no target scrapes at all: r6 stays the island; the other is "not scraped",
    listed apart, never an island, a weak point or a critical device."""
    from tests.test_topology_graph import MANAGED, _capture, _intents
    res, up = _capture()
    g = T.network_graph(MANAGED + ["zz-new"], {}, _intents(), res, up)
    an = g["analysis"]["physical"]
    assert an["islands"] == [["r6"]] and an["not_scraped"] == ["zz-new"]
    assert g["nodes"]["zz-new"]["not_scraped"] and "not_scraped" not in g["nodes"]["r6"]
    assert "zz-new" not in an["island_why"] and "zz-new" not in an["main"]
    assert "zz-new" not in {s["device"] for s in an["spof"]} | {
        c["device"] for c in an["critical"]}


def _ref():
    from modules.nsot.listref import ListRef
    nowhere = os.path.join(os.path.dirname(os.path.abspath(__file__)), "no-such-repo")
    return ListRef(name="Lab", slug="lab", data_dir=nowhere, repo_dir=nowhere,
                   csv_path=os.path.join(nowhere, "devices.csv"))


def test_with_no_prometheus_a_network_s_controller_layer_is_still_read():
    """C1928: Prometheus not configured. A network with a controller connection is read from
    the SDN reader's stored value alone, said as not routed; one with none has no graph, and
    with no network at all the value is what it always was."""
    got = T.read(source=lambda: (False, {}, {}), clock=lambda: 0,
                 population=lambda: [("Lab", _ref(), ["leaf-1", "leaf-2", "zz-new"])],
                 sdn=lambda network, now: {"state": "read", "controllers": [_controller()]},
                 netbox=lambda network: _netbox())
    assert got["configured"] is False and set(got["networks"]) == {"lab"}
    net = got["networks"]["lab"]
    assert net["routed"] is False and net["sdn"]["controllers"][0]["switches"] == 2
    assert net["nodes"]["leaf-1"]["sdn"]["dpid"] == 1, "one node a device, with no Prometheus"
    an = net["analysis"]["physical"]
    assert an["islands"] == [] and an["not_scraped"] == ["zz-new"]
    assert all(net["layers"][layer] == [] for layer in T.ROUTING)
    none = T.read(source=lambda: (False, {}, {}), clock=lambda: 0,
                  population=lambda: [("Lab", _ref(), ["r1"])],
                  sdn=lambda network, now: {"state": "none", "why": "", "controllers": []},
                  netbox=lambda network: pytest.fail("no controller layer: NetBox is not read"))
    assert none == {"configured": False, "networks": {}, "errors": []}


def test_netbox_s_view_that_cannot_be_read_is_said_and_the_layer_still_drawn():
    def boom(network):
        raise OSError("the repository is locked")
    got = T.read(source=lambda: (False, {}, {}), clock=lambda: 0,
                 population=lambda: [("Lab", _ref(), ["leaf-1"])],
                 sdn=lambda network, now: {"state": "read", "controllers": [_controller()]},
                 netbox=boom)
    assert got["errors"] == ["Lab: NetBox's names for the controller layer could not be read "
                             "(OSError: the repository is locked)"]
    net = got["networks"]["lab"]
    assert net["sdn"]["netbox"]["state"] == "unreadable"
    assert "of:0000000000000001" in net["nodes"] and net["nodes"]["leaf-1"]["not_scraped"]


@pytest.fixture
def kit(tmp_path, monkeypatch):
    """Lab's Topology page over a store a test fills (`_kit_value`), removed afterwards."""
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.topology_expected._path",
                        lambda name: str(tmp_path / "lab" / "topology_expected.json"))
    import app as A
    from modules import reader_job
    yield {"client": A.app.test_client()}
    if os.path.exists(reader_job.store_path("topology-graph")):
        os.remove(reader_job.store_path("topology-graph"))


def _kit_value():
    """Lab as the kit was: no Prometheus, a controller connection, each switch a managed
    NetBox device, one more managed device nothing reads: the Topology reader's own value for
    it (`read`)."""
    value = T.read(source=lambda: (False, {}, {}), clock=lambda: READ_EPOCH,
                   population=lambda: [("Lab", _ref(), ["leaf-1", "leaf-2", "zz-new"])],
                   sdn=lambda network, now: {"state": "read", "controllers": [_controller()]},
                   netbox=lambda network: _netbox())
    value["networks"] = {"Lab": value["networks"]["lab"]}
    return value


def test_with_no_prometheus_the_page_draws_the_controller_s_layer_and_says_so(kit, monkeypatch):
    from tests import test_sdn_trace_v2 as V
    from tests.test_topology_v2 import _store
    _store(_kit_value())
    box = {"store": V.fresh(), "asked": []}
    V.answering(monkeypatch, box)
    html = _map(kit)
    # The page is the reader's stored value: the flow layer's form reads the SDN reader's
    # store once for the network, and nothing else is asked (no per-device work a view).
    assert box["asked"] == ["Lab"]
    assert "so there is nothing to draw" not in html
    notice = re.search(r'<div class="notice notice-warn" role="status" id="topo-no-prometheus">'
                       r'.*?</div>', html, re.S).group(0)
    assert "The routed map is not drawn: Prometheus is not configured." in notice
    assert "What is drawn is the controller" in notice
    # One node a switch, by its NetBox name, its DPID on its second line.
    assert re.search(r'class="topo-n topo-c-sdn[^"]*" data-node="leaf-1"', html)
    assert 'data-node="of:0000000000000001"' not in html
    assert re.search(r'<text class="topo-sdnline"[^>]*>of:…0001 · via controller</text>', html)
    strip = re.search(r'<div class="topo-cov small".*?</div>', html, re.S).group(0)
    assert "LLDP: not read (Prometheus is not configured)" in strip
    assert ("NetBox&#39;s names · the NSOT export abababababab · 2 switches drawn as their "
            "managed device") in strip
    # Not scraped is said, apart, and is no island.
    assert re.search(r'<g class="topo-tag topo-tag-unscraped"><title>Not scraped: ', html)
    assert "topo-tag-isl" not in html
    group = re.search(r'<details class="topo-grp" data-keep="topo-att-unscraped">.*?</details>',
                      html, re.S).group(0)
    assert "Not scraped (1): not measured, so not counted as islands" in group
    assert "zz-new" in group and "leaf-1" not in group
    # Path… is offered, on the flow tables (the only layer there is).
    assert '<form id="topo-of-form"' in html and "Trace the path" in html
    # A network with neither Prometheus nor a controller says what it always said.
    _store({"configured": False, "networks": {}, "errors": []})
    html = _map(kit)
    assert "Prometheus is not configured, so there is nothing to draw" in html
    assert "topo-no-prometheus" not in html and "topo-of-form" not in html


def test_a_trace_lights_a_switch_drawn_as_its_managed_device(kit, monkeypatch):
    """The flow trace names a switch by its DPID; on the map that switch is its managed
    device's one node, and the trace's path rings that node (the captured IPv6 path from h1 to
    h3, tests/test_sdn_trace.py's)."""
    from tests import test_sdn_trace_v2 as V
    from tests.test_topology_v2 import _store
    _store(_kit_value())
    box = {"store": V.fresh(), "asked": []}
    V.answering(monkeypatch, box)
    html = _map(kit, "&layer=of&src=2001:db8:8::1&dst=2001:db8:8::3")
    assert box["asked"] == ["Lab"], "the trace and the map share one read of the SDN store"
    assert "delivered through 2 switches" in html
    for name in ("leaf-1", "leaf-2"):
        assert re.search(r'class="topo-n topo-c-sdn[^"]*topo-onpath topo-onpath-on[^"]*" '
                         rf'data-node="{name}"', html), name
    assert "topo-pathglow topo-path-on" in html
