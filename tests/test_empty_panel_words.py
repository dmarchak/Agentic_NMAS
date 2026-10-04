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
    return device_page.monitoring({"hostname": "s3", "ip": "192.0.2.23"}, client=client,
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
        payload, status = device_page.panel_data({"hostname": "r2"}, "nmas-device", p["id"], "1h",
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
        (asked,) = [b for b in g.bodies if [q["refId"] for q in b["queries"]] == ["S"]]
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

    def test_the_renderer_puts_the_hover_on_the_empty_line(self):
        src = open(os.path.join(ROOT, "static", "js", "nmas_panels.js"), encoding="utf-8").read()
        assert "var hover = emptyHover(p);" in src and "if (hover) note.title = hover;" in src
