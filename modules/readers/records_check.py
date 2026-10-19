"""Do the moved records still match their files? A reader job (Phase 4, section 7, step 5:
"the same check as a job-health row each cycle for the release that follows").

For each record store on the records database (K31: every line store, deploy receipts the
first), each cycle runs `records_migrate.check`: per network, the file's line count against the
table's copied lines, every line's hash, and the store's merged rows from each, row for row. A
mismatch is a Needs attention row naming the store, the network, both counts and the first
differing line; a database that does not answer is a failed read (a job-health row, and Needs
attention's row saying the moved stores cannot be written). A store on its files has nothing
to compare, and the value says so with each network's line count, which the Record stores
card draws.
"""

from modules import reader_job

INTERVAL_SECONDS = 300


def read() -> dict:
    """``{"stores": {store: {"backend", "files": {network: lines}, "check": {...} | None,
    "why"}}}``, every line store (K31). Raises, naming the store, when one is on the database
    and it cannot be asked."""
    from modules import records_db
    from modules import records_migrate as RM

    out = {}
    for name in records_db.STORES:
        files = {n: len(RM._file(p)) for n, p in RM.file_networks(name).items()}
        backend = records_db.backend(name)
        if backend != records_db.POSTGRES:
            out[name] = {"backend": backend, "files": files, "check": None,
                         "why": f"{records_db.STORE_WORDS[name].lower()} are on their files: "
                                "nothing to compare"}
            continue
        try:
            out[name] = {"backend": backend, "files": files, "check": RM.check(store=name)}
        except Exception as exc:                      # noqa: BLE001 (re-raised, named)
            raise RuntimeError(f"{records_db.STORE_WORDS[name]}: {exc}") from exc
    return {"stores": out}


READER = reader_job.register(reader_job.Reader(
    name="records-check",
    what="whether the record stores moved to the records database still match their files",
    endpoints=("this host: every record store's files (deploy_receipts.jsonl first)",
               "the records database: each moved store's audit.<store>_lines"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("receipts change only when a deploy or restore finishes, minutes apart; "
                    "the check reads two small local stores, so every five minutes names a "
                    "writer still on files, or a database that stopped answering, within one "
                    "deploy's length"),
    read=read,
    invalidates=("records",),
    remedy="Read the error above: it names what the records database answered",
    window="the files and the table at the read",
))
