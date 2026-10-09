"""A throwaway PostgreSQL for the records tests (Phase 4; the operator's decision, option a: a
real PostgreSQL in CI and locally, never a stand-in).

Started BY THE SUITE inside its own network namespace (C46): a server on the runner's network
(a CI service container) would be out of the confined suite's reach, so the binaries are unpacked
(never installed as a service, like promtool) and run from a temporary folder on loopback, with
the same shape host step 6a makes: a superuser, and the role `mercury` (not a superuser)
owning the database `mercury`, signing in by password (scram-sha-256) over TCP.

Where they come from: ``NMAS_PG_BIN`` (a `bin` folder), else the unpacked copy at
``~/.local/share/nmas-pg`` (CI's workflow and the laptop), else Ubuntu's own
``/usr/lib/postgresql/<n>/bin``. psycopg loads libpq through the system's library cache (CI and
the host install libpq5) or ``LD_LIBRARY_PATH`` (the laptop's unpacked copy).

Absent binaries or an unloadable libpq SKIP with the reason, except where
``NMAS_REQUIRE_PG=1`` (CI's workflow): there they FAIL, so CI never passes by skipping them.
"""

import glob
import os
import shutil
import socket
import subprocess
import tempfile
import time

import pytest

UNPACKED = os.path.expanduser("~/.local/share/nmas-pg")
SUPER_PW = "suite-superuser-pw"
MERCURY_PW = "suite-mercury-pw-1234567890"
#: Measured on the laptop, 2026-10-09: initdb about 1.5 s, start under 1 s. Each bound 2.5x a
#: generous round of that, named when it fires.
INITDB_BOUND_S = 60
START_BOUND_S = 30


def required() -> bool:
    return os.environ.get("NMAS_REQUIRE_PG") == "1"


def _unavailable(why: str):
    if required():
        pytest.fail(f"NMAS_REQUIRE_PG=1 and the real PostgreSQL is not usable: {why}")
    pytest.skip(f"no real PostgreSQL here ({why}); NMAS_REQUIRE_PG=1 makes this a failure")


def bin_dir() -> str:
    """The folder holding initdb, pg_ctl and postgres, or ``""``."""
    env = os.environ.get("NMAS_PG_BIN", "")
    candidates = ([env] if env else []) + sorted(
        glob.glob(os.path.join(UNPACKED, "usr/lib/postgresql/*/bin")), reverse=True) + sorted(
        glob.glob("/usr/lib/postgresql/*/bin"), reverse=True)
    for d in candidates:
        if all(os.access(os.path.join(d, n), os.X_OK) for n in ("initdb", "pg_ctl", "postgres")):
            return d
    return ""


def _env() -> dict:
    """The child processes' environment: the unpacked copy's libpq on their library path."""
    env = dict(os.environ)
    lib = os.path.join(UNPACKED, "usr/lib/x86_64-linux-gnu")
    if os.path.isdir(lib):
        env["LD_LIBRARY_PATH"] = ":".join(p for p in (lib, env.get("LD_LIBRARY_PATH", "")) if p)
    return env


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Instance:
    """One running server: ``host``, ``port``, ``url()``; ``stop()`` removes it."""

    def __init__(self, folder: str, bindir: str, port: int):
        self.folder, self.bindir, self.port, self.host = folder, bindir, port, "127.0.0.1"

    def connect(self, user="mercury", password=MERCURY_PW, dbname="mercury", **kw):
        import psycopg
        return psycopg.connect(host=self.host, port=self.port, user=user, password=password,
                               dbname=dbname, connect_timeout=10, **kw)

    def stop(self):
        subprocess.run([os.path.join(self.bindir, "pg_ctl"), "-D", os.path.join(self.folder,
                        "data"), "-m", "immediate", "stop"], env=_env(), capture_output=True,
                       timeout=START_BOUND_S)
        shutil.rmtree(self.folder, ignore_errors=True)


def start() -> Instance:
    """A fresh server shaped as host step 6a makes it, or skip/fail naming why there is none."""
    try:
        import psycopg  # noqa: F401  (libpq is loaded here, or not)
    except ImportError as exc:
        _unavailable(f"psycopg could not be loaded: {str(exc).splitlines()[0]}")
    bindir = bin_dir()
    if not bindir:
        _unavailable(f"no initdb, pg_ctl and postgres in NMAS_PG_BIN, {UNPACKED} or "
                     "/usr/lib/postgresql/*/bin")
    folder = tempfile.mkdtemp(prefix="nmas-pg-")
    data, env = os.path.join(folder, "data"), _env()
    with open(os.path.join(folder, "pw"), "w") as fh:
        fh.write(SUPER_PW + "\n")
    init = subprocess.run([os.path.join(bindir, "initdb"), "-D", data, "-U", "postgres",
                           "--auth-local=trust", "--auth-host=scram-sha-256",
                           f"--pwfile={os.path.join(folder, 'pw')}", "-E", "UTF8"],
                          env=env, capture_output=True, text=True, timeout=INITDB_BOUND_S)
    if init.returncode != 0:
        shutil.rmtree(folder, ignore_errors=True)
        _unavailable(f"initdb failed: {(init.stderr or init.stdout).strip().splitlines()[-1:]}")
    port = _free_port()
    run = subprocess.run([os.path.join(bindir, "pg_ctl"), "-D", data, "-l",
                          os.path.join(folder, "pg.log"), "-w", "-t", str(START_BOUND_S), "-o",
                          f"-c listen_addresses=127.0.0.1 -p {port} -k {folder}", "start"],
                         env=env, capture_output=True, text=True, timeout=START_BOUND_S + 10)
    if run.returncode != 0:
        log = open(os.path.join(folder, "pg.log")).read()[-400:] if os.path.exists(
            os.path.join(folder, "pg.log")) else ""
        shutil.rmtree(folder, ignore_errors=True)
        _unavailable(f"the server did not start in {START_BOUND_S} s: {log.strip()}")
    inst = Instance(folder, bindir, port)
    import psycopg
    with psycopg.connect(host=folder, port=port, user="postgres", dbname="postgres",
                         autocommit=True, connect_timeout=10) as c:
        c.execute(f"create role mercury login password '{MERCURY_PW}'")
        c.execute("create database mercury owner mercury")
        c.execute("revoke all on database mercury from public")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:          # the role signs in by password, over TCP
        try:
            inst.connect().close()
            break
        except Exception:                           # noqa: BLE001
            time.sleep(0.1)
    return inst
