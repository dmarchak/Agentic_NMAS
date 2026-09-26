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

# ---------------------------------------------------------------------------
# NO TEST TOUCHES A NETWORK, and a run says whether that covers what it starts
# ---------------------------------------------------------------------------
# Installed at import, before anything imports the program. See
# tests/network_guard.py for the two layers and why each exists (C46).
from tests import network_guard  # noqa: E402

network_guard.install()
_NETWORK_STATE = network_guard.confinement()


def pytest_report_header(config):
    return network_guard.report_line(_NETWORK_STATE)


def pytest_sessionstart(session):
    if os.environ.get(network_guard.REQUIRE_ENV) == "1" and _NETWORK_STATE[0] is not True:
        pytest.exit(f"{network_guard.REQUIRE_ENV}=1 and this run is not confined: "
                    f"{network_guard.report_line(_NETWORK_STATE)}", returncode=2)
    session.nmas_checkout_data_before = data_tree(_CHECKOUT_DATA_DIR)


def pytest_sessionfinish(session, exitstatus):
    """The live store must be byte-for-byte what it was. Any change fails the
    run, naming the paths, even if every test passed."""
    changed = tree_changes(getattr(session, "nmas_checkout_data_before", {}),
                           data_tree(_CHECKOUT_DATA_DIR))
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
    if changed:
        import sys
        sys.stderr.write(
            f"\nTHE SUITE CHANGED THE CHECKOUT'S data/ ({_CHECKOUT_DATA_DIR}): "
            f"{len(changed)} path(s), first {changed[:10]}. The suite must "
            "write only under NMAS_DATA_DIR. (Or another process wrote there "
            "during the run; the app is not meant to run on this machine.)\n")
        session.exitstatus = 1


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
    import logging
    import app  # noqa: F401

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
