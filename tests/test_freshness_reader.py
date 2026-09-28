"""Oxidized freshness as a reader job (7.2 step 15; modules/readers/
freshness_reader.py): the signal is computed on a schedule and the page reads
what was stored, never Oxidized (it was one Oxidized fetch and one golden read
per device on every index page load). The reports here are built by the REAL
`freshness.reconcile()` from device rows in `compare_device()`'s shape."""

import dataclasses
import os
import re

import pytest

from modules import attention as A
from modules import config
from modules import reader_job as R
from modules.nsot import freshness as F
from modules.readers import freshness_reader as FR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = 1_790_000_000.0


def device(name, verdict, reason="", only_right=()):
    return {"device": name, "verdict": verdict, "reason": reason, "only_left": [],
            "only_right": list(only_right), "golden_at": "2026-09-28T20:00:00Z",
            "oxidized_at": "2026-09-28T21:18:00Z", "fingerprint": "ab" * 16,
            "time_assumed_utc": False}


def report(list_name, rows):
    base = {"ok": True, "list": list_name, "source": "oxidized", "devices": list(rows),
            "counts": {}, "blocked": [], "errors": [], "checked": 0, "population": 0}
    return F.reconcile(base, [r["device"] for r in rows])


FLEET = [device("r1", F.MATCH),
         device("r2", F.UNAPPROVED, "Oxidized's copy is newer and differs",
                ["snmp-server community Pl4ntedSecret RO", "ntp server 192.0.2.1"]),
         device("s1", F.POLL_RACE, "the golden is newer"),
         device("s2", F.AUTHORISED, "authorised by a person"),
         device("s3", F.INCONCLUSIVE, "Oxidized's index could not be read")]


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))


def stored(monkeypatch, reports, active="Lab"):
    monkeypatch.setattr(F, "check", lambda name: reports[name])
    reader = dataclasses.replace(FR.READER, read=lambda: FR.read(lists=list(reports)))
    doc = R.run_once(reader, clock=lambda: T0)
    import modules.config as C
    monkeypatch.setattr(C, "get_current_list_name", lambda: active)
    return doc


class TestTheRead:
    def test_every_list_is_compared_and_a_failing_one_is_stored_with_its_reason(self, monkeypatch):
        def check(name):
            if name == "Broken":
                raise OSError("oxidized refused")
            return report(name, FLEET)
        monkeypatch.setattr(F, "check", check)
        v = FR.read(lists=["Lab", "Broken"])
        assert set(v["lists"]) == {"Lab", "Broken"}, "a list it could not answer is never absent"
        assert v["lists"]["Lab"]["ok"] and "summary" in v["lists"]["Lab"]
        assert v["lists"]["Broken"]["ok"] is False and "oxidized refused" in v["lists"]["Broken"]["error"]

    def test_no_lists_is_a_failed_read_not_an_empty_answer(self):
        with pytest.raises(ValueError, match="no device lists"):
            FR.read(lists=[])

    def test_it_is_declared_with_its_measured_basis(self):
        assert FR.READER in R.readers() and FR.READER.interval_seconds == 300
        assert "4 ms per device" in FR.READER.interval_basis
        assert FR.READER.invalidates == ("freshness",)


class TestTheRoute:
    """Through the real route, on a list the registry holds (an unknown list
    is refused before anything is read, C51)."""

    @pytest.fixture
    def client(self):
        import app as Ap
        return Ap.app.test_client()

    @pytest.fixture
    def lst(self):
        from modules.device import get_device_lists
        names = [d["name"] for d in get_device_lists()]
        assert names, "the test store holds a list"
        return names[0]

    def test_nothing_stored_is_503_and_says_it_is_not_nothing_diverged(self, client, lst):
        r = client.get(f"/freshness/report?list={lst}")
        assert r.status_code == 503
        assert "not the same as nothing having diverged" in r.get_json()["error"]

    def test_it_serves_the_stored_list_with_its_time_and_never_asks_oxidized(self, client, lst,
                                                                              monkeypatch):
        stored(monkeypatch, {lst: report(lst, FLEET)}, active=lst)

        def live(name):
            raise AssertionError("the report route asked Oxidized")
        monkeypatch.setattr(F, "check", live)
        body = client.get(f"/freshness/report?list={lst}").get_json()
        assert body["ok"] and body["value_at"] == R._iso(T0)
        assert body["stale_after_seconds"] == 300 * R.STALE_AFTER_INTERVALS
        assert body["counts"][F.UNAPPROVED] == 1
        assert "Pl4ntedSecret" not in str(body), "the lines are masked on the way out"

    def test_a_list_the_value_does_not_hold_names_what_it_compared(self, client, lst, monkeypatch):
        stored(monkeypatch, {"Elsewhere": report("Elsewhere", FLEET)}, active=lst)
        r = client.get(f"/freshness/report?list={lst}")
        assert r.status_code == 404 and "(it compared: Elsewhere)" in r.get_json()["error"]


class TestTheSource:
    def test_unapproved_and_inconclusive_are_rows_and_the_rest_are_counted(self, monkeypatch):
        stored(monkeypatch, {"Lab": report("Lab", FLEET)})
        res = A.freshness_source()
        rows = {r["id"]: r for r in res["rows"]}
        assert set(rows) == {"freshness:Lab:r2", "freshness:Lab:s3"}
        assert rows["freshness:Lab:r2"]["level"] == "warning"
        assert "nobody approved" in rows["freshness:Lab:r2"]["what"]
        assert "Pl4ntedSecret" not in rows["freshness:Lab:r2"]["cause"]
        assert rows["freshness:Lab:s3"]["level"] == "unknown"
        assert "1 approved, 1 poll race, 1 authorised" in res["checked"]
        assert res["value_at"] == R._iso(T0) and res["stale_after_seconds"] == 900

    def test_a_list_that_could_not_be_compared_is_one_unknown_row(self, monkeypatch):
        stored(monkeypatch, {"Lab": {"ok": False, "list": "Lab",
                                     "error": "Oxidized is not configured"}})
        (row,) = A.freshness_source()["rows"]
        assert row["level"] == "unknown" and "not the same as nothing" in row["cause"]

    def test_nothing_stored_is_unreadable_never_clean(self):
        res = A.freshness_source(cached={"state": "absent", "doc": None, "why": "never run"})
        assert res["state"] == "unreadable" and "not compared yet" in res["rows"][0]["cause"]


class TestThePanel:
    SRC = os.path.join(ROOT, "static", "js", "gen", "partials__freshness_signal.1.js")

    def test_it_reads_the_stored_value_stamps_its_age_and_hears_the_reader(self):
        src = open(self.SRC, encoding="utf-8").read()
        assert re.search(r"^\s*NMAS\.subscribe\('freshness', 'freshnessSignal', loadFreshnessSignal",
                         src, re.M)
        assert "window.NMAS.stamp('freshnessBody'" in src
        assert "new Date().toLocaleTimeString()" not in src, "the fetch time is not the value's"
