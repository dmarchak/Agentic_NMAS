"""History's Verify and Push answer survives the header's live redraw (PHASE8_PLAN 21.2 (4),
C2268): a person's own result is drawn outside the live region.

The two buttons answered beside themselves, inside `#hist-remote`, which a push's own `remote`
announcement redraws: the answer went with it. nmas_history.js `remotePost` now writes it to
`#hist-remote-answer`, beside the header, which no redraw touches. On tests/test_history_v2.py's
world (its own lab), the remote "ahead" so both buttons are drawn; in a real browser.
"""

import time

import pytest

from tests.test_history_v2 import client, lab, repo  # noqa: F401 - the fixtures

SLOT = "document.getElementById('hist-remote-answer')"


def test_history_s_verify_answer_survives_the_header_s_redraw(client, monkeypatch):  # noqa: F811
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from modules.readers import remote_publication as P
    pub = {"state": "ahead", "ahead": 1, "remote": "example/nsot", "branch": "main",
           "head": "7a72258" + "0" * 33, "remote_head": "cf4d96d" + "0" * 33,
           "oldest_sha": "7a72258", "oldest_at": time.time() - 300, "asked_at": time.time(),
           "value_at": "2026-11-02T03:00:00Z"}
    monkeypatch.setattr(P, "status_for", lambda name: pub)
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/history"))
            b.wait_for(f"return !!window.Alpine && !!{SLOT} && "
                       "!!document.querySelector('#hist-remote [data-kind=verify] button')", 15)
            b.click("#hist-remote [data-kind=verify] button")
            b.wait_for(f"return !{SLOT}.hidden && {SLOT}.textContent.length > 0", 15)
            said = b.js(f"return {SLOT}.textContent")
            beside = b.js("return document.querySelector('#hist-remote [data-kind=verify] "
                          ".remote-said').textContent")
            # The header redrawn, as the push's own announcement does.
            b.js("htmx.trigger(document.body, 'nmas:remote'); return 1")
            b.wait_for("return !document.querySelector('.htmx-request, .htmx-settling')", 10)
            time.sleep(0.5)
            after = b.js(f"return {SLOT}.hidden ? '' : {SLOT}.textContent")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert said and after == said, (said, after)
    assert beside == "", "said once, outside the header"
