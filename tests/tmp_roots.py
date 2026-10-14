"""pytest's temporary roots of runs that were killed are removed when the next run starts (C776).

pytest makes one root per run (`/tmp/pytest-of-<user>/pytest-<n>`) and removes its `.lock` in an
`atexit` handler, keeping a locked root for three days. A run ended by a signal (nmas-test's
bound, a stopped job, an ended session) never runs `atexit`, so its root stayed, every file
the run's tests had made in it: measured 2026-10-14, 429 of 433 roots locked, 842,278 files,
88% of the tmpfs `/tmp`'s inodes, and the gate's suite then failed hundreds of tests with
"could not create numbered dir" while the filesystem still had space.

At a run's start, a root whose lock names a process that no longer exists is removed: by the
owner the lock records, never by age or name alone. A root whose owner lives (another shard of
the gate, running at the same moment) and a root with no lock (pytest's own rule keeps the
last three) are left alone. Only `pytest-<n>` folders, under the parent of this run's root.
"""
import os
import re
import shutil

_ROOT = re.compile(r"^pytest-\d+$")


def owner_gone(root: str) -> bool:
    """True when *root*'s `.lock` names a process that does not exist. A missing or unreadable
    lock, or an owner this user may not signal, is never "gone"."""
    try:
        with open(os.path.join(root, ".lock"), encoding="utf-8") as fh:
            pid = int(fh.read().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def prune_dead_roots(parent: str, current: str = "") -> list:
    """Remove each `pytest-<n>` folder of *parent* (not *current*) whose lock's owner is gone;
    returns the names removed."""
    removed = []
    try:
        names = sorted(os.listdir(parent))
    except OSError:
        return removed
    keep = os.path.realpath(current) if current else ""
    for name in names:
        path = os.path.join(parent, name)
        if not _ROOT.match(name) or os.path.realpath(path) == keep or not owner_gone(path):
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            removed.append(name)
    return removed
