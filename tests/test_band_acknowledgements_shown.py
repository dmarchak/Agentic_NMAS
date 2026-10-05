"""C433's first real run (the operator, 2026-10-05): s3's "Interface output discards" was
acknowledged within its band, recorded (band 3.24, value 3.19), and shown NOWHERE: the alert
stopped firing, so Needs attention hid nothing and listed nothing; History read only one
acknowledgement kind; s3's Checks still showed the alert with no word of it.

Held here (History's half is tests/test_history_declared.py, every acknowledgeable kind):
- Needs attention lists a band acknowledgement IN FORCE even when it hides nothing now, with
  who, why, the band and the value when acknowledged; one that hides a row now is not listed
  twice;
- the device page's Alerts check reads an acknowledged alert as acknowledged (who, band,
  value) when its reading is inside the band, and as firing when above it, the same judgement
  Needs attention makes.
"""

import pytest

from modules import acknowledgements as ACK
from modules.alert_bands import series_key

LABELS = {"ifDescr": "GigabitEthernet1/1", "instance": "192.0.2.23"}
SERIES = series_key("rule-1", LABELS)
ROW = f"grafana:series:{SERIES}"


@pytest.fixture
def band_ack(tmp_path, monkeypatch):
    monkeypatch.setattr(ACK, "_path", lambda: str(tmp_path / "acknowledgements.jsonl"))
    ACK.record(ROW, SERIES, why="known issue no fix yet", by="operator@example.com",
               verified="access", kind="grafana/series",
               what="Interface output discards is alerting on s3", band=3.2354, value=3.1875,
               devices=["s3"])


class TestNeedsAttentionListsItInForce:
    def test_listed_when_it_hides_nothing(self, band_ack):
        from modules.attention import _standing_acknowledgements
        got = _standing_acknowledgements([])
        assert len(got) == 1, got
        k = got[0]
        assert k["what"] == "Interface output discards is alerting on s3"
        assert k["by"] == "operator@example.com" and k["why"] == "known issue no fix yet"
        assert "at or under 3.24" in k["band"] and "3.19 when acknowledged" in k["band"]

    def test_not_repeated_when_it_hides_a_row_now(self, band_ack):
        from modules.attention import _standing_acknowledgements
        assert _standing_acknowledgements([{"id": ROW}]) == []

    def test_the_newest_per_series_stands(self, band_ack):
        ACK.record(ROW, SERIES, why="re-measured", by="operator2@example.com",
                   verified="access", kind="grafana/series", what="discards", band=4.0,
                   value=3.5, devices=["s3"])
        from modules.attention import _standing_acknowledgements
        got = _standing_acknowledgements([])
        assert [k["by"] for k in got] == ["operator2@example.com"]

    def test_the_page_draws_it(self, band_ack):
        import app as A
        with A.app.test_request_context("/"):
            from flask import render_template
            html = render_template("v2/_attention.html", a={
                "rows": [], "unreadable": [], "acknowledged": [], "sources": [],
                "badge": {}, "headline": "Nothing needs attention",
                "in_force": [{"id": ROW, "what": "Interface output discards is alerting on s3",
                              "by": "operator@example.com", "why": "known issue no fix yet",
                              "at": "2026-10-05T02:47:24Z",
                              "band": "holds while its value stays at or under 3.24"}]})
        assert 'id="att-in-force"' in html and "known issue no fix yet" in html


def _instance(**over):
    return dict({"rule_uid": "rule-1", "rule": "Interface output discards", "kind": "condition",
                 "labels": LABELS, "device": "s3", "address": "192.0.2.23"}, **over)


class TestTheDevicePageSaysAcknowledged:
    def test_inside_its_band_it_reads_acknowledged(self, band_ack):
        from modules.device_page import _acknowledged_alerts
        acked, open_ = _acknowledged_alerts([_instance()], {SERIES: {"value": 3.1, "in_band": True}})
        assert not open_ and len(acked) == 1
        _i, a, reading = acked[0]
        assert a["by"] == "operator@example.com" and reading == pytest.approx(3.1)

    def test_above_its_band_it_is_firing(self, band_ack):
        from modules.device_page import _acknowledged_alerts
        acked, open_ = _acknowledged_alerts([_instance()], {SERIES: {"value": 5.0, "in_band": False}})
        assert not acked and len(open_) == 1

    def test_unread_it_judges_by_the_value_when_acknowledged(self, band_ack):
        from modules.device_page import _acknowledged_alerts
        acked, _open = _acknowledged_alerts([_instance()], {})
        assert len(acked) == 1 and acked[0][2] == pytest.approx(3.1875)

    def test_another_series_is_not_covered(self, band_ack):
        from modules.device_page import _acknowledged_alerts
        other = _instance(labels={"ifDescr": "GigabitEthernet1/2", "instance": "192.0.2.23"})
        acked, open_ = _acknowledged_alerts([other], {})
        assert not acked and len(open_) == 1
