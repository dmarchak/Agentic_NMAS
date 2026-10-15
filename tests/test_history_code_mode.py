"""History › Query's Code mode: free text, BOUNDED (the operator's decision, 2026-10-15, C817),
and LogQL counts drawn on the chart (C819); modules/history_query.py, _history_metric.html.

Fed by real captures of the lab's Loki (tests/fixtures/loki/ask_lines_labelled.json and
ask_counts_by_device.json, 2026-10-15, read-only, addresses mapped into 192.0.2.0/24). The
secret-bearing line is that capture with ONE PLANTED LINE (a PARSER-5-CFGLOG_LOGGEDCMD line
setting an SNMP community, the kind of line a device logs), said so where it is planted.

- every line and label fetched through Code mode is masked by `redact_text`;
- Code mode asks Loki only through its read endpoints (query, query_range, labels): one
  query_range, never Loki's /config, with Mercury's line and range bounds and a fixed wait; a
  path outside the list is refused naming both, and the page says "Couldn't load" in place;
- its PromQL is asked only of a Prometheus data source, through Grafana's query endpoint;
- a LogQL metric query is drawn as series by the Monitoring chart (`data-panel-json`), each
  label set masked, the values Loki's, the largest drawn (F3's "Edit as code" from Counts
  ending in that chart: tests/test_history_ask_logs.py).
"""

import copy
import json
import os
import re
from html import unescape

import pytest

from tests.test_logs_v2 import web  # noqa: F401 (the Logs tests' app, with the reader's value)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOKI = os.path.join(ROOT, "tests", "fixtures", "loki")


def _fx(name):
    with open(os.path.join(LOKI, name), encoding="utf-8") as fh:
        return json.load(fh)


LINES = _fx("ask_lines_labelled.json")
COUNTS = _fx("ask_counts_by_device.json")
#: The planted value (not in any capture): a community a device would log being set.
PLANTED = "Pl4ntedC0mmunity"


class _Resp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


@pytest.fixture
def loki(monkeypatch):
    """The network's Loki answering *answer* to every ask, each recorded with the client's
    wait: ``[(path, params, timeout)]``."""
    from modules import history_logq
    from modules.integrations import loki as L

    state = {"answer": LINES["answer"], "asked": []}

    def _get(self, path, **params):
        state["asked"].append((path, params, self.timeout))
        return {"ok": True, "response": _Resp(state["answer"])}

    monkeypatch.setattr(L.LokiIntegration, "is_configured", lambda self: True)
    monkeypatch.setattr(L.LokiIntegration, "_get", _get)
    history_logq.forget()
    yield state
    history_logq.forget()


def _code(web, q, rng="24h"):  # noqa: F811
    r = web.get("/v2/history/query/metric/ask", query_string={"lang": "logql", "q": q,
                                                                "range": rng})
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _with_planted_line():
    """The lines capture with ONE PLANTED line in its first stream (s4's), its newest."""
    body = copy.deepcopy(LINES["answer"])
    first = body["data"]["result"][0]
    ns = str(int(first["values"][0][0]) + 1)
    first["values"].insert(0, [ns, (f"Oct 15 08:24:59 s4 3072: s4: *Oct 12 02:41:01.100: "
                                    f"%PARSER-5-CFGLOG_LOGGEDCMD: User:nmas  logged command:"
                                    f"snmp-server community {PLANTED} RO")])
    return body


class TestMasked:
    def test_a_secret_bearing_line_is_masked_when_fetched_through_code_mode(self, web, loki):  # noqa: F811
        loki["answer"] = _with_planted_line()
        html = _code(web, '{job="network_syslog"}')
        assert PLANTED not in html, "the planted community reached the page"
        assert "snmp-server community &lt;redacted:snmp_community&gt; RO" in html, \
            "the line was not drawn at all, so its masking proves nothing"

    def test_a_secret_in_a_series_label_is_masked_too(self, web, loki):  # noqa: F811
        body = copy.deepcopy(COUNTS["answer"])
        body["data"]["result"][0]["metric"] = {"line": f"snmp-server community {PLANTED} RO"}
        loki["answer"] = body
        html = _code(web, 'sum by (line) (count_over_time({job=~".+"} [1h]))')
        assert PLANTED not in html and "data-panel-json" in html


class TestBounded:
    def test_one_query_range_with_mercury_s_bounds_and_a_fixed_wait(self, web, loki):  # noqa: F811
        from modules import history_logq
        _code(web, '{job="network_syslog"}', "7d")
        assert [a[0] for a in loki["asked"]] == ["loki/api/v1/query_range"], \
            "Code mode asked Loki something other than one query_range (its /config included)"
        _path, p, timeout = loki["asked"][0]
        assert p["limit"] == 200 and p["direction"] == "backward"
        assert int(p["end"]) - int(p["start"]) == 7 * 86400 * 10 ** 9
        assert timeout == history_logq.DEFAULT_WAIT == 65.0

    def test_the_bounds_are_said_under_the_answer(self, web, loki):  # noqa: F811
        text = re.sub(r"<[^>]+>", "", _code(web, '{job="network_syslog"}'))
        assert ("Bounds: 200 lines (Mercury) · 30 days an ask (Mercury) · a metric query's 20 "
                "largest series drawn, a point every 5 min · Mercury waits at most 1 min 5 s "
                "for Loki") in unescape(text)
        assert "read through Loki's query, query_range, labels only" in unescape(text)

    def test_a_path_outside_the_read_endpoints_is_refused_naming_both(self):
        from modules import history_query as H
        with pytest.raises(H.AskRefused) as err:
            H.read_only("loki", "loki/api/v1/push")
        assert "loki/api/v1/query, loki/api/v1/query_range, loki/api/v1/labels" in str(err.value)
        assert "'loki/api/v1/push'" in str(err.value)
        assert H.read_only("loki", "loki/api/v1/labels") == "loki/api/v1/labels"

    def test_a_refused_path_is_drawn_in_place_and_nothing_is_asked(self, web, loki,  # noqa: F811
                                                                   monkeypatch):
        """The control's shape: with query_range off the list, the ask is refused before
        Loki is asked, and the page says so in place."""
        from modules import history_query as H
        monkeypatch.setitem(H.READS, "loki", ("loki/api/v1/query", "loki/api/v1/labels"))
        html = unescape(_code(web, '{job="network_syslog"}'))
        assert "Couldn't load: Refused: Code mode reads loki only through" in html
        assert loki["asked"] == []

    def test_a_timeout_names_code_mode_s_wait(self, web, monkeypatch):  # noqa: F811
        from modules import history_logq
        from modules.integrations import loki as L
        monkeypatch.setattr(L.LokiIntegration, "is_configured", lambda self: True)
        monkeypatch.setattr(L.LokiIntegration, "_get", lambda self, path, **p: {
            "ok": False, "error": f"Timed out after {self.timeout}s"})
        history_logq.forget()
        html = unescape(_code(web, '{job="network_syslog"}'))
        assert ("Couldn't load: Loki did not answer within 1 min 5 s (Code mode's wait: Loki's "
                "default query_timeout, 1 min, and 5 s)") in html


class TestPromQLReadsOnlyPrometheus:
    @pytest.fixture
    def grafana(self, monkeypatch):
        from modules import device_page
        from tests.test_history_query import _Grafana
        g = _Grafana()
        g.sources = [{"uid": "prom", "type": "prometheus", "name": "Prometheus"}]
        monkeypatch.setattr(device_page, "_cached", lambda name, list_name=None: (
            {"datasources": g.sources}, "2026-10-11T09:00:00Z", ""))
        monkeypatch.setattr(device_page, "grafana_client", lambda list_name: g)
        return g

    def test_asked_of_a_prometheus_source_through_the_query_endpoint(self, web, grafana):  # noqa: F811
        from modules.integrations.grafana import GrafanaIntegration
        r = web.get("/v2/history/query/metric/ask/data?q=up")
        assert r.status_code == 200 and grafana.asked
        assert {q["datasource"]["type"] for q in grafana.asked[0]["queries"]} == {"prometheus"}
        assert GrafanaIntegration.QUERY_PATH == "api/ds/query"

    def test_a_network_with_no_prometheus_source_is_refused_naming_it(self, web, grafana):  # noqa: F811
        grafana.sources = [{"uid": "pg", "type": "grafana-postgresql-datasource",
                            "name": "Records", "isDefault": True}]
        r = web.get("/v2/history/query/metric/ask/data?q=up")
        body = r.get_json()
        assert r.status_code == 400, body
        assert ("Code mode's PromQL is asked only of a prometheus data source; query A would be "
                "asked of no named data source") in body["error"]
        assert grafana.asked == [], "Grafana was asked"

    def test_a_source_of_another_type_is_refused_naming_its_type(self):
        from modules import history_query as H
        with pytest.raises(H.AskRefused) as err:
            H.promql_sources({"queries": [{"refId": "B", "datasource": {"uid": "pg",
                                                                       "type": "postgres"}}]})
        assert "query B would be asked of a postgres data source (pg)" in str(err.value)


class TestLogQLCountsAreDrawn:
    def test_a_count_query_is_drawn_by_the_chart_with_loki_s_values(self, web, loki):  # noqa: F811
        loki["answer"] = COUNTS["answer"]
        html = _code(web, 'sum by (device) (count_over_time({job=~".+"} [1h]))')
        m = re.search(r"data-panel-json='([^']+)'", html)
        assert m, "no chart island"
        p = json.loads(unescape(m.group(1)))
        assert p["type"] == "timeseries" and p["step"] == 300, (p["type"], p["step"])
        assert loki["asked"][0][1]["step"] == "300"
        got = {s["label"]: s for s in p["series"]}
        want = {f'{{device="{r["metric"]["device"]}"}}': r for r in
                COUNTS["answer"]["data"]["result"]}
        assert set(got) == set(want)
        for label, row in want.items():
            assert got[label]["times"] == [int(t) for t, _v in row["values"]]
            assert got[label]["values"] == [float(v) for _t, v in row["values"]]
        assert "Your LogQL query's series" in html and "9 series every 5 min" in html

    def test_more_series_than_drawn_draws_the_largest_and_counts_the_rest(self, web, loki,  # noqa: F811
                                                                         monkeypatch):
        from modules import history_logq
        monkeypatch.setattr(history_logq, "MAX_SERIES", 3)
        loki["answer"] = COUNTS["answer"]
        html = unescape(_code(web, 'sum by (device) (count_over_time({job=~".+"} [1h]))'))
        m = re.search(r"data-panel-json='([^']+)'", html)
        assert m, "no chart island"
        p = json.loads(m.group(1))
        sizes = sorted(((sum(float(v) for _t, v in r["values"]), r["metric"]["device"])
                        for r in COUNTS["answer"]["data"]["result"]), reverse=True)
        assert [s["label"] for s in p["series"]] == [f'{{device="{d}"}}' for _n, d in sizes[:3]]
        assert "9 series: the 3 largest are drawn" in html


def test_a_count_query_is_drawn_in_a_browser(web, loki):  # noqa: F811
    """In a real browser: Code mode's LogQL count query is drawn by the Monitoring chart (its
    canvas and its legend's series), nothing scrolling sideways."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A

    loki["answer"] = COUNTS["answer"]
    url = ("/v2/history/query/metric/ask?lang=logql&range=24h&q="
           "sum+by+%28device%29+%28count_over_time%28%7Bjob%3D~%22.%2B%22%7D+%5B1h%5D%29%29")
    with browser.Served(A.app) as srv, browser.Browser() as b:
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
        b.go(srv.url(url))
        b.wait_for("return document.querySelector('.hq-logql .u-over')", 15)
        legend = b.js("return document.querySelectorAll('.hq-logql .legend-item').length")
        wait = b.js("return !!document.querySelector('.hq-logql .panel-wait')")
        wide = b.js("return document.documentElement.scrollWidth <= window.innerWidth")
        b.go("about:blank")
    assert legend >= 9 and not wait and wide, (legend, wait, wide)
