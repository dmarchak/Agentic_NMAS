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

**The store** is a small JSON file beside the record of AI calls (``ai_reservations.json``,
owner-only from creation: `filestore.write_atomic`'s ``mkstemp`` is 0600, replaced atomically).
It holds no request, answer or key: ``{"held": {call_id: {"usd", "feature", "network",
"background", "day", "month", "at", "expires_at", "pid"}}}``.

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
            live = {k: v for k, v in held.items() if float(v["expires_at"]) > t}
            for k in sorted(set(held) - set(live)):
                log.warning("ai reservations: %s's reservation of $%.4f expired unsettled "
                            "(made at %s; its process died or never recorded it): dropped",
                            k, float(held[k]["usd"]), held[k].get("at"))
            said = judge(live)
            if said:
                if len(live) != len(held):
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


def open_reservations(now=None) -> dict:
    """``{"state": "ok"|"unreadable", "held", "error"}``: the open reservations, read without
    the lock (a reader's view: a screen or a test), expired ones left out."""
    t = time.time() if now is None else now
    path = _path()
    if not os.path.exists(path):
        return {"state": "ok", "held": {}, "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)["held"]
        return {"state": "ok", "error": "",
                "held": {k: v for k, v in got.items() if float(v["expires_at"]) > t}}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"state": "unreadable", "held": {}, "error": f"{type(exc).__name__}: {exc}"}
