"""A baseline earned, and a golden committed, are events other tools can wait on (C553; Phase 3,
the operator's decision P3-2, 2026-10-08: "the marker and a path unit"; C663, the operator,
2026-10-11: "Mercury also emits a generic 'golden committed' event next to 'baseline earned'").

**Golden committed** (``<DATA_DIR>/events/golden-committed/<network>``): written on every commit
that changes a golden, naming the devices, the commit and the time. A rotation commits the new
credential into the device's golden without earning a baseline; a tool that builds what a
device boots from (credentials from its current golden) waits on this one too, so what boots
never carries a credential the device no longer has.

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
GOLDEN_EVENTS = os.path.join("events", "golden-committed")


def path(list_name: str, events: str = EVENTS) -> str:
    """The event file for *list_name*: its name, with anything outside ``[A-Za-z0-9_.-]`` as
    ``_`` (a path unit names the file literally)."""
    from modules import config
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", list_name or "") or "_"
    return os.path.join(config.DATA_DIR, events, safe)


def golden_hook(context: dict, run=None) -> dict:
    """The post-commit hook: write the golden-committed event when the commit changed a golden
    (``golden/<device>.cfg``), naming each device. Logged and returned, never blocking."""
    import subprocess

    repo, sha = context.get("repo") or "", context.get("sha") or ""
    if not repo or not sha:
        return {"ok": True, "message": "no commit to read"}
    p = (run or subprocess.run)(["git", "-C", repo, "diff-tree", "--no-commit-id", "--name-only",
                                 "-r", "--root", sha], capture_output=True, text=True, timeout=15)
    if p.returncode != 0:
        return {"ok": False, "error": f"git diff-tree {sha[:10]} exited {p.returncode}"}
    devices = sorted(os.path.basename(x)[:-4] for x in p.stdout.split()
                     if x.startswith("golden/") and x.endswith(".cfg"))
    if not devices:
        return {"ok": True, "message": "no golden changed"}
    list_name = context.get("list_name") or ""
    target = path(list_name, GOLDEN_EVENTS)
    body = json.dumps({"list": list_name, "commit": sha, "devices": devices,
                       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                      sort_keys=True) + "\n"
    try:
        from modules.filestore import write_atomic
        os.makedirs(os.path.dirname(target), exist_ok=True)
        write_atomic(target, body)
    except OSError as exc:
        log.error("golden event: %s committed %s, and %s could not be written: %s",
                  list_name, ", ".join(devices), target, exc)
        return {"ok": False, "error": f"{target} could not be written: {exc}"}
    log.info("golden event: %s committed %s (%s)", list_name, ", ".join(devices), target)
    return {"ok": True, "message": f"{len(devices)} golden(s) written to {target}"}


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
