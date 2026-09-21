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
import re
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


#: Bumped when the fingerprint's *meaning* changes. A stored record from an
#: older scheme is not silently honoured: its number says it was answering a
#: different question, and accepting it would be a gate that passes because
#: nobody updated it.
FINGERPRINT_SCHEME = 2


#: Jinja tags that pull another file into a template's rendered output.
_IMPORT_RE = re.compile(
    r"{%-?\s*(?:import|include|extends|from)\s+['\"]([^'\"]+)['\"]")


def template_imports(text: str) -> list:
    """Template paths *text* pulls in, in the order they appear."""
    return _IMPORT_RE.findall(text or "")


def template_closure(repo: str, rel_path: str) -> list:
    """*rel_path* and every template it transitively imports, sorted.

    Cycles terminate: a path already seen is not followed again.
    """
    from modules.nsot import templates_repo

    seen, queue = set(), [rel_path]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        text = templates_repo.read_template(repo, current)
        if text is None:
            # A missing import is not silently ignored — it changes the render
            # (to an error), so it stays in the closure and its absence is part
            # of the hash.
            continue
        queue.extend(template_imports(text))
    return sorted(seen)


def template_closure_text(repo: str, rel_path: str) -> str:
    """The closure's contents, path-labelled, for hashing.

    Paths are included so moving a macro between files changes the hash even
    when the total text does not.
    """
    from modules.nsot import templates_repo

    parts = []
    for path in template_closure(repo, rel_path):
        parts.append(f"--- {path}\n{templates_repo.read_template(repo, path) or ''}")
    return "\n".join(parts)


def binding_fingerprint(repo: str, rel_path: str,
                        host_vars_by_device: dict = None) -> dict:
    """Everything an approval is bound to: the template, and the devices it covers.

    Approval claims **"this template was validated against this device set"**.
    It does not claim anything about those devices' current configuration —
    that is ``template_report``, computed live on every plan, per device, and
    gating there.

    Scheme 1 also hashed each bound device's parsed host_vars. That keyed the
    gate on the *result of the work*: a successful deploy changes the device's
    captured config, so the hash moves and the approval is revoked — by the
    very change it authorised. On a four-device template, deploying to one
    revoked approval for the other three, which had received nothing. It is
    the rule recorded in NSOT_PLAN.md ("gate on template fidelity, never on
    intent drift") broken in its own implementation, and the only visible
    symptom is a gate that is red so routinely it teaches you to clear it.

    *host_vars_by_device* is accepted and ignored, so callers that have it
    need not change; it is no longer part of the hash.
    """
    from modules.nsot import templates_repo

    # The full import closure, not just this file. A template IS base.j2 plus
    # every macro file it imports; hashing only base.j2 meant an edit to the
    # shared `_common.j2` — where every routing, interface and service macro
    # lives — left every approval standing while the render changed underneath
    # it. Found while fixing the BGP macro: that edit would have kept
    # cisco_ios/base.j2 approved for s1-s4 on the strength of a hash that never
    # looked at the file being changed. Same shape as the round-trip metric —
    # a gate measuring less than its claim.
    template_text = template_closure_text(repo, rel_path)
    bound = templates_repo.devices_for_template(repo, rel_path)
    # Stable identities, not names: a rename is the same device, onboarding is
    # not. Falls back to the name when a device has no manifest identity.
    identities = sorted(entry.get("identity") or entry["device"]
                        for entry in bound)

    payload = {
        "scheme": FINGERPRINT_SCHEME,
        "template": rel_path,
        "template_hash": content_hash(template_text),
        "devices": sorted(entry["device"] for entry in bound),
        "device_identities": identities,
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


def is_approved(repo: str, rel_path: str, host_vars_by_device: dict = None) -> bool:
    """True only if a stored approval matches the current binding fingerprint.

    A record written under an older scheme is **not** accepted. Its fingerprint
    answered a different question, and honouring it would be a gate that passes
    because nobody migrated it.
    """
    record = _load(repo).get(rel_path)
    if not record:
        return False
    if record.get("revoked"):
        # First, and unconditionally. A revocation is a decision about this
        # template; nothing computed afterwards may overturn it.
        log.warning("approval: '%s' is revoked — %s", rel_path,
                    record.get("reason", "(no reason recorded)"))
        return False
    if record.get("scheme") != FINGERPRINT_SCHEME:
        log.warning("approval: '%s' was approved under fingerprint scheme %s, "
                    "current is %s — treating as unapproved until re-approved",
                    rel_path, record.get("scheme", 1), FINGERPRINT_SCHEME)
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
    if record.get("revoked"):
        return {"approved": False, "revoked": True,
                "reason": f"REVOKED: {record.get('reason', '')}",
                "revoked_at": record.get("revoked_at"),
                "actor": record.get("actor"),
                "fingerprint": current["fingerprint"],
                "changes": ["re-approval must validate against every bound "
                            "device before this template can deploy again"],
                "previously_approved_at": record.get("previously_approved_at")}
    if record.get("scheme") != FINGERPRINT_SCHEME:
        return {"approved": False,
                "reason": (f"approved under fingerprint scheme "
                           f"{record.get('scheme', 1)}, current is "
                           f"{FINGERPRINT_SCHEME}"),
                "fingerprint": current["fingerprint"],
                "changes": ["the approval scheme changed — re-approve once, "
                            "explicitly, so the record says what it now means"],
                "previously_approved_at": record.get("approved_at")}
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
    # Deliberately no per-device config comparison here. A device's
    # configuration changing is not an approval question — it is answered live
    # by template_report on every plan, per device, with the lines named.

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
            "excluded_unrenderable": report.get("excluded_unrenderable", []),
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

    fingerprint = binding_fingerprint(repo, rel_path)
    data = _load(repo)
    data[rel_path] = {**fingerprint,
                      "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "actor": actor}
    _save(repo, data)
    log.info("approval: '%s' approved by %s against %d device(s)",
             rel_path, actor, validation["device_count"])
    return {"ok": True, "template": rel_path, "validation": validation,
            "fingerprint": fingerprint["fingerprint"]}


def approved_templates(repo: str) -> list:
    """Template paths carrying a stored record, revoked or not."""
    return sorted(_load(repo))


def revoke(repo: str, rel_path: str, reason: str = "", actor: str = "") -> dict:
    """Withdraw an approval and record **why**.

    Popping the record made a revocation indistinguishable from "never
    approved". Both block a deploy, so the gate behaved correctly either way —
    but the next person sees an unapproved template with no indication that
    somebody withdrew it deliberately, or what they must check before granting
    it again. A revocation is a finding; deleting it throws the finding away.

    The tombstone is *not* an approval and can never be read as one:
    :func:`is_approved` refuses anything carrying ``revoked``, ahead of every
    other check, so a revoked record cannot pass even if a later scheme or
    fingerprint happened to line up.
    """
    if not reason.strip():
        return {"ok": False, "error": (
            "A revocation needs a reason. It is the only record of why this "
            "template must be re-validated, and 'unapproved' on its own says "
            "nothing to whoever finds it.")}

    data = _load(repo)
    previous = data.get(rel_path) or {}
    data[rel_path] = {
        "revoked": True,
        "reason": reason.strip(),
        "revoked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "actor": actor or "operator",
        # Kept so the record says what was withdrawn, not merely that something
        # was. Never consulted by the gate.
        "previous_fingerprint": previous.get("fingerprint", ""),
        "previously_approved_at": previous.get("approved_at", ""),
        "previously_approved_by": previous.get("actor", ""),
        "previous_devices": previous.get("devices", []),
    }
    _save(repo, data)
    log.warning("approval: '%s' REVOKED by %s — %s", rel_path,
                actor or "operator", reason.strip())
    return {"ok": True, "template": rel_path, "reason": reason.strip(),
            "was_approved": bool(previous.get("fingerprint"))}
