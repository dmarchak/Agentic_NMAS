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

import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

_lock = threading.Lock()


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
        "actor": actor or "unauthenticated",
        "kind": kind or "",          # person | service
        "what": what,                # e.g. "golden_config"
        "target": target,            # e.g. "r1"
        "detail": detail,            # e.g. the ref
        "peer": peer,
    }
    if extra:
        entry.update(extra)

    try:
        path = _path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _lock, open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except Exception as exc:                  # noqa: BLE001
        log.error("reveal_audit: COULD NOT RECORD a reveal of %s/%s by %s (%s)",
                  what, target, entry["actor"], exc)
    log.info("reveal_audit: %s revealed %s for %s", entry["actor"], what, target)
    return entry


def entries(limit: int = 200) -> list:
    """The most recent reveals, newest first."""
    path = _path()
    if not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError as exc:
        log.error("reveal_audit: unreadable (%s)", exc)
        return []
    return list(reversed(out))[:limit]
