"""nsot/approval.py

Template approval, **scheme 3** (NSOT_PLAN P.5, register D11; decided
2026-09-26): an approval is **the template's closure hash and the person who
approved it**. It is a claim about the TEMPLATE.

What it does NOT claim is that every bound device renders faithfully. That is
checked where it already runs, live, per device, on every plan:
``RenderArtifact.template_report`` renders the capture's own parse and
``blocking_reasons`` refuses a device the template cannot reproduce, naming
the lines, whatever approval says (measured in code before this scheme was
built). So a device the template cannot reproduce is blocked ALONE, at its own
deploy, instead of blocking every other device on its platform.

History, because each scheme was a correction:

* scheme 1 hashed each device's host_vars, so the deploy an approval
  authorised revoked it;
* scheme 2 hashed the bound device SET, so onboarding one device revoked the
  approval for every device on its platform, and one device the template could
  not reproduce blocked all the others: a property of the inventory keyed into
  a claim about the template (D11), and the reason a never-reached device took
  its platform's deploy path offline (D2).

Approving still validates against the bound set and records the result per
device, as EVIDENCE; it requires at least one validated device, not all. A
template edit changes the hash and so revokes every approval over it. A
record written under an older scheme is never honoured silently: moving to
scheme 3 is an explicit re-approval.

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
FINGERPRINT_SCHEME = 3

#: What an approval covers and what it does not, in the words every surface
#: shows (the operator: without the second sentence scheme 3 reads as WEAKER
#: than scheme 2 to anyone who does not know why).
COVERS = ("This approval covers the template itself: its text and every macro file it "
          "imports, as they are now.")
DOES_NOT_COVER = ("It does not say every device renders faithfully. Each device is "
                  "validated at its own deploy, and a device this template cannot "
                  "reproduce is blocked there alone, with the lines named.")


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


def template_fingerprint(repo: str, rel_path: str,
                         host_vars_by_device: dict = None) -> dict:
    """What an approval is bound to under scheme 3: the template's closure.

    The full import closure, not just this file. A template IS ``base.j2``
    plus every macro file it imports; hashing only ``base.j2`` meant an edit
    to the shared ``_common.j2`` left every approval standing while the
    render changed underneath it.

    No device appears here, deliberately (see the module docstring). The
    bound devices at the moment of approval are recorded beside the
    fingerprint as evidence, never inside it, so onboarding, retiring or
    re-capturing a device cannot move it.

    *host_vars_by_device* is accepted and ignored, so callers that have it
    need not change.
    """
    payload = {
        "scheme": FINGERPRINT_SCHEME,
        "template": rel_path,
        "template_hash": content_hash(template_closure_text(repo, rel_path)),
    }
    payload["fingerprint"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return payload


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class ApprovalsUnreadable(RuntimeError):
    """The approvals record exists and cannot be read: nothing is written over it."""


def _lock(repo: str):
    """Every read-modify-write of the record, across processes (CONCURRENCY_AUDIT R13): an
    approve and a revoke at once each saved a stale copy, so one person's revocation could be
    undone by another's approval, and a host script writes this file too.

    The lock file is BESIDE the repository (``<repo>.approvals.lock``), as the repository's
    own lock is: inside ``templates/`` it was an untracked file in the NSoT repository, which
    the library's seeding stages."""
    from modules.filestore import PathLock
    return PathLock(os.path.abspath(repo) + ".approvals")


def _load_for_write(repo: str) -> dict:
    """The working record for a read-modify-write: {} when ABSENT; ApprovalsUnreadable when
    it cannot be read (it used to read as {}, and the next save erased every approval and
    every tombstone in it). The damaged file is preserved beside it."""
    from modules.filestore import StoreUnreadable, read_json_for_write
    try:
        data = read_json_for_write(approvals_path(repo), aside=_aside(repo))
    except StoreUnreadable as exc:
        raise ApprovalsUnreadable(str(exc)) from exc
    if not isinstance(data, dict):
        raise ApprovalsUnreadable(f"{APPROVALS_REL} is not a mapping, so nothing was written")
    return data


def _aside(repo: str) -> str:
    """Where the record's damaged copy goes, and the folder of its write's temp file:
    BESIDE the repository (``<repo>.approvals.json``), never inside it, where seeding stages
    untracked files under ``templates/`` (C345)."""
    return os.path.abspath(repo) + ".approvals.json"


def _save(repo: str, data: dict) -> None:
    """Replaced atomically, a temp file per write (it was one shared `.tmp`), the temp
    beside the repository, on the same filesystem (C345)."""
    from modules.filestore import write_atomic
    write_atomic(approvals_path(repo), json.dumps(data, indent=2, sort_keys=True), newline="\n",
                 tmp_dir=os.path.dirname(_aside(repo)))


def _load(repo: str) -> dict:
    """The working record for display; {} (logged) when unreadable. Never written back:
    writers use `_load_for_write` under `_lock`."""
    try:
        return _load_for_write(repo)
    except ApprovalsUnreadable as exc:
        log.error("approval: %s", exc)
        return {}


def _committed(repo: str):
    """The record at HEAD: {} when not committed, None when it cannot be read."""
    from modules.nsot.repo import git, git_raw

    rel = APPROVALS_REL.replace(os.sep, "/")
    if git(repo, "cat-file", "-e", f"HEAD:{rel}")[0] != 0:
        return {}
    rc, out, err = git_raw(repo, "show", f"HEAD:{rel}")
    if rc != 0:
        log.error("approval: the committed record could not be read: %s", err)
        return None
    try:
        data = json.loads(out)
    except ValueError as exc:
        log.error("approval: the committed record is not JSON: %s", exc)
        return None
    return data if isinstance(data, dict) else None


def _effective(repo: str, rel_path: str) -> tuple:
    """``(record, problem)``: the record the gate judges (CONCURRENCY_AUDIT R13).

    An approval counts only when it is COMMITTED and the working record still holds it, so
    it fails closed both ways: an approval whose commit failed is not one (the gate read the
    working file, so an uncommitted approval passed), and a revocation not yet committed
    already refuses (the working record holds it). Either record unreadable refuses."""
    try:
        work = _load_for_write(repo)
    except ApprovalsUnreadable as exc:
        return None, f"the approvals record could not be read: {exc}"
    head = _committed(repo)
    if head is None:
        return None, "the committed approvals record could not be read"
    w, h = work.get(rel_path), head.get(rel_path)
    if w and not w.get("revoked") and w != h:
        return None, ("approved in the record but not committed: the deploy gate counts an "
                      "approval once its commit exists")
    return w, ""


def is_approved(repo: str, rel_path: str, host_vars_by_device: dict = None) -> bool:
    """True only if a stored scheme-3 approval matches the template as it is now.

    A record written under an older scheme is **not** accepted. Its fingerprint
    answered a different question, and honouring it would be a gate that passes
    because nobody migrated it.
    """
    record, problem = _effective(repo, rel_path)
    if problem:
        log.warning("approval: '%s' is not approved: %s", rel_path, problem)
        return False
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
    return record.get("fingerprint") == template_fingerprint(repo, rel_path)["fingerprint"]


def approval_status(repo: str, rel_path: str, host_vars_by_device: dict = None) -> dict:
    """Approval state, what it covers and does not, and when stale, what changed."""
    record, problem = _effective(repo, rel_path)
    current = template_fingerprint(repo, rel_path)
    scope = {"covers": COVERS, "does_not_cover": DOES_NOT_COVER}

    if problem:
        return {"approved": False, "reason": problem,
                "fingerprint": current["fingerprint"], "changes": [], **scope}
    if not record:
        return {"approved": False, "reason": "never approved",
                "fingerprint": current["fingerprint"], "changes": [], **scope}
    if record.get("revoked"):
        return {"approved": False, "revoked": True,
                "reason": f"REVOKED: {record.get('reason', '')}",
                "revoked_at": record.get("revoked_at"),
                "actor": record.get("actor"),
                "fingerprint": current["fingerprint"],
                "changes": ["re-approval must validate the template against at least "
                            "one bound device before it can deploy again"],
                "previously_approved_at": record.get("previously_approved_at"), **scope}
    if record.get("scheme") != FINGERPRINT_SCHEME:
        old = record.get("scheme", 1)
        return {"approved": False,
                "reason": (f"approved under fingerprint scheme {old}, current is "
                           f"{FINGERPRINT_SCHEME}"),
                "fingerprint": current["fingerprint"],
                "changes": [(f"scheme {old} bound the approval to the device set; scheme "
                             f"{FINGERPRINT_SCHEME} approves the template alone, and each "
                             "device is checked at its own deploy — re-approve once, "
                             "explicitly, so the record says what it now means")],
                "previously_approved_at": record.get("approved_at"), **scope}
    if record.get("fingerprint") == current["fingerprint"]:
        return {"approved": True, "approved_at": record.get("approved_at"),
                "actor": record.get("actor"),
                "evidence": record.get("evidence", {}),
                "fingerprint": current["fingerprint"], "changes": [], **scope}
    return {"approved": False, "reason": "approval is stale",
            "fingerprint": current["fingerprint"],
            "changes": ["the template was edited (it, or a macro file it imports)"],
            "previously_approved_at": record.get("approved_at"), **scope}


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


def approve(repo: str, rel_path: str, devices: list, actor: str = "user",
            not_validated: list = None, shown: str = None) -> dict:
    """Approve *rel_path* when it validates against AT LEAST ONE bound device.

    Every device's result is recorded as evidence: the ones that validated,
    and the ones that did not with the reason. A device that does not
    round-trip is not a reason to withhold the approval from the template,
    because that device is blocked at its own deploy regardless (scheme 3).
    *not_validated*: bound devices the caller could not validate at all
    (``{"device", "reason"}``, e.g. no captured config yet), recorded as such.
    *shown*: the closure fingerprint the person's page showed (R12's client half); a
    template that moved since is refused naming both. None for a caller with no page.
    """
    if not devices:
        return {"ok": False,
                "error": "no bound device has a captured config, so there is nothing "
                         "to validate this template against; at least one is required",
                "not_validated": list(not_validated or [])}

    # ONE snapshot (CONCURRENCY_AUDIT R12): the closure is fingerprinted BEFORE validation and
    # again under the record's lock just before the save. An edit saved in between made an
    # approval of content no validation ran against, and overwrote the edit's revocation.
    before = template_fingerprint(repo, rel_path)
    if shown is not None and shown != before.get("fingerprint"):
        return {"ok": False, "not_validated": list(not_validated or []),
                "error": (f"Not approved: {rel_path} (or a template it imports) changed after "
                          f"your page showed it: it showed fingerprint {str(shown)[:12]} and "
                          f"is {str(before.get('fingerprint'))[:12]} now. Reload the template "
                          "library, review the change, then approve again.")}
    validation = validate_template(repo, rel_path, devices)
    passed = [r["device"] for r in validation["results"] if r["ok"]]
    failed = [{"device": r["device"],
               "reason": r.get("error") or _summary(r)} for r in validation["results"]
              if not r["ok"]]
    skipped = list(not_validated or [])
    if not passed:
        return {"ok": False, "error": (
            f"none of the {validation['device_count']} bound device(s) with a capture "
            "round-trips cleanly; at least one must, or nothing shows the template "
            "reproduces a real device"), "validation": validation,
            "not_validated": skipped}

    evidence = {"validated": sorted(passed), "failed": failed, "not_validated": skipped,
                "bound": len(passed) + len(failed) + len(skipped)}
    with _lock(repo):
        fingerprint = template_fingerprint(repo, rel_path)
        if fingerprint.get("fingerprint") != before.get("fingerprint"):
            return {"ok": False, "validation": validation, "not_validated": skipped,
                    "error": (f"Not approved: {rel_path} (or a template it imports) changed "
                              f"while it was being validated: its fingerprint was "
                              f"{str(before.get('fingerprint'))[:12]} when validation began "
                              f"and is {str(fingerprint.get('fingerprint'))[:12]} now. Review "
                              "the change, then approve again.")}
        try:
            data = _load_for_write(repo)
        except ApprovalsUnreadable as exc:
            return {"ok": False, "error": f"Not approved: {exc}", "validation": validation,
                    "not_validated": skipped}
        data[rel_path] = {**fingerprint,
                          "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "actor": actor, "evidence": evidence}
        _save(repo, data)
    log.info("approval: '%s' approved by %s; validated %d of %d bound device(s)",
             rel_path, actor, len(passed), evidence["bound"])
    return {"ok": True, "template": rel_path, "validation": validation,
            "fingerprint": fingerprint["fingerprint"], "evidence": evidence,
            "covers": COVERS, "does_not_cover": DOES_NOT_COVER}


def _summary(result: dict) -> str:
    parts = []
    for key, words in (("missing", "line(s) not reproduced"), ("extra", "line(s) invented"),
                       ("reordered", "section(s) reordered")):
        if result.get(key):
            parts.append(f"{result[key]} {words}")
    if result.get("unmodeled") and not result.get("unmodeled_acknowledged"):
        parts.append(f"{result['unmodeled']} unmodelled line(s) not acknowledged")
    return "; ".join(parts) or "does not round-trip"


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

    with _lock(repo):
        try:
            data = _load_for_write(repo)
        except ApprovalsUnreadable as exc:
            return {"ok": False, "error": f"Not revoked: {exc}"}
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
            "previous_evidence": previous.get("evidence", {}),
        }
        _save(repo, data)
    log.warning("approval: '%s' REVOKED by %s — %s", rel_path,
                actor or "operator", reason.strip())
    return {"ok": True, "template": rel_path, "reason": reason.strip(),
            "was_approved": bool(previous.get("fingerprint"))}
