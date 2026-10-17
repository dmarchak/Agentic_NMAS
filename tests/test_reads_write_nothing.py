"""Register C33: a GET must not write to the store. Ten did; none does since 2026-10-17, when
the last, today's template library listing (`/templates`, which seeded and committed the
library on a read), left at 7.8 (P7-23). The floor is a planted writer now.

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

#: route -> what it creates. The finding, not an allowance. Empty since 2026-10-17: its last
#: member, `/templates` (today's library listing, which seeded and committed the whole template
#: library on a read), left with today's template editor at 7.8 (P7-23); v2's Seed the
#: library… seeds as a previewed, confirmed write.
KNOWN_WRITERS = {
    # `/settings/integrations` and `/settings/integrations/general` ran migrate() on every GET,
    # writing user_settings.json when the stored schema version was behind; both left with
    # today's Settings modal at 7.8 (2026-10-15).
}

#: The planted writer the floor test makes of an argument-free GET: the route and its endpoint.
PLANTED = ("/health", "health.health")


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
    return _sweep(monkeypatch)


def _sweep(monkeypatch):
    """{route: [paths it changed]} over every argument-free GET."""
    import app as A
    from modules import config
    from modules.nsot import hooks

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
    client.get("/v2/")                  # initialize, as the first page load does
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
            # A GET that commits (`/templates` seeded, and since C931 its seed really committed,
            # until it left at 7.8) starts the post-commit hooks on a thread: their writes are
            # the route's, and a hook still writing raced the next route's reset ("Directory not
            # empty").
            assert hooks.wait_for_hooks() == [], f"{rule}'s post-commit hooks did not finish"
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


def test_the_sweep_can_see_a_writer(monkeypatch):
    """Floor: a sweep that saw nothing is indistinguishable from one that
    could not see. The last writer this harness measured, `/templates` (the template library,
    seeded), left at 7.8 (2026-10-17, P7-23); before it, `/settings/integrations`
    (user_settings.json, through migrate(), until today's Settings modal left at 7.8,
    2026-10-15), `/backup_stats` (until today's Backups left at 7.8, C632) and the approval
    queue (until its reads stopped writing: CONCURRENCY_AUDIT R4). With none left, the
    writer is PLANTED: an argument-free GET made to write one file in the store, which the
    sweep must charge to that route and to no other."""
    import app as A
    from modules import config

    rule, endpoint = PLANTED
    real = A.app.view_functions[endpoint]

    def planted(*a, **k):
        with open(os.path.join(config.DATA_DIR, "planted-by-the-floor-test"), "w",
                  encoding="utf-8") as fh:
            fh.write("x")
        return real(*a, **k)

    monkeypatch.setitem(A.app.view_functions, endpoint, planted)
    found = _sweep(monkeypatch)
    assert len(found["_swept"]) >= 60, len(found["_swept"])
    assert found.get(rule) == ["planted-by-the-floor-test"], found.get(rule)
    assert sorted(set(found) - {"_swept"}) == [rule], found


def test_no_new_get_writes(writers):
    new = sorted(set(writers) - {"_swept"} - set(KNOWN_WRITERS))
    assert new == [], {r: writers[r] for r in new}


def test_no_fixed_writer_stays_listed(writers):
    ghosts = sorted(set(KNOWN_WRITERS) - set(writers))
    assert ghosts == [], f"these no longer write: remove them from KNOWN_WRITERS: {ghosts}"
