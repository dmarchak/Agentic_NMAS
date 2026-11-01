"""C2267 (the item 5 audit, 2026-11-01): a live region whose redraw is answered with an error
keeps what it shows, says it could not be read, and keeps listening.

Before: an unexpected exception in a region's GET is answered with a bare notice
(`routes/v2_failure.py`), and `neverSilent` (static/js/nmas_v2.js) swaps an error answer that is
an HTML fragment, so an outerHTML region became that notice: no id, no `hx-get`, no
`hx-trigger`, never updated again, and nothing marked the page stale. Now an error answering a
LIVE redraw (an `nmas:` announcement's) is never swapped in: the region keeps its content with
"Couldn't load" above it and its listener, and the next announcement that is answered draws it
as usual. A person's own request still swaps its error answer (C2203's refusals are drawn
beside their forms).

In a real browser, on the Intent tab's Secret references card (tests/test_intent_secrets_v2.py's
world), which re-reads on `nmas:credentials`.
"""

import pytest

from tests.test_intent_editor import world  # noqa: F401 (the fixture)
from tests.test_intent_secrets_v2 import DEV, sr  # noqa: F401 (the fixture)


def test_an_errored_live_redraw_keeps_the_region_and_its_listener(sr, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    from modules.nsot import secret_refs as SR
    from routes import intent_v2
    ref = SimpleNamespace(name="lab", repo_dir=SR._repo("lab"))
    monkeypatch.setattr("routes.device_v2._device_or_404", lambda name: ((ref, DEV), None))
    from routes import v2_failure
    real = intent_v2._secrets_card
    broken = {"on": False}

    # The app's error handler's own answer to an htmx request (`v2_failure.answer`): the bare
    # notice fragment, status 500. Planted as the card's answer, since the test server may
    # answer a raised exception with its own full page instead.
    def card(ctx, code=200):
        if broken["on"]:
            return v2_failure.answer("planted: the card's read failed", 500)
        return real(ctx, code)
    monkeypatch.setattr(intent_v2, "_secrets_card", card)

    import app as A
    with browser.Served(A.app) as served, browser.Browser() as b:
        b.go(served.url("/v2/device/s4?tab=intent"))
        b.wait_for("return !!document.querySelector('#intent-secrets[hx-trigger]') && "
                   "!document.querySelector('.htmx-request')", 15)
        broken["on"] = True
        b.js("htmx.trigger(document.body, 'nmas:credentials'); return 1")
        b.wait_for("return !!document.querySelector('#intent-secrets [data-couldnt]')", 15)
        assert b.js("var r = document.querySelector('#intent-secrets');"
                    "return !!r && r.hasAttribute('hx-trigger') && "
                    "/user_lab_secret/.test(r.textContent)"), \
            "the errored redraw replaced the region or its listener"
        broken["on"] = False
        b.js("htmx.trigger(document.body, 'nmas:credentials'); return 1")
        b.wait_for("return !!document.querySelector('#intent-secrets') && "
                   "!document.querySelector('#intent-secrets [data-couldnt]') && "
                   "!document.querySelector('.htmx-request')", 15)
