"""The live-data contract (7.2 step 13; the operator's standing requirement):
a page showing live information updates itself, and a panel that cannot tell
whether it is current SAYS SO.

Three parts, each for one way of looking current while not being:
  - the HEARTBEAT proves the channel (a dead socket names itself ON THE DATA);
  - AGE against the source's own promise proves the SOURCE (a reader that
    died announces nothing, and silence must not read as "nothing changed");
  - CATCH-UP on reconnect covers what was announced while the channel was down.

The shipped client runs in duktape on a clock the test controls."""

import ast
import os

import dukpy
import pytest

from modules import attention as A
from modules import config
from modules import invalidation as I
from modules import reader_job as R
from tests.test_invalidation_map import CLIENT, HARNESS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A socket stand-in and a panel stub whose querySelector honours the
# attribute it is asked for (the shared harness's stub returns one marker
# for any selector, which cannot tell a live mark from an age line).
PRELUDE = """
var handlers = {};
window.io = function () { return {on: function (ev, f) { handlers[ev] = f; }}; };
function panel2(id) {
  var el = {id: id, children: [],
    insertAdjacentHTML: function (w, h) {
      var m = {html: h, parentNode: null}; m.parentNode = el;
      if (w === 'afterbegin') el.children.unshift(m); else el.children.push(m); },
    querySelector: function (sel) {
      var attr = sel.replace(/^\\[/, '').replace(/\\]$/, '');
      for (var i = 0; i < el.children.length; i++) {
        if (el.children[i].html.indexOf(attr + '=') >= 0) return el.children[i]; }
      return null; },
    removeChild: function (m) { el.children.splice(el.children.indexOf(m), 1); },
    text: function () { return el.children.map(function (c) { return c.html; }).join(''); }};
  doc.els[id] = el;
  return el;
}
"""


def _run(body, **kw):
    client = open(CLIENT, encoding="utf-8").read()
    script = (HARNESS + PRELUDE + "(function () {\n" + client.replace(
        "})(typeof window !== 'undefined' ? window : this);", "})(window);")
        + "\n})();\nvar NMAS = window.NMAS;\nvar T = 1790000000000;\n"
        "NMAS._clock = function () { return T; };\n" + body)
    return dukpy.evaljs(script, **kw)


# ---------------------------------------------------------------------------
# The server's half
# ---------------------------------------------------------------------------

class TestTheHeartbeat:
    def test_it_beats_on_its_interval_and_a_failed_beat_does_not_stop_it(self, monkeypatch):
        sent, slept = [], []
        monkeypatch.setattr(I, "_emitter", lambda ev, msg: sent.append((ev, msg)))
        assert I.heartbeat_loop(slept.append, beats=3) == 3
        assert slept == [I.HEARTBEAT_SECONDS] * 3
        assert {ev for ev, _ in sent} == {I.HEARTBEAT_EVENT}
        assert sent[0][1]["interval_seconds"] == I.HEARTBEAT_SECONDS

        def deaf(ev, msg):
            raise ConnectionError("gone")
        monkeypatch.setattr(I, "_emitter", deaf)
        assert I.heartbeat_loop(lambda s: None, beats=2) == 0

    def test_its_interval_is_half_the_fastest_reader_it_judges(self):
        """30 s: the channel is judged faster than the fastest data it
        carries (Grafana's 60 s evaluation), so 2.5 beats is 75 s."""
        assert I.HEARTBEAT_SECONDS * 2 <= 60

    def test_a_beat_reaches_a_connected_page_through_the_apps_emitter(self):
        import app as Ap
        c = Ap.socketio.test_client(Ap.app)
        try:
            c.get_received()
            assert I.heartbeat_loop(lambda s: None, beats=1) == 1
            got = [m for m in c.get_received() if m["name"] == I.HEARTBEAT_EVENT]
            assert got and got[0]["args"][0]["interval_seconds"] == I.HEARTBEAT_SECONDS
        finally:
            c.disconnect()

    def test_the_app_starts_it_with_its_other_background_services(self):
        tree = ast.parse(open(os.path.join(ROOT, "app.py"), encoding="utf-8").read())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_start_background_daemons")
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and getattr(n.func, "attr", "") == "start_background_task"]
        assert any("heartbeat_loop" in ast.unparse(c) for c in calls)


class TestSourcesCarryTheirPromise:
    @pytest.fixture(autouse=True)
    def store(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))

    def test_a_read_for_this_request_makes_no_promise(self):
        r = A.source_result("x", "X", read_at=1.0, took_ms=0, checked="c")
        assert r["stale_after_seconds"] is None

    def test_the_job_health_reader_s_value_carries_its_promise(self, monkeypatch):
        from modules import job_health as J
        from modules.readers import job_health_reader as JHR
        monkeypatch.setattr(J, "health", lambda **kw: {"jobs": []})
        doc = R.run_once(JHR.READER, clock=lambda: 1_790_000_000.0)
        assert doc["stale_after_seconds"] == JHR.INTERVAL_SECONDS * R.STALE_AFTER_INTERVALS
        res = A.job_health_source(readers_now=[])
        assert res["stale_after_seconds"] == doc["stale_after_seconds"]


# ---------------------------------------------------------------------------
# The shipped client's half
# ---------------------------------------------------------------------------

class TestTheChannel:
    def test_a_silent_channel_is_named_after_two_and_a_half_beats(self):
        out = _run("""
          handlers['connect']();
          handlers['nmas_heartbeat']({interval_seconds: 30});
          T += 74000; NMAS.tick(); var at74 = NMAS.live().state;
          T += 2000; NMAS.tick(); var at76 = NMAS.live().state;
          [at74, at76, NMAS.liveNoteHtml()];
        """)
        at74, at76, note = out
        assert at74 == "connected" and at76 == "silent"
        assert "went silent" in note and "no heartbeat" in note

    def test_a_beat_after_silence_brings_it_back(self):
        out = _run("""
          handlers['connect']();
          T += 100000; NMAS.tick();
          var s = NMAS.live().state;
          handlers['nmas_heartbeat']({interval_seconds: 30});
          [s, NMAS.live().state];
        """)
        assert out == ["silent", "connected"]

    def test_the_mark_is_on_every_subscribed_panel_not_only_a_status_area(self):
        out = _run("""
          var p1 = panel2('p1'), p2 = panel2('p2');
          NMAS.subscribe('drift', 'a', function () { return true; }, {panel: 'p1'});
          NMAS.subscribe('approvals', 'b', function () { return true; }, {panel: 'p2'});
          handlers['connect']();
          var up = p1.text() + p2.text();
          handlers['disconnect']();
          var down = [p1.text(), p2.text()];
          handlers['connect']();
          [up, down, p1.text() + p2.text()];
        """)
        up, down, back = out
        assert up == "", "a connected page draws no mark"
        assert all("Live updates stopped at" in d for d in down)
        assert back == ""

    def test_reconnect_catches_up_every_panel_once_and_a_first_connect_does_not(self):
        out = _run("""
          var runs = 0;
          NMAS.subscribe('drift', 'a', function () { runs++; return true; });
          NMAS.subscribe('approvals', 'a', function () { runs++; return true; });
          handlers['connect']();
          var first = runs;
          handlers['disconnect']();
          handlers['connect']();
          [first, runs];
        """)
        assert out == [0, 1], "once per panel, and nothing on the page's first connect"


class TestAge:
    def test_fresh_stale_no_promise_and_unknown_each_say_what_they_are(self):
        out = _run("""
          [NMAS.ageHtml({valueAt: T - 10000, staleAfter: 60}, T),
           NMAS.ageHtml({valueAt: T - 61000, staleAfter: 60}, T),
           NMAS.ageHtml({valueAt: T - 10000, staleAfter: null}, T),
           NMAS.ageHtml({valueAt: null, staleAfter: 60}, T)];
        """)
        fresh, stale, none, unknown = out
        assert 'data-nmas-age="fresh"' in fresh and "10 s ago" in fresh
        assert 'data-nmas-age="stale"' in stale and "older than the 60 s" in stale
        assert 'data-nmas-age="no_promise"' in none and "not known" in none
        assert 'data-nmas-age="unknown"' in unknown and "cannot be told" in unknown

    def test_the_tick_redraws_a_stamped_panel_and_marks_it_stale_with_no_request(self):
        out = _run("""
          var p = panel2('p'); var redraws = 0; var fetched = 0;
          window.fetch = function () { fetched++; };
          NMAS.stamp('p', T, 150, 'P', function () { redraws++; });
          var before = p.text();
          T += 151000; NMAS.tick();
          [before.indexOf('fresh') >= 0, p.text().indexOf('Stale:') >= 0,
           p.children.length, redraws, fetched];
        """)
        fresh_first, stale_later, n, redraws, fetched = out
        assert fresh_first and stale_later
        assert n == 1, "one age line, replaced, never stacked"
        assert redraws == 2 and fetched == 0


class TestNeedsAttentionJudgesEachSource:
    def _page(self, value_at, stale_after):
        src = {"source": "job_health", "label": "Job health", "state": "read",
               "read_at": "2026-09-28T20:51:46Z", "value_at": value_at,
               "stale_after_seconds": stale_after, "took_ms": 61,
               "checked": "26 job-health row(s), 26 ok", "count": 0}
        return {"ok": True, "headline": "Nothing needs attention", "rows": [],
                "sources": [src], "unreadable": []}

    def _draw(self, page, now_iso):
        src = open(os.path.join(ROOT, "static", "js", "nmas_attention.js"), encoding="utf-8").read()
        js = ("var window = {}; var document = undefined;\n" + src.replace(
            "})(typeof window !== 'undefined' ? window : this);", "})(window);")
            + "\nwindow.attentionPanelHtml(dukpy['page'], Date.parse(dukpy['now']));")
        return dukpy.evaljs(js, page=page, now=now_iso)

    def test_within_its_promise_the_healthy_page_stays_one_line(self):
        html = self._draw(self._page("2026-09-28T20:51:38Z", 900), "2026-09-28T20:55:00Z")
        assert html.startswith("<details") and "stale" not in html

    def test_past_its_promise_the_source_is_a_row(self):
        """The operator's case: the job-health reader died, nothing announces,
        and the page's own clock notices. A stale source is something needing
        attention, so it is a ROW (answer first), not a word in the evidence."""
        html = self._draw(self._page("2026-09-28T20:51:38Z", 900), "2026-09-28T21:10:00Z")
        assert 'data-attention="rows"' in html
        rows = html[:html.index('data-attention="evidence"')]
        assert "Job health&#39;s value is older than its source promises" in rows \
            or "Job health's value is older than its source promises" in rows
        assert "current for 900 s" in rows
