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

import time

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


def _after_ack():
    """A reading's time as the reader records it (`band_readings` sets `at`), a minute after the
    acknowledgement the fixture makes now: the newest value is the one judged (C533)."""
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 60))


def _instance(**over):
    return dict({"rule_uid": "rule-1", "rule": "Interface output discards", "kind": "condition",
                 "labels": LABELS, "device": "s3", "address": "192.0.2.23"}, **over)


class TestTheDevicePageSaysAcknowledged:
    def test_inside_its_band_it_reads_acknowledged(self, band_ack):
        from modules.device_page import _acknowledged_alerts
        acked, open_ = _acknowledged_alerts([_instance()], {SERIES: {"value": 3.1, "in_band": True, "at": _after_ack()}})
        assert not open_ and len(acked) == 1
        _i, a, reading = acked[0]
        assert a["by"] == "operator@example.com" and reading == pytest.approx(3.1)

    def test_above_its_band_it_is_firing(self, band_ack):
        from modules.device_page import _acknowledged_alerts
        acked, open_ = _acknowledged_alerts([_instance()], {SERIES: {"value": 5.0, "in_band": False, "at": _after_ack()}})
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


class TestAnEarlierDevicesAcknowledgementHidesNothing:
    """C1476: a band acknowledged for a RETIRED s3 kept hiding the new s3's rows, its series and
    adjacencies keyed by name. An acknowledgement made at or before the name's cut
    (`retire.name_cuts_everywhere`; planted as a real retire commit and the new device's Create
    in the network's repository) hides nothing: Needs attention, its in-force list and the
    device page. It can only ever hide LESS: one made after the cut still hides (the other
    direction, held beside it)."""

    NOW = time.time()
    ADJ = "adjacency_log:Default|s3|ospf|r1"

    @pytest.fixture(autouse=True)
    def _new_s3(self, band_ack, tmp_path, monkeypatch):
        import os

        from modules.config import list_data_path
        from tests.test_retire_leaves_nothing import plant_name_history

        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
        plant_name_history(os.path.join(list_data_path("Default"), "config_repo"),
                           retired=[("s3", self.NOW - 3600)], created=[("s3", self.NOW - 600)])
        ACK.record(self.ADJ, self.ADJ, why="a known flap on this link", by="operator@example.com",
                   verified="access", kind="adjacency_log/flap",
                   what="s3's ospf adjacency to r1 went down 2 times", band=3, value=2,
                   devices=["s3"])

    def _made_at(self, row, at):
        """The recorded acknowledgement of *row*, its time set to *at* (the record's own file)."""
        import json

        path = ACK._path()
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        for r in rows:
            if r["row"] == row:
                r["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rows))

    def _rows(self):
        return [{"id": ROW, "event": SERIES, "acknowledge": True, "what": "discards on s3",
                 "cause": "alerting", "operands": {"band_reading": {"value": 3.0,
                                                                    "at": _after_ack()}}},
                {"id": self.ADJ, "event": self.ADJ, "acknowledge": True,
                 "what": "s3's ospf adjacency to r1 went down 2 times", "cause": "logged",
                 "operands": {"band_reading": {"value": 2, "at": _after_ack()}}}]

    def test_made_after_the_cut_it_still_hides_both(self):
        from modules.attention import _without_acknowledged
        kept, gone, problem = _without_acknowledged(self._rows())
        assert problem is None and kept == [], kept
        assert {g["id"] for g in gone} == {ROW, self.ADJ}

    def test_made_before_the_cut_it_hides_neither(self):
        from modules.attention import _standing_acknowledgements, _without_acknowledged
        from modules.device_page import _acknowledged_alerts
        self._made_at(ROW, self.NOW - 7200)
        self._made_at(self.ADJ, self.NOW - 5400)
        kept, gone, _problem = _without_acknowledged(self._rows())
        assert {r["id"] for r in kept} == {ROW, self.ADJ} and gone == [], gone
        assert _standing_acknowledgements([]) == [], "an earlier device's is in force for nothing"
        acked, open_ = _acknowledged_alerts([_instance()], {})
        assert not acked and len(open_) == 1

    def test_one_before_and_one_after_only_the_after_hides(self):
        from modules.attention import _without_acknowledged
        self._made_at(self.ADJ, self.NOW - 5400)
        kept, gone, _problem = _without_acknowledged(self._rows())
        assert [r["id"] for r in kept] == [self.ADJ] and [g["id"] for g in gone] == [ROW]

    def test_the_record_keeps_every_one(self):
        self._made_at(ROW, self.NOW - 7200)
        assert {a["row"] for a in ACK.read()["rows"]} == {ROW, self.ADJ}
