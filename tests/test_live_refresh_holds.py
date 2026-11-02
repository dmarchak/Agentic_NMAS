"""A live redraw keeps what a person is doing, region by region (PHASE8_PLAN 21, C2268; the
operator's brief of 2026-11-01, item 5).

The page-wide hold (static/js/nmas_v2.js `editingIn`, `releaseHeld`) skips a region's redraw
while a person works in it and redraws it once they stop. Each region below is reached with
the hold, and each is shown in a real browser: the person's state survives an announcement,
and the newer data arrives once they are done.

- **The device page's Actions menu** (the busiest, 21.3's order): its innerHTML redraw on eight
  keys closed it while open. Open, it marks itself `data-editing`; a redraw is held; closed,
  the held redraw happens.
"""

import pytest

from tests.test_device_v2 import lab  # noqa: F401 - the fixture

MENU = "document.querySelector('#actions-menu .menu-wrap')"
REGION = "document.getElementById('actions-menu')"


def test_the_spend_panel_s_re_read_on_a_call_is_held_while_a_person_types(lab):  # noqa: F811
    """The AI spend panel re-reads on each recorded call while open; its event had no `nmas:`
    prefix, so the hold never applied. A field being typed in it holds the re-read now."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    panel = "document.getElementById('nmas-ai-panel')"
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/device/r3"))
            b.wait_for(f"return !!window.htmx && !!{panel}", 15)
            b.js("document.getElementById('ai-spend').open = true; return 1")
            b.wait_for(f"return {panel}.textContent.indexOf('Reading AI spend') < 0 && "
                       "!document.querySelector('.htmx-request')", 10)
            # A person typing in it (any field the panel draws).
            b.js(f"var i = document.createElement('input'); i.type = 'text'; i.id = 'typed';"
                 f"{panel}.appendChild(i); i.focus(); i.value = 'half typed'; return 1")
            # A recorded call, as the relay fires it (htmx.trigger, which bubbles).
            b.js("htmx.trigger(document.body, 'nmas:ai_calls'); return 1")
            b.wait_for(f"return {panel}.getAttribute('data-held') === '1'", 5)
            kept = b.js("var i = document.getElementById('typed'); return i ? i.value : null")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert kept == "half typed"


def test_an_open_actions_menu_survives_a_live_redraw_and_closed_it_redraws(lab):  # noqa: F811
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/device/r3"))
            b.wait_for(f"return !!window.Alpine && !!{MENU}", 15)
            b.click("#actions-menu button[aria-haspopup=menu]")
            b.wait_for(f"return {MENU}.getAttribute('data-editing') === 'true'", 5)
            b.js("document.body.dispatchEvent(new CustomEvent('nmas:intent')); return 1")
            b.wait_for(f"return {REGION}.getAttribute('data-held') === '1'", 5)
            still_open = b.js("return document.querySelector('#actions-menu [role=menu]')"
                              ".offsetParent !== null")
            # Closed, the held redraw happens (the page's one-second tick).
            b.js(f"{MENU}.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Escape', "
                 "bubbles: true})); return 1")
            b.wait_for(f"return {REGION}.getAttribute('data-held') !== '1' && "
                       "!document.querySelector('.htmx-request')", 10)
            closed = b.js(f"return {MENU}.getAttribute('data-editing')")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert still_open is True, "the open menu was closed by the redraw"
    assert closed == "false"
