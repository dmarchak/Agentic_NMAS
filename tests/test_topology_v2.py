"""OBSERVE › Topology on v2 (P.11 step 2), through the real routes and templates, drawing a stored
value the real reader built from the real captures (tests/test_topology_graph's fixtures: LLDP,
interfaces, routing tables, the fleet's configs with r5 retired, as on the host; Mercury's host
on s3 Vlan99's subnet, as the lab's is). What boards TopoDesktop and TopoPhone draw
(docs/fidelity/topology.md compares them region by region; this checks what each region holds):

- the header: the network, its counts and the read's age, Find, How does this work?;
- every link labelled with the PORT at each end, and the neighbourship between its two ends as
  the board's chips, the protocol and the state ("OSPF FULL", "BGP Estab"; C658); the area and
  the peer AS in the link's card;
- each link's line class against intent, the legend's four styles and device classes; device
  icons, an L3 switch badged, r5 as an outside peer with its AS, Mercury's host where measured;
- Needs attention on the map: the one-sided links under "not as intended" with what is wrong,
  the weak points (s3 the single point of failure, through Mercury's port; r6 an island to look
  at); a group or a filter shows a subset and says so;
- a hover card per link, and a selected link's sheet (the phone's);
- the protocol toggles change what the links carry; Ports, Labels and zoom; RIP and RIPng as read
  (C662), a one-sided link confirmed by them (C671), and RIP not read shown as not
  read; a down link is thick and red, chipped "down", naming its end;
- a path trace and a what-if, each a claim about the stored graph;
- marking an island expected is a verified person's recorded act; with no person, nothing;
- a device-announced name with markup is escaped where drawn (the brief, Q16);
- no read stored, an unreadable store, Prometheus not configured: each its own words.
"""

import json
import os
import re
import time

import pytest

from modules import reader_job
from modules.readers import topology_graph as T
from tests.test_topology_graph import MANAGED, _capture, _intents, _rip


def _here(intents):
    """Mercury's host as on the lab's: an address in s3 Vlan99's subnet (the NMAS management
    segment), derived from the captured config, never typed."""
    import ipaddress
    svi = next(i for i in intents["s3"]["interfaces"] if i["name"] == "Vlan99")
    net = ipaddress.ip_interface("/".join(svi["ipv4"].split())).network
    return [("eth1", f"{net.network_address + 250}/{net.prefixlen}")]


def _value(results=None, up=None, expected=None, here=True, rip=None):
    res, u = _capture()
    intents = {h: hv for h, hv in _intents().items() if h != "r5"}
    net = T.network_graph(MANAGED, {h: ("router" if h.startswith("r") else "switch")
                                    for h in MANAGED}, intents, results or res, up or u,
                          expected=expected or {}, previous=None, now="2026-10-10T19:00:00Z",
                          at_here=_here(intents) if here else [],
                          rip=_rip() if rip is None else rip)
    return {"configured": True, "networks": {"Lab": net}, "errors": [],
            "read_at": "2026-10-10T19:00:00Z"}


def _store(value, ok=True):
    path = reader_job.store_path("topology-graph")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = {"last_attempt": {"at": "2026-10-10T19:00:00Z", "ok": ok,
                            "error": "" if ok else "Prometheus could not be asked"}}
    if value is not None:
        doc["last_good"] = {"value": value, "value_at": "2026-10-10T19:00:00Z"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


@pytest.fixture
def web(tmp_path, monkeypatch):
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.topology_expected._path",
                        lambda name: str(tmp_path / "lab" / "topology_expected.json"))
    _store(_value())
    import app as A
    yield {"client": A.app.test_client(), "dir": tmp_path / "lab"}
    os.remove(reader_job.store_path("topology-graph"))


def _get(web, query=""):
    return web["client"].get(f"/v2/topology/map?list=Lab{query}").get_data(as_text=True)


def _chips(html):
    return re.findall(r'<text class="topo-st-t topo-st-(\w+)"[^>]*>([^<]*)</text>', html)


def _ports(html):
    return re.findall(r'<text class="topo-port"[^>]*>([^<]*)</text>', html)


def _section(html, ident):
    return re.search(rf'aria-labelledby="{ident}".*?</section>', html, re.S).group(0)


def test_the_page_its_sidebar_and_header(web):
    html = web["client"].get("/v2/topology?list=Lab").get_data(as_text=True)
    assert 'aria-current="page"' in html and "<span>Topology</span>" in html
    assert re.search(r"<h1>Topology <a class=\"info-link\".*?</a> <span class=\"topo-sub\">· Lab · "
                     r"9 devices, 12 links, 1 "
                     r"external · read <time", html)
    assert 'placeholder="Find a device, address or interface"' in html
    # The board's header: Find is the field alone (Enter finds), no button beside it.
    assert ">Find</span>" not in html
    assert "How does this work?" in html
    assert re.search(r'<a href="/v2/device/r1\?list=Lab">', html), "a device opens its page"
    assert 'hx-trigger="nmas:topology from:body"' in html


def test_every_link_names_the_port_at_each_end(web):
    ports = _ports(_get(web))
    # Eleven LLDP links and Mercury's own: two ports each.
    assert len(ports) == 24
    for p in ("Gi4", "Gi2", "Gi3", "Gi0/2", "Gi1/0", "Gi0/3", "Gi1/1", "eth1"):
        assert p in ports, p


def test_each_link_names_the_neighbourship_between_its_two_ends(web):
    """C658, the board's chips: "OSPF FULL", "BGP Estab": the protocol and the state of the
    neighbourship between the link's two ends, one chip per protocol; no area, AS or count. The
    lab's twelve links, measured on the captures: r3-r4 OSPF and OSPFv3 FULL; r3-s3 and r4-s4
    OSPF FULL; r1-s3, r2-s4 and s3-s4 OSPF 2WAY (DROthers on VLAN 100, as OSPF intends); r3-r5
    and r4-r5 BGP Estab (the IPv4 and IPv6 sessions, one chip); r1-s1 and r2-s2 RIP and RIPng
    up, heard both ways (C662, the devices' own answers); s1-s2 RIPng up (three VLAN interfaces'
    adjacencies, one chip). Each VLAN 100 trunk also carries seven adjacencies between OTHER
    devices, all as intended: no chip (the live page repeated them on every trunk)."""
    chips = _chips(_get(web))
    texts = sorted(t for _c, t in chips)
    assert texts == sorted(["OSPF FULL"] * 3 + ["OSPFv3 FULL"] + ["OSPF 2WAY"] * 3 +
                           ["BGP Estab"] * 2 + ["RIP up"] * 2 + ["RIPng up"] * 3)
    assert {c for c, _t in chips} == {"ok"}


def test_ripng_not_read_is_said_not_read(web):
    """No RIP read stored (or one past its promise): the RIP and RIPng adjacencies committed
    intent implies (r1-s1 and r2-s2 both; s1-s2 RIPng on its VLAN interfaces) are chipped "?",
    not read, never up and never missing."""
    _store(_value(rip={}))
    chips = _chips(_get(web))
    assert sorted(t for c, t in chips if c == "unread") == ["RIP ?"] * 2 + ["RIPng ?"] * 3
    assert not [t for _c, t in chips if t.startswith("RIP") and not t.endswith("?")]


def test_a_2way_where_full_is_intended_is_flagged_by_name(web):
    """The board's "OSPF 2WAY, intended FULL": r1's adjacency with r3, the segment's DR, stuck in
    2WAY. It passes over r1-s3 and r3-s3 (VLAN 100), so each gets its own chip naming both
    devices, the lines turn "not as intended", and Needs attention says what was intended."""
    res, up = _capture()
    for row in res["r1"]["ospfNbrState"]:
        if row["metric"].get("ospfNbrIpAddr", "").endswith(".13"):          # r3, the DR
            row["value"] = [row["value"][0], "4"]                           # 2-way
    for row in res["r3"]["ospfNbrState"]:
        if row["metric"].get("ospfNbrIpAddr", "").endswith(".11"):
            row["value"] = [row["value"][0], "4"]
    _store(_value(res, up))
    html = _get(web)
    assert _chips(html).count(("warn", "OSPF r1–r3 2WAY")) == 2
    att = _section(html, "topo-att-h")
    assert "OSPF area 0 r1 to r3: 2WAY, intended FULL" in att


def test_lines_say_how_each_link_compares_with_intent(web):
    html = _get(web)
    classes = re.findall(r'<path class="topo-line topo-(\w+)[^"]*" d=', html)
    # 12 drawn on the map, 12 again in the zoomed-out view; r1-s1 and r2-s2, which only r1's
    # and r2's LLDP reports, are confirmed by RIP and RIPng heard both ways (C671).
    assert len(classes) == 24
    assert classes[:12].count("ok") == 12
    # With no second witness (RIP not read), the two one-sided links are "not as intended", and
    # s1-s2, whose only adjacencies are RIPng's, is not read.
    _store(_value(rip={}))
    classes = re.findall(r'<path class="topo-line topo-(\w+)[^"]*" d=', _get(web))
    assert [classes[:12].count(c) for c in ("warn", "unread", "ok")] == [2, 1, 9]
    legend = re.search(r'aria-label="Legend".*?</div>', html, re.S).group(0)
    for words in ("as intended", "not as intended", "down, or a neighbour missing", "not read",
                  "router", "L2 switch", "L3 switch", "server", "external", "not classified in NetBox"):
        assert words in legend, words


def test_devices_are_icons_by_class(web):
    html = _get(web)
    assert html.count('href="#ti-router"') >= 5 and 'href="#ti-cloud"' in html
    assert 'href="#ti-server"' in html and '<symbol id="ti-switch"' in html
    # s3 and s4 route (OSPF on their VLAN interfaces), and s1 and s2 (RIP on their routed
    # ports, RIPng on their VLAN interfaces): L3, badged.
    assert html.count('class="topo-l3-t"') == 4
    assert re.search(r'<text class="topo-name"[^>]*>r5 · AS 65002</text>', html)
    assert re.search(r'<text class="topo-name"[^>]*>Mercury</text>', html)


def test_the_board_s_other_classes_come_from_the_role_s_own_word(web):
    """C658: the board's legend has nine classes; firewall, access point and controller are each
    our own icon, and a device is one only when its role names it; never a guess."""
    from modules.topology_layout import node_class
    assert node_class("x", {"role": "edge-firewall"}) == "firewall"
    assert node_class("x", {"role": "access-point"}) == "accesspoint"
    assert node_class("x", {"role": "wlan-controller"}) == "controller"
    assert node_class("x", {"role": "app-server"}) == "server"
    assert node_class("x", {"role": "load-balancer"}) == "unknown"
    html = _get(web)
    for name in ("firewall", "access-point", "controller"):
        assert f'<symbol id="ti-{name}"' in html, name


def test_needs_attention_names_what_is_wrong_and_the_weak_points(web):
    att = _section(_get(web), "topo-att-h")
    # r1-s1 and r2-s2 have their second witness: not listed.
    assert "Up, not as intended" not in att and "r1 Gi3 ↔ s1 Gi0/2" not in att
    assert "12 as intended" in att
    _store(_value(rip={}))
    att = _section(_get(web), "topo-att-h")
    assert "Up, not as intended (2)" in att
    assert "r1 Gi3 ↔ s1 Gi0/2" in att and (
        "LLDP: r1 Gi3 reports s1; s1 Gi0/2 reports no neighbour, polled; no "
        "second witness (no routing adjacency on it heard from both ends)") in att
    assert "Weak points (2)" in att
    assert ("the only path between Mercury and r1, r2, r3, r4, s1, s2, s4 (Mercury reaches them "
            "only through s3 Gi1/1, VLAN 99). If s3 or that port fails, Mercury loses 7 "
            "devices") in att
    assert "r6" in att and "island" in att and "Mark as expected…" in att
    assert "9 as intended" in att and "r5" not in att


def test_a_group_or_a_filter_shows_a_subset_and_says_so(web):
    _store(_value(rip={}))
    att = _section(_get(web, "&show=weak"), "topo-att-h")
    assert "r1 Gi3" not in att and "s3" in att
    assert "the counts are the whole" in att and "Show all" in att
    att = _section(_get(web, "&f=s2"), "topo-att-h")
    assert "r2 Gi3 ↔ s2 Gi0/2" in att and "r1 Gi3 ↔ s1" not in att
    assert "what matches s2" in att


def test_each_link_has_a_hover_card_and_a_selected_one_its_sheet(web):
    html = _get(web)
    cards = re.findall(r'<foreignObject class="topo-card".*?</foreignObject>', html, re.S)
    assert len(cards) == 12
    card = next(c for c in cards if "r3 Gi4 ↔ r4 Gi4" in c)
    # The board's card: a row per protocol, its area, the state, and against intent.
    assert "<dt>OSPF area 0</dt>" in card and "as intended" in card
    assert "BGP, RIP / RIPng</dt>" in card and "none on this link; none intended" in card
    assert "r3's Neighbours" in card and "tab=neighbours" in card
    # A VLAN 100 trunk's card lists what passes over it, one level down from the map.
    trunk = next(c for c in cards if "r3 Gi3 ↔ s3 Gi0/2" in c)
    assert "passing over this link: " in trunk and "r1–r3 FULL" in trunk
    html = _get(web, "&sel=r1%3AGi3~s1%3AGi0%2F2")
    assert '<g class="topo-l topo-sel">' in html and 'class="topo-glow' in html
    sheet = re.search(r'<section class="topo-sheet".*?</section>', html, re.S).group(0)
    assert "r1 Gi3" in sheet and "s1 Gi0/2" in sheet
    assert "only r1&#39;s LLDP reports it" in sheet
    # The silent LLDP end, with what was measured, and the witness.
    assert "LLDP: r1 Gi3 reports s1; s1 Gi0/2 reports no neighbour, polled" in sheet
    assert "confirmed by RIP, RIPng heard both ways" in sheet
    assert "on 10.255.2.10/31" in sheet and "on 2001:db8:2:a::/64" in sheet
    assert "Show on the map" in sheet
    _store(_value(rip={}))
    sheet = re.search(r'<section class="topo-sheet".*?</section>',
                      _get(web, "&sel=r1%3AGi3~s1%3AGi0%2F2"), re.S).group(0)
    assert "no second witness" in sheet and "on 2001:db8:2:a::/64" in sheet
    assert "not measured" in sheet and "confirmed by" not in sheet


def test_the_protocol_toggles_change_what_the_links_carry(web):
    html = _get(web, "&p=bgp")
    texts = [t for _c, t in _chips(html)]
    assert texts == ["BGP Estab"] * 2
    assert re.search(r'aria-pressed="false">OSPF</a>', html)
    assert re.search(r'aria-pressed="true">BGP</a>', html)
    # The board's six toggles, in its order; EIGRP and IS-IS drawn off and say why.
    tools = re.search(r'aria-label="Protocols on the links">(.*?)</div>', html, re.S).group(1)
    assert re.findall(r">(OSPF|OSPFv3|BGP|RIP / RIPng|EIGRP|IS-IS)<", tools) == \
        ["OSPF", "OSPFv3", "BGP", "RIP / RIPng", "EIGRP", "IS-IS"]
    assert 'aria-disabled="true" title="Mercury does not read EIGRP">EIGRP<' in tools


def test_ports_labels_and_zoom(web):
    assert 'topo-ports-auto' in _get(web) and 'topo-ports-off' in _get(web, "&ports=off")
    assert _ports(_get(web, "&labels=off")) == [] and _chips(_get(web, "&labels=off")) == []
    # Labels auto: shown at Fit and closer, hidden zoomed out (C661: drawn, and hidden by the
    # browser's `topo-far` as the map is zoomed, so a zoom in the browser needs no redraw).
    far = _get(web, "&z=75")
    assert _ports(far) and 'topo-labels-auto topo-far' in far
    near = _get(web, "&z=150")
    assert _ports(near) and 'class="topo-map topo-z150 topo-labels-auto topo-ports' in near
    assert "topo-far" not in _get(web, "&labels=on&z=75").split('class="topo-map')[1][:60]


def _snap_button(html):
    return re.search(r'<a class="btn btn-small topo-wide( on)?" href="([^"]*)"[^>]*'
                     r'aria-pressed="(true|false)"[^>]*>Snap to grid</a>', html)


def test_snap_to_grid_is_a_switch_off_by_default(web):
    """C691, board E: Snap to grid is a toolbar switch in the page's address, off by default; on,
    the map carries its step and draws the grid and the landing outline; off, neither."""
    off = _get(web)
    btn = _snap_button(off)
    assert btn and btn.group(3) == "false" and "snap=1" in btn.group(2), btn
    assert "data-snap" not in off and "topo-grid" not in off and "topo-snapmark" not in off
    on = _get(web, "&snap=1")
    btn = _snap_button(on)
    assert btn and btn.group(1) == " on" and btn.group(3) == "true", btn
    assert "snap=" not in btn.group(2), "turning it off leaves the default out of the link"
    assert 'data-snap="40"' in on and 'id="topo-grid" width="40" height="40"' in on
    assert 'class="topo-snapmark"' in on and 'visibility="hidden"' in on
    # A saved move redraws the map with the switch kept: the move form posts the question.
    move = re.search(r'<form id="topo-move"[^>]*action="([^"]*)"', on).group(1)
    assert "snap=1" in move
    # Anything but "1" is off, never an error.
    assert "data-snap" not in _get(web, "&snap=yes")


def test_snap_lands_on_the_nearest_grid_point_never_the_edge():
    """The pure rule the drop and Alt-arrow use, executed from the shipped script."""
    import dukpy
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "static", "js", "nmas_topology.js"), encoding="utf-8").read()
    got = dukpy.evaljs("var window = {};\n" + src + "\n[window.NMAS_TOPOLOGY.snapTo(57, 40),"
                       " window.NMAS_TOPOLOGY.snapTo(61, 40), window.NMAS_TOPOLOGY.snapTo(80, 40),"
                       " window.NMAS_TOPOLOGY.snapTo(5, 40), window.NMAS_TOPOLOGY.snapTo(-90, 40)]")
    assert got == [40, 80, 80, 40, 40], got


def test_a_down_link_is_thick_red_chipped_and_names_its_end(web):
    res, up = _capture()
    for row in res["r1"]["ifOperStatus"]:
        if row["metric"]["ifName"] == "Gi2":
            row["value"] = [row["value"][0], "2"]
    _store(_value(res, up))
    html = _get(web)
    assert ("bad", "down") in _chips(html)
    att = _section(html, "topo-att-h")
    assert "Down, or an intended neighbour missing (1)" in att
    assert "r1 Gi2 ↔ s3 Gi1/0" in att and "link down at r1" in att


def _fake_reads(monkeypatch, answers=None):
    """The reads engine answering from the captured `show ip cef` answers (C693's fixture),
    recording what it was asked; every other step of the trace is the real one."""
    from tests.test_path_trace import _fx
    answers = answers or _fx()["answers"]
    asked = []

    def run(list_name, hosts, commands, actor, **kw):
        asked.append((list(hosts), commands, actor, kw.get("purpose")))
        return {"id": f"run-{len(asked)}", "results": {
            h: {"state": "answered", "answers": [{"command": c, "state": "answered",
                                                  "answer": answers[h][c]} for c in commands]}
            for h in hosts}}
    monkeypatch.setattr("modules.nsot.reads.run", run)
    return asked


def _trace_post(web, a="r1", b="198.51.100.1", hx=True):
    from modules.nsot import capture_job
    r = web["client"].post("/v2/topology/path", data={"list": "Lab", "a": a, "b": b},
                           headers={"HX-Request": "true"} if hx else {})
    for job in list(capture_job._jobs):
        capture_job.wait(job, 10)
    return r


def test_path_offers_the_routing_devices_and_r5_by_each_peering(web):
    form = _get(web)
    to = re.search(r'<select id="topo-b"[^>]*>(.*?)</select>', form, re.S).group(1)
    assert '<option value="198.51.100.1">r5 (outside, AS 65002): 198.51.100.1, r3&#39;s peering' \
        in to
    assert '<option value="198.51.100.3">r5 (outside, AS 65002): 198.51.100.3, r4&#39;s peering' \
        in to
    frm = re.search(r'<select id="topo-a"[^>]*>(.*?)</select>', form, re.S).group(1)
    assert "<option>r1</option>" in frm and "<option>r6</option>" not in frm
    assert 'hx-post="/v2/topology/path"' in form and "Trace the path" in form


def test_a_trace_is_the_path_packets_take_read_hop_by_hop(web, monkeypatch):
    asked = _fake_reads(monkeypatch)
    r = _trace_post(web)
    assert r.status_code == 200
    there = r.headers["HX-Push-Url"]
    assert there.startswith("/v2/topology?list=Lab&a=r1&b=198.51.100.1&trace=")
    assert [h for h, *_ in asked] == [["r1"], ["r3", "r4"]]
    assert asked[0][1:] == (["show ip cef 198.51.100.1"], "test-person@example.invalid",
                            "Path: r1 to 198.51.100.1")
    html = _get(web, "&" + there.split("?", 1)[1].split("&", 1)[1])
    card = _section(html, "topo-trace-h")
    assert ("r1 to r5 (outside, AS 65002): 198.51.100.1, r3&#39;s peering: 2 equal-cost "
            "branches, 1 delivers, 1 does not") in card
    assert "1 of 2 branches not delivered" in card
    assert "dropped at r4: no route to 198.51.100.1" in card and "delivered to r5" in card
    assert "across s3, s4 <span class=\"faint\">(layer 2, not read)</span>" in card
    assert "0.0.0.0/0, next hop 10.255.3.14 (r4) out Gi2" in card
    assert "198.51.100.1/32 attached to Gi2: r5&#39;s address" in card
    assert "r3 to r5, cabled directly" in card
    assert "Read <time" in card and "from r1, r3, r4 (2 reads" in card
    # The map: the delivered branch on, the dropped one in red, the switched hops dashed.
    assert html.count("topo-pathglow topo-path-on") == 3
    assert html.count("topo-pathglow topo-path-drop") == 2
    assert html.count("topo-path-l2") == 4
    assert 'topo-onpath topo-onpath-drop" data-node="r4"' in html.replace(
        " topo-outside", "").replace(" topo-spof", "")
    # The region listens for the trace while one is shown, and Trace again carries it.
    assert "nmas:topology from:body, nmas:path_trace from:body" in html
    assert "Trace again" in card


def test_a_trace_beyond_the_network_says_it_leaves_and_is_not_red(web, monkeypatch):
    """C696: r1 to 8.8.8.8, both branches handed to r5 (the captured answers)."""
    with open(os.path.join(os.path.dirname(__file__), "fixtures", "path",
                           "cef_beyond_r5.json"), encoding="utf-8") as fh:
        _fake_reads(monkeypatch, json.load(fh)["answers"])
    there = _trace_post(web, b="8.8.8.8").headers["HX-Push-Url"]
    html = _get(web, "&" + there.split("?", 1)[1].split("&", 1)[1])
    card = _section(html, "topo-trace-h")
    assert "r1 to 8.8.8.8: 2 equal-cost branches, 2 leave the network toward r5</h2>" in card
    assert "not delivered" not in card and "topo-trace-drop" not in card
    assert card.count(">leaves the network</span>") == 3
    assert "topo-path-drop" not in html and html.count("topo-pathglow topo-path-out") >= 3


def test_a_running_trace_is_busy_on_its_button(web, monkeypatch):
    from modules import path_trace
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(web["dir"]))
    path_trace._write("Lab", {"id": "a" * 32, "state": "running", "source": "r1",
                              "dest": "198.51.100.1", "dest_words": "198.51.100.1",
                              "reading": ["r3", "r4"], "read": ["r1"], "runs": [],
                              "branches": [], "started_at": 1760000000.0})
    html = _get(web, f"&a=r1&b=198.51.100.1&trace={'a' * 32}")
    assert '<button type="button" class="btn btn-small" data-op="path-trace" disabled aria-busy="true">Tracing… ' \
           'reading r3, r4</button>' in html
    assert "Reading r3, r4 now" in _section(html, "topo-trace-h")
    assert "Trace again" not in html


def test_a_refused_trace_names_both_sides_and_asks_nothing(web, monkeypatch):
    asked = _fake_reads(monkeypatch)
    r = _trace_post(web, a="r6")
    body = r.get_data(as_text=True)
    assert r.status_code == 400 and not asked
    assert ("Not traced:</strong> From is &#39;r6&#39;, which is not one of this network&#39;s "
            "routing devices (r1, r2, r3, r4, s1, s2, s3, s4). Nothing was asked") in body
    assert not (web["dir"] / "paths").exists()


def test_a_trace_id_with_no_record_and_an_unreadable_one_say_so(web):
    html = _get(web, f"&trace={'b' * 32}")
    assert "There is no recorded trace" in _section(html, "topo-trace-h")
    (web["dir"] / "paths").mkdir()
    (web["dir"] / "paths" / ("c" * 32 + ".json")).write_text("{")
    html = _get(web, f"&trace={'c' * 32}")
    assert "The trace's record cannot be read" in _section(html, "topo-trace-h")
    assert "There is no recorded trace" in _section(_get(web, "&trace=../x"), "topo-trace-h")


def test_a_what_if_names_who_loses_the_rest(web):
    panel = _section(_get(web, "&out=s3"), "topo-wi-h")
    assert "Mercury loses every device" in panel and "nothing was sent to a device" in panel
    panel = _section(_get(web, "&out=r6"), "topo-wi-h")
    assert "Nothing is cut off" in panel


def test_find_rings_what_matches_and_hides_nothing(web):
    html = _get(web, "&q=Gi1/0")
    assert "Found, ringed on the map:" in html and "topo-match" in html
    assert html.count('<g class="topo-n') == len(MANAGED) + 2       # r5 and Mercury too
    assert "Found, ringed on the map: r1" in _get(web, "&q=" + _r1_address())


def _r1_address():
    hv = _intents()["r1"]
    return next(i["ipv4"].split()[0] for i in hv["interfaces"] if i["name"] == "Loopback0")


def test_marking_an_island_expected_is_a_person_s_recorded_act(web):
    form = web["client"].get("/v2/topology/expected?list=Lab&device=r6").get_data(as_text=True)
    assert 'name="reason"' in form and "Mark r6 as expected" in form
    short = web["client"].post("/v2/topology/expected",
                               data={"list": "Lab", "device": "r6", "reason": "lab"})
    assert short.status_code == 400 and "say why r6 is apart" in short.get_data(as_text=True)
    assert not (web["dir"] / "topology_expected.json").exists()
    r = web["client"].post("/v2/topology/expected",
                           data={"list": "Lab", "device": "r6",
                                 "reason": "its own containerlab lab, cabled apart"})
    assert r.status_code == 200 and "r6 is an expected island" in r.get_data(as_text=True)
    stored = json.loads((web["dir"] / "topology_expected.json").read_text())
    assert stored["islands"]["r6"]["by"] == "test-person@example.invalid"
    log = (web["dir"] / "topology_expected_log.jsonl").read_text()
    assert '"action": "declared"' in log
    # The reader's next read draws it apart on purpose, with the reason, and warns nothing.
    _store(_value(expected={"r6": stored["islands"]["r6"]}))
    att = _section(_get(web), "topo-att-h")
    assert "Apart on purpose (1)" in att and "its own containerlab lab, cabled apart" in att
    assert "Weak points (1)" in att and "Withdraw" in att


def test_a_refusal_declares_no_change_and_a_success_does(web):
    """C656: a refused write wrote nothing, so its answer declares no invalidation (its keys made
    the page redraw the region showing the refusal's reason, wiping it); a declared island
    declares `topology`, and its result goes out of band to the slot above the map, which the
    redraw does not touch."""
    bad = web["client"].post("/v2/topology/expected",
                             data={"list": "Lab", "device": "r6", "reason": "lab"})
    assert bad.status_code == 400 and "X-NMAS-Invalidates" not in bad.headers
    ok = web["client"].post("/v2/topology/expected",
                            data={"list": "Lab", "device": "r6",
                                  "reason": "its own containerlab lab, cabled apart"})
    assert ok.headers.get("X-NMAS-Invalidates") == "topology"
    body = ok.get_data(as_text=True)
    assert '<div id="topo-result" aria-live="polite" hx-swap-oob="true">' in body
    assert body.index('<div id="topo" ') < body.index('id="topo-result"')
    slot = body[body.index('id="topo-result"'):]
    assert "r6 is an expected island" in slot
    page = web["client"].get("/v2/topology?list=Lab").get_data(as_text=True)
    assert '<div id="topo-result" aria-live="polite"></div>' in page


# --------------------------------------------------------------- C661: the network's layout

def _places(html):
    return {n: (float(x), float(y)) for n, x, y in
            re.findall(r'data-node="([^"]+)" data-x="([\d.]+)" data-y="([\d.]+)"', html)}


def test_no_bands_and_a_seeded_layout_a_refresh_does_not_move(web):
    """C661: no Access, Edge, Core or Management section on the map; the generated layout is the
    cabling's springs from a fixed seed, every device on the frame and none on another."""
    html = _get(web)
    assert "topo-bandrule" not in html and 'class="topo-band"' not in html
    first = _places(html)
    assert len(first) >= 10 and first == _places(_get(web))
    for (a, pa) in first.items():
        assert pa[0] >= 20 and pa[1] >= 20
        for b, pb in first.items():
            if a < b:
                assert ((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2) ** 0.5 >= 100, (a, b)
    assert "Reset layout" in html and 'aria-disabled="true" title="Nobody has moved a device' in html
    assert "Drag a device to move it" in html and 'data-topo-view="Lab"' in html


def _move(web, name, dx, dy, html=None):
    places = _places(html or _get(web))
    places[name] = (places[name][0] + dx, places[name][1] + dy)
    return web["client"].post("/v2/topology/positions", data={
        "list": "Lab", "moved": name,
        "positions": json.dumps({n: [x, y] for n, (x, y) in places.items()})}), places


def test_a_move_is_the_network_s_layout_for_everyone_and_recorded(web):
    r, places = _move(web, "r1", 140, 60)
    assert r.status_code == 200 and r.headers.get("X-NMAS-Invalidates") == "topology"
    stored = json.loads((web["dir"] / "topology_layout.json").read_text())
    assert stored["by"] == "test-person@example.invalid"
    assert stored["positions"]["r1"] == [round(places["r1"][0]), round(places["r1"][1])]
    log = [json.loads(l) for l in (web["dir"] / "topology_layout_log.jsonl").read_text()
           .splitlines()]
    assert log[-1]["action"] == "moved" and log[-1]["device"] == "r1"
    html = _get(web)
    assert _places(html)["r1"] == tuple(float(v) for v in stored["positions"]["r1"])
    assert "Arranged by test-person@example.invalid" in html
    # A move draws no notice: its result is the device where it was dropped (no narration).
    assert "set-result" not in r.get_data(as_text=True).split('id="topo-result"')[-1]
    # History: the move, by whom, on the network's History and on r1's own.
    from modules import history_sources as H

    class Ref:
        data_dir = str(web["dir"])
    ctx = {"ref": Ref(), "device": "", "since": None, "members": None}
    (event,) = H.topology_layout(ctx)["events"]
    assert event["what"].startswith("r1 moved on Topology to (") and event["kind"] == "layout"
    assert event["who"] == "test-person@example.invalid" and event["devices"] == ["r1"]
    assert H.topology_layout(dict(ctx, device="r1"))["events"]
    assert not H.topology_layout(dict(ctx, device="r2"))["events"]


def test_a_device_the_layout_lacks_is_placed_near_its_neighbours_and_no_arranged_one_moves(web):
    """The decision: a new device is placed near its neighbours without moving arranged ones.
    Planted: the layout saved without r2, as if r2 had been added since."""
    html = _get(web)
    places = _places(html)
    held = {n: [x + 30, y + 30] for n, (x, y) in places.items() if n != "r2"}
    r = web["client"].post("/v2/topology/positions", data={
        "list": "Lab", "moved": "r1", "positions": json.dumps(held)})
    assert r.status_code == 200
    now = _places(_get(web))
    assert all(now[n] == (float(x), float(y)) for n, (x, y) in held.items())
    assert "r2" in now and now["r2"] != places["r2"]


def test_the_layout_is_the_same_every_time_and_keeps_devices_apart():
    """The seed: a device the shared layout lacks lands in the same place on every call (it
    starts at a seeded angle from its neighbours); and no two devices end closer than MIN_GAP,
    planted: two placed on the same spot with a third to settle."""
    from modules import topology_layout as L
    nodes = {n: {} for n in ("hub", "a", "b", "c", "new")}
    phys = [{"a": "hub", "b": x} for x in ("a", "b", "c", "new")]
    placed = {"hub": (400, 300), "a": (250, 300), "b": (550, 300), "c": (400, 150)}
    first = L.layout(nodes, phys, placed)["positions"]["new"]
    assert all(L.layout(nodes, phys, placed)["positions"]["new"] == first for _ in range(3))
    pushed = L._apart({"x": (100.0, 100.0), "y": (100.0, 100.0), "z": (104.0, 100.0)})
    for p, q in (("x", "y"), ("x", "z"), ("y", "z")):
        d = ((pushed[p][0] - pushed[q][0]) ** 2 + (pushed[p][1] - pushed[q][1]) ** 2) ** 0.5
        assert d >= 100, (p, q, d)          # a name under each icon: about 100 units


def test_the_grid_finds_exactly_the_near_pairs():
    """C670: the spring layout's grid variant repels only devices within REPEL_WITHIN
    spacings, found through a grid of cells; it must find exactly the pairs closer than the
    radius, each once, never a far one. Planted: 300 random places, against every pair."""
    import random

    from modules import topology_layout as L
    rng = random.Random(5)
    pos = {f"d{i}": (rng.uniform(-900, 2900), rng.uniform(-400, 2400)) for i in range(300)}
    names = sorted(pos)
    radius = 340.0
    got = list(L._near_pairs(pos, names, radius))
    want = {(a, b) for i, a in enumerate(names) for b in names[i + 1:]
            if (pos[a][0] - pos[b][0]) ** 2 + (pos[a][1] - pos[b][1]) ** 2 < radius ** 2}
    assert len(got) == len(set(got)) and set(got) == want and len(want) > 100


@pytest.mark.parametrize("positions,moved,words", [
    ({"r9": [10, 10]}, "r9", "'r9' is not on this network's map"),
    ({"r1": [10]}, "r1", "r1's place is not two numbers"),
    ({"r1": [10, 99999]}, "r1", "outside the map's frame"),
    ({"r1": [100, 100]}, "r2", "the device moved, 'r2', is not among the places sent"),
])
def test_a_move_that_is_not_the_map_s_is_refused_writing_nothing(web, positions, moved, words):
    r = web["client"].post("/v2/topology/positions", data={
        "list": "Lab", "moved": moved, "positions": json.dumps(positions)})
    assert r.status_code == 400 and "X-NMAS-Invalidates" not in r.headers
    assert words in r.get_data(as_text=True).replace("&#39;", "'")
    assert not (web["dir"] / "topology_layout.json").exists()


def test_an_unreadable_layout_refuses_a_move_and_draws_the_generated_one(web):
    generated = _places(_get(web))
    (web["dir"] / "topology_layout.json").write_text("{not json")
    html = _get(web)
    assert "The saved layout cannot be read" in html and _places(html) == generated
    r, _ = _move(web, "r1", 10, 10, html)
    assert r.status_code == 409 and "nothing was written" in r.get_data(as_text=True)
    assert (web["dir"] / "topology_layout.json").read_text() == "{not json"


#: Today's (v1) Topology page's own layout, its shape as the host's Default network held it
#: (read 2026-10-11 through topology_positions.read, shapes only): places as {x, y}, a hidden
#: list, no who or when. Coordinates planted.
V1_LAYOUT = {"positions": {"r1": {"x": 412.5, "y": -80.25}, "s3": {"x": 10, "y": 220}},
             "hidden": []}


def test_today_s_layout_file_is_not_this_page_s_and_never_breaks_it(web):
    """The operator's report, 2026-10-11 03:46 UTC: /v2/topology failed whole, "KeyError: 0".
    The v2 layout had taken the file name today's page keeps its layout in, and read v1's
    {x, y} places as its own. Now each has its own file: v1's is not read here at all."""
    generated = _places(_get(web))
    (web["dir"] / "topology_positions.json").write_text(json.dumps(V1_LAYOUT))
    for path in ("/v2/topology?list=Lab", "/v2/topology/map?list=Lab"):
        r = web["client"].get(path)
        assert r.status_code == 200, path
    html = _get(web)
    assert _places(html) == generated and "cannot be read" not in html


def test_odd_saved_places_draw_the_generated_layout_and_say_why(web, monkeypatch):
    """The page never fails whole because one part's data is odd: places that are not two
    numbers make the saved layout unreadable, named; the generated layout is drawn; Reset sets
    the file aside under a dated name (kept) and records it. A layout step that raises for any
    other reason draws the generated layout too."""
    generated = _places(_get(web))
    (web["dir"] / "topology_layout.json").write_text(json.dumps(V1_LAYOUT))
    for path in ("/v2/topology?list=Lab", "/v2/topology/map?list=Lab"):
        assert web["client"].get(path).status_code == 200, path
    html = _get(web)
    assert _places(html) == generated
    assert "r1&#39;s place is not two numbers (a dict)" in html
    assert 'title="The saved layout cannot be read: Reset sets it aside' in html
    r = web["client"].post("/v2/topology/positions/reset", data={"list": "Lab"})
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "is set aside as" in body
    aside = [p.name for p in web["dir"].iterdir()
             if p.name.startswith("topology_layout.json.unreadable-")]
    assert len(aside) == 1 and aside[0].startswith("topology_layout.json.unreadable-")
    assert json.loads((web["dir"] / aside[0]).read_text()) == V1_LAYOUT
    assert '"set_aside"' in (web["dir"] / "topology_layout_log.jsonl").read_text()
    r, _ = _move(web, "r1", 30, 30)
    assert r.status_code == 200, "a move is saved again once the layout is set aside"
    # Any other failure laying out saved places: drawn as generated, said, never a 500.
    monkeypatch.setattr("modules.topology_page.layout",
                        lambda nodes, phys, placed=None: (_ for _ in ()).throw(KeyError(0))
                        if placed else __import__("modules.topology_layout").topology_layout
                        .layout(nodes, phys))
    r = web["client"].get("/v2/topology?list=Lab")
    assert r.status_code == 200 and "its places could not be drawn (0)" in \
        r.get_data(as_text=True)


def test_reset_withdraws_every_move_for_everyone_recorded(web):
    generated = _places(_get(web))
    _move(web, "r1", 140, 60)
    assert _places(_get(web)) != generated
    html = _get(web)
    assert 'action="/v2/topology/positions/reset' in html
    r = web["client"].post("/v2/topology/positions/reset", data={"list": "Lab"})
    assert r.status_code == 200 and "The layout is reset" in r.get_data(as_text=True)
    assert not (web["dir"] / "topology_layout.json").exists()
    assert _places(_get(web)) == generated
    assert '"action": "reset"' in (web["dir"] / "topology_layout_log.jsonl").read_text()


@pytest.mark.real_identity
def test_no_person_moves_nothing(web):
    r, _ = _move(web, "r1", 10, 10)
    assert r.status_code in (401, 403)
    assert not (web["dir"] / "topology_layout.json").exists()


def test_drag_pan_and_zoom_in_a_browser(web):
    """A real pointer (WebDriver's actions) at 1440: dragging empty space pans (the view box
    moves, nothing is saved); the wheel zooms at the pointer (the view box shrinks, the % says
    so, Labels Auto hide when zoomed out); dragging r1 moves it, its lines follow, and the drop
    saves the map for everyone. At 390 a drag on a device pans and moves nothing."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A

    def actions(b, origin, steps):
        b._call("POST", f"/session/{b.session}/actions", {"actions": [{
            "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
            "actions": [{"type": "pointerMove", "origin": origin, "x": 0, "y": 0}] + steps}]})
        b._call("DELETE", f"/session/{b.session}/actions")

    def view(b):
        return b.js("return document.querySelector('svg.topo-map').getAttribute('viewBox')")

    def element(b, css):
        return b._call("POST", f"/session/{b.session}/element", {"using": "css selector",
                                                                  "value": css})

    with browser.Served(A.app) as srv, browser.Browser() as b:
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
        b.go(srv.url("/v2/topology?list=Lab"))
        b.wait_for("return window.NMAS_TOPOLOGY && document.querySelector('svg.topo-map')")
        before = view(b)
        # A pan from the map's empty top-left corner.
        actions(b, element(b, "[data-topo-view]"), [
            {"type": "pointerMove", "origin": "pointer", "x": -300, "y": -150},
            {"type": "pointerDown", "button": 0},
            {"type": "pointerMove", "origin": "pointer", "x": 80, "y": 50, "duration": 150},
            {"type": "pointerUp", "button": 0}])
        panned = view(b)
        assert panned != before and panned.split()[2:] == before.split()[2:], (before, panned)
        assert not (web["dir"] / "topology_layout.json").exists()
        # The wheel zooms in at the pointer: the view box shrinks; out past fit, labels hide.
        b._call("POST", f"/session/{b.session}/actions", {"actions": [{
            "type": "wheel", "id": "wheel", "actions": [{
                "type": "scroll", "origin": element(b, "[data-topo-view]"), "x": 0, "y": 0,
                "deltaX": 0, "deltaY": -300}]}]})
        assert float(view(b).split()[2]) < float(panned.split()[2])
        assert b.js("return document.querySelector('[data-topo-zoom=\"fit\"]').textContent") \
            != "100%"
        b.click('[data-topo-zoom="fit"]')
        b.click('[data-topo-zoom="out"]')
        assert b.js("return document.querySelector('svg.topo-map')"
                    ".classList.contains('topo-far')")
        b.click('[data-topo-zoom="fit"]')
        # A device dragged: it moves, its lines follow straight, the drop saves.
        x0 = b.js("return +document.querySelector('[data-node=\"r1\"]').getAttribute('data-x')")
        actions(b, element(b, '[data-node="r1"] .topo-ic'), [
            {"type": "pointerDown", "button": 0},
            {"type": "pointerMove", "origin": "pointer", "x": 70, "y": 40, "duration": 200},
            {"type": "pointerUp", "button": 0}])
        b.wait_for("return document.body.textContent.indexOf('Arranged by') >= 0")
        stored = json.loads((web["dir"] / "topology_layout.json").read_text())
        assert stored["positions"]["r1"][0] > x0 + 20, (x0, stored["positions"]["r1"])
        assert b.js("return +document.querySelector('[data-node=\"r1\"]')"
                    ".getAttribute('data-x')") == stored["positions"]["r1"][0]
        # The phone: a drag on a device pans and moves nothing.
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 390, "height": 844})
        b.go(srv.url("/v2/topology?list=Lab&tab=map"))
        b.wait_for("return document.querySelector('svg.topo-map')")
        before = view(b)
        actions(b, element(b, '[data-node="r2"] .topo-ic'), [
            {"type": "pointerDown", "button": 0},
            {"type": "pointerMove", "origin": "pointer", "x": 40, "y": 30, "duration": 150},
            {"type": "pointerUp", "button": 0}])
        assert view(b) != before
        again = json.loads((web["dir"] / "topology_layout.json").read_text())
        assert again == stored


def test_a_drag_with_the_grid_on_lands_on_a_grid_point_in_a_browser(web):
    """C691, board E, with a real pointer at 1440: with Snap to grid on, the outline marks the
    landing point while r1 is dragged, and the drop saves r1 on a grid point (both coordinates
    multiples of 40); the redrawn map keeps the switch on."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A

    def element(b, css):
        return b._call("POST", f"/session/{b.session}/element", {"using": "css selector",
                                                                  "value": css})

    with browser.Served(A.app) as srv, browser.Browser() as b:
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
        b.go(srv.url("/v2/topology?list=Lab&snap=1"))
        b.wait_for("return window.NMAS_TOPOLOGY && document.querySelector('svg.topo-map')")
        b._call("POST", f"/session/{b.session}/actions", {"actions": [{
            "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
            "actions": [{"type": "pointerMove", "origin": element(b, '[data-node="r1"] .topo-ic'),
                         "x": 0, "y": 0},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pointerMove", "origin": "pointer", "x": 57, "y": 23,
                         "duration": 200}]}]})
        assert b.js("return document.querySelector('.topo-snapmark')"
                    ".getAttribute('visibility')") == "visible"
        b._call("POST", f"/session/{b.session}/actions", {"actions": [{
            "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
            "actions": [{"type": "pointerUp", "button": 0}]}]})
        b._call("DELETE", f"/session/{b.session}/actions")
        b.wait_for("return document.body.textContent.indexOf('Arranged by') >= 0")
        x, y = json.loads((web["dir"] / "topology_layout.json").read_text())["positions"]["r1"]
        assert x % 40 == 0 and y % 40 == 0, (x, y)
        assert b.js("return document.querySelector('svg.topo-map').getAttribute('data-snap')") \
            == "40"


# C882 (the operator's walk W1, 2026-10-16): with Snap to grid on, a dragged device stuttered and
# landed far from the pointer, saved for everyone and recorded. Measured in a real browser: the
# map region redrew under the pointer (`topology` announced, or the last drop's save answering),
# the drag went on moving the replaced map, whose screen offset was gone (getScreenCTM's e and f
# 281 and 297 before, 0 and 60 detached), and the drop saved r1 at (760, 880) with the pointer
# over (406, 555). The guard is static/js/nmas_drag.js, shared with any draggable list.

#: What each browser test watches: the pointer's last place and where it went down, the map's
#: requests as they finish, and r1's element as first drawn (a redraw replaces it).
_WATCH = """
window.__ptr = null; window.__down = null; window.__done = []; window.__r1 = null;
document.addEventListener('pointermove', function (e) { window.__ptr = [e.clientX, e.clientY]; },
                          true);
document.addEventListener('pointerdown', function (e) { window.__down = [e.clientX, e.clientY];
  var g = document.querySelector('svg.topo-map [data-node="r1"]');
  window.__at = [+g.getAttribute('data-x') + +(g.getAttribute('data-dx') || 0),
                 +g.getAttribute('data-y') + +(g.getAttribute('data-dy') || 0)]; }, true);
document.addEventListener('htmx:afterRequest', function (e) {
  window.__done.push(e.detail.requestConfig.verb.toUpperCase() + ' ' +
                     e.detail.pathInfo.requestPath); });
window.__r1 = document.querySelector('svg.topo-map [data-node="r1"]');
"""

#: Where the pointer says r1 lands, read from the browser's own geometry, never the script's
#: drag state: the pointer's map place plus where on r1 it went down, on the map as drawn now.
_WANT = """
var s = document.querySelector('svg.topo-map'), m = s.getScreenCTM().inverse();
function at(c) { var p = s.createSVGPoint(); p.x = c[0]; p.y = c[1]; p = p.matrixTransform(m);
                 return [p.x, p.y]; }
var now = at(window.__ptr), down = at(window.__down);
return [now[0] + window.__at[0] - down[0], now[1] + window.__at[1] - down[1]];
"""


def _pointer(b, steps):
    b._call("POST", f"/session/{b.session}/actions", {"actions": [{
        "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
        "actions": steps}]})


def _element(b, css):
    return b._call("POST", f"/session/{b.session}/element", {"using": "css selector",
                                                              "value": css})


def _rows(web):
    log = web["dir"] / "topology_layout_log.jsonl"
    return log.read_text().splitlines() if log.exists() else []


def _dot(v):
    """The grid point nearest *v*, never nearer the edge than one step (board E's rule, worked
    here from the step, independent of the script's snapTo)."""
    return max(40, int(round(v / 40.0)) * 40)


def _open_snapped(b, srv):
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
    b.go(srv.url("/v2/topology?list=Lab&snap=1"))
    b.wait_for("return window.NMAS_TOPOLOGY && window.NMAS_DRAG && "
               "document.querySelector('svg.topo-map')")
    b.js(_WATCH)


def test_an_announcement_mid_drag_waits_for_the_drop_in_a_browser(web):
    """C882: r1 dragged with Snap to grid on while `topology` is announced (another person's
    move, the reader's minute). The map is asked again and the answer arrives mid-drag, but
    nothing is redrawn under the pointer: r1 is the element first drawn, where the pointer has
    it. On the drop it lands on the dot under the pointer, and exactly one layout row is
    saved."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        _open_snapped(b, srv)
        _pointer(b, [{"type": "pointerMove", "origin": _element(b, '[data-node="r1"] .topo-ic'),
                      "x": 3, "y": -4},
                     {"type": "pointerDown", "button": 0},
                     {"type": "pointerMove", "origin": "pointer", "x": 30, "y": 10,
                      "duration": 100}])
        b.js("htmx.trigger(document.body, 'nmas:topology')")
        b.wait_for("return window.__done.some(function (r) {"
                   " return r.indexOf('GET /v2/topology/map') === 0; })")
        assert b.js("return window.__r1.isConnected"), "the map was redrawn under the pointer"
        _pointer(b, [{"type": "pointerMove", "origin": "pointer", "x": 90, "y": 60,
                      "duration": 200}])
        want = b.js(_WANT)
        drawn = b.js("var g = window.__r1; return [+g.getAttribute('data-x') + "
                     "+g.getAttribute('data-dx'), +g.getAttribute('data-y') + "
                     "+g.getAttribute('data-dy')]")
        assert abs(drawn[0] - want[0]) <= 1 and abs(drawn[1] - want[1]) <= 1, (drawn, want)
        _pointer(b, [{"type": "pointerUp", "button": 0}])
        b._call("DELETE", f"/session/{b.session}/actions")
        b.wait_for("return !window.__r1.isConnected && "
                   "document.body.textContent.indexOf('Arranged by') >= 0")
        stored = json.loads((web["dir"] / "topology_layout.json").read_text())["positions"]
        assert stored["r1"] == [_dot(want[0]), _dot(want[1])], (stored["r1"], want)
        time.sleep(1.0)       # the save's own announcement redraws; nothing more is saved
        assert len(_rows(web)) == 1, _rows(web)
        assert b.js("var g = document.querySelector('svg.topo-map [data-node=\"r1\"]');"
                    "return [+g.getAttribute('data-x'), +g.getAttribute('data-y')]") \
            == stored["r1"]


def test_a_save_answering_mid_drag_waits_for_the_next_drop_in_a_browser(web, monkeypatch):
    """C882, the walk's own sequence: r1 dropped, and dragged again before the save answers
    (held 0.8 s here). The answer arrives mid-drag and waits; the second drop lands on the dot
    under the pointer; two drops, two layout rows."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules import topology_positions
    real = topology_positions.save

    def slow(*a, **k):
        time.sleep(0.8)
        return real(*a, **k)
    monkeypatch.setattr(topology_positions, "save", slow)
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        _open_snapped(b, srv)
        _pointer(b, [{"type": "pointerMove", "origin": _element(b, '[data-node="r1"] .topo-ic'),
                      "x": 0, "y": 0},
                     {"type": "pointerDown", "button": 0},
                     {"type": "pointerMove", "origin": "pointer", "x": 50, "y": 0,
                      "duration": 100},
                     {"type": "pointerUp", "button": 0},
                     {"type": "pointerDown", "button": 0},
                     {"type": "pointerMove", "origin": "pointer", "x": 10, "y": 10,
                      "duration": 50}])
        b.js("window.__r1 = document.querySelector('svg.topo-map [data-node=\"r1\"]')")
        b.wait_for("return window.__done.some(function (r) {"
                   " return r.indexOf('POST /v2/topology/positions') === 0; })")
        assert b.js("return window.__r1.isConnected"), "the save's answer redrew mid-drag"
        _pointer(b, [{"type": "pointerMove", "origin": "pointer", "x": 90, "y": 60,
                      "duration": 200}])
        want = b.js(_WANT)
        _pointer(b, [{"type": "pointerUp", "button": 0}])
        b._call("DELETE", f"/session/{b.session}/actions")
        b.wait_for("return !window.__r1.isConnected && window.__done.filter(function (r) {"
                   " return r.indexOf('POST /v2/topology/positions') === 0; }).length === 2")
        stored = json.loads((web["dir"] / "topology_layout.json").read_text())["positions"]
        assert stored["r1"] == [_dot(want[0]), _dot(want[1])], (stored["r1"], want)
        time.sleep(1.0)
        assert len(_rows(web)) == 2, _rows(web)


def test_a_drop_far_from_the_pointer_is_refused_and_put_back_in_a_browser(web):
    """C882's second rule, client-side, where the pointer is known: a drop whose place is more
    than one grid step from where the pointer let go is refused, said above the map naming both
    places, r1 put back, nothing saved. Planted: r1's origin moved 300 units under the drag (what
    the operator first suspected a redraw did)."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        _open_snapped(b, srv)
        _pointer(b, [{"type": "pointerMove", "origin": _element(b, '[data-node="r1"] .topo-ic'),
                      "x": 0, "y": 0},
                     {"type": "pointerDown", "button": 0},
                     {"type": "pointerMove", "origin": "pointer", "x": 30, "y": 10,
                      "duration": 100}])
        b.js("var g = window.__r1; g.setAttribute('data-x', +g.getAttribute('data-x') + 300)")
        _pointer(b, [{"type": "pointerMove", "origin": "pointer", "x": 40, "y": 20,
                      "duration": 100},
                     {"type": "pointerUp", "button": 0}])
        b._call("DELETE", f"/session/{b.session}/actions")
        b.wait_for("return document.querySelector('#topo-result [role=alert]')")
        said = b.js("return document.getElementById('topo-result').textContent")
        assert re.search(r"Not moved: r1 would have landed at \(\d+, \d+\), but the pointer let "
                         r"go over \(\d+, \d+\): \d+ map units apart, more than one grid step "
                         r"\(40\); nothing was saved\. Drag it again\.", said), said
        assert b.js("return window.__r1.getAttribute('data-dx')") == "0"
        time.sleep(0.5)
        assert not (web["dir"] / "topology_layout.json").exists() and not _rows(web)
        assert not any("positions" in r for r in b.js("return window.__done"))


def test_a_pan_that_ends_asks_again_for_what_waited_in_a_browser(web):
    """C882: a press on the map's empty space holds it too; an announcement answered during the
    pan waits, and when the pointer comes up the map asks again and is redrawn (nothing saved)."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        _open_snapped(b, srv)
        _pointer(b, [{"type": "pointerMove", "origin": _element(b, "[data-topo-view]"),
                      "x": -300, "y": -150},
                     {"type": "pointerDown", "button": 0},
                     {"type": "pointerMove", "origin": "pointer", "x": 40, "y": 20,
                      "duration": 100}])
        b.js("htmx.trigger(document.body, 'nmas:topology')")
        b.wait_for("return window.__done.length >= 1")
        assert b.js("return window.__r1.isConnected")
        _pointer(b, [{"type": "pointerUp", "button": 0}])
        b._call("DELETE", f"/session/{b.session}/actions")
        b.wait_for("return !window.__r1.isConnected")
        assert not (web["dir"] / "topology_layout.json").exists()


def test_the_drag_guard_s_far_rule_and_the_map_s_step():
    """The shared guard's pure rule (static/js/nmas_drag.js), executed from the shipped script:
    per axis, within the limit passes (a diagonal step included), past it names how far; one
    axis serves a list's index (C905). The map's limit is one grid step (topology_page.GRID)."""
    import dukpy

    from modules import topology_page
    js = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "js")
    drag = open(os.path.join(js, "nmas_drag.js"), encoding="utf-8").read()
    got = dukpy.evaljs("var window = {};\n" + drag + "\nvar f = window.NMAS_DRAG.far;"
                       "[f([40, 40], [40, 40], 40), f([80, 80], [40, 40], 40),"
                       " f([121, 40], [40, 40], 40), f([40, 760], [40, 400], 40),"
                       " f([3], [1], 1), f([2], [1], 1)]")
    assert got == [None, None, {"by": 81, "limit": 40}, {"by": 360, "limit": 40},
                   {"by": 2, "limit": 1}, None], got
    topo = open(os.path.join(js, "nmas_topology.js"), encoding="utf-8").read()
    assert dukpy.evaljs("var window = {};\n" + topo + "\nwindow.NMAS_TOPOLOGY.FAR") \
        == topology_page.GRID == 40


def test_a_map_taller_than_its_box_opens_whole_at_100_with_its_labels(web):
    """C661's walk on the host: the host's layout is taller than the map's box, the fit is set
    by the height, and the first view read 93% (widths alone), hiding Labels Auto. Planted: the
    captures' devices placed down a tall column."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    value = _value()
    net = value["networks"]["Lab"]
    names = sorted(net["nodes"])
    net["layout"] = {"positions": {n: [200 + (i % 2) * 300, 80 + i * 140]
                                   for i, n in enumerate(names)},
                     "width": 880, "height": 80 + len(names) * 140 + 90, "placed": []}
    _store(value)
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
        b.go(srv.url("/v2/topology?list=Lab"))
        b.wait_for("return window.NMAS_TOPOLOGY && document.querySelector('svg.topo-map')")
        assert b.js("return document.querySelector('[data-topo-zoom=\"fit\"]').textContent") \
            == "100%"
        assert not b.js("return document.querySelector('svg.topo-map')"
                        ".classList.contains('topo-far')")


def test_a_selected_link_s_card_closes_and_is_smaller_in_a_browser(web):
    """C668: a link selected from Needs attention holds its card open; a click on the map's empty
    space, Escape, or the card's own × closes it (the selection gone from the region); the card is
    250 map units wide, not 320."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    # No RIP read: r1-s1 and r2-s2 have no second witness, so Needs attention lists them.
    _store(_value(rip={}))
    html = _get(web)
    sel = re.search(r'class="topo-ent[^"]*"[^>]*href="[^"]*sel=([^&"]+)', html).group(1)
    assert 'width="250"' in _get(web, f"&sel={sel}") and 'width="320"' not in html
    assert 'class="topo-cardx"' in _get(web, f"&sel={sel}") and 'class="topo-cardx"' not in html
    import app as A

    def selected(b):
        return b.js("return !!document.querySelector('.topo-l.topo-sel')")

    with browser.Served(A.app) as srv, browser.Browser() as b:
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
        for how in ("click", "escape"):
            b.go(srv.url(f"/v2/topology?list=Lab&sel={sel}&tab=map"))
            b.wait_for("return window.NMAS_TOPOLOGY && document.querySelector('.topo-l.topo-sel')")
            assert selected(b)
            if how == "click":
                # The map's empty top-left corner: no device, link or card there.
                el = b._call("POST", f"/session/{b.session}/element",
                             {"using": "css selector", "value": "[data-topo-view]"})
                b._call("POST", f"/session/{b.session}/actions", {"actions": [{
                    "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
                    "actions": [{"type": "pointerMove", "origin": el, "x": -330, "y": -170},
                                {"type": "pointerDown", "button": 0},
                                {"type": "pointerUp", "button": 0}]}]})
            else:
                b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', "
                     "bubbles: true})); return 1")
            b.wait_for("return !document.querySelector('.topo-l.topo-sel')")
            assert "sel=" not in b.js("return location.search"), how


@pytest.mark.real_identity
def test_no_person_declares_nothing(web):
    r = web["client"].post("/v2/topology/expected",
                           data={"list": "Lab", "device": "r6", "reason": "its own lab, apart"})
    assert r.status_code in (401, 403)
    assert not (web["dir"] / "topology_expected.json").exists()


def test_a_device_announced_name_is_escaped(web):
    res, up = _capture()
    row = json.loads(json.dumps(res["s1"]["lldpRemEntry"][0]))
    row["metric"]["lldpRemEntry"] = "<img src=x onerror=alert(1)>"
    res["s1"]["lldpRemEntry"].append(row)
    _store(_value(res, up))
    html = _get(web)
    assert "<img src=x" not in html and "&lt;img src=x onerror=alert(1)&gt;" in html


def test_a_value_stored_before_the_layout_still_draws(web):
    value = _value()
    del value["networks"]["Lab"]["layout"]
    _store(value)
    assert len(_ports(_get(web))) == 24


@pytest.mark.parametrize("value,ok,words", [
    (None, True, "The topology reader has not read yet"),
    ({"configured": False, "networks": {}, "errors": []}, True,
     "Prometheus is not configured"),
    ({"configured": True, "networks": {}, "errors": []}, True, "Lab was not in the reader"),
])
def test_each_state_has_its_words(web, value, ok, words):
    _store(value, ok)
    assert words in _get(web)


def test_an_unreadable_store_draws_nothing(web):
    with open(reader_job.store_path("topology-graph"), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    html = _get(web)
    assert "store cannot be read" in html and "<svg class=\"topo-map" not in html


#: Every drawn link against every device it does not join, measured by the browser on what it
#: drew: the path's points (every 2% of its length) against each device's icon, name and tags
#: as laid out (getBBox), independent of the geometry that placed them.
CROSSINGS_JS = """
var map = document.querySelector('svg.topo-map'), out = [];
var nodes = Array.prototype.map.call(map.querySelectorAll('g.topo-n'), function (g) {
  return {name: g.getAttribute('data-node'), boxes: Array.prototype.map.call(
    g.querySelectorAll('rect.topo-ic, text.topo-name, g.topo-tag rect'),
    function (e) { var b = e.getBBox(); return [b.x, b.y, b.x + b.width, b.y + b.height,
                                                e.getAttribute('class') || 'tag']; })};
});
var paths = map.querySelectorAll('path.topo-line');
Array.prototype.forEach.call(paths, function (p) {
  var a = p.getAttribute('data-a'), b = p.getAttribute('data-b'), len = p.getTotalLength();
  nodes.forEach(function (n) {
    if (n.name === a || n.name === b) return;
    n.boxes.forEach(function (bb) {
      for (var i = 1; i < 50; i++) {
        var pt = p.getPointAtLength(len * i / 50);
        if (pt.x >= bb[0] && pt.x <= bb[2] && pt.y >= bb[1] && pt.y <= bb[3]) {
          out.push(a + '-' + b + ' crosses ' + n.name + "'s " + bb[4]); return;
        }
      }
    });
  });
});
return [out, nodes.length, paths.length];
"""


#: The host's layout as its reader stored it (read 2026-10-11 00:08 UTC, the same device names
#: as the captures): r6 above r5 at the right, Mercury at the bottom; the straight line from
#: r6 to Mercury passes s2, and the old fixed bow carried it through r5's cloud and name.
HOST_LAYOUT = {"height": 669, "positions": {
    "@mercury": [440, 589], "r1": [440, 64], "r2": [187, 64], "r3": [187, 239],
    "r4": [440, 239], "r5": [693, 160], "r6": [693, 64], "s1": [725, 414], "s2": [535, 414],
    "s3": [155, 414], "s4": [345, 414]}}


def _with_mercury_on_r6(value):
    """The host's case (C659, read on the host 2026-10-11): Mercury's host also attached to r6
    Gi2, measured, on the host's own layout."""
    net = value["networks"]["Lab"]
    net["layers"]["physical"].append({
        "a": T.MANAGER, "b": "r6", "port_a": "eth1", "port_b": "Gi2", "kind": "address",
        "manager": True, "state": "up", "ends": {"r6": "up"}, "reported_by": [], "via": "Gi2",
        "vlan": "", "since": "2026-10-10T19:00:00Z", "since_seen": False, "speed": None,
        "witness": [], "down_at": []})
    net["layout"] = dict(net["layout"], height=HOST_LAYOUT["height"],
                         positions=dict(HOST_LAYOUT["positions"]))
    return value


@pytest.mark.parametrize("case", ["captures", "mercury-on-r6"])
def test_no_link_is_drawn_across_a_device_or_label_it_does_not_join(web, case):
    """C659: on the host, Mercury's link to r6 was bowed through r5's cloud and name, reading as
    r5 joined to Mercury. Measured in a real browser on what it drew, at the desktop board's
    width, Weak points on (their tags are labels too)."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    value = _value()
    if case == "mercury-on-r6":
        value = _with_mercury_on_r6(value)
    _store(value)
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
        b.go(srv.url("/v2/topology?list=Lab"))
        b.wait_for("return !!document.querySelector('svg.topo-map g.topo-n')", 10)
        crossings, n_nodes, n_paths = b.js(CROSSINGS_JS)
    assert n_nodes == len(MANAGED) + 2 and n_paths >= 12, (n_nodes, n_paths)
    assert not crossings, "\n".join(sorted(set(crossings)))
