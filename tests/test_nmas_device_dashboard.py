"""The NMAS device dashboard (`deploy/grafana/nmas-device.json`, UID
`nmas-device`), approved by the operator 2026-09-30, and the app additions it
uses. The operator's rules, each a test, through the app's OWN reader
(`readers.grafana_dashboards._panels`) and panel logic (`modules.panels`):
every panel selects the device; native types only; half and third widths on
the 24-column grid with no overlap; a unit, a meaning for every colour, a
plain title and a noValue sentence; the source named on every series.

Every query was run read-only against the real Prometheus 2.x and Loki 3.3 on
the host for r3 and s3 (2026-09-30): all 52 accepted; the telemetry halves
answered with `source` in place of `device`, as they will after the relabel.
"""

import json
import os
import subprocess
import sys

import dukpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON = os.path.join(ROOT, "deploy", "grafana", "nmas-device.json")
BUILDER = os.path.join(ROOT, "deploy", "grafana", "build_nmas_device.py")
NATIVE = {"stat", "timeseries", "table", "state-timeline", "gauge", "bargauge"}


def _doc():
    return json.load(open(JSON, encoding="utf-8"))


def _content():
    return [p for p in _doc()["panels"] if p["type"] != "row"]


class TestTheFile:
    def test_it_is_what_the_builder_produces(self):
        r = subprocess.run([sys.executable, BUILDER, "--check"], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr

    def test_its_own_uid_and_the_device_variable(self):
        d = _doc()
        assert d["uid"] == "nmas-device" and d["title"] == "NMAS device"
        assert [v["name"] for v in d["templating"]["list"]] == ["device"]
        assert {i["name"] for i in d["__inputs"]} == {"DS_PROMETHEUS", "DS_LOKI"}


class TestTheOperatorsRules:
    def test_every_panel_selects_the_device_and_the_app_draws_them_all(self):
        from modules import panels
        from modules.readers.grafana_dashboards import _panels

        trimmed = {"panels": _panels(_doc())}
        drawn, left_out = panels.split_device_panels(trimmed, "device")
        assert left_out == [], [(l["panel"]["title"], l["reason"]) for l in left_out]
        assert len(drawn) == len(_content()) >= 25
        for p in _content():
            for t in p["targets"]:
                assert panels.uses_variable(t["expr"], "device"), (p["title"], t["expr"])

    def test_only_native_panel_types(self):
        assert {p["type"] for p in _content()} <= NATIVE

    def test_the_grid_is_half_and_third_widths_with_no_overlap(self):
        cells = set()
        widths = set()
        for p in _doc()["panels"]:
            g = p["gridPos"]
            assert 0 <= g["x"] and g["x"] + g["w"] <= 24, p["title"]
            widths.add(g["w"])
            for x in range(g["x"], g["x"] + g["w"]):
                for y in range(g["y"], g["y"] + g["h"]):
                    assert (x, y) not in cells, f"{p['title']} overlaps at {x},{y}"
                    cells.add((x, y))
        assert {12, 8}.issubset(widths)                        # half and third widths

    def test_a_unit_description_and_plain_title_on_every_panel(self):
        for p in _content():
            d = p["fieldConfig"]["defaults"]
            assert d.get("unit"), p["title"]
            assert len(p.get("description") or "") > 30, p["title"]
            assert "$" not in p["title"] and "_" not in p["title"], p["title"]

    def test_every_colour_means_something(self):
        """A stat is coloured by thresholds or mappings; the one exception is
        named, with why."""
        NO_COLOUR = {"LLDP neighbours": "the right number depends on the cabling",
                     "Up for": "a duration has no good or bad value; reboots are counted beside it"}
        for p in _content():
            if p["type"] != "stat" or p["title"] in NO_COLOUR:
                continue
            d = p["fieldConfig"]["defaults"]
            assert d.get("thresholds") or d.get("mappings"), p["title"]
        assert set(NO_COLOUR) <= {p["title"] for p in _content()}

    def test_every_series_names_its_source(self):
        for p in _content():
            for t in p["targets"]:
                assert "via" in t["legendFormat"], (p["title"], t["legendFormat"])

    def test_a_panel_that_can_be_empty_says_why(self):
        ALWAYS = {"Routing neighbours in a wrong state", "Critical syslog lines, last 24 h"}  # or vector(0)
        for p in _content():
            if p["title"] in ALWAYS:
                assert "vector(0)" in p["targets"][0]["expr"]
                continue
            assert p["fieldConfig"]["defaults"].get("noValue"), p["title"]

    def test_telemetry_is_primary_where_it_measures_the_same_thing(self):
        """Traffic, errors and discards: the same counters from either
        collector, telemetry first and SNMP only for a device not streaming."""
        by = {p["title"]: p for p in _content()}
        for title in ("Traffic in", "Traffic out", "Interface errors", "Interface discards"):
            expr = by[title]["targets"][0]["expr"]
            assert '"via", "gRPC telemetry"' in expr and "unless on(device)" in expr, title

    def test_cpu_draws_both_sources_named_never_merged(self):
        """Measured 2026-09-30: about 54% over SNMP against 9% over telemetry on
        every router. Two measurements, so never `or`-ed into one."""
        by = {p["title"]: p for p in _content()}
        glance = by["CPU, 1-minute average"]["targets"]
        assert len(glance) == 1 and "gRPC" not in glance[0]["expr"]
        over_time = by["CPU over time"]["targets"]
        assert len(over_time) == 2 and all("unless" not in t["expr"] for t in over_time)
        assert {t["legendFormat"].split(" (")[0] for t in over_time} == {"device CPU", "IOS processes"}

    def test_two_way_is_never_counted_wrong(self):
        """The operator's catch: two-way (state 4) is expected between
        DROTHERs, so the wrong-state count excludes it."""
        expr = {p["title"]: p for p in _content()}["Routing neighbours in a wrong state"]["targets"][0]["expr"]
        assert "< 4" in expr and "> 4 < 8" in expr and "!= 6" in expr

    def test_the_app_lays_it_out_in_its_rows(self):
        from modules import panels
        from modules.readers.grafana_dashboards import _panels

        drawn, _ = panels.split_device_panels({"panels": _panels(_doc())}, "device")
        rows = [c["title"] for c in panels.layout(drawn) if c["kind"] == "row"]
        assert rows[:3] == ["At a glance", "Traffic (bits per second, each interface)",
                            "Errors and discards (packets per second, each interface)"]


class TestTheAppAdditions:
    def _panels_js(self, expr):
        src = open(os.path.join(ROOT, "static", "js", "nmas_panels.js"), encoding="utf-8").read()
        return json.loads(dukpy.evaljs("var window = {};\n" + src + f"\nJSON.stringify({expr});"))

    def test_no_value_is_the_panels_own_sentence(self):
        got = self._panels_js("[window.NMAS_PANELS.emptyWords({no_value: 'No stream.', range: '1 h'}),"
                              " window.NMAS_PANELS.emptyWords({range: '1 h'})]")
        assert got[0] == "No stream." and got[1].startswith("Grafana answered with no data")

    def test_durations_read_as_two_units(self):
        got = self._panels_js("[675416, 3840, 59, 0].map(function (s) { return window.NMAS_PANELS.formatValue(s, 'dtdurations'); })")
        assert got == ["7 d 19 h", "1 h 4 min", "59 s", "0 s"]

    def test_the_payload_carries_no_value_and_the_series_label(self):
        from modules import panels

        panel = {"type": "stat", "no_value": "Not a target.", "targets": [{"refId": "A", "legendFormat": "via {{via}}"}]}
        answer = {"results": {"A": {"frames": [{"schema": {"fields": [
            {"name": "Time"}, {"name": "Value", "labels": {"device": "r3", "via": "SNMP"}}]},
            "data": {"values": [[1, 2], [40, 47]]}}]}}}
        p = panels.render_payload(panel, answer, 3600)
        assert p["no_value"] == "Not a target." and p["label"] == "via SNMP" and p["value"] == 47
