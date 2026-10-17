"""modules/grafana_writes.py — every write Mercury sends to Grafana, who it was for, and what
Grafana answered (C1089, the operator, 2026-10-17).

Mercury's Grafana writes are silences: set or moved by a planned-restart window
(`modules/restarts.py`), and expired (`GrafanaIntegration.expire_silence`). Each one SENT is
appended here by the integration itself, the one place they leave from, whether Grafana took
it or not: the person it was for and how they were established, the silence's id, its
matchers, its end, the outcome and Grafana's reason. A write refused before sending (a matcher
on another label, no person, no reason) sent nothing and is not a write. History's "Grafana
writes" kind reads it.

Installation-wide, as Grafana's Alertmanager is: one file in the data folder. A row names the
network whose Grafana client sent it, or none for the installation's own client.
"""

import json
import logging
import os
import threading
import time

from modules.identity import UNVERIFIED as _UNVERIFIED

log = logging.getLogger(__name__)

LOG = "grafana_writes.jsonl"
_lock = threading.Lock()

#: The writes a row may record.
ACTIONS = ("silence_set", "silence_moved", "silence_expired")


def _path() -> str:
    from modules import config
    return os.path.join(config.DATA_DIR, LOG)


def record(*, action: str, by: str, ok: bool, silence_id: str = "", matchers: list = None,
           ends_at: str = "", error: str = "", verified: str = "", via: str = "",
           comment: str = "", network: str = "") -> dict:
    """Append one write: ``{"ok", "error", "entry"}``. Never raises: the write was sent
    whether or not its record could be kept, and the caller is told which."""
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "action": action,
             "by": by or _UNVERIFIED, "verified": verified, "via": via, "ok": bool(ok),
             "silence_id": silence_id, "ends_at": ends_at, "error": error, "network": network,
             "comment": comment,
             "matchers": [f"{m.get('name')}{'=~' if m.get('isRegex') else '='}{m.get('value')}"
                          for m in matchers or []]}
    try:
        with _lock, open(_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("grafana_writes: COULD NOT RECORD %s %s by %s (%s)", action,
                  silence_id or "(no id)", entry["by"], exc)
        return {"ok": False, "error": f"{LOG} could not be written: {exc}", "entry": entry}
    return {"ok": True, "error": "", "entry": entry}


def entries() -> dict:
    """Every write, oldest first: ``{"rows", "error"}``; absent is no rows, unreadable says
    why (two different states)."""
    path = _path()
    if not os.path.exists(path):
        return {"rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"rows": [json.loads(line) for line in fh if line.strip()], "error": ""}
    except (OSError, ValueError) as exc:
        return {"rows": [], "error": f"{LOG} could not be read: {exc}"}
