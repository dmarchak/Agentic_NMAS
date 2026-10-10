"""OBSERVE › Logs (C652): the network's syslog by device, drawn to History › Query board C
(AskLogs), on real captures of the lab's Loki (tests/fixtures/loki/: three days' counts by
device and mnemonic, and r4's and s3's lines, captured 2026-10-10 and sanitised on the host:
every address mapped into 192.0.2.0/24 or 2001:db8::/32, account names `<user>`).

The reader (modules/readers/logs_summary.py):
- counts each day once, by device and mnemonic, heartbeats left out, unparsed lines apart;
  re-reads today and the last 24 h; fills the past at most 7 days a read, inside the network's
  Logs retention and since the store's first line; drops a day past the retention;
- keeps each device's newest line, and fails the read (never an empty count) when Loki cannot
  be asked.

The page (routes/logs_v2.py, templates/v2/_logs_view.html):
- the sidebar's Logs opens it, never the app's own log;
- the headline and the device table sum the kept days for the range and severity (expected
  counts summed here from the fixture, independently);
- the range says what it can hold: days before the store's first line, days still being
  counted, Loki holding more than the retention states;
- a device opened: its filters, its trend by mnemonic, its lines from Loki newest first and
  masked, a refused filter saying why with nothing asked, the device's own Logs tab one link away;
- each empty state in its own words.
"""

import json
import os
import re
import time

import pytest

from modules import reader_job
from modules.readers import logs_summary as L

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOKI = os.path.join(ROOT, "tests", "fixtures", "loki")
MANAGED = ["r1", "r2", "r3", "r4", "r6", "s1", "s2", "s3", "s4"]


def _fx(name):
    with open(os.path.join(LOKI, name), encoding="utf-8") as fh:
        return json.load(fh)


DAYS = _fx("day_counts.json")["days"]
#: The read happens at noon of the day after the last captured one.
NOW = max(v["time"] for v in DAYS.values()) + 12 * 3600
FIRST_NS = str(int((NOW - 33 * 86400) * 1e9))


class FakeLoki:
    """Answers as the lab's Loki did: each captured day's count at its end, the newest day's
    for today and the last 24 h, r4's and s3's lines, the first line 33 days back."""

    def __init__(self, fail=False):
        self.asked, self.fail = [], fail

    def configured(self):
        return True

    def ask(self, path, **params):
        self.asked.append((path, params))
        if self.fail:
            raise RuntimeError("Loki could not be asked (loki/api/v1/query): connection refused")
        if path.endswith("/query"):
            for v in DAYS.values():
                if str(v["time"]) == params["time"]:
                    return v["answer"]["data"]["result"]
            newest = max(DAYS.values(), key=lambda v: v["time"])
            return newest["answer"]["data"]["result"]
        if params.get("direction") == "forward":
            return [{"stream": {}, "values": [[FIRST_NS, "first"]]}]
        return [s for f in ("lines_r4.json", "lines_s3.json")
                for s in _fx(f)["answer"]["data"]["result"]]


def _read(previous=None, loki=None, retention=730):
    return L.read(list_name="Lab", loki=loki or FakeLoki(), clock=lambda: NOW,
                  previous=previous or {}, retention_days=retention)


def _sum(day, sevmax, devices=MANAGED):
    """Lines at or below *sevmax* in a captured day: summed from the fixture, not the code."""
    n = 0
    for row in DAYS[day]["answer"]["data"]["result"]:
        m = row["metric"]
        sev = re.search(r"-([0-7])-[A-Z0-9_]+$", m.get("mn", ""))
        if m.get("dev") in devices and sev and int(sev.group(1)) <= sevmax:
            n += int(float(row["value"][1]))
    return n


class TestTheReader:
    def test_each_captured_day_is_counted_by_device_and_mnemonic(self):
        v = _read()
        for day in DAYS:
            assert day in v["days"], day
            total = sum(n for mns in v["days"][day].values() for n in mns.values())
            assert total == _sum(day, 7, devices=set(v["days"][day])), day
        assert all(mn.startswith("%") for d in v["days"].values() for m in d.values() for mn in m)

    def test_heartbeats_are_left_out_and_unparsed_lines_kept_apart(self):
        loki = FakeLoki()
        v = _read(loki=loki)
        counts = [p["query"] for path, p in loki.asked if path.endswith("/query")]
        assert counts and all("!~ `%HA_EM-" in q for q in counts)
        unparsed = sum(int(float(r["value"][1])) for r in DAYS["2026-10-07"]["answer"]["data"]["result"]
                       if not r["metric"])
        assert unparsed and v["unparsed"]["2026-10-07"] == unparsed

    def test_the_past_is_filled_seven_days_a_read_and_carried(self):
        v1 = _read()
        assert len(v1["days"]) == 1 + 7 and v1["days_missing"] == 33 - 7
        v2 = _read(previous=v1)
        assert len(v2["days"]) == 1 + 14
        assert v2["first_day"] == v1["first_day"] == time.strftime(
            "%Y-%m-%d", time.gmtime(int(FIRST_NS) / 1e9))

    def test_a_day_past_the_retention_is_dropped_and_never_asked(self):
        v = _read(retention=3)
        assert sorted(v["days"]) == sorted(set(v["days"]))
        assert len(v["days"]) == 3 and v["days_missing"] == 0

    def test_each_device_s_newest_line(self):
        v = _read()
        newest_r4 = max(int(t) for s in _fx("lines_r4.json")["answer"]["data"]["result"]
                        for t, _l in s["values"])
        assert v["newest"]["r4"] == time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime(newest_r4 / 1e9))
        assert "s3" in v["newest"]

    def test_loki_unanswered_fails_the_read(self):
        with pytest.raises(RuntimeError, match="connection refused"):
            _read(loki=FakeLoki(fail=True))


# ---------------------------------------------------------------------------- the page

def _store(value, ok=True, name="logs-summary"):
    path = reader_job.store_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = {"last_attempt": {"at": "2026-10-10T21:30:00Z", "ok": ok,
                            "error": "" if ok else "Loki could not be asked"}}
    if value is not None:
        doc["last_good"] = {"value": value, "value_at": "2026-10-10T21:30:00Z"}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


@pytest.fixture
def web(tmp_path, monkeypatch):
    from types import SimpleNamespace
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.readers.adjacencies.lists",
                        lambda: [("Lab", SimpleNamespace(repo_dir=str(tmp_path)), MANAGED)])
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: reader_job.read_cached(name))
    v1 = _read()
    _store(_read(previous=v1, retention=730))
    import app as A
    yield A.app.test_client()
    os.remove(reader_job.store_path("logs-summary"))


def _get(web, query=""):
    return web.get(f"/v2/logs/view?list=Lab{query}").get_data(as_text=True)


def _now(monkeypatch):
    monkeypatch.setattr("modules.logs_page.time.time", lambda: NOW)


def test_the_sidebar_s_logs_opens_the_queryable_logs(web):
    html = web.get("/v2/logs?list=Lab").get_data(as_text=True)
    assert re.search(r'<a class="nav-item active" href="/v2/logs" aria-current="page">', html)
    assert "the app&#39;s own" not in html and "<h1>Syslog by device" in html
    assert 'hx-trigger="nmas:logs from:body"' in html
    assert 'data-label="Copy the link"' in html and "range=" not in html.split("data-copy=")[1][:80]


def test_the_headline_and_table_sum_the_kept_days(web, monkeypatch):
    _now(monkeypatch)
    html = _get(web, "&range=7d")
    days = [d for d in DAYS]
    want = sum(_sum(d, 3) for d in days)
    # Seven days: the three captured, and four the fake answers with the newest captured day.
    newest = max(DAYS, key=lambda d: DAYS[d]["time"])
    want = sum(_sum(d, 3) for d in days) + 4 * _sum(newest, 3)
    m = re.search(r"<strong>(\d+) lines? at error or worse, (\d+) devices?</strong>", html)
    assert m and int(m.group(1)) == want
    assert html.count('class="btn btn-small mono lg-dev"') == int(m.group(2))
    every = re.search(r"<strong>(\d+) lines? at every severity", _get(web, "&range=7d&sev=all"))
    assert int(every.group(1)) > want


def test_the_range_says_what_it_can_hold(web, monkeypatch):
    _now(monkeypatch)
    html = _get(web, "&range=120d")
    assert "Part of this range holds nothing yet" in html
    assert "this network keeps logs 730 days" in html
    assert re.search(r"the first \d+ days of this 120-day range were never kept", html)
    assert "still being counted" in html
    assert "Part of this range" not in _get(web, "&range=24h")


def test_loki_holding_more_than_the_setting_says_is_said(web, monkeypatch):
    _now(monkeypatch)
    _store(_read(retention=10))
    html = _get(web, "&range=7d")
    assert "older than this network's Logs retention (10 days) says" in html


def test_a_device_opened_draws_its_filters_trend_and_lines(web, monkeypatch):
    _now(monkeypatch)
    lines = _fx("lines_r4.json")["answer"]
    asked = []

    def get(self, path, **params):
        asked.append(params)

        class R:
            def json(self_inner):
                return lines
        return {"ok": True, "response": R()}
    monkeypatch.setattr("modules.integrations.loki.LokiIntegration._get", get)
    html = _get(web, "&range=7d&sev=all&d=r4")
    assert "aria-label=\"Filter r4's lines\"" in html and "Trend by mnemonic" in html
    assert html.count('<polyline class="lg-line') >= 1
    assert "%DBAL-4-DELAYED_BATCH" in html
    rows = re.findall(r'<tr><td class="mono">(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)</td>', html)
    assert len(rows) == 50 and rows == sorted(rows, reverse=True)
    assert "href=\"/v2/device/r4?list=Lab&amp;tab=logs\">Open r4's Logs tab" in html
    assert "the next 50" in html
    q = asked[-1]["query"]
    assert '|= "r4:"' in q and "!~ `%HA_EM-" in q and int(asked[-1]["limit"]) == 50
    span = (int(asked[-1]["end"]) - int(asked[-1]["start"])) / 1e9
    assert span <= 30 * 86400 + 1


def test_a_refused_filter_says_why_and_asks_nothing(web, monkeypatch):
    _now(monkeypatch)
    monkeypatch.setattr("modules.integrations.loki.LokiIntegration._get",
                        lambda *a, **k: pytest.fail("Loki was asked"))
    assert "the text may not hold a quote, a backtick" in _get(web, "&d=r4&text=a%60b")
    assert "is not a mnemonic" in _get(web, "&d=r4&mn=nope")
    assert "is not a time this reads" in _get(web, "&d=r4&from=yesterday")
    assert "is not a device of Lab" in _get(web, "&d=r9")


@pytest.mark.parametrize("value,ok,words", [
    (None, True, "The logs reader has not counted yet"),
    ({"configured": False}, True, "Loki is not configured for this network"),
])
def test_each_state_has_its_words(web, value, ok, words):
    _store(value, ok)
    assert words in _get(web)
