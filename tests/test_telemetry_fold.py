"""Panels fold for a device without their source (the operator, 2026-09-30),
on the REAL nmas-device dashboard through the app's own reader.

"Streams telemetry" is decided from the device's COMMITTED configuration (a
`telemetry ietf subscription`), never from whether series exist now: a router
whose stream stopped shows the failure, red, instead of hiding its panels.
The goldens are the REAL fleet configs: r2 subscribes, s1 does not.
"""

import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
DASH = os.path.join(ROOT, "deploy", "grafana", "nmas-device.json")


class _Ref:
    name = "Lab"


def _golden(host):
    return open(os.path.join(FLEET, f"{host}.cfg"), encoding="utf-8").read()


class _Resp:
    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


class _Grafana:
    """The label values for the device variable, and query answers."""

    def __init__(self, answer=None):
        self.answer = answer or {"results": {"A": {"frames": []}}}

    def _get(self, path, **params):
        return {"ok": True, "response": _Resp({"status": "success", "data": ["r2", "s1"]})}

    def query(self, body):
        return {"ok": True, "body": self.answer}


@pytest.fixture
def stored(monkeypatch):
    from modules import device_page
    from modules.readers.grafana_dashboards import _panels, _variables

    model = json.load(open(DASH, encoding="utf-8"))
    dash = {"uid": "nmas-device", "title": "NMAS device", "folder": "", "refresh": "30s",
            "variables": _variables(model), "panels": _panels(model)}
    value = {"dashboards": {"nmas-device": dash},
             "datasources": [{"uid": "prom", "type": "prometheus", "name": "P", "is_default": True},
                             {"uid": "loki", "type": "loki", "name": "L", "is_default": False}]}
    monkeypatch.setattr(device_page, "_cached", lambda reader: (value, "2026-09-30T20:00:00Z", ""))
    monkeypatch.setattr(device_page, "device_dashboard_settings",
                        lambda: {"uid": "nmas-device", "variable": "device", "value_from": "hostname"})
    return dash


def _titles(m):
    return [c["panel"]["title"] for c in m["layout"] if c["kind"] == "panel"]


class TestStreamsIsDecidedByTheConfiguration:
    def test_a_router_that_subscribes_and_a_switch_that_does_not(self, monkeypatch):
        from modules import device_page, prometheus_targets

        monkeypatch.setattr(prometheus_targets, "read_golden", lambda ref, host: _golden(host))
        assert device_page.streams_telemetry(_Ref(), {"hostname": "r2"})[0] is True
        ok, why = device_page.streams_telemetry(_Ref(), {"hostname": "s1"})
        assert ok is False and why == "s1 doesn't stream model-driven telemetry (its configuration has no subscription)"

    def test_an_unreadable_configuration_is_unknown_never_no(self, monkeypatch):
        from modules import device_page, prometheus_targets

        def boom(ref, host):
            raise OSError("git show failed")
        monkeypatch.setattr(prometheus_targets, "read_golden", boom)
        assert device_page.streams_telemetry(_Ref(), {"hostname": "r2"})[0] is None


class TestTheFold:
    def test_a_switch_folds_exactly_the_telemetry_only_panels_under_one_line(self, stored):
        from modules import device_page

        m = device_page.monitoring({"hostname": "s1", "ip": "192.0.2.21"}, client=_Grafana(),
                                   streams=(False, "s1 doesn't stream model-driven telemetry"))
        assert m["folded"]["titles"] == ["Telemetry stream", "Interface flaps"]
        assert m["folded"]["line"] == ("2 panels hidden for s1: Telemetry stream and Interface flaps "
                                       "(not streamed)")
        # The panel's own sentence, unchanged, one level down.
        (flaps,) = [f for f in m["folded"]["panels"] if f["title"] == "Interface flaps"]
        assert flaps["detail"] == "IOS-XE telemetry only: this device does not stream."
        shown = _titles(m)
        assert "Telemetry stream" not in shown and "Interface flaps" not in shown
        # Panels with an SNMP fallback stay: they draw SNMP's figures.
        assert {"Traffic in", "IOS CPU, 1-minute average", "IOS CPU over time"} <= set(shown)

    def test_a_router_that_streams_folds_nothing(self, stored):
        from modules import device_page

        m = device_page.monitoring({"hostname": "r2", "ip": "192.0.2.12"}, client=_Grafana(),
                                   streams=(True, "r2's configuration subscribes model-driven telemetry"))
        assert "folded" not in m and "Telemetry stream" in _titles(m)

    def test_unknown_folds_nothing_and_says_why(self, stored):
        from modules import device_page

        m = device_page.monitoring({"hostname": "r2", "ip": "192.0.2.12"}, client=_Grafana(),
                                   streams=(None, "r2's committed configuration could not be read (OSError)"))
        assert "folded" not in m and "could not be read" in m["streams_unknown"]
        assert "Telemetry stream" in _titles(m)

    def test_a_stopped_stream_on_a_router_that_subscribes_is_red(self, stored):
        from modules import device_page

        pid = next(p["id"] for p in stored["panels"] if p["title"] == "Telemetry stream")
        payload, code = device_page.panel_data(
            {"hostname": "r2", "ip": "192.0.2.12"}, "nmas-device", pid, "1h", client=_Grafana(),
            streams=(True, "r2's configuration subscribes model-driven telemetry"))
        assert code == 200 and payload["no_value_kind"] == "danger"
        assert payload["no_value"].startswith("No stream: r2's configuration subscribes")
        # The control: a panel WITH an SNMP fallback is never turned red.
        cpu = next(p["id"] for p in stored["panels"] if p["title"] == "IOS CPU, 1-minute average")
        payload, _ = device_page.panel_data(
            {"hostname": "r2", "ip": "192.0.2.12"}, "nmas-device", cpu, "1h", client=_Grafana(),
            streams=(True, "subscribes"))
        assert "no_value_kind" not in payload


class TestWhichPanelsAreTelemetryOnly:
    def test_from_the_real_dashboards_queries(self, stored):
        from modules import panels

        only = [p["title"] for p in stored["panels"] if p.get("type") != "row" and panels.telemetry_only(p)]
        assert only == ["Telemetry stream", "Interface flaps"]

    def test_the_shipped_renderer_draws_a_stopped_stream_as_an_error(self):
        src = open(os.path.join(ROOT, "static", "js", "nmas_panels.js"), encoding="utf-8").read()
        assert "p.no_value_kind === 'danger' ? 'panel-error' : 'panel-note'" in src


# ---------------------------------------------------------------------------
# One rule for "nothing to show here", and no hole where a panel folded
# (the operator, 2026-09-30, on s3's page after the redeploy).
# ---------------------------------------------------------------------------

def _answer(v_has, f_has):
    """Grafana's answer to a guard's two halves: `V` the value, `F` the panel's query."""
    def frames(has):
        if not has:
            return []
        return [{"schema": {"fields": [{"name": "Time"}, {"name": "Value", "labels": {"device": "s3"}}]},
                 "data": {"values": [[1790000000000], [123456.0]]}}]
    return {"results": {"V": {"frames": frames(v_has)}, "F": {"frames": frames(f_has)}}}


def _s3(stored, model=("vios_l2", "the golden's image line"), answer=None, ok=True):
    from modules import device_page

    g = _Grafana(answer if answer is not None else _answer(True, False))
    if not ok:
        g.query = lambda body: {"ok": False, "error": "Grafana did not answer"}
    return device_page.monitoring({"hostname": "s3", "ip": "192.0.2.23"}, client=g,
                                  streams=(False, "s3 doesn't stream model-driven telemetry"),
                                  model=model)


def _cells(m):
    return [c for c in m["layout"] if c["kind"] == "panel"]


class TestOneRuleForNothingToShow:
    def test_s3_folds_telemetry_memory_and_uptime_under_one_line(self, stored):
        m = _s3(stored)
        # In the dashboard's order, each reason with its panels.
        assert m["folded"]["line"] == ("4 panels hidden for s3: Memory used (not reported by vIOS), "
                                       "Up for (slow clock), Telemetry stream and Interface flaps "
                                       "(not streamed)")
        by = {f["title"]: f for f in m["folded"]["panels"]}
        # The explanations stay exactly as the dashboard writes them.
        assert by["Memory used"]["detail"] == "Memory isn't available over SNMP on vIOS."
        assert by["Up for"]["detail"].startswith("Not shown: this device's own clock runs slow")
        assert "vios_l2" in by["Memory used"]["basis"] and "measured on s3" in by["Memory used"]["basis"]
        assert {"Memory used", "Up for", "Telemetry stream"}.isdisjoint(_titles(m))

    def test_the_page_draws_one_expandable_line_with_every_explanation(self, stored, monkeypatch):
        from flask import Flask, render_template

        import app as A
        with A.app.test_request_context("/"):
            html = render_template("v2/_monitoring.html", device={"hostname": "s3"}, m=_s3(stored))
        assert html.count('id="folded-panels"') == 1 and "4 panels hidden for s3" in html
        assert "Memory isn&#39;t available over SNMP on vIOS." in html
        assert "Telemetry panels hidden" not in html


class TestShouldHaveDataNeverFolds:
    def test_a_router_that_streams_keeps_its_telemetry_panels(self, stored):
        from modules import device_page

        m = device_page.monitoring({"hostname": "r2", "ip": "192.0.2.12"},
                                   client=_Grafana(_answer(True, True)),
                                   streams=(True, "r2 subscribes"), model=("C8000V", "chassis"))
        assert "folded" not in m and {"Telemetry stream", "Memory used", "Up for"} <= set(_titles(m))

    def test_memory_folds_only_on_the_model_measured(self, stored):
        from modules import device_page

        for model in (("C8000V", "chassis"), ("", "the golden names no model")):
            m = device_page.monitoring({"hostname": "r2", "ip": "192.0.2.12"},
                                       client=_Grafana(_answer(True, True)),
                                       streams=(True, "r2 subscribes"), model=model)
            assert "Memory used" in _titles(m), model

    def test_a_guard_whose_value_is_missing_is_the_panels_to_show(self, stored):
        # No sysUpTime at all: the device should report and does not.
        assert "Up for" in _titles(_s3(stored, answer=_answer(False, False)))
        # The clock keeps time: the guarded query answers, nothing withheld.
        assert "Up for" in _titles(_s3(stored, answer=_answer(True, True)))
        # Grafana could not be asked: nothing is decided, the panel stays.
        assert "Up for" in _titles(_s3(stored, ok=False))


class TestAFoldLeavesNoHole:
    def test_the_line_that_lost_a_panel_closes_up_and_fills_its_width(self, stored):
        cells = [c for c in _cells(_s3(stored)) if (c["panel"].get("gridPos") or {}).get("y") == 5]
        assert [c["panel"]["title"] for c in cells] == ["Reboots detected", "Device clock rate",
                                                        "LLDP neighbours"]
        x = 0
        for c in cells:                        # packed left, in the dashboard's order, no gap
            assert c["x"] == x
            x += c["w"]
        assert x == 24                         # the whole width the line took

    def test_a_line_that_lost_nothing_keeps_its_exact_place(self, stored):
        from modules import device_page
        m = device_page.monitoring({"hostname": "r2", "ip": "192.0.2.12"},
                                   client=_Grafana(_answer(True, True)),
                                   streams=(True, "r2 subscribes"), model=("C8000V", "chassis"))
        for c in _cells(m):
            g = c["panel"]["gridPos"]
            assert (c["x"], c["w"]) == (g["x"], g["w"]), c["panel"]["title"]

    def test_a_row_whose_panels_all_fold_goes_with_its_heading(self, stored):
        from modules import panels
        drawn = [p for p in stored["panels"] if p.get("type") != "row"]
        row = next(p["row"] for p in drawn if p.get("row"))
        gone = [p["id"] for p in drawn if p.get("row") == row]
        out = panels.layout(drawn, gone)
        assert not any(c["kind"] == "row" and c["title"] == row for c in out)
        assert not any(c["kind"] == "panel" and c["panel"].get("row") == row for c in out)
        assert any(c["kind"] == "row" for c in out)    # the other rows keep theirs
