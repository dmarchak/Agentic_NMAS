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
        summary = _text(re.search(r'<summary class="tl-sum">(.*?)</summary>', html, re.S).group(1))
        assert "Golden recorded (capture)" in summary and "· operator@example.com" in summary
        more = _text(re.search(r'<div class="tl-more">(.*?)</div>', html, re.S).group(1))
        assert "By operator@example.com" in more

    def test_a_long_note_expands_under_its_row_and_never_widens_the_summary(self, lab, monkeypatch):
        """The operator, 2026-10-02: r1's redeploy restart carried its reason, the window's
        why, a correction and who with how identified, in a narrow left column, so its row was
        many times taller than its neighbours. ONE line per row (what, marks, short who); the
        full wording expands UNDER it at full width."""
        from modules import device_page
        long_note = "the redeploy was planned; the tool could not record a window until 30c2fd4"
        monkeypatch.setattr(device_page, "history", lambda ref, dev, limit=None: {
            "events": [{"at": "2026-10-01T16:58:00Z", "kind": "restart",
                        "what": "Restarted as planned", "marks": ["corrected"],
                        "who": "alex (host login, not a verified identity)",
                        "who_short": "alex", "correction": long_note,
                        "detail": "reason: Reload Command; planned: lab redeploy",
                        "sha": "", "outcome": "planned"}],
            "errors": [], "cut": [], "limit": 50})
        r, html = _get(lab, "/v2/device/r3/history")
        summary = _text(re.search(r'<summary class="tl-sum">(.*?)</summary>', html, re.S).group(1))
        assert summary.strip().endswith("Restarted as planned · corrected · alex"), summary
        assert long_note not in summary and "host login" not in summary
        more = _text(re.search(r'<div class="tl-more">(.*?)</div>', html, re.S).group(1))
        for words in (long_note, "By alex (host login, not a verified identity)",
                      "reason: Reload Command"):
            assert words in more

    def test_the_short_name_drops_only_how_the_person_was_identified(self):
        from modules.device_page import short_who
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
        _r, html = _get(lab, "/v2/device/r3/history")
        assert "Cut at the golden history&#39;s newest 1" in html or \
            "Cut at the golden history's newest 1" in html

    def test_nothing_recorded_says_so(self, lab):
        _r, html = _get(lab, "/v2/device/r9/history")
        assert "Nothing is recorded for r9 yet" in _text(html)


class TestTheTab:
    def test_the_tab_is_built_and_the_fragment_strict(self, lab):
        from modules import csp
        r, html = _get(lab, "/v2/device/r3?tab=history")
        assert 'hx-get="/v2/device/r3/history"' in html and 'id="history"' in html
        r, frag = _get(lab, "/v2/device/r3/history")
        assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert not re.search(r"\sstyle=|\son[a-z]+=", frag)
        assert frag.lstrip().startswith('<section class="card history" id="history"')
        keys = re.findall(r"nmas:(\w+) from:body", re.search(r'hx-trigger="([^"]*)"', frag).group(1))
        # + rotation and device_state (C359): a persist and a rotation re-read History.
        assert keys == ["goldens", "deploy_job", "restarts", "acknowledgements", "rotation",
                        "device_state"]
