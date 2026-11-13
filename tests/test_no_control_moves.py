"""No control moves when a row opens and the page begins to scroll (C3468; the operator,
2026-11-13: "no control moves when its result appears").

Measured 2026-11-13 in a real browser at 1280 px, each screen's controls pressed once from a
window the page fitted (143 presses on Needs attention, the incident page, the heal card on a
device's History tab, History, Settings › Self-healing and Logs): on every one of those
screens, an answer that made the page taller than its window grew the window's scrollbar,
which took 12 px from the layout (45 of the 143 presses): a History row's own summary became
12 px narrower and everything placed from the right moved 12 px left (the timeline's help link,
the right column of a two-column page 6 px). One cause for every screen, held here on the three
pages the suite's lab draws rows on: the frame keeps the scrollbar's place whether or not the
page scrolls (`scrollbar-gutter: stable` on the page, static/css/nmas-v2.css).

- **The case is reached:** the window is made as tall as the page, so the page does not scroll;
  rows are opened until it does (both asserted, so the test cannot pass on a page that never
  began to scroll).
- **Nothing moved sideways:** the layout is as wide after as before, and every control drawn
  before is at the same x with the same width; the opened row's own summary is where it was.
- **Each read is of a settled page** (the pattern of `tests.browser.Browser.settled_place`):
  two equal reads `PLACE_STEP_S` apart, and a page still moving at the bound fails.
"""

import time

import pytest

from tests import browser as BR
from tests.test_device_v2 import lab  # noqa: F401 - the fixture
from tests.test_history_paging import _fleet, stores  # noqa: F401 - the fixture
from tests.test_swaps_in_a_browser import READY, served  # noqa: F401

#: Every control drawn in the page's main area, and each part of the top bar, with its place
#: in the document: ``{key: [x, width]}``, the layout's width and whether the page scrolls. A
#: key is the control's tag, its words and its turn among those alike.
PLACES = r"""
function vis(e) { var r = e.getBoundingClientRect(), s = getComputedStyle(e);
  // A closed <details> keeps its content's boxes (content-visibility: hidden) without
  // drawing them: a control in one is not on the page until its row opens.
  for (var d = e.parentElement && e.parentElement.closest('details'); d;
       d = d.parentElement && d.parentElement.closest('details')) {
    var own = e.closest('summary');
    if (!d.open && !(own && own.parentElement === d)) return false;
  }
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; }
var seen = {}, out = {};
document.querySelectorAll('main button, main summary, main select, main input:not([type=hidden]),'
    + ' main a, header.topbar > *').forEach(function (e) {
  if (!vis(e)) return;
  var words = (e.innerText || e.value || e.getAttribute('aria-label') || e.name || '')
      .trim().replace(/\s+/g, ' ').slice(0, 50);
  var base = e.tagName.toLowerCase() + '|' + words;
  seen[base] = (seen[base] || 0) + 1;
  var r = e.getBoundingClientRect();
  out[base + '|' + seen[base]] = [Math.round((r.left + window.scrollX) * 10) / 10,
                                  Math.round(r.width * 10) / 10];
});
var d = document.documentElement;
return {places: out, layout: d.clientWidth, window: window.innerWidth,
        scrolls: d.scrollHeight > window.innerHeight, tall: d.scrollHeight,
        inner: window.innerHeight};
"""

#: Each page, and its rows' summaries (opened in turn until the page scrolls).
PAGES = (("/v2/history?since=", ".hist-tl details.tl-row > summary"),
         ("/v2/device/r3?tab=history", "#history details.tl-row > summary"),
         ("/v2/", "#attention details.att > summary"))


def _settled(b, bound=None):
    """PLACES once two reads `PLACE_STEP_S` apart agree; a page still moving at *bound* fails
    naming what differed, and returns nothing."""
    bound = BR.PLACE_SETTLE_BOUND_S * 4 if bound is None else bound
    reads = [b.js(PLACES)]
    deadline = time.monotonic() + bound
    while True:
        time.sleep(BR.PLACE_STEP_S)
        reads.append(b.js(PLACES))
        if reads[-1] == reads[-2]:
            return reads[-1]
        if time.monotonic() > deadline:
            raise AssertionError(
                f"the page did not settle within {bound} s (two equal reads {BR.PLACE_STEP_S} s "
                f"apart): layout {[r['layout'] for r in reads]}, height "
                f"{[r['tall'] for r in reads]}")


def _fit(b):
    """The window made as tall as the page, so the page does not scroll."""
    for _ in range(4):
        got = _settled(b)
        if not got["scrolls"]:
            return got
        rect = b._call("GET", f"/session/{b.session}/window/rect")
        b._call("POST", f"/session/{b.session}/window/rect",
                {"width": rect["width"], "height": rect["height"] + got["tall"] - got["inner"] + 24})
    raise AssertionError(f"the window could not be made to fit the page: {got['tall']} px tall "
                         f"in {got['inner']} px")


def _moved(before, after) -> list:
    """Each control drawn before whose x or width differs after, by more than half a pixel."""
    out = []
    for key, (x, w) in before["places"].items():
        if key in after["places"]:
            ax, aw = after["places"][key]
            if abs(ax - x) > 0.5 or abs(aw - w) > 0.5:
                out.append((key, [x, w], [ax, aw]))
    return out


@pytest.mark.parametrize("path,rows", PAGES)
def test_a_row_that_opens_moves_nothing_sideways_when_the_page_begins_to_scroll(
        served, stores, path, rows):  # noqa: F811
    srv, b = served
    stores(c=_fleet(12))
    b.go(srv.url(path))
    b.wait_for(f"return {READY[len('return '):]} && "
               f"document.querySelectorAll(arguments[0]).length >= 3", 20, rows)
    before = _fit(b)
    assert not before["scrolls"] and len(before["places"]) >= 12, (path, before["tall"])
    top = ("var r = document.querySelectorAll(arguments[0])[0].getBoundingClientRect();"
           "return Math.round((r.top + window.scrollY) * 10) / 10")
    first_top, opened = b.js(top, rows), 0
    for i in range(int(b.js("return document.querySelectorAll(arguments[0]).length", rows))):
        b.js("var s = document.querySelectorAll(arguments[0])[arguments[1]];"
             "s.scrollIntoView({block: 'nearest'}); s.click(); return 1", rows, i)
        opened += 1
        after = _settled(b)
        if after["scrolls"]:
            break
    assert opened and after["scrolls"], \
        (path, "no row made the page scroll: the case was not reached", opened, after["tall"])
    assert after["window"] == before["window"] == 1280, (path, before["window"], after["window"])
    assert after["layout"] == before["layout"], \
        (path, f"the layout was {before['layout']} px wide and is {after['layout']} px once "
               f"the page scrolls: a scrollbar took its place from the page")
    moved = _moved(before, after)
    assert not moved, (path, f"{len(moved)} of {len(before['places'])} controls moved sideways",
                       moved[:4])
    assert len(set(before["places"]) & set(after["places"])) >= 12, \
        (path, "the controls drawn before are not the ones read after")
    assert b.js(top, rows) == first_top, (path, "the first opened row's own summary moved")
