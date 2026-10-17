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


BOOT = "Bootstrap-Pass-2345678"
BOOT_ADDR = "192.0.2.66"


@pytest.fixture
def pending(lab, tmp_path, monkeypatch):
    """C1159: a pending ZTP onboarding, s6, as Create leaves it: a manifest
    entry with `onboarded_at` and no `verified_at`, the bootstrap credential
    staged (`onboard.stage_bootstrap_credential`, the rotation's store) and
    held as the device override at its reserved address."""
    from modules import credentials
    from modules.nsot import manifest as M
    from modules.nsot import onboard

    monkeypatch.setattr("modules.credentials._FILE", str(tmp_path / "creds.json"))
    M.upsert_device(lab["repo"], "uid:s6", "s6", pending=True, address_source="ztp",
                    mgmt_mac="02:00:00:00:00:66", reserved_address=BOOT_ADDR)
    credentials.set_device_override(BOOT_ADDR, "nmas", BOOT, BOOT)
    onboard.stage_bootstrap_credential(lab["repo"], "s6", BOOT)
    return lab


class TestAPendingOnboardingIsNotARotation:
    """C1159 (W4, 2026-10-17): a pending onboarding's staged bootstrap credential
    read as Needs attention's CRITICAL "rotation-staged … was rotated and not
    recorded", whose advice said not to reboot, for the whole of the boot the
    onboarding needs. It is said as what it is: expected until Verify or
    Abandon clears it, under What was checked, never a row. A rotation's staged
    credential (r2, the fixture's) stays the row it is."""

    @staticmethod
    def _by_device():
        return {r["device"]: r for r in job_health.staged_rotation_rows(holder=lambda l, h: None)}

    def test_it_reads_as_the_onboardings_own_and_the_rotation_stays(self, pending):
        rows = self._by_device()
        s6 = rows["s6"]
        assert s6["state"] == "onboarding_staged", s6
        assert s6["unit"] == "onboarding-staged:Lab/s6"
        text = " ".join(str(s6.get(k, "")) for k in ("what", "detail", "headline"))
        assert "rotated" not in text and "reboot" not in text, text
        assert "Verify or Abandon" in s6["detail"], s6
        assert BOOT not in str(s6)
        assert rows["r2"]["state"] == "not_recorded"                  # the control

    def test_needs_attention_says_it_under_what_was_checked_not_as_a_row(self, pending):
        from modules import attention

        src = attention.job_health_source(
            health=lambda: {"jobs": job_health.staged_rotation_rows(holder=lambda l, h: None)})
        assert [r["id"] for r in src["rows"]] == ["job_health:rotation-staged:Lab/r2"], \
            src["rows"]
        assert "s6" in src["checked"] and "Verify or Abandon" in src["checked"], src["checked"]

    def test_a_verify_rotation_that_died_still_reads_as_a_rotation(self, pending):
        """Control: Verify's rotation stages its NEW password over the bootstrap
        one; a process that dies before the record leaves a staged value the
        held override is not, and that IS a rotation not recorded."""
        cr.stage_plaintext(pending["repo"], "s6", "Rotated-N3w-Value-5678")
        assert self._by_device()["s6"]["state"] == "not_recorded"

    def test_a_promoted_device_reads_as_a_rotation(self, pending):
        """Control: only a PENDING onboarding's staged credential is its own; a
        device Verify promoted (`verified_at` set) has no bootstrap left."""
        from modules.nsot import manifest as M

        M.mark_verified(pending["repo"], "uid:s6", actor="op")
        assert self._by_device()["s6"]["state"] == "not_recorded"


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
