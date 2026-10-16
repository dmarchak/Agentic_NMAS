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
- the Drift checks card (Settings › Installation › Diagnostics) draws an unreadable state, a
  run another process holds with who, and a refusal naming it. Today's drift panel, whose
  shipped JavaScript these executed, and its /drift/status and /drift/check/sync left at 7.8
  (2026-10-15); the card is the screen that shows the same states now.
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
        """By the network that held it, Default (C487); the lab's folder stands in for it."""
        D = lab["D"]
        with open(lab["legacy"], "w", encoding="utf-8") as fh:
            json.dump({"disabled": True}, fh)
        assert D._load_state("Default")["disabled"] is True
        assert json.load(open(lab["state"], encoding="utf-8"))["migrated_from"]


@pytest.fixture
def card(lab, monkeypatch):
    """The Drift checks card (board F4) over the lab's one network, through the real routes:
    `get()` draws it, `check()` presses its Check now; each returns (status, the R19lab row's
    text without tags, the row's HTML)."""
    import re

    import app as nmas

    D = lab["D"]
    monkeypatch.setattr(D.DriftChecker, "networks", staticmethod(lambda: ["R19lab"]))
    client = nmas.app.test_client()

    def _row(r):
        html = r.get_data(as_text=True)
        m = re.search(r"<tr>\s*<td>R19lab</td>.*?</tr>", html, re.S)
        assert m, html[:500]
        return r.status_code, " ".join(re.sub(r"<[^>]+>", " ", m.group(0)).split()), m.group(0), html

    base = "/v2/settings/installation/diagnostics/drift"
    return {"get": lambda: _row(client.get(base)),
            "check": lambda: _row(client.post(f"{base}/R19lab/check",
                                              headers={"HX-Request": "true"}))}


def _holding(tmp_path, lab):
    """Another PROCESS holding R19lab's run lock, as the scheduled run does."""
    return _child(tmp_path, "import time\nwith D._OneRun(D._run_lock_path('R19lab'),"
                            " 'scheduled'):\n    print('held', flush=True)\n"
                            "    time.sleep(30)\n", str(lab["dir"]))


class TestOneRunAtATime:
    def test_a_second_run_is_refused_naming_the_first(self, lab, tmp_path, card, monkeypatch):
        D = lab["D"]
        child = _holding(tmp_path, lab)
        try:
            assert child.stdout.readline().strip() == "held"
            with pytest.raises(D.DriftRunning) as exc:
                D.run_drift_check("manual")
            assert exc.value.holder["triggered_by"] == "scheduled"
            assert exc.value.holder["pid"] == child.pid
            assert "did not start" in str(exc.value)
            status = D.DriftChecker().status()
            assert status["state"] == "running" and status["running_run"]["pid"] == child.pid

            # Check now (the card's; today's /drift/check/sync until 7.8) refuses, naming it.
            started = []
            from modules.drift_check import get_checker
            monkeypatch.setattr(get_checker(), "trigger", lambda name="": started.append(name))
            code, _text, _row, html = card["check"]()
            assert code == 409 and started == []
            assert "already running" in html and f"process {child.pid}" in html
            assert "by scheduled" in html
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
    def test_it_is_not_recorded_and_the_card_never_draws_it_done(self, lab, monkeypatch, card):
        """Check now runs in the background (the scheduler's `run_one`): a result its state
        cannot take is logged and not recorded, and the card draws the network unreadable,
        in the danger colour, never the run's summary as its last run."""
        D = lab["D"]
        monkeypatch.setattr(D, "_run_drift_check",
                            lambda triggered_by="", list_name="": {"ok": True, "summary": "checked 1 of 1",
                                                     "drifted": 0})
        with open(lab["state"], "w", encoding="utf-8") as fh:
            fh.write("{torn")
        result = D.DriftChecker().run_one("R19lab", "manual")
        assert result["summary"] == "checked 1 of 1"
        assert open(lab["state"], encoding="utf-8").read() == "{torn", "nothing written over it"
        code, text, row, _html = card["get"]()
        assert code == 200 and "unreadable" in text and "badge-danger" in row
        assert "checked 1 of 1" not in row and "badge-ok" not in row


class TestTheCard:
    """The Drift checks card over the states this module makes, through its real route."""

    def test_an_unreadable_state_is_drawn_unreadable_never_not_run_yet(self, lab, card):
        with open(lab["state"], "w", encoding="utf-8") as fh:
            fh.write("{torn")
        code, text, row, _html = card["get"]()
        assert code == 200 and "unreadable" in text and "could not be read" in text
        assert "badge-danger" in row
        # Last run unknown, never "never"; the schedule paused, never a next run due.
        assert "never" not in text and "unknown" in text and "paused" in text
        assert "Check now" not in text, "nothing can be recorded, so nothing is offered"

    def test_a_run_another_process_holds_is_drawn_running_with_who(self, lab, tmp_path, card):
        child = _holding(tmp_path, lab)
        try:
            assert child.stdout.readline().strip() == "held"
            code, text, _row, _html = card["get"]()
        finally:
            child.kill()
            child.wait(10)
        assert code == 200 and "checking now" in text
        assert "by scheduled" in text and f"process {child.pid}" in text
        assert "Check now" not in text
