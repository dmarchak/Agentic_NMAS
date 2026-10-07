"""nsot/approve_op.py — approving and revoking a network's configuration template.

The one code path today's `/templates/approve`, `/templates/validate` and `/templates/revoke`
and the v2 Templates page (7.6, boards A to C, signed off 2026-10-05; C481) share. Scheme 3
(`approval.py`): an approval is a claim about the TEMPLATE, its closure's fingerprint and the
person; each bound device's check is recorded as evidence and at least one must reproduce.

The steps, as the manual's How it works page names them:

- ``check``: every bound device's CAPTURED configuration (its golden at HEAD; never a live
  read) parsed and rendered back through the template, compared line by line, the unmodelled
  lines judged against the acknowledgement in the device's committed intent. Writes nothing.
- ``approve``: refused when the template moved since the page showed it (its fingerprint) or
  the check's outcome moved since the person read it; else the approval is recorded as the
  verified person, with the evidence per device.
- ``commit``: the approvals record committed (the deploy gate counts an approval once it is).
- ``revoke``: the approval withdrawn with the person's reason, recorded and committed.

Nothing here contacts a device.
"""

import hashlib
import json
import logging
import os

log = logging.getLogger(__name__)

STEPS = ("check", "approve", "commit", "revoke")

#: A dialect's name in words, for the page (the template's directory is its dialect).
PLATFORM_WORDS = {"cisco_ios": "IOS", "cisco_iosxe": "IOS-XE"}


def repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _capture(repo: str, hostname: str):
    """*hostname*'s golden at HEAD (`repo.golden_at`, the store deploy and restore read), or
    None: the only input the check takes, never a live read."""
    from modules.nsot import repo as repo_service
    return repo_service.golden_at(repo, hostname, "HEAD")


def bound_captures(repo: str, rel_path: str) -> tuple:
    """``(devices, not_validated)``: each device bound to *rel_path* with its capture, and
    the bound devices with none yet, each with why."""
    from modules.nsot import templates_repo

    devices, not_validated = [], []
    for entry in templates_repo.devices_for_template(repo, rel_path):
        golden = _capture(repo, entry["device"])
        if not golden:
            not_validated.append({"device": entry["device"], "reason": "no captured config yet"})
            continue
        devices.append({"device": entry["device"], "platform": entry["platform"],
                        "running_config": golden})
    return devices, not_validated


def _seen(results: list, not_validated: list) -> str:
    """What the check's outcome WAS, as the person read it: each device and whether it
    reproduced, and the devices not validated. The confirm carries it back; an approval whose
    evidence moved since (a capture, an acknowledgement, a binding) is refused, naming it."""
    shape = {"passed": sorted(r["device"] for r in results if r.get("ok")),
             "failed": sorted(r["device"] for r in results if not r.get("ok")),
             "not_validated": sorted(n["device"] for n in not_validated)}
    return hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()[:16], shape


def check(list_name: str, rel_path: str) -> dict:
    """The approval's preview: the comparison on every bound device, every failing line, the
    fingerprint the confirm is bound to, and whether at least one device reproduces. Writes
    nothing."""
    from modules.nsot import approval

    repo = repo_for(list_name)
    devices, not_validated = bound_captures(repo, rel_path)
    fingerprint = approval.template_fingerprint(repo, rel_path)["fingerprint"]
    results = approval.validate_template(repo, rel_path, devices)["results"] if devices else []
    seen, shape = _seen(results, not_validated)
    return {"ok": True, "list": list_name, "template": rel_path, "fingerprint": fingerprint,
            "imports": len(approval.template_closure(repo, rel_path)) - 1,
            "results": results, "not_validated": not_validated, "passed": shape["passed"],
            "failed": shape["failed"], "can_approve": bool(shape["passed"]), "seen": seen,
            "covers": approval.COVERS, "does_not_cover": approval.DOES_NOT_COVER}


def approve(list_name: str, rel_path: str, shown: str, actor: str, seen: str = None) -> dict:
    """Approve as *actor* and commit the record. *shown*: the fingerprint the page showed
    (required; a template that moved is refused naming both). *seen*: the check's outcome as
    the person read it (v2's confirm carries it; None for a caller with no preview).
    ``status`` is the HTTP answer."""
    from modules.nsot import approval, repo as repo_service

    shown = shown.strip() if isinstance(shown, str) else ""
    if not shown:
        return {"ok": False, "status": 400, "error": (
            f"Not approved: this page did not say which version of {rel_path} it showed, so "
            "the approval could cover a change made since. Reload and approve again.")}
    repo = repo_for(list_name)
    devices, not_validated = bound_captures(repo, rel_path)
    if seen is not None:
        now = check(list_name, rel_path)
        if now["seen"] != seen:
            return {"ok": False, "status": 409, "check": now, "error": (
                f"Not approved: the check you read is not the check now. Now it validates "
                f"{', '.join(now['passed']) or 'no device'}; fails "
                f"{', '.join(now['failed']) or 'no device'}; cannot validate "
                f"{', '.join(n['device'] for n in now['not_validated']) or 'no device'}. "
                "A capture, an acknowledgement or a binding changed since. Read it again, "
                "then approve.")}
    result = approval.approve(repo, rel_path, devices, actor=actor,
                              not_validated=not_validated, shown=shown)
    if not result["ok"]:
        return {**result, "status": 400}
    commit = repo_service.save_templates(list_name, [".approvals.json"], actor=actor,
                                         message=f"template: approve {rel_path}")
    if not commit.get("ok"):
        # The gate counts an approval once it is COMMITTED (CONCURRENCY_AUDIT R13), so an
        # approval whose commit failed is not one, and this says so instead of "approved".
        return {**result, "ok": False, "status": 500, "error": (
            f"Not approved yet: the approval is in the working record but its commit failed "
            f"({commit.get('error')}), and the deploy gate counts an approval once it is "
            "committed. Approve again.")}
    log.info("approve_op: %s approved %s in %s (commit %s)", actor, rel_path, list_name,
             commit.get("commit", ""))
    return {**result, "status": 200, "commit": commit.get("commit", ""), "actor": actor}


def revoke(list_name: str, rel_path: str, reason: str, actor: str) -> dict:
    """Withdraw the approval with *reason* and commit the record. ``status`` is the HTTP
    answer; a revocation in the working record already refuses deploys, said when its commit
    fails."""
    from modules.nsot import approval, repo as repo_service

    repo = repo_for(list_name)
    result = approval.revoke(repo, rel_path, reason=reason or "", actor=actor)
    if not result.get("ok"):
        return {**result, "status": 400}
    commit = repo_service.save_templates(
        list_name, [".approvals.json"], actor=actor,
        message=f"template: revoke approval for {rel_path}",
        paths=[os.path.join("templates", ".approvals.json")])
    if not commit.get("ok"):
        return {**result, "ok": False, "status": 500, "error": (
            f"Revoked in the working record, so deploys from it are already refused, but "
            f"the commit failed ({commit.get('error')}): the revocation is not in the "
            "repository's history yet. Revoke again to commit it.")}
    log.warning("approve_op: %s revoked %s in %s: %s", actor, rel_path, list_name, reason)
    return {**result, "status": 200, "commit": commit.get("commit", ""), "actor": actor}


def committed_templates(repo: str) -> list:
    """The template paths COMMITTED at HEAD under ``templates/`` (relative to it), sorted: a
    file nobody committed is not drawn as the network's template."""
    from modules.nsot import repo as repo_service, templates_repo

    rc, out, _ = repo_service.git(repo, "ls-tree", "-r", "--name-only", "HEAD",
                                  templates_repo.TEMPLATES_REL + "/")
    if rc != 0:
        return []
    prefix = templates_repo.TEMPLATES_REL + "/"
    return sorted(p[len(prefix):] for p in out.splitlines()
                  if p.startswith(prefix) and p.endswith(".j2"))


def library(list_name: str) -> dict:
    """The page's table: each committed template (a shared macro file is counted, never a
    row: it has no binding and no approval of its own), its platform, imports, the devices
    bound to it, and its approval; with the counts by state."""
    from modules.nsot import approval, templates_repo

    repo = repo_for(list_name)
    try:
        templates_repo.load_bindings(repo)
    except templates_repo.BindingsUnreadable as exc:
        return {"ok": False, "error": str(exc), "rows": [], "counts": {}, "shared": 0}
    paths = committed_templates(repo)
    shared = [p for p in paths if p.split("/")[-1].startswith("_")]
    shipped = _shipped_states(repo)
    rows = []
    for path in paths:
        if path in shared:
            continue
        dialect = path.split("/")[0]
        status = approval.approval_status(repo, path)
        state = ("approved" if status.get("approved") else
                 "revoked" if status.get("revoked") else "not approved")
        rows.append({"path": path, "platform": PLATFORM_WORDS.get(dialect, dialect),
                     "imports": len(approval.template_closure(repo, path)) - 1,
                     "bound": [d["device"] for d in
                               templates_repo.devices_for_template(repo, path)],
                     "status": status, "state": state, "kind": "template",
                     "shipped": shipped.get(path) or _NOT_SHIPPED})
    counts = {s: sum(1 for r in rows if r["state"] == s)
              for s in ("approved", "not approved", "revoked")}
    # A SHARED macro file is a row too (C566, board B): it has no approval or binding of its
    # own, and it is the file that falls behind the shipped version (`_common.j2`, C565).
    for path in shared:
        users = [r for r in rows if path in approval.template_closure(repo, r["path"])]
        rows.append({"path": path, "platform": "shared", "imports": 0,
                     "bound": sorted({d for r in users for d in r["bound"]}),
                     "status": {}, "state": "shared", "kind": "shared",
                     "importers": [r["path"] for r in users],
                     "shipped": shipped.get(path) or _NOT_SHIPPED})
    return {"ok": True, "rows": rows, "counts": counts, "shared": len(shared),
            "behind": sum(1 for r in rows if r["shipped"]["state"] == "stale")}


#: A template the application does not ship (the network's own): nothing to compare.
_NOT_SHIPPED = {"state": "not_shipped", "words": "not a shipped template: the network's own"}
#: Each state against the shipped version, in a person's words (`templates_repo.seed_status`).
SHIPPED_WORDS = {
    "current": "current",
    "stale": "behind: an older shipped version, unedited; the shipped one has changed since",
    "edited": "edited here, on purpose; the shipped file has not moved since",
    "edited_and_stale": ("edited here AND the shipped file has moved since: a merge a person "
                         "makes, not offered as one action"),
}


def _shipped_states(repo: str) -> dict:
    """``{path: {"state", "words"}}`` against the shipped version, from ONE `seed_status` read
    for the page; a file it could not classify says why, never guessed into a state."""
    from modules.nsot import templates_repo

    try:
        report = templates_repo.seed_status(repo)
    except Exception as exc:                            # noqa: BLE001
        log.warning("templates: the shipped versions could not be compared: %s", exc)
        return {}
    out = {f["path"]: {"state": f["state"], "words": SHIPPED_WORDS.get(f["state"], f["state"])}
           for f in report.get("files") or []}
    for f in report.get("unclassified") or []:
        out[f["path"]] = {"state": "unclassified",
                          "words": f"not compared: {f.get('reason') or f['state']}"}
    return out
