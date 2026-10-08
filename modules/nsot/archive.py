"""nsot/archive.py

Off-host durability for the NSoT repo: an optional git remote and an optional
S3-compatible archive.

Both are registered as **post-commit hooks**, so they run on a background
thread with short timeouts, never hold the repo lock, and never delay or roll
back a commit. Git is the system of record; S3 is the archive. A failure shows
on the integration badge and in the log.
"""

import io
import logging

log = logging.getLogger(__name__)


#: The tag namespaces the tool creates, each meant for publication with its
#: commit (`repo.save_golden`, `golden_state`).
TOOL_TAG_PATTERNS = ("baseline/*", "golden/*", "golden-state/*")


def unpushed_tool_tags(repo: str, remote: str = "origin", timeout: int = 30) -> list:
    """The tool's tags that ``remote`` lacks and that name a commit HEAD holds,
    sorted, leaving out a WITHDRAWN baseline (C177: deleted on the remote on
    purpose). The publication reader's measurement; the push hook never
    publishes from it. ``[]`` when the remote cannot be asked."""
    from modules.nsot.record_exceptions import withdrawn_baseline
    from modules.nsot.repo import git

    rc, out, _ = git(repo, "tag", "-l", *TOOL_TAG_PATTERNS)
    local = [t for t in out.splitlines() if t.strip()] if rc == 0 else []
    if not local:
        return []
    import subprocess

    try:
        got = subprocess.run(["git", "-C", repo, "ls-remote", "--tags", remote],
                             capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return []
    if got.returncode != 0:
        return []
    there = {l.split("refs/tags/", 1)[1] for l in got.stdout.splitlines()
             if "refs/tags/" in l and not l.endswith("^{}")}
    out = []
    for t in local:
        if t in there:
            continue
        rc, sha, _ = git(repo, "rev-parse", f"{t}^{{commit}}")
        if rc != 0 or withdrawn_baseline(sha.strip()):
            continue
        if git(repo, "merge-base", "--is-ancestor", sha.strip(), "HEAD")[0] == 0:
            out.append(t)
    return sorted(out)


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
    config, unreadable = R.config_or_refusal(list_name) if list_name else (None, "")
    if config is None:
        # Absent and unreadable are different states (R18, C172): an unreadable record
        # answered "no remote configured" with ok, and publication stopped behind a success
        # message. The refusal names the file and that nothing is pushed until it is repaired.
        if unreadable:
            log.error("archive: auto-push for '%s' stopped: %s", list_name, unreadable)
            return {"ok": False, "error": unreadable}
        return {"ok": True, "message": (
            f"no remote configured for '{list_name or '(unknown list)'}' — "
            f"nothing pushed")}
    # ONE publisher per repository at a time, across processes (R18): each commit's hook
    # thread pushed on its own, and two pushes could land out of order.
    with R.publish_lock(context.get("repo", "")):
        return _push_locked(context, list_name, config)


def _push_locked(context: dict, list_name: str, config: dict) -> dict:
    from modules.nsot import remote as R
    from modules.nsot.repo import git


    decision = R.auto_push_decision(list_name, context.get("repo", ""))
    if not decision["push"]:
        if decision.get("held"):
            log.warning("archive: auto-push HELD for '%s': %s", list_name,
                        decision["reason"])
            # RECORDED where the publication reader reads it (the operator,
            # 2026-10-01): four held commits read as "not pushed" with no
            # cause for four hours, the reason in this log line alone.
            R.record_push_held(list_name, reason=decision["reason"],
                               needs=decision.get("needs") or "",
                               tags=context.get("tags") or [])
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
    #
    # HEAD is read ONCE, under the publish lock, and that sha is pushed and recorded (R18): a
    # hook for an older commit pushes the newest, never an older one after it.
    rc_head, out_head, _ = git(repo, "rev-parse", "HEAD")
    head = (out_head or "").strip() if rc_head == 0 else ""
    if not head:
        reason = "HEAD could not be read, so nothing was pushed"
        R.record_push_failure(list_name, actor="auto-push", reason=reason,
                              tags=context.get("tags") or [])
        return {"ok": False, "error": reason}
    rc, _, err = git(repo, "push", "origin", f"{head}:refs/heads/{branch}")
    if rc != 0:
        if "non-fast-forward" in err or "rejected" in err:
            # Never force-push: surface the conflict and stop.
            reason = ("remote has commits this repo does not — resolve the "
                      "divergence manually; Mercury will not force-push")
        else:
            reason = err[:300]
        R.record_push_failure(list_name, actor="auto-push", reason=reason,
                              tags=context.get("tags") or [])
        return {"ok": False, "error": reason}

    # The tags this save created, AND the tags an earlier hook call NAMED and
    # could not send (held, or a failed push: `pending_tags`). 2026-10-01: a
    # baseline tagged while auto-push was held was never sent by the push
    # that followed, which sent only ITS save's tags. Still named one by
    # one, never computed from reachability: a tag nobody named (a withdrawn
    # baseline deleted on the remote, an older tag) never rides along. A
    # pending tag deleted here since is dropped.
    named = list(config.get("pending_tags") or [])
    pending = [t for t in named
               if git(repo, "rev-parse", "-q", "--verify", f"refs/tags/{t}")[0] == 0]
    gone = sorted(set(named) - set(pending))
    tags = sorted({t for t in (context.get("tags") or []) if t} | set(pending))
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
    # no-op and the baseline tag is the entire publication. `head` is what was pushed.
    #
    # Tag-only iff the caller published tags for no devices -- which is
    # exactly `save_golden()`'s no-commit baseline path. A golden commit names
    # its changed devices; a template commit names no tags.
    tag_only = bool(context.get("tags")) and not context.get("devices")
    R.record_push(list_name, actor="auto-push", branch=branch, commit=head,
                  tags=pushed_tags, kind="tags" if tag_only else "commit",
                  pending=[t for t in tags if t not in pushed_tags], gone=gone)

    message = f"pushed to {branch}"
    if tags:
        message += f", {len(pushed_tags)}/{len(tags)} tag(s)"
    return {"ok": True, "message": message, "tags_pushed": pushed_tags}


def committed_bytes(repo: str, sha: str, rel: str):
    """The bytes of *rel* at commit *sha*, or None when that commit has no such file."""
    import subprocess

    out = subprocess.run(["git", "-C", repo, "show", f"{sha}:{rel}"], capture_output=True,
                         timeout=60, check=False)
    return out.stdout if out.returncode == 0 else None


def s3_archive_hook(context: dict) -> dict:
    """Upload changed golden configs to the S3-compatible archive."""
    from modules import list_settings
    from modules.integrations.s3_archive import S3ArchiveIntegration
    from modules.nsot.repo import _safe_name

    # The commit's own network (the hook's context carries it): its archive, its keys.
    list_name = context.get("list_name") or ""
    if not list_name:
        return {"ok": False, "error": "the commit's context names no list, so no network's "
                                      "archive can be chosen"}
    integration = S3ArchiveIntegration(list_name=list_name)
    if not integration.is_configured():
        return {"ok": True, "message": "S3 not configured"}

    try:
        from minio import Minio
    except ImportError:
        return {"ok": False, "error": "minio SDK not installed"}

    def net(key, default=None):
        return list_settings.value(list_name, key, default)

    def net_secret(key):
        return list_settings.secret(list_name, key)

    endpoint = integration.url
    host = endpoint.split("://", 1)[-1]
    bucket = net("s3_bucket", "")
    prefix = (net("s3_prefix", "") or "").strip("/")
    repo = context["repo"]
    sha = context.get("sha", "")

    try:
        client = Minio(host,
                       access_key=net_secret("s3_access_key"),
                       secret_key=net_secret("s3_secret_key"),
                       secure=endpoint.startswith("https://"),
                       region=net("s3_region", "") or None)
    except Exception as exc:                  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    stamp = next((t.rsplit("/", 1)[-1] for t in context.get("tags", [])
                  if t.startswith("baseline/")), sha[:12])
    uploaded, failed = [], []

    if not sha:
        return {"ok": False, "error": "the hook named no commit, so nothing was archived"}
    for hostname in context.get("devices", []):
        rel = f"golden/{_safe_name(hostname)}.cfg"
        # The blob AT THE HOOK'S COMMIT (R18): the working file may already hold a later
        # save, and it was uploaded under this commit's sha.
        data = committed_bytes(repo, sha, rel)
        if data is None:
            continue
        key = "/".join(filter(None, [prefix, "golden", _safe_name(hostname),
                                     f"{stamp}.cfg"]))
        try:
            client.put_object(bucket, key, io.BytesIO(data), len(data), metadata={
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


def publication_hook(context: dict) -> dict:
    """Re-read HEAD against the remote now (C223). Imported lazily: the
    reader imports reader_job and settings, which a hook module should not
    pull in at import."""
    from modules.readers.remote_publication import refresh_hook

    return refresh_hook(context)


def register_default_hooks() -> None:
    """Register push and archive. Idempotent."""
    from modules.nsot.hooks import register
    register("git-push", push_hook, timeout=30)
    # After the push, so the re-read sees what the push did (C223): the
    # Remote card, the Git tab and Needs attention then show whether this
    # commit is published without waiting for the reader's next cycle.
    register("publication-check", publication_hook, timeout=30)
    register("s3-archive", s3_archive_hook, timeout=60)
    # A golden commit can change a device's eligibility for a Prometheus
    # target group: wake the targets keeper (a no-op where it does not run).
    from modules.prometheus_targets import golden_hook
    register("prometheus-targets", golden_hook, timeout=15)
    # A commit that earned a baseline writes an event a host service may wait on (C553,
    # Phase 3), rather than polling for the newest baseline on a timer.
    from modules.nsot.baseline_event import hook as baseline_event_hook
    register("baseline-event", baseline_event_hook, timeout=10)
    # A commit that changed a golden asks Oxidized to fetch those devices now,
    # never at its next hourly poll (C314).
    from modules.oxidized_fetch import golden_hook as oxidized_fetch_hook
    register("oxidized-fetch", oxidized_fetch_hook, timeout=30)
