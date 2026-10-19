"""Needs attention's acknowledgements on the records database (K31 part 2b: the second line
store, one file for the installation), against a REAL PostgreSQL shaped as host step 6a makes it
(tests/pg_instance.py; skipped with its reason here, a failure in CI).

The acknowledgements are written by the module's own `record()`, as Needs attention's
Acknowledge writes them, a band acknowledgement (C433) among them.
"""

import os
import stat

import pytest

from modules import acknowledgements as ACK
from modules import records_db, records_migrate as RM
from tests.test_records_receipts import pg  # noqa: F401 (the module's real server)

STORE = "acknowledgements"


@pytest.fixture
def db(pg, tmp_path, monkeypatch):  # noqa: F811
    """The settings pointed at the real server, every store on files; the data folder this
    test's own; the audit schema dropped first."""
    from tests import pg_instance

    values = {"records_db_host": "127.0.0.1", "records_db_port": pg.port,
              "records_db_name": "mercury", "records_db_user": "mercury",
              "records_store_receipts": "file", "records_store_acknowledgements": "file"}
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: values.get(key, default))
    monkeypatch.setattr("modules.secrets_store.get_secret",
                        lambda key, default="": pg_instance.MERCURY_PW
                        if key == "records_db_password" else default)
    monkeypatch.setattr("modules.secrets_store.is_set", lambda key: True)

    def write_settings(changes, actor=""):
        values.update(changes)
        return {"ok": True, "error": ""}
    monkeypatch.setattr("modules.settings_schema.write_settings", write_settings)
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
    with pg.connect() as c:
        c.execute("drop schema if exists audit cascade")
    return {"values": values, "pg": pg}


def _ack(n, band=None):
    return ACK.record(f"restarts:Default:r{n}", f"2026-10-1{n}T00:00:00Z",
                      why="a planned reload during the maintenance window", by="alex@example.com",
                      verified="access", kind="restarts/unplanned", what=f"r{n} restarted",
                      devices=[f"r{n}"], **({"band": band, "value": 1.5} if band else {}))


def _move():
    return RM.move(RM.plan(store=STORE)["fingerprint"], "alex@example.com", "access",
                   store=STORE)


class TestTheStore:
    def test_it_is_a_line_store_kept_once_for_the_installation(self, db):
        st = RM.store_of(STORE)
        assert (st.table, st.per_network, st.qualified) == (
            "acknowledgement_lines", False, "audit.acknowledgement_lines")
        assert STORE in records_db.STORES and ACK.files() == {}
        _ack(1)
        assert ACK.files() == {"": ACK._path()}

    def test_the_preview_counts_the_installation_s_one_file(self, db):
        _ack(1), _ack(2, band=2.0)
        p = RM.plan(store=STORE)
        assert p["db"]["ok"] and p["backend"] == "file" and p["words"] == "Acknowledgements"
        (row,) = p["networks"]
        assert (row["network"], row["lines"], row["rows"], row["copied"]) == ("", 2, 2, 0)


class TestMovedAndBack:
    def test_the_move_keeps_every_acknowledgement_and_new_ones_land_in_the_table(self, db):
        before = [_ack(1), _ack(2, band=2.0)]
        out = _move()
        assert out["ok"], out["steps"]
        assert db["values"]["records_store_acknowledgements"] == "postgres"
        assert db["values"]["records_store_receipts"] == "file", "only this store switched"
        assert ACK.read() == {"state": "ok", "rows": before}
        mode = stat.S_IMODE(os.stat(ACK._path()).st_mode)
        assert mode == 0o400, oct(mode)
        third = _ack(3)
        assert ACK.read()["rows"] == before + [third]
        assert len(open(ACK._path()).read().splitlines()) == 2, "the file is not written"
        assert RM.check(store=STORE)["ok"]

    def test_the_move_back_exports_what_was_written_since(self, db):
        before = [_ack(1)]
        assert _move()["ok"]
        since = _ack(2, band=2.0)
        back = RM.move_back(RM.plan(store=STORE)["fingerprint"], "alex@example.com", "access",
                            store=STORE)
        assert back["ok"], back["steps"]
        assert db["values"]["records_store_acknowledgements"] == "file"
        assert ACK.read() == {"state": "ok", "rows": before + [since]}

    def test_the_reader_checks_this_store_too(self, db):
        from modules.readers import records_check

        _ack(1)
        assert _move()["ok"]
        got = records_check.read()["stores"]
        assert got["acknowledgements"]["check"]["ok"]
        assert got["receipts"]["check"] is None, "receipts stay on their files"


class TestADatabaseThatDoesNotAnswer:
    def test_a_read_is_unreadable_never_none_acknowledged(self, db):
        db["values"]["records_store_acknowledgements"] = "postgres"
        db["values"]["records_db_port"] = 1
        got = ACK.read()
        assert got["state"] == "unreadable" and got["rows"] == []
        assert "the records database" in got["error"]

    def test_a_write_is_refused_never_answered_as_recorded(self, db):
        db["values"]["records_store_acknowledgements"] = "postgres"
        db["values"]["records_db_port"] = 1
        with pytest.raises(records_db.Unavailable, match="did not accept the connection"):
            _ack(1)
        assert not os.path.exists(ACK._path()), "nothing fell back to the file"
