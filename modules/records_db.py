"""Mercury's records database (Phase 4, docs/NSOT_PHASE4_RECORDS_POSTGRES.md): the ONE
connection every store moved off files uses, for the whole installation (P4-2, never a
network's). The database is `mercury-postgres` on 127.0.0.1:5433 (P4-1, PG-1, host step 6a).

**Off until its host is set.** `records_db_host` empty means every store stays on its files,
today's behaviour. An unset host, an unset password, an absent driver and a server that does
not answer are four different answers, each named, never a raise into a request.

**The driver is psycopg 3**, the host's apt package (`python3-psycopg` 3.1.17, as boto3 is
the host's: no pip into the system interpreter), pinned through the lock once a release that
imports it is deployed.

The Test (`test_connection`) is a person's: it signs in, reads the server's version, checks
Mercury's role is not a superuser (P4-1: it owns its database and nothing more), and, with
*write*, writes a row to a temporary table and reads it back inside a transaction it rolls
back, so nothing persists.
"""

import logging

log = logging.getLogger(__name__)

#: The Test's steps, in order, as the manual and a Settings card name them.
TEST_STEPS = ("connect", "version", "role", "write")
#: The PostgreSQL major the records database runs (host step 6a: NetBox's image, so one major to
#: patch; board F2: "the server is PostgreSQL 18"). Another major fails the Test, naming both.
MAJOR = 18
#: Not measured over a network: the database is on the same host (loopback). The sign-in bound
#: the host step used, kept until a sign-in is timed on the host.
CONNECT_TIMEOUT_S = 10
#: Visible in the server's own activity list, so a connection names whose it is.
APPLICATION_NAME = "mercury"


class Unavailable(RuntimeError):
    """No connection could be opened; the message names which of the reasons."""


def config() -> dict:
    """``{"host", "port", "name", "user", "password_set"}``: the installation's settings, the
    password's presence only, never its value."""
    from modules.secrets_store import is_set
    from modules.settings_schema import get_setting

    return {"host": (get_setting("records_db_host", "") or "").strip(),
            "port": int(get_setting("records_db_port", 5433) or 5433),
            "name": (get_setting("records_db_name", "mercury") or "").strip(),
            "user": (get_setting("records_db_user", "mercury") or "").strip(),
            "password_set": is_set("records_db_password")}


def configured() -> bool:
    """Whether stores MAY use the database: its host is set. Empty is today's behaviour."""
    return bool(config()["host"])


def connect(timeout: float = CONNECT_TIMEOUT_S):
    """An open psycopg connection, or `Unavailable` naming why there is none."""
    from modules.secrets_store import get_secret

    c = config()
    if not c["host"]:
        raise Unavailable("not configured: records_db_host is empty, so every store stays on "
                          "its files")
    if not c["name"] or not c["user"]:
        raise Unavailable("not configured: records_db_name and records_db_user must both be "
                          "set")
    password = get_secret("records_db_password", "")
    if not password:
        raise Unavailable("records_db_password is not set (the password host step 6a asked "
                          "for)")
    try:
        import psycopg
    except ImportError as exc:
        # Absent, or present without the libpq it loads (psycopg's own words say which, measured
        # 2026-10-09: "no pq wrapper available … libpq library not found"): never "not
        # installed" for a driver that is.
        first = (str(exc).strip().splitlines() or ["no reason given"])[0]
        raise Unavailable(f"psycopg could not be loaded on this host ({first}): Ubuntu's "
                          "python3-psycopg and its libpq5, docs/NSOT_PHASE4_RECORDS_POSTGRES.md, "
                          "step 6a") from None
    try:
        return psycopg.connect(host=c["host"], port=c["port"], dbname=c["name"],
                               user=c["user"], password=password, connect_timeout=timeout,
                               application_name=APPLICATION_NAME)
    except psycopg.Error as exc:
        # The server's own words (a refused password, no such database, nothing listening),
        # its first line only; psycopg never puts the password in them.
        first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        raise Unavailable(f"{c['user']}@{c['host']}:{c['port']}/{c['name']} did not accept "
                          f"the connection: {first}") from None


def test_connection(write: bool = True, connector=None) -> dict:
    """The Test, in `TEST_STEPS` order: ``{"ok", "steps": [{"name", "ok", "detail"}],
    "error"}``. The first step that fails is named with what the server said, and the rest are
    not tried. With *write* false, everything but the write (a reader's, which writes
    nothing)."""
    steps = []

    def failed(name, detail):
        steps.append({"name": name, "ok": False, "detail": detail})
        return {"ok": False, "steps": steps, "error": f"{name}: {detail}"}

    try:
        conn = (connector or connect)()
    except Unavailable as exc:
        return failed("connect", str(exc))
    c = config()
    steps.append({"name": "connect", "ok": True,
                  "detail": f"signed in as {c['user']} at {c['host']}:{c['port']}/{c['name']}"})
    try:
        with conn:
            version = conn.execute("show server_version").fetchone()[0]
            major = str(version).split(".")[0].split()[0]
            if major != str(MAJOR):
                return failed("version", f"the server is PostgreSQL {version}; Mercury's records "
                                         f"database runs PostgreSQL {MAJOR} (host step 6a)")
            steps.append({"name": "version", "ok": True, "detail": f"PostgreSQL {version}"})
            row = conn.execute("select current_user, rolsuper from pg_roles "
                               "where rolname = current_user").fetchone()
            if row is None:
                return failed("role", f"{c['user']}'s role could not be read from pg_roles")
            if row[1]:
                return failed("role", f"{row[0]} is a superuser; Mercury's role owns its "
                                      "database and nothing more (P4-1)")
            steps.append({"name": "role", "ok": True,
                          "detail": f"{row[0]} is not a superuser"})
            if write:
                conn.execute("create temporary table mercury_test (probe text) "
                             "on commit drop")
                conn.execute("insert into mercury_test values ('mercury')")
                got = conn.execute("select probe from mercury_test").fetchone()
                conn.rollback()
                if not got or got[0] != "mercury":
                    return failed("write", f"read back {got!r}, not the row written")
                steps.append({"name": "write", "ok": True,
                              "detail": "a temporary row written and read back; rolled back, "
                                        "nothing kept"})
    except Exception as exc:                          # noqa: BLE001 (that step's answer)
        name = TEST_STEPS[len(steps)] if len(steps) < len(TEST_STEPS) else "write"
        first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        log.warning("records_db: the Test failed at %s: %s", name, first)
        return failed(name, first)
    finally:
        try:
            conn.close()
        except Exception:                             # noqa: BLE001
            log.debug("records_db: close failed", exc_info=True)
    return {"ok": True, "steps": steps, "error": ""}
