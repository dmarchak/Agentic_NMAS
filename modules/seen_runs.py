"""What each verified person has seen under the In progress list's "Finished, not opened yet"
(the operator, 2026-11-12: "Opening a result must mark it seen PERSISTENTLY (per person,
stored), so it leaves the list and the chip; add a "Dismiss" on each entry too"; C3081).

Before this, "opened" was kept in memory only (`heal.run_card._opened`, each job's ``opened``
set in `capture_job`), so every restart (three deploys on 2026-11-12) listed again every run
of the last day a person had opened, on every page.

One small store, `data/seen_runs.json`: ``{"entries": [{"viewer", "id", "how", "at"}, ...]}``,
oldest first. *id* is the id the entry is keyed by today: a re-subscribe's record id (``run``)
and the id of the job that ran it, a heal's (or any device card's) job id. *how* is
``opened`` (the person pressed Open the result) or ``dismissed`` (Dismiss). Written only by a
person's own press (`routes/v2.seen_run`, a declared mutating route), under its lock across
processes, replaced atomically, owner-only from creation (`filestore.write_atomic`'s temp file
is 0600). A read writes nothing.

**Per person:** an entry one person has seen is still listed for every other person until they
open or dismiss it.

**Bounded:** the newest `KEEP` entries are kept. 2,000 is a guess, nothing measured: an entry
is listed for at most a day (`heal.run_card.FINISHED_KEEP_S`; a job's for `capture_job.KEEP_S`),
so only the marks of the last day can hide anything, and 2,000 is many times the runs a day of
this lab finishes.

**An unreadable store** (it exists and cannot be parsed) refuses every write, naming the file
and why, and every read answers "not seen", saying so (`state`): every finished run is listed,
never hidden by a guess.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

FILENAME = "seen_runs.json"
#: The newest marks kept. A guess, nothing measured: see the module's note.
KEEP = 2000
#: How a person marked an entry seen.
HOW = ("opened", "dismissed")

#: The parsed store, keyed by the file's identity (inode, size, modification time), so the
#: chip on every page does not parse it again until it changes. A cache of the file, never a
#: second owner: a write replaces the file, and a new identity reads it again.
_cache = {"key": None, "entries": ()}


class Unreadable(RuntimeError):
    """The store exists and cannot be read; nothing is written over it."""


def _path() -> str:
    from modules.config import DATA_DIR

    return os.path.join(DATA_DIR, FILENAME)


def _parse(p: str) -> list:
    try:
        with open(p, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Unreadable(f"{p} cannot be read: {exc}") from None
    entries = got.get("entries") if isinstance(got, dict) else None
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise Unreadable(f"{p} holds no list of entries (it holds {type(got).__name__})")
    return entries


def _entries() -> list:
    """The store's entries, oldest first; [] when there is no store yet. Raises
    `Unreadable`."""
    p = _path()
    try:
        st = os.stat(p)
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise Unreadable(f"{p} cannot be read: {exc}") from None
    key = (p, st.st_ino, st.st_size, st.st_mtime_ns)
    if _cache["key"] != key:
        entries = _parse(p)
        _cache.update(key=key, entries=tuple(entries))
    return list(_cache["entries"])


def read() -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "why", "entries"}``. A READ."""
    p = _path()
    if not os.path.exists(p):
        return {"state": "absent", "why": "", "entries": []}
    try:
        return {"state": "ok", "why": "", "entries": _entries()}
    except Unreadable as exc:
        return {"state": "unreadable", "why": str(exc), "entries": []}


def seen_by(viewer: str) -> dict:
    """``{"state", "why", "ids"}``: the ids *viewer* has opened or dismissed. With no viewer,
    or an unreadable store, no id (everything is listed; *state* says which)."""
    got = read()
    ids = frozenset(str(e.get("id")) for e in got["entries"]
                    if viewer and e.get("viewer") == viewer and e.get("id"))
    return {"state": got["state"], "why": got["why"], "ids": ids}


def is_seen(viewer: str, *ids) -> bool:
    """Whether *viewer* has opened or dismissed any of *ids* (an entry's job id and its run's
    id name one run). False with no viewer, no id, or an unreadable store."""
    wanted = {str(i) for i in ids if i}
    if not viewer or not wanted:
        return False
    return bool(wanted & seen_by(viewer)["ids"])


def mark(viewer: str, ids, how: str, now: float = None) -> dict:
    """Record that *viewer* has seen the run named by *ids* (*how*: `HOW`):
    ``{"ok", "error", "news"}``. Refused, writing nothing, with no verified viewer, no id, a
    *how* not declared, or a store that cannot be read. *news* is False when every id was
    already marked for *viewer*."""
    from modules.filestore import PathLock, write_atomic

    ids = [str(i) for i in dict.fromkeys(ids or ()) if i]
    if not viewer:
        return {"ok": False, "news": False,
                "error": "nobody verified is looking, so there is no one to remember it for"}
    if how not in HOW:
        return {"ok": False, "news": False,
                "error": f"{how!r} is not a way of marking it seen ({', '.join(HOW)})"}
    if not ids:
        return {"ok": False, "news": False, "error": "no run was named"}
    now = time.time() if now is None else now
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    try:
        with PathLock(_path):
            entries = _entries()
            had = {str(e.get("id")) for e in entries if e.get("viewer") == viewer}
            new = [{"viewer": viewer, "id": i, "how": how, "at": at} for i in ids
                   if i not in had]
            if not new:
                return {"ok": True, "news": False, "error": ""}
            entries = (entries + new)[-KEEP:]
            write_atomic(_path(), json.dumps({"entries": entries}, indent=0) + "\n")
            os.chmod(_path(), 0o600)
    except Unreadable as exc:
        log.warning("seen_runs: %s; nothing was written", exc)
        return {"ok": False, "news": False, "error": f"{exc}; nothing was written"}
    return {"ok": True, "news": True, "error": ""}
