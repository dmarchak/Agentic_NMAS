"""Mercury's records database (Phase 4, docs/NSOT_PHASE4_RECORDS_POSTGRES.md): the ONE
connection every store moved off files uses, for the whole installation (P4-2, never a
network's). The database is `mercury-postgres` on 127.0.0.1:5433 (P4-1, PG-1, host step 6a).

**Off until its host is set.** `records_db_host` empty means every store stays on its files,
today's behaviour. An unset host, an unset password, an absent driver and a server that does
not answer are four different answers, each named, never a raise into a request.

**The driver is psycopg 3**, the host's apt package (`python3-psycopg` 3.1.17, as boto3 is
the host's: no pip into the system interpreter), pinned through the lock once a release that
imports it is deployed.

The Test (`test_connection`) is a person's, and checks what host step 6a made (board F2, the
operator's condition, 2026-10-09): it signs in, reads the server's version, checks Mercury's
role owns its database and is not a superuser (P4-1: its database and nothing more), that
Mercury reaches it on a loopback address, and, with *write*, writes a row to a temporary table
and reads it back inside a transaction it rolls back, so nothing persists. It opens a FRESH
connection (`connect`), because what it proves is that Mercury can sign in now.

**The stores use one pool of connections per process** (`pooled`, C1330; psycopg's own pool,
`psycopg_pool`, the operator's decision, 2026-10-19). A new connection cost a median of 25.8 ms
on the host, and the readers' stored values are read many times per page; a pooled read took
0.32 ms on the laptop against 4.15 ms with a fresh sign-in (`POOL_WAIT_S`). The pool is
made on first use and keyed by the connection settings (the password by a keyed hash, never the
value) and by the process: a changed setting retires the old pool, and a forked process makes
its own, never touching its parent's sockets. Each failure is `Unavailable` in the words
`connect` uses, and an absent `psycopg_pool` is a reason of its own.
"""

import contextlib
import hashlib
import hmac
import ipaddress
import logging
import os
import socket
import threading

log = logging.getLogger(__name__)

#: The Test's steps, in order, as the manual and the Settings card name them.
TEST_STEPS = ("connect", "version", "owner", "role", "loopback", "write")
#: The PostgreSQL major the records database runs (host step 6a: NetBox's image, so one major to
#: patch; board F2: "the server is PostgreSQL 18"). Another major fails the Test, naming both.
MAJOR = 18
#: Each step in the card's words: the check it makes (board F2), for a step not tried too.
STEP_WORDS = {"connect": "signs in", "version": f"PostgreSQL {MAJOR}",
              "owner": "owns the database", "role": "not a superuser",
              "loopback": "loopback", "write": "a temporary row"}
#: Not measured over a network: the database is on the same host (loopback). The sign-in bound
#: the host step used, kept until a sign-in is timed on the host.
CONNECT_TIMEOUT_S = 10
#: Visible in the server's own activity list, so a connection names whose it is.
APPLICATION_NAME = "mercury"
#: The stores that can move to this database, in the order they move (section 3 of the Phase 4
#: document: receipts first), each with its words and its switch, `records_store_<name>`
#: ("file", today's, or "postgres"). A store moves only through records_migrate, which copies,
#: switches and checks; the Settings card draws each ("Stores on it").
STORES = ("receipts", "acknowledgements", "restarts", "restart_windows", "restart_window_ends",
          "rotations", "breakglass_exports", "breakglass_intact", "breakglass_checks",
          "breakglass_drills", "reveals", "host_steps_done", "heartbeat_rules", "netbox_removals",
          "network_settings_record", "onboarding_runs", "inventory_edits", "approval_queue",
          "rollback_blocks", "retry_log", "netbox_created", "netbox_modified", "netbox_adopted",
          "interrupted_holds", "reader_values", "ai_calls", "evidence_packs")
STORE_WORDS = {"receipts": "Deploy receipts", "acknowledgements": "Acknowledgements",
               "restarts": "Restarts seen", "restart_windows": "Planned-restart windows",
               "restart_window_ends": "Planned-restart windows ended early",
               "rotations": "Rotations and saves",
               "breakglass_exports": "Break-glass exports",
               "breakglass_intact": "Break-glass download verdicts",
               "breakglass_checks": "Break-glass checks", "breakglass_drills": "Break-glass drills",
               "reveals": "Reveals", "host_steps_done": "Host steps said done",
               "heartbeat_rules": "Heartbeat window re-measures",
               "netbox_removals": "NetBox removals",
               "network_settings_record": "Network settings changes",
               "onboarding_runs": "Onboarding runs", "inventory_edits": "Inventory edits",
               "approval_queue": "Approval queue", "rollback_blocks": "Rollback blocks",
               "retry_log": "Retries authorised", "netbox_created": "NetBox objects created",
               "netbox_modified": "NetBox objects modified",
               "netbox_adopted": "NetBox objects adopted",
               "interrupted_holds": "Interrupted operations",
               "reader_values": "Stored reader values", "ai_calls": "AI calls",
               "evidence_packs": "Alert evidence packs"}
FILE, POSTGRES = "file", "postgres"


class Unavailable(RuntimeError):
    """No connection could be opened; the message names which of the reasons."""


def backend(store: str) -> str:
    """Where *store* keeps its records now: ``file`` or ``postgres``, read at each call so
    every process follows a switch together. Anything else stored reads as ``file``."""
    from modules.settings_schema import get_setting

    got = get_setting(f"records_store_{store}", FILE)
    return POSTGRES if got == POSTGRES else FILE


def stores() -> list:
    """The stores on this database now, in `STORES` order."""
    return [s for s in STORES if backend(s) == POSTGRES]


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


def _first(exc) -> str:
    return (str(exc).strip().splitlines() or [type(exc).__name__])[0]


def _resolve():
    """``(config, password, psycopg)``, or `Unavailable` naming the first thing missing: the
    checks every connection, fresh or pooled, makes before it is tried."""
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
    return c, password, psycopg


def _refused(c: dict, first: str) -> Unavailable:
    """The server's own words (a refused password, no such database, nothing listening), its
    first line only; psycopg never puts the password in them."""
    return Unavailable(f"{c['user']}@{c['host']}:{c['port']}/{c['name']} did not accept the "
                       f"connection: {first}")


def _kwargs(c: dict, password: str, timeout: float) -> dict:
    return {"host": c["host"], "port": c["port"], "dbname": c["name"], "user": c["user"],
            "password": password, "connect_timeout": timeout,
            "application_name": APPLICATION_NAME}


def connect(timeout: float = CONNECT_TIMEOUT_S):
    """A FRESH psycopg connection, or `Unavailable` naming why there is none. The Test's, and
    the probe a new pool is made after; the stores take `pooled`."""
    c, password, psycopg = _resolve()
    try:
        return psycopg.connect(**_kwargs(c, password, timeout))
    except psycopg.Error as exc:
        raise _refused(c, _first(exc)) from None


# ── One pool per process (C1330) ─────────────────────────────────────────────────────────────

#: At most this many connections per process. A hold is one statement or one short transaction
#: (a stored document's read held its connection a median of 0.07 ms on the laptop, 2026-10-19,
#: and the whole pooled read with its checkout 0.32 ms), so a thread that finds all four busy
#: waits a hold, not a sign-in. Who asks at once: the request threads (Flask-SocketIO in
#: threading mode; a browser opens at most six requests per page at once), the reader threads
#: (25 readers, each on its own interval, the fastest every 5 s) and at most one move
#: (`records_migrate._Lock`), which holds one for its copy. Four leaves three free during a move,
#: and four server processes per Mercury process.
POOL_MAX = 4
#: A pool shrinks to none when idle: a process that never touches a moved store holds no
#: connection, and the first use after an idle spell makes one (a sign-in, as before C1330).
POOL_MIN = 0
#: How long a store waits for a pooled connection before `Unavailable`. 2.5x the slowest of 20
#: sign-ins measured on the host (234.8 ms, K31, 2026-10-19; median 25.8 ms), since the longest
#: wait is the pool making one: 0.6 s. On the laptop's real PostgreSQL (2026-10-19, median of 20
#: each, `records_docs.load` of one document): 4.15 ms with a fresh sign-in per read, 0.32 ms
#: pooled (the check that the connection answers included).
POOL_WAIT_S = 0.6
#: The pool's own retries of a sign-in that failed stop after this; the next store's use makes a
#: new pool after a fresh sign-in succeeds (`_entry`), so a database back up is used at once.
POOL_RECONNECT_S = CONNECT_TIMEOUT_S
#: Visible to the pool's own log lines and stats.
POOL_NAME = "mercury-records"

#: A random key per process for the password's hash in the pool's key: the value is never kept
#: beside the pool, and the hash means nothing outside this process.
_TAG_KEY = os.urandom(16)
_LOCK = threading.Lock()
_ENTRY = None
#: A parent's pool seen in a forked child: kept, never closed (closing it would end the
#: parent's sessions on the sockets the child inherited).
_ABANDONED: list = []


class _Entry:
    """This process's pool: its *key*, and the sign-in failure the pool last met (``""`` once
    one succeeds), so a store that times out says why."""

    def __init__(self, key: tuple, pool):
        self.key, self.pool = key, pool
        self.last_error = ""
        self.retired = False


def _after_fork_in_child() -> None:
    # A lock another thread held at the fork is never released here: a fresh one. The parent's
    # pool is left as it is (`_ABANDONED`).
    global _LOCK, _ENTRY
    _LOCK = threading.Lock()
    if _ENTRY is not None:
        _ABANDONED.append(_ENTRY)
        _ENTRY = None


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_in_child)


def _tag(password: str) -> bytes:
    return hmac.new(_TAG_KEY, password.encode("utf-8"), hashlib.sha256).digest()


def _pool_module():
    try:
        import psycopg_pool
    except ImportError as exc:
        raise Unavailable(f"psycopg_pool could not be loaded on this host ({_first(exc)}): the "
                          "psycopg-pool package requirements.lock pins (C1330); a virtualenv "
                          "built before it lacks it, and scripts/host-steps/venv-1-build.sh "
                          "builds one that has it") from None
    return psycopg_pool


def _retire(entry) -> None:
    """Close *entry*'s pool off the caller's thread: a worker inside a sign-in to a server that
    does not answer would hold `close` for up to `CONNECT_TIMEOUT_S`."""
    entry.retired = True
    if entry.key[0] != os.getpid():
        _ABANDONED.append(entry)
        return

    def close():
        try:
            entry.pool.close(timeout=CONNECT_TIMEOUT_S)
        except Exception:                             # noqa: BLE001
            log.debug("records_db: closing a retired pool failed", exc_info=True)
    threading.Thread(target=close, name="records-db-pool-close", daemon=True).start()


def _new_pool(psycopg, psycopg_pool, c: dict, password: str, entry_box: list):
    class Recording(psycopg.Connection):
        """The pool's connections, each sign-in's failure kept on the entry in the words
        `connect` uses, so a store that times out waiting says what the server said."""

        @classmethod
        def connect(cls, conninfo: str = "", **kwargs):
            try:
                conn = super().connect(conninfo, **kwargs)
            except psycopg.Error as exc:
                if entry_box:
                    entry_box[0].last_error = _first(exc)
                raise
            if entry_box:
                entry_box[0].last_error = ""
            return conn

    # Its INFO lines are one per connection handed out: the pool's warnings only.
    logging.getLogger("psycopg.pool").setLevel(logging.WARNING)
    return psycopg_pool.ConnectionPool(
        "", kwargs=_kwargs(c, password, CONNECT_TIMEOUT_S), connection_class=Recording,
        min_size=POOL_MIN, max_size=POOL_MAX, timeout=POOL_WAIT_S, name=POOL_NAME,
        reconnect_timeout=POOL_RECONNECT_S, open=True)


def _entry():
    """``(entry, config)``: this process's pool for the settings now, made when there is none,
    when a setting (or the password) changed, in a forked child, or after the last pool failed.
    A new pool is made only after a fresh sign-in succeeds, so a database that does not answer
    is named in the server's words at once, as `connect` names it."""
    global _ENTRY
    c, password, psycopg = _resolve()
    psycopg_pool = _pool_module()
    key = (os.getpid(), c["host"], c["port"], c["name"], c["user"], _tag(password))
    with _LOCK:
        current = _ENTRY
        if current is not None and current.key == key and not current.retired:
            return current, c
    try:
        psycopg.connect(**_kwargs(c, password, CONNECT_TIMEOUT_S)).close()
    except psycopg.Error as exc:
        raise _refused(c, _first(exc)) from None
    with _LOCK:
        current = _ENTRY
        if current is not None and current.key == key and not current.retired:
            return current, c                 # another thread made it meanwhile
        box: list = []
        made = _Entry(key, _new_pool(psycopg, psycopg_pool, c, password, box))
        box.append(made)
        if current is not None and not current.retired:
            _retire(current)              # a forked child's parent pool is kept, never closed
        _ENTRY = made
        log.info("records_db: a pool of up to %d connection(s) for %s@%s:%s/%s in process %d",
                 POOL_MAX, c["user"], c["host"], c["port"], c["name"], os.getpid())
        return made, c


def _checkout(psycopg_pool):
    """A pooled connection that answers, or `Unavailable`. One that does not (the server
    restarted under the pool) retires the pool and is tried once more on a new one."""
    for attempt in (1, 2):
        entry, c = _entry()
        try:
            conn = entry.pool.getconn(timeout=POOL_WAIT_S)
        except psycopg_pool.PoolClosed:
            continue                          # another thread retired it: the next pool
        except psycopg_pool.PoolTimeout:
            if entry.last_error:
                with _LOCK:
                    if not entry.retired:
                        _retire(entry)
                raise _refused(c, entry.last_error) from None
            raise Unavailable(f"no connection to {c['user']}@{c['host']}:{c['port']}/"
                              f"{c['name']} came free within {POOL_WAIT_S} s: all "
                              f"{POOL_MAX} of this process's are in use") from None
        try:
            psycopg_pool.ConnectionPool.check_connection(conn)
        except Exception as exc:                      # noqa: BLE001 (a broken connection)
            entry.pool.putconn(conn)
            with _LOCK:
                if not entry.retired:
                    _retire(entry)
            if attempt == 2:
                raise _refused(c, _first(exc)) from None
            continue
        return entry, conn
    raise Unavailable("the records database's pool was replaced twice while this store "
                      "waited for a connection")


@contextlib.contextmanager
def pooled():
    """A connection from this process's pool, as ``with records_db.pooled() as conn:``: the
    transaction committed when the block ends and rolled back when it raises (as a fresh
    connection's ``with`` does), and the connection returned to the pool, never closed.
    `Unavailable` names why there is none, in `connect`'s words."""
    entry, conn = _checkout(_pool_module())
    try:
        with conn:
            yield conn
    finally:
        entry.pool.putconn(conn)


def pool_stats() -> dict:
    """This process's pool's counters (psycopg_pool's `get_stats`), ``{}`` when there is none."""
    entry = _ENTRY
    if entry is None or entry.retired or entry.key[0] != os.getpid():
        return {}
    return dict(entry.pool.get_stats())


def loopback(host: str, resolve=None) -> tuple:
    """``(ok, addresses)``: whether every address *host* names is a loopback one, and those
    addresses, for the card. *resolve* is `socket.getaddrinfo`, for tests."""
    try:
        infos = (resolve or socket.getaddrinfo)(host, None)
    except OSError as exc:
        return False, f"{host} did not resolve: {exc}"
    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        return False, f"{host} named no address"
    ok = all(ipaddress.ip_address(a.split("%")[0]).is_loopback for a in addresses)
    return ok, ", ".join(addresses)


def test_connection(write: bool = True, connector=None, resolve=None) -> dict:
    """The Test, in `TEST_STEPS` order: ``{"ok", "steps": [{"name", "ok", "detail"}],
    "error"}``. The first step that fails is named with what the server said, and the rest are
    not tried (the card names them "not tried"). With *write* false, everything but the write
    (a reader's, which writes nothing). *resolve* is `socket.getaddrinfo`, for tests."""
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
            owner = conn.execute("select pg_catalog.pg_get_userbyid(datdba), current_user "
                                 "from pg_catalog.pg_database "
                                 "where datname = current_database()").fetchone()
            if owner is None or owner[0] != owner[1]:
                return failed("owner", f"the database {c['name']} is owned by "
                                       f"{owner[0] if owner else 'nobody readable'}, not "
                                       f"{c['user']} (host step 6a makes {c['user']} its owner)")
            steps.append({"name": "owner", "ok": True,
                          "detail": f"{owner[1]} owns the database {c['name']}"})
            row = conn.execute("select current_user, rolsuper from pg_roles "
                               "where rolname = current_user").fetchone()
            if row is None:
                return failed("role", f"{c['user']}'s role could not be read from pg_roles")
            if row[1]:
                return failed("role", f"{row[0]} is a superuser; Mercury's role owns its "
                                      "database and nothing more (P4-1)")
            steps.append({"name": "role", "ok": True,
                          "detail": f"{row[0]} is not a superuser"})
            ok, addresses = loopback(c["host"], resolve)
            if not ok:
                return failed("loopback", f"Mercury reaches it at {c['host']} ({addresses}), "
                                          "not a loopback address: host step 6a publishes it "
                                          "on loopback only, so this is another server or "
                                          "the port is offered beyond this host")
            steps.append({"name": "loopback", "ok": True,
                          "detail": f"Mercury reaches it on loopback ({addresses}), the only "
                                    "address host step 6a publishes it on"})
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
