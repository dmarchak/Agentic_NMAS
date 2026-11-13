"""Declare a fault drill… pressed in a real browser (C3405, the operator, 2026-11-13: "Required-field
errors use Mercury's inline message, not the browser's bubble"; tests/test_fault_drills.py holds
the choice, the record and the route through the test client).

What only a browser shows: pressing Declare the drill with no fault chosen sends the form (the
browser stops nothing: the form is ``novalidate``), the route refuses it, and the refusal is drawn
inline at the choice, in place of the card, naming the field; no drill is recorded. Then the same
card with a choice made declares it, drawn in place.

Each step waits on the card's own ``htmx:afterSettle`` (counted by a listener the test installs
before it presses), never on a timer.
"""

import pytest

from tests.test_fault_drills import DEV, FD, NET
from tests.test_heal_decide import lab  # noqa: F401 (the fixture, named below)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)
from tests.test_v2_busy_on_itself import _browser_or_skip  # the suite's one browser check

CARD = "#device-op"
#: Counts each settle of the card from now on (the card replaces itself: outerHTML).
LISTEN = ("window.__fd = 0;"
          "document.body.addEventListener('htmx:afterSettle', function (e) {"
          "  if ((e.target || {}).id === 'device-op') window.__fd += 1; });"
          "return true")


@pytest.fixture
def page(lab, monkeypatch):  # noqa: F811
    browser = _browser_or_skip()
    device = {"hostname": DEV, "ip": "192.0.2.6", "device_type": "cisco_xe",
              "platform": "cisco_iosxe", "username": "admin"}
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [dict(device)])
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])
    import app as A

    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url(f"/v2/device/{DEV}?op=declare_drill"))
            b.wait_for("return !!window.htmx", 15)
            b.wait_for(f"return !!document.querySelector('{CARD} select[name=kind]')", 15)
            assert b.js(LISTEN)
            yield b
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def test_declare_with_nothing_chosen_is_refused_inline_and_records_nothing(page):
    b = page
    assert b.js(f"return document.querySelector('{CARD} form').noValidate") is True
    assert b.js(f"return document.querySelector('{CARD} select[name=kind]').value") == ""
    b.click(f"{CARD} button.btn-primary")
    b.wait_for("return window.__fd >= 1", 15)
    said = b.js("var e = document.getElementById('fd-kind-err'); return e ? e.innerText : ''")
    assert said.startswith("Refused: the expected fault is one of the") and \
        "none was chosen" in said, said
    assert b.js("return document.querySelector('#fd-kind').getAttribute('aria-invalid')") == \
        "true"
    # Drawn inside the choice's own field, never a notice above the form.
    assert b.js("return document.getElementById('fd-kind-err').closest('label')"
                ".contains(document.getElementById('fd-kind'))") is True
    assert "Couldn't declare the drill" not in b.js(f"return document.querySelector("
                                                     f"'{CARD}').innerText")
    assert FD().declared(NET) == [], "the refused press recorded nothing"
    # Chosen, the same card declares it, drawn in place.
    b.js(f"var s = document.querySelector('{CARD} select[name=kind]'); s.value = 'no_fault';"
         "return true")
    b.click(f"{CARD} button.btn-primary")
    b.wait_for("return window.__fd >= 2", 15)
    said = b.js(f"return document.querySelector('{CARD} #fault-drill-result').innerText")
    assert f"Declared: a drill on {DEV} until" in said and \
        "No fault (testing the drill itself)" in said, said
    (row,) = FD().declared(NET)
    assert (row["kind"], row["expects"]) == ("no_fault", "No fault (testing the drill itself)")
