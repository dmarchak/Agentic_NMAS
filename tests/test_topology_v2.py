"""OBSERVE › Topology on v2 (P.11 step 2), through the real routes and templates, drawing a stored
value the real reader built from the real captures (tests/test_topology_graph's fixtures: LLDP,
interfaces, routing tables, the fleet's configs with r5 retired, as on the host; Mercury's host
on s3 Vlan99's subnet, as the lab's is). What boards TopoDesktop and TopoPhone draw
(docs/fidelity/topology.md compares them region by region; this checks what each region holds):

- the header: the network, its counts and the read's age, Find, How does this work?;
- every link labelled with the PORT at each end, and the neighbourships it carries as chips with
  their key fact and state (OSPF and OSPFv3 area, BGP peer AS; the operator, 2026-10-10);
- each link's line class against intent, the legend's four styles and device classes; device
  icons, an L3 switch badged, r5 as an outside peer with its AS, Mercury's host where measured;
- Needs attention on the map: the one-sided links under "not as intended" with what is wrong,
  the weak points (s3 the single point of failure, through Mercury's port; r6 an island to look
  at); a group or a filter shows a subset and says so;
- a hover card per link, and a selected link's sheet (the phone's);
- the protocol toggles change what the links carry; Ports, Labels and zoom; RIPng shown as not
  read; a down link is thick and red, chipped "down", naming its end;
- a path trace and a what-if, each a claim about the stored graph;
- marking an island expected is a verified person's recorded act; with no person, nothing;
- a device-announced name with markup is escaped where drawn (the brief, Q16);
- no read stored, an unreadable store, Prometheus not configured: each its own words.
"""

import json
import os
import re

import pytest

from modules import reader_job
from modules.readers import topology_graph as T
from tests.test_topology_graph import MANAGED, _capture, _intents


def _here(intents):
    """Mercury's host as on the lab's: an address in s3 Vlan99's subnet (the NMAS management
    segment), derived from the captured config, never typed."""
    import ipaddress
    svi = next(i for i in intents["s3"]["interfaces"] if i["name"] == "Vlan99")
    net = ipaddress.ip_interface("/".join(svi["ipv4"].split())).network
    return [("eth1", f"{net.network_address + 250}/{net.prefixlen}")]


def _value(results=None, up=None, expected=None, here=True):
    res, u = _capture()
    intents = {h: hv for h, hv in _intents().items() if h != "r5"}
    net = T.network_graph(MANAGED, {h: ("router" if h.startswith("r") else "switch")
                                    for h in MANAGED}, intents, results or res, up or u,
                          expected=expected or {}, previous=None, now="2026-10-10T19:00:00Z",
                          at_here=_here(intents) if here else [])
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
    return re.findall(r'<text class="topo-st-t topo-st-(\w+)[^"]*"[^>]*>([^<]*)</text>', html)


def _ports(html):
    return re.findall(r'<text class="topo-port[^"]*"[^>]*>([^<]*)</text>', html)


def _section(html, ident):
    return re.search(rf'aria-labelledby="{ident}".*?</section>', html, re.S).group(0)


def _svg_class(html):
    return re.search(r'<svg class="(topo-map [^"]*)"', html).group(1)


def test_the_page_its_sidebar_and_header(web):
    html = web["client"].get("/v2/topology?list=Lab").get_data(as_text=True)
    assert 'aria-current="page"' in html and "<span>Topology</span>" in html
    assert re.search(r"<h1>Topology <a class=\"info-link\".*?</a> <span class=\"topo-sub\">· Lab · "
                     r"9 devices, 12 links, 1 "
                     r"outside · read <time", html)
    assert 'placeholder="Find a device, address or interface"' in html
    assert "How does this work?" in html
    assert re.search(r'<a href="/v2/device/r1\?list=Lab">', html), "a device opens its page"
    assert 'hx-trigger="nmas:topology from:body"' in html


def test_the_default_view_is_devices_links_and_state_labels_on_hover(web):
    """C654: at Fit, devices, links and state by line style and colour with the legend; each
    link's ports and chips only on hover or selection (in its own hover group, hidden by the
    page's style), every one at 150% and closer; Off, none at all."""
    html = _get(web)
    assert "topo-lbl-hover" in _svg_class(html)
    # Every label sits in its link's hover group, never loose on the map.
    loose = re.sub(r'<g class="topo-l[^"]*">.*?</g>\n', "", html, flags=re.S)
    assert 'class="topo-port' not in loose and 'class="topo-st-t' not in loose
    assert "topo-lbl-all" in _svg_class(_get(web, "&z=150"))
    assert "topo-lbl-all" in _svg_class(_get(web, "&labels=on"))
    off = _get(web, "&labels=off")
    assert "topo-lbl-off" in _svg_class(off) and _ports(off) == [] and _chips(off) == []
    legend = re.search(r'aria-label="Legend".*?</div>', html, re.S).group(0)
    assert "Ports and states on hover or when a link is selected" in legend


def test_every_link_names_the_port_at_each_end(web):
    ports = _ports(_get(web))
    # Eleven LLDP links and Mercury's own, two ports each; each of VLAN 100's six members, one.
    assert len(ports) == 24 + 6
    for p in ("Gi4", "Gi2", "Gi3", "Gi0/2", "Gi1/0", "Gi0/3", "Gi1/1", "eth1", "Vl100"):
        assert p in ports, p


def test_one_chip_per_adjacency_both_ends_merged(web):
    """C654: r3 Gi4 to r4 Gi4 is one OSPF and one OSPFv3 adjacency, reported by both ends:
    one chip each. eBGP's IPv4 and IPv6 sessions to r5 agree: one chip naming both."""
    texts = [t for _c, t in _chips(_get(web))]
    assert texts.count("OSPF area 0: FULL") == 1 and texts.count("OSPFv3 area 0: FULL") == 1
    assert texts.count("eBGP AS 65002: Estab (IPv4, IPv6)") == 2
    assert not any("×" in t for t in texts)


def test_ends_that_disagree_are_both_shown_and_flagged(web):
    res, up = _capture()
    for row in res["r4"]["ospfNbrState"]:
        if row["metric"].get("ospfNbrIpAddr", "").startswith("10.255.2."):
            row["value"] = [row["value"][0], "4"]                       # 2-way
    _store(_value(res, up))
    html = _get(web)
    assert ("warn", "OSPF area 0: r3 FULL / r4 2WAY (ends disagree)") in _chips(html)
    att = _section(html, "topo-att-h")
    assert "r3 FULL / r4 2WAY (ends disagree), the two ends disagree" in att


def test_a_multi_access_segment_is_one_node_with_its_summary_once(web):
    """C654: VLAN 100 is one node, its members joined by thin lines; its OSPF and OSPFv3
    summary once, on it; DR and BDR named neutrally; 2WAY between the others is normal."""
    html = _get(web)
    assert html.count('class="topo-segname"') == 1 and ">VLAN 100</text>" in html
    assert html.count("topo-member") >= 6
    texts = [t for _c, t in _chips(html)]
    assert "OSPF area 0: 6 devices, DR/BDR r3, r4" in texts
    assert "OSPFv3 area 0: 4 devices, DR/BDR r3, r4" in texts
    assert not any("2WAY" in t for t in texts)
    card = next(c for c in re.findall(r'<foreignObject class="topo-card".*?</foreignObject>',
                                      html, re.S) if "<strong class=\"mono\">VLAN 100" in c)
    assert "DR and BDR: r3, r4 (the devices FULL with the most others)" in card
    assert "2WAY with each other, as OSPF intends" in card
    assert "VLAN 100" not in _section(html, "topo-att-h")


def test_a_2way_with_the_dr_is_flagged_on_the_segment(web):
    res, up = _capture()
    for row in res["r1"]["ospfNbrState"]:
        if row["metric"].get("ospfNbrIpAddr", "").endswith(".13"):          # r3, a DR/BDR
            row["value"] = [row["value"][0], "4"]                           # 2-way
    for row in res["r3"]["ospfNbrState"]:
        if row["metric"].get("ospfNbrIpAddr", "").endswith(".11"):
            row["value"] = [row["value"][0], "4"]
    _store(_value(res, up))
    html = _get(web)
    att = _section(html, "topo-att-h")
    assert "VLAN 100" in att and "2WAY with the DR or BDR, expected FULL" in att
    assert any(c == "warn" and t.startswith("OSPF area 0: 6 devices") for c, t in _chips(html))


def test_a_protocol_not_read_adds_no_label(web):
    """C654: RIPng is configured on r1 Gi3 and s1 Gi0/2 and read by nothing: no chip, no toggle,
    no attention; the link's card says it is configured."""
    html = _get(web)
    assert not any("RIPng" in t for _c, t in _chips(html))
    assert ">RIPng</a>" not in html and "Not read: RIPng, EIGRP, IS-IS" in html
    assert "RIPng" not in _section(html, "topo-att-h")
    card = next(c for c in re.findall(r'<foreignObject class="topo-card".*?</foreignObject>',
                                      html, re.S) if "r1 Gi3 ↔ s1 Gi0/2" in c)
    assert "configured on r1 Gi3 and s1 Gi0/2 by committed intent" in card


def test_lines_say_how_each_link_compares_with_intent(web):
    html = _get(web)
    mapped = html.split('class="topo-mini"')[0]
    classes = re.findall(r'<path class="topo-line topo-(\w+)([^"]*)" d=', mapped)
    links = [c for c, extra in classes if "topo-member" not in extra]
    assert len(links) == 12 and links.count("warn") == 2 and links.count("ok") == 10
    assert len([c for c, extra in classes if "topo-member" in extra]) == 6
    legend = re.search(r'aria-label="Legend".*?</div>', html, re.S).group(0)
    for words in ("as intended", "not as intended", "down, or a neighbour missing", "not read",
                  "on a segment", "router", "L2 switch", "L3 switch", "Mercury&#39;s host",
                  "outside management", "class unknown", "multi-access segment (VLAN)"):
        assert words in legend, words


def test_devices_are_icons_by_class(web):
    html = _get(web)
    assert html.count('href="#ti-router"') >= 5 and 'href="#ti-cloud"' in html
    assert 'href="#ti-server"' in html and '<symbol id="ti-switch"' in html
    # s3 and s4 route (OSPF on their VLAN interfaces): L3, badged; s1 and s2 do not.
    assert html.count('class="topo-l3-t"') == 2
    assert re.search(r'<text class="topo-name"[^>]*>r5 · AS 65002</text>', html)
    assert re.search(r'<text class="topo-name"[^>]*>Mercury</text>', html)
    # No band is drawn: the generated places are a starting point (C655).
    assert 'class="topo-band"' not in html and "topo-bandrule" not in html


def test_needs_attention_names_what_is_wrong_and_the_weak_points(web):
    att = _section(_get(web), "topo-att-h")
    assert "Up, not as intended (2)" in att
    assert "r1 Gi3 ↔ s1 Gi0/2" in att and "only r1 reports it: s1 is polled and does not" in att
    assert "Weak points (2)" in att
    assert ("the only path between Mercury and r1, r2, r3, r4, s1, s2, s4 (Mercury reaches them "
            "only through s3 Gi1/1, VLAN 99). If s3 or that port fails, Mercury loses 7 "
            "devices") in att
    assert "r6" in att and "island" in att and "Mark as expected…" in att
    assert "11 as intended" in att and "r5" not in att


def test_a_group_or_a_filter_shows_a_subset_and_says_so(web):
    att = _section(_get(web, "&show=weak"), "topo-att-h")
    assert "r1 Gi3" not in att and "s3" in att
    assert "the counts are the whole" in att and "Show all" in att
    att = _section(_get(web, "&f=s2"), "topo-att-h")
    assert "r2 Gi3 ↔ s2 Gi0/2" in att and "r1 Gi3 ↔ s1" not in att
    assert "what matches s2" in att


def test_each_link_has_a_hover_card_and_a_selected_one_its_sheet(web):
    html = _get(web)
    cards = re.findall(r'<foreignObject class="topo-card".*?</foreignObject>', html, re.S)
    assert len(cards) == 12 + 6 + 1                     # links, VLAN 100's members, VLAN 100
    card = next(c for c in cards if "r3 Gi4 ↔ r4 Gi4" in c)
    assert "OSPF area 0" in card and "r3 to r4 FULL" in card
    assert "BGP</dt>" in card and "none on this link; none intended" in card
    assert "r3's Neighbours" in card and "tab=neighbours" in card
    html = _get(web, "&sel=r1%3AGi3~s1%3AGi0%2F2")
    assert '<g class="topo-l topo-sel">' in html and 'class="topo-glow' in html
    sheet = re.search(r'<section class="topo-sheet".*?</section>', html, re.S).group(0)
    assert "r1 Gi3" in sheet and "s1 Gi0/2" in sheet and "only r1 reports it" in sheet
    assert "configured on r1 Gi3 and s1 Gi0/2 by committed intent" in sheet
    assert "Show on the map" in sheet


def test_the_protocol_toggles_change_what_the_links_carry(web):
    html = _get(web, "&p=bgp")
    texts = [t for _c, t in _chips(html)]
    assert texts == ["eBGP AS 65002: Estab (IPv4, IPv6)"] * 2
    assert re.search(r'aria-pressed="false">OSPF</a>', html)
    assert re.search(r'aria-pressed="true">BGP</a>', html)


def test_ports_and_zoom(web):
    assert 'topo-ports-auto' in _get(web) and 'topo-ports-off' in _get(web, "&ports=off")
    assert 'class="topo-map topo-z150' in _get(web, "&z=150")


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


def test_a_path_trace_lists_every_shortest_path_with_its_ports(web):
    html = _get(web, "&a=r1&b=r4")
    panel = _section(html, "topo-trace-h")
    assert "never about forwarding" in panel and "r1 Gi2 to s3 Gi1/0" in panel
    assert html.count("topo-onpath") >= 3


def test_a_path_across_islands_says_why_there_is_none(web):
    assert "r6 has no link carrying traffic" in _get(web, "&a=r1&b=r6")


def test_a_what_if_names_who_loses_the_rest(web):
    panel = _section(_get(web, "&out=s3"), "topo-wi-h")
    assert "Mercury loses every device" in panel and "nothing was sent to a device" in panel
    panel = _section(_get(web, "&out=r6"), "topo-wi-h")
    assert "Nothing is cut off" in panel


def test_find_rings_what_matches_and_hides_nothing(web):
    html = _get(web, "&q=Gi1/0")
    assert "Found, ringed on the map:" in html and "topo-match" in html
    assert html.count('<g class="topo-n') == len(MANAGED) + 3   # r5, Mercury and VLAN 100 too
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
    assert len(_ports(_get(web))) == 24 + 6


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


# ---------------------------------------------------------------------------- Arrange (C655)

def _seg_id():
    return next(s["id"] for s in _value()["networks"]["Lab"]["segments"])


def test_arrange_draws_the_map_to_drag(web):
    html = _get(web, "&arrange=1")
    assert "topo-arranging" in _svg_class(html)
    assert 'action="/v2/topology/positions"' in html and 'id="topo-positions"' in html
    assert 'data-node="r1"' in html and 'aria-label="Move r1: drag it, or use the arrow keys"' in html
    # Arranging, a device is dragged, never followed to its page.
    assert not re.search(r'<a href="/v2/device/r1\?list=Lab">', html.split('class="topo-mapbox"')[1]
                         .split("</svg>")[0])
    assert "The generated layout" in html and "Reset to the generated layout" not in html


def test_a_saved_layout_is_the_network_s_for_everyone_and_recorded(web):
    seg = _seg_id()
    r = web["client"].post("/v2/topology/positions",
                           data={"list": "Lab",
                                 "positions": json.dumps({"r1": [120, 140], seg: [300, 260]})})
    assert r.status_code == 200 and "The layout is saved" in r.get_data(as_text=True)
    stored = json.loads((web["dir"] / "topology_positions.json").read_text())
    assert stored["positions"] == {"r1": [120, 140], seg: [300, 260]}
    assert stored["by"] == "test-person@example.invalid"
    assert '"action": "arranged"' in (web["dir"] / "topology_positions_log.jsonl").read_text()
    html = _get(web)
    assert 'transform="translate(120 140)" data-node="r1"' in html
    assert f'transform="translate(300 260)" data-node="{seg}"' in html
    assert "Arranged by test-person@example.invalid" in html
    # A device the layout does not hold keeps its generated place.
    assert re.search(r'transform="translate\(\d+ \d+\)" data-node="r2"', html)
    # Reset withdraws it, for everyone, recorded.
    assert "Reset to the generated layout" in _get(web, "&arrange=1")
    r = web["client"].post("/v2/topology/positions/reset", data={"list": "Lab"})
    assert r.status_code == 200 and "The saved layout is withdrawn" in r.get_data(as_text=True)
    assert not (web["dir"] / "topology_positions.json").exists()
    assert "The generated layout" in _get(web)


@pytest.mark.parametrize("positions,words", [
    ({"r9": [10, 10]}, "'r9' is not on this network's map"),
    ({"r1": [10]}, "r1's place is not two numbers"),
    ({"r1": [10, 99999]}, "outside the map's frame"),
])
def test_a_layout_that_is_not_the_map_s_is_refused_writing_nothing(web, positions, words):
    r = web["client"].post("/v2/topology/positions",
                           data={"list": "Lab", "positions": json.dumps(positions)})
    assert r.status_code == 400 and words in r.get_data(as_text=True).replace("&#39;", "'")
    assert not (web["dir"] / "topology_positions.json").exists()


def test_an_unreadable_layout_refuses_a_save_and_draws_the_generated_one(web):
    (web["dir"] / "topology_positions.json").write_text("{not json")
    assert "The saved layout cannot be read" in _get(web)
    r = web["client"].post("/v2/topology/positions",
                           data={"list": "Lab", "positions": json.dumps({"r1": [10, 10]})})
    assert r.status_code == 409 and "nothing was written" in r.get_data(as_text=True)
    assert (web["dir"] / "topology_positions.json").read_text() == "{not json"


@pytest.mark.real_identity
def test_no_person_arranges_nothing(web):
    r = web["client"].post("/v2/topology/positions",
                           data={"list": "Lab", "positions": json.dumps({"r1": [10, 10]})})
    assert r.status_code in (401, 403)
    assert not (web["dir"] / "topology_positions.json").exists()


def test_a_device_is_dragged_and_the_layout_saved_in_a_browser(web):
    """A real pointer drag (WebDriver's actions): the device moves, its lines follow straight,
    the Save form's field holds every place; Save writes the network's layout; the arrow keys
    move a focused device too."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1100})
        b.go(srv.url("/v2/topology?list=Lab&arrange=1"))
        b.wait_for("return document.querySelector('svg.topo-arranging') && "
                   "document.getElementById('topo-positions').value.length > 2")
        x0, y0 = b.js("var n = document.querySelector('[data-node=\"r1\"]');"
                      "return [+n.getAttribute('data-x'), +n.getAttribute('data-y')];")
        el = b._call("POST", f"/session/{b.session}/element",
                     {"using": "css selector", "value": '[data-node="r1"] .topo-ic'})
        b._call("POST", f"/session/{b.session}/actions", {"actions": [{
            "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
            "actions": [{"type": "pointerMove", "origin": el, "x": 0, "y": 0},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pointerMove", "origin": "pointer", "x": 60, "y": 40,
                         "duration": 200},
                        {"type": "pointerUp", "button": 0}]}]})
        x1, y1 = b.js("var n = document.querySelector('[data-node=\"r1\"]');"
                      "return [+n.getAttribute('data-x'), +n.getAttribute('data-y')];")
        assert x1 > x0 + 20 and y1 > y0 + 10, (x0, y0, x1, y1)
        field = json.loads(b.js("return document.getElementById('topo-positions').value"))
        assert field["r1"] == [x1, y1] and "r2" in field
        assert b.js("return Array.from(document.querySelectorAll('path[data-a=\"r1\"],"
                    "path[data-b=\"r1\"]')).every(function (p) {"
                    "return p.getAttribute('d').indexOf('L') > 0; })")
        # The arrow keys move a focused device 10 units.
        b.js("document.querySelector('[data-node=\"r2\"]').focus(); return 1")
        x2 = b.js("return +document.querySelector('[data-node=\"r2\"]').getAttribute('data-x')")
        b.js("document.querySelector('[data-node=\"r2\"]').dispatchEvent(new KeyboardEvent("
             "'keydown', {key: 'ArrowRight', bubbles: true})); return 1")
        assert b.js("return +document.querySelector('[data-node=\"r2\"]')"
                    ".getAttribute('data-x')") == x2 + 10
        b.click('form.topo-arrange button[type="submit"]')
        b.wait_for("return document.body.textContent.indexOf('The layout is saved') >= 0 "
                   "|| (document.querySelector('.set-result') && "
                   "document.querySelector('.set-result').textContent)")
        notice = b.js("var n = document.querySelector('.set-result'); "
                      "return n ? n.textContent : document.body.textContent.slice(0, 300)")
        assert 'The layout is saved' in notice, notice
    stored = json.loads((web["dir"] / "topology_positions.json").read_text())
    assert stored["positions"]["r1"] == [x1, y1] and stored["positions"]["r2"][0] == x2 + 10


def test_a_refusal_declares_no_change_and_a_success_does(web):
    """C656: a refused write wrote nothing, so its answer declares no invalidation (its keys made
    the page redraw the region showing the refusal's reason, wiping it); a saved one declares
    `topology`, and its result goes out of band to the slot above the map, which the redraw
    does not touch."""
    bad = web["client"].post("/v2/topology/positions",
                             data={"list": "Lab", "positions": json.dumps({"r9": [1, 1]})})
    assert bad.status_code == 400 and "X-NMAS-Invalidates" not in bad.headers
    ok = web["client"].post("/v2/topology/positions",
                            data={"list": "Lab", "positions": json.dumps({"r1": [50, 60]})})
    assert ok.headers.get("X-NMAS-Invalidates") == "topology"
    body = ok.get_data(as_text=True)
    assert '<div id="topo-result" aria-live="polite" hx-swap-oob="true">' in body
    assert body.index('<div id="topo" ') < body.index('id="topo-result"')
    assert "topo-arranging" not in body
