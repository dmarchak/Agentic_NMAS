"""OBSERVE › Topology on v2 (P.11 step 2), through the real routes and templates, drawing a stored
value the real reader built from the real captures (tests/test_topology_graph's fixtures: LLDP,
interfaces, routing tables, the fleet's configs with r5 retired, as on the host).

- the sidebar has Topology; the page draws the counts, the legend, the map (every device a link
  to its page), the list by band, the islands, the single points of failure, the limits;
- r5 is an outside peer: drawn outside, never in the islands;
- r6 is an island to look at, with Mark as expected…; declared with a reason by a verified person,
  it is recorded, and a reason too short is refused writing nothing; with no person, nothing;
- a down link is dashed and crossed, its end named on hover;
- a routing layer draws the physical links faintly underneath;
- a path trace lists every shortest path with its ports, said as the graph's claim; one across
  islands says why there is none;
- a search rings what matches and hides nothing;
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


def _value(results=None, up=None, expected=None):
    res, u = _capture()
    intents = {h: hv for h, hv in _intents().items() if h != "r5"}
    net = T.network_graph(MANAGED, {h: ("router" if h.startswith("r") else "switch")
                                    for h in MANAGED}, intents, results or res, up or u,
                          expected=expected or {}, previous=None, now="2026-10-10T19:00:00Z")
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


def test_the_page_and_its_sidebar(web):
    html = web["client"].get("/v2/topology?list=Lab").get_data(as_text=True)
    assert 'aria-current="page"' in html and "<span>Topology</span>" in html
    assert "Topology · Lab" in html
    for words in ("devices managed", "outside peers", "reported by both ends",
                  "one end silent", "far end not polled", "islands to look at",
                  "single points of failure", "down (dashed, crossed)",
                  "What this cannot see"):
        assert words in html, words
    assert re.search(r'<a href="/v2/device/r1\?list=Lab">', html), "a device opens its page"
    assert 'hx-trigger="nmas:topology from:body"' in html


def test_r5_is_an_outside_peer_never_an_island(web):
    html = _get(web)
    assert re.search(r'<g class="topo-n topo-outside">\s*<title>r5: outside management', html)
    islands = re.search(r'id="topo-islands-h".*?</section>', html, re.S).group(0)
    assert "r5" not in islands and "<strong>r6</strong>" in islands
    assert "look at it" in islands and "Mark as expected…" in islands


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
    # The reader's next read draws it expected, with the reason, and warns nothing.
    _store(_value(expected={"r6": stored["islands"]["r6"]}))
    islands = re.search(r'id="topo-islands-h".*?</section>', _get(web), re.S).group(0)
    assert "expected" in islands and "its own containerlab lab, cabled apart" in islands
    assert "look at it" not in islands and "Withdraw" in islands


@pytest.mark.real_identity
def test_no_person_declares_nothing(web):
    r = web["client"].post("/v2/topology/expected",
                           data={"list": "Lab", "device": "r6", "reason": "its own lab, apart"})
    assert r.status_code in (401, 403)
    assert not (web["dir"] / "topology_expected.json").exists()


def test_a_down_link_is_dashed_crossed_and_names_its_end(web):
    res, up = _capture()
    for row in res["r1"]["ifOperStatus"]:
        if row["metric"]["ifName"] == "Gi2":
            row["value"] = [row["value"][0], "2"]
    _store(_value(res, up))
    html = _get(web)
    g = re.search(r'<g class="topo-e topo-down[^"]*"><title>r1 Gi2 to s3 Gi1/0: down, down at '
                  r'r1[^<]*</title>.*?</g>', html, re.S)
    assert g and 'class="topo-x"' in g.group(0)


def test_a_routing_layer_draws_the_physical_links_underneath(web):
    html = _get(web, "&layer=ospf")
    # 9 of the 11: the two to r5 are not drawn, since r5 takes no part in OSPF (an outside peer
    # is on a layer's map only where it peers).
    assert html.count('class="topo-edge topo-under"') == 9
    assert '<g class="topo-e topo-up">' in html


def test_a_path_trace_lists_every_shortest_path_with_its_ports(web):
    html = _get(web, "&a=r1&b=r4")
    panel = re.search(r'id="topo-trace-h".*?</section>', html, re.S).group(0)
    assert "never about forwarding" in panel
    assert "r1 Gi2 to s3 Gi1/0" in panel
    assert html.count("topo-onpath") >= 3


def test_a_path_across_islands_says_why_there_is_none(web):
    html = _get(web, "&a=r1&b=r6")
    assert "r6 has no link carrying traffic in this layer" in html


def test_a_search_rings_what_matches_and_hides_nothing(web):
    html = _get(web, "&q=Gi1/0")
    assert "Found, ringed on the map:" in html and "s3" in html
    assert html.count('<g class="topo-n') == len(MANAGED) + 1      # r5 too: nothing hidden


def test_a_device_announced_name_is_escaped(web):
    res, up = _capture()
    row = json.loads(json.dumps(res["s1"]["lldpRemEntry"][0]))
    row["metric"]["lldpRemEntry"] = "<img src=x onerror=alert(1)>"
    res["s1"]["lldpRemEntry"].append(row)
    _store(_value(res, up))
    html = _get(web)
    assert "<img src=x" not in html and "&lt;img src=x onerror=alert(1)&gt;" in html


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
    assert "store cannot be read" in html and "<svg class=\"topo-map\"" not in html
