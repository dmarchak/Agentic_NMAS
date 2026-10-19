"""Mercury's DOCUMENT stores on the records database (K31 part 3; docs/NSOT_PHASE4_RECORDS_POSTGRES.md
section 3: "then the approval queue (its concurrency fix)").

A line store (`records_migrate.LineStore`) only ever appends. A DOCUMENT store holds one JSON
document per network that its owner reads, changes and replaces whole: the approval queue, one
array per network, its items updated in place. On the records database each network's document
is one row of `audit.<store>_docs`:

- ``body``: the document now, which the store reads and writes once moved;
- ``copied`` and ``copied_sha256``: the document as copied from its file, which the check
  compares with the file (the file is read-only once moved, so the two must stay equal);
- ``version``: 1 as copied, one more each save, so the preview says how many saves were made
  since the move.

**The owner keeps its own cross-process lock.** Every read-modify-write of a document store
already holds `filestore.PathLock` on the document's path (the approval queue's R4 fix); the lock
file stays on the host's disk once the document has moved, so writers stay serialised across
processes on the one host, and each save is one transaction. A read writes nothing. A database
that does not answer raises `filestore.StoreUnreadable` on a read and refuses a write, as an
unreadable file does: "no approval is waiting" and "the queue could not be read" never share an
answer.

**Moving is the same person's operation as a line store's** (Settings › Installation ›
Connections, the Record stores card), with the same steps (`records_migrate.MOVE_STEPS`,
`BACK_STEPS`) and the same preview, bound by its fingerprint: copy (a network already copied
with the same file is skipped; one copied from a DIFFERENT file refuses, naming both hashes),
switch, copy again, check (each file against its copied document), the files read-only. Moving
back writes each network's current document to its file atomically, then switches, then checks
the files against what the table held. `records_migrate.plan`, `move`, `move_back` and
`check` hand a document store here.
"""

import dataclasses
import hashlib
import json
import logging
import os
from typing import Callable

log = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class DocStore:
    """One store of whole JSON documents, one per network. *files*: ``{network: path}`` of every
    document that exists; *path_for*: a network's document, for the move back; *shape*: the type
    the document must be (the approval queue: a list)."""

    name: str
    words: str
    table: str
    files: Callable[[], dict]
    path_for: Callable[[str], str]
    shape: type = list
    noun: str = "documents"

    @property
    def setting(self) -> str:
        return f"records_store_{self.name}"

    @property
    def qualified(self) -> str:
        return f"audit.{self.table}"


def _approval_queue() -> DocStore:
    from modules import approval_queue as Q
    from modules import records_migrate as RM

    return DocStore(name="approval_queue", words="Approval queue", table="approval_queue_docs",
                    files=lambda: RM.network_files(Q.QUEUE_FILE),
                    path_for=lambda network: RM.network_path(Q.QUEUE_FILE, network),
                    shape=list, noun="approval items")


#: Each document store, by name, built when asked (its owner imports late).
DOC_STORES = {"approval_queue": _approval_queue}


def is_doc_store(name: str) -> bool:
    return name in DOC_STORES


def store_of(name: str) -> DocStore:
    from modules.records_migrate import Refused

    build = DOC_STORES.get(name)
    if build is None:
        raise Refused(f"no document store {name!r}: the document stores are "
                      f"{', '.join(DOC_STORES)}")
    return build()


def on_database(name: str) -> bool:
    from modules import records_db

    return records_db.backend(name) == records_db.POSTGRES


def _sha(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True)


def _schema(st: DocStore) -> tuple:
    return ("create schema if not exists audit",
            f"create table if not exists {st.qualified} ("
            " network text primary key,"
            " body jsonb not null,"
            " copied jsonb not null,"
            " copied_sha256 bytea not null,"
            " version bigint not null default 1,"
            " updated_at timestamptz not null default now())")


def _exists(conn, st: DocStore) -> bool:
    return conn.execute("select to_regclass(%s) is not null", (st.qualified,)).fetchone()[0]


# ── The owner's reads and writes, once moved ─────────────────────────────────────────────────

def load(name: str, network: str, empty):
    """The network's document for a read-modify-write (the owner holds its lock), or *empty*
    when none is kept. Raises `filestore.StoreUnreadable` when the database cannot be asked or
    holds something of the wrong shape: never *empty* for "could not be read"."""
    from modules import records_db
    from modules.filestore import StoreUnreadable

    st = store_of(name)
    try:
        with records_db.connect() as conn:
            if not _exists(conn, st):
                return empty
            row = conn.execute(f"select body from {st.qualified} where network = %s",
                               (network,)).fetchone()
    except Exception as exc:                          # noqa: BLE001 (refused, named)
        first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        raise StoreUnreadable(f"the {st.words.lower()} could not be read from the records "
                              f"database ({type(exc).__name__}: {first}), so nothing was "
                              "written") from exc
    if row is None:
        return empty
    if not isinstance(row[0], st.shape):
        raise StoreUnreadable(f"the {st.words.lower()} in the records database is not a "
                              f"{st.shape.__name__}, so nothing was written")
    return row[0]


def save(name: str, network: str, value) -> None:
    """Replace the network's document, one transaction; raises naming why when the database
    cannot take it. A network with none yet gets its row, its copy the empty document."""
    from psycopg.types.json import Jsonb

    from modules import records_db

    st = store_of(name)
    with records_db.connect() as conn:
        for sql in _schema(st):
            conn.execute(sql)
        empty = st.shape()
        conn.execute(f"insert into {st.qualified} (network, body, copied, copied_sha256)"
                     " values (%s, %s, %s, %s) on conflict (network) do update set"
                     " body = excluded.body, version = "
                     f"{st.qualified}.version + 1, updated_at = now()",
                     (network, Jsonb(value), Jsonb(empty), _sha(_canonical(empty))))


# ── Plan, copy, check: the migration, as records_migrate's for a line store ─────────────────

def _file_doc(path: str, st: DocStore):
    """``(value, text, unparsable)`` for a document file."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        value = json.loads(text)
    except ValueError as exc:
        return None, text, f"it is not JSON ({exc})"
    if not isinstance(value, st.shape):
        return None, text, f"it is not a {st.shape.__name__}"
    return value, text, ""


def file_counts(store: str) -> dict:
    """``{network: entries}`` in each network's file, reading only the files (the records-check
    reader's count; a file that cannot be read counts 0, and the move's preview names it)."""
    st = store_of(store)
    out = {}
    for n, path in st.files().items():
        try:
            value = _file_doc(path, st)[0]
        except OSError:
            value = None
        out[n] = len(value) if value is not None else 0
    return out


def plan(connector=None, store: str = "") -> dict:
    """What a move or a move back would do, writing nothing, in the shape the Record stores card
    draws for a line store: per network, ``lines`` and ``rows`` the document's entries,
    ``copied`` the entries copied (None when the database could not be asked), ``since`` the
    saves made since the move."""
    from modules import records_db

    st = store_of(store)
    backend = records_db.backend(st.name)
    nets = {}
    for n, path in st.files().items():
        value, _text, bad = _file_doc(path, st)
        count = len(value) if value is not None else 0
        nets[n] = {"lines": count, "rows": count, "completions": 0, "unparsable": bad}
    db = {"ok": False, "error": ""}
    table = {}
    try:
        with (connector or records_db.connect)() as conn:
            if _exists(conn, st):
                for n, copied, version in conn.execute(
                        f"select network, copied, version from {st.qualified}").fetchall():
                    table[n] = (len(copied), version - 1)
            db["ok"] = True
    except Exception as exc:                          # noqa: BLE001 (named on the preview)
        db["error"] = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
    out = []
    for n in sorted(set(nets) | set(table)):
        c = nets.get(n) or {"lines": 0, "rows": 0, "completions": 0, "unparsable": ""}
        copied, since = table.get(n, (0, 0)) if db["ok"] else (None, None)
        out.append(dict(c, network=n, copied=copied, since=since))
    basis = json.dumps([st.name, backend, db["ok"], [(r["network"], r["lines"], r["copied"],
                                                      r["since"]) for r in out]], sort_keys=True)
    return {"store": st.name, "words": st.words, "second_kind": "", "noun": st.noun, "unit": "item",
            "backend": backend, "db": db, "networks": out,
            "fingerprint": hashlib.sha256(basis.encode()).hexdigest()[:16]}


def copy(conn, store: str) -> dict:
    """Copy each network's document into the table. ``{network: {"copied", "skipped"}}`` in
    entries. Refuses (`records_migrate.Refused`) a network copied before from a different file."""
    from psycopg.types.json import Jsonb

    from modules.records_migrate import Refused

    st = store_of(store)
    out = {}
    for network, path in st.files().items():
        value, text, bad = _file_doc(path, st)
        if bad:
            raise Refused(f"{network}: {os.path.basename(path)} cannot be moved: {bad}")
        h = _sha(_canonical(value))
        row = conn.execute(f"select copied_sha256 from {st.qualified} where network = %s",
                           (network,)).fetchone()
        if row is not None:
            if bytes(row[0]) != h:
                raise Refused(f"{network}: the document has sha256 {h.hex()[:16]} and the table "
                              f"holds a copy with {bytes(row[0]).hex()[:16]}: the file changed "
                              "after it was copied")
            out[network] = {"copied": 0, "skipped": len(value)}
            continue
        conn.execute(f"insert into {st.qualified} (network, body, copied, copied_sha256)"
                     " values (%s, %s, %s, %s)", (network, Jsonb(value), Jsonb(value), h))
        out[network] = {"copied": len(value), "skipped": 0}
    conn.commit()
    return out


def check(connector=None, store: str = "") -> dict:
    """Per network, the file's document against the table's copy, in the shape a line store's
    check answers. Raises when the database cannot be asked."""
    from modules import records_db

    st = store_of(store)
    results = []
    with (connector or records_db.connect)() as conn:
        exists = _exists(conn, st)
        rows = {n: (copied, version) for n, copied, version in (conn.execute(
            f"select network, copied, version from {st.qualified}").fetchall()
            if exists else [])}
    files = st.files()
    for network in sorted(set(files) | set(rows)):
        value = None
        if network in files:
            value, _text, bad = _file_doc(files[network], st)
        copied, _version = rows.get(network, (None, 0))
        if network not in files:
            differs = ""          # written after the move, never in a file: nothing to compare
        elif network not in rows:
            differs = "the document is in its file and not in the table"
        elif value is None:
            differs = f"the file cannot be read ({bad})"
        elif _canonical(value) != _canonical(copied):
            differs = (f"the file differs from the copy: file {_sha(_canonical(value)).hex()[:16]}"
                       f", table {_sha(_canonical(copied)).hex()[:16]}")
        else:
            differs = ""
        size = len(value) if value is not None else 0
        results.append({"network": network, "file": size,
                        "table": len(copied) if copied is not None else 0,
                        "merged": [size, len(copied) if copied is not None else 0],
                        "ok": not differs, "differs": differs})
    ok = all(r["ok"] for r in results)
    words = "; ".join(f"{r['network']}: file {r['file']} entries, copied {r['table']}"
                      + ("" if r["ok"] else f": {r['differs']}")
                      for r in results) or f"no {st.noun} in any network"
    return {"ok": ok, "networks": results, "words": words}


def back(actor: str, verified: str, connector=None, store: str = "") -> dict:
    """Write each network's current document to its file (atomically, owner-only), then switch
    to files; the rows are removed only after every file holds its document."""
    from modules import records_db
    from modules import records_migrate as RM
    from modules.filestore import write_atomic

    st = store_of(store)
    for path in st.files().values():
        os.chmod(path, 0o600)
    exported = {}
    with (connector or records_db.connect)() as conn:
        if _exists(conn, st):
            got = conn.execute(f"select network, body, version from {st.qualified}").fetchall()
            for network, body, version in got:
                path = st.path_for(network)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                write_atomic(path, json.dumps(body, indent=2))
                exported[network] = version - 1
            conn.execute(f"delete from {st.qualified}")
            conn.commit()
    entry = RM._switch(records_db.FILE, actor, verified, store)
    return {"exported": exported, "recorded": entry.get("recorded", True),
            "record_error": entry.get("record_error", "")}


def move(fingerprint: str, actor: str, verified: str, connector=None, store: str = "") -> dict:
    """Move a document store to the records database: `records_migrate.MOVE_STEPS`, as a line
    store moves."""
    from modules import records_db
    from modules import records_migrate as RM

    st = store_of(store)
    steps = []

    def step(name, detail, ok=True):
        steps.append({"name": name, "ok": ok, "detail": detail})

    with RM._Lock():
        RM._preconditions(plan(connector, store), records_db.FILE, fingerprint)
        step("plan", "the counts the preview drew, read again: unchanged")
        with (connector or records_db.connect)() as conn:
            for sql in _schema(st):
                conn.execute(sql)
            conn.commit()
            got = copy(conn, store)
        step("copy", ", ".join(f"{n}: {v['copied']} copied, {v['skipped']} already there"
                               for n, v in got.items()) or f"no {st.noun} in any network")
        entry = RM._switch(records_db.POSTGRES, actor, verified, store)
        step("switch", f"the {st.words.lower()} now reads and writes the records database"
             + ("" if entry.get("recorded", True) else
                f"; its record could not be written: {entry.get('record_error')}"))
        try:
            with (connector or records_db.connect)() as conn:
                again = copy(conn, store)
            step("copy-again", ", ".join(f"{n}: {v['copied']} more" for n, v in again.items())
                 or "nothing more")
            result = check(connector, store)
        except Exception as exc:                      # noqa: BLE001 (after the switch: undo it)
            first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
            step("copy-again" if len(steps) == 3 else "check", first, ok=False)
            return {"ok": False, "steps": steps, "check": None,
                    "switched_back": back(actor, verified, connector, store),
                    "recorded": entry.get("recorded", True)}
        step("check", result["words"], ok=result["ok"])
        if not result["ok"]:
            return {"ok": False, "steps": steps, "check": result,
                    "switched_back": back(actor, verified, connector, store),
                    "recorded": entry.get("recorded", True)}
        for path in st.files().values():
            os.chmod(path, 0o400)
        step("read-only", f"{len(st.files())} file(s) now read-only, kept for a release")
    return {"ok": True, "steps": steps, "check": result, "switched_back": None,
            "recorded": entry.get("recorded", True)}


def move_back(fingerprint: str, actor: str, verified: str, connector=None,
              store: str = "") -> dict:
    """Move a document store back to its files: `records_migrate.BACK_STEPS`. The files must read
    what the table held, network by network."""
    from modules import records_db
    from modules import records_migrate as RM

    st = store_of(store)
    steps = []
    with RM._Lock():
        RM._preconditions(plan(connector, store), records_db.POSTGRES, fingerprint)
        steps.append({"name": "plan", "ok": True,
                      "detail": "the counts the preview drew, read again: unchanged"})
        with (connector or records_db.connect)() as conn:
            before = {n: body for n, body in (conn.execute(
                f"select network, body from {st.qualified}").fetchall()
                if _exists(conn, st) else [])}
        done = back(actor, verified, connector, store)
        steps.append({"name": "export", "ok": True,
                      "detail": ", ".join(f"{n}: {c} save(s) since the move"
                                          for n, c in done["exported"].items())
                      or "no document was kept on the database"})
        steps.append({"name": "switch", "ok": True,
                      "detail": f"the {st.words.lower()} now reads and writes its files again"
                      + ("" if done["recorded"] else
                         f"; its record could not be written: {done['record_error']}")})
        files = st.files()
        moved = [n for n in before
                 if n not in files or _canonical(_file_doc(files[n], st)[0]) !=
                 _canonical(before[n])]
        steps.append({"name": "check", "ok": not moved,
                      "detail": ("each file reads what the table held: "
                                 + ", ".join(f"{n} {len(before[n])}" for n in sorted(before))
                                 if not moved else
                                 "the files read differently from the table for: "
                                 + ", ".join(moved))})
    return {"ok": not moved, "steps": steps, "recorded": done["recorded"]}
