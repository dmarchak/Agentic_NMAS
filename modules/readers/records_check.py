"""Do the moved records still match their files? A reader job (Phase 4, section 7, step 5:
"the same check as a job-health row each cycle for the release that follows").

While deploy receipts are on the records database, each cycle runs `records_migrate.check`:
per network, the file's line count against the table's copied lines, every line's hash, and
the merged receipts from each, row for row. A mismatch is a Needs attention row naming the
network, both counts and the first differing line; a database that does not answer is a
failed read (a job-health row, and Needs attention's row saying receipts cannot be written).
While they are on their files there is nothing to compare, and the value says so with each
network's line count, which the Records database card draws.
"""

from modules import reader_job

INTERVAL_SECONDS = 300


def read() -> dict:
    """``{"backend", "files": {network: lines}, "check": {...} | None, "why"}``. Raises when
    the store is on the database and it cannot be asked."""
    from modules import records_db
    from modules import records_migrate as RM

    files = {n: len(RM._file(p)) for n, p in RM.file_networks().items()}
    backend = records_db.backend(RM.STORE)
    if backend != records_db.POSTGRES:
        return {"backend": backend, "files": files, "check": None,
                "why": "deploy receipts are on their files: nothing to compare"}
    return {"backend": backend, "files": files, "check": RM.check()}


READER = reader_job.register(reader_job.Reader(
    name="records-check",
    what="whether deploy receipts moved to the records database still match their files",
    endpoints=("this host: every network's deploy_receipts.jsonl",
               "the records database: audit.receipt_lines"),
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
