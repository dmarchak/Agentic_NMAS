"""A drift item that no longer stands closes itself, saying why (the
operator, 2026-10-01: r1, r2 and r4 each waited with "Config drift detected
-- 55 changed lines", created before C302 stopped counting a regenerated
certificate, and a Save All would not have closed them, since a capture
closed only the items it was handed from the queue).

Two rules, one mechanism (`approval_queue.supersede_drift`, recorded as
`withdrawn` with its reason and what withdrew it):

* a drift run that finds the device at its golden under the rules in force
  withdraws an older item for it (r2's REAL config, its certificate
  regenerated: the C302 case);
* every golden recorded through `save_golden()`, the one place every capture
  commits, withdraws older items for the devices it recorded, changed or
  measured unchanged, in ITS list's queue.
"""

import time

import pytest

from modules import approval_queue as Q
from tests.test_capture import _apply, _hash, _preview, build_capture_lab
from tests.test_intent_match import R2


def _item(host, ip="203.0.113.12", list_name=""):
    """A pending drift item, as the drift check queues one."""
    entries = Q._load_queue(list_name)
    entry_id = f"item-{host}-{len(entries)}"
    entries.append({"id": entry_id, "action_type": Q.DRIFT_ACTION, "status": "pending",
                    "created_at": "an hour ago", "created_ts": time.time() - 3600,
                    "device_ip": ip, "device_hostname": host,
                    "description": f"Config drift detected on {host} -- 55 changed lines",
                    "diff": "", "context": "", "action_params": {}, "resolved_at": None})
    Q._save_queue(entries, list_name)
    return entry_id


def _status(entry_id, list_name=""):
    return next(e for e in Q._load_queue(list_name) if e["id"] == entry_id)


@pytest.fixture
def cap(tmp_path, monkeypatch):
    return build_capture_lab(monkeypatch, tmp_path)


class TestWithdraw:
    def test_it_records_why_and_by_what(self, cap):
        i = _item("r2", list_name="Lab")
        assert Q.withdraw(i, "no longer stands", "drift check", list_name="Lab")["ok"]
        e = _status(i, "Lab")
        assert (e["status"], e["withdrawn_reason"], e["withdrawn_by"]) == \
            ("withdrawn", "no longer stands", "drift check")

    def test_a_withdrawal_without_its_reason_is_refused(self, cap):
        i = _item("r2", list_name="Lab")
        assert not Q.withdraw(i, "", "drift check", list_name="Lab")["ok"]
        assert _status(i, "Lab")["status"] == "pending"

    def test_only_older_pending_drift_items_for_the_named_devices(self, cap):
        old = _item("r2", list_name="Lab")
        other = _item("r9", ip="203.0.113.19", list_name="Lab")
        assert Q.supersede_drift(["r2"], "why", "who", list_name="Lab",
                                 before_ts=time.time() - 7200) == []     # created after
        assert Q.supersede_drift(["r2"], "why", "who", list_name="Lab") == [old]
        assert _status(other, "Lab")["status"] == "pending"


class TestACaptureSupersedes:
    def test_a_recorded_golden_withdraws_the_older_item(self, cap):
        i = _item("r2", list_name="Lab")
        cap["running"]["r2"] = cap["captured"].replace(
            "hostname r2\n", "hostname r2\nip domain lookup source-interface Loopback0\n")
        d = _preview(cap)
        _apply(cap, {"r2": _hash(d)})
        e = _status(i, "Lab")
        assert e["status"] == "withdrawn"
        assert e["withdrawn_reason"].startswith("superseded by commit ")
        assert "a newer golden records the device" in e["withdrawn_reason"]

    def test_a_capture_that_finds_it_unchanged_withdraws_it_too(self, cap):
        from modules.nsot.repo import GoldenItem, save_golden
        i = _item("r2", list_name="Lab")
        out = save_golden("Lab", [GoldenItem("r2", cap["captured"], "203.0.113.12",
                                             platform="cisco_iosxe")],
                          source="capture", actor="person@example.com", allow_new=False,
                          baseline=False)
        assert out["ok"] and out["unchanged"] == ["r2"]
        e = _status(i, "Lab")
        assert e["status"] == "withdrawn" and e["withdrawn_by"] == "person@example.com"


@pytest.fixture
def drift(monkeypatch, tmp_path):
    from modules import drift_check

    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    from tests.test_self_signed_certificate_label import _regenerated

    r2 = open(R2, encoding="utf-8").read()
    devices = [{"hostname": "r2", "ip": "203.0.113.12", "username": "u", "password": "p",
                "device_type": "cisco_xe"}]
    running = {"203.0.113.12": _regenerated(r2)}
    monkeypatch.setattr("modules.device.get_current_device_list", lambda: ("lab", "lab.csv"))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path: list(devices))
    monkeypatch.setattr("modules.ai_assistant._golden_record",
                        lambda ip: {"text": r2, "path": "", "commit": "", "source": "",
                                    "refused": ""})
    monkeypatch.setattr("modules.connection.get_persistent_connection",
                        lambda dev, pool, lock: dev["ip"])
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, cmd: running[conn])
    return {"module": drift_check, "running": running, "r2": r2}


class TestADriftRunUnderTheCurrentRules:
    def test_a_certificate_only_device_s_old_item_is_withdrawn(self, drift):
        # The C302 case: the item was queued when a regenerated certificate
        # counted; today's rules find r2 at its golden.
        i = _item("r2")
        r = drift["module"].run_drift_check("test")
        assert r["clean"] == 1
        e = _status(i)
        assert e["status"] == "withdrawn" and e["withdrawn_by"] == "drift check"
        assert "found r2 at its golden under the current rules" in e["withdrawn_reason"]

    def test_a_device_still_drifted_keeps_its_item(self, drift, monkeypatch):
        monkeypatch.setattr("modules.approval_queue.add_approval", lambda **kw: {"ok": True})
        i = _item("r2")
        drift["running"]["203.0.113.12"] = drift["r2"].replace(
            "hostname r2\n", "hostname r2\nip domain lookup source-interface Loopback0\n")
        assert drift["module"].run_drift_check("test")["drifted"] == 1
        assert _status(i)["status"] == "pending"


class TestARecordedGoldenAnswersTheDriftRow:
    """The operator, 2026-10-01: five Critical "has drifted from its golden"
    rows from the 23:40 run stood after Save All recorded those devices at
    23:52. Recording a golden answers the stored run's row for the device,
    saying by what; the next run measures again."""

    def _plant_run(self, cap):
        from modules import drift_check as D
        D._save_state({"last_check_ts": time.time() - 720, "last_result": {
            "ok": True, "inventory": 2, "checked": 2, "drifted": 2, "clean": 0,
            "drifted_devices": [{"hostname": "r2", "diff_lines": 23},
                                {"hostname": "r9", "diff_lines": 4}],
            "skipped": [], "errors": [], "summary": "Drift detected on 2 device(s).",
            "timestamp": "2026-10-01 23:40:00", "triggered_by": "scheduled"}}, "Lab")

    def test_a_capture_moves_the_device_to_clean_and_says_why(self, cap):
        from modules import attention as A
        from modules import drift_check as D

        self._plant_run(cap)
        _grown = cap["captured"].replace(
            "hostname r2\n", "hostname r2\nip domain lookup source-interface Loopback0\n")
        cap["running"]["r2"] = _grown
        d = _preview(cap)
        _apply(cap, {"r2": _hash(d)})
        last = D._load_state("Lab")["last_result"]
        assert [x["hostname"] for x in last["drifted_devices"]] == ["r9"]
        assert (last["drifted"], last["clean"]) == (1, 1)
        assert last["answered"][0]["hostname"] == "r2"
        assert last["answered"][0]["why"].startswith("recorded by commit ")
        assert "Since this run: r2 at its golden" in last["summary"]
        res = A.drift_source(status=lambda: {"list": "Lab", "last_ts": time.time() - 720,
                                             "last_run": last})
        drifted = [r["devices"] for r in res["rows"] if "has drifted" in r["what"]]
        assert drifted == [["r9"]]

    def test_no_stored_run_is_left_alone(self, cap):
        from modules import drift_check as D
        assert D.answer_by_golden("Lab", ["r2"], "x") == []
