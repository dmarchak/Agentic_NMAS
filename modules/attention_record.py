"""NEEDS ATTENTION'S RECORD: each row's life, from its first sighting to how it cleared (C1192;
the operator, 2026-10-18: "the record only: rows built when each reader finishes, a store safe
across workers, tests including the appear-and-clear case").

The page computes its rows when it is read, so a row that appeared and cleared between two
reads of the page was never seen by anyone, and nothing kept it (five such items across the
walks W2 to W4). This module SIGHTS the rows whenever a reader whose value Needs attention draws
finishes (`reader_job`, after its store; the readers whose `invalidates` meet
`attention.ATTENTION_KEYS`, the one list the page itself redraws on). A page read never writes
here: a read writes nothing.

Each sighting is `needs_attention()` itself, the page's own rows, so the record holds exactly
what the page would have shown at that moment. Per row id, a LIFE:

- **first seen**, **last seen** and how many sightings;
- **cleared at** and **how**: ``acknowledged`` (a person's acknowledgement hid it: who and
  why), ``time`` (it was due to clear by time, and that time passed), or ``resolved`` (its
  source was read and the row is gone);
- a row whose source could not be read this time is NOT cleared: its life stays open (an
  unreadable source is not a resolved one);
- a row that comes back after it cleared starts a new life.

A row folded into another (attached) is still present: it is sighted by its own id. A row
first seen in the sighting after the one that would have caught it is first seen THEN: the
record is as fine as the readers' rhythm, never finer, and says so in `observed`.

**Across processes:** one JSON store under the data folder, read-modify-written under a
`filestore.PathLock` (an exclusive `flock`) and replaced atomically. In one process, sightings
coalesce: a reader finishing while a sighting runs asks for one more, never a queue.

**Kept:** open lives, and cleared lives for `KEPT_DAYS` days, at most `KEPT_MAX` (the oldest
dropped first, counted in `dropped`). What a row says is masked at rest (`redact.redact_text`).

The screen that reads this record is C1319 (Stage 7's tail); `read()` is its reader.
"""

import json
import logging
import os
import threading
import time

from modules import filestore

log = logging.getLogger(__name__)

FILE = "attention_record.json"
KEPT_DAYS = 30
KEPT_MAX = 5000
HOWS = ("resolved", "acknowledged", "time")

_coalesce = threading.Lock()
_pending = threading.Event()
_installed = {"on": False}


def path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, FILE)


def _iso(ts) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


def _epoch(iso: str):
    try:
        import calendar
        return calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def _masked(text) -> str:
    from modules.redact import redact_text
    return redact_text(str(text or ""))


def _empty() -> dict:
    return {"version": 1, "open": {}, "cleared": [], "observed": {"count": 0, "last": "",
                                                                   "first": ""},
            "dropped": 0}


def read() -> dict:
    """``{"state": "absent" | "read" | "unreadable", "doc": ..., "error": ...}``: the record
    as stored, for a page. Absent is no sighting yet, never an error."""
    p = path()
    if not os.path.exists(p):
        return {"state": "absent", "doc": _empty(), "error": ""}
    try:
        with open(p, encoding="utf-8") as fh:
            return {"state": "read", "doc": json.load(fh), "error": ""}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "doc": None, "error": f"{type(exc).__name__}: {exc}"}


def _present(result: dict) -> dict:
    """``{row id: row}`` of every row the page holds: its rows and each row folded into one.
    A folded row carries its own id (`attention._attach`)."""
    out = {}
    for r in result.get("rows") or []:
        out[r["id"]] = r
        for a in r.get("attached") or []:
            if a.get("id"):
                out.setdefault(a["id"], dict(a, level=r.get("level"), kind=a.get("kind", ""),
                                             devices=a.get("devices") or [],
                                             clears_at=None))
    return out


def _unread_sources(result: dict) -> set:
    return {s["source"] for s in result.get("sources") or [] if s.get("state") != "read"}


def _life(rid: str, r: dict, now: float) -> dict:
    return {"id": rid, "source": r.get("source", rid.split(":", 1)[0]),
            "kind": r.get("kind", ""), "level": r.get("level", ""),
            "what": _masked(r.get("what")), "devices": list(r.get("devices") or []),
            "first_seen": _iso(now), "last_seen": _iso(now), "seen": 0,
            "clears_at": r.get("clears_at") or "", "cleared_at": "", "how": ""}


def apply(doc: dict, result: dict, now: float) -> dict:
    """*doc* with one sighting of *result* (`attention.needs_attention()`'s answer) taken at
    *now*: lives opened, carried and cleared. Pure: the caller stores it. Returns
    ``{"doc", "opened", "cleared"}``."""
    present = _present(result)
    unread = _unread_sources(result)
    acknowledged = {a["id"]: a for a in result.get("acknowledged") or [] if a.get("id")}
    open_ = dict(doc.get("open") or {})
    cleared = list(doc.get("cleared") or [])
    opened, closed = [], []
    for rid, r in present.items():
        life = open_.get(rid) or _life(rid, r, now)
        if rid not in open_:
            opened.append(rid)
        life.update(last_seen=_iso(now), seen=int(life.get("seen", 0)) + 1,
                     level=r.get("level") or life.get("level", ""),
                     what=_masked(r.get("what")) or life.get("what", ""),
                     devices=list(r.get("devices") or life.get("devices") or []),
                     clears_at=r.get("clears_at") or life.get("clears_at", ""))
        open_[rid] = life
    for rid in [k for k in open_ if k not in present]:
        life = dict(open_[rid])
        if rid in acknowledged:
            a = acknowledged[rid]
            life.update(how="acknowledged", by=a.get("by") or "", why=_masked(a.get("why")))
        elif life["source"] in unread:
            continue                     # its source was not read: not cleared, not known
        else:
            due = _epoch(life.get("clears_at") or "")
            life["how"] = "time" if due is not None and now >= due else "resolved"
        life["cleared_at"] = _iso(now)
        cleared.append(life)
        closed.append(rid)
        del open_[rid]
    cutoff = now - KEPT_DAYS * 86400
    kept = [c for c in cleared if (_epoch(c.get("cleared_at")) or now) >= cutoff]
    dropped = int(doc.get("dropped", 0)) + len(cleared) - len(kept)
    if len(kept) > KEPT_MAX:
        dropped += len(kept) - KEPT_MAX
        kept = kept[-KEPT_MAX:]
    observed = dict(doc.get("observed") or {})
    observed.update(count=int(observed.get("count", 0)) + 1, last=_iso(now),
                    first=observed.get("first") or _iso(now))
    return {"doc": {"version": 1, "open": open_, "cleared": kept, "observed": observed,
                    "dropped": dropped},
            "opened": opened, "cleared": closed}


def observe(result: dict = None, now: float = None) -> dict:
    """One sighting, stored: *result* is the page's answer (computed here when None), *now*
    the sighting's time. Locked across processes; the store replaced atomically. An unreadable
    store is preserved aside and refused, never overwritten."""
    if result is None:
        from modules import attention
        result = attention.needs_attention()
    now = time.time() if now is None else float(now)
    p = path()
    with filestore.PathLock(p):
        try:
            doc = filestore.read_json_for_write(p, empty=_empty())
        except filestore.StoreUnreadable as exc:
            log.error("attention record: %s", exc)
            return {"ok": False, "error": str(exc), "opened": [], "cleared": []}
        got = apply(doc, result, now)
        filestore.write_atomic(p, json.dumps(got["doc"], indent=1, sort_keys=True))
    return {"ok": True, "error": "", "opened": got["opened"], "cleared": got["cleared"]}


def sight(trigger: str = "") -> None:
    """A reader whose value the page draws finished: take a sighting. In one process,
    sightings coalesce: one running, at most one more asked for. A failure is logged and never
    stops the reader."""
    _pending.set()
    if not _coalesce.acquire(blocking=False):
        return                           # the running sighting takes one more
    try:
        while _pending.is_set():
            _pending.clear()
            try:
                observe()
            except Exception as exc:                    # noqa: BLE001
                log.error("attention record: a sighting after %s failed: %s: %s",
                          trigger or "a reader", type(exc).__name__, exc)
    finally:
        _coalesce.release()


def draws(reader) -> bool:
    """Does Needs attention draw *reader*'s value? Its announcement redraws the page: one of
    its `invalidates` keys is in `attention.ATTENTION_KEYS`."""
    from modules.attention import ATTENTION_KEYS
    return bool(set(getattr(reader, "invalidates", ()) or ()) & set(ATTENTION_KEYS))


def install() -> None:
    """Sight after every reader the page draws (`reader_job.after_any_store`). Installed where
    the readers start (`reader_job.start`), so a process that runs no readers sights nothing."""
    from modules import reader_job
    if not _installed["on"]:
        reader_job.after_any_store(_after_store)
        _installed["on"] = True


def uninstall() -> None:
    from modules import reader_job
    reader_job.after_any_store(_after_store, remove=True)
    _installed["on"] = False


def _after_store(reader, moved: bool = True) -> None:
    """A reader the page draws finished. One that announces only on change (the 5 s
    reachability probe, the 10 s onboarding progress) is sighted only when its value moved:
    measured on the host, 2026-10-19, a sighting takes about 0.17 s warm and the drawn
    readers finish about 25 times a minute, most of them those two."""
    if draws(reader) and moved:
        sight(reader.name)
