"""NetBox import and removal as jobs for v2's NetBox page (cutover blocker 2, 2026-10-10). A
preview runs the real dry run (`netbox_ops.dry_run`, about a minute on the lab, measured
2026-09-28) on a thread, so no request waits on it; an import runs on the import's own thread.
Each job's answer is stored under its id in ``DATA_DIR/netbox_jobs/<id>.json`` (several worker
processes are assumed, so never in memory), and announced on the ``netbox`` key when it lands, so
the page's card redraws from the store: no polling.

A preview's answer is the preview component's own dict (`preview_confirm.netbox_import_preview`,
`netbox_removal_preview`), MASKED (`outbound.mask_payload`) after the token is bound to the
truthful plan, with the token beside it: a capability this server issued for the confirm to hand
back, never a stored secret. A removal runs in its request (it deletes only what Mercury created
and recorded), and its result is the recorded removal's own.
"""

import json
import logging
import os
import threading
import time
import uuid

log = logging.getLogger(__name__)

STATES = ("previewing", "previewed", "refused", "importing", "imported", "failed")


def _dir() -> str:
    from modules.config import DATA_DIR

    return os.path.join(DATA_DIR, "netbox_jobs")


def _path(job_id: str) -> str:
    return os.path.join(_dir(), f"{job_id}.json")


def valid(job_id: str) -> bool:
    from modules import op_progress

    return op_progress.valid_id(job_id)


def _write(job_id: str, doc: dict) -> None:
    from modules.filestore import write_atomic

    doc = dict(doc, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    write_atomic(_path(job_id), json.dumps(doc, sort_keys=True))


def read(job_id: str) -> dict:
    """The job's stored answer, or ``{"state": "unknown"}`` (never started here, or gone)."""
    if not valid(job_id) or not os.path.exists(_path(job_id)):
        return {"state": "unknown", "id": job_id}
    try:
        with open(_path(job_id), encoding="utf-8") as fh:
            return dict(json.load(fh), id=job_id)
    except (OSError, ValueError) as exc:
        return {"state": "unknown", "id": job_id, "error": f"its record cannot be read: {exc}"}


def _announce() -> None:
    from modules import invalidation

    try:
        invalidation.announce(["netbox"], "netbox-job")
    except Exception:                                 # noqa: BLE001 (counted by announce)
        log.debug("netbox_jobs: the announcement could not be sent", exc_info=True)


def new_id() -> str:
    return uuid.uuid4().hex


def start_preview(operation: str, list_name: str, actor: str, confirm: dict) -> str:
    """Start a preview job; its id. *confirm* is who would confirm, read in the request."""
    from modules import netbox_ops, op_progress
    from modules.outbound import mask_payload
    from modules.preview_confirm import netbox_import_preview, netbox_removal_preview

    job_id = new_id()
    label = "every network" if operation == "import_all" else list_name
    op_progress.start(job_id, "previewed for " + ("removal" if operation == "remove" else
                                                  "import"), f"NetBox ({label})", actor=actor)
    _write(job_id, {"state": "previewing", "operation": operation, "list": list_name,
                    "actor": actor})

    def _run():
        try:
            d = netbox_ops.dry_run(operation, list_name, actor, progress_id=job_id)
            if operation == "remove":
                pv = netbox_removal_preview(d, confirm)
            else:
                pv = mask_payload(netbox_import_preview(d, confirm,
                                                        all_lists=operation == "import_all"))
            _write(job_id, {"state": "previewed", "operation": operation, "list": list_name,
                            "actor": actor, "preview": pv, "token": d.get("token", ""),
                            "writes_allowed": bool(d.get("writes_allowed")),
                            "device_count": d.get("device_count")})
        except netbox_ops.Refused as exc:
            _write(job_id, {"state": "refused", "operation": operation, "list": list_name,
                            "actor": actor, "error": exc.payload.get("error", "")})
        except Exception as exc:                      # noqa: BLE001 (said on the card)
            log.exception("netbox_jobs: preview %s failed", job_id)
            _write(job_id, {"state": "refused", "operation": operation, "list": list_name,
                            "actor": actor, "error": f"the preview failed: {exc}"})
        finally:
            op_progress.finish(job_id)
            _announce()
    threading.Thread(target=_run, daemon=True, name=f"netbox-preview-{job_id[:8]}").start()
    return job_id


def start_import(job_id: str, data: dict, actor: str) -> dict:
    """Confirm the previewed import *job_id* and start it; its stored state. Raises
    `netbox_ops.Refused`."""
    from modules import netbox_ops, op_progress

    job = read(job_id)
    if job.get("state") != "previewed" or job.get("operation") not in ("import", "import_all"):
        raise netbox_ops.Refused({"ok": False, "error": "that preview is not one ready to "
                                  "confirm: preview again"}, 409)
    operation, list_name = job["operation"], job["list"]
    op_progress.start(job_id, "re-checked, then imported",
                      f"NetBox ({'every network' if operation == 'import_all' else list_name})",
                      actor=actor)

    def on_end(outcome):
        from modules.netbox_client import sync_status_with_results

        status = sync_status_with_results()
        lists = status.get("lists") or {}
        names = ([n for n in lists] if operation == "import_all" else [list_name])
        results = {n: (lists.get(n) or {}).get("result") for n in names if lists.get(n)}
        _write(job_id, dict(job, state="imported" if outcome == "done" else "failed",
                            outcome=outcome, results=results, token=""))
        _announce()

    payload = dict(data, token=job.get("token", ""))
    # "importing" is written BEFORE the thread starts: one that ended first would otherwise be
    # overwritten, and the card would say "importing" for ever. A refusal puts the preview back.
    _write(job_id, dict(job, state="importing", token=""))
    try:
        netbox_ops.start_import(operation, list_name if operation == "import" else
                                netbox_ops.ALL_LISTS, payload, actor, progress_id=job_id,
                                where="v2's NetBox page", on_end=on_end)
    except netbox_ops.Refused:
        _write(job_id, job)
        raise
    return read(job_id)


def remove(job_id: str, data: dict, actor: str) -> dict:
    """Confirm the previewed removal *job_id* and run it; ``{"result", "row"}`` as recorded.
    Raises `netbox_ops.Refused`."""
    from modules import netbox_guard, netbox_ops
    from modules.preview_confirm import netbox_removal_result

    job = read(job_id)
    if job.get("state") != "previewed" or job.get("operation") != "remove":
        raise netbox_ops.Refused({"ok": False, "error": "that preview is not one ready to "
                                  "confirm: preview again"}, 409)
    result = netbox_ops.remove(job["list"], dict(data, token=job.get("token", "")), actor,
                               where="v2's NetBox page")
    status = netbox_guard.record_removal(job["list"], actor, result)
    drawn = netbox_removal_result(status["row"], status)
    _write(job_id, dict(job, state="imported" if result.get("ok") else "failed", token="",
                        removal=drawn))
    _announce()
    return read(job_id)
