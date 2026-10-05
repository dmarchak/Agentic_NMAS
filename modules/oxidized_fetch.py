"""Ask Oxidized to fetch a device as soon as its configuration changed (C314).

The operator, 2026-10-01: after a change the tool waited for other systems'
schedules instead of nudging them. Oxidized polls hourly, the clab sync writes
the lab's startup files from Oxidized's copy, so for up to an hour after a
deploy the lab startup check read "the file is not what its golden would
produce" and suggested a capture, for a device that was exactly as recorded.

Every operation that changes a device's configuration and keeps the tool's
record commits a golden (deploy, Mode B, restore, profile and IP SLA applies,
adopt, onboarding, rotation), so ONE post-commit hook reaches them all: each
device whose golden the commit changed is asked for with Oxidized's own
``GET /node/next/<node>``, which moves it to the head of the fetch queue, and
the request is recorded per list (``oxidized_fetch_requests.json``, the newest
per device). A capture that changed a golden asks too: the device moved
before it, and Oxidized's copy is just as old.

**Since plan item 4 (the same night) the lab's startup files are built from
the newest earned baseline, not from Oxidized**, so the lab startup row no
longer waits on Oxidized and its "Oxidized hasn't fetched" wording is gone.
The fetch still serves what reads Oxidized's copy: the freshness signal on
Needs attention and the clab sync's cross-check (what each device runs now).

It asks; it never waits. Whether the fetch happened is Oxidized's own record
(``nodes.json``), read where it is needed. A rotation's persist chain still
confirms its own fetch, because it must not continue without one.
"""

import json
import logging
import os
import subprocess
import time

log = logging.getLogger(__name__)

RECORD_NAME = "oxidized_fetch_requests.json"


def _record_path(list_name: str) -> str:
    from modules.nsot import listref
    return os.path.join(listref.resolve(list_name).data_dir, RECORD_NAME)


def node_for(hostname: str, mgmt_ip: str) -> str:
    """The name Oxidized keeps *hostname* under: ``oxidized_node_identity``
    decides (the clab sync's map reads the same setting). The Default network's: one
    router.db names every list's devices until P.7."""
    from modules.list_settings import default_layer

    by_name = default_layer("oxidized_node_identity", "hostname") == "hostname"
    return hostname if by_name else (mgmt_ip or "")


def requests_for(list_name: str) -> dict:
    """``{hostname: {at, node, why, ok, error}}``, the newest request per
    device; absent is ``{}``; unreadable raises (it is not "none asked")."""
    path = _record_path(list_name)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def request(list_name: str, devices, why: str, client=None, clock=time.time) -> dict:
    """Ask Oxidized to fetch each of *devices* (``[(hostname, mgmt_ip)]``) now.

    ``{"ok", "asked": [...], "failed": [{device, error}], "skipped": [...]}``.
    Not configured asks nothing and records nothing, and says so."""
    from modules.filestore import PathLock, read_json_for_write, write_atomic

    if client is None:
        from modules.integrations.oxidized import OxidizedIntegration
        client = OxidizedIntegration(timeout=10)
    if not client.is_configured():
        return {"ok": True, "asked": [], "failed": [], "skipped": [],
                "message": "Oxidized is not configured (oxidized_url): nothing was asked"}
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock()))
    rows, asked, failed, skipped = {}, [], [], []
    for host, ip in devices:
        node = node_for(host, ip)
        if not node:
            skipped.append(host)
            rows[host] = {"at": at, "node": "", "why": why, "ok": False,
                          "error": "no management address to name its Oxidized node by"}
            continue
        got = client._get(f"node/next/{node}")              # noqa: SLF001 - the client's API
        rows[host] = {"at": at, "node": node, "why": why, "ok": bool(got.get("ok")),
                      "error": "" if got.get("ok") else (got.get("error") or "no answer")}
        (asked if got.get("ok") else failed).append(
            host if got.get("ok") else {"device": host, "error": rows[host]["error"]})
    path = _record_path(list_name)
    try:
        with PathLock(path):
            stored = read_json_for_write(path)
            stored.update(rows)
            write_atomic(path, json.dumps(stored, indent=1, sort_keys=True) + "\n")
    except Exception as exc:                                 # noqa: BLE001
        log.error("oxidized fetch: the request record for %s could not be written: %s",
                  list_name, exc)
    for f in failed:
        log.warning("oxidized fetch: %s could not be asked for: %s", f["device"], f["error"])
    if asked:
        log.info("oxidized fetch: asked for %s (%s)", ", ".join(asked), why)
    return {"ok": not failed, "asked": asked, "failed": failed, "skipped": skipped}


def golden_hook(context: dict, run=None, ask=None) -> dict:
    """The post-commit sender: each device whose golden the commit changed is
    asked for. The devices' addresses come from the list's manifest."""
    from modules.nsot import manifest

    repo, sha = context.get("repo") or "", context.get("sha") or ""
    list_name = context.get("list_name") or ""
    if not repo or not sha or not list_name:
        return {"ok": True, "message": "no commit to read"}
    p = (run or subprocess.run)(["git", "-C", repo, "diff-tree", "--no-commit-id", "--name-only",
                                 "-r", "--root", sha], capture_output=True, text=True, timeout=15)
    if p.returncode != 0:
        return {"ok": False, "error": f"git diff-tree {sha[:10]} exited {p.returncode}"}
    hosts = [os.path.basename(x)[:-4] for x in p.stdout.split()
             if x.startswith("golden/") and x.endswith(".cfg")]
    if not hosts:
        return {"ok": True, "message": "no golden changed"}
    devices = []
    for h in hosts:
        _ident, entry = manifest.find_by_name(repo, h)
        devices.append((h, (entry or {}).get("mgmt_ip") or ""))
    why = f"commit {sha[:10]} ({context.get('source') or 'a commit'}) changed its golden"
    got = (ask or request)(list_name, devices, why)
    if got.get("message"):
        return {"ok": True, "message": got["message"]}
    if got.get("failed"):
        return {"ok": False, "error": "; ".join(f"{f['device']}: {f['error']}"
                                                for f in got["failed"])}
    return {"ok": True, "message": f"asked Oxidized to fetch {', '.join(got['asked'])}"}
