"""A live refresh never interrupts the person (C2810; the operator, 2026-11-08; the charter's
"Human-facing means human-readable", rule 6).

The operator's words: "A refresh keeps scroll position, focus, open or closed disclosures, text
in inputs, and marks (Right/Wrong). It doesn't flash, and nothing above the reader shifts: new
items above the viewport show as 'N new, show them' instead of pushing the page."

Each live region replaced itself whole on every announcement. It now MERGES the answer
(static/js/nmas_v2.js, `mergeInto`): what the server left alone is left exactly as the person
has it, a changed row has only what changed set, rows are matched by their key, and a new
keyed row that would land above the window waits behind "N new, show them".

- **The merge itself, in a real browser:** an unchanged node is the same node afterwards, with
  its state; a changed one is the same node with the server's change; a new row above the
  window is held and counted; a part the page loaded itself (a row's body, a person's answer
  drawn in place, Load more's rows) is kept.
- **Each live page, in a real browser:** scrolled to the middle, a disclosure opened, a control
  focused and a field typed in, the page's own announcement fired; then the reader's place
  (`scrollY`), the disclosure, the focus and the text are as they were, the region is the same
  node (it was never replaced, so never half drawn), and nothing on the screen moved (each
  shown element's top, before and after; and the browser's layout-shift entries where it has
  them).

The browser's layout-shift entries (`PerformanceObserver`, 'layout-shift') are read where the
browser offers them; Firefox did not on 2026-11-08, so the shift measured is every shown
element's top before and after, in CSS pixels.
"""

import pytest

from tests.test_device_v2 import lab  # noqa: F401 - the fixture
from tests.test_swaps_in_a_browser import READY, SETTLED, served  # noqa: F401

#: C1522: these pages' readers write their stores; each test keeps them in its own folder.
pytestmark = pytest.mark.usefixtures("reader_stores_in_tmp")

#: Counts each live redraw as it settles, and the browser's layout shifts where it has them.
WATCH = """
window.__settled = 0; window.__shift = 0; window.__shiftKnown = false;
document.addEventListener('htmx:afterSettle', function (e) {
  var ev = e.detail && e.detail.requestConfig && e.detail.requestConfig.triggeringEvent;
  if (ev && String(ev.type).indexOf('nmas:') === 0) window.__settled++;
});
try {
  if ((PerformanceObserver.supportedEntryTypes || []).indexOf('layout-shift') >= 0) {
    window.__shiftKnown = true;
    new PerformanceObserver(function (list) {
      list.getEntries().forEach(function (x) { if (!x.hadRecentInput) window.__shift += x.value; });
    }).observe({type: 'layout-shift', buffered: false});
  }
} catch (x) {}
return 1;
"""

#: Every element shown in the window, with its top: what the reader sees, before a refresh.
SHOWN = """
var out = [], all = document.querySelectorAll('main *');
for (var i = 0; i < all.length; i++) {
  var r = all[i].getBoundingClientRect();
  if (r.height > 0 && r.bottom > 0 && r.top < innerHeight) out.push([all[i], r.top]);
}
window.__shown = out;
return out.length;
"""

#: The largest move, in CSS px, of any element shown before that is still on the page.
MOVED = """
var most = 0, gone = 0, which = [];
(window.__shown || []).forEach(function (p) {
  if (!p[0].isConnected) {
    gone++;
    if (which.length < 5) which.push(p[0].tagName + '.' + p[0].className + '#' + p[0].id);
    return;
  }
  var r = p[0].getBoundingClientRect();
  if (r.height === 0) return;
  most = Math.max(most, Math.abs(r.top - p[1]));
});
return {most: most, gone: gone, which: which, shown: (window.__shown || []).length};
"""


def _fire(b, key):
    """The page's own announcement, as the relay fires it (nmas_v2.js `relay`)."""
    b.js("window.__settledBefore = window.__settled; htmx.trigger(document.body, 'nmas:' + arguments[0]);"
         " return 1", key)
    b.wait_for(f"return window.__settled > window.__settledBefore && {SETTLED}", 15)



# ── the merge itself ────────────────────────────────────────────────────────────────────────

@pytest.fixture
def page(served):  # noqa: F811
    srv, b = served
    b.go(srv.url("/v2/devices"))
    b.wait_for(READY, 15)
    return b


def _merge(b, before, after, setup=""):
    """Draw *before* in a box as the server drew it, run *setup* (the person's doing), then
    merge *after* into it; return what the checks read, set by *setup* as `window.__check`."""
    b.js("var old = document.getElementById('merge-box'); if (old) old.remove();"
         "var box = document.createElement('div'); box.id = 'merge-box';"
         "box.innerHTML = arguments[0]; document.querySelector('main').prepend(box);"
         "NMAS_V2.capture(box); return 1", before)
    b.js("var box = document.getElementById('merge-box');" + setup + "; return 1")
    return b.js("var box = document.getElementById('merge-box');"
                "var t = document.createElement('template'); t.innerHTML = arguments[0];"
                "NMAS_V2.mergeInto(false, box, t.content);"
                "return window.__check ? window.__check(box) : box.innerHTML", after)


ROW = [f'<details class="r" data-key="r{i}"><summary>row {i}</summary><p>body {i}</p></details>'
       for i in range(3)]
ROWS = "".join(ROW)


class TestTheMerge:
    def test_an_unchanged_row_is_the_same_node_with_its_state(self, page):
        got = _merge(page, ROWS, ROWS.replace("row 2", "row 2, changed"),
                     "var r = box.querySelectorAll('details'); window.__r = r; r[0].open = true;"
                     "r[0].querySelector('summary').tabIndex = 0;"
                     "r[0].querySelector('summary').focus();"
                     "window.__check = function (box) { var n = box.querySelectorAll('details');"
                     " return {same: n[0] === window.__r[0] && n[2] === window.__r[2],"
                     " open: n[0].open, focused: document.activeElement === n[0].querySelector('summary'),"
                     " changed: n[2].querySelector('summary').textContent}; }")
        assert got == {"same": True, "open": True, "focused": True, "changed": "row 2, changed"}, got

    def test_rows_are_matched_by_their_key_not_their_place(self, page):
        moved = '<details class="r" data-key="rX"><summary>row X</summary></details>' + ROWS
        got = _merge(page, ROWS, moved,
                     "window.__r = box.querySelectorAll('details'); window.__r[1].open = true;"
                     "window.__check = function (box) { var n = box.querySelectorAll('details');"
                     " return {count: n.length, keys: Array.prototype.map.call(n, function (x) {"
                     " return x.getAttribute('data-key'); }), same: n[2] === window.__r[1],"
                     " open: n[2].open}; }")
        assert got["keys"] == ["rX", "r0", "r1", "r2"], got
        assert got["same"] and got["open"], got

    def test_a_new_row_above_the_window_waits_behind_n_new(self, page):
        # The box is at the top of the page and the window scrolled past it.
        page.js("var s = document.createElement('div'); s.id = 'merge-spacer';"
                " s.style.height = '3000px'; document.querySelector('main').appendChild(s);"
                " return 1")
        new = ('<details class="r" data-key="rN1"><summary>new 1</summary></details>'
               '<details class="r" data-key="rN2"><summary>new 2</summary></details>' + ROWS)
        got = _merge(page, ROWS, new,
                     "window.scrollTo(0, 600); window.__y = window.scrollY;"
                     "window.__check = function (box) {"
                     " var held = box.querySelectorAll('[data-nmas-new][hidden]');"
                     " var note = box.querySelector('.live-new button');"
                     " return {held: held.length, note: note ? note.textContent : null,"
                     " y: window.scrollY === window.__y}; }")
        # The place a moment later too, once settled: a late move the merge caused is caught.
        y, was = page.settled_place(), page.js("return window.__y")
        page.js("document.getElementById('merge-spacer').remove(); return 1")
        assert got == {"held": 2, "note": "2 new, show them", "y": True}, got
        assert y == was, f"the reader's place moved after the merge: scrollY {was} -> {y}"

    def test_show_them_draws_the_rows_and_takes_the_reader_there(self, page):
        page.js("var s = document.createElement('div'); s.id = 'merge-spacer';"
                " s.style.height = '3000px'; document.querySelector('main').appendChild(s);"
                " return 1")
        new = '<details class="r" data-key="rN1"><summary>new 1</summary></details>' + ROWS
        _merge(page, ROWS, new, "window.scrollTo(0, 600)")
        page.js("document.querySelector('#merge-box .live-new button').click(); return 1")
        got = page.js("var box = document.getElementById('merge-box');"
                      "var n = box.querySelector('[data-key=rN1]');"
                      "return {hidden: n.hidden, note: !!box.querySelector('.live-new'),"
                      " top: Math.round(n.getBoundingClientRect().top)}")
        page.js("document.getElementById('merge-spacer').remove(); return 1")
        assert got["hidden"] is False and got["note"] is False, got
        assert 0 <= got["top"] < 200, got

    def test_a_new_row_in_view_is_drawn_at_once(self, page):
        new = '<details class="r" data-key="rN1"><summary>new 1</summary></details>' + ROWS
        got = _merge(page, ROWS, new,
                     "window.scrollTo(0, 0);"
                     "window.__check = function (box) { return {held: box.querySelectorAll("
                     "'[data-nmas-new]').length, note: !!box.querySelector('.live-new')}; }")
        assert got == {"held": 0, "note": False}, got

    def test_what_the_page_loaded_into_a_row_is_kept(self, page):
        # A row's body loaded by a person (an Explain, a diff, a proposal), and a person's
        # answer drawn in place of a keyed part (a Right mark): the page's own, so kept.
        before = ('<div data-key="a"><p>head a</p><div class="slot"><p>Drawn when open</p></div>'
                  '<span id="mark-a"><button>Right</button></span></div>')
        after = before.replace("head a", "head a, changed")
        got = _merge(page, before, after,
                     "var slot = box.querySelector('.slot'); slot.innerHTML = '<p>the answer</p>';"
                     "var m = box.querySelector('#mark-a'); var a = document.createElement('span');"
                     "a.id = 'mark-a'; a.textContent = 'Marked right by you'; m.replaceWith(a);"
                     "window.__check = function (box) { return {slot: box.querySelector('.slot').textContent,"
                     " mark: box.querySelector('#mark-a').textContent,"
                     " head: box.querySelector('p').textContent,"
                     " marks: box.querySelectorAll('[id=mark-a]').length}; }")
        assert got == {"slot": "the answer", "mark": "Marked right by you",
                       "head": "head a, changed", "marks": 1}, got

    def test_rows_loaded_after_a_row_keep_it_when_it_falls_off_the_first_page(self, page):
        # Load more's rows follow the last row; a newer record pushes that row to page two,
        # and it must not vanish from between the pages.
        before = ROWS + '<div class="foot" data-key="foot"><button>Load more</button></div>'
        after = ('<details class="r" data-key="rN"><summary>newest</summary></details>' +
                 ROW[0] + ROW[1] + '<div class="foot" data-key="foot"><button>Load more</button></div>')
        got = _merge(page, before, after,
                     "var foot = box.querySelector('.foot'); var t = document.createElement('template');"
                     "t.innerHTML = '<details class=r data-key=r3><summary>row 3</summary></details>"
                     "<div class=foot data-key=foot><p>No older record.</p></div>';"
                     "foot.replaceWith(t.content);"
                     "window.__check = function (box) { return Array.prototype.map.call("
                     "box.querySelectorAll('[data-key]'), function (x) { return x.getAttribute('data-key'); }); }")
        assert got == ["rN", "r0", "r1", "r2", "r3", "foot"], got

    def test_a_component_or_a_loading_part_the_server_drew_differently_starts_again(self, page):
        # A redraw always gave an Alpine component its state afresh from what the server drew
        # (a busy check's late words), and htmx fires `load` on an element's first wiring only
        # (a held card drawn again as "starting" must ask for its preview): both are drawn new.
        # One the server left alone is the same node, its state kept.
        before = ('<div data-key="a" x-data="menu"><p>one</p></div>'
                  '<div data-key="b" x-data="menu"><p>two</p></div>'
                  '<section data-key="c" hx-trigger="nmas:x from:body"><p>held</p></section>')
        after = (before.replace("<p>two</p>", "<p>two, changed</p>")
                 .replace('hx-trigger="nmas:x from:body"><p>held', 'hx-trigger="load"><p>starting'))
        got = _merge(page, before, after,
                     "window.__k = Array.prototype.slice.call(box.children);"
                     "window.__check = function (box) { var n = box.children;"
                     " return [n[0] === window.__k[0], n[1] === window.__k[1], n[2] === window.__k[2],"
                     " n[1].textContent, n[2].textContent]; }")
        assert got == [True, False, False, "two, changed", "starting"], got

    def test_an_attribute_the_server_left_alone_keeps_what_the_page_made_of_it(self, page):
        before = '<div data-key="a" class="x"><button class="b" style="">Go</button></div>'
        after = '<div data-key="a" class="x y"><button class="b">Go</button></div>'
        got = _merge(page, before, after,
                     "var b = box.querySelector('button'); b.style.display = 'none';"
                     "b.classList.add('mine'); box.firstChild.classList.add('mine');"
                     "window.__check = function (box) { var d = box.firstChild;"
                     " return {cls: d.className, btn: d.firstChild.className}; }")
        assert got == {"cls": "x mine y", "btn": "b mine"}, got


# ── Needs attention ─────────────────────────────────────────────────────────────────────────


def _row(i, what=None, ack=False):
    return {"id": f"t:row{i}", "level": "danger", "what": what or f"Row {i} needs a look",
            "source": "drift", "since": "2026-11-08T02:00:00Z", "devices": [], "action": {},
            "clears": "", "clears_at": None, "cause": f"cause {i}", "operands": [],
            "attached": [], "read_at": "2026-11-08T02:01:00Z", "acknowledge": ack,
            "event": f"e-{i}" if ack else None}


@pytest.fixture
def attention_rows(monkeypatch):
    from routes import v2
    real = v2._attention
    state = {"rows": [_row(i, ack=(i == 22)) for i in range(40)]}

    def with_rows():
        a = dict(real())
        a["rows"] = [dict(r) for r in state["rows"]]
        a["badge"] = dict(a.get("badge") or {}, n=len(state["rows"]))
        return a
    monkeypatch.setattr(v2, "_attention", with_rows)
    return state


def test_needs_attention_keeps_the_reader_s_place_through_a_refresh(served, attention_rows):  # noqa: F811
    srv, b = served
    b.go(srv.url("/v2/"))
    b.wait_for(READY + " && document.querySelectorAll('details.att').length === 40", 15)
    b.js(WATCH)
    row = "document.querySelector('[data-attention-row=\"t:row20\"]')"
    # The person: row 20 opened, the window at the middle of the list, row 21's line focused.
    b.click('[data-attention-row="t:row20"] > summary')
    b.wait_for(f"return {row}.open", 5)
    b.js(f"{row}.scrollIntoView({{block: 'center'}}); "
         "document.querySelector('[data-attention-row=\"t:row21\"] > summary').focus(); return 1")
    b.js("window.__region = document.getElementById('attention');"
         "window.__focus = document.activeElement; return 1")
    before = b.settled_place()
    b.js(SHOWN)
    # Three new rows arrive at the top, and row 30's title changes.
    attention_rows["rows"][30] = _row(30, what="Row 30, measured again")
    attention_rows["rows"][0:0] = [_row(100 + i) for i in range(3)]
    _fire(b, "acknowledgements")
    y = b.settled_place()
    after = b.js(f"return {{open: {row}.open,"
                 " same: document.getElementById('attention') === window.__region,"
                 " focused: document.activeElement === window.__focus,"
                 " changed: document.querySelector('[data-attention-row=\"t:row30\"] .att-what').textContent,"
                 " held: document.querySelectorAll('#attention [data-nmas-new][hidden]').length,"
                 " note: (document.querySelector('#attention .live-new button') || {}).textContent || '',"
                 " shift: window.__shift, known: window.__shiftKnown}")
    moved = b.js(MOVED)
    assert after["same"], "the list was replaced, not merged (it can be caught half drawn)"
    assert y == before, f"the reader's place moved: scrollY {before} -> {y}"
    assert after["open"] and after["focused"], after
    assert after["changed"] == "Row 30, measured again", after
    assert after["held"] == 3 and after["note"] == "3 new, show them", after
    assert moved["most"] < 1 and moved["gone"] == 0, moved
    assert after["shift"] < 0.01, after
    # Shown, the three are drawn and the reader is taken to them.
    b.click("#attention .live-new button")
    b.wait_for("return !document.querySelector('#attention [data-nmas-new]') &&"
               " !document.querySelector('#attention .live-new') &&"
               " document.querySelector('[data-attention-row=\"t:row100\"]').getBoundingClientRect().top >= -1", 5)


def test_needs_attention_keeps_typed_text_through_a_refresh(served, attention_rows):  # noqa: F811
    srv, b = served
    b.go(srv.url("/v2/"))
    b.wait_for(READY + " && document.querySelectorAll('details.att').length === 40", 15)
    b.js(WATCH)
    row = "document.querySelector('[data-attention-row=\"t:row22\"]')"
    b.click('[data-attention-row="t:row22"] > summary')
    b.wait_for(f"return {row}.open", 5)
    b.js(f"{row}.scrollIntoView({{block: 'center'}}); return 1")
    b.click('[data-attention-row="t:row22"] .att-ack button')
    b.wait_for(f"var i = {row}.querySelector('input[name=why]'); return !!i && i.offsetParent !== null", 10)
    b.click('[data-attention-row="t:row22"] input[name=why]')
    b.type('[data-attention-row="t:row22"] input[name=why]', "the uplink flapped")
    before = b.settled_place()
    # A new row above, and row 5 (on screen above the reader's) measured again.
    attention_rows["rows"][5] = _row(5, what="Row 5, measured again")
    attention_rows["rows"][0:0] = [_row(100)]
    _fire(b, "acknowledgements")
    y = b.settled_place()
    got = b.js(f"var i = {row}.querySelector('input[name=why]');"
               "return {value: i.value, focused: document.activeElement === i,"
               " held: document.getElementById('attention').getAttribute('data-held'),"
               " note: (document.querySelector('#attention .live-new button') || {}).textContent || '',"
               f" waiting: ({row}.querySelector('.held-note') || {{}}).textContent || '',"
               " changed: document.querySelector('[data-attention-row=\"t:row5\"] .att-what').textContent}")
    # The field and its form stay as the person has them, saying newer data waits; the rest
    # of the list is drawn around them (C2810, the survey's finding 79: one open form held
    # the whole list).
    assert got["value"] == "the uplink flapped" and got["focused"], got
    assert y == before, f"the reader's place moved: scrollY {before} -> {y}"
    assert got["held"] == "1" and "Newer data is waiting" in got["waiting"], got
    assert got["note"] == "1 new, show them" and got["changed"] == "Row 5, measured again", got


# ── History ─────────────────────────────────────────────────────────────────────────────────


def _event(i, what=None):
    return {"id": f"ev-{i}", "kind": "commit", "at": f"2026-11-08T{i // 60:02d}:{i % 60:02d}:00Z",
            "devices": ["r3"], "devices_words": "r3", "what": what or f"Record {i}",
            "who": "alex", "who_short": "alex", "detail": f"what record {i} says", "sha": "",
            "marks": []}


@pytest.fixture
def history_rows(monkeypatch):
    from modules import history_sources as HS
    state = {"events": [_event(i) for i in range(60, 0, -1)]}

    def timeline(ref, **kw):
        ev = [dict(e) for e in state["events"]]
        return {"events": ev, "errors": [], "unreached": [], "unborn": [], "limit": 100,
                "total": len(ev), "more": False, "next": "", "people": [], "counts": {},
                "identity": {}}
    monkeypatch.setattr(HS, "timeline", timeline)
    return state


def test_history_keeps_the_reader_s_place_through_a_refresh(served, history_rows):  # noqa: F811
    srv, b = served
    b.go(srv.url("/v2/history"))
    b.wait_for(READY + " && document.querySelectorAll('#hist-timeline details.tl-row').length === 60", 15)
    b.js(WATCH)
    b.click("#ev-30 > summary")
    b.wait_for("return document.getElementById('ev-30').open", 5)
    b.js("document.getElementById('ev-30').scrollIntoView({block: 'center'});"
         "document.querySelector('#ev-29 > summary').focus(); return 1")
    b.js("window.__region = document.getElementById('hist-timeline');"
         "window.__focus = document.activeElement; return 1")
    before = b.settled_place()
    b.js(SHOWN)
    history_rows["events"][20] = _event(40, what="Record 40, amended")
    history_rows["events"][0:0] = [_event(70), _event(69)]
    _fire(b, "goldens")
    y = b.settled_place()
    after = b.js("return {open: document.getElementById('ev-30').open,"
                 " same: document.getElementById('hist-timeline') === window.__region,"
                 " focused: document.activeElement === window.__focus,"
                 " changed: document.querySelector('#ev-40 .hist-what').textContent,"
                 " held: document.querySelectorAll('#hist-timeline [data-nmas-new][hidden]').length,"
                 " note: (document.querySelector('#hist-timeline .live-new button') || {}).textContent || '',"
                 " shift: window.__shift}")
    moved = b.js(MOVED)
    assert after["same"], "the timeline was replaced, not merged"
    assert y == before, f"the reader's place moved: scrollY {before} -> {y}"
    assert after["open"] and after["focused"], after
    assert after["changed"] == "Record 40, amended", after
    assert after["held"] == 2 and after["note"] == "2 new, show them", after
    assert moved["most"] < 1 and moved["gone"] == 0, moved
    assert after["shift"] < 0.01, after


# ── every other live page ───────────────────────────────────────────────────────────────────

#: The live regions on the page, their keys, and what a person has there: the first disclosure
#: drawn in one, the first control a person can focus, and the first text field.
SURVEY = """
var regions = Array.prototype.filter.call(document.querySelectorAll('[hx-trigger*="nmas:"]'),
  function (r) { return r.offsetParent !== null || r.id === 'nmas-in-progress'; });
var keys = {};
regions.forEach(function (r) {
  (r.getAttribute('hx-trigger').match(/nmas:[a-z_]+/g) || []).forEach(function (k) { keys[k.slice(5)] = 1; });
});
function first(sel) {
  for (var i = 0; i < regions.length; i++) {
    var all = regions[i].querySelectorAll(sel);
    for (var j = 0; j < all.length; j++) if (all[j].offsetParent !== null) return all[j];
  }
  return null;
}
var main = regions.filter(function (r) { return document.querySelector('main').contains(r); });
var d = first('main details:not([hx-get]) > summary');
var f = first('main button:not([disabled]), main a[href]');
var t = first('main input[type=text]:not([disabled]), main input[type=search]:not([disabled])');
window.__regions = regions;
window.__survey = {details: d ? d.parentNode : null, focus: f, field: t};
return {regions: main.map(function (r) { return r.id || r.tagName; }), keys: Object.keys(keys).sort(),
        details: !!d, focus: !!f, field: !!t};
"""

#: The live pages, each in the lab of tests/test_device_v2.py (the survey's table of 93 regions
#: lists which regions each draws).
LIVE_PAGES = ["/v2/devices", "/v2/device/r3", "/v2/device/r3?tab=intent",
              "/v2/device/r3?tab=history", "/v2/device/r3?tab=monitoring",
              "/v2/device/r3?tab=logs", "/v2/device/r3?tab=netbox",
              "/v2/device/r3?tab=neighbours", "/v2/monitoring", "/v2/monitoring/coverage",
              "/v2/monitoring/alerts?view=history", "/v2/history", "/v2/credentials",
              "/v2/logs", "/v2/templates", "/v2/settings", "/v2/update", "/v2/sdn",
              "/v2/dhcp", "/v2/topology"]


@pytest.mark.parametrize("url", LIVE_PAGES)
def test_a_live_page_keeps_what_the_person_is_doing_through_a_refresh(served, url):  # noqa: F811
    srv, b = served
    b.go(srv.url(url))
    b.wait_for(READY, 20)
    b.js(WATCH)
    survey = b.js(SURVEY)
    assert survey["regions"] and survey["keys"], f"{url}: no live region drawn: {survey}"
    # Room to scroll, so the reader's place is a place in the middle of the page: a spacer
    # above the page's own content and one under it.
    b.js("var m = document.querySelector('main'), a = document.createElement('div'),"
         " z = document.createElement('div'); a.style.height = '900px'; z.style.height = '2000px';"
         " m.insertBefore(a, m.firstChild); m.appendChild(z); return 1")
    if survey["details"]:
        b.js("window.__survey.details.querySelector('summary').click(); return 1")
    b.js("var at = window.__survey.details || window.__survey.focus || window.__regions[0];"
         " at.scrollIntoView({block: 'center'}); return 1")
    if survey["focus"]:
        b.js("window.__survey.focus.focus({preventScroll: true}); return 1")
    b.js("window.__before = window.__regions.slice();"
         "window.__focusWas = document.activeElement; return 1")
    # Read once the browser has settled the scroll: /v2/update's lands on a fractional place
    # that Firefox moves by a pixel about 0.06 s later, with no refresh sent (C3397).
    before = b.settled_place()
    assert before > 0, f"{url}: the page did not scroll, so its place is not tested"
    b.js(SHOWN)
    for key in survey["keys"]:
        b.js("htmx.trigger(document.body, 'nmas:' + arguments[0]); return 1", key)
    b.wait_for(f"return window.__settled > 0 && {SETTLED}", 20)
    b.wait_for(f"return {SETTLED}", 20)
    y = b.settled_place()
    after = b.js("var s = window.__survey;"
                 "return {replaced: window.__before.filter(function (r) { return !r.isConnected; })"
                 "  .map(function (r) { return r.id || r.tagName; }),"
                 " open: s.details ? s.details.isConnected && s.details.open : null,"
                 " focused: s.focus ? document.activeElement === s.focus : null}")
    moved = b.js(MOVED)
    assert after["replaced"] == [], f"{url}: replaced whole, not merged: {after['replaced']}"
    assert y == before, f"{url}: the reader's place moved: scrollY {before} -> {y}"
    if survey["details"]:
        assert after["open"], f"{url}: the disclosure the person opened closed"
    if survey["focus"]:
        assert after["focused"], f"{url}: the focus was lost"
    assert moved["most"] < 1, f"{url}: what was on screen moved {moved['most']} px: {moved}"
    # Nothing on screen was drawn again (a chart rebuilt, a row replaced): the flash.
    assert moved["gone"] == 0, (f"{url}: {moved['gone']} element(s) on screen were drawn "
                                f"again: {moved['which']}")
    # Typed text, held while it is edited.
    if survey["field"]:
        b.js("var t = window.__survey.field; t.focus(); t.value = 'half typed';"
             " t.dispatchEvent(new Event('input', {bubbles: true})); return 1")
        for key in survey["keys"]:
            b.js("htmx.trigger(document.body, 'nmas:' + arguments[0]); return 1", key)
        b.wait_for(f"return {SETTLED}", 20)
        kept = b.js("var t = window.__survey.field;"
                    "return {value: t.isConnected ? t.value : null, focused: document.activeElement === t}")
        assert kept == {"value": "half typed", "focused": True}, f"{url}: {kept}"
