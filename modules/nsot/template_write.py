"""nsot/template_write.py — write one template into a network's library and commit it, with the
approvals it ends (C566).

The one code path today's template editor (`routes/templates.py`, `write_template`) and v2's
Templates › Bring in the shipped version (`template_bring.bring`) share. Called under the
repository's lock by the caller, which has already compared the version it was shown.

Editing a template changes its content hash, so every approval whose import closure holds the
file no longer matches its fingerprint: each is REVOKED with the reason, not left standing
(`_common.j2` holds the macros for both platforms, so revoking only it, which has no approval of
its own, would leave every base template approved over content nobody validated). The
revocations are committed WITH the template (CONCURRENCY_AUDIT R13).
"""

import logging

log = logging.getLogger(__name__)


def commit(list_name: str, repo: str, rel_path: str, content: str, *, actor: str,
           message: str = "", why: str = "") -> dict:
    """Write *content* at *rel_path* in the library, revoke every approval over it with *why*
    (or "was edited"), and commit both. ``{"ok", "status", "path", "commit", "revoked",
    "not_revoked", "approval_revoked", "error", "stage"}``; ``status`` is the HTTP status a
    route answers with."""
    from modules.nsot import approval, repo as repo_service, templates_repo

    result = templates_repo.write_template(repo, rel_path, content)
    if not result["ok"]:
        return dict(result, status=400)

    revoked, not_revoked = [], []
    for stored_path in approval.approved_templates(repo):
        if rel_path in approval.template_closure(repo, stored_path):
            done = approval.revoke(
                repo, stored_path,
                reason=(f"'{rel_path}' {why or 'was edited'}, and this template imports it; "
                        "re-approval must validate the new content against every bound "
                        "device"),
                actor=actor)
            (revoked if done.get("ok") else not_revoked).append(stored_path)

    got = repo_service.save_templates(
        list_name, [rel_path] + ([".approvals.json"] if revoked else []),
        actor=actor, message=message)
    if not got.get("ok"):
        return {"ok": False, "status": 500, "path": rel_path, "revoked": revoked,
                "error": (f"The template is written but its commit failed ({got.get('error')}): "
                          "it is not in the repository's history. The deploy gate already "
                          "counts the edited template as unapproved.")}
    return {"ok": True, "status": 200, "path": rel_path, "commit": got.get("commit", ""),
            "approval_revoked": bool(revoked), "revoked": revoked, "not_revoked": not_revoked}
