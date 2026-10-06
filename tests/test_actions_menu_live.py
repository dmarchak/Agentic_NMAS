"""C507 (the operator, 2026-10-05, the throwaway session's Part 6): after a deploy rolled back
and recorded its block, the device page's Actions menu still said "nothing to revert or retry"
until the page was reloaded, while the result card on the same page offered both. The menu was
computed at page load and never redrawn. A person must never have to reload to use an action.

On test_device_revert_retry_v2's lab (r2, its rollback record real):

- the menu is its own fragment (`GET /v2/device/<name>/actions`), and the page's container
  re-reads it on every key that changes what it offers;
- every operation that records or lifts a block, or retires the device, announces a key the
  menu listens to (read from the deploy job's and the routes' own declarations);
- the fragment offers Revert and Retry exactly while a block stands;
- in a real browser: a block recorded while the page is open, and announced, puts Revert and
  Retry in the menu without a reload.
"""

import re

import pytest

from tests.test_device_revert_retry_v2 import _get, blocked, page  # noqa: F401
from tests.test_intent_ops import _note, classify, lab  # noqa: F401


def _trigger_keys():
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "templates", "v2", "device.html"),
               encoding="utf-8").read()
    container = re.search(r'<div class="page-actions" id="actions-menu"(.*?)>', src, re.S).group(1)
    return set(re.findall(r"nmas:([a-z_]+) from:body", container))


class TestTheMenuListens:
    def test_the_container_re_reads_the_fragment(self):
        keys = _trigger_keys()
        assert {"rolled_back", "intent", "inventory", "device_holds", "deploy_job"} <= keys, keys

    def test_every_operation_that_changes_what_it_offers_is_heard(self):
        """Read from the declarations, never typed again: a deploy or restore job's end, and
        Revert, Retry, Seed and Retire's confirms."""
        from modules import deploy_job, invalidation
        keys = _trigger_keys()
        announced = {
            "deploy job": set(deploy_job.DONE_KEYS),
            "restore job": set(deploy_job.RESTORE_DONE_KEYS),
            **{route: set(invalidation.DECLARED[route]) for route in (
                "device_v2.revert_confirm", "device_v2.retry_confirm",
                "device_v2.seed_confirm", "device_v2.retire_confirm")},
        }
        deaf = {who: sorted(k) for who, k in announced.items() if not (k & keys)}
        assert not deaf, f"the menu hears none of these operations' keys: {deaf}"


class TestTheFragment:
    def test_no_block_greys_both(self, page):  # noqa: F811
        from modules import csp
        r, html = _get(page, "/v2/device/r2/actions")
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert 'role="menu"' in html and "/v2/device/r2/revert" not in html
        assert 'aria-disabled="true"' in html

    def test_a_standing_block_offers_both(self, blocked):  # noqa: F811
        _r, html = _get(blocked, "/v2/device/r2/actions")
        assert "/v2/device/r2/revert" in html and "/v2/device/r2/retry" in html


def test_a_real_browser_offers_revert_and_retry_without_a_reload(page):  # noqa: F811
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from modules import invalidation
    from tests.test_device_seed_v2 import SETTLED
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/device/r2"))
            b.wait_for("return !!window.Alpine && window.NMAS && "
                       "NMAS.live().state === 'connected' && " + SETTLED, 15)
            b.js("window.__notReloaded = 1; return 1")
            assert not b.js("return !!document.querySelector('#actions-menu a[href*=\"op=revert\"]')")
            _note(page, "blocking")                          # the rollback recorded
            invalidation.announce(("rolled_back",), by="deploy-job")
            b.wait_for("return !!document.querySelector('#actions-menu a[href*=\"op=revert\"]')"
                       " && !!document.querySelector('#actions-menu a[href*=\"op=retry\"]') && "
                       + SETTLED, 15)
            assert b.js("return window.__notReloaded") == 1, "no reload"
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
