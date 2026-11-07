"""An htmx form is never posted by the browser itself (C2217).

Measured 2026-11-03 (tests/test_evidence_pack_rebuild.py::test_build_again_in_a_real_browser,
the gate's shard browser1): Build again was pressed on a pack card htmx had swapped in but not
yet processed (htmx 2.0.11 processes swapped content in its settle task, 20 ms later), so the
browser posted the form itself and the page became the route's bare fragment, its URL the
form's action. `static/js/nmas_early.js` now stops the submit of a form carrying hx-post or
hx-get that htmx has not processed, has htmx process it, and clicks its submitter again, so
htmx sends it in place; a press before htmx has loaded is kept, busy on itself, and sent once
it has. A form with no hx-* is never touched.

Each test inserts its form with WebDriver's execute_script, never through htmx, so htmx has not
processed it by construction (htmx 2 has no observer of the page: it processes what it swaps
and what `htmx.process` is given). The route answered is the real Build again
(`v2.monitoring_alert_pack_rebuild`) on test_evidence_pack_rebuild's kept schema-4 pack.
"""

import threading

import pytest

from modules import evidence_pack as EP
# The fixtures, imported to be used by name (no linter runs here, so no noqa: C2360).
from tests.test_alert_history_packs import history
from tests.test_device_v2 import lab
from tests.test_evidence_pack import pack_lab
from tests.test_evidence_pack_rebuild import _kept_four

PAGE = "/v2/monitoring/alerts/history?range=all&show=all"
ROUTE = "v2.monitoring_alert_pack_rebuild"
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
#: How long the served app holds htmx at most when a test never releases it.
HTMX_HOLD_BOUND = 30.0
#: The form, its target and its submitter, put on the page by script (never by htmx): the
#: submitter carries a name and value, so a test can see they reached htmx's request; the page
#: is marked, so a navigation (which replaces the window) is seen; and each request htmx makes
#: for the form is recorded with the submitter's value it carried.
INSERT = """
var a = arguments[0];
var w = document.createElement('div'); w.id = 'c2217';
w.style.position = 'fixed'; w.style.top = '0'; w.style.left = '0';
w.style.zIndex = '2147483647'; w.style.background = 'white';
var f = document.createElement('form'); f.id = 'c2217-form';
for (var k in a) { f.setAttribute(k, a[k]); }
var i = document.createElement('input'); i.type = 'hidden'; i.name = 'c2217'; i.value = 'plain';
f.appendChild(i);
var b = document.createElement('button'); b.type = 'submit'; b.id = 'c2217-press';
b.name = 'pressed'; b.value = 'yes'; b.textContent = 'Press'; f.appendChild(b);
var t = document.createElement('div'); t.id = 'c2217-target';
w.appendChild(f); w.appendChild(t); document.body.appendChild(w);
window.__c2217page = 1; window.__c2217sent = [];
document.addEventListener('htmx:configRequest', function (e) {
  if (e.detail.elt === f) { window.__c2217sent.push(e.detail.formData.get('pressed')); }
});
return 1;
"""
#: This test's own elements settled: the form and its submitter no longer requesting, the target
#: no longer swapping or settling. Scoped to them, not the page (C2460, 2026-11-07): CI #1499
#: failed here with the answer drawn, sent once and the submitter no longer busy, only the
#: page-wide clause unmet; once the held htmx is released it processes the whole history page,
#: and another element's request under CI's load is not this test's subject. `_ready` keeps
#: the page-wide SETTLED, where a test starts.
OWN_SETTLED = ("!document.querySelector('#c2217-form.htmx-request, #c2217-press.htmx-request, "
               "#c2217-target.htmx-swapping, #c2217-target.htmx-settling, "
               "#c2217-target .htmx-swapping, #c2217-target .htmx-settling')")
#: The answer drawn in the target: the pack built again.
ANSWERED = ("return !!document.querySelector('#c2217-target .pack[data-pack]') && "
            + OWN_SETTLED)
#: What the page then held, for a failure: still this page, its landmark, the target, the
#: trace nmas_early.js keeps, and every element on the page still in an htmx request, swap or
#: settle (its tag, id and hx-get or hx-post), so a failure names what was still moving.
STATE = ("return {url: location.href, same_page: window.__c2217page === 1, "
         "landmark: !!document.getElementById('alert-history'), "
         "target: (document.getElementById('c2217-target') || {innerHTML: '(none)'})"
         ".innerHTML.slice(0, 160), sent: window.__c2217sent, "
         "busy: (document.getElementById('c2217-press') || {getAttribute: function () "
         "{ return '(none)'; }}).getAttribute('aria-busy'), "
         "early: (window.__nmasEarly || []).join('; '), "
         "moving: Array.prototype.map.call(document.querySelectorAll("
         "'.htmx-swapping, .htmx-settling, .htmx-request'), function (e) { return e.tagName + "
         "'#' + e.id + ' ' + (e.getAttribute('hx-get') || e.getAttribute('hx-post') || '') + "
         "' ' + e.className; })}")


def _browser_or_skip():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    return browser


def _counted(monkeypatch):
    """Each request the served app answers on Build again's route, counted: one press, one."""
    import app as A
    real, calls = A.app.view_functions[ROUTE], []

    def counted(**kw):
        calls.append(kw.get("pack_id"))
        return real(**kw)
    monkeypatch.setitem(A.app.view_functions, ROUTE, counted)
    return calls


def _hold_htmx(monkeypatch, release):
    """Hold htmx's script back until the test sets *release* (a ``threading.Event``): the press
    lands before htmx by construction, not by a race (as test_menu_clicks_and_busy holds
    Alpine). Alpine, deferred after htmx, waits with it."""
    import app as A
    real = A.app.view_functions["static"]

    def slow(**kw):
        if kw.get("filename", "").endswith("htmx.org/htmx.min.js"):
            release.wait(HTMX_HOLD_BOUND)
        return real(**kw)
    monkeypatch.setitem(A.app.view_functions, "static", slow)


def _ready(b, srv):
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
    b.go(srv.url(PAGE))
    b.wait_for("return !!window.htmx && !!window.Alpine && document.readyState === 'complete'"
               " && !!document.getElementById('alert-history') && " + SETTLED, 15)


def _answered_in_place(b, calls, old):
    try:
        b.wait_for(ANSWERED, 30)
    except AssertionError as exc:
        raise AssertionError(f"{exc}; the page then held {b.js(STATE)}") from exc
    state = b.js(STATE)
    assert state["same_page"] and state["landmark"], f"the page left for the answer: {state}"
    assert state["url"].endswith(PAGE), state
    built = b.js("return document.querySelector('#c2217-target .pack').getAttribute('data-pack')")
    assert built == f"{old['id']}-s{EP.SCHEMA}", state
    # Sent through htmx with the submitter's name and value, once.
    assert state["sent"] == ["yes"], state
    assert calls == [old["id"]], calls
    assert state["busy"] is None, f"the submitter left busy: {state}"
    assert "submit: sent through htmx" in state["early"], state


@pytest.mark.parametrize("with_action", [True, False], ids=["with-action", "no-action"])
def test_a_form_htmx_has_not_processed_is_answered_in_place(history, monkeypatch, with_action):
    """The page has loaded and every script run; a form htmx has not processed is pressed. It
    is answered in place, never by the browser leaving for the form's action (with one) or
    posting to the page's own URL (without)."""
    browser = _browser_or_skip()
    import app as A
    old, _rows = _kept_four()
    calls = _counted(monkeypatch)
    route = f"/v2/monitoring/alerts/pack/{old['id']}/rebuild"
    attrs = {"hx-post": route, "hx-target": "#c2217-target", "hx-swap": "innerHTML"}
    if with_action:
        attrs.update(method="post", action=route)
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            _ready(b, srv)
            b.js(INSERT, attrs)
            assert b.js("var d = document.getElementById('c2217-form')['htmx-internal-data'];"
                        "return !(d && d.initHash)"), "the form must be one htmx has not processed"
            b.click("#c2217-press")
            _answered_in_place(b, calls, old)
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def test_a_press_in_htmxs_settle_delay_is_answered_in_place(history, monkeypatch):
    """The measured path itself: History's row opened, its pack card swapped in by htmx, and
    Build again pressed before htmx's settle task has processed it (the delay lengthened from
    htmx's 20 ms to 3 s, so the press lands in it by construction). Answered in place."""
    browser = _browser_or_skip()
    import app as A
    old, _rows = _kept_four()
    calls = _counted(monkeypatch)
    group = ("[...document.querySelectorAll('details.ah-group')].find(g => "
             "/NMAS heartbeat missing/.test(g.querySelector('summary').textContent))")
    row = f"[...{group}.querySelectorAll('details.ah-row')].find(r => /r2/.test(r.textContent))"
    button = f"{row}.querySelector('form.pack-rebuild button')"
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            _ready(b, srv)
            b.wait_for("return (function () { var g = " + group + "; return !!(g && "
                       "[...g.querySelectorAll('details.ah-row')].find(r => /r2/.test("
                       "r.textContent))); })()", 15)
            b.js("window.__c2217page = 1; htmx.config.defaultSettleDelay = 3000; "
                 f"{group}.open = true; {row}.open = true;")
            b.wait_for(f"return !!{button}", 15)
            form_unbound = ("var d = " + button + ".form['htmx-internal-data'];"
                            "return !(d && d.initHash)")
            assert b.js(form_unbound), "the press must land before htmx has processed the card"
            b.js(f"{button}.setAttribute('id', 'c2217-press'); return 1")
            b.click("#c2217-press")
            try:
                # A page left for the bare answer has no group: false, never a script error, so
                # the failure says what the page held (CI #1327 and #1330 said only
                # "[].find(...) is undefined").
                b.wait_for(f"try {{ var p = {row}.querySelector('.pack'); return !!p && "
                           f"p.getAttribute('data-pack') === '{old['id']}-s{EP.SCHEMA}'; }} "
                           "catch (e) { return false; }", 30)
            except AssertionError as exc:
                raise AssertionError(f"{exc}; the page then held {b.js(STATE)}") from exc
            state = b.js(STATE)
            assert state["same_page"] and state["landmark"] and state["url"].endswith(PAGE), state
            assert calls == [old["id"]], calls
            assert "submit: sent through htmx" in state["early"], state
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def test_a_press_before_htmx_has_loaded_is_kept_and_sent_once_it_has(history, monkeypatch):
    """htmx held back by the served app: the press lands before it by construction. It is
    kept, its submitter busy on itself and the page left where it is; once htmx has loaded it
    is sent through htmx, answered in place, and the submitter is no longer busy."""
    browser = _browser_or_skip()
    import app as A
    old, _rows = _kept_four()
    calls = _counted(monkeypatch)
    release = threading.Event()
    _hold_htmx(monkeypatch, release)
    route = f"/v2/monitoring/alerts/pack/{old['id']}/rebuild"
    attrs = {"method": "post", "action": route, "hx-post": route,
             "hx-target": "#c2217-target", "hx-swap": "innerHTML"}
    with browser.Served(A.app) as srv, browser.Browser(page_load="none") as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url(PAGE))
            b.wait_for("return location.pathname.indexOf('/alerts/history') !== -1 && "
                       "!!document.getElementById('alert-history') && "
                       "document.readyState === 'interactive'", 15)
            b.js(INSERT, attrs)
            assert b.js("return !window.htmx"), "the press must land before htmx"
            b.click("#c2217-press")
            kept = b.js(STATE)
            assert kept["same_page"] and kept["busy"] == "true", kept
            assert "submit kept: the form not processed by htmx" in kept["early"], kept
            assert calls == [], calls
            release.set()
            _answered_in_place(b, calls, old)
        finally:
            release.set()
            b.go("about:blank")
            browser.close_socketio_sessions()


def test_a_form_with_no_htmx_is_submitted_by_the_browser_untouched(history, monkeypatch):
    """A plain form (no hx-*) is the browser's: pressed, it leaves for its action at once, and
    nmas_early.js kept nothing first. Its submit is seen by a listener after nmas_early.js's,
    which writes what had been kept into `window.name` (it survives the navigation)."""
    browser = _browser_or_skip()
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            _ready(b, srv)
            b.js("window.name = '';")
            b.js(INSERT, {"method": "get", "action": "/v2/monitoring/alerts/history"})
            b.js("window.addEventListener('submit', function () { window.name = 'c2217:' + "
                 "(window.__nmasEarly || []).filter(function (s) { return /^submit/.test(s); })"
                 ".length; }); return 1")
            b.click("#c2217-press")
            b.wait_for("return location.search.indexOf('c2217=plain') !== -1 && "
                       "!!document.getElementById('alert-history') && "
                       "window.__c2217page === undefined", 15)
            assert b.js("return window.name") == "c2217:0", b.js("return window.name")
        finally:
            b.js("window.name = ''; return 1")
            b.go("about:blank")
            browser.close_socketio_sessions()
