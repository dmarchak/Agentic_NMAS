"""C188: Save All read nine devices one after another, twice (the preview,
then the apply): 101 s and 102 s of reads measured on the host 2026-09-29,
s3 the slowest at 23-24 s. A capture now reads its devices AT ONCE, times
each, and names the slowest, since a parallel read is only as fast as its
slowest member (the operator).
"""

import threading
import time

import routes.golden as G
from tests.test_capture import build_capture_lab



def _devices(n):
    return [{"hostname": f"d{i}", "ip": f"203.0.113.{i + 1}"} for i in range(n)]


def _fake_reads(monkeypatch, delays, fail=()):
    """Each device's read takes its delay; `fail` raises. Records the peak
    number of reads in flight at once, which a shorter wall clock alone would
    not prove (a faster fake could produce that)."""
    state = {"now": 0, "peak": 0}
    mu = threading.Lock()

    def entry(list_name, repo, device):
        host = device["hostname"]
        with mu:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        try:
            time.sleep(delays[host])
            if host in fail:
                raise TimeoutError("read timed out")
            return ({"device": host, "read": True, "error": "", "platform": "cisco_ios",
                     "capture_hash": host, "changed": False, "diff": [],
                     "intent": {"state": "match"}, "busy": ""}, f"hostname {host}\n")
        finally:
            with mu:
                state["now"] -= 1

    monkeypatch.setattr(G, "_capture_entry", entry)
    return state


class TestTheReadsOverlap:
    def test_nine_devices_take_the_slowest_ones_time_not_the_sum(self, monkeypatch):
        # Spaced 0.1 s apart: per-device times are rounded to 0.1 s, so a
        # closer spacing ties and the slowest is named by order, not by time.
        delays = {f"d{i}": 0.05 + 0.1 * i for i in range(9)}       # slowest d8, 0.85 s
        state = _fake_reads(monkeypatch, delays)
        read, timing = G._read_all("Lab", "/nowhere", _devices(9))
        assert state["peak"] == 9, "every read in flight at once"
        assert timing["workers"] == 9
        assert timing["wall_s"] < 0.5 * sum(delays.values()), timing
        assert timing["slowest"] == "d8" and timing["slowest_s"] >= 0.8
        assert [e["device"] for e, _t in read] == [f"d{i}" for i in range(9)], "order kept"

    def test_one_failing_read_is_that_devices_alone(self, monkeypatch):
        _fake_reads(monkeypatch, {f"d{i}": 0.05 for i in range(3)}, fail=("d1",))
        read, _timing = G._read_all("Lab", "/nowhere", _devices(3))
        by = {e["device"]: e for e, _t in read}
        assert by["d1"]["read"] is False and "read timed out" in by["d1"]["error"]
        assert by["d0"]["read"] and by["d2"]["read"]

    def test_the_cap_bounds_the_sessions_opened_at_once(self, monkeypatch):
        monkeypatch.setattr(G, "CAPTURE_READ_WORKERS", 2)
        state = _fake_reads(monkeypatch, {f"d{i}": 0.1 for i in range(5)})
        _read, timing = G._read_all("Lab", "/nowhere", _devices(5))
        assert timing["workers"] == 2 and state["peak"] == 2


class TestTheTimingIsSaid:
    def test_the_words_name_both_times_and_the_slowest(self):
        from modules.preview_confirm import read_timing_words
        words = read_timing_words({"wall_s": 24.1, "series_s": 101.3, "workers": 9,
                                   "slowest": "s3", "slowest_s": 23.8,
                                   "per_device_s": {f"x{i}": 1 for i in range(9)}})
        assert words == ("Read 9 device(s) at once in 24.1 s (one after another: 101.3 s); "
                         "slowest s3, 23.8 s.")

    def test_the_preview_and_the_result_say_it_through_the_real_routes(self, tmp_path,
                                                                      monkeypatch):
        lab = build_capture_lab(monkeypatch, tmp_path)
        d = lab["client"].post("/golden/capture/preview", json={"devices": ["r2"]}).get_json()
        p = d["preview"]
        assert "Read 1 device(s) in " in p["what"]["summary"]
        assert "slowest r2" in p["what"]["summary"]
        op = {o["name"]: o["value"] for o in p["targets"][0]["operands"]}
        assert op["read in"].endswith(" s")
        h = p["what"]["targets"][0]["select_data"]["hash"]
        out = lab["client"].post("/golden/capture/apply",
                                 json={"confirmations": {"r2": h}}).get_json()
        assert "slowest r2" in out["result"]["happened"]["summary"]
