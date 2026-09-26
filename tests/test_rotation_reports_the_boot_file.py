"""P.3 step 12 (register B15): a rotation reports success only when the
device's boot file is SAFE, names the stage that stopped it when it is not,
and leaves a record that outlives the terminal.

s1, 2026-09-26: the rotation of an EXPOSED credential completed on the device
and in the store, and the boot file kept the exposed password for 8.5 minutes
until a timer rewrote it. The persistence chain had stopped at its sync stage
(`clab_sync_script` empty since the 2026-09-23 erasure). The CLI said so, but
its message began "s1: ROTATED and committed", and the stage lines existed
only in a terminal scrollback, unrecoverable twice in one incident (B2).
"""

import json

import pytest

from modules import job_health as J
from modules.nsot import credential_rotation as cr

BASE = dict(mgmt_ip="203.0.113.21", username="admin", password="pw", hostname="s1",
            new_hash="9 $9$s$h", after_iso="2026-09-26T06:21:50+00:00",
            platform="cisco_ios", list_name="Default")


@pytest.fixture
def chain(monkeypatch):
    """Every stage passing; each test breaks the one it is about."""
    for name, value in (("update_oxidized_row", {"ok": True}),
                        ("reload_oxidized", {"ok": True, "mechanism": "rest_reload"}),
                        ("confirm_fetch", {"ok": True, "end": "x"}),
                        ("run_sync", {"ok": True}),
                        ("verify_startup_file", {"ok": True, "matches": 1}),
                        ("verify_startup_applies", {"ok": True, "applies": True}),
                        ("verify_startup_carries_current", {"ok": True})):
        monkeypatch.setattr(cr, name, (lambda v: (lambda *a, **k: dict(v)))(value))
    monkeypatch.setattr(cr, "clab_target_for", lambda ln, h: {
        "host": "lab@203.0.113.10", "configs_dir": "labs/lab/configs",
        "launch_patch": "labs/lab/patches/x.py", "sync_script": "/usr/local/bin/clab-sync",
        "lab": "default"})
    return monkeypatch


def _persist():
    return cr.persist({"device": "s1", "state": cr.ROTATED_PENDING_PERSIST, "steps": []}, **BASE)


class TestTheSyncStageBroken:
    """The operator's acceptance, measured on the case that happened."""

    def test_it_is_not_success_and_names_the_stage(self, chain):
        chain.setattr(cr, "run_sync", lambda **k: {"ok": False,
                      "error": "clab_sync_script is not configured"})
        out = _persist()
        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert "clab_sync" in cr.summarise(out)

    def test_the_message_leads_with_the_danger(self, chain):
        chain.setattr(cr, "run_sync", lambda **k: {"ok": False, "error": "x"})
        summary = cr.summarise(_persist())
        assert summary.startswith("s1: NOT SAFE TO REBOOT OR REDEPLOY"), summary
        assert summary.index("NOT SAFE") < summary.index("ROTATED and committed")

    def test_it_writes_a_durable_row_and_a_health_row(self, chain):
        chain.setattr(cr, "run_sync", lambda **k: {"ok": False, "error": "x"})
        _persist()
        rec = cr.rotation_records()[-1]
        assert rec["phase"] == "persist" and rec["device"] == "s1"
        assert rec["state"] == cr.ROTATED_UNVERIFIED and rec["failed_stage"] == "clab_sync"
        rows = {r["unit"]: r for r in J.rotation_rows()}
        assert rows["rotation:s1"]["state"] == "not_safe_to_reboot"
        assert "clab_sync" in rows["rotation:s1"]["detail"]


class TestSuccessMeansTheCheckersVerdict:
    def test_every_earlier_stage_passing_is_not_enough(self, chain):
        """The new hash is present and the form applies, and the checker still
        says the file does not carry the device's credential."""
        chain.setattr(cr, "verify_startup_carries_current", lambda *a, **k: {
            "ok": False, "reason": "the startup line is not the golden's"})
        out = _persist()
        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert out["persistence"][-1]["name"] == "startup_safe"
        assert out["persistence"][-1]["verdict"] == "NOT SAFE"

    def test_safe_is_success_and_clears_the_row(self, chain):
        chain.setattr(cr, "run_sync", lambda **k: {"ok": False, "error": "x"})
        _persist()
        chain.setattr(cr, "run_sync", lambda **k: {"ok": True})
        out = _persist()
        assert out["state"] == cr.ROTATED_PERSISTED
        assert "reads SAFE" in out["reason"]
        rows = {r["unit"]: r for r in J.rotation_rows()}
        assert rows["rotation:s1"]["state"] == "ok", "a later SAFE persist clears it"

    def test_the_chain_and_the_checker_share_one_function(self):
        import inspect
        assert "startup_safety(" in inspect.getsource(cr._persist)


class TestTheRecord:
    def test_rotate_records_its_outcome_too(self, monkeypatch):
        monkeypatch.setattr(cr, "_rotate", lambda ln, h, **k: {
            "state": cr.ROTATED_PENDING_PERSIST,
            "steps": [{"name": "verify_new_credential", "ok": True}]})
        cr.rotate("Default", "s1", confirmed_fingerprint="f")
        rec = cr.rotation_records()[-1]
        assert rec["phase"] == "rotate" and rec["device"] == "s1"
        rows = {r["unit"]: r for r in J.rotation_rows()}
        assert "NOT ATTEMPTED" in rows["rotation:s1"]["detail"]

    def test_it_never_holds_a_credential(self):
        cr.record_outcome("persist", {"device": "s1", "state": cr.ROTATED_UNVERIFIED,
                                      "persistence": [{"name": "startup_file", "ok": False,
                                                       "error": "username admin privilege 15 "
                                                                "password 0 Hunter2Hunter2xyz"}]})
        raw = open(cr._rotation_record_path()).read()
        assert "Hunter2Hunter2xyz" not in raw
        assert json.loads(raw.splitlines()[-1])["failed_stage"] == "startup_file"

    def test_a_record_failure_never_breaks_the_rotation(self, monkeypatch, caplog):
        def _boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr("modules.config.open_secure", _boom)
        cr.record_outcome("persist", {"device": "s1", "state": cr.ROTATED_PERSISTED})
        assert any("COULD NOT RECORD" in r.getMessage() for r in caplog.records)


class TestTheSyncScriptHasOneOwner:
    UNIT = "LoadState=loaded\nExecStart={ path=/home/u/bin/clab-sync ; argv[]=/home/u/bin/clab-sync }\n"

    def _row(self, setting, out=None, rc=0):
        return J.sync_owner_rows(run=lambda cmd: (rc, self.UNIT if out is None else out),
                                 get=lambda k, d=None: setting)[0]

    def test_empty_names_what_the_timer_runs(self):
        row = self._row("")
        assert row["state"] == "unset_guard" and "/home/u/bin/clab-sync" in row["detail"]

    def test_a_mismatch_names_both(self):
        row = self._row("/opt/other")
        assert row["state"] == "mismatch"
        assert "/opt/other" in row["detail"] and "/home/u/bin/clab-sync" in row["detail"]

    def test_the_same_path_is_ok(self):
        assert self._row("/home/u/bin/clab-sync")["state"] == "ok"

    def test_not_installed_and_unknown_are_not_ok(self):
        assert self._row("/x", out="LoadState=not-found\n")["state"] == "not_installed"
        assert self._row("/x", out="", rc=1)["state"] == "unknown"


class TestHealthCarriesThem:
    """Found by a control that passed: rotation_rows() was tested and nothing
    asserted that health(), which nmas-jobs and /jobs/health read, calls it."""

    def test_an_unsafe_rotation_is_a_not_ok_row_in_health(self):
        cr.record_outcome("persist", {"device": "s1", "state": cr.ROTATED_UNVERIFIED,
                                      "persistence": [{"name": "clab_sync", "ok": False}]})
        unit = "LoadState=loaded\nExecStart={ path=/b/clab-sync ; }\n"
        h = J.health(0, run=lambda cmd: (0, unit) if "clab-sync.service" in cmd
                     and "ExecStart" in cmd else (1, ""), images=[], settings=[])
        assert "rotation:s1" in h["not_ok"], h["not_ok"]
        assert any(j["unit"] == "clab-sync-owner" for j in h["jobs"])
