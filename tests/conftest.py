"""Shared test setup.

`redact.known_secret_values()` caches for 30 seconds so a burst of log records
does not decrypt the credential store once per line. In a test suite that TTL
is cross-contamination: a test that monkeypatches the store inherits whatever
the previous test built, and the failure looks like a redaction bug rather than
a fixture one.

Cleared before and after every test — cheap, and it makes each test's view of
the store its own.
"""

import os
import shutil
import sys
import tempfile

import pytest

# ---------------------------------------------------------------------------
# THE SUITE NEVER TOUCHES THE LIVE STORE (2026-09-26)
# ---------------------------------------------------------------------------
# Run from a checkout, the suite wrote fixture lists into `data/`, and the
# per-test guard below looked only for NEW paths, so paths that already
# existed made it blind: the suite passed here because of this checkout's
# residue and its settings file, and 19 tests errored in a pristine one.
#
# So the whole store moves, before anything imports `modules.config`: this
# file is imported by pytest ahead of every test module. It is ALWAYS a fresh
# directory, never an inherited NMAS_DATA_DIR, which could name a real store.
_CHECKOUT_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
#
# ONCE PER PROCESS. A test that imports `tests.conftest` for a constant
# executes this file a second time under another module name, and the first
# version then moved NMAS_DATA_DIR mid-session (measured 2026-09-26). The
# owner pid makes the second execution adopt the store instead; a subprocess
# has its own pid and never runs this file anyway.
if os.environ.get("NMAS_TEST_STORE_OWNER") == str(os.getpid()):
    _TEST_DATA_DIR = os.environ["NMAS_DATA_DIR"]
else:
    _TEST_DATA_DIR = tempfile.mkdtemp(prefix="nmas-test-data-")
    os.environ["NMAS_DATA_DIR"] = _TEST_DATA_DIR
    os.environ["NMAS_TEST_STORE_OWNER"] = str(os.getpid())


from tests.store_guard import data_tree, tree_changes  # noqa: E402
from tests import store_guard  # noqa: E402
from tests import home_guard  # noqa: E402
home_guard.run_id()     # set before xdist starts its workers, which inherit it

# Every write the test process makes under the checkout's data/ is SEEN (an
# audit hook), so a change there can be attributed rather than assumed.
if getattr(store_guard, "_watch", None) is None:
    store_guard._watch = store_guard.install_write_watch(_CHECKOUT_DATA_DIR)

# ---------------------------------------------------------------------------
# NO TEST TOUCHES A NETWORK, and a run says whether that covers what it starts
# ---------------------------------------------------------------------------
# Installed at import, before anything imports the program. See
# tests/network_guard.py for the two layers and why each exists (C46).
from tests import network_guard  # noqa: E402

network_guard.install()
_NETWORK_STATE = network_guard.confinement()
# Every process a test starts, by construction, on every machine (C46): see
# network_guard.SpawnGuard. Its own directory, never inside the test store,
# which some tests delete and restore mid-session.
if network_guard.spawn_guard() is None:
    network_guard.install_spawn_guard(tempfile.mkdtemp(prefix="nmas-test-spawn-"))


@pytest.fixture(scope="session", autouse=True)
def _fakes_live_under_pytests_temporary_tree(tmp_path_factory):
    network_guard.spawn_guard().fakes_under = os.path.realpath(str(tmp_path_factory.getbasetemp()))
    network_guard.spawn_guard().checkout_data = os.path.realpath(_CHECKOUT_DATA_DIR)
    yield


@pytest.fixture(autouse=True)
def _no_test_writes_into_the_checkout_data(request):
    """A write the test process made into the checkout's data/ fails the test
    that made it, by name (seen by an audit hook, not inferred from a
    directory that the running app also writes)."""
    watch = store_guard._watch
    watch.current = request.node.nodeid
    start = len(watch.writes)
    yield
    watch.current = ""
    mine = watch.writes[start:]
    if mine:
        pytest.fail(f"this test wrote into the checkout's data/: {[(e, p) for _t, e, p in mine][:5]}",
                    pytrace=False)


#: What Flask-SocketIO's test client replaces on the APP'S OWN server and never puts back
#: (flask_socketio/test_client.py, 5.3.6: `socketio.server._send_packet = _mock_send_packet`).
SOCKETIO_PATCHED = ("_send_packet", "_send_eio_packet")


@pytest.fixture(autouse=True)
def _socketio_server_sends_to_real_clients():
    """After each test, the app's Socket.IO server sends through its own methods again.

    A test that makes `socketio.test_client(app)` diverts every packet the server sends,
    for the rest of the process, into that client's mock: a real browser's page in a later
    test then never hears its connect, and its live channel never connects. That was CI's
    red from ca52963 to 64d4377 (test_attention_badge's three live tests, run in a worker
    after test_announce); the local gate never ran a browser test in the same process as
    a test client. Restored for every test, so no list of offending files is kept."""
    yield
    app = sys.modules.get("app")
    server = getattr(getattr(app, "socketio", None), "server", None)
    if server is not None:
        for name in SOCKETIO_PATCHED:
            server.__dict__.pop(name, None)


@pytest.fixture(autouse=True)
def _no_spawned_process_reaches_a_network(request, _fakes_live_under_pytests_temporary_tree):
    """A child that tried to reach a real endpoint fails the test that
    started it, by name: the child's own error is often swallowed by the
    code under test, which is how C46's request went unseen."""
    guard = network_guard.spawn_guard()
    guard.current = request.node.nodeid
    guard.offset, _ = guard.attempts(0)
    yield
    _, tried = guard.attempts(guard.offset)
    guard.current = ""
    if tried:
        pytest.fail("a process this test started did something no test may do (a "
                    "network, C46; or a write into the checkout's data/), and the harness "
                    f"recorded it: {tried[:5]}", pytrace=False)


def pytest_report_header(config):
    return network_guard.report_line(_NETWORK_STATE)


def pytest_sessionstart(session):
    if os.environ.get(network_guard.REQUIRE_ENV) == "1" and _NETWORK_STATE[0] is not True:
        pytest.exit(f"{network_guard.REQUIRE_ENV}=1 and this run is not confined: "
                    f"{network_guard.report_line(_NETWORK_STATE)}", returncode=2)
    session.nmas_checkout_data_before = data_tree(_CHECKOUT_DATA_DIR)
    session.nmas_home_before = home_guard.snapshot()
    _register_stack_dump(session)
    session.config._nmas_t0 = __import__("time").time()


def pytest_sessionfinish(session, exitstatus):
    """The checkout's data/ must hold nothing a TEST wrote. A change no test
    made is judged against a measured fact, not an assumption: on the
    deployment host the app runs from this checkout and writes its own data/
    while the suite runs (its approval queue, measured 2026-09-26), and the
    suite reads only its own store, so that change is reported and does not
    fail the run. With no app process running from here, an unexplained
    change still fails it."""
    import sys
    changed = tree_changes(getattr(session, "nmas_checkout_data_before", {}),
                           data_tree(_CHECKOUT_DATA_DIR))
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
    shutil.rmtree(network_guard.spawn_guard().root, ignore_errors=True)
    fail, message = store_guard.judge(
        changed, store_guard._watch.writes, _CHECKOUT_DATA_DIR,
        lambda: store_guard.processes_running_from(os.path.dirname(_CHECKOUT_DATA_DIR)))
    if message:
        sys.stderr.write("\n" + message + "\n")
        if fail:
            _ci_annotate("error", "the session guard failed the run", message)
    if fail:
        session.exitstatus = 1
    # The person's home (C391, C392): judged by the process that ran the whole session, so a
    # session still open in another xdist worker is not one left behind; each worker names
    # the folders its own sessions could not remove.
    browser_mod = sys.modules.get("tests.browser")
    left = list(getattr(browser_mod, "LEFT_BEHIND", []) or [])
    worker = hasattr(session.config, "workerinput")
    home = (home_guard.judge({}, {}, left) if worker else
            home_guard.judge(getattr(session, "nmas_home_before", {}), home_guard.snapshot(), left))
    if home:
        sys.stderr.write("\n" + home + "\n")
        _ci_annotate("error", "the run touched the home", home)
        session.exitstatus = 1
    leaked = leaked_threads()
    if leaked:
        message = ("the session ended with NON-DAEMON threads still alive, which keep this "
                   "process from exiting (the operator, 2026-10-01: CI run #241 timed out at "
                   "the session's end with a live server's threads in a worker): "
                   + "; ".join(leaked))
        sys.stderr.write("\n" + message + "\n")
        _ci_annotate("error", "threads left alive at the session's end", message)
        session.exitstatus = 1


#: How long the session end waits for a non-daemon thread to finish on its own
#: before naming it: a thread finishing its last second of work is not a leak.
LEAK_GRACE_SECONDS = 5


def leaked_threads(grace: float = LEAK_GRACE_SECONDS) -> list:
    """Every NON-DAEMON thread but this one still alive after *grace* seconds,
    named with where it started. A daemon thread cannot hold the process open,
    so it is not one; a non-daemon one can, and is named instead of becoming
    a 300 s timeout with nothing in progress."""
    import threading
    import time

    me = threading.current_thread()
    deadline = time.monotonic() + grace
    alive = []
    for t in threading.enumerate():
        if t is me or t.daemon or t is threading.main_thread():
            continue
        t.join(timeout=max(0.0, deadline - time.monotonic()))
        if t.is_alive():
            target = getattr(t, "_target", None)
            alive.append(f"{t.name} (target {getattr(target, '__qualname__', target)!s})")
    return alive


def _ci_annotate(level: str, title: str, message: str) -> None:
    """A GitHub Actions workflow command, so a failure is readable from the
    public API. The job log needs authentication and the annotations do not:
    a red run whose reason only the log holds cannot be diagnosed from here
    (232d001, 2026-09-27: 'Process completed with exit code 1', nothing
    else). Inert outside Actions."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    esc = lambda t: str(t).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{level} title={esc(title).replace(',', '%2C').replace(':', '%3A')}::"
          f"{esc(message)[:4000]}", flush=True)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """One annotation per failed or erroring test (GitHub keeps ten per
    step, so the first ten), naming the test and its first error line. Runs
    in the controller under xdist, which receives every worker's reports."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    bad = (terminalreporter.stats.get("failed", []) + terminalreporter.stats.get("error", []))
    for report in bad[:10]:
        text = str(getattr(report, "longreprtext", "") or report.longrepr or "")
        first = next((l for l in text.splitlines() if l.startswith("E ")), text[-600:])
        _ci_annotate("error", report.nodeid, first)
    if len(bad) > 10:
        _ci_annotate("error", "more failures", f"{len(bad) - 10} more not annotated")


@pytest.fixture(scope="session", autouse=True)
def _the_store_is_the_test_store():
    """Stop at once if the redirect did not take: every later assertion
    about isolation would be about the wrong directory."""
    from modules import config

    if os.path.realpath(config.DATA_DIR) != os.path.realpath(_TEST_DATA_DIR):
        pytest.exit(f"modules.config.DATA_DIR is {config.DATA_DIR}, not the test "
                    f"store {_TEST_DATA_DIR}: something imported it before "
                    "conftest set NMAS_DATA_DIR", returncode=2)
    yield


@pytest.fixture(scope="session", autouse=True)
def _import_the_application_first(_the_store_is_the_test_store):
    """Import the whole program before any test can patch it (register C20).

    Several modules bind a function by NAME at import
    (`from modules.settings_schema import get_setting`), so a module imported
    for the FIRST time while a test has that function monkeypatched keeps
    the test's stub for the rest of the process. Measured: `test_onboard_plan`'s
    `lab` fixture replaces `settings_schema.get_setting` with a lambda
    answering unlisted keys with the schema default, and when it ran before
    anything had imported `app`, `modules.integrations.base` was first
    imported inside that fixture. Every later `get_config()` then read settings
    through the lambda, and the Kea route echoed `kea_username` as `''`
    after writing it correctly. The full suite never showed it, because an
    earlier test always imported `app` first. A subset in another order
    failed every time.

    The program imports everything at start-up, so the harness does too.

    **And it takes the app's log file back off.** Importing `app` attaches a
    RotatingFileHandler for `logs/device_manager.log` to the ROOT logger, in
    whatever checkout the suite runs in. Measured on the host 2026-09-26: a
    suite run there on 2026-09-23 wrote fixture lines into the live app log,
    24 of them ERRORs from `save_golden` refusing devices called `BRAND-NEW`
    and `never-seen` on a list called `Lab`. That log is the channel
    `nmas-netbox-modified` counts recorder failures from (C5), so a test run
    would read as failures of the running app.
    """
    import importlib
    import logging
    import os as _os
    import pkgutil

    # A PROBE run (tests/test_suite_bound.py drives the real runner over a one-test file
    # with a 5 s bound) skips the whole-program import: its start would otherwise grow with
    # the program, and on CI's cold, two-core runner it passed the bound (run #312,
    # 2026-10-02, two modules after the last pass). The isolation this import buys is for
    # the real suite; a probe's one trivial test patches nothing.
    if _os.environ.get("NMAS_PROBE_RUN") == "1":
        return

    import app  # noqa: F401
    import modules
    import routes

    # **"The program imports everything at start-up" is false for LAZY
    # imports** (2026-09-28, the laptop's first 24-worker run). `app` loads
    # `modules.agent_timers` only inside the functions that use it, so the
    # first importer on an xdist worker could be a fixture that had just
    # patched `config.DATA_DIR` (`test_drift_routes`'s client: DATA_DIR, then
    # `monkeypatch.setattr("modules.agent_timers.save", ...)`, which imports
    # the module to patch it). The module then bound `_TIMERS_FILE` inside
    # that test's tmp_path for the rest of the worker, and
    # `test_derived_paths_follow_it` failed on whichever worker drew both.
    # Serial runs and 4 workers had always imported it earlier by chance.
    # So every module and route is imported here, before any test: 117,
    # measured to start no thread.
    for pkg in (modules, routes):
        for info in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
            importlib.import_module(info.name)

    # **And it initialises the store, as the first page load does** (C43,
    # C45). The first read of the device-list config creates the default
    # list, so whichever test happened to run first was charged with it by
    # the per-test store guard: `test_newest_content_wins` errored when its
    # file ran alone and passed in the full suite, and under 4 xdist workers
    # 83 and 107 tests were charged with it (2026-09-26). A real install is
    # initialised before anybody uses it; so is the harness, once.
    from modules import device
    device._load_device_lists_config()

    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "baseFilename", "").endswith("device_manager.log"):
            root.removeHandler(handler)
            handler.close()


#: The person every test is, unless it asks for the real identity layer.
TEST_PERSON = "test-person@example.invalid"


@pytest.fixture(autouse=True)
def _a_verified_person_by_default(request, monkeypatch):
    """Every request in a test comes from a verified PERSON, by default.

    P.3 put one identity gate in front of every mutating route
    (`modules/route_gates.py`). Before it, most of the suite POSTed to routes
    with no identity at all and passed only because those routes had no gate,
    which is register B12 seen from the test side. So the harness now says
    who is asking, and a test that is ABOUT identity opts out with
    ``@pytest.mark.real_identity`` and meets the real ``identify()``.

    This patches ``identify`` and nothing below it, so ``may()``, the service
    rules and the refusal shapes still run for real on every gated request.
    """
    if request.node.get_closest_marker("real_identity"):
        yield
        return
    from modules import identity

    person = identity.Identity(actor=TEST_PERSON, email=TEST_PERSON,
                               kind="person", verified=True, outcome="ok",
                               peer="198.51.100.7", peer_trusted=True,
                               header_present=True)
    monkeypatch.setattr(identity, "identify", lambda _request: person)
    yield


@pytest.fixture(autouse=True)
def _deploy_receipts_go_to_a_temp_file(request, monkeypatch, tmp_path):
    """Every deploy and restore apply appends a receipt per device (C60), into
    the list's directory. In the suite that is the shared test store, so each
    test that drives an apply would leave a file there, which the store guard
    rightly refuses. The receipt goes to THIS test's own directory instead,
    where a test can read it back (`receipts.read`). The rotation record's
    fixture below is the precedent. A test about the real path opts out with
    ``@pytest.mark.real_receipts_path``."""
    if request.node.get_closest_marker("real_receipts_path"):
        yield
        return
    from modules.nsot import receipts

    monkeypatch.setattr(receipts, "path_for",
                        lambda list_name: str(tmp_path / f"{list_name}__deploy_receipts.jsonl"))
    yield


@pytest.fixture(autouse=True)
def _rotation_record_goes_to_a_temp_file(monkeypatch, tmp_path):
    """Every rotate() and persist() appends to the rotation record (P.3 step
    12), and in the suite DATA_DIR is this checkout's data/: a test run would
    write fixture rotations where a person reads real ones (C26's rule)."""
    from modules.nsot import credential_rotation
    monkeypatch.setattr(credential_rotation, "_rotation_record_path",
                        lambda: str(tmp_path / "rotation_audit.jsonl"))
    yield


@pytest.fixture(autouse=True)
def _fresh_redaction_cache():
    from modules import redact

    redact.invalidate_cache()
    redact.reset_health()
    yield
    redact.invalidate_cache()
    redact.reset_health()


#: Tests allowed to create paths in the store, each with the finding that
#: makes it so. Capped, and each one must still create something (no ghosts):
#: an exemption that outlives its reason is the check switched off quietly.
STORE_WRITERS_EXEMPT = {
    "tests/test_p3_secrets_write_only.py::TestNoGetReturnsASecret::"
    "test_no_argument_free_get_carries_a_planted_secret":
        "register C33: 10 of 80 argument-free GET routes write to the store; "
        "this test calls all of them",
}
assert len(STORE_WRITERS_EXEMPT) <= 3


@pytest.fixture(autouse=True)
def _no_test_writes_into_live_data(request):
    """No test may create a path in the store, except a named exemption.

    **Since 2026-09-26 the store is a temporary directory** (NMAS_DATA_DIR,
    set at the top of this file), and the live `data/` is guarded for the
    whole session by `pytest_sessionfinish`. What this per-test check now
    catches is a test, or the product path it drives, WRITING where it should
    only read. That is how it found `/deploy/plan` and the onboarding plan
    creating directories, the moment the store stopped being pre-populated
    with the residue that hid them.

    History, from when it watched the live store:

    Found while building the intent editor. A fixture called
    ``save_golden("lab", ...)`` **before** monkeypatching
    ``get_list_data_dir``, so the call resolved its own path and wrote
    ``data/lists/lab/config_repo/golden/s4.cfg`` into the working checkout.
    The list name was arbitrary — had it been ``default`` it would have
    written into the live list, whose goldens are the record of a real
    network.

    ``data/`` is gitignored, so nothing would have reached a commit and
    nothing would have said a word.

    This is the same rule as "no test touches a live network", applied to the
    other thing a test can reach.

    It compares the set of FILES, not of list directories. A first version
    compared directory names and did not catch the very bug it was written
    for: `lab` already existed, so writing a new golden into it changed no
    name. Verified by reintroducing the bug and watching the guard pass —
    which is the only way to know a guard guards anything.
    """
    import os

    from modules.config import LISTS_DIR

    def _snapshot():
        """Directories AND files.

        The first version compared directory names and missed a golden
        written into a list that already existed. The second compared files
        and missed a list directory created with nothing in it —
        `get_list_data_dir()` calls `os.makedirs()`, so merely *resolving* a
        path for an unknown list leaves one behind.

        Each version caught what the other missed, which is the argument for
        the union rather than for choosing between them.
        """
        found = set()
        for root, dirs, files in os.walk(LISTS_DIR):
            # `.git` inside a config_repo churns on any read (gc, logs, index
            # refreshes) and is not what a test polluting live data leaves.
            if os.sep + ".git" in root:
                continue
            for name in dirs:
                if name != ".git":
                    found.add(os.path.join(root, name) + os.sep)
            for name in files:
                found.add(os.path.join(root, name))
        return found

    before = _snapshot()
    yield
    created = sorted(_snapshot() - before)

    # Clean up what THIS test created, then report it.
    #
    # Without the cleanup only the first offender in a run is visible: every
    # later one finds the directory already there and the guard says nothing.
    # Removing it makes one pass name them all, and it removes only paths
    # that did not exist when this test started.
    import shutil

    for path in sorted(created, key=len, reverse=True):
        try:
            if path.endswith(os.sep):
                shutil.rmtree(path.rstrip(os.sep), ignore_errors=True)
            elif os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    exempt = STORE_WRITERS_EXEMPT.get(request.node.nodeid)
    if exempt:
        assert created, (f"{request.node.nodeid} is exempt from the store guard "
                         f"({exempt}) and created nothing: remove the exemption")
        return
    assert not created, (
        f"this test created {created[:5]} in the store "
        f"({LISTS_DIR}). Patch `modules.config.get_list_data_dir` BEFORE "
        f"anything that resolves a path through it — `get_list_data_dir()` "
        f"calls os.makedirs(), so merely resolving a path is enough.")


@pytest.fixture
def intent_matches(monkeypatch):
    """Every capture reads as MATCHING its committed intent, for tests about
    baseline MECHANICS (tags, hooks, coverage, messages).

    Since 2026-09-27 a baseline needs every capture to match committed intent
    (register C89 (c)), and a fixture device with no committed intent is
    `unknown`, which correctly earns nothing. The comparison itself is tested
    against real renders in `test_intent_match.py`. A test that uses this AND
    asserts a denial on intent grounds would be testing nothing, so none does."""
    from modules.nsot import intent_match as im

    monkeypatch.setattr(im, "intent_match",
                        lambda repo, list_name, hostname, config_text, platform="": {
                            "state": "match", "adds": 0, "removes": 0, "reordered": 0,
                            "lines": [], "why": ""})


# ---------------------------------------------------------------------------
# What was running when a bound fired (scripts/nmas-test)
# ---------------------------------------------------------------------------
#
# A timeout that fires should say WHERE it hung (the operator, 2026-09-28):
# the difference between a five-minute diagnosis and an hour. nmas-test sets
# NMAS_TEST_INFLIGHT to a directory; each test process (the main one, or each
# xdist worker) keeps the test it has started in `running-<process>` and
# clears it when that test finishes, and dumps every thread's stack into
# `stack-<process>` when the bound's SIGTERM arrives. A plain `pytest` run
# sets nothing and this is inert.
#
# The per-TEST bound is pytest.ini's `faulthandler_timeout`, which dumps the
# stack of a single test that runs too long without stopping the run.

def _inflight_file(kind):
    d = os.environ.get("NMAS_TEST_INFLIGHT", "")
    if not d or not os.path.isdir(d):
        return ""
    return os.path.join(d, f"{kind}-{os.environ.get('PYTEST_XDIST_WORKER', 'main')}")


def _register_stack_dump(session):
    """Called from pytest_sessionstart above: a second hook of the same name
    in this file would silently replace the first (C90's shape, a name for a
    key), and with it the confinement check."""
    path = _inflight_file("stack")
    if path:
        import faulthandler
        import signal

        # Kept open for the process's life: faulthandler writes from the
        # signal handler to this descriptor. To a FILE, because pytest's fd
        # capture owns stderr while a test runs, and a dump into the capture
        # is lost with the process. chain=True: the SIGTERM still ends it.
        fh = open(path, "w", encoding="utf-8")
        session.config._nmas_stack_file = fh
        faulthandler.register(signal.SIGTERM, file=fh, all_threads=True, chain=True)


def pytest_runtest_logstart(nodeid, location):
    from tests import run_history

    run_history.record(nodeid)
    path = _inflight_file("running")
    if path:
        import time

        # A test outside the rootdir has a nodeid with no file ("::name"); the
        # location's path names it, so the report never loses the file.
        name = f"{location[0]}{nodeid}" if nodeid.startswith("::") else nodeid
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"{name}\t{time.time():.0f}\n")


def pytest_runtest_logreport(report):
    """WHEN the tests finished, recorded by the process that sees every report
    (the controller under xdist, else the one process): the number done and the
    time of the last, rewritten as each finishes. A timeout with no test in
    progress then says whether the tests had finished and how long ago, so
    the time spent at the session's end is a number, not a guess (the
    operator, 2026-10-01, run #241)."""
    import time

    if report.when != "teardown" or _is_worker():
        return
    _PROGRESS["done"] += 1
    _PROGRESS["last"] = time.time()
    path = _inflight_file("progress")
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"{_PROGRESS['done']}\t{_PROGRESS['last']:.1f}\n")


_PROGRESS = {"done": 0, "last": None}


def _is_worker() -> bool:
    return bool(os.environ.get("PYTEST_XDIST_WORKER"))


def pytest_unconfigure(config):
    """The run's two numbers, said last (and annotated in CI, where the log
    needs authentication and annotations do not): when the last test finished
    after the start, and how long the session took to END after it
    (coverage's report, fixture teardown, worker shutdown). The bound is
    judged against both (the operator: "so we know how close it sits to the
    limit")."""
    import time

    t0 = getattr(config, "_nmas_t0", None)
    if _is_worker() or t0 is None or _PROGRESS["last"] is None:
        return
    now = time.time()
    line = (f"nmas-test timing: {_PROGRESS['done']} test(s); the last finished "
            f"{_PROGRESS['last'] - t0:.0f} s after the session started, and the session "
            f"ended {now - _PROGRESS['last']:.0f} s after that ({now - t0:.0f} s in all; "
            f"the bound is {os.environ.get('NMAS_TEST_TIMEOUT', '300')} s)")
    import sys
    sys.stderr.write(line + "\n")
    _ci_annotate("notice", "suite timing", line)


def pytest_runtest_logfinish(nodeid, location):
    path = _inflight_file("running")
    if path:
        open(path, "w", encoding="utf-8").close()
