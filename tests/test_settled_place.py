"""`tests.browser.Browser.settled_place`, the one helper every test that holds a refresh keeps
the reader's place reads its place through (C3397; the operator, 2026-11-12).

On the laptop's Firefox, /v2/update's place after tests/test_live_merge.py's own steps moved by
a pixel 0.06 to 0.09 s after the scroll, with no refresh sent (1683 to 1682, 19 runs), and the
test read `before` first, so a refresh that moved nothing failed it. The helper reads the place
until two reads PLACE_STEP_S apart agree, before AND after the refresh, and a place still
moving at its bound fails the test, never passes it.

- **Settled:** the value of the first two equal reads in a row; a place that moves once and
  stops is waited for, and its last value returned.
- **Never settles:** an AssertionError naming the bound and every read; no value returned.
- **In a real browser:** a scroll that lands and is moved again 0.06 s later (the measured case)
  gives the moved place; a place kept moving fails.
"""

import pytest

from tests import browser
from tests.test_device_v2 import lab  # noqa: F401 - the fixture
from tests.test_swaps_in_a_browser import READY, served  # noqa: F401


class _Reads:
    """A browser whose place reads are *values*, in order, the last one repeated."""

    def __init__(self, values):
        self.values, self.asked = list(values), 0

    def js(self, script):
        assert script == "return window.scrollY", script
        self.asked += 1
        return self.values[min(self.asked, len(self.values)) - 1]


class _Moving:
    """A browser whose place moves by one pixel on every read."""

    def __init__(self):
        self.asked = 0

    def js(self, script):
        self.asked += 1
        return 1000 + self.asked


class TestTheHelper:
    def test_a_place_that_moves_once_is_read_where_it_stopped(self):
        b = _Reads([1683, 1682, 1682])
        assert browser.Browser.settled_place(b) == 1682
        assert b.asked == 3

    def test_a_still_place_is_read_at_the_second_equal_read(self):
        b = _Reads([773, 773])
        assert browser.Browser.settled_place(b) == 773
        assert b.asked == 2

    def test_a_place_still_moving_at_the_bound_fails_naming_every_read(self):
        b = _Moving()
        with pytest.raises(AssertionError) as caught:
            browser.Browser.settled_place(b, bound=0.3)
        words = str(caught.value)
        assert "did not settle within 0.3 s" in words, words
        assert "two equal reads 0.1 s apart" in words, words
        assert str([1000 + i for i in range(1, b.asked + 1)]) in words, words

    def test_the_bound_is_the_measured_one(self):
        # 0.091 s the slowest measured settle, the confirming read 0.1 s after it: about 2.5x.
        assert browser.PLACE_STEP_S == 0.1
        assert browser.PLACE_SETTLE_BOUND_S == 0.5


#: The page made tall enough to scroll, then scrolled to 600.
TALL = ("var s = document.createElement('div'); s.id = 'settle-spacer'; s.style.height = '4000px';"
        " document.querySelector('main').appendChild(s); window.scrollTo(0, 600); return 1")


def test_a_place_moved_again_after_the_scroll_is_read_where_it_stopped(served):  # noqa: F811
    srv, b = served
    b.go(srv.url("/v2/devices"))
    b.wait_for(READY, 20)
    b.js(TALL)
    # The measured case: the place lands, and the browser moves it again 0.06 s later.
    b.js("window.scrollTo(0, 700); setTimeout(function () { window.scrollTo(0, 701); }, 60);"
         " return 1")
    assert b.settled_place() == 701


def test_a_place_kept_moving_fails_in_a_real_browser(served):  # noqa: F811
    srv, b = served
    b.go(srv.url("/v2/devices"))
    b.wait_for(READY, 20)
    b.js(TALL)
    b.js("window.__moving = setInterval(function () { window.scrollBy(0, 1); }, 30); return 1")
    try:
        with pytest.raises(AssertionError, match="did not settle within 0.5 s"):
            b.settled_place()
    finally:
        b.js("clearInterval(window.__moving); return 1")
