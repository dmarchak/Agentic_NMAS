"""C3330: while the logs buffer is stale, the Logs pages say so and never look current
(modules/logs_buffer.py `stale_words`; templates/v2/_logs.html, _drift_detail.html,
_logs_view.html).

"Stale" is the logs-tail reader's own promise, as its job-health row judges it: its interval
times its stale factor (5 s x 3). Past it, the device's Logs tab, the drift row's log part and
Syslog by device with a device opened draw "Held lines are <age> old: the logs reader has
stopped (<its last error>)" in the warning colour, in place of the held-by line; a fresh store
draws the held-by line and no such words. The reader's own Needs attention row opens Syslog by
device, where the words are. On a planted store, r3's real lines (test_logs_buffer's corpus).
"""

import re
import time

import pytest

from modules import logs_buffer as B
from modules import reader_job
from modules.readers import logs_tail as T
from tests.test_logs_buffer import (CORPUS, NOW, FakeLoki, counted, data, fill,  # noqa: F401
                                    page, store)
from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

ERROR = "RuntimeError: Loki did not answer within 5 s (loki/api/v1/query_range)"


def _ago(seconds):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds))


def _stale():
    """The buffer as the incident left it: the last good read 12 minutes ago, every read since
    failing."""
    path = store(fill(), value_at=_ago(720))
    doc = reader_job.read_cached(T.READER_NAME)["doc"]
    doc["last_attempt"] = {"at": _ago(3), "ok": False, "error": ERROR}
    import json
    with open(reader_job.store_path(T.READER_NAME), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path


WORDS = re.compile(r"Held lines are 12 min(?: \d+ s)? old: the logs reader has stopped \(Loki "
                   r"did not answer within 5 s \(loki/api/v1/query_range\)\)")


class TestTheWords:
    def test_past_the_promise_it_says_how_old_and_why(self, data):
        _stale()
        h = B.held("Lab", "r3")
        assert WORDS.fullmatch(h["stale"]), h["stale"]
        assert B.promise_seconds() == T.INTERVAL_SECONDS * T.READER.stale_after_intervals == 15

    def test_inside_the_promise_it_says_nothing(self, data):
        store(fill())
        assert B.held("Lab", "r3")["stale"] == ""

    def test_a_reader_that_stopped_reading_says_since_when(self, data):
        store(fill(), value_at=_ago(600))
        assert "the logs reader has stopped (it has not read since " in B.held("Lab", "r3")["stale"]


class TestThePages:
    def test_the_logs_tab_draws_it_in_place_of_the_held_by_line(self, lab, page):
        _stale()
        html = lab["client"].get("/v2/device/r3/logs").get_data(as_text=True)
        assert page == [], "stale or not, the page asks Loki nothing (C3166): it says how old"
        assert WORDS.search(html), html[-800:]
        assert re.search(r'class="notice notice-warn"[^>]*id="logs-held"', html)
        assert "held by Mercury" not in html and "The last refresh failed" not in html

    def test_a_fresh_logs_tab_draws_the_held_by_line(self, lab, page):
        store(fill())
        html = lab["client"].get("/v2/device/r3/logs").get_data(as_text=True)
        assert page == [], "stale or not, the page asks Loki nothing (C3166): it says how old"
        assert "held by Mercury" in html and "Held lines are" not in html

    def test_the_drift_rows_log_part_says_it(self, lab, page):
        _stale()
        html = lab["client"].get("/v2/device/r3/drift").get_data(as_text=True)
        assert page == [], "stale or not, the page asks Loki nothing (C3166): it says how old"
        assert WORDS.search(html) and "data-held-stale" in html
        assert "held by the logs reader, read" not in html

    @pytest.fixture
    def web(self, data, counted, monkeypatch):  # noqa: F811
        from types import SimpleNamespace

        from modules import logs_page
        from tests import test_logs_v2 as L
        (data / "lab").mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(data / "lab"))
        monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
        monkeypatch.setattr("modules.readers.adjacencies.lists",
                            lambda: [("Lab", SimpleNamespace(repo_dir=str(data)), L.MANAGED)])
        L._store(L._read(previous=L._read(), retention=730))
        monkeypatch.setattr(logs_page, "_OLDER", {})
        import app as A
        return A.app.test_client()

    def test_syslog_by_device_says_it(self, web, counted):  # noqa: F811
        _stale()
        html = web.get("/v2/logs/view?list=Lab&range=24h&sev=all&d=r3").get_data(as_text=True)
        assert counted == [], "stale or not, the region asks Loki nothing: it says how old"
        assert WORDS.search(html) and 'id="logs-held"' in html
        assert "held by the logs reader, read" not in html


class TestTheRowOpensIt:
    def test_the_readers_failing_row_opens_syslog_by_device(self, data):
        _stale()
        (row,) = reader_job.health_rows(now=time.time(), population=[T.READER])
        assert row["state"] in ("failing", "stale")
        assert row["action"]["href"] == "/v2/history/query/syslog"
