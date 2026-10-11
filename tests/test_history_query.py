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
    assert links == [("/v2/history/query/syslog", "Syslog by device")]
    assert html.count("not built yet") == 5


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
