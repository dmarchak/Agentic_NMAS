"""Register C33: a GET must not write to the store. Ten do.

Measured 2026-09-26, each route against the same INITIALIZED store (the state
after the first page load, which creates the default list), reset before every
route so each is charged only for its own writes. Against an uninitialized
store 45 routes "write", because every one of them materialises the default
list; that is one fact reported 45 times. The first page load (`/`) creating
the default list is that initialization, and is the baseline, not a writer. Pinned as a list that must not GROW (a new writer fails)
and must not keep GHOSTS (a fixed route fails until it is removed here), so
the fix of each is a decision and not a discovery.

Two READS that wrote are already fixed, found the same day when the suite
first ran on an empty store: `/deploy/plan` created `host_vars/` through
`hostvars.committed_dir()`, and the onboarding plan created `templates/`
through `templates_repo.templates_dir()`. Both helpers are pure now.
"""

import os
import shutil
import socket

import pytest

#: route -> what it creates. The finding, not an allowance.
KNOWN_WRITERS = {
    "/ai/approvals": "the approval queue file",
    "/ai/playbooks": "the playbooks directory",
    "/ai/topology_context": "the topology cache",
    "/backup_stats": "the backups directory",
    "/configure/audit_latest": "the pipeline audit directory",
    "/drift/status": "the approval queue file",
    "/golden/migrate/plan": "the list directory",
    "/templates": "the whole template library, seeded",
    # migrate() RUNS on every GET of this panel and WRITES when the stored
    # schema version is behind, which on a fresh install it always is.
    "/settings/integrations": "user_settings.json, through migrate()",
    "/settings/integrations/general": "user_settings.json, through migrate()",
}


def _tree(path):
    out = {}
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            full = os.path.join(root, name)
            st = os.lstat(full)
            out[os.path.relpath(full, path)] = (st.st_size, st.st_mtime_ns)
    return out


@pytest.fixture
def writers(monkeypatch):
    """{route: [paths it changed]} over every argument-free GET."""
    import app as A
    from modules import config

    def _no_network(*a, **k):
        raise OSError("tests do not touch a network")
    monkeypatch.setattr(socket.socket, "connect", _no_network)

    store = config.DATA_DIR
    client = A.app.test_client()
    original = os.path.join(os.path.dirname(store), os.path.basename(store) + ".orig")
    shutil.copytree(store, original)
    # An EMPTY store, then the first page load: independent of whatever the
    # tests before this one left (measured: an earlier test's directory hid
    # /configure/audit_latest's write in the full run).
    shutil.rmtree(store)
    os.makedirs(store)
    client.get("/")                     # initialize, as the first page load does
    saved = os.path.join(os.path.dirname(store), os.path.basename(store) + ".saved")
    shutil.copytree(store, saved)
    found = {}
    try:
        rules = sorted(r.rule for r in A.app.url_map.iter_rules()
                       if "GET" in (r.methods or ()) and r.endpoint != "static"
                       and not r.arguments)
        for rule in rules:
            shutil.rmtree(store)
            shutil.copytree(saved, store)
            before = _tree(store)
            client.get(rule)
            after = _tree(store)
            changed = sorted(k for k in set(before) | set(after)
                             if before.get(k) != after.get(k))
            if changed:
                found[rule] = changed
        found["_swept"] = rules
    finally:
        shutil.rmtree(store, ignore_errors=True)
        shutil.copytree(original, store)
        shutil.rmtree(saved, ignore_errors=True)
        shutil.rmtree(original, ignore_errors=True)
    return found


def test_the_sweep_can_see_a_writer(writers):
    """Floor: a sweep that saw nothing is indistinguishable from one that
    could not see. The approval queue is a writer this harness has measured."""
    assert len(writers["_swept"]) >= 60, len(writers["_swept"])
    assert "/ai/approvals" in writers


def test_no_new_get_writes(writers):
    new = sorted(set(writers) - {"_swept"} - set(KNOWN_WRITERS))
    assert new == [], {r: writers[r] for r in new}


def test_no_fixed_writer_stays_listed(writers):
    ghosts = sorted(set(KNOWN_WRITERS) - set(writers))
    assert ghosts == [], f"these no longer write: remove them from KNOWN_WRITERS: {ghosts}"
