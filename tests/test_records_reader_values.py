"""The readers' stored values on the records database (C1330: a DOCUMENT store, one document per
reader's store, read and written through the process's pool), against a REAL PostgreSQL shaped
as host step 6a makes it (tests/pg_instance.py; skipped with its reason here, a failure in CI).

Each value is written and read through `reader_job`'s own `run_once`, `read_cached` and
`health_rows`, the ones every page and Needs attention call, so a move is judged by what they
answer. A database that does not answer: every value reads as unreadable (never absent, never an
empty value read as fresh), and no run stores over the last good value.
"""

import json
import os
import stat

import pytest

from modules import reader_job as R
from modules import records_docs
from modules import records_migrate as RM
from modules.filestore import StoreUnreadable
from tests.test_records_restarts import db, pg  # noqa: F401 (the server and the settings)

STORE = "reader_values"


def _reader(name="t-values", value=None):
    return R.Reader(name=name, what="a test reader", endpoints=("api/test",),
                    interval_seconds=60, interval_basis="the test's own choice",
                    read=lambda: dict(value or {"firing": 2}), invalidates=("records",))


def _move():
    return RM.move(RM.plan(store=STORE)["fingerprint"], "alex@example.com", "access",
                   store=STORE)


def _file(name):
    with open(R.store_path(name), encoding="utf-8") as fh:
        return json.load(fh)


def test_it_is_a_document_store_of_objects_kept_per_reader(db):  # noqa: F811
    st = records_docs.store_of(STORE)
    assert st.shape is dict and st.cache
    R.run_once(_reader("t-values"))
    R.run_once(_reader("t-values@abc123"))
    assert sorted(st.files()) == ["t-values", "t-values@abc123"], "lock files are not values"


class TestTheMove:
    def test_the_move_keeps_every_value_and_new_runs_land_in_the_table(self, db):  # noqa: F811
        R.run_once(_reader())
        R.run_once(_reader("t-other"))
        before = R.read_cached("t-values")
        assert before["state"] == "ok"
        out = _move()
        assert out["ok"], out["steps"]
        assert db["values"]["records_store_reader_values"] == "postgres"
        assert R.read_cached("t-values") == before
        assert stat.S_IMODE(os.stat(R.store_path("t-values")).st_mode) == 0o400
        R.run_once(_reader(value={"firing": 3}))
        got = R.read_cached("t-values")
        assert got["state"] == "ok" and len(got["doc"]["runs"]) == 2
        assert got["doc"]["last_good"]["value"] == {"firing": 3}
        assert _file("t-values") == before["doc"], "the file is not written once moved"
        assert RM.check(store=STORE)["ok"]

    def test_the_move_back_writes_what_the_table_held(self, db):  # noqa: F811
        R.run_once(_reader())
        assert _move()["ok"]
        R.run_once(_reader(value={"firing": 5}))
        moved = R.read_cached("t-values")
        back = RM.move_back(RM.plan(store=STORE)["fingerprint"], "alex@example.com", "access",
                            store=STORE)
        assert back["ok"], back["steps"]
        assert db["values"]["records_store_reader_values"] == "file"
        assert R.read_cached("t-values") == moved
        assert _file("t-values")["last_good"]["value"] == {"firing": 5}

    def test_a_value_rewritten_before_the_switch_is_copied_again(self, db):  # noqa: F811
        from modules import records_db

        R.run_once(_reader())
        st = records_docs.store_of(STORE)
        with records_db.pooled() as conn:
            for sql in records_docs._schema(st):
                conn.execute(sql)
            records_docs.copy(conn, STORE)
        R.run_once(_reader(value={"firing": 9}))          # the reader's next cycle, on file
        with records_db.pooled() as conn:
            assert records_docs.copy(conn, STORE)["t-values"]["copied"] > 0
            body, copied = conn.execute("select body, copied from audit.reader_values_docs "
                                        "where network = 't-values'").fetchone()
        assert body == copied == _file("t-values")


class TestADatabaseThatDoesNotAnswer:
    @pytest.fixture
    def moved(self, db):  # noqa: F811
        R.run_once(_reader())
        assert _move()["ok"]
        return db

    def test_a_value_reads_as_unreadable_never_absent(self, moved):
        moved["values"]["records_db_port"] = 1
        got = R.read_cached("t-values")
        assert got["state"] == "unreadable" and got["doc"] is None and got["unanswered"]
        assert "the records database could not be asked" in got["why"]
        rows = R.health_rows(population=[_reader()])
        assert rows[0]["state"] == "unknown"
        assert "nothing is stored until it can be asked" in rows[0]["detail"]

    def test_a_run_stores_nothing_and_says_so(self, moved):
        moved["values"]["records_db_port"] = 1
        with pytest.raises(StoreUnreadable, match="nothing was stored"):
            R.run_once(_reader(value={"firing": 0}))
        assert not [f for f in os.listdir(os.path.dirname(R.store_path("t-values")))
                    if ".corrupt-" in f], "nothing on disk was set aside"

    def test_a_read_that_could_not_ask_never_lets_a_run_replace_the_last_good_value(
            self, moved, monkeypatch):
        good = R.read_cached("t-values")["doc"]["last_good"]
        real = records_docs.load
        calls = []

        def once_down(name, network, empty):
            calls.append(network)
            if len(calls) == 1:
                raise StoreUnreadable("the records database did not answer") from OSError("down")
            return real(name, network, empty)
        monkeypatch.setattr(records_docs, "load", once_down)
        with pytest.raises(StoreUnreadable):
            R.run_once(_reader(value={"firing": 0}))
        assert R.read_cached("t-values")["doc"]["last_good"] == good

    def test_a_value_of_the_wrong_shape_is_replaced_and_says_so(self, moved):
        from psycopg.types.json import Jsonb

        from modules import records_db

        with records_db.pooled() as conn:
            conn.execute("update audit.reader_values_docs set body = %s "
                         "where network = 't-values'", (Jsonb([1, 2]),))
        got = R.read_cached("t-values")
        assert got["state"] == "unreadable" and not got.get("unanswered")
        doc = R.run_once(_reader(value={"firing": 4}))
        assert "not an object" in doc["replaced_unreadable"]["why"]
        assert R.read_cached("t-values")["doc"]["last_good"]["value"] == {"firing": 4}
