"""Moving a store of Mercury's records from its files into the records database, and back
(Phase 4, docs/NSOT_PHASE4_RECORDS_POSTGRES.md section 7: deploy receipts first). The ONE owner
of the receipts table: its definition, its writes and its reads.

**The table keeps the file's shape exactly**, one row per file line: `audit.receipt_lines`,
the line's JSON as `body`, its sha256, and, for a line copied from a file, its place there
(`source_line`, counted over the file's non-empty lines from 1), unique per network, so two
identical lines stay two. A line written after the move has no `source_line`. Reads return a
network's copied lines in file order, then the lines written since, so `receipts._merged` runs
unchanged and every completion follows its row.

**Moving is a person's operation** on Settings › Installation › Connections, the Records
database card (`MOVE_STEPS`): a preview of every network's counts, then, bound to that preview,
copy (a line already there with the same hash is skipped; one there with a DIFFERENT hash
refuses, naming the network, the line and both hashes), switch (`records_store_receipts`,
recorded as the person), copy again (a line a deploy appended in between), check, and the files
made read-only for the release that follows (P4-4), so a writer still on files fails loudly. A
check that fails after the switch switches back at once, exporting any line written to the
table since, so nothing is lost and nothing is half-moved.

**Moving back** (`BACK_STEPS`) writes the lines written to the table since the move to the end
of each network's file, then switches back: a rollback loses nothing, which is why the files
stay for a release.

**The check** (`check`), also run by the `records-check` reader each cycle while the store is on
the database: per network, the file's line count against the table's copied lines, every
line's hash, and the merged receipts from each equal row for row. A mismatch names the network,
both counts and the first differing line; Needs attention draws it.

Network = the list's folder name (`config.list_slug`), as on disk. The population is every
`deploy_receipts.jsonl` that exists, registered list or not: a property, never the list of
lists.
"""

import datetime
import fcntl
import hashlib
import json
import logging
import os
import time

log = logging.getLogger(__name__)

STORE = "receipts"
SETTING = "records_store_receipts"
#: The steps each operation declares, in order, as the manual's How it works page names them.
MOVE_STEPS = ("plan", "copy", "switch", "copy-again", "check", "read-only")
BACK_STEPS = ("plan", "export", "switch", "check")
STEP_WORDS = {"plan": "the preview's counts, read again and compared",
              "copy": "every file line copied into the table",
              "switch": "receipts switched to the records database, recorded",
              "copy-again": "any line appended in between copied too",
              "check": "the file and the table compared, network by network",
              "read-only": "the files made read-only for a release",
              "export": "lines written since the move appended to the files"}

SCHEMA_SQL = (
    "create schema if not exists audit",
    "create table if not exists audit.receipt_lines ("
    " seq bigserial primary key,"
    " network text not null,"
    " kind text not null check (kind in ('row', 'completion')),"
    " id text not null default '',"
    " at timestamptz,"
    " body jsonb not null,"
    " line_sha256 bytea not null,"
    " source_line integer,"
    " unique (network, source_line))",
    "create index if not exists receipt_lines_network"
    " on audit.receipt_lines (network, source_line, seq)",
)
#: Copied lines in file order, then the lines written since, each network apart.
_ORDER = "order by (source_line is null), source_line, seq"


class Refused(ValueError):
    """Nothing was moved; the message names what was compared and both values."""


def _now() -> float:
    return time.time()


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch))) if epoch else ""


def network_of(list_name: str) -> str:
    from modules.config import list_slug

    return list_slug(list_name)


def sha(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()


def _at(obj: dict):
    try:
        return datetime.datetime.strptime(obj.get("at") or "", "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def _insert(conn, network: str, text: str, source_line=None) -> None:
    from psycopg.types.json import Jsonb

    obj = json.loads(text)
    kind, ident = (("completion", obj.get("completes") or "") if "completes" in obj
                   else ("row", obj.get("id") or ""))
    conn.execute("insert into audit.receipt_lines (network, kind, id, at, body, line_sha256,"
                 " source_line) values (%s, %s, %s, %s, %s, %s, %s)",
                 (network, kind, str(ident), _at(obj), Jsonb(obj), sha(text), source_line))


def ensure_schema(conn) -> None:
    for sql in SCHEMA_SQL:
        conn.execute(sql)


# ── The store's writes and reads (receipts.write and receipts.read call these) ───────────────

def append_lines(list_name: str, texts: list) -> None:
    """Insert *texts* (each a line as the file would hold it) in ONE transaction: all or none.
    Raises naming why when the database cannot take them."""
    from modules import records_db

    network = network_of(list_name)
    with records_db.connect() as conn:
        for text in texts:
            _insert(conn, network, text)


def table_lines(list_name: str, copied_only: bool = False, conn=None) -> list:
    """A network's lines from the table, as parsed JSON, in `_ORDER`. Raises when it cannot be
    read."""
    from modules import records_db

    sql = ("select body from audit.receipt_lines where network = %s"
           + (" and source_line is not null " if copied_only else " ") + _ORDER)
    if conn is not None:
        return [r[0] for r in conn.execute(sql, (network_of(list_name),)).fetchall()]
    with records_db.connect() as c:
        return [r[0] for r in c.execute(sql, (network_of(list_name),)).fetchall()]


# ── The files ────────────────────────────────────────────────────────────────────────────────

def file_networks() -> dict:
    """``{network: path}`` for every receipts file that exists (the receipts module owns
    where they are)."""
    from modules.nsot.receipts import files

    return files()


def _file(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [line.rstrip("\n") for line in fh if line.strip()]


def _counts(texts: list) -> dict:
    """Lines, rows and completions, or the first line that does not parse."""
    rows = completions = 0
    for n, text in enumerate(texts, 1):
        try:
            obj = json.loads(text)
        except ValueError as exc:
            return {"lines": len(texts), "unparsable": f"line {n} is not JSON ({exc})"}
        if "completes" in obj:
            completions += 1
        else:
            rows += 1
    return {"lines": len(texts), "rows": rows, "completions": completions, "unparsable": ""}


# ── Plan, copy, check ────────────────────────────────────────────────────────────────────────

def _copied(conn, network: str) -> dict:
    return {r[0]: bytes(r[1]) for r in conn.execute(
        "select source_line, line_sha256 from audit.receipt_lines"
        " where network = %s and source_line is not null", (network,)).fetchall()}


def _table_exists(conn) -> bool:
    return conn.execute("select to_regclass('audit.receipt_lines') is not null").fetchone()[0]


def plan(connector=None) -> dict:
    """What a move (or a move back) would do, writing nothing: ``{"backend", "db": {"ok",
    "error"}, "networks": [{"network", "lines", "rows", "completions", "unparsable",
    "copied", "since"}], "fingerprint"}``. ``copied``: the network's lines already in the
    table; ``since``: lines written there after a move. Both ``None`` when the database could
    not be asked."""
    from modules import records_db

    backend = records_db.backend(STORE)
    nets = {n: _counts(_file(p)) for n, p in file_networks().items()}
    db = {"ok": False, "error": ""}
    table = {}
    try:
        with (connector or records_db.connect)() as conn:
            if _table_exists(conn):
                for n, copied, since in conn.execute(
                        "select network, count(source_line), count(*) - count(source_line)"
                        " from audit.receipt_lines group by network").fetchall():
                    table[n] = (copied, since)
            db["ok"] = True
    except Exception as exc:                          # noqa: BLE001 (named on the preview)
        db["error"] = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
    out = []
    for n in sorted(set(nets) | set(table)):
        c = nets.get(n) or {"lines": 0, "rows": 0, "completions": 0, "unparsable": ""}
        copied, since = table.get(n, (0, 0)) if db["ok"] else (None, None)
        out.append(dict(c, network=n, copied=copied, since=since))
    basis = json.dumps([backend, db["ok"], [(r["network"], r["lines"], r["copied"],
                                             r["since"]) for r in out]], sort_keys=True)
    return {"backend": backend, "db": db, "networks": out,
            "fingerprint": hashlib.sha256(basis.encode()).hexdigest()[:16]}


def copy(conn) -> dict:
    """Copy every file line into the table, one transaction per network. ``{network: {"copied",
    "skipped"}}``. Raises `Refused` for a line there with a different hash, before that
    network's transaction commits."""
    out = {}
    for network, path in file_networks().items():
        texts = _file(path)
        have = _copied(conn, network)
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
                _insert(conn, network, text, source_line=n)
                copied += 1
        conn.commit()
        out[network] = {"copied": copied, "skipped": skipped}
    return out


def check(connector=None) -> dict:
    """Per network, the file against the table's copied lines: counts, every hash, and the
    merged receipts row for row. ``{"ok", "networks": [{"network", "file", "table", "merged":
    [file, table], "ok", "differs"}], "words"}``. Raises when the database cannot be asked."""
    from modules import records_db
    from modules.nsot.receipts import _merged

    results = []
    with (connector or records_db.connect)() as conn:
        exists = _table_exists(conn)
        nets = sorted(set(file_networks()) | set(
            r[0] for r in (conn.execute("select distinct network from audit.receipt_lines")
                           .fetchall() if exists else [])))
        for network in nets:
            texts = _file(file_networks().get(network, ""))
            have = _copied(conn, network) if exists else {}
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
            from_file = _merged([json.loads(t) for t in texts])
            from_table = _merged(table_lines(network, copied_only=True, conn=conn)) if exists else []
            if not differs and from_file != from_table:
                first = next((i for i, (a, b) in enumerate(zip(from_file, from_table)) if a != b),
                             min(len(from_file), len(from_table)))
                differs = f"the merged receipts differ from row {first + 1}"
            results.append({"network": network, "file": len(texts), "table": len(have),
                            "merged": [len(from_file), len(from_table)], "ok": not differs,
                            "differs": differs})
    ok = all(r["ok"] for r in results)
    words = "; ".join(f"{r['network']}: file {r['file']} lines, table {r['table']}, merged "
                      f"{r['merged'][0]} = {r['merged'][1]}" if r["ok"] else
                      f"{r['network']}: file {r['file']} lines, table {r['table']}: {r['differs']}"
                      for r in results) or "no receipts in any network"
    return {"ok": ok, "networks": results, "words": words}


# ── The operations ───────────────────────────────────────────────────────────────────────────

class _Lock:
    """One move or move back at a time, across processes."""

    def __enter__(self):
        from modules.config import DATA_DIR, open_secure

        self.fh = open_secure(os.path.join(DATA_DIR, "records_migrate.lock"), "a")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fh.close()
            raise Refused("another move of the receipts is running; nothing was changed") from None
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


def _switch(to: str, actor: str, verified: str) -> dict:
    from modules import installation_settings as IS
    from modules.settings_schema import write_settings

    out = write_settings({SETTING: to}, actor=actor)
    if not out.get("ok"):
        raise Refused(f"the switch to {to} was refused by the settings store: {out.get('error')}")
    return IS._record({"kind": "records_store_move" if to == "postgres" else "records_store_back",
                       "actor": actor, "actor_verified": verified, "fields": [SETTING]})


def _chmod(mode: int) -> list:
    done = []
    for path in file_networks().values():
        os.chmod(path, mode)
        done.append(path)
    return done


def _preconditions(p: dict, want_backend: str, fingerprint: str) -> None:
    if fingerprint != p["fingerprint"]:
        raise Refused(f"the preview's counts moved since it was drawn (preview {fingerprint}, "
                      f"now {p['fingerprint']}): preview again")
    if p["backend"] != want_backend:
        raise Refused(f"receipts are on {p['backend']} now, not {want_backend}")
    if not p["db"]["ok"]:
        raise Refused(f"the records database does not answer: {p['db']['error']}")
    bad = [f"{r['network']}: {r['unparsable']}" for r in p["networks"] if r.get("unparsable")]
    if bad:
        raise Refused("a file line is not JSON, so it cannot be moved: " + "; ".join(bad))


def move(fingerprint: str, actor: str, verified: str, connector=None) -> dict:
    """Move the receipts to the records database (`MOVE_STEPS`), bound to the preview's
    *fingerprint*. ``{"ok", "steps": [{"name", "ok", "detail"}], "check", "recorded",
    "switched_back"}``. Raises `Refused` (nothing changed) before the switch; after it, a failed
    check switches back and says so."""
    from modules import records_db

    steps = []

    def step(name, detail, ok=True):
        steps.append({"name": name, "ok": ok, "detail": detail})

    with _Lock():
        _preconditions(plan(connector), records_db.FILE, fingerprint)
        step("plan", "the counts the preview drew, read again: unchanged")
        with (connector or records_db.connect)() as conn:
            ensure_schema(conn)
            conn.commit()
            got = copy(conn)
        step("copy", ", ".join(f"{n}: {v['copied']} copied, {v['skipped']} already there"
                               for n, v in got.items()) or "no receipts file in any network")
        entry = _switch(records_db.POSTGRES, actor, verified)
        step("switch", "receipts now read and write the records database"
             + ("" if entry.get("recorded", True) else
                f"; its record could not be written: {entry.get('record_error')}"))
        try:
            with (connector or records_db.connect)() as conn:
                again = copy(conn)
            step("copy-again", ", ".join(f"{n}: {v['copied']} more" for n, v in again.items())
                 or "nothing more")
            result = check(connector)
        except Exception as exc:                      # noqa: BLE001 (after the switch: undo it)
            first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
            step("copy-again" if len(steps) == 3 else "check", first, ok=False)
            return {"ok": False, "steps": steps, "check": None,
                    "switched_back": _back(actor, verified, connector),
                    "recorded": entry.get("recorded", True)}
        step("check", result["words"], ok=result["ok"])
        if not result["ok"]:
            back = _back(actor, verified, connector)
            return {"ok": False, "steps": steps, "check": result, "switched_back": back,
                    "recorded": entry.get("recorded", True)}
        _chmod(0o400)
        step("read-only", f"{len(file_networks())} file(s) now read-only, kept for a release")
    return {"ok": True, "steps": steps, "check": result, "switched_back": None,
            "recorded": entry.get("recorded", True)}


def _back(actor: str, verified: str, connector=None) -> dict:
    """Export the lines written to the table since the move to the end of each file, then
    switch to files. The exported lines leave the table in the transaction that read them, only
    after the file holds them."""
    from modules import records_db
    from modules.config import open_secure
    from modules.nsot.receipts import encode, path_for

    _chmod(0o600)
    exported = {}
    with (connector or records_db.connect)() as conn:
        if _table_exists(conn):
            for network, in conn.execute("select distinct network from audit.receipt_lines"
                                         " where source_line is null").fetchall():
                with conn.transaction():
                    got = conn.execute("select seq, body from audit.receipt_lines where network"
                                       " = %s and source_line is null order by seq",
                                       (network,)).fetchall()
                    path = path_for(network)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open_secure(path, "a", encoding="utf-8") as fh:
                        for _seq, body in got:
                            fh.write(encode(body) + "\n")
                        fh.flush()
                        os.fsync(fh.fileno())
                    conn.execute("delete from audit.receipt_lines where network = %s and seq ="
                                 " any(%s)", (network, [s for s, _b in got]))
                exported[network] = len(got)
    entry = _switch(records_db.FILE, actor, verified)
    return {"exported": exported, "recorded": entry.get("recorded", True),
            "record_error": entry.get("record_error", "")}


def move_back(fingerprint: str, actor: str, verified: str, connector=None) -> dict:
    """Move the receipts back to their files (`BACK_STEPS`), bound to the preview's
    *fingerprint*: the merged receipts read the same before and after."""
    from modules import records_db
    from modules.nsot import receipts

    steps = []
    with _Lock():
        p = plan(connector)
        _preconditions(p, records_db.POSTGRES, fingerprint)
        steps.append({"name": "plan", "ok": True,
                      "detail": "the counts the preview drew, read again: unchanged"})
        names = list(file_networks()) or []
        with (connector or records_db.connect)() as conn:
            if _table_exists(conn):
                names = sorted(set(names) | {r[0] for r in conn.execute(
                    "select distinct network from audit.receipt_lines").fetchall()})
            before = {n: receipts._merged(table_lines(n, conn=conn)) for n in names}
        back = _back(actor, verified, connector)
        steps.append({"name": "export", "ok": True,
                      "detail": ", ".join(f"{n}: {c} line(s)" for n, c in back["exported"].items())
                      or "no line was written since the move"})
        steps.append({"name": "switch", "ok": True,
                      "detail": "receipts now read and write their files again"
                      + ("" if back["recorded"] else
                         f"; its record could not be written: {back['record_error']}")})
        after = {n: receipts._merged([json.loads(t) for t in _file(file_networks().get(n, ""))])
                 for n in names}
        moved = [n for n in names if before[n] != after[n]]
        steps.append({"name": "check", "ok": not moved,
                      "detail": ("the merged receipts read the same from the files: "
                                 + ", ".join(f"{n} {len(after[n])}" for n in names)
                                 if not moved else
                                 "the files read differently from the table for: "
                                 + ", ".join(moved))})
    return {"ok": not moved, "steps": steps, "recorded": back["recorded"]}


def view(cached=None) -> dict:
    """The Records database card's store rows, from the setting and the `records-check`
    reader's stored check (never a read of the database per page view): ``[{"store", "words",
    "backend", "check": {...} | None, "check_at", "check_error"}]``."""
    from modules import reader_job, records_db

    got = reader_job.read_cached("records-check") if cached is None else cached
    doc = got.get("doc") or {}
    good = (doc.get("last_good") or {})
    value = good.get("value") or {}
    attempt = doc.get("last_attempt") or {}
    return [{"store": s, "words": records_db.STORE_WORDS[s], "backend": records_db.backend(s),
             "files": value.get("files") or {},
             "check": value.get("check"), "check_at": good.get("value_at", ""),
             "check_error": attempt.get("error", "") if attempt.get("ok") is False else ""}
            for s in records_db.STORES]
