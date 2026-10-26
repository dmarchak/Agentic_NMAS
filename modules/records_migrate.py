"""Moving a store of Mercury's records from its files into the records database, and back
(Phase 4, docs/NSOT_PHASE4_RECORDS_POSTGRES.md section 7: deploy receipts first). The ONE owner
of each moved store's table: its definition, its writes and its reads.

**A LINE STORE** (`LineStore`, K31): an append-only file of JSON lines, one per network or one
for the installation, whose owner module writes and reads it through one seam. Deploy receipts
were the first; every store of that shape moves by the same steps, each with its own table and
its own switch (`records_store_<name>`, P4-2: store by store, for the whole installation).
`LINE_STORES` names them, in `records_db.STORES` order.

**The table keeps the file's shape exactly**, one row per file line: `audit.<store>_lines`
(receipts: `audit.receipt_lines`), the line's JSON as `body`, its sha256, and, for a line copied
from a file, its place there (`source_line`, counted over the file's non-empty lines from 1),
unique per network, so two identical lines stay two. A line written after the move has no
`source_line`. Reads return a network's copied lines in file order, then the lines written
since, so a store's own fold (receipts' `_merged`) runs unchanged.

**Moving is a person's operation** on Settings › Installation › Connections, the Record stores
card (`MOVE_STEPS`): a preview of every network's counts, then, bound to that preview, copy (a
line already there with the same hash is skipped; one there with a DIFFERENT hash refuses,
naming the network, the line and both hashes), switch (the store's setting, recorded as the
person), copy again (a line appended in between), check, and the files made read-only for the
release that follows (P4-4), so a writer still on files fails loudly. A check that fails after
the switch switches back at once, exporting any line written to the table since, so nothing is
lost and nothing is half-moved.

**Moving back** (`BACK_STEPS`) writes the lines written to the table since the move to the end
of each network's file, then switches back: a rollback loses nothing, which is why the files
stay for a release.

**The check** (`check`), also run by the `records-check` reader each cycle while a store is on
the database: per network, the file's line count against the table's copied lines, every
line's hash, and the store's folded rows from each equal row for row. A mismatch names the
store, the network, both counts and the first differing line; Needs attention draws it.

Network = the list's folder name (`config.list_slug`), as on disk, for a store kept per
network; ``""`` for one the installation keeps. The population is every file of the store that
exists, registered list or not: a property, never the list of lists.
"""

import dataclasses
import datetime
import fcntl
import hashlib
import json
import logging
import os
import time
from typing import Callable

log = logging.getLogger(__name__)

#: The first store, and every function's default: a caller from before K31 meant it.
STORE = "receipts"
SETTING = "records_store_receipts"
#: The steps each operation declares, in order, as the manual's How it works page names them.
MOVE_STEPS = ("plan", "copy", "switch", "copy-again", "check", "read-only")
BACK_STEPS = ("plan", "export", "switch", "check")
STEP_WORDS = {"plan": "the preview's counts, read again and compared",
              "copy": "every file line copied into the table",
              "switch": "the store switched to the records database, recorded",
              "copy-again": "any line appended in between copied too",
              "check": "the file and the table compared, network by network",
              "read-only": "the files made read-only for a release",
              "export": "lines written since the move appended to the files"}


def _same(rows: list) -> list:
    return rows


def _row_id(obj: dict) -> tuple:
    return "row", str(obj.get("id") or "")


@dataclasses.dataclass(frozen=True)
class LineStore:
    """One append-only store of JSON lines, as the migration and the table see it.

    *files*: ``{network: path}`` of every file of the store that exists (its owner says where);
    *path_for*: a network's file, for the move back's export; *fold*: the store's own reading of
    its lines into rows (receipts fold each completion into its row), the same on both backends;
    *kind_id*: a line's ``(kind, id)`` columns; *per_network*: kept per network (the list's
    slug) or once for the installation (network ``""``)."""

    name: str
    words: str
    table: str
    files: Callable[[], dict]
    path_for: Callable[[str], str]
    fold: Callable[[list], list] = _same
    kind_id: Callable[[dict], tuple] = _row_id
    per_network: bool = True
    #: The words of a line folded into another, on the preview ("completions"), or "".
    second_kind: str = ""
    #: The store's rows in a sentence ("receipts are on the records database now").
    noun: str = "records"

    @property
    def setting(self) -> str:
        return f"records_store_{self.name}"

    @property
    def qualified(self) -> str:
        return f"audit.{self.table}"


def _receipts() -> LineStore:
    from modules.nsot import receipts

    def kind_id(obj):
        return (("completion", str(obj.get("completes") or "")) if "completes" in obj
                else ("row", str(obj.get("id") or "")))

    return LineStore(name="receipts", words="Deploy receipts", table="receipt_lines",
                     files=receipts.files, path_for=receipts.path_for, fold=receipts._merged,
                     kind_id=kind_id, second_kind="completions", noun="receipts")


def _acknowledgements() -> LineStore:
    """Needs attention's acknowledgements: one file for the installation (K31)."""
    from modules import acknowledgements as A

    return LineStore(name="acknowledgements", words="Acknowledgements",
                     table="acknowledgement_lines", files=A.files,
                     path_for=lambda _network: A._path(), per_network=False,
                     noun="acknowledgements")


def _restart_store(name: str, words: str, noun: str):
    """One of `restarts.py`'s three records, each one file for the installation (K31)."""
    def build() -> LineStore:
        from modules import restarts as R

        file_name = next(f for f, s in R.LINE_STORES.items() if s == name)
        return LineStore(name=name, words=words, table=f"{name.rstrip('s')}_lines",
                         files=lambda: R.files(file_name),
                         path_for=lambda _network: R._data(file_name), per_network=False,
                         noun=noun)
    return build


def _rotations() -> LineStore:
    """The rotation and save record: one file for the installation (K31)."""
    from modules.nsot import credential_rotation as cr

    return LineStore(name="rotations", words="Rotations and saves", table="rotation_lines",
                     files=cr.rotation_record_files,
                     path_for=lambda _network: cr._rotation_record_path(), per_network=False,
                     noun="rotations and saves")


def _breakglass_store(name: str, words: str, noun: str):
    """One of the four break-glass logs, each one file for the installation (K31)."""
    def build() -> LineStore:
        import os

        from modules import breakglass as bg
        from modules import config

        log_name = next(f for f, s in bg.LOG_STORES.items() if s == name)
        return LineStore(name=name, words=words, table=f"{name}_lines",
                         files=lambda: bg.log_files(config.DATA_DIR, log_name),
                         path_for=lambda _network: os.path.join(config.DATA_DIR, log_name),
                         per_network=False, noun=noun)
    return build


def _installation_store(name: str, words: str, noun: str, path: Callable[[], str]):
    """A store the installation keeps once, its file named by *path* when asked (an owner's
    path read late, so a test's patch of it holds), read and written through `store_rows`
    and `store_append` (K31)."""
    def build() -> LineStore:
        return LineStore(name=name, words=words, table=f"{name}_lines",
                         files=lambda: file_of(path()), path_for=lambda _network: path(),
                         per_network=False, noun=noun)
    return build


def _reveals_path() -> str:
    from modules import reveal_audit
    return reveal_audit._path()


def _host_steps_path() -> str:
    from modules import host_steps
    return host_steps.DONE


def _heartbeat_path() -> str:
    from modules import heartbeat_windows
    return heartbeat_windows._record_path()


def _removals_path() -> str:
    from modules import netbox_guard
    return netbox_guard._REMOVALS_FILE


#: Each line store, by name, built when asked (its owner module imports late), in
#: `records_db.STORES` order.
LINE_STORES = {"receipts": _receipts, "acknowledgements": _acknowledgements,
               "restarts": _restart_store("restarts", "Restarts seen", "restarts"),
               "restart_windows": _restart_store("restart_windows", "Planned-restart windows",
                                                 "windows"),
               "restart_window_ends": _restart_store(
                   "restart_window_ends", "Planned-restart windows ended early", "ends"),
               "rotations": _rotations,
               "breakglass_exports": _breakglass_store("breakglass_exports",
                                                       "Break-glass exports", "exports"),
               "breakglass_intact": _breakglass_store("breakglass_intact",
                                                      "Break-glass download verdicts",
                                                      "verdicts"),
               "breakglass_checks": _breakglass_store("breakglass_checks",
                                                      "Break-glass checks", "checks"),
               "breakglass_drills": _breakglass_store("breakglass_drills",
                                                      "Break-glass drills", "drills"),
               "reveals": _installation_store("reveals", "Reveals", "reveals", _reveals_path),
               "host_steps_done": _installation_store("host_steps_done", "Host steps said done",
                                                      "host steps", _host_steps_path),
               "heartbeat_rules": _installation_store("heartbeat_rules",
                                                      "Heartbeat window re-measures",
                                                      "re-measures", _heartbeat_path),
               "netbox_removals": _installation_store("netbox_removals", "NetBox removals",
                                                      "removals", _removals_path)}


def store_of(name: str = STORE):
    """The `LineStore` named *name*, or the document store (`records_docs.DocStore`); `Refused`
    naming the stores there are for another."""
    from modules import records_docs

    if records_docs.is_doc_store(name):
        return records_docs.store_of(name)
    build = LINE_STORES.get(name)
    if build is None:
        raise Refused(f"no record store {name!r}: the stores are "
                      f"{', '.join(list(LINE_STORES) + list(records_docs.DOC_STORES))}")
    return build()


def _docs(store: str):
    """The document stores' module when *store* is one of them (K31 part 3), else None."""
    from modules import records_docs

    return records_docs if records_docs.is_doc_store(store) else None


def _schema_sql(st: LineStore) -> tuple:
    return (
        "create schema if not exists audit",
        f"create table if not exists {st.qualified} ("
        " seq bigserial primary key,"
        " network text not null,"
        " kind text not null,"
        " id text not null default '',"
        " at timestamptz,"
        " body jsonb not null,"
        " line_sha256 bytea not null,"
        " source_line integer,"
        " unique (network, source_line))",
        f"create index if not exists {st.table}_network"
        f" on {st.qualified} (network, source_line, seq)",
    )


#: Copied lines in file order, then the lines written since, each network apart.
_ORDER = "order by (source_line is null), source_line, seq"


class Refused(ValueError):
    """Nothing was moved; the message names what was compared and both values."""


def _now() -> float:
    return time.time()


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch))) if epoch else ""


def network_of(list_name: str, store: str = STORE) -> str:
    """The table's `network` for *list_name*: its folder name for a store kept per network, ``""``
    for one the installation keeps."""
    from modules.config import list_slug

    return list_slug(list_name) if store_of(store).per_network else ""


def sha(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()


def _at(obj: dict):
    try:
        return datetime.datetime.strptime(obj.get("at") or "", "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def _insert(conn, st: LineStore, network: str, text: str, source_line=None) -> None:
    from psycopg.types.json import Jsonb

    obj = json.loads(text)
    kind, ident = st.kind_id(obj)
    conn.execute(f"insert into {st.qualified} (network, kind, id, at, body, line_sha256,"
                 " source_line) values (%s, %s, %s, %s, %s, %s, %s)",
                 (network, kind, ident, _at(obj), Jsonb(obj), sha(text), source_line))


def ensure_schema(conn, store: str = STORE) -> None:
    for sql in _schema_sql(store_of(store)):
        conn.execute(sql)


# ── The store's writes and reads (each store's owner module calls these) ────────────────────

def append_lines(list_name: str, texts: list, store: str = STORE, network: str = None) -> None:
    """Insert *texts* (each a line as the file would hold it) in ONE transaction: all or none.
    Raises naming why when the database cannot take them."""
    from modules import records_db

    st = store_of(store)
    network = network if network is not None else network_of(list_name, store)
    with records_db.pooled() as conn:
        for text in texts:
            _insert(conn, st, network, text)


def table_lines(list_name: str, copied_only: bool = False, conn=None,
                store: str = STORE, network: str = None) -> list:
    """A network's lines from the table, as parsed JSON, in `_ORDER`. Raises when it cannot be
    read."""
    from modules import records_db

    st = store_of(store)
    sql = (f"select body from {st.qualified} where network = %s"
           + (" and source_line is not null " if copied_only else " ") + _ORDER)
    network = (network if network is not None else
               network_of(list_name, store) if st.per_network else "")
    if conn is not None:
        return [r[0] for r in conn.execute(sql, (network,)).fetchall()]
    with records_db.pooled() as c:
        return [r[0] for r in c.execute(sql, (network,)).fetchall()]


def store_rows(store: str, path: str, skip_unparsable: bool = False, network: str = "") -> dict:
    """A line store's rows, oldest first, from its file or, once moved, the records database:
    ``{"state": "absent"|"unreadable"|"ok", "rows", "error"}``. Absent and unreadable are
    different answers, and a database that does not answer is unreadable, never no rows.
    *skip_unparsable*: a store whose reader has always skipped a line that does not parse
    keeps doing so (C1327 names the disagreement; it is not settled here). *network*: the
    list's folder name for a store kept per network, ``""`` for one the installation keeps.
    The one read of the line stores that came after part 2b's first five."""
    from modules import records_db

    if records_db.backend(store) == records_db.POSTGRES:
        try:
            return {"state": "ok", "rows": table_lines("", store=store, network=network),
                    "error": ""}
        except Exception as exc:                      # noqa: BLE001 (said, never "none")
            first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
            return {"state": "unreadable", "rows": [],
                    "error": f"the records database: {type(exc).__name__}: {first}"}
    if not os.path.exists(path):
        return {"state": "absent", "rows": [], "error": ""}
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    if not skip_unparsable:
                        raise
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": f"{type(exc).__name__}: {exc}"}
    return {"state": "ok", "rows": rows, "error": ""}


def store_append(store: str, path: str, row: dict, network: str = "") -> None:
    """Append *row* to a line store: its file, owner-only and under its cross-process lock
    (C1328), or, once moved, the records database. Raises naming why when it could not be kept:
    the caller decides whether its record failing stops it."""
    from modules import records_db

    line = json.dumps(row, sort_keys=True)
    if records_db.backend(store) == records_db.POSTGRES:
        append_lines("", [line], store=store, network=network)
        return
    from modules.config import open_secure
    from modules.filestore import PathLock

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PathLock(path):
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def file_of(path: str) -> dict:
    """``{"": path}`` when *path* exists, else ``{}``: a store kept once for the installation,
    as the migration counts its files."""
    return {"": path} if os.path.exists(path) else {}


def network_files(name: str) -> dict:
    """``{network: path}`` for every list folder holding file *name*: a store kept per network,
    as the migration counts its files (every file that exists, registered list or not: a
    property, never the list of lists)."""
    from modules.config import LISTS_DIR

    out = {}
    if os.path.isdir(LISTS_DIR):
        for folder in sorted(os.listdir(LISTS_DIR)):
            path = os.path.join(LISTS_DIR, folder, name)
            if os.path.isfile(path):
                out[folder] = path
    return out


def network_path(name: str, network: str) -> str:
    """A per-network store's file for *network* (its list folder), for the move back."""
    from modules.config import LISTS_DIR

    return os.path.join(LISTS_DIR, network, name)


def _network_store(name: str, words: str, noun: str, file_name: str):
    """A store kept one file per network, in each list's folder (K31)."""
    def build() -> LineStore:
        return LineStore(name=name, words=words, table=f"{name}_lines",
                         files=lambda: network_files(file_name),
                         path_for=lambda network: network_path(file_name, network),
                         per_network=True, noun=noun)
    return build


# The stores kept one file per network, registered here, below the helpers they need.
LINE_STORES.update({
    "network_settings_record": _network_store("network_settings_record",
                                              "Network settings changes", "changes",
                                              "settings_record.jsonl"),
    "onboarding_runs": _network_store("onboarding_runs", "Onboarding runs", "runs",
                                      "onboarding_runs.jsonl"),
    "inventory_edits": _network_store("inventory_edits", "Inventory edits", "edits",
                                      "inventory_edits.jsonl"),
})


def _interrupted_holds() -> LineStore:
    """The operations interrupted while they held a device: one kept log per list folder under
    `device_ops/`, the folder's name the network (K31)."""
    from modules import config
    from modules.nsot import device_ops as D

    return LineStore(name="interrupted_holds", words="Interrupted operations",
                     table="interrupted_hold_lines", files=D.interrupted_files,
                     path_for=lambda network: os.path.join(config.DATA_DIR, "device_ops",
                                                           network, D.INTERRUPTED_LOG),
                     per_network=True, noun="interrupted operations")


LINE_STORES["interrupted_holds"] = _interrupted_holds


def _ai_calls_path() -> str:
    from modules.ai import calls
    return calls._path()


# Phase 8's record of every AI call (modules/ai/calls.py; the operator, 2026-10-25: a records
# store with the per-store switch), one file for the installation.
LINE_STORES["ai_calls"] = _installation_store("ai_calls", "AI calls", "calls", _ai_calls_path)


def _evidence_packs_path() -> str:
    from modules import evidence_pack
    return evidence_pack._path()


# The alerts' evidence packs (PHASE8_PLAN 15.9, P1): one file for the installation, one line per
# pack, written and read through `store_append` and `store_rows` (`modules/evidence_pack.py`).
LINE_STORES["evidence_packs"] = _installation_store("evidence_packs", "Alert evidence packs",
                                                    "packs", _evidence_packs_path)


def _alert_history_path() -> str:
    from modules import alert_history
    return alert_history._path()


# Every alert's state transitions, as Grafana timed them (the operator, 2026-10-26): one file
# for the installation, one line per transition, through `store_append` and `store_rows`
# (`modules/alert_history.py`).
LINE_STORES["alert_history"] = _installation_store("alert_history", "Alert history",
                                                   "transitions", _alert_history_path)


# ── The files ────────────────────────────────────────────────────────────────────────────────

def file_networks(store: str = STORE) -> dict:
    """``{network: path}`` for every file of *store* that exists (its owner says where)."""
    return store_of(store).files()


def _file(path: str) -> list:
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [line.rstrip("\n") for line in fh if line.strip()]


def _counts(texts: list, st: LineStore = None) -> dict:
    """Lines, rows and the lines folded into them, or the first line that does not parse."""
    st = st or store_of(STORE)
    rows = folded = 0
    for n, text in enumerate(texts, 1):
        try:
            obj = json.loads(text)
        except ValueError as exc:
            return {"lines": len(texts), "unparsable": f"line {n} is not JSON ({exc})"}
        if st.kind_id(obj)[0] == "row":
            rows += 1
        else:
            folded += 1
    return {"lines": len(texts), "rows": rows, "completions": folded, "unparsable": ""}


# ── Plan, copy, check ────────────────────────────────────────────────────────────────────────

def _copied(conn, st: LineStore, network: str) -> dict:
    return {r[0]: bytes(r[1]) for r in conn.execute(
        f"select source_line, line_sha256 from {st.qualified}"
        " where network = %s and source_line is not null", (network,)).fetchall()}


def _table_exists(conn, st: LineStore) -> bool:
    return conn.execute("select to_regclass(%s) is not null", (st.qualified,)).fetchone()[0]


def plan(connector=None, store: str = STORE) -> dict:
    """What a move (or a move back) of *store* would do, writing nothing: ``{"store", "words",
    "backend", "db": {"ok", "error"}, "networks": [{"network", "lines", "rows", "completions",
    "unparsable", "copied", "since"}], "fingerprint"}``. ``copied``: the network's lines
    already in the table; ``since``: lines written there after a move. Both ``None`` when the
    database could not be asked."""
    from modules import records_db

    if _docs(store):
        return _docs(store).plan(connector, store)
    st = store_of(store)
    backend = records_db.backend(st.name)
    nets = {n: _counts(_file(p), st) for n, p in file_networks(store).items()}
    db = {"ok": False, "error": ""}
    table = {}
    try:
        with (connector or records_db.pooled)() as conn:
            if _table_exists(conn, st):
                for n, copied, since in conn.execute(
                        "select network, count(source_line), count(*) - count(source_line)"
                        f" from {st.qualified} group by network").fetchall():
                    table[n] = (copied, since)
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
    return {"store": st.name, "words": st.words, "second_kind": st.second_kind, "noun": st.noun,
            "unit": "line",
            "backend": backend, "db": db, "networks": out,
            "fingerprint": hashlib.sha256(basis.encode()).hexdigest()[:16]}


def copy(conn, store: str = STORE) -> dict:
    """Copy every file line of *store* into its table, one transaction per network.
    ``{network: {"copied", "skipped"}}``. Raises `Refused` for a line there with a different
    hash, before that network's transaction commits."""
    st = store_of(store)
    out = {}
    for network, path in file_networks(store).items():
        texts = _file(path)
        have = _copied(conn, st, network)
        copied = skipped = 0
        with conn.transaction():
            for n, text in enumerate(texts, 1):
                h = sha(text)
                if n in have:
                    if have[n] != h:
                        raise Refused(f"{network}: line {n} of the file has sha256 {h.hex()[:16]} "
                                      f"and the table holds {have[n].hex()[:16]} for it: the "
                                      f"file changed after it was copied; {network}'s copy was "
                                      "rolled back")
                    skipped += 1
                    continue
                _insert(conn, st, network, text, source_line=n)
                copied += 1
        conn.commit()
        out[network] = {"copied": copied, "skipped": skipped}
    return out


def check(connector=None, store: str = STORE) -> dict:
    """Per network, *store*'s file against its table's copied lines: counts, every hash, and the
    folded rows row for row. ``{"ok", "networks": [{"network", "file", "table", "merged":
    [file, table], "ok", "differs"}], "words"}``. Raises when the database cannot be asked."""
    from modules import records_db

    if _docs(store):
        return _docs(store).check(connector, store)
    st = store_of(store)
    results = []
    with (connector or records_db.pooled)() as conn:
        exists = _table_exists(conn, st)
        files = file_networks(store)
        nets = sorted(set(files) | set(
            r[0] for r in (conn.execute(f"select distinct network from {st.qualified}")
                           .fetchall() if exists else [])))
        for network in nets:
            texts = _file(files.get(network, ""))
            have = _copied(conn, st, network) if exists else {}
            differs = ""
            for n, text in enumerate(texts, 1):
                if n not in have:
                    differs = f"line {n} is in the file and not in the table"
                    break
                if have[n] != sha(text):
                    differs = (f"line {n} differs: file {sha(text).hex()[:16]}, table "
                               f"{have[n].hex()[:16]}")
                    break
            if not differs and len(have) > len(texts):
                differs = f"the table holds {len(have) - len(texts)} copied line(s) the file does not"
            from_file = st.fold([json.loads(t) for t in texts])
            from_table = (st.fold(_copied_lines(conn, st, network)) if exists else [])
            if not differs and from_file != from_table:
                first = next((i for i, (a, b) in enumerate(zip(from_file, from_table)) if a != b),
                             min(len(from_file), len(from_table)))
                differs = f"the merged {st.noun} differ from row {first + 1}"
            results.append({"network": network, "file": len(texts), "table": len(have),
                            "merged": [len(from_file), len(from_table)], "ok": not differs,
                            "differs": differs})
    ok = all(r["ok"] for r in results)
    words = "; ".join(f"{r['network'] or 'the installation'}: file {r['file']} lines, table "
                      f"{r['table']}, merged {r['merged'][0]} = {r['merged'][1]}" if r["ok"] else
                      f"{r['network'] or 'the installation'}: file {r['file']} lines, table "
                      f"{r['table']}: {r['differs']}"
                      for r in results) or f"no {st.noun} in any network"
    return {"ok": ok, "networks": results, "words": words}


def _copied_lines(conn, st: LineStore, network: str) -> list:
    return [r[0] for r in conn.execute(
        f"select body from {st.qualified} where network = %s and source_line is not null "
        + _ORDER, (network,)).fetchall()]


# ── The operations ───────────────────────────────────────────────────────────────────────────

class _Lock:
    """One move or move back of any store at a time, across processes."""

    def __enter__(self):
        from modules.config import DATA_DIR, open_secure

        self.fh = open_secure(os.path.join(DATA_DIR, "records_migrate.lock"), "a")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fh.close()
            raise Refused("another move of a record store is running; nothing was "
                          "changed") from None
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def _switch(to: str, actor: str, verified: str, store: str = STORE) -> dict:
    from modules import installation_settings as IS
    from modules.settings_schema import write_settings

    setting = store_of(store).setting
    out = write_settings({setting: to}, actor=actor)
    if not out.get("ok"):
        raise Refused(f"the switch to {to} was refused by the settings store: {out.get('error')}")
    return IS._record({"kind": "records_store_move" if to == "postgres" else "records_store_back",
                       "actor": actor, "actor_verified": verified, "fields": [setting]})


def _chmod(mode: int, store: str = STORE) -> list:
    done = []
    for path in file_networks(store).values():
        os.chmod(path, mode)
        done.append(path)
    return done


def _preconditions(p: dict, want_backend: str, fingerprint: str) -> None:
    if fingerprint != p["fingerprint"]:
        raise Refused(f"the preview's counts moved since it was drawn (preview {fingerprint}, "
                      f"now {p['fingerprint']}): preview again")
    if p["backend"] != want_backend:
        raise Refused(f"{p['noun']} are on {p['backend']} now, not {want_backend}")
    if not p["db"]["ok"]:
        raise Refused(f"the records database does not answer: {p['db']['error']}")
    bad = [f"{r['network']}: {r['unparsable']}" for r in p["networks"] if r.get("unparsable")]
    if bad:
        raise Refused("a file line is not JSON, so it cannot be moved: " + "; ".join(bad))


def move(fingerprint: str, actor: str, verified: str, connector=None,
         store: str = STORE) -> dict:
    """Move *store* to the records database (`MOVE_STEPS`), bound to the preview's
    *fingerprint*. ``{"ok", "steps": [{"name", "ok", "detail"}], "check", "recorded",
    "switched_back"}``. Raises `Refused` (nothing changed) before the switch; after it, a failed
    check switches back and says so."""
    from modules import records_db

    if _docs(store):
        return _docs(store).move(fingerprint, actor, verified, connector, store)
    st = store_of(store)
    steps = []

    def step(name, detail, ok=True):
        steps.append({"name": name, "ok": ok, "detail": detail})

    with _Lock():
        _preconditions(plan(connector, store), records_db.FILE, fingerprint)
        step("plan", "the counts the preview drew, read again: unchanged")
        with (connector or records_db.pooled)() as conn:
            ensure_schema(conn, store)
            conn.commit()
            got = copy(conn, store)
        step("copy", ", ".join(f"{n or 'the installation'}: {v['copied']} copied, "
                               f"{v['skipped']} already there" for n, v in got.items())
             or f"no {st.noun} file in any network")
        entry = _switch(records_db.POSTGRES, actor, verified, store)
        step("switch", f"{st.noun} now read and write the records database"
             + ("" if entry.get("recorded", True) else
                f"; its record could not be written: {entry.get('record_error')}"))
        try:
            with (connector or records_db.pooled)() as conn:
                again = copy(conn, store)
            step("copy-again", ", ".join(f"{n or 'the installation'}: {v['copied']} more"
                                         for n, v in again.items()) or "nothing more")
            result = check(connector, store)
        except Exception as exc:                      # noqa: BLE001 (after the switch: undo it)
            first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
            step("copy-again" if len(steps) == 3 else "check", first, ok=False)
            return {"ok": False, "steps": steps, "check": None,
                    "switched_back": _back(actor, verified, connector, store),
                    "recorded": entry.get("recorded", True)}
        step("check", result["words"], ok=result["ok"])
        if not result["ok"]:
            back = _back(actor, verified, connector, store)
            return {"ok": False, "steps": steps, "check": result, "switched_back": back,
                    "recorded": entry.get("recorded", True)}
        _chmod(0o400, store)
        step("read-only", f"{len(file_networks(store))} file(s) now read-only, kept for a release")
    return {"ok": True, "steps": steps, "check": result, "switched_back": None,
            "recorded": entry.get("recorded", True)}


def _back(actor: str, verified: str, connector=None, store: str = STORE) -> dict:
    """Export the lines written to *store*'s table since the move to the end of each file, then
    switch to files. The exported lines leave the table in the transaction that read them, only
    after the file holds them."""
    from modules import records_db
    from modules.config import open_secure

    st = store_of(store)
    _chmod(0o600, store)
    exported = {}
    with (connector or records_db.pooled)() as conn:
        if _table_exists(conn, st):
            for network, in conn.execute(f"select distinct network from {st.qualified}"
                                         " where source_line is null").fetchall():
                with conn.transaction():
                    got = conn.execute(f"select seq, body from {st.qualified} where network"
                                       " = %s and source_line is null order by seq",
                                       (network,)).fetchall()
                    path = st.path_for(network)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open_secure(path, "a", encoding="utf-8") as fh:
                        for _seq, body in got:
                            fh.write(json.dumps(body, sort_keys=True) + "\n")
                        fh.flush()
                        os.fsync(fh.fileno())
                    conn.execute(f"delete from {st.qualified} where network = %s and seq ="
                                 " any(%s)", (network, [s for s, _b in got]))
                exported[network] = len(got)
    entry = _switch(records_db.FILE, actor, verified, store)
    return {"exported": exported, "recorded": entry.get("recorded", True),
            "record_error": entry.get("record_error", "")}


def move_back(fingerprint: str, actor: str, verified: str, connector=None,
              store: str = STORE) -> dict:
    """Move *store* back to its files (`BACK_STEPS`), bound to the preview's *fingerprint*:
    the folded rows read the same before and after."""
    from modules import records_db

    if _docs(store):
        return _docs(store).move_back(fingerprint, actor, verified, connector, store)
    st = store_of(store)
    steps = []
    with _Lock():
        p = plan(connector, store)
        _preconditions(p, records_db.POSTGRES, fingerprint)
        steps.append({"name": "plan", "ok": True,
                      "detail": "the counts the preview drew, read again: unchanged"})
        names = list(file_networks(store)) or []
        with (connector or records_db.pooled)() as conn:
            if _table_exists(conn, st):
                names = sorted(set(names) | {r[0] for r in conn.execute(
                    f"select distinct network from {st.qualified}").fetchall()})
            before = {n: st.fold([r[0] for r in conn.execute(
                f"select body from {st.qualified} where network = %s " + _ORDER,
                (n,)).fetchall()]) for n in names}
        back = _back(actor, verified, connector, store)
        steps.append({"name": "export", "ok": True,
                      "detail": ", ".join(f"{n or 'the installation'}: {c} line(s)"
                                          for n, c in back["exported"].items())
                      or "no line was written since the move"})
        steps.append({"name": "switch", "ok": True,
                      "detail": f"{st.noun} now read and write their files again"
                      + ("" if back["recorded"] else
                         f"; its record could not be written: {back['record_error']}")})
        files = file_networks(store)
        after = {n: st.fold([json.loads(t) for t in _file(files.get(n, ""))]) for n in names}
        moved = [n for n in names if before[n] != after[n]]
        steps.append({"name": "check", "ok": not moved,
                      "detail": (f"the merged {st.noun} read the same from the files: "
                                 + ", ".join(f"{n or 'the installation'} {len(after[n])}"
                                             for n in names)
                                 if not moved else
                                 "the files read differently from the table for: "
                                 + ", ".join(moved))})
    return {"ok": not moved, "steps": steps, "recorded": back["recorded"]}


def view(cached=None) -> list:
    """The Record stores card's rows, from each store's setting and the `records-check`
    reader's stored check (never a read of the database per page view): ``[{"store", "words",
    "backend", "files", "check": {...} | None, "check_at", "check_error"}]``."""
    from modules import reader_job, records_db

    got = reader_job.read_cached("records-check") if cached is None else cached
    doc = got.get("doc") or {}
    good = (doc.get("last_good") or {})
    value = good.get("value") or {}
    attempt = doc.get("last_attempt") or {}
    # A value stored before K31 is receipts' alone, its fields at the top.
    per = value.get("stores") or ({STORE: value} if "check" in value else {})
    return [{"store": s, "words": records_db.STORE_WORDS[s], "backend": records_db.backend(s),
             "files": (per.get(s) or {}).get("files") or {},
             "check": (per.get(s) or {}).get("check"), "check_at": good.get("value_at", ""),
             "unit": "item" if _docs(s) else "line",
             "check_error": attempt.get("error", "") if attempt.get("ok") is False else ""}
            for s in records_db.STORES]
