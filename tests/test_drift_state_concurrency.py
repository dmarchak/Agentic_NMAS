"""Drift state and drift runs, across processes (CONCURRENCY_AUDIT R19).

One RLock in one function guarded the state file; `_save_state` was an unlocked merge and
`_write_state` truncated in place; a torn read adopted the installation-wide legacy file and
wrote it over the list's state (it could drop `disabled`); and Check now never set the
scheduler's flag, so two people pressing it, or Check now during the scheduled run, ran two
full passes and could queue two items for one device.

Measured here:

- two PROCESSES merging into one list's state lose no key;
- an unreadable state is never empty and never the legacy file: a save refuses with the file
  byte-identical and a `.corrupt-` copy beside it, the scheduler reads it as paused, and the
  status says "unreadable" with why;
- one run per list at a time, across processes: a second run raises `DriftRunning` naming
  the first (who started it, from which process), Check now answers 409 naming it, and the
  status shows the other process's run as running;
- a run whose result cannot be recorded says so, never in the success colour;
- the shipped panel draws an unreadable state and a refusal.
"""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from modules import config
    from modules import drift_check as D

    list_dir = tmp_path / "lab"
    list_dir.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "R19lab")
    monkeypatch.setattr("modules.device.get_current_device_list",
                        lambda: ("R19lab", str(list_dir / "devices.csv")))
    legacy = os.path.join(config.DATA_DIR, "drift_state.json")
    assert not os.path.exists(legacy)
    yield {"D": D, "dir": list_dir, "state": str(list_dir / "drift_state.json"),
           "legacy": legacy}
    if os.path.exists(legacy):
        os.remove(legacy)


def _child(tmp_path, body, *args):
    """A second PROCESS on the same store and list folder."""
    from modules import config

    script = tmp_path / "child.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {ROOT!r})\n"
        "import modules.config as C\n"
        "C.get_list_data_dir = lambda name: sys.argv[1]\n"
        "C.get_current_list_name = lambda: 'R19lab'\n"
        "from modules import drift_check as D\n" + body, encoding="utf-8")
    return subprocess.Popen([sys.executable, str(script), *args],
                            env=dict(os.environ, NMAS_DATA_DIR=config.DATA_DIR),
                            stdout=subprocess.PIPE, text=True)


class TestTwoProcessesLoseNothing:
    def test_concurrent_merges_keep_every_key(self, lab, tmp_path):
        body = ("tag = sys.argv[2]\n"
                "for i in range(30):\n"
                "    D._save_state({f'{tag}{i}': i}, 'R19lab')\n")
        procs = [_child(tmp_path, body, str(lab["dir"]), tag) for tag in ("a", "b")]
        assert [p.wait(120) for p in procs] == [0, 0]
        state = json.load(open(lab["state"], encoding="utf-8"))
        assert {f"{t}{i}" for t in "ab" for i in range(30)} <= set(state)


class TestAnUnreadableStateIsNeverEmpty:
    def test_a_save_refuses_and_keeps_the_file_and_the_legacy_is_not_adopted(self, lab):
        D = lab["D"]
        with open(lab["legacy"], "w", encoding="utf-8") as fh:
            json.dump({"disabled": False, "last_check_ts": 1}, fh)
        with open(lab["state"], "w", encoding="utf-8") as fh:
            fh.write('{"disabled": true, "last_resu')          # torn
        before = open(lab["state"], "rb").read()
        assert D.UNREADABLE in D._load_state("R19lab")
        with pytest.raises(D.DriftStateUnreadable):
            D._save_state({"last_check_ts": 2}, "R19lab")
        assert open(lab["state"], "rb").read() == before
        assert any(n.startswith("drift_state.json.corrupt-") for n in os.listdir(lab["dir"]))
        assert D._is_disabled() is True                          # paused, never run
        status = D.DriftChecker().status()
        assert status["state"] == "unreadable" and "could not be read" in status["unreadable"]

    def test_an_absent_state_still_adopts_the_legacy_file_once(self, lab):
        D = lab["D"]
        with open(lab["legacy"], "w", encoding="utf-8") as fh:
            json.dump({"disabled": True}, fh)
        assert D._load_state("R19lab")["disabled"] is True
        assert json.load(open(lab["state"], encoding="utf-8"))["migrated_from"]


class TestOneRunAtATime:
    def test_a_second_run_is_refused_naming_the_first(self, lab, tmp_path):
        D = lab["D"]
        body = ("import time\n"
                "with D._OneRun(D._run_lock_path('R19lab'), 'scheduled'):\n"
                "    print('held', flush=True)\n"
                "    time.sleep(30)\n")
        child = _child(tmp_path, body, str(lab["dir"]))
        try:
            assert child.stdout.readline().strip() == "held"
            with pytest.raises(D.DriftRunning) as exc:
                D.run_drift_check("manual")
            assert exc.value.holder["triggered_by"] == "scheduled"
            assert exc.value.holder["pid"] == child.pid
            assert "did not start" in str(exc.value)
            status = D.DriftChecker().status()
            assert status["state"] == "running" and status["running_run"]["pid"] == child.pid

            import app as nmas
            r = nmas.app.test_client().post("/drift/check/sync")
            assert r.status_code == 409
            assert r.get_json()["running_run"]["pid"] == child.pid
        finally:
            child.kill()
            child.wait(10)
        assert D.running_now("R19lab") is None                  # the kernel let go

    def test_a_finished_run_leaves_the_lock_free(self, lab):
        D = lab["D"]
        with D._OneRun(D._run_lock_path("R19lab"), "manual"):
            assert D.running_now("R19lab")["triggered_by"] == "manual"
        assert D.running_now("R19lab") is None


class TestARunWhoseResultCannotBeRecorded:
    def test_check_now_says_so(self, lab, monkeypatch):
        D = lab["D"]
        monkeypatch.setattr(D, "_run_drift_check",
                            lambda triggered_by="", list_name="": {"ok": True, "summary": "checked 1 of 1",
                                                     "drifted": 0})
        with open(lab["state"], "w", encoding="utf-8") as fh:
            fh.write("{torn")
        import app as nmas
        r = nmas.app.test_client().post("/drift/check/sync")
        body = r.get_json()
        assert r.status_code == 500 and body["ok"] is False
        assert "not recorded" in body["error"] and body["summary"] == "checked 1 of 1"


def _sync(source):
    """The shipped function with its asynchrony stripped, and ONLY that (the stub fetch
    answers plainly), as test_agent_panel_renders does; no branch is touched."""
    import re
    stripped = re.sub(r"\bawait\s+", "", source.replace("async function", "function"))
    assert stripped != source and "await " not in stripped
    return stripped


class TestTheShippedPanel:
    """`loadDriftStatus` and `runDriftCheck` EXECUTED in duktape against the routes' REAL
    answers, with a stub page."""

    DOM = ("var __els = {driftStatusBadge: {className: '', textContent: '', title: ''},"
           " driftLastRun: {innerHTML: '', textContent: ''}};\n"
           "function __el(id) { return __els[id] || null; }\n"
           "var document = {getElementById: __el};\n"
           "var console = {error: function () {}};\n"
           "var __toasts = [];\n"
           "function showToast(m, kind) { __toasts.push([m, kind]); }\n"
           "function loadApprovalsTab() {}\n")

    def _run(self, call, payload, status=200):
        import dukpy

        from tests.payload_render import lift, shipped
        src = shipped("index.4.js")
        js = (self.DOM + f"var __payload = {json.dumps(payload)};\n"
              f"function fetch(u) {{ return {{ok: {str(status < 400).lower()}, "
              f"status: {status}, json: function () {{ return __payload; }}}}; }}\n"
              + lift(src, "_esc") + "\n" + _sync(lift(src, "loadDriftStatus")) + "\n"
              + _sync(lift(src, "runDriftCheck")) + "\n" + call + ";\n"
              "JSON.stringify({badge: __els.driftStatusBadge, last: __els.driftLastRun.innerHTML,"
              " toasts: __toasts});")
        return json.loads(dukpy.evaljs(js))

    def test_an_unreadable_state_is_drawn_paused_never_not_run_yet(self, lab):
        with open(lab["state"], "w", encoding="utf-8") as fh:
            fh.write("{torn")
        import app as nmas
        payload = nmas.app.test_client().get("/drift/status").get_json()
        assert payload["state"] == "unreadable"
        got = self._run("loadDriftStatus()", payload)
        assert got["badge"]["textContent"] == "State unreadable"
        assert "bg-danger" in got["badge"]["className"]
        assert "Scheduled checks paused" in got["last"] and "could not be read" in got["last"]

    def test_a_run_another_process_holds_is_drawn_running_with_who(self, lab, tmp_path):
        D = lab["D"]
        child = _child(tmp_path, "import time\nwith D._OneRun(D._run_lock_path('R19lab'),"
                                 " 'scheduled'):\n    print('held', flush=True)\n"
                                 "    time.sleep(30)\n", str(lab["dir"]))
        try:
            assert child.stdout.readline().strip() == "held"
            import app as nmas
            client = nmas.app.test_client()
            payload = client.get("/drift/status").get_json()
            refused = client.post("/drift/check/sync")
            refusal = refused.get_json()
        finally:
            child.kill()
            child.wait(10)
        got = self._run("loadDriftStatus()", payload)
        assert got["badge"]["textContent"] == "Running…"
        assert "scheduled" in got["badge"]["title"] and str(child.pid) in got["badge"]["title"]
        toasted = self._run("runDriftCheck()", refusal, status=refused.status_code)["toasts"]
        assert toasted and "already running" in toasted[0][0] and toasted[0][1] == "warning"

    def test_an_unrecorded_run_is_never_drawn_green(self, lab, monkeypatch):
        D = lab["D"]
        monkeypatch.setattr(D, "_run_drift_check",
                            lambda triggered_by="", list_name="": {"ok": True, "summary": "checked 1 of 1",
                                                     "drifted": 0})
        with open(lab["state"], "w", encoding="utf-8") as fh:
            fh.write("{torn")
        import app as nmas
        r = nmas.app.test_client().post("/drift/check/sync")
        toasts = self._run("runDriftCheck()", r.get_json(), status=r.status_code)["toasts"]
        assert toasts and toasts[0][1] == "danger" and "not recorded" in toasts[0][0]
