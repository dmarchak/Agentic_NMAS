"""How each person is named on Mercury's screens, records' summaries and exports (board E2a,
the operator, 2026-11-11: "Display names: configurable per person; default the part before
"@"").

One small store, `data/display_names.json`, in the shape of `modules/network_choice.py`'s:
``{actor: {"name", "set_by", "actor_verified", "at"}}``, keyed by the verified identity, written
under its lock, replaced atomically, owner-only from creation, and never written over when it
cannot be read. It is not a `settings_schema` key: it is per person, not per installation.

**One function draws every person:** `shown(actor)` (`identity.display_name`): the name the
person set, else the part of their identity before the "@", else the label a host login or a
service already has. It never returns the domain. **Recorded words are never rewritten:** a
text recorded with an identity inside it is drawn through `people(text)` (the Jinja filter
`people`), which replaces each email-shaped token with its display name at draw time. The full
verified identity stays in every record.

**Who may set what:** a verified person sets their own; an admin sets anyone's. Mercury holds
no roles yet, so every verified person is an admin (NSOT_AUTHORIZATION section 6), and a service
or an unverified request never is: the route says which the request is (`set_name`'s *admin*).

An unreadable store is said, refuses a write (`Unreadable`), and every name is then drawn as
its default.
"""

import hashlib
import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

FILENAME = "display_names.json"
#: The longest display name, in printable characters (board E2a's bound): the name chip and
#: History's "who" column draw it in one line.
MAX_LENGTH = 32

#: An email-shaped token in a recorded text: a local part, "@", and a domain of dotted labels.
#: The domain never ends in a dot, so a sentence's full stop after an address stays where it is.
#: A word that only holds an "@" is not one, and is left as recorded: the user part of an
#: address in a URL (``https://user@host/…``, after a "/") and a remote written as
#: ``git@host:path`` (a ":" or "/" with more behind it).
#: The domain is matched whole or not at all (an atomic group), so a refused word is never
#: taken in part.
#: Inside a JSON-encoded text (an AI request's ``pack``, C3424) an address may follow an escape
#: (``\n``, ``\t``, ``\"``, ``\u00e9``): the address starts after the escape, and the escape's
#: letter is never taken as the address's first, so a replacement never leaves a ``\`` before
#: a letter that would make an escape JSON refuses (``\person-…``). The local part may hold any
#: letter, digit or "_", not only ASCII ones (``josé@…``, ``_ops@…``), so no part of such an
#: address is left.
EMAIL = re.compile(r"(?:(?<=\\[nrtbf])|(?<=\\u[0-9A-Fa-f]{4})|(?<![\w.%+/@-])"
                   r"(?!(?<=\\)(?:[nrtbf]|u[0-9A-Fa-f]{4})))"
                   r"\w[\w.%+-]*@"
                   r"(?>[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*)(?![\w-]|[:/]\S)")
#: A stable label (`label`): what a person is in a text sent off the host.
LABEL = re.compile(r"person-[0-9a-f]{6}")

#: How Mercury names itself, a service, and nobody, on its records: never a person's name, or a
#: record "by Mercury" could be a person's.
_RESERVED = ("mercury", "you", "nobody", "nobody recorded", "unknown", "unverified",
             "not identified")
_RESERVED_PREFIXES = ("mercury:", "service:")


class Unreadable(RuntimeError):
    """The store exists and cannot be read; nothing is written over it. *kind* is the failure's
    own name (``ValueError`` for a file that is not a table of people), for a refusal to say."""

    def __init__(self, message: str, kind: str = "OSError"):
        super().__init__(message)
        self.kind = kind


class Refused(ValueError):
    """A display name that is not saved; the message names the comparison and both sides."""


def _path() -> str:
    from modules.config import DATA_DIR

    return os.path.join(DATA_DIR, FILENAME)


#: The parsed store, kept until the file changes (its path, inode, size and modification
#: time): a page draws hundreds of people, and each is one `os.stat`, never one read.
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
    """The store's table (empty when the file is absent); raises `Unreadable`. The answer, a
    failure included, is kept until the file changes."""
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


def default(actor: str) -> str:
    """How *actor* is drawn with no name set: the part of a person's identity before the "@";
    a service token by its label (`identity.service_label`); anything else (a host login,
    Mercury's own name for a job, "unverified") as it is. Never the domain."""
    actor = str(actor or "").strip()
    if not actor:
        return ""
    if actor.startswith("service:"):
        from modules import identity

        return identity.service_label(actor[len("service:"):])
    if "@" in actor:
        return actor.split("@", 1)[0] or "unnamed"
    return actor


def of(actor: str) -> str:
    """The name *actor* has set, or "" (none set, or the store cannot be read: the default is
    then drawn, and the failure logged)."""
    if not actor:
        return ""
    try:
        row = _read().get(actor) or {}
    except Unreadable as exc:
        # Said once per failure, never once per person drawn: a page draws hundreds.
        if _CACHE.get("warned") != str(exc):
            _CACHE["warned"] = str(exc)
            log.warning("display_names: %s; each person is drawn by their default", exc)
        return ""
    return str(row.get("name") or "")


def shown(actor: str) -> str:
    """How *actor* is drawn: the name they set, else their default. Never the domain."""
    return of(actor) or default(actor)


def people(text) -> str:
    """*text* with each email-shaped token replaced by that person's display name: a recorded
    text, or a recorded actor, as a screen or an export draws it (a service token's actor by
    its label). Every other word is left exactly as recorded."""
    text = "" if text is None else str(text)
    if text.startswith("service:") and not any(c.isspace() for c in text):
        return default(text)
    if "@" not in text:
        return text
    return EMAIL.sub(lambda m: shown(m.group(0)), text)


def people_payload(value):
    """*value* (a page's model: tables, lists and words) with every string in it drawn through
    `people`, as a copy: a model whose words its sources wrote, each naming people by identity,
    for a screen that names them by display name. Keys are left as they are, and so is what
    a row is known by (``id``, ``event``): the page sends those back, and they must match."""
    if isinstance(value, str):
        return people(value) if "@" in value or value.startswith("service:") else value
    if isinstance(value, dict):
        return {k: (v if k in ("id", "event") else people_payload(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(people_payload(v) for v in value)
    return value


#: The per-installation secret a person's label is keyed under (C3426; the operator,
#: 2026-11-13: "labels are a keyed hash (HMAC) under a per-installation secret, generated at
#: install, kept in the credential store, never sent or shown"): generated on the
#: installation's first label, sealed in the settings' credential store (`secrets_store`,
#: `SECRET_KEYS`, masked on every read), held in this process once read.
LABEL_KEY_SETTING = "person_label_key"
_LABEL_KEY = {}


def _label_key() -> bytes:
    """This installation's label key: read from the credential store, or generated there once
    (under the settings lock, read again inside it, so two processes keep one key). Never
    logged, sent or returned by any route."""
    held = _LABEL_KEY.get("key")
    if held is not None:
        return held
    from modules import secrets_store
    from modules.config import settings_lock

    value = secrets_store.get_secret("person_label_key")
    if not value:
        with settings_lock():
            value = secrets_store.get_secret("person_label_key")
            if not value:
                import secrets
                value = secrets.token_hex(32)
                secrets_store.set_secret("person_label_key", value)
                log.info("display names: this installation's label key was generated and sealed")
    _LABEL_KEY["key"] = value.encode("utf-8")
    return _LABEL_KEY["key"]


def label(actor: str, key: bytes = None) -> str:
    """A person as a text sent off the host names them: a stable label, the same for the same
    identity in every request ("person-3f9a1c"), never their identity or a name they set.

    **Stable:** an HMAC-SHA-256 of the identity, trimmed and lower-cased, under this
    installation's secret key (`_label_key`; *key* replaces it in a test), behind a fixed
    prefix, so one identity has one label in every pack, every call and every process, however
    its case was written; distinct identities differ but by a 24-bit chance (about 1 in 3,400
    that any two of 100 people share one). **Nothing of the address in it, and not
    recomputable from the code** (C3424, C3426): six hex digits of a keyed one-way digest, so
    someone holding a candidate address and this code, but not the installation's key, cannot
    confirm the guess."""
    import hmac
    digest = hmac.new(_label_key() if key is None else key,
                      str(actor).strip().lower().encode("utf-8"), hashlib.sha256)
    return "person-" + digest.hexdigest()[:6]


def labelled(text) -> str:
    """*text* with each email-shaped token replaced by its person's stable label (`label`):
    a recorded text as an AI request carries it (the operator, 2026-11-12, objective 2: no
    identity or name in an AI payload). Every other word is left exactly as recorded."""
    text = "" if text is None else str(text)
    if "@" not in text:
        return text
    return EMAIL.sub(lambda m: label(m.group(0)), text)


def is_person(actor: str) -> bool:
    """Whether *actor*, a recorded actor, names a person: not empty, not how Mercury names
    itself, a service or nobody (`_RESERVED`, `_RESERVED_PREFIXES`), and not a label already."""
    actor = str(actor or "").strip()
    low = actor.casefold()
    return bool(actor) and low not in _RESERVED and not low.startswith(_RESERVED_PREFIXES) \
        and not LABEL.fullmatch(actor)


def as_sent(actor, actors=()) -> str:
    """A recorded actor (a record's ``who``, ``actor``, ``created_by``) as an AI request
    carries it (C3424): a person's stable label (`label`); Mercury's own name, nobody, or a
    label already, as it is; a service by its label (`default`). A value with a space in it is
    words, not one actor ("alex (host login, not a verified identity)"): each person in it
    labelled (`unnamed`, with *actors*' names)."""
    actor = "" if actor is None else str(actor)
    one = actor.strip()
    if not one or any(c.isspace() for c in one):
        return unnamed(actor, actors)
    if one.casefold().startswith("service:"):
        return default(one)
    return label(one) if is_person(one) else actor


def _names_of(actor: str) -> list:
    """The ways *actor* can be written in a recorded text other than their identity: the name
    they set and their default, longest first."""
    out = {of(actor), default(actor)}
    return sorted((n for n in out if n and n != actor), key=len, reverse=True)


def unnamed(text, actors=()) -> str:
    """*text* with no person named in it, as an AI request carries it: each email-shaped
    identity labelled (`labelled`), and each of *actors*' display names (set or default)
    replaced by that actor's label where it stands as a word of its own."""
    out = labelled(text)
    for actor in actors:
        if not is_person(actor):
            continue
        mark = label(actor)
        for name in _names_of(actor):
            out = re.sub(r"(?<![\w.@-])" + re.escape(name) + r"(?![\w@-])", mark, out)
    return out


def known() -> list:
    """Every identity the store holds (their set names are what a recorded text may name them
    by), or none when it cannot be read. A READ: it writes nothing."""
    try:
        return sorted(_read())
    except Unreadable:
        return []


def person_key(actor: str) -> str:
    """A person's key on a form: a digest of their identity, so the page never carries the
    identity itself outside its record."""
    return hashlib.sha256(("display-name:" + str(actor)).encode("utf-8")).hexdigest()[:16]


def _why_not(name: str) -> str:
    """Why *name* cannot be a display name, both sides named, or ""."""
    if "@" in name:
        return f"A display name holds no address: '{name}' contains '@'."
    bad = [c for c in name if not c.isprintable()]
    if bad:
        return (f"A display name is at most {MAX_LENGTH} printable characters: this one holds "
                f"{len(bad)} that cannot be printed (the first is U+{ord(bad[0]):04X}).")
    if len(name) > MAX_LENGTH:
        return (f"A display name is at most {MAX_LENGTH} printable characters: this one is "
                f"{len(name)}.")
    low = name.casefold()
    if low in _RESERVED or low.startswith(_RESERVED_PREFIXES):
        return (f"A display name is a person's: '{name}' is how Mercury names itself, a service "
                "or nobody on its records.")
    return ""


def _taken_by(table: dict, person: str, name: str) -> str:
    """Why *name* is another person's already, or "": another person's set name, or the default
    of another person the store holds."""
    low = name.casefold()
    for other, row in table.items():
        if other == person:
            continue
        if str(row.get("name") or "").casefold() == low:
            return (f"'{name}' is already {shown(other)}'s display name: choose another, so two "
                    "people are never drawn alike.")
        if default(other).casefold() == low:
            return (f"'{name}' is already {shown(other)}'s default name (the part of their "
                    "identity before the \"@\"): choose another, so two people are never drawn "
                    "alike.")
    return ""


def set_name(person: str, name: str, *, by: str, actor_verified: str, admin: bool = False,
             now: float = None) -> dict:
    """Set *person*'s display name to *name*, as *by* (the request's verified actor, established
    as *actor_verified*); an empty *name* returns them to the default. *admin* is whether *by*
    may change another person's. ``{"person", "name", "shown", "was", "default": bool,
    "nothing": bool, "at"}``.

    Raises `Refused`, naming both sides, for a name with an "@", one longer than `MAX_LENGTH`
    or not printable, one another person already has, a name Mercury uses for itself, or another
    person's name changed by someone who is no admin; and `Unreadable` rather than replace a
    store it cannot read."""
    from modules.filestore import PathLock, write_atomic

    person, by = str(person or "").strip(), str(by or "").strip()
    if not by or by == "unverified":
        raise Refused("A display name is set by a verified person: this request's identity is "
                      "not verified.")
    if not person:
        raise Refused("A display name is one person's: no person was named.")
    if person != by and not admin:
        raise Refused(f"Only an admin changes another person's display name: you are "
                      f"{shown(by)}, and this is {shown(person)}'s.")
    name = " ".join(str(name or "").split())
    why = _why_not(name) if name else ""
    if why:
        raise Refused(why)
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now))
    with PathLock(_path):
        table = dict(_read())
        was = str((table.get(person) or {}).get("name") or "")
        if name:
            why = _taken_by(table, person, name)
            if why:
                raise Refused(why)
        if name == was:
            return {"person": person, "name": name, "shown": name or default(person),
                    "was": was, "default": not name, "nothing": True, "at": at}
        # A name returned to the default keeps its row, empty: who returned it, and when.
        table[person] = {"name": name, "set_by": by, "actor_verified": actor_verified, "at": at}
        # `write_atomic` makes its temporary file owner-only (0600) before a byte is written
        # and replaces the store with it, so the store is owner-only from creation.
        write_atomic(_path(), json.dumps(table, indent=1, sort_keys=True) + "\n")
    log.info("display_names: a display name was %s (no identity logged)",
             "set" if name else "returned to its default")
    return {"person": person, "name": name, "shown": name or default(person), "was": was,
            "default": not name, "nothing": False, "at": at}


def resolve(key: str, viewer: str) -> str:
    """The identity a form's person *key* names: the viewer's own (an empty key, or theirs), or
    a person the store holds; "" when it names nobody known. Raises `Unreadable`."""
    if not key or key == person_key(viewer):
        return viewer
    for actor in _read():
        if person_key(actor) == key:
            return actor
    return ""


def view(viewer: str, how: str = "", admin: bool = False) -> dict:
    """What the Display names card draws for *viewer* (a verified actor, or "" for nobody
    verified; *how* is how they were verified, in words): ``{"readable", "why", "viewer",
    "rows": [{"key", "you", "shown", "set", "default", "set_by", "at", "identity", "how",
    "may_change"}], "max"}``, the viewer first, then every other person the store holds, by
    name. A READ: it writes nothing."""
    out = {"readable": True, "why": "", "viewer": bool(viewer), "rows": [], "max": MAX_LENGTH}
    try:
        table = _read()
    except Unreadable as exc:
        table = {}
        out.update(readable=False, why=str(exc))

    def row(actor, you):
        r = table.get(actor) or {}
        name = str(r.get("name") or "")
        return {"key": person_key(actor), "you": you, "shown": name or default(actor),
                "set": name, "default": default(actor),
                "set_by": shown(r.get("set_by") or ""), "at": str(r.get("at") or ""),
                "identity": actor, "how": how if you else "",
                "may_change": out["readable"] and (you or admin)}

    if viewer:
        out["rows"].append(row(viewer, True))
    others = [row(a, False) for a in table if a != viewer]
    out["rows"] += sorted(others, key=lambda r: (r["shown"].casefold(), r["key"]))
    return out
