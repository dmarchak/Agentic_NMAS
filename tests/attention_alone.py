"""A Needs attention page computed from a test's planted sources alone.

`attention.needs_attention` adds a row for every incident that needs a person in the page's
network (`attention._incidents_agree`, from `incidents_list.rows`), read from the session's data
directory, which every test in one worker shares. A test before it that left such an incident
made a planted-sources test fail by the order it ran in (the full suite of 2026-11-23: a heal
incident on edge-b drawn first in test_installation_kind, test_host_step_decline and
test_recheck). A test that asserts the page from its own sources, and plants no incident, uses
`no_stored_incidents`.
"""

import pytest


@pytest.fixture
def no_stored_incidents(monkeypatch):
    """The incidents' store reads as holding none, for this test only."""
    from modules import incidents_list
    monkeypatch.setattr(incidents_list, "rows",
                        lambda network: {"rows": [], "folded": 0, "unreadable": []})
