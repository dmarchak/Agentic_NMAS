"""P.3 step 12 (register B15): a rotation leaves a record that outlives the terminal.

s1, 2026-09-26: the rotation of an EXPOSED credential completed on the device and in the
store, and its persistence stopped; the stage lines existed only in a terminal scrollback,
unrecoverable twice in one incident (B2). Every rotation and persist now writes a row, never a
credential, which job health reads.

These tests were in tests/test_rotation_reports_the_boot_file.py, whose other classes tested
the lab's boot-file stages; C663 took those stages out of the persistence, and this class,
about the record, moved here unchanged.
"""

import json

from modules import job_health as J
from modules.nsot import credential_rotation as cr


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
                                      "persistence": [{"name": "device_startup_config",
                                                       "ok": False,
                                                       "error": "username admin privilege 15 "
                                                                "password 0 Hunter2Hunter2xyz"}]})
        raw = open(cr._rotation_record_path()).read()
        assert "Hunter2Hunter2xyz" not in raw
        assert json.loads(raw.splitlines()[-1])["failed_stage"] == "device_startup_config"

    def test_a_record_failure_never_breaks_the_rotation(self, monkeypatch, caplog):
        def _boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr("modules.config.open_secure", _boom)
        cr.record_outcome("persist", {"device": "s1", "state": cr.ROTATED_PERSISTED})
        assert any("COULD NOT RECORD" in r.getMessage() for r in caplog.records)
