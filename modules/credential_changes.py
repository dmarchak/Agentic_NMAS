"""modules/credential_changes.py — who changed a credential profile, when, and which of its
fields (Source of truth › Credentials › Profiles on v2, 2026-10-10).

`credentials.save_profile` and `delete_profile` kept no record of who or when (register
operation_stages.HISTORY said MISSING for both). Each change from the Profiles tab is appended
here, naming the profile and the FIELDS it set, never a value: a password changed is recorded
as "password", nothing more. History's Credential profiles source reads it.

Installation-wide, as the profiles are: one file beside `credential_profiles.json`.
"""

import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

LOG = "credential_changes.jsonl"
_lock = threading.Lock()

#: The fields a change may name, in the order a row lists them.
FIELDS = ("username", "password", "secret")


def _path() -> str:
    from modules import config
    return os.path.join(config.DATA_DIR, LOG)


def record(*, action: str, profile: str, fields: list, actor: str, verified: str = "") -> dict:
    """Append one change: ``{"ok", "error", "entry"}``. Never raises: the change was made
    whether or not its record could be written, and the caller says which."""
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "action": action,
             "profile": profile, "fields": [f for f in FIELDS if f in (fields or [])],
             "actor": actor or "unauthenticated", "verified": verified}
    try:
        with _lock, open(_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("credential_changes: COULD NOT RECORD %s of profile %r by %s (%s)",
                  action, profile, entry["actor"], exc)
        return {"ok": False, "error": f"{LOG} could not be written: {exc}", "entry": entry}
    log.info("credential_changes: %s %s profile %r (%s)", entry["actor"], action, profile,
             ", ".join(entry["fields"]) or "no field")
    return {"ok": True, "error": "", "entry": entry}


def entries() -> dict:
    """Every change, oldest first: ``{"rows", "error"}``; absent is no rows, unreadable says
    why (two different states)."""
    path = _path()
    if not os.path.exists(path):
        return {"rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"rows": [json.loads(l) for l in fh if l.strip()], "error": ""}
    except (OSError, ValueError) as exc:
        return {"rows": [], "error": f"{LOG} could not be read: {exc}"}
