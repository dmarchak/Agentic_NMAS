"""nsot/approval.py

Template approval: a template may not be marked approved until it round-trips
cleanly against **every device currently bound to it**.

Approval is keyed on a **binding fingerprint**, not just the template's path and
content:

* the template's content hash, and
* the sorted set of bound device identities, and
* a hash of each bound device's ``host_vars``

Any of those changing invalidates the approval. Editing the template changes the
content hash; onboarding a device in Phase 4 changes the device set; a
``host_vars`` edit changes that device's hash. Without the device half, a newly
onboarded device would silently inherit an approval for a template it was never
validated against — the approval would say "validated" about a device that had
never been looked at.

The approval record is committed to git, so it is reviewable and its history is
visible. It is not a UI toggle.
"""

import hashlib
import json
import logging
import os
import time

log = logging.getLogger(__name__)

APPROVALS_REL = os.path.join("templates", ".approvals.json")


def approvals_path(repo: str) -> str:
    return os.path.join(repo, APPROVALS_REL)


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------

def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def binding_fingerprint(repo: str, rel_path: str, host_vars_by_device: dict) -> dict:
    """Everything an approval is bound to.

    *host_vars_by_device* maps device name → parsed host_vars for each bound
    device, so the fingerprint moves when a device's configuration model moves.
    """
    from modules.nsot import templates_repo
    from modules.nsot.render_artifact import host_vars_fingerprint

    template_text = templates_repo.read_template(repo, rel_path) or ""
    bound = templates_repo.devices_for_template(repo, rel_path)

    device_hashes = {}
    for entry in bound:
        name = entry["device"]
        host_vars = host_vars_by_device.get(name)
        device_hashes[name] = host_vars_fingerprint(host_vars) if host_vars else "unknown"

    payload = {
        "template": rel_path,
        "template_hash": content_hash(template_text),
        "devices": sorted(device_hashes),
        "device_hashes": {k: device_hashes[k] for k in sorted(device_hashes)},
    }
    payload["fingerprint"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return payload


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _load(repo: str) -> dict:
    path = approvals_path(repo)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        log.error("approval: unreadable record (%s) — treating as unapproved", exc)
        return {}


def _save(repo: str, data: dict) -> None:
    path = approvals_path(repo)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def is_approved(repo: str, rel_path: str, host_vars_by_device: dict) -> bool:
    """True only if a stored approval matches the current binding fingerprint."""
    record = _load(repo).get(rel_path)
    if not record:
        return False
    current = binding_fingerprint(repo, rel_path, host_vars_by_device)
    return record.get("fingerprint") == current["fingerprint"]


def approval_status(repo: str, rel_path: str, host_vars_by_device: dict) -> dict:
    """Approval state plus, when stale, precisely what changed."""
    record = _load(repo).get(rel_path)
    current = binding_fingerprint(repo, rel_path, host_vars_by_device)

    if not record:
        return {"approved": False, "reason": "never approved",
                "fingerprint": current["fingerprint"], "changes": []}
    if record.get("fingerprint") == current["fingerprint"]:
        return {"approved": True, "approved_at": record.get("approved_at"),
                "actor": record.get("actor"),
                "devices": record.get("devices", []),
                "fingerprint": current["fingerprint"], "changes": []}

    changes = []
    if record.get("template_hash") != current["template_hash"]:
        changes.append("the template was edited")
    old_devices = set(record.get("devices", []))
    new_devices = set(current["devices"])
    for added in sorted(new_devices - old_devices):
        changes.append(f"device '{added}' is now bound to this template")
    for removed in sorted(old_devices - new_devices):
        changes.append(f"device '{removed}' is no longer bound")
    for name in sorted(new_devices & old_devices):
        if record.get("device_hashes", {}).get(name) != current["device_hashes"][name]:
            changes.append(f"host_vars for '{name}' changed")

    return {"approved": False, "reason": "approval is stale",
            "fingerprint": current["fingerprint"], "changes": changes,
            "previously_approved_at": record.get("approved_at")}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def validate_template(repo: str, rel_path: str, devices: list) -> dict:
    """Round-trip *rel_path* against every bound device. No device contact.

    *devices* is a list of ``{"device", "running_config", "platform"}`` built
    from **captured** artifacts (a golden file or a stored backup).
    """
    from modules.nsot import roundtrip, templates_repo
    from modules.nsot.parsers import get_parser

    results, host_vars_by_device = [], {}
    root = templates_repo.templates_dir(repo)
    platform_dir = os.path.dirname(rel_path)
    template_name = os.path.basename(rel_path)

    for entry in devices:
        name = entry["device"]
        parsed = get_parser(entry["platform"]).parse(entry["running_config"])
        host_vars_by_device[name] = parsed
        try:
            rendered = roundtrip.render(parsed, platform_dir, None,
                                        template_root=root,
                                        template_name=template_name)
        except Exception as exc:              # noqa: BLE001
            results.append({"device": name, "ok": False,
                            "error": f"render failed: {exc}"})
            continue

        report = roundtrip.compare(entry["running_config"], rendered, parsed)
        from modules.nsot.render_artifact import acknowledgement_is_complete
        acknowledged = acknowledgement_is_complete(parsed)
        results.append({
            "device": name,
            "ok": report["ok"] and acknowledged,
            "missing": report["missing_from_render"],
            "extra": report["extra_in_render"],
            "reordered": report["reordered_sections"],
            "unmodeled": report["unmodeled"],
            "unmodeled_acknowledged": acknowledged,
            "modeled_coverage": report["modeled_coverage"],
            "missing_sample": [m["line"] for m in report["details"]["missing"][:5]],
            "extra_sample": [e["line"] for e in report["details"]["extra"][:5]],
        })

    return {"ok": bool(results) and all(r["ok"] for r in results),
            "template": rel_path, "results": results,
            "host_vars_by_device": host_vars_by_device,
            "device_count": len(results)}


def approve(repo: str, rel_path: str, devices: list, actor: str = "user") -> dict:
    """Approve *rel_path* — only if it validates against every bound device."""
    if not devices:
        return {"ok": False,
                "error": "no devices are bound to this template, so there is "
                         "nothing to validate it against"}

    validation = validate_template(repo, rel_path, devices)
    if not validation["ok"]:
        failed = [r for r in validation["results"] if not r["ok"]]
        return {"ok": False, "error": (
            f"{len(failed)} of {validation['device_count']} bound device(s) "
            "do not round-trip cleanly"), "validation": validation}

    fingerprint = binding_fingerprint(repo, rel_path,
                                      validation["host_vars_by_device"])
    data = _load(repo)
    data[rel_path] = {**fingerprint,
                      "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "actor": actor}
    _save(repo, data)
    log.info("approval: '%s' approved by %s against %d device(s)",
             rel_path, actor, validation["device_count"])
    return {"ok": True, "template": rel_path, "validation": validation,
            "fingerprint": fingerprint["fingerprint"]}


def revoke(repo: str, rel_path: str) -> dict:
    data = _load(repo)
    data.pop(rel_path, None)
    _save(repo, data)
    return {"ok": True}
