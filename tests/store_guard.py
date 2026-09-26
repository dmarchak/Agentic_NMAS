"""Snapshots of a data directory, for the store guards in conftest.py.

A module of its own, with no side effects, so a test can import the helpers.
Importing `tests.conftest` instead EXECUTES it a second time under another
name, and its top level points NMAS_DATA_DIR at a new temporary store:
measured 2026-09-26, it moved the environment mid-session.
"""

import os


def data_tree(path):
    """``{relpath: (size, mtime_ns)}`` for every file and directory under
    *path*: the evidence that nothing was written there."""
    tree = {}
    # The root's OWN entry too: a file created and removed at the top level
    # changes nothing below it, and changes the root's mtime. Found by a
    # negative control that passed (2026-09-26): without this, a test could
    # write into the live store and tidy up after itself unseen.
    try:
        st = os.lstat(path)
        tree["."] = (st.st_size, st.st_mtime_ns)
    except OSError:
        pass
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            full = os.path.join(root, name)
            try:
                st = os.lstat(full)
            except OSError:
                continue
            tree[os.path.relpath(full, path)] = (st.st_size, st.st_mtime_ns)
    return tree


def tree_changes(before, after):
    """Paths added, removed or modified between two `data_tree` snapshots."""
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
