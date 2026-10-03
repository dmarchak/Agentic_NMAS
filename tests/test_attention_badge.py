"""The sidebar's Needs attention count (the operator, 2026-10-02: "wrong until I refresh").

Measured causes, each held here:

1. The badge's `<span>` carried the listener, and the fragment that REPLACED it
   (`hx-swap="outerHTML"`) was a bare span: it updated once after the page loaded and never
   again. The fragment is now the whole badge, listener included.
2. The count was computed apart: danger and warning rows only, while the page counted every
   row. Both now take `needs_attention()["badge"]`, from the rows the page draws.
3. Its listener was a hand-kept list, short of `lab_startup` (the page had it), and neither
   heard approvals, pending onboardings, blocked changes, intent or the device's state. One
   declaration (`attention.SOURCE_KEYS`) now builds the page's listener, the count's, and the
   client's relays.
4. A row that clears by TIME (an approval's expiry, an unplanned restart's seven days) had no
   sender; the count re-reads at that moment (`next_change_at`).
5. Its colour is the worst row's level; while the live channel is down, or its oldest source
   is past its promise, it is marked "may be out of date".

The proof in a real browser: on Help > About, a row appears and clears through the real
announcement, and the count follows without a reload, equal to the page's own count.
"""

import json
import os
import re
import time

import pytest

from modules import attention, invalidation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEP = {"id": "aaaa:0", "sha": "a" * 12, "shas": ["a" * 12], "step": "restart the renderer",
        "check": "", "check_state": "not_checkable", "check_detail": ""}


def _client():
    import app as nmas
    return nmas.app.test_client()


@pytest.fixture
def state(monkeypatch):
    """Needs attention over two controllable REAL sources: owed host steps (warning rows)
    and job health (a danger row for a writable updater)."""
    from routes import health
    monkeypatch.setattr(health, "_COMMIT", "f" * 40)
    st = {"steps": [], "jobs": []}
    monkeypatch.setattr(attention, "SOURCES", (
        lambda: attention.host_steps_source(owed={"ok": True, "steps": list(st["steps"])}),
        lambda: attention.job_health_source(health=lambda: {"jobs": list(st["jobs"])})))
    return st


class TestOneCount:
    def test_the_count_is_the_pages_rows_whatever_their_level(self, state):
        state["steps"] = [STEP]
        state["jobs"] = [{"unit": "updater", "state": "writable", "detail": "writable"}]
        count = _client().get("/v2/attention-count").get_data(as_text=True)
        page = _client().get("/v2/attention").get_data(as_text=True)
        assert re.search(r">\s*2\s*</span>", count), count
        assert "<strong>2 items</strong>" in page
        assert "count-danger" in count            # the worst row's level

    def test_an_unknown_row_is_counted_and_coloured_as_unknown(self, monkeypatch):
        rows = [attention.row(source="x", kind="unreadable", key="u", level="unknown",
                              what="X could not be read", cause="it raised",
                              action={"label": "Find why it cannot be read"})]
        b = attention.badge_of(rows, [])
        assert b["n"] == 1 and b["level"] == "unknown"

    def test_a_warning_only_list_is_amber_and_nothing_is_zero(self, state):
        state["steps"] = [STEP]
        assert "count-warning" in _client().get("/v2/attention-count").get_data(as_text=True)
        state["steps"] = []
        html = _client().get("/v2/attention-count").get_data(as_text=True)
        assert "count-zero" in html and re.search(r">\s*0\s*</span>", html)


class TestItKeepsListening:
    def test_the_fragment_is_the_whole_badge_with_its_listener_and_no_load(self, state):
        html = _client().get("/v2/attention-count").get_data(as_text=True)
        assert 'id="attention-count"' in html and 'hx-get="/v2/attention-count"' in html
        trigger = re.search(r'hx-trigger="([^"]*)"', html).group(1)
        assert "load" not in trigger                 # a response never re-loads itself
        for key in attention.ATTENTION_KEYS + (attention.DUE_EVENT,):
            assert f"nmas:{key} from:body" in trigger, key

    def test_the_sidebar_loads_it_and_the_page_listens_to_the_same_list(self, state):
        page = _client().get("/v2/help/about").get_data(as_text=True)
        badge = re.search(r'<span id="attention-count"[^>]*hx-trigger="([^"]*)"', page).group(1)
        assert badge.startswith("load, ")
        attention_html = _client().get("/v2/attention").get_data(as_text=True)
        listened = re.search(r'id="attention"[^>]*hx-trigger="([^"]*)"', attention_html,
                             re.S).group(1)
        assert badge[len("load, "):] == listened


class TestOneKeyList:
    def test_every_source_declares_what_moves_it_both_ways(self):
        names = {f.__name__ for f in attention.SOURCES}
        assert len(names) >= 20
        assert set(attention.SOURCE_KEYS) == names

    def test_every_key_is_in_the_vocabulary_and_relayed_by_the_client(self):
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        for key in attention.ATTENTION_KEYS:
            assert key in invalidation.VOCABULARY, key
            assert re.search(r"^\s*NMAS\.subscribe\('%s'" % key, src, re.M), key


class TestARowThatClearsByTime:
    def test_an_approval_and_a_restart_say_when_and_the_count_reads_then(self):
        from modules import approval_queue as Q
        created = 1_790_000_000
        rows = attention.approvals_source(read=lambda: ([{
            "id": "q1", "action_type": "push_config", "description": "a change",
            "created_ts": created, "device_hostname": "r2"}], ""))["rows"]
        assert rows[0]["clears_at"] == attention._iso(created + Q.EXPIRY_HOURS * 3600)
        later = dict(rows[0], clears_at=attention._iso(created + 10 * 3600 * 24))
        b = attention.badge_of([later, rows[0]], [])
        assert b["next_change_at"] == rows[0]["clears_at"]

    def test_every_kind_that_clears_by_time_has_rows_that_say_when(self):
        """Its population: the kinds whose CLEARS names time. Each source's call passes
        clears_at (read from the source, AST), so a new time-cleared kind needs it."""
        import ast
        timed = {k for k, (ways, _) in attention.CLEARS.items() if "time" in ways}
        assert timed == {("approvals", "pending"), ("restarts", "unplanned")}
        tree = ast.parse(open(attention.__file__, encoding="utf-8").read())
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "row":
                kw = {k.arg: k.value for k in node.keywords}
                if all(isinstance(kw.get(n), ast.Constant) for n in ("source", "kind")) \
                        and "clears_at" in kw:
                    found.add((kw["source"].value, kw["kind"].value))
        assert timed <= found, timed - found


class TestTheDoubtMark:
    def _doubt(self, live, stale, now):
        import dukpy
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        return dukpy.evaljs("var window = {};\n" + src
                            + f"\nwindow.NMAS_V2.badgeDoubt({json.dumps(live)}, "
                              f"{json.dumps(stale)}, {now});")

    def test_current_says_nothing(self):
        assert self._doubt("connected", 2000, 1000) == ""

    def test_a_dead_channel_says_it_may_be_out_of_date(self):
        got = self._doubt("disconnected", None, 1000)
        assert got.startswith("May be out of date") and "reconnect" in got

    def test_past_the_oldest_promise_says_so(self):
        assert "within its promise" in self._doubt("connected", 1000, 2000)


class TestAnAnnouncementDuringAFetchIsNotLost:
    """Measured in a real browser (2026-10-02): an announcement relayed 18 ms after the
    count began loading was dropped, and the count stayed wrong. A fragment that settles
    after one of its keys was relayed during its request reads again."""

    def _missed(self, trigger, relayed, asked):
        import dukpy
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        return dukpy.evaljs("var window = {};\n" + src
                            + f"\nwindow.NMAS_V2.missedKeys({json.dumps(trigger)}, "
                              f"{json.dumps(relayed)}, {asked});")

    def test_a_key_relayed_after_the_request_began_is_missed(self):
        trig = "nmas:app_version from:body, nmas:job_health from:body"
        assert self._missed(trig, {"app_version": 1005}, 1000) == ["app_version"]

    def test_one_before_it_or_in_its_own_millisecond_is_not(self):
        trig = "nmas:app_version from:body"
        assert self._missed(trig, {"app_version": 1000}, 1000) == []
        assert self._missed(trig, {"app_version": 900}, 1000) == []

    def test_a_key_it_does_not_listen_for_is_not(self):
        assert self._missed("nmas:drift from:body", {"app_version": 2000}, 1000) == []


# ── a real browser ─────────────────────────────────────────────────────────────

def _browser_or_skip():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    return browser


@pytest.fixture(scope="module")
def live_browser():
    browser = _browser_or_skip()
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        yield browser, srv, b


@pytest.fixture
def served(state, live_browser):
    browser, srv, b = live_browser
    yield {"b": b, "srv": srv, "state": state}
    try:
        b.go("about:blank")
    finally:
        browser.close_socketio_sessions()


COUNT = "document.getElementById('attention-count')"


def _wait(b, script, timeout=10):
    """`b.wait_for`, and on failure the live client's own record (NMAS.log()): whether the
    announcement ARRIVED and which panels it refreshed, so a miss names its stage."""
    try:
        return b.wait_for(script, timeout)
    except AssertionError as exc:
        trail = b.js("return JSON.stringify(window.NMAS ? NMAS.log().slice(-12) : null)")
        raise AssertionError(f"{exc}\nthe live client's record: {trail}") from None


class TestInARealBrowser:
    def test_the_count_follows_a_row_appearing_and_clearing_without_a_reload(self, served):
        b, st = served["b"], served["state"]
        b.go(served["srv"].url("/v2/help/about"))            # NOT the Needs attention page
        b.wait_for(f"return {COUNT} && {COUNT}.textContent.trim() === '0'")
        b.wait_for("return window.NMAS && NMAS.live().state === 'connected'")
        b.js("window.__notReloaded = 1; return 1")
        st["steps"] = [STEP]                                 # a row appears ...
        invalidation.announce(["app_version"], "test", True)  # ... and its reader announces
        _wait(b, f"return {COUNT}.textContent.trim() === '1'")
        assert "count-warning" in b.js(f"return {COUNT}.className")
        st["jobs"] = [{"unit": "updater", "state": "writable", "detail": "writable"}]
        invalidation.announce(["job_health"], "test", True)
        _wait(b, f"return {COUNT}.textContent.trim() === '2' "
                   f"&& {COUNT}.className.indexOf('count-danger') >= 0")
        st["steps"], st["jobs"] = [], []                     # both clear
        invalidation.announce(["app_version", "job_health"], "test", True)
        _wait(b, f"return {COUNT}.textContent.trim() === '0'")
        assert b.js("return window.__notReloaded") == 1      # no reload happened

    def test_it_reads_again_when_a_row_clears_by_time(self, served):
        """Nothing announces the moment an approval expires: the badge's own
        `data-next-change-at` fires the re-read, once."""
        b = served["b"]
        b.go(served["srv"].url("/v2/help/about"))
        b.wait_for(f"return {COUNT} && {COUNT}.textContent.trim() === '0'")
        b.js(f"{COUNT}.setAttribute('data-old', '1');"
             f"{COUNT}.setAttribute('data-next-change-at', '2020-01-01T00:00:00Z'); return 1")
        b.wait_for(f"return {COUNT} && !{COUNT}.hasAttribute('data-old')", 10)

    def test_it_says_it_may_be_out_of_date_and_catches_up(self, served):
        """A value past its promise, and a live channel that dropped, each mark the count
        (a quiet mark, its title saying why); the channel coming back clears it."""
        from tests import browser
        b = served["b"]
        b.go(served["srv"].url("/v2/help/about"))
        b.wait_for(f"return {COUNT} && {COUNT}.textContent.trim() === '0'")
        b.wait_for("return window.NMAS && NMAS.live().state === 'connected'")
        b.js(f"{COUNT}.setAttribute('data-stale-at', '2020-01-01T00:00:00Z'); return 1")
        b.wait_for(f"return {COUNT}.className.indexOf('count-maybe') >= 0", 5)
        assert "within its promise" in b.js(f"return {COUNT}.title")
        b.js(f"{COUNT}.removeAttribute('data-stale-at'); return 1")
        b.wait_for(f"return {COUNT}.className.indexOf('count-maybe') < 0", 5)
        # The channel drops: the page's own socket, closed from the page (a server-side
        # close is reconnected within a tick, measured: the mark was sometimes never seen).
        b.js("window.__nmasSocket.disconnect(); return 1")
        _wait(b, f"return {COUNT}.className.indexOf('count-maybe') >= 0", 5)
        assert b.js(f"return {COUNT}.title").startswith("May be out of date")
        b.js("window.__nmasSocket.connect(); return 1")           # and comes back
        _wait(b, "return NMAS.live().state === 'connected'", 15)
        _wait(b, f"return {COUNT}.className.indexOf('count-maybe') < 0", 5)

    def test_an_announcement_while_the_count_is_loading_is_not_lost(self, served, monkeypatch):
        """The race the real run hit, forced: the count's request is held open, a row
        appears and its reader announces while it is in flight; the count ends correct."""
        import threading
        b, st = served["b"], served["state"]
        b.go(served["srv"].url("/v2/help/about"))
        b.wait_for(f"return {COUNT} && {COUNT}.textContent.trim() === '0'")
        b.wait_for("return window.NMAS && NMAS.live().state === 'connected'")
        entered, real = threading.Event(), attention.needs_attention

        def slow(sources=None):
            page = real(sources)          # read BEFORE the row appears: an old answer
            entered.set()
            time.sleep(1.5)
            return page
        monkeypatch.setattr(attention, "needs_attention", slow)
        # No fetch of the count in flight (htmx drops a trigger on a fetching element).
        b.wait_for(f"return !{COUNT}.classList.contains('htmx-request')")
        # Through the live client's own dispatch (a response's invalidation goes this way).
        b.js("NMAS.invalidate(['drift']); return 1")                     # a fetch begins
        assert entered.wait(5)
        monkeypatch.setattr(attention, "needs_attention", real)
        st["steps"] = [STEP]
        invalidation.announce(["app_version"], "test", True)             # during it
        _wait(b, f"return {COUNT}.textContent.trim() === '1'")

    def test_the_count_equals_the_pages_own_count(self, served):
        b, st = served["b"], served["state"]
        st["steps"] = [STEP]
        st["jobs"] = [{"unit": "updater", "state": "writable", "detail": "writable"}]
        b.go(served["srv"].url("/v2/"))
        b.wait_for(f"return {COUNT} && {COUNT}.textContent.trim() !== '…'")
        page = b.js("return document.querySelector('#attention .att-summary strong').textContent")
        assert page == f"{b.js(f'return {COUNT}.textContent.trim()')} items"
