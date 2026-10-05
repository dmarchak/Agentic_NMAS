"""C435 in a real browser: a person's selection on Coverage survives another person's change.

(the register, 2026-10-04: another person's deploy finishing announces `goldens` and `intent` to
every page; Coverage's section re-renders on both and the re-render ticked every offered row,
so a person's unticks silently reverted while they chose. The operator, the same day: "confirm
in a browser, then carry the person's selection through each redraw".)

On test_coverage_deploy's lab, Coverage offers r6 (its SNMP, LLDP and IP SLA templates
missing). The test unticks it, announces the way the job's broadcast arrives (the
`nmas:<key>` event on the body), waits for the section to be REPLACED, and reads the box: it
stays unticked. After `goldens`, after `intent`, and after both in a row. And a box the person
left ticked stays ticked.
"""

import pytest

from tests.test_coverage_deploy import r6_probe_unsent  # noqa: F401 (the fixture)
from tests.test_coverage_grid import r2_snmp_down  # noqa: F401 (the fixture)
from tests.test_coverage_reporting import read  # noqa: F401 (r2_snmp_down's fixture)
from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
BOXES = ("return Array.prototype.map.call(document.querySelectorAll("
         "'#coverage input[name=device]'), function (x) { return [x.value, x.checked]; })")


@pytest.fixture
def coverage(lab, monkeypatch, r6_probe_unsent, r2_snmp_down):  # noqa: F811
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from modules.nsot import listref
    from tests.test_coverage_page import R2, R6
    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.device.load_saved_devices", lambda *a, **k: [dict(R2), dict(R6)])
    monkeypatch.setattr("modules.device_page._cached", lambda name, *_l: (r2_snmp_down, "", ""))
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            yield srv, b
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def _announce_and_wait(b, key):
    """Fire the broadcast's event and wait until #coverage was replaced and settled."""
    b.js("document.getElementById('coverage').dataset.old = '1';"
         "document.body.dispatchEvent(new CustomEvent('nmas:' + arguments[0])); return 1", key)
    b.wait_for("var c = document.getElementById('coverage');"
               f"return !!c && !c.dataset.old && {SETTLED}", 15)


def _load(srv, b):
    b.go(srv.url("/v2/monitoring/coverage"))
    b.wait_for("return window.Alpine && window.htmx && document.querySelector('#cov-r6') && "
               + SETTLED, 15)
    boxes = dict(b.js(BOXES))
    assert boxes.get("r6") is True, f"r6 is offered and starts ticked: {boxes}"
    return boxes


@pytest.mark.parametrize("keys", [("goldens",), ("intent",), ("goldens", "intent")])
def test_an_untick_survives_another_person_s_change(coverage, keys):
    srv, b = coverage
    _load(srv, b)
    b.click("#cov-r6")
    assert dict(b.js(BOXES))["r6"] is False, "the click did not untick it"
    for key in keys:
        _announce_and_wait(b, key)
    assert dict(b.js(BOXES)).get("r6") is False, (
        f"r6 was unticked, and the redraw after {' and '.join(keys)} ticked it again (C435)")


class TestTheRouteKeepsTheSelection:
    """The server's half, with no browser: the redraw's own query decides each box."""

    def _boxes(self, lab, monkeypatch, r2_snmp_down, query):  # noqa: F811
        import re

        from modules.nsot import listref
        from tests.test_coverage_page import R2, R6
        monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda *a, **k: [dict(R2), dict(R6)])
        monkeypatch.setattr("modules.device_page._cached", lambda name, *_l: (r2_snmp_down, "", ""))
        page = lab["client"].get("/v2/monitoring/coverage/table" + query).get_data(as_text=True)
        return {m.group(1): ' checked' in m.group(0) for m in re.finditer(
            r'<input type="checkbox" name="device" value="([^"]+)"[^>]*>', page)}

    def test_a_first_draw_ticks_every_offered_row(self, lab, monkeypatch, r6_probe_unsent,  # noqa: F811
                                                  r2_snmp_down):  # noqa: F811
        assert self._boxes(lab, monkeypatch, r2_snmp_down, "") == {"r6": True}

    def test_a_redraw_with_nothing_ticked_keeps_it_unticked(self, lab, monkeypatch,
                                                            r6_probe_unsent, r2_snmp_down):  # noqa: F811
        assert self._boxes(lab, monkeypatch, r2_snmp_down, "?picked=1") == {"r6": False}

    def test_a_redraw_keeps_what_was_ticked(self, lab, monkeypatch, r6_probe_unsent,  # noqa: F811
                                            r2_snmp_down):  # noqa: F811
        assert self._boxes(lab, monkeypatch, r2_snmp_down,
                           "?picked=1&device=r6") == {"r6": True}


def test_a_ticked_box_stays_ticked(coverage):
    srv, b = coverage
    _load(srv, b)
    _announce_and_wait(b, "goldens")
    assert dict(b.js(BOXES)).get("r6") is True, "the redraw unticked a box the person left ticked"
