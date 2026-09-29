"""The rotate screen's first piece: recovering a credential a rotation staged
and never cleared (7.3, built assuming a fourth failure mode exists).

The password is staged before the push, so a process that dies between the
push and the record (an app restart, which a deploy causes) leaves the device
on a password the inventory does not hold, the staged file its only copy, and
nothing that read the file: `ROTATED_NOT_RECORDED`'s remedy was a Python call.
Recovery asks the device, and removes nothing until the record it protects is
proven. The device side is a fake at `verify_new_credential`'s seam; the
staging file, the record and job health are real.
"""

import os
import threading

import pytest

from modules import job_health
from modules.nsot import credential_rotation as cr

STAGED = "Staged-N3w-Value-1234"
STORED = "Recorded-0ld-Value-99"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from modules import device

    list_dir = tmp_path / "lists" / "lab"
    repo = list_dir / "config_repo"
    repo.mkdir(parents=True)
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
    monkeypatch.setattr("modules.device.get_device_lists",
                        lambda: [{"name": "Lab", "filename": "lab"}])
    row = {"hostname": "r2", "ip": "192.0.2.12", "username": "admin",
           "device_type": "cisco_xe",
           "password": device.fernet.encrypt(STORED.encode()).decode(),
           "secret": device.fernet.encrypt(b"").decode()}
    monkeypatch.setattr("modules.device.load_saved_devices", lambda p: [dict(row)])
    monkeypatch.setattr(cr, "_csv_path_for", lambda ln: str(list_dir / "devices.csv"))
    commits = []
    state = {"commit_ok": True}

    def _commit(list_name, repo_, host, dev, username, privilege, password, new_hash,
                golden, actor, record="csv"):
        commits.append({"host": host, "password_is_staged": password == STAGED,
                        "privilege": privilege, "new_hash": new_hash, "record": record})
        return ({"ok": True, "commit": "abc123"} if state["commit_ok"]
                else {"ok": False, "error": "the store could not be written"})

    monkeypatch.setattr(cr, "_commit", _commit)
    monkeypatch.setattr(cr, "_current_golden", lambda repo_, h: "")
    cr.stage_plaintext(str(repo), "r2", STAGED)
    return {"repo": str(repo), "commits": commits, "state": state}


def _device(accepts):
    """A fake device that accepts exactly the passwords in *accepts*; a
    `None` in it makes every ask a local fault."""
    asked = []

    def verify(device, username, password, *, secret=None):
        from modules.nsot import device_ops

        asked.append({"held": device_ops.may_write(device["ip"]),
                      "which": "staged" if password == STAGED else
                               "stored" if password == STORED else "other"})
        if None in accepts:
            return {"ok": False, "attempted": False, "error": "OSError: no route"}
        if password in accepts:
            return {"ok": True, "attempted": True,
                    "config": "username admin privilege 15 secret 9 $9$salt$hash"}
        return {"ok": False, "attempted": True, "error": "NetmikoAuthenticationException"}
    return verify, asked


def _staged(lab):
    return os.path.exists(os.path.join(lab["repo"], cr.STAGING_REL, "r2.enc"))


class TestTheDeviceSettlesIt:
    def test_accepted_is_recorded_and_only_then_cleared(self, lab):
        verify, asked = _device({STAGED})
        out = cr.recover_staged("Lab", "r2", actor="op", via="test", verify=verify)
        assert out["state"] == cr.ROTATED_PENDING_PERSIST
        assert lab["commits"] == [{"host": "r2", "password_is_staged": True, "privilege": 15,
                                   "new_hash": "9 $9$salt$hash", "record": "csv"}]
        assert not _staged(lab), "cleared once the record was written"
        assert asked == [{"held": True, "which": "staged"}], "asked holding the device"

    def test_a_record_that_fails_keeps_the_staged_file(self, lab):
        lab["state"]["commit_ok"] = False
        verify, _asked = _device({STAGED})
        out = cr.recover_staged("Lab", "r2", actor="op", via="test", verify=verify)
        assert out["state"] == cr.ROTATED_NOT_RECORDED
        assert _staged(lab), "the only copy is kept until the record is written"

    def test_refused_but_the_recorded_one_works_means_it_never_landed(self, lab):
        verify, asked = _device({STORED})
        out = cr.recover_staged("Lab", "r2", actor="op", via="test", verify=verify)
        assert out["state"] == cr.STAGED_NEVER_APPLIED
        assert [a["which"] for a in asked] == ["staged", "stored"]
        assert lab["commits"] == [] and not _staged(lab)

    def test_refusing_both_changes_nothing_and_names_the_console(self, lab):
        verify, _asked = _device(set())
        out = cr.recover_staged("Lab", "r2", actor="op", via="test", verify=verify)
        assert out["state"] == cr.NEITHER_ACCEPTED and "console" in out["reason"]
        assert lab["commits"] == [] and _staged(lab)

    def test_a_device_that_cannot_be_asked_changes_nothing(self, lab):
        verify, _asked = _device({None})
        out = cr.recover_staged("Lab", "r2", actor="op", via="test", verify=verify)
        assert out["state"] == cr.RECOVERY_INCONCLUSIVE
        assert lab["commits"] == [] and _staged(lab)

    def test_nothing_staged_is_said(self, lab):
        cr.clear_staged(lab["repo"], "r2")
        verify, asked = _device({STAGED})
        out = cr.recover_staged("Lab", "r2", actor="op", via="test", verify=verify)
        assert out["state"] == cr.NOTHING_STAGED and asked == []

    def test_no_credential_reaches_the_result_or_the_record(self, lab):
        verify, _asked = _device({STAGED})
        out = cr.recover_staged("Lab", "r2", actor="op", via="test", verify=verify)
        assert STAGED not in str(out)
        recs = [r for r in cr.rotation_records() if r.get("device") == "r2"]
        assert recs and recs[-1]["via"] == "test" and STAGED not in str(recs)


class TestJobHealthNamesIt:
    def test_a_staged_file_nobody_holds_is_a_not_recorded_row(self, lab):
        (row,) = job_health.staged_rotation_rows()
        assert row["state"] == "not_recorded" and row["device"] == "r2"
        assert row["action"]["command"] == "nmas-rotation-recover r2 --list Lab"
        assert "only copy" in row["detail"]

    def test_a_device_mid_rotation_is_left_to_the_in_flight_panel(self, lab):
        from modules.nsot import device_ops

        held, done = threading.Event(), threading.Event()

        def _rotating():
            with device_ops.hold("Lab", "r2", "rotate", "op"):
                held.set()
                done.wait(10)

        t = threading.Thread(target=_rotating)
        t.start()
        try:
            assert held.wait(10)
            assert job_health.staged_rotation_rows() == []
        finally:
            done.set()
            t.join(10)

    def test_the_recovery_outcomes_read_as_rows(self):
        known = ({"r2"}, "")
        for state, expected in ((cr.STAGED_NEVER_APPLIED, "ok"), (cr.NOTHING_STAGED, "ok"),
                                (cr.NEITHER_ACCEPTED, "neither_accepted"),
                                (cr.RECOVERY_INCONCLUSIVE, "unknown")):
            (row,) = job_health.rotation_rows(
                records=[{"device": "r2", "state": state, "at": "t"}], known=known)
            assert row["state"] == expected, (state, row)

    def test_not_recorded_names_the_recovery_command(self):
        (row,) = job_health.rotation_rows(
            records=[{"device": "r2", "state": cr.ROTATED_NOT_RECORDED, "at": "t"}],
            known=({"r2"}, ""))
        assert "nmas-rotation-recover r2" in row["action"]["command"]


class TestTheCommand:
    def test_it_prints_the_state_and_never_a_credential(self, lab, monkeypatch, capsys):
        import importlib.machinery
        import importlib.util

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "scripts", "nmas-rotation-recover")
        loader = importlib.machinery.SourceFileLoader("nmas_rotation_recover", path)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        verify, _asked = _device({STAGED})
        monkeypatch.setattr(cr, "verify_new_credential", verify)
        assert mod.main(["r2", "--list", "Lab"]) == 0
        out = capsys.readouterr().out
        assert "state: rotated_persistence_not_attempted" in out
        assert "Persist" in out and STAGED not in out
