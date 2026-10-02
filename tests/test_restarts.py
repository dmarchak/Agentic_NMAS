"""The tool notices a restart, tells planned from unplanned, and keeps every one (the operator,
2026-10-02: five devices restarted in a day, r3 with a crash file, and the tool noticed none).

On s3's REAL sysUpTime around its reboot on 2026-10-01 (`tests/fixtures/heartbeat/
s3_reboot.json`, Prometheus's own answer, captured read-only), and the reload reasons as the
devices print them (r3's crash, the operator's reading; vIOS's "Unknown reason"):

- a restart is found where the counter FELL, never from now minus uptime: s3's clock runs at
  about 0.55, so that would drift and invent restarts (the slow series alone finds none);
- the reader records it once, judged planned only when the tool reloaded it or was told
  (`record_planned`), with the device's own reason and crash file;
- an unplanned restart is a Needs attention row, DANGER with a crash file; a planned one is
  none; both are in the device's History;
- the tool's own reload writes its planned window BEFORE the reload is sent.
"""

import json
import os
import time

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "heartbeat", "s3_reboot.json")
R3_CRASH = ("Last reload reason: Critical software exception, check "
            "bootflash:r3_crashinfo_RP_00_00_20261002-083421-UTC\n"
            "r3 uptime is 8 hours, 55 minutes\n")
VIOS = "s3 uptime is 13 hours, 50 minutes\nSystem returned to ROM by reload\n" \
       "Last reload reason: Unknown reason\n"


def _series():
    return json.load(open(FIX))["sysUpTime"][0]["values"]


def _expected_boot():
    """Computed here by a plain walk of the capture, never by the module under test."""
    v = _series()
    i = next(i for i in range(1, len(v)) if v[i][1] < v[i - 1][1])
    return v[i][0] - v[i][1] / 100.0, v[i][0]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    return tmp_path


class TestDetection:
    def test_the_real_reboot_is_found_where_the_counter_fell(self):
        from modules.restarts import drops
        boot, seen = _expected_boot()
        found = drops(_series())
        assert len(found) == 1, found
        v = _series()
        before = max(t for t, _u in v if t < seen)
        assert found[0]["seen_at"] == seen and found[0]["last_seen"] == before
        # Kept inside the gap the device was silent in, whatever its clock says.
        assert before <= found[0]["at"] <= seen
        assert abs(found[0]["at"] - max(boot, before)) < 1

    def test_an_uptime_longer_than_the_gap_is_kept_inside_it(self):
        """A minimal edit of the real series: the first sample after the drop reports more
        uptime than the gap is long (a stale sample, or a clock running fast). The restart
        is never placed before the last sample that showed the device up."""
        from modules.restarts import drops
        v = [list(p) for p in _series()]
        i = next(i for i in range(1, len(v)) if v[i][1] < v[i - 1][1])
        gap = v[i][0] - v[i - 1][0]
        v[i][1] = (gap + 600) * 100.0
        assert v[i][1] < v[i - 1][1]
        found = drops(v)
        assert found[0]["at"] == v[i - 1][0] == found[0]["last_seen"]

    def test_a_slow_clock_without_a_reset_is_no_restart(self):
        """s3's counter before the reboot: 0.55 of real time, never falling."""
        from modules.restarts import drops
        v = _series()
        i = next(i for i in range(1, len(v)) if v[i][1] < v[i - 1][1])
        before = v[:i]
        rate = (before[-1][1] - before[0][1]) / 100 / (before[-1][0] - before[0][0])
        assert rate < 0.9, rate          # the clock IS slow, so now-minus-uptime would drift
        assert drops(before) == []

    def test_the_reason_is_the_devices_own(self):
        from modules.restarts import reason_from
        assert reason_from(R3_CRASH) == {
            "reason": "Critical software exception",
            "crash_file": "bootflash:r3_crashinfo_RP_00_00_20261002-083421-UTC"}
        assert reason_from(VIOS)["reason"] == "Unknown reason"
        assert reason_from("")["reason"] == "" and reason_from("")["crash_file"] == ""


def _read(previous=None, reason=R3_CRASH, now=None):
    from modules.readers import restarts as reader
    from modules.restarts import reason_from
    dev = {"hostname": "s3", "ip": "192.0.2.13"}
    return reader.read(previous=previous or {}, clock=lambda: now or _series()[-1][0] + 60,
                       source=lambda window, at: (True, {"s3": [_series()]}),
                       devices=lambda: {"s3": ("Lab", dev)},
                       reason=lambda d: dict(reason_from(reason), error=""))


class TestTheReader:
    def test_an_unplanned_restart_is_recorded_once_with_its_reason(self, store):
        from modules.restarts import events
        v = _read()
        assert [r["device"] for r in v["new"]] == ["s3"]
        r = v["new"][0]
        assert r["planned"] is False and r["reason"] == "Critical software exception"
        assert r["crash_file"].startswith("bootflash:r3_crashinfo")
        assert _read(previous=v)["new"] == [], "the same restart was recorded twice"
        assert len(events("s3")["rows"]) == 1

    def test_a_planned_window_makes_it_planned(self, store):
        from modules.restarts import record_planned
        boot, _seen = _expected_boot()
        assert record_planned(["s3"], boot - 120, boot + 60, "operator@example.com",
                              "lab redeploy", "test", list_name="Lab")["ok"]
        r = _read()["new"][0]
        assert r["planned"] is True and r["planned_by"] == "operator@example.com"

    def test_a_window_for_another_device_does_not_cover_it(self, store):
        from modules.restarts import record_planned
        boot, _seen = _expected_boot()
        record_planned(["s4"], boot - 120, boot + 60, "x@example.com", "s4 only", "test")
        assert _read()["new"][0]["planned"] is False

    def test_a_planned_record_names_who_and_why_or_is_refused(self, store):
        from modules.restarts import record_planned
        assert not record_planned(["s3"], 0, 10, "", "why", "t")["ok"]
        assert not record_planned(["s3"], 0, 10, "who", " ", "t")["ok"]
        assert not record_planned(["s3"], 10, 0, "who", "why", "t")["ok"]
        assert not record_planned([], 0, 10, "who", "why", "t")["ok"]

    def test_an_unreadable_record_is_a_failed_read_never_nothing_restarted(self, store):
        (store / "restarts.jsonl").write_text("{not json\n")
        with pytest.raises(RuntimeError, match="restart record could not be read"):
            _read()


def _cached(value):
    return {"state": "ok", "doc": {"last_good": {"value": value,
                                                 "value_at": "2026-10-02T09:00:00Z"},
                                   "stale_after_seconds": 180}}


class TestNeedsAttention:
    def test_a_crash_is_a_danger_row_naming_the_crash_file(self, store):
        from modules.attention import restart_source
        v = _read(now=time.time())
        rows = restart_source(cached=_cached(v))["rows"]
        assert len(rows) == 1 and rows[0]["level"] == "danger"
        assert "s3 restarted unexpectedly at" in rows[0]["what"]
        assert "reason: critical software exception (crash file saved)" in rows[0]["what"]
        assert "Read the crash file (bootflash:r3_crashinfo" in rows[0]["action"]["label"]
        assert rows[0]["action"]["href"] == "/v2/device/s3?tab=history"

    def test_no_crash_file_is_a_warning(self, store):
        from modules.attention import restart_source
        v = _read(reason=VIOS, now=time.time())
        rows = restart_source(cached=_cached(v))["rows"]
        assert rows[0]["level"] == "warning" and "reason: unknown reason" in rows[0]["what"]

    def test_a_planned_restart_is_no_row(self, store):
        from modules.attention import restart_source
        from modules.restarts import record_planned
        boot, _seen = _expected_boot()
        record_planned(["*"], boot - 60, boot + 60, "x@example.com", "redeploy", "t", "Lab")
        v = _read(now=time.time())
        assert v["new"][0]["planned"] and restart_source(cached=_cached(v))["rows"] == []


class TestHistory:
    def test_every_restart_is_in_the_devices_history(self, store, monkeypatch):
        from modules import device_page
        from modules.nsot import listref
        _read()
        monkeypatch.setattr("modules.nsot.repo.golden_history", lambda *a, **k: [])
        monkeypatch.setattr("modules.nsot.hostvars.intent_commits", lambda *a, **k: [])
        monkeypatch.setattr("modules.nsot.receipts.read",
                            lambda *a, **k: {"state": "absent", "rows": []})
        ref = listref.ListRef(name="Lab", slug="lab", data_dir=str(store), repo_dir=str(store),
                              csv_path="")
        h = device_page.history(ref, {"hostname": "s3"})
        ev = [e for e in h["events"] if e["kind"] == "restart"]
        assert len(ev) == 1 and ev[0]["what"] == "Restarted unexpectedly"
        assert ev[0]["outcome"] == "crash" and "crash file bootflash:" in ev[0]["detail"]


class TestTheToolsOwnReload:
    def test_the_reload_records_its_window_before_it_is_sent(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py"),
                   encoding="utf-8").read()
        body = src[src.index("def bulk_reload("):]
        body = body[:body.index(chr(10) + "@" + "app.route")]   # the next route
        assert 0 < body.index("_restarts.record_planned(") < body.index("outcome = reload_device(conn)")


def test_the_command_sent_is_the_declared_one():
    """The send carries the literal (so the command scans see a read) and it is REASON_COMMAND."""
    from modules import restarts
    src = open(restarts.__file__, encoding="utf-8").read()
    assert f'"{restarts.REASON_COMMAND}"' in src


class TestTheCommand:
    def _main(self):
        from importlib.machinery import SourceFileLoader
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts",
                            "nmas-planned-restart")
        return SourceFileLoader("nmas_planned_restart", path).load_module().main

    def test_a_past_window_is_recorded_from_its_start(self, store):
        from modules.restarts import _read_jsonl, _data
        assert self._main()(["Lab", "*", "--from", "2026-10-01T15:20Z", "--minutes", "110",
                             "--why", "the lab redeploy", "--by", "operator@example.com"]) == 0
        row = _read_jsonl(_data("planned_restarts.jsonl"))["rows"][0]
        assert row["from"] == "2026-10-01T15:20:00Z" and row["until"] == "2026-10-01T17:10:00Z"
        assert row["devices"] == ["*"] and row["via"] == "nmas-planned-restart"

    def test_a_time_that_is_not_one_is_refused(self, store):
        assert self._main()(["Lab", "s3", "--from", "yesterday", "--minutes", "5",
                             "--why", "a hand reload"]) == 1
