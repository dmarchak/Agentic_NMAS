"""The stall captures itself (C2003; the operator, 2026-11-02: "make the stall capture itself
... no live catching by me").

The moment a page shows its stale note (static/js/nmas_v2.js `drawStale`), it posts what it
knows of itself and its live connection (`stallBody`, `NMAS.liveDetail`) to
`/v2/diagnostics/stall`; the app adds its own view of that connection
(`stall_capture.server_view`) and keeps one row (`modules/stall_capture.py`), which History's
"Page stalls" kind draws (`history_sources.page_stalls`), for the UNKNOWN row that names it as
its measurement.

- **The record:** only declared fields, bounded; anything else dropped and counted; a body
  that is not a stall refused; one tab held to its per-minute count.
- **The route:** records who, the network, and the app's view (this process, whether it knows
  the session, its last heartbeat and announcement sent).
- **History:** each stall a row, red, its record whole; another network's not drawn.
- **The script:** the body and the live detail, pure, in duktape.
- **In a real browser:** a region past its promise shows its note and the stall is recorded
  once, naming the page, the tab and the connection the page holds, which the app knows.
"""

import json
import os
import types

import pytest

from modules import invalidation
from modules import stall_capture as SC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    path = tmp_path / SC.LOG
    monkeypatch.setattr(SC, "_path", lambda: str(path))
    return path


def _body(**page):
    return {"page": dict({"page": "/v2/sdn/responses?list=Default", "tab": "t1",
                          "shown_at": "2026-11-02T00:30:00.000Z", "promise_s": 90,
                          "words": ": no update has arrived in the 90 s it promises"}, **page),
            "live": {"state": "connected", "sid": "abc", "reconnect_attempts": 0,
                     "last_announce_at": "2026-11-02T00:28:00.000Z",
                     "last_announce_keys": "sdn"},
            "events": [{"event": "socket", "state": "connected"}, "a line"]}


SERVER = {"pid": 7, "session": "connected to this process",
          "server_last_heartbeat_at": "2026-11-02T00:29:50Z",
          "server_last_announce_at": "2026-11-02T00:29:40Z",
          "server_last_announce_keys": ["sdn"]}


class TestTheRecord:
    def test_a_stall_is_kept_with_the_app_s_view_and_only_its_declared_fields(self):
        body = _body(extra="x")
        body["live"]["nonsense"] = {"deep": 1}
        got = SC.record(body, actor="ops@example.com", network="Default", server=SERVER)
        assert got["ok"], got
        (row,) = SC.entries()["rows"]
        assert row["by"] == "ops@example.com" and row["network"] == "Default"
        assert row["page"]["tab"] == "t1" and row["live"]["sid"] == "abc"
        assert row["server"]["session"] == "connected to this process"
        assert row["events"] == ['{"event": "socket", "state": "connected"}', "a line"]
        assert row["dropped"] == ["extra", "live.nonsense"]
        assert "extra" not in row["page"] and "nonsense" not in row["live"]

    def test_every_kept_value_is_bounded(self):
        SC.record(_body(words="w" * 5000), actor="a", network="", server={})
        assert len(SC.entries()["rows"][0]["page"]["words"]) == SC.MAX_TEXT

    @pytest.mark.parametrize("body", [{}, {"page": {"page": "/v2/x"}}, {"live": {"state": "x"}},
                                      "not a dict"])
    def test_a_body_that_is_not_a_stall_is_refused_and_writes_nothing(self, body, store):
        got = SC.record(body, actor="a", network="", server={})
        assert got["ok"] is False and "names its page" in got["error"]
        assert not store.exists()

    def test_one_tab_is_held_to_its_count_a_minute(self):
        for _ in range(SC.PER_TAB_PER_MINUTE):
            assert SC.record(_body(), actor="a", network="", server={})["ok"]
        got = SC.record(_body(), actor="a", network="", server={})
        assert got["ok"] is False and "last minute" in got["error"]
        # Another tab is not held by this one's count.
        assert SC.record(_body(tab="t2"), actor="a", network="", server={})["ok"]

    def test_absent_is_no_rows_and_unreadable_says_why(self, store):
        assert SC.entries() == {"rows": [], "error": ""}
        store.write_text("{not json\n")
        assert "could not be read" in SC.entries()["error"]


class TestTheServerView:
    def test_it_names_the_process_and_whether_it_knows_the_session(self):
        known = types.SimpleNamespace(server=types.SimpleNamespace(
            manager=types.SimpleNamespace(is_connected=lambda sid, ns: sid == "abc")))
        assert SC.server_view("abc", known)["session"] == "connected to this process"
        assert SC.server_view("zzz", known)["session"] == "not connected to this process"
        assert SC.server_view("", known)["session"] == "the page sent no session id"
        assert SC.server_view("abc", None)["session"].startswith("unknown")
        assert SC.server_view("abc", None)["pid"] == os.getpid()

    def test_it_carries_the_last_heartbeat_and_announcement_this_process_sent(self, monkeypatch):
        sent = []
        monkeypatch.setattr(invalidation, "_emitter", lambda e, m: sent.append(e))
        monkeypatch.setattr(invalidation, "_last", dict(invalidation._last))
        monkeypatch.setattr("modules.reader_wakes.wake", lambda keys, by: None)
        invalidation.announce(["sdn"], "test")
        invalidation.heartbeat_loop(lambda s: None, beats=1)
        view = SC.server_view("", None)
        assert view["server_last_announce_keys"] == ["sdn"]
        assert view["server_last_announce_at"] and view["server_last_heartbeat_at"]


class TestTheRoute:
    def _post(self, body):
        import app as A
        return A.app.test_client().post("/v2/diagnostics/stall", json=body)

    def test_a_stall_is_recorded_with_who_and_the_app_s_view(self):
        r = self._post(_body())
        assert r.status_code == 200 and r.get_json() == {"ok": True, "error": ""}
        (row,) = SC.entries()["rows"]
        assert row["by"] and row["server"]["pid"] == os.getpid()
        # The test client holds no socket: the app says it does not know the session.
        assert row["server"]["session"] == "not connected to this process"

    def test_not_a_stall_is_400_and_a_tab_past_its_count_is_429(self):
        assert self._post({"page": {}}).status_code == 400
        for _ in range(SC.PER_TAB_PER_MINUTE):
            assert self._post(_body()).status_code == 200
        r = self._post(_body())
        assert r.status_code == 429 and "last minute" in r.get_json()["error"]


class TestHistory:
    def _ctx(self, name="Default", device=""):
        return {"ref": types.SimpleNamespace(name=name), "device": device, "members": set(),
                "limit": 50, "since": None}

    def test_each_stall_is_a_red_row_with_its_record(self):
        from modules import history_sources as HS
        SC.record(_body(), actor="ops@example.com", network="Default", server=SERVER)
        (ev,) = HS.page_stalls(self._ctx())["events"]
        assert ev["kind"] == "stall"
        assert ev["what"] == ("A page showed its stale note: /v2/sdn/responses?list=Default "
                              "(live updates connected; the app: connected to this process)")
        rec = dict(ev["record"])
        assert rec["Tab"] == "t1" and rec["Session"] == "abc"
        assert rec["Last announcement heard"] == "2026-11-02T00:28:00.000Z (sdn)"
        assert rec["The app's view"].startswith("connected to this process; process 7")
        assert "stalls" in HS.KIND_FILTERS and HS.SOURCES["page_stalls"] is HS.page_stalls
        # Another network's stall, and any one device's History, draw none.
        assert HS.page_stalls(self._ctx(name="Other"))["events"] == []
        assert HS.page_stalls(self._ctx(device="edge1"))["events"] == []

    def test_an_unreadable_record_is_said(self, store):
        from modules import history_sources as HS
        store.write_text("{not json\n")
        assert "page stall record could not be read" in HS.page_stalls(self._ctx())["errors"][0]


from tests.test_sdn_connections import networks  # noqa: F401,E402 - the fixture
from tests.test_sdn_ops_v2 import lab  # noqa: F401,E402 - the fixture


def test_a_shown_note_records_its_stall_once_in_a_real_browser(lab):  # noqa: F811
    from tests import browser
    from tests.test_sdn_stale import READY, STALE, _past
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import time

    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/sdn/responses?list=Default"))
            b.wait_for(READY, 15)
            b.wait_for("return window.NMAS && NMAS.live().state === 'connected'", 15)
            sid = b.js("return window.__nmasSocket.id")
            assert SC.entries()["rows"] == [], "a current page records nothing"
            _past(b)
            b.wait_for(f"return !{STALE}.hidden", 5)
            deadline = time.time() + 10
            while not SC.entries()["rows"] and time.time() < deadline:
                time.sleep(0.2)
            time.sleep(2)                     # two more ticks: still once
            rows = SC.entries()["rows"]
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["page"]["page"] == "/v2/sdn/responses?list=Default" and row["page"]["tab"]
    assert row["page"]["promise_s"] == 90 and "no update has arrived" in row["page"]["words"]
    assert row["live"]["state"] == "connected" and row["live"]["sid"] == sid
    assert row["server"]["session"] == "connected to this process", row["server"]
    assert any('"state": "connected"' in e for e in row["events"]), row["events"]


def _js(expr):
    import dukpy
    src = "".join(open(os.path.join(ROOT, "static", "js", f), encoding="utf-8").read() + "\n"
                  for f in ("nmas_invalidation.js", "nmas_v2.js"))
    return dukpy.evaljs("var window = {};\n" + src + "\n" + expr)


class TestTheScript:
    def test_the_body_holds_the_page_its_note_and_the_last_twenty_events(self):
        got = _js("window.NMAS_V2.stallBody('/v2/sdn', 't1', 0, 'd', 's', 90, ': late', 'sdn', "
                  "'', {state: 'connected'}, " + json.dumps(list(range(30))) + ")")
        assert got["page"] == {"page": "/v2/sdn", "tab": "t1",
                               "shown_at": "1970-01-01T00:00:00.000Z", "drawn_at": "d",
                               "stale_at": "s", "promise_s": 90, "words": ": late",
                               "region": "sdn", "held": ""}
        assert got["live"] == {"state": "connected"} and got["events"] == list(range(10, 30))

    def test_the_live_detail_says_each_time_and_never_as_absent(self):
        got = _js("window.NMAS.liveDetail({state: 'failed', since: 0, sid: 'x', "
                  "reconnectAttempts: 3, lastError: 'connect_error: refused', lastErrorAt: 0, "
                  "lastAnnounceAt: null, lastAnnounceKeys: ['sdn', 'flows'], lastBeat: null, "
                  "beatSeconds: 30})")
        assert got["state"] == "failed" and got["reconnect_attempts"] == 3
        assert got["last_error"] == "connect_error: refused"
        assert got["last_error_at"] == "1970-01-01T00:00:00.000Z"
        assert got["last_announce_at"] == "" and got["last_heartbeat_at"] == ""
        assert got["last_announce_keys"] == "sdn,flows"
        # The SAME fields the app keeps.
        assert set(got) == set(SC.LIVE_FIELDS)
