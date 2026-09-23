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
        found = set()
        for root, _dirs, files in os.walk(LISTS_DIR):
            # `.git` inside a config_repo churns on any read (gc, logs), and
            # is not what a test polluting live data would leave behind.
            if os.sep + ".git" in root:
                continue
            for name in files:
                found.add(os.path.join(root, name))
        return found

    before = _snapshot()
    yield
    created = sorted(_snapshot() - before)
    assert not created, (
        f"this test created {created[:5]} in the real data directory "
        f"({LISTS_DIR}). Patch `modules.config.get_list_data_dir` BEFORE "
        f"anything that resolves a path through it — `save_golden()` does.")
