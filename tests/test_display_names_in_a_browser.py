"""The Display names card pressed in a real browser (board E2a; tests/test_display_names.py holds
the store, the refusals and the route through the test client).

What only a browser shows: the card draws itself into the Access and identity tab; Change…
opens the row's form in place; Save is busy on itself and its answer is drawn in the card, with
no reload; the response's `people` key reaches the name chip in the top bar, which reads again
and draws the new name; Use the default returns it; a refusal keeps what was typed in its
opened row; and the page a person sees holds no identity (the visible text, and every hover).

Each step waits on the card's own `htmx:afterSettle` (counted by a listener the test installs
before it presses), never on a timer.
"""

import pytest

from tests.conftest import TEST_PERSON
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)
from tests.test_v2_busy_on_itself import _browser_or_skip  # the suite's one browser check

PAGE = "/v2/settings/installation?tab=access"
CARD = "#card-display-names"
#: Counts each settle of the card, and of the chip, from now on.
LISTEN = ("window.__dn = {card: 0, chip: 0};"
          "document.body.addEventListener('htmx:afterSettle', function (e) {"
          "  var t = e.target || {};"
          "  if (t.id === 'card-display-names') window.__dn.card += 1;"
          "  if (t.id === 'nmas-who') window.__dn.chip += 1; });"
          "return true")
CHIP = "return document.querySelector('#nmas-who .who-name').textContent.trim()"
SEEN = ("var hovers = Array.prototype.map.call(document.querySelectorAll('[title]'),"
        " function (x) { return x.getAttribute('title'); }).join(' | ');"
        "return document.body.innerText + ' | ' + hovers")


@pytest.fixture
def page(networks):  # noqa: F811
    browser = _browser_or_skip()
    import app as A

    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url(PAGE))
            b.wait_for("return !!window.htmx", 15)
            # The card draws itself in (hx-trigger="load"): wait for its table.
            b.wait_for(f"return !!document.querySelector('{CARD} table')", 15)
            assert b.js(LISTEN)
            yield b
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def _settled(b, what, n):
    b.wait_for(f"return window.__dn.{what} >= {n}", 15)


def _open_and_type(b, name):
    b.wait_for(f"return !!document.querySelector('{CARD} details.set-replace summary')", 10)
    if not b.js(f"return document.querySelector('{CARD} details.set-replace').open"):
        b.click(f"{CARD} details.set-replace summary")
    b.wait_for(f"return document.querySelector('{CARD} details.set-replace').open", 5)
    b.js(f"var i = document.querySelector('{CARD} input[name=name]'); i.value = ''; return true")
    b.type(f"{CARD} input[name=name]", name)


def test_a_saved_name_is_drawn_in_place_and_on_the_chip_with_no_reload(page):
    b = page
    assert b.js(CHIP) == "test-person"
    assert TEST_PERSON not in b.js(SEEN), "the identity is only in the closed record"
    b.js("window.__not_reloaded = true; return true")
    _open_and_type(b, "Tess")
    b.click(f"{CARD} button.btn-primary")
    _settled(b, "card", 1)
    said = b.js(f"return document.querySelector('{CARD} .set-result').innerText")
    assert "Saved:" in said and "now shown as Tess" in said, said
    # The response named `people`: the chip read again, by itself (its own settle counted;
    # the socket's announcement of the same change may read it once more).
    _settled(b, "chip", 1)
    b.wait_for(CHIP.replace("return ", "return 'Tess' === "), 15)
    assert b.js(CHIP) == "Tess"
    assert b.js("return document.querySelector('#nmas-who .avatar').textContent.trim()") == "TE"
    assert b.js("return window.__not_reloaded === true"), "drawn in place, the page not reloaded"
    assert TEST_PERSON not in b.js(SEEN)
    # A refusal: what was typed stays in its opened row, and nothing changes.
    _open_and_type(b, "tess@home")
    b.click(f"{CARD} button.btn-primary")
    _settled(b, "card", 2)
    said = b.js(f"return document.querySelector('{CARD} .set-result').innerText")
    assert "Not saved:" in said and "contains '@'" in said, said
    assert b.js(f"return document.querySelector('{CARD} details.set-replace').open") is True
    assert b.js(f"return document.querySelector('{CARD} input[name=name]').value") == "tess@home"
    assert b.js(CHIP) == "Tess"
    # Use the default returns to the part before the "@", on the card and the chip.
    b.click(f"{CARD} button[name=use_default]")
    _settled(b, "card", 3)
    said = b.js(f"return document.querySelector('{CARD} .set-result').innerText")
    assert "now shown as test-person" in said, said
    b.wait_for(CHIP.replace("return ", "return 'test-person' === "), 15)
    assert b.js(CHIP) == "test-person"
    from modules import display_names
    assert display_names.of(TEST_PERSON) == "", "and the store holds no name for them"
