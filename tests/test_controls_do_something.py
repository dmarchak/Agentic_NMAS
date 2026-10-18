"""Three defects the GUI research's inventory measured in today's pages
(docs/NSOT_GUI_RESEARCH.md Appendix A; the operator, 2026-09-29: fix them now,
whatever the layout becomes). Register C226 to C228.

* C226: a Settings control nothing read or saved (`#bgAgentEnabled`, a second
  "Background agent" switch beside the one that persists). Pinned as the CLASS:
  every control in the rendered Settings modal was referenced by the program
  that page assembled; since that modal left at 7.8 (2026-10-15), every control
  in v2's settings cards is a key its Save reads.
* C227: the device page loaded Bootstrap's CSS and bundle a second time, so
  every data-API handler was registered twice.
* C228: the empty device list said "Add one below." after Add Device was
  removed: its text must name a control the page has. Checked on v2's Devices page since
  P7-19 (2026-10-15); today's half, and C227's, left with today's pages at 7.8 (2026-10-17,
  P7-27).
"""

import os
import re

import pytest

from tests.test_device_v2 import lab  # noqa: F401 (the fixture: a list with two devices)
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


#: The settings cards' Saves: an Installation card's and a network group's (the records database
#: card and a network's inventory source have their own forms and their own tests).
_SAVES = re.compile(r'<form class="set-form"[^>]*action="/v2/settings/(?:installation/card/[^/"]+'
                    r'|network/[^/"]+/group/[^/"]+)/save".*?</form>', re.S)


def _unread(html: str, reads: set) -> tuple:
    """(controls, unread): every named input, select and textarea in the page's settings card
    forms, and those whose name the form's Save does not read."""
    names = []
    for form in _SAVES.findall(html):
        names += re.findall(r'<(?:input|select|textarea)\b[^>]*\bname="([^"]+)"', form)
    return names, sorted({n for n in names if n not in reads})


def _saves_read() -> set:
    """What the settings Saves read: each Installation card's fields (`installation_settings.
    CARDS`) and each network group's keys (`settings_scope.group_keys`), and `loaded` (R17)."""
    from modules import installation_settings as I
    from modules.settings_scope import group_keys, network_groups

    keys = {f["key"] for spec in I.CARDS.values() for f in spec["fields"]}
    keys |= {k for g in network_groups() for k in group_keys(g)}
    return keys | {"loaded"}


class TestEverySettingsControlIsRead:
    """C226, the class: a Settings control nothing read or saved. Today's Settings modal, where
    it was found, left at 7.8 (2026-10-15); its homes are v2's settings cards, each a form whose
    Save reads the card's own declared keys."""

    @pytest.fixture
    def pages(self, networks):
        out = ""
        for path in ("/v2/settings/installation", "/v2/settings/network/Default",
                     "/v2/settings/network/Default?tab=network"):
            out += networks["client"].get(path).get_data(as_text=True)
        return out

    def test_no_control_in_a_settings_card_is_read_by_nothing(self, pages):
        names, unread = _unread(pages, _saves_read())
        assert len(names) >= 30, f"the scan read the cards' controls ({len(names)})"
        assert unread == [], f"controls no Save reads: {unread}"

    def test_the_control_a_planted_unread_control_is_found(self, pages):
        # Planted in the first form the scan reads (the records card, which carries `loaded`
        # too since C813, is outside it, with its own tests).
        first = _SAVES.search(pages).group(0)
        planted = pages.replace(first, first.replace(
            '<input type="hidden" name="loaded"',
            '<input name="plantedDeadSwitch"><input type="hidden" name="loaded"', 1), 1)
        assert planted != pages
        _names, unread = _unread(planted, _saves_read())
        assert unread == ["plantedDeadSwitch"]


# TestBootstrapLoadsOnce (C227: today's base supplied Bootstrap once) and
# TestTodaysListOpensTheDevicesV2Page (today's list's Manage opened the device's v2 page) left
# with today's index, its base and the vendored Bootstrap at 7.8 (2026-10-17, P7-27): no page
# loads Bootstrap (tests/test_csp.py holds every vendored file to a page that loads it), and `/`
# answers 302 to v2 (tests/test_no_new_v1_capability.py).


class TestTheEmptyListNamesAControlThatExists:
    def test_v2_s_empty_list_says_so_and_the_page_offers_add_device(self, lab, monkeypatch):
        """C228 on v2 (P7-19, 2026-10-15): the Devices page of a network with no device says
        so, names no control, and the page's head carries the way to add one, Add device…
        (onboarding). Today's empty list, held beside it until today's index left (7.8, P7-27),
        named v2's Add device… too."""
        monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [])
        r = lab["client"].get("/v2/devices")
        html = r.get_data(as_text=True)
        assert r.status_code == 200
        notice = re.search(r'<p class="cov-head">(.*?)</p>', html, re.S)
        assert notice and "Lab has no devices yet." in notice.group(1), notice
        assert "below" not in notice.group(1) and "above" not in notice.group(1)
        assert re.search(r'<a class="btn" data-op="onboard" href="/v2/onboard/new[^"]*"[^>]*>'
                         r'Add device…</a>', html)
