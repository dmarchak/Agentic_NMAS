"""DHCP's change cards survive a live redraw (PHASE8_PLAN 21, C2268; C2001's rule).

A subnet, reservation, lease or exclusion change draws its card (#dh-op: the preview, its
refusal or its result) inside `#dhcp`, which redraws on `nmas:dhcp` and could not draw the card
again: the card went with the redraw. Each card carries `data-holds-live`, so the redraw is held
with "Paused while you review this" and Show it now. On tests/test_dhcp_v2.py's world, in a
real browser.
"""

import pytest

from tests.test_dhcp_v2 import web  # noqa: F401 - the fixture

CARD = "document.getElementById('dh-op')"
REGION = "document.getElementById('dhcp')"


def test_an_open_subnet_card_survives_an_announcement(web):  # noqa: F811
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/dhcp/subnet?list=Lab&op=add"))
            b.wait_for(f"return !!window.htmx && !!{CARD} && !!{REGION}", 15)
            assert b.js(f"return {CARD}.getAttribute('data-holds-live')") == "review"
            b.js("htmx.trigger(document.body, 'nmas:dhcp'); return 1")
            b.wait_for(f"return {REGION}.getAttribute('data-held') === '1'", 10)
            kept = b.js(f"return !!{CARD}")
            said = b.js(f"return {REGION}.textContent.indexOf('Paused while you review this') >= 0")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert kept is True, "the card went with the redraw"
    assert said is True, "the region says the redraw is paused"
