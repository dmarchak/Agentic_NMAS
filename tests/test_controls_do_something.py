"""Three defects the GUI research's inventory measured in today's pages
(docs/NSOT_GUI_RESEARCH.md Appendix A; the operator, 2026-09-29: fix them now,
whatever the layout becomes). Register C226 to C228.

* C226: a Settings control nothing read or saved (`#bgAgentEnabled`, a second
  "Background agent" switch beside the one that persists). Pinned as the CLASS:
  every control in the rendered Settings modal is referenced by the program
  that page assembles, beyond its own declaration.
* C227: the device page loaded Bootstrap's CSS and bundle a second time, so
  every data-API handler was registered twice.
* C228: the empty device list said "Add one below." after Add Device was
  removed: its text must name a control the page has.
"""

import os
import re

from tests.js_source import with_loaded_scripts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _index():
    import app as nmas

    return nmas.app.test_client().get("/").get_data(as_text=True)


def _settings_modal(html: str) -> str:
    """The rendered Settings modal element, bounded by balancing its divs (a
    looser bound ran on into script text and read template literals)."""
    start = html.rindex("<div", 0, html.index('id="settingsModal"'))
    depth = 0
    for m in re.finditer(r"<div\b|</div>", html[start:]):
        depth += 1 if m.group(0) == "<div" else -1
        if depth == 0:
            return html[start: start + m.end()]
    raise AssertionError("the Settings modal never closes")


def _unread(html: str) -> tuple:
    """(controls, unread): every input/select/textarea id in the Settings
    modal, and those the assembled program never names outside the tag that
    declares them."""
    modal = _settings_modal(html)
    ids = re.findall(r'<(?:input|select|textarea)\b[^>]*\bid="([^"]+)"', modal)
    program = with_loaded_scripts(html)
    unread = []
    for control in ids:
        declared = len(re.findall(rf'\bid="{re.escape(control)}"', program))
        named = len(re.findall(re.escape(control), program))
        if named <= declared:
            unread.append(control)
    return ids, unread


class TestEverySettingsControlIsRead:
    def test_no_control_in_the_settings_modal_is_read_by_nothing(self):
        """Its limit, stated: the integration cards are drawn by script from
        the schema, so their fields are not in the markup this reads (26
        controls measured, 2026-09-29)."""
        ids, unread = _unread(_index())
        assert len(ids) >= 20, f"the scan read the modal's controls ({len(ids)})"
        assert unread == [], f"controls nothing reads or saves: {unread}"

    def test_the_control_a_planted_unread_control_is_found(self):
        html = _index().replace('id="settingsModal"',
                                'id="settingsModal"><input id="plantedDeadSwitch"', 1)
        _ids, unread = _unread(html)
        assert unread == ["plantedDeadSwitch"]

    def test_the_removed_switch_is_gone_and_the_real_one_stays(self):
        html = _index()
        assert 'id="bgAgentEnabled"' not in html
        assert 'id="settingsBackgroundAgentEnabled"' in html


class TestBootstrapLoadsOnce:
    def test_the_device_page_adds_no_second_bootstrap(self):
        device = open(os.path.join(ROOT, "templates", "device.html"), encoding="utf-8").read()
        assert "bootstrap.min.css" not in device and "bootstrap.bundle" not in device
        base = open(os.path.join(ROOT, "templates", "base.html"), encoding="utf-8").read()
        assert base.count("bootstrap.bundle.min.js") == 1 and \
            base.count("bootstrap.min.css") == 1, "base.html supplies both, once"


class TestTheEmptyListNamesAControlThatExists:
    def test_it_names_onboard_a_device_and_the_page_has_it(self):
        table = open(os.path.join(ROOT, "templates", "partials", "device_table.html"),
                     encoding="utf-8").read()
        assert "Add one below" not in table
        assert '"Onboard a device" above adds one' in table
        assert re.search(r"openOnboardWizard\(\)[^<]*>\s*Onboard a device", _index()) or \
            "Onboard a device" in _index()
