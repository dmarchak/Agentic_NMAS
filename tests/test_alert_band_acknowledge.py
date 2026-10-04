"""A chronic alert acknowledged within its measured band (C433; the operator's decision,
2026-10-04).

s3's output discards on its manager-facing port were above the rule's 0.1 pps threshold in 64%
of 5-minute windows over 7 days, so the row was read as noise. A person may now acknowledge
such a row with a reason; the acknowledgement records the series' 7-day p95 as its band, and
the row stays away only while the value is inside it. Above it, or unread, the row is shown,
naming the band and the value.

Against the real capture (tests/fixtures/grafana/, 2026-09-28): its own "Interface output
discards" rule, PromQL `max by (instance, ifDescr) (rate(ifOutDiscards{...}[5m])) > 0.1` on
the Prometheus datasource, and its own s3 Gi1/1 instance set Alerting (the one edit). Prometheus
is a fake answering the two queries the band and the reading make.
"""

import json
from types import SimpleNamespace

import pytest

from modules import alert_bands as B
from modules import attention as A
from modules import config
from tests.test_grafana_reader import READ_AT, cached, inventory, load, rule  # noqa: F401

PROM = {"efwpn8hr7sfeob"}       # the capture's Prometheus datasource
TITLE = "Interface output discards"


class _Prom:
    """Prometheus answering the band (a quantile) and the reading (the plain query)."""

    def __init__(self, p95=3.7, now=0.8):
        self.p95, self.now, self.asked = p95, now, []

    def is_configured(self):
        return True

    def _get(self, path, **params):
        q = params["query"]
        self.asked.append(q)
        value = self.p95 if q.startswith("quantile_over_time(0.95, (") else self.now
        series = {"instance": "10.255.1.23", "ifDescr": "GigabitEthernet1/1"}
        body = {"data": {"result": [{"metric": series, "value": [READ_AT, str(value)]},
                                    {"metric": {**series, "ifDescr": "Gi0/2"},
                                     "value": [READ_AT, "99"]}]}}
        return {"ok": True, "response": SimpleNamespace(json=lambda: body)}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))


def _firing(active_at="2026-09-28T20:20:00Z"):
    """Edit: the capture's own discards instance on s3 Gi1/1 set Alerting."""
    from modules.readers import grafana_alerts as G

    view = load("rules_view")
    inst = rule(view, TITLE)["alerts"][0]
    inst["state"], inst["activeAt"] = "Alerting", active_at
    return G.parse(load("ruler"), view, [], READ_AT, prom_uids=PROM)


_SOURCE = A.grafana_source          # the real one, whatever a test patches


def _rows(value):
    return _SOURCE(cached=cached(value))["rows"]


class TestTheValue:
    def test_the_threshold_comes_off_and_only_a_prometheus_query_is_banded(self):
        assert B.value_expr('max by (instance, ifDescr) (rate(ifOutDiscards{job=~"x"}[5m])) '
                            '> 0.1') == ('max by (instance, ifDescr) '
                                         '(rate(ifOutDiscards{job=~"x"}[5m]))')
        assert B.value_expr("up == 0") == "up" and B.value_expr("rate(x[5m])") == ""
        rules = {r["title"]: r for r in _firing()["rules"]}
        assert rules[TITLE]["value_expr"].startswith("max by (instance, ifDescr) (rate(")
        assert all(not r["value_expr"] for t, r in rules.items()
                   if t.startswith("NMAS heartbeat")), "a Loki rule was banded"


class TestTheRow:
    def test_one_series_is_one_row_keyed_on_the_series_never_its_onset(self, inventory):
        (a,) = _rows(_firing("2026-09-28T20:20:00Z"))
        (b,) = _rows(_firing("2026-09-28T20:24:00Z"))         # re-fired: a later onset
        assert a["kind"] == "series" and a["acknowledge"] is True and a["id"] == b["id"]
        assert a["event"] == b["event"] == B.series_key(a["event"].split("|")[0],
                                                        a["operands"]["labels"])
        assert "acknowledge it within its measured band" in a["action"]["label"]


class TestAcknowledgingWithinTheBand:
    def _acknowledge(self, monkeypatch, value, prom):
        monkeypatch.setattr("modules.integrations.prometheus.PrometheusIntegration",
                            lambda: prom)
        rows = _rows(value)
        monkeypatch.setattr(A, "grafana_source", lambda cached=None: {"rows": rows})
        (r,) = rows
        return A.acknowledge(r["id"], r["event"], "chronic on the manager port, cause C93",
                             by="operator@example.invalid", verified="test"), r

    def test_the_band_and_the_value_are_measured_and_recorded(self, store, inventory,
                                                              monkeypatch):
        prom = _Prom(p95=3.7, now=0.8)
        out, r = self._acknowledge(monkeypatch, _firing(), prom)
        assert out["ok"] is True, out
        assert out["acknowledged"]["band"] == 3.7 and out["acknowledged"]["value"] == 0.8
        assert prom.asked[0].startswith("quantile_over_time(0.95, (max by (instance, ifDescr)")
        assert prom.asked[0].endswith(")[7d:5m])")

    def test_inside_its_band_the_row_leaves_and_says_why(self, store, inventory, monkeypatch):
        value = _firing()
        self._acknowledge(monkeypatch, value, _Prom(p95=3.7, now=0.8))
        rows, gone, _p = A._without_acknowledged(_rows(value))
        assert rows == [] and gone[0]["band"] == "within its band: 0.8 at or under 3.7"

    def test_outside_its_band_the_row_comes_back_naming_both(self, store, inventory,
                                                             monkeypatch):
        from modules.readers import grafana_alerts as G

        value = _firing()
        self._acknowledge(monkeypatch, value, _Prom(p95=3.7, now=0.8))
        value["bands"] = G.band_readings(value, prom=_Prom(now=5.0))   # the reader's next run
        (r,), gone, _p = A._without_acknowledged(_rows(value))
        assert gone == []
        assert ("Acknowledged by operator@example.invalid within a band of 3.7 (its 7-day "
                "95th percentile when acknowledged); its value is now 5, above it") in r["cause"]

    def test_a_band_that_cannot_be_measured_is_refused(self, store, inventory, monkeypatch):
        class Down(_Prom):
            def _get(self, path, **params):
                return {"ok": False, "error": "connection refused"}

        out, _r = self._acknowledge(monkeypatch, _firing(), Down())
        assert out["ok"] is False and "connection refused" in out["error"]
        from modules import acknowledgements as ACK
        assert ACK.read()["rows"] == []

    def test_an_incident_row_is_still_not_acknowledged_here(self, store, monkeypatch):
        monkeypatch.setattr(A, "grafana_source", lambda cached=None: {"rows": [
            {"id": "grafana:incident:x", "acknowledge": False}]})
        out = A.acknowledge("grafana:incident:x", "", "a reason with words", by="a", verified="t")
        assert out["ok"] is False and "clears when its condition resolves" in out["error"]
