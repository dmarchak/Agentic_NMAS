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
    """Push to the configured remote, if there is one and auto-push is on."""
    from modules.nsot.repo import git
    from modules.settings_schema import get_setting

    remote = (get_setting("nsot_git_remote_url", "") or "").strip()
    if not remote or not get_setting("nsot_git_auto_push", False):
        return {"ok": True, "message": "push not configured"}

    repo = context["repo"]
    branch = get_setting("nsot_git_branch", "main") or "main"

    rc, _, _ = git(repo, "remote", "get-url", "origin")
    if rc != 0:
        git(repo, "remote", "add", "origin", remote)

    # --follow-tags carries the annotated golden/baseline tags with the commit.
    rc, _, err = git(repo, "push", "--follow-tags", "origin", branch)
    if rc != 0:
        if "non-fast-forward" in err or "rejected" in err:
            # Never force-push: surface the conflict and stop.
            return {"ok": False, "error": (
                "remote has commits this repo does not — resolve the divergence "
                "manually; NMAS will not force-push")}
        return {"ok": False, "error": err[:300]}
    return {"ok": True, "message": f"pushed to {branch}"}


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
