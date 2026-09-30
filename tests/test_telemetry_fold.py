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
        assert m["folded"]["why"] == "s1 doesn't stream model-driven telemetry; these figures come from SNMP"
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
