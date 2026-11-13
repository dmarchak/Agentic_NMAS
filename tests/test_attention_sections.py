"""Needs attention by severity, one line each (board NA-R, PHASE8_PLAN 20.6, approved
2026-11-01; built 2026-11-02, part 1).

- **The sections:** one per severity, in order (Critical, Warning, Unknown), its count in its
  heading, Critical always open, Warning and Unknown remembered per viewer (`data-remember`);
  a severity with no item draws no section; Acknowledged its own section.
- **The line:** severity, title, age and the primary action (the row's first action: its
  first device's page, or the spend panel, or its own page), working without opening the row;
  opened, What to do (every control, Clears when, Acknowledge…) comes before the Details.
- **The summary:** counts by severity, and an operation's expected effects as one quiet link
  to its card (decision 4), never rows (`attention._expected_on_cards`).
- **In a real browser:** a Warning section the viewer closed stays closed across a redraw.
"""

import re
import time

import pytest

from modules import attention as A
from modules import restarts as R
from tests.test_attribution_b2 import b2  # noqa: F401 - the fixture
from tests.test_needs_attention import _panel

NOW = time.time()


def _src(rows=(), held=()):
    return lambda: A.source_result("drift", "Drift", read_at=NOW, took_ms=1, rows=list(rows),
                                   checked="read", held=list(held))


def _rows():
    action = {"label": "Capture it, or put it back"}
    return [A.row(source="drift", kind="drifted", key="drifted:edge1", level="danger",
                  what="edge1 has drifted from its golden", cause="differs by 3 lines",
                  action=action, devices=["edge1"], since=NOW - 360),
            A.row(source="drift", kind="skipped", key="skipped:edge2", level="warning",
                  what="edge2 was not checked for drift", cause="no golden config saved",
                  action={"label": "Capture its golden", "href": "/v2/devices"})]


def _page(monkeypatch, sources):
    monkeypatch.setattr(A, "SOURCES", tuple(sources))
    return A.needs_attention()


class TestTheSections:
    def test_one_section_per_severity_with_its_count_critical_open(self, monkeypatch):
        page = _page(monkeypatch, [_src(_rows()),
                                   lambda: A.source_result("x", "Broken", read_at=NOW,
                                                           took_ms=1, error="it raised")])
        html = _panel(page)
        heads = re.findall(r'<summary class="att-grp-sum">([^<]+)</summary>', html)
        assert heads == ["Critical · 1", "Warning · 1", "Unknown · 1"], heads
        # Critical is never remembered closed; the others are, per viewer.
        assert '<details class="att-grp att-grp-danger" data-keep="att-grp-danger" open>' in html
        assert 'data-remember="att-grp-warning" open>' in html
        assert "1 critical · 1 warning · 1 unknown" in html

    def test_a_severity_with_nothing_draws_no_section(self, monkeypatch):
        html = _panel(_page(monkeypatch, [_src(_rows()[:1])]))
        assert "Critical · 1" in html and "Warning ·" not in html and "Unknown ·" not in html


class TestTheLine:
    def test_the_line_holds_severity_title_age_and_the_primary_action(self, monkeypatch):
        html = _panel(_page(monkeypatch, [_src(_rows())]))
        line = re.search(r'data-attention-row="drift:drifted:edge1"[^>]*>\s*'
                         r'<summary class="att-line">(.*?)</summary>', html, re.S).group(1)
        assert '<span class="att-level">Critical</span>' in line
        assert 'title="edge1 has drifted from its golden"' in line
        assert 'data-age=' in line, "its age"
        assert re.search(r'href="/v2/device/edge1[^"]*">Open edge1</a>', line), line
        # A row with no device opens its own page from its line.
        assert '<a class="btn btn-small btn-outline" href="/v2/devices">Open…</a>' in html

    def test_what_to_do_comes_before_the_details(self, monkeypatch):
        # Part 2: Mercury's own finding says why from its record (no alert, so no Explain).
        # Premise corrected (the operator, 2026-11-13; the GUI review's item 1, C3449): opened,
        # a row is a summary. What is wrong (its cause, said once, written by Mercury: on its
        # hover) leads, then What to do; a finding of Mercury's own with nothing more to show
        # has no "Why this happened" block and no Details.
        html = _panel(_page(monkeypatch, [_src(_rows())]))
        body = html.split('data-attention-row="drift:drifted:edge1"')[1].split("</details>")[0]
        assert body.index('<div class="att-body">') < body.index("differs by 3 lines") \
            < body.index("<h3>What to do</h3>") < body.index("Capture it, or put it back") \
            < body.index('class="att-meta"')
        assert "<h3>Why this happened</h3>" not in body and "Details</summary>" not in body
        assert "Written by Mercury from its own record: no AI." in body
        assert body.count("differs by 3 lines") == 1, "the cause said once"
        assert "<h3>Explain</h3>" not in body


class TestTheSummary:
    def _window(self, via="reload", devices=("edge1",)):
        return {"devices": list(devices), "list": "Default", "from": R._iso(NOW - 120),
                "until": R._iso(NOW + 600), "by": "op@example.com", "why": "r",
                "via": via, "recorded_at": R._iso(NOW - 120)}

    def _held(self, w, n):
        return [{"source": "drift", "window": R.window_id(w), "devices": ["edge2"],
                 "what": f"effect {i}", "how": "unreachable", "back_by": ""} for i in range(n)]

    def test_a_reload_s_effects_are_one_link_to_its_card(self, monkeypatch):
        w = self._window()
        monkeypatch.setattr(R, "planned_rows", lambda: [w])
        page = _page(monkeypatch, [_src(held=self._held(w, 3))])
        assert page["expected"] == [{"n": 3, "device": "edge1", "words":
                                     "3 expected effects of edge1's Reload are on its card"}]
        assert page["rows"] == [], "never rows"
        html = _panel(page)
        assert re.search(r'<a href="/v2/device/edge1[^"]*">3 expected effects of edge1&#39;s '
                         r'Reload are on its card</a>', html), html

    def test_a_planned_restart_has_no_card_and_says_its_effects_are_held(self, monkeypatch):
        w = self._window(via="api", devices=("edge1", "edge2"))
        monkeypatch.setattr(R, "planned_rows", lambda: [w])
        page = _page(monkeypatch, [_src(held=self._held(w, 1))])
        assert page["expected"] == [{"n": 1, "device": "", "words": (
            "1 expected effect of a planned restart is held, said under What was checked")}]

    def test_nothing_held_says_nothing(self, monkeypatch):
        assert _page(monkeypatch, [_src(_rows())])["expected"] == []


class TestPartTwo:
    def test_an_alert_s_item_carries_its_pack_and_loads_explain_when_opened(self, b2):
        # B2's real Grafana capture with no window: its alerts are rows, each knowing the
        # evidence pack Monitoring builds for it (`evidence_pack.alert_key`).
        from tests import test_attribution_b2 as B
        b2["planned"] = []
        res = B._grafana()
        rows = [r for r in res["rows"] if r["kind"] == "incident"]
        assert rows and all(r.get("packs") for r in rows), rows
        html = _panel(A.needs_attention(sources=[lambda: res]))
        pid = rows[0]["packs"][0]
        assert pid.startswith("ep-") and f'hx-get="/v2/attention/explain/{pid}"' in html
        assert 'hx-trigger="toggle once from:closest details.att"' in html
        body = html.split(f'data-attention-row="{rows[0]["id"]}"')[1].split("</details>")[0]
        # Premise corrected (the operator, 2026-11-13; the GUI review's item 1, C3449): Explain
        # is one level down, under the row's Details, closed; an alert has no incident page.
        assert body.index('<details class="att-more"') < body.index("<summary>Details</summary>") \
            < body.index("<h3>Explain</h3>")
        assert "<h3>Why this happened</h3>" not in body, "an alert's item is explained, not"


def test_opening_an_alert_s_item_loads_its_explain_in_a_real_browser(b2, monkeypatch):
    from tests import browser
    from tests import test_attribution_b2 as B
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as nmas
    b2["planned"] = []
    monkeypatch.setattr(A, "SOURCES", (B._grafana,))
    row = "document.querySelector('details.att')"
    with browser.Served(nmas.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/"))
            b.wait_for(f"return !!window.htmx && !!{row}", 15)
            closed = b.js(f"return {row}.querySelector('.att-why').textContent")
            b.click("details.att > summary.att-line")
            b.wait_for(f"return {row}.querySelector('.att-why').textContent"
                       ".indexOf('No evidence pack is built') >= 0", 10)
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert "No evidence pack is built" not in closed, "nothing asked before it opens"


def test_a_closed_warning_section_stays_closed_across_a_redraw(monkeypatch):
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as nmas
    monkeypatch.setattr(A, "SOURCES", (_src(_rows()),))
    grp = "document.querySelector('details.att-grp-warning')"
    with browser.Served(nmas.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/"))
            b.wait_for(f"return !!window.htmx && !!{grp}", 15)
            assert b.js(f"return {grp}.open") is True
            # The viewer closes it, by pressing its heading.
            b.js(f"{grp}.querySelector('summary').click(); return 1")
            b.wait_for(f"return {grp}.open === false", 5)
            # A live redraw of the list, as any reader's announcement asks.
            b.js("htmx.ajax('GET', document.getElementById('attention').getAttribute('hx-get'),"
                 " {target: '#attention', swap: 'outerHTML'}); return 1")
            b.wait_for(f"return !!{grp} && !document.querySelector('.htmx-request')", 15)
            b.wait_for(f"return {grp}.open === false", 5)
            critical_open = b.js("return document.querySelector('details.att-grp-danger').open")
            b.go(srv.url("/v2/"))
            b.wait_for(f"return !!{grp}", 15)
            b.wait_for(f"return {grp}.open === false", 5)
        finally:
            b.js("try { localStorage.clear(); } catch (e) {} return 1")
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert critical_open is True
