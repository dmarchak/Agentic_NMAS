"""C3166's slice 2: one shared Loki tail, filled incrementally, feeding each device's buffer
(modules/readers/logs_tail.py, modules/logs_buffer.py), and the pages that draw it instead of
asking Loki (the device's Logs tab, its drift row, History › Query › Syslog by device), and the
logs builder's bounds and labels from the loki-labels reader (modules/readers/loki_labels.py).

On r3's and s3's real lines (tests/fixtures/loki/device_logs.json, captured from the lab's Loki
2026-10-01); the fake Loki applies each query's own line-filter stages and its time range and
limit, so what is tested is the queries the reader sends. Calls are counted, never timed.

- the first read asks the window; a later read asks from a minute before the newest line held,
  one query for every device, never 15 minutes again; the heartbeats once a minute; one older
  page a read until the buffer reaches back 24 h (30 days for configuration lines), then none;
- a read that returns its limit going forward starts the kind again from its oldest line;
- each device's buffer is bounded and masked;
- the Logs tab, the drift row's part and Syslog by device with a device opened ask Loki
  nothing, draw the buffer's age, and say a failed refresh and a buffer still reading back;
  only the part for lines older than the buffer asks Loki, at most once a minute a question;
- the builder's page asks Loki nothing; Ask's answer does.
"""

import json
import os
import re
import time

import pytest

from modules import logs_buffer as B
from modules import reader_job
from modules.readers import logs_tail as T
from tests.test_device_logs import _keep, _lines, _stages
from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

#: The capture's lines moved, every one by the same amount, to end a minute before this run
#: (a minimal edit: their spacing, text and order as captured), so the buffer is read at the
#: real clock and no clock is replaced.
NOW = time.time()
_SHIFT = int((NOW - 60) * 1e9) - max(ns for ns, _l in _lines("r3") + _lines("s3"))
R3 = [(ns + _SHIFT, line) for ns, line in _lines("r3")]
CORPUS = R3 + [(ns + _SHIFT, line) for ns, line in _lines("s3")]
HEARTBEAT = "NMAS-HEARTBEAT: NMAS-HEARTBEAT"
#: A minimal edit of one of r3's real lines: its mnemonic made a configuration change's.
CONFIG = next(l for _n, l in _lines("r3") if HEARTBEAT not in l and "%SEC_LOGIN" in l)
CONFIG = re.sub(r"%SEC_LOGIN-5-LOGIN_SUCCESS:.*$",
                "%SYS-5-CONFIG_I: Configured from console by <user> on vty0", CONFIG)


class FakeLoki:
    """`logs_tail.read`'s Loki: each query_range answered from the corpus by its own stages,
    its start (inclusive), end (exclusive) and limit, newest first."""

    def __init__(self, corpus=None):
        self.asked, self.corpus = [], list(CORPUS if corpus is None else corpus)

    def configured(self):
        return True

    def ask(self, path, **p):
        self.asked.append(dict(p, path=path))
        lo, hi, stages = int(p["start"]), int(p["end"]), _stages(p["query"])
        kept = sorted((x for x in self.corpus if lo <= x[0] < hi and _keep(x[1], stages)),
                      reverse=True)[:p["limit"]]
        return [{"stream": {}, "values": [[str(ns), l] for ns, l in kept]}] if kept else []


def _kind(p) -> str:
    q = p["query"]
    return "beats" if "|~ `%HA_EM" in q else "changes" if "CONFIG_I" in q else "lines"


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: reader_job.read_cached(name))
    return tmp_path


def fill(loki=None, now=NOW, reads=800):
    """Read every 5 s until every kind reaches back as far as it is kept (at most *reads*);
    returns the last value and how many reads it took."""
    loki = loki or FakeLoki()
    v, t = {}, now - 5 * reads
    for i in range(reads):
        t = now - 5 * (reads - 1 - i)
        v = T.read("Lab", loki=loki, clock=lambda t=t: t, previous=v)
    return v


def store(value, ok=True, error="", value_at="2026-10-01T10:21:00Z"):
    """The reader's stored document, as `reader_job` writes it."""
    path = reader_job.store_path(T.READER_NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = {"last_attempt": {"at": value_at, "ok": ok, "error": error}}
    if value is not None:
        doc["last_good"] = {"value": value, "value_at": value_at}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


class TestTheIncrementalFill:
    def test_a_later_read_asks_only_since_the_newest_line_held(self, data):
        loki = FakeLoki()
        v1 = T.read("Lab", loki=loki, clock=lambda: NOW - 5, previous={})
        assert len(loki.asked) == 1
        first = loki.asked[0]
        assert int(first["end"]) - int(first["start"]) == T.WINDOW_SECONDS * 10 ** 9
        del loki.asked[:]
        T.read("Lab", loki=loki, clock=lambda: NOW, previous=v1)
        forward = loki.asked[0]
        assert _kind(forward) == "lines"
        assert int(forward["start"]) == v1["buffer"]["lines"]["to"] - T.OVERLAP_SECONDS * 10 ** 9
        assert int(forward["end"]) - int(forward["start"]) == (T.OVERLAP_SECONDS + 5) * 10 ** 9
        # Every query for every device: never one device's.
        assert all('|= "' not in p["query"] for p in loki.asked)
        # The lines, the heartbeats' first read, and one older page: three, never more.
        assert [_kind(p) for p in loki.asked] == ["lines", "beats", "lines"]

    def test_filled_it_asks_one_query_a_read_and_the_heartbeats_once_a_minute(self, data):
        loki = FakeLoki()
        v = fill(loki)
        assert all(B.KINDS and v["buffer"][k]["from"] <= int((NOW - B.HORIZON[k]) * 1e9)
                   for k in B.KINDS), v["buffer"]
        del loki.asked[:]
        for i in range(1, 13):                       # a minute of reads, 5 s apart
            v = T.read("Lab", loki=loki, clock=lambda i=i: NOW + 5 * i, previous=v)
        kinds = [_kind(p) for p in loki.asked]
        assert kinds.count("lines") == 12 and kinds.count("beats") == 1, kinds
        assert "changes" not in kinds
        spans = [(int(p["end"]) - int(p["start"])) / 1e9 for p in loki.asked]
        # About a minute each, against the 15 minutes every read asked before (C3166).
        assert max(spans) <= T.BEATS_EVERY + T.OVERLAP_SECONDS + 5
        assert sum(spans) < 12 * T.WINDOW_SECONDS / 5

    def test_it_fills_back_one_page_a_read_until_it_holds_every_line(self, data, monkeypatch):
        monkeypatch.setattr(T, "BACKFILL_LIMIT", 4)
        loki = FakeLoki()
        v = {}
        for i in range(80):
            before = len(loki.asked)
            v = T.read("Lab", loki=loki, clock=lambda i=i: NOW + 5 * i, previous=v)
            # The lines, at most the heartbeats, and at most one older page.
            assert len(loki.asked) - before <= 3
        held = B.load(v["buffer"]["store"], "r3")
        want = sorted((ns for ns, l in R3 if HEARTBEAT not in l), reverse=True)
        assert [e["ns"] for e in held["lines"]] == want
        assert sorted(held["beats"], reverse=True) == sorted(
            (ns for ns, l in R3 if HEARTBEAT in l), reverse=True)

    def test_after_failed_reads_the_forward_read_never_asks_past_its_window(self, data):
        """C3330 (the NMAS host, 2026-11-12): every read failed from 14:36:21 UTC, the cover's
        end stayed there, and each later read asked from it to now, a range growing toward the
        24 h floor that Loki could not answer in time. Two hours of failed reads later, the
        next forward read asks only the tail's own window."""
        v1 = fill()
        later = NOW + 7200
        loki = FakeLoki()
        T.read("Lab", loki=loki, clock=lambda: later, previous=v1)
        forward = [p for p in loki.asked if _kind(p) == "lines"
                   and int(p["end"]) >= int(later * 1e9)]
        assert forward, loki.asked
        assert int(forward[0]["start"]) >= int((later - T.WINDOW_SECONDS) * 1e9), forward[0]

    def test_an_older_page_spans_at_most_its_page_and_a_failed_one_keeps_the_read(self, data):
        """C3330's second hotfix (the NMAS host, 2026-11-12 18:38 UTC): after the first hotfix the
        read still failed every 20 s, because one older page asked from the 24 h floor (30 days
        for the changes) to the oldest line held, which Loki could not answer in time, and that
        page's failure failed the whole read, the lines going forward (detection's) with it."""
        v1 = T.read("Lab", loki=FakeLoki(), clock=lambda: NOW, previous={})
        loki = FakeLoki()
        T.read("Lab", loki=loki, clock=lambda: NOW + 5, previous=v1)
        older = [p for p in loki.asked if int(p["end"]) <= v1["buffer"]["lines"]["from"] + 1]
        assert older, loki.asked
        assert all(int(p["end"]) - int(p["start"]) <= (T.BACKFILL_PAGE_SECONDS + 1) * 1e9
                   for p in older), older

        class OlderFails(FakeLoki):
            def ask(self, path, **p):
                if int(p["end"]) <= v1["buffer"]["lines"]["from"] + 1:
                    raise RuntimeError("Loki did not answer within 5 s (planted)")
                return super().ask(path, **p)

        v2 = T.read("Lab", loki=OlderFails(), clock=lambda: NOW + 5, previous=v1)
        assert v2["configured"] and v2["lines"], "the lines going forward were kept"
        assert v2["buffer"]["lines"]["to"] == int((NOW + 5) * 1e9)

    def test_a_read_that_returns_its_limit_going_forward_starts_again_from_its_oldest(
            self, data, monkeypatch):
        v1 = fill()
        burst = [(int((NOW + 100) * 1e9) + i, CONFIG.replace("vty0", f"vty{i}")) for i in range(8)]
        monkeypatch.setattr(T, "WINDOW_LIMIT", 5)
        monkeypatch.setattr(T, "BACKFILL_LIMIT", 2)
        v2 = T.read("Lab", loki=FakeLoki(CORPUS + burst), clock=lambda: NOW + 300, previous=v1)
        by_age = sorted((ns for ns, _l in burst), reverse=True)
        # The forward read held the newest five; the hole under them is read back one page a
        # read (two lines here, the first the boundary's own again), so the kind is whole only
        # from the oldest of that page.
        assert v2["buffer"]["lines"]["from"] == by_age[5]
        assert v2["truncated"] is True
        held = [e["ns"] for e in B.load(v2["buffer"]["store"], "r3")["lines"]]
        assert set(by_age[:6]) <= set(held) and not set(by_age[6:]) & set(held)

    def test_each_device_is_bounded_and_masked(self, data):
        newest = max(ns for ns, _l in CORPUS)
        burst = [(newest + 1 + i, CONFIG.replace("vty0", f"vty{i}"))
                 for i in range(B.DEVICE_LINES + 5)]
        secret = "username admin password 0 Sup3rSecret"
        planted = (newest + len(burst) + 1, CONFIG.replace(
            "Configured from console by <user> on vty0", secret))
        v = fill(FakeLoki(CORPUS + burst + [planted]))
        held = B.load(v["buffer"]["store"], "r3")
        assert len(held["lines"]) == B.DEVICE_LINES and held["lines"][0]["ns"] == planted[0]
        assert len(held["changes"]) == B.DEVICE_CHANGES
        assert held["changes"][0]["mn"] == "%SYS-5-CONFIG_I"
        assert "Sup3rSecret" not in json.dumps(held)

    def test_it_announces_a_heartbeat_and_a_buffer_reaching_back(self, data):
        v1 = T.read("Lab", loki=FakeLoki(), clock=lambda: NOW, previous={})
        v2 = T.read("Lab", loki=FakeLoki(), clock=lambda: NOW + 5, previous=v1)
        assert T.changed(v1, v2), "the buffer reached further back"
        v = fill()
        quiet = T.read("Lab", loki=FakeLoki(), clock=lambda: NOW + 5, previous=v)
        assert not T.changed(v, quiet), "nothing new, nothing announced"


# ---------------------------------------------------------------------------- the pages


class _Empty:
    def json(self):
        return {"status": "success", "data": {"result": []}}


@pytest.fixture
def counted(monkeypatch):
    """Every Loki read through the integration client, counted; each answers with nothing."""
    from modules.integrations.loki import LokiIntegration
    calls = []

    def get(self, path, **params):
        calls.append(path)
        return {"ok": True, "response": _Empty()}
    monkeypatch.setattr(LokiIntegration, "is_configured", lambda self: True)
    monkeypatch.setattr(LokiIntegration, "_get", get)
    monkeypatch.setattr("modules.device_logs._LABEL", {"since": None, "asked": None})
    return calls


@pytest.fixture
def page(lab, counted, tmp_path, monkeypatch):  # noqa: F811
    from modules import device_page
    from modules.nsot import listref
    monkeypatch.setattr("modules.reader_job.store_path",
                        lambda name: str(tmp_path / "readers" / f"{name}.json"))
    monkeypatch.setattr(device_page, "find_device", lambda name, ref=None: (
        listref.resolve("Lab"), {"hostname": name, "ip": "192.0.2.1", "platform": "cisco_ios"}))
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: reader_job.read_cached(name))
    return counted


class TestNoPageAsksLoki:
    def test_the_logs_tab_draws_the_buffer_and_its_age(self, lab, page, monkeypatch):
        store(fill())
        html = lab["client"].get("/v2/device/r3/logs").get_data(as_text=True)
        assert page == [], page
        assert re.search(r"\d+ heartbeat\(s\) in the last 24 h, the last <time", html), html
        assert "<code>%SEC_LOGIN-5-LOGIN_SUCCESS</code>" in html
        assert 'data-age="2026-10-01T10:21:00Z"' in html and "held by Mercury" in html
        assert "nmas:logs from:body" in html

    def test_before_the_first_read_it_says_reading_never_quiet(self, lab, page):
        html = lab["client"].get("/v2/device/r3/logs").get_data(as_text=True)
        assert page == [] and "Reading Loki" in html and "fills itself" in html
        assert "sent nothing" not in html

    def test_a_failed_refresh_keeps_the_lines_and_says_it_failed(self, lab, page, monkeypatch):
        store(fill(), ok=False, error="Loki could not be asked: connection refused")
        html = lab["client"].get("/v2/device/r3/logs").get_data(as_text=True)
        assert page == []
        assert "The last refresh failed (Loki could not be asked: connection refused)" in html
        assert "<code>%SEC_LOGIN-5-LOGIN_SUCCESS</code>" in html

    def test_a_buffer_still_reading_back_says_from_when(self, lab, page, monkeypatch):
        store(T.read("Lab", loki=FakeLoki(), clock=lambda: NOW, previous={}))
        html = lab["client"].get("/v2/device/r3/logs").get_data(as_text=True)
        assert page == [] and "Loading older lines: held from <time" in html

    def test_the_drift_rows_log_part_asks_nothing(self, lab, page, monkeypatch):
        store(fill(FakeLoki(CORPUS + [(max(ns for ns, _l in CORPUS) + 1, CONFIG)])))
        html = lab["client"].get("/v2/device/r3/drift").get_data(as_text=True)
        assert page == [], page
        assert "%SYS-5-CONFIG_I" in html and 'id="drift-log"' in html
        assert "nmas:logs from:body" in html


class TestSyslogByDevice:
    """On test_logs_v2's counts (its lab) and r3's real lines at this run's time."""

    @pytest.fixture
    def web(self, data, counted, monkeypatch):
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
        web = A.app.test_client()
        web.corpus, web.now = CORPUS, NOW
        return web

    def test_a_device_opened_draws_the_buffer_and_asks_loki_only_for_older(self, web, counted):
        store(fill(FakeLoki(web.corpus), now=web.now))
        html = web.get("/v2/logs/view?list=Lab&range=24h&sev=all&d=r3").get_data(as_text=True)
        assert counted == [], counted
        rows = re.findall(r'<tr><td class="mono">(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)</td>', html)
        assert len(rows) == sum(1 for _n, l in R3 if HEARTBEAT not in l)
        assert 'id="lg-older"' not in html, "the buffer holds the whole range"
        week = web.get("/v2/history/query/syslog?list=Lab&range=7d&sev=all&d=r3"
                       ).get_data(as_text=True)
        assert counted == [], "the page asked Loki"
        older = re.search(r'<tbody id="lg-older" hx-get="([^"]+)" hx-trigger="load"', week)
        assert older and "Loading older lines" in week
        url = older.group(1).replace("&amp;", "&")
        web.get(url)
        first = list(counted)
        assert first and first[-1] == "loki/api/v1/query_range"
        for _i in range(3):                          # the region redrawn by announcements
            web.get(url)
        assert counted == first, "the same question within a minute asks Loki again"

    def test_no_buffer_yet_the_older_part_asks_for_the_whole_range(self, web, counted):
        html = web.get("/v2/logs/view?list=Lab&range=24h&sev=all&d=r3").get_data(as_text=True)
        assert counted == [] and 'id="lg-older"' in html


class TestTheBuilder:
    @pytest.fixture
    def builder(self, data, counted, monkeypatch):
        (data / "lab").mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(data / "lab"))
        monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
        monkeypatch.setattr("modules.history_logq.roles", lambda ln: [("router", 5)])
        monkeypatch.setattr("modules.history_logq._devices_of_role", lambda ln, role: [])
        from modules import history_logq as Q
        Q.forget()
        yield Q
        Q.forget()

    def test_its_page_draws_the_labels_reader_and_asks_nothing(self, builder, counted,
                                                               monkeypatch):
        from tests import test_history_ask_logs as H
        from modules.readers import loki_labels
        Q = builder
        fake = H.FakeLoki()
        monkeypatch.setattr("modules.history_logq._now", lambda: H.NOW)
        value = loki_labels.read("Lab", client=fake, clock=lambda: H.NOW)
        assert value["configured"] and set(value["ranges"]) == set(Q.RANGES)
        path = reader_job.store_path(loki_labels.READER_NAME)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"last_attempt": {"ok": True}, "last_good": {
                "value": value, "value_at": "2026-10-15T08:20:00Z"}}, fh)
        Q.forget()
        q = Q.view("Lab", {"range": "24h"}, now=H.NOW)
        assert counted == [], counted
        assert q["disc"]["state"] == "ok" and q["disc"]["held"]["range"] == "24h"
        assert q["disc"]["values"]["job"] == value["ranges"]["24h"]["values"]["job"]
        assert set(q["limits"]) == set(value["limits"])
        # Ask pressed (ask=1): the person's question, and only it, is asked of Loki.
        Q.view("Lab", {"range": "24h", "ask": "1"}, now=H.NOW)
        assert counted and set(counted) <= {"loki/api/v1/query_range", "loki/api/v1/query"}

    def test_before_its_first_read_the_builder_says_reading(self, builder, counted):
        q = builder.view("Lab", {"range": "24h"})
        assert counted == [] and q["disc"]["state"] == "reading"

    def test_asked_before_its_first_read_it_is_refused_never_asked_blind(self, builder,
                                                                         counted):
        q = builder.view("Lab", {"range": "24h", "ask": "1"})
        assert counted == [] and q["answer"]["state"] == "error"
