"""Add device…, clicked in a real browser (the manual's rule: every screen and operation clicked
for real; cutover blocker 3): Devices opens the card in place above the list, and the address
fields follow the source chosen with no script (DHCP hides the address and mask; static hides
the MAC; ZTP shows both).
"""

from tests.test_device_v2 import lab  # noqa: F401
from tests.test_network_picker_in_a_browser import _wait
from tests.test_v2_layout_in_a_browser import served  # noqa: F401


def _shown(b, css):
    return b.js(f"var e = document.querySelector('{css}'); "
                "return !!e && e.getClientRects().length > 0;")   # drawn: a hidden parent hides it


def test_add_device_opens_in_place_and_follows_the_source(served):
    srv, b = served
    b.go(srv.url("/v2/devices"))
    _wait(b, "!!window.htmx && !!document.querySelector('a[hx-target=\"#onboard-add\"]')")
    b.js("document.querySelector('a[hx-target=\"#onboard-add\"]').click();")
    _wait(b, "!!document.querySelector('#onboard-add form.ob-form')")
    assert b.js("return location.pathname;") == "/v2/devices", "the card navigated away"
    assert _shown(b, "#f-ob-ip") and not _shown(b, "#f-ob-mac")          # static, the default
    for source, ip, mac in (("dhcp", False, True), ("ztp", True, True), ("static", True, False)):
        b.js(f"var s = document.getElementById('f-ob-source'); s.value = '{source}'; "
             "s.dispatchEvent(new Event('change', {bubbles: true}));")
        assert _shown(b, "#f-ob-ip") is ip, (source, "address")
        assert _shown(b, "#f-ob-mask") is ip, (source, "mask")
        assert _shown(b, "#f-ob-mac") is mac, (source, "MAC")
    # The review answers in place too: an empty form is refused, its reasons drawn on the card.
    b.js("document.getElementById('f-ob-hostname').removeAttribute('required');"
         "document.getElementById('f-ob-platform').removeAttribute('required');"
         "document.getElementById('f-ob-role').removeAttribute('required');"
         "document.getElementById('f-ob-domain').removeAttribute('required');"
         "document.querySelector('#onboard-add form.ob-form button[type=submit]').click();")
    _wait(b, "!document.querySelector('.htmx-request') && "
             "!!document.querySelector('#onboard-add h3, #onboard-add .notice')")
    assert b.js("return location.pathname;") == "/v2/devices"


def test_out_of_band_asks_as_the_name_is_given_and_hides_every_address_field(served):
    """Board A of docs/boards/oob-onboarding.html: Out-of-band (console) waits for a name; a
    name typed asks again (the lab's NetBox holds no console path for it, so it stays
    disabled with its reason); chosen, every address field leaves the form and the Derived
    line takes their place, by the form's own rule (no script)."""
    srv, b = served
    b.go(srv.url("/v2/devices"))
    _wait(b, "!!window.htmx && !!document.querySelector('a[hx-target=\"#onboard-add\"]')")
    b.js("document.querySelector('a[hx-target=\"#onboard-add\"]').click();")
    _wait(b, "!!document.querySelector('#onboard-add form.ob-form')")
    assert b.js("return document.querySelector('#f-ob-source option[value=ztp_console]')"
                ".disabled;") is True
    assert not _shown(b, ".ob-oob")
    # htmx binds the select's `change from:#f-ob-hostname` when it processes the swapped form;
    # a change sent before that is heard by no one (the gate's run of 2026-10-23, under load).
    _wait(b, "!!document.getElementById('f-ob-source')['htmx-internal-data'] && "
             "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')")
    b.js("var h = document.getElementById('f-ob-hostname'); h.value = 'edge9'; "
         "h.dispatchEvent(new Event('change', {bubbles: true}));")
    _wait(b, "document.getElementById('ob-oob-why').dataset.oobState !== 'unchecked'")
    why = b.js("return document.getElementById('ob-oob-why').textContent;")
    assert "Out-of-band (console) is not available" in why, why
    assert b.js("return document.querySelector('#f-ob-source option[value=ztp_console]')"
                ".disabled;") is True
    b.js("var s = document.getElementById('f-ob-source'); "
         "s.querySelector('option[value=ztp_console]').disabled = false; s.value = 'ztp_console';"
         " s.dispatchEvent(new Event('change', {bubbles: true}));")
    for css in ("#f-ob-ip", "#f-ob-mask", "#f-ob-mac", "#f-ob-intf", "#f-ob-gw", "#f-ob-router"):
        assert not _shown(b, css), css
    assert _shown(b, ".ob-oob") and _shown(b, "#f-ob-domain")
