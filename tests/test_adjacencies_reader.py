"""C38's second consumer: the `adjacencies` reader and its Needs attention rows
(`modules/readers/adjacencies.py`, `attention.adjacency_source`).

On the nine REAL fleet configs parsed as committed intent and Prometheus's
REAL answer captured read-only on 2026-10-01 (the same fixtures as
`test_neighbours.py`); every failure is a minimal edit of that answer. One
link is ONE row naming its pair; a failure is raised only after two reads (a
deploy's settle window passes first); a protocol nothing scrapes is an
unknown row, never "all up". Nothing here reads a device.
"""

import copy
import re
import time

import pytest

from tests.test_neighbours import METRICS, UP, _capture, _intents

T0 = 1_790_000_000.0


def _source(cap):
    def src():
        results, up = {}, {}
        for m in METRICS:
            for r in cap[m]["data"]["result"]:
                results.setdefault(r["metric"]["device"], {}).setdefault(m, []).append(r)
        for r in cap[UP]["data"]["result"]:
            up.setdefault(r["metric"]["device"], {})[r["metric"]["job"]] = int(r["value"][1])
        return True, results, up
    return src


@pytest.fixture
def fleet(monkeypatch):
    from types import SimpleNamespace
    intents = _intents()
    # The host's fleet: r5 retired (in no inventory, its intent removed), so
    # r3's and r4's BGP peers are outside management.
    del intents["r5"]
    monkeypatch.setattr("modules.neighbours.committed_intents", lambda repo: (intents, ""))
    return {"intents": intents,
            "population": lambda: [("Lab", SimpleNamespace(repo_dir="/nowhere"), sorted(intents))]}


def _read(fleet, cap, previous=None, at=T0):
    from modules.readers import adjacencies
    return adjacencies.read(previous=previous or {}, clock=lambda: at, source=_source(cap),
                            population=fleet["population"])


def _rows(value, at=T0):
    from modules import attention
    cached = {"state": "ok", "doc": {"last_good": {"value": value, "value_at": at},
                                     "stale_after_seconds": 180}}
    return attention.adjacency_source(cached=cached)


def _break_r3_r4_link(cap):
    """Both ends stop reporting each other on their /31 (10.255.2.14/31)."""
    cap = copy.deepcopy(cap)
    cap["ospfNbrState"]["data"]["result"] = [
        r for r in cap["ospfNbrState"]["data"]["result"]
        if r["metric"]["ospfNbrIpAddr"] not in ("10.255.2.14", "10.255.2.15")]
    return cap


class TestTheFleet:
    def test_the_fleet_as_captured_raises_nothing(self, fleet):
        v = _read(fleet, _capture())
        assert v["adjacencies"] == {} and v["unmeasured"] == [] and v["devices"] == 8
        assert v["checked"] >= 40
        src = _rows(v)
        assert src["rows"] == [] and "adjacency report(s) over 8 device(s)" in src["checked"]


class TestABrokenLink:
    def test_one_link_is_one_entry_naming_its_pair(self, fleet):
        v = _read(fleet, _break_r3_r4_link(_capture()))
        assert list(v["adjacencies"]) == ["Lab|ospf|r3|r4|10.255.2.14/31"]
        a = v["adjacencies"]["Lab|ospf|r3|r4|10.255.2.14/31"]
        assert a["devices"] == ["r3", "r4"] and {s["device"] for s in a["sides"]} == {"r3", "r4"}
        assert a["reads"] == 1

    def test_one_read_is_not_a_row_two_are(self, fleet):
        cap = _break_r3_r4_link(_capture())
        first = _read(fleet, cap)
        src = _rows(first)
        assert src["rows"] == [] and "1 not up for less than 2 reads, not raised yet" in src["checked"]
        second = _read(fleet, cap, previous=first, at=T0 + 60)
        rows = _rows(second, at=T0 + 60)["rows"]
        assert len(rows) == 1
        r = rows[0]
        assert r["level"] == "danger" and r["what"] == "OSPF between r3 and r4 is not up"
        assert r["devices"] == ["r3", "r4"]
        assert r["since"] == time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T0))
        assert "r3 GigabitEthernet4 reports no such neighbour" in r["cause"]
        assert r["action"]["href"] == "/v2/device/r3?tab=neighbours"

    def test_a_link_that_comes_back_leaves(self, fleet):
        first = _read(fleet, _break_r3_r4_link(_capture()))
        assert _read(fleet, _capture(), previous=first, at=T0 + 60)["adjacencies"] == {}

    def test_a_stuck_state_is_named_on_the_row(self, fleet):
        cap = copy.deepcopy(_capture())
        for r in cap["ospfNbrState"]["data"]["result"]:
            if r["metric"]["device"] == "r1" and r["metric"]["ospfNbrIpAddr"] == "10.255.3.13":
                r["value"][1] = "3"
        first = _read(fleet, cap)
        rows = _rows(_read(fleet, cap, previous=first, at=T0 + 60), at=T0 + 60)["rows"]
        assert [r["what"] for r in rows] == ["OSPF between r1 and r3 is not up"]
        assert "r1 GigabitEthernet2 reports it init" in rows[0]["cause"]

    def test_a_peer_outside_management_is_said(self, fleet):
        cap = copy.deepcopy(_capture())
        for r in cap["cbgpPeer2State"]["data"]["result"]:
            if r["metric"]["cbgpPeer2RemoteAddr"] == "198.51.100.1":
                r["value"][1] = "3"
        first = _read(fleet, cap)
        rows = _rows(_read(fleet, cap, previous=first, at=T0 + 60), at=T0 + 60)["rows"]
        assert [r["what"] for r in rows] == \
            ["BGP from r3 to 198.51.100.1 (outside management) is not up"]


class TestWhatCannotBeJudged:
    def test_an_unscraped_protocol_is_an_unknown_row_never_all_up(self, fleet):
        cap = copy.deepcopy(_capture())
        cap[UP]["data"]["result"] = [r for r in cap[UP]["data"]["result"]
                                     if not (r["metric"]["device"] == "r3" and r["metric"]["job"] == "bgp")]
        cap["cbgpPeer2State"]["data"]["result"] = [
            r for r in cap["cbgpPeer2State"]["data"]["result"] if r["metric"]["device"] != "r3"]
        rows = _rows(_read(fleet, cap))["rows"]
        assert [(r["level"], r["devices"]) for r in rows] == [("unknown", ["r3"])]
        assert "r3 (BGP)" in rows[0]["cause"]

    def test_prometheus_unreadable_raises_for_job_health(self, monkeypatch, fleet):
        from modules.integrations.prometheus import PrometheusIntegration
        from modules.readers import adjacencies
        monkeypatch.setattr(PrometheusIntegration, "is_configured", lambda self: True)
        monkeypatch.setattr(PrometheusIntegration, "_get",
                            lambda self, path, **p: {"ok": False, "error": "Could not connect"})
        with pytest.raises(RuntimeError, match="Prometheus could not be asked for ospfNbrState"):
            adjacencies.read(previous={}, population=fleet["population"])

    def test_not_configured_says_so(self, fleet):
        from modules.readers import adjacencies
        v = adjacencies.read(previous={}, source=lambda: (False, {}, {}),
                             population=fleet["population"])
        assert "no Prometheus configured" in _rows(v)["checked"]

    def test_never_read_is_a_source_error(self):
        from modules import attention
        src = attention.adjacency_source(cached={"state": "absent", "doc": None,
                                                 "why": "no reader has written it"})
        assert src["state"] == "unreadable"
        assert src["rows"][0]["cause"].startswith("not read yet")


class TestDrawn:
    def test_the_v2_list_draws_the_row_and_links_to_the_devices_neighbours(self, monkeypatch, fleet):
        from tests.test_v2_pages import _client, _page
        cap = _break_r3_r4_link(_capture())
        rows = _rows(_read(fleet, cap, previous=_read(fleet, cap), at=T0 + 60), at=T0 + 60)["rows"]
        monkeypatch.setattr("modules.attention.needs_attention", lambda sources=None: _page(rows))
        monkeypatch.setattr("modules.nsot.receipts.read",
                            lambda list_name, device="", limit=50: {"state": "absent", "rows": []})
        html = _client().get("/v2/").get_data(as_text=True)
        assert "OSPF between r3 and r4 is not up" in html
        assert '<a class="btn btn-small btn-outline" href="/v2/device/r3?tab=neighbours">Open…</a>' in html

    def test_todays_renderer_draws_the_link_and_only_to_v2(self):
        import json as _json
        from tests.js_source import read_shipped
        import dukpy
        src = read_shipped("static/js/nmas_attention.js")
        m = re.search(r"function actionHtml\(a\) \{.*?\n  \}\n", src, re.S)
        esc = re.search(r"function esc\(.*?\n  \}\n", src, re.S)
        assert m and esc
        js = esc.group(0) + m.group(0)
        good = dukpy.evaljs(js + "actionHtml(%s)" % _json.dumps(
            {"label": "Open", "href": "/v2/device/r3?tab=neighbours"}))
        bad = dukpy.evaljs(js + "actionHtml(%s)" % _json.dumps(
            {"label": "Open", "href": "javascript:alert(1)"}))
        assert 'href="/v2/device/r3?tab=neighbours"' in good and "href=" not in bad

    def test_the_reader_is_declared_and_the_key_heard(self):
        import os
        from modules import invalidation, reader_job
        assert "modules.readers.adjacencies" in reader_job.DECLARED_MODULES
        assert "adjacencies" in invalidation.VOCABULARY
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assert "nmas:adjacencies from:body" in open(
            os.path.join(root, "templates/v2/_neighbours.html")).read()
        # Needs attention and the sidebar's count listen to ONE generated list (2026-10-02):
        # the key is in it, and both templates draw it.
        from modules import attention
        assert "adjacencies" in attention.ATTENTION_KEYS
        for path in ("templates/v2/_attention.html", "templates/v2/_count.html"):
            assert "{{ attention_trigger }}" in open(os.path.join(root, path)).read(), path
        src = open(os.path.join(root, "static/js/nmas_attention.js")).read()
        assert re.search(r"NMAS\.subscribe\('adjacencies', 'attention'", src)
