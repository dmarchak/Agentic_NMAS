"""Snapshots of a data directory, for the store guards in conftest.py.

A module of its own, with no side effects, so a test can import the helpers.
Importing `tests.conftest` instead EXECUTES it a second time under another
name, and its top level points NMAS_DATA_DIR at a new temporary store:
measured 2026-09-26, it moved the environment mid-session.
"""

import os


def data_tree(path, lstat=os.lstat):
    """``{relpath: (size, mtime_ns)}`` for every file and directory under
    *path*: the evidence that nothing was written there.

    **Its premise, which the session guard meets and a careless test does
    not**: a directory's mtime moves on a write only if the write lands on a
    later clock tick than the directory's previous change. The deployment host
    stamps ext4 times from a 1 ms tick (kernel 6.8) and measured a directory
    mtime UNCHANGED after a create in 1,795 of 2,000 tries. The session guard
    compares the store's state from BEFORE the session with its state after,
    and no test can write in the same millisecond as a change made before
    pytest started, so it holds on any clock. A control that makes a directory
    and writes into it within microseconds does not, and passed in CI and
    failed on the host (2026-09-26). *lstat* is replaceable so a test can run
    under a coarser clock than the machine's.
    """
    tree = {}
    # The root's OWN entry too: a file created and removed at the top level
    # changes nothing below it, and changes the root's mtime. Found by a
    # negative control that passed (2026-09-26): without this, a test could
    # write into the live store and tidy up after itself unseen.
    try:
        st = lstat(path)
        tree["."] = (st.st_size, st.st_mtime_ns)
    except OSError:
        pass
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            full = os.path.join(root, name)
            try:
                st = lstat(full)
            except OSError:
                continue
            tree[os.path.relpath(full, path)] = (st.st_size, st.st_mtime_ns)
    return tree


def tree_changes(before, after):
    """Paths added, removed or modified between two `data_tree` snapshots."""
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
