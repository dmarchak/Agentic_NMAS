"""Which network each verified person is looking at (board N, approved 2026-10-05: "the choice is
remembered per verified person, never for anyone else").

One small store, `data/network_choices.json`: ``{actor: {"current": name, "recent": [names,
newest first]}}``, written only by a person's own choice (`choose`), under its lock, replaced
atomically, owner-only. `listref.active()` reads it on a v2 request (`for_request`): the address's
``?list=`` first, then the person's own choice, then the installation's current list, so one
person's choice never moves another's page, and a background job or today's pages read the
installation's list as before.

An unreadable store is said and refuses a write (a record lost is lost), and a read takes the
installation's list rather than guessing.
"""

import json
import logging
import os

log = logging.getLogger(__name__)

FILENAME = "network_choices.json"
RECENT_KEPT = 8


class Unreadable(RuntimeError):
    """The store exists and cannot be read; nothing is written over it."""


def _path() -> str:
    from modules.config import DATA_DIR

    return os.path.join(DATA_DIR, FILENAME)


def _read() -> dict:
    p = _path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Unreadable(f"{p} cannot be read: {exc}") from None
    if not isinstance(got, dict):
        raise Unreadable(f"{p} holds {type(got).__name__}, not a table of people")
    return got


def of(actor: str) -> dict:
    """``{"current", "recent"}`` for *actor*; empty when they have chosen nothing, or the store
    cannot be read (the installation's list is then theirs)."""
    if not actor:
        return {"current": "", "recent": []}
    try:
        mine = _read().get(actor) or {}
    except Unreadable as exc:
        log.warning("network_choice: %s; the installation's current list is used", exc)
        mine = {}
    return {"current": str(mine.get("current") or ""),
            "recent": [str(n) for n in mine.get("recent") or []]}


def choose(actor: str, name: str) -> dict:
    """Record *actor*'s choice of the network *name* (registered, checked by the caller):
    current, and first of their recent ones. Raises `Unreadable` rather than replace a store it
    cannot read."""
    from modules.filestore import PathLock, write_atomic

    if not actor:
        raise ValueError("a choice is a verified person's; nobody was identified")
    with PathLock(_path):
        table = _read()
        mine = table.get(actor) or {}
        recent = [name] + [n for n in mine.get("recent") or [] if n != name]
        table[actor] = {"current": name, "recent": recent[:RECENT_KEPT]}
        write_atomic(_path(), json.dumps(table, indent=1, sort_keys=True) + "\n")
        os.chmod(_path(), 0o600)
    return table[actor]


def for_request() -> str:
    """The verified person's own choice on this request, or ""."""
    from modules import identity

    try:
        ident = identity.viewer()
    except Exception:                                 # noqa: BLE001 (no identity: no choice)
        return ""
    if not getattr(ident, "is_identified", False) or getattr(ident, "kind", "") != "person":
        return ""
    return of(ident.actor)["current"]
