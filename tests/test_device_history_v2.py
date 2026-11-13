"""The device page's History tab (NSOT_GUI_BRIEF 3.3; step 4): one timeline of
the device's golden commits, intent commits and deploy and restore receipts,
newest first, from `device_page.history()`.

On test_device_v2's lab: r3 with r2's REAL config committed as its golden by
`save_golden` (Source: capture), then an intent commit and receipts written
through the real receipt store. A record that cannot be read is said; a cut
timeline says where it was cut.
"""

import re
import time

import pytest

from tests.test_device_v2 import _get, _text, lab  # noqa: F401 (the fixture)


def _receipt(outcome="deployed", at=None, reason=""):
    from modules.nsot import receipts
    row = {"id": "r1", "at": at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 5)),
           "action": "deploy", "device": "r3", "actor": "operator@example.com",
           "outcome": outcome, "program_lines": 3, "reason": reason, "golden_commit": "abc1234def"}
    assert receipts.write("Lab", [row])["ok"]


def _intent_commit(lab):
    from modules.nsot import hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import save_host_vars
    hv = get_parser("cisco_iosxe").parse(open(_r2(), encoding="utf-8").read())
    hv["hostname"] = "r3"
    hostvars.write_committed(lab["repo"], hv)
    assert save_host_vars("Lab", ["r3"], actor="t", source="extraction")["ok"]


def _r2():
    from tests.test_intent_match import R2
    return R2


class TestTheTimeline:
    def test_the_golden_capture_is_there_with_its_workflow_and_person(self, lab):
        r, html = _get(lab, "/v2/device/r3/history")
        assert r.status_code == 200
        text = _text(html)
        assert "Golden recorded (capture)" in text
        summary = _text(re.search(r'<summary class="hist-sum">(.*?)</summary>', html, re.S).group(1))
        # Board E2a: the line names the person by display name, the part before the "@".
        assert "Golden recorded (capture)" in summary and summary.strip().endswith(" operator")
        more = _text(re.search(r'<div class="hist-detail tl-more">(.*?)</div>', html, re.S).group(1))
        # Opened, By names the person the same way; the identity the record keeps is after
        # the row's record, in the closed "The identity as recorded", kept across redraws.
        assert "By operator (not verified)" in more
        assert "The identity as recorded operator@example.com (not verified)" in more
        assert '<details class="id-record small muted" data-keep="tl-who-' in html

    def test_a_long_note_expands_under_its_row_and_never_widens_the_summary(self, lab, monkeypatch):
        """The operator, 2026-10-02: r1's redeploy restart carried its reason, the window's
        why, a correction and who with how identified, in a narrow left column, so its row was
        many times taller than its neighbours. ONE line per row (what, marks, short who); the
        full wording expands UNDER it at full width."""
        from modules import device_page
        long_note = "the redeploy was planned; the tool could not record a window until 30c2fd4"
        monkeypatch.setattr(device_page, "history", lambda ref, dev, limit=None, kinds=None, before=None: {
            "events": [{"at": "2026-10-01T16:58:00Z", "kind": "restart",
                        "what": "Restarted as planned", "marks": ["corrected"],
                        "who": "alex (host login, not a verified identity)",
                        "who_short": "alex", "correction": long_note,
                        "detail": "reason: Reload Command; planned: lab redeploy",
                        "sha": "", "outcome": "planned"}],
            "errors": [], "cut": [], "limit": 50})
        r, html = _get(lab, "/v2/device/r3/history")
        summary = _text(re.search(r'<summary class="hist-sum">(.*?)</summary>', html, re.S).group(1))
        assert summary.strip().endswith("Restarted as planned · corrected alex"), summary
        assert long_note not in summary and "host login" not in summary
        more = _text(re.search(r'<div class="hist-detail tl-more">(.*?)</div>', html, re.S).group(1))
        for words in (long_note, "By alex (host login, not a verified identity)",
                      "reason: Reload Command"):
            assert words in more

    def test_the_short_name_drops_only_how_the_person_was_identified(self):
        from modules.history_sources import short_who
        assert short_who("alex (host login, not a verified identity)") == "alex"
        assert short_who("operator@example.com") == "operator@example.com"
        assert short_who("") == ""

    def test_three_records_newest_first(self, lab):
        time.sleep(1.1)                      # the intent commit is a second later than the golden
        _intent_commit(lab)
        _receipt()
        _r, html = _get(lab, "/v2/device/r3/history")
        whats = re.findall(r"<strong>([^<]+)</strong>", html)
        # An intent line names its Source: trailer since C359 (2026-10-03).
        assert whats[:3] == ["Deployed: deployed", "Intent committed (extraction)",
                             "Golden recorded (capture)"]
        assert "3 line(s) sent" in _text(html) and "abc1234def" in html

    def test_a_failed_deploy_is_drawn_as_one(self, lab):
        _receipt(outcome="rolled_back", reason="verify failed: OSPF neighbour lost")
        _r, html = _get(lab, "/v2/device/r3/history")
        assert re.search(r'badge-danger[^>]*>[^<]*receipt', html)
        assert "Deployed: rolled back" in html and "verify failed: OSPF neighbour lost" in html

    def test_an_unreadable_record_is_said_never_a_shorter_timeline(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.receipts.read", lambda *a, **k: {
            "state": "unreadable", "rows": [], "error": "line 3 is not JSON"})
        _r, html = _get(lab, "/v2/device/r3/history")
        text = _text(html)
        assert "the deploy receipts could not be read: line 3 is not JSON" in text
        assert "not the same as nothing having happened" in text
        assert "Golden recorded (capture)" in text

    def test_a_cut_timeline_says_where(self, lab, monkeypatch):
        from modules import device_page
        monkeypatch.setattr(device_page, "HISTORY_LIMIT", 1)
        _receipt()                           # a second record beside the golden
        _r, html = _get(lab, "/v2/device/r3/history")
        # The one timeline (C369): the newest of how many, and where the rest are.
        assert re.search(r"Showing the newest 1 of \d+", html), html

    def test_nothing_recorded_says_so(self, lab):
        _r, html = _get(lab, "/v2/device/r9/history")
        assert "Nothing is recorded for r9 yet" in _text(html)


class TestTheTab:
    def test_the_tab_is_built_and_the_fragment_strict(self, lab):
        from modules import csp
        r, html = _get(lab, "/v2/device/r3?tab=history")
        assert 'hx-get="/v2/device/r3/history?list=Lab"' in html and 'id="history"' in html
        r, frag = _get(lab, "/v2/device/r3/history")
        assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert not re.search(r"\sstyle=|\son[a-z]+=", frag)
        assert frag.lstrip().startswith('<section class="card history" id="history"')
        keys = re.findall(r"nmas:(\w+) from:body", re.search(r'hx-trigger="([^"]*)"', frag).group(1))
        # + rotation and device_state (C359): a persist and a rotation re-read History; +
        # inventory: a device marked drained or cleared (modules/drained.py); + reveals: a
        # log line of the device revealed (C818); + fault_drills: a fault drill declared on
        # the device is a History row (C3142).
        assert keys == ["goldens", "deploy_job", "restarts", "fault_drills", "acknowledgements",
                        "rotation", "device_state", "inventory", "reveals"]


HEAD = re.compile(r'<div class="hist-head"[^>]*>(.*?)</div>', re.S)


def _columns(html):
    return re.findall(r"<span>([^<]*)</span>", HEAD.search(html).group(1))


class TestTheTabHasNoDeviceColumn:
    """The operator, 2026-11-13: "no Device column on a device's own History tab". Every row
    there is that device's, so the column is not drawn; the fleet's History keeps it. A row
    that is also another device's still says so, in its line.

    The one timeline macro (templates/v2/_timeline.html) drawn over the lab's own rows, as
    the reader returns them (`device_page.history`): with the device named (*here*, the tab)
    and without (the History page). In a real browser, where its cells line up under their
    headings and a pressed row opens: tests/test_v2_layout_in_a_browser.py."""

    DRAW = ('{% from "v2/_timeline.html" import timeline_rows, timeline_page %}'
            "{{ timeline_rows(h, here=here) }}|MORE|{{ timeline_page(h, here=here) }}")

    def _drawn(self, lab, here, change=None):
        import app as A
        from flask import render_template_string
        from modules import device_page
        from modules.nsot import listref

        got = device_page.history(listref.resolve("Lab"), {"hostname": "r3"})
        if change:
            change(next(e for e in got["events"] if e["kind"] == "golden"))
        with A.app.test_request_context("/v2/device/r3/history?list=Lab"):
            return render_template_string(self.DRAW, h=got, here=here).split("|MORE|")

    def test_the_tab_draws_no_device_column_and_history_keeps_it(self, lab):
        _receipt()
        tab, more = self._drawn(lab, "r3")
        assert tab.count('class="hist-sum"') >= 2, "the golden and the deploy are drawn"
        assert _columns(tab) == ["", "When", "Kind", "What", "Who"]
        assert 'class="hist-list hist-tl hist-own"' in tab and "hist-dev" not in tab
        # Each line has as many cells as its head: when, kind, what, who; Load more's rows
        # (the macro's page alone) the same.
        for line in re.findall(r'<summary class="hist-sum">(.*?)</summary>', tab + more, re.S):
            assert re.findall(r'<span class="(hist-\w+)', line) == [
                "hist-when", "hist-kind", "hist-what", "hist-who"], line
        assert more.count('class="hist-sum"') >= 2
        page, _more = self._drawn(lab, "")
        assert _columns(page) == ["", "When", "Kind", "Device", "What", "Who"]
        assert 'class="hist-list hist-tl"' in page
        devices = re.findall(r'<span class="hist-dev[^"]*">\s*([^<]*?)\s*</span>', page)
        assert set(devices) == {"r3"} and len(devices) == page.count('class="hist-sum"')

    @pytest.mark.parametrize("devices, said", [
        (["r3"], None),
        (["r3", "r9"], "with r9"),
        (["r3", "r8", "r9"], "with r8, r9"),
        (["r1", "r2", "r3", "r4", "r6", "s1", "s2", "s3", "s4"], "with 8 other devices"),
        (["*"], "every device"),
        ([], "fleet"),
    ])
    def test_a_row_that_is_not_this_devices_alone_says_so_in_its_line(self, lab, devices, said):
        """The lab's own golden row as the reader returns it, its devices changed: what the
        Device cell said beyond this device joins the line's marks; on the History page,
        which names the devices in their column, the line says nothing more."""
        from modules import history_sources

        def change(row):
            row["devices"] = list(devices)
            row["devices_words"] = history_sources.devices_words(devices)

        line = re.compile(r'data-kind="golden"[^>]*>\s*<summary class="hist-sum">(.*?)</summary>',
                          re.S)
        also = re.compile(r'<span class="tl-mark tl-also"> · ([^<]*)</span>')
        tab, _more = self._drawn(lab, "r3", change)
        assert also.findall(line.search(tab).group(1)) == ([said] if said else [])
        assert "hist-dev" not in tab
        page, _more = self._drawn(lab, "", change)
        assert also.findall(line.search(page).group(1)) == []
        assert (history_sources.devices_words(devices)
                in re.search(r'<span class="hist-dev[^"]*">\s*([^<]*?)\s*</span>',
                             line.search(page).group(1)).group(1))
