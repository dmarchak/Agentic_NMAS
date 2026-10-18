"""History's Kind filter, one click away, applied before the newest-N cut (the operator's walk,
2026-10-18, B: r2's last golden, 6 days old, sat behind daily Save All rows; the device's
History tab showed the newest 30 of 162, and the golden was reached only by scrolling the fleet
History page).

On test_device_v2's lab (a real repository: r3's golden committed by `save_golden`, Source:
capture), with 55 Save All measurements of r3 committed AFTER it as Save All writes them (an
empty commit naming r3 in `Devices-Measured:`), so the golden is older than both page sizes
(the tab's 30, the History page's 50):

- without a filter neither the tab nor the page draws the golden in its first page (the defect's
  precondition);
- under `kind=golden` both draw it, and only goldens: the filter is applied by the reader before
  its newest-N cut, so a golden older than the newest page is still found;
- the filter is in the address (a GET parameter): the tab's live redraw, its link to the History
  page and its Show more keep it, and the page's network (`list=`) rides on every choice;
- the control is drawn on both, one link per choice, the chosen one pressed;
- a kind the reader does not know is IGNORED and said by name ("Not applied: the kind filter
  'bogus' is not a kind History records"), every kind drawn.
"""

import re
import time

import pytest

from tests.test_device_v2 import _get, _text, lab  # noqa: F401 (the fixture)

MEASURED = 55            # more than the History page's 50 and the tab's 30
GOLDEN = "Golden recorded (capture)"


def _git_date(offset):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset))


@pytest.fixture
def saves(lab, monkeypatch):  # noqa: F811
    """r3's golden (the lab's), then MEASURED Save All measurements of r3, each a minute
    later than the last, committed as Save All commits a save that found r3 unchanged."""
    from modules.nsot import repo as R
    for i in range(MEASURED):
        monkeypatch.setenv("GIT_COMMITTER_DATE", _git_date(60 * (i + 1)))
        rc, out, err = R.git(lab["repo"], "commit", "-q", "--allow-empty", "-m",
                             "golden: no configuration changed; decision recorded (1 device(s) "
                             "measured via save_all)\n\nSource: save_all\n"
                             "Actor: operator@example.com\nDevices-Measured: r3")
        assert rc == 0, err or out
    monkeypatch.delenv("GIT_COMMITTER_DATE")
    return lab


def _whats(html):
    """Each timeline row's What, in order (a row's own `hist-what`, never the identity line)."""
    return re.findall(r'<span class="hist-what"><strong>([^<]+)</strong>', html)


class TestTheReader:
    def test_the_golden_filter_is_applied_before_the_cut(self, saves):
        from modules import history_sources as HS
        from modules.nsot import listref
        ref = listref.resolve("Lab")
        cut = HS.timeline(ref, device="r3", limit=30)
        assert cut["total"] > 30 and not [e for e in cut["events"] if e["kind"] == "golden"]
        got = HS.timeline(ref, device="r3", kinds=["golden"], limit=30)
        assert [e["what"] for e in got["events"]] == [GOLDEN], got["events"][:3]

    def test_each_one_click_choice_is_a_kind_the_reader_filters_by(self):
        from modules import history_sources as HS
        assert [k for k, _w in HS.QUICK_KINDS][0] == "golden"
        for key, words in HS.QUICK_KINDS:
            assert HS.KIND_FILTERS[key] and words
        assert HS.KIND_FILTERS["golden"] == ("golden",)

    def test_an_unknown_kind_is_ignored_and_named(self):
        from modules import history_sources as HS
        assert HS.kind_filter(["golden", "bogus", "golden", "receipts"]) == (
            ["golden", "receipts"],
            "the kind filter 'bogus' is not a kind History records")
        assert HS.kind_filter([]) == ([], "")


class TestTheDeviceTab:
    def test_without_a_filter_the_golden_is_not_in_the_first_page(self, saves):
        _r, html = _get(saves, "/v2/device/r3/history")
        assert GOLDEN not in _whats(html)
        assert re.search(r"Showing the newest 30 of \d+", _text(html))

    @pytest.mark.parametrize("url", ["/v2/device/r3/history?kind=golden",
                                     "/v2/device/r3?tab=history&kind=golden"])
    def test_under_the_golden_filter_the_golden_is_drawn(self, saves, url):
        r, html = _get(saves, url)
        assert r.status_code == 200
        assert _whats(html) == [GOLDEN]

    def test_the_control_is_drawn_and_each_choice_links_its_address(self, saves):
        from modules import history_sources as HS
        _r, html = _get(saves, "/v2/device/r3?tab=history&kind=golden&list=Lab")
        group = re.search(r'<div class="seg hist-quick" role="group" aria-label="Kind">(.*?)</div>',
                          html, re.S)
        assert group, "the tab draws the Kind choices"
        links = re.findall(r'<a class="seg-btn( on)?" aria-pressed="(true|false)" href="([^"]+)">'
                           r'([^<]+)</a>', group.group(1))
        assert [w for _o, _p, _h, w in links] == ["All"] + [w for _k, w in HS.QUICK_KINDS]
        hrefs = {w: h.replace("&amp;", "&") for _o, _p, h, w in links}
        assert hrefs["All"] == "/v2/device/r3?tab=history&list=Lab"
        assert hrefs["Goldens"] == "/v2/device/r3?tab=history&kind=golden&list=Lab"
        pressed = [w for on, p, _h, w in links if on and p == "true"]
        assert pressed == ["Goldens"]

    def test_the_redraw_and_the_links_out_keep_the_filter(self, saves):
        _r, html = _get(saves, "/v2/device/r3/history?kind=golden&list=Lab")
        section = re.search(r'<section class="card history" id="history" hx-get="([^"]+)"', html)
        assert section.group(1).replace("&amp;", "&") == "/v2/device/r3/history?kind=golden&list=Lab"
        assert "/v2/history?device=r3&amp;since=&amp;kind=golden&amp;list=Lab" in html

    def test_a_filter_with_nothing_says_which_kind(self, lab):  # noqa: F811
        _r, html = _get(lab, "/v2/device/r3/history?kind=restarts")
        text = _text(html)
        assert "No record of the kind chosen (Restarts) for r3" in text
        assert "Nothing is recorded for r3 yet" not in text

    def test_an_unknown_kind_is_ignored_and_said_by_name(self, saves):
        _r, html = _get(saves, "/v2/device/r3/history?kind=bogus")
        assert "Not applied: the kind filter &#39;bogus&#39; is not a kind History records" in html
        assert re.search(r"Showing the newest 30 of \d+", _text(html))   # every kind drawn


class TestTheHistoryPage:
    def test_without_a_filter_the_golden_is_not_in_the_first_page(self, saves):
        _r, html = _get(saves, "/v2/history?since=")
        assert "Measured, golden unchanged (save_all)" in _whats(html)
        assert GOLDEN not in _whats(html)

    @pytest.mark.parametrize("url", ["/v2/history?since=&kind=golden",
                                     "/v2/history?since=&device=r3&kind=golden",
                                     "/v2/history/timeline?since=&kind=golden"])
    def test_under_the_golden_filter_the_golden_is_drawn(self, saves, url):
        _r, html = _get(saves, url)
        assert _whats(html) == [GOLDEN]

    def test_the_control_is_drawn_and_each_choice_keeps_the_other_filters(self, saves):
        from modules import history_sources as HS
        _r, html = _get(saves, "/v2/history?since=30&device=r3&kind=golden&list=Lab")
        group = re.search(r'<div class="seg hist-quick" role="group" aria-label="Kind">(.*?)</div>',
                          html, re.S)
        assert group, "the page draws the Kind choices"
        links = re.findall(r'<a class="seg-btn( on)?" aria-pressed="(true|false)" href="([^"]+)">'
                           r'([^<]+)</a>', group.group(1))
        assert [w for _o, _p, _h, w in links] == ["All"] + [w for _k, w in HS.QUICK_KINDS]
        hrefs = {w: h.replace("&amp;", "&") for _o, _p, h, w in links}
        assert hrefs["All"] == "/v2/history?device=r3&since=30&list=Lab"
        assert hrefs["Goldens"] == "/v2/history?device=r3&since=30&kind=golden&list=Lab"
        assert [w for on, p, _h, w in links if on and p == "true"] == ["Goldens"]
        # The full menu names the one kind chosen.
        assert 'name="kind" value="golden" checked' in html

    def test_an_unknown_kind_is_ignored_and_said_by_name(self, saves):
        _r, html = _get(saves, "/v2/history?since=&kind=bogus")
        assert "Not applied: the kind filter &#39;bogus&#39; is not a kind History records" in html
        assert "Measured, golden unchanged (save_all)" in _whats(html)   # every kind drawn
