"""A baseline earned is an event other tools can wait on (C553; Phase 3, the operator's decision
P3-2, 2026-10-08: "the marker and a path unit").

When a commit earns a network's baseline (`baseline/<ts>`, a measurement: every device at its
committed intent), the post-commit hook writes one small file,
``<DATA_DIR>/events/baseline-earned/<network>``, holding the tag, the commit and the time,
replaced atomically. That is all the product does: it names no tool that might care. A host
service that should act on a new baseline watches the file (a systemd path unit), the
updater's pattern (`deploy/systemd/nmas-update.path` watches the app's request directory).

A watcher that used to poll on a timer (C553: a job that builds boot files from the newest
baseline waited up to 30 minutes after a Save All earned one) now starts when the file moves.

**Never a lost event, never a false one.** The file is written only when the commit's tags hold
a baseline, and a failure to write it is logged and returned (the hook's result, which the
post-commit runner records); it never blocks or undoes the commit. A watcher that misses a write
still has its timer.
"""

import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

#: Under the installation's data directory.
EVENTS = os.path.join("events", "baseline-earned")


def path(list_name: str) -> str:
    """The event file for *list_name*: its name, with anything outside ``[A-Za-z0-9_.-]`` as
    ``_`` (a path unit names the file literally)."""
    from modules import config
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", list_name or "") or "_"
    return os.path.join(config.DATA_DIR, EVENTS, safe)


def hook(context: dict) -> dict:
    """The post-commit hook: write the event when the commit's tags hold a baseline."""
    tags = context.get("tags") or []
    baseline = next((t for t in tags if t.startswith("baseline/")), "")
    if not baseline:
        return {"ok": True, "message": "no baseline earned"}
    list_name = context.get("list_name") or ""
    target = path(list_name)
    body = json.dumps({"list": list_name, "tag": baseline, "commit": context.get("sha", ""),
                       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                      sort_keys=True) + "\n"
    try:
        from modules.filestore import write_atomic
        os.makedirs(os.path.dirname(target), exist_ok=True)
        write_atomic(target, body)
    except OSError as exc:
        log.error("baseline event: %s earned %s, and %s could not be written: %s",
                  list_name, baseline, target, exc)
        return {"ok": False, "error": f"{target} could not be written: {exc}"}
    log.info("baseline event: %s earned %s (%s)", list_name, baseline, target)
    return {"ok": True, "message": f"{baseline} written to {target}"}
