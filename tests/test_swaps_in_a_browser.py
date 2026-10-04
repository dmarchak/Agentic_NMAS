"""C409 in a real browser: a swap works every time, and a failure is drawn where it belongs.

(the operator, 2026-10-04: on Dashboards the FIRST range click worked and every later one drew
"Couldn't load: nothing on this page is #tab-body" until a reload; a single click passes, so the
tests click several in a row, and every v2 swap control twice.)

On test_device_v2's lab, this lab's real fleet dashboard set:
- Dashboards' range links clicked in a row (6h, 24h, 7d, 1h, 6h), and a device's Monitoring
  tab the same: each lands, marks its range, and leaves `#tab-body` for the next;
- every distinct GET swap control on the v2 pages (by page, path, target and swap) clicked
  twice: no "Couldn't load" and its target still there after both;
- a failure (the dashboard's answer made an error): the notice is in the region that was meant
  to update, below the range row, in a person's words ("Couldn't load the 6-hour view."), the
  technical reason on hover; the range row's layout is unchanged, measured; Try again asks
  again and, answered, clears it.
"""

import json

import pytest

from tests.test_device_v2 import lab  # noqa: F401 (the fixture)

FLEET = "rcn-lab-overview"
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
READY = "return !!window.htmx && !!window.Alpine && " + SETTLED
PAGES = ["/v2/monitoring", "/v2/monitoring/coverage", "/v2/devices", "/v2/device/r3",
         "/v2/device/r3?tab=intent", "/v2/device/r3?tab=history", "/v2/device/r3?tab=monitoring",
         "/v2/device/r3?tab=logs", "/v2/device/r3?tab=netbox", "/v2/device/r3?tab=neighbours",
         "/v2/history", "/v2/credentials"]

#: Every GET swap control on the page, one per shape: its index among `[hx-get]`, path, target
#: and swap. Distinct shapes, so a family of identical links is clicked once, not forty times.
SHAPES = """
var seen = {}, out = [];
var els = document.querySelectorAll('a[hx-get], button[hx-get]');
for (var i = 0; i < els.length; i++) {
  var e = els[i], url = e.getAttribute('hx-get') || '';
  if (url.charAt(0) !== '/') continue;
  var key = url.split('?')[0] + '|' + (e.getAttribute('hx-target') || '') + '|' +
            (e.getAttribute('hx-swap') || '');
  if (seen[key]) continue;
  seen[key] = 1;
  out.push({key: key, url: url, target: e.getAttribute('hx-target') || ''});
}
return out;
"""

#: Controls this sweep found failing for another reason, each a registered finding: its answer is
#: checked to STILL fail, so an exemption leaves the moment its finding is fixed.
#: Empty since C410 was fixed (2026-10-04): the persist preview refuses r3 by name.
KNOWN = {}

CLICK = """
var els = document.querySelectorAll('a[hx-get], button[hx-get]');
for (var i = 0; i < els.length; i++) {
  if (els[i].getAttribute('hx-get') === arguments[0]) { els[i].click(); return true; }
}
return false;
"""


def _browser_or_skip():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    return browser


@pytest.fixture
def served(lab, monkeypatch):  # noqa: F811
    browser = _browser_or_skip()
    import app as A
    lab["settings"]["grafana_fleet_dashboard_uid"] = FLEET
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            yield srv, b
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def _ranges_in_a_row(srv, b, url):
    b.go(srv.url(url))
    b.wait_for(READY, 15)
    for key in ("6h", "24h", "7d", "1h", "6h"):
        assert b.js("return !!document.getElementById('tab-body')"), f"before {key}: target gone"
        b.js("var a = Array.prototype.filter.call(document.querySelectorAll('.seg-btn'),"
             " function (x) { return x.textContent.trim() === arguments[0]; }.bind(null));"
             "return 1")
        b.js("var k = arguments[0]; var a = Array.prototype.filter.call("
             "document.querySelectorAll('.seg-btn'), function (x) {"
             " return x.textContent.trim() === k; })[0]; a.click(); return 1", key)
        b.wait_for("var k = arguments[0]; var on = document.querySelector('.seg-btn.on');"
                   f"return !!on && on.textContent.trim() === k && {SETTLED}", 15, key)
        assert not b.js("return !!document.querySelector('[data-couldnt]')"), \
            f"{key}: " + str(b.js("var n = document.querySelector('[data-couldnt] p');"
                                  "return n ? n.textContent + ' | ' + n.title : ''"))
        assert b.js("return !!document.getElementById('tab-body')"), f"after {key}: target gone"


def test_dashboards_ranges_clicked_in_a_row_each_land(served):
    srv, b = served
    _ranges_in_a_row(srv, b, "/v2/monitoring")


def test_a_device_monitoring_tabs_ranges_clicked_in_a_row_each_land(served):
    srv, b = served
    _ranges_in_a_row(srv, b, "/v2/device/r3?tab=monitoring")


def test_every_swap_control_clicked_twice_lands_both_times(served):
    srv, b = served
    failures, clicked, known_seen = [], 0, set()
    for page in PAGES:
        b.go(srv.url(page))
        b.wait_for(READY, 15)
        for shape in b.js(SHAPES):
            path = shape["url"].split("?")[0]
            if path in KNOWN:
                b.go(srv.url(page))
                b.wait_for(READY, 15)
                b.js(CLICK, shape["url"])
                b.wait_for("return " + SETTLED, 20)
                if b.js("return !!document.querySelector('[data-couldnt]')"):
                    known_seen.add(path)
                else:
                    failures.append(f"{path} answers now: remove its exemption ({KNOWN[path]})")
                continue
            b.go(srv.url(page))
            b.wait_for(READY, 15)
            for n in (1, 2):
                if not b.js(CLICK, shape["url"]):
                    break       # the first answer replaced the control: nothing to click twice
                b.wait_for("return " + SETTLED, 20)
                bad = b.js("var n = document.querySelector('[data-couldnt] p');"
                           "return n ? n.textContent + ' | ' + n.title : ''")
                target = shape["target"]
                gone = target.startswith("#") and not b.js(
                    "return !!document.querySelector(arguments[0])", target)
                if bad or gone:
                    failures.append(f"{page}: {shape['key']}, click {n}: "
                                    + (bad or f"{target} gone"))
                    break
                clicked += 1
    assert clicked >= 40, f"the population is too small to mean anything ({clicked} clicks)"
    assert known_seen == set(KNOWN), f"an exempted control was not reached: {set(KNOWN) - known_seen}"
    assert failures == [], "\n".join(failures)


def test_a_failure_is_drawn_in_its_region_and_the_row_does_not_move(served, monkeypatch):
    srv, b = served
    from flask import abort
    import app as A
    view = A.app.view_functions["v2.monitoring_dashboard"]
    broken = {"on": True}

    def maybe(*a, **k):
        if broken["on"]:
            abort(500)
        return view(*a, **k)
    monkeypatch.setitem(A.app.view_functions, "v2.monitoring_dashboard", maybe)
    b.go(srv.url("/v2/monitoring"))
    b.wait_for(READY, 15)
    row = ("var r = document.querySelector('.seg'); var b = r.getBoundingClientRect();"
           "return [b.left, b.top, b.width, b.height].concat(Array.prototype.map.call("
           "r.querySelectorAll('.seg-btn'), function (a) { return a.getBoundingClientRect().left; }))")
    before = b.js(row)
    b.js("Array.prototype.filter.call(document.querySelectorAll('.seg-btn'), function (x) {"
         " return x.textContent.trim() === '6h'; })[0].click(); return 1")
    b.wait_for("return !!document.querySelector('[data-couldnt]') && " + SETTLED, 15)
    got = b.js("var n = document.querySelector('[data-couldnt]'), p = n.querySelector('p');"
               "return {words: p.textContent, why: p.title,"
               " inRegion: !!n.closest('#tab-body'), rowAfter: !!(n.compareDocumentPosition("
               "document.querySelector('.seg')) & Node.DOCUMENT_POSITION_PRECEDING),"
               " retry: !!n.querySelector('button') && n.querySelector('button').textContent}")
    assert got["words"] == "Couldn't load the 6-hour view.", got
    assert "500" in got["why"], got
    assert got["inRegion"] and got["rowAfter"], f"in the region, below the range row: {got}"
    assert got["retry"] == "Try again", got
    after = b.js(row)
    assert after == before, f"the range row moved: {json.dumps(before)} -> {json.dumps(after)}"
    broken["on"] = False
    b.js("document.querySelector('[data-couldnt] button').click(); return 1")
    b.wait_for("var on = document.querySelector('.seg-btn.on');"
               "return !document.querySelector('[data-couldnt]') && !!on && "
               f"on.textContent.trim() === '6h' && {SETTLED}", 15)
