"""C516 (found 2026-10-06 checking every menu and action bar for C507): the Templates table was
drawn at page load and redrawn only by its own Approve and Revoke, so an approval or a
revocation made elsewhere (another tab, today's page, a template edit that revokes) showed only
after a reload. A route's response names its keys to the tab that made it; other tabs hear the
socket.

Now every template-library commit (`repo.save_templates`, the one path approvals, revocations,
edits and bindings commit through) announces `templates`; the client relays it, and the table
(`#tpl-table`, `/v2/templates/rows`) re-reads on it, apart from the op card below it, which
keeps what a person is in the middle of.
"""

import re

import pytest

from tests.test_approvals_record import REL, lab  # noqa: F401 (the fixture)
from tests.test_templates_v2 import _ack_s1, _check, _get, _git, _hidden, tl  # noqa: F401


def _approve_elsewhere(tl):
    """Another tab approves: the acknowledgement committed, the check, the confirm."""
    _ack_s1(tl)
    _r, card = _check(tl)
    r = tl["client"].post("/v2/templates/approve", data={
        "list": "Lab", "path": REL, "fingerprint": _hidden(card, "fingerprint"),
        "seen": _hidden(card, "seen")})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]


class TestTheTableIsItsOwnFragment:

    def test_the_page_re_reads_the_table_on_templates_apart_from_the_card(self, tl):
        _r, html = _get(tl, "/v2/templates?list=Lab")
        m = re.search(r'<div id="tpl-table" ([^>]*)>', html)
        assert m, "the table has its own container"
        attrs = m.group(1)
        assert 'hx-get="/v2/templates/rows?list=Lab"' in attrs
        assert 'hx-trigger="nmas:templates from:body"' in attrs
        between = html[html.index('<div id="tpl-table"'):html.index('<div id="tpl-op"')]
        assert 'class="tpl-counts"' in between and "<table" in between, "the table inside"
        assert between.count("<div") == between.count("</div>"), (
            "the re-read container closes before the op card, so a re-read never replaces it")

    def test_rows_draws_an_approval_made_elsewhere_and_writes_nothing(self, tl):
        _r, before = _get(tl, "/v2/templates/rows?list=Lab")
        assert 'class="tpl-counts"' in before and "approved <strong>1</strong>" not in before
        _approve_elsewhere(tl)
        head = _git(tl["repo"], "rev-parse", "HEAD")
        r, after = _get(tl, "/v2/templates/rows?list=Lab")
        assert r.status_code == 200 and "approved <strong>1</strong>" in after
        assert 'id="tpl-op"' not in after, "the table alone"
        assert _git(tl["repo"], "rev-parse", "HEAD") == head, "a read commits nothing"

    def test_an_unknown_network_is_refused_naming_it(self, tl):
        r, html = _get(tl, "/v2/templates/rows?list=Nowhere")
        assert r.status_code == 404 and "Nowhere" in html and "Nothing was read" in html


class TestEveryTemplateCommitAnnounces:

    @pytest.fixture
    def heard(self, monkeypatch):
        from modules import invalidation
        got = []
        monkeypatch.setattr(invalidation, "_emitter", lambda event, msg: got.append(msg))
        return got

    def test_an_approval_announces_templates(self, tl, heard):
        _approve_elsewhere(tl)
        assert {"keys": ["templates"], "by": "template-library"}.items() <= heard[-1].items()

    def test_a_revocation_announces_templates(self, tl, heard):
        _approve_elsewhere(tl)
        heard.clear()
        tl["client"].post("/v2/templates/revoke", data={"list": "Lab", "path": REL,
                                                        "reason": "a reason in its shape"})
        assert [m["keys"] for m in heard] == [["templates"]]

    def test_a_commit_that_fails_announces_nothing(self, monkeypatch, heard):
        from modules.nsot import repo
        monkeypatch.setattr(repo, "_commit_paths", lambda *a, **k: {"ok": False, "error": "x"})
        assert repo.save_templates("Lab", [".approvals.json"])["ok"] is False
        assert heard == []

    def test_an_announcement_that_cannot_be_made_leaves_the_commit(self, monkeypatch):
        from modules import invalidation
        from modules.nsot import repo
        monkeypatch.setattr(invalidation, "_emitter", None)
        monkeypatch.setattr(repo, "_commit_paths", lambda *a, **k: {"ok": True, "commit": "c"})
        assert repo.save_templates("Lab", [".approvals.json"]) == {"ok": True, "commit": "c"}


def test_a_real_browser_redraws_the_table_and_keeps_the_open_card(tl):
    """The page open with Approve…'s check card; another tab approves; the table says it
    without a reload, and the card the person opened is still there."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from tests.test_device_seed_v2 import SETTLED
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/templates?list=Lab"))
            b.wait_for("return !!window.Alpine && window.NMAS && "
                       "NMAS.live().state === 'connected' && " + SETTLED, 15)
            b.js("window.__notReloaded = 1; return 1")
            b.click(".tpl-act a.btn-primary[data-op='approve-template']")
            b.wait_for("return !!document.querySelector('#tpl-card') && " + SETTLED, 15)
            assert "approved <strong>1</strong>" not in b.js(
                "return document.querySelector('.tpl-counts').innerHTML")
            _approve_elsewhere(tl)
            b.wait_for("return /approved <strong>1<\\/strong>/.test(document.querySelector("
                       "'.tpl-counts').innerHTML) && " + SETTLED, 15)
            assert b.js("return !!document.querySelector('#tpl-card')"), "the open card stays"
            assert b.js("return window.__notReloaded") == 1, "no reload"
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


@pytest.mark.parametrize("width", [1366, 500])
def test_the_table_s_first_column_is_inside_its_card(tl, width):
    """C502 (the operator, 2026-10-05): the Templates table's first column touched the card's
    left border. Measured as test_v2_layout_in_a_browser measures every v2 table, with the
    approve card open so its controls are measured too."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from tests.test_device_seed_v2 import SETTLED
    from tests.test_v2_layout_in_a_browser import measure_help_links, measure_layout
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": width, "height": 1000})
            b.go(srv.url(f"/v2/templates?list=Lab&approve={REL}"))
            b.wait_for("return !!document.querySelector('#tpl-card') && " + SETTLED, 15)
            problems, tables, controls = measure_layout(b, f"templates at {width}")
            problems += measure_help_links(b, f"templates at {width}")[0]
            assert not problems, "\n".join(problems)
            assert tables >= 1 and controls >= 3, (tables, controls)
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
