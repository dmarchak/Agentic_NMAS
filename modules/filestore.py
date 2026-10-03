"""A store the program READ-MODIFY-WRITES, written so that no failure erases it.

One implementation of the fix found three times in three files (C20 for the
settings file, C21 for the modification record, C157 for the credential
store), made reusable rather than re-implemented (C158, C160; the operator:
the second-implementation rule pointed at a safety property). Three properties
erased the settings file on 2026-09-23, and each is closed here:

- a READ-MODIFY-WRITE is serialised across PROCESSES (`PathLock`: an RLock plus
  an exclusive ``flock`` on ``<path>.lock``, outermost level only), because
  the host's CLIs write the same files as the app. Measured on the credential
  store: without it, two processes writing 60 entries each kept 63 to 76 of
  120 (37-47% lost, silently);
- every write goes through its OWN temp file (`write_atomic`: ``mkstemp`` in
  the same directory, 0600, fsync, ``os.replace``), never a shared ``.tmp``
  and never a truncate in place, so a reader sees the old file or the new one
  and never a fragment;
- a store that exists and cannot be read is NOT empty on a write path
  (`read_json_for_write` raises `StoreUnreadable` and preserves the file as
  ``.corrupt-<ts>``), because saving what an unreadable read returned is
  how every entry disappears.
"""

import json
import logging
import os
import tempfile
import threading
import time

log = logging.getLogger(__name__)


class StoreUnreadable(RuntimeError):
    """A store exists and could not be read, on a write path."""


class PathLock:
    """``with PathLock(path_or_callable):`` around a read-modify-write.

    *path* may be a callable, read at entry, so a module whose path is
    patched in tests (or re-pointed at a list) locks the file it will
    actually write.

    **Re-entrancy is per (thread, PATH), never per instance.** Callers build
    a lock where they need one (``devices_csv_lock(path)``), so a nested
    acquire is usually a different instance for the same file. Tracked per
    instance, the inner one took a second ``flock`` on a new descriptor, and
    ``flock`` is per open file description: the process blocked on its own
    lock (measured: the first run of C160's tests hung)."""

    _registry: dict = {}
    _registry_mu = threading.Lock()
    _held = threading.local()           # {path: [depth, rlock, fd]} per thread

    def __init__(self, path):
        self._path = path
        self._entered = threading.local()

    def path(self) -> str:
        return os.path.abspath(self._path() if callable(self._path) else self._path)

    @classmethod
    def _table(cls) -> dict:
        table = getattr(cls._held, "table", None)
        if table is None:
            table = cls._held.table = {}
        return table

    def depth(self) -> int:
        slot = self._table().get(self.path())
        return slot[0] if slot else 0

    def __enter__(self):
        path = self.path()
        table = self._table()
        slot = table.get(path)
        if slot:
            slot[1].acquire()
            slot[0] += 1
        else:
            with PathLock._registry_mu:
                rlock = PathLock._registry.setdefault(path, threading.RLock())
            rlock.acquire()
            fd = None
            try:
                import fcntl
                lock_path = path + ".lock"
                os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
                fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX)
            except ImportError:
                pass
            except Exception:
                if fd is not None:
                    os.close(fd)
                rlock.release()
                raise
            table[path] = [1, rlock, fd]
        stack = getattr(self._entered, "stack", None)
        if stack is None:
            stack = self._entered.stack = []
        stack.append(path)
        return self

    def __exit__(self, *exc):
        path = self._entered.stack.pop()
        table = self._table()
        slot = table[path]
        slot[0] -= 1
        rlock, fd = slot[1], slot[2]
        try:
            if slot[0] == 0:
                del table[path]
                if fd is not None:
                    import fcntl
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    finally:
                        os.close(fd)
        finally:
            rlock.release()
        return False


def write_atomic(path: str, text: str, *, newline: str = None, tmp_dir: str = None) -> None:
    """Replace *path* with *text*: a temp file per write, 0600, fsynced.

    *tmp_dir* puts the temp file elsewhere ON THE SAME FILESYSTEM (so the replace stays
    atomic): a store inside a git repository keeps its temp out of the repository, where a
    stager would see an untracked file (C345)."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".tmp-",
                               dir=tmp_dir or directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def preserve_corrupt(path: str, reason: str, aside: str = None) -> str:
    """Copy a damaged store aside, owner-only, before anything overwrites it.

    *aside* is the copy's name without its suffix, when it must not sit beside the store
    (a store inside a git repository: C345); by default it is the store's own path."""
    target = f"{aside or path}.corrupt-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    try:
        if not os.path.exists(target):
            from modules.config import open_secure
            with open(path, "rb") as src, open_secure(target, "wb") as dst:
                dst.write(src.read())
        log.error("store %s: %s; preserved as %s", os.path.basename(path), reason,
                  os.path.basename(target))
    except OSError as exc:
        log.error("store %s: %s; and it could not be preserved: %s",
                  os.path.basename(path), reason, exc)
        return ""
    return target


def read_json_for_write(path: str, empty=None, aside: str = None):
    """The store for a read-modify-write: *empty* when ABSENT; raises
    `StoreUnreadable` (and preserves the file, at *aside* when given) when it exists and
    cannot be read, which is not empty."""
    if not os.path.exists(path):
        return {} if empty is None else empty
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        reason = f"unreadable ({type(exc).__name__})"
        preserve_corrupt(path, reason, aside=aside)
        raise StoreUnreadable(
            f"{os.path.basename(path)} could not be read ({type(exc).__name__}), so "
            "nothing was written: saving would have replaced every entry in it. "
            "The damaged file is preserved beside it.") from exc
