"""modules/nsot/freshness.py — the freshness gate's past authorisations, read back.

Until Phase 3 (docs/NSOT_PHASE3_RETIRE_OXIDIZED.md), this module compared Oxidized's copy
of each device against its golden, and a person could authorise one divergence past the
gate, recorded per list in ``freshness_authorisations.json`` with who, why and when it
expired. Oxidized is retired: the comparison, the gate and the writer are gone, and the
drift checker (``modules/drift_check.py``) asks the device itself against its golden.

**What stays is the record.** An authorisation once given is history, and History reads it
(``history_sources.freshness`` and the History page's authorisations tab). Nothing writes
the file now; this module only reads it, and a list that never had one reads as none.
"""

import json
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)

AUTHORISATION_FILE = "freshness_authorisations.json"


def parse_time(value):
    """A timestamp as an aware ``datetime``, or ``None``.

    ``None`` is a real answer and the caller must treat it as one: an unparseable time is a
    different fact from an expired one. A naive timestamp is read as UTC.
    """
    text = (value or "").strip()
    if not text:
        return None
    # `UTC`/`GMT` as a trailing word: strptime's %Z parses it and returns a
    # NAIVE datetime, which is the one outcome that must not look aware.
    for suffix in (" UTC", " GMT", " utc"):
        if text.endswith(suffix):
            text = text[: -len(suffix)] + "+0000"
            break
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                    "%a %b %d %H:%M:%S %Y %z", "%a %b %d %H:%M:%S %Y"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _authorisation_path(list_name: str) -> str:
    """Where a list's authorisations live — **resolved, never created**.

    Deliberately not `get_list_data_dir()`, which calls `os.makedirs()`: a read must not
    bring a list into existence merely by asking. `LISTS_DIR` is read at call time, which
    is also what lets a test point it somewhere else.
    """
    from modules import config as _config

    return os.path.join(_config.LISTS_DIR, _config.list_slug(list_name),
                        AUTHORISATION_FILE)


def _load_authorisations(list_name: str) -> list:
    try:
        with open(_authorisation_path(list_name), encoding="utf-8") as fh:
            records = json.load(fh)
    except (OSError, ValueError):
        return []
    return records if isinstance(records, list) else []


def authorisations(list_name: str, include_expired: bool = False) -> list:
    """Every recorded authorisation, newest last."""
    now = datetime.now(timezone.utc)
    rows = []
    for record in _load_authorisations(list_name):
        expires = parse_time(record.get("expires_at"))
        record = dict(record)
        record["expired"] = bool(expires and expires <= now)
        if record["expired"] and not include_expired:
            continue
        rows.append(record)
    return rows
