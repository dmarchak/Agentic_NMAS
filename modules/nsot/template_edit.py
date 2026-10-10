"""nsot/template_edit.py — a configuration template edited on v2 (cutover blocker 5, 2026-10-10;
the intent editor H's pattern, drawn under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md).

Open: the committed text and the blob it was opened at (the BASE, CONCURRENCY_AUDIT R14), the
devices it governs and its last commit. Check, as typed: the syntax, then the edit rendered for
every device it governs against that device's COMMITTED golden (`approve_op.bound_captures`, the
approval's own inputs; never a backup, C632), each failing line named, in a copy of the library
outside the repository, so a check writes nothing. Commit: bound to the base under the
repository's lock, through `template_write.commit`, the one path today's editor and Bring in
the shipped version share, which revokes every approval over the file in the same commit.

A shared file (`_common.j2`) governs every device bound to a template that imports it, so its
check renders each importer. Nothing here contacts a device.
"""

import logging
import os
import shutil
import tempfile

log = logging.getLogger(__name__)

#: The editor's steps, each named on its manual page (docs/manual/how-it-works/edit-template.md).
STEPS = ("open", "check", "commit", "moved")


def _repo(list_name: str) -> str:
    from modules.nsot import approve_op
    return approve_op.repo_for(list_name)


def governs(repo: str, rel_path: str) -> list:
    """``[(template, [device, ...])]``: the templates whose render *rel_path* takes part in
    (itself, or each importer of a shared file), each with the devices bound to it."""
    from modules.nsot import approval, templates_repo

    names = [t["path"] for t in templates_repo.list_templates(repo)]
    out = []
    for path in names:
        if os.path.basename(path).startswith("_"):
            continue
        if path == rel_path or rel_path in approval.template_closure(repo, path):
            bound = [b["device"] for b in templates_repo.devices_for_template(repo, path)]
            out.append((path, bound))
    return out


def open_doc(list_name: str, rel_path: str) -> dict:
    """``{"ok", "path", "text", "base", "last", "governs", "error"}``: the committed text, read
    FROM the blob handed out as the base (a file not yet committed opens from disk, base "")."""
    from modules.nsot import hostvars, templates_repo

    repo = _repo(list_name)
    base = templates_repo.committed_blob(repo, rel_path)
    text = hostvars.blob_text(repo, base) if base else templates_repo.read_template(repo,
                                                                                   rel_path)
    if text is None:
        return {"ok": False, "path": rel_path,
                "error": f"there is no template {rel_path!r} in {list_name}'s library"}
    return {"ok": True, "path": rel_path, "text": text, "base": base,
            "last": templates_repo.last_commit(repo, rel_path),
            "governs": governs(repo, rel_path), "revokes": revokes(repo, rel_path), "error": ""}


def revokes(repo: str, rel_path: str) -> list:
    """The approvals a commit of *rel_path* revokes: every approved template whose import
    closure holds it (`template_write.commit`'s own test), said before the commit."""
    from modules.nsot import approval

    return sorted(p for p in approval.approved_templates(repo)
                  if rel_path in approval.template_closure(repo, p))


def check(list_name: str, rel_path: str, text: str) -> dict:
    """The edit checked: ``{"ok", "syntax", "changed", "templates": [{"template", "results",
    "not_validated"}], "devices", "passed", "error"}``. Writes nothing in the repository: the
    edit is rendered from a copy of the library in a temporary folder, removed after."""
    from modules.nsot import approval, approve_op, templates_repo

    repo = _repo(list_name)
    ok, error = templates_repo.check_syntax(text)
    out = {"ok": False, "path": rel_path, "syntax": error, "changed": False, "templates": [],
           "devices": 0, "passed": 0, "error": ""}
    if templates_repo._safe_join(repo, rel_path) is None:
        return dict(out, error=f"{rel_path!r} is not a template path in this library")
    committed = open_doc(list_name, rel_path)
    out["changed"] = text != (committed.get("text") or "")
    if not ok:
        return out
    tmp = tempfile.mkdtemp(prefix="nmas-template-check-")
    try:
        root = os.path.join(tmp, "templates")
        shutil.copytree(templates_repo.templates_dir(repo), root)
        dest = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        for template, _bound in governs(repo, rel_path):
            devices, not_validated = approve_op.bound_captures(repo, template)
            got = approval.validate_template(repo, template, devices, template_root=root)
            got.pop("host_vars_by_device", None)
            out["templates"].append({"template": template, "results": got["results"],
                                     "not_validated": not_validated})
    except Exception as exc:                          # noqa: BLE001 (said on the card)
        log.exception("template_edit: the check of %s failed", rel_path)
        return dict(out, error=f"the check could not run: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    results = [r for t in out["templates"] for r in t["results"]]
    out["devices"], out["passed"] = len(results), sum(1 for r in results if r.get("ok"))
    out["ok"] = True
    return out


def commit(list_name: str, rel_path: str, text: str, summary: str, base: str,
           actor: str) -> dict:
    """Commit the edit as *actor*, bound to *base*: ``{"ok", "stage", "status", ...}``. A
    template that moved since it was opened is refused naming both blobs and who moved it
    (``stage`` "moved"); a syntax error, an empty reason or no change is refused, nothing
    written."""
    from modules.nsot import repo as repo_service, template_write, templates_repo

    summary = " ".join((summary or "").split())
    if not summary:
        return {"ok": False, "stage": "summary", "status": 400,
                "error": "say why in one line: it is the commit's subject"}
    ok, error = templates_repo.check_syntax(text)
    if not ok:
        return {"ok": False, "stage": "syntax", "status": 400,
                "error": f"the template does not parse ({error})"}
    repo = _repo(list_name)
    with repo_service.repo_lock(repo):
        current = templates_repo.committed_blob(repo, rel_path)
        if current != (base or "").strip():
            last = templates_repo.last_commit(repo, rel_path)
            return {"ok": False, "stage": "moved", "status": 409, "base": base or "",
                    "current": current, "last_commit": last,
                    "error": (f"{rel_path} changed after you opened it: you opened "
                              f"{(base or '')[:8] or 'a version not yet committed'}, committed "
                              f"now is {current[:8] or 'nothing'}")}
        if current and text == (open_doc(list_name, rel_path).get("text") or ""):
            return {"ok": True, "stage": "unchanged", "status": 200, "changed": False,
                    "path": rel_path}
        got = template_write.commit(list_name, repo, rel_path, text, actor=actor,
                                    message=f"template: {rel_path} {summary}")
    got.setdefault("stage", "committed" if got.get("ok") else "write")
    got["changed"] = bool(got.get("ok"))
    return got
