"""nsot/restore.py

Restoring devices to a previous golden config.

Restore **never pushes directly**. It creates one approval-queue item per
device, so a human reviews each change. Stale devices — devices that have
disappeared from a NetBox-sourced list — are **skipped and named**, never
silently omitted: a partial restore the operator did not know about is worse
than a refused one.
"""

import logging
import os

from modules.nsot import repo as _repo

log = logging.getLogger(__name__)


def _repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def plan_restore(list_name: str, ref: str, devices: list = None) -> dict:
    """Report what a restore to *ref* would do. Reads only.

    Returns ``restorable`` and ``skipped``; the confirm dialog shows both
    *before* anything is queued.
    """
    from modules.inventory import is_stale, stale_message

    repo = _repo_for(list_name)
    if not os.path.isdir(os.path.join(repo, ".git")):
        return {"ok": False, "error": "This list has no configuration repository yet."}

    at_ref = _repo.devices_at(repo, ref)
    if not at_ref:
        return {"ok": False, "error": f"No golden configs found at '{ref}'."}

    wanted = set(devices) if devices else set(at_ref)
    restorable, skipped = [], []

    from modules.device import get_current_device_list, load_saved_devices
    _name, csv_path = get_current_device_list()
    ip_by_host = {d.get("hostname", ""): d.get("ip", "")
                  for d in load_saved_devices(csv_path)}

    for hostname in sorted(at_ref):
        if hostname not in wanted:
            continue
        mgmt_ip = ip_by_host.get(hostname, "")

        if not mgmt_ip:
            skipped.append({"hostname": hostname, "reason":
                            "not in the current device list"})
            continue
        if is_stale(mgmt_ip, list_name):
            skipped.append({"hostname": hostname, "ip": mgmt_ip,
                            "reason": "no longer in NetBox for this list",
                            "detail": stale_message(mgmt_ip, list_name)})
            continue

        content = _repo.golden_at(repo, hostname, ref)
        if content is None:
            skipped.append({"hostname": hostname, "ip": mgmt_ip,
                            "reason": f"no golden config at {ref}"})
            continue
        restorable.append({"hostname": hostname, "ip": mgmt_ip,
                           "bytes": len(content)})

    return {
        "ok": True, "ref": ref, "list": list_name,
        "restorable": restorable, "skipped": skipped,
        "summary": (
            f"Restoring {len(restorable)} of {len(restorable) + len(skipped)} device(s)."
            + (f" Skipped: {', '.join(s['hostname'] for s in skipped)}."
               if skipped else "")
        ),
    }


def build_targets(list_name: str, ref: str, devices: list = None) -> tuple:
    """``(targets, skipped)`` for a re-apply of *ref*. Reads only.

    **Scope is declared, not remembered.** Every read goes through a
    ``RefSource`` constructed with ``golden/`` only, so asking for
    ``templates/``, ``bindings.yml`` or ``.approvals.json`` raises rather than
    returning content. Templates are code; rolling them back to restore a
    *network* would silently revert template fixes, including this week's.

    A future second restore path inherits the bound by constructing its own
    source and saying what it needs — item 2's intent restore will declare
    ``("golden/", "host_vars/")``, and declaring it at the call site is the
    point.
    """
    import os as _os

    from modules.device import get_current_device_list, load_saved_devices
    from modules.inventory import is_stale, stale_message
    from modules.nsot.deploy import RestoreTarget
    from modules.nsot.platform import platform_for_device

    repo = _repo_for(list_name)
    source = _repo.RefSource(repo, ref)          # golden/ only, by construction
    at_ref = source.devices()
    if not at_ref:
        return [], [{"hostname": "", "reason": f"no golden configs at '{ref}'"}]

    wanted = set(devices) if devices else set(at_ref)
    _name, csv_path = get_current_device_list()
    rows = {d.get("hostname", ""): d for d in load_saved_devices(csv_path)}

    targets, skipped = [], []
    for hostname in sorted(at_ref):
        if hostname not in wanted:
            continue
        row = rows.get(hostname)
        if not row:
            skipped.append({"hostname": hostname,
                            "reason": "not in the current device list"})
            continue
        mgmt_ip = row.get("ip", "")
        if is_stale(mgmt_ip, list_name):
            skipped.append({"hostname": hostname, "ip": mgmt_ip,
                            "reason": "no longer in NetBox for this list",
                            "detail": stale_message(mgmt_ip, list_name)})
            continue

        stored = source.golden(hostname)
        if stored is None:
            skipped.append({"hostname": hostname, "ip": mgmt_ip,
                            "reason": f"no golden config at {ref}"})
            continue

        from routes.deploy import _captured_config
        captured = _captured_config(repo, hostname)
        targets.append(RestoreTarget(
            device=hostname, platform=platform_for_device(row),
            target_config=stored, captured=captured, ref=ref, device_row=row))

    return targets, skipped


def invalidate_queued_restores(reason: str = "") -> dict:
    """Reject any restore approvals the old path queued.

    Those entries carry whole-config text for an executor that pushes it
    directly — no confirm hash, no ASCII guard, no provenance, no
    ``error_pattern``, no failure capture, no rollback. Executing one after the
    switch would send exactly the payload this rebuild exists to stop sending.

    Rejected with a reason rather than deleted, so the queue shows what
    happened.
    """
    from modules.approval_queue import get_pending, resolve

    reason = reason or ("superseded: restore now goes through the confirmed "
                        "deploy path; re-run it from the Baselines panel")
    rejected = []
    for entry in get_pending():
        if entry.get("action_type") != "revert_to_golden":
            continue
        try:
            resolve(entry["id"], "reject")
            rejected.append({"id": entry["id"],
                             "hostname": entry.get("device_hostname", ""),
                             "reason": reason})
        except Exception as exc:              # noqa: BLE001
            log.error("restore: could not reject queued item %s: %s",
                      entry.get("id"), exc)
    if rejected:
        log.warning("restore: rejected %d queued restore approval(s) — %s",
                    len(rejected), reason)
    return {"ok": True, "rejected": rejected, "reason": reason}
