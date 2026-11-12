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
    """C3166 (the operator's addition 3, 2026-11-12: "the badge is pushed over the page's live
    connection when its count changes, not polled"): the count is asked for once, as the page
    loads, and then drawn from what the server pushes; it re-fetches on no key."""

    def test_the_fragment_is_the_whole_badge_and_hears_only_its_own_page_s_press(self, state):
        from modules import attention_store
        before = attention_store.reads()
        html = _client().get("/v2/attention-count").get_data(as_text=True)
        assert attention_store.reads() == before + 1, "one read of the held value"
        assert 'id="attention-count"' in html and 'data-network="Default"' in html
        trigger = re.search(r'hx-trigger="([^"]*)"', html).group(1)
        assert trigger == "nmas:acknowledgements from:body", \
            "pushed after it; asked again only on this page's own acknowledgement"
        assert re.search(r'data-at="[0-9T:.Z-]+"', html), "when the drawn value was assembled"

    def test_the_sidebar_loads_it_once_and_the_list_hears_the_store(self, state):
        page = _client().get("/v2/help/about").get_data(as_text=True)
        badge = re.search(r'<span id="attention-count"[^>]*hx-trigger="([^"]*)"', page).group(1)
        assert badge == "load, nmas:acknowledgements from:body"
        attention_html = _client().get("/v2/attention").get_data(as_text=True)
        listened = re.search(r'id="attention"[^>]*hx-trigger="([^"]*)"', attention_html,
                             re.S).group(1)
        assert "nmas:attention from:body" in listened
        assert "nmas:acknowledgements from:body" in listened, "the person's own press"
        sources = {k for ks in attention.SOURCE_KEYS.values() for k in ks}
        assert not [k for k in sources if f"nmas:{k} from:body" in listened], \
            "a source's key reaches the background store, never the page"
        assert ("attention",) in [tuple(v) for v in invalidation.ANNOUNCERS.values()], \
            "the store announces what the list hears"


class TestOneKeyList:
    def test_every_source_declares_what_moves_it_both_ways(self):
        names = {f.__name__ for f in attention.SOURCES}
        assert len(names) >= 20
        assert set(attention.SOURCE_KEYS) == names

    def test_every_key_is_in_the_vocabulary_and_reaches_the_store(self):
        """C3166: a key that moves a row reaches Needs attention's background store, which
        recomputes the sources it moves (and an acknowledgement re-assembles), and the client
        relays the store's own key, which the list hears."""
        from modules import attention_store
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        for key in attention.ATTENTION_KEYS:
            assert key in invalidation.VOCABULARY, key
            assert attention_store._touched([key]) - {attention_store._UNDECLARED}, key
        assert re.search(r"^\s*NMAS\.subscribe\('attention'", src, re.M)


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
        assert timed == {("approvals", "pending"), ("restarts", "unplanned"),
                         ("adjacency_log", "flap"),     # a day after its last drop (C589)
                         # The day or month a background AI feature's spend counts ends (C1843).
                         ("ai_spend", "warning"), ("ai_spend", "stopped"),
                         # The day the installation's day cap counts ends (C2056).
                         ("ai_spend", "day_warning"), ("ai_spend", "day_reached"),
                         # The moment the provider named for its workspace limit (C2084).
                         ("ai_spend", "workspace_limit"),
                         # 24 hours after the restart that stopped an SDN loop (C2000).
                         ("sdn_loop", "restart_stopped"),
                         # A lost response's hard timeout, when it would have expired (C2018).
                         ("sdn_mitigation", "lost"),
                         # A day after the last AI call that withheld a line (C2272).
                         ("ai_withheld", "withheld"),
                         # A dry-run heal record's marking window ends (board H, H3).
                         ("heal", "would_heal"),
                         # The day or month the can't-fix analysis's cap counts ends (H8).
                         ("heal", "analysis_capped"),
                         # A held or failed bounce, 7 days after it (CANT_FIX_DAYS; H20).
                         ("heal", "bounce"),
                         # A held or failed BGP session clear, 7 days after it (H23).
                         ("heal", "clear"),
                         # A dampening proposal, its port stable 24 h; an approved one not
                         # ended dampened, 7 days after it (H22).
                         ("heal", "dampening")}
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


class TestThePushedBadge:
    """C3166: the count the server pushes (`attention_store.PUSH_EVENT`), drawn in place by the
    shipped script: the same class, text and title the fragment draws, and never an older value
    over a newer one."""

    def _js(self, call):
        import dukpy
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        return dukpy.evaljs("var window = {};\n" + src + f"\nwindow.NMAS_V2.{call};")

    def test_its_parts_are_the_fragments_own(self, state):
        state["steps"] = [STEP]
        html = _client().get("/v2/attention-count").get_data(as_text=True)
        got = self._js('badgeParts({"n": 1, "level": "warning"})')
        assert f'class="{got["className"]}"' in html and f'title="{got["title"]}"' in html
        assert re.search(r">\s*1\s*</span>", html) and got["text"] == "1"
        state["steps"] = []
        html = _client().get("/v2/attention-count").get_data(as_text=True)
        got = self._js('badgeParts({"n": 0, "level": ""})')
        assert f'class="{got["className"]}"' in html and f'title="{got["title"]}"' in html

    def test_an_older_push_is_older_and_an_unknown_time_never_is(self):
        assert self._js('pushIsOlder("2026-11-12T04:00:00Z", "2026-11-12T04:00:05Z")') is True
        assert self._js('pushIsOlder("2026-11-12T04:00:05Z", "2026-11-12T04:00:00Z")') is False
        assert self._js('pushIsOlder("2026-11-12T04:00:00Z", "2026-11-12T04:00:00Z")') is False
        assert self._js('pushIsOlder("", "2026-11-12T04:00:00Z")') is False
        assert self._js('pushIsOlder("2026-11-12T04:00:00Z", null)') is False


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
def served(state, live_browser, monkeypatch):
    """The served app with Needs attention's store as in production (C3166): nothing computed
    on a request, its background worker running, the count pushed over the live connection."""
    import threading

    from modules import attention_store
    browser, srv, b = live_browser
    monkeypatch.setattr(attention_store, "COMPUTE_ON_READ", False)
    stop = threading.Event()
    worker = threading.Thread(target=attention_store.run, args=(stop,), daemon=True)
    worker.start()
    try:
        yield {"b": b, "srv": srv, "state": state}
    finally:
        stop.set()
        attention_store._wake.set()
        worker.join(10)
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

    def test_a_row_that_clears_by_time_leaves_the_count_with_nothing_announced(
            self, served, monkeypatch):
        """Nothing announces the moment an approval expires: the background store reads its
        source again at the row's `clears_at` and pushes the count (C3166); the page asks
        for nothing."""
        b = served["b"]
        until, asked = time.time() + 6, []

        def approvals_source():
            asked.append(time.time())
            rows = [attention.row(source="approvals", kind="pending", key="q1",
                                  level="warning", what="An approval is waiting",
                                  cause="a test's approval, expiring", clears_at=until,
                                  action={"label": "Review the approval"})] \
                if time.time() < until else []
            return attention.source_result("approvals", "Approvals", read_at=time.time(),
                                           took_ms=0, rows=rows, checked="a test's queue")
        monkeypatch.setattr(attention, "SOURCES", (approvals_source,))
        # The worker already holds a value from the fixture's sources (it started with them):
        # dropped, so this test's one source is the value the page loads (measured: kept, the
        # count stayed at the fixture's 0 for its 20 s cadence, past this test's wait).
        from modules import attention_store
        attention_store.clear()
        b.go(served["srv"].url("/v2/help/about"))
        _wait(b, f"return {COUNT} && {COUNT}.textContent.trim() === '1'")
        b.js("window.__notReloaded = 1; return 1")
        _wait(b, f"return {COUNT}.textContent.trim() === '0'", 20)
        assert b.js("return window.__notReloaded") == 1
        assert [t for t in asked if t >= until], "its source was read again at its clear time"

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

    def test_a_push_while_the_count_is_loading_is_not_lost(self, served, monkeypatch):
        """The race, forced (C3166): the count's one load is held open with the value held
        BEFORE a row appears; the row appears, the store pushes the new count while the load
        is in flight, and the old answer settles after the push: the count ends at the push."""
        import threading

        from modules import attention_store
        b, st = served["b"], served["state"]
        b.go(served["srv"].url("/v2/help/about"))
        _wait(b, f"return {COUNT} && {COUNT}.textContent.trim() === '0'")
        entered, real = threading.Event(), attention_store.badge

        def slow(network=None):
            got = real(network)           # read BEFORE the row appears: an old answer
            entered.set()
            time.sleep(attention_store.DEBOUNCE_S + 3)
            return got
        monkeypatch.setattr(attention_store, "badge", slow)
        b.go(served["srv"].url("/v2/help/about"))            # its load begins
        assert entered.wait(10)
        st["steps"] = [STEP]
        invalidation.announce(["app_version"], "test", True)             # during it
        _wait(b, f"return {COUNT}.textContent.trim() === '1'", 15)
        _wait(b, f"return !{COUNT}.classList.contains('htmx-request') "
                 f"&& {COUNT}.textContent.trim() === '1'", 15)

    def test_the_count_equals_the_pages_own_count(self, served):
        b, st = served["b"], served["state"]
        st["steps"] = [STEP]
        st["jobs"] = [{"unit": "updater", "state": "writable", "detail": "writable"}]
        # As their readers would: the store (its worker already running, C3166) reads the
        # sources the announcement moves, and the open page fills itself from what it holds.
        invalidation.announce(["app_version", "job_health"], "test", True)
        b.go(served["srv"].url("/v2/"))
        b.wait_for(f"return {COUNT} && {COUNT}.textContent.trim() !== '…'")
        strong = "document.querySelector('#attention .att-summary strong')"
        _wait(b, f"return {strong} && {strong}.textContent.indexOf('items') > 0")
        page = b.js(f"return {strong}.textContent")
        assert page == f"{b.js(f'return {COUNT}.textContent.trim()')} items"
