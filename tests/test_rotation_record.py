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
                                                                "password 0 Hunter2Hunter2xyz"}]}, list_name="Default")
        raw = open(cr._rotation_record_path()).read()
        assert "Hunter2Hunter2xyz" not in raw
        assert json.loads(raw.splitlines()[-1])["failed_stage"] == "device_startup_config"

    def test_a_record_failure_never_breaks_the_rotation(self, monkeypatch, caplog):
        def _boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr("modules.config.open_secure", _boom)
        cr.record_outcome("persist", {"device": "s1", "state": cr.ROTATED_PERSISTED}, list_name="Default")
        assert any("COULD NOT RECORD" in r.getMessage() for r in caplog.records)


class TestARowNamesItsNetwork:
    """C361: a row named the device and no network, so History matched it by hostname alone,
    and a hostname in two networks drew each one's rotations on both pages."""

    @staticmethod
    def _drawn(network, device, monkeypatch, tmp_path):
        from modules import history_sources as H

        class Ref:
            name, repo_dir = network, str(tmp_path / network)
        return H.rotation({"ref": Ref, "device": device, "limit": 50})["events"]

    @staticmethod
    def _own_record(monkeypatch, tmp_path):
        from modules import config
        monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))

    def test_a_rotation_is_drawn_only_in_its_own_network(self, monkeypatch, tmp_path):
        self._own_record(monkeypatch, tmp_path)
        cr.record_outcome("rotate", {"device": "r1", "state": cr.ROTATED_PERSISTED,
                                     "steps": [{"name": "push", "ok": True}]}, list_name="Lab")
        assert json.loads(open(cr._rotation_record_path()).read().splitlines()[-1])["list"] == "Lab"
        assert len(self._drawn("Lab", "r1", monkeypatch, tmp_path)) == 1
        assert self._drawn("Branch", "r1", monkeypatch, tmp_path) == []

    def test_an_older_row_naming_no_network_is_matched_by_name_and_says_so(self, monkeypatch,
                                                                            tmp_path):
        self._own_record(monkeypatch, tmp_path)
        with open(cr._rotation_record_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": "2026-10-01T00:00:00Z", "phase": "rotate", "device": "r1",
                                 "state": cr.ROTATED_PERSISTED, "stages": []}) + "\n")
        (event,) = self._drawn("Branch", "r1", monkeypatch, tmp_path)
        assert "an older row naming no network" in event["detail"], event
