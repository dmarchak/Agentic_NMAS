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

from tests.test_telemetry_fold import stored  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON = os.path.join(ROOT, "deploy", "grafana", "nmas-device.json")
BUILDER = os.path.join(ROOT, "deploy", "grafana", "build_nmas_device.py")
# The types the app draws itself: one list, the app's (modules/panels.py).
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
        assert [v["name"] for v in d["templating"]["list"]] == ["device", "syslog_job"]
        assert {i["name"] for i in d["__inputs"]} == {"DS_PROMETHEUS", "DS_LOKI"}


def _target(title):
    (t,) = next(p for p in _content() if p["title"] == title)["targets"]
    return t


class TestNoCollectorsJobIsNamed:
    """C964: the builder named the lab's syslog job and its two platform SNMP jobs, so on
    another network the syslog panels, "Answering SNMP" and the device list read nothing. The
    syslog job is now a variable Grafana reads from Loki at view time (every job by default),
    and the platform jobs are the ones holding the device's own sysUpTime, joined in the query."""

    def _variable(self, name):
        return next(v for v in _doc()["templating"]["list"] if v["name"] == name)

    def test_no_query_or_variable_names_a_job(self):
        """By the lab-specifics scan's own shape (`names_a_job`), every expression and every
        variable's question; the floor: every Loki target and the variables were read."""
        from tests.test_lab_specifics import names_a_job
        exprs = [t["expr"] for p in _content() for t in p["targets"]]
        exprs += [v["definition"] for v in _doc()["templating"]["list"]]
        assert len(exprs) >= 29
        assert [e for e in exprs if names_a_job(e)] == []

    def test_the_syslog_job_is_lokis_every_job_by_default(self):
        v = self._variable("syslog_job")
        assert v["datasource"]["type"] == "loki" and v["type"] == "query"
        assert v["query"] == v["definition"] == 'label_values({device=~".+"}, job)'
        assert v["includeAll"] is True and v["allValue"] == ".+"
        assert v["current"]["value"] == "$__all"
        loki = [p for p in _content() if p["datasource"]["type"] == "loki"]
        assert len(loki) == 2
        for p in loki:
            assert p["targets"][0]["expr"].count('{job=~"$syslog_job"} |~ `\\d+: $device: `') == 1

    def test_answering_snmp_reads_the_job_holding_the_devices_uptime(self):
        expr = _target("Answering SNMP")["expr"]
        assert expr == ('max by (device) (up{device="$device"} and on(job, device) '
                        'group by (job, device) (last_over_time(sysUpTime{device="$device"}[1d])))')

    def test_the_device_list_is_every_device_prometheus_scrapes(self):
        v = self._variable("device")
        assert v["definition"] == v["query"]["query"] == 'label_values(up{device=~".+"}, device)'

    def test_the_device_page_sends_lokis_all_value_never_an_empty_matcher(self, stored):
        """Through the app's own reader and request (`device_page.panel_data`): the variable's
        All reaches Loki as `.+`. Loki refuses a selector whose only matcher is `.*` (measured
        on the lab's Loki, 2026-10-16: "queries require at least one regexp or equality matcher
        that does not have an empty-compatible value"), which is what All was sent as."""
        from modules import device_page
        from tests.test_telemetry_fold import _Grafana

        class Asked(_Grafana):
            bodies = []

            def query(self, body):
                self.bodies.append(body)
                return super().query(body)
        g = Asked()
        pid = next(p["id"] for p in stored["panels"] if p["title"] == "Critical syslog lines, last 24 h")
        _payload, code = device_page.panel_data({"hostname": "r3", "ip": "192.0.2.13"}, "Default",
                                                "nmas-device", pid, "1h", client=g)
        assert code == 200
        (q,) = g.bodies[0]["queries"]
        assert q["expr"].startswith('sum(count_over_time({job=~".+"} |~ `\\d+: r3: `'), q["expr"]

    def test_all_is_the_declared_all_value_else_any(self):
        from modules import panels
        dash = {"variables": [
            {"name": "a", "type": "query", "current": "$__all", "all_value": ".+"},
            {"name": "b", "type": "query", "current": None, "all_value": ""},
            {"name": "c", "type": "query", "current": ["$__all"], "all_value": "x|y"},
            {"name": "d", "type": "query", "current": "one", "all_value": ".+"}]}
        assert panels.variable_values(dash, "", "") == {"a": ".+", "b": ".*", "c": "x|y", "d": "one"}


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
        from modules import panels
        assert NATIVE == panels.NATIVE_TYPES, "the app draws a different set of panel types"
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

    def test_cpu_at_a_glance_is_ios_cpu_and_the_platform_figure_is_one_level_down(self):
        """The operator's measurement on r3 (2026-09-30): IOS's own CPU 2-15%,
        the platform 40-70% with the forwarding engine busy-polling at 90%+.
        At a glance and over time: IOS CPU, telemetry on IOS-XE and SNMP's
        busy figure on vIOS, one label. The platform figure: the detail row."""
        by = {p["title"]: p for p in _content()}
        for title in ("IOS CPU, 1-minute average", "IOS CPU over time"):
            (t,) = by[title]["targets"]
            assert f"{'Cisco_IOS_XE_process_cpu_oper'}:cpu_usage_cpu_utilization_one_minute" in t["expr"]
            assert "cpuAvgBusy1" in t["expr"] and "unless on(device)" in t["expr"]
            assert "cpmCPUTotal" not in t["expr"] and t["legendFormat"] == "IOS CPU (via {{via}})"
        platform = by["Platform CPU (the whole route processor)"]
        assert "cpmCPUTotal1minRev" in platform["targets"][0]["expr"] and platform["gridPos"]["y"] >= 52
        assert "busy-polls" in platform["description"]

    def test_the_clock_rates_colours_follow_the_protocol_timers(self):
        """Red where a protocol would drop (BGP's 60/180 fails below 1/3; with
        the 1.5x margin, 0.5), amber below 0.9, so s3 at 0.58 is amber, not red
        (the operator's tiers, 2026-09-30)."""
        by = {p["title"]: p for p in _content()}
        steps = by["Device clock rate"]["fieldConfig"]["defaults"]["thresholds"]["steps"]
        assert [(s["value"], s["color"]) for s in steps] == [(None, "red"), (0.5, "orange"), (0.9, "green")]
        assert "P.7" in by["Device clock rate"]["description"]

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
