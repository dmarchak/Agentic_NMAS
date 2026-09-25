"""Shared test setup.

`redact.known_secret_values()` caches for 30 seconds so a burst of log records
does not decrypt the credential store once per line. In a test suite that TTL
is cross-contamination: a test that monkeypatches the store inherits whatever
the previous test built, and the failure looks like a redaction bug rather than
a fixture one.

Cleared before and after every test — cheap, and it makes each test's view of
the store its own.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _import_the_application_first():
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
    """
    import app  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_redaction_cache():
    from modules import redact

    redact.invalidate_cache()
    redact.reset_health()
    yield
    redact.invalidate_cache()
    redact.reset_health()


@pytest.fixture(autouse=True)
def _no_test_writes_into_live_data():
    """No test may create a device list in the real ``data/`` directory.

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

    assert not created, (
        f"this test created {created[:5]} in the real data directory "
        f"({LISTS_DIR}). Patch `modules.config.get_list_data_dir` BEFORE "
        f"anything that resolves a path through it — `get_list_data_dir()` "
        f"calls os.makedirs(), so merely resolving a path is enough.")
