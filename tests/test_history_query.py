"""History › Query (C667; board A, AskLibrary): the tab sits between Timeline and Baselines; it
says what the history holds from the settings and the logs reader, never a guessed date; its
six ready-made questions are the board's, in its order, and only a built one is a link."""

import re

import pytest

from tests.test_logs_v2 import web  # noqa: F401 (the Logs tests' app, with the reader's value)


def _tab(web):  # noqa: F811
    return web.get("/v2/history?tab=query").get_data(as_text=True)


def test_the_tab_sits_between_timeline_and_baselines(web):  # noqa: F811
    html = _tab(web)
    tabs = re.findall(r'<a class="tab[^"]*" href="/v2/history\?tab=(\w+)"', html)
    assert tabs == ["timeline", "query", "baselines", "authorisations"]
    assert re.search(r'<a class="tab on" href="/v2/history\?tab=query" aria-current="page">',
                     html)


def test_the_six_questions_in_the_board_s_order_and_only_the_built_one_links(web):  # noqa: F811
    html = _tab(web)
    titles = re.findall(r'class="hq-q[^"]*"[^>]*><strong>([^<]+)</strong>', html)
    assert titles == ["Interface errors and discards over time", "CPU and memory trend",
                      "Routing neighbour changes", "Syslog by device", "Restarts",
                      "Telemetry rates"]
    links = re.findall(r'<a class="hq-q" href="([^"]+)"><strong>([^<]+)', html)
    assert links == [("/v2/history/query/metric/errors", "Interface errors and discards over time"),
                     ("/v2/history/query/metric/cpu", "CPU and memory trend"),
                     ("/v2/history/query/syslog", "Syslog by device")]
    assert html.count("not built yet") == 3


def test_what_the_history_holds_comes_from_the_settings_and_the_reader(web, monkeypatch):  # noqa: F811
    from modules import history_query
    real = history_query._setting
    monkeypatch.setattr(history_query, "_setting", lambda l, k, d: {
        "metrics_live_retention_days": 45, "logs_retention_days": 730,
        "grafana_history_datasource_uid": "thanos"}.get(k, real(l, k, d)))
    text = re.sub(r"<[^>]+>", "", _tab(web))
    assert "Metrics: the last 45 days at full detail, older from the long-term store" in text
    assert "Logs: kept 730 days" in text
    monkeypatch.setattr(history_query, "_setting", lambda l, k, d: {
        "grafana_history_datasource_uid": ""}.get(k, d))
    text = re.sub(r"<[^>]+>", "", _tab(web))
    assert "nothing older is kept (no long-term store is set" in text, \
        "the control: without a long-term store the strip says so"
    assert "30 Aug" not in text, "no date the tool did not measure"


def test_the_coverage_reads_nothing_per_device(web, monkeypatch):  # noqa: F811
    """A read of settings and one stored value: no device is asked."""
    from modules import connection

    def refuse(*a, **k):
        raise AssertionError("the Query tab opened a device session")
    monkeypatch.setattr(connection, "open_ssh", refuse)
    assert "What the history holds" in _tab(web)


# ---------------------------------------------------------------------------
# Board B (AskMetric): a metrics question, its PromQL the question's, asked of the network's
# Grafana by the Monitoring panel's path, drawn by the same chart.
# ---------------------------------------------------------------------------

import json  # noqa: E402
import os  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANSWER = json.load(open(os.path.join(ROOT, "tests", "fixtures", "grafana", "dsquery",
                                     "throughput.json"), encoding="utf-8"))["answer"]


class _Grafana:
    """A Grafana that records each body asked and answers with a real capture."""

    def __init__(self):
        self.asked = []

    def query(self, body, timeout=20.0):
        self.asked.append(body)
        return {"ok": True, "body": ANSWER}


@pytest.fixture
def grafana(monkeypatch):
    from modules import device_page
    g = _Grafana()
    monkeypatch.setattr(device_page, "_cached", lambda name, list_name=None: (
        {"datasources": [{"uid": "prom", "type": "prometheus", "name": "Prometheus",
                          "isDefault": True}]}, "2026-10-11T09:00:00Z", ""))
    monkeypatch.setattr(device_page, "grafana_client", lambda list_name: g)
    return g


class TestTheMetricQuestion:
    def test_the_expression_carries_only_the_checked_names(self):
        from modules import history_query as H
        assert H.metric_expr("errors", {"d": "", "i": "", "range": "30d"}).startswith(
            "sum by (device) (rate(ifInDiscards")
        e = H.metric_expr("errors", {"d": "s3", "i": "Gi1/1", "range": "30d"})
        assert 'ifInDiscards{device="s3",ifName="Gi1/1"}' in e and "sum by (ifName)" in e

    @pytest.mark.parametrize("values, words", [
        ({"d": 's3"}) or vector(1'}, "is not a device name"),
        ({"d": "s3", "i": "Gi1 1"}, "is not an interface name"),
        ({"i": "Gi1"}, "choose the device first"),
        ({"range": "2y"}, "is not one of the ranges"),
    ])
    def test_a_value_it_cannot_carry_is_refused_by_name(self, values, words):
        from modules import history_query as H
        with pytest.raises(H.AskRefused) as err:
            H.metric_ask(values)
        assert words in str(err.value)

    def test_the_data_route_asks_grafana_the_question_s_query(self, web, grafana):  # noqa: F811
        r = web.get("/v2/history/query/metric/errors/data?d=s3&range=24h")
        assert r.status_code == 200, r.get_json()
        body = grafana.asked[-1]
        assert [q["expr"] for q in body["queries"]][0].startswith(
            'sum by (ifName) (rate(ifInDiscards{device="s3"}')
        assert body["from"] == "now-86400s"
        assert r.get_json()["series"], "the capture's series are drawn"

    def test_a_range_past_the_live_store_with_no_long_term_store_is_refused(self, web,  # noqa: F811
                                                                           grafana):
        r = web.get("/v2/history/query/metric/errors/data?range=1y")
        assert r.status_code == 400 and grafana.asked == []

    def test_the_page_draws_the_question_and_the_chart_island(self, web, grafana):  # noqa: F811
        html = web.get("/v2/history/query/metric/errors?d=s3&range=7d").get_data(as_text=True)
        assert ">Query</a> › Interface errors and discards over time" in html
        assert 'data-panel-src="/v2/history/query/metric/errors/data?' in html
        assert "d=s3" in html.split('data-panel-src="')[1].split('"')[0]
        assert 'sum by (ifName) (rate(ifInDiscards{device=&#34;s3&#34;}' in html
        assert re.findall(r'class="seg-btn[^"]*"[^>]*>([^<]+)</a>', html) == \
            ["24 h", "7 d", "30 d", "180 d", "1 y"]

    def test_an_unknown_question_is_not_found(self, web):  # noqa: F811
        assert web.get("/v2/history/query/metric/nope").status_code == 404


class TestTheCpuQuestion:
    """Board A's "CPU and memory trend" in board B's layout: per device, two series (CPU from
    either object a device answers, memory from its Processor pool), no interface, and what
    it covers said (the switches carry no memory pool, measured on the host 2026-10-11)."""

    def test_two_series_per_device_each_with_its_legend(self):
        from modules import history_query as H
        every = H.metric_exprs("cpu", {"d": "", "i": "", "range": "30d"})
        assert [l for _e, l in every] == ["{{device}} CPU", "{{device}} memory"]
        assert every[0][0] == "max by (device) (cpmCPUTotal5minRev or cpuAvgBusy5)"
        one = H.metric_exprs("cpu", {"d": "s3", "i": "", "range": "30d"})
        assert one[0][0] == 'max(cpmCPUTotal5minRev{device="s3"} or cpuAvgBusy5{device="s3"})'
        assert 'ciscoMemoryPoolUsed{device="s3",ciscoMemoryPoolName="Processor"}' in one[1][0]
        panel = H.metric_panel("cpu", {"d": "s3", "i": "", "range": "30d"})
        assert [t["refId"] for t in panel["targets"]] == ["A", "B"]

    def test_an_interface_is_refused(self):
        from modules import history_query as H
        with pytest.raises(H.AskRefused) as err:
            H.metric_ask({"d": "r1", "i": "Gi1"}, "cpu")
        assert "asked per device, not per interface" in str(err.value)

    def test_the_page_offers_no_interface_and_says_what_it_covers(self, web, grafana):  # noqa: F811
        html = web.get("/v2/history/query/metric/cpu?d=r1&range=7d").get_data(as_text=True)
        assert ">Query</a> › CPU and memory trend" in html
        assert 'name="i"' not in html and "choose a device to ask by interface" not in html
        assert "<strong>Covers:</strong> CPU on every device" in html
        assert "r1: percent busy and percent of memory used</h3>" in html

    def test_the_data_route_asks_both_series(self, web, grafana):  # noqa: F811
        r = web.get("/v2/history/query/metric/cpu/data?d=r1&range=24h")
        assert r.status_code == 200, r.get_json()
        exprs = [q["expr"] for q in grafana.asked[-1]["queries"]]
        assert len(exprs) == 2 and exprs[0].startswith("max(cpmCPUTotal5minRev")
