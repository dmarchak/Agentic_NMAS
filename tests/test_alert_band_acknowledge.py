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
import re
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
        assert re.search(r"Acknowledged by operator@example\.invalid at \d\d:\d\d UTC within a "
                         r"band of 3\.7 \(its 7-day 95th percentile when acknowledged\), the "
                         r"band that governs; its value is 5 \(read by the reader at \d\d:\d\d "
                         r"UTC\), above it, so it is shown", r["cause"]), r["cause"]


class TestTheStuckAcknowledgeC533:
    """C533 (the operator, 2026-10-06, s3's discards): the row re-raised above its band; three
    acknowledgements were RECORDED (bands 3.717, values 4.44, 5.92, 4.75, read on the host), each
    above its band, so the row stayed; the button stayed "Acknowledging…" and said nothing. The
    row named the newest acknowledgement's band while the reader still judged by the day
    before's (3.235)."""

    def _ack(self, monkeypatch, value, prom):
        return TestAcknowledgingWithinTheBand._acknowledge(None, monkeypatch, value, prom)

    def test_an_acknowledgement_that_cannot_hide_its_row_says_so_with_both_numbers(
            self, store, inventory, monkeypatch):
        out, _r = self._ack(monkeypatch, _firing(), _Prom(p95=3.717, now=4.44))
        assert out["ok"] is True and out["hides_now"] is False
        assert "Recorded." in out["words"] and "3.72" in out["words"] and "4.44" in out["words"]
        assert "above it" in out["words"] and "the band that governs" in out["words"]

    def test_one_that_hides_its_row_says_nothing_more(self, store, inventory, monkeypatch):
        out, _r = self._ack(monkeypatch, _firing(), _Prom(p95=3.7, now=0.8))
        assert out["hides_now"] is True and out["words"] == ""

    def test_the_newest_acknowledgements_band_governs_never_the_readers_stale_one(
            self, store, inventory, monkeypatch):
        """The reader ran before the second acknowledgement and still carries the first one's
        band (3.235, value 3.6 above it); the second recorded 3.717. Its band governs: 3.6 is
        within it, so the row is hidden, and the words never name a band that did not decide."""
        from modules import acknowledgements as ACK

        value = _firing()
        self._ack(monkeypatch, value, _Prom(p95=3.717, now=3.6))
        key = next(iter(_rows(value)))["event"]
        value["bands"] = {key: {"band": 3.235, "value": 3.6, "in_band": False,
                                "at": "2099-01-01T00:00:00Z"}}
        rows, gone, _p = A._without_acknowledged(_rows(value))
        assert rows == [] and gone[0]["band"] == "within its band: 3.6 at or under 3.72"
        a = ACK.read()["rows"][-1]
        judged = ACK.within_band(a, value["bands"][key])
        assert judged["band"] == pytest.approx(3.717) and judged["value_from"] == "the reader"

    def test_the_newest_value_is_judged(self):
        from modules import acknowledgements as ACK
        a = {"band": 3.7, "value": 4.4, "at": "2026-10-06T18:28:54Z"}
        older = {"value": 3.6, "at": "2026-10-06T18:20:00Z"}
        newer = {"value": 3.6, "at": "2026-10-06T18:30:39Z"}
        assert ACK.within_band(a, older)["in_band"] is False, "the acknowledgement's is newer"
        assert ACK.within_band(a, newer)["in_band"] is True
        assert ACK.within_band({"band": 3.7, "value": None}, {})["in_band"] is None


def test_the_button_is_never_left_busy_with_nothing_said():
    """The Acknowledge form's answer (`ackAnswer`, run in the shipped script): a refusal frees
    it and says why; recorded-and-hidden stays busy for the redraw that removes the row;
    recorded-and-NOT-hidden frees it and says why the row stays."""
    from tests.test_device_v2 import _eval

    def answer(status, body):
        return json.loads(_eval("nmas_v2.js", "NMAS_V2", f"ackAnswer({status}, {json.dumps(body)})"))

    hidden = answer(200, {"ok": True, "hides_now": True})
    assert hidden["busy"] is True
    stays = answer(200, {"ok": True, "hides_now": False, "words": "Recorded. above it"})
    assert stays == {"busy": False, "isOpen": False, "said": "", "note": "Recorded. above it"}
    refused = answer(409, {"ok": False, "error": "a reason"})
    assert refused["busy"] is False and refused["said"] == "Not acknowledged: a reason"

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
