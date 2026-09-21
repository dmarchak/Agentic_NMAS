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
