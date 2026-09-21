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


def build_targets(list_name: str, ref: str, devices: list = None,
                  un_onboard: list = None) -> tuple:
    """``(targets, skipped)`` for a re-apply of *ref*. Reads only.

    **Scope is declared, not remembered.** Every read goes through a
    ``RefSource`` constructed with ``golden/`` and ``host_vars/`` and nothing
    else, so asking for ``templates/``, ``bindings.yml`` or ``.approvals.json``
    raises rather than returning content. Templates are code; rolling them back
    to restore a *network* would silently revert template fixes, including this
    week's. The allowlist is a constructor argument precisely so a second
    restore path has to say what it needs at its own call site.

    **Device and intent are one unit per device.** A device is either restored
    with its intent from the same ref, or not restored at all — restoring the
    configuration while committed intent still describes something else leaves
    the device fighting the next plan.
    """
    import os as _os

    from modules.device import get_current_device_list, load_saved_devices
    from modules.inventory import is_stale, stale_message
    from modules.nsot.deploy import RestoreTarget
    from modules.nsot.platform import platform_for_device

    repo = _repo_for(list_name)
    # Declared, not remembered: intent restore needs host_vars/ and says so.
    source = _repo.RefSource(repo, ref, allow=("golden/", "host_vars/"))
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

        platform = platform_for_device(row)
        ref_intent_text = source.read(f"host_vars/{hostname}.yml") or ""
        ref_intent = intent_at(source, hostname)

        if ref_intent is None:
            # Restoring the device while its committed intent still says
            # something else recreates the fight-itself loop; removing the
            # intent is an un-onboarding nobody asked for. Skipping changes
            # neither half and says so — consistent with a stale device.
            if hostname not in set(un_onboard or []):
                skipped.append({
                    "hostname": hostname, "ip": mgmt_ip,
                    "reason": f"no committed intent at {ref}",
                    "detail": ("This ref predates the device's onboarding. "
                               "Restoring its configuration while current "
                               "intent says something else would make the next "
                               "plan offer to undo the restore. Tick "
                               "'un-onboard' to remove the committed intent as "
                               "well — a forward commit, recoverable from git "
                               "history."),
                    "un_onboardable": True})
                continue

        gaps = []
        if ref_intent is not None:
            gaps = validate_restored_intent(repo, hostname, ref_intent,
                                            stored, platform)
        if gaps:
            skipped.append({"hostname": hostname, "ip": mgmt_ip,
                            "reason": "this ref's intent is not usable today",
                            "detail": "; ".join(gaps)})
            continue

        from routes.deploy import _captured_config
        captured = _captured_config(repo, hostname)
        targets.append(RestoreTarget(
            device=hostname, platform=platform,
            target_config=stored, captured=captured, ref=ref, device_row=row,
            ref_intent=ref_intent, ref_intent_text=ref_intent_text,
            un_onboard=(ref_intent is None)))

    return targets, skipped


def intent_at(source, hostname: str):
    """The device's committed intent at the ref, or ``None`` if it had none."""
    from modules.nsot import hostvars

    raw = source.read(f"host_vars/{hostname}.yml")
    return hostvars.from_yaml(raw) if raw else None


def validate_restored_intent(repo: str, hostname: str, intent: dict,
                             stored_golden: str, platform: str) -> list:
    """Plan-time gaps between old intent and the CURRENT tooling.

    Two ways a ref's intent can be unusable today, both refused here rather
    than discovered mid-batch:

    * **It no longer round-trips.** The schema and the templates have moved
      since older refs. Rendering the ref's intent through *today's* template
      must reproduce the ref's golden — otherwise restoring that intent
      immediately produces a plan proposing changes nobody asked for.
    * **A secret it names is gone.** The credential store is unversioned, so a
      ref can reference a secret since rotated away or never present on this
      installation. The render emits ``<missing-secret:…>``, which
      ``assert_no_mask`` catches at deploy — naming the device and the ref at
      plan time is the difference between a refusal and a failed batch.
    """
    from modules.credentials import get_template_secret
    from modules.nsot import hostvars, roundtrip

    gaps = []

    for ref_name in (intent.get("secret_refs") or []):
        if not get_template_secret(f"{hostname}:{ref_name}"):
            gaps.append(f"secret '{ref_name}' is named by this ref's intent but "
                        "is not in the credential store")

    try:
        live = hostvars.hydrate_secrets(intent, hostname)
        rendered = roundtrip.render(live, live.get("platform", platform))
    except Exception as exc:                  # noqa: BLE001
        gaps.append(f"this ref's intent does not render through the current "
                    f"template: {exc}")
        return gaps

    report = roundtrip.compare(stored_golden, rendered, live)
    if report["missing_from_render"] or report["extra_in_render"]:
        sample = [m["line"] for m in report["details"]["missing"][:2]] + \
                 [e["line"] for e in report["details"]["extra"][:2]]
        gaps.append(
            f"this ref's intent no longer reproduces its own golden through "
            f"the current template ({report['missing_from_render']} missing, "
            f"{report['extra_in_render']} invented): " + "; ".join(sample))
    return gaps


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
