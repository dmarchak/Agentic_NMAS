"""Mercury's records database connection (Phase 4, the receipts foundation;
docs/NSOT_PHASE4_RECORDS_POSTGRES.md): the installation's settings, the four named reasons there
is no connection, and the Test's steps.

The driver, psycopg, is not in CI's interpreter until the lock is regenerated on the host from
the release that first imports it (boto3's order); so here the Test's steps run against a
connection shaped like psycopg's, and the tests against a REAL PostgreSQL (the operator's
decision, option a: a service in CI, a throwaway instance locally) come with that lock.
"""

import re
import sys

import pytest

from modules import records_db as RD

PW = "Records-Pw-8q2w4e6r0t9y7u5i"


@pytest.fixture
def settings(monkeypatch):
    values = {"records_db_host": "", "records_db_port": 5433, "records_db_name": "mercury",
              "records_db_user": "mercury"}
    secrets = {}
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: values.get(key, default))
    monkeypatch.setattr("modules.secrets_store.get_secret",
                        lambda key, default="": secrets.get(key, default))
    monkeypatch.setattr("modules.secrets_store.is_set", lambda key: bool(secrets.get(key)))
    return {"values": values, "secrets": secrets}


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    """psycopg 3's shape as the Test uses it: ``execute(sql).fetchone()``, ``rollback``,
    ``close``, and a context manager. A temporary table holds what is inserted until the
    rollback."""

    def __init__(self, superuser=False, fail_on="", owner="mercury"):
        self.superuser, self.fail_on, self.owner = superuser, fail_on, owner
        self.sql, self.table, self.rolled_back, self.closed = [], None, 0, False

    def execute(self, sql):
        self.sql.append(sql)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError(f"ERROR:  permission denied ({self.fail_on})\nDETAIL: more")
        if sql.startswith("show server_version"):
            return FakeCursor(("18.6",))
        if "from pg_catalog.pg_database" in sql:
            return FakeCursor((self.owner, "mercury"))
        if "from pg_roles" in sql:
            return FakeCursor(("mercury", self.superuser))
        if sql.startswith("create temporary table"):
            self.table = []
            return FakeCursor(None)
        if sql.startswith("insert into mercury_test"):
            self.table.append("mercury")
            return FakeCursor(None)
        if sql.startswith("select probe from mercury_test"):
            return FakeCursor((self.table[0],) if self.table else None)
        raise AssertionError(f"unexpected SQL: {sql}")

    def rollback(self):
        self.rolled_back += 1
        self.table = None

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _configure(settings):
    settings["values"]["records_db_host"] = "127.0.0.1"
    settings["secrets"]["records_db_password"] = PW


class TestOffUntilSet:
    def test_an_empty_host_is_today_s_behaviour_and_says_so(self, settings):
        assert RD.configured() is False
        got = RD.test_connection()
        assert got["ok"] is False and got["steps"][0]["name"] == "connect"
        assert "records_db_host is empty, so every store stays on its files" in got["error"]

    def test_the_defaults_are_what_host_step_6a_makes(self, settings):
        from modules import settings_schema as S

        d = S.DEFAULTS
        assert (d["records_db_host"], d["records_db_port"], d["records_db_name"],
                d["records_db_user"], d["records_db_password"]) == ("", 5433, "mercury",
                                                                     "mercury", "")

    def test_one_for_the_installation_never_a_network_s(self):
        from modules import secrets_store, settings_scope

        group = [k for k, (scope, g) in settings_scope.SCOPES.items() if g == "records_db"]
        assert sorted(group) == ["records_db_host", "records_db_name", "records_db_password",
                                 "records_db_port", "records_db_user"]
        assert {settings_scope.SCOPES[k][0] for k in group} == {settings_scope.HOST}
        assert "records_db_password" in secrets_store.SECRET_KEYS

    def test_no_password_is_named(self, settings):
        settings["values"]["records_db_host"] = "127.0.0.1"
        got = RD.test_connection()
        assert "records_db_password is not set" in got["error"]

    def test_an_absent_driver_is_named(self, settings, monkeypatch):
        _configure(settings)
        monkeypatch.setitem(sys.modules, "psycopg", None)
        got = RD.test_connection()
        assert "psycopg could not be loaded on this host (" in got["error"]

    def test_the_password_is_never_in_what_it_says(self, settings, monkeypatch):
        _configure(settings)
        assert PW not in repr(RD.config()) and RD.config()["password_set"] is True
        monkeypatch.setitem(sys.modules, "psycopg", None)
        assert PW not in repr(RD.test_connection())


class TestTheTest:
    def test_every_step_passes_and_nothing_is_kept(self, settings):
        _configure(settings)
        conn = FakeConnection()
        got = RD.test_connection(connector=lambda: conn)
        assert got["ok"] is True, got
        assert [s["name"] for s in got["steps"]] == list(RD.TEST_STEPS)
        details = {s["name"]: s["detail"] for s in got["steps"]}
        assert details["connect"] == "signed in as mercury at 127.0.0.1:5433/mercury"
        assert details["version"] == "PostgreSQL 18.6"
        assert details["owner"] == "mercury owns the database mercury"
        assert details["role"] == "mercury is not a superuser"
        assert details["loopback"].startswith("Mercury reaches it on loopback (127.0.0.1)")
        assert "rolled back, nothing kept" in details["write"]
        assert conn.rolled_back == 1 and conn.table is None and conn.closed
        assert any("on commit drop" in s for s in conn.sql)

    def test_another_major_fails_the_version_step_naming_both(self, settings):
        _configure(settings)
        conn = FakeConnection()
        real = conn.execute
        conn.execute = lambda sql: FakeCursor(("16.4 (Ubuntu 16.4-1)",)) \
            if sql.startswith("show server_version") else real(sql)
        got = RD.test_connection(connector=lambda: conn)
        assert got["ok"] is False and got["steps"][-1]["name"] == "version"
        assert "the server is PostgreSQL 16.4 (Ubuntu 16.4-1); Mercury's records database runs " \
               "PostgreSQL 18" in got["error"]

    def test_a_reader_s_test_writes_nothing(self, settings):
        _configure(settings)
        conn = FakeConnection()
        got = RD.test_connection(write=False, connector=lambda: conn)
        assert got["ok"] and [s["name"] for s in got["steps"]] == [
            "connect", "version", "owner", "role", "loopback"]
        assert not any("insert" in s or "create" in s for s in conn.sql)

    def test_a_database_another_role_owns_fails_the_owner_step(self, settings):
        """Board F2: the Test checks what host step 6a made, naming the check that failed."""
        _configure(settings)
        conn = FakeConnection(owner="postgres")
        got = RD.test_connection(connector=lambda: conn)
        assert got["ok"] is False and got["steps"][-1]["name"] == "owner"
        assert "owned by postgres, not mercury" in got["error"]
        assert not any("insert" in s for s in conn.sql)

    def test_an_address_beyond_loopback_fails_the_loopback_step(self, settings):
        _configure(settings)
        settings["values"]["records_db_host"] = "db.example.invalid"
        conn = FakeConnection()
        lan = lambda host, port: [(2, 1, 6, "", ("192.0.2.40", 0))]    # noqa: E731
        got = RD.test_connection(connector=lambda: conn, resolve=lan)
        assert got["ok"] is False and got["steps"][-1]["name"] == "loopback"
        assert "db.example.invalid (192.0.2.40), not a loopback address" in got["error"]

    @pytest.mark.parametrize("addrs, ok", [(["127.0.0.1"], True), (["::1"], True),
                                           (["127.0.0.1", "192.0.2.40"], False)])
    def test_loopback_means_every_address_the_host_names(self, addrs, ok):
        infos = [(2, 1, 6, "", (a, 0)) for a in addrs]
        assert RD.loopback("h", lambda host, port: infos)[0] is ok

    def test_a_superuser_role_fails_and_the_write_is_not_tried(self, settings):
        _configure(settings)
        conn = FakeConnection(superuser=True)
        got = RD.test_connection(connector=lambda: conn)
        assert got["ok"] is False and got["steps"][-1]["name"] == "role"
        assert "mercury is a superuser; Mercury's role owns its database and nothing more" \
            in got["error"]
        assert not any("insert" in s for s in conn.sql) and conn.closed

    def test_a_failing_step_is_named_with_the_server_s_first_line(self, settings):
        _configure(settings)
        conn = FakeConnection(fail_on="insert into")
        got = RD.test_connection(connector=lambda: conn)
        assert got["ok"] is False and got["steps"][-1]["name"] == "write"
        assert got["error"] == "write: ERROR:  permission denied (insert into)"
        assert conn.closed

    def test_a_refused_connection_is_named(self, settings):
        _configure(settings)

        def refused():
            raise RD.Unavailable("mercury@127.0.0.1:5433/mercury did not accept the "
                                 "connection: password authentication failed")
        got = RD.test_connection(connector=refused)
        assert got["steps"] == [{"name": "connect", "ok": False, "detail": got["error"][9:]}]
        assert "password authentication failed" in got["error"]


@pytest.fixture(scope="module")
def pg():
    """A real PostgreSQL shaped as host step 6a makes it (tests/pg_instance.py): skipped with
    its reason here, a failure where NMAS_REQUIRE_PG=1 (CI)."""
    from tests import pg_instance

    inst = pg_instance.start()
    yield inst
    inst.stop()


def _point_at(settings, pg, password=None, user="mercury"):
    from tests import pg_instance

    settings["values"].update(records_db_host="127.0.0.1", records_db_port=pg.port,
                              records_db_user=user)
    settings["secrets"]["records_db_password"] = password or pg_instance.MERCURY_PW


class TestAgainstARealPostgreSQL:
    """The Test over a real server (option a): what host step 6a made, checked as it is."""

    def test_every_step_passes_on_what_6a_makes(self, settings, pg):
        _point_at(settings, pg)
        got = RD.test_connection()
        assert got["ok"] is True, got
        assert [s["name"] for s in got["steps"]] == list(RD.TEST_STEPS)
        assert got["steps"][1]["detail"].startswith("PostgreSQL 18."), got["steps"][1]

    def test_the_write_keeps_nothing(self, settings, pg):
        _point_at(settings, pg)
        assert RD.test_connection()["ok"]
        with pg.connect() as c:
            left = c.execute("select count(*) from pg_class where relname = 'mercury_test'"
                             ).fetchone()[0]
        assert left == 0, "the Test's temporary table outlived its transaction"

    def test_a_wrong_password_is_named_by_the_server(self, settings, pg):
        _point_at(settings, pg, password="not-the-password")
        got = RD.test_connection()
        assert got["ok"] is False and got["steps"][-1]["name"] == "connect"
        assert "password authentication failed" in got["error"], got["error"]
        assert "not-the-password" not in repr(got)

    def test_a_superuser_role_fails_its_step(self, settings, pg):
        from tests import pg_instance

        _point_at(settings, pg, password=pg_instance.SUPER_PW, user="postgres")
        settings["values"]["records_db_name"] = "postgres"
        got = RD.test_connection()
        assert got["ok"] is False and got["steps"][-1]["name"] == "role", got
        assert "postgres is a superuser" in got["error"]

    def test_nothing_listening_is_named(self, settings, pg):
        from tests import pg_instance

        _point_at(settings, pg)
        settings["values"]["records_db_port"] = pg_instance._free_port()
        got = RD.test_connection()
        assert got["ok"] is False and got["steps"][-1]["name"] == "connect"
        assert "did not accept the connection" in got["error"]


class TestTheLock:
    def test_psycopg_is_authored_and_pinned_at_the_hosts_version(self):
        """The host's apt psycopg was 3.1.17 (host step 6a); the authored lock (Phase 4 section
        8.2) holds that version, so the venv's driver is the one 6a proved."""
        from tests import test_requirements_lock as L

        assert L.IMPORT_TO_DIST["psycopg"] == "psycopg" and "psycopg" in L.static_imports()
        assert L._pins()["psycopg"] == "3.1.17"
        assert "psycopg" in {L._norm(r.name) for r in L._authored("requirements.txt")}


