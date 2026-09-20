"""nsot/repo.py

The golden config repository service — the one write path.

Everything that promotes a golden config routes through :func:`save_golden`:
the AI tool, "Save All", auto-create, the approval queue, and the pipeline.

Design points:

* **One call is one commit**, even for a nine-device "Save All". That is a
  network-wide consistent snapshot, not nine unrelated commits.
* **Timestamps and metadata live in git**, not in the file. The file keeps one
  stable header line so existing readers do not break; ``! Saved:`` and
  ``! Source:`` are gone because they created a diff on every save even when
  nothing had changed.
* **Renames are their own commit.** A ``git mv`` mixed with content edits
  defeats git's rename detection, so a pending rename is committed alone,
  immediately before the content commit. That is what keeps
  ``git log --follow -- golden/<new>.cfg`` working across a rename.
* **Identity, not filename.** Devices resolve through ``.nsot/manifest.json``.

Concurrency: one lock per repo serialises every git invocation in-process, and
a stale ``index.lock`` is detected and removed. Post-commit hooks run on a
background thread and never hold the lock.
"""

import logging
import os
import subprocess
import threading
import time

from modules.nsot import manifest as _manifest
from modules.nsot import normalize as _normalize

log = logging.getLogger(__name__)

GIT_TIMEOUT = 30
STALE_LOCK_SECONDS = 120

_repo_locks: dict = {}
_locks_guard = threading.Lock()

VALID_SOURCES = ("manual", "save_all", "pipeline", "approval", "ai",
                 "onboarding", "migration", "rename", "template", "extraction")


class GoldenItem:
    """One device's golden config in a save."""

    def __init__(self, hostname: str, config_text: str, mgmt_ip: str = "",
                 netbox_id=None, device_uid: str = "", platform: str = ""):
        self.hostname = hostname
        self.config_text = config_text
        self.mgmt_ip = mgmt_ip
        self.netbox_id = netbox_id
        self.device_uid = device_uid
        self.platform = platform

    @property
    def identity(self) -> str:
        return _manifest.identity_for(self.netbox_id, self.device_uid)


def repo_lock(repo: str) -> threading.Lock:
    with _locks_guard:
        if repo not in _repo_locks:
            _repo_locks[repo] = threading.Lock()
        return _repo_locks[repo]


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------

def _clear_stale_lock(repo: str) -> None:
    """Remove an abandoned ``.git/index.lock``.

    Multiple writers — UI routes, the approval queue, the background agent —
    used to be able to leave one behind after a crash, wedging every later
    commit.
    """
    lock_path = os.path.join(repo, ".git", "index.lock")
    if not os.path.exists(lock_path):
        return
    try:
        age = time.time() - os.path.getmtime(lock_path)
    except OSError:
        return
    if age > STALE_LOCK_SECONDS:
        try:
            os.remove(lock_path)
            log.warning("repo: removed stale index.lock (%.0fs old) in %s", age, repo)
        except OSError as exc:
            log.error("repo: could not remove stale index.lock: %s", exc)


def _git_env() -> dict:
    """Commit identity from settings. Secrets never go on the command line."""
    from modules.settings_schema import get_setting
    env = os.environ.copy()
    name = get_setting("nsot_git_author_name", "NMAS") or "NMAS"
    email = get_setting("nsot_git_author_email", "nmas@localhost") or "nmas@localhost"
    env.update({
        "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
        "GIT_TERMINAL_PROMPT": "0",
    })
    return env


#: Ignore rules every NSoT repo must carry, whenever it was created.
GITIGNORE_RULES = ("*.swp", "*.tmp", ".nsot/migration-backup/",
                   ".nsot/staging/", ".nsot/migrated.json")


def ensure_repo_hygiene(repo: str) -> None:
    """Bring an existing repo up to date with rules added after it was created.

    ``_ensure_gitignore()`` appends what is missing — but it only ever ran from
    ``init_repo()``, and ``init_repo()`` only ever ran on a write path. A repo
    created before a rule existed therefore never received it, which is the
    same failure one level up: *a rule that never reaches the artifacts that
    already existed*. The live lab repo proved it — created with a two-line
    ``.gitignore``, it committed nine migration backups and then showed the
    marker as untracked.

    Hooking :func:`git` instead means every repo this process touches, read or
    write, is brought up to date on first use. Deliberately not memoised: the
    cost is one small file read against a subprocess spawn, and a memo would
    mean a ``.gitignore`` edited *after* first touch stayed stale for the life
    of the process — reintroducing the bug in a smaller window.
    """
    if not os.path.isdir(os.path.join(repo, ".git")):
        return                                 # not a repo yet; init_repo will
    _ensure_gitignore(repo, list(GITIGNORE_RULES))


def git(repo: str, *args) -> tuple:
    """Run a git command in *repo*. Returns ``(rc, stdout, stderr)``."""
    _clear_stale_lock(repo)
    ensure_repo_hygiene(repo)
    try:
        proc = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, timeout=GIT_TIMEOUT, env=_git_env(),
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git is not installed or not on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"git {args[0] if args else ''} timed out after {GIT_TIMEOUT}s"


def init_repo(repo: str) -> bool:
    """Create the repo and its NSoT layout. Idempotent."""
    os.makedirs(repo, exist_ok=True)
    if not os.path.isdir(os.path.join(repo, ".git")):
        rc, _, _ = git(repo, "init", "-b", "main")
        if rc != 0:
            git(repo, "init")

    for sub in ("golden", "host_vars", "intended", ".nsot", "infra"):
        os.makedirs(os.path.join(repo, sub), exist_ok=True)

    # Windows development, Linux deployment: normalise line endings in the repo.
    attributes = os.path.join(repo, ".gitattributes")
    if not os.path.exists(attributes):
        with open(attributes, "w", encoding="utf-8") as fh:
            fh.write("*.cfg text eol=lf\n*.j2 text eol=lf\n"
                     "*.yml text eol=lf\n*.yaml text eol=lf\n*.json text eol=lf\n")

    _ensure_gitignore(repo, list(GITIGNORE_RULES))

    rc, out, _ = git(repo, "rev-parse", "--verify", "HEAD")
    if rc != 0:
        git(repo, "add", ".gitattributes", ".gitignore")
        git(repo, "commit", "--allow-empty", "-m",
            "Initialize NSoT configuration repository")
    return True


def _ensure_gitignore(repo: str, lines: list) -> None:
    """Make sure every line in *lines* is present, appending what is missing.

    Writing the file only when absent left every repo created before a new
    ignore rule existed without it — silently, since nothing reads the file
    back. Append-if-missing is idempotent and upgrades existing repos.
    """
    path = os.path.join(repo, ".gitignore")
    existing = []
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                existing = [ln.strip() for ln in fh]
        except OSError:
            return
    missing = [ln for ln in lines if ln not in existing]
    if not missing:
        return
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            if existing and existing[-1] != "":
                fh.write("\n")
            fh.write("\n".join(missing) + "\n")
    except OSError as exc:
        log.debug("repo: could not update .gitignore in %s: %s", repo, exc)


# ---------------------------------------------------------------------------
# File content
# ---------------------------------------------------------------------------

def golden_body(hostname: str, mgmt_ip: str, config_text: str) -> str:
    """Render a golden file.

    One stable header line, so existing readers keep working. ``! Saved:`` and
    ``! Source:`` are deliberately absent: they changed on every save and made
    every commit look like a modification even when the config was identical.
    Those facts live in the commit instead.
    """
    body = "\n".join(_normalize.strip_for_repo(config_text)).strip()
    return f"! Golden config — {hostname} ({mgmt_ip})\n{body}\n"


def _content_changed(path: str, new_content: str) -> bool:
    if not os.path.exists(path):
        return True
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read() != new_content
    except OSError:
        return True


# ---------------------------------------------------------------------------
# Renames (amendment 1)
# ---------------------------------------------------------------------------

def apply_pending_renames(repo: str, actor: str = "nmas") -> dict:
    """Commit any renames the inventory refresh recorded.

    Each rename is its own commit containing only the ``git mv``. Mixing a
    rename with content edits defeats git's rename detection and breaks
    ``git log --follow``.
    """
    pending = _manifest.pending_renames(repo)
    if not pending:
        return {"ok": True, "renamed": []}

    renamed = []
    with repo_lock(repo):
        init_repo(repo)
        for item in pending:
            identity = item["identity"]
            old_name, new_name = item["from"], item["to"]
            old_rel = f"golden/{_safe_name(old_name)}.cfg"
            new_rel = f"golden/{_safe_name(new_name)}.cfg"
            old_abs = os.path.join(repo, old_rel)

            if not os.path.exists(old_abs):
                # Nothing committed for this device yet; just record the name.
                _manifest.clear_pending_rename(repo, identity, new_name, new_rel)
                continue

            rc, _, err = git(repo, "mv", "-f", old_rel, new_rel)
            if rc != 0:
                log.error("repo: git mv %s -> %s failed: %s", old_rel, new_rel, err)
                continue

            message = (
                f"rename: {old_name} → {new_name}\n\n"
                f"Device-Id: {identity}\n"
                f"Device-Name: {new_name}\n"
                f"Previous-Name: {old_name}\n"
                f"Source: rename\n"
                f"Actor: {actor}\n"
            )
            # Update the manifest BEFORE staging, and stage .nsot with it.
            # Clearing the rename afterwards left the manifest out of the
            # rename commit entirely: a clone or bundle restore at that commit
            # got a manifest still naming the old file, so every lookup fell
            # through to the deprecated legacy header scan. The move has
            # already happened on disk, so the manifest is correct either way —
            # what matters is that the commit carries it.
            _manifest.clear_pending_rename(repo, identity, new_name, new_rel)
            git(repo, "add", "-A", "golden", ".nsot")
            rc, _, err = git(repo, "commit", "-m", message)
            if rc != 0:
                log.error("repo: rename commit failed: %s", err)
                continue

            renamed.append({"identity": identity, "from": old_name, "to": new_name})
            log.info("repo: renamed %s → %s (history preserved via git mv)",
                     old_name, new_name)

    return {"ok": True, "renamed": renamed}


def _safe_name(hostname: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in (hostname or ""))


# ---------------------------------------------------------------------------
# The one write path
# ---------------------------------------------------------------------------

class IdentityRequired(ValueError):
    """A save reached the repo with no identity for a device the manifest knows."""


def resolve_identity(repo: str, item, allow_new: bool):
    """The identity this item's device already has, or a new one if permitted.

    Minting happens in exactly one place, and this is it — gated. The previous
    behaviour was ``identity = item.identity or _manifest.new_device_uid()``,
    one line, and it meant a caller that simply *forgot* to pass an identity
    got a brand-new device instead of an error. The first successful deploy did
    exactly that: s4 gained a second manifest entry, with an empty platform,
    for a device the manifest had known since migration.

    A function that creates identity when none is supplied will always mask a
    caller that forgot to supply it. Same shape as intent derived from current
    state: the fallback is indistinguishable from the correct answer, so the
    bug cannot surface.
    """
    if item.identity:
        return item.identity

    identity, _entry = _manifest.find_by_ip(repo, item.mgmt_ip)
    if not identity:
        identity, _entry = _manifest.find_by_name(repo, item.hostname)
    if identity:
        return identity

    if allow_new:
        return _manifest.new_device_uid()

    raise IdentityRequired(
        f"{item.hostname} ({item.mgmt_ip or 'no ip'}) reached save_golden with "
        "no identity and is not in the manifest. Pass the device's identity, or "
        "call with allow_new=True if this really is a device being onboarded "
        "for the first time.")


def save_golden(list_name: str, items: list, source: str = "manual",
                actor: str = "nmas", message: str = "", allow_new: bool = True,
                pipeline_id: str = None) -> dict:
    """Promote golden configs for one or more devices in a single commit.

    Returns ``{"ok", "commit", "changed", "unchanged", "tags", "renamed", "error"}``.
    An unchanged device produces no commit but is still reported.
    """
    from modules.config import get_list_data_dir

    if source not in VALID_SOURCES:
        source = "manual"
    repo = os.path.join(get_list_data_dir(list_name), "config_repo")

    rename_result = apply_pending_renames(repo, actor)

    changed, unchanged = [], []
    with repo_lock(repo):
        init_repo(repo)
        os.makedirs(os.path.join(repo, "golden"), exist_ok=True)

        for item in items:
            try:
                identity = resolve_identity(repo, item, allow_new)
            except IdentityRequired as exc:
                log.error("repo: %s", exc)
                return {"ok": False, "error": str(exc), "changed": [],
                        "unchanged": unchanged, "tags": [],
                        "renamed": rename_result["renamed"]}
            rel = f"golden/{_safe_name(item.hostname)}.cfg"
            abs_path = os.path.join(repo, rel)
            content = golden_body(item.hostname, item.mgmt_ip, item.config_text)

            _manifest.upsert_device(repo, identity, item.hostname, item.mgmt_ip,
                                    netbox_id=item.netbox_id,
                                    platform=item.platform, golden=rel)

            if not _content_changed(abs_path, content):
                unchanged.append(item.hostname)
                continue

            with open(abs_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
            changed.append({"hostname": item.hostname, "identity": identity,
                            "path": rel})

        if not changed:
            return {"ok": True, "commit": "", "changed": [],
                    "unchanged": unchanged, "tags": [],
                    "renamed": rename_result["renamed"],
                    "message": "No content changed — no commit created."}

        git(repo, "add", "-A", "golden", ".nsot")

        names = ", ".join(c["hostname"] for c in changed)
        subject = message or (
            f"golden: baseline {len(changed)} device(s) via {source}"
            + (f" {pipeline_id}" if pipeline_id else "")
        )
        trailers = [
            f"Source: {source}",
            f"Actor: {actor}",
            f"Devices: {','.join(c['hostname'] for c in changed)}",
        ]
        for c in changed:
            trailers.append(f"Device-Id: {c['identity']}")
            trailers.append(f"Device-Name: {c['hostname']}")
        if pipeline_id:
            trailers.append(f"Pipeline-Id: {pipeline_id}")

        commit_message = f"{subject}\n\n" + "\n".join(trailers) + "\n"
        rc, _, err = git(repo, "commit", "-m", commit_message)
        if rc != 0:
            return {"ok": False, "error": f"commit failed: {err}",
                    "changed": [], "unchanged": unchanged, "tags": []}

        _, sha, _ = git(repo, "rev-parse", "HEAD")

        # Annotated tags are the "golden config saved with timestamp" the lab
        # asks for. UTC basic ISO, no colons, so they are valid ref names.
        # The stamp has one-second resolution, so two saves in the same second
        # would collide and the second would silently lose its tag — hence the
        # short-sha suffix on collision.
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        tags = []
        for c in changed:
            tag = _unique_tag(repo, f"golden/{_safe_name(c['hostname'])}/{stamp}", sha)
            if git(repo, "tag", "-a", tag, "-m",
                   f"golden {c['hostname']} via {source}")[0] == 0:
                tags.append(tag)
        if source in ("save_all", "migration") or len(changed) > 1:
            baseline = _unique_tag(repo, f"baseline/{stamp}", sha)
            if git(repo, "tag", "-a", baseline, "-m",
                   f"network baseline — {len(changed)} device(s) via {source}")[0] == 0:
                tags.append(baseline)

        _prune_device_tags(repo, [c["hostname"] for c in changed])
        git(repo, "gc", "--auto")

    log.info("repo: saved golden for %d device(s) in '%s' — %s (%d unchanged)",
             len(changed), list_name, sha[:8], len(unchanged))

    from modules.nsot.hooks import run_post_commit
    run_post_commit({"list_name": list_name, "repo": repo, "sha": sha,
                     "source": source, "actor": actor, "tags": tags,
                     "devices": [c["hostname"] for c in changed]})

    return {"ok": True, "commit": sha, "changed": [c["hostname"] for c in changed],
            "unchanged": unchanged, "tags": tags,
            "renamed": rename_result["renamed"], "error": ""}


def _unique_tag(repo: str, tag: str, sha: str) -> str:
    """Return *tag*, suffixed with a short sha if that name already exists."""
    rc, _, _ = git(repo, "rev-parse", "--verify", f"refs/tags/{tag}")
    if rc != 0:
        return tag
    return f"{tag}-{sha[:7]}"


def _commit_paths(list_name: str, paths: list, subject: str, trailers: list,
                  source: str) -> dict:
    """Stage and commit specific paths. Shared plumbing for non-golden commits.

    Deliberately does **not** create ``golden/<device>`` or ``baseline/`` tags:
    those mark a network snapshot, and a template or host_vars change is not
    one. Phase 2's restore reads ``golden/*`` at a ref, so a template commit
    must never be mistakable for a golden promotion.
    """
    from modules.config import get_list_data_dir

    repo = os.path.join(get_list_data_dir(list_name), "config_repo")
    with repo_lock(repo):
        init_repo(repo)
        for path in paths:
            git(repo, "add", "-A", path)

        rc, out, _ = git(repo, "status", "--porcelain")
        if not out.strip():
            return {"ok": True, "commit": "", "changed": [],
                    "message": "No changes to commit."}

        message = f"{subject}\n\n" + "\n".join(
            trailers + [f"Source: {source}"]) + "\n"
        rc, _, err = git(repo, "commit", "-m", message)
        if rc != 0:
            return {"ok": False, "error": f"commit failed: {err}"}
        _, sha, _ = git(repo, "rev-parse", "HEAD")
        git(repo, "gc", "--auto")

    changed = [l.split()[-1] for l in out.splitlines() if l.strip()]
    log.info("repo: %s commit %s in '%s' (%d path(s))",
             source, sha[:8], list_name, len(changed))

    from modules.nsot.hooks import run_post_commit
    run_post_commit({"list_name": list_name, "repo": repo, "sha": sha,
                     "source": source, "tags": [], "devices": []})
    return {"ok": True, "commit": sha, "changed": changed}


def save_templates(list_name: str, files: list, actor: str = "user",
                   message: str = "", paths: list = None) -> dict:
    """Commit template-library changes.

    Separate from :func:`save_golden` in every way that matters: its own
    subject namespace (``template:`` rather than ``golden:``), its own
    ``Source`` trailer, and **no tags**. They share the lock and the plumbing
    and nothing else.

    *files* names the change for the subject and trailer. *paths* is what gets
    staged, defaulting to the whole ``templates`` tree; pass specific paths when
    a commit must not sweep in unrelated work sitting in the same directory.
    """
    names = ", ".join(files) if files else "templates"
    subject = message or f"template: update {names}"
    trailers = [f"Actor: {actor}", f"Template-Files: {','.join(files)}"]
    return _commit_paths(list_name, paths or ["templates"], subject,
                         trailers, "template")


def save_host_vars(list_name: str, devices: list, actor: str = "user",
                   message: str = "") -> dict:
    """Commit extracted ``host_vars`` after human review.

    Phase 3a writes extractions to a gitignored staging area precisely so that
    this — the first commit of a device's modelled configuration — has a person
    looking at a diff first.
    """
    names = ", ".join(devices) if devices else "devices"
    subject = message or f"host_vars: commit extraction for {names}"
    trailers = [f"Actor: {actor}", f"Devices: {','.join(devices)}"]
    return _commit_paths(list_name, ["host_vars"], subject, trailers, "extraction")


def _prune_device_tags(repo: str, hostnames: list) -> None:
    """Amendment 4: keep the last N per-device tags; baselines are never pruned.

    Commits keep full history regardless — only the tag refs are trimmed.
    """
    from modules.settings_schema import get_setting
    keep = get_setting("nsot_device_tag_retention", 50)
    try:
        keep = int(keep)
    except (TypeError, ValueError):
        keep = 50
    if keep <= 0:
        return

    for hostname in hostnames:
        prefix = f"golden/{_safe_name(hostname)}/"
        rc, out, _ = git(repo, "tag", "--list", f"{prefix}*")
        if rc != 0:
            continue
        tags = sorted(t for t in out.splitlines() if t.strip())
        for stale in tags[:-keep] if len(tags) > keep else []:
            git(repo, "tag", "-d", stale)
            log.debug("repo: pruned old tag %s", stale)


# ---------------------------------------------------------------------------
# Reading history
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%H%x1f%cI%x1f%(trailers:key=Source,valueonly)%x1f%(trailers:key=Actor,valueonly)%x1f%s"


def golden_history(repo: str, hostname: str, limit: int = 50) -> list:
    """Promotion timeline for one device, following renames."""
    rel = f"golden/{_safe_name(hostname)}.cfg"
    rc, out, _ = git(repo, "log", "--follow", f"--format={_LOG_FORMAT}%x1e",
                     f"-{limit}", "--", rel)
    if rc != 0 or not out:
        return []
    entries = []
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) < 5:
            continue
        entries.append({"sha": parts[0], "timestamp": parts[1],
                        "source": parts[2].strip(), "actor": parts[3].strip(),
                        "subject": parts[4]})
    return entries


def golden_at(repo: str, hostname: str, ref: str):
    """The golden config for *hostname* as of *ref*."""
    rel = f"golden/{_safe_name(hostname)}.cfg"
    rc, out, _ = git(repo, "show", f"{ref}:{rel}")
    return out if rc == 0 else None


def list_baselines(repo: str) -> list:
    """Network-wide restore points, newest first."""
    # `git tag --format` does not expand %x1f — that is a `git log` feature —
    # so use a literal separator that cannot occur in a ref name or subject.
    sep = "@@|@@"
    rc, out, _ = git(repo, "tag", "--list", "baseline/*",
                     f"--format=%(refname:short){sep}%(creatordate:iso-strict){sep}%(subject)")
    if rc != 0 or not out:
        return []
    baselines = []
    for line in out.splitlines():
        parts = line.split(sep)
        if len(parts) >= 3:
            baselines.append({"tag": parts[0], "created": parts[1], "subject": parts[2]})
    return sorted(baselines, key=lambda b: b["created"], reverse=True)


def devices_at(repo: str, ref: str) -> list:
    """Device names with a golden config at *ref*."""
    rc, out, _ = git(repo, "ls-tree", "--name-only", f"{ref}:golden")
    if rc != 0 or not out:
        return []
    return [os.path.splitext(n)[0] for n in out.splitlines() if n.endswith(".cfg")]


def add_ci_note(repo: str, sha: str, job: str, build: int, result: str,
                url: str = "") -> dict:
    """Attach CI evidence to the exact commit it validated (``refs/notes/ci``)."""
    note = f"job={job}\nbuild={build}\nresult={result}\nurl={url}\n"
    with repo_lock(repo):
        rc, _, err = git(repo, "notes", "--ref=ci", "add", "-f", "-m", note, sha)
    if rc != 0:
        return {"ok": False, "error": err}
    return {"ok": True}


def get_ci_note(repo: str, sha: str):
    rc, out, _ = git(repo, "notes", "--ref=ci", "show", sha)
    if rc != 0 or not out:
        return None
    note = {}
    for line in out.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            note[key.strip()] = value.strip()
    return note
