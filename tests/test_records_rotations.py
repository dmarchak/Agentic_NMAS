"""The rotation and save record on the records database (K31 part 2b: a line store, one file for the
installation), against a REAL PostgreSQL shaped as host step 6a makes it (tests/pg_instance.py;
skipped with its reason here, a failure in CI).

The rows are written by `credential_rotation.record_outcome`, as rotate, persist, recover and a
device's own save write them, and read back through `rotation_records()`, the read job health,
the credential-health reader, Needs attention, History and the scheduled rotation share.
"""

import logging
import os
import stat

import pytest

from modules import records_db, records_migrate as RM
from modules.nsot import credential_rotation as cr
from tests.test_records_restarts import db, pg  # noqa: F401 (the server and the settings)

STORE = "rotations"


def _record(n, phase="rotate", state=None):
    cr.record_outcome(phase, {"device": f"r{n}", "actor": "alex@example.com",
                              "state": state or cr.ROTATED_PERSISTED, "via": "device page",
                              "steps": [{"name": "push", "ok": True}]}, list_name="Default")
    return cr.rotation_records()[-1]


def _move():
    return RM.move(RM.plan(store=STORE)["fingerprint"], "alex@example.com", "access", store=STORE)


def test_it_is_a_line_store_kept_once_for_the_installation(db):
    st = RM.store_of(STORE)
    assert (st.qualified, st.per_network) == ("audit.rotation_lines", False)
    assert STORE in records_db.STORES and cr.rotation_record_files() == {}
    _record(1)
    assert cr.rotation_record_files() == {"": cr._rotation_record_path()}


def test_the_move_keeps_every_row_and_a_new_one_lands_in_the_table(db):
    _record(1), _record(2, phase="persist")
    before = cr.rotation_records()
    out = _move()
    assert out["ok"], out["steps"]
    assert db["values"]["records_store_rotations"] == "postgres"
    assert cr.rotation_records() == before
    assert stat.S_IMODE(os.stat(cr._rotation_record_path()).st_mode) == 0o400
    third = _record(3)
    assert cr.rotation_records() == before + [third] and third["list"] == "Default"
    assert len(open(cr._rotation_record_path()).read().splitlines()) == 2
    assert RM.check(store=STORE)["ok"]


def test_the_move_back_exports_what_was_written_since(db):
    _record(1)
    assert _move()["ok"]
    _record(2)
    moved = cr.rotation_records()
    back = RM.move_back(RM.plan(store=STORE)["fingerprint"], "alex@example.com", "access",
                        store=STORE)
    assert back["ok"], back["steps"]
    assert cr.rotation_records() == moved and len(moved) == 2


def test_a_line_that_does_not_parse_refuses_the_move_naming_it(db):
    """The file's own reader skips such a line (C1327); the move never copies around it."""
    _record(1)
    with open(cr._rotation_record_path(), "a", encoding="utf-8") as fh:
        fh.write("{torn\n")
    p = RM.plan(store=STORE)
    assert p["networks"][0]["unparsable"].startswith("line 2 is not JSON")
    with pytest.raises(RM.Refused, match="a file line is not JSON"):
        _move()
    assert db["values"]["records_store_rotations"] == "file"


class TestADatabaseThatDoesNotAnswer:
    def test_a_read_raises_as_an_unreadable_file_does(self, db):
        db["values"]["records_store_rotations"] = "postgres"
        db["values"]["records_db_port"] = 1
        with pytest.raises(OSError, match="the records database"):
            cr.rotation_records()

    def test_a_write_is_logged_as_not_recorded_and_never_falls_back(self, db, caplog):
        db["values"]["records_store_rotations"] = "postgres"
        db["values"]["records_db_port"] = 1
        with caplog.at_level(logging.ERROR):
            cr.record_outcome("rotate", {"device": "r1", "state": cr.ROTATED_PERSISTED},
                              list_name="Default")
        assert any("COULD NOT RECORD" in r.getMessage() for r in caplog.records)
        assert not os.path.exists(cr._rotation_record_path())

    def test_history_says_the_record_could_not_be_read(self, db):
        import types

        from modules import history_sources as H

        db["values"]["records_store_rotations"] = "postgres"
        db["values"]["records_db_port"] = 1
        ref = types.SimpleNamespace(name="Default", repo_dir="/nonexistent")
        got = H.rotation({"ref": ref, "device": "r1", "members": None, "limit": 5})
        assert got["events"] == [] and "could not be read" in got["errors"][0]
