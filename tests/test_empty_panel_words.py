"""An empty panel says what it asked and that nothing matched; a fold is checked, never trusted
(C412, the operator, 2026-10-04).

The device page said "No interface counters from telemetry or SNMP" for r2's switches' panels:
an absence it never measured, where a query had matched nothing (C411's cause). Now:

- the panel payload carries the selectors the panel asked with, its variables filled for this
  device (`panels.selectors_of`), and the page draws "No series matched <selectors> in the last
  <range>.", the dashboard's own sentence on hover; a stopped stream keeps its red words;
- a panel a declared platform rule would fold is folded only once Grafana, asked now, finds no
  series under its selectors for the device in the last hour; one that matches is drawn (the
  rule wrong for it), and a Grafana that cannot be asked is said in the fold's basis.

Measured on the host before building it (2026-10-04, read-only): Prometheus holds
`cempMemPool*` series for r1, r2, r3, r4 and r6 (two each), every one a C8000V by its golden's
license line, and none for the vIOS switches the memory rule folds: the rule held then; the
check keeps it honest.

On the REAL nmas-device dashboard (`deploy/grafana/nmas-device.json`) through the same stored
model and fake Grafana as tests/test_telemetry_fold.py.
"""

import json
import os
import re

import pytest

from tests.test_telemetry_fold import _answer, _Grafana, stored  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _panel(dash, title):
    return next(p for p in dash["panels"] if p.get("title") == title)


def _frames():
    return [{"schema": {"fields": [{"name": "Time"}, {"name": "Value", "labels": {}}]},
             "data": {"values": [[1790000000000], [2.0]]}}]


class _Asked(_Grafana):
    """Grafana whose answer to the fold's series question (`S`) is *series*; the guard's two
    halves answered as test_telemetry_fold's s3 (value present, guard withholding)."""

    def __init__(self, series):
        super().__init__(_answer(True, False))
        self.series, self.bodies = series, []

    def query(self, body):
        self.bodies.append(body)
        refs = [q.get("refId") for q in body.get("queries") or []]
        if refs == ["S"]:
            if self.series is None:
                return {"ok": False, "error": "Grafana did not answer"}
            return {"ok": True, "body": {"results": {"S": {"frames": _frames() if self.series
                                                           else []}}}}
        return super().query(body)


def _s3(client):
    from modules import device_page
    return device_page.monitoring({"hostname": "s3", "ip": "192.0.2.23"}, "Default", client=client,
                                  streams=(False, "s3 doesn't stream model-driven telemetry"),
                                  model=("vios_l2", "the golden's image line"))


class TestTheSelectorsAsked:
    def test_traffic_in_asks_both_sources_for_the_device(self, stored):  # noqa: F811
        from modules import panels
        got = panels.selectors_of(_panel(stored, "Traffic in"), {"device": "r2"})
        assert any(s.startswith('ifHCInOctets{') and 'device="r2"' in s for s in got), got
        assert all("$device" not in s for s in got)
        assert len(got) == len(set(got))

    def test_memory_asks_its_two_pools(self, stored):  # noqa: F811
        from modules import panels
        got = panels.selectors_of(_panel(stored, "Memory used"), {"device": "s3"})
        assert [s.split("{")[0] for s in got] == ["cempMemPoolUsed", "cempMemPoolFree"]
        assert all('device="s3"' in s for s in got)

    def test_the_payload_carries_them(self, stored):  # noqa: F811
        from modules import device_page
        p = _panel(stored, "Traffic in")
        payload, status = device_page.panel_data({"hostname": "r2"}, "Default", "nmas-device", p["id"], "1h",
                                                 client=_Grafana())
        assert status == 200, payload
        assert payload["asked"] and any("ifHCInOctets{" in s for s in payload["asked"])


class TestAFoldIsChecked:
    def test_no_series_folds_and_its_basis_names_what_was_asked(self, stored):  # noqa: F811
        g = _Asked(series=False)
        by = {f["title"]: f for f in _s3(g)["folded"]["panels"]}
        basis = by["Memory used"]["basis"]
        assert "measured on s3" in basis
        assert "no series matched cempMemPoolUsed{" in basis and 'device="s3"' in basis
        assert basis.endswith("in the last hour")
        (asked,) = [b for b in g.bodies if [q["refId"] for q in b["queries"]] == ["S"]
                    and "cempMemPoolUsed" in b["queries"][0]["expr"]]
        expr = asked["queries"][0]["expr"]
        assert expr.startswith("count(count_over_time(cempMemPoolUsed{") and "[3600s]" in expr

    def test_a_series_found_draws_the_panel(self, stored):  # noqa: F811
        m = _s3(_Asked(series=True))
        assert "Memory used" not in {f["title"] for f in m["folded"]["panels"]}
        assert "Memory used" in [c["panel"]["title"] for c in m["layout"] if c["kind"] == "panel"]

    def test_a_grafana_that_cannot_be_asked_is_said_and_the_declared_fold_stands(
            self, stored):  # noqa: F811
        by = {f["title"]: f for f in _s3(_Asked(series=None))["folded"]["panels"]}
        assert by["Memory used"]["basis"].endswith(
            "whether a series matches could not be asked now")


class TestAKnownPlatformLimitLeadsWithItsReason:
    """C429 (the operator, 2026-10-04, s3 at 17cb78f): Memory used and Platform CPU read "No
    series matched ..." where they said the vIOS limit. s3's golden on the host names no model
    (C426), so its panels are drawn, not folded; their reason still leads."""

    @pytest.mark.parametrize("title", ["Memory used", "Platform CPU (the whole route processor)"])
    def test_an_unknown_or_matching_model_is_explained_a_known_other_is_not(self, stored, title):  # noqa: F811
        from modules import panels
        p = _panel(stored, title)
        assert panels.known_limit(p, "") is not None
        assert panels.known_limit(p, "vios_l2") is not None
        assert panels.known_limit(p, "C8000V") is None

    def test_traffic_is_no_platform_limit(self, stored):  # noqa: F811
        from modules import panels
        assert panels.known_limit(_panel(stored, "Traffic in"), "") is None

    def _page(self, stored, model):  # noqa: F811
        from flask import render_template

        import app as A
        from modules import device_page
        m = device_page.monitoring({"hostname": "s3", "ip": "192.0.2.23"}, "Default", client=_Asked(False),
                                   streams=(False, "s3 doesn't stream model-driven telemetry"),
                                   model=model)
        with A.app.test_request_context("/"):
            return m, render_template("v2/_monitoring.html", device={"hostname": "s3"}, m=m)

    def test_with_no_model_the_cells_are_marked_and_drawn(self, stored):  # noqa: F811
        m, html = self._page(stored, ("", "the golden names no model"))
        cells = {c["panel"]["title"]: c for c in m["layout"] if c["kind"] == "panel"}
        assert cells["Memory used"].get("limit") is True
        assert cells["Platform CPU (the whole route processor)"].get("limit") is True
        assert not cells["Traffic in"].get("limit")
        assert html.count('data-panel-limit="1"') == 2

    def test_a_router_is_not_excused(self, stored):  # noqa: F811
        _m, html = self._page(stored, ("C8000V", "the golden's license udi line"))
        assert 'data-panel-limit="1"' not in html


class TestTheHiddenListSaysOneSentenceEach:
    """C425 (the operator, 2026-10-04, s3's list): "Up for" showed its raw PromQL condition
    with `$device` unfilled; each telemetry entry gave two reasons for one fact."""

    def _items(self, stored):  # noqa: F811
        from flask import render_template

        import app as A
        m = _s3(_Asked(False))
        with A.app.test_request_context("/"):
            html = render_template("v2/_monitoring.html", device={"hostname": "s3"}, m=m)
        return {f["title"]: f for f in m["folded"]["panels"]}, html

    def test_up_for_shows_its_reason_and_its_condition_on_hover_filled(self, stored):  # noqa: F811
        by, html = self._items(stored)
        up = by["Up for"]
        assert up["words"].startswith("Not shown: this device's own clock runs slow")
        assert 'rate(sysUpTime{device="s3"}' in up["hover"] and "$device" not in up["hover"]
        visible = re.sub(r'title="[^"]*"', "", html)
        assert "rate(sysUpTime" not in visible and "$device" not in html

    def test_a_telemetry_entry_says_the_configurations_reason_once(self, stored):  # noqa: F811
        by, _html = self._items(stored)
        t = by["Telemetry stream"]
        assert t["words"] == "s3 doesn't stream model-driven telemetry."
        assert t["hover"].startswith("The dashboard says: No stream:")

    def test_a_platform_limit_shows_its_reason_and_its_measurement_on_hover(self, stored):  # noqa: F811
        by, html = self._items(stored)
        mem = by["Memory used"]
        assert mem["words"] == "Memory isn't available over SNMP on vIOS."
        assert "measured on s3" in mem["hover"] and "no series matched" in mem["hover"]
        visible = re.sub(r'title="[^"]*"', "", html)
        assert "measured on s3" not in visible


def _js(expr):
    import dukpy
    src = open(os.path.join(ROOT, "static", "js", "nmas_panels.js"), encoding="utf-8").read()
    return json.loads(dukpy.evaljs("var window = {};\n" + src + f"\nJSON.stringify({expr});"))


class TestTheWordsDrawn:
    P = ("{asked: ['ifHCInOctets{device=\"s1\"}', 'in_octets{device=\"s1\"}'], range: '1 h', "
         "no_value: 'No interface counters from telemetry or SNMP.'}")

    def test_the_line_is_what_was_asked_and_the_range(self):
        got = _js(f"window.NMAS_PANELS.emptyWords({self.P})")
        assert got == ('No series matched ifHCInOctets{device="s1"} or in_octets{device="s1"} '
                       'in the last 1 h.')

    def test_the_dashboards_sentence_is_on_hover(self):
        got = _js(f"window.NMAS_PANELS.emptyHover({self.P})")
        assert got == "The dashboard says: No interface counters from telemetry or SNMP."

    def test_a_stopped_stream_keeps_its_red_words(self):
        p = "{asked: ['x{device=\"r2\"}'], range: '1 h', no_value: 'No stream: r2', no_value_kind: 'danger'}"
        assert _js(f"[window.NMAS_PANELS.emptyWords({p}), window.NMAS_PANELS.emptyHover({p})]") \
            == ["No stream: r2", ""]

    def test_nothing_asked_keeps_the_panels_own_sentence(self):
        assert _js("window.NMAS_PANELS.emptyWords({range: '1 h', no_value: 'No stream.'})") \
            == "No stream."

    def test_a_known_limit_leads_with_its_reason_and_the_query_on_hover(self):
        p = ("{asked: ['cempMemPoolUsed{device=\"s3\"}'], range: '1 h', limit: true, "
             "no_value: 'Memory isn\\'t available over SNMP on vIOS.'}")
        assert _js(f"[window.NMAS_PANELS.emptyWords({p}), window.NMAS_PANELS.emptyHover({p})]") \
            == ["Memory isn't available over SNMP on vIOS.",
                'No series matched cempMemPoolUsed{device="s3"} in the last 1 h.']

    def test_the_renderer_reads_the_cells_mark(self):
        src = open(os.path.join(ROOT, "static", "js", "nmas_panels.js"), encoding="utf-8").read()
        assert "p.limit = section.getAttribute('data-panel-limit') === '1';" in src

    def test_the_renderer_puts_the_hover_on_the_empty_line(self):
        src = open(os.path.join(ROOT, "static", "js", "nmas_panels.js"), encoding="utf-8").read()
        assert "var hover = emptyHover(p);" in src and "if (hover) note.title = hover;" in src
