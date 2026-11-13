"""Each person's time zone, in which every v2 screen draws its times (one time zone per screen,
docs/UI_RULES.md; the operator, 2026-11-12: "The server draws times in the viewer's stored time
zone (a per-person setting like display names, defaulting from the browser on first visit), so
no UTC flashes before the script runs").

One small store, `data/time_zones.json`, in the shape of `modules/display_names.py`'s:
``{actor: {"zone", "set_by", "actor_verified", "at", "source"}}``, keyed by the verified
identity, written under its lock, replaced atomically, owner-only from creation, and never
written over when it cannot be read. *source* is ``browser`` (the zone the person's browser
named on their first visit) or ``person`` (set on Settings › Installation › Access and
identity's Time zone card). It is not a `settings_schema` key: it is per person.

**The zone a screen draws in:** `zone_of(actor)`: the person's stored zone, else the host's
own (`time.localtime`, as the can't-fix email says it) for a viewer with no identity or no
stored zone. A zone is an IANA name `zoneinfo` knows ("America/Denver"), or "UTC"; anything
else is refused naming it.

**Who sets it:** a verified person sets their own (a time zone is how one person reads the
screens, never another's). The first visit's zone is set only while none is stored: the
browser's never replaces a zone a person chose.

An unreadable store is said, refuses a write (`Unreadable`), and every time is then drawn in
the host's zone.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

FILENAME = "time_zones.json"
#: Where a zone came from: the browser's on a first visit, or a person's choice.
SOURCES = ("browser", "person")


class Unreadable(RuntimeError):
    """The store exists and cannot be read; nothing is written over it."""

    def __init__(self, message: str, kind: str = "OSError"):
        super().__init__(message)
        self.kind = kind


class Refused(ValueError):
    """A zone that is not saved; the message names the comparison and both sides."""


def _path() -> str:
    from modules.config import DATA_DIR

    return os.path.join(DATA_DIR, FILENAME)


#: The parsed store, kept until the file changes: every time a page draws asks it, and each
#: ask is one `os.stat`, never one read.
_CACHE = {"key": None, "table": None}


def _signature(p: str):
    try:
        st = os.stat(p)
    except FileNotFoundError:
        return (p, None)
    except OSError as exc:
        raise Unreadable(f"{p} cannot be read ({type(exc).__name__}): {exc}",
                         type(exc).__name__) from None
    return (p, st.st_ino, st.st_size, st.st_mtime_ns)


def _parse(p: str) -> dict:
    try:
        with open(p, encoding="utf-8") as fh:
            table = json.load(fh)
    except (OSError, ValueError) as exc:
        kind = "ValueError" if isinstance(exc, ValueError) else type(exc).__name__
        raise Unreadable(f"{p} cannot be read ({kind}): {exc}", kind) from None
    if not isinstance(table, dict) or not all(isinstance(v, dict) for v in table.values()):
        raise Unreadable(f"{p} cannot be read (ValueError): it holds a "
                         f"{type(table).__name__}, not a table of people", "ValueError")
    return table


def _read() -> dict:
    """The store's table (empty when the file is absent); raises `Unreadable`."""
    p = _path()
    key = _signature(p)
    if _CACHE["key"] != key:
        try:
            got = {} if key[1] is None else _parse(p)
        except Unreadable as exc:
            got = exc
        _CACHE.update(key=key, table=got)
    if isinstance(_CACHE["table"], Unreadable):
        raise _CACHE["table"]
    return _CACHE["table"]


def unreadable() -> str:
    """Why the store cannot be read, or "" (absent is readable, and empty)."""
    try:
        _read()
    except Unreadable as exc:
        return str(exc)
    return ""


def zone_info(name: str):
    """*name* as a `zoneinfo.ZoneInfo`, or None when `zoneinfo` does not know it."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    name = str(name or "").strip()
    if not name or name.startswith(("/", ".")) or ".." in name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def why_not(name: str) -> str:
    """Why *name* cannot be a time zone, both sides named, or ""."""
    if not str(name or "").strip():
        return "A time zone is named: none was given."
    if zone_info(name) is None:
        return (f"A time zone is an IANA name this installation's time zone database knows "
                f"(for example America/Denver, Europe/London or UTC): '{name}' is not one.")
    return ""


_NAMES = {"names": None}


def zone_names(first: str = "") -> list:
    """The zone picker's choices (`_macros.zone_picker`): *first* (the viewer's own kept zone,
    when they have one), then "UTC", then every zone this host's database holds, by name; each
    once. The database is read once per process (it changes with the host's packages, which a
    restart follows). A picker offers these and a save still checks what was sent (`why_not`):
    a name typed that is not among them is refused, naming it."""
    if _NAMES["names"] is None:
        from zoneinfo import available_timezones

        _NAMES["names"] = sorted(z for z in available_timezones()
                                 if "/" in z and not z.startswith(("posix/", "right/", "Etc/")))
    lead = [z for z in (str(first or "").strip(), "UTC") if z and zone_info(z) is not None]
    lead = list(dict.fromkeys(lead))
    return lead + [z for z in _NAMES["names"] if z not in lead]


def stored(actor: str) -> str:
    """*actor*'s stored zone, or "" (none stored, no actor, or an unreadable store)."""
    if not actor:
        return ""
    try:
        row = _read().get(actor) or {}
    except Unreadable:
        return ""
    zone = str(row.get("zone") or "")
    return zone if zone_info(zone) is not None else ""


def zone_of(actor: str):
    """The zone *actor*'s screens draw in: their stored zone's `ZoneInfo`, else None, the
    host's own (`time.localtime`)."""
    zone = stored(actor)
    return zone_info(zone) if zone else None


def set_zone(person: str, zone: str, *, by: str, actor_verified: str, source: str = "person",
             now: float = None) -> dict:
    """Set *person*'s time zone to *zone*, as *by* (the request's verified actor, established
    as *actor_verified*); *source* ``browser`` sets it only while none is stored (the first
    visit), ``person`` always. ``{"person", "zone", "was", "nothing": bool, "at", "source"}``.

    Raises `Refused`, naming both sides, for a zone `zoneinfo` does not know, a request that is
    no verified person's, or another person's zone; and `Unreadable` rather than replace a store
    it cannot read."""
    from modules.filestore import PathLock, write_atomic

    person, by = str(person or "").strip(), str(by or "").strip()
    zone = str(zone or "").strip()
    if not by or by == "unverified":
        raise Refused("A time zone is set by a verified person: this request's identity is "
                      "not verified.")
    if person != by:
        raise Refused("A time zone is one person's own: it is set by that person, never for "
                      "another.")
    if source not in SOURCES:
        raise Refused(f"A time zone comes from {' or '.join(SOURCES)}: not '{source}'.")
    why = why_not(zone)
    if why:
        raise Refused(why)
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now))
    with PathLock(_path):
        table = dict(_read())
        was = str((table.get(person) or {}).get("zone") or "")
        if zone == was or (source == "browser" and was):
            return {"person": person, "zone": was or zone, "was": was, "nothing": True,
                    "at": at, "source": source}
        table[person] = {"zone": zone, "set_by": by, "actor_verified": actor_verified,
                         "at": at, "source": source}
        write_atomic(_path(), json.dumps(table, indent=1, sort_keys=True) + "\n")
    log.info("time_zones: a time zone was set from the %s (no identity logged)", source)
    return {"person": person, "zone": zone, "was": was, "nothing": False, "at": at,
            "source": source}


def host_zone_name(now: float = None) -> str:
    """The host's own zone, as `time.localtime` names it ("UTC", "MST")."""
    t = time.localtime(time.time() if now is None else now)
    return t.tm_zone or "UTC"


def view(viewer: str) -> dict:
    """What the Time zone card draws for *viewer* (a verified actor, or "" for nobody
    verified): ``{"readable", "why", "viewer", "zone", "source", "at", "host"}``. A READ: it
    writes nothing."""
    out = {"readable": True, "why": "", "viewer": bool(viewer), "zone": "", "source": "",
           "at": "", "host": host_zone_name()}
    try:
        row = _read().get(viewer) or {} if viewer else {}
    except Unreadable as exc:
        row = {}
        out.update(readable=False, why=str(exc))
    out.update(zone=str(row.get("zone") or ""), source=str(row.get("source") or ""),
               at=str(row.get("at") or ""))
    return out
