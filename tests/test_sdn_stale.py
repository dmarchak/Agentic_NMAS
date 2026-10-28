"""SDN's region is never a frozen page shown as current (C2003, the operator's Lab 8 walk,
2026-10-28: SDN › Responses stopped updating after a topology restart and looked current).

The region (`#sdn`, every tab, redrawn on `nmas:sdn`) carries a hidden `.stale-note` with the
moment its drawing passes its promise (`data-stale-at`) and the promise (`data-promise`), the
sidebar count's pattern (`badgeDoubt`, templates/v2/_count.html). The promise is the SDN
reader's own page promise (`reader_job.page_promise`, 3 read intervals of 30 s, 90 s), never
typed again (`sdn_page.redraw_promise`). The page's one-second tick (static/js/nmas_v2.js
`drawStale`) shows the note past that moment with no redraw, or while the live channel is down,
with Reload; while a card open in place holds the redraw (C2001) it says so instead and offers
no Reload, which would close the card.

- **The words** (`staleNote`, pure, run in duktape): current or not yet connected says nothing;
  past the promise or a dropped channel says so with Reload; held says what holds it and what
  to do, with no Reload; a redraw that arrived and was held says newer data is waiting.
- **The promise:** derived from the reader's declaration, moving when it moves.
- **The template:** every tab, page and fragment, carries one note inside the region, hidden,
  its stale moment the drawn time plus the promise, its Reload the tab's own page.
- **In a real browser:** a region past its promise shows the note with Reload; a redraw clears
  it; with a preview open it says the page is held and offers no Reload; a dropped channel says
  so.
"""

import dataclasses
import json
import os
import re
import time
from datetime import datetime, timezone

import pytest

from modules import reader_job, sdn_page
from modules.readers import sdn_controllers as SDN
from modules.sdn import loop as LP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_ops_v2 import lab  # noqa: F401 - the fixture

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _note(live, stale_at, promise, now, hold="", skipped=False):
    import dukpy
    src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
    return dukpy.evaljs("var window = {};\n" + src
                        + f"\nwindow.NMAS_V2.staleNote({json.dumps(live)}, "
                          f"{json.dumps(stale_at)}, {promise}, {now}, {json.dumps(hold)}, "
                          f"{json.dumps(skipped)});")


class TestTheWords:
    def test_current_says_nothing(self):
        assert _note("connected", 2000, 90, 1000) is None

    def test_a_page_not_yet_connected_is_current(self):
        """The first connect: a page just loaded holds fresh values (nmas_invalidation.js)."""
        assert _note("not_connected", 2000, 90, 1000) is None
        assert _note("", 2000, 90, 1000) is None

    def test_past_its_promise_it_says_so_and_offers_reload(self):
        got = _note("connected", 1000, 90, 2000)
        assert got == {"words": ": no update has arrived in the 90 s it promises, so this "
                                "page may be out of date.", "reload": True}, got

    @pytest.mark.parametrize("live,words", [("disconnected", "live updates stopped"),
                                            ("silent", "live updates silent"),
                                            ("failed", "live updates could not connect")])
    def test_a_dropped_channel_says_so_within_the_promise(self, live, words):
        got = _note(live, 2000, 90, 1000)
        assert got == {"words": f": {words}, so this page may be out of date.",
                       "reload": True}, got

    def test_held_for_an_open_card_it_offers_no_reload(self):
        got = _note("connected", 1000, 90, 2000, hold="review")
        assert got["reload"] is False
        assert "a reload would close the card open below. Send or close it first." \
            in got["words"], got

    def test_a_held_redraw_says_newer_data_is_waiting(self):
        got = _note("connected", 1000, 90, 2000, hold="review", skipped=True)
        assert got == {"words": ": newer data is waiting, held for the card open below. "
                                "Send or close it to see it.", "reload": False}, got

    def test_held_while_the_channel_is_down_names_the_channel(self):
        got = _note("disconnected", 2000, 90, 1000, hold="editing", skipped=True)
        assert got["reload"] is False and got["words"].startswith(": live updates stopped")
        assert "what you are typing" in got["words"], got


class TestThePromise:
    def test_it_is_the_readers_own_page_promise(self):
        got = sdn_page.redraw_promise(now=1_000_000)
        assert got["seconds"] == reader_job.page_promise(SDN.READER) \
            == SDN.INTERVAL_SECONDS * SDN.READER.stale_after_intervals
        drawn = datetime.strptime(got["drawn_at"], "%Y-%m-%dT%H:%M:%SZ")
        stale = datetime.strptime(got["stale_at"], "%Y-%m-%dT%H:%M:%SZ")
        assert (stale - drawn).total_seconds() == got["seconds"]

    def test_it_moves_when_the_readers_interval_moves(self, monkeypatch):
        monkeypatch.setattr(SDN, "READER", dataclasses.replace(SDN.READER, interval_seconds=7))
        assert sdn_page.redraw_promise(now=0)["seconds"] == 21


NOTE = re.compile(r'<div class="notice notice-warn stale-note" role="status" '
                  r'data-stale-at="([^"]+)" data-promise="(\d+)" hidden>')


def _region(html):
    at = html.index('<div id="sdn"')
    return html[at:]


class TestTheTemplate:
    @pytest.mark.parametrize("path,reload", [
        ("/v2/sdn?list=Default", "/v2/sdn?list=Default"),
        ("/v2/sdn/flows?list=Default&q=METER", "/v2/sdn/flows?q=METER&amp;own=hide&amp;list=Default"),
        ("/v2/sdn/responses?list=Default", "/v2/sdn/responses?list=Default"),
        ("/v2/sdn/view?list=Default&tab=responses", "/v2/sdn/responses?list=Default"),
        ("/v2/sdn/view?list=Default&tab=flows", "/v2/sdn/flows?own=hide&amp;list=Default")])
    def test_every_tab_carries_one_hidden_note_its_moment_and_its_reload(self, lab, path,
                                                                         reload):
        before = time.time()
        html = lab["client"].get(path).get_data(as_text=True)
        found = NOTE.findall(_region(html))
        assert len(found) == 1, (path, found)
        stale_at, promise = found[0]
        assert int(promise) == reader_job.page_promise(SDN.READER)
        stale = datetime.strptime(stale_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
        assert int(before) - 1 + int(promise) <= stale <= time.time() + int(promise) + 1
        note = _region(html)[_region(html).index("stale-note"):]
        note = note[:note.index("</div>")]
        assert "Last updated <time" in note and 'class="stale-why"' in note
        assert f'class="btn btn-small stale-reload" href="{reload}"' in note, note


# ── In a real browser ─────────────────────────────────────────────────────────────────────

READY = ("return !!window.htmx && !!document.getElementById('sdn') && "
         "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')")
STALE = "document.querySelector('#sdn .stale-note')"


def _past(b):
    """The region's drawing past its promise, as after 90 s with no redraw."""
    b.js(f"{STALE}.setAttribute('data-stale-at', '2020-01-01T00:00:00Z'); return 1")


def _said(b):
    return b.js(f"var n = {STALE}, r = n.querySelector('.stale-reload');"
                "return {hidden: n.hidden, words: n.textContent.replace(/\\s+/g, ' ').trim(),"
                " reload: !r.hidden}")


def test_a_region_past_its_promise_says_so_and_a_redraw_clears_it(lab):
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as A

    row = LP.propose("Default", {
        "key": "k-stale", "rule": "scan", "title": "SDN scan", "network": "Default",
        "connection": "lab-controller", "dpid": 1, "dpid_hex": "0000000000000001",
        "source": "192.0.2.1", "targets": ["192.0.2.2"], "confidence": "high",
        "words": "192.0.2.1 reached 25 distinct destination ports"}, "drop_source", "low",
        why="HITL")
    slot = f"#sdn-rp-{row['id']}"
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/sdn/responses?list=Default"))
            b.wait_for(READY, 15)
            b.wait_for("return window.NMAS && NMAS.live().state === 'connected'", 15)
            current = _said(b)
            # Past its promise with nothing open: said, with Reload.
            _past(b)
            b.wait_for(f"return !{STALE}.hidden", 5)
            stale = _said(b)
            # A redraw (the reader's announcement) draws a new region, current again.
            b.js("document.body.dispatchEvent(new CustomEvent('nmas:sdn')); return 1")
            b.wait_for(f"return !!{STALE} && {STALE}.hidden && "
                       f"{STALE}.getAttribute('data-stale-at') !== '2020-01-01T00:00:00Z'", 15)
            b.wait_for(READY, 15)
            # A preview open in place: past its promise, held, and no Reload.
            b.js(f"document.querySelector('form[hx-post*=\"/response/{row['id']}/preview\"]"
                 " button[type=submit]').click(); return 1")
            b.wait_for(f"return !!document.querySelector('{slot} input[name=hash]')", 15)
            _past(b)
            b.wait_for(f"return !{STALE}.hidden", 5)
            held = _said(b)
            # The channel drops, the preview still open: the channel named, still no Reload.
            b.js("window.__nmasSocket.disconnect(); return 1")
            b.wait_for(f"return {STALE}.textContent.indexOf('live updates stopped') >= 0", 5)
            down = _said(b)
            preview_kept = b.js(f"return !!document.querySelector('{slot} input[name=hash]')")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert current["hidden"] is True, current
    assert stale["hidden"] is False and stale["reload"] is True, stale
    assert re.fullmatch(r"Last updated (just now|1 min ago): no update has arrived in the "
                        r"90 s it promises, so this page may be out of date\. Reload",
                        stale["words"]), stale
    assert held["reload"] is False, held
    assert "a reload would close the card open below. Send or close it first." \
        in held["words"], held
    assert down["reload"] is False and "live updates stopped" in down["words"], down
    assert preview_kept is True
