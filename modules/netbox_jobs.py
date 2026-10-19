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
and recorded), and its result is the recorded removal's own. So does Stop tracking (`forget`,
C954), the Remove card's second choice: previewed from Mercury's created record alone, confirmed
by its hash, deleting nothing in NetBox, recorded as a forget-only removal.

An import's job record is also its record for History (B8, `history`): who confirmed it
(``actor``, with ``previewed_by`` beside it), when it started and ended, and its result; a removal's and a Stop
tracking's is the removal record (`netbox_guard.record_removal`).
"""

import json
import logging
import os
import threading
import time
import uuid

log = logging.getLogger(__name__)

STATES = ("previewing", "previewed", "refused", "importing", "imported", "failed")

#: The Remove card's second choice (C954): its words, as the card draws them and the removal
#: preview names them.
FORGET_CONTROL = "Stop tracking instead…"

#: The phases `netbox_client` reports through `op_progress` while it reads and plans or writes,
#: in order: (its phase words, the step's key, the step's words). THE stepper's steps (the one
#: stepper, 2026-10-12).
PHASES = (("setting up the region, site and template", "setup", "Region, site and template"),
          ("reading and planning each device", "devices", "Each device"),
          ("cables between devices", "cables", "Cables between devices"))


def run_card(job: dict, progress) -> dict:
    """A previewing or importing job on THE stepper (`run_stepper.at_step`): its declared steps,
    the one it is on from *progress* (`op_progress.get`; None after a restart, which starts it
    at the first), with that step's counts as its note. None in any other state.

    An import's confirm re-checks the plan in its request, so the card it draws starts there,
    done; the write then runs the same phases again, from when it says so (`writing`)."""
    from modules import run_stepper as RS

    state, op, p = job.get("state"), job.get("operation") or "", progress or {}
    if state not in ("previewing", "importing"):
        return None
    name = "every network" if op == "import_all" else (job.get("list") or "NetBox")
    at = next((i for i, (ph, _k, _w) in enumerate(PHASES) if ph == p.get("phase")), 0)
    if op == "remove":
        # The removal's dry run reads what Mercury created and recorded; it names no phase.
        steps, current = (("read", "What it created, read"), ("preview", "The preview")), 0
    elif op == "forget":
        # Stop tracking reads Mercury's created record alone (C954); it names no phase.
        steps, current = (("read", "Mercury's record, read"), ("preview", "The preview")), 0
    elif state == "previewing":
        steps = tuple((k, w + (" read and planned" if k == "devices" else ""))
                      for _ph, k, w in PHASES) + (("preview", "The preview"),)
        current = at
    else:
        steps = (("recheck", "The plan re-checked"),) + tuple(
            (k, w + (" written" if k == "devices" else "")) for _ph, k, w in PHASES)
        current = 1 + at if p.get("writing") else 1
    note = p.get("step_words", "") if p else "this server process holds no progress for it"
    return RS.at_step(name, "NetBox progress", steps, current, elapsed_s=(
        round(p["elapsed_s"]) if p.get("elapsed_s") is not None else None), note=note,
        device=False)


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


#: The import jobs History draws (B8): confirmed, so started, running or ended. A preview, a
#: refusal and a removal or Stop tracking are not imports (the removal record holds those two).
IMPORT_OPERATIONS = ("import", "import_all")
IMPORT_STATES = ("importing", "imported", "failed")


def history(list_name: str) -> dict:
    """Every confirmed import that wrote, or tried to write, *list_name* into NetBox, read from
    the jobs' own records (B8): ``{"rows": [...newest first], "error"}``. An import of every
    network is *list_name*'s when its results name it. One read of the store per call, whatever
    the number of devices; a record that cannot be read is counted in *error*, never skipped
    as if absent. No store yet is no import yet, which is not an error."""
    folder = _dir()
    if not os.path.isdir(folder):
        return {"rows": [], "error": ""}
    rows, bad = [], []
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(".json"))
    except OSError as exc:
        return {"rows": [], "error": f"the NetBox job records could not be listed: {exc}"}
    for name in names:
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError) as exc:
            bad.append(f"{name}: {exc}")
            continue
        if doc.get("operation") not in IMPORT_OPERATIONS or doc.get("state") not in IMPORT_STATES:
            continue
        mine = (list_name in (doc.get("results") or {}) if doc["operation"] == "import_all"
                else doc.get("list") == list_name)
        if mine:
            rows.append(dict(doc, id=name[:-len(".json")]))
    rows.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
    return {"rows": rows, "error": (f"{len(bad)} NetBox job record(s) could not be read "
                                    f"({bad[0]})" if bad else "")}


def start_preview(operation: str, list_name: str, actor: str, confirm: dict,
                  device: str = "") -> str:
    """Start a preview job; its id. *confirm* is who would confirm, read in the request.
    *device* scopes an import to one device of the list (C1344); the job keeps it, so its
    confirm recomputes the same plan."""
    from modules import netbox_ops, op_progress
    from modules.outbound import mask_payload
    from modules.preview_confirm import (netbox_forget_preview, netbox_import_preview,
                                         netbox_removal_preview)

    job_id = new_id()
    device = device if operation == "import" else ""
    label = "every network" if operation == "import_all" else (
        f"{device} in {list_name}" if device else list_name)
    op_progress.start(job_id, "previewed for " + {"remove": "removal",
                                                  "forget": "stopping tracking"}.get(
                                                      operation, "import"),
                      f"NetBox ({label})", actor=actor)
    op_progress.on_phase(job_id, _announce)           # THE stepper redraws as the phase moves
    scope = {"device": device} if device else {}
    _write(job_id, {"state": "previewing", "operation": operation, "list": list_name,
                    "actor": actor, **scope})

    def _run():
        try:
            d = netbox_ops.dry_run(operation, list_name, actor, progress_id=job_id,
                                   device=device)
            if operation == "remove":
                # v2's Remove card offers Stop tracking beside it (C954).
                pv = netbox_removal_preview(d, confirm, forget_offered=FORGET_CONTROL)
            elif operation == "forget":
                pv = netbox_forget_preview(d, confirm)
            else:
                pv = mask_payload(netbox_import_preview(d, confirm,
                                                        all_lists=operation == "import_all"))
            _write(job_id, {"state": "previewed", "operation": operation, "list": list_name,
                            **scope, "actor": actor, "preview": pv, "token": d.get("token", ""),
                            "writes_allowed": bool(d.get("writes_allowed")),
                            "device_count": d.get("device_count")})
        except netbox_ops.Refused as exc:
            _write(job_id, {"state": "refused", "operation": operation, "list": list_name,
                            **scope, "actor": actor, "error": exc.payload.get("error", "")})
        except Exception as exc:                      # noqa: BLE001 (said on the card)
            log.exception("netbox_jobs: preview %s failed", job_id)
            _write(job_id, {"state": "refused", "operation": operation, "list": list_name,
                            **scope, "actor": actor, "error": f"the preview failed: {exc}"})
        finally:
            op_progress.finish(job_id)
            _announce()
    threading.Thread(target=_run, daemon=True, name=f"netbox-preview-{job_id[:8]}").start()
    return job_id


def _confirmed(job: dict, actor: str) -> dict:
    """The job's record from its confirm on: ``actor`` is who CONFIRMED (the gate verified
    them), the preview's kept as ``previewed_by``. B2 (W2, 2026-10-16): the confirm carried
    the preview's record forward whole, so all 8 job records of the sitting, the import
    d0d4031f77 among them, named the preview's actor ("unauthenticated") though every write
    the import made named the person."""
    return dict(job, actor=actor, previewed_by=job.get("actor", ""))


def start_import(job_id: str, data: dict, actor: str) -> dict:
    """Confirm the previewed import *job_id* and start it; its stored state. Raises
    `netbox_ops.Refused`."""
    from modules import netbox_ops, op_progress

    previewed = read(job_id)
    if previewed.get("state") != "previewed" or previewed.get("operation") not in (
            "import", "import_all"):
        raise netbox_ops.Refused({"ok": False, "error": "that preview is not one ready to "
                                  "confirm: preview again"}, 409)
    # Who confirmed it (B2's `_confirmed`: `actor` the confirmer, `previewed_by` the preview's
    # caller) and when it started (B8): the record History draws (`history`).
    job = dict(_confirmed(previewed, actor),
               started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    operation, list_name = job["operation"], job["list"]
    op_progress.start(job_id, "re-checked, then imported",
                      f"NetBox ({'every network' if operation == 'import_all' else list_name})",
                      actor=actor)
    op_progress.on_phase(job_id, _announce)

    def on_end(outcome):
        from modules.netbox_client import sync_status_with_results

        status = sync_status_with_results()
        lists = status.get("lists") or {}
        names = ([n for n in lists] if operation == "import_all" else [list_name])
        results = {n: (lists.get(n) or {}).get("result") for n in names if lists.get(n)}
        _write(job_id, dict(job, state="imported" if outcome == "done" else "failed",
                            outcome=outcome, results=results, token=""))
        # Its `netbox` announcement wakes the NetBox-behind-the-golden reader (reader_wakes,
        # C1344), so a device's "NetBox holds less" row clears when its import lands.
        _announce()

    payload = dict(data, token=job.get("token", ""))
    # "importing" is written BEFORE the thread starts: one that ended first would otherwise be
    # overwritten, and the card would say "importing" for ever. A refusal puts the preview back.
    _write(job_id, dict(job, state="importing", token=""))
    try:
        netbox_ops.start_import(operation, list_name if operation == "import" else
                                netbox_ops.ALL_LISTS, payload, actor, progress_id=job_id,
                                where="v2's NetBox page", on_end=on_end,
                                device=job.get("device") or "")
    except netbox_ops.Refused:
        _write(job_id, previewed)                    # the preview back, as it was
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
    # A preview whose target cannot be selected (B9, C932: an object not read, what the deletes
    # take with them not established, nothing to delete) is refused here too, not only by the
    # card not drawing Remove: a confirm posted without the card must not run it.
    blocked = [t for t in (((job.get("preview") or {}).get("what") or {}).get("targets") or [])
               if not t.get("selectable")]
    if blocked:
        raise netbox_ops.Refused({"ok": False, "error": (
            "that preview cannot be confirmed: " + (blocked[0].get("why_not") or "it says why")
            + ". Nothing was deleted; read again")}, 409)
    result = netbox_ops.remove(job["list"], dict(data, token=job.get("token", "")), actor,
                               where="v2's NetBox page")
    status = netbox_guard.record_removal(job["list"], actor, result)
    drawn = netbox_removal_result(status["row"], status)
    _write(job_id, dict(_confirmed(job, actor), state="imported" if result.get("ok") else
                        "failed", token="",
                        removal=drawn))
    _announce()
    return read(job_id)


def forget(job_id: str, data: dict, actor: str) -> dict:
    """Confirm the previewed Stop tracking *job_id* (C954) and run it in the request
    (`netbox_ops.forget`: bound to the preview's hash, deleting nothing in NetBox); its result
    recorded in the removal record as forget-only, with each entry forgotten, and drawn from
    that row. Raises `netbox_ops.Refused`."""
    from modules import netbox_guard, netbox_ops
    from modules.preview_confirm import netbox_removal_result

    job = read(job_id)
    if job.get("state") != "previewed" or job.get("operation") != "forget":
        raise netbox_ops.Refused({"ok": False, "error": "that preview is not one ready to "
                                  "confirm: preview again"}, 409)
    result = netbox_ops.forget(job["list"], dict(data, token=job.get("token", "")), actor)
    status = netbox_guard.record_removal(job["list"], actor, result, forget_only=True)
    drawn = netbox_removal_result(status["row"], status)
    _write(job_id, dict(_confirmed(job, actor), state="imported" if result.get("ok") else
                        "failed", token="",
                        removal=drawn))
    _announce()
    return read(job_id)
