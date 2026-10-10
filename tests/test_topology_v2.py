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
                     r"outside · read <time", html)
    assert 'placeholder="Find a device, address or interface"' in html
    assert "How does this work?" in html
    assert re.search(r'<a href="/v2/device/r1\?list=Lab">', html), "a device opens its page"
    assert 'hx-trigger="nmas:topology from:body"' in html


def test_every_link_names_the_port_at_each_end(web):
    ports = _ports(_get(web))
    # Eleven LLDP links and Mercury's own: two ports each.
    assert len(ports) == 24
    for p in ("Gi4", "Gi2", "Gi3", "Gi0/2", "Gi1/0", "Gi0/3", "Gi1/1", "eth1"):
        assert p in ports, p


def test_each_neighbourship_is_chipped_with_its_key_fact_and_state(web):
    chips = _chips(_get(web))
    texts = [t for _c, t in chips]
    # r3 Gi4 to r4 Gi4: one adjacency each way, FULL, area 0.
    assert "OSPF area 0: FULL" in texts and "OSPFv3 area 0: FULL" in texts
    # A port on the shared VLAN 100 segment: its five OSPF neighbours, counted by state.
    assert "OSPF area 0: 2WAY×3 FULL×2" in texts
    # eBGP to the outside peer: its AS and the two sessions (IPv4 and IPv6).
    assert texts.count("eBGP AS 65002: Estab×2") == 2
    # RIPng is configured on the one-sided links and read by nothing.
    assert texts.count("RIPng ?") == 2 and ("unread", "RIPng ?") in chips
    assert {c for c, _t in chips} <= {"ok", "unread"}


def test_lines_say_how_each_link_compares_with_intent(web):
    html = _get(web)
    classes = re.findall(r'<path class="topo-line topo-(\w+)[^"]*" d=', html)
    # 12 drawn on the map, 12 again in the zoomed-out view.
    assert len(classes) == 24
    assert classes[:12].count("warn") == 2 and classes[:12].count("ok") == 10
    legend = re.search(r'aria-label="Legend".*?</div>', html, re.S).group(0)
    for words in ("as intended", "not as intended", "down, or a neighbour missing", "not read",
                  "router", "L2 switch", "L3 switch", "Mercury&#39;s host", "outside management",
                  "class unknown"):
        assert words in legend, words


def test_devices_are_icons_by_class(web):
    html = _get(web)
    assert html.count('href="#ti-router"') >= 5 and 'href="#ti-cloud"' in html
    assert 'href="#ti-server"' in html and '<symbol id="ti-switch"' in html
    # s3 and s4 route (OSPF on their VLAN interfaces): L3, badged; s1 and s2 do not.
    assert html.count('class="topo-l3-t"') == 2
    assert re.search(r'<text class="topo-name"[^>]*>r5 · AS 65002</text>', html)
    assert re.search(r'<text class="topo-name"[^>]*>Mercury</text>', html)


def test_needs_attention_names_what_is_wrong_and_the_weak_points(web):
    att = _section(_get(web), "topo-att-h")
    assert "Up, not as intended (2)" in att
    assert "r1 Gi3 ↔ s1 Gi0/2" in att and "only r1 reports it: s1 is polled and does not" in att
    assert "Weak points (2)" in att
    assert ("the only path between Mercury and r1, r2, r3, r4, s1, s2, s4 (Mercury reaches them "
            "only through s3 Gi1/1, VLAN 99). If s3 or that port fails, Mercury loses 7 "
            "devices") in att
    assert "r6" in att and "island" in att and "Mark as expected…" in att
    assert "10 as intended" in att and "r5" not in att


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
    assert len(cards) == 12
    card = next(c for c in cards if "r3 Gi4 ↔ r4 Gi4" in c)
    assert "OSPF area 0" in card and "r3 Gi4 to r4 FULL" in card
    assert "BGP, RIPng</dt>" in card and "none on this link; none intended" in card
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
    assert texts == ["eBGP AS 65002: Estab×2"] * 2
    assert re.search(r'aria-pressed="false">OSPF</a>', html)
    assert re.search(r'aria-pressed="true">BGP</a>', html)
    assert "Not read: EIGRP, IS-IS" in html


def test_ports_labels_and_zoom(web):
    assert 'topo-ports-auto' in _get(web) and 'topo-ports-off' in _get(web, "&ports=off")
    assert _ports(_get(web, "&labels=off")) == [] and _chips(_get(web, "&labels=off")) == []
    # Labels auto: shown at Fit and closer, hidden zoomed out.
    assert _ports(_get(web, "&z=75")) == [] and _ports(_get(web, "&z=150"))
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
