"""nsot/archive.py

Off-host durability for the NSoT repo: an optional git remote and an optional
S3-compatible archive.

Both are registered as **post-commit hooks**, so they run on a background
thread with short timeouts, never hold the repo lock, and never delay or roll
back a commit. Git is the system of record; S3 is the archive. A failure shows
on the integration badge and in the log.
"""

import logging
import os

log = logging.getLogger(__name__)


def push_hook(context: dict) -> dict:
    """Push to this LIST's remote, if there is one and auto-push is on.

    Reads ``data/lists/{slug}/remote.json`` rather than the global settings:
    one repository per network cannot be expressed by one global URL, and two
    lists pushing to each other's repositories is a silent catastrophe.

    **Auto-push must not widen what is published.** Every commit is re-scanned
    before it goes: if it introduces a gated kind that nobody acknowledged, or
    raises the count of one that was acknowledged, the push is HELD and a
    person is asked to re-acknowledge in the UI. Ordinary commits — a golden
    change carrying no new exposure — push as before.

    Holding is both the conservative direction and the recoverable one. The
    commit is already safe locally and nothing is lost by waiting; a push is
    irreversible, and a credential published by an unattended hook cannot be
    unpublished.
    """
    from modules.nsot import remote as R
    from modules.nsot.repo import git

    # NO remote.json, NO push. There is deliberately no fallback to the global
    # `nsot_git_remote_url`.
    #
    # A global URL cannot express one repository per network, so a second list
    # without its own remote.json would push into whatever repository the
    # global happens to name — one network's history landing in another's,
    # silently. That is the exact failure the per-list design exists to
    # prevent, and leaving a fallback in place would have reintroduced it for
    # precisely the lists that had not been configured yet.
    #
    # The setting key is not deleted (settings keys never are); it is simply
    # no longer read here.
    list_name = context.get("list_name", "")
    config = R.load_remote(list_name) if list_name else None
    if config is None:
        return {"ok": True, "message": (
            f"no remote configured for '{list_name or '(unknown list)'}' — "
            f"nothing pushed")}

    decision = R.auto_push_decision(list_name, context.get("repo", ""))
    if not decision["push"]:
        if decision.get("held"):
            log.warning("archive: auto-push HELD for '%s': %s", list_name,
                        decision["reason"])
            return {"ok": False, "held": True, "error": (
                f"auto-push held — {decision['reason']}. A person must "
                f"re-acknowledge publication in the UI before this commit "
                f"is pushed.")}
        return {"ok": True, "message": decision["reason"]}

    remote = R.remote_url(config)
    branch = config.get("branch", "main") or "main"
    repo = context["repo"]

    rc, _, _ = git(repo, "remote", "get-url", "origin")
    if rc != 0:
        git(repo, "remote", "add", "origin", remote)

    # The branch, then EXACTLY the tags this save created -- one explicit
    # refspec each, named by the caller.
    #
    # `--follow-tags` used to carry them, and measurement showed it carries
    # too much: it publishes every annotated tag reachable from the pushed
    # ref that the remote lacks, so an unrelated older tag rides along with
    # whatever commit happens to be pushed next. Publishing is irreversible,
    # so what goes out is named rather than computed from reachability.
    #
    # `--tags` would be worse again, and is never used here: it publishes
    # every local tag in the repository.
    rc, _, err = git(repo, "push", "origin", f"HEAD:refs/heads/{branch}")
    if rc != 0:
        if "non-fast-forward" in err or "rejected" in err:
            # Never force-push: surface the conflict and stop.
            reason = ("remote has commits this repo does not — resolve the "
                      "divergence manually; NMAS will not force-push")
        else:
            reason = err[:300]
        R.record_push_failure(list_name, actor="auto-push", reason=reason)
        return {"ok": False, "error": reason}

    tags = [t for t in (context.get("tags") or []) if t]
    pushed_tags = []
    for tag in tags:
        # One tag per invocation, so a single bad ref cannot take the others
        # with it, and the failure names which tag.
        rc, _, err = git(repo, "push", "origin",
                         f"refs/tags/{tag}:refs/tags/{tag}")
        if rc != 0:
            log.warning("archive: tag %s not pushed: %s", tag, err[:200])
            continue
        pushed_tags.append(tag)

    # Recorded here because auto-push never went through remote.push(), so
    # nothing wrote `last_push` for it. The card then showed whenever somebody
    # last clicked Push, which reads as "nothing has been published since" and
    # is a different claim entirely.
    #
    # `kind` says which this was: with no new commit the branch push is a
    # no-op and the baseline tag is the entire publication.
    head = ""
    rc_head, out_head, _ = git(repo, "rev-parse", "HEAD")
    if rc_head == 0:
        head = (out_head or "").strip()
    # Tag-only iff the caller published tags for no devices -- which is
    # exactly `save_golden()`'s no-commit baseline path. A golden commit names
    # its changed devices; a template commit names no tags.
    tag_only = bool(pushed_tags) and not context.get("devices")
    R.record_push(list_name, actor="auto-push", branch=branch, commit=head,
                  tags=pushed_tags, kind="tags" if tag_only else "commit")

    message = f"pushed to {branch}"
    if tags:
        message += f", {len(pushed_tags)}/{len(tags)} tag(s)"
    return {"ok": True, "message": message, "tags_pushed": pushed_tags}


def s3_archive_hook(context: dict) -> dict:
    """Upload changed golden configs to the S3-compatible archive."""
    from modules.integrations.s3_archive import S3ArchiveIntegration
    from modules.nsot.repo import _safe_name
    from modules.settings_schema import get_setting

    integration = S3ArchiveIntegration()
    if not integration.is_configured():
        return {"ok": True, "message": "S3 not configured"}

    try:
        from minio import Minio
    except ImportError:
        return {"ok": False, "error": "minio SDK not installed"}

    from modules.secrets_store import get_secret

    endpoint = integration.url
    host = endpoint.split("://", 1)[-1]
    bucket = get_setting("s3_bucket", "")
    prefix = (get_setting("s3_prefix", "") or "").strip("/")
    repo = context["repo"]
    sha = context.get("sha", "")

    try:
        client = Minio(host,
                       access_key=get_secret("s3_access_key"),
                       secret_key=get_secret("s3_secret_key"),
                       secure=endpoint.startswith("https://"),
                       region=get_setting("s3_region", "") or None)
    except Exception as exc:                  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    stamp = next((t.rsplit("/", 1)[-1] for t in context.get("tags", [])
                  if t.startswith("baseline/")), sha[:12])
    uploaded, failed = [], []

    for hostname in context.get("devices", []):
        rel = f"golden/{_safe_name(hostname)}.cfg"
        path = os.path.join(repo, rel)
        if not os.path.exists(path):
            continue
        key = "/".join(filter(None, [prefix, "golden", _safe_name(hostname),
                                     f"{stamp}.cfg"]))
        try:
            client.fput_object(bucket, key, path, metadata={
                "x-amz-meta-commit": sha,
                "x-amz-meta-source": context.get("source", ""),
                "x-amz-meta-actor":  context.get("actor", ""),
            })
            uploaded.append(key)
        except Exception as exc:              # noqa: BLE001
            failed.append(f"{hostname}: {exc}")

    if failed:
        return {"ok": False, "error": "; ".join(failed)[:300]}
    return {"ok": True, "message": f"archived {len(uploaded)} config(s)"}


def register_default_hooks() -> None:
    """Register push and archive. Idempotent."""
    from modules.nsot.hooks import register
    register("git-push", push_hook, timeout=30)
    register("s3-archive", s3_archive_hook, timeout=60)
