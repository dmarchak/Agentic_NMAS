"""History's paging (PHASE8_PLAN 15.14 part B, the operator, 2026-10-25), for the History page
and a device's History tab alike, and the links both ways between an AI call's row and what
it produced (15.14).

- **Load more by keyset:** a page holds 50 rows; Load more reads the next 50 older than the
  last one shown, by a cursor on its time and its id (`before=<time>~<id>`), never an offset:
  walking every page draws every row once, in order, rows of one second split across a page
  included; rows arriving meanwhile do not shift the next page.
- **Each source asked for rows older than the place:** a paged source keeps its rows at or
  before the cursor before its newest-N cut (`_recent`, git's --until), so one read reaches any
  depth; an `UNPAGED` one is read again for more, at most `ROUNDS` reads a load and `MAX_READ`
  rows a read, and a page it cannot reach says so by name.
- **Bounded at scale (work counted, never wall-clock):** with 6,000 records in each of two
  stores, every load draws 50 rows and reads each source at most `ROUNDS` times, no read
  asking for more than `MAX_READ` rows; a paged store's load costs the same at page 1 and at
  page 100.
- **Jump to a day** (`on=YYYY-MM-DD`): the page starts at the end of that day, UTC.
- **The filters on the server and in the address:** a kind filter reads only the sources that
  can hold its kinds (`SOURCE_KINDS`, every source's rows held to it on a planted lab); Load
  more's fragment and the address it pushes carry every filter; a place that is not one is not
  applied and said.
- **Links both ways:** Explain's answer and Ask in words' filled notice link to the call's row
  (`/v2/history?call=<id>`), which shows that one call opened, however old; the row links to
  what it produced (its last use row's page and anchor, only ever a page of Mercury's own).
"""

import calendar
import html as _h
import re
import time

import pytest

from modules import history_sources as HS
from tests.test_ai_nl_query import _choices, _words, site, web, world  # noqa: F401 (fixtures)
from tests.test_device_v2 import _get, lab  # noqa: F401 (the fixture)
from tests.test_history_one_timeline import DEVICES, planted  # noqa: F401 (the fixture)


def _utc(text):
    return float(calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ")))


BASE = _utc("2026-09-21T13:00:00Z")      # every fake row is at or before it


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _rows(name, n, start=BASE, step=60, ties=()):
    """*n* rows of store *name*, newest first, one every *step* seconds back from *start*;
    each index in *ties* shares the time of the row before it (rows of one second)."""
    out, t = [], start
    for i in range(n):
        if i and i not in ties:
            t -= step
        out.append({"at": _iso(t), "what": f"{name} {i}"})
    return out


class Store:
    """A fake History source over *rows* (newest first), read as a real one reads its store:
    a paged one keeps its rows at or before the page's place BEFORE its newest-N cut; an
    unpaged one returns its newest N whatever the place. Each read's asked-for count is kept,
    so a test counts the work."""

    def __init__(self, rows, paged=True, kind="commit", devices=(), who="", verified=None):
        self.rows, self.paged, self.kind = rows, paged, kind
        self.devices, self.who, self.verified = list(devices), who, verified
        self.reads = []

    def __call__(self, ctx):
        self.reads.append(ctx["limit"])
        kept = [r for r in self.rows if HS._recent(ctx, r["at"])] if self.paged else self.rows
        events = []
        for r in kept[:ctx["limit"]]:
            e = HS._event(r["at"], self.kind, r["what"], self.devices, who=self.who)
            if self.verified is not None:
                e["verified"] = self.verified
            events.append(e)
        return HS._out(events, cut=["more"] if len(kept) > ctx["limit"] else [])


def _walk(**kw):
    """Every page in turn, by each page's `next`, as Load more reads them: the rows drawn and
    the loads it took."""
    drawn, before, loads = [], None, 0
    for _ in range(400):
        h = HS.timeline(None, members=[], before=before, **kw)
        loads += 1
        drawn += h["events"]
        assert len(h["events"]) <= h["limit"]
        if not h["more"]:
            return drawn, loads, h
        before, err = HS.parse_cursor(h["next"])
        assert before and not err, h["next"]
    raise AssertionError("Load more never ended")


@pytest.fixture
def stores(monkeypatch):
    def use(**sources):
        monkeypatch.setattr(HS, "SOURCES", sources)
        return sources
    return use


class TestLoadMoreByKeyset:
    def test_every_row_once_in_order_across_pages_and_ties(self, stores):
        # Two stores interleaved; rows of one second on both sides of page boundaries.
        a = _rows("a", 130, step=60, ties=(49, 50, 51, 99, 100))
        b = _rows("b", 70, start=BASE - 30, step=120, ties=(24, 25))
        stores(a=Store(a), b=Store(b))
        drawn, loads, last = _walk()
        whats = [e["what"] for e in drawn]
        assert len(whats) == len(set(whats)) == 200, "every row once"
        assert loads == 4 and last["next"] == "" and not last["more"]
        times = [HS.epoch(e["at"]) for e in drawn]
        assert times == sorted(times, reverse=True), "newest first, across pages"
        # Within one second, each store's own order (git's, for commits) is kept.
        assert [w for w in whats if w.startswith("a ")] == [f"a {i}" for i in range(130)]

    def test_rows_arriving_meanwhile_do_not_shift_the_next_page(self, stores):
        a = _rows("a", 120)
        store = Store(a)
        stores(a=store)
        first = HS.timeline(None, members=[])
        before = HS.parse_cursor(first["next"])[0]
        expected = [e["what"] for e in HS.timeline(None, members=[], before=before)["events"]]
        store.rows = _rows("new", 10, start=BASE + 3600) + a          # ten newer records land
        got = [e["what"] for e in HS.timeline(None, members=[], before=before)["events"]]
        assert got == expected == [f"a {i}" for i in range(50, 100)]

    def test_the_cursor_is_the_last_row_s_time_and_id(self, stores):
        stores(a=Store(_rows("a", 60)))
        h = HS.timeline(None, members=[])
        last = h["events"][-1]
        assert h["more"] and h["next"] == f"{last['at']}~{last['id']}"
        assert re.fullmatch(r"r-[0-9a-f]{16}", last["id"])
        assert HS.row_id(dict(last)) == last["id"], "the same record has the same id"


class TestEachSourceIsAskedForOlderRows:
    def test_a_paged_store_is_read_once_a_load_at_any_depth(self, stores):
        store = Store(_rows("a", 6000, step=10))
        stores(a=store)
        deep = HS.parse_cursor(f"{_iso(BASE - 10 * 5000)}~")[0]
        for before, asked in ((None, 50), (deep, 51)):
            store.reads.clear()
            h = HS.timeline(None, members=[], before=before)
            assert len(h["events"]) == 50 and h["more"]
            # One read: its newest 50 (51 at a place, which returns the row it names too).
            assert store.reads == [asked], store.reads
        assert h["events"][0]["what"] == "a 5001", "strictly older than the place"

    def test_an_unpaged_store_is_read_again_deeper_and_said_when_it_cannot_reach(self, stores):
        paged, unpaged = Store(_rows("p", 6000, step=10)), Store(_rows("u", 6000, step=10,
                                                                       start=BASE - 5),
                                                                 paged=False)
        stores(p=paged, u=unpaged)
        # The rows older than the 100th of the two together: the unpaged store's newest 51 are
        # all newer than the place, so it is asked again for 204, which reach it.
        before = HS.parse_cursor(f"{_iso(BASE - 10 * 50)}~")[0]
        h = HS.timeline(None, members=[], before=before)
        assert unpaged.reads == [51, 51 * HS.GROWTH] and paged.reads == [51]
        assert len(h["events"]) == 50 and not h["unreached"]
        assert {e["what"][0] for e in h["events"]} == {"p", "u"}, "both stores, interleaved"
        # Past MAX_READ rows back, it cannot be reached: the page says so, naming it.
        unpaged.reads.clear()
        far = HS.parse_cursor(f"{_iso(BASE - 10 * 4000)}~")[0]
        h = HS.timeline(None, members=[], before=far)
        assert len(unpaged.reads) <= HS.ROUNDS and max(unpaged.reads) == HS.MAX_READ
        assert h["unreached"] == [f"the u record, read to its newest {HS.MAX_READ}"]
        assert {e["what"][0] for e in h["events"]} == {"p"} and h["more"]


class TestBoundedAtScale:
    """Many thousands of events (6,000 in each of two stores, one unpaged): each load's rows and
    reads, counted, stay bounded; nothing is timed."""

    def test_every_load_draws_a_page_and_reads_each_source_a_bounded_number_of_times(
            self, stores):
        paged = Store(_rows("p", 6000, step=7))
        unpaged = Store(_rows("u", 6000, step=11, start=BASE - 3), paged=False)
        stores(p=paged, u=unpaged)
        before = None
        for page in range(30):
            paged.reads.clear()
            unpaged.reads.clear()
            h = HS.timeline(None, members=[], before=before)
            assert len(h["events"]) == 50, page
            for reads in (paged.reads, unpaged.reads):
                assert 1 <= len(reads) <= HS.ROUNDS and max(reads) <= HS.MAX_READ, (page, reads)
            assert paged.reads == [51 if before else 50], "the paged store: one read, any depth"
            before = HS.parse_cursor(h["next"])[0]
        assert len(unpaged.reads) > 1, "the control: the unpaged store was read again deeper"
        # The worst a load can cost: ROUNDS reads of each source, MAX_READ rows at most each.
        assert sum(unpaged.reads) <= sum(min(51 * HS.GROWTH ** i, HS.MAX_READ)
                                         for i in range(HS.ROUNDS))

    def test_a_jump_far_back_costs_what_the_first_page_does_for_a_paged_store(self, stores):
        paged = Store(_rows("p", 6000, step=60))
        stores(p=paged)
        HS.timeline(None, members=[])
        first = list(paged.reads)
        paged.reads.clear()
        day = time.strftime("%Y-%m-%d", time.gmtime(BASE - 60 * 5500))
        h = HS.timeline(None, members=[], before=HS.parse_day(day)[0])
        assert first == [50] and paged.reads == [51] and len(h["events"]) == 50


class TestJumpToADay:
    def test_the_page_starts_at_the_end_of_the_day_utc(self, stores):
        day_end = _utc("2026-09-21T00:00:00Z")
        rows = [{"at": _iso(day_end + 5), "what": "next day"},
                {"at": _iso(day_end), "what": "midnight"},
                {"at": _iso(day_end - 1), "what": "last second"},
                {"at": _iso(day_end - 86400), "what": "the day's first second"},
                {"at": _iso(day_end - 86401), "what": "the day before"}]
        stores(a=Store(rows))
        place, err = HS.parse_day("2026-09-20")
        assert not err and place == (day_end, "")
        whats = [e["what"] for e in HS.timeline(None, members=[], before=place)["events"]]
        assert whats == ["last second", "the day's first second", "the day before"]

    @pytest.mark.parametrize("text", ["2026-13-01", "20-09-2026", "yesterday", "2026-02-30"])
    def test_a_day_that_is_not_a_date_is_refused_by_name(self, text):
        place, err = HS.parse_day(text)
        assert place is None and repr(text) in err

    def test_the_earlier_of_a_day_and_a_cursor_is_the_place(self):
        assert HS.place((10.0, "r-b"), (5.0, "")) == (5.0, "")
        assert HS.place(None, (5.0, "")) == (5.0, "") and HS.place(None, None) is None


class TestTheCursor:
    def test_a_cursor_is_a_time_with_its_zone_and_an_id(self):
        assert HS.parse_cursor("2026-10-20T10:00:00Z~r-0123456789abcdef") == (
            (_utc("2026-10-20T10:00:00Z"), "r-0123456789abcdef"), "")
        assert HS.parse_cursor("2026-10-20T10:00:00+00:00~ai-ab12")[0][1] == "ai-ab12"
        assert HS.parse_cursor("") == (None, "")

    @pytest.mark.parametrize("text", ["2026-10-20T10:00:00Z", "noon~r-1",
                                      "2026-10-20T10:00:00Z~r-1<script>",
                                      "2026-10-20T10:00:00~r-1"])
    def test_anything_else_is_refused_by_name(self, text):
        place, err = HS.parse_cursor(text)
        assert place is None and err and text[:20] in err


class TestTheFiltersOnTheServer:
    def test_a_kind_filter_reads_only_the_sources_that_hold_its_kinds(self, stores,
                                                                       monkeypatch):
        golden, receipts = Store(_rows("g", 80), kind="golden"), Store(_rows("r", 80),
                                                                       kind="receipt")
        stores(golden=golden, receipts=receipts)
        monkeypatch.setattr(HS, "SOURCE_KINDS", {"golden": ("golden",),
                                                 "receipts": ("receipt",)})
        h = HS.timeline(None, members=[], kinds=["golden"])
        assert receipts.reads == [] and golden.reads == [50]
        drawn, _loads, _h = _walk(kinds=["golden"])
        assert [e["what"] for e in drawn] == [f"g {i}" for i in range(80)] and h["more"]
        assert receipts.reads == [], "Load more under a kind reads no other store"

    def test_every_source_declares_its_kinds_and_every_kind_has_a_source(self):
        assert set(HS.SOURCE_KINDS) == set(HS.SOURCES)
        held = {k for kinds in HS.SOURCE_KINDS.values() for k in kinds}
        assert {k for kinds in HS.KIND_FILTERS.values() for k in kinds} <= held
        assert set(HS.UNPAGED) <= set(HS.SOURCES)


def _ctx(ref, until=None):
    return {"ref": ref, "device": "", "limit": 50, "since": None, "members": set(DEVICES),
            "inventory": set(DEVICES), "until": until, "call": ""}


class TestTheRealSources:
    """Every real source, on test_history_one_timeline's planted lab (records of every kind
    across three devices, all written now)."""

    def test_each_source_s_rows_are_the_kinds_it_declares(self, planted):  # noqa: F811
        found = {}
        for name, source in HS.SOURCES.items():
            got = source(_ctx(planted))
            kinds = {e["kind"] for e in got["events"]}
            assert kinds <= set(HS.SOURCE_KINDS[name]), (name, kinds)
            found[name] = len(got["events"])
        # The population's floor: the planted lab reaches most of the sources.
        assert sum(1 for n in found.values() if n) >= 8, found

    def test_a_paged_source_returns_nothing_newer_than_the_place(self, planted):  # noqa: F811
        until = time.time() - 3600                   # every planted record is newer
        asked, unpaged_later = [], []
        for name, source in HS.SOURCES.items():
            if not source(_ctx(planted))["events"]:
                continue
            later = [e for e in source(_ctx(planted, until))["events"]
                     if HS.epoch(e["at"]) > until]
            if name in HS.UNPAGED:
                unpaged_later += [name] if later else []
                continue
            asked.append(name)
            assert not later, (name, later[:2])
        assert len(asked) >= 6, asked              # the floor: paged sources holding rows
        # The control: an unpaged store, asked the same way, still returns its newer rows.
        assert "receipts" in unpaged_later, unpaged_later


# ---------------------------------------------------------------------------- the screens

def _fleet(n=120):
    """A store of *n* commits about r3, by a host login (so the device, person and identity
    filters all keep them)."""
    return Store(_rows("c", n), devices=["r3"], who="alex (host login, not verified)",
                 verified="host-shell")


def _attr(tag, name):
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return _h.unescape(m.group(1)) if m else None


def _more(html):
    tags = re.findall(r'<button[^>]*class="btn btn-small tl-more-btn"[^>]*>', html)
    assert len(tags) == 1, tags
    return tags[0]


def _whats(html):
    return re.findall(r'<span class="hist-what"><strong>([^<]+)</strong>', html)


class TestTheHistoryPage:
    URL = ("/v2/history?device=r3&person=alex&kind=commits&since=&identity=unverified"
           "&on=2030-01-01")

    def test_load_more_carries_every_filter_and_pushes_the_page_s_address(self, lab, stores):
        stores(c=_fleet())
        _r, html = _get(lab, self.URL)
        assert len(_whats(html)) == 50
        tag = _more(html)
        get, push = _attr(tag, "hx-get"), _attr(tag, "hx-push-url")
        assert get.startswith("/v2/history/timeline/more?") and push.startswith("/v2/history?")
        for pair in ("device=r3", "person=alex", "kind=commits", "since=", "identity=unverified",
                     "on=2030-01-01", "before="):
            assert pair in get and pair in push, (pair, get, push)
        assert _attr(tag, "hx-disabled-elt") == "this" and _attr(tag, "hx-swap") == "outerHTML"
        assert 'class="op-busy">Loading…' in html and "c 49" in _whats(html)

    def test_the_fragment_is_the_next_rows_and_the_next_foot(self, lab, stores):
        stores(c=_fleet())
        _r, html = _get(lab, self.URL)
        r, more = _get(lab, _attr(_more(html), "hx-get"))
        assert r.status_code == 200 and "<section" not in more and 'class="tl-foot"' in more
        assert _whats(more) == [f"c {i}" for i in range(50, 100)]
        r, last = _get(lab, _attr(_more(more), "hx-get"))
        assert _whats(last) == [f"c {i}" for i in range(100, 120)]
        assert "tl-more-btn" not in last and "No older record than these." in last

    def test_the_pushed_address_returns_to_the_same_place(self, lab, stores):
        stores(c=_fleet())
        _r, html = _get(lab, self.URL)
        r, page = _get(lab, _attr(_more(html), "hx-push-url"))
        assert r.status_code == 200
        assert _whats(page) == [f"c {i}" for i in range(50, 100)]
        assert "Back to the newest" in page and "Showing the 50 before" in _h.unescape(page)
        card = re.search(r'<section class="card hist-timeline" id="hist-timeline"\s+hx-get="([^"]+)"',
                         page).group(1)
        assert "before=" in card and "identity=unverified" in card, "its redraw keeps the place"

    def test_a_place_that_is_not_one_is_not_applied_and_said(self, lab, stores):
        stores(c=_fleet())
        _r, html = _get(lab, "/v2/history?since=&before=yesterday&on=someday")
        assert "Not applied: the place &#39;yesterday&#39; is not a time and a row" in html
        assert "the day &#39;someday&#39; is not a date" in html
        assert _whats(html)[0] == "c 0", "the newest page, every row there"

    def test_jump_to_is_a_field_of_the_filters(self, lab, stores):
        stores(c=_fleet())
        _r, html = _get(lab, "/v2/history?since=&on=2026-09-01")
        form = re.search(r'<form class="dev-filters".*?</form>', html, re.S).group(0)
        assert re.search(r'<input type="date" name="on" value="2026-09-01"', form)


class TestTheDeviceTab:
    def test_load_more_on_the_tab_appends_the_device_s_next_rows(self, lab, stores):
        stores(c=_fleet())
        _r, html = _get(lab, "/v2/device/r3?tab=history")
        assert len(_whats(html)) == 50
        tag = _more(html)
        get, push = _attr(tag, "hx-get"), _attr(tag, "hx-push-url")
        assert get.startswith("/v2/device/r3/history/more?") and "before=" in get
        assert push.startswith("/v2/device/r3?") and "tab=history" in push and "before=" in push
        r, more = _get(lab, get)
        assert r.status_code == 200 and _whats(more) == [f"c {i}" for i in range(50, 100)]
        r, page = _get(lab, push)
        assert r.status_code == 200 and _whats(page)[:1] == ["c 50"]
        assert "Back to the newest" in page

    def test_jump_to_on_the_tab(self, lab, stores):
        stores(c=_fleet())
        day = time.strftime("%Y-%m-%d", time.gmtime(BASE))        # every fake row's day
        r, html = _get(lab, f"/v2/device/r3?tab=history&on={day}")
        assert r.status_code == 200 and _whats(html)[:1] == ["c 0"]
        assert re.search(r'<form class="hist-jump"[^>]*>', html)
        assert f'<input type="date" name="on" value="{day}"' in html
        before = time.strftime("%Y-%m-%d", time.gmtime(BASE - 86400))
        _r, html = _get(lab, f"/v2/device/r3?tab=history&on={before}")
        assert not _whats(html)
        assert f"Nothing is recorded for r3 on or before {before}" in _h.unescape(html)
        assert "Back to the newest" in html


class Held(Store):
    """A store whose reads at a place (Load more's) wait until the test lets them answer."""

    def __init__(self, *a, **k):
        import threading
        super().__init__(*a, **k)
        self.gate, self.asked = threading.Event(), threading.Event()

    def __call__(self, ctx):
        if ctx.get("until") is not None:
            self.asked.set()
            assert self.gate.wait(20), "the test never let it answer"
        return super().__call__(ctx)


ROWS = "document.querySelectorAll('.hist-tl details.tl-row')"


class TestInABrowser:
    """Load more clicked in a real browser (Firefox; it cannot start inside nmas-test's
    namespace, so run unconfined): busy on itself while its answer is held, the next rows
    drawn in place under the first, the place pushed into the address, Back returning."""

    def test_load_more_is_busy_on_itself_appends_in_place_and_pushes_the_place(
            self, lab, stores):
        from tests import browser
        if not browser.available()[0]:
            pytest.skip(browser.available()[1])
        store = Held(_rows("c", 120), devices=["r3"], who="alex (host login, not verified)",
                     verified="host-shell")
        stores(c=store)
        import app as A
        with browser.Served(A.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url("/v2/history?since="))
                b.wait_for(f"return {ROWS}.length === 50", 15)
                b.js("document.querySelector('.tl-more-btn').scrollIntoView({block: 'center'})")
                b.click(".tl-more-btn")
                assert store.asked.wait(10), "Load more asked for the next page"
                busy = b.js("var x = document.querySelector('.tl-more-btn');"
                            "return [x.disabled, x.classList.contains('htmx-request'),"
                            " getComputedStyle(x.querySelector('.op-busy')).display !== 'none']")
                assert busy == [True, True, True], busy
                store.gate.set()
                b.wait_for(f"return {ROWS}.length === 100", 15)
                ids = b.js(f"return Array.from({ROWS}).map(function (d) {{ return d.id; }})")
                assert len(set(ids)) == 100, "each row once"
                assert b.js("return document.querySelectorAll('.tl-foot').length") == 1
                first = b.js("return location.search")
                assert "before=" in first
                # The foot was swapped in with the page: its button answers a click once htmx
                # has wired it (its internal data set), which can be after the rows land
                # (C2102: clicked before, the click did nothing and 120 never came).
                b.wait_for("var x = document.querySelector('.tl-more-btn');"
                           " return !!(x && x['htmx-internal-data'] && !x.disabled)", 15)
                b.click(".tl-more-btn")
                b.wait_for(f"return {ROWS}.length === 120", 15)
                assert b.js("return !!document.querySelector('.tl-end')"), "nothing older"
                # Back returns to the place the first Load more pushed: the page from there.
                what = ("return (document.querySelector('.hist-tl details.tl-row .hist-what')"
                        " || {}).textContent")
                b.js("history.back()")
                b.wait_for(f"return location.search === {first!r}", 15)
                b.wait_for(f"var w = {what[7:]}; return w === 'c 50'", 15)
                b.js("history.back()")
                b.wait_for("return location.search.indexOf('before=') < 0", 15)
                b.wait_for(f"var w = {what[7:]}; return w === 'c 0'", 15)
                # Phone width: the foot and the rows stay inside the page.
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": 390, "height": 900})
                b.go(srv.url("/v2/history?since="))
                b.wait_for(f"return {ROWS}.length === 50", 15)
                assert b.js("return document.documentElement.scrollWidth "
                            "<= window.innerWidth + 1")
            finally:
                store.gate.set()
                b.go("about:blank")
                browser.close_socketio_sessions()


# ---------------------------------------------------------------------------- links both ways

def _call_rows(n):
    from modules.ai import calls
    ids = []
    for i in range(n):
        cid = f"ai-{i:016x}"
        calls.record({"id": cid, "at": _iso(BASE - 600 * (n - i)), "feature": "explain",
                      "verdict": "ok", "model": "claude-sonnet-5-5", "cost_usd": 0.001,
                      "subject": {"kind": "alert", "id": f"p{i}", "rule": "R",
                                  "devices": ["r3"]}})
        ids.append(cid)
    return ids


class TestLinksBothWays:
    @pytest.fixture(autouse=True)
    def own_record(self, tmp_path, monkeypatch):
        """The record of AI calls is this test's own (as tests/test_ai_explain.py's is): the
        session's store is every test's."""
        from modules.ai import calls
        monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))

    def test_a_call_s_row_by_its_id_is_drawn_opened_however_old(self, lab, monkeypatch):
        from modules.ai import calls
        ids = _call_rows(60)                    # the oldest is past the newest 50
        calls.record_use(ids[0], "shown: answer",
                         links={"page": "/v2/monitoring/alerts/pack/p0", "anchor": "explain-p0"})
        reads, real = [], HS.SOURCES["ai_calls"]
        monkeypatch.setitem(HS.SOURCES, "ai_calls", lambda ctx: reads.append(ctx) or real(ctx))
        _r, html = _get(lab, f"/v2/history?call={ids[0]}")
        # One read, of the one source that holds AI calls: the call found by its id at the
        # store, before its newest-N cut, never by reading further back.
        assert len(reads) == 1 and reads[0]["call"] == ids[0]
        rows = re.findall(r'<details class="hist-row tl-row"[^>]*>', html)
        assert len(rows) == 1 and f'id="{ids[0]}"' in rows[0] and rows[0].endswith(" open>")
        # The page's network rides on every link of Mercury's own (`list=`), the anchor kept.
        assert ('<a href="/v2/monitoring/alerts/pack/p0?list=Lab#explain-p0">Open what it '
                'produced</a>') in html
        assert "One AI call, " + ids[0] in html

    def test_an_id_that_is_not_a_call_s_is_said(self, lab):
        _r, html = _get(lab, "/v2/history?call=x%3Cy")
        assert "Not applied: the call &#39;x&lt;y&#39; is not an AI call&#39;s id" in html

    @pytest.mark.parametrize("links,want", [
        ({"page": "/v2/history/query/ask/metrics?list=Lab&m=ifInErrors"},
         "/v2/history/query/ask/metrics?list=Lab&m=ifInErrors"),
        ({"page": "/v2/monitoring/alerts/pack/p1", "anchor": "explain-p1"},
         "/v2/monitoring/alerts/pack/p1#explain-p1"),
        ({"page": "/v2/monitoring/alerts/pack/p1", "anchor": 'x" onclick="y'},
         "/v2/monitoring/alerts/pack/p1"),
        ({"page": "https://example.invalid/x"}, ""), ({"page": "//example.invalid/x"}, ""),
        ({"page": "javascript:alert(1)"}, ""), ({"page": "/v1/x"}, ""), ({}, ""), (None, ""),
    ])
    def test_what_it_produced_is_only_ever_a_page_of_mercury_s_own(self, links, want):
        assert HS.produced(links) == want

    def test_ask_in_words_links_its_notice_to_the_call_and_the_call_to_the_builder(
            self, site):  # noqa: F811
        from modules.ai import calls
        site.world.answer = _choices()
        r, html = _words(site, "input errors per interface, the top 5")
        assert r.status_code == 200
        (row,) = calls.read()["rows"]
        note = html.split("Filled from your words", 1)[1].split("</p>", 1)[0]
        assert re.search(rf'<a href="/v2/history\?call={row["id"]}(&list=Lab)?"[^>]*>this call '
                         r'in History</a>\)', note), note
        # The call's row links to the builder as the answer filled it: the pushed address.
        (use,) = calls.uses()[row["id"]]
        assert use["use"] == "filled the builder"
        pushed = r.headers["HX-Push-Url"]
        assert use["links"]["page"] == pushed and "m=ifInErrors" in pushed
        assert HS.produced(use["links"]) == pushed

    def test_explain_s_answer_links_to_its_call_s_row(self, lab):
        import app as A
        from flask import render_template
        x = {"ok": False, "error": "couldnt_analyse", "detail": "d", "call_id": "ai-0123abcd",
             "cost_usd": 0.0123, "pack_id": "p1", "recorded": True}
        with A.app.test_request_context("/"):
            html = render_template("v2/_explain.html", x=x, explain_model="m")
            unrecorded = render_template("v2/_explain.html", x=dict(x, recorded=False),
                                         explain_model="m")
        assert '<a href="/v2/history?call=ai-0123abcd">This call in History</a> ($0.0123)' in html
        assert "This call in History" not in unrecorded, "an unrecorded call has no row"
