"""The restart records on the records database (K31 part 2b: three line stores, each one file for
the installation): the restarts seen, the planned-restart windows, and the windows ended early,
against a REAL PostgreSQL shaped as host step 6a makes it (tests/pg_instance.py; skipped with its
reason here, a failure in CI).

Each store is read back through `restarts.py`'s own public readers (`events`, `planned`,
`planned_rows`, `ends`), the ones the restarts reader, Needs attention and History call, so a
move is judged by what those readers answer, never by the table alone. C1324: the restarts
reader read the planned windows' file itself; it reads `restarts.planned()` now.
"""

import os
import stat

import pytest

from modules import records_db, records_migrate as RM
from modules import restarts as R
from tests.test_records_receipts import pg  # noqa: F401 (the module's real server)

#: Each store: its file, a row shaped as its writer writes it, and its public read.
CASES = {
    "restarts": ("restarts.jsonl",
                 lambda n: {"device": f"r{n}", "list": "Default", "at": f"2026-10-1{n}T01:00:00Z",
                            "seen_at": f"2026-10-1{n}T01:02:00Z", "planned": False,
                            "how": "sysUpTime reset"},
                 lambda: R.events()),
    "restart_windows": ("planned_restarts.jsonl",
                        lambda n: {"devices": [f"r{n}"], "list": "Default",
                                   "start": f"2026-10-1{n}T00:00:00Z",
                                   "end": f"2026-10-1{n}T02:00:00Z", "by": "alex@example.com",
                                   "why": "a planned reload during the maintenance window",
                                   "via": "Reload", "silence": {}},
                        lambda: R.planned()),
    "restart_window_ends": ("planned_restart_ends.jsonl",
                            lambda n: {"window": f"w{n}", "ended_at": f"2026-10-1{n}T01:30:00Z",
                                       "why": "the reload is back", "by": "alex@example.com",
                                       "silences": [], "recorded_at": f"2026-10-1{n}T01:30:01Z"},
                            lambda: R._read("planned_restart_ends.jsonl")),
}


@pytest.fixture
def db(pg, tmp_path, monkeypatch):  # noqa: F811
    """The settings pointed at the real server, every store on files; the data folder this
    test's own; the audit schema dropped first."""
    from tests import pg_instance

    values = {"records_db_host": "127.0.0.1", "records_db_port": pg.port,
              "records_db_name": "mercury", "records_db_user": "mercury"}
    values.update({f"records_store_{s}": "file" for s in records_db.STORES})
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
    return {"values": values}


def _write(store, n):
    name, make, _read = CASES[store]
    row = make(n)
    R._append(name, row)
    return row


def _rows(store):
    return CASES[store][2]()


def _move(store):
    return RM.move(RM.plan(store=store)["fingerprint"], "alex@example.com", "access", store=store)


def test_every_record_of_restarts_py_is_a_store():
    assert sorted(R.LINE_STORES.values()) == sorted(CASES)
    assert set(CASES) <= set(records_db.STORES) and set(CASES) <= set(RM.LINE_STORES)


@pytest.mark.parametrize("store", sorted(CASES))
class TestEachStore:
    def test_the_move_keeps_every_row_and_new_ones_land_in_the_table(self, db, store):
        name = CASES[store][0]
        _write(store, 1), _write(store, 2)
        before = _rows(store)
        out = _move(store)
        assert out["ok"], out["steps"]
        assert db["values"][f"records_store_{store}"] == "postgres"
        others = [s for s in records_db.STORES if s != store]
        assert all(db["values"][f"records_store_{s}"] == "file" for s in others)
        assert _rows(store) == before
        assert stat.S_IMODE(os.stat(R._data(name)).st_mode) == 0o400
        _write(store, 3)
        assert len(_rows(store)["rows"]) == 3
        assert len(open(R._data(name)).read().splitlines()) == 2, "the file is not written"
        assert RM.check(store=store)["ok"]

    def test_the_move_back_exports_what_was_written_since(self, db, store):
        _write(store, 1)
        assert _move(store)["ok"]
        _write(store, 2)
        moved = _rows(store)
        back = RM.move_back(RM.plan(store=store)["fingerprint"], "alex@example.com", "access",
                            store=store)
        assert back["ok"], back["steps"]
        assert db["values"][f"records_store_{store}"] == "file"
        assert _rows(store) == moved and len(moved["rows"]) == 2

    def test_a_database_that_does_not_answer_is_unreadable_and_refuses_a_write(self, db, store):
        db["values"][f"records_store_{store}"] = "postgres"
        db["values"]["records_db_port"] = 1
        got = R._read(CASES[store][0])
        assert got["state"] == "unreadable" and "the records database" in got["error"]
        with pytest.raises(records_db.Unavailable, match="did not accept the connection"):
            _write(store, 1)
        assert not os.path.exists(R._data(CASES[store][0])), "nothing fell back to the file"


class TestTheReadersReadThroughTheOwner:
    def test_planned_windows_on_the_database_reach_planned_rows_and_ends(self, db):
        window = _write("restart_windows", 1)
        assert _move("restart_windows")["ok"]
        assert R.planned_rows() == [window]
        _write("restart_window_ends", 1)
        assert _move("restart_window_ends")["ok"]
        assert list(R.ends()) == ["w1"]

    def test_an_unreadable_planned_record_is_refused_by_planned_rows(self, db):
        db["values"]["records_store_restart_windows"] = "postgres"
        db["values"]["records_db_port"] = 1
        with pytest.raises(RuntimeError, match="could not be read"):
            R.planned_rows()

    def test_the_restarts_reader_reads_the_windows_through_the_owner(self):
        """C1324: parsed, so prose naming the old read cannot satisfy it."""
        import ast

        tree = ast.parse(open(os.path.join(os.path.dirname(__file__), "..", "modules",
                                           "readers", "restarts.py")).read())
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert "planned" in names and "_read_jsonl" not in names and "_data" not in names
