"""Topology › Path… on the Flow tables layer: the SDN trace's screen and its caller (board D,
docs/boards/sdn-trace.html; the final SDN lab's A4, C2578 and C1911), no network.

The route is Topology's region, through the REAL trace (`modules/sdn/trace.py`) over the SDN
reader's stored value built from the real captures tests/test_sdn_trace.py uses (Ryu 4.34 over
Open vSwitch 2.17.12, 2026-10-27: tests/fixtures/sdn/ryu/topology_rest.json and the Lab 8 flow
tables tests/fixtures/sdn/lab8/l2_only_s1.json and unauthorised_s2.json; their README says how
each was made), the map from test_sdn_topology.py's captured network. Only the store's read is
replaced (`reader_job.read_cached_for` answers the built value), never the walk. Every expected
DPID, port and port name is read off the captures by hand (s1 DPID 1: h1 on s1-eth1, h2 on
s1-eth2, the link on s1-eth3; s2 DPID 2: h3 on s2-eth1, h4 on s2-eth2, the link on s2-eth3).

- **The question:** the Layer switch on a network with routing devices and a controller layer;
  the Flow tables form's fields in the address; Port off for an ICMP echo; suggestions from the
  controller's hosts, never more than 20; Path… as before on a network with no controller.
- **The answer:** IPv4 and IPv6 delivered with each hop's DPID, in and out port and their names,
  the deciding flow and the pipeline one level down; IPv4 h1 to h3 carried to h4's port by the
  unauthorised flow, red, beside IPv6 delivered; the map lighting the switches on the path;
  Trace the reverse, Copy the hops (the trace's own words), Clear the path.
- **Cannot tell, said as such:** a group action, amber, never delivered or dropped; a switch
  whose table was not read.
- **Refusals:** an unknown host refused naming it, IPv4 and IPv6; one listed at two places offers
  each MAC as a trace; two families; a missing port.
- **The read's own states:** a read older than its promise drawn grey with an amber notice, never
  green; a store that cannot be read refused naming it; a walk that raises drawn as failed, never
  a 500.
- **A name:** an end host named as NetBox records it is traced by its MAC from the committed NSOT
  export, the answer naming that source; a name the export does not record is refused naming
  both sources.
- **A read:** nothing is written, no route_gates or invalidation entry (a GET), the form's answer
  pushes its address and a redraw pushes nothing.
"""
import html as html_mod
import copy
import os
import re
import time

import pytest

from modules.readers import sdn_controllers as R
from tests.test_sdn_trace import (H1, H3, S1, S2, S1_H1_H3, cached, replacing, _twice)
from tests.sdn_fakes import with_flows

DPID1, DPID2 = "0000000000000001", "0000000000000002"


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def fresh(**kw):
    """The SDN reader's stored value from the captures, read just now."""
    return cached(value_at=_iso(time.time() - 5), **kw)


def topology_value():
    """The Topology reader's value for Lab: test_sdn_topology.py's captured network (the routed
    fleet, r6's LLDP neighbour named by Ryu's chassis id) with its controller layer from Ryu's
    captured topology."""
    from tests import test_sdn_topology as ST
    from tests.test_topology_v2 import _value
    from modules.readers import topology_graph as T
    from tests.test_topology_graph import MANAGED, _capture, _intents

    frame = ST.LLDP["frames"][0]
    raw = bytes.fromhex(frame["port_id_hex"]).decode("latin-1")
    res, up = _capture()
    res.setdefault("r6", {}).update(ST._r6_facing(frame["chassis_id"], raw))
    value = _value(results=res, up=up)
    intents = {h: hv for h, hv in _intents().items() if h != "r5"}
    value["networks"]["Lab"] = T.network_graph(
        MANAGED, {h: ("router" if h.startswith("r") else "switch") for h in MANAGED}, intents,
        res, up, now="2026-10-10T19:00:00Z", at_here=[],
        sdn={"state": "read", "controllers": [ST._controller()]})
    return value


def answering(mp, box):
    """The SDN reader's store answers ``box["store"]``, each read of it noted in
    ``box["asked"]``; every other reader's store as it is."""
    from modules import reader_job
    real = reader_job.read_cached_for

    def read(name, list_name):
        if name == R.READER_NAME:
            box["asked"].append(list_name)
            return box["store"]
        return real(name, list_name)
    mp.setattr(reader_job, "read_cached_for", read)


def chain_fabric(n):
    """A fabric of *n* switches in a line (DPIDs 1 to n, each port 1 to the next's port 2), the
    stored fabric's own shape (`trace.fabric`'s): h1 (H1, 192.0.2.1, 2001:db8:8::1) on switch
    1's port 3, h3 (H3, .3, ::3) on switch n's port 3 and h9 on its port 4; every switch
    forwards to H3 by destination MAC, and the last floods it (OpenFlow's FLOOD), so the packet
    is delivered once, reaches h9's port once and leaves the fabric by ports 1 and 5. Built
    where it is used: no capture holds a fabric this long (board D, artboard F)."""
    switches, links = {}, {}
    for d in range(1, n + 1):
        out = 1 if d < n else "FLOOD"
        switches[d] = {"name": f"sw{d}", "why": "",
                       "ports": {p: f"sw{d}-eth{p}" for p in range(1, 6)},
                       "flows": [{"table_id": 0, "priority": 10, "cookie": 0, "owner":
                                  "controller_own", "match": {"eth_dst": H3},
                                  "actions": [{"type": "OUTPUT", "port": out}]}]}
        if d < n:
            links[(d, 1)], links[(d + 1, 2)] = (d + 1, 2), (d, 1)
    hosts = [{"mac": mac, "dpid": dpid, "port_no": port, "port_name": f"sw{dpid}-eth{port}",
              "ipv4": [f"192.0.2.{last}"], "ipv6": [f"2001:db8:8::{last}"]}
             for mac, dpid, port, last in ((H1, 1, 3, 1), (H3, n, 3, 3),
                                           ("00:00:00:00:00:09", n, 4, 9))]
    return {"state": "read", "why": "", "controllers": [{
        "name": "lab", "label": "Ryu", "state": "read", "why": "",
        "read_at": _iso(time.time() - 5), "hosts_note": "", "switches": switches,
        "links": links, "hosts": hosts}]}


@pytest.fixture
def web(tmp_path, monkeypatch):
    """Topology over `topology_value()`, and the SDN reader's store answering ``web["store"]``
    (set per test; `fresh()` by default)."""
    from tests.test_topology_v2 import _store
    from modules import reader_job

    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.topology_expected._path",
                        lambda name: str(tmp_path / "lab" / "topology_expected.json"))
    _store(topology_value())
    box = {"store": fresh(), "asked": []}
    answering(monkeypatch, box)
    import app as A
    box["client"] = A.app.test_client()
    yield box
    os.remove(reader_job.store_path("topology-graph"))


def _map(web, query="", headers=None):
    """Topology's region on the Flow tables layer, asked *query*. Each answer reads the SDN
    reader's stored value exactly once, for the network asked, whatever it draws: the
    suggestions and the walk share the one read (CLAUDE.md, "Enterprise scale")."""
    web["asked"].clear()
    resp = web["client"].get(f"/v2/topology/map?list=Lab&layer=of{query}", headers=headers or {})
    assert resp.status_code == 200, resp.status_code
    assert web["asked"] == ["Lab"], web["asked"]
    return resp.get_data(as_text=True)


def _card(html):
    m = re.search(r'<section class="card topo-panel topo-of-card".*?</section>', html, re.S)
    assert m, "no flow-trace card drawn"
    return html_mod.unescape(m.group(0))


def _strip(card):
    """The one-line strip: each switch's words, tags stripped."""
    ol = re.search(r'<ol class="topo-of-hops".*?</ol>', card, re.S).group(0)
    items = re.findall(r"<li class=\"([^\"]*)\">(.*?)</li>", ol, re.S)
    return [(cls.strip(), " ".join(re.sub(r"<[^>]+>", " ", body).split()).replace(" ,", ","))
            for cls, body in items if "topo-of-arrow" not in cls]


# ───────────────────────────────────────────────────────────────────────────── the question

def test_the_layer_switch_and_the_flow_tables_form(web):
    html = _map(web)
    seg = re.search(r'<span class="seg topo-of-layer".*?</span>\s*</span>|'
                    r'<span class="seg topo-of-layer".*?</a>\s*</span>', html, re.S).group(0)
    assert "Routing (CEF)" in seg and "Flow tables (OpenFlow)" in seg
    assert re.search(r'class="seg-btn on"[^>]*aria-pressed="true"><span class="topo-wide-only">'
                     r'Flow tables', seg)
    form = re.search(r'<form id="topo-of-form".*?</form>', html, re.S).group(0)
    for name in ("src", "dst", "proto", "dport"):
        assert f'name="{name}"' in form, name
    assert '<input type="hidden" name="layer" value="of">' in form
    assert 'hx-get="/v2/topology/map?list=Lab"' in form and 'method="get"' in form
    # ICMP has no port, so Port is off, drawn off before any script runs.
    assert re.search(r'name="dport"[^>]*placeholder="no port" disabled', form)
    assert 'data-op="sdn-trace"' in form and "How does a flow-table trace work?" in form
    # The popover opens on the Flow tables layer until a question is asked.
    assert re.search(r'<details class="topo-pop topo-wide" data-keep="topo-path" open>', html)


def test_the_suggestions_are_the_controller_s_hosts_never_more_than_twenty(web):
    html = _map(web)
    options = re.findall(r'<datalist id="topo-of-hosts">(.*?)</datalist>', html, re.S)[0]
    values = re.findall(r'<option value="([^"]+)"', options)
    assert "192.0.2.1" in values and "192.0.2.4" in values
    assert len(values) == 6, values       # the six hosts the capture lists, none dropped
    assert "6 of 6 suggested" in html
    from modules import sdn_trace_page as P
    assert P.SUGGESTED == 20
    many = {"controllers": [{"hosts": [{"mac": f"02:00:00:00:00:{n:02x}", "dpid": 1,
                                        "port_no": n, "ipv4": [f"192.0.2.{n}"], "ipv6": []}
                                       for n in range(1, 40)]}]}
    got = P._suggestions(many)
    assert len(got["hosts"]) == 20 and got["of"] == 39


def test_a_network_with_no_controller_draws_path_as_before(tmp_path, monkeypatch):
    from tests.test_topology_v2 import _store, _value
    from modules import reader_job
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.topology_expected._path",
                        lambda name: str(tmp_path / "lab" / "topology_expected.json"))
    _store(_value())
    asked = []
    real = reader_job.read_cached_for
    monkeypatch.setattr(reader_job, "read_cached_for",
                        lambda name, list_name: asked.append(name) or real(name, list_name))
    import app as A
    try:
        html = A.app.test_client().get("/v2/topology/map?list=Lab&layer=of&src=192.0.2.1"
                                       "&dst=192.0.2.3").get_data(as_text=True)
    finally:
        os.remove(reader_job.store_path("topology-graph"))
    assert R.READER_NAME not in asked, "a network with no controller layer reads no SDN store"
    assert "topo-of-layer" not in html and "topo-of-card" not in html
    assert 'action="/v2/topology/path?list=Lab"' in html     # today's Path…, unchanged


# ───────────────────────────────────────────────────────────────────────────── the answer

@pytest.mark.parametrize("src,dst,family", [("2001:db8:8::1", "2001:db8:8::3", "IPv6")])
def test_ipv6_delivered_with_each_hop_s_dpid_and_ports(web, src, dst, family):
    card = _card(_map(web, f"&src={src}&dst={dst}"))
    assert f"{src} to {dst}, ICMPv6 echo: delivered through 2 switches" in card
    assert (f"From {src} ({H1}) on s1 port 1 (s1-eth1) to {dst} ({H3}) on s2 port 1 (s2-eth1) · "
            "through lab's flow tables") in card
    assert 'badge badge-ok">delivered<' in card
    assert _strip(card) == [("", f"s1 {DPID1} · in 1 s1-eth1 → out 3 s1-eth3"),
                            ("topo-of-dst", f"s2 {DPID2} · in 3 s2-eth3 → out 1 s2-eth1")]
    assert f"{DPID2} port 1 is the destination's port: delivered." in card
    assert "link to s2 port 3" in card and f"{dst}'s port" in card
    # The deciding flow, then every flow the pipeline ran, one level down.
    assert "table 0 · priority 1 · cookie 0" in card
    assert "Open in SDN › Flows" in card and f"/v2/sdn/flows?list=Lab&q={DPID1}" in card
    assert f"The packet traced: ICMPv6 echo, {family}" in card
    assert "ipv6_src=2001:db8:8::1" in card and "icmpv6_type=128" in card


def _classified(rows):
    """The owner the SDN reader stores on each flow (`flow_intent.classify`, run by the reader,
    not by the capture's parse): cookie 0 the controller's own, 0xbad0 unauthorised."""
    for row in rows:
        for f in row["flows"]:
            f["owner"] = "unauthorised" if f["cookie"] == 0xBAD0 else "controller_own"


def test_ipv4_h1_to_h3_is_carried_to_h4_s_port_red_beside_ipv6_delivered(web):
    web["store"] = fresh(rows_edit=_classified)
    six = _card(_map(web, "&src=2001:db8:8::1&dst=2001:db8:8::3"))
    assert 'badge badge-ok">delivered<' in six and "unauthorised" not in six
    assert 'badge badge-muted">the controller\'s own<' in six
    card = _card(_map(web, "&src=192.0.2.1&dst=192.0.2.3"))
    assert ("192.0.2.1 to 192.0.2.3, ICMP echo: not delivered, sent to another host's port "
            "at s2") in card
    assert 'badge badge-danger">to another host<' in card
    assert _strip(card)[-1] == ("topo-of-stopped", f"s2 {DPID2} · in 3 s2-eth3 → out 2 s2-eth2")
    assert "topo-of-end topo-of-end-danger" in card and "192.0.2.4" in card
    assert "cookie 0xbad0" in card and 'badge badge-danger">unauthorised<' in card
    assert 'badge badge-ok">delivered<' not in card


def test_tcp_to_a_port_traces_from_49152(web):
    card = _card(_map(web, "&src=2001:db8:8::1&dst=2001:db8:8::3&proto=tcp&dport=80"))
    assert "TCP 80: delivered through 2 switches" in card
    assert "from 2001:db8:8::1 port 49152 to 2001:db8:8::3 port 80" in card
    assert "tcp_src=49152, tcp_dst=80" in card


def test_the_map_lights_the_path_and_rings_each_switch(web):
    html = _map(web, "&src=2001:db8:8::1&dst=2001:db8:8::3")
    assert re.search(r'class="topo-n topo-c-sdn[^"]*topo-onpath topo-onpath-on[^"]*" '
                     r'data-node="of:0000000000000001"', html)
    assert re.search(r'class="topo-n topo-c-sdn[^"]*topo-onpath topo-onpath-on[^"]*" '
                     r'data-node="of:0000000000000002"', html)
    assert "topo-pathglow topo-path-on" in html


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_a_long_flooded_path_leads_with_a_summary_folds_and_groups(web, monkeypatch, src, dst):
    from modules.sdn import trace as TR
    monkeypatch.setattr(TR, "fabric", lambda network, cached=None, now=None: chain_fabric(9))
    card = _card(_map(web, f"&src={src}&dst={dst}"))
    assert ("delivered through 9 switches; and 3 other copies of it") in card
    summary = re.search(r'<div class="topo-of-sum".*?</div>\s*</div>|<div class="topo-of-sum"'
                        r'.*?</div>\n', card, re.S).group(0)
    counts = dict((w.strip(), int(n)) for n, w in re.findall(r"<b[^>]*>(\d+)</b>([^<]+)",
                                                             summary))
    assert counts == {"delivered": 1, "to another host": 1, "leaves the fabric": 2}
    # The delivered branch: the first two and last two hops, the middle five folded, named.
    assert "Hops 3 to 7 (5 switches: sw3, sw4, sw5, sw6, sw7)" in card
    table = re.search(r'<table class="table topo-of-table" aria-label="The hops">.*?</table>\s*'
                      r'</div>\s*(?=<div class="topo-of-groups")', card, re.S).group(0)
    head, rest = table.split('<tr class="topo-of-fold">')
    folded, tail = rest.split("</details></td></tr>", 1)
    drawn = re.compile(r"<td>(\d)</td>\s*<td><a")
    assert drawn.findall(head) + drawn.findall(tail) == ["1", "2", "8", "9"]
    assert drawn.findall(folded) == ["3", "4", "5", "6", "7"]
    # Every branch grouped by ending, the delivered group open, the others closed.
    groups = re.findall(r'<details class="topo-of-group" data-keep="topo-of-group-(\w+)"( open)?',
                        card)
    assert groups == [("delivered", " open"), ("elsewhere", ""), ("leaves", "")]
    assert "it leaves the fabric by 0000000000000009 port 5" in card


def test_reverse_copy_and_clear(web):
    card = _card(_map(web, "&src=192.0.2.3&dst=192.0.2.1"))
    acts = re.search(r'<div class="topo-trace-acts">.*?</div>', card, re.S).group(0)
    rev = re.search(r'<a class="btn btn-small" data-op="sdn-trace" href="([^"]+)"[^>]*>Trace the '
                    r'reverse</a>', acts).group(1)
    assert "src=192.0.2.1" in rev and "dst=192.0.2.3" in rev and "layer=of" in rev
    copied = re.search(r'data-copy="([^"]+)"', acts).group(1)
    assert copied.startswith(f"Delivered: {DPID2} (in 1, out 3) → {DPID1} (in 3, out 1)")
    clear = re.search(r'href="([^"]+)"[^>]*>Clear the path</a>', acts).group(1)
    assert "src=" not in clear and "dst=" not in clear and "layer=of" in clear
    assert acts.count("How does a flow-table trace work?") == 3


# ───────────────────────────────────────────────────────────────────────────── cannot tell

@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_a_group_action_is_cannot_tell_in_amber_never_delivered(web, src, dst):
    web["store"] = fresh(s1=with_flows(S1, 1, replacing(S1_H1_H3, ["GROUP:1"])))
    card = _card(_map(web, f"&src={src}&dst={dst}"))
    assert ": cannot tell, at s1" in card
    assert 'badge badge-warn">cannot tell<' in card
    assert "sends it to a group, whose buckets the trace does not read" in card
    assert "topo-of-end-warn" in card
    assert "badge-ok\">delivered" not in card and "dropped" not in card


@pytest.mark.parametrize("src,dst", [("192.0.2.1", "192.0.2.3"),
                                     ("2001:db8:8::1", "2001:db8:8::3")])
def test_a_switch_whose_table_was_not_read_is_cannot_tell_on_its_hop(web, src, dst):
    def unread(rows):
        rows[1].update(active_flows=None, flows=[], error="flows: HTTP 500 from /stats/flow/2")
    web["store"] = fresh(rows_edit=unread)
    card = _card(_map(web, f"&src={src}&dst={dst}"))
    assert ": cannot tell, s2's table not read" in card
    assert "its table was not read" in card and "HTTP 500" in card
    assert _strip(card)[-1] == ("topo-of-stopped", f"s2 {DPID2} · in 3 s2-eth3, no out port")


# ───────────────────────────────────────────────────────────────────────────── refusals

@pytest.mark.parametrize("src", ["192.0.2.99", "2001:db8:8::99"])
def test_an_unknown_host_is_refused_naming_it(web, src):
    dst = "192.0.2.3" if "." in src else "2001:db8:8::3"
    card = _card(_map(web, f"&src={src}&dst={dst}"))
    assert "Path: not traced" in card
    assert (f"<strong>Not traced:</strong> no controller lists a host with {src} on an edge port "
            "(6 hosts listed). Nothing was asked of the controller or any switch.") in card
    assert 'role="alert"' in card


@pytest.mark.parametrize("address", ["192.0.2.3", "2001:db8:8::3"])
def test_one_listed_at_two_places_offers_each_mac(web, address):
    web["store"] = fresh(topo_edit=_twice(address))
    src = "192.0.2.1" if "." in address else "2001:db8:8::1"
    card = _card(_map(web, f"&src={src}&dst={address}"))
    assert "is listed at 2 places" in card
    links = re.findall(r'data-op="sdn-trace" href="([^"]+)"[^>]*>Trace to ([0-9a-f:]+)</a>', card)
    assert sorted(m for _h, m in links) == sorted(["02:00:00:00:00:99", H3])
    for href, mac in links:
        assert f"dst={mac.replace(':', '%3A')}" in href and f"src={src.replace(':', '%3A')}" in \
            href


def test_two_families_and_a_missing_port_are_refused(web):
    assert "a packet has one family" in _card(_map(web, "&src=192.0.2.1&dst=2001:db8:8::3"))
    card = _card(_map(web, "&src=192.0.2.1&dst=192.0.2.3&proto=udp"))
    assert "a UDP trace needs its destination port, from 1 to 65535" in card


def test_an_empty_end_is_refused_naming_which(web):
    assert "to is empty: give the destination host's" in _card(_map(web, "&src=192.0.2.1"))


# ───────────────────────────────────────────────────────────────────────────── the read's states

def test_a_read_older_than_its_promise_is_grey_with_an_amber_notice_never_green(web):
    web["store"] = cached(value_at=_iso(time.time() - 7200))
    card = _card(_map(web, "&src=2001:db8:8::1&dst=2001:db8:8::3"))
    assert "delivered through 2 switches, as last read" in card
    assert 'badge badge-neutral">delivered, as last read<' in card
    assert 'badge badge-ok">' not in card
    assert re.search(r'<div class="notice notice-warn" role="status">.*?lab has not been read '
                     r'since .*?older than its promise', card, re.S)
    assert "the switches may hold other flows now" in card


def test_a_store_that_cannot_be_read_is_refused_naming_it(web):
    web["store"] = {"state": "unreadable", "doc": None, "why": "sdn-controllers.json could not "
                                                               "be read (ValueError)"}
    card = _card(_map(web, "&src=192.0.2.1&dst=192.0.2.3"))
    assert "the controller's topology is not read" in card and "ValueError" in card


def test_a_walk_that_raises_is_drawn_as_failed_never_a_500(web, monkeypatch):
    from modules.sdn import trace as TR

    def broken(*_a, **_k):
        raise TypeError("switch 0000000000000002's flows: not a list")
    monkeypatch.setattr(TR, "walk", broken)
    card = _card(_map(web, "&src=192.0.2.1&dst=192.0.2.3"))
    assert "<strong>The trace failed:</strong> TypeError: switch 0000000000000002's flows" in card


# ───────────────────────────────────────────────────────────────────────────── a name

def _export(hosts):
    return {"ok": True, "sha256": "ab" * 32, "error": "",
            "export": {"sha256": "ab" * 32, "body": {"devices": [], "interfaces": [],
                                                     "hosts": hosts}}}


H1_EXPORT = [{"name": "h1", "id": 9, "site": "lab", "status": "active", "role": "host",
              "tags": ["mercury-end-host"],
              "interfaces": [{"name": "eth0", "mac": H1,
                              "ip_addresses": ["192.0.2.1/24", "2001:db8:8::1/64"],
                              "attached": ["s1", "s1-eth1"]}]}]


def test_an_end_host_named_as_netbox_records_it_is_traced_by_its_mac(web, monkeypatch):
    monkeypatch.setattr("modules.nsot.export.read", lambda network: _export(H1_EXPORT))
    card = _card(_map(web, "&src=h1&dst=2001:db8:8::3"))
    assert "h1 to 2001:db8:8::3, ICMPv6 echo: delivered through 2 switches" in card
    assert (f"h1 is {H1} (eth0, cabled to s1 s1-eth1) by NetBox's end hosts, in the NSOT export "
            f"{'ab' * 6}") in card


@pytest.mark.parametrize("export,words", [
    (_export(H1_EXPORT), "names no end host 'h9' (1 end host recorded)"),
    ({"ok": False, "error": "Lab has no committed NSOT export at HEAD"},
     "no end host can be looked up by name: Lab has no committed NSOT export"),
    ({"ok": True, "sha256": "cd" * 32, "export": {"sha256": "cd" * 32, "body": {}}},
     "was built before end hosts were recorded"),
])
def test_a_name_no_source_answers_is_refused_naming_both(web, monkeypatch, export, words):
    monkeypatch.setattr("modules.nsot.export.read", lambda network: export)
    card = _card(_map(web, "&src=h9&dst=192.0.2.3"))
    assert "'h9' is not an IPv4 or IPv6 address or a MAC" in card and words in card


def test_an_address_never_reads_the_export(web, monkeypatch):
    def refuse(network):
        raise AssertionError("an address read the NSOT export")
    monkeypatch.setattr("modules.nsot.export.read", refuse)
    _card(_map(web, "&src=192.0.2.1&dst=192.0.2.3"))


# ───────────────────────────────────────────────────────────────────────────── a read

def test_the_trace_reads_the_store_once_and_writes_nothing(web, tmp_path):
    before = copy.deepcopy(web["store"])
    listing = sorted(os.listdir(tmp_path / "lab"))
    web["asked"].clear()
    _map(web, "&src=192.0.2.1&dst=192.0.2.3")
    assert web["asked"] == ["Lab"], "one read of the stored value per answer"
    assert web["store"] == before and sorted(os.listdir(tmp_path / "lab")) == listing


def test_the_form_pushes_its_address_and_a_redraw_pushes_nothing(web):
    q = "&src=192.0.2.1&dst=192.0.2.3"
    web["asked"].clear()
    resp = web["client"].get(f"/v2/topology/map?list=Lab&layer=of{q}",
                             headers={"HX-Request": "true", "HX-Trigger": "topo-of-form"})
    assert web["asked"] == ["Lab"]
    push = resp.headers.get("HX-Push-Url", "")
    assert push.startswith("/v2/topology?") and "layer=of" in push and "src=192.0.2.1" in push
    redraw = web["client"].get(f"/v2/topology/map?list=Lab&layer=of{q}",
                               headers={"HX-Request": "true", "HX-Trigger": "topo"})
    assert "HX-Push-Url" not in redraw.headers


def test_the_answer_redraws_as_each_read_arrives(web):
    html = _map(web, "&src=192.0.2.1&dst=192.0.2.3")
    trigger = re.search(r'<div id="topo"[^>]*hx-trigger="([^"]+)"', html).group(1)
    assert "nmas:sdn from:body" in trigger


def test_the_page_opens_the_same_answer_under_the_strict_policy(web):
    web["asked"].clear()
    resp = web["client"].get("/v2/topology?list=Lab&layer=of&src=2001:db8:8::1"
                             "&dst=2001:db8:8::3")
    assert resp.status_code == 200
    assert web["asked"] == ["Lab"]
    from modules import csp
    assert resp.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
    assert "delivered through 2 switches" in resp.get_data(as_text=True)


SHOTS = os.environ.get("NMAS_SDN_TRACE_SHOTS", "")


def test_the_trace_pressed_in_a_browser(web):
    """A real browser at 1440 and 390: Path… opens on the Flow tables layer from SDN › Flows'
    address; Port is off for ICMP and on once TCP is chosen; From, to, TCP and port 80 typed
    and Trace the path pressed: the card is drawn in place with both DPIDs and their ports, the
    page's address now carries the question, and the map rings both switches. Then Trace the
    reverse is pressed and its answer drawn. (NMAS_SDN_TRACE_SHOTS names a folder to keep the
    shots in, for the fidelity comparison.)"""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A

    with browser.Served(A.app) as srv, browser.Browser() as b:
        # The desktop asks in Path…'s popover; the phone, where the popover is not drawn, in
        # the card above the tab's content (artboard G).
        for width, height, sfx in ((1440, 1000, ""), (390, 844, "-n")):
            b._call("POST", f"/session/{b.session}/window/rect", {"width": width,
                                                                  "height": height})
            b.go(srv.url("/v2/topology?list=Lab&layer=of"))
            form = f"#topo-of-form{sfx}"
            b.wait_for(f"return document.querySelector('{form} input[name=dport]')")
            assert b.js(f"return document.querySelector('{form} input[name=dport]')"
                        ".disabled") is True, "ICMP has no port"
            b.js(f"var f = document.querySelector('{form}'); "
                 "var s = f.querySelector('select[name=proto]'); s.value = 'tcp'; "
                 "s.dispatchEvent(new Event('change', {bubbles: true}));")
            b.wait_for(f"return !document.querySelector('{form} input[name=dport]').disabled")
            assert b.js(f"return document.querySelector('{form} input[name=dport]')"
                        ".placeholder") == "1 to 65535"
            if SHOTS:
                b.screenshot(os.path.join(SHOTS, f"sdn-trace-form-{width}.png"))
            b.type(f"#topo-src{sfx}", "2001:db8:8::1")
            b.type(f"#topo-dst{sfx}", "2001:db8:8::3")
            b.type(f"#topo-dport{sfx}", "80")
            b.click(f"{form} button[type=submit]")
            b.wait_for("return document.querySelector('#topo-of-h') && "
                       "document.querySelector('#topo-of-h').textContent"
                       ".indexOf('delivered through 2 switches') >= 0", timeout=20)
            strip = b.js("return document.querySelector('.topo-of-hops').textContent")
            assert DPID1 in strip and DPID2 in strip and "s1-eth3" in strip and \
                "s2-eth1" in strip, strip
            here = b.js("return location.search")
            assert "layer=of" in here and "dport=80" in here and "proto=tcp" in here, here
            assert b.js("return document.querySelectorAll('.topo-n.topo-onpath-on').length") \
                >= 2
            if SHOTS:
                b.screenshot(os.path.join(SHOTS, f"sdn-trace-{width}.png"))
            b.js("Array.prototype.find.call(document.querySelectorAll('.topo-trace-acts a'), "
                 "function (a) { return a.textContent === 'Trace the reverse'; }).click();")
            b.wait_for("return document.querySelector('#topo-of-h').textContent"
                       ".indexOf('2001:db8:8::3 to 2001:db8:8::1') === 0", timeout=20)
            assert "src=2001%3Adb8%3A8%3A%3A3" in b.js("return location.search")


def test_the_route_is_a_get_in_neither_gates_nor_invalidation():
    import app as A
    from modules import invalidation, route_gates
    rules = [r for r in A.app.url_map.iter_rules() if r.endpoint == "topology_v2.region"]
    assert rules and all(set(r.methods) - {"HEAD", "OPTIONS"} == {"GET"} for r in rules)
    assert "topology_v2.region" not in invalidation.DECLARED
    assert "topology_v2.region" not in route_gates.GATES
    assert "sdn" in invalidation.VOCABULARY, "the region redraws on the SDN reader's key"
