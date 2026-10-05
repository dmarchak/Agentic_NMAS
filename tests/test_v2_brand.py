"""The sidebar's Mercury lockup (NSOT_STAGE7_PLAN section 19, the boards approved 2026-10-05),
and the menu buttons that showed where they do nothing (C475).

The lockup: the mark (the master geometry, its gap in the sidebar's own colour, so the orbit
crosses in front in both themes) beside the short name over the tagline, both read from
`modules.brand`, the one place the name is kept. At phone width, the mark and the short name.

C475 (the operator, 2026-10-05: "the X button next to it doesn't seem to do anything"): the rule
hiding the drawer's close button and the menu button on desktop sat ABOVE `.icon-btn`, whose
`display` won the cascade, so both always showed. On desktop the X closed a drawer that was not
open and the menu button opened one that never moved. The X is gone (the scrim closes the
drawer); the menu button is hidden on desktop and opens the drawer at phone width.
"""

import re

import pytest

from modules import brand
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_swaps_in_a_browser import READY, served  # noqa: F401


def _sidebar(html):
    return re.search(r'<nav class="sidebar".*?</nav>', html, re.S).group(0)


class TestTheLockup:
    def test_the_sidebar_draws_the_mark_and_the_name_from_one_place(self, lab):  # noqa: F811
        html = lab["client"].get("/v2/").get_data(as_text=True)
        head = _sidebar(html)[:2000]
        assert 'class="mercury-mark"' in head and f'aria-label="{brand.PRODUCT_SHORT}"' in head
        assert f'<span class="brand-name">{brand.PRODUCT_SHORT}</span>' in head
        assert f'<span class="brand-sub">{brand.PRODUCT_TAGLINE}</span>' in head
        assert "NMAS" not in head and "brand-mark" not in head

    def test_the_gap_is_the_colour_the_mark_sits_on(self):
        css = open("static/css/nmas-v2.css", encoding="utf-8").read()
        assert re.search(r"^\.mk-gap \{[^}]*stroke: var\(--side\)", css, re.M)
        assert css.count("--brand: #1D9E75;") == 3, "fixed in the light and both dark blocks"

    def test_no_close_button_on_the_drawer(self, lab):  # noqa: F811
        html = lab["client"].get("/v2/").get_data(as_text=True)
        assert "Close the menu" not in html and "drawer-close" not in html


def _shown(b, sel):
    return b.js("var e = document.querySelector(arguments[0]);"
                "return !!e && getComputedStyle(e).display !== 'none'", sel)


def test_the_menu_button_shows_only_where_it_opens_the_drawer(served):  # noqa: F811
    srv, b = served
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 800})
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    assert not _shown(b, ".menu-btn"), "on desktop the menu button opens nothing"
    assert _shown(b, ".brand-sub")
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 390, "height": 800})
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    assert _shown(b, ".menu-btn") and not _shown(b, ".brand-sub")
    b.click(".menu-btn")
    b.wait_for("return !!document.querySelector('.sidebar.open')", 5)
    b.js("document.querySelector('.scrim').click(); return 1")
    b.wait_for("return !document.querySelector('.sidebar.open')", 5)
