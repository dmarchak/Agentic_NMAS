"""One pool of records-database connections per process (C1330; the operator's decision,
2026-10-19: psycopg's own pool), against a REAL PostgreSQL shaped as host step 6a makes it
(tests/pg_instance.py; skipped with its reason here, a failure in CI).

What the pool must hold: reads in one process share its connections (one sign-in, not one per
read); a changed setting or password retires the pool; a forked process makes its own and leaves
its parent's sessions alone; a server that stops accepting, or a pool with every connection busy,
is `Unavailable` in words within the bound; a pooled connection the server ended is replaced, not
read as unreadable; an absent `psycopg_pool` is its own reason; and the Test signs in fresh.
"""

import multiprocessing
import os
import sys
import time

import pytest

from modules import records_db, records_docs
from modules.filestore import StoreUnreadable
from tests.test_records_restarts import db, pg  # noqa: F401 (the server and the settings)

STORE = "rollback_blocks"


@pytest.fixture
def pool(db):  # noqa: F811
    """No pool from an earlier test: the first use in each test makes this test's."""
    def drop():
        entry = records_db._ENTRY
        if entry is not None and not entry.retired:
            records_db._retire(entry)
        records_db._ENTRY = None
    drop()
    yield db
    drop()


def _super(pg):  # noqa: F811
    """The server's superuser, over its socket folder (tests/pg_instance.py)."""
    import psycopg  # loaded only once pg_instance has started a server (it skips without one)

    return psycopg.connect(host=pg.folder, port=pg.port, user="postgres", dbname="postgres",
                           autocommit=True, connect_timeout=10)


def _backend():
    with records_db.pooled() as conn:
        return conn.execute("select pg_backend_pid()").fetchone()[0]


class TestOnePoolPerProcess:
    def test_twenty_reads_share_one_sign_in(self, pool):
        records_docs.save(STORE, "Default", {"r1": {"why": "a test"}})
        pids = set()
        for _ in range(20):
            assert records_docs.load(STORE, "Default", {}) == {"r1": {"why": "a test"}}
            pids.add(_backend())
        assert len(pids) == 1, f"{len(pids)} server sessions served 20 reads"
        assert records_db.pool_stats()["connections_num"] == 1

    def test_a_returned_connection_holds_no_transaction(self, pool):
        with records_db.pooled() as conn:
            conn.execute("select 1")
        from psycopg.pq import TransactionStatus

        with records_db.pooled() as conn:
            assert conn.info.transaction_status == TransactionStatus.IDLE
            assert not conn.closed

    def test_a_write_that_raises_is_rolled_back(self, pool, pg):  # noqa: F811
        records_docs.save(STORE, "Default", {"r1": {}})
        with pg.connect() as other:
            assert other.execute("select to_regclass('audit.rollback_blocks_docs') is not null"
                                 ).fetchone()[0], "the save was not committed"
        with pytest.raises(RuntimeError):
            with records_db.pooled() as conn:
                conn.execute("delete from audit.rollback_blocks_docs")
                raise RuntimeError("the caller failed mid-transaction")
        assert records_docs.load(STORE, "Default", {}) == {"r1": {}}

    def test_a_changed_setting_makes_a_new_pool(self, pool):
        _backend()
        first = records_db._ENTRY
        pool["values"]["records_db_host"] = "localhost"
        _backend()
        assert records_db._ENTRY is not first and first.retired
        assert records_db._ENTRY.key[1] == "localhost"

    def test_a_changed_password_makes_a_new_pool_and_the_key_never_holds_it(
            self, pool, pg, monkeypatch):  # noqa: F811
        from tests import pg_instance

        _backend()
        first = records_db._ENTRY
        assert pg_instance.MERCURY_PW not in repr(first.key)
        with _super(pg) as su:
            su.execute("alter role mercury password 'a-new-suite-password-0987'")
        try:
            monkeypatch.setattr("modules.secrets_store.get_secret",
                                lambda key, default="": "a-new-suite-password-0987"
                                if key == "records_db_password" else default)
            _backend()
            assert records_db._ENTRY is not first and first.retired
        finally:
            with _super(pg) as su:
                su.execute(f"alter role mercury password '{pg_instance.MERCURY_PW}'")


def _in_child(q):
    try:
        value = records_docs.load(STORE, "Default", {})
        entry = records_db._ENTRY
        q.put({"value": value, "own": entry is not None and entry.key[0] == os.getpid(),
               "pid": _backend()})
    except BaseException as exc:                      # noqa: BLE001 (reported to the parent)
        q.put({"error": f"{type(exc).__name__}: {exc}"})


class TestAForkedProcess:
    @pytest.mark.skipif(sys.platform != "linux", reason="fork is the host's start method")
    def test_a_child_makes_its_own_pool_and_leaves_the_parent_s_sessions(self, pool):
        records_docs.save(STORE, "Default", {"r1": {"why": "forked"}})
        parent = _backend()
        ctx = multiprocessing.get_context("fork")
        q = ctx.Queue()
        child = ctx.Process(target=_in_child, args=(q,))
        child.start()
        got = q.get(timeout=30)
        child.join(timeout=30)
        assert "error" not in got, got
        assert got["value"] == {"r1": {"why": "forked"}}
        assert got["own"], "the child used its parent's pool"
        assert got["pid"] != parent, "the child read on its parent's session"
        assert _backend() == parent, "the parent's session did not survive the child"


class TestUnavailable:
    def test_a_server_that_refuses_is_named_at_once(self, pool):
        import socket

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        pool["values"]["records_db_port"] = port
        t0 = time.monotonic()
        with pytest.raises(records_db.Unavailable, match=f"mercury@127.0.0.1:{port}/mercury did "
                                                         "not accept the connection: "):
            records_db.pooled().__enter__()
        assert time.monotonic() - t0 < records_db.POOL_WAIT_S

    def test_a_server_that_stops_accepting_under_a_pool_is_named_in_its_words(
            self, pool, pg):  # noqa: F811
        _backend()
        with _super(pg) as su:
            su.execute("alter role mercury nologin")
            su.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                       "where usename = 'mercury'")
        try:
            t0 = time.monotonic()
            with pytest.raises(records_db.Unavailable, match="not permitted to log in"):
                _backend()
            assert time.monotonic() - t0 < records_db.POOL_WAIT_S
            with pytest.raises(StoreUnreadable):
                records_docs.load(STORE, "Default", {})
        finally:
            with _super(pg) as su:
                su.execute("alter role mercury login")
        assert _backend(), "the next read after the server accepts again"

    def test_a_session_the_server_ended_is_replaced_never_read_as_unreadable(
            self, pool, pg):  # noqa: F811
        records_docs.save(STORE, "Default", {"r1": {}})
        before = _backend()
        with _super(pg) as su:
            su.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                       "where usename = 'mercury'")
        assert records_docs.load(STORE, "Default", {}) == {"r1": {}}
        assert _backend() != before

    def test_every_connection_busy_is_unavailable_within_the_bound(self, pool):
        held = [records_db.pooled() for _ in range(records_db.POOL_MAX)]
        try:
            for cm in held:
                cm.__enter__()
            t0 = time.monotonic()
            with pytest.raises(records_db.Unavailable,
                               match=f"all {records_db.POOL_MAX} of this process's are in use"):
                _backend()
            took = time.monotonic() - t0
            assert records_db.POOL_WAIT_S * 0.9 <= took < records_db.POOL_WAIT_S * 2.5, took
        finally:
            for cm in held:
                cm.__exit__(None, None, None)
        assert _backend()

    def test_an_absent_pool_package_is_its_own_reason(self, pool, monkeypatch):
        monkeypatch.setitem(sys.modules, "psycopg_pool", None)
        with pytest.raises(records_db.Unavailable, match="psycopg_pool could not be loaded on "
                                                         "this host"):
            _backend()
        with pytest.raises(StoreUnreadable, match="psycopg_pool"):
            records_docs.load(STORE, "Default", {})

    @pytest.mark.parametrize("key, words", [
        ("records_db_host", "records_db_host is empty"),
        ("records_db_password", "records_db_password is not set")])
    def test_an_unset_setting_is_named_as_connect_names_it(self, pool, monkeypatch, key, words):
        if key == "records_db_host":
            pool["values"]["records_db_host"] = ""
        else:
            monkeypatch.setattr("modules.secrets_store.get_secret", lambda k, default="": "")
        with pytest.raises(records_db.Unavailable, match=words):
            _backend()


class TestTheTest:
    def test_the_test_signs_in_fresh_and_never_takes_the_pool(self, pool, monkeypatch):
        def no(*_a, **_k):
            raise AssertionError("the Test took a pooled connection")
        monkeypatch.setattr(records_db, "pooled", no)
        monkeypatch.setattr(records_db, "_entry", no)
        got = records_db.test_connection()
        assert got["ok"], got
        assert records_db._ENTRY is None
