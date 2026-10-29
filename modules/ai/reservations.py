"""The caps' reservations: each AI call's worst case held against the caps while it is in
flight (C2039; the operator's decision of 2026-10-28).

Without them the gateway read today's spend, compared it plus the call's worst case with each
cap and sent, with no lock: calls made at once each passed against the same spend and together
could pass a cap. Now, before a call is sent:

1. **one cross-process lock** (`filestore.PathLock` on the store: an RLock and an exclusive
   ``flock``, so threads AND worker processes take turns) is held around
2. reading the open reservations, and the spend the gateway's *judge* reads inside it (the
   record of AI calls), and judging every cap the call is held to against the spend PLUS what
   is reserved in flight PLUS this call's worst case, and
3. writing this call's reservation, when every cap allows it.

**Settled** (`settle`: removed) when the call's row, with its actual cost, is in the record,
whatever the outcome (the gateway's ``finally``). The row is written first and the reservation
removed after, so a judge in between counts the call twice (its cost and its reservation),
never not at all.

**A reservation left by a process that died** is not held for ever: each carries when it
expires (``expires_at``, from the gateway's `gateway.reservation_ttl_s`, derived from the
adapter's own bound on one call), and an expired one is dropped at the next reserve, logged.

**A call whose row the record refused** (C2047, 2026-10-29) is never left to expire: it was
sent and may be billed, and once its reservation expired the spend the caps read held nothing
for it. The gateway keeps its reservation as **unrecorded** (`hold_unrecorded`): it never
expires, it holds the cost the row would have counted (the call's actual cost, or its worst
case where that is unknown), and it keeps a late row for each call it stands for, the row's
names and numbers only (`late_row`: no request, answer or detail). Every reserve, under the
lock and before the caps are judged, asks the record to take each late row again; a row it
takes is the record's to count from then, and the reservation goes once all of its rows have
gone. Until then the caps count it as in flight (the cap never reads low), and Needs attention
names it (`attention`'s ``ai_spend`` ``unrecorded``). A late row keeps the call's own time, so
the record counts it on its own day; while unrecorded it counts against every day's cap, high,
never low.

**The store** is a small JSON file beside the record of AI calls (``ai_reservations.json``,
owner-only from creation: `filestore.write_atomic`'s ``mkstemp`` is 0600, replaced atomically).
It holds no request, answer or key: ``{"held": {call_id: {"usd", "feature", "network",
"background", "day", "month", "at", "expires_at", "pid"}}}``, and an unrecorded one's
``"unrecorded": true`` and ``"rows"`` (its late rows).

**An unreadable store refuses the call** (fail closed, said): it is never read as nothing
reserved. It stays refused until its last write is older than the longest a reservation
lives, when nothing it could hold is still in flight; it is then preserved aside
(``.corrupt-<ts>``) and replaced by an empty store, logged. No person has to clear it.
"""
import json
import logging
import os
import time

log = logging.getLogger(__name__)

#: The store's file name, beside the record of AI calls.
NAME = "ai_reservations.json"


def _path() -> str:
    from modules.ai import calls
    return os.path.join(os.path.dirname(os.path.abspath(calls._path())), NAME)


class Unreadable(RuntimeError):
    """The store exists and cannot be read."""


def _read(path: str, now: float, ttl_s: float) -> dict:
    """``{call_id: reservation}`` as stored; {} when absent. Raises `Unreadable` for a store
    that cannot be read, unless its last write is older than *ttl_s* (nothing it holds can
    still be in flight), when it is preserved aside and read as empty, logged."""
    from modules import filestore

    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        held = got.get("held") if isinstance(got, dict) else None
        if not isinstance(held, dict) or not all(
                isinstance(v, dict) and _num(v.get("usd")) is not None
                and _num(v.get("expires_at")) is not None for v in held.values()):
            raise ValueError("not a reservations store")
        return held
    except (OSError, ValueError) as exc:
        reason = f"unreadable ({type(exc).__name__}: {exc})"
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            age = 0.0
        if age > ttl_s:
            # Kept aside before anything replaces it; until then it stays where it is.
            filestore.preserve_corrupt(path, reason)
            log.error("ai reservations: %s, last written %.0f s ago, over the %.0f s a "
                      "reservation lives: nothing it held is in flight; it is replaced",
                      os.path.basename(path), age, ttl_s)
            return {}
        raise Unreadable(f"the AI caps' reservations ({os.path.basename(path)}) cannot be "
                         f"read ({type(exc).__name__}), so what is in flight is unknown; it "
                         f"was last written {age:.0f} s ago and is refused until "
                         f"{ttl_s:.0f} s have passed, when nothing it held can still be in "
                         "flight") from exc


def _num(v):
    ok = isinstance(v, (int, float)) and not isinstance(v, bool)
    return float(v) if ok else None


def _write(path: str, held: dict) -> None:
    from modules import filestore
    filestore.write_atomic(path, json.dumps({"held": held}, sort_keys=True))


def _live(held: dict, t: float) -> dict:
    """*held* without its expired reservations; an unrecorded one never expires (C2047)."""
    return {k: v for k, v in held.items()
            if v.get("unrecorded") or float(v["expires_at"]) > t}


#: What a late row keeps of the call's row (C2047): its names and numbers, never the request,
#: the answer, the output or the detail's words.
LATE_ROW_KEYS = ("id", "feature", "actor", "trigger", "model", "prompt", "schema",
                 "prompt_sha256", "subject", "batch")


def late_row(row: dict, *, verdict: str, cost_usd: float) -> dict:
    """The row the record is asked to take again for a call whose row it refused (C2047): the
    call's names and numbers (`LATE_ROW_KEYS`), its *verdict* and the *cost_usd* it counts,
    said to be late. Its time is the reservation's (`hold_unrecorded`)."""
    kept = {k: row[k] for k in LATE_ROW_KEYS if k in row}
    return dict(kept, verdict=verdict, cost_usd=float(cost_usd), recorded_late=True,
                detail=("recorded late (C2047): the record of AI calls refused this call's "
                        "row when it was made; its request, answer and tokens were not kept, "
                        f"and its cost ${float(cost_usd):.4f} was held against the caps "
                        "until this row was taken"))


def _record_late(entry: dict):
    """Ask the record to take each late row of an unrecorded *entry* again: None when every row
    was taken (the record counts them now), else the entry holding the rows still refused and
    their cost."""
    from modules.ai import calls

    left = [r for r in entry.get("rows") or [] if not calls.record(r).get("recorded")]
    if not left:
        return None
    if len(left) == len(entry.get("rows") or []):
        return entry
    return dict(entry, rows=left, usd=sum(float(r.get("cost_usd") or 0.0) for r in left))


def in_flight(held: dict, *, feature: str = None, network: str = None) -> dict:
    """``{"usd", "calls"}``: what *held* reserves, all of it, or a background feature's on a
    network (*feature* and *network* given: only background reservations of both)."""
    rows = [h for h in held.values()
            if feature is None or (h.get("background") and h.get("feature") == feature
                                   and h.get("network") == network)]
    return {"usd": sum(float(h["usd"]) for h in rows), "calls": len(rows)}


def reserve(call_id: str, usd: float, *, judge, ttl_s: float, feature: str = "",
            network: str = "", background: bool = False, day: str = "",
            now=None) -> dict:
    """Hold *usd* (the call's worst case) for *call_id* when *judge* allows it.

    Under the store's cross-process lock: the open reservations read (an expired one dropped),
    ``judge(held)`` asked (it reads the spend inside the lock and answers None to allow, or the
    gateway's refusal ``{"kind", "why", ...}``), and this call's reservation written, expiring
    *ttl_s* after now. ``{"ok": True}``, or ``{"ok": False, "refusal": {...}}``; an unreadable
    store is a refusal (``over_cap``, said), never read as nothing reserved."""
    from modules import filestore

    path = _path()
    try:
        with filestore.PathLock(path):
            t = time.time() if now is None else now
            try:
                held = _read(path, t, ttl_s)
            except Unreadable as exc:
                return {"ok": False, "refusal": {"kind": "over_cap",
                                                 "why": f"{exc}; nothing was sent"}}
            live = _live(held, t)
            changed = len(live) != len(held)
            for k in sorted(set(held) - set(live)):
                log.warning("ai reservations: %s's reservation of $%.4f expired unsettled "
                            "(made at %s; its process died): dropped",
                            k, float(held[k]["usd"]), held[k].get("at"))
            # An unrecorded call's late rows asked of the record again (C2047), before the
            # caps read it: a row taken is the record's to count from now.
            for k in sorted(k for k, v in live.items() if v.get("unrecorded")):
                now_entry = _record_late(live[k])
                if now_entry is live[k]:
                    continue
                changed = True
                if now_entry is None:
                    live.pop(k)
                    log.warning("ai reservations: %s's late row(s) are recorded; its "
                                "reservation is settled", k)
                else:
                    live[k] = now_entry
            said = judge(live)
            if said:
                if changed:
                    _write(path, live)
                return {"ok": False, "refusal": said}
            live[call_id] = {"usd": float(usd), "feature": feature, "network": network,
                             "background": bool(background), "day": day, "month": day[:7],
                             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)),
                             "expires_at": t + ttl_s, "pid": os.getpid()}
            _write(path, live)
            return {"ok": True}
    except OSError as exc:
        return {"ok": False, "refusal": {"kind": "over_cap", "why": (
            f"the AI caps' reservations ({NAME}) could not be written "
            f"({type(exc).__name__}: {exc}), so this call could not be held against the caps; "
            "nothing was sent")}}


def settle(call_id: str, ttl_s: float, now=None) -> bool:
    """Remove *call_id*'s reservation (its row, with its actual cost, is in the record). True
    when it was removed or was not there; False, logged, when the store could not be read or
    written (the reservation then lives to its expiry). Never raises."""
    from modules import filestore

    path = _path()
    try:
        with filestore.PathLock(path):
            t = time.time() if now is None else now
            held = _read(path, t, ttl_s)
            if call_id in held:
                held.pop(call_id)
                _write(path, held)
        return True
    except (Unreadable, OSError) as exc:
        log.error("ai reservations: %s's reservation could not be settled (%s); it is held "
                  "until it expires", call_id, exc)
        return False


def hold_unrecorded(call_id: str, rows: list, ttl_s: float, now=None) -> bool:
    """Keep *call_id*'s reservation as unrecorded (C2047): the record refused the row of each
    call it stands for (*rows*, `late_row`s), so it never expires, holds their cost, and keeps
    them to be asked of the record again at every reserve. Each row's time is the
    reservation's (the call's), so the record counts it on its own day once taken. True when
    kept; False when the store could not be read or written, said at CRITICAL (the reservation
    as it was then counts the call until it expires, and the next reserve, which must write the
    store, refuses while it cannot)."""
    from modules import filestore

    path = _path()
    try:
        with filestore.PathLock(path):
            t = time.time() if now is None else now
            held = _read(path, t, ttl_s)
            base = held.get(call_id) or {}
            at = base.get("at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
            kept = [dict(r, at=r.get("at") or at) for r in rows]
            held[call_id] = dict(
                base, usd=sum(float(r.get("cost_usd") or 0.0) for r in kept), at=at,
                feature=base.get("feature", kept[0].get("feature", "") if kept else ""),
                network=base.get("network", ""), background=bool(base.get("background")),
                day=base.get("day", ""), month=base.get("month", ""),
                expires_at=float(base.get("expires_at") or t + ttl_s), pid=os.getpid(),
                unrecorded=True, rows=kept)
            _write(path, held)
        log.error("ai reservations: the record of AI calls refused %d row(s) of %s; its "
                  "reservation of $%.4f is kept, unexpiring, until the record takes them",
                  len(rows), call_id, held[call_id]["usd"])
        return True
    except (Unreadable, OSError) as exc:
        log.critical("ai reservations: the record of AI calls refused %s's row(s) AND its "
                     "reservation could not be kept (%s): it counts the call until it expires",
                     call_id, exc)
        return False


def open_reservations(now=None) -> dict:
    """``{"state": "ok"|"unreadable", "held", "error"}``: the open reservations, read without
    the lock (a reader's view: a screen or a test), expired ones left out (an unrecorded one
    never expires)."""
    t = time.time() if now is None else now
    path = _path()
    if not os.path.exists(path):
        return {"state": "ok", "held": {}, "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)["held"]
        return {"state": "ok", "error": "", "held": _live(got, t)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {"state": "unreadable", "held": {}, "error": f"{type(exc).__name__}: {exc}"}


def unrecorded(now=None) -> dict:
    """``{"state", "calls", "error"}``: each unrecorded reservation (C2047), ``{"id", "usd",
    "at", "feature", "rows"}`` (its late rows' count), oldest first; a reader's view."""
    got = open_reservations(now)
    rows = sorted(({"id": k, "usd": float(v["usd"]), "at": v.get("at") or "",
                    "feature": v.get("feature") or "", "rows": len(v.get("rows") or [])}
                   for k, v in got["held"].items() if v.get("unrecorded")),
                  key=lambda r: (r["at"], r["id"]))
    return {"state": got["state"], "calls": rows, "error": got["error"]}
