"""C188: Save All read nine devices one after another, twice (the preview,
then the apply): 101 s and 102 s of reads measured on the host 2026-09-29,
s3 the slowest at 23-24 s. A capture now reads its devices AT ONCE, times
each, and names the slowest, since a parallel read is only as fast as its
slowest member (the operator).

Step 2: the preview no longer answers when the reads end. The POST starts a
JOB and answers at once (202), the in-flight panel shows the reads, and the
job ANNOUNCES `capture_preview` (C58) when it finishes, so no request waits on
a device and no edge limit can end one.
"""

import threading
import time

import pytest

import routes.golden as G
from tests.test_capture import build_capture_lab, run_capture_preview



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
        d = run_capture_preview(lab["client"], {"devices": ["r2"]}).get_json()
        p = d["preview"]
        assert "Read 1 device(s) in " in p["what"]["summary"]
        assert "slowest r2" in p["what"]["summary"]
        op = {o["name"]: o["value"] for o in p["targets"][0]["operands"]}
        assert op["read in"].endswith(" s")
        h = p["what"]["targets"][0]["select_data"]["hash"]
        out = lab["client"].post("/golden/capture/apply",
                                 json={"confirmations": {"r2": h}}).get_json()
        assert "slowest r2" in out["result"]["happened"]["summary"]


class TestThePreviewIsAJob:
    """C188 step 2, through the real routes: a read held open by a gate
    proves the POST answered BEFORE any read ended (a fast fake could not)."""

    @pytest.fixture
    def held(self, tmp_path, monkeypatch):
        from modules import invalidation as I

        lab = build_capture_lab(monkeypatch, tmp_path)
        gate = threading.Event()
        real = G._capture_entry

        def entry(list_name, repo, device):
            assert gate.wait(30), "the test never released the read"
            return real(list_name, repo, device)

        monkeypatch.setattr(G, "_capture_entry", entry)
        heard = []
        monkeypatch.setattr(I, "_emitter", lambda event, msg: heard.append((event, msg)))
        yield lab, gate, heard
        gate.set()

    def test_the_post_answers_while_the_reads_are_still_running(self, held):
        from modules.nsot import capture_job

        lab, gate, heard = held
        r = lab["client"].post("/golden/capture/preview", json={"devices": ["r2"]})
        assert r.status_code == 202, r.get_data(as_text=True)[:300]
        d = r.get_json()
        assert d["ok"] and d["devices"] == ["r2"] and d["job"]
        running = lab["client"].get(f"/golden/capture/preview/{d['job']}").get_json()
        assert running["state"] == "running" and running["preview"] is None
        assert "reading 1 device(s) at once" in running["step_words"], running
        assert "NetBox" not in running["step_words"], "a capture counts no NetBox requests"
        assert heard == [], "nothing is announced before the reads end"
        # The in-flight panel lists it while it runs (C99's standing rule).
        panel = lab["client"].get("/operations/in_flight").get_json()
        assert panel["ok"], panel
        rows = [x for x in panel["running"] if x["operation"] == "capture preview"]
        assert rows and rows[0]["device"] == "Lab: 1 device(s)", panel["running"]
        gate.set()
        assert capture_job.wait(d["job"], 30)
        done = lab["client"].get(f"/golden/capture/preview/{d['job']}").get_json()
        assert done["state"] == "done" and done["preview"]["what"]["targets"][0]["name"] == "r2"
        assert [m["keys"] for e, m in heard] == [["capture_preview"]]
        assert heard[0][1]["by"] == "capture-preview" and heard[0][1]["ok"] is True
        assert "read 1 of 1 device(s)" in done["step_words"]

    def test_a_failed_announcement_is_recorded_and_the_result_still_served(self, held,
                                                                         monkeypatch):
        from modules import invalidation as I
        from modules.nsot import capture_job

        lab, gate, _heard = held
        monkeypatch.setattr(I, "_emitter", None)          # no socket: announce raises
        gate.set()
        d = lab["client"].post("/golden/capture/preview", json={"devices": ["r2"]}).get_json()
        assert capture_job.wait(d["job"], 30)
        assert capture_job.get(d["job"])["announced"] is False
        done = lab["client"].get(f"/golden/capture/preview/{d['job']}").get_json()
        assert done["state"] == "done" and done["preview"]

    def test_a_job_that_raises_is_failed_with_its_reason(self, held, monkeypatch):
        from modules.nsot import capture_job

        lab, gate, heard = held

        def boom(*a, **k):
            raise RuntimeError("the preview could not be built")

        monkeypatch.setattr("modules.preview_confirm.capture_preview", boom)
        gate.set()
        d = lab["client"].post("/golden/capture/preview", json={"devices": ["r2"]}).get_json()
        assert capture_job.wait(d["job"], 30)
        got = lab["client"].get(f"/golden/capture/preview/{d['job']}").get_json()
        assert got["state"] == "failed" and got["ok"] is False
        assert "RuntimeError: the preview could not be built" in got["error"]
        assert heard and heard[-1][1]["ok"] is False, "a failed job is announced too"

    def test_an_unknown_job_says_why_and_is_never_an_empty_preview(self, held):
        lab, _gate, _heard = held
        r = lab["client"].get("/golden/capture/preview/0123456789abcdef")
        d = r.get_json()
        assert r.status_code == 404 and d["state"] == "unknown" and not d["ok"]
        assert "server restarted" in d["error"] and "start the preview again" in d["error"]

    def test_nothing_to_capture_still_answers_at_once_with_no_job(self, tmp_path,
                                                                 monkeypatch):
        lab = build_capture_lab(monkeypatch, tmp_path)
        r = lab["client"].post("/golden/capture/preview", json={"scope": "no_golden"})
        d = r.get_json()
        assert r.status_code == 200 and "job" not in d and d["preview"] is None
        assert "nothing to capture" in d["nothing"]


class TestTheModalSaysWhatItWaitsFor:
    """The SHIPPED client's pure parts, executed."""

    def _js(self, expr):
        import dukpy

        from tests.payload_render import shipped
        return dukpy.evaljs("var window = {};\n" + shipped("nmas_capture.js") + "\n" + expr)

    def test_waiting_names_the_devices_and_what_it_is_doing(self):
        w = self._js("window.captureWaitingWords(['s1', 's3'], {step_words: 'read 1 of 2 device(s); "
                     "waiting on s3', elapsed_s: 12.5}, 'connected')")
        assert w["live"] is True
        assert w["lines"][0] == "Reading 2 device(s) at once, on the server: s1, s3."
        assert w["lines"][1] == "Now: read 1 of 2 device(s); waiting on s3 (12.5 s so far)."
        assert not any("Check now" in x for x in w["lines"])

    def test_a_page_without_the_live_channel_says_to_ask(self):
        w = self._js("window.captureWaitingWords(['r2'], null, 'disconnected')")
        assert w["live"] is False
        assert any("will not appear by itself: press Check now" in x for x in w["lines"])

    def test_an_announcement_with_no_job_open_does_nothing(self):
        assert self._js("window.capturePreviewHeard()") is True
