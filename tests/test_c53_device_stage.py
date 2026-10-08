"""Register C53: the device's OWN startup config carries the credential NMAS
holds. The CLI rotation chain now saves on the device first, and an hourly
read-only job asks every device. Measured on the fleet 2026-09-27: s1 booted
the credential the terminal had exposed, while its boot FILE read SAFE.
Documentation addresses throughout; no value is ever printed."""

import importlib.machinery
import importlib.util
import json
import os

import pytest

from modules import job_health
from modules.nsot import credential_rotation as cr
from modules.nsot import onboard, startup_check

RUN = "username admin privilege 15 secret 9 $9$AbCdEfGh$SaltedHashValue"
OLD = "username admin privilege 15 secret 9 $9$ZzZzZzZz$ExposedHashValue"


# ── the pure judgement, shared by the save path and the job ─────────────────

class TestStartupCarries:
    def test_carries(self):
        assert onboard.startup_carries(f"hostname x\n{RUN}\n", RUN)["state"] == "persisted"

    def test_the_old_credential_is_not_carried(self):
        """s1's state exactly: the startup config held the EXPOSED line."""
        out = onboard.startup_carries(f"hostname x\n{OLD}\n", RUN)
        assert out["state"] == "not_persisted" and "secret 9 <value>" in out["detail"]
        assert "SaltedHashValue" not in repr(out) and "ExposedHashValue" not in repr(out)

    def test_no_startup_config(self):
        out = onboard.startup_carries("startup-config is not present\n", RUN)
        assert out["state"] == "not_persisted" and "NO startup config" in out["detail"]

    def test_no_username_line_is_unknown_not_a_pass(self):
        assert onboard.startup_carries(f"{RUN}\n", "")["state"] == "unknown"


class _Conn:
    def __init__(self, startup):
        self.startup, self.saved = startup, False

    def enable(self):
        pass

    def save_config(self):
        self.saved = True

    def send_command(self, cmd, **kw):
        return self.startup if cmd == "show startup-config" else RUN

    def disconnect(self):
        pass


def test_the_check_is_read_only():
    conn = _Conn(f"{OLD}\n")
    out = onboard.check_startup("192.0.2.1", "admin", "x", "x", "cisco_ios",
                                connect=lambda **kw: conn)
    assert out["state"] == "not_persisted" and conn.saved is False


# ── the CLI chain saves on the device FIRST ─────────────────────────────────

BASE = dict(mgmt_ip="192.0.2.21", username="admin", password="pw", hostname="s1",
            new_hash="9 $9$s$h", after_iso="2026-09-27T06:00:00+00:00",
            platform="cisco_ios", list_name="Default")


@pytest.fixture
def chain(monkeypatch):
    for name, value in (("run_sync", {"ok": True}),
                        ("verify_startup_file", {"ok": True, "matches": 1}),
                        ("verify_startup_applies", {"ok": True, "applies": True}),
                        ("verify_startup_carries_current", {"ok": True})):
        monkeypatch.setattr(cr, name, (lambda v: (lambda *a, **k: dict(v)))(value))
    monkeypatch.setattr(cr, "clab_target_for", lambda ln, h: {
        "host": "lab@192.0.2.10", "configs_dir": "labs/lab/configs",
        "launch_patch": "labs/lab/patches/x.py", "sync_script": "/usr/local/bin/clab-sync",
        "lab": "default"})
    return monkeypatch


def _persist():
    return cr.persist({"device": "s1", "state": cr.ROTATED_PENDING_PERSIST, "steps": []}, **BASE)


class TestTheChainSavesTheDevice:
    def test_the_device_stage_runs_first(self, chain):
        chain.setattr(cr, "save_on_device", lambda *a, **k: {"ok": True, "state": "persisted"})
        out = _persist()
        assert out["persistence"][0]["name"] == "device_startup_config"
        assert out["state"] == cr.ROTATED_PERSISTED

    def test_a_device_that_did_not_save_stops_the_chain_and_is_recorded(self, chain):
        later = []
        chain.setattr(cr, "save_on_device", lambda *a, **k: {
            "ok": False, "state": "not_persisted",
            "error": "the startup config does not carry username admin privilege 15 secret 9 <value>"})
        chain.setattr(cr, "run_sync", lambda *a, **k: later.append(1) or {"ok": True})
        out = _persist()
        assert out["state"] == cr.ROTATED_UNVERIFIED and later == []
        rec = [r for r in cr.rotation_records() if r.get("device") == "s1"][-1]
        assert rec["failed_stage"] == "device_startup_config"
        row = [r for r in job_health.rotation_rows() if r["unit"] == "rotation:s1"][0]
        assert "nmas-persist-native s1" in row["detail"]

    def test_the_stage_uses_the_platforms_driver(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(onboard, "persist_on_device", lambda ip, u, p, s, dt, **k: (
            seen.update(ip=ip, dt=dt) or {"ok": True, "state": "persisted", "detail": ""}))
        out = cr.save_on_device("192.0.2.21", "admin", "pw", "cisco_ios")
        assert out["ok"] and seen == {"ip": "192.0.2.21", "dt": "cisco_ios"}

    def test_an_unknown_platform_is_refused_not_guessed(self):
        assert not cr.save_on_device("192.0.2.21", "admin", "pw", "junos")["ok"]


# ── the job ─────────────────────────────────────────────────────────────────

INV = [("Default", {"hostname": "s1"}), ("Default", {"hostname": "r1"})]


class TestTheJob:
    @pytest.fixture(autouse=True)
    def _own_file(self, tmp_path, monkeypatch):
        """Its own results file: the shared test store is read by every other
        test's health(), and a row written here was read there (found by the
        full suite: a job-health headline counted this test's s1)."""
        monkeypatch.setattr(startup_check, "_path", lambda: str(tmp_path / "startup_check.json"))

    def test_it_records_every_device_and_counts_them(self):
        out = startup_check.run_check(
            inventory=INV, check=lambda row: {"state": "persisted" if row["hostname"] == "r1"
                                              else "not_persisted", "detail": "d"},
            clock=lambda: 1000.0)
        assert out["counts"] == {"persisted": 1, "not_persisted": 1}
        assert startup_check.read_results()["devices"] == out["devices"]
        assert oct(os.stat(startup_check._path()).st_mode & 0o777) == "0o600"

    def test_a_check_that_raised_is_unknown(self):
        def boom(row):
            raise OSError("timed out")
        out = startup_check.run_check(inventory=INV[:1], check=boom, write=False)
        assert out["devices"][0]["state"] == "unknown"

    def test_the_script_exit_codes(self, monkeypatch):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "scripts", "nmas-startup-check")
        loader = importlib.machinery.SourceFileLoader("nmas_startup_check", path)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(mod)
        # An unreadable device is not a failed run (the operator, 2026-10-01):
        # 2 only when the run read NO device.
        for counts, code in (({"persisted": 9}, 0), ({"persisted": 8, "not_persisted": 1}, 1),
                             ({"persisted": 8, "unknown": 1}, 0),
                             ({"persisted": 2, "unknown": 7}, 0),
                             ({"not_persisted": 1, "unknown": 8}, 1),
                             ({"unknown": 9}, 2), ({}, 2)):
            monkeypatch.setattr(startup_check, "run_check",
                                lambda c=counts: {"devices": [], "counts": c})
            assert mod.main() == code


class TestTheRows:
    def _rows(self, res, now=1000.0):
        return job_health.startup_rows(read=lambda: res, now=now)

    def test_never_run_is_left_to_the_unit_row(self):
        assert self._rows({}) == []
        assert "nmas-startup-check" in [j["unit"] for j in job_health.JOBS]

    def test_all_carrying_is_one_ok_row_naming_the_count(self):
        rows = self._rows({"at": 900.0, "devices": [
            {"list": "Default", "device": d, "state": "persisted", "detail": ""}
            for d in ("r1", "s1")]})
        assert [r["state"] for r in rows] == ["ok"] and "2 of 2" in rows[0]["detail"]

    def test_a_device_that_would_boot_the_wrong_credential_is_named(self):
        rows = self._rows({"at": 900.0, "devices": [
            {"list": "Default", "device": "s1", "state": "not_persisted", "detail": "old line"},
            {"list": "Default", "device": "r1", "state": "persisted", "detail": ""}]})
        assert [(r["unit"], r["state"]) for r in rows] == [("startup:Default/s1", "not_safe_to_reboot")]
        assert "nmas-persist-native s1 --list Default" in rows[0]["detail"]

    def test_could_not_ask_is_one_unread_row_never_the_critical_one(self):
        rows = self._rows({"at": 900.0, "devices": [
            {"list": "Default", "device": "s1", "state": "unknown", "detail": "timeout"}]})
        assert [r["state"] for r in rows] == ["unread"]

    def test_stale_results_are_not_ok(self):
        rows = self._rows({"at": 0.0, "devices": []}, now=4 * 3600.0)
        assert rows[0]["state"] == "stale"

    def test_an_unreadable_file_is_unknown(self):
        def boom():
            raise ValueError("Expecting value")
        assert job_health.startup_rows(read=boom)[0]["state"] == "unknown"


def test_a_run_that_found_no_devices_is_not_ok():
    """The floor: "0 of 0" would read as coverage."""
    rows = job_health.startup_rows(read=lambda: {"at": 900.0, "devices": []}, now=1000.0)
    assert rows[0]["state"] == "unknown" and "NO devices" in rows[0]["detail"]


# ── an unreadable device is not the critical finding (2026-10-01) ───────────

#: The host's 06:03 run, as job health read it: two devices read, seven not,
#: each reason in Netmiko's own words (journalctl -u nmas-startup-check).
_ECHO = ("could not ask: ReadTimeout: \n\nPattern not detected: "
         "'show\\\\ running\\\\-config\\\\ \\\\|\\\\ include\\\\ \\\\^username' in output.\n\n"
         "Things you might try to fix this:\n1. Explicitly set your pattern using the "
         "expect_string argument.\n2. Increase the read_timeout to a larger value.\n")
_0603 = {"at": 21600.0, "devices": (
    [{"list": "Default", "device": d, "state": "unknown", "detail": _ECHO, "since": 21600.0}
     for d in ("r1", "r2", "r3", "r4")]
    + [{"list": "Default", "device": "s1", "state": "unknown", "since": 21600.0,
        "detail": "could not ask: ReadTimeout: Pattern not detected: '(\\\\#|>)' in output."},
       {"list": "Default", "device": "s3", "state": "unknown", "since": 21600.0,
        "detail": "could not ask: ReadTimeout: Pattern not detected: 'terminal width 511'"},
       {"list": "Default", "device": "s4", "state": "unknown", "since": 21600.0,
        "detail": "could not ask: ReadTimeout: Pattern not detected: 'terminal\\\\ length\\\\ 0'"},
       {"list": "Default", "device": "r6", "state": "persisted", "detail": "", "since": 0.0},
       {"list": "Default", "device": "s2", "state": "persisted", "detail": "", "since": 0.0}])}


class TestAnUnreadableDeviceIsNotTheCriticalFinding:
    def test_the_0603_run_is_one_row_naming_the_seven_and_what_to_do(self):
        from modules import attention as A

        rows = job_health.startup_rows(read=lambda: _0603, now=21660.0)
        assert [r["state"] for r in rows] == ["unread"]
        row = rows[0]
        assert row["devices"] == ["r1", "r2", "r3", "r4", "s1", "s3", "s4"]
        assert "could not read 7 of 9 device(s) this hour" in row["headline"]
        assert row["since"] == 21600.0
        assert "next run" in row["action"]["label"]
        assert "Things you might try" not in row["detail"]
        assert "terminal width 511" in row["detail"]
        # Expected for a run, nothing to do yet (the operator, 2026-10-02):
        # job health's finding on Needs attention, never a row there.
        src = A.job_health_source(health=lambda: {"jobs": rows})
        assert src["rows"] == []
        assert "could not read 7 of 9 device(s) this hour" in src["checked"]

    def test_it_becomes_a_warning_once_it_persists_with_the_check_to_run(self):
        from modules import attention as A

        later = dict(_0603, at=21600.0 + job_health.UNREAD_PERSISTS_S)
        (row,) = job_health.startup_rows(read=lambda: later, now=later["at"] + 60)
        assert row["state"] == "unread_persisting"
        assert row["action"]["command"] == "python3 scripts/nmas-startup-check"
        (drawn,) = A.job_health_source(health=lambda: {"jobs": [row]})["rows"]
        assert drawn["level"] == "warning"

    def test_a_device_that_would_boot_the_wrong_credential_keeps_its_own_danger_row(self):
        from modules import attention as A

        res = {"at": 21600.0, "devices": _0603["devices"] + [
            {"list": "Default", "device": "r9", "state": "not_persisted", "detail": "old line",
             "since": 18000.0}]}
        rows = job_health.startup_rows(read=lambda: res, now=21660.0)
        assert sorted(r["state"] for r in rows) == ["not_safe_to_reboot", "unread"]
        drawn = A.job_health_source(health=lambda: {"jobs": rows})["rows"]
        danger = [r for r in drawn if r["level"] == "danger"]
        assert len(danger) == 1 and danger[0]["devices"] == ["r9"] and danger[0]["since"]

    def test_each_device_keeps_since_when_its_state_began(self, tmp_path, monkeypatch):
        monkeypatch.setattr(startup_check, "_path", lambda: str(tmp_path / "startup_check.json"))
        states = {"s1": "unknown", "r1": "persisted"}

        def check(row):
            return {"state": states[row["hostname"]], "detail": "d"}

        first = startup_check.run_check(inventory=INV, check=check, clock=lambda: 1000.0)
        second = startup_check.run_check(inventory=INV, check=check, clock=lambda: 4600.0)
        assert [d["since"] for d in first["devices"]] == [1000.0, 1000.0]
        assert [d["since"] for d in second["devices"]] == [1000.0, 1000.0]
        states["s1"] = "persisted"
        third = startup_check.run_check(inventory=INV, check=check, clock=lambda: 8200.0)
        assert [d["since"] for d in third["devices"]] == [8200.0, 1000.0]

    def test_a_reason_is_one_short_line_without_netmikos_advice(self):
        assert startup_check.brief(_ECHO).startswith("could not ask: ReadTimeout: Pattern")
        assert "Things you might try" not in startup_check.brief(_ECHO)
        assert len(startup_check.brief("x " * 400)) <= 200
