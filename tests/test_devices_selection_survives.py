"""C472: a person's ticks on the v2 Devices list survive another person's change.

(R27's survey, 2026-10-05: the Devices list redraws on `reachability` and `goldens`, and the
redraw read only the search and the filters, so every tick a person had made was cleared. It is
C435's case on Coverage exactly, and broadcasting every route's keys (R27) would make it happen
on every commit by anyone.)

The redraw now sends its form: the section includes `.dev-form`, and `devices_table` ticks a
row exactly when its person had it ticked. Rows start unticked, so nothing joins a selection
unseen. On test_devices_v2's inventory (r2 and r6, the lab's real shapes): the route, then a
real browser that ticks r6, fires the broadcast's events, waits for the section to be REPLACED,
and reads the boxes.
"""

import re

import pytest

from tests.test_devices_v2 import inv  # noqa: F401 (the fixture)
from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
BOXES = ("return Array.prototype.map.call(document.querySelectorAll("
         "'#devices input[name=device]'), function (x) { return [x.value, x.checked]; })")


def _ticked(html):
    return sorted(re.findall(r'name="device" value="(\w+)"[^>]*\schecked>', html))


class TestTheRedrawKeepsTheTicks:
    def test_a_redraw_ticks_exactly_what_it_was_sent(self, inv):  # noqa: F811
        html = inv["client"].get("/v2/devices/table?device=r6").get_data(as_text=True)
        assert _ticked(html) == ["r6"], _ticked(html)
        html = inv["client"].get("/v2/devices/table").get_data(as_text=True)
        assert _ticked(html) == [], "rows start unticked"

    def test_the_section_sends_its_form_when_it_redraws(self, inv):  # noqa: F811
        html = inv["client"].get("/v2/devices").get_data(as_text=True)
        section = re.search(r'<section class="card devices" id="devices"[^>]*>', html).group(0)
        assert 'hx-include="find .dev-form"' in section, section


@pytest.fixture
def served(inv, monkeypatch):  # noqa: F811
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from modules.nsot import listref
    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            yield srv, b
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def _announce_and_wait(b, key):
    b.js("document.getElementById('devices').dataset.old = '1';"
         "document.body.dispatchEvent(new CustomEvent('nmas:' + arguments[0])); return 1", key)
    b.wait_for("var c = document.getElementById('devices');"
               f"return !!c && !c.dataset.old && {SETTLED}", 15)


def test_in_a_browser_a_tick_survives_another_persons_change(served):
    srv, b = served
    b.go(srv.url("/v2/devices"))
    b.wait_for("return window.htmx && document.querySelector('#dev-r6') && " + SETTLED, 15)
    assert dict(b.js(BOXES)) == {"r2": False, "r6": False}
    b.js("document.getElementById('dev-r6').click(); return 1")
    for key in ("reachability", "goldens", "reachability"):
        _announce_and_wait(b, key)
        assert dict(b.js(BOXES)) == {"r2": False, "r6": True}, key
