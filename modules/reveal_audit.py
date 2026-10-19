"""modules/reveal_audit.py

An append-only record of who looked at an unredacted secret.

A masked-by-default view plus a reveal button is only half a control. The other
half is that using it leaves a mark — otherwise "masked by default" means
"masked until somebody clicks", which is a UI convenience rather than a
safeguard.

Append-only JSONL, one line per reveal, never rewritten. The file is small by
construction: it records reveals, not requests.

**What is recorded is what was looked at, never what was seen.** The device,
the ref, the actor and the time. Never the configuration, never a secret
value — an audit trail that copies the secret it is recording has become a
second place the secret lives.
"""

import logging
import os
import threading
import time

from modules.identity import UNVERIFIED as _UNVERIFIED

log = logging.getLogger(__name__)

_lock = threading.Lock()


#: The record's store on the records database (K31: one file for the installation).
STORE = "reveals"


def _path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, "reveal_audit.jsonl")


def record(*, actor: str, kind: str, what: str, target: str, detail: str = "",
           peer: str = "", extra: dict = None) -> dict:
    """Append one reveal. Returns the entry.

    Never raises: a failure to record is logged loudly, because the alternative
    — an exception here breaking the reveal — teaches somebody to route around
    the audit trail.
    """
    entry = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "actor": actor or _UNVERIFIED,
        "kind": kind or "",          # person | service
        "what": what,                # e.g. "golden_config"
        "target": target,            # e.g. "r1"
        "detail": detail,            # e.g. the ref
        "peer": peer,
    }
    if extra:
        entry.update(extra)

    recorded = False
    try:
        from modules import records_migrate

        # Its file under its cross-process lock, owner-only (C1328: a thread lock and a plain
        # open before), or the records database once moved (K31).
        with _lock:
            records_migrate.store_append(STORE, _path(), entry)
        recorded = True
    except Exception as exc:                  # noqa: BLE001
        log.error("reveal_audit: COULD NOT RECORD a reveal of %s/%s by %s (%s)",
                  what, target, entry["actor"], exc)
    log.info("reveal_audit: %s revealed %s for %s", entry["actor"], what, target)
    # `recorded` is on the RETURN, never in the file. A caller that hands a
    # secret to something no person is watching (the ZTP responder) serves
    # only when the row exists; the browser reveal keeps failing open, for
    # the reason in this function's docstring.
    return dict(entry, recorded=recorded)


def read() -> dict:
    """Every reveal, newest first: ``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``.
    A record that cannot be read is said (History draws it as an error), never an empty one."""
    from modules import records_migrate

    got = records_migrate.store_rows(STORE, _path(), skip_unparsable=True)
    if got["state"] == "unreadable":
        log.error("reveal_audit: unreadable (%s)", got["error"])
    return dict(got, rows=list(reversed(got["rows"])))


def entries(limit: int = 200) -> list:
    """The most recent reveals, newest first (none when the record cannot be read)."""
    return read()["rows"][:limit]
