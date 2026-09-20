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


def execute_restore(list_name: str, ref: str, devices: list = None,
                    actor: str = "user") -> dict:
    """Queue per-device restore approvals. Pushes nothing directly."""
    from modules.approval_queue import add_approval

    planned = plan_restore(list_name, ref, devices)
    if not planned["ok"]:
        return planned

    repo = _repo_for(list_name)
    queued, errors = [], []

    for item in planned["restorable"]:
        content = _repo.golden_at(repo, item["hostname"], ref)
        if content is None:
            errors.append({"hostname": item["hostname"], "error": "config vanished"})
            continue
        try:
            add_approval(
                action_type="revert_to_golden",
                description=f"Restore {item['hostname']} to {ref}",
                device_ip=item["ip"],
                device_hostname=item["hostname"],
                action_params={"ref": ref, "config_text": content,
                               "list_name": list_name, "requested_by": actor},
                context=f"Network restore to baseline {ref}, requested by {actor}",
            )
            queued.append(item["hostname"])
        except Exception as exc:              # noqa: BLE001
            log.exception("restore: could not queue %s", item["hostname"])
            errors.append({"hostname": item["hostname"], "error": str(exc)})

    log.info("restore: queued %d device(s) for '%s' at %s (%d skipped)",
             len(queued), list_name, ref, len(planned["skipped"]))
    return {"ok": True, "ref": ref, "queued": queued,
            "skipped": planned["skipped"], "errors": errors,
            "message": (
                f"Queued {len(queued)} device(s) for approval."
                + (f" Skipped {len(planned['skipped'])}: "
                   f"{', '.join(s['hostname'] for s in planned['skipped'])}."
                   if planned["skipped"] else "")
            )}
