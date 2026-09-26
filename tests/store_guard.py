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


# ---------------------------------------------------------------------------
# Attribution: WHO wrote into the checkout's data/ (2026-09-26)
# ---------------------------------------------------------------------------
# On the deployment host the app runs from the same checkout the suite runs
# in, and writes its own data/ while the suite runs. The snapshot guard saw
# the app's approval queue change and reported it as the suite's write, with a
# parenthetical asserting the app does not run there. It does. So the guard
# judges attribution, not only change:
#   - the test process's own writes are SEEN, by an audit hook, and fail the
#     test that made them, by name;
#   - a change no test made is checked against a MEASURED fact, whether an
#     app process is running from this checkout, rather than an assumption.

import sys

#: Audit events that write: ``(path argument, its dir_fd argument or None)``.
#: A path given WITH a dir_fd is relative to that directory, not to the cwd:
#: `shutil.rmtree` removes entries as `os.rmdir(name, dir_fd=...)`, and
#: resolving "data" against the cwd (the checkout root) reported a temp
#: directory's own `data` subdirectory as the checkout's data/ (2026-09-26).
_WRITE_EVENTS = {
    "os.mkdir": ((0, 2),), "os.rmdir": ((0, 1),), "os.remove": ((0, 1),),
    "os.rename": ((0, 2), (1, 3)), "os.symlink": ((1, 2),), "os.link": ((1, 3),),
    "os.chmod": ((0, 2),), "os.chown": ((0, 3),), "os.utime": ((0, 3),),
    "os.truncate": ((0, None),), "shutil.rmtree": ((0, 1),), "shutil.move": ((0, None), (1, None)),
    "shutil.copytree": ((1, None),), "shutil.copyfile": ((1, None),),
}


def resolve(path, dir_fd=None):
    """The absolute path an audited call acts on, or None when it cannot be
    known (a dir_fd this process cannot read back). Unknown is not attributed:
    a guard that guesses reports a write nobody made."""
    import os
    if isinstance(path, int):
        return None                     # an fd, not a path
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    if not isinstance(path, (str, os.PathLike)):
        return None
    path = os.fspath(path)
    if isinstance(dir_fd, int) and dir_fd >= 0 and not os.path.isabs(path):
        try:
            base = os.readlink(f"/proc/self/fd/{dir_fd}")
        except OSError:
            return None
        path = os.path.join(base, path)
    return os.path.realpath(path)
_OPEN_WRITE_FLAGS = None


def _is_write_open(mode, flags):
    import os
    global _OPEN_WRITE_FLAGS
    if _OPEN_WRITE_FLAGS is None:
        _OPEN_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    if isinstance(mode, str) and any(c in mode for c in "wax+"):
        return True
    return isinstance(flags, int) and flags != -1 and bool(flags & _OPEN_WRITE_FLAGS)


class WriteWatch:
    """Records every write the test process makes under *root*."""

    def __init__(self, root):
        import os
        self.root = os.path.realpath(root)
        self.current = ""
        self.writes = []            # (test, event, path)

    def _inside(self, path, dir_fd=None):
        import os
        full = resolve(path, dir_fd)
        if full is None:
            return None
        return full if full == self.root or full.startswith(self.root + os.sep) else None

    def hook(self, event, args):
        try:
            if event == "open":
                path, mode, flags = (list(args) + [None, None, None])[:3]
                if _is_write_open(mode, flags):
                    hit = self._inside(path)
                    if hit:
                        self.writes.append((self.current, "open", hit))
            elif event in _WRITE_EVENTS:
                for i, fd_i in _WRITE_EVENTS[event]:
                    if i < len(args):
                        fd = args[fd_i] if fd_i is not None and fd_i < len(args) else None
                        hit = self._inside(args[i], fd)
                        if hit:
                            self.writes.append((self.current, event, hit))
        except Exception:           # an audit hook must never break the call it watches
            pass


def install_write_watch(root):
    watch = WriteWatch(root)
    sys.addaudithook(watch.hook)
    return watch


def processes_running_from(checkout, proc="/proc"):
    """``[(pid, argv)]``: processes whose argv names this checkout's app.py,
    resolved against their own working directory. MEASURED from /proc; an
    unreadable process is skipped, and a machine with no /proc answers []."""
    import os
    app = os.path.realpath(os.path.join(checkout, "app.py"))
    found = []
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return found
    for pid in pids:
        if int(pid) == os.getpid():
            continue
        try:
            with open(os.path.join(proc, pid, "cmdline"), "rb") as fh:
                argv = [a.decode(errors="replace") for a in fh.read().split(b"\0") if a]
            cwd = os.readlink(os.path.join(proc, pid, "cwd"))
        except OSError:
            continue
        for arg in argv[1:3]:
            if os.path.realpath(os.path.join(cwd, arg)) == app:
                found.append((int(pid), " ".join(argv)))
                break
    return found


def judge(changed, writes, checkout_data, find_apps):
    """``(fail, message)`` for the session guard.

    *changed*: paths under the checkout's data/ that differ from the start of
    the session. *writes*: ``(test, event, path)`` the audit hook saw the test
    process make there. *find_apps*: called only when needed, returns
    ``[(pid, argv)]`` of app processes running from this checkout.

    A write a test made fails the run, naming the tests. A change no test
    made is the app's when an app is running from this checkout (a note,
    because the suite reads only its own store); otherwise it is unexplained
    and fails the run.
    """
    import os
    by_tests = set()
    for _t, _e, path in writes:
        rel = os.path.relpath(path, checkout_data)
        while rel and rel not in (".", os.curdir):
            by_tests.add(rel)
            rel = os.path.dirname(rel)
    if writes:
        by_tests.add(".")
    unexplained = [p for p in changed if p not in by_tests]
    fail, lines = False, []
    if writes:
        tests = sorted({t for t, _e, _p in writes})
        lines.append(f"TESTS WROTE INTO THE CHECKOUT'S data/ ({checkout_data}): "
                     f"{len(writes)} write(s) by {tests[:5]}.")
        fail = True
    if unexplained:
        apps = find_apps()
        if apps:
            pid, argv = apps[0]
            lines.append(
                f"note: the checkout's data/ changed in {len(unexplained)} path(s) that no test "
                f"wrote, first {unexplained[:5]}. The app is running from this checkout "
                f"(pid {pid}: {argv}), so these are its writes. The suite reads only its own "
                "store (NMAS_DATA_DIR), so they did not reach any test.")
        else:
            lines.append(
                f"THE CHECKOUT'S data/ CHANGED ({checkout_data}): {len(unexplained)} path(s), "
                f"first {unexplained[:10]}, that no test in this process wrote, and no app "
                "process is running from this checkout. Something unexplained wrote there: a "
                "process a test started, or another process on this machine.")
            fail = True
    return fail, "\n".join(lines)
