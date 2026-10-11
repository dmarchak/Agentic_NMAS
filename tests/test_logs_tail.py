"""C675, the sidebar's Logs as a live tail (board D, LogsTail; the operator, 2026-10-11): the
logs-tail reader (modules/readers/logs_tail.py) on real lines of the lab's Loki
(tests/fixtures/loki/lines_r4.json and lines_s3.json), and the page through its routes
(modules/logs_tail_page.py, templates/v2/_logs_tail.html).

- the reader asks ONE query over the last 15 minutes for every device (never per device),
  heartbeats left out, newest first, each line's device, severity and mnemonic, the text
  masked; a read that returns its limit is truncated; it announces only when something new
  arrived;
- the page: the window's counts first, whatever the filters; the four filters; the newest 200
  drawn and a cut list saying so; Pause holds the window and counts what arrived since;
  History › Query's "Open these lines on Logs" arrives filtered and says so; "older than 15
  minutes" goes back to History › Query with the same filters; the store's states each said.
"""

import json
import os
import re

import pytest

from modules import reader_job
from modules.readers import logs_tail as T

LOKI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "loki")


def _streams():
    out = []
    for f in ("lines_r4.json", "lines_s3.json"):
        with open(os.path.join(LOKI, f), encoding="utf-8") as fh:
            out += json.load(fh)["answer"]["data"]["result"]
    return out


class FakeLoki:
    def __init__(self, streams=None):
        self.asked, self.streams = [], _streams() if streams is None else streams

    def configured(self):
        return True

    def ask(self, path, **params):
        self.asked.append((path, params))
        return self.streams


NOW = max(int(ns) for s in _streams() for ns, _l in s["values"]) / 1e9 + 30


def _read(loki=None):
    return T.read("Lab", loki=loki or FakeLoki(), clock=lambda: NOW)


class TestTheReader:
    def test_one_query_for_every_device_over_the_window(self):
        loki = FakeLoki()
        v = _read(loki)
        assert len(loki.asked) == 1
        path, p = loki.asked[0]
        assert path == "loki/api/v1/query_range" and p["direction"] == "backward"
        assert "!~ `%HA_EM-" in p["query"] and "|=" not in p["query"], "never one device's query"
        assert int(p["end"]) - int(p["start"]) == T.WINDOW_SECONDS * 10 ** 9
        assert p["limit"] == T.WINDOW_LIMIT and v["configured"] is True

    def test_lines_newest_first_with_their_fields(self):
        v = _read()
        ts = [l["ts"] for l in v["lines"]]
        assert ts == sorted(ts, reverse=True) and len(ts) == sum(len(s["values"])
                                                                 for s in _streams())
        assert {l["dev"] for l in v["lines"]} == {"r4", "s3"}
        known = [l for l in v["lines"] if l["mn"]]
        assert known and all(re.match(r"^%[A-Z0-9_-]+-[0-7]-", l["mn"]) for l in known)
        assert all(l["sev"] == int(re.search(r"-([0-7])-", l["mn"]).group(1)) for l in known)
        assert all(l["at"].endswith("Z") for l in v["lines"])

    def test_the_text_is_masked_on_the_way_in(self):
        secret = "username admin password 0 Sup3rSecret"
        ns = str(int(NOW * 1e9) - 1)
        line = f"<189>Oct 11 10:00:00 192.0.2.1 r4: Oct 11 10:00:00.000: %SYS-5-CONFIG_I: {secret}"
        v = T.read("Lab", loki=FakeLoki([{"stream": {}, "values": [[ns, line]]}]),
                   clock=lambda: NOW)
        assert "Sup3rSecret" not in json.dumps(v)

    def test_a_read_that_returns_its_limit_is_truncated(self, monkeypatch):
        monkeypatch.setattr(T, "WINDOW_LIMIT", 3)
        v = _read()
        assert v["truncated"] is True and len(v["lines"]) == 3

    def test_it_announces_only_when_something_new_arrived(self):
        a = _read()
        assert not T.changed(a, dict(a, read_at="later", read_at_ts=NOW + 5))
        newer = dict(a, lines=[dict(a["lines"][0], ts=a["lines"][0]["ts"] + 1)] + a["lines"])
        assert T.changed(a, newer)


@pytest.fixture
def web(tmp_path, monkeypatch):
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: reader_job.read_cached(name))
    path = reader_job.store_path("logs-tail")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    def store(value, ok=True, error=""):
        doc = {"last_attempt": {"at": "2026-10-11T18:20:17Z", "ok": ok, "error": error}}
        if value is not None:
            doc["last_good"] = {"value": value, "value_at": "2026-10-11T18:20:12Z"}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    store(_read())
    import app as A
    yield {"client": A.app.test_client(), "store": store}
    os.remove(path)


def _get(web, query=""):
    return web["client"].get(f"/v2/logs/tail?list=Lab{query}").get_data(as_text=True)


def _rows(html):
    return re.findall(r'<tr><td class="mono">(\d\d:\d\d:\d\d)</td><td class="mono"><a [^>]*>'
                      r'(\w+)</a>', html)


class TestThePage:
    def test_the_sidebar_s_logs_is_the_tail(self, web):
        html = web["client"].get("/v2/logs?list=Lab").get_data(as_text=True)
        assert re.search(r'<a class="nav-item active" href="/v2/logs"', html)
        assert 'hx-trigger="nmas:logs from:body"' in html and 'id="logs-tail"' in html
        assert "Live · checked every 5 s" in html and "Pause</a>" in html

    def test_the_window_s_counts_come_first_and_lines_newest_first(self, web):
        v = _read()
        html = _get(web)
        assert f"<strong>{len(v['lines'])}</strong> lines in the last 15 minutes" in html
        errors = sum(1 for l in v["lines"] if l["sev"] is not None and l["sev"] <= 3)
        assert f"{errors} error or worse" in html and "from 2 devices" in html
        rows = _rows(html)
        assert rows and len(rows) == min(len(v["lines"]), 200)
        assert rows[0][1] == v["lines"][0]["dev"]

    def test_each_filter_narrows_and_says_how_many_match(self, web):
        html = _get(web, "&d=s3")
        assert {d for _t, d in _rows(html)} == {"s3"} and " lines match." in html
        html = _get(web, "&sev=error")
        assert "error or worse (0 to 3)</option>" in html
        assert all(b in ("0", "1", "2", "3") for b in re.findall(r'badge-danger">(\d) ', html))
        mn = next(l["mn"] for l in _read()["lines"] if l["mn"])
        assert all(d for _t, d in _rows(_get(web, f"&mn={mn}")))
        assert "No line in the window matches these filters." in _get(web, "&text=zz-none-zz")

    def test_pause_holds_the_window_and_counts_what_arrived(self, web):
        import calendar
        import time
        v = _read()
        at = v["lines"][5]["at"]
        # The pause holds at a whole second (the address carries the read's second).
        held = calendar.timegm(time.strptime(at, "%Y-%m-%dT%H:%M:%SZ"))
        later = sum(1 for l in v["lines"] if l["ts"] > held)
        html = _get(web, f"&paused={at}")
        assert f"{later} new line{'s' if later != 1 else ''} since" in html and "Resume</a>" in html
        held_lines = sum(1 for l in v["lines"] if l["ts"] <= held)
        assert len(_rows(html)) == min(held_lines, 200)

    def test_from_history_query_it_arrives_filtered_and_says_so(self, web):
        html = _get(web, "&d=s3&sev=error&text=Gi0%2F3&from=query")
        assert "Filtered as you came from History › Query: device" in html
        assert "Clear filters</a> to see every line." in html

    def test_older_lines_go_back_to_history_query_with_the_filters(self, web):
        html = _get(web, "&d=s3&sev=warning")
        older = re.search(r'Older than 15 minutes: <a href="([^"]+)"', html).group(1)
        assert older.startswith("/v2/history/query/syslog?") and "d=s3" in older
        assert "sev=warning" in older

    def test_history_query_s_drilldown_opens_these_lines_on_logs(self):
        """Board C's link, in the drill-down's footer, carrying the device and the filters."""
        path = os.path.join(os.path.dirname(os.path.dirname(LOKI)), "..", "templates", "v2",
                            "_logs_view.html")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        link = re.search(r"<a href=\"\{\{ url_for\('logs_v2\.page',(.*?)\) \}\}\">Open these lines "
                         r"on Logs</a>", src)
        assert link and all(k in link.group(1) for k in ("d=r.device", "sev=", "mn=", "text=",
                                                         "'from': 'query'"))

    @pytest.mark.parametrize("value,ok,words", [
        (None, True, "The logs-tail reader has not read the log store yet"),
        ({"configured": False}, True, "no log store is configured for this network"),
    ])
    def test_each_state_has_its_words(self, web, value, ok, words):
        web["store"](value, ok)
        assert words in _get(web)

    def test_a_failed_read_draws_the_last_window_with_its_error(self, web):
        web["store"](_read(), ok=False, error="Loki could not be asked: connection refused")
        html = _get(web)
        assert "The log store did not answer at 18:20:17 UTC" in html and "connection refused" in html
        assert _rows(html)
