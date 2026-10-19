"""The four break-glass logs on the records database (K31 part 2b: line stores, one file each for
the installation): exports, the browser's download verdicts, checks of a kept file, and drills,
against a REAL PostgreSQL shaped as host step 6a makes it (tests/pg_instance.py; skipped with its
reason here, a failure in CI).

Each log is written by its own `breakglass.record_*` and read back through the readers job
health, the Credentials page and History use (`all_exports`, `last_exports`,
`intact_verdicts`, `checks`, `drills`). C1324: History read the exports file itself; it reads
`breakglass.all_exports()` now. Digests and verdicts only: no credential value is in any line.
"""

import os
import stat
import types

import pytest

from modules import breakglass as bg
from modules import config
from modules import records_db, records_migrate as RM
from tests.test_records_restarts import db, pg  # noqa: F401 (the server and the settings)

DEVICES = [{"hostname": "r1", "username": "admin", "password": "not-a-real-one-1"}]


def _export(n):
    return bg.record_export(config.DATA_DIR, list_name="Default", devices=DEVICES,
                            path=f"/kept/r{n}.nmasbg", key_fingerprint="ab" * 8,
                            actor="alex@example.com", at=1790000000 + n, via="browser",
                            sha256=f"{n:064x}", filename=f"r{n}.nmasbg")


#: Each log: its file, a writer as the app calls it, and its public read as rows.
CASES = {
    "breakglass_exports": (bg.EXPORT_LOG, _export,
                           lambda: bg.all_exports(config.DATA_DIR)["rows"]),
    "breakglass_intact": (bg.INTACT_LOG,
                          lambda n: bg.record_intact(config.DATA_DIR, list_name="Default",
                                                     sha256=f"{n:064x}",
                                                     browser_sha256=f"{n:064x}",
                                                     actor="alex@example.com",
                                                     at=1790000000 + n),
                          lambda: list(bg.intact_verdicts(config.DATA_DIR)["by_sha"].values())),
    "breakglass_checks": (bg.CHECK_LOG,
                          lambda n: bg.record_check(config.DATA_DIR, list_name="Default",
                                                    actor="alex@example.com", sha256=f"{n:064x}",
                                                    created="2026-10-01T00:00:00Z",
                                                    devices={"r1": "current"}, key="opens",
                                                    at=1790000000 + n),
                          lambda: bg.checks(config.DATA_DIR)["rows"]),
    "breakglass_drills": (bg.DRILL_LOG,
                          lambda n: bg.record_drill(config.DATA_DIR, list_name="Default",
                                                    actor="alex@example.com",
                                                    receipt={"list": "Default",
                                                             "sha256": f"{n:064x}",
                                                             "created": "2026-10-01T00:00:00Z",
                                                             "devices": 1, "key": "opens",
                                                             "opened": 1790000000 + n},
                                                    at=1790000000 + n),
                          lambda: bg.drills(config.DATA_DIR)["rows"]),
}


def _move(store):
    return RM.move(RM.plan(store=store)["fingerprint"], "alex@example.com", "access", store=store)


def test_every_log_is_a_store():
    assert sorted(bg.LOG_STORES.values()) == sorted(CASES)
    assert set(CASES) <= set(records_db.STORES) and set(CASES) <= set(RM.LINE_STORES)


@pytest.mark.parametrize("store", sorted(CASES))
class TestEachLog:
    def test_the_move_keeps_every_row_and_new_ones_land_in_the_table(self, db, store):
        name, write, read = CASES[store]
        write(1), write(2)
        before = read()
        out = _move(store)
        assert out["ok"], out["steps"]
        assert db["values"][f"records_store_{store}"] == "postgres"
        assert read() == before
        path = os.path.join(config.DATA_DIR, name)
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o400
        write(3)
        assert len(read()) == 3 and len(open(path).read().splitlines()) == 2
        assert RM.check(store=store)["ok"]
        assert "not-a-real-one-1" not in repr(read()), "a value never reaches a line"

    def test_the_move_back_exports_what_was_written_since(self, db, store):
        _name, write, read = CASES[store]
        write(1)
        assert _move(store)["ok"]
        write(2)
        moved = read()
        back = RM.move_back(RM.plan(store=store)["fingerprint"], "alex@example.com", "access",
                            store=store)
        assert back["ok"], back["steps"]
        assert read() == moved and len(moved) == 2

    def test_a_database_that_does_not_answer_is_unreadable_and_refuses_a_write(self, db,
                                                                               store):
        name, write, _read = CASES[store]
        db["values"][f"records_store_{store}"] = "postgres"
        db["values"]["records_db_port"] = 1
        got = bg._jsonl(config.DATA_DIR, name)
        assert got["state"] == "unreadable" and "the records database" in got["error"]
        with pytest.raises(records_db.Unavailable, match="did not accept the connection"):
            write(1)
        assert not os.path.exists(os.path.join(config.DATA_DIR, name))


class TestTheReadersReadThroughTheOwner:
    def test_history_draws_an_export_on_the_database(self, db):
        from modules import history_sources as H

        _export(1)
        assert _move("breakglass_exports")["ok"]
        ref = types.SimpleNamespace(name="Default", repo_dir="/nonexistent")
        got = H.breakglass({"ref": ref, "device": "r1", "members": None, "limit": 5})
        assert [e["what"] for e in got["events"]] == ["Break-glass record exported (1 device)"]

    def test_history_says_an_unreadable_export_log(self, db):
        from modules import history_sources as H

        db["values"]["records_store_breakglass_exports"] = "postgres"
        db["values"]["records_db_port"] = 1
        ref = types.SimpleNamespace(name="Default", repo_dir="/nonexistent")
        got = H.breakglass({"ref": ref, "device": "r1", "members": None, "limit": 5})
        assert got["events"] == [] and "could not be read" in got["errors"][0]

    def test_last_exports_on_the_database_keeps_the_newest_per_list(self, db):
        _export(1), _export(2)
        assert _move("breakglass_exports")["ok"]
        got = bg.last_exports(config.DATA_DIR)
        assert got["state"] == "ok" and got["by_list"]["Default"]["at"] == 1790000002

    def test_history_reads_the_exports_through_the_owner(self):
        """C1324: parsed, so prose naming the old read cannot satisfy it."""
        import ast
        import inspect

        from modules import history_sources as H

        tree = ast.parse(inspect.getsource(H.breakglass).lstrip())
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        calls = {n.func.id for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "all_exports" in attrs and "EXPORT_LOG" not in attrs and "open" not in calls
